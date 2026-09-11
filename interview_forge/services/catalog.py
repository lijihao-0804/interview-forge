"""Runtime access to generated library metadata and static learning routes."""
from __future__ import annotations

import json
import threading
from pathlib import Path

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
