"""Look up excerpts in the site's published bookshelf search index."""
from __future__ import annotations

from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.ai.tools.contracts import LibrarySource, ToolExecutionContext, ToolResult
from interview_forge.core.web_access import canonical_url_path, is_sensitive_path
from interview_forge.services.community import search_index_server


class SearchLibraryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_to_lower=True)

    query: str = Field(min_length=1, max_length=120, description="一个知识点关键词或连续短语，如线程池或 TCP")
    limit: int = Field(default=3, ge=1, le=3, strict=True)


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


def search_library(_context: ToolExecutionContext, args: SearchLibraryArgs) -> ToolResult:
    items = []
    sources: dict[str, LibrarySource] = {}
    for hit in search_index_server(args.query):
        url = _chapter_url(hit.get("url"))
        title = hit.get("title")
        if not url or url in sources or not isinstance(title, str) or not title.strip():
            continue
        source = LibrarySource(
            title=title.strip()[:96],
            module_title=str(hit.get("module_title") or "")[:64],
            url=url,
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
