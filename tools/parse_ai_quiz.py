"""从采集到的 AI 岗笔试页面正文中抽取可练习的选择题。

输入：data/ai_exam/zero2leetcode_ai_pages.json
输出：assets/ai-exam-quiz.json

只抽取原页明确给出题干、A-D 选项和答案的题目；原页只给答案、没有选项的题会跳过，
避免为了凑数量而伪造选项。题目解析保留原页解析文本，供学习时展开。
"""
from __future__ import annotations

import json
import html as html_lib
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import math_html  # noqa: E402

SRC = ROOT / "data" / "ai_exam" / "zero2leetcode_ai_pages.json"
OUT = ROOT / "assets" / "ai-exam-quiz.json"


def render_math_text(text: str) -> str:
    """把题目里的 $...$ / $$...$$ 转为站内 MathML，其余内容做 HTML 转义。"""
    output = []
    cursor = 0
    for match in re.finditer(r"\$\$([^$]+?)\$\$|\$([^$\n]+?)\$|\\\[(.+?)\\\]|\\\((.+?)\\\)", text, re.S):
        output.append(html_lib.escape(text[cursor:match.start()]))
        source = next((group for group in match.groups() if group is not None), "")
        output.append(math_html(source, display=bool(match.group(1) is not None or match.group(3) is not None)))
        cursor = match.end()
    output.append(html_lib.escape(text[cursor:]))
    return "".join(output).replace("\n", "<br>")


COMPANY = {
    "huawei": "华为", "alibaba": "阿里巴巴", "ant": "蚂蚁", "meituan": "美团",
    "baidu": "百度", "jd": "京东", "pinduoduo": "拼多多", "didi": "滴滴",
    "ctrip": "携程", "netease": "网易", "iflytek": "科大讯飞", "oppo": "OPPO", "dewu": "得物",
}


def normal_lines(text: str) -> list[str]:
    """合并被页面排版拆开的「答案」「解析」标签与冒号，并拆开同一行的 A/B/C/D 选项。"""
    lines = [line.strip() for line in text.splitlines()]
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line in ("答案", "解析", "考点", "难度", "参考答案") and i + 1 < len(lines) and lines[i + 1].startswith("："):
            out.append(line + lines[i + 1])
            i += 2
            continue
        # 常见于 PDF 转文本：A. 选项一　　B. 选项二
        if re.match(r"^[A-D]\s*[.、．]", line) and re.search(r"\s+[B-D]\s*[.、．]", line):
            out.extend(re.split(r"\s+(?=[B-D]\s*[.、．])", line))
        else:
            out.append(line)
        i += 1
    return out


def answer_of(text: str) -> list[int]:
    match = re.search(r"答案\s*[：:]\s*([A-Da-d][A-Da-d,，、\s]*)", text)
    if not match:
        return []
    return sorted({ord(char.upper()) - 65 for char in re.findall(r"[A-Da-d]", match.group(1))})


def parse_chunk(lines: list[str], first: str, multi: bool) -> dict[str, object] | None:
    options: list[str] = []
    option_start = None
    answer: list[int] = []
    answer_index = None
    for index, line in enumerate(lines):
        option = re.match(r"^([A-D])\s*[.、．]\s*(.*)$", line)
        if option:
            if option_start is None:
                option_start = index
            option_text = option.group(2).strip()
            # 有的页面把“A.”与选项正文拆成两行
            if not option_text and index + 1 < len(lines):
                following = lines[index + 1].strip()
                if following and not re.match(r"^[A-D]\s*[.、．]", following) and not following.startswith(("答案", "解析", "考点", "难度")):
                    option_text = following
            options.append(option_text)
        found = answer_of(line)
        if found and not answer:
            answer = found
            answer_index = index
    if len(options) < 2 or option_start is None or not answer:
        return None
    if any(not option.strip() for option in options):
        return None
    answer = [value for value in answer if value < len(options)]
    if not answer:
        return None
    stem = " ".join([first] + [part for part in lines[:option_start]
                                if part and not re.match(r"^(答案|解析|考点|难度|题型)", part)]).strip()
    stem = re.sub(r"^(?:第\s*\d+\s*题|\d{1,3}[.、])\s*", "", stem)
    stem = re.sub(r"\s+", " ", stem)
    tail = lines[answer_index:] if answer_index is not None else []
    explain = " ".join(re.sub(r"^答案\s*[：:]", "", part) for part in tail).strip()
    explain = re.sub(r"\s+", " ", explain)[:1500]
    return {
        "stem": stem,
        "options": options,
        "answer": answer,
        "multi": multi or len(answer) > 1,
        "explain": explain,
    }


def parse_by_headings(page: dict[str, object]) -> list[dict[str, object]]:
    """适配使用 h3 作题目标题（1. xxx / 第1题）的页面。"""
    text = str(page.get("text", ""))
    headings = page.get("headings", []) or []
    positions = []
    cursor = 0
    for name, heading in headings:
        index = text.find(str(heading), cursor)
        if index < 0:
            continue
        positions.append((index, name, str(heading)))
        cursor = index + len(str(heading))

    questions: list[dict[str, object]] = []
    for order, (index, name, heading) in enumerate(positions):
        if name != "h3" or not re.match(r"^(?:\d{1,3}[.、]\s*|第\s*\d+\s*题\s*$)", heading):
            continue
        previous = [h for _, kind, h in positions[:order] if kind in ("h2", "h3")]
        if any(kind == "h2" and re.match(r"^第\s*\d+\s*题", h) for _, kind, h in positions[:order]):
            continue
        next_index = positions[order + 1][0] if order + 1 < len(positions) else len(text)
        chunk = normal_lines(text[index + len(heading):next_index])
        multi = False
        for h in reversed(previous):
            if re.search(r"(多选|不定项)", h):
                multi = True
                break
            if re.search(r"(单选|单选题|选择题)", h):
                multi = False
                break
        question = parse_chunk(chunk, heading, multi)
        if question:
            number = re.match(r"^(?:第\s*)?(\d+)", heading)
            question["num"] = int(number.group(1)) if number else 0
            questions.append(question)
    return questions


def parse_numbered(page: dict[str, object]) -> list[dict[str, object]]:
    """适配题干写在正文编号行（1、... / 1. ...）的页面。"""
    lines = normal_lines(str(page.get("text", "")))
    starts = [index for index, line in enumerate(lines) if re.match(r"^选择题(?:（.*?）)?$", line)]
    if starts:
        start = starts[-1]
    else:
        start = next((index for index, line in enumerate(lines) if "选择题" in line), 0)

    questions: list[dict[str, object]] = []
    expected = 1
    multi = False
    index = start
    while index < len(lines):
        line = lines[index]
        if re.match(r"^第\s*\d+\s*题", line) or line.startswith(("编程题", "代码题", "题目描述")):
            break
        if len(line) < 40 and re.search(r"(多选|不定项)", line):
            multi = True
            expected = 1
            index += 1
            continue
        if len(line) < 40 and re.search(r"(单选|选择题)", line):
            multi = False
            expected = 1
            index += 1
            continue
        current = re.match(r"^(\d{1,3})\s*[.、]\s*(.+)$", line)
        if current and int(current.group(1)) == expected:
            end = index + 1
            while end < len(lines):
                if re.match(r"^第\s*\d+\s*题", lines[end]):
                    break
                following = re.match(r"^(\d{1,3})\s*[.、]\s*(.+)$", lines[end])
                if following and int(following.group(1)) == expected + 1:
                    break
                end += 1
            question = parse_chunk(lines[index + 1:end], current.group(2).strip(), multi)
            if question:
                question["num"] = expected
                questions.append(question)
                expected += 1
                index = end
                continue
        index += 1
    return questions


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    all_questions: list[dict[str, object]] = []
    stats = []
    for page in data:
        if page.get("slug") == "ai-exam-guide":
            continue
        questions = parse_by_headings(page) or parse_numbered(page)
        if not questions:
            continue
        company = COMPANY.get(str(page.get("company")), str(page.get("company")))
        role = str(page.get("role", ""))
        date = str(page.get("date", "")) or "未标注日期"
        role_label = {"ai": "AI岗", "ai-coding": "AI Coding", "agent": "Agent岗", "algo": "算法岗"}.get(role, role)
        category = f"{company} · {date} · {role_label}"
        for serial, question in enumerate(questions, 1):
            question["stem_html"] = render_math_text(question["stem"])
            question["options_html"] = [render_math_text(option) for option in question["options"]]
            question["explain_html"] = render_math_text(question["explain"])
            question.update({
                "key": f"ai-exam:{page.get('company')}:{page.get('date')}:{page.get('slug')}:{question.get('num')}:{serial}",
                "category": category,
                "company": company,
                "date": page.get("date", ""),
                "role": role,
                "source_url": page.get("url", ""),
            })
            all_questions.append(question)
        stats.append((len(questions), page.get("company"), page.get("date"), page.get("title")))

    OUT.write_text(json.dumps({"total": len(all_questions), "questions": all_questions},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("pages with questions:", len(stats), "| questions:", len(all_questions),
          "| multi:", sum(1 for q in all_questions if q["multi"]))
    print("by company:", Counter(q["company"] for q in all_questions).most_common())
    print("lowest pages:", sorted(stats)[:8])


if __name__ == "__main__":
    main()
