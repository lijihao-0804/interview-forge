"""HTTP-boundary dependency helpers kept for import compatibility."""
from __future__ import annotations

from fastapi import Request

from interview_forge.api.support import current_user


def request_id(request: Request) -> str:
    """Return a caller-provided request id only for correlation, never secrets."""
    value = (request.headers.get("X-Request-ID") or "").strip()
    return value[:96] if value else ""

