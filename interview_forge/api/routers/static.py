"""Authenticated static/Web-root routes.

This replaces the old handler's static catch-all in the FastAPI runtime.  It
keeps the same path gate and widget injection but never invokes StudyHandler.
"""
from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from interview_forge.analytics.cache import invalidate_learning_caches
from interview_forge.api.support import current_user, error_response
from interview_forge.core.paths import ROOT
from interview_forge.services.catalog import load_library_manifest
from interview_forge.services.study import record_content_view, record_view

router = APIRouter()

_PUBLIC_GET = {"/pages/login.html", "/pages/register.html", "/favicon.ico", "/api/health"}
_PUBLIC_PREFIXES = ("/assets/fonts",)
_ADMIN_PAGE = "/pages/admin.html"
_WIDGET_STYLES = ("/assets/ai-launcher.css?v=2",)
_WIDGET_SCRIPTS = (
    "/assets/time-utils.js?v=1",
    "/assets/navigation-policy.js?v=1",
    "/assets/auth-widget.js?v=3",
    "/assets/feedback-widget.js?v=2",
    "/assets/theme-toggle.js?v=2",
    "/assets/ai-page-context.js?v=1",
    "/assets/ai-launcher.js?v=2",
)
_AUTH_WIDGET_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}
_FEEDBACK_WIDGET_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}
_AI_LAUNCHER_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}


def _sensitive(path: str) -> bool:
    normalized = path or "/"
    for _ in range(2):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    normalized = "/" + normalized.replace("\\", "/").lstrip("/")
    normalized = posixpath.normpath(normalized)
    lowered = normalized.lower()
    if ".." in lowered.split("/"):
        return True
    public_docs = {"/docs/qa-report.html", "/docs/深度审查与修复报告-2026-09-08.html", "/docs/学情分析ai专项审查报告.html"}
    if lowered in public_docs:
        return False
    sensitive_prefixes = ("/data/", "/tools/", "/.git/", "/docs/", "/qa-report/")
    return lowered.startswith(sensitive_prefixes) or lowered in ("/data", "/tools", "/.git", "/docs", "/maintenance.html", "/guide.html.md") or lowered.startswith(("/.", "/maintenance", "/readme")) or lowered.endswith(".md")


def _path(request: Request) -> str:
    value = unquote(request.url.path or "/")
    return "/" + value.lstrip("/") if value.startswith("//") else value


def _security_headers(path: str) -> dict[str, str]:
    suffix = path.split("?", 1)[0].lower()
    if suffix.endswith((".html", ".json", ".webmanifest")):
        cache = "no-store"
    elif suffix.endswith((".css", ".js")):
        cache = "no-cache"
    elif suffix.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".mp4")):
        cache = "public, max-age=604800"
    else:
        cache = "no-store"
    return {"Cache-Control": cache, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN"}


def _inject_html(path: str, body: bytes, *, embedded: bool = False) -> bytes:
    navigation_only = path.startswith("/books/hot100/05-可视化/")
    embedded_assistant = path == "/pages/ai-assistant.html" and embedded
    scripts = ("/assets/navigation-policy.js?v=1",) if navigation_only else tuple(
        script for script in _WIDGET_SCRIPTS
        if not (
            (script.startswith("/assets/auth-widget") and (path in _AUTH_WIDGET_SKIP or embedded_assistant))
            or (script.startswith("/assets/feedback-widget") and (path in _FEEDBACK_WIDGET_SKIP or embedded_assistant))
        )
    )
    if path in _AI_LAUNCHER_SKIP or navigation_only:
        scripts = tuple(script for script in scripts if not any(
            marker in script for marker in ("ai-page-context.js", "ai-launcher.js")
        ))
    styles = () if path in _AI_LAUNCHER_SKIP or navigation_only else _WIDGET_STYLES
    style_html = b"" if b"ai-launcher.css" in body else "".join(
        f'<link rel="stylesheet" data-interviewforge-ai href="{style}">'
        for style in styles
    ).encode()
    script_html = "".join(
        f'<script src="{script}" defer data-interviewforge-ai></script>'
        for script in scripts
        if script.rsplit("/", 1)[-1].split("?", 1)[0].encode() not in body
    ).encode()
    widget = style_html + script_html
    marker = b"</body>"
    index = body.lower().rfind(marker)
    return body[:index] + widget + body[index:] if index >= 0 else body + widget


def _record_view(path: str, db_path: Path) -> None:
    try:
        if path.startswith("/books/hot100/03-题解/") and path.lower().endswith(".html"):
            filename = Path(path).name
            target = (ROOT / path.lstrip("/")).resolve()
            if target.is_file() and str(target).startswith(str(ROOT.resolve())) and record_view(int(filename[:4]), db_path):
                invalidate_learning_caches(db_path)
        route = load_library_manifest().get("routes", {}).get(path)
        if route and record_content_view(str(route["module_id"]), str(route["content_id"]), db_path):
            invalidate_learning_caches(db_path)
    except Exception:
        invalidate_learning_caches(db_path)


@router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def static_path(request: Request, path: str):
    decoded = _path(request)
    if _sensitive(decoded):
        return error_response("Not Found", 404)
    if decoded == "/":
        return RedirectResponse("/cockpit.html", status_code=307, headers={"Cache-Control": "no-store"})
    if decoded.startswith("/api/"):
        return error_response("Not Found", 404)
    user = current_user(request)
    if user is None and decoded not in _PUBLIC_GET and not decoded.startswith(_PUBLIC_PREFIXES):
        return RedirectResponse(f"/pages/login.html?next={quote(decoded)}", status_code=307, headers={"Cache-Control": "no-store"})
    if decoded == _ADMIN_PAGE and (user is None or str(user["role"]) != "admin"):
        return error_response("Forbidden", 403)
    target = (ROOT / decoded.lstrip("/")).resolve()
    if not target.is_file() or not str(target).startswith(str(ROOT.resolve())):
        return error_response("Not Found", 404)
    db_path = Path(ROOT / "data" / "users" / str(user["username"]) / "hot100-study.db") if user is not None else None
    if db_path is not None:
        _record_view(decoded, db_path)
    if decoded.lower().endswith(".html"):
        body = _inject_html(decoded, target.read_bytes(), embedded=request.query_params.get("embedded") == "1")
        return Response(content=body, media_type="text/html", headers=_security_headers(decoded))
    return FileResponse(target, headers=_security_headers(decoded))


@router.api_route("/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
def unknown_method(request: Request, path: str):
    return error_response("Not Found", 404)
