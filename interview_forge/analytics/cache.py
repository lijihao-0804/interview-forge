"""Process-local analytics snapshot cache.

Cache state remains owned by the server assembly for compatibility with the
existing singleton and test hooks; this module owns the cache algorithms.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path



def _runtime():
    from interview_forge.server import study_server

    return study_server


def _analytics_resolved_path(db_path: Path) -> str:
    return str(Path(db_path).resolve())


def _analytics_cache_scope(resolved_path: str) -> str:
    return hashlib.sha256(resolved_path.encode("utf-8")).hexdigest()


def _analytics_cache_prefix(resolved_path: str) -> str:
    runtime = _runtime()
    return (
        f"analytics:{runtime.ANALYTICS_SCHEMA_VERSION}:{runtime.ANALYTICS_RULE_VERSION}:"
        f"{_analytics_cache_scope(resolved_path)}"
    )


def _analytics_cache_key(db_path: Path, generation: int | None = None) -> str:
    runtime = _runtime()
    resolved_path = _analytics_resolved_path(db_path)
    if generation is None:
        with runtime._ANALYTICS_CACHE_LOCK:
            generation = runtime._ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0)
    return f"{_analytics_cache_prefix(resolved_path)}:g{int(generation)}"


def _analytics_cache_has_path_locked(resolved_path: str) -> bool:
    runtime = _runtime()
    marker = f":{_analytics_cache_scope(resolved_path)}:g"
    return any(key.startswith("analytics:") and marker in key for key in runtime._ANALYTICS_CACHE)


def _prune_analytics_cache_locked(now: float) -> None:
    runtime = _runtime()
    expired = [
        key for key, (created_at, _result) in runtime._ANALYTICS_CACHE.items()
        if now - float(created_at) >= runtime._ANALYTICS_TTL
    ]
    for key in expired:
        runtime._ANALYTICS_CACHE.pop(key, None)
    max_entries = max(0, int(runtime._ANALYTICS_CACHE_MAX_ENTRIES))
    while len(runtime._ANALYTICS_CACHE) > max_entries:
        oldest_key = min(
            runtime._ANALYTICS_CACHE,
            key=lambda item: (float(runtime._ANALYTICS_CACHE[item][0]), item),
        )
        runtime._ANALYTICS_CACHE.pop(oldest_key, None)


def _prune_analytics_generations_locked() -> None:
    runtime = _runtime()
    max_entries = max(0, int(runtime._ANALYTICS_GENERATION_MAX_ENTRIES))
    if len(runtime._ANALYTICS_CACHE_GENERATIONS) <= max_entries:
        return
    candidates = sorted(
        (
            runtime._ANALYTICS_GENERATION_TOUCHED.get(path, 0.0),
            path,
        )
        for path in runtime._ANALYTICS_CACHE_GENERATIONS
        if runtime._ANALYTICS_CACHE_ACTIVE.get(path, 0) == 0
    )
    for _touched, path in candidates:
        if len(runtime._ANALYTICS_CACHE_GENERATIONS) <= max_entries:
            break
        runtime._ANALYTICS_CACHE_GENERATIONS.pop(path, None)
        runtime._ANALYTICS_GENERATION_TOUCHED.pop(path, None)


def _invalidate_analytics_cache(db_path: Path) -> None:
    runtime = _runtime()
    resolved_path = _analytics_resolved_path(db_path)
    with runtime._ANALYTICS_CACHE_LOCK:
        now = time.time()
        _prune_analytics_cache_locked(now)
        marker = f":{_analytics_cache_scope(resolved_path)}:g"
        for key in list(runtime._ANALYTICS_CACHE):
            if key.startswith("analytics:") and marker in key:
                runtime._ANALYTICS_CACHE.pop(key, None)
        runtime._ANALYTICS_CACHE_GENERATIONS[resolved_path] = (
            runtime._ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0) + 1
        )
        runtime._ANALYTICS_GENERATION_TOUCHED[resolved_path] = now
        _prune_analytics_generations_locked()


def _analytics_build_started_locked(resolved_path: str) -> None:
    runtime = _runtime()
    runtime._ANALYTICS_CACHE_ACTIVE[resolved_path] = runtime._ANALYTICS_CACHE_ACTIVE.get(resolved_path, 0) + 1


def _analytics_build_finished_locked(resolved_path: str) -> None:
    runtime = _runtime()
    active = runtime._ANALYTICS_CACHE_ACTIVE.get(resolved_path, 0)
    if active <= 1:
        runtime._ANALYTICS_CACHE_ACTIVE.pop(resolved_path, None)
    else:
        runtime._ANALYTICS_CACHE_ACTIVE[resolved_path] = active - 1


def analytics_cached(db_path: Path) -> dict[str, object]:
    runtime = _runtime()
    resolved_path = _analytics_resolved_path(db_path)
    with runtime._ANALYTICS_CACHE_LOCK:
        now = time.time()
        _prune_analytics_cache_locked(now)
        generation = runtime._ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0)
        runtime._ANALYTICS_GENERATION_TOUCHED[resolved_path] = now
        key = _analytics_cache_key(db_path, generation)
        hit = runtime._ANALYTICS_CACHE.get(key)
        if hit and now - hit[0] < runtime._ANALYTICS_TTL:
            return hit[1]
        if hit:
            runtime._ANALYTICS_CACHE.pop(key, None)
        _analytics_build_started_locked(resolved_path)

    try:
        if not runtime.USERS_DIR.is_dir():
            runtime.USERS_DIR.mkdir(parents=True, exist_ok=True)
        result = runtime.build_learning_analytics(
            db_path,
            runtime.PROBLEM_BY_ID,
            runtime.load_library_manifest(),
            allowed_db_root=runtime.USERS_DIR,
        )
    except BaseException:
        with runtime._ANALYTICS_CACHE_LOCK:
            _analytics_build_finished_locked(resolved_path)
            _prune_analytics_generations_locked()
        raise

    with runtime._ANALYTICS_CACHE_LOCK:
        _analytics_build_finished_locked(resolved_path)
        if runtime._ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0) == generation:
            created_at = time.time()
            _prune_analytics_cache_locked(created_at)
            runtime._ANALYTICS_CACHE[key] = (created_at, result)
            _prune_analytics_cache_locked(created_at)
        _prune_analytics_generations_locked()
    return result


def invalidate_learning_caches(db_path: Path) -> None:
    _invalidate_analytics_cache(db_path)
    _runtime()._invalidate_dashboard_cache(db_path)
