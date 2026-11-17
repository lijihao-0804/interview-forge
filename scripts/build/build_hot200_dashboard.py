"""Render the supplement from exactly the same dashboard template as Hot 100."""

import json
import re
from scripts.build.asset_version import ASSET_VERSION


def render_dashboard(root):
    items = json.loads((root / "data/hot200-extra.json").read_text(encoding="utf-8"))
    problems = []
    for i, p in enumerate(items, 1):
        source = (root / f"books/hot200-extra/solutions/{p['id']}.md").read_text(
            encoding="utf-8-sig"
        )

        def paragraph(heading):
            match = re.search(rf"^### {heading}\s*\n+([^\n]+)", source, re.M)
            if not match:
                raise ValueError(f"LC {p['id']}: missing {heading}")
            return match[1].strip().replace("`", "")

        method = re.split(r"(?<=[。！？])", paragraph("思路"), maxsplit=1)[0]
        problems.append(
            dict(
                id=p["id"],
                title=p["title"],
                category=p["topic"],
                difficulty=p["difficulty"],
                method=method,
                complexity=paragraph("复杂度"),
                original=f"https://leetcode.cn/problems/{p['slug']}/",
                note=f"chapter-{i:02d}.html",
            )
        )
    page = (root / "tools/templates/dashboard.tpl").read_text(encoding="utf-8")
    page = page.replace(
        'href="library/hot200-extra/index.html"', 'href="index.html"'
    ).replace("练 Hot 200 补充题 →", "返回 Hot 100 →")
    page = re.sub(
        r'((?:href|src)="|url\(")(?!#)(assets/|pages/|books/|library/|index\.html|cockpit\.html|guide\.html|manifest\.webmanifest)',
        r"\1../../\2",
        page,
    )
    page = (
        page.replace(
            'href="../../books/hot100/00-总览/01-学习路线.html"', 'href="#problemGrid"'
        )
        .replace("查看学习路线", "按题单顺序练习")
        .replace(">学习路线<", ">补充题目录<")
    )
    page = page.replace(
        'href="../../books/hot100/00-总览/05-错题本.html"', 'href="#weakList"'
    ).replace("错题本页 →", "查看薄弱题 ↓")
    page = page.replace("pages/history.html#d-", "../../pages/history.html#d-")
    page = (
        page.replace("Hot 100 算法题库", "Hot 200 补充题库")
        .replace("Hot 100 首轮", "Hot 200 补充题首轮")
        .replace("至少 AC 一次的 Hot 100 题目进度", "至少完成一轮的补充题进度")
    )
    page = page.replace("道高频面试题，涵盖", "道补充题（原题单第 101–200 题），涵盖")
    page = (
        page.replace(
            'href="../../books/hot100/03-题解/01-哈希表/0001-两数之和.html"',
            'href="chapter-01.html"',
        )
        .replace(
            "查看两数之和题解。数组 2、7、11、15 中，2 与 7 的和等于目标值 9。",
            "查看反转字符串中的单词 II 题解",
        )
        .replace(">两数之和<", ">反转字符串中的单词 II<")
        .replace(
            '>2</span><span class="example-cell is-sum">7<',
            '>the</span><span class="example-cell is-sum">sky<',
        )
        .replace(
            '>11</span><span class="example-cell">15<',
            '>is</span><span class="example-cell">blue<',
        )
        .replace("目标和 9 <b>2 + 7 = 9", "逆序 <b>blue is sky the")
    )
    page = page.replace("专题顺序", "题单顺序").replace(
        "整套首轮需完成 90 题，后续每轮需超过半数已完成题目达到该轮。",
        "每道补充题都完成一次后算整套一轮；语言缺失的旧记录仍计入全语言。",
    )
    page = page.replace(
        "JSON.stringify({full,async:true",
        "JSON.stringify({module:'hot200-extra',full,async:true",
    )
    page = page.replace(
        "forge_leetcode_sync_offset_", "forge_hot200_leetcode_sync_offset_"
    )
    page = (
        page.replace("/api/bootstrap", "/api/hot200-extra/bootstrap")
        .replace("/api/plan", "/api/hot200-extra/plan")
        .replace("/api/mock?", "/api/hot200-extra/mock?")
    )
    page = page.replace(
        "target_type:'problem',target_id:key",
        "target_type:'content',target_id:'hot200-extra:'+key.padStart(4,'0')",
    )
    page = page.replace("key:'daily_goal_rounds'", "key:'hot200_daily_goal_rounds'")
    page = page.replace(
        "state.settings=boot.settings;",
        "state.settings=boot.settings;state.pinnedTomorrow=boot.pinnedTomorrow||{};",
    )
    page = (
        page.replace(
            "forge-hot100-progress-updated:", "forge-hot200-extra-progress-updated:"
        )
        .replace("forge-progress-language:", "forge-hot200-progress-language:")
        .replace(
            "const MOCK_SESSION_KEY='forge-mock-session-v1';",
            "const mockSessionKey=()=>'forge-hot200-mock-session-v1:'+dashboardSessionKey;",
        )
        .replace("MOCK_SESSION_KEY", "mockSessionKey()")
        .replace("forge-last-opened-problem-v1", "forge-hot200-last-opened-v1")
    )
    page = page.replace(
        "/api/export?kind=${kind}",
        "${kind==='db'?'/api/export':'/api/hot200-extra/export'}?kind=${kind}",
    ).replace("备份数据库", "备份账号数据库")
    page = page.replace(
        "lang&&!stats.submits?'未做'", "lang&&!rounds&&!stats.submits?'未做'"
    )
    page = page.replace(
        "lang?'尚无该语言提交'", "lang?(rounds?'已记录手动复习':'尚无该语言记录')"
    )
    page = page.replace(
        "书架待复习 ${daily.summary.contents||0} 项 →", "查看全站学习书架 →"
    )
    page = page.replace(
        "</footer>",
        ' · <a href="https://leetcode.cn/problem-list/qg88wci/">力扣精选算法 200 题 · 官方题单</a> · <a href="LICENSE-walkccc.txt">参考代码许可</a></footer>',
    )
    return (
        page.replace(
            "__HOT100_PROBLEMS__",
            json.dumps(problems, ensure_ascii=False).replace("</", "<\\/"),
        )
        .replace("__PROBLEM_COUNT__", str(len(problems)))
        .replace("__TOPIC_COUNT__", str(len({p["category"] for p in problems})))
        .replace("__ASSET_VERSION__", ASSET_VERSION)
    )
