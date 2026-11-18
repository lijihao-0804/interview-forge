"""Point cited recall results back to their exact stored character ranges."""
from __future__ import annotations

import hashlib
import re
from contextlib import closing
from pathlib import Path
from typing import TypedDict

from interview_forge.core.runtime import server_runtime


class HistorySource(TypedDict):
    message_id: int
    offset: int
    length: int
    sha256: str


_CITED_ID = re.compile(
    r"(?:消息|\bmessage)\s*(?:ID|编号)?\s*[：:]?\s*[#＃]?\s*(\d{1,19})(?!\d)|[#＃]\s*(\d{1,19})(?!\d)", re.I,
)
_NON_MESSAGE_NUMBER = re.compile(r"(?:力扣|题(?:目|号)?|(?<![a-z])(?:leetcode|lc|problem|exercise|issue|pr))\s*$", re.I)
_QUOTED_TEXT = re.compile(
    r"「([^」\n]+)」|『([^』\n]+)』|“([^”\n]+)”|‘([^’\n]+)’|\"([^\"\n]+)\"|(?<![a-z0-9])'([^'\n]+)'(?![a-z0-9])", re.I,
)
_CLAUSE = re.compile(r"[^\n；;，,、。.!?！？]+")
_SOURCE_LABEL = re.compile(
    r"(?:详见|参见|参阅|见|出自|来源|出处|原文|参考|和|与|及|and|see|sources?|references?|"
    r"[\s:：()（）\[\]【】*—-])*", re.I,
)
_QUOTE_INTRO = re.compile(r"(?:原[话句文](?:是|为)?|(?:写|说|答)(?:道|的是|着|过)|引文|said|wrote|reads?)\s*[：:]*\s*$", re.I)
_QUOTE_CREDIT = re.compile(r"\s*[（(【\[]\s*(?:(?:来源|出处|source)\s*[：:]?\s*)?(?:" + _CITED_ID.pattern + ")", re.I)


def _quoted_claims(passage: str) -> list[str]:
    quotes = list(_QUOTED_TEXT.finditer(passage))
    # A quoted category or technical term in the same clause does not
    # establish another original when the author explicitly marks the quote.
    attributed = [quote for quote in quotes if
                  _QUOTE_INTRO.search(passage, max(0, quote.start() - 48), quote.start())
                  or _QUOTE_CREDIT.match(passage, quote.end())]
    return [next(part for part in quote.groups() if part) for quote in attributed or quotes]


def _citation_passages(answer: str) -> dict[int, list[str]]:
    # Use matching offsets into the original answer. A number or comma in a
    # quotation belongs to the source text, not the answer's citation syntax.
    structure = _QUOTED_TEXT.sub(lambda m: " " * len(m.group()), answer)
    clauses = []
    for part in _CLAUSE.finditer(structure):
        text = answer[part.start():part.end()]
        if text.strip():
            masked = part.group()
            ids = {int(m[1] or m[2]) for m in _CITED_ID.finditer(masked)
                   if m[1] or not _NON_MESSAGE_NUMBER.search(masked, max(0, m.start() - 32), m.start())}
            clauses.append((text, ids))
    passages: dict[int, list[str]] = {}
    for i, (passage, ids) in enumerate(clauses):
        if not ids:
            continue
        if not _QUOTED_TEXT.search(passage):
            previous = clauses[i - 1] if i else ("", set())
            following = clauses[i + 1] if i + 1 < len(clauses) else ("", set())
            before = previous[0] if not previous[1] and _QUOTED_TEXT.search(previous[0]) else ""
            after = following[0] if not following[1] and _QUOTED_TEXT.search(following[0]) else ""
            if _QUOTE_INTRO.search(passage) and after:
                passage = after
            elif _SOURCE_LABEL.fullmatch(_CITED_ID.sub("", passage)) and (before or after):
                # A separate source caption normally follows the quotation.
                # Without a directional label, two neighbouring quotes compete.
                if before and after and not re.search(r"来源|出处|出自|见|\b(?:source|see|reference)", passage, re.I):
                    continue
                passage = before or after
        if len(ids) == 1:
            passages.setdefault(next(iter(ids)), []).append(passage)
        elif not _QUOTED_TEXT.search(passage):
            # An unquoted list can cite individual messages, but cannot
            # establish which of several excerpts within one was intended.
            for mid in ids:
                passages.setdefault(mid, []).append("")
    return passages


def cited_history_sources(answer: str, visible_items: list[dict]) -> tuple[HistorySource, ...]:
    if not visible_items:
        return ()
    passages = _citation_passages(answer)
    ranges: dict[int, dict[tuple[int, str], None]] = {}
    # The caller supplies only results still visible at final model admission.
    for item in visible_items:
        if not isinstance(item, dict):
            continue
        mid, start, excerpt = item.get("message_id"), item.get("offset"), item.get("excerpt")
        if type(mid) is not int or mid not in passages or type(start) is not int or start < 0:
            continue
        if not isinstance(excerpt, str) or not 0 < len(excerpt) <= 320:
            continue
        ranges.setdefault(mid, {})[(start, excerpt)] = None
    sources = []
    for mid, candidates in ranges.items():
        associated = "\n".join(passages[mid])
        quotations = [quote for passage in passages[mid] for quote in _quoted_claims(passage)]
        for start, excerpt in candidates:
            if quotations and not any(q in excerpt for q in quotations):
                continue
            if not quotations and len(candidates) > 1 and excerpt not in associated:
                continue
            sources.append(HistorySource(
                message_id=mid, offset=start, length=len(excerpt),
                sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            ))
    return tuple(sources)


def read_source(database: Path, session_id: str, mid: int, offset: int, length: int, expected: str) -> dict | None:
    # Use the same Unicode code-point offsets as the recall tool and verify the
    # returned text so a changed message never displays as an earlier quote.
    if not (0 < mid < 2**63 and 0 <= offset < 2**31 and 0 < length <= 320
            and re.fullmatch("[0-9a-f]{64}", expected)):
        return None
    with closing(server_runtime.connect(database)) as conn:
        row = conn.execute("SELECT role, content FROM chat_messages WHERE session_id=? AND id=?",
                           (session_id, mid)).fetchone()
    if row is None:
        return None
    excerpt = row["content"][offset:offset + length]
    if len(excerpt) != length or hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != expected:
        return None
    return {"message_id": mid, "role": row["role"], "offset": offset, "excerpt": excerpt}
