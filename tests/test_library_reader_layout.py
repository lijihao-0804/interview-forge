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

    def test_reader_shell_matches_hot100_three_column_layout(self):
        reader = (
            '<div class="shell"><header class="topbar"></header>\n'
            ' <main class="reader"><div class="reader-grid has-otp">'
            '<div class="reader-body">body</div>'
            '<aside class="sol-rail sol-rail-right shelf-page-rail" aria-label="本页目录">'
            '<div class="sol-rail-title">本页目录</div><div class="toc"><ul>'
            '<li><a href="#section">小节</a></li></ul></div></aside>'
            "</div></main></div>"
        )
        nav = build_library.chapter_topic_navigation([{"title": "第一章"}], 1)

        page = build_library.apply_chapter_reader_layout(reader, nav)

        self.assertIn('class="shell chapter-shell site-shell-cols"', page)
        self.assertIn('class="reader-grid"', page)
        self.assertLess(page.index("shelf-topic-rail"), page.index("<main class=\"reader\""))
        main_end = page.index("</main>")
        self.assertGreater(page.index('class="sol-rail sol-rail-right shelf-page-rail"'), main_end)
        self.assertIn('<div class="sol-rail-title">本页目录</div>', page)
        self.assertIn('<a href="#section">小节</a>', page)

        reader_without_toc = (
            '<div class="shell"><header class="topbar"></header> '
            '<main class="reader"><div class="reader-grid">'
            '<div class="reader-body"></div></div></main></div>'
        )
        placeholder_page = build_library.apply_chapter_reader_layout(reader_without_toc, nav)
        self.assertIn('class="shell chapter-shell site-shell-cols"', placeholder_page)
        self.assertIn('class="sol-rail sol-rail-right shelf-page-rail"', placeholder_page)
        self.assertIn("本页暂无小节", placeholder_page)

    def test_library_styles_use_a_scoped_cache_version_and_constrain_images(self):
        page = build_library.document("测试", "", "assets/library.css")

        self.assertIn(f"assets/library.css?v={build_library.LIBRARY_STYLE_VERSION}", page)
        self.assertIn(f"ui.js?v={build_library.ASSET_VERSION}", page)
        self.assertIn("grid-template-columns:216px minmax(0,1fr) 232px", build_library.LIBRARY_CSS)
        self.assertIn("width:calc(100% - 400px)", build_library.LIBRARY_CSS)
        self.assertIn("max-width:1440px", build_library.LIBRARY_CSS)
        self.assertIn("max-width:1150px", build_library.LIBRARY_CSS)
        self.assertIn("max-width:min(100%,680px)", build_library.LIBRARY_CSS)
        self.assertIn("@media(max-width:640px)", build_library.LIBRARY_CSS)

        generated_css = (ROOT / "library" / "assets" / "library.css").read_text(encoding="utf-8")
        generated_page = (ROOT / "library" / "xiaolin-langchain" / "chapter-04.html").read_text(encoding="utf-8")
        self.assertEqual(generated_css, build_library.LIBRARY_CSS.strip() + "\n")
        self.assertIn('class="reader-grid"', generated_page)
        self.assertIn('aria-label="本页目录"', generated_page)
        self.assertIn('class="shelf-topic-link current"', generated_page)
        self.assertIn('</main><script>', generated_page)
        self.assertIn('<aside class="sol-rail sol-rail-right shelf-page-rail"', generated_page)
        self.assertLess(
            generated_page.index('</main>'),
            generated_page.index('<aside class="sol-rail sol-rail-right shelf-page-rail"'),
        )

        generated_no_toc_page = (ROOT / "library" / "agent-mianjing" / "chapter-04.html").read_text(encoding="utf-8")
        self.assertIn('class="shell chapter-shell site-shell-cols"', generated_no_toc_page)
        self.assertIn('class="sol-rail sol-rail-right shelf-page-rail"', generated_no_toc_page)
        self.assertIn("本页暂无小节", generated_no_toc_page)


if __name__ == "__main__":
    unittest.main()
