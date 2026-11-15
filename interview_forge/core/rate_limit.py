"""In-process authentication rate limits."""
from __future__ import annotations

import threading
import time

_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCKOUT_SECONDS = 600.0


def login_rate_limit_ok(ip: str) -> bool:
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.get(ip)
        if not entry:
            return True
        fails, unlock_at = entry
        return fails < _LOGIN_MAX_FAILS or time.time() >= unlock_at


def login_rate_limit_fail(ip: str) -> None:
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.setdefault(ip, [0, 0.0])
        entry[0] += 1
        if entry[0] >= _LOGIN_MAX_FAILS:
            entry[1] = time.time() + _LOGIN_LOCKOUT_SECONDS


def login_rate_limit_clear(ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(ip, None)
