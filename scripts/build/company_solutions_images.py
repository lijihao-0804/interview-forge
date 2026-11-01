"""为企业题解补图：抓 LeetCode 题面图片，下载到 assets/leetcode/，并把
「## 题目与约束」段替换为含图片的新题面（其余段落/代码保持不动，保留已做的修正）。

用法：python -m scripts.build.company_solutions_images
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from curl_cffi import requests  # noqa: E402

DETAIL = ROOT / "books" / "company-solutions" / "_meta" / "problems_detail.json"
IMG_DIR = ROOT / "assets" / "leetcode"

QUERY = """query q($s:String!){question(titleSlug:$s){translatedContent}}"""

TAG_BLOCK = {"p": "\n\n", "div": "\n", "ul": "\n", "ol": "\n", "li": "\n- ",
             "pre": "\n\n", "h1": "\n\n# ", "h2": "\n\n## ", "h3": "\n\n### "}
TAG_INLINE = {"code": "`"}  # 强调(<strong>/<em>)降级为纯文本，避免 *** 残留


def download_img(url: str) -> str | None:
    """下载图片到 assets/leetcode/lc-<hash>.<ext>，返回文件名；失败返回 None。"""
    try:
        ext = ".png"
        m = re.search(r"\.(png|jpe?g|gif|webp)(?:\?|$)", url, re.I)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        name = f"lc-{digest}{ext}"
        dst = IMG_DIR / name
        if dst.exists():
            return name
        r = requests.get(url, impersonate="chrome", timeout=30,
                         headers={"Referer": "https://leetcode.cn/"})
        if r.status_code == 200 and r.content:
            IMG_DIR.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(r.content)
            return name
    except Exception as exc:  # noqa: BLE001
        print(f"    图片失败 {url[:60]}: {exc}")
    return None


def html_to_md_with_images(raw: str) -> str:
    if not raw:
        return ""
    s = raw
    s = re.sub(r"<(?![a-zA-Z/!])", "&lt;", s)  # 保护数学符号 <= <
    pres: list[str] = []

    def stash_pre(m: re.Match) -> str:
        code = re.sub(r"</?(?:code|span)[^>]*>", "", m.group(1))  # 只去 code/span，保留代码里的 <
        code = html_lib.unescape(code).strip("\n")
        pres.append(code)
        return f"\n\n@@PRE{len(pres)-1}@@\n\n"

    s = re.sub(r"<pre[^>]*>(.*?)</pre>", stash_pre, s, flags=re.S)

    # 图片：下载并替换为相对路径（相对 books/company-solutions/<分类>/*.html → ../../../assets/leetcode/）
    def stash_img(m: re.Match) -> str:
        src = m.group(1)
        name = download_img(src)
        if not name:
            return ""
        return f"\n\n![题面插图](../../../assets/leetcode/{name})\n\n"

    s = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', stash_img, s, flags=re.I)

    for tag, mark in TAG_BLOCK.items():
        if tag == "pre":
            continue
        s = re.sub(rf"<{tag}[^>]*>", mark, s, flags=re.I)
        s = re.sub(rf"</{tag}>", "\n", s, flags=re.I)
    for tag, mark in TAG_INLINE.items():
        s = re.sub(rf"<{tag}[^>]*>", mark, s, flags=re.I)
        s = re.sub(rf"</{tag}>", mark, s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n\n- ", s, flags=re.I)
    s = re.sub(r"</li>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"^[ 	]+$", "", s, flags=re.M)  # 清空纯空白行，避免挡住列表
    s = re.sub(r"(?m)\n(?=- )", "\n\n", s)  # 列表项前保证空行
    s = re.sub(r"\*{2,}", "", s)  # 兜底清理残留 ** 强调符
    s = html_lib.unescape(s).replace("\xa0", " ")
    for i, code in enumerate(pres):
        s = s.replace(f"@@PRE{i}@@", "```\n" + code + "\n```")
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def main() -> None:
    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    used = 0
    for i, d in enumerate(detail, 1):
        try:
            r = requests.post("https://leetcode.cn/graphql/",
                              json={"query": QUERY, "variables": {"s": d["slug"]}},
                              impersonate="chrome", timeout=30)
            content = (r.json().get("data") or {}).get("question", {}).get("translatedContent") or ""
        except Exception as exc:  # noqa: BLE001
            print(f"  {d['id']} 抓取失败: {exc}"); continue
        new_stmt = html_to_md_with_images(content)
        used += 1
        # 写回 detail
        d["statement_md"] = new_stmt
        if i % 30 == 0:
            print(f"  进度 {i}/{len(detail)}")
        time.sleep(0.4)
    DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成：{used} 题题面已补图，图片目录 {IMG_DIR}")


if __name__ == "__main__":
    main()
