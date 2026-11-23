"""按“其它小林书”的方式重新抓取《图解 Codex》原文（含图片）。

此前的 tujie-codex 专题是纯文字摘要（0 图）。本脚本复用 scrape_xiaolinnote
的正文/图片转换逻辑，按现有合订本的原文链接顺序重抓 4 篇原文，覆盖分篇
Markdown，并重建《图解 Codex》.md。

用法：python scripts/scrape/rescrape_xiaolin_codex.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.scrape import scrape_xiaolinnote as S  # noqa: E402
from scripts.build import build_xiaolinnote_books as B  # noqa: E402

TOPIC_DIR = S.OUT_DIR / "tujie-codex"
AGGREGATE = TOPIC_DIR / "《图解 Codex》.md"


def main() -> None:
    old = AGGREGATE.read_text(encoding="utf-8")
    urls = re.findall(r"\[小林原文\]\((https://xiaolinnote\.com/codex/[^)]+)\)", old)
    if len(urls) != 4:
        raise SystemExit(f"expected 4 codex urls, got {len(urls)}")
    S.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for p in TOPIC_DIR.glob("*.md"):
        if p.name != AGGREGATE.name:
            p.unlink()
    for index, url in enumerate(urls, 1):
        md = S.convert_page(url, index)
        title = md.splitlines()[0].lstrip("# ").strip()
        (TOPIC_DIR / f"{index:02d}-{S.safe_filename(title)}.md").write_text(md, encoding="utf-8")
        print(f"[codex] {index}/4 {url}", flush=True)
    out = B.build_one("tujie-codex", "图解 Codex")
    text = out.read_text(encoding="utf-8")
    image_refs = len(re.findall(r"!\[", text))
    print(f"aggregate={out.name} lines={text.count(chr(10))+1} images={image_refs}")


if __name__ == "__main__":
    main()
