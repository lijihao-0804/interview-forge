"""Serve an operator-supplied archive outside the public repository.

Every resource (including JSON, media and JavaScript) rechecks the real session.
Directory mode serves a separately installed site tree; ZIP mode is legacy only.
Neither mode indexes, copies to web roots or caches content publicly.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import Response

from interview_forge.api import support
from interview_forge.core.paths import ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.core.roles import effective_role

from interview_forge.services.private_archive_store import (
    MAX_MEMBER_BYTES, member_type, private_directory, read_directory_member,
)

router = APIRouter()
HEADERS = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache",
           "Vary": "Cookie", "X-Content-Type-Options": "nosniff",
           "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin",
           "Cross-Origin-Resource-Policy": "same-origin"}


def _denied(request: Request):
    user = support.current_user(request)
    if user is None:
        return support.error_response("未登录", 401, headers=HEADERS)
    if effective_role(user, permanent_username=server_runtime.PERMANENT_ADMIN_USERNAME) != "super_admin":
        return support.error_response("此档案仅限永久管理员访问", 403, headers=HEADERS)
    return None


def _archive_path() -> Path | None:
    value = os.environ.get("INTERVIEW_FORGE_PRIVATE_ARCHIVE", "").strip()
    if not value:
        return None
    path = Path(value)
    # Resolve symlinks too: configuration must never expose a repo-local file.
    if not path.is_absolute():
        return None
    path = path.resolve()
    if path.is_relative_to(ROOT.resolve()) or not path.is_file():
        return None
    return path


def _read_member(path: str) -> bytes:
    directory = os.environ.get("INTERVIEW_FORGE_PRIVATE_ARCHIVE_DIR", "").strip()
    if directory:
        # An invalid configured directory never silently falls back to an old ZIP.
        return read_directory_member(private_directory(directory), path)
    archive = _archive_path()
    if archive is None:
        raise ValueError("Private teaching site is not configured")
    with zipfile.ZipFile(archive) as package:
        info = package.getinfo("site/" + path)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if info.is_dir() or mode not in (0, stat.S_IFREG) or info.file_size > MAX_MEMBER_BYTES:
            raise FileNotFoundError(path)
        return package.read(info)


@router.get("/api/private-archive-status")
def archive_status(request: Request):
    denied = _denied(request)
    if denied is not None:
        return denied
    try:
        _read_member("index.html")
        available = True
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError):
        available = False
    return support.json_response({"available": available,
                                  "url": "/api/private-archive/index.html"}, headers=HEADERS)


@router.api_route("/api/private-archive/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def archive_resource(request: Request, path: str):
    denied = _denied(request)
    if denied is not None:
        return denied
    media_type = member_type(path)
    if media_type is None:
        return support.error_response("Not Found", 404, headers=HEADERS)
    try:
        body = _read_member(path)
    except (KeyError, FileNotFoundError, NotADirectoryError):
        return support.error_response("Not Found", 404, headers=HEADERS)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        return support.error_response("私有教学站尚未安装或暂时无法读取，请联系服务器管理员。", 503, headers=HEADERS)
    if path == "index.html":
        # Leave scripts, history templates/data and animation code byte-for-byte intact.
        body = body.replace(b'./assets/hljs.js', b'/assets/vendor/highlight-11.11.1.min.js')
        body = body.replace(b'<script defer src="./assets/app.js">', b'<script defer src="/assets/private-archive-highlight.js"></script><script defer src="./assets/app.js">')
        body = body.replace(b"</head>", b'<link rel="stylesheet" href="/assets/private-archive-theme.css?v=1"></head>', 1)
        body = body.replace(b"</body>", b'<script src="/assets/private-archive-shell.js?v=1" defer></script></body>', 1)
    return Response(content=b"" if request.method == "HEAD" else body,
                    media_type=media_type, headers=HEADERS)
