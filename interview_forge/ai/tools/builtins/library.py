"""Look up excerpts in the site's published bookshelf search index."""
from __future__ import annotations

import json
import re
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
    previous_source: int | None = Field(default=None, ge=1, le=99, strict=True, description="回读最近一次资料列表中的第几项，从 1 开始。与 query 二选一")

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


_CARD_LABEL = re.compile(r"""[“「"]本轮检索资料[”」"]""")
_CARD_REQUEST = re.compile(r"(?:本轮检索资料(?:卡片|卡)?|资料卡片?)\s*(?:里|中)?的?\s*"
                           r"第\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*(?:项|篇|章|条)")
_PREAMBLE = re.compile(r"(?:请|麻烦|想|我|要|帮我|能否|能不能|能|可以|把|给我|打开|回读|查看|读一下|"
                       r"看一下|看看|查一下|读一读|刚才|上次|上回|刚刚|上一张|最近一张|那张|的|\s)*")
_NON_SELECTION = re.compile(
    r"不要|别(?:再)?(?:查|看|读|打开)|无需|不用(?:打开|回读)|举例|例如|假设|示例|引用|假如|或者|还是|[“”「」`\"]"
)


def unclear_card_order(query: str) -> bool:
    return (len(query) <= 200 and "正文" in query and "资料卡" in query and "顺序" in query
            and not re.search(r"举例|例如|假设|示例|假如|[：:`]", query)
            and any(cue in query for cue in ("记不清", "不确定", "弄不清", "分不清", "还是哪份")))


def _nonselection(text: str) -> bool:
    # A condition after the command may qualify failure handling ("如果没有，不要猜").
    # An example or a negative in the selection itself has a different meaning.
    command = re.split(r"[，,。？?]\s*(?:如果|若)(?:没有|没找到|超出|越界|不存在)", text, maxsplit=1)[0]
    return bool(_NON_SELECTION.search(command))


def requested_card_ordinal(query: str) -> int | None:
    text = _CARD_LABEL.sub("本轮检索资料", query.strip())
    if len(text) > 240 or unclear_card_order(text) or _nonselection(text):
        return None
    match = _CARD_REQUEST.search(text)
    if not match or not _PREAMBLE.fullmatch(text[:match.start()]) or _CARD_REQUEST.search(text, match.end()):
        return None
    tail = text[match.end():].strip(" 。！？!?")
    if tail and not re.match(r"^(?:(?:能否|可以|能不能|能)?(?:再)?(?:给我)?(?:打开|读一下|看一下|展开|讲讲|具体讲|说说|介绍|是什么)|"
                             r"[，,、。]\s*(?:请|写出|告诉我|说明|介绍|解释|概括|总结|如果|若))", tail):
        return None
    value = match[1]
    if value.isascii():
        return int(value) or None
    digits = "〇一二三四五六七八九"
    tens, sep, ones = value.partition("十")
    if sep and len(tens) <= 1 and len(ones) <= 1 and (not ones or ones in digits):
        return (digits.index(tens) if tens else 1) * 10 + (digits.index(ones) if ones else 0)
    return digits.index(value) if len(value) == 1 and value in digits else None


def latest_card_sources(context: ToolExecutionContext) -> list[dict]:
    with closing(server_runtime.connect(context.user_db)) as db:
        row = db.execute("""SELECT metadata_json FROM chat_messages WHERE session_id=? AND role='assistant'
            AND id < ? AND CASE WHEN json_valid(metadata_json) THEN
                json_type(metadata_json, '$.library_sources')='array' AND json_array_length(metadata_json, '$.library_sources')>0 END
            ORDER BY id DESC LIMIT 1""", (context.session_id, context.user_message_id)).fetchone()
    sources = json.loads(row[0])["library_sources"] if row else []
    return [s for s in sources if isinstance(s, dict) and isinstance(s.get("url"), str)
            and isinstance(s.get("title"), str) and s["title"]]


def _previous_chapter(context: ToolExecutionContext, ordinal: int) -> ToolResult:
    sources = latest_card_sources(context)
    if ordinal > len(sources):
        return ToolResult({"items": [], "reason": "previous_source_missing", "available": len(sources)})
    prior = sources[ordinal - 1]
    path = unquote(prior["url"])
    index_url = ".." + path if path.startswith("/books/") else path.removeprefix("/library/")
    chapter = indexed_chapter(index_url) if _chapter_url(index_url) == prior["url"] else None
    if chapter is None:
        return ToolResult({"items": [], "reason": "chapter_no_longer_indexed"})
    body = str(chapter.get("text") or "")
    term = prior.get("body_match") if isinstance(prior.get("body_match"), str) else ""
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
        reference = _CARD_LABEL.sub("本轮检索资料", context.current_query)
        if _CARD_REQUEST.search(reference) and _nonselection(reference):
            return ToolResult({"items": [], "reason": "selection_not_requested"})
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
