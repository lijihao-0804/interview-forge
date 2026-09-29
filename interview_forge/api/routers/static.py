"""Authenticated static/Web-root routes.

This replaces the old handler's static catch-all in the FastAPI runtime.  It
keeps the same path gate and widget injection but never invokes StudyHandler.
"""
from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from interview_forge.analytics.cache import invalidate_learning_caches
from interview_forge.api.support import current_user, error_response
from interview_forge.core.paths import ROOT
from interview_forge.services.catalog import load_library_manifest
from interview_forge.services.study import record_content_view, record_view

router = APIRouter()

_PUBLIC_GET = {"/pages/login.html", "/pages/register.html", "/favicon.ico", "/api/health"}
# 整个 /assets/ 都是公开前端资源（样式/脚本/字体/图标，不含用户数据）。
# 登录页自身也引用这些脚本（服务端注入），只豁免字体会让未登录时脚本被 307
# 成 HTML，登录/注册页的主题切换、导航策略全部静默失效。
_PUBLIC_PREFIXES = ("/assets/",)
_ADMIN_PAGE = "/pages/admin.html"
_WIDGET_STYLES = ("/assets/ai-launcher.css?v=5",)
_WIDGET_SCRIPTS = (
    "/assets/time-utils.js?v=2",
    "/assets/navigation-policy.js?v=2",
    "/assets/auth-widget.js?v=4",
    "/assets/feedback-widget.js?v=2",
    "/assets/theme-toggle.js?v=2",
    "/assets/ai-page-context.js?v=1",
    "/assets/ai-launcher.js?v=3",
)
_AUTH_WIDGET_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}
_FEEDBACK_WIDGET_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}
_AI_LAUNCHER_SKIP = {"/pages/login.html", "/pages/register.html", "/pages/admin.html", "/pages/ai-assistant.html"}


# 内容页 404 的品牌化兜底页：只给浏览器（Accept: text/html）返回；
# API/程序化请求仍拿 JSON。页面内联样式，避免依赖任何需登录或缓存的资源。
_NOT_FOUND_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>页面不存在 · Interview Forge</title>
<style>
:root{color-scheme:light dark}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f5fa;color:#172033;font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;text-align:center}
@media(prefers-color-scheme:dark){body{background:#0f131b;color:#edf2fb}}
.box{max-width:460px;margin:24px;padding:44px 34px;border:1px solid rgba(100,113,136,.28);border-radius:18px;background:rgba(255,255,255,.72)}
@media(prefers-color-scheme:dark){.box{background:rgba(24,30,41,.72)}}
h1{margin:0 0 6px;font-size:44px;letter-spacing:-.02em;color:#5654d4}
p{margin:0 0 22px;color:#647188}
nav{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
nav a{padding:9px 16px;border:1px solid rgba(100,113,136,.32);border-radius:10px;color:inherit;text-decoration:none}
nav a:hover{border-color:#5654d4;color:#5654d4}
</style>
</head>
<body>
<main class="box">
  <h1>404</h1>
  <p>要找的页面不存在，或已被移动。可以从这里继续：</p>
  <nav>
    <a href="/cockpit.html">学习中控台</a>
    <a href="/index.html">学习面板</a>
    <a href="/library/search.html">全文搜索</a>
  </nav>
</main>
</body>
</html>
"""


def _not_found_response(request: Request, decoded: str) -> Response:
    """HTML 请求给品牌 404 页，API/脚本请求保持 JSON 错误体。"""
    accepts_html = "text/html" in (request.headers.get("accept") or "").lower()
    if accepts_html and not decoded.startswith("/api/"):
        return HTMLResponse(_NOT_FOUND_PAGE, status_code=404, headers=_security_headers("404.html"))
    return error_response("Not Found", 404)


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
    return {
        "Cache-Control": cache,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy-Report-Only": (
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
            "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
        ),
    }


def _inject_html(path: str, body: bytes, *, embedded: bool = False) -> bytes:
    navigation_only = path.startswith("/books/hot100/05-可视化/")
    embedded_assistant = path == "/pages/ai-assistant.html" and embedded
    scripts = ("/assets/navigation-policy.js?v=2",) if navigation_only else tuple(
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
    icon_html = b""
    if b"rel=\"icon\"" not in body and b"rel='icon'" not in body:
        icon_html = (
            b'<link rel="icon" href="/assets/icons/icon.svg" type="image/svg+xml">'
            b'<link rel="apple-touch-icon" href="/assets/icons/icon-180.png">'
        )
    head_marker = b"</head>"
    head_index = body.lower().find(head_marker)
    if head_index >= 0 and icon_html:
        body = body[:head_index] + icon_html + body[head_index:]
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
        return _not_found_response(request, decoded)
    if decoded == "/":
        return RedirectResponse("/cockpit.html", status_code=307, headers={"Cache-Control": "no-store"})
    if decoded.startswith("/api/"):
        return error_response("Not Found", 404)
    user = current_user(request)
    if user is None and decoded not in _PUBLIC_GET and not decoded.startswith(_PUBLIC_PREFIXES):
        # next 只保留 .html 页面（带上 query，保持与客户端 401 跳转一致的行为）：
        # 否则登录成功后会被带到裸 CSS/JS 资源文件上。
        next_value = ""
        if decoded.lower().endswith(".html"):
            next_value = decoded + (f"?{request.url.query}" if request.url.query else "")
        next_suffix = f"?next={quote(next_value)}" if next_value else ""
        return RedirectResponse(f"/pages/login.html{next_suffix}", status_code=307, headers={"Cache-Control": "no-store"})
    if decoded == _ADMIN_PAGE and (user is None or str(user["role"]) != "admin"):
        return error_response("Forbidden", 403)
    target = (ROOT / decoded.lstrip("/")).resolve()
    if not target.is_file() or not str(target).startswith(str(ROOT.resolve())):
        return _not_found_response(request, decoded)
    db_path = Path(ROOT / "data" / "users" / str(user["username"]) / "hot100-study.db") if user is not None else None
    if db_path is not None:
        _record_view(decoded, db_path)
    if decoded.lower().endswith(".html"):
        body = _inject_html(decoded, target.read_bytes(), embedded=request.query_params.get("embedded") == "1")
        # HTML 协商缓存：注入后的页面按内容指纹发 ETag，浏览器以 no-cache
        # 回存并在每次导航时重验证（命中即 304，不再全量下载 771 个阅读页）。
        # 注入内容只取决于页面本身，与用户身份无关；_record_view 在上方
        # 已执行，浏览计数不受 304 影响。
        headers = _security_headers(decoded)
        headers["Cache-Control"] = "private, no-cache"
        headers["ETag"] = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        if headers["ETag"] in (request.headers.get("if-none-match") or ""):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="text/html", headers=headers)
    return FileResponse(target, headers=_security_headers(decoded))


@router.api_route("/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
def unknown_method(request: Request, path: str):
    return error_response("Not Found", 404)
