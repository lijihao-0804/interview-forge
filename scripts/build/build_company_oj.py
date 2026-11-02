"""把抓取的语雀各公司真题文本整理成 books/company-oj/<公司>/<题号>-<标题>.md。

格式说明：源为 innerText，可能有 OCR 识别误差，这里仅按题目起始行切分，
保留原文（不臆造内容），标题取自起始行。
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".maintenance"
DST = ROOT / "books" / "company-oj"

# (公司, 源文件, 切分正则)
SOURCES = [
    ("华为-软开岗", "yq_华为软开岗.txt", re.compile(r"^(\d+)[,，](.+)$")),
    ("华为-可信", "yq_华为可信科目一.txt", None),
    ("阿里", "yuque/阿里.txt", re.compile(r"^题目描述$")),
    ("网易雷火", "yuque/网易雷火.txt", re.compile(r"^第[一二三四五六七八九十]+题[：: ]*(.*)$")),
    ("京东", "yuque/京东.txt", re.compile(r"^第[一二三四五六七八九十]+题[：: ]*(.*)$")),
    ("小米", "yuque/小米.txt", re.compile(r"^第[一二三四五六七八九十]+题[：: ]*(.*)$")),
    ("拼多多", "yuque/拼多多.txt", re.compile(r"^第\d+题[：: ]*(.*)$")),
    ("携程", "yuque/携程.txt", re.compile(r"^第[一二三四五六七八九十\d]+题[：: ]*(.*)$")),
]


def safe(s):
    return re.sub(r'[\\/:*?"<>|]', "", s).strip()[:40] or "题目"


def main():
    total = 0
    for company, rel, pat in SOURCES:
        f = SRC / rel
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        d = DST / company
        d.mkdir(parents=True, exist_ok=True)
        chapters = []  # (title, [lines])
        if pat is None:
            # 整篇一题
            title = next((l.strip() for l in lines if l.strip()), company)
            chapters.append((title, lines))
        else:
            cur = None
            for l in lines:
                m = pat.match(l.strip())
                if m:
                    if cur:
                        chapters.append(cur)
                    groups = [g for g in m.groups() if g]
                    t = groups[-1] if groups else ""
                    cur = (t.strip() or f"题{len(chapters)+1}", [])
                elif cur is not None:
                    cur[1].append(l)
            if cur:
                chapters.append(cur)
            # 标题为空（形如“第一题”单独成行）时，取正文首个非空行当标题
            for idx, (title, body) in enumerate(chapters):
                if title.startswith("题") and title[1:].isdigit():
                    nxt = next((x.strip() for x in body if x.strip()), "")
                    if nxt:
                        chapters[idx] = (nxt[:30], body)
            # 通用词/过长标题兜底为「第N题」
            GENERIC = {"题意", "题目描述", "题目内容", "题目", "问题描述"}
            for idx, (title, body) in enumerate(chapters):
                if title in GENERIC or len(title) > 25:
                    chapters[idx] = (f"第{idx+1}题", body)
        for i, (title, body) in enumerate(chapters, 1):
            content = "\n".join(body).strip()
            if len(content) < 30:
                continue
            # 正文里若自带 "# 标题" 行（OCR 里常见），全角化为 ＃，避免阅读页出现多个 H1
            content = re.sub(r"(?m)^(\s*)(#+)", lambda m: m.group(1) + "＃" * len(m.group(2)), content)
            md = f"# {title}\n\n> 来源：语雀「{company}真题题解」（OCR 原文，可能存在识别误差）\n\n{content}\n"
            (d / f"{i:02d}-{safe(title)}.md").write_text(md, encoding="utf-8")
            total += 1
        print(f"  {company}: {len(list(d.glob('*.md')))} 题")
    print(f"共 {total} 题 → books/company-oj")


if __name__ == "__main__":
    main()
