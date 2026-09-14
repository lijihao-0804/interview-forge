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

    def test_embedded_assistant_does_not_receive_auth_or_feedback_widgets(self):
        body = b"<html><body></body></html>"
        rendered = _inject_html("/pages/ai-assistant.html", body, embedded=True).decode()
        self.assertNotIn("auth-widget.js", rendered)
        self.assertNotIn("feedback-widget.js", rendered)
        self.assertIn("theme-toggle.js", rendered)

    def test_full_assistant_does_not_receive_bottom_overlays(self):
        rendered = _inject_html("/pages/ai-assistant.html", b"<html><body></body></html>").decode()
        self.assertNotIn("auth-widget.js", rendered)
        self.assertNotIn("feedback-widget.js", rendered)

    def test_launcher_is_not_injected_into_admin_or_full_page(self):
        body = b"<html><body></body></html>"
        for path in ("/pages/admin.html", "/pages/ai-assistant.html", "/pages/login.html"):
            with self.subTest(path=path):
                rendered = _inject_html(path, body).decode()
                self.assertNotIn("ai-launcher.js", rendered)
                self.assertNotIn("ai-page-context.js", rendered)

    def test_admin_does_not_receive_floating_auth_or_feedback_widgets(self):
        rendered = _inject_html("/pages/admin.html", b"<html><body></body></html>").decode()
        self.assertNotIn("auth-widget.js", rendered)
        self.assertNotIn("feedback-widget.js", rendered)

    def test_admin_ai_config_uses_tabbed_cards_and_modal_editors(self):
        page = (ROOT / "pages" / "admin.html").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "admin-ai-config.js").read_text(encoding="utf-8")
        style = (ROOT / "assets" / "admin-ai-config.css").read_text(encoding="utf-8")
        for marker in (
            'data-ai-tab="providers"', 'data-ai-tab="models"', 'data-ai-tab="routes"',
            'id="admin-ai-provider-dialog"', 'id="admin-ai-model-dialog"',
            'id="admin-ai-route-dialog"', 'id="admin-ai-provider-count"',
            'id="admin-ai-capability-profile"', 'id="admin-ai-capability-profile-note"',
            'id="admin-ai-reasoning-note"',
        ):
            self.assertIn(marker, page)
        self.assertIn("showModal", script)
        self.assertIn("renderPresetSelect", script)
        self.assertIn('option(select, preset.key', script)
        self.assertIn("emptyOption(select", script)
        self.assertIn("暂无可用模型，请先同步或添加", script)
        self.assertIn("capabilityProfiles", script)
        self.assertIn("capabilitySourceLabel", script)
        self.assertIn('mode.textContent = ""', script)
        self.assertIn('effort.textContent = ""', script)
        self.assertIn("capability_profile", script)
        self.assertNotIn('if (item.model_id.indexOf("deepseek")', script)
        self.assertIn("status-partial", style)
        self.assertIn("position:fixed", style)
        self.assertIn("width:100%; max-width:none", style)
        self.assertNotIn("window.prompt", script)
        self.assertNotIn("innerHTML", script)

    def test_feedback_button_uses_dynamic_auth_reserve(self):
        auth = (ROOT / "assets" / "auth-widget.js").read_text(encoding="utf-8")
        feedback = (ROOT / "assets" / "feedback-widget.js").read_text(encoding="utf-8")
        self.assertIn("--forge-auth-reserve", auth)
        self.assertIn("ResizeObserver", auth)
        self.assertIn("var(--forge-auth-reserve", feedback)
        self.assertNotIn("bottom:calc(58px", feedback)

    def test_generated_library_page_does_not_receive_duplicate_launcher(self):
        page = ROOT / "library" / "agent-cli" / "chapter-01.html"
        body = page.read_bytes()
        rendered = _inject_html("/library/agent-cli/chapter-01.html", body).decode()
        self.assertEqual(rendered.count("ai-launcher.js"), 1)
        self.assertEqual(rendered.count("ai-page-context.js"), 1)

    def test_generated_page_markup_uses_shared_launcher_contract(self):
        from scripts.build import build_html_site, build_library

        self.assertIn("/ai-launcher.css?v=2", "".join(str(item) for item in build_html_site.render_markdown.__code__.co_consts))
        self.assertIn("data-interviewforge-ai", build_library.document("x", "", "assets/library.css"))


if __name__ == "__main__":
    unittest.main()
