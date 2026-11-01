"""抓取 375 题的中文题面与代码模板，供生成题解使用。

输出 books/company-solutions/_meta/problems_detail.json：
  {id, title, slug, difficulty, statement_md, snippets:{lang:code}}
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from curl_cffi import requests  # noqa: E402

META = ROOT / "books" / "company-solutions" / "_meta" / "problems.json"
OUT = ROOT / "books" / "company-solutions" / "_meta" / "problems_detail.json"

# 补上抓取时缺失的题（1240 铺瓷砖）
EXTRA = [{"id": 1240, "title": "铺瓷砖",
          "slug": "tiling-a-rectangle-with-the-fewest-squares"}]

QUERY = """query q($slug:String!){question(titleSlug:$slug){
  questionFrontendId translatedTitle difficulty translatedContent
  codeSnippets{lang code} }}"""

TAG_BLOCK = {"p": "\n\n", "div": "\n", "ul": "\n", "ol": "\n", "li": "\n- ",
             "pre": "\n\n", "h1": "\n\n# ", "h2": "\n\n## ", "h3": "\n\n### "}
TAG_INLINE = {"code": "`", "strong": "**", "b": "**", "em": "*", "i": "*"}


def html_to_md(raw: str) -> str:
    """把 LeetCode 题面 HTML 转成简洁 Markdown（够用即可）。"""
    if not raw:
        return ""
    s = raw
    # 代码块先抽出来（pre>code），避免内部标签被误处理
    pres: list[str] = []

    def stash_pre(m: re.Match) -> str:
        code = re.sub(r"<[^>]+>", "", m.group(1))
        code = html_lib.unescape(code).strip("\n")
        pres.append(code)
        return f"\n\n@@PRE{len(pres)-1}@@\n\n"

    s = re.sub(r"<pre[^>]*>(.*?)</pre>", stash_pre, s, flags=re.S)
    # 块级标签
    for tag, mark in TAG_BLOCK.items():
        if tag == "pre":
            continue
        s = re.sub(rf"<{tag}[^>]*>", mark, s, flags=re.I)
        s = re.sub(rf"</{tag}>", "\n", s, flags=re.I)
    # 行内标签
    for tag, mark in TAG_INLINE.items():
        s = re.sub(rf"<{tag}[^>]*>", mark, s, flags=re.I)
        s = re.sub(rf"</{tag}>", mark, s, flags=re.I)
    # 列表项
    s = re.sub(r"</li>", "", s, flags=re.I)
    # 去掉剩余标签
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s).replace("\xa0", " ")
    # 还原代码块
    for i, code in enumerate(pres):
        s = s.replace(f"@@PRE{i}@@", "```\n" + code + "\n```")
    # 压缩空行
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def fetch_one(slug: str) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.post("https://leetcode.cn/graphql/",
                              json={"query": QUERY, "variables": {"slug": slug}},
                              impersonate="chrome", timeout=30)
            q = r.json().get("data", {}).get("question")
            return q
        except Exception as exc:  # noqa: BLE001
            print(f"    {slug} 抓取失败({attempt+1}): {exc}")
            time.sleep(2 + attempt * 2)
    return None


def main() -> None:
    problems = json.loads(META.read_text(encoding="utf-8"))
    for e in EXTRA:
        if all(p["id"] != e["id"] for p in problems):
            problems.append(e)
            print(f"补入 {e['id']} {e['title']}")

    detail = []
    ok = fail = 0
    for i, p in enumerate(problems, 1):
        q = fetch_one(p["slug"])
        if not q:
            fail += 1
            continue
        snippets = {c["lang"]: c["code"] for c in (q.get("codeSnippets") or [])}
        detail.append({
            "id": int(p["id"]),
            "title": q.get("translatedTitle") or p["title"],
            "slug": p["slug"],
            "difficulty": q.get("difficulty") or "",
            "statement_md": html_to_md(q.get("translatedContent") or ""),
            "snippets": snippets,
        })
        ok += 1
        if i % 20 == 0:
            print(f"  进度 {i}/{len(problems)}（成功 {ok} 失败 {fail}）")
        time.sleep(0.5)

    OUT.write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成：{ok} 题写入 {OUT.relative_to(ROOT)}，失败 {fail}")


if __name__ == "__main__":
    main()
