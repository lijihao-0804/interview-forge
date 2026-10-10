import json
import unittest
from pathlib import Path

from scripts.build import build_library

ROOT = Path(__file__).resolve().parents[1]


class LibraryReaderLayoutTests(unittest.TestCase):
    def test_mermaid_flowchart_renders_as_a_diagram(self):
        rendered = build_library.render_markdown(
            "```mermaid\nflowchart TD\n    query[用户问题] --> rewrite[问题改写]\n```"
        )

        self.assertIn('<figure class="mermaid-diagram" data-diagram-type="flowchart">', rendered)
        self.assertIn('<pre class="mermaid" aria-label="流程图">', rendered)
        self.assertIn("query[用户问题] --&gt; rewrite[问题改写]", rendered)

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
        self.assertIn(".reader h5{margin:24px 0 9px;font-size:17px;line-height:1.55}", build_library.LIBRARY_CSS)
        self.assertIn(".reader h6{margin:20px 0 8px;font-size:16px;line-height:1.55}", build_library.LIBRARY_CSS)
        self.assertIn(".reader h1,.reader h2,.reader h3,.reader h4,.reader h5,.reader h6{overflow-wrap:break-word}", build_library.LIBRARY_CSS)

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

    def test_agent_mianjing_rag_image_has_no_ocr_dump_and_subheadings_are_structured(self):
        source = (ROOT / "books" / "agent面经" / "agent面经.md").read_text(encoding="utf-8")
        generated = (ROOT / "library" / "agent-mianjing" / "chapter-24.html").read_text(encoding="utf-8")
        document_processing = (ROOT / "library" / "agent-mianjing" / "chapter-26.html").read_text(encoding="utf-8")

        self.assertIn("agent-.pdf-0097-11.png", generated)
        self.assertNotIn("请基于以上资料回答问题", source)
        self.assertNotIn("请基于以上资料回答问题", generated)
        self.assertNotIn("[ 文档 1]", generated)
        self.assertRegex(generated, r'<h5 id="llm-generation">LLM Generation</h5>')
        self.assertNotRegex(source, r"(?m)^\s*-\s*[•◦]\s+")
        self.assertNotRegex(source, r"方式来编\s*\n\s*码")
        self.assertIn("表示方式来编码。因此：", source)
        self.assertIn("多栏排版、复杂排版（如学术论文）易导致文本顺序错乱。", document_processing)
        self.assertRegex(
            document_processing,
            r"<li>\s*<p>多栏排版、复杂排版（如学术论文）易导致文本顺序错乱。</p>\s*</li>",
        )
        self.assertNotIn("•", document_processing)
        self.assertNotIn("来编</p><p>码", document_processing)

    def test_agent_mianjing_ocr_text_and_rag_flow_render_without_duplicate_screenshots(self):
        source = (ROOT / "books" / "agent面经" / "《Agent 面经》.md").read_text(encoding="utf-8")
        source_alias = (ROOT / "books" / "agent面经" / "agent面经.md").read_text(encoding="utf-8")
        chapter_pages = sorted((ROOT / "library" / "agent-mianjing").glob("chapter-*.html"))
        sentence = "上下文压缩的目标是：在保留关键信息的前提下，减少输入文本长度。"
        matching_pages = [page for page in chapter_pages if sentence in page.read_text(encoding="utf-8")]

        self.assertEqual(source, source_alias)
        self.assertNotIn("<!-- Start of picture text -->", source)
        self.assertNotIn("<!-- End of picture text -->", source)
        self.assertIn("agent面经.pdf-0039-08.png", source)
        self.assertIn("agent面经.pdf-0124-10.png", source)
        self.assertEqual(len(matching_pages), 1)
        generated = matching_pages[0].read_text(encoding="utf-8")
        self.assertNotIn("agent面经.pdf-0123-10.png", "".join(page.read_text(encoding="utf-8") for page in chapter_pages))
        self.assertEqual(generated.count(sentence), 1)
        self.assertIn('<figure class="mermaid-diagram" data-diagram-type="flowchart">', generated)
        self.assertIn("User Query", generated)
        self.assertIn("Multi Query Retrieval", generated)
        self.assertIn("LLM Generation", generated)

    def test_agent_mianjing_tool_components_have_consistent_numbered_labels(self):
        source = (ROOT / "books" / "agent面经" / "《Agent 面经》.md").read_text(encoding="utf-8")
        self.assertIn("**1. 名称（Tool Name / Name）**", source)
        self.assertIn("**2. 描述（Description）**", source)
        self.assertIn("**3. 执行函数（Function）**", source)


if __name__ == "__main__":
    unittest.main()
