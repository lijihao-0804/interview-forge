"""把小林面试笔记的抓取结果按大专题合成一本书，供书架生成器登记使用。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE_ROOT = ROOT / "books" / "小林面试笔记AI"

SERIES = [
    ("agent", "Agent 面试题"),
    ("rag", "RAG 面试题"),
    ("tools", "LLM 工具调用面试题"),
    ("llm", "大模型工程面试题"),
    ("langchain", "LangChain 框架面试题"),
    ("tujie-agent", "图解 Agent"),
    ("tujie-claude-code", "图解 Claude Code"),
]


def build_one(key: str, title: str) -> Path:
    topic_dir = NOTE_ROOT / key
    files = sorted(p for p in topic_dir.glob("*.md") if not p.name.startswith("《"))
    chapters: list[str] = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        heading = ""
        start = 0
        for index, line in enumerate(lines):
            if line.startswith("# "):
                heading = line[2:].strip()
                start = index + 1
                break
        body_lines = lines[start:]
        while body_lines and body_lines[0].strip() == "":
            body_lines.pop(0)
        while body_lines and body_lines[0].strip().startswith(">"):
            body_lines.pop(0)
        while body_lines and body_lines[0].strip() == "":
            body_lines.pop(0)

        demoted: list[str] = []
        in_fence = False
        for raw_line in body_lines:
            stripped = raw_line.lstrip()
            if stripped.startswith(("```", "~~~")):
                in_fence = not in_fence
                demoted.append(raw_line)
                continue
            if in_fence:
                demoted.append(raw_line)
                continue
            if re.match(r"^#{1,6}\s", raw_line):
                raw_line = "#" + raw_line
            demoted.append(raw_line)
        body = "\n".join(demoted).strip()
        if heading:
            chapters.append(f"## {heading}\n\n{body}")

    aggregate = f"# {title}\n\n" + "\n\n".join(chapters) + "\n"
    out = topic_dir / f"《{title}》.md"
    out.write_text(aggregate, encoding="utf-8")
    return out


def main() -> None:
    for key, title in SERIES:
        out = build_one(key, title)
        print(f"{out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
