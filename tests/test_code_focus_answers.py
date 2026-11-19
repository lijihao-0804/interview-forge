"""Regression coverage for bookmarked reader URLs and the toolbox-only entry."""
import os
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LIVE = "/pages/code-focus-live.html"


class StaticPage(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.elements = []
        self.feed((ROOT / path).read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def attributes(self, tag):
        return [attrs for element, attrs in self.elements if element == tag]


class CodeFocusEntryTests(unittest.TestCase):
    def test_old_bookmark_opens_publication_without_running_draft_scripts(self):
        page = StaticPage("pages/code-focus.html")
        self.assertIn({"http-equiv": "refresh", "content": "0; url=" + LIVE}, page.attributes("meta"))
        self.assertIn({"href": LIVE}, page.attributes("a"))
        for tag in ("script", "form", "textarea"):
            self.assertFalse(page.attributes(tag), tag)

    def test_cockpit_and_acm_do_not_offer_a_separate_entry(self):
        for path in ("cockpit.html", "books/ai-exam/acm-playground.html"):
            with self.subTest(path=path):
                links = StaticPage(path).attributes("a")
                self.assertFalse(any("code-focus" in link.get("href", "") for link in links))

    @unittest.skipUnless(os.getenv("FORGE_CODE_FOCUS_BROWSER_ACCEPTANCE") == "1", "optional Chrome acceptance")
    def test_bookmarked_reader_only_displays_published_answers(self):
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            page = browser.new_page(service_workers="block")
            page.add_init_script("""if (!sessionStorage.getItem('hot100.codeFocus.draft')) {
                sessionStorage.setItem('hot100.codeFocus.draft', '{"code":"private-draft"}');
            }""")
            methods = []

            def serve(route):
                req = route.request
                url = urlsplit(req.url)
                path = (ROOT / url.path.lstrip("/")).resolve()
                methods.append(req.method)
                if url.path == "/api/code-focus/publication":
                    route.fulfill(json={"version": 1, "language": "python", "code": "", "answers": "a，bC、 d Ｅｆ G, z"})
                elif url.hostname == "localhost" and ROOT in path.parents and path.is_file():
                    route.fulfill(path=path)
                else:
                    route.abort()

            page.route("**/*", serve)
            page.goto("http://localhost/pages/code-focus.html?transfer=unavailable")
            expect(page).to_have_url("http://localhost" + LIVE)
            expect(page.locator(".answer-value")).to_have_text(["A", "BC", "D", "EF", "G", "Z"])
            expect(page.locator(".answer-number")).to_have_text(list("123456"))
            self.assertEqual(page.locator(".answer-group").evaluate_all(
                "(groups) => groups.map(group => group.childElementCount)"
            ), [5, 1])
            expect(page.locator("#reader")).to_be_hidden()
            self.assertEqual(page.evaluate("sessionStorage.getItem('hot100.codeFocus.draft')"), '{"code":"private-draft"}')
            self.assertEqual(set(methods), {"GET"})
            browser.close()
