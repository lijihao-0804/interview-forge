"""Public liveness endpoint."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health", summary="Service liveness")
def health() -> dict[str, bool]:
    return {"ok": True}

