"""Process and bounded aggregation helpers shared by admin services."""
from __future__ import annotations

import time
from datetime import datetime, timezone

STARTED_AT = datetime.now(timezone.utc)
STARTED_MONOTONIC = time.monotonic()


def started_at() -> str:
    return STARTED_AT.isoformat(timespec="seconds")


def uptime_seconds() -> int:
    return max(0, int(time.monotonic() - STARTED_MONOTONIC))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["now_utc", "started_at", "uptime_seconds"]
