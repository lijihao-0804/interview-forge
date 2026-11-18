"""Real Chromium check with local fixture identity and streaming provider."""
import json
import mimetypes
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

from interview_forge.api.routers.static import _inject_html
from interview_forge.core.paths import ROOT


def check_session_recovery(browser, serve):
    chat = "http://localhost/pages/ai-assistant.html"
    for failure, width in [("offline", 390), ("busy", 2560), ("guest", 390)]:
        page = browser.new_page(viewport={"width": width, "height": 860}, service_workers="block")
        page.route("**/*", serve)
        available = False

        def identity(route):
            if available:
                return route.fulfill(json={"username": "smoke"})
            if failure == "offline":
                return route.abort()
            return route.fulfill(status=401 if failure == "guest" else 503, json={})

        page.route("**/api/me", identity)
        page.goto(chat)
        if failure == "guest":
            expect(page.locator("#ai-auth-gate")).to_be_visible()
            expect(page.locator("#messageInput")).to_be_disabled()
        else:
            retry = page.get_by_role("button", name="重新连接")
            expect(retry).to_be_visible()
            expect(page.locator("#ai-auth-gate")).to_have_count(0)
            available = True
            if failure == "offline":
                page.evaluate("window.dispatchEvent(new Event('online'))")
            else:
                retry.click()
            expect(page.locator("#messageInput")).to_be_enabled()
        page.close()

    page = browser.new_page(viewport={"width": 2560, "height": 1440}, service_workers="block")
    page.route("**/*", serve)
    sessions = [{"id": "one", "title": "第一段"}, {"id": "two", "title": "第二段"}]
    creates = []
    refreshes = []
    hold_list = False

    def session_list(route):
        if route.request.method == "POST":
            creates.append(route)
        elif hold_list:
            refreshes.append(route)
        else:
            route.fulfill(json={"items": sessions})

    page.route("**/api/chat/sessions", session_list)
    page.route("**/api/chat/sessions/two/actions?*", lambda route: route.fulfill(
        json={"items": [{"action_id": "mark", "display_name": "标记为复习中"}]}))
    confirm_calls = []

    def confirm(route):
        confirm_calls.append(route.request.method)
        if len(confirm_calls) == 1:
            return route.abort()
        return route.fulfill(json={"ok": True, "status": "succeeded", "display": "已标记为复习中"})

    page.route("**/api/chat/actions/mark/confirm", confirm)
    page.goto(chat)
    expect(page.locator("#messageInput")).to_be_enabled()
    hold_list = True
    page.locator("#messageInput").fill("触发会话列表刷新")
    with page.expect_request(lambda req: req.url.endswith("/api/chat/sessions") and req.method == "GET"):
        page.locator("#send").click()
    with page.expect_request(lambda req: req.url.endswith("/api/chat/sessions") and req.method == "POST"):
        page.locator("#newSession").evaluate("button => { button.click(); button.click(); }")
    page.locator('[data-session="two"]').click()
    draft = page.locator("#messageInput")
    draft.fill("还没发送的草稿")
    assert len(creates) == 1, "连续点击只应提交一次建会话请求"
    created = {"id": "three", "title": "新对话"}
    creates[0].fulfill(json=created)
    expect(page.locator('[data-session="three"]')).to_have_count(1)
    with page.expect_request_finished(lambda req: req.url.endswith("/api/chat/sessions") and req.method == "GET"):
        refreshes[0].fulfill(json={"items": sessions})
    expect(page.locator('[data-session="three"]')).to_have_count(1)
    expect(page.locator('[data-session="two"]')).to_have_class("session-item active")
    expect(draft).to_have_value("还没发送的草稿")
    page.get_by_role("button", name="确认", exact=True).click()
    expect(page.get_by_role("button", name="取消", exact=True)).to_be_disabled()
    page.get_by_role("button", name="重试确认").click()
    expect(page.locator(".action-state")).to_contain_text("已标记为复习中")
    assert confirm_calls == ["POST", "POST"]
    page.close()


def run():
    posts = []
    sessions = [{"id": "s1", "title": "Smoke"}]
    rows = []

    def serve(route):
        url = urlsplit(route.request.url)
        path = unquote(url.path)
        if url.hostname != "localhost":
            return route.abort()
        if path == "/api/me":
            return route.fulfill(json={"id": 1, "username": "smoke", "role": "user", "lang": "python"})
        if path.startswith("/api/practice/hot100/problem/"):
            problem_id = path.rsplit("/", 1)[-1]
            volume = "hot200-extra" if problem_id.startswith("hot200-") else "hot100"
            problems = json.loads((ROOT / "data" / "acm" / f"{volume}.json").read_text(encoding="utf-8"))
            return route.fulfill(json=next(item for item in problems if item["id"] == problem_id))
        if path == "/api/chat/sessions":
            if route.request.method == "POST":
                session = {"id": f"s{len(sessions) + 1}", "title": "新对话"}
                sessions.insert(0, session)
                return route.fulfill(json=session)
            return route.fulfill(json={"items": sessions})
        if path.endswith("/messages"):
            return route.fulfill(json={"session": {"title": "Smoke"}, "items": rows})
        if path.endswith("/stream"):
            posts.append(route.request.post_data_json)
            return route.fulfill(content_type="text/event-stream", body=(
                'event: message.start\ndata: {}\n\nevent: message.delta\ndata: {"delta":"review ready"}\n\n'
                'event: message.done\ndata: {"message_id":"m1"}\n\n'
            ))
        if path.startswith("/api/"):
            return route.fulfill(json={"items": []})
        source = (ROOT / path.lstrip("/")).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file():
            return route.fulfill(status=404, body="")
        data = source.read_bytes()
        if path.endswith(".html"):
            data = _inject_html(path, data, embedded="embedded=1" in url.query)
        mime = mimetypes.guess_type(str(source))[0] or "text/plain"
        route.fulfill(content_type=mime + "; charset=utf-8", body=data)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        check_session_recovery(browser, serve)
        posts.clear()
        page = browser.new_page(service_workers="block")
        page.route("**/*", serve)
        practice_url = "http://localhost/books/ai-exam/acm-playground.html?id="
        page.goto(practice_url + "hot100-1")
        expect(page.locator("#problem-context")).to_have_text("两数之和")
        page.locator("#code-editor").fill("def solve():\n    print(19)")
        page.locator("#stdin-area").fill("19")
        page.get_by_role("button", name="问 AI 助教").click()
        frame = page.frame_locator('iframe[title="AI 助手对话"]')
        frame.locator("#studyCode").click(timeout=10000)
        composer = frame.locator("#messageInput")
        draft = composer.input_value()
        assert draft == "" and not posts
        frame.locator("#attachPractice").uncheck()
        composer.fill("保留这段草稿，稍后补充。")
        frame.locator("#historyToggle").click()
        frame.locator("#newSession").click()
        expect(composer).to_have_value("")
        expect(frame.locator("#studyAuto")).to_have_attribute("aria-pressed", "true")
        composer.fill("另一段草稿")
        frame.locator("#historyToggle").click()
        frame.locator('[data-session="s1"]').click()
        expect(composer).to_have_value("保留这段草稿，稍后补充。")
        expect(frame.locator("#studyCode")).to_have_attribute("aria-pressed", "true")
        expect(frame.locator("#attachPractice")).not_to_be_checked()
        frame.locator("#historyToggle").click()
        frame.locator('[data-session="s1"]').click()
        expect(composer).to_have_value("保留这段草稿，稍后补充。")
        frame.locator("#attachPractice").check()
        composer.fill("Check the duplicate input case.")
        frame.locator("#send").click()
        expect(frame.get_by_text("review ready")).to_be_visible()
        assert posts[0]["message"] == "Check the duplicate input case."
        assert posts[0]["study_mode"] == "code"
        assert "print(19)" in posts[0]["practice_snapshot"] and "当前输入\n19" in posts[0]["practice_snapshot"]
        assert posts[0]["page_context"]["problem_id"] == 1
        frame.locator("#attachPractice").uncheck()
        page.locator("#code-editor").evaluate("editor => editor.select()")
        composer.fill("还有哪些边界情况？")
        frame.locator("#send").click()
        expect(frame.get_by_text("review ready")).to_have_count(2)
        assert "practice_snapshot" not in posts[-1]
        assert "print(19)" not in json.dumps(posts[-1]) and "selected_text" not in posts[-1]["page_context"]
        page.goto(practice_url + "hot200-186")
        expect(page.locator("#problem-context")).to_have_text("反转字符串中的单词 II")
        practice_context = page.evaluate("window.InterviewForgeAI.getPageContext()")
        assert (practice_context["problem_id"], practice_context["page_type"]) == (186, "problem")
        for path, pid in [("/library/hot200-extra/chapter-01.html", 186),
                          ("/books/hot100/03-题解/17-技巧/0075-颜色分类.html", 75)]:
            page.goto("http://localhost" + path)
            ctx = page.evaluate("window.InterviewForgeAI.getPageContext()")
            assert (ctx["problem_id"], ctx["page_type"]) == (pid, "problem")
        sessions.clear()
        for width, height in [(2560, 1440), (375, 760), (320, 640)]:
            page.set_viewport_size({"width": width, "height": height})
            page.goto("http://localhost/pages/ai-assistant.html")
            expect(page.locator("#themeSlot #forge-theme-btn")).to_be_visible()
            expect(page.locator("#status")).to_have_text("已连接")
            expect(page.locator(".welcome")).to_be_visible()
            expect(page.locator("#messageInput")).to_be_enabled()
            if width < 760:
                page.locator("#historyToggle").click()
                expect(page.locator("#sessionDrawer")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#sessionDrawer")).to_be_hidden()
            composer = page.locator("#messageInput")
            composer.fill("为什么这样做？")
            page.locator("#studyHint").click()
            expect(composer).to_have_value("为什么这样做？")
            expect(page.locator("#welcomeTitle")).to_have_text("卡在哪一步？")
            composer.press("Enter")
            expect(page.get_by_text("review ready")).to_be_visible()
            assert posts[-1]["study_mode"] == "hint" and posts[-1]["message"] == "为什么这样做？"

        rows.extend({"role": "assistant", "content": "历史记录 " + str(i)} for i in range(65))
        code = "print(" + "1," * 160 + "2)"
        rows.append({"role": "assistant", "content": "```python\n" + code + "\n```"})
        page.reload()
        copy = page.locator(".copy-code")
        expect(copy).to_be_in_viewport()
        assert page.locator(".code-block pre").evaluate("el => el.scrollWidth > el.clientWidth")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        copy.click()
        expect(copy).to_have_text("已复制")
        assert page.evaluate("navigator.clipboard.readText()") == code
        page.locator("#messages").evaluate("el => { el.scrollTop = 0; }")
        expect(page.locator("#send")).to_be_in_viewport()
        page.set_viewport_size({"width": 320, "height": 330})
        composer = page.locator("#messageInput")
        composer.fill("第一行")
        composer.press("Shift+Enter")
        composer.press("A")
        expect(composer).to_have_value("第一行\nA")
        expect(composer).to_be_in_viewport()
        expect(page.locator("#send")).to_be_in_viewport()
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        assert page.locator("#send").evaluate("el => el.getBoundingClientRect().bottom <= innerHeight")
        composer.press("Enter")
        expect(page.get_by_text("review ready")).to_be_visible()
        browser.close()
    print("PASS: reconnect, session races, action receipt retry, practice context, study modes, "
          "mobile history, 2K layout, long history and code copying")


if __name__ == "__main__":
    run()
