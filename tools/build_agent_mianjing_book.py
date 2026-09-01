"""把 agent面经.md 规范成书架合订本：一级标题为书名，正文标题整体降一级。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "books" / "agent面经" / "agent面经.md"
OUT = ROOT / "books" / "agent面经" / "《Agent 面经》.md"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    demoted: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            demoted.append(line)
            continue
        if not in_fence and re.match(r"^#{1,6}\s", line):
            line = "#" + line
        demoted.append(line)

    book = "# Agent 面经\n\n" + "\n".join(demoted) + "\n"
    OUT.write_text(book, encoding="utf-8")
    chapter_count = sum(1 for l in demoted if l.startswith("## "))
    print(f"{OUT.relative_to(ROOT)} chapters={chapter_count}")


if __name__ == "__main__":
    main()
