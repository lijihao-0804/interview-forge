"""Reusable, cancellation-aware SSE formatting primitive."""
from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator
from collections.abc import Mapping
from typing import Any


async def sse_events(
    source: AsyncIterable[Any],
    *,
    request: Any = None,
) -> AsyncIterator[bytes]:
    """Yield JSON SSE frames and stop when the ASGI client disconnects.

    The source is closed when it exposes ``aclose``.  No route is registered
    by this primitive; it is an internal foundation for future streaming work.
    """
    try:
        async for item in source:
            if request is not None and await request.is_disconnected():
                return
            if isinstance(item, Mapping) and isinstance(item.get("event"), str):
                event_name = str(item["event"])
                event_data = item.get("data", {})
                payload = json.dumps(event_data, ensure_ascii=False, separators=(",", ":"), default=str)
                yield f"event: {event_name}\ndata: {payload}\n\n".encode("utf-8")
            else:
                payload = json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str)
                yield f"data: {payload}\n\n".encode("utf-8")
    finally:
        close = getattr(source, "aclose", None)
        if close is not None:
            await close()
