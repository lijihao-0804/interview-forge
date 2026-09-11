"""Persistent AI task queue and lifecycle operations.

This module owns the single process queue/worker state.  Facade lookups are lazy
so legacy ai_coach patch points and provider timing remain unchanged.
"""
from __future__ import annotations

from interview_forge.ai.runtime import facade
from interview_forge.core.runtime import server_runtime

import json
import queue
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import closing, contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.prompts import (
    AI_TASK_STATUSES, MAX_RECENT_TASKS, MAX_TASK_ROWS, PROMPT_VERSION,
)
from interview_forge.ai.quota import (
    _consume_ai_quota, _now_iso, _open_ai_db, _release_ai_quota_reservation,
    _reserve_ai_quota, get_ai_quota,
)
from interview_forge.ai.context_projection import (
    _context_json, _prune_empty, _semantic_coverage,
)
from interview_forge.ai.validation import _json_load, build_rule_fallback

AI_TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")



def load_ai_config():
    return facade().load_ai_config()


def ai_capability(username: str, role: str, daily_limit: int | None = None):
    return facade().ai_capability(username, role, daily_limit)


def model_key(config=None):
    return facade().model_key(config)


def generate_ai_insight(context, config=None, **kwargs):
    return facade().generate_ai_insight(context, config=config, **kwargs)


def debug_ai_event(event, **fields):
    return facade().debug_ai_event(event, **fields)

_AI_QUEUE: queue.Queue[tuple[Path, str]] = queue.Queue(maxsize=256)
_AI_WORKERS: list[threading.Thread] = []
_AI_WORKER_LOCK = threading.Lock()
_AI_RUNTIME_LOCK = threading.Lock()
_AI_ACTIVE_TASKS: set[str] = set()
_AI_PROCESS_ID = uuid.uuid4().hex
_AI_CALL_CONDITION = threading.Condition()
_AI_CALL_ACTIVE = 0


@contextmanager
def _ai_call_slot():
    """Enforce the configured global model-call limit across all workers."""
    global _AI_CALL_ACTIVE
    with _AI_CALL_CONDITION:
        while _AI_CALL_ACTIVE >= load_ai_config().max_concurrent_requests:
            _AI_CALL_CONDITION.wait(timeout=0.5)
        _AI_CALL_ACTIVE += 1
    try:
        yield
    finally:
        with _AI_CALL_CONDITION:
            _AI_CALL_ACTIVE = max(0, _AI_CALL_ACTIVE - 1)
            _AI_CALL_CONDITION.notify_all()


def _worker_loop() -> None:
    while True:
        db_path, task_id = _AI_QUEUE.get()
        try:
            _run_persisted_task(db_path, task_id)
        except Exception:
            # The task runner itself converts failures to a controlled row.  A
            # final guard keeps a worker alive if a migration or test double
            # raises before that conversion point.
            try:
                _finish_task_failure(
                    db_path,
                    task_id,
                    AIServiceError("provider_error", "AI 分析暂时失败，请稍后重试。"),
                )
            except Exception:
                pass
        finally:
            with _AI_RUNTIME_LOCK:
                _AI_ACTIVE_TASKS.discard(task_id)
            _AI_QUEUE.task_done()


def _ensure_workers() -> None:
    target = load_ai_config().max_concurrent_requests
    with _AI_WORKER_LOCK:
        _AI_WORKERS[:] = [item for item in _AI_WORKERS if item.is_alive()]
        while len(_AI_WORKERS) < target:
            worker = threading.Thread(target=_worker_loop, name="interviewforge-ai", daemon=True)
            worker.start()
            _AI_WORKERS.append(worker)


def _recoverable_task_ids() -> set[str]:
    with _AI_RUNTIME_LOCK:
        return set(_AI_ACTIVE_TASKS)


def recover_ai_tasks(db_path: Path) -> int:
    """Converge tasks left by a previous process to a visible terminal state."""
    active = _recoverable_task_ids()
    changed = 0
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT task_id, fallback_json FROM ai_tasks WHERE status IN ('queued', 'running')"
        ).fetchall()
        for row in rows:
            task_id = str(row["task_id"])
            if task_id in active:
                continue
            _release_ai_quota_reservation(connection, task_id)
            connection.execute(
                """UPDATE ai_tasks
                   SET status = 'failed', finished_at = ?, error_category = 'cancelled',
                       error_message = '服务重启后任务已结束，请重新分析', worker_id = NULL
                   WHERE task_id = ? AND status IN ('queued', 'running')""",
                (_now_iso(), task_id),
            )
            changed += 1
        connection.execute("COMMIT")
    return changed


def _parse_json_column(row: sqlite3.Row, name: str, default: Any) -> Any:
    return _json_load(row[name], default)


def _support_labels(refs: Any, context: Mapping[str, Any]) -> list[str]:
    trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
    labels: list[str] = []
    if isinstance(refs, list) and isinstance(trace_map, Mapping):
        for ref in refs:
            entry = trace_map.get(str(ref))
            if isinstance(entry, Mapping):
                label = str(entry.get("label", "")).strip()[:160]
                if label and label not in labels:
                    labels.append(label)
    return labels


def _legacy_evidence_labels(refs: Any, context: Mapping[str, Any]) -> list[str]:
    wanted = {str(item) for item in refs} if isinstance(refs, list) else set()
    entities: set[tuple[str, str]] = set()
    for item in context.get("evidence", []) if isinstance(context, Mapping) else []:
        if isinstance(item, Mapping) and str(item.get("evidence_id")) in wanted:
            entities.add((str(item.get("entity_type")), str(item.get("entity_id"))))
    labels: list[str] = []
    for fact in context.get("facts", []) if isinstance(context, Mapping) else []:
        if not isinstance(fact, Mapping):
            continue
        entity_type = str(fact.get("entity_type"))
        entity_id = str(fact.get("problem_id") if entity_type == "problem" else fact.get("module_id") if entity_type == "module" else fact.get("content_id"))
        if (entity_type, entity_id) in entities:
            label = str(fact.get("title") or fact.get("module_title") or "").strip()[:160]
            if label and label not in labels:
                labels.append(label)
    return labels


def _replace_public_refs(value: Any, context: Mapping[str, Any]) -> Any:
    trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
    if isinstance(value, str) and isinstance(trace_map, Mapping):
        result = value
        for ref, entry in sorted(trace_map.items(), key=lambda item: -len(str(item[0]))):
            if isinstance(entry, Mapping) and entry.get("label"):
                result = result.replace(str(ref), str(entry["label"])[:160])
        return result
    if isinstance(value, list):
        return [_replace_public_refs(item, context) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _replace_public_refs(item, context) for key, item in value.items()}
    return value


def _public_insight(result: Any, context: Mapping[str, Any]) -> Any:
    if not isinstance(result, Mapping):
        return result
    public = {
        key: _replace_public_refs(result.get(key), context)
        for key in ("summary", "strengths", "confidence", "data_gaps") if key in result
    }
    for section in ("weaknesses", "actions"):
        output: list[dict[str, Any]] = []
        for item in result.get(section, []) if isinstance(result.get(section), list) else []:
            if not isinstance(item, Mapping):
                continue
            clean = {
                str(k): _replace_public_refs(v, context)
                for k, v in item.items() if k not in {"support_refs", "evidence_ids", "_support_trace"}
            }
            labels = _support_labels(item.get("support_refs"), context)
            if not labels:
                labels = _legacy_evidence_labels(item.get("evidence_ids"), context)
            if labels:
                clean["support_labels"] = labels
            output.append(clean)
        public[section] = output
    return public


def _public_context(context: Mapping[str, Any]) -> dict[str, Any]:
    digest = context.get("diagnostic_digest", {}) if isinstance(context, Mapping) else {}
    digest = digest if isinstance(digest, Mapping) else {}
    trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
    cases: list[dict[str, Any]] = []
    for item in digest.get("representative_cases", []) if isinstance(digest.get("representative_cases"), list) else []:
        if not isinstance(item, Mapping):
            continue
        entry = trace_map.get(str(item.get("ref")), {}) if isinstance(trace_map, Mapping) else {}
        cases.append(_prune_empty({
            "case_type": item.get("case_type"), "severity": item.get("severity"),
            "label": entry.get("label") if isinstance(entry, Mapping) else item.get("title"),
        }))
    return _prune_empty({
        "task": context.get("task"), "data_as_of": context.get("data_as_of"),
        "diagnostic_digest": {
            "overview": digest.get("overview"), "review_backlog": digest.get("review_backlog"),
            "overdue_distribution": digest.get("overdue_distribution"),
            "round_distribution": digest.get("round_distribution"), "representative_cases": cases,
            "coverage": _semantic_coverage(digest),
        },
    })


def _public_task(row: sqlite3.Row, *, include_context: bool = True) -> dict[str, Any]:
    result = _parse_json_column(row, "result_json", None)
    fallback = _parse_json_column(row, "fallback_json", None)
    context = _parse_json_column(row, "context_preview", {})
    context = context if isinstance(context, Mapping) else {}
    payload: dict[str, Any] = {
        "task_id": str(row["task_id"]),
        "task": str(row["task"]),
        "status": str(row["status"]),
        "snapshot_hash": str(row["snapshot_hash"]),
        "prompt_version": str(row["prompt_version"]),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_category": row["error_category"],
        "error": row["error_message"],
        "result": _public_insight(result, context),
        "fallback": ({**fallback, "result": _public_insight(fallback.get("result"), context)} if isinstance(fallback, Mapping) else fallback),
        "insight_id": row["insight_id"],
    }
    if include_context:
        payload["context_preview"] = _public_context(context)
    return payload


def _public_history_task(row: sqlite3.Row, *, is_latest: bool) -> dict[str, Any]:
    """Small history projection: display data only, without context or tracing metadata."""
    task = _public_task(row, include_context=False)
    context = _parse_json_column(row, "context_preview", {})
    return {
        key: task.get(key) for key in (
            "task_id", "status", "created_at", "started_at", "finished_at",
            "error_category", "error", "result", "fallback", "insight_id",
        )
    } | {
        "data_as_of": context.get("data_as_of") if isinstance(context, Mapping) else None,
        "is_latest": is_latest,
    }


def _finish_task_failure(db_path: Path, task_id: str, error: AIServiceError) -> None:
    fallback_json: str | None = None
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT fallback_json FROM ai_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            connection.execute("ROLLBACK")
            return
        fallback_json = row["fallback_json"]
        connection.execute(
            """UPDATE ai_tasks SET status = 'failed', finished_at = ?,
               error_category = ?, error_message = ?, worker_id = NULL
               WHERE task_id = ? AND status = 'running'""",
            (_now_iso(), error.category, error.user_message, task_id),
        )
        _release_ai_quota_reservation(connection, task_id)
        connection.commit()


def _run_persisted_task(db_path: Path, task_id: str) -> None:
    task_started = time.perf_counter()
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None or str(row["status"]) != "queued":
            connection.execute("COMMIT")
            return
        connection.execute(
            """UPDATE ai_tasks SET status = 'running', started_at = ?, worker_id = ?
               WHERE task_id = ? AND status = 'queued'""",
            (_now_iso(), _AI_PROCESS_ID, task_id),
        )
        connection.execute("COMMIT")
        row = connection.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return
    debug_ai_event("worker_started", task_id=task_id)
    context = _parse_json_column(row, "context_preview", None)
    if not isinstance(context, Mapping):
        _finish_task_failure(db_path, task_id, AIServiceError("invalid_output", "分析上下文无效。"))
        return
    try:
        slot_started = time.perf_counter()
        with _ai_call_slot():
            debug_ai_event(
                "call_slot_acquired",
                task_id=task_id,
                wait_ms=round((time.perf_counter() - slot_started) * 1000, 2),
            )
            def consume_quota() -> None:
                with closing(_open_ai_db(db_path)) as quota_connection:
                    quota_connection.execute("BEGIN IMMEDIATE")
                    _consume_ai_quota(quota_connection, task_id)
                    quota_connection.execute("COMMIT")

            result = generate_ai_insight(
                context, debug_id=task_id, before_model_request=consume_quota
            )
    except AIServiceError as exc:
        debug_ai_event(
            "task_failed",
            task_id=task_id,
            total_ms=round((time.perf_counter() - task_started) * 1000, 2),
            category=exc.category,
        )
        _finish_task_failure(db_path, task_id, exc)
        return
    except Exception:
        _finish_task_failure(
            db_path,
            task_id,
            AIServiceError("provider_error", "AI 分析暂时失败，请稍后重试。"),
        )
        return
    insight_id = uuid.uuid4().hex
    result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT status FROM ai_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if current is None or str(current["status"]) != "running":
            connection.execute("COMMIT")
            return
        task_row = connection.execute(
            "SELECT snapshot_hash, prompt_version, model_key, context_preview FROM ai_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        task_context = _parse_json_column(task_row, "context_preview", {}) if task_row else {}
        data_as_of = task_context.get("data_as_of") if isinstance(task_context, Mapping) else None
        connection.execute(
            """INSERT INTO ai_insights(
               insight_id, task_id, created_at, snapshot_hash, prompt_version, model_key,
               data_as_of, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                insight_id,
                task_id,
                _now_iso(),
                task_row["snapshot_hash"],
                task_row["prompt_version"],
                task_row["model_key"],
                data_as_of,
                result_json,
            ),
        )
        connection.execute(
            """UPDATE ai_tasks SET status = 'succeeded', finished_at = ?, result_json = ?,
               insight_id = ?, error_category = NULL, error_message = NULL, worker_id = NULL
               WHERE task_id = ? AND status = 'running'""",
            (_now_iso(), result_json, insight_id, task_id),
        )
        connection.execute("COMMIT")
    debug_ai_event(
        "task_succeeded",
        task_id=task_id,
        total_ms=round((time.perf_counter() - task_started) * 1000, 2),
    )


def _prune_tasks(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """SELECT task_id FROM ai_tasks
           WHERE status NOT IN ('queued', 'running')
           ORDER BY created_at DESC LIMIT -1 OFFSET ?""",
        (MAX_TASK_ROWS,),
    ).fetchall()
    for row in rows:
        task_id = str(row["task_id"])
        connection.execute("DELETE FROM ai_insights WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM ai_tasks WHERE task_id = ?", (task_id,))


def create_ai_task(
    db_path: Path, context: Mapping[str, Any], username: str, role: str,
    daily_limit: int | None = None,
) -> dict[str, Any]:
    """Create or reuse one diagnosis task and enqueue it without blocking HTTP."""
    config = load_ai_config()
    capability = ai_capability(username, role, daily_limit)
    fallback = build_rule_fallback(context)
    public_fallback = {**fallback, "result": _public_insight(fallback.get("result"), context)}
    if not capability["can_analyze"]:
        status_map = {
            "disabled": HTTPStatus.SERVICE_UNAVAILABLE,
            "not_configured": HTTPStatus.SERVICE_UNAVAILABLE,
            "not_allowed": HTTPStatus.FORBIDDEN,
            "quota_disabled": HTTPStatus.TOO_MANY_REQUESTS,
        }
        raise AIServiceError(
            str(capability["status"]),
            str(capability["message"]),
            status=status_map.get(str(capability["status"]), HTTPStatus.SERVICE_UNAVAILABLE),
            fallback=public_fallback,
        )
    _context_json(context)  # validate the LLM projection before persisting the task
    full_context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    snapshot_hash = str(context.get("snapshot_hash", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash):
        raise AIServiceError("invalid_output", "分析上下文无效。", fallback=public_fallback)
    current_model_key = model_key(config)
    recover_ai_tasks(db_path)
    created = False
    task_id = ""
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        params = ("learning_diagnosis", snapshot_hash, PROMPT_VERSION, current_model_key)
        existing = connection.execute(
            """SELECT * FROM ai_tasks
               WHERE task = ? AND snapshot_hash = ? AND prompt_version = ? AND model_key = ?
                 AND status IN ('queued', 'running', 'succeeded')
               ORDER BY CASE status WHEN 'succeeded' THEN 0 ELSE 1 END, created_at DESC
               LIMIT 1""",
            params,
        ).fetchone()
        if existing is not None:
            connection.execute("COMMIT")
            return {
                **_public_task(existing, include_context=True), "reused": True,
                "quota": get_ai_quota(db_path, role, daily_limit=daily_limit),
            }
        task_id = uuid.uuid4().hex
        now = _now_iso()
        # Register the task before committing it so a concurrent first GET
        # cannot mistake this process's tiny insert→enqueue window for a task
        # abandoned by a previous process.
        with _AI_RUNTIME_LOCK:
            _AI_ACTIVE_TASKS.add(task_id)
        try:
            connection.execute(
                """INSERT INTO ai_tasks(
                   task_id, task, status, snapshot_hash, prompt_version, model_key,
                   created_at, context_preview, fallback_json
                ) VALUES (?, 'learning_diagnosis', 'queued', ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    snapshot_hash,
                    PROMPT_VERSION,
                    current_model_key,
                    now,
                    full_context_json,
                    json.dumps(fallback, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            if role != "admin":
                try:
                    _reserve_ai_quota(connection, task_id, daily_limit=daily_limit)
                except AIServiceError as exc:
                    exc.fallback = public_fallback
                    raise
            _prune_tasks(connection)
            connection.execute("COMMIT")
        except BaseException:
            with _AI_RUNTIME_LOCK:
                _AI_ACTIVE_TASKS.discard(task_id)
            raise
        created = True
        row = connection.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not created or row is None:
        with _AI_RUNTIME_LOCK:
            _AI_ACTIVE_TASKS.discard(task_id)
        raise AIServiceError("provider_error", "AI 分析任务创建失败。", fallback=public_fallback)
    _ensure_workers()
    try:
        _AI_QUEUE.put_nowait((Path(db_path), task_id))
    except queue.Full:
        with _AI_RUNTIME_LOCK:
            _AI_ACTIVE_TASKS.discard(task_id)
        error = AIServiceError("concurrency", "当前分析任务较多，请稍后重试。", status=HTTPStatus.TOO_MANY_REQUESTS, fallback=public_fallback)
        _finish_task_failure(db_path, task_id, error)
        with closing(_open_ai_db(db_path)) as connection:
            failed_row = connection.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
        row = failed_row or row
    return {
        **_public_task(row, include_context=True),
        "reused": False,
        "quota": get_ai_quota(db_path, role, daily_limit=daily_limit),
    }


def get_ai_task(
    db_path: Path, task_id: str, role: str = "user", daily_limit: int | None = None
) -> dict[str, Any] | None:
    if not AI_TASK_ID_RE.fullmatch(task_id):
        return None
    recover_ai_tasks(db_path)
    with closing(_open_ai_db(db_path)) as connection:
        row = connection.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
    return ({**_public_task(row, include_context=True),
             "quota": get_ai_quota(db_path, role, daily_limit=daily_limit)}
            if row is not None else None)


def get_recent_ai_tasks(
    db_path: Path, username: str, role: str, daily_limit: int | None = None
) -> dict[str, Any]:
    recover_ai_tasks(db_path)
    with closing(_open_ai_db(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM ai_tasks ORDER BY created_at DESC LIMIT ?", (MAX_RECENT_TASKS,)
        ).fetchall()
    return {
        "items": [
            _public_history_task(row, is_latest=(index == 0))
            for index, row in enumerate(rows)
        ],
        "capability": ai_capability(username, role, daily_limit),
        "quota": get_ai_quota(db_path, role, daily_limit=daily_limit),
    }


def cancel_ai_task(
    db_path: Path, task_id: str, role: str = "user", daily_limit: int | None = None
) -> dict[str, Any]:
    if not AI_TASK_ID_RE.fullmatch(task_id):
        raise AIServiceError("cancelled", "任务不存在或已结束。", status=HTTPStatus.NOT_FOUND)
    recover_ai_tasks(db_path)
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            connection.execute("ROLLBACK")
            raise AIServiceError("cancelled", "任务不存在或已结束。", status=HTTPStatus.NOT_FOUND)
        status = str(row["status"])
        if status == "queued":
            _release_ai_quota_reservation(connection, task_id)
            connection.execute(
                """UPDATE ai_tasks SET status = 'cancelled', finished_at = ?,
                   error_category = 'cancelled', error_message = '任务已取消'
                   WHERE task_id = ? AND status = 'queued'""",
                (_now_iso(), task_id),
            )
            connection.execute("COMMIT")
            with _AI_RUNTIME_LOCK:
                _AI_ACTIVE_TASKS.discard(task_id)
        elif status == "running":
            connection.execute("ROLLBACK")
            raise AIServiceError("cancelled", "任务已开始处理，暂不能取消。", status=HTTPStatus.CONFLICT)
        else:
            connection.execute("COMMIT")
            raise AIServiceError("cancelled", "任务已结束，不能取消。", status=HTTPStatus.CONFLICT)
    result = get_ai_task(db_path, task_id, role, daily_limit)
    return result or {"task_id": task_id, "status": "cancelled"}


def reset_ai_runtime_for_tests() -> None:
    """Clear in-memory queue bookkeeping; daemon workers are intentionally kept."""
    with _AI_RUNTIME_LOCK:
        _AI_ACTIVE_TASKS.clear()
    while True:
        try:
            _AI_QUEUE.get_nowait()
            _AI_QUEUE.task_done()
        except queue.Empty:
            break


from interview_forge.runtime.task_manager import TaskBackend, task_manager


def _registered_submit(*args, **kwargs):
    return server_runtime.create_ai_task(*args, **kwargs)


def _registered_query(*args, **kwargs):
    return server_runtime.get_ai_task(*args, **kwargs)


def _registered_cancel(*args, **kwargs):
    return server_runtime.cancel_ai_task(*args, **kwargs)


task_manager.register(
    "ai",
    TaskBackend(
        submit=_registered_submit,
        query=_registered_query,
        cancel=_registered_cancel,
    ),
)
