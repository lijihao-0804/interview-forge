"""Serve an operator-supplied archive outside the public repository.

Every resource (including JSON, media and JavaScript) rechecks the real session.
The archive is never extracted, indexed, copied to web roots or cached publicly.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import Response

from interview_forge.api import support
from interview_forge.core.paths import ROOT
from interview_forge.core.runtime import server_runtime

router = APIRouter()
HEADERS = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache",
           "Vary": "Cookie", "X-Content-Type-Options": "nosniff",
           "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin",
           "Cross-Origin-Resource-Policy": "same-origin"}


def _denied(request: Request):
    user = support.current_user(request)
    if user is None:
        return support.error_response("未登录", 401, headers=HEADERS)
    configured = str(server_runtime.PERMANENT_ADMIN_USERNAME).strip()
    if not configured or str(user["role"]) != "admin" or str(user["username"]) != configured:
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


@router.get("/api/private-archive-status")
def archive_status(request: Request):
    denied = _denied(request)
    if denied is not None:
        return denied
    return support.json_response({"available": _archive_path() is not None,
                                  "url": "/api/private-archive/index.html"}, headers=HEADERS)


@router.api_route("/api/private-archive/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def archive_resource(request: Request, path: str):
    denied = _denied(request)
    if denied is not None:
        return denied
    if not path or path.startswith("/") or "\\" in path or "%" in path or any(
        part in ("", ".", "..") or part.startswith(".") for part in path.split("/")
    ):
        return support.error_response("Not Found", 404, headers=HEADERS)
    suffix = PurePosixPath(path).suffix.lower()
    types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript",
             ".json": "application/json", ".webp": "image/webp", ".png": "image/png",
             ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".woff2": "font/woff2"}
    if suffix not in types or not (path == "index.html" or path.startswith(("assets/", "data/"))):
        return support.error_response("Not Found", 404, headers=HEADERS)
    archive = _archive_path()
    if archive is None:
        return support.error_response("私有档案尚未配置，请由服务器管理员安装附件。", 503, headers=HEADERS)
    try:
        with zipfile.ZipFile(archive) as package:
            info = package.getinfo("site/" + path)
            if info.is_dir() or info.file_size > 32 * 1024 * 1024:
                return support.error_response("Not Found", 404, headers=HEADERS)
            body = package.read(info)
    except KeyError:
        return support.error_response("Not Found", 404, headers=HEADERS)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        return support.error_response("私有档案暂时无法读取", 503, headers=HEADERS)
    if path == "index.html":
        # Leave scripts, history templates/data and animation code byte-for-byte intact.
        body = body.replace(b'./assets/hljs.js', b'/assets/vendor/highlight-11.11.1.min.js')
        body = body.replace(b'<script defer src="./assets/app.js">', b'<script defer src="/assets/private-archive-highlight.js"></script><script defer src="./assets/app.js">')
        body = body.replace(b"</head>", b'<link rel="stylesheet" href="/assets/private-archive-theme.css?v=1"></head>', 1)
        body = body.replace(b"</body>", b'<script src="/assets/private-archive-shell.js?v=1" defer></script></body>', 1)
    return Response(content=b"" if request.method == "HEAD" else body,
                    media_type=types[suffix], headers=HEADERS)
