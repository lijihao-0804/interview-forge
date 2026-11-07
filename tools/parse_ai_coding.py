"""从采集到的 AI/算法岗笔试页面中抽取编程大题，生成 assets/ai-exam-coding.json。

只保留页面里带编程题段落的内容；原页代码块尽量按 <pre> 原样保留。
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ai_exam" / "zero2leetcode_ai_pages.json"
OUT = ROOT / "assets" / "ai-exam-coding.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

COMPANY = {
    "huawei": "华为", "alibaba": "阿里巴巴", "ant": "蚂蚁", "meituan": "美团",
    "baidu": "百度", "jd": "京东", "pinduoduo": "拼多多", "didi": "滴滴",
    "ctrip": "携程", "netease": "网易", "iflytek": "科大讯飞", "oppo": "OPPO", "dewu": "得物",
}
ROLE = {"ai": "AI岗", "ai-coding": "AI Coding", "agent": "Agent岗", "algo": "算法岗"}


def fetch(page):
    try:
        request = urllib.request.Request(page["url"], headers=UA)
        html = urllib.request.urlopen(request, timeout=40).read().decode("utf-8", "replace")
        article = BeautifulSoup(html, "html.parser").find("article")
        if article is None:
            return page, []
        blocks = article.find_all(["h2", "h3", "p", "pre", "ul", "ol", "table"], recursive=True)
        problems = []
        current = None
        current_section = None
        for block in blocks:
            name = block.name
            text = block.get_text(" ", strip=True)
            code = block.get_text().strip() if name == "pre" else ""
            if name == "h2":
                if current and (current["sections"] or current["codes"]):
                    problems.append(current)
                current = None
                current_section = None
                if re.match(r"^第\s*\d+\s*题", text):
                    if re.search(r"(选择题|单选题|多选题)", text):
                        continue
                    current = {
                        "title": re.sub(r"^第\s*\d+\s*题\s*[:：]?\s*", "", text),
                        "sections": [],
                        "codes": [],
                    }
                continue
            if not current:
                continue
            if name == "h3":
                current_section = {"heading": text, "text": [], "code": ""}
                current["sections"].append(current_section)
            elif name == "pre":
                if code:
                    current["codes"].append(code)
                    if current_section is not None:
                        current_section["code"] += ("\n" if current_section["code"] else "") + code
            else:
                if current_section is None:
                    current_section = {"heading": "题目说明", "text": [], "code": ""}
                    current["sections"].append(current_section)
                if text:
                    current_section["text"].append(text)
        if current and (current["sections"] or current["codes"]):
            problems.append(current)
        for p in problems:
            for section in p["sections"]:
                section["text"] = "\n".join(section["text"]).strip()
            p["plain"] = "\n".join(
                part for section in p["sections"] for part in [section.get("heading", ""), section.get("text", "")]
                if part
            )
            p["summary"] = next((section["text"] for section in p["sections"]
                                 if section.get("heading") == "题目描述" and section.get("text")), p["plain"][:240])
        return page, problems
    except Exception as error:  # noqa: BLE001
        return page, [{"error": f"{type(error).__name__}: {error}"}]


def main() -> None:
    pages = [page for page in json.loads(SRC.read_text(encoding="utf-8")) if page.get("slug") != "ai-exam-guide"]
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, page): page for page in pages}
        for future in as_completed(futures):
            results.append(future.result())

    items = []
    for page, problems in results:
        company = COMPANY.get(page.get("company"), page.get("company"))
        role = ROLE.get(page.get("role"), page.get("role", ""))
        date = page.get("date", "")
        category = f"{company} · {date} · {role}" if date else f"{company} · {role}"
        for index, problem in enumerate(problems, 1):
            if "error" in problem:
                continue
            problem.update({
                "key": f"ai-coding:{page.get('company')}:{date}:{page.get('slug')}:{index}",
                "company": company,
                "date": date,
                "role": role,
                "category": category,
                "source_url": page.get("url", ""),
            })
            items.append(problem)
    items.sort(key=lambda item: (item["company"], item["date"], item["title"]))
    OUT.write_text(json.dumps({"total": len(items), "problems": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("pages", len(results), "problems", len(items), "by company", Counter(x["company"] for x in items).most_common())
    print("with code", sum(1 for x in items if x["codes"]))
    print("sample", items[0]["title"] if items else None)


if __name__ == "__main__":
    main()
