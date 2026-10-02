"""Bounded, per-connection SQLite settings (not a multi-process task lock)."""
from __future__ import annotations

import os
import sqlite3


def _integer_setting(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if 0 <= value <= maximum else default


def configure_connection(connection: sqlite3.Connection, *, auth: bool = False) -> None:
    """Apply on every open, outside schema initialization.

    Retain the existing 10-second lock wait and FULL durability by default.
    NORMAL is an explicit learning-DB opt-in; auth always remains FULL.
    Page cache is a per-connection budget, not a reservation or shared cache.
    mmap is an upper bound and may be limited by the SQLite build/platform.
    """
    busy_ms = _integer_setting("IF_SQLITE_BUSY_TIMEOUT_MS", 10000, 60000)
    cache_kib = _integer_setting("IF_SQLITE_CACHE_KIB", 32000, 65536)
    mmap_bytes = _integer_setting("IF_SQLITE_MMAP_BYTES", 268435456, 1073741824)
    synchronous = os.environ.get("IF_SQLITE_SYNCHRONOUS", "FULL").upper()
    if auth or synchronous not in {"FULL", "NORMAL"}:
        synchronous = "FULL"
    connection.execute(f"PRAGMA busy_timeout = {busy_ms}")
    connection.execute(f"PRAGMA cache_size = {-cache_kib}")
    connection.execute(f"PRAGMA mmap_size = {mmap_bytes}")
    connection.execute(f"PRAGMA synchronous = {synchronous}")
