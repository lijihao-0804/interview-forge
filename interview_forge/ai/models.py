"""Small transport value objects shared by AI provider adapters."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StreamEnvelope:
    content: str
    usage_metadata: dict[str, int]
