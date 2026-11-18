"""Look up excerpts in the site's published bookshelf search index."""
from __future__ import annotations

import json
from contextlib import closing
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_forge.ai.tools.contracts import LibrarySource, ToolExecutionContext, ToolResult
from interview_forge.core.web_access import canonical_url_path, is_sensitive_path
from interview_forge.core.runtime import server_runtime
from interview_forge.services.community import indexed_chapter, search_index_server


class SearchLibraryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_to_lower=True)

    query: str | None = Field(default=None, min_length=1, max_length=120, description="知识点或连续短语。找同时涉及多个概念的章节时用空格分隔，如 LRU 双向链表")
    limit: int = Field(default=3, ge=1, le=3, strict=True)
    previous_source: int | None = Field(default=None, ge=1, le=64, strict=True, description="回读最近一次资料列表中的第几项，从 1 开始。与 query 二选一")

    @model_validator(mode="after")
    def one_lookup(self):
        if (self.query is None) == (self.previous_source is None):
            raise ValueError("请指定 query 或 previous_source 其中一项")
        return self


def _chapter_url(index_url: object) -> str | None:
    # Index URLs are relative to /library/. The book entries have one known
    # parent prefix. Never resolve user input, fetch URLs or open a hit's path.
    if not isinstance(index_url, str) or not index_url.endswith(".html"):
        return None
    if any(c in "%?#\\" or ord(c) < 32 or ord(c) == 127 for c in index_url):
        return None
    path = index_url[2:] if index_url.startswith("../books/") else "/library/" + index_url
    if canonical_url_path(path) != path or is_sensitive_path(path):
        return None
    url = quote(path, safe="/")
    return url if len(url) <= 512 else None


def _previous_chapter(context: ToolExecutionContext, ordinal: int) -> ToolResult:
    with closing(server_runtime.connect(context.user_db)) as db:
        row = db.execute("""SELECT metadata_json FROM chat_messages WHERE session_id=? AND role='assistant'
            AND id < ? AND json_type(metadata_json, '$.library_sources')='array'
            ORDER BY id DESC LIMIT 1""", (context.session_id, context.user_message_id)).fetchone()
    sources = json.loads(row[0])["library_sources"] if row else []
    if ordinal > len(sources):
        return ToolResult({"items": [], "reason": "previous_source_missing", "available": len(sources)})
    prior = sources[ordinal - 1]
    path = unquote(prior["url"])
    index_url = ".." + path if path.startswith("/books/") else path.removeprefix("/library/")
    chapter = indexed_chapter(index_url) if _chapter_url(index_url) == prior["url"] else None
    if chapter is None:
        return ToolResult({"items": [], "reason": "chapter_no_longer_indexed"})
    body = str(chapter.get("text") or "")
    term = prior.get("body_match", "")
    start = body.lower().find(term.lower()) if term else -1
    source = LibrarySource(url=prior["url"], title=str(chapter.get("title") or "")[:96],
                           module_title=str(chapter.get("module_title") or "")[:64],
                           body_match=term if start >= 0 else "")
    offset = max(0, start - 40)
    excerpt = ("…" if offset else "") + body[offset:offset + 196] + ("…" if offset + 196 < len(body) else "")
    return ToolResult({"previous_source": ordinal, "items": [{**source, "snippet": excerpt}],
                       "edition": "current_index"}, "已回读上次所列章节的当前索引", library_sources=(source,))


def search_library(context: ToolExecutionContext, args: SearchLibraryArgs) -> ToolResult:
    if args.previous_source is not None:
        return _previous_chapter(context, args.previous_source)
    items = []
    sources: dict[str, LibrarySource] = {}
    for hit in search_index_server(args.query, all_terms=True):
        url = _chapter_url(hit.get("url"))
        title = hit.get("title")
        if not url or url in sources or not isinstance(title, str) or not title.strip():
            continue
        source = LibrarySource(
            title=title.strip()[:96],
            module_title=str(hit.get("module_title") or "")[:64],
            url=url,
            body_match=str(hit.get("body_match") or ""),
        )
        # A title/module match can legitimately have no matching body text.
        items.append({**source, "snippet": str(hit.get("snippet") or "")[:200]})
        sources[url] = source
        if len(items) >= args.limit:
            break
    return ToolResult(
        {"items": items},
        "找到站内资料" if items else "未找到匹配的站内资料",
        library_sources=tuple(sources.values()),
    )
