"""Read bounded excerpts from the current chat's persisted source messages."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_forge.ai.chat.relevance import requests_first_history_match
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult

_EXCERPT_CHARS = 320
_SEARCH_ROWS = 256
_MAX_HITS = 3
_MAX_MESSAGE_ID = 2**63 - 1


class RecallChatHistoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message_id: int | None = Field(
        default=None, strict=True, ge=1, le=_MAX_MESSAGE_ID, description="摘要或上次查询给出的来源消息 ID",
    )
    query: str | None = Field(
        default=None, strict=True, min_length=1, max_length=96,
        description="要在历史原文中查找的连续短语，可与消息 ID 合用",
    )
    oldest_first: bool = Field(default=False, strict=True, description="关键词默认从最近查起；查最初的约定时设为 true")
    offset: int = Field(
        default=0, strict=True, ge=0, le=2**31 - 1, description="读取指定消息时的起始字符位置，从零计数",
    )
    before_message_id: int | None = Field(
        default=None, strict=True, ge=1, le=_MAX_MESSAGE_ID,
        description="从近到远翻页，填上次返回的 next_before_message_id",
    )
    after_message_id: int | None = Field(
        default=None, strict=True, ge=1, le=_MAX_MESSAGE_ID,
        description="从早到晚翻页，保持 oldest_first=true，填上次返回的 next_after_message_id",
    )

    @model_validator(mode="after")
    def validate_lookup(self) -> RecallChatHistoryArgs:
        if self.message_id is None and self.query is None:
            raise ValueError("Provide a message_id or a query")
        if self.offset and self.message_id is None:
            raise ValueError("An offset requires a message_id")
        paginated = self.before_message_id is not None or self.after_message_id is not None
        if self.message_id is not None and (self.oldest_first or paginated):
            raise ValueError("Search order and page cursors apply only to keyword searches across messages")
        if self.before_message_id is not None and self.oldest_first:
            raise ValueError("Use after_message_id to continue an oldest-first search")
        if self.after_message_id is not None and not self.oldest_first:
            raise ValueError("Use oldest_first with after_message_id")
        return self


def recall_chat_history(context: ToolExecutionContext, args: RecallChatHistoryArgs) -> ToolResult:
    first_only = requests_first_history_match(context.current_query)
    oldest_first = args.oldest_first or (first_only and args.message_id is None)
    cutoff = context.user_message_id
    if args.before_message_id is not None and not oldest_first:
        cutoff = min(cutoff, args.before_message_id)
    sql = """SELECT id, role, content FROM chat_messages
             WHERE session_id = ? AND id < ? AND role IN ('user', 'assistant')"""
    parameters: list[str | int] = [context.session_id, cutoff]
    if args.message_id is not None:
        sql += " AND id = ?"
        parameters.append(args.message_id)
    if args.after_message_id is not None:
        sql += " AND id > ?"
        parameters.append(args.after_message_id)
    if oldest_first:
        sql += " ORDER BY id ASC LIMIT ?"
        next_cursor = "next_after_message_id"
    else:
        sql += " ORDER BY id DESC LIMIT ?"
        next_cursor = "next_before_message_id"
    parameters.append(_SEARCH_ROWS + 1)

    # Search the original string so offsets address the exact stored text, including
    # Unicode, Markdown fences, punctuation and whitespace. The query is literal.
    pattern = re.compile(re.escape(args.query), re.IGNORECASE) if args.query else None
    items: list[dict[str, object]] = []
    data: dict[str, object] = {"items": items}
    uri = context.user_db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as database:
        last_id = None
        for index, (message_id, role, content) in enumerate(database.execute(sql, parameters)):
            if index == _SEARCH_ROWS or len(items) == _MAX_HITS:
                data[next_cursor] = last_id
                break
            last_id = message_id
            start = args.offset
            if start >= len(content):
                continue
            if pattern is not None:
                match = pattern.search(content, pos=start)
                if match is None:
                    continue
                start = max(start, match.start() - _EXCERPT_CHARS // 4)
            end = min(len(content), start + _EXCERPT_CHARS)
            item = {"message_id": message_id, "role": role, "offset": start, "excerpt": content[start:end]}
            if end < len(content):
                item["next_offset"] = end
            items.append(item)
            if first_only:
                # A hit completes the single-source search. Empty bounded pages
                # still provide their forward cursor; long hits retain next_offset.
                break

    return ToolResult(data, "已找到本会话历史片段" if items else "本次未找到匹配的历史片段")
