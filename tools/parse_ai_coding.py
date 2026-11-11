"""从采集到的 AI/算法岗笔试页面中抽取编程大题，生成 assets/ai-exam-coding.json。

只保留页面里带编程题段落的内容；原页代码块尽量按 <pre> 原样保留。
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build.build_html_site import math_html  # noqa: E402

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


def render_text(text: str) -> str:
    """把纯文本中的 $...$ / $$...$$ 转成站内 MathML，其余文本做 HTML 转义。"""
    output = []
    cursor = 0
    for match in re.finditer(r"\$\$([^$]+?)\$\$|\$([^$\n]+?)\$|\\\[(.+?)\\\]|\\\((.+?)\\\)", text, re.S):
        output.append(html_lib.escape(text[cursor:match.start()]))
        source = next((group for group in match.groups() if group is not None), "")
        output.append(math_html(source, display=bool(match.group(1) is not None or match.group(3) is not None)))
        cursor = match.end()
    output.append(html_lib.escape(text[cursor:]))
    return "".join(output).replace("\n", "<br>")


def fetch(page):
    try:
        html = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(page["url"], headers=UA)
                html = urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace")
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)
        article = BeautifulSoup(html, "html.parser").find("article")
        if article is None:
            return page, []
        # 保留 article 的文档顺序：原站的 display math（\\[...\\]）是
        # article 的直接文本节点；代码 pre 又可能嵌在 div 里，因此用 descendants
        # 收集正文标签，并单独收集 article 的直接公式文本。
        allowed = ("h2", "h3", "p", "pre", "ul", "ol", "table")
        blocks = []
        for child in article.descendants:
            if isinstance(child, NavigableString):
                if child.parent is article and str(child).strip():
                    blocks.append(child)
            elif getattr(child, "name", None) in allowed:
                blocks.append(child)
        problems = []
        current = None
        current_section = None
        for block in blocks:
            if isinstance(block, NavigableString):
                formula = str(block).strip()
                if current is not None and current_section is not None and formula and (
                    "\\[" in formula or "\\(" in formula or "$$" in formula
                ):
                    current_section["text"].append(formula)
                continue
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
                section["text_html"] = render_text(section["text"]) if section.get("text") else ""
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
    with ThreadPoolExecutor(max_workers=4) as pool:
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
