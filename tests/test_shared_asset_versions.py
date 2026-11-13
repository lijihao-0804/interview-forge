import tempfile
import unittest
from pathlib import Path

from scripts.build import build_html_site


class SharedAssetVersionTests(unittest.TestCase):
    def test_rewrite_is_local_tag_scoped_and_idempotent(self):
        markup = """<!doctype html>
<html><head>
<link rel="stylesheet" href="../../assets/ui.js?v=20261101-pop-bg&amp;theme=dark#styles">
<script src="assets/site.js?v=20261014-code-block-visibility&amp;mode=read#app"></script>
<script src="/assets/solution-progress.js?v=20261101-pop-bg&keep=1#progress"></script>
<script src="https://cdn.example/assets/site.js?v=old&mode=read"></script>
<script src="//cdn.example/assets/ui.js?v=old"></script>
<script>const template = '<link href="../../assets/site.js?v=old">';</script>
</head><body>
<p>教学正文仍写作 assets/site.js?v=old 与 solution-progress.js?v=20261101-pop-bg。</p>
<pre>&lt;script src="assets/ai-launcher.js?v=3"&gt;&lt;/script&gt;</pre>
</body></html>"""

        rewritten, count = build_html_site.rewrite_shared_asset_versions(markup)

        self.assertEqual(count, 3)
        self.assertIn(
            'href="../../assets/ui.js?v=' + build_html_site.ASSET_VERSION + '&amp;theme=dark#styles"',
            rewritten,
        )
        self.assertIn(
            'src="assets/site.js?v=' + build_html_site.SITE_JS_VERSION + '&amp;mode=read#app"',
            rewritten,
        )
        self.assertIn(
            'src="/assets/solution-progress.js?v=' + build_html_site.SHARED_ASSET_VERSIONS["solution-progress.js"] + '&keep=1#progress"',
            rewritten,
        )
        self.assertIn('<script src="https://cdn.example/assets/site.js?v=old&mode=read"></script>', rewritten)
        self.assertIn('<script src="//cdn.example/assets/ui.js?v=old"></script>', rewritten)
        self.assertIn("const template = '<link href=\"../../assets/site.js?v=old\">';", rewritten)
        self.assertIn("教学正文仍写作 assets/site.js?v=old 与 solution-progress.js?v=20261101-pop-bg。", rewritten)
        self.assertIn('&lt;script src="assets/ai-launcher.js?v=3"&gt;', rewritten)

        unchanged, second_count = build_html_site.rewrite_shared_asset_versions(rewritten)
        self.assertEqual(second_count, 0)
        self.assertEqual(unchanged, rewritten)

    def test_file_updater_preserves_encoding_newlines_and_unrelated_text(self):
        body = (
            '\ufeff<!doctype html>\r\n<html><head>\r\n'
            '<script src="../../assets/ai-launcher.js?v=3"></script>\r\n'
            '<script src="../../assets/guest-auth.js?v=1#account"></script>\r\n'
            '</head><body><p>正文保持不变</p></body></html>\r\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "page.html"
            path.write_text(body, encoding="utf-8", newline="")

            changed_files, changed_references = build_html_site.update_shared_asset_versions((path,))

            result = path.read_bytes().decode("utf-8")
            self.assertEqual((changed_files, changed_references), (1, 2))
            self.assertTrue(result.startswith("\ufeff<!doctype html>\r\n"))
            self.assertIn('src="../../assets/ai-launcher.js?v=4"', result)
            self.assertIn('src="../../assets/guest-auth.js?v=2#account"', result)
            self.assertIn("<p>正文保持不变</p>", result)
            self.assertIn("\r\n", result)

    def test_shared_versions_follow_runtime_constants(self):
        self.assertEqual(
            build_html_site.SHARED_ASSET_VERSIONS["site.js"],
            build_html_site.SITE_JS_VERSION,
        )
        for name in ("ui.js", "engagement-tracker.js", "term-tooltip.js"):
            self.assertEqual(
                build_html_site.SHARED_ASSET_VERSIONS[name],
                build_html_site.ASSET_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
