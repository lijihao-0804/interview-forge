"""One Code Focus notification watcher per serving worker with connected readers."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator
from threading import Event

from interview_forge.runtime.streaming import HEARTBEAT_INTERVAL_SECONDS
from interview_forge.services.code_focus import publication_signal_directory, publication_version


RECONCILE_SECONDS = 30.0
logger = logging.getLogger(__name__)


class PublicationFeed:
    def __init__(self) -> None:
        self.version = -1
        self.changed = asyncio.Event()
        self.readers = 0
        self.watcher: asyncio.Task | None = None
        self.stop = Event()

    def committed(self, version: int) -> None:
        if self.readers and version > self.version:
            self.version = version
            self.changed.set()
            self.changed = asyncio.Event()

    async def _refresh(self) -> None:
        try:
            self.committed(await asyncio.to_thread(publication_version))
        except sqlite3.Error:
            logger.warning("Could not read Code Focus publication version", exc_info=True)

    async def _watch(self, stop: Event) -> None:
        try:
            from watchfiles import awatch  # Included with uvicorn[standard].

            # Reconcile on the first native timeout too, covering a publish that
            # raced installation of the filesystem watch and the initial snapshot.
            deadline = 0.0
            loop = asyncio.get_running_loop()
            async for changes in awatch(
                publication_signal_directory(), recursive=False, watch_filter=None,
                debounce=50, step=25, rust_timeout=1000, yield_on_timeout=True,
                stop_event=stop,
            ):
                if changes or loop.time() >= deadline:
                    await self._refresh()
                    deadline = loop.time() + RECONCILE_SECONDS
        except (ImportError, OSError, RuntimeError):
            logger.warning("Code Focus filesystem notifications unavailable", exc_info=True)
            while not stop.is_set():
                await self._refresh()
                await asyncio.sleep(RECONCILE_SECONDS)

    async def frames(self) -> AsyncIterator[bytes]:
        self.readers += 1
        if self.watcher is None:
            self.stop = Event()
            self.watcher = asyncio.create_task(self._watch(self.stop))
        try:
            # On every (re)connect, send the durable version including zero.
            # Register first so a notification during the read cannot be lost.
            self.committed(await asyncio.to_thread(publication_version))
            sent = -1
            while True:
                if self.version > sent:
                    sent = self.version
                    yield f"id: {sent}\nevent: publication\ndata: {sent}\n\n".encode("ascii")
                else:
                    try:
                        await asyncio.wait_for(self.changed.wait(), HEARTBEAT_INTERVAL_SECONDS)
                    except asyncio.TimeoutError:
                        yield b": ping\n\n"
        finally:
            self.readers -= 1
            if self.readers == 0:
                self.stop.set()
                self.watcher.cancel()
                self.watcher = None
                self.version = -1
                self.changed = asyncio.Event()
