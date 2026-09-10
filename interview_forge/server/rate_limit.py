"""In-process authentication and registration rate limits."""
from __future__ import annotations

import threading
import time


# ---- 登录防爆破：进程内滑动窗口（IP → [失败次数, 解禁时间戳]），重启即清零 ----
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCKOUT_SECONDS = 600.0

# ---- 注册频控：每 IP 每小时 10 次 + 全局每小时 100 次（防高速穷举注册码）----
_REGISTER_ATTEMPTS: dict[str, list[float]] = {}
_REGISTER_GLOBAL: list[float] = []
_REGISTER_LOCK = threading.Lock()
_REGISTER_WINDOW = 3600.0
_REGISTER_MAX_PER_IP = 10
_REGISTER_MAX_GLOBAL = 100


def login_rate_limit_ok(ip: str) -> bool:
    """该 IP 当前是否允许尝试登录（失败 5 次锁 10 分钟）。"""
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.get(ip)
        if not entry:
            return True
        fails, unlock_at = entry
        if fails < _LOGIN_MAX_FAILS or time.time() >= unlock_at:
            return True
        return False


def login_rate_limit_fail(ip: str) -> None:
    """记录一次登录失败，达到阈值时启动锁定期。"""
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.setdefault(ip, [0, 0.0])
        entry[0] += 1
        if entry[0] >= _LOGIN_MAX_FAILS:
            entry[1] = time.time() + _LOGIN_LOCKOUT_SECONDS


def login_rate_limit_clear(ip: str) -> None:
    """登录成功后清零该 IP 的失败计数。"""
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(ip, None)


def register_rate_limit_ok(ip: str) -> bool:
    """注册接口频控：滑动 1 小时窗口内该 IP ≤10 次、全站 ≤100 次。"""
    now = time.time()
    with _REGISTER_LOCK:
        stamps = [t for t in _REGISTER_ATTEMPTS.get(ip, []) if now - t < _REGISTER_WINDOW]
        global_stamps = [t for t in _REGISTER_GLOBAL if now - t < _REGISTER_WINDOW]
        _REGISTER_ATTEMPTS[ip] = stamps
        _REGISTER_GLOBAL[:] = global_stamps
        return len(stamps) < _REGISTER_MAX_PER_IP and len(global_stamps) < _REGISTER_MAX_GLOBAL


def register_rate_limit_record(ip: str) -> None:
    """记录一次注册尝试（无论成败都计数）。"""
    now = time.time()
    with _REGISTER_LOCK:
        _REGISTER_ATTEMPTS.setdefault(ip, []).append(now)
        _REGISTER_GLOBAL.append(now)
