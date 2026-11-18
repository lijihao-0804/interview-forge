"""Real Chromium check with local fixture identity and streaming provider."""
import mimetypes
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

from interview_forge.api.routers.static import _inject_html
from interview_forge.core.paths import ROOT


def run():
    posts = []

    def serve(route):
        url = urlsplit(route.request.url)
        path = unquote(url.path)
        if url.hostname != "localhost":
            return route.abort()
        if path == "/api/me":
            return route.fulfill(json={"id": 1, "username": "smoke", "role": "user", "lang": "python"})
        if path == "/api/chat/sessions":
            return route.fulfill(json={"items": [{"id": "s1", "title": "Smoke"}]})
        if path.endswith("/messages"):
            return route.fulfill(json={"session": {"title": "Smoke"}, "items": []})
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
        page = browser.new_page(service_workers="block")
        page.route("**/*", serve)
        page.goto("http://localhost/books/ai-exam/acm-playground.html")
        page.locator("#code-editor").fill("def solve():\n    print(19)")
        page.locator("#stdin-area").fill("19")
        page.get_by_role("button", name="问 AI 助教").click()
        frame = page.frame_locator('iframe[title="AI 助手对话"]')
        frame.locator("#studyCode").click(timeout=10000)
        composer = frame.locator("#messageInput")
        draft = composer.input_value()
        assert "    print(19)" in draft and "当前输入\n19" in draft and not posts
        composer.fill(draft + "\nCheck the duplicate input case.")
        frame.locator("#send").click()
        expect(frame.get_by_text("review ready")).to_be_visible()
        assert posts[0]["message"].endswith("Check the duplicate input case.")
        for path, pid in [("/library/hot200-extra/chapter-01.html", 186),
                          ("/books/hot100/03-题解/17-技巧/0075-颜色分类.html", 75)]:
            page.goto("http://localhost" + path)
            ctx = page.evaluate("window.InterviewForgeAI.getPageContext()")
            assert (ctx["problem_id"], ctx["page_type"]) == (pid, "problem")
        browser.close()
    print("PASS: ACM draft, edited message, streamed reply and both catalog contexts")


if __name__ == "__main__":
    run()
