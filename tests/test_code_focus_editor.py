"""Run with FORGE_CODE_FOCUS_BROWSER_ACCEPTANCE=1 and Playwright with Chrome installed."""
import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
EDITOR = "http://localhost/pages/tools/code-focus.html"
PUBLIC = "/api/code-focus/publication"
ADMIN = "/api/admin/code-focus/publication"


@unittest.skipUnless(os.getenv("FORGE_CODE_FOCUS_BROWSER_ACCEPTANCE") == "1", "optional Chrome acceptance")
class CodeFocusEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(channel="chrome")
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(service_workers="block")
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.clock.install(time="2026-01-01T09:00:00Z")
        self.page.clock.pause_at("2026-01-01T09:01:00Z")
        self.published = dict(version=0, code="", language="auto", answers="")
        self.writes = []
        self.hold_next = False
        self.held = None
        self.fail_get = False
        self.reject_write = None
        self.context.route("**/*", self.serve)
        self.page.add_init_script("""sessionStorage.setItem('hot100.codeFocus.answers.standalone', 'SECRET');""")
        self.code = self.page.locator("#source-code")
        self.answers = self.page.locator("#answer-input")
        self.status = self.page.locator("#save-status")

    def serve(self, route):
        path = urlsplit(route.request.url).path
        if path == PUBLIC:
            if self.fail_get:
                route.abort()
            else:
                route.fulfill(json=self.published)
        elif path == ADMIN:
            data = route.request.post_data_json
            self.writes.append(data)
            if self.reject_write:
                route.fulfill(status=self.reject_write)
            elif data["version"] != self.published["version"]:
                route.fulfill(status=409)
            else:
                self.published = {**data, "version": data["version"] + 1}
                if self.hold_next:
                    self.hold_next = False
                    self.held = route
                else:
                    route.fulfill(json=self.published)
        else:
            asset = (ROOT / path.lstrip("/")).resolve()
            if ROOT in asset.parents and asset.is_file():
                route.fulfill(path=asset)
            else:
                route.abort()

    def start(self):
        self.page.goto(EDITOR)
        self.page.get_by_text("尚未发布内容", exact=True).wait_for()
        self.assertEqual(self.answers.input_value(), "")
        self.assertEqual(self.writes, [])

    def test_debounce_max_wait_and_edits_during_request(self):
        self.start()
        self.hold_next = True
        self.page.locator("#language").select_option("python")
        for i in range(8):
            self.code.fill(f"print({i})")
            self.page.clock.run_for(975)
        self.assertEqual(self.writes, [])
        with self.page.expect_request(lambda req: req.method == "PUT") as first_request:
            self.page.clock.run_for(400)
        self.assertEqual(first_request.value.post_data_json, dict(version=0, code="print(7)", language="python", answers=""))
        self.answers.fill("A, BC")
        self.code.fill("print(8)")
        self.page.clock.run_for(1900)
        self.assertEqual(len(self.writes), 1)
        self.held.fulfill(json=self.published)
        self.page.get_by_text("有未保存的修改，等待自动保存…", exact=True).wait_for()
        self.page.clock.run_for(1)
        self.page.get_by_text("已保存并公开 · 版本 2", exact=True).wait_for()
        self.assertEqual(self.writes[-1], dict(version=1, code="print(8)", language="python", answers="A, BC"))
        self.assertEqual(self.page.locator(".answer-value").all_text_contents(), ["A", "BC"])

    def test_conflict_can_compare_rebase_or_discard(self):
        self.start()
        self.published.update(version=1, code="another admin", answers="D")
        self.code.fill("local draft")
        self.page.clock.run_for(1600)
        self.page.locator("#conflict").wait_for()
        self.page.locator("#remote-version").click()
        self.assertEqual(self.page.locator("#remote-code").inner_text(), "another admin")
        self.assertEqual(self.page.locator("#remote-answers").inner_text(), "D")
        self.assertEqual(self.code.input_value(), "local draft")
        self.code.fill("merged")
        self.answers.fill("D")
        self.page.clock.run_for(9000)
        self.assertEqual(len(self.writes), 1)

        self.page.locator("#use-local").click()
        self.page.get_by_text("已保存并公开 · 版本 2", exact=True).wait_for()
        self.assertEqual(self.writes[-1], dict(version=1, code="merged", language="auto", answers="D"))
        self.published.update(version=3, code="newest")
        self.code.fill("discard")
        self.page.clock.run_for(1600)
        self.page.locator("#use-remote").click()
        self.assertEqual(self.code.input_value(), "newest")
        self.page.clock.run_for(9000)
        self.assertEqual(len(self.writes), 3)

    def test_untouched_crlf_fields_are_preserved(self):
        self.published.update(version=1, code="a\r\nb", answers="A\r\nD")
        self.page.goto(EDITOR)
        self.page.get_by_text("已保存并公开 · 版本 1", exact=True).wait_for()
        self.page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', {value: true, configurable: true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        self.page.clock.run_for(9000)
        self.assertEqual(self.writes, [])
        self.page.locator("#language").select_option("c")
        self.page.get_by_text("已保存并公开 · 版本 2", exact=True).wait_for()
        self.assertEqual(self.writes, [dict(version=1, code="a\r\nb", language="c", answers="A\r\nD")])

    def test_failed_load_and_oversize_save_recover_with_explicit_retry(self):
        self.fail_get = True
        self.page.goto(EDITOR)
        retry = self.page.locator("#retry")
        retry.wait_for()
        self.assertTrue(self.code.is_disabled())
        self.fail_get = False
        retry.click()
        self.page.get_by_text("尚未发布内容", exact=True).wait_for()
        self.reject_write = 413
        self.code.fill("oversize")
        self.page.clock.run_for(1600)
        retry.wait_for()
        self.assertIn("内容过大", self.status.inner_text())
        self.code.fill("short")
        self.page.clock.run_for(9000)
        self.assertEqual(len(self.writes), 1)
        self.reject_write = None
        retry.click()
        self.page.get_by_text("已保存并公开 · 版本 1", exact=True).wait_for()
        self.assertEqual(self.published["code"], "short")

    def test_mobile_background_flush_waits_for_composition_and_skips_clean_fields(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.start()
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.answers.evaluate("""el => {
            el.dispatchEvent(new CompositionEvent('compositionstart'));
            el.value = 'ni';
            el.dispatchEvent(new InputEvent('input', {isComposing: true}));
            Object.defineProperty(document, 'hidden', {value: true, configurable: true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        self.page.clock.run_for(9000)
        self.assertEqual(self.writes, [])
        self.answers.evaluate("""el => {
            el.value = 'Ａ，Ｂ';
            el.dispatchEvent(new CompositionEvent('compositionend'));
        }""")
        self.page.get_by_text("已保存并公开 · 版本 1", exact=True).wait_for()
        self.assertEqual(self.published["answers"], "Ａ，Ｂ")
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.page.clock.run_for(9000)
        self.assertEqual(len(self.writes), 1)
