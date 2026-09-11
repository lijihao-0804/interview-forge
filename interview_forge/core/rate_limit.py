"""In-process authentication and registration rate limits."""
from __future__ import annotations

import threading
import time

_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCKOUT_SECONDS = 600.0
_REGISTER_ATTEMPTS: dict[str, list[float]] = {}
_REGISTER_GLOBAL: list[float] = []
_REGISTER_LOCK = threading.Lock()
_REGISTER_WINDOW = 3600.0
_REGISTER_MAX_PER_IP = 10
_REGISTER_MAX_GLOBAL = 100


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


def register_rate_limit_ok(ip: str) -> bool:
    now = time.time()
    with _REGISTER_LOCK:
        stamps = [stamp for stamp in _REGISTER_ATTEMPTS.get(ip, []) if now - stamp < _REGISTER_WINDOW]
        global_stamps = [stamp for stamp in _REGISTER_GLOBAL if now - stamp < _REGISTER_WINDOW]
        _REGISTER_ATTEMPTS[ip] = stamps
        _REGISTER_GLOBAL[:] = global_stamps
        return len(stamps) < _REGISTER_MAX_PER_IP and len(global_stamps) < _REGISTER_MAX_GLOBAL


def register_rate_limit_record(ip: str) -> None:
    now = time.time()
    with _REGISTER_LOCK:
        _REGISTER_ATTEMPTS.setdefault(ip, []).append(now)
        _REGISTER_GLOBAL.append(now)
