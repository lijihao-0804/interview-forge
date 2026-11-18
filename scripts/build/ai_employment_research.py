"""Register the independently delivered public employment research books."""
from posixpath import normpath

MODULE_ID = "ai-employment-research"
COMMUNICATIONS_MODULE_ID = "communications-research"
TITLE = "AI 就业调研 · 就业数据台"
URL = f"{MODULE_ID}/index.html"
ABOUT = (
    "2026-11-17 招聘广告截面，覆盖 20 家雇主、28,344 条公开记录。"
    "按城市与技术筛选岗位，查看完整 JD、四方向对照、技术需求表和研究结论。"
    "广告记录数不等于招聘人数。"
)


RESEARCH_BOOKS = (
    {
        "id": "employment-market",
        "title": "AI 应用与电子信息就业研究",
        "chapter_title": "广覆盖就业研究 · 专业、技能与岗位筛选",
        "url": "../research/market/index.html",
        "about": "8,474 条去重岗位发布记录，覆盖 547 个归并雇主名称。按 AI 方向、通信与电子信息专业、城市、员工规模和技术筛选，阅读完整 JD、研究结论与采集方法。",
        "keywords": "就业研究 AI应用 智能体 Agent 通信工程 电子信息 学生招聘 城市 员工规模 雇主 技术词表 JD SQLite CSV",
    },
    {
        "id": MODULE_ID,
        "title": TITLE,
        "chapter_title": "就业数据台 · 岗位探索与研究结论",
        "url": URL,
        "about": ABOUT,
        "keywords": "市场总览 岗位探索 路线对比 研究结论 数据口径 AI Agent AI Infra 后训练 技能矩阵 职位 JD 城市 学历 技术词典 LangChain LangGraph 期次档案",
    },
    {
        "id": COMMUNICATIONS_MODULE_ID,
        "title": "通信工程就业调研",
        "chapter_title": "通信工程就业数据台 · 岗位与技术需求",
        "url": f"{COMMUNICATIONS_MODULE_ID}/index.html",
        "about": "2,367 条通信专业相关记录，按母集团、城市、学历和职业筛选，查看专业证据、完整 JD 与技术需求。含 AI 就业调研主语料中的 1,203 条记录。",
        "keywords": "通信工程 通信专业 母集团 招聘单位 所有制 城市 学历 学生入口 招聘状态 专业证据 技术词典 MATLAB HFSS SQLite 岗位 JD",
    },
)


def register(modules, routes, search_entries):
    """Refresh shelf entries while preserving each supplied package."""
    for book in RESEARCH_BOOKS:
        module_id = book["id"]
        content_id = f"{module_id}:workspace"
        chapter = {
            "id": content_id,
            "title": book["chapter_title"],
            "url": book["url"],
            "intro": book["about"],
        }
        modules[:] = [module for module in modules if module["id"] != module_id]
        modules.append({
            "id": module_id,
            "title": book["title"],
            "category": "岗位与进阶",
            "about": book["about"],
            "url": book["url"],
            "chapter_count": 1,
            "unit": "研究入口",
            "chapters": [chapter],
        })
        routes[normpath(f"/library/{book['url']}")] = {"module_id": module_id, "content_id": content_id}
        search_entries[:] = [entry for entry in search_entries if entry.get("module_id") != module_id]
        search_entries.append({
            "id": content_id,
            "module_id": module_id,
            "module_title": book["title"],
            "title": chapter["title"],
            "url": book["url"],
            "text": book["about"] + " " + book["keywords"],
        })
