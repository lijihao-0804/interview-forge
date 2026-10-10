import json
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
        self.assertNotIn('</main><script>', generated_page)
        self.assertIn('function fetchWithTimeout', generated_page)
        self.assertIn('<aside class="sol-rail sol-rail-right shelf-page-rail"', generated_page)
        self.assertLess(
            generated_page.index('</main>'),
            generated_page.index('<aside class="sol-rail sol-rail-right shelf-page-rail"'),
        )

        generated_no_toc_page = (ROOT / "library" / "agent-mianjing" / "chapter-04.html").read_text(encoding="utf-8")
        self.assertIn('class="shell chapter-shell site-shell-cols"', generated_no_toc_page)
        self.assertIn('class="sol-rail sol-rail-right shelf-page-rail"', generated_no_toc_page)
        self.assertIn("本页暂无小节", generated_no_toc_page)
        self.assertNotIn("readerSticky", generated_no_toc_page)
        self.assertNotIn("reader-sticky", generated_no_toc_page)
        chapter_nav_start = generated_no_toc_page.index('<nav class="chapter-nav"')
        chapter_nav_end = generated_no_toc_page.index("</nav>", chapter_nav_start)
        chapter_nav = generated_no_toc_page[chapter_nav_start:chapter_nav_end]
        self.assertIn('href="chapter-05.html"', chapter_nav)
        self.assertIn("下一章 →", chapter_nav)
        self.assertNotIn(".reader-sticky", build_library.LIBRARY_CSS)

    def test_agent_interview_embedding_copy_has_no_split_chinese_words(self):
        source = (ROOT / "books" / "agent面经" / "agent面经.md").read_text(encoding="utf-8")
        generated = (ROOT / "library" / "agent-mianjing" / "chapter-04.html").read_text(encoding="utf-8")

        cjk = r"\u3001-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f"
        self.assertNotRegex(source, rf"(?<=[{cjk}]) +(?=[{cjk}])")
        self.assertIn("每个 Token 都对应一个向量", source)
        self.assertIn("随后，模型会在", source)
        self.assertIn("每个 Token 都对应一个向量", generated)
        self.assertIn("随后，模型会在", generated)
        self.assertNotIn("对应 一个向量", generated)
        self.assertNotIn("随 后", generated)

        manifest = json.loads((ROOT / "library" / "manifest.json").read_text(encoding="utf-8"))
        module = next(item for item in manifest["modules"] if item["id"] == "agent-mianjing")
        chapter = next(item for item in module["chapters"] if item["id"] == "agent-mianjing:04")
        self.assertIn("文本进入模型之前", chapter["intro"])
        self.assertNotIn("文 本进入", chapter["intro"])

        search_index = json.loads((ROOT / "library" / "search-index.json").read_text(encoding="utf-8"))
        search_entry = next(item for item in search_index if item["id"] == "agent-mianjing:04")
        self.assertIn("都对应一个向量", search_entry["text"])
        self.assertNotIn("对应 一个向量", search_entry["text"])

    def test_agent_mianjing_lora_code_renders_as_a_code_block(self):
        generated = (ROOT / "library" / "agent-mianjing" / "chapter-14.html").read_text(encoding="utf-8")
        sample_start = generated.index("<p>代码示例：</p>")
        sample_end = generated.index("</div>", sample_start) + len("</div>")
        rendered_sample = generated[sample_start:sample_end]

        self.assertIn('class="codehilite" data-lang="python"', rendered_sample)
        self.assertIn("LoRALinear", rendered_sample)
        self.assertIn("language-python", rendered_sample)
        self.assertNotIn("<table", rendered_sample)
        self.assertNotIn("torch.nnas", generated)

    def test_agent_mianjing_prompt_examples_render_without_line_numbers(self):
        generated = (ROOT / "library" / "agent-mianjing" / "chapter-18.html").read_text(encoding="utf-8")

        self.assertIn('class="codehilite" data-lang="text"', generated)
        self.assertIn("文本：这个电影非常精彩", generated)
        self.assertIn("情感：负面", generated)
        self.assertNotIn("1 任务：判断文本情感", generated)
        self.assertNotIn("2 3 文本：", generated)
        self.assertNotIn("1 请判断以下文本的情感倾向", generated)


if __name__ == "__main__":
    unittest.main()
