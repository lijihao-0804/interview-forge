import unittest
from pathlib import Path

from scripts.build import build_library

ROOT = Path(__file__).resolve().parents[1]


class LibraryReaderLayoutTests(unittest.TestCase):
    def test_topic_navigation_is_escaped_and_marks_the_active_chapter(self):
        chapters = [
            {"title": "基础篇"},
            {"title": "图示 <安全>"},
        ]

        nav = build_library.chapter_topic_navigation(chapters, current_index=2)

        self.assertIn('aria-label="本专题章节"', nav)
        self.assertIn('href="chapter-01.html"', nav)
        self.assertIn('href="chapter-02.html" aria-current="page"', nav)
        self.assertIn("图示 &lt;安全&gt;", nav)
        self.assertEqual(nav.count('aria-current="page"'), 1)

    def test_reader_shell_gets_left_rail_and_right_page_toc_layout(self):
        reader = (
            '<div class="shell"><header class="topbar"></header>\n'
            ' <main class="reader"><div class="reader-grid has-otp">'
            '<div class="reader-body"></div><nav class="otp"></nav>'
            "</div></main></div>"
        )
        nav = build_library.chapter_topic_navigation([{"title": "第一章"}], 1)

        page = build_library.apply_chapter_reader_layout(reader, nav)

        self.assertIn('class="shell chapter-shell"', page)
        self.assertIn('class="reader-grid has-topic has-otp"', page)
        self.assertLess(page.index("shelf-topic-rail"), page.index("<main class=\"reader\""))
        self.assertIn('<nav class="otp"', page)

    def test_library_styles_use_a_scoped_cache_version_and_constrain_images(self):
        page = build_library.document("测试", "", "assets/library.css")

        self.assertIn(f"assets/library.css?v={build_library.LIBRARY_STYLE_VERSION}", page)
        self.assertIn(f"ui.js?v={build_library.ASSET_VERSION}", page)
        self.assertIn("grid-template-columns:minmax(190px,220px) minmax(0,1fr)", build_library.LIBRARY_CSS)
        self.assertIn("max-width:min(100%,680px)", build_library.LIBRARY_CSS)
        self.assertIn("@media(max-width:1280px)", build_library.LIBRARY_CSS)
        self.assertIn("@media(max-width:900px)", build_library.LIBRARY_CSS)

        generated_css = (ROOT / "library" / "assets" / "library.css").read_text(encoding="utf-8")
        generated_page = (ROOT / "library" / "xiaolin-langchain" / "chapter-04.html").read_text(encoding="utf-8")
        self.assertEqual(generated_css, build_library.LIBRARY_CSS.strip() + "\n")
        self.assertIn('class="reader-grid has-topic has-otp"', generated_page)
        self.assertIn('aria-label="本页目录"', generated_page)
        self.assertIn('class="shelf-topic-link current"', generated_page)


if __name__ == "__main__":
    unittest.main()
