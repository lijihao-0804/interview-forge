"""Vendor 《深入理解 AI Agent：设计原理与工程实践》 (李博杰 著) into the bookshelf source tree.

Upstream: https://github.com/bojieli/ai-agent-book (Apache-2.0), Chinese edition under ``book/``.
Upstream ships Pandoc-flavoured Markdown (heading/图 attribute blocks, one file per
chapter). The bookshelf builder (``scripts/build/build_library.py``) reads one Markdown
per course and splits chapters on ``## ``. This script therefore:

* promotes each source file's single ``# H1`` to a ``## `` chapter heading,
* demotes inner headings by one level so the hierarchy stays intact,
* strips Pandoc ``{.unnumbered}`` / ``{height=55%}`` attribute blocks,
* concatenates 前言 + 第 1–10 章 + 后记 + 思考题参考答案, and
* copies only the referenced figures (114 SVG/PNG) into ``books/ai-agent-book/images``.

Usage::

    python scripts/build/vendor_ai_agent_book.py --raw <path-to-upstream/book>
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "books" / "ai-agent-book"
UPSTREAM = "https://github.com/bojieli/ai-agent-book"
UPSTREAM_COMMIT = "defacfb21b7dc19f37702a9e89b7e99104e6218f"
UPSTREAM_TAG = "v3.1"

# (filename, chapter heading template). Titles come from the file's own H1.
FILES: list[tuple[str, str]] = [
    ("introduction.md", "前言"),
    *[(f"chapter{i}.md", f"第 {i} 章 {{title}}") for i in range(1, 11)],
    ("afterword.md", "后记：回到 Agent = LLM + 上下文 + 工具"),
    ("reference-answers.md", "思考题参考答案"),
]

ATTR_RE = re.compile(r"\s*\{[^{}]*\}\s*$")
IMG_ATTR_RE = re.compile(r"(!\[[^\]]*\]\([^)]+\))\s*\{[^{}]*\}")
IMG_REF_RE = re.compile(r"!\[[^\]]*\]\((images/[^)\s]+)")


def _transform(text: str, heading_template: str) -> str:
    """Normalize one upstream chapter file into bookshelf chapter Markdown."""
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    fence = ""
    title = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m:
            out.append(line)
            continue
        hashes, heading = m.group(1), ATTR_RE.sub("", m.group(2)).strip()
        if len(hashes) == 1 and title is None:
            title = heading
            out.append("## " + heading_template.replace("{title}", heading))
            continue
        # Demote every inner heading one level (## -> ###, etc.) so it nests under the chapter.
        out.append("#" * min(len(hashes) + 1, 6) + " " + heading)
    if title is None:
        raise ValueError("no H1 title found")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="upstream book/ directory")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    raw: Path = args.raw
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    parts = []
    for filename, template in FILES:
        parts.append(_transform((raw / filename).read_text(encoding="utf-8"), template))
    combined = "\n\n".join(parts).strip() + "\n"
    combined = IMG_ATTR_RE.sub(r"\1", combined)
    # 上游把“消息历史 / messages”这类结构示意也标成 text 纯文本，阅读时没有语法色。
    # 这些块实际是类 Python 的伪代码（# 注释、字符串、数字、括号），改用 python
    # 词法器着色更易读；真正是并排示意的 text 块（如 tools/assistant 两栏）保持不动。
    combined = re.sub(
        r"^```text[ \t]*\r?\n(?=(?:消息历史 = \[|messages = \[|messages: \[))",
        "```python\n",
        combined,
        flags=re.M,
    )

    # Copy only the figures actually referenced, preserving the images/... layout.
    referenced = sorted(set(IMG_REF_RE.findall(combined)))
    for rel in referenced:
        src = raw / rel
        if not src.is_file():
            raise FileNotFoundError(rel)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    (out / "ai-agent-book.md").write_text(combined, encoding="utf-8")

    license_src = raw.parent / "LICENSE"
    if license_src.is_file():
        shutil.copy2(license_src, out / "LICENSE")

    (out / "ATTRIBUTION.md").write_text(
        "\n".join(
            [
                "# 来源与许可",
                "",
                "- 书名：《深入理解 AI Agent：设计原理与工程实践》（李博杰 著）中文版",
                f"- 上游仓库：{UPSTREAM}",
                f"- 固定提交：`{UPSTREAM_COMMIT}`（{UPSTREAM_TAG}）",
                "- 许可：Apache License 2.0（见同目录 `LICENSE`）",
                "- 处理：由 `scripts/build/vendor_ai_agent_book.py` 合并前言、第 1–10 章、后记与思考题参考答案；",
                "  仅做标题层级归一、Pandoc 属性清理与图片抽取，正文未改写。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"wrote {out/'ai-agent-book.md'} ({combined.count(chr(10))+1} lines); figures={len(referenced)}")


if __name__ == "__main__":
    main()
