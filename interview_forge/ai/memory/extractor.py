"""Structured memory extraction with a deterministic safe baseline."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .contracts import MemoryCandidate
from .policy import MemoryPolicy, memory_worthy


class _ExtractedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = "upsert"
    kind: str = "preference"
    canonical_key: str = Field(min_length=1, max_length=80)
    value: dict[str, Any] = Field(default_factory=dict)
    display_text: str = Field(min_length=1, max_length=240)
    explicit: bool = False
    confidence: float = 0.8
    importance: int = 3


class _ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[_ExtractedCandidate] = Field(default_factory=list, max_length=4)


def _deterministic_candidate(message: str) -> MemoryCandidate | None:
    text = " ".join(message.strip().split())
    if not memory_worthy(text):
        return None
    forget = any(marker in text for marker in ("忘记", "不要再记住", "别再记住"))
    preference = any(marker in text for marker in ("喜欢", "偏好", "讲思路", "解释算法"))
    goal = any(marker in text for marker in ("目标", "想学", "希望学", "准备") )
    constraint = any(marker in text for marker in ("每天", "不喜欢", "不要") )
    if preference:
        kind, key, importance = "preference", "explanation_style", 4
    elif goal:
        kind, key, importance = "goal", "learning_goal", 4
    elif constraint:
        kind, key, importance = "constraint", "study_constraint", 3
    else:
        kind, key, importance = "learning_context", "long_term_learning_context", 3
    if forget:
        return MemoryCandidate("forget", kind, key, {}, "删除相关长期记忆", True, 1.0, importance)
    prefix = re.sub(r"^(请)?(记住|以后|通常|长期目标是)[:：，,]?\s*", "", text)
    display = prefix[:240] or text[:240]
    return MemoryCandidate(
        "upsert", kind, key, {"text": display[:300]},
        display, any(marker in text for marker in ("记住", "以后", "目标", "希望")),
        1.0 if "记住" in text else 0.82,
        importance,
    )


class MemoryExtractor:
    """Extract at most a few candidates; it never writes to the database."""

    def __init__(self, *, policy: MemoryPolicy | None = None) -> None:
        self.policy = policy or MemoryPolicy()

    def _provider_candidates(self, model: Any, message: str) -> list[MemoryCandidate]:
        structured_factory = getattr(model, "with_structured_output", None)
        invoke = getattr(model, "invoke", None)
        if not callable(structured_factory) or not callable(invoke):
            return []
        prompt = (
            "从下面用户消息中提取稳定、未来有用的长期记忆。只返回 candidates JSON。"
            "不得保存密码、token、cookie、凭证、路径或任何秘密；普通短期状态返回空列表。\n"
            f"用户消息：{message}"
        )
        try:
            value = structured_factory(_ExtractionEnvelope).invoke([
                ("system", "你是严格的长期记忆提取器。"),
                ("human", prompt),
            ])
        except Exception:
            return []
        if isinstance(value, _ExtractionEnvelope):
            raw = value.candidates
        elif isinstance(value, Mapping):
            try:
                raw = _ExtractionEnvelope.model_validate(value).candidates
            except Exception:
                raw = []
        else:
            try:
                decoded = json.loads(str(value))
                raw = _ExtractionEnvelope.model_validate(decoded).candidates
            except Exception:
                raw = []
        result = []
        for item in raw:
            try:
                result.append(MemoryCandidate(
                    item.operation, item.kind, item.canonical_key, item.value,
                    item.display_text, item.explicit, item.confidence, item.importance,
                ))
            except Exception:
                continue
        return result

    def extract(self, message: str, *, model: Any = None) -> list[MemoryCandidate]:
        if not memory_worthy(message):
            return []
        deterministic = _deterministic_candidate(message)
        candidates = [deterministic] if deterministic is not None else []
        if not candidates and model is not None:
            candidates = self._provider_candidates(model, message)
        accepted = []
        for candidate in candidates[:4]:
            value = self.policy.accept(candidate)
            if value is not None:
                accepted.append(value)
        return accepted


__all__ = ["MemoryExtractor"]
