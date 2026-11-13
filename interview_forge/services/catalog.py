"""Runtime access to generated library metadata and static learning routes."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from interview_forge.core.problem_catalog import PROBLEMS, problem_filename
from interview_forge.core.paths import ROOT

_MANIFEST_CACHE: tuple[float, dict[str, object]] | None = None
_MANIFEST_LOCK = threading.Lock()


def load_library_manifest() -> dict[str, object]:
    global _MANIFEST_CACHE
    path = ROOT / "library" / "manifest.json"
    if not path.exists():
        return {"modules": [], "routes": {}}
    mtime = path.stat().st_mtime
    with _MANIFEST_LOCK:
        if _MANIFEST_CACHE is not None and _MANIFEST_CACHE[0] == mtime:
            return _MANIFEST_CACHE[1]
        value = json.loads(path.read_text(encoding="utf-8"))
        _MANIFEST_CACHE = (mtime, value)
        return value


def valid_content(module_id: str, content_id: str) -> bool:
    manifest = load_library_manifest()
    return any(
        module.get("id") == module_id
        and any(chapter.get("id") == content_id for chapter in module.get("chapters", []))
        for module in manifest.get("modules", [])
    )


def public_catalog() -> dict[str, object]:
    """Return reviewed public metadata without sessions or learning state."""
    manifest = load_library_manifest()
    modules: list[dict[str, object]] = []
    for module in manifest.get("modules", []):
        if not isinstance(module, dict):
            continue
        chapters = []
        for chapter in module.get("chapters", []):
            if not isinstance(chapter, dict):
                continue
            chapters.append({
                "id": str(chapter.get("id", "")),
                "title": str(chapter.get("title", "")),
                "url": "/library/" + str(chapter.get("url", "")).lstrip("/"),
                "intro": str(chapter.get("intro", "")),
            })
        modules.append({
            "id": str(module.get("id", "")),
            "title": str(module.get("title", "")),
            "category": str(module.get("category", "")),
            "about": str(module.get("about", "")),
            "chapter_count": len(chapters),
            "chapters": chapters,
        })

    problems = []
    for problem in PROBLEMS:
        filename = problem_filename(problem)[:-3] + ".html"
        problems.append({
            "id": int(problem["id"]),
            "title": str(problem["title"]),
            "category": str(problem["category"]),
            "difficulty": str(problem["difficulty"]),
            "url": f"/books/hot100/03-题解/{problem['folder']}/{filename}",
        })
    return {"version": 1, "modules": modules, "problems": problems}
