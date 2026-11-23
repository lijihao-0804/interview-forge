"""按“其它小林书”的方式重新抓取《AI 编程面试题》原文（含图片）。

当前 coding 专题此前是以“本站学习笔记”摘要形式人工加入的，源里没有图片。
本脚本复用 scrape_xiaolinnote 的正文/图片转换逻辑，按现有合订本的原文链接顺序
重新抓取 14 篇原文，覆盖 coding/ 下的分篇 Markdown，并重建《AI 编程面试题》.md。

用法：python scripts/scrape/rescrape_xiaolin_coding.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.scrape import scrape_xiaolinnote as S  # noqa: E402
from scripts.build import build_xiaolinnote_books as B  # noqa: E402

TOPIC_DIR = S.OUT_DIR / "coding"
AGGREGATE = TOPIC_DIR / "《AI 编程面试题》.md"


def main() -> None:
    old = AGGREGATE.read_text(encoding="utf-8")
    urls = re.findall(r"\[小林原文\]\((https://xiaolinnote\.com/ai/coding/[^)]+)\)", old)
    if len(urls) != 14:
        raise SystemExit(f"expected 14 coding urls, got {len(urls)}")
    S.IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Remove previous per-page summaries (keep nothing; aggregate rebuilt below).
    for p in TOPIC_DIR.glob("*.md"):
        if p.name != AGGREGATE.name:
            p.unlink()

    for index, url in enumerate(urls, 1):
        md = S.convert_page(url, index)
        title = md.splitlines()[0].lstrip("# ").strip()
        filename = f"{index:02d}-{S.safe_filename(title)}.md"
        (TOPIC_DIR / filename).write_text(md, encoding="utf-8")
        print(f"[coding] {index}/14 {filename}", flush=True)

    out = B.build_one("coding", "AI 编程面试题")
    text = out.read_text(encoding="utf-8")
    image_refs = len(re.findall(r"!\[", text))
    print(f"aggregate={out.name} lines={text.count(chr(10))+1} images={image_refs}")
    print(f"image files in store={len(list(S.IMAGE_DIR.glob('*')))}")


if __name__ == "__main__":
    main()
