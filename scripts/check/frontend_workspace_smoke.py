"""Real Chromium UI smoke checks via FastAPI's in-process HTTP transport.

Install playwright and the dev requirements, then run:
  python -m playwright install chromium --only-shell
  python -m scripts.check.frontend_workspace_smoke --output /tmp/forge-ui

Only identity is synthetic; catalog, plan, mock, marks and bootstrap use the
real application with a temporary study database. No external API is called.
Service workers are blocked in this transport; test their contracts separately.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import sqlite3
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from interview_forge.api.app import app


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    identity = [None]
    failures: set[str] = set()
    user = {"id": 987654, "username": "frontend_smoke", "nickname": "UI 测试", "lang": "java", "role": "user"}
    with tempfile.TemporaryDirectory(prefix="forge-ui-") as temp, ExitStack() as stack:
        db = Path(temp) / "study.db"
        for module in ("support", "routers.auth", "routers.static"):
            stack.enter_context(patch(f"interview_forge.api.{module}.current_user", side_effect=lambda *_: identity[0]))
        stack.enter_context(patch("interview_forge.api.routers.study.user_db", return_value=db))
        client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch(args=["--no-sandbox", "--no-zygote", "--single-process"])
        context = browser.new_context(service_workers="block", locale="zh-CN", reduced_motion="reduce", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def transport(route):
            request = route.request
            url = urlsplit(request.url)
            if url.hostname != "localhost":
                route.abort()
                return
            path = url.path + ("?" + url.query if url.query else "")
            if url.path in failures or url.path.startswith(("/api/weather", "/api/coach", "/api/chat", "/api/leetcode")):
                route.fulfill(status=503, json={"error": "测试中的服务不可用"})
                return
            headers = {key: value for key, value in request.headers.items() if key not in ("host", "content-length")}
            response = client.request(request.method, path, content=request.post_data_buffer, headers=headers)
            route.fulfill(status=response.status_code, body=response.content,
                          headers={key: value for key, value in response.headers.items() if key not in ("content-length", "content-encoding")})

        context.route("**/*", transport)
        page.goto("http://localhost/index.html")
        expect(page.locator("body")).to_have_class("is-guest")
        expect(page.locator("#grid .card")).to_have_count(24)
        expect(page.locator(".stats")).to_be_hidden()
        page.locator("#loadMore").click()
        expect(page.locator("#grid .card")).to_have_count(48)
        assert page.evaluate("document.activeElement.closest('.card') === document.querySelectorAll('#grid .card')[24]")
        page.locator("#showAll").click()
        expect(page.locator("#grid .card")).to_have_count(100)
        page.locator("#difficulty").select_option("简单")
        assert set(page.locator("#grid .meta [class^=difficulty-]").all_text_contents()) == {"简单"}
        page.locator("#category").select_option("哈希表")
        expect(page.locator("#grid .card")).to_have_count(1)
        page.reload()
        expect(page.locator("#difficulty")).to_have_value("简单")
        expect(page.locator("#category")).to_have_value("哈希表")
        expect(page.locator("#grid .card")).to_have_count(1)
        page.locator("#search").fill("not-a-real-problem")
        expect(page.locator("#empty")).to_be_visible()
        page.locator("#emptyReset").click()
        expect(page.locator("#grid .card")).to_have_count(24)
        expect(page.locator("#search")).to_be_focused()
        page.locator("#sortOrder").select_option("number")
        ids = page.locator("#grid [data-problem-id]").evaluate_all("items => items.map(item => Number(item.dataset.problemId))")
        assert ids == sorted(ids)
        page.locator("#compactView").click()
        page.reload()
        expect(page.locator("#compactView")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#grid")).to_have_class("grid is-compact")
        page.locator("#cardView").click()
        page.locator("#sortOrder").select_option("topic")
        page.locator("#grid [data-problem-id='1']").click(modifiers=["Control"])
        expect(page.locator("#resumeProblem")).to_contain_text("两数之和")
        page.reload()
        expect(page.locator("#resumeStrip")).to_be_visible()
        page.locator("#clearResume").click()
        expect(page.locator("#resumeStrip")).to_be_hidden()
        page.locator("#catalogTitle").click()
        page.keyboard.press("/")
        expect(page.locator("#search")).to_be_focused()
        page.screenshot(path=str(output / "catalog-desktop.png"), full_page=True)

        # Actual landing route is cockpit.html. Exercise both search destinations.
        page.goto("http://localhost/")
        page.locator("#launchQuery").fill("两数之和")
        page.locator("#launchSearch button").click()
        expect(page.locator("#search")).to_have_value("两数之和")
        expect(page.locator("#grid .card")).to_have_count(1)
        page.goto("http://localhost/")
        expect(page.locator("#launchRecentLink")).to_have_text("两数之和")
        page.locator("#launchClearRecent").click()
        expect(page.locator("#launchRecent")).to_be_hidden()
        page.locator("#launchScope").select_option("library/search.html")
        page.locator("#launchQuery").fill("数据库")
        page.locator("#launchSearch button").click()
        expect(page).to_have_url("http://localhost/library/search.html?q=" + "%E6%95%B0%E6%8D%AE%E5%BA%93")
        page.goto("http://localhost/")
        page.screenshot(path=str(output / "cockpit-desktop.png"), full_page=True)
        expect(page.locator(".launch-paths,.launch-path")).to_have_count(0)
        expect(page.locator("#launchSearch")).to_be_visible()

        for width in (320, 390, 768, 1920, 2560):
            page.set_viewport_size({"width": width, "height": 1440 if width == 2560 else 1080 if width == 1920 else 900})
            for path, name in (("/index.html", "catalog"), ("/", "cockpit")):
                page.goto("http://localhost" + path)
                expect(page.locator("body")).to_have_class("is-guest")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, path)
                if path == "/index.html":
                    assert page.evaluate("document.querySelector('.hero-cta').nextElementSibling.id === 'leetcodeSyncBtn'")
                    expect(page.locator('#leetcodeSyncBtn')).to_be_disabled()
                    first=page.locator('.hero-cta').bounding_box(); sync=page.locator('#leetcodeSyncBtn').bounding_box()
                    same_row=abs(sync['y']+sync['height']/2-first['y']-first['height']/2)<2
                    assert (same_row and sync['x']>first['x']) or sync['y']>=first['y']+first['height']-1
                else:
                    assert page.locator('.launchpad').bounding_box()['height'] < 350
                if width in (390,1920,2560):
                    page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True)
                page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
                page.wait_for_function("getComputedStyle(document.body).backgroundColor === 'rgb(15, 19, 27)'")
                if width in (390, 1440):
                    page.screenshot(path=str(output / f"{name}-dark-{width}.png"), full_page=True)

        page.set_viewport_size({"width": 1440, "height": 1000})
        identity[0] = user
        page.goto("http://localhost/index.html")
        expect(page.locator("body")).to_have_class("is-authenticated")
        expect(page.locator("#connection")).to_have_text("学习服务已连接")
        expect(page.locator('#leetcodeSyncBtn')).to_be_enabled()
        with page.expect_response(lambda response: '/api/leetcode/status' in response.url):
            page.locator('#leetcodeSyncBtn').click()
        expect(page.locator('#leetcodeSyncBtn')).to_be_enabled()
        expect(page.locator('#leetcodeSyncBtn')).to_have_text('一键同步')
        expect(page.locator('#leetcodeSyncModal')).to_be_visible()
        page.locator('#leetcodeSyncDone').click()
        with page.expect_response(lambda response: response.url.endswith("/api/mark")) as marked:
            page.locator("#grid [data-mark='1']").select_option("weak")
        assert marked.value.status == 201, marked.value.text()
        page.reload()
        expect(page.locator("#grid [data-mark='1']")).to_have_value("weak")
        page.locator("#status").select_option("weak")
        expect(page.locator("#grid .card")).to_have_count(1)
        failures.add("/api/mark")
        page.locator("#grid [data-mark='1']").select_option("clear")
        expect(page.locator("#toast")).to_contain_text("标记失败")
        expect(page.locator("#grid [data-mark='1']")).to_have_value("weak")
        failures.clear()
        page.locator(".study-nav a[href='#practice']").click()
        page.locator("#mockStart").click()
        expect(page.locator("#mockList .mock-item")).to_have_count(1)
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#mockAbandon").click()
        expect(page.locator("#mockReport")).to_contain_text("已放弃")
        # Metadata-only fixtures: Python excludes its WA attempt, Java excludes its own AC.
        with sqlite3.connect(db) as connection:
            connection.executemany("INSERT INTO submissions(problem_id,status,lang,submitted_at) VALUES (?,?,?,?)", [(1,'wa','Python3','2026-01-01T12:00:00Z'),(2,'ac','Java','2026-01-01T12:00:00Z')])
        page.locator('#mockSettings summary').click()
        page.locator('#mockScope').select_option('unseen')
        page.locator('#mockLanguage').select_option('python')
        expect(page.locator('#mockPool')).to_contain_text('当前可抽 99 题')
        for width,height in ((1920,1080),(2560,1440),(390,844)):
            page.set_viewport_size({'width':width,'height':height})
            page.locator('#mockSettings').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / f'mock-language-{width}.png'))
        for language, excluded in (('python',1),('java',2)):
            page.locator('#mockLanguage').select_option(language)
            expect(page.locator('#mockPool')).to_contain_text('当前可抽 99 题')
            with page.expect_response(lambda response:'/api/mock?' in response.url and 'preview=' not in response.url) as exam:
                page.locator('#mockStart').click()
            actual=exam.value.json()
            assert actual['language']==language and actual['scope_pool']==99
            assert excluded not in [problem['id'] for problem in actual['problems']]
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#mockAbandon').click()
            page.locator('#mockSettings summary').click()
        page.locator('#mockScope').select_option('all')
        expect(page.locator('#mockLanguage')).to_be_disabled()
        expect(page.locator('#mockPool')).to_contain_text('当前可抽 100 题')
        page.set_viewport_size({'width':1440,'height':1000})
        failures.add("/api/bootstrap")
        page.reload()
        expect(page.locator("#serverNotice")).to_be_visible()
        expect(page.locator("#goalText")).to_have_text("—")
        expect(page.locator("#streakMessage")).to_contain_text("未读取")
        failures.clear()
        page.locator("#serverRetry").click()
        expect(page.locator("#connection")).to_have_text("学习服务已连接")
        expect(page.locator("#goalText")).not_to_have_text("—")
        page.evaluate("scrollTo(0,0)")
        page.screenshot(path=str(output / "catalog-authenticated.png"), full_page=True)
        # Expired sessions must hide personal controls, keeping public filtering usable.
        identity[0] = None
        page.reload()
        expect(page.locator("body")).to_have_class("is-guest")
        expect(page.locator(".stats")).to_be_hidden()
        page.locator("#difficulty").select_option("困难")
        assert page.locator("#grid .card").count() > 0
        assert not errors, errors
        browser.close()
    (output / "result.json").write_text(json.dumps({"ok": True, "widths": [320, 390, 768, 1920, 2560], "page_errors": errors}, ensure_ascii=False, indent=2))
    print("PASS: guest/authenticated/error recovery, filters, navigation, mock, marks, five widths and two themes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "forge-ui")
    run(parser.parse_args().output)
