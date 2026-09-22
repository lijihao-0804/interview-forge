"""把 agent面经.md 规范成书架合订本：一级标题为书名，正文标题整体降一级。

幂等：源文件本身就是这个脚本的产物格式(第一个标题已经是书名)时，只做同步、
不再加标题也不再降级。历史上这里踩过坑——SRC 被人工修过一轮、内容已经是合订
本形态，再跑一次就会多出一层 `# Agent 面经` 并把全书标题又压深一级。
"""
from __future__ import annotations

import re
from pathlib import Path

from interview_forge.core.paths import ROOT
SRC = ROOT / "books" / "agent面经" / "agent面经.md"
OUT = ROOT / "books" / "agent面经" / "《Agent 面经》.md"
TITLE = "# Agent 面经"


def iter_body(lines: list[str]):
    """逐行产出 (是否在代码围栏内, 原始行)。

    围栏按反引号个数配对：正文里举 Markdown 例子时会出现 ```` 包着 ```python 的
    嵌套写法，只看 startswith("```") 会把内层当成收栏，之后的行围栏状态全反。
    """
    fence: str | None = None
    for line in lines:
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
                yield True, line
                continue
            if token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            yield True, line
            continue
        yield fence is not None, line


def first_heading(lines: list[str]) -> str | None:
    for in_fence, line in iter_body(lines):
        if not in_fence and re.match(r"^#{1,6}\s", line):
            return line.strip()
    return None


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()

    if first_heading(lines) == TITLE:
        body = lines
        note = "（源文件已是合订本形态，仅同步）"
    else:
        body = [TITLE, ""]
        for in_fence, line in iter_body(lines):
            body.append("#" + line if not in_fence and re.match(r"^#{1,6}\s", line) else line)
        note = ""

    OUT.write_text("\n".join(body).rstrip("\n") + "\n", encoding="utf-8")
    chapter_count = sum(1 for in_fence, l in iter_body(body) if not in_fence and l.startswith("## "))
    print(f"{OUT.relative_to(ROOT)} chapters={chapter_count} {note}".rstrip())


if __name__ == "__main__":
    main()
