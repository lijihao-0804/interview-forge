"""Public reading and administrator publishing for Code Focus."""
from __future__ import annotations

import asyncio
import sqlite3

from fastapi import APIRouter, Request, Response

from interview_forge.api.support import (
    ApiError, async_require_admin, error_response, json_response, read_json, service_error,
)
from interview_forge.services.code_focus import (
    PublicationConflict, publication_version, publish, read_publication,
)


router = APIRouter()
MAX_PUBLICATION_BYTES = 1024 * 1024


def _headers(version: int) -> dict[str, str]:
    return {"ETag": f'"code-focus-{version}"', "Cache-Control": "no-cache"}


@router.get("/api/code-focus/publication")
def get_publication(request: Request):
    try:
        condition = request.headers.get("if-none-match")
        if condition:
            headers = _headers(publication_version())
            tags = {tag.strip() for tag in condition.split(",")}
            if tags.intersection({"*", headers["ETag"], "W/" + headers["ETag"]}):
                return Response(status_code=304, headers=headers)
        document = read_publication()
        return json_response(document, headers=_headers(document["version"]))
    except sqlite3.Error as exc:
        return service_error(exc)


@router.put("/api/admin/code-focus/publication")
async def put_publication(request: Request):
    _, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=MAX_PUBLICATION_BYTES,
                                  too_large_message="共享文稿的请求大小不能超过 1 MiB")
        document = await asyncio.to_thread(publish, payload)
        return json_response(document, headers=_headers(document["version"]))
    except PublicationConflict:
        return error_response("其他编辑器已更新文稿，请读取最新版本", 409)
    except (ApiError, ValueError, sqlite3.Error) as exc:
        return service_error(exc, write=True)
