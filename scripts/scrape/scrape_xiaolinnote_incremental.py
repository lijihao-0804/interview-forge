"""增量抓取小林面试笔记：只抓线上有、本地没有的页面。

与全量脚本（scripts/scrape/scrape_xiaolinnote.py）的区别：
  · 不重写已有文章（按"标题归一化"匹配，避免序号变化导致重复下载）
  · 只下载新增文章引用的图片（download_image 本身有 dest.exists() 跳过）
  · README 只在有变化时重建
保持原脚本的转换逻辑不变（直接 import 复用），确保新旧文章格式一致。
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(r"E:\interview-forge")
sys.path.insert(0, str(ROOT))

from scripts.scrape.scrape_xiaolinnote import (  # noqa: E402
    OUT_DIR,
    SERIES,
    collect_pages,
    convert_page,
    safe_filename,
    build_readme,
)


def norm(s: str) -> str:
    """标题归一化：去掉序号、标点与空白，便于识别同一篇文章。"""
    s = re.sub(r"^\d+[.、]\s*", "", s.strip())
    return re.sub(r"[\s\W_]+", "", s).lower()


def local_titles(key: str) -> set[str]:
    """本地已有文章的标题集合（文件名去掉 NN- 前缀）。"""
    out = set()
    for f in (OUT_DIR / key).glob("*.md"):
        if f.name.startswith("README") or f.name.startswith("《"):
            continue
        stem = re.sub(r"^\d+[-_.]\s*", "", f.stem)
        out.add(norm(stem))
    return out


def main() -> None:
    dry = "--dry-run" in sys.argv
    pages = collect_pages()

    total_new = 0
    summary = []
    for key, title, _prefix in SERIES:
        urls = pages.get(key, [])
        known = local_titles(key)
        existing_numbers = set()
        for f in (OUT_DIR / key).glob("*.md"):
            m = re.match(r"^(\d+)[-_.]", f.name)
            if m:
                existing_numbers.add(int(m.group(1)))

        added = []
        for index, url in enumerate(urls, 1):
            if dry:
                # dry-run 下无法拿标题，只能比较序号：本地最大序号之后视为新增
                if index in existing_numbers:
                    continue
                added.append((index, url, "(未知标题，dry-run)"))
                continue
            try:
                md = convert_page(url, index)
            except Exception as exc:  # noqa: BLE001
                print(f"[{key}] FAIL {url}: {exc}", file=sys.stderr)
                continue
            page_title = md.splitlines()[0].lstrip("# ").strip()
            if norm(page_title) in known:
                continue  # 已抓过
            filename = f"{index:02d}-{safe_filename(page_title)}.md"
            dest = OUT_DIR / key / filename
            if dest.exists():
                continue
            dest.write_text(md, encoding="utf-8")
            known.add(norm(page_title))
            added.append((index, url, filename))
            total_new += 1
            print(f"[{key}] + {filename}", flush=True)
            time.sleep(0.15)

        summary.append((title, len(urls), len(known), len(added)))
        if added and not dry:
            print(f"  → {title}: 新增 {len(added)} 篇")

    print(f"\n{'系列':24s}{'线上':>6}{'本地(新增后)':>12}{'本次新增':>10}")
    print("-" * 56)
    for title, online, local, added in summary:
        print(f"{title:24s}{online:>6}{local:>12}{added:>10}")

    if dry:
        print("\n[dry-run] 未写入任何文件")
    else:
        image_count = len(list((OUT_DIR / "images").glob("*")))
        build_readme(image_count)
        print(f"\n合计新增 {total_new} 篇，图片总数 {image_count}")


if __name__ == "__main__":
    main()
