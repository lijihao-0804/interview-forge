"""Deterministic Learning Context selection for the conversational assistant."""
from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from interview_forge.ai.context_projection import project_learning_context_for_chat
from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.analytics.cache import analytics_cached
from interview_forge.analytics.context_compiler import (
    ContextCompilerError,
    compile_learning_context,
)


_PROBLEM_QUERY_RE = re.compile(
    r"(?:第\s*([0-9]{1,9})\s*题|([0-9]{1,9})\s*题|题\s*([0-9]{1,9}))"
)
_PROBLEM_REVIEW_MARKERS = ("复习", "为什么错", "掌握情况")
_TODAY_MARKERS = ("今天做什么", "今天复习什么", "今日计划")
_DIAGNOSIS_MARKERS = ("最近状态", "我的弱项", "最近学得怎么样")
_ROUTE_MARKERS = ("学习路线", "接下来学什么")

CHAT_TASK_POLICIES: dict[str, str] = {
    "today_plan": "small",
    "learning_diagnosis": "medium",
    "learning_route": "medium",
    "problem_review": "medium",
}


def select_learning_task(query: str) -> dict[str, Any] | None:
    """Select only explicit learning intents; ordinary chat returns ``None``."""
    if not isinstance(query, str):
        return None
    text = " ".join(query.strip().split())
    if not text:
        return None

    problem_match = _PROBLEM_QUERY_RE.search(text)
    if problem_match and any(marker in text for marker in _PROBLEM_REVIEW_MARKERS):
        raw_problem_id = next(
            group for group in problem_match.groups() if group is not None
        )
        return {
            "task": "problem_review",
            "target_problem_id": int(raw_problem_id),
            "budget_tier": CHAT_TASK_POLICIES["problem_review"],
        }
    for marker in _TODAY_MARKERS:
        if marker in text:
            return {"task": "today_plan", "budget_tier": CHAT_TASK_POLICIES["today_plan"]}
    for marker in _DIAGNOSIS_MARKERS:
        if marker in text:
            return {
                "task": "learning_diagnosis",
                "budget_tier": CHAT_TASK_POLICIES["learning_diagnosis"],
            }
    for marker in _ROUTE_MARKERS:
        if marker in text:
            return {
                "task": "learning_route",
                "budget_tier": CHAT_TASK_POLICIES["learning_route"],
            }
    return None


def _quality_from_analytics(analytics: Any) -> dict[str, Any]:
    if isinstance(analytics, Mapping) and isinstance(analytics.get("data_quality"), Mapping):
        return dict(analytics["data_quality"])
    return {
        "status": "unavailable",
        "notes": ["学习数据不足，无法生成该学习上下文。"],
    }


def _unavailable_result(
    selection: Mapping[str, Any],
    analytics: Any,
) -> dict[str, Any]:
    quality = _quality_from_analytics(analytics)
    if not quality.get("notes"):
        quality["notes"] = ["学习数据不足，无法生成该学习上下文。"]
    quality.setdefault("status", "unavailable")
    projection = {
        "context_schema_version": "context-v1",
        "task": selection["task"],
        "data_quality": quality,
        "summary": {"availability": "unavailable"},
        "facts": [],
        "signals": [],
        "profile": {},
        "data_as_of": None,
    }
    return {
        "task": selection["task"],
        "target_problem_id": selection.get("target_problem_id"),
        "budget_tier": selection["budget_tier"],
        "available": False,
        "context": None,
        "projection": project_learning_context_for_chat(projection, max_chars=1_800),
        "data_quality": quality,
    }


def _record_compile_failure(selection: Mapping[str, Any], exc: BaseException) -> None:
    """Record only safe exception metadata; never include learning content."""
    debug_ai_event(
        "chat_learning_context_failed",
        task=str(selection.get("task", "unknown")),
        error_type=type(exc).__name__,
    )


class LearningContextProvider:
    """Build a short-lived, task-specific view over the existing analytics compiler."""

    def build_for_task(
        self,
        *,
        user_db: Path | str,
        task: str,
        problem_id: int | None = None,
    ) -> dict[str, Any]:
        """Build one explicit task without asking a Tool to parse SQLite."""
        if task not in CHAT_TASK_POLICIES:
            raise ValueError("学习上下文任务不正确")
        if task == "problem_review" and (problem_id is None or int(problem_id) <= 0):
            raise ValueError("题目复习需要有效题号")
        selection: dict[str, Any] = {
            "task": task,
            "budget_tier": CHAT_TASK_POLICIES[task],
        }
        if problem_id is not None:
            selection["target_problem_id"] = int(problem_id)
        return self._build_selection(user_db=user_db, selection=selection)

    def _build_selection(
        self,
        *,
        user_db: Path | str,
        selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        analytics: Any = None
        try:
            analytics = analytics_cached(Path(user_db))
            compiled = compile_learning_context(
                analytics,
                str(selection["task"]),
                user_request="",
                target_problem_id=selection.get("target_problem_id"),
                budget_tier=str(selection["budget_tier"]),
            )
        except (ContextCompilerError, ValueError, TypeError) as exc:
            _record_compile_failure(selection, exc)
            return _unavailable_result(selection, analytics)
        except Exception as exc:
            # Analytics is a read-only enhancement to chat.  A stale, missing,
            # or temporarily unreadable learning DB must not break ordinary AI.
            _record_compile_failure(selection, exc)
            return _unavailable_result(selection, analytics)

        projection = project_learning_context_for_chat(
            compiled,
            include_user_request=False,
            max_chars=1_800,
        )
        return {
            "task": selection["task"],
            "target_problem_id": selection.get("target_problem_id"),
            "budget_tier": selection["budget_tier"],
            "available": True,
            "context": compiled,
            "projection": projection,
            "data_quality": compiled.get("data_quality", {}),
        }

    def build(self, *, user_db: Path | str, query: str) -> dict[str, Any] | None:
        selection = select_learning_task(query)
        if selection is None:
            return None
        return self._build_selection(user_db=user_db, selection=selection)


__all__ = ["CHAT_TASK_POLICIES", "LearningContextProvider", "select_learning_task"]
