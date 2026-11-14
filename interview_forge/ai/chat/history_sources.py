"""Point cited recall results back to their exact stored character ranges."""
from __future__ import annotations

import hashlib
import re
from contextlib import closing
from pathlib import Path
from typing import TypedDict

from interview_forge.core.runtime import server_runtime


class HistorySource(TypedDict):
    message_id: int
    offset: int
    length: int
    sha256: str


_CITED_ID = re.compile(
    r"[#＃]\s*(\d{1,19})(?!\d)|(?:消息|message)\s*(?:ID|编号)?\s*[：:]?\s*(\d{1,19})(?!\d)", re.I,
)


def cited_history_sources(answer: str, visible_items: list[dict]) -> tuple[HistorySource, ...]:
    if not visible_items:
        return ()
    cited = {int(a or b) for a, b in _CITED_ID.findall(answer)}
    sources = {}
    # The caller supplies only results still visible at final model admission.
    for item in visible_items:
        if not isinstance(item, dict):
            continue
        mid, start, excerpt = item.get("message_id"), item.get("offset"), item.get("excerpt")
        if type(mid) is not int or mid not in cited or type(start) is not int or start < 0:
            continue
        if not isinstance(excerpt, str) or not 0 < len(excerpt) <= 320:
            continue
        sources[(mid, start, len(excerpt))] = HistorySource(
            message_id=mid, offset=start, length=len(excerpt),
            sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        )
    return tuple(sources.values())


def read_source(database: Path, session_id: str, mid: int, offset: int, length: int, expected: str) -> dict | None:
    # Use the same Unicode code-point offsets as the recall tool and verify the
    # returned text so a changed message never displays as an earlier quote.
    if not (0 < mid < 2**63 and 0 <= offset < 2**31 and 0 < length <= 320
            and re.fullmatch("[0-9a-f]{64}", expected)):
        return None
    with closing(server_runtime.connect(database)) as conn:
        row = conn.execute("SELECT role, content FROM chat_messages WHERE session_id=? AND id=?",
                           (session_id, mid)).fetchone()
    if row is None:
        return None
    excerpt = row["content"][offset:offset + length]
    if len(excerpt) != length or hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != expected:
        return None
    return {"message_id": mid, "role": row["role"], "offset": offset, "excerpt": excerpt}
