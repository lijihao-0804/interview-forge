"""Serve the project teaching sites and older AgentHub installations to super admins."""
from __future__ import annotations

import os
import re
from pathlib import Path
import stat
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import Response

from interview_forge.api import support
from interview_forge.api.routers.static import private_reader_widget_tags
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


AGENTHUB_DIR = ROOT / "library" / "agenthub"
AGENTHUB_STUDY_DIR = ROOT / "library" / "agenthub-study"
AGENTHUB_STUDY_URL = "/library/agenthub-study/index.html"
VOLTEDU_DIR = ROOT / "library" / "voltedu-study"
VOLTEDU_URL = "/library/voltedu-study/index.html"


def _project_file(directory: Path, path: str) -> Path:
    target = directory / path
    if directory.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(directory.resolve()):
        raise FileNotFoundError(path)
    return target


def _read_member(path: str) -> bytes:
    if AGENTHUB_DIR.is_dir():
        if member_type(path) is None:
            raise FileNotFoundError(path)
        return _project_file(AGENTHUB_DIR, path).read_bytes()
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


REPORT_DIR = ROOT / "library" / "development-history"
REPORT_URL = "/library/development-history/index.html"
# Older service workers may attempt to cache every successful /library/ response.
# Vary: * prevents even those workers from putting a private response in CacheStorage.
REPORT_HEADERS = {**HEADERS, "Vary": "*"}


def _integrate_reader(request: Request, body: bytes) -> bytes:
    embedded = request.query_params.get("embedded") == "1" or request.headers.get("sec-fetch-dest") == "iframe"
    widgets = b"" if embedded else private_reader_widget_tags(body)
    if widgets:
        # Ordinary mobile pages put AI inside the account pill. Project books use a standalone button.
        widgets += b'<style>@media(max-width:640px){#if-ai-launcher:not([hidden]){display:inline-flex!important}}</style>'
    if widgets and request.url.path.startswith("/api/private-archive/"):
        # The bundled and imported history viewers absolutely position all iframes.
        widgets += b'<style>.if-ai-drawer iframe{position:static;height:auto}</style>'
    body = body.replace(b"</head>", b'<link rel="stylesheet" href="/assets/project-reader-shell.css?v=20261118-study"></head>', 1)
    shell = b'<script defer src="/assets/private-archive-shell.js?v=6"></script>'
    return body.replace(b"</body>", widgets + shell + b"</body>", 1)


@router.api_route("/library/development-history/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def report_resource(request: Request, path: str):
    return _reader_resource(request, REPORT_DIR, path)


@router.api_route("/library/voltedu-study/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def voltedu_resource(request: Request, path: str):
    return _reader_resource(request, VOLTEDU_DIR, path)


@router.api_route("/library/agenthub-study/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def agenthub_study_resource(request: Request, path: str):
    return _reader_resource(request, AGENTHUB_STUDY_DIR, path)


def _reader_resource(request: Request, directory: Path, path: str):
    denied = _denied(request)
    if denied is not None:
        return denied
    if path == "assets/reader.css":
        media_type = "text/css"
    elif path == "index.html":
        media_type = "text/html"
    elif directory == REPORT_DIR and re.fullmatch(r"chapters/[a-z0-9][a-z0-9-]*\.html", path):
        media_type = "text/html"
    elif directory == VOLTEDU_DIR and re.fullmatch(r"(story|claims|interview|notes)/[a-z0-9][a-z0-9-]*\.html", path):
        media_type = "text/html"
    elif directory == VOLTEDU_DIR and re.fullmatch(r"media/[a-z0-9-]+\.webp", path):
        media_type = "image/webp"
    elif directory == AGENTHUB_STUDY_DIR and re.fullmatch(r"chapter-\d{2}\.html", path):
        media_type = "text/html"
    else:
        return support.error_response("Not Found", 404, headers=REPORT_HEADERS)
    try:
        target = _project_file(directory, path)
        body = b"" if request.method == "HEAD" else target.read_bytes()
    except FileNotFoundError:
        return support.error_response("Not Found", 404, headers=REPORT_HEADERS)
    if media_type == "text/html" and body:
        body = _integrate_reader(request, body)
    return Response(content=body, media_type=media_type, headers=REPORT_HEADERS)


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
    result = {"available": available, "url": "/api/private-archive/index.html"}
    if available:
        result["entry"] = {"title": "AgentHub 教学档案", "description": "专属教学资料 · 仅超级管理员可见",
                           "url": "/api/private-archive/index.html"}
    if (REPORT_DIR / "index.html").is_file():
        report = {"title": "InterviewForge 开发手记", "description": "一道题做完以后 · 项目历程、工程选择与面试追问",
                  "url": REPORT_URL}
        result["entries"] = [result["entry"], report] if available else [report]
    if (VOLTEDU_DIR / "index.html").is_file():
        entries = result.setdefault("entries", [result["entry"]] if available else [])
        entries.append({"title": "VoltEdu 毕设手记", "description": "电路课程辅学、LoRA 微调、评测与面试追问",
                        "url": VOLTEDU_URL})
    if (AGENTHUB_STUDY_DIR / "index.html").is_file():
        entries = result.setdefault("entries", [result["entry"]] if available else [])
        entries.append({"title": "AgentHub 从 0 到 1 深度课程",
                        "description": "20 讲全栈源码演进 + 220 道面试问答 · 一节一页书架版",
                        "url": AGENTHUB_STUDY_URL})
    return support.json_response(result, headers=HEADERS)


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
    if path == "index.html" and not AGENTHUB_DIR.is_dir():
        # Leave scripts, history templates/data and animation code byte-for-byte intact.
        body = body.replace(b'./assets/hljs.js', b'/assets/vendor/highlight-11.11.1.min.js')
        body = body.replace(b'<script defer src="./assets/app.js">', b'<script defer src="/assets/private-archive-highlight.js"></script><script defer src="./assets/app.js">')
        body = body.replace(b"</head>", b'<link rel="stylesheet" href="/assets/private-archive-theme.css?v=1"></head>', 1)
    if path == "index.html":
        body = _integrate_reader(request, body)
    return Response(content=b"" if request.method == "HEAD" else body,
                    media_type=media_type, headers=HEADERS)
