"""Authenticated static/Web-root routes.

This replaces the old handler's static catch-all in the FastAPI runtime.  It
keeps the same path gate and widget injection but never invokes StudyHandler.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from interview_forge.analytics.cache import invalidate_learning_caches
from interview_forge.api.support import current_user, error_response
from interview_forge.core.paths import ROOT
from interview_forge.core.web_access import (
    canonical_url_path,
    is_admin_path,
    is_public_get,
    is_sensitive_path,
    target_relative_path,
)
from interview_forge.services.catalog import load_library_manifest
from interview_forge.services.study import record_content_view, record_view

router = APIRouter()

_WIDGET_STYLES = ("/assets/ai-launcher.css?v=5",)
_WIDGET_SCRIPTS = (
    "/assets/time-utils.js?v=2",
    "/assets/navigation-policy.js?v=2",
    "/assets/auth-widget.js?v=6",
    "/assets/feedback-widget.js?v=4",
    "/assets/theme-toggle.js?v=2",
    "/assets/ai-page-context.js?v=1",
    "/assets/ai-launcher.js?v=4",
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
    return is_sensitive_path(path)


def _security_headers(path: str) -> dict[str, str]:
    suffix = path.split("?", 1)[0].lower()
    if path == "/books/ai-exam/practice-meta.json":
        # A single 620KB metadata file is fetched by every practice page.
        # Allow a short private cache instead of forcing a full re-download.
        cache = "private, max-age=300"
    elif suffix.endswith((".html", ".json", ".webmanifest")):
        cache = "no-store"
    elif suffix.endswith((".css", ".js")):
        cache = "no-cache"
    elif suffix.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".mp4")):
        cache = "public, max-age=2592000"  # 30 天；文件名含路径 hash，暂不用 immutable
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
    # ?embedded=1：页面被本站 iframe 内嵌（如“重要通知”壳页的子页）。此时只保留导航策略，
    # 认证胶囊/反馈球/AI 启动器均不注入，否则外层壳页与 iframe 内会各有一套 fixed
    # 定位控件，在右下角叠成两层。
    if embedded and not embedded_assistant:
        navigation_only = True
    scripts = ("/assets/navigation-policy.js?v=2",) if navigation_only else tuple(
        script for script in _WIDGET_SCRIPTS
        if not (
            (script.startswith("/assets/auth-widget") and (path in _AUTH_WIDGET_SKIP or embedded_assistant))
            or (script.startswith("/assets/feedback-widget") and (path in _FEEDBACK_WIDGET_SKIP or embedded_assistant))
            or (script.startswith("/assets/theme-toggle") and path == "/books/ai-exam/acm-playground.html")
        )
    )
    if path in _AI_LAUNCHER_SKIP or navigation_only:
        scripts = tuple(script for script in scripts if not any(
            marker in script for marker in ("ai-page-context.js", "ai-launcher.js")
        ))
    if path.startswith("/books/ai-exam/"):
        scripts = scripts + ("/assets/practice-bridge.js?v=5",)
    if path.startswith("/library/"):
        scripts = scripts + (
            "/assets/toc-scroll.js?v=8",
            "/assets/search-target.js?v=1",
        )
    elif path.startswith("/books/"):
        # Search results also cover Hot 100 / AI Exam pages; highlight the
        # matched keyword there too (no reading-position resume on those pages).
        scripts = scripts + ("/assets/search-target.js?v=1",)
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
    head_extra = b""
    if path.startswith("/library/"):
        # Search result navigation uses ?q=...; clear the old reading position
        # before the chapter page's inline restore script runs so the keyword
        # target has priority over "resume last position".
        head_extra = b'<script>(function(){try{var q=new URLSearchParams(location.search).get("q");if(!q)return;var m=location.pathname.match(/^\\/library\\/([^/]+)\\/chapter-(\\d+)\\.html$/);if(!m)return;var keys=[m[1]+":"+m[2],m[1]+":"+m[1]+":"+m[2]];var raw=localStorage.getItem("readingPos:v1");if(!raw)return;var all=JSON.parse(raw),changed=false;keys.forEach(function(k){if(all&&Object.prototype.hasOwnProperty.call(all,k)){delete all[k];changed=true;}});if(changed)localStorage.setItem("readingPos:v1",JSON.stringify(all));}catch(e){}})();</script>'
    head_marker = b"</head>"
    head_index = body.lower().find(head_marker)
    if head_index >= 0 and (icon_html or head_extra):
        body = body[:head_index] + icon_html + head_extra + body[head_index:]
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
    decoded = canonical_url_path(request.url.path or "/")
    if decoded is None or _sensitive(decoded):
        return _not_found_response(request, decoded or "/")
    if decoded == "/":
        return RedirectResponse("/cockpit.html", status_code=307, headers={"Cache-Control": "no-store"})
    if decoded.startswith("/api/"):
        return error_response("Not Found", 404)

    target_relative = target_relative_path(ROOT, decoded)
    if target_relative is None or _sensitive(target_relative):
        return _not_found_response(request, decoded)
    user = current_user(request)
    if is_admin_path(decoded) or is_admin_path(target_relative):
        if user is None or str(user["role"]) != "admin":
            return error_response("Forbidden", 403)
    if user is None and not is_public_get(decoded):
        # next 只保留 .html 页面（带上 query，保持与客户端 401 跳转一致的行为）：
        # 否则登录成功后会被带到裸 CSS/JS 资源文件上。
        next_value = ""
        if decoded.lower().endswith(".html"):
            next_value = decoded + (f"?{request.url.query}" if request.url.query else "")
        next_suffix = f"?next={quote(next_value)}" if next_value else ""
        return RedirectResponse(f"/pages/login.html{next_suffix}", status_code=307, headers={"Cache-Control": "no-store"})
    target = (ROOT / decoded.lstrip("/")).resolve()
    if not target.is_file() or not target.is_relative_to(ROOT.resolve()):
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
