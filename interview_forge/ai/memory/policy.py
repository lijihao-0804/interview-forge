"""Cheap memory gate and secret-safe write policy."""
from __future__ import annotations

import re
from dataclasses import replace

from .contracts import MemoryCandidate


_WORTH_MARKERS = (
    "记住", "不要忘", "以后", "通常", "长期", "目标", "希望", "不喜欢",
    "喜欢", "偏好", "忘记", "不要再记住", "别再记住",
)
_SECRET_MARKERS = (
    "password", "api key", "apikey", "cookie", "token", "leetcode_session",
    "csrf", "authorization", "密码", "令牌", "凭证", "密钥", "访问令牌",
)
_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)(?:[^\s\\/]+[\\/])+[^\s]+")


def memory_worthy(message: str) -> bool:
    text = " ".join(str(message or "").strip().split()).casefold()
    return bool(text) and any(marker.casefold() in text for marker in _WORTH_MARKERS)


def contains_secret(value: str) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in _SECRET_MARKERS) or bool(_PATH_RE.search(text))


class MemoryPolicy:
    """Final server-side decision before a candidate reaches SQLite."""

    def accept(self, candidate: MemoryCandidate) -> MemoryCandidate | None:
        if candidate.kind not in {"preference", "goal", "constraint", "learning_context"}:
            return None
        if candidate.operation not in {"upsert", "forget"}:
            return None
        if not candidate.canonical_key or contains_secret(candidate.canonical_key):
            return None
        if contains_secret(candidate.display_text):
            return None
        if candidate.operation == "upsert" and any(contains_secret(str(v)) for v in candidate.value.values()):
            return None
        confidence = min(1.0, max(0.0, float(candidate.confidence)))
        importance = min(5, max(1, int(candidate.importance)))
        # A one-off inferred preference is not stable enough to persist.
        if not candidate.explicit and (confidence < 0.8 or importance < 3):
            return None
        return replace(candidate, confidence=confidence, importance=importance)


__all__ = ["MemoryPolicy", "contains_secret", "memory_worthy"]
