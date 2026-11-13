"""Public, read-only learning catalog metadata."""
from __future__ import annotations

from fastapi import APIRouter

from interview_forge.api.support import error_response, json_response
from interview_forge.services.catalog import public_catalog

router = APIRouter()


@router.get("/api/catalog")
def catalog():
    try:
        return json_response(
            public_catalog(),
            headers={"Cache-Control": "public, max-age=300"},
        )
    except (OSError, ValueError, TypeError):
        return error_response("公开目录暂时不可用", 500)
