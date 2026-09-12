"""Cheap memory gate and secret-safe write policy."""
from __future__ import annotations

import re
from dataclasses import replace
from hashlib import sha256

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
_LANGUAGE_MARKERS = ("python", "java", "javascript", "typescript", "c++", "rust", "golang", "go")


def canonicalize_key(kind: str, canonical_key: str, display_text: str) -> str:
    """Keep provider keys concrete enough that unrelated facts do not collide."""
    prefix = f"{kind}."
    raw = " ".join(str(canonical_key or "").strip().split())
    lowered = raw.casefold()
    display = str(display_text or "").casefold()
    if kind == "preference":
        if "先讲思路" in display or "讲思路" in display or "explanation_order" in lowered:
            return "preference.explanation_order"
        if any(marker in display for marker in _LANGUAGE_MARKERS) or "programming_language" in lowered:
            return "preference.programming_language"
        if lowered in {"explanation_style", "preference", "style"}:
            return "preference.fact_" + sha256(display.encode("utf-8")).hexdigest()[:12]
    if kind == "constraint":
        if re.search(r"(?:每天|每日).{0,10}\d+\s*(?:分钟|分|小时)", display):
            return "constraint.daily_study_minutes"
        if lowered in {"study_constraint", "constraint"}:
            return "constraint.fact_" + sha256(display.encode("utf-8")).hexdigest()[:12]
    if kind == "goal":
        if any(marker in display for marker in ("后端", "前端", "全栈", "算法工程", "数据工程")):
            return "goal.target_role"
        if lowered in {"learning_goal", "goal"}:
            return "goal.fact_" + sha256(display.encode("utf-8")).hexdigest()[:12]
    if kind == "learning_context" and lowered in {"long_term_learning_context", "learning_context"}:
        return "learning_context.fact_" + sha256(display.encode("utf-8")).hexdigest()[:12]
    if raw.startswith(prefix) and len(raw) > len(prefix):
        return raw[:80]
    slug = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", raw).strip("._-")
    if not slug:
        slug = "fact_" + sha256(display.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{slug}"[:80]


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
        canonical_key = canonicalize_key(candidate.kind, candidate.canonical_key, candidate.display_text)
        if contains_secret(canonical_key):
            return None
        return replace(
            candidate,
            canonical_key=canonical_key,
            confidence=confidence,
            importance=importance,
        )


__all__ = ["MemoryPolicy", "canonicalize_key", "contains_secret", "memory_worthy"]
