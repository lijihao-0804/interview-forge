"""Register the independently delivered public employment research application."""

MODULE_ID = "ai-employment-research"
TITLE = "AI 就业调研 · 就业数据台"
URL = f"{MODULE_ID}/index.html"
ABOUT = (
    "2026-11-17 招聘广告截面，覆盖 20 家雇主、28,344 条公开记录。"
    "探索技术方向与技能要求，查看完整 JD、岗位对照、研究结论和数据口径。"
    "广告记录数不等于招聘人数。"
)


def register(modules, routes, search_entries):
    """Refresh one shelf entry without rendering or changing the supplied package."""
    content_id = f"{MODULE_ID}:workspace"
    chapter = {
        "id": content_id,
        "title": "就业数据台 · 岗位探索与研究结论",
        "url": URL,
        "intro": ABOUT,
    }
    modules[:] = [module for module in modules if module["id"] != MODULE_ID]
    modules.append({
        "id": MODULE_ID,
        "title": TITLE,
        "category": "岗位与进阶",
        "about": ABOUT,
        "url": URL,
        "chapter_count": 1,
        "unit": "研究入口",
        "chapters": [chapter],
    })
    routes[f"/library/{URL}"] = {"module_id": MODULE_ID, "content_id": content_id}
    search_entries[:] = [entry for entry in search_entries if entry.get("module_id") != MODULE_ID]
    search_entries.append({
        "id": content_id,
        "module_id": MODULE_ID,
        "module_title": TITLE,
        "title": chapter["title"],
        "url": URL,
        "text": ABOUT + " 市场总览 岗位探索 路线对比 研究结论 数据口径 AI Agent AI Infra 后训练 技能矩阵 职位 JD",
    })
