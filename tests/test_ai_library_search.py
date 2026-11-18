from pathlib import Path
import json
from contextlib import closing
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import unquote

from pydantic import ValidationError

from interview_forge.ai.token_counting import estimate_json_tokens
from interview_forge.ai.tools.builtins.library import SearchLibraryArgs, latest_card_sources, requested_card_ordinal, search_library
from interview_forge.core.runtime import server_runtime
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.services import community


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ToolExecutionContext(Path("unused.db"), "session", "turn", 1, "找站内资料")


class LibrarySearchTests(TestCase):
    def test_explicit_card_ordinal_excludes_quoted_negative_and_ambiguous_language(self):
        for query, number in [
            ("请回读刚才“本轮检索资料”卡片第 2 项，写出这篇的完整标题，并说明当前索引片段涉及的内容。", 2),
            ("请打开上一张本轮检索资料卡第 57 项，告诉我它的章节标题。", 57),
            ("资料卡第二篇", 2), ("资料卡第十一项", 11), ("资料卡第五十七项", 57),
            ("麻烦把上次资料卡里的第二篇给我打开。", 2),
            ("刚才那张资料卡第七条展开说说，如果超出请告诉我一共有几项。", 7),
            ("能不能看看资料卡第三章，如果没找到就告诉我。", 3),
            ("帮我查看资料卡第三条，如果没有，不要猜。", 3),
            ("麻烦把上回那张资料卡的第二条再打开，告诉我章节标题。", 2),
            ("上一张资料卡里的第37条能打开吗？如果越界请告诉我共有几项。", 37),
            ("上回资料卡第三章可以再给我读一下吗？", 3),
        ]:
            self.assertEqual(requested_card_ordinal(query), number)
        for text in ("不要打开资料卡第2项", "如果用户说“打开资料卡第2项”怎么办", "例如：打开资料卡第2项",
                     "正文还是资料卡第2项？", "资料卡第2项，告诉我为什么不要打开", "资料卡第2项只是举例",
                     "“打开资料卡第2项”", "资料卡第十十项", "资料卡第0项", "请打开资料卡第2项和第3项"):
            self.assertIsNone(requested_card_ordinal(text))

    def test_canonical_arguments_and_server_owned_fields(self):
        self.assertEqual(SearchLibraryArgs(query=" TCP ").model_dump(exclude_none=True), {"query": "tcp", "limit": 3})
        for args in (
            {}, {"query": "  "}, {"query": "x" * 121}, {"query": "tcp", "limit": 4},
            {"query": "tcp", "limit": 0}, {"query": "tcp", "limit": True},
            {"query": "tcp", "user_db": "unused.db"}, {"query": "tcp", "path": "books"},
            {"query": "tcp", "previous_source": 1}, {"previous_source": 0}, {"previous_source": True},
        ):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                SearchLibraryArgs.model_validate(args)

    def test_read_skips_empty_and_malformed_historical_metadata(self):
        with TemporaryDirectory() as folder:
            context = ToolExecutionContext(Path(folder) / "study.db", "s", "turn", 20, "请按卡片回读")
            old = {"title": "旧章", "url": "/library/a.html"}
            with closing(server_runtime.connect(context.user_db)) as db, db:
                db.execute("INSERT INTO chat_sessions(id,title,created_at,updated_at) VALUES ('s','x','now','now')")
                for metadata in (json.dumps({"library_sources": [old]}), "{", '{}', '{"library_sources":[]}'):
                    db.execute("INSERT INTO chat_messages(session_id,role,content,metadata_json,created_at) "
                               "VALUES ('s','assistant','x',?,'now')", (metadata,))
            self.assertEqual(latest_card_sources(context), [old])
            context.current_query = "例如：打开资料卡第2项"
            result = search_library(context, SearchLibraryArgs(previous_source=2))
            self.assertEqual(result.data["reason"], "selection_not_requested")

    def test_index_ranking_snippet_and_safe_library_relative_links(self):
        book = "../books/hot100/03-题解/0146-LRU 缓存.html"
        long_body = "前" * 300 + "lru" + "后" * 300
        rows = [
            {"url": "caches/chapter-03.html", "title": "双向链表", "text": long_body},
            {"url": book, "title": "0146 LRU 缓存", "text": "哈希表加双向链表"},
            {"url": book, "title": "重复的 LRU 命中", "text": ""},
            {"url": "caches/chapter-02.html", "title": "淘汰策略", "module_title": "LRU", "text": "算法"},
        ]
        with patch.object(community, "_SEARCH_INDEX", rows):
            result = search_library(CONTEXT, SearchLibraryArgs(query="LRU"))
            missing = search_library(CONTEXT, SearchLibraryArgs(query="无此专题"))
        items = result.data["items"]
        self.assertEqual([r["title"] for r in items], ["0146 LRU 缓存", "淘汰策略", "双向链表"])
        self.assertEqual(unquote(items[0]["url"]), book[2:])
        self.assertNotIn(" ", items[0]["url"])
        self.assertEqual([item["snippet"] for item in items[:2]], ["", ""])
        self.assertIn("lru", items[2]["snippet"])
        self.assertLess(len(items[2]["snippet"]), 201)
        self.assertNotIn(long_body, str(result))
        self.assertEqual(result.library_sources, tuple(
            {k: item[k] for k in ("title", "module_title", "url", "body_match")} for item in items
        ))
        self.assertEqual([item["body_match"] for item in items], ["", "", "lru"])
        self.assertEqual(missing.data, {"items": []})
        self.assertEqual(missing.library_sources, ())

    def test_compound_concepts_require_every_term_and_prefer_exact_phrase(self):
        rows = [
            {"url": "m/a.html", "title": "LRU", "text": "通过双向链表维护顺序"},
            {"url": "m/b.html", "title": "双向链表", "text": "节点的删除"},
            {"url": "m/c.html", "title": "专题", "text": "LRU 双向链表的实现"},
        ]
        with patch.object(community, "_SEARCH_INDEX", rows):
            result = search_library(CONTEXT, SearchLibraryArgs(query="LRU 双向链表"))
            self.assertEqual(len(community.search_index_server("LRU 双向链表")), 1)
        self.assertEqual([s["body_match"] for s in result.library_sources], ["lru 双向链表", "双向链表"])
        self.assertIn("维护顺序", result.data["items"][1]["snippet"])

    def test_invalid_index_destinations_cannot_become_references(self):
        urls = [
            "//example.test/article.html", "https://example.test/other.html", "../pages/admin.html",
            "../books/../pages/admin.html", "../books/%2E%2E/private.html", "module\\bad.html",
            ".private/file.html", "../books/file.db", "../books/file.html?fake=.html",
            "../books/file.html#section.html", "module/\x00.html", "/library/absolute.html",
        ]
        rows = [{"url": url, "title": "测试", "text": ""} for url in urls]
        rows.append({"url": "m/chapter-01.html", "title": "测试", "text": "测试资料"})
        with patch.object(community, "_SEARCH_INDEX", rows):
            result = search_library(CONTEXT, SearchLibraryArgs(query="测试", limit=1))
        self.assertEqual([s["url"] for s in result.library_sources], ["/library/m/chapter-01.html"])

    def test_real_index_results_open_locally_and_fit_the_registered_budget(self):
        spec = build_default_tool_registry().get("search_library")
        for term, path in (
            ("TCP", "/library/computer-network/chapter-04.html"),
            ("线程池", "/library/java-concurrency/chapter-11.html"),
            ("0146 LRU 缓存", "/books/hot100/03-题解/07-链表/0146-LRU 缓存.html"),
        ):
            with self.subTest(query=term):
                result = search_library(CONTEXT, SearchLibraryArgs(query=term))
                sources = result.library_sources
                self.assertIn(path, [unquote(source["url"]) for source in sources])
                self.assertTrue(all((ROOT / unquote(s["url"]).lstrip("/")).is_file() for s in sources))
                self.assertLessEqual(len(sources), 3)
                self.assertLessEqual(
                    estimate_json_tokens({"ok": True, "tool": spec.name, "data": result.data}),
                    spec.max_result_tokens,
                )
