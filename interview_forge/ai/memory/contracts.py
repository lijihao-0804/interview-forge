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
