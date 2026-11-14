"""Separate native DSML invocations from the answer in a forced tool-free round."""
from __future__ import annotations

import re


_PIPE = r"[|｜]{1,2}"
_NAMESPACE = _PIPE + r"DSML" + _PIPE + r"[ \t]*"
_NAMES = r"function_calls|tool_calls|calls|invoke|parameter"
_TOKEN = re.compile(r"(?P<code>`+|~{3,})|<" + _NAMESPACE + r"(?P<tag>" + _NAMES + r")\b", re.I)
_EOS = re.compile(r"\s*<" + _PIPE + r"end▁of▁sentence" + _PIPE + ">")
_INCOMPLETE = re.compile(r"</?" + _PIPE + r"DSML[|｜]{0,2}[ \t]*[a-z_]*\Z", re.I)


def visible_final_reply(text: str) -> tuple[str, bool]:
    """Return answer text and whether a native invocation was suppressed.

    The caller joins this one model round before publishing a delta, so a
    network chunk cannot expose half a protocol tag. Ordinary answers (including
    literal Markdown code examples) retain their original text.
    """
    output = []
    copied = position = 0
    code = ""
    suppressed = False
    while match := _TOKEN.search(text, position):
        position = match.end()
        delimiter = match.group("code")
        if delimiter:
            if not code:
                code = delimiter
            elif delimiter == code or (len(code) >= 3 and delimiter.startswith(code)):
                code = ""
            continue
        if code:
            continue
        output.append(text[copied:match.start()])
        suppressed = True
        tag = match.group("tag")
        closing = re.compile(r"</" + _NAMESPACE + tag + r"[ \t]*>", re.I).search(text, position)
        if closing is None:
            # Truncated invocations never become user text, including their arguments.
            return "".join(output), True
        eos = _EOS.match(text, closing.end())
        copied = position = eos.end() if eos else closing.end()
    remainder = text[copied:]
    partial = None if code else _INCOMPLETE.search(remainder)
    if partial:
        remainder = remainder[:partial.start()]
        suppressed = True
    output.append(remainder)
    return "".join(output), suppressed
