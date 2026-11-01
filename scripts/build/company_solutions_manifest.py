"""构建企业题库 375 题（Hot100 之外）的清单：id / title / slug / difficulty。

- slug 优先从源数据 url 提取；
- 缺失的用 LeetCode 全量题库列表（questionFrontendId → titleSlug）补；
- 输出 books/company-solutions/_meta/problems.json 供后续抓题面与生成题解使用。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curl_cffi import requests  # noqa: E402
from interview_forge.core.problem_catalog import PROBLEMS  # noqa: E402

SRC = ROOT / "books" / "company-topics" / "_source"
OUT = ROOT / "books" / "company-solutions" / "_meta" / "problems.json"

HOT = {int(p["id"]): p for p in PROBLEMS}


def parse_source() -> dict[int, dict]:
    """从企业题库源数据提取题号 → {title, url}。"""
    found: dict[int, dict] = {}
    bs = chr(92)
    for md in SRC.rglob("*.md"):
        for line in md.read_text(encoding="utf-8").splitlines():
            clean = line.strip().replace(bs, "")
            m = re.match(r"^\|\s*(\d+)\.\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\S+)?", clean)
            if not m:
                m2 = re.match(r"^\|[^|]*\|[^|]*\|\s*(\d+)\.\s*(.+?)\s*\|\s*(\S+)?", clean)
                if m2:
                    pid, title, url = int(m2.group(1)), m2.group(2).strip(), (m2.group(3) or "")
                    found.setdefault(pid, {"title": title, "url": url})
                continue
            pid, title, url = int(m.group(1)), m.group(2).strip(), (m.group(4) or "")
            old = found.get(pid)
            if old is None or (url and not old.get("url")):
                found[pid] = {"title": title, "url": url}
    return found


def fetch_all_slugs() -> dict[int, str]:
    """分页抓 LeetCode 全量题库，返回 题号 → slug。"""
    query = """query q($skip:Int,$limit:Int){problemsetQuestionList(categorySlug:"",limit:$limit,skip:$skip,filters:{}){
      questions{questionFrontendId titleSlug} totalNum }}"""
    mapping: dict[int, str] = {}
    skip = 0
    total = None
    while True:
        try:
            r = requests.post("https://leetcode.cn/graphql/",
                              json={"query": query, "variables": {"skip": skip, "limit": 100}},
                              impersonate="chrome", timeout=30)
            data = r.json()["data"]["problemsetQuestionList"]
        except Exception as exc:  # noqa: BLE001
            print("  抓取分页失败 skip=%d: %s" % (skip, exc))
            break
        total = data["totalNum"]
        for q in data["questions"]:
            try:
                mapping[int(q["questionFrontendId"])] = q["titleSlug"]
            except (TypeError, ValueError):
                pass
        skip += 100
        if skip >= total:
            break
    print(f"  全量题库 slug 映射：{len(mapping)} 条（total={total}）")
    return mapping


def slug_from_url(url: str) -> str:
    m = re.search(r"/problems/([A-Za-z0-9\-_]+)", url or "")
    return m.group(1) if m else ""


def main() -> None:
    found = parse_source()
    targets = {pid: v for pid, v in found.items() if pid not in HOT}
    print(f"源数据题号 {len(found)}，Hot100 之外 {len(targets)}")

    need_slug = [pid for pid, v in targets.items() if not slug_from_url(v.get("url", ""))]
    all_slugs = {}
    if need_slug:
        print(f"缺 slug 的 {len(need_slug)} 题，抓全量题库补：")
        all_slugs = fetch_all_slugs()

    out = []
    missing = []
    for pid, v in sorted(targets.items()):
        slug = slug_from_url(v.get("url", "")) or all_slugs.get(pid, "")
        if not slug:
            missing.append(pid)
            continue
        out.append({"id": pid, "title": v["title"], "slug": slug})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}：{len(out)} 题 | 缺 slug {len(missing)}：{missing[:10]}")


if __name__ == "__main__":
    main()
