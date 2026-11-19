"""Run with FORGE_CODE_FOCUS_BROWSER_ACCEPTANCE=1 and Playwright with Chrome installed."""
import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost"
FOCUS = BASE + "/pages/code-focus.html"
ACM = BASE + "/books/ai-exam/acm-playground.html?id="


@unittest.skipUnless(os.getenv("FORGE_CODE_FOCUS_BROWSER_ACCEPTANCE") == "1", "optional Chrome acceptance")
class CodeFocusAnswerTests(unittest.TestCase):
    def test_grouping_composition_and_tab_scoped_problem_drafts(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            context = browser.new_context(service_workers="block")

            def serve(route):
                url = urlsplit(route.request.url)
                path = ROOT / url.path.lstrip("/")
                if url.hostname == "localhost" and ROOT in path.resolve().parents and path.is_file():
                    route.fulfill(path=path)
                else:
                    route.abort()

            context.route("**/*", serve)
            page = context.new_page()
            page.goto(FOCUS, referer=ACM + "hot100-1")
            field = page.get_by_role("textbox", name="答案", exact=True)
            raw = "a，bC、 d\tＥｆ\nG, " + "a" * 80
            field.fill(raw)
            preview = page.get_by_role("region", name="分组答案")
            self.assertEqual(preview.get_attribute("tabindex"), "0")
            sizes = preview.locator(".answer-group").evaluate_all("(groups) => groups.map(g => g.childElementCount)")
            self.assertEqual(sizes, [5, 1])
            self.assertEqual(page.locator(".answer-number").all_text_contents(), list("123456"))
            self.assertEqual(page.locator(".answer-value").all_text_contents(), ["A", "BC", "D", "EF", "G", "A" * 80])
            self.assertEqual(field.input_value(), raw)

            field.evaluate("""el => {
                el.value = 'ni';
                el.dispatchEvent(new InputEvent('input', {isComposing: true}));
            }""")
            self.assertEqual(page.locator(".answer-item").count(), 6)
            field.evaluate("""el => {
                el.value = 'Ａ，Ｂ';
                el.dispatchEvent(new CompositionEvent('compositionend'));
            }""")
            self.assertEqual(page.locator(".answer-value").all_text_contents(), ["A", "B"])
            field.fill(raw)
            page.reload()
            self.assertEqual(field.input_value(), raw)

            page.goto("about:blank")
            page.goto(FOCUS, referer=ACM + "hot100-2")
            self.assertEqual(field.input_value(), "")
            field.fill("C")
            page.goto("about:blank")
            page.goto(FOCUS, referer=ACM + "hot100-1")
            self.assertEqual(field.input_value(), raw)
            other_tab = context.new_page()
            other_tab.goto(FOCUS, referer=ACM + "hot100-1")
            self.assertEqual(other_tab.locator("#answer-input").input_value(), "")
            field.fill("")
            page.reload()
            self.assertEqual(page.locator(".answer-item").count(), 0)
            self.assertFalse(preview.is_visible())
            browser.close()
