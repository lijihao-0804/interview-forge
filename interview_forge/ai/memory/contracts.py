"""Domain contracts for bounded assistant memory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


MemoryKind = Literal["preference", "goal", "constraint", "learning_context"]
MemoryOperation = Literal["upsert", "forget"]
MemorySource = Literal["explicit", "inferred"]


@dataclass(frozen=True)
class MemoryCandidate:
    operation: MemoryOperation
    kind: MemoryKind
    canonical_key: str
    value: Mapping[str, Any]
    display_text: str
    explicit: bool
    confidence: float
    importance: int


@dataclass(frozen=True)
class MemoryPersistenceResult:
    """Server-owned result made available before an explicit answer is generated."""

    explicit: bool
    success: bool
    operation: MemoryOperation | None = None
    count: int = 0
    error_code: str | None = None

    @property
    def context_text(self) -> str:
        if not self.explicit:
            return "本轮没有执行显式长期记忆写入。"
        action = "删除" if self.operation == "forget" else "保存"
        state = "成功" if self.success else "失败"
        return (
            f"服务端已完成显式记忆{action}，persistence_success={str(self.success).lower()}。"
            f"结果：{state}。"
        )


@dataclass(frozen=True)
class MemoryItem:
    id: str
    kind: MemoryKind
    canonical_key: str
    value: Mapping[str, Any]
    display_text: str
    source_type: MemorySource
    source_session_id: str | None
    source_message_id: int | None
    confidence: float
    importance: int
    valid_from: str | None
    valid_to: str | None
    status: str
    created_at: str
    updated_at: str

    def api_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "display_text": self.display_text,
            "source_type": self.source_type,
            "updated_at": self.updated_at,
            "importance": self.importance,
        }
