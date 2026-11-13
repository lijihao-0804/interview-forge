from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import unquote

from pydantic import ValidationError

from interview_forge.ai.token_counting import estimate_json_tokens
from interview_forge.ai.tools.builtins.library import SearchLibraryArgs, search_library
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.services import community


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ToolExecutionContext(Path("unused.db"), "session", "turn", 1, "找站内资料")


class LibrarySearchTests(TestCase):
    def test_canonical_arguments_and_server_owned_fields(self):
        self.assertEqual(SearchLibraryArgs(query=" TCP ").model_dump(), {"query": "tcp", "limit": 3})
        for args in (
            {}, {"query": "  "}, {"query": "x" * 121}, {"query": "tcp", "limit": 4},
            {"query": "tcp", "limit": 0}, {"query": "tcp", "limit": True},
            {"query": "tcp", "user_db": "unused.db"}, {"query": "tcp", "path": "books"},
        ):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                SearchLibraryArgs.model_validate(args)

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
            {k: item[k] for k in ("title", "module_title", "url")} for item in items
        ))
        self.assertEqual(missing.data, {"items": []})
        self.assertEqual(missing.library_sources, ())

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
