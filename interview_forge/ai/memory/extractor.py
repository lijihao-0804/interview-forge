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


_EXPLICIT_MEMORY_RE = re.compile(
    r"^(?:请你|请|帮我|麻烦你|麻烦)?\s*(?:以后\s*)?(?:请\s*)?"
    r"(?:记住|牢记|记得)(?=\s*(?:我|我的|以后|这|该|用户|[:：，,]|$))"
)
_EXPLICIT_FORGET_RE = re.compile(
    r"^(?:请你|请|帮我|麻烦你|麻烦)?\s*(?:以后\s*)?(?:请\s*)?"
    r"(?:不要再记住|别再记住|忘记|删除|清除|不要忘记|不要忘)"
    r"(?=\s*(?:我|我的|这个|这条|之前|刚才|关于|这些|该|所有|[:：，,]|$))"
)


def is_explicit_memory_request(message: str) -> bool:
    text = " ".join(str(message or "").strip().split())
    return bool(text) and bool(_EXPLICIT_MEMORY_RE.match(text) or _EXPLICIT_FORGET_RE.match(text))


def _deterministic_candidate(message: str) -> MemoryCandidate | None:
    text = " ".join(message.strip().split())
    if not memory_worthy(text):
        return None
    forget = any(marker in text for marker in ("忘记", "不要再记住", "别再记住"))
    language = re.search(r"\b(Python|JavaScript|TypeScript|Java|Go|Rust|C\+\+)\b", text, re.I)
    if language and any(marker in text for marker in ("喜欢", "偏好", "使用", "用")):
        kind, key, importance = "preference", "preference.programming_language", 4
    elif any(marker in text for marker in ("先讲思路", "先讲直觉", "讲思路", "解释算法先")):
        kind, key, importance = "preference", "preference.explanation_order", 4
    elif re.search(r"(?:每天|每日).{0,10}\d+\s*(?:分钟|分|小时)", text):
        kind, key, importance = "constraint", "constraint.daily_study_minutes", 3
    elif re.search(r"(?:长期)?目标(?:是|为)?\s*(?:后端|前端|全栈|算法工程|数据工程)", text):
        kind, key, importance = "goal", "goal.target_role", 4
    elif forget and "偏好" in text:
        # A generic legacy phrase has one intentionally narrow meaning.  More
        # specific forget requests are handled by the structured extractor.
        kind, key, importance = "preference", "preference.explanation_order", 4
    else:
        # Do not claim that every marker has a deterministic interpretation.
        # Complex worthy messages must reach the structured extractor.
        return None
    if forget:
        return MemoryCandidate("forget", kind, key, {}, "删除相关长期记忆", True, 1.0, importance)
    prefix = re.sub(r"^(请)?(记住|以后请记住|以后|通常|长期目标是)[:：，,]?\s*", "", text)
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
                    item.display_text, item.explicit or is_explicit_memory_request(message),
                    item.confidence, item.importance,
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


__all__ = ["MemoryExtractor", "is_explicit_memory_request"]
