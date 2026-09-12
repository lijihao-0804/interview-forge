"""Deterministic relevance retrieval without embeddings."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .contracts import MemoryItem
from .store import MemoryStore


def _units(value: str) -> set[str]:
    text = "".join(str(value or "").casefold().split())
    parts = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text))
    chars = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    parts.update("".join(chars[index:index + 2]) for index in range(max(0, len(chars) - 1)))
    return {part for part in parts if part}


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
        query_units = _units(query)
        ranked = []
        for item in self.store.list_active(user_db=user_db):
            item_units = _units(item.display_text + " " + item.canonical_key)
            overlap = len(query_units & item_units)
            score = overlap * 5.0 + item.importance * 1.5 + item.confidence + _recency(item)
            if overlap == 0 and item.importance < 4:
                continue
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
