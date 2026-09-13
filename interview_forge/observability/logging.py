"""Credential-free JSONL application logging.

This module deliberately uses only a project-owned rotating file.  Callers
should pass metadata, never request bodies or provider payloads; the final
redaction pass is a second safety boundary.
"""
from __future__ import annotations

import json
import logging as stdlib_logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

from interview_forge.core.paths import PROJECT_ROOT

MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
_LOGGER_NAME = "interview_forge.application"
_CONFIG_LOCK = Lock()
_CONFIGURED_PATH: Path | None = None

_SECRET_KEY = re.compile(
    r"(?:password|passwd|token|cookie|authorization|api[_-]?key|secret|credential|csrf|"
    r"leetcode[_-]?session|prompt|message|content|memory|context|result|arguments|body|"
    r"exception|traceback|locals?)",
    re.I,
)


def log_path() -> Path:
    configured = os.environ.get("INTERVIEW_FORGE_LOG_PATH", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "logs" / "app.jsonl"


def log_paths() -> list[Path]:
    base = log_path()
    return [base, *[Path(f"{base}.{index}") for index in range(1, BACKUP_COUNT + 1)]]


def _safe_value(key: str, value: Any) -> Any:
    if _SECRET_KEY.search(str(key)):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _safe_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(key, item) for item in value[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 256:
            return value[:256] + "…"
        return value
    return str(type(value).__name__)


class _JsonFormatter(stdlib_logging.Formatter):
    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload = getattr(record, "payload", {})
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _logger() -> stdlib_logging.Logger:
    global _CONFIGURED_PATH
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = stdlib_logging.getLogger(_LOGGER_NAME)
    logger.setLevel(stdlib_logging.INFO)
    logger.propagate = False
    with _CONFIG_LOCK:
        if _CONFIGURED_PATH != path:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()
            handler = RotatingFileHandler(
                path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                encoding="utf-8", delay=True,
            )
            handler.setFormatter(_JsonFormatter())
            logger.addHandler(handler)
            _CONFIGURED_PATH = path
    return logger


def log_event(event: str, *, level: str = "INFO", **fields: Any) -> None:
    """Write a bounded, redacted structured event without raising to callers."""
    try:
        payload = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": str(level).upper(),
            "module": str(fields.pop("module", "app"))[:96],
            "event": str(event)[:128],
        }
        payload.update({str(key): _safe_value(str(key), value) for key, value in fields.items()})
        logger = _logger()
        record = logger.makeRecord(
            logger.name, getattr(stdlib_logging, payload["level"], stdlib_logging.INFO),
            __file__, 0, "", (), None,
        )
        record.payload = payload
        logger.handle(record)
    except (OSError, TypeError, ValueError):
        return


def close_log_handlers() -> None:
    """Close the project handler; primarily useful for isolated test runtimes."""
    global _CONFIGURED_PATH
    logger = stdlib_logging.getLogger(_LOGGER_NAME)
    with _CONFIG_LOCK:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        _CONFIGURED_PATH = None


__all__ = ["BACKUP_COUNT", "MAX_BYTES", "close_log_handlers", "log_event", "log_path", "log_paths"]
