"""导入华为 OD 机试题库（321 题）到 books/huawei-od/。

来源：datawhalechina/huawei-od-python（MIT，Datawhale 整理）
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".maintenance" / "hwod" / "docs"
DST = ROOT / "books" / "huawei-od"

GROUPS = [
    ("choice100", "01-精选100分题"),
    ("questions200", "02-200分题"),
    ("others100", "03-其他100分题"),
]

IMG_RE = re.compile(r"!\[([^\]]*)\]\(\.?/?images/([^)]+)\)")


def main() -> None:
    img_src = SRC / "images"
    img_dst = DST / "assets"
    if img_src.is_dir():
        img_dst.mkdir(parents=True, exist_ok=True)
        for p in img_src.iterdir():
            if p.is_file():
                shutil.copy2(p, img_dst / p.name)

    total = 0
    for src_dir, out_dir in GROUPS:
        s = SRC / src_dir
        if not s.is_dir():
            continue
        d = DST / out_dir
        d.mkdir(parents=True, exist_ok=True)
        for md in sorted(s.glob("*.md")):
            if md.name.upper() == "README.MD":
                continue
            m = re.match(r"(\d+)_(.+)", md.stem)
            num = m.group(1) if m else md.stem
            content = md.read_text(encoding="utf-8")
            h1 = None
            for line in content.splitlines():
                if line.startswith("# "):
                    t = re.match(r"#\s*(\d+)?\s*(.+)", line)
                    h1 = t.group(2).strip() if t else None
                    break
            title = re.sub(r'[\/:*?"<>|]', "", h1 or md.stem).strip() or md.stem
            content = IMG_RE.sub(
                lambda mm: "![" + mm.group(1) + "](../assets/" + mm.group(2) + ")", content)
            # 跨行的 $$...$$ 公式合并成单行，render_math_in_markdown 是逐行处理的
            content = re.sub(r"\$\$[ \t]*\n(.*?)\n[ \t]*\$\$",
                             lambda mm: "$$" + mm.group(1).strip().replace("\n", " ") + "$$",
                             content, flags=re.S)
            (d / (str(num) + "-" + title + ".md")).write_text(content, encoding="utf-8")
            total += 1
        print("  " + out_dir + ": " + str(len(list(d.glob("*.md")))) + " 题")
    print("完成：" + str(total) + " 题")


if __name__ == "__main__":
    main()
