# -*- coding: utf-8 -*-
"""多语言题解提取管线（一次性工具，产物提交入库供构建期使用）。

来源：
  A. 力扣题解-EndlessCheng（灵茶山艾府）：标准多语言围栏 ```java/cpp/py/go/c
  B. 代码随想录-Hot100：网页抓取格式，代码为 4 空格缩进块 + "### 语言：" 小节标题

产物：tools/lang_solutions.json —— {题号: {"cpp": {"code":..., "source":...}, ...}}
语言规范化：py/python3→python，cpp/c++→cpp，c→c，go/golang→go，java→java
每个语言取该文件中第一个完整实现（主解法）。
"""
import json
import re
from pathlib import Path

EC = Path(r"E:\JAVA\AI+agent\笔记\力扣题解-EndlessCheng")
CARL = Path(r"E:\JAVA\AI+agent\笔记\代码随想录-Hot100")
OUT = Path(r"E:\interview-forge\tools\lang_solutions.json")

NORM = {"py": "python", "python": "python", "python3": "python",
        "cpp": "cpp", "c++": "cpp",
        "c": "c",
        "go": "go", "golang": "go",
        "java": "java"}

# ---- 来源 A：EndlessCheng 围栏提取 ----
def extract_ec(text):
    """返回 {lang: code}。按围栏标签取每语言第一个块。"""
    out = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^```([a-zA-Z+#]+)", lines[i])
        if m:
            lang = NORM.get(m.group(1).lower())
            if lang:
                buf = []
                i += 1
                while i < len(lines) and lines[i] != "```":
                    buf.append(lines[i]); i += 1
                code = "\n".join(buf).strip()
                if lang not in out and code:
                    out[lang] = code
        i += 1
    return out

# ---- 来源 B：代码随想录 缩进块提取 ----
LANG_HEADER = re.compile(r"^#{2,4}\s*(?:\d+[.、)]?\s*)?(C\+\+|Java|Python3?|Golang|Go|C语言|C)\s*[:：]?\s*$", re.I)
NUM_LINE = re.compile(r"^\s*(?:\d+\s*)+$")

def extract_carl(text):
    """返回 {lang: code}。跟踪语言小节标题，收集其后连续 4 空格缩进行为代码块。"""
    out = {}
    lines = text.split("\n")
    cur_lang = None      # 当前小节语言（carl 主思路区默认 C++）
    in_main_idea = False
    buf = []
    def flush():
        nonlocal buf
        code = "\n".join(l[4:] if l.startswith("    ") else l for l in buf).strip("\n").strip()
        _lines = code.split("\n")
        while _lines and re.match(r"^[（(【]?[^\x00-\x7F]", _lines[0]):
            _lines.pop(0)
        code = "\n".join(_lines).strip()
        if code and cur_lang and cur_lang not in out and len(code) > 40:
            out[cur_lang] = code
        buf = []
    for line in lines:
        h = LANG_HEADER.match(line)
        if h:
            flush()
            raw = h.group(1).lower()
            cur_lang = NORM.get(raw.replace("c语言", "c").replace("golang", "go"))
            if raw == "c语言": cur_lang = "c"
            in_main_idea = False
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            if any(k in title for k in ("思路", "方法", "解法", "题意", "算法")):
                flush()
                cur_lang = "cpp"    # carl 主思路区代码默认 C++
                in_main_idea = True
            elif any(k in title for k in ("其他语言", "公开课", "总结")):
                flush()
                in_main_idea = False
                if "其他语言" in title: cur_lang = None
            continue
        if line.startswith("    ") and line.strip():
            buf.append(line)
        else:
            if line.strip() and NUM_LINE.match(line):
                continue    # 行号噪声行：跳过但不断开代码块？→ 行号在代码块后成段出现，遇数字行直接跳过
            flush()
    flush()
    return out

def main():
    hot100 = []
    sol = Path(r"E:\interview-forge\books\hot100\03-题解")
    for d in sorted(sol.iterdir()):
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                m = re.match(r"(\d{4})-(.+)\.md", f.name)
                if m: hot100.append(int(m.group(1)))

    ec_index = {}
    for f in EC.rglob("*.md"):
        m = re.match(r"^(\d+)\.md$", f.name)
        if m: ec_index.setdefault(int(m.group(1)), []).append(f)
    carl_index = {}
    for f in CARL.glob("*.md"):
        m = re.match(r"^(\d{4})\.", f.name)
        if m: carl_index[int(m.group(1))] = f

    result = {}
    stats = {"ec": 0, "carl": 0, "langs": {"java": 0, "cpp": 0, "python": 0, "go": 0, "c": 0}}
    for num in hot100:
        langs = {}
        if num in ec_index:
            text = "".join(f.read_text(encoding="utf-8", errors="replace") for f in ec_index[num])
            for lang, code in extract_ec(text).items():
                if lang != "java":
                    langs.setdefault(lang, {"code": code, "source": "灵茶山艾府题解（MIT License）"})
            if langs: stats["ec"] += 1
        if num in carl_index:
            text = carl_index[num].read_text(encoding="utf-8", errors="replace")
            for lang, code in extract_carl(text).items():
                if lang != "java" and lang not in langs:
                    langs.setdefault(lang, {"code": code, "source": "代码随想录（programmercarl.com）"})
            if langs: stats["carl"] += 1
        for lang in langs: stats["langs"][lang] += 1
        if langs: result[str(num)] = langs

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("题目数据:", len(result), "题")
    print("来源统计: EC 贡献", stats["ec"], "题 | carl 贡献", stats["carl"], "题")
    print("分语言覆盖:", stats["langs"])
    covered = sorted(int(k) for k in result)
    missing = [n for n in hot100 if str(n) not in result]
    print("仍无任何补充语言的题:", len(missing), missing[:40])

if __name__ == "__main__":
    main()
