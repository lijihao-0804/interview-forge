import unittest
from pathlib import Path

from interview_forge.api.routers.static import _inject_html


ROOT = Path(__file__).resolve().parents[1]


class AiFrontendIntegrationTests(unittest.TestCase):
    def test_static_html_injects_launcher_assets(self):
        body = "<!doctype html><html><body><main>学习</main></body></html>".encode()
        rendered = _inject_html("/books/hot100/03-题解/0146-LRU.html", body).decode()
        self.assertIn("ai-launcher.css", rendered)
        self.assertIn("ai-page-context.js", rendered)
        self.assertIn("ai-launcher.js", rendered)

    def test_launcher_is_not_injected_into_admin_or_full_page(self):
        body = b"<html><body></body></html>"
        for path in ("/pages/admin.html", "/pages/ai-assistant.html", "/pages/login.html"):
            with self.subTest(path=path):
                rendered = _inject_html(path, body).decode()
                self.assertNotIn("ai-launcher.js", rendered)
                self.assertNotIn("ai-page-context.js", rendered)

    def test_generated_library_page_does_not_receive_duplicate_launcher(self):
        page = ROOT / "library" / "agent-cli" / "chapter-01.html"
        body = page.read_bytes()
        rendered = _inject_html("/library/agent-cli/chapter-01.html", body).decode()
        self.assertEqual(rendered.count("ai-launcher.js"), 1)
        self.assertEqual(rendered.count("ai-page-context.js"), 1)

    def test_generated_page_markup_uses_shared_launcher_contract(self):
        from scripts.build import build_html_site, build_library

        self.assertIn("/ai-launcher.css?v=1", "".join(str(item) for item in build_html_site.render_markdown.__code__.co_consts))
        self.assertIn("data-interviewforge-ai", build_library.document("x", "", "assets/library.css"))


if __name__ == "__main__":
    unittest.main()
