"""从 LeetcodeTop 数据生成「企业高频题库」Markdown。

数据来源：https://github.com/huangzhangting/LeetcodeTop（CodeTop 社区按公司/岗位
人工汇总的 LeetCode 考察热度）。源文件原样放在 books/company-topics/_source/，
本脚本只做解析与排版，不改动原始数据。

用法：python -m scripts.build.build_company_topics
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "books" / "company-topics" / "_source"
OUT = ROOT / "books" / "company-topics" / "企业高频题库.md"

COMPANIES = [
    ("bytedance", "字节跳动"),
    ("alibaba", "阿里巴巴"),
    ("tencent", "腾讯"),
    ("meituan", "美团"),
    ("baidu", "百度"),
    ("kuaishou", "快手"),
    ("shopee", "Shopee"),
    ("microsoft", "微软"),
    ("yuanfudao", "猿辅导"),
    ("amazon", "Amazon"),
]

ROLES = [
    ("algorithm", "算法"),
    ("backend", "后端"),
    ("frontend", "前端"),
    ("client", "客户端"),
    ("data", "数据"),
    ("test", "测试"),
]

TOP_N = 30

# 兼容三种表头：|题目|出现次数|链接|、|题目|出现次数|、以及题号带 \. 转义的写法
ROW = re.compile(r"^\|\s*(\d+)\.\s*(.+?)\s*\|\s*(\d+)\s*\|\s*([^|\s]+)?")
# 少数公司（如百度）用「公司|岗位|题目|链接」四列且没有出现次数
ROW_COMPANY = re.compile(r"^\|[^|]*\|[^|]*\|\s*(\d+)\.\s*(.+?)\s*\|\s*([^|\s]+)?")


def load_hot100() -> dict[int, dict]:
    """读取 Hot 100 的题号 → {title, difficulty, folder}，用于标注覆盖情况。"""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from interview_forge.core.problem_catalog import PROBLEMS
        return {int(p["id"]): p for p in PROBLEMS}
    except Exception:  # noqa: BLE001
        return {}



def _resolve_link(item, hot100):
    """返回 (链接, 来源标签)。Hot 100 内的题指向站内题解页，其余指向 LeetCode。"""
    pid = item["id"]
    if pid in hot100:
        pr = hot100[pid]
        path = f"/books/hot100/03-题解/{pr['folder']}/{pid:04d}-{pr['title']}.html"
        return path, "Hot 100"
    url = (item.get("url") or "").strip()
    if "leetcode" in url:
        return url.replace("leetcode-cn.com", "leetcode.cn"), "LeetCode"
    return f"https://leetcode.cn/problemset/?search={pid}", "LeetCode"

def parse_file(path: Path) -> list[dict]:
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip().replace("\\", "")  # 源数据里题号写作 53\. ，先去掉转义符
        match = ROW.match(clean)
        if match:
            items.append({"id": int(match.group(1)), "title": match.group(2).strip(),
                          "count": int(match.group(3)), "url": match.group(4) or ""})
            continue
        alt = ROW_COMPANY.match(clean)
        if alt:
            items.append({"id": int(alt.group(1)), "title": alt.group(2).strip(),
                          "count": None, "url": alt.group(3) or ""})
    # 同一文件内可能重复（不同小节），按题号合并取最大热度
    merged: dict[int, dict] = {}
    for item in items:
        old = merged.get(item["id"])
        new_count = item["count"] if item["count"] is not None else -1
        old_count = (old["count"] if old and old["count"] is not None else -1) if old else None
        if old is None or new_count > old_count:
            merged[item["id"]] = item
    return sorted(merged.values(), key=lambda x: -(x["count"] if x["count"] is not None else -1))


def build() -> None:
    hot100 = load_hot100()
    lines: list[str] = [
        "# 企业高频算法题库",
        "",
        "> 数据来源：[LeetcodeTop](https://github.com/huangzhangting/LeetcodeTop) / "
        "[CodeTop](https://codetop.cc)。热度由社区按面经人工整理，反映「公司考察频率」，"
        "不是官方数据，仅供安排刷题优先级参考。",
        "",
        "## 怎么用这份题库",
        "",
        "1. 先用 **Hot 100** 打底：它覆盖了绝大多数公司的通用高频题。",
        "2. 再按目标公司补它的专属高频题：出现次数越高，越值得优先刷。",
        "3. 表格列出每个岗位的**全部高频题**；题目标题可点，Hot 100 里的题进站内题解，其余进 LeetCode 原题。",
        "",
        "## 覆盖速览",
        "",
        "| 公司 | 算法 | 后端 | 前端 | 客户端 | 数据 | 测试 |",
        "|---|---|---|---|---|---|---|",
    ]

    # 先算每家公司的岗位题数，做速览表
    per_company: dict[str, dict[str, list[dict]]] = {}
    for folder, cn in COMPANIES:
        per_role: dict[str, list[dict]] = {}
        for role_key, role_cn in ROLES:
            path = SRC / folder / f"{role_key}.md"
            if not path.is_file() and role_key == "algorithm":
                path = SRC / folder / "SDE.md"   # 微软 / Amazon 只提供 SDE 一份
            if path.is_file():
                items = parse_file(path)
                if items:
                    per_role[role_cn] = items
        per_company[cn] = per_role

    for folder, cn in COMPANIES:
        per_role = per_company[cn]
        cells = []
        for role_key, role_cn in ROLES:
            n = len(per_role.get(role_cn, []))
            cells.append(str(n) if n else "—")
        lines.append(f"| [{cn}](#{cn}) | " + " | ".join(cells) + " |")

    # 每家公司的详细表格
    for folder, cn in COMPANIES:
        per_role = per_company[cn]
        if not per_role:
            continue
        lines += ["", f"## {cn}", ""]
        for role_key, role_cn in ROLES:
            items = per_role.get(role_cn)
            if not items:
                continue
            covered_n = sum(1 for x in items if x["id"] in hot100)
            lines += [f"### {cn} · {role_cn}", ""]
            lines += [f"共 {len(items)} 题（其中 {covered_n} 题在 Hot 100 里有站内题解）。", ""]
            lines += ["| 题目 | 出现次数 | 题解 |", "|---|---|---|"]
            for item in items:
                count_text = item["count"] if item["count"] is not None else "—"
                link, tag = _resolve_link(item, hot100)
                lines.append(f"| [{item['id']}. {item['title']}]({link}) | {count_text} | {tag} |")
            lines.append("")

    lines += [
        "## 说明",
        "",
        "- 只统计纯数字题号的 LeetCode 题目；剑指 Offer 等系列未纳入表格。",
        f"- 每个「公司 · 岗位」组合只展示热度前 {TOP_N} 题。",
        "- 热度来自社区面经整理，样本有限，不同年份会有波动。",
        "- 原始数据见 `books/company-topics/_source/`，由 `scripts/build/build_company_topics.py` 生成本文。",
        "",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    total = sum(len(v) for per in per_company.values() for v in per.values())
    print(f"已生成 {OUT.relative_to(ROOT)}：{len(COMPANIES)} 家公司，{total} 条题目记录")


if __name__ == "__main__":
    build()
