"""Reusable, cancellation-aware SSE formatting primitive."""
from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress
from collections.abc import Mapping
from typing import Any


HEARTBEAT_INTERVAL_SECONDS = 12.0


async def sse_events(
    source: AsyncIterable[Any],
    *,
    request: Any = None,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[bytes]:
    """Yield JSON SSE frames and stop when the ASGI client disconnects.

    The source is closed when it exposes ``aclose``.  No route is registered
    by this primitive; it is an internal foundation for future streaming work.
    """
    iterator = source.__aiter__()
    pending: asyncio.Task[Any] | None = None
    interval = max(0.001, float(heartbeat_interval))
    try:
        while True:
            if request is not None and await request.is_disconnected():
                return
            if pending is None:
                pending = asyncio.create_task(iterator.__anext__())
            done, _ = await asyncio.wait((pending,), timeout=interval)
            if not done:
                if request is not None and await request.is_disconnected():
                    return
                yield b": ping\n\n"
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                break
            finally:
                pending = None
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
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        close = getattr(iterator, "aclose", None)
        if not callable(close):
            close = getattr(source, "aclose", None)
        if callable(close):
            with suppress(Exception):
                await close()
