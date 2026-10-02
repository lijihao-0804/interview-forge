"""Bounded process-local read caches, validated against cross-worker DB writes."""
from __future__ import annotations

import threading
import time


class ReadCache:
    def __init__(self, ttl: float, capacity: int):
        self.ttl = ttl
        self.capacity = capacity
        self.entries: dict[tuple, tuple[float, tuple, object]] = {}
        self.lock = threading.Lock()

    def get(self, key: tuple, signature: tuple):
        with self.lock:
            entry = self.entries.get(key)
            if entry and time.monotonic() - entry[0] < self.ttl and entry[1] == signature:
                return entry[2]
            self.entries.pop(key, None)
        return None

    def put(self, key: tuple, signature: tuple, value) -> None:
        with self.lock:
            now = time.monotonic()
            self.entries = {key: entry for key, entry in self.entries.items() if now - entry[0] < self.ttl}
            if len(self.entries) >= self.capacity:
                oldest = min(self.entries, key=lambda item: self.entries[item][0])
                self.entries.pop(oldest)
            self.entries[key] = (now, signature, value)


session_cache = ReadCache(30, 4096)
bootstrap_cache = ReadCache(3, 512)
