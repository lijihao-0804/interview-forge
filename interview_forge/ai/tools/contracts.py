"""Stable domain contracts shared by tool runtimes and future adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from pydantic import BaseModel


class ToolKind(str, Enum):
    READ = "read"
    ACTION = "action"


@dataclass
class ToolExecutionContext:
    """Server-owned context; none of these fields are model-controlled args."""

    user_db: Path
    session_id: str
    turn_id: str
    user_message_id: int
    current_query: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, "ToolResult"] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    data: dict[str, Any]
    display_text: str | None = None


ToolHandler = Callable[
    [ToolExecutionContext, BaseModel],
    Any | Awaitable[Any],
]
ConfirmationBuilder = Callable[[BaseModel], str]


class ToolHandlerError(Exception):
    """A safe, expected handler failure with a stable public error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolSpec:
    name: str
    display_name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    kind: ToolKind = ToolKind.READ
    requires_confirmation: bool = False
    timeout_seconds: float = 8.0
    max_result_tokens: int = 1500
    confirmation_builder: ConfirmationBuilder | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("tool name must be a non-empty identifier")
        if self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")
        if self.max_result_tokens <= 0:
            raise ValueError("tool result budget must be positive")
        if not callable(self.handler):
            raise TypeError("tool handler must be callable")


@dataclass(frozen=True)
class ToolExecutionResult:
    """Safe result returned by ToolRuntime; internal exceptions never escape here."""

    tool_name: str
    call_id: str
    status: str
    result: ToolResult | None = None
    error_code: str | None = None
    error_message: str | None = None
    cache_hit: bool = False
    run_id: str = ""
    duration_ms: int = 0
    arguments: Mapping[str, Any] = field(default_factory=dict)
    action_id: str | None = None
    confirmation_text: str | None = None
    expires_at: str | None = None

    @property
    def display_text(self) -> str | None:
        return self.result.display_text if self.result is not None else None

    def model_payload(self) -> dict[str, Any]:
        if self.status in {"ok", "cache_hit"} and self.result is not None:
            return {
                "ok": True,
                "tool": self.tool_name,
                "data": self.result.data,
            }
        payload = {
            "ok": False,
            "tool": self.tool_name,
            "error": {
                "code": self.error_code or "tool_error",
                "message": self.error_message or "工具暂时不可用",
            },
        }
        if self.action_id:
            payload["action_id"] = self.action_id
        return payload
