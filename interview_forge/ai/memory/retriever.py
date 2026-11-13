"""Deterministic relevance retrieval without embeddings."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .contracts import MemoryItem
from .store import MemoryStore

_ASCII_UNIT_RE = re.compile(r"[a-z0-9_+#.-]+")
_HAN_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_HAN_FUNCTION_CHARS = frozenset(
    "的了是吗呢吧啊呀哦么这那些个一在与和及或我你他她它们请帮被把给从到对以后些"
)
_LOW_SIGNAL_UNITS = frozenset({
    "如何", "怎么", "什么", "为何", "为什么", "是否", "可以", "需要",
    "帮我", "请你", "麻烦", "问题", "用户", "偏好", "记忆", "记住", "忘记",
    "以后", "现在", "每天", "分钟", "小时",
})

_STABLE_PREFERENCE_MARKERS = {
    "preference.explanation_order": (
        "解释", "讲解", "讲讲", "说明", "思路", "为什么", "怎么", "如何",
        "算法", "代码", "实现", "分析", "排查", "回答",
    ),
    "preference.programming_language": (
        "代码", "编程", "示例", "写个", "写一段", "算法题", "用哪种语言", "语言偏好",
    ),
    "goal.target_role": (
        "求职", "简历", "岗位", "职业", "面试准备", "准备面试", "学习路线",
        "学习计划", "复习计划", "刷题计划",
    ),
    "constraint.daily_study_minutes": (
        "学习计划", "复习计划", "学习安排", "每天学习", "学习时间", "刷题计划", "今日计划",
    ),
}


def _units(value: str) -> set[str]:
    """Return topic-bearing terms; common Chinese single characters are noise."""
    text = str(value or "").casefold()
    parts = {
        part.rstrip("._-")
        for part in _ASCII_UNIT_RE.findall(text)
        if part.rstrip("._-")
    }
    for run in _HAN_RUN_RE.findall(text):
        for index in range(len(run) - 1):
            unit = run[index:index + 2]
            if unit in _LOW_SIGNAL_UNITS:
                continue
            if run[index] in _HAN_FUNCTION_CHARS or run[index + 1] in _HAN_FUNCTION_CHARS:
                continue
            parts.add(unit)
    return parts


def _relevance(item: MemoryItem, query: str) -> float:
    query_text = str(query or "").casefold()
    matched = _units(query_text) & _units(item.display_text)
    lexical_score = sum(
        1.5 if any("a" <= char <= "z" or char.isdigit() for char in unit) else 1.0
        for unit in matched
    )
    markers = _STABLE_PREFERENCE_MARKERS.get(item.canonical_key, ())
    if any(marker in query_text for marker in markers):
        return lexical_score + 2.0
    if item.kind in {"goal", "constraint"} and len(matched) < 2:
        # A generic shared word such as 算法 (or a number/time unit) does
        # not make a personal career goal or time limit relevant.
        return 0.0
    return lexical_score


def _recency(item: MemoryItem) -> float:
    try:
        value = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(value.tzinfo) - value).total_seconds() / 86400)
        return max(0.0, 1.0 - min(age_days, 30.0) / 30.0)
    except (TypeError, ValueError, OverflowError):
        return 0.5


class MemoryRetriever:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def retrieve(
        self,
        *,
        user_db: Path | str,
        query: str,
        max_items: int = 6,
        max_tokens: int = 800,
    ) -> list[MemoryItem]:
        if max_items <= 0 or max_tokens <= 0:
            return []
        ranked = []
        for item in self.store.list_active(user_db=user_db):
            relevance = _relevance(item, query)
            if relevance <= 0:
                continue
            score = relevance * 4.0 + item.importance + item.confidence + _recency(item)
            ranked.append((score, item))
        ranked.sort(key=lambda value: (-value[0], value[1].updated_at, value[1].id), reverse=False)
        result: list[MemoryItem] = []
        used = 0
        for _, item in ranked:
            cost = max(1, len(item.display_text) // 3)
            if result and used + cost > max_tokens:
                continue
            if not result and cost > max_tokens:
                continue
            result.append(item)
            used += cost
            if len(result) >= max_items:
                break
        return result


__all__ = ["MemoryRetriever"]
