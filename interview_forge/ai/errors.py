"""Stable service errors shared by the AI coach execution layers."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


class AIServiceError(RuntimeError):
    """Controlled error that is safe to serialize to a user-facing API."""

    def __init__(
        self,
        category: str,
        user_message: str,
        *,
        status: HTTPStatus = HTTPStatus.SERVICE_UNAVAILABLE,
        fallback: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.user_message = user_message
        self.status = status
        self.fallback = fallback
        self.details = details
