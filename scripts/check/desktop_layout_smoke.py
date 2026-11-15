"""Check desktop, zoom-equivalent and mobile layouts through the real app.
Run with: python -m scripts.check.desktop_layout_smoke --output /tmp/forge-desktop
Uses the same optional Playwright dependency as frontend_workspace_smoke.py.
External integrations are deliberately unavailable; identity and data are local.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from interview_forge.api.app import app
from interview_forge.services.favorites import toggle_favorite
from interview_forge.services.study import record_view

PAGES = {
    "cockpit": "/cockpit.html",
    "catalog": "/index.html",
    "library": "/library/index.html",
    "module": "/library/java-core/index.html",
    "chapter": "/library/java-core/chapter-01.html",
    "solution": "/books/hot100/03-题解/01-哈希表/0001-两数之和.html",
    "search": "/library/search.html?q=Java",
    "history": "/pages/history.html",
    "favorites": "/pages/favorites.html",
    "connection": "/pages/leetcode-connect.html",
    "quiz": "/pages/quiz.html",
    "notices": "/pages/notices.html",
    "tools": "/pages/tools.html",
    "booking": "/pages/tools/nju-booking.html",
    "chat": "/pages/ai-assistant.html",
    "login": "/pages/login.html",
    "register": "/pages/register.html",
    "guide": "/guide.html",
    "admin": "/pages/admin.html",
}
# CSS viewports: native desktop plus 125%/150%/200%-equivalent reflow widths.
VIEWPORTS = [(1920,1080), (2560,1440), (1536,864), (1707,960), (1280,720), (768,1024), (390,844)]


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    results = []
    page_errors = []
    with tempfile.TemporaryDirectory(prefix="forge-desktop-") as temp, ExitStack() as stack:
        db = Path(temp) / "study.db"
        for pid in [1,49,128]:
            record_view(pid, db_path=db)
            toggle_favorite("problem", str(pid), db_path=db)
        user = {"id": 987653, "username": "desktop_smoke", "nickname": "桌面验证", "lang": "java", "role": "admin"}
        for module in ("support", "routers.auth", "routers.static"):
            stack.enter_context(patch(f"interview_forge.api.{module}.current_user", return_value=user))
        stack.enter_context(patch("interview_forge.api.routers.study.user_db", return_value=db))
        # Reading must not create study records in any persistent account database.
        stack.enter_context(patch("interview_forge.api.routers.static._record_view"))
        client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
        pw = stack.enter_context(sync_playwright())
        browser = pw.chromium.launch(args=["--no-sandbox", "--no-zygote", "--single-process"])
        context = browser.new_context(service_workers="block", locale="zh-CN", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append({"url": page.url, "error": str(error)}))
        allowed = {"/api/me", "/api/bootstrap", "/api/dashboard", "/api/daily", "/api/plan", "/api/library", "/api/history", "/api/settings", "/api/favorites", "/api/search", "/api/catalog", "/api/health"}

        def transport(route):
            req = route.request
            url = urlsplit(req.url)
            if url.hostname != "localhost":
                route.abort()
                return
            if url.path.startswith("/api/") and url.path not in allowed:
                route.fulfill(status=503, json={"error": "外部服务未启用（本地布局验证）"})
                return
            response = client.request(req.method, url.path + ("?" + url.query if url.query else ""), content=req.post_data_buffer,
                                      headers={key: value for key, value in req.headers.items() if key not in ("host", "content-length")})
            route.fulfill(status=response.status_code, body=response.content,
                          headers={key: value for key, value in response.headers.items() if key not in ("content-length", "content-encoding")})

        context.route("**/*", transport)
        for width,height in VIEWPORTS:
            page.set_viewport_size({"width":width,"height":height})
            for name,path in PAGES.items():
                response = page.goto("http://localhost" + path, wait_until="domcontentloaded")
                assert response.status == 200, (name, response.status)
                expect(page.locator("h1").first).to_be_visible()
                page.evaluate("document.fonts.ready")
                if name == "catalog":
                    expect(page.locator("#connection")).to_have_text("学习服务已连接")
                if name == "favorites":
                    expect(page.locator(".fav").first).to_be_visible()
                metrics = page.evaluate("""() => {
                  const shell=document.querySelector('.shell,.site-shell,.wrap,.quiz-shell,body > .card');
                  const reader=document.querySelector('.reader-body,.markdown-body');
                  return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,
                    shellWidth:shell?.getBoundingClientRect().width,
                    readerWidth:reader?.getBoundingClientRect().width,
                    rails:[...document.querySelectorAll('.sol-rail,.shelf-topic-rail')].filter(el=>el.getClientRects().length).length};
                }""")
                results.append({"page":name,"viewport":[width,height],**metrics})
                if metrics["documentWidth"] > width + 1:
                    page.screenshot(path=str(output / f"OVERFLOW-{name}-{width}.png"),full_page=True)
                    raise AssertionError((name,width,metrics))
                if name in ("chapter","solution"):
                    assert metrics["readerWidth"] <= 1000, (name,width,metrics)
                    if width >= 1920: assert metrics["rails"] >= 2, (name,width,metrics)
                if name in ("library","catalog") and width>=1920:
                    assert 1500 < metrics["shellWidth"] <= 1841, (name,width,metrics)
                if width in (1920,2560) or (width==390 and name in ("library","chapter","chat","history","favorites")):
                    page.screenshot(path=str(output / f"{name}-{width}.png"))
            print(f"PASS {width}×{height}: {len(PAGES)} pages",flush=True)
        for name in ("library","chapter","solution","chat","history","favorites"):
            page.set_viewport_size({"width":2560,"height":1440})
            page.goto("http://localhost" + PAGES[name])
            page.emulate_media(color_scheme="dark")
            page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
            page.screenshot(path=str(output / f"{name}-dark-2560.png"))
        browser.close()
    (output / "result.json").write_text(json.dumps({"measurements":results,"page_errors":page_errors},ensure_ascii=False,indent=2))
    assert not page_errors, page_errors
    print(f"PASS: {len(results)} page/viewport combinations; no page JS errors")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path(tempfile.gettempdir())/"forge-desktop")
    run(parser.parse_args().output)
