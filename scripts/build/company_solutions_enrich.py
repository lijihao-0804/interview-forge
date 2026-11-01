"""补抓：3 道失败题 + 全部题的 topicTags 分类。就地更新 problems_detail.json。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from curl_cffi import requests  # noqa: E402

DETAIL = ROOT / "books" / "company-solutions" / "_meta" / "problems_detail.json"
META = ROOT / "books" / "company-solutions" / "_meta" / "problems.json"
EXTRA = [{"id": 1240, "title": "铺瓷砖", "slug": "tiling-a-rectangle-with-the-fewest-squares"}]

QUERY = """query q($slug:String!){question(titleSlug:$slug){
  questionFrontendId translatedTitle difficulty translatedContent
  topicTags{name slug} codeSnippets{lang code} }}"""


def fetch(slug):
    for a in range(3):
        try:
            r = requests.post("https://leetcode.cn/graphql/",
                              json={"query": QUERY, "variables": {"slug": slug}},
                              impersonate="chrome", timeout=30)
            return r.json().get("data", {}).get("question")
        except Exception as exc:  # noqa: BLE001
            print(f"  {slug} 失败{a+1}: {exc}")
            time.sleep(2)
    return None


def main():
    problems = json.loads(META.read_text(encoding="utf-8"))
    for e in EXTRA:
        if all(p["id"] != e["id"] for p in problems):
            problems.append(e)
    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in detail}
    id2slug = {p["id"]: p["slug"] for p in problems}

    # 1) 补失败/缺失的题
    missing = [pid for pid in id2slug if pid not in by_id]
    print("缺失题:", missing)
    sys.path.insert(0, str(ROOT / "scripts" / "build"))
    from company_solutions_fetch import html_to_md
    for pid in missing:
        q = fetch(id2slug[pid])
        if not q:
            continue
        by_id[pid] = {
            "id": pid, "title": q.get("translatedTitle") or id2slug[pid],
            "slug": id2slug[pid], "difficulty": q.get("difficulty") or "",
            "statement_md": html_to_md(q.get("translatedContent") or ""),
            "snippets": {c["lang"]: c["code"] for c in (q.get("codeSnippets") or [])},
            "tags": [t["name"] for t in (q.get("topicTags") or [])],
        }
        print(f"  补齐 {pid}")
        time.sleep(0.5)

    # 2) 给所有缺 tags 的题补
    for pid, d in list(by_id.items()):
        if d.get("tags"):
            continue
        q = fetch(id2slug.get(pid, d["slug"]))
        if q:
            d["tags"] = [t["name"] for t in (q.get("topicTags") or [])]
        time.sleep(0.4)

    out = sorted(by_id.values(), key=lambda x: x["id"])
    DETAIL.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    no_tag = [d["id"] for d in out if not d.get("tags")]
    print(f"完成：{len(out)} 题 | 仍无 tags: {no_tag}")


if __name__ == "__main__":
    main()
