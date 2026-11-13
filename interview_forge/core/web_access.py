"""Canonical web paths and the public/private static-content boundary.

URL policy is shared by the FastAPI static router and the legacy
``StudyHandler``.  Paths are decoded repeatedly, normalized, and compared
case-insensitively so Windows and encoded aliases cannot select a private
directory after the public-path check.
"""
from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote

PUBLIC_FILES = frozenset({
    "/",
    "/index.html",
    "/cockpit.html",
    "/maintenance.html",
    "/guide.html",
    "/manifest.webmanifest",
    "/service-worker.js",
    "/favicon.ico",
    "/pages/login.html",
    "/pages/register.html",
    "/api/health",
    "/api/catalog",
    "/api/search",
})
PUBLIC_PREFIXES = ("/assets/", "/books/", "/library/")
PUBLIC_DOCUMENTS = frozenset({
    "/docs/qa-report.html",
    "/docs/深度审查与修复报告-2026-09-08.html",
    "/docs/学情分析ai专项审查报告.html",
})
_WEB_PREFIXES = ("/books/", "/library/", "/pages/", "/assets/", "/api/")
_ADMIN_FILES = frozenset({"/pages/admin.html", "/pages/tools.html"})
_ADMIN_PREFIXES = ("/pages/tools/", "/api/admin/")
_DENIED_SUFFIXES = (
    ".db", ".db-journal", ".db-wal", ".db-shm",
    ".sqlite", ".sqlite-journal", ".sqlite-wal", ".sqlite-shm",
    ".sqlite3", ".sqlite3-journal", ".sqlite3-wal", ".sqlite3-shm",
    ".key", ".pem", ".p12", ".pfx", ".bak", ".backup", ".dump",
    ".sql", ".py", ".pyc", ".log", ".env",
)


def canonical_url_path(value: str) -> str | None:
    """Return a safe URL path, or ``None`` for ambiguous filesystem input.

    Repeated decoding covers generic URL decoding in the HTTP stack plus one
    or more application-level encodings.  Dot segments are rejected before
    normalization.  Trailing dots/spaces and decoded colons are rejected because
    Windows treats them as filesystem aliases while POSIX policy checks do not.
    """
    normalized = str(value or "/")
    for _ in range(4):
        decoded = unquote(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    else:
        return None

    normalized = normalized.replace("\\", "/")
    if ":" in normalized:
        return None
    normalized = "/" + normalized.lstrip("/")
    raw_parts = normalized.split("/")
    if any(part == ".." for part in raw_parts):
        return None

    parts: list[str] = []
    for part in raw_parts:
        if part in ("", "."):
            continue
        if part != part.rstrip(" ."):
            return None
        parts.append(part)
    canonical = "/" + "/".join(parts) if parts else "/"
    canonical = posixpath.normpath(canonical)
    return "/" + canonical.lstrip("/")


def policy_key(value: str) -> str | None:
    canonical = canonical_url_path(value)
    return canonical.casefold() if canonical is not None else None


def is_public_get(value: str) -> bool:
    key = policy_key(value)
    if key is None or is_admin_path(key):
        return False
    return key in PUBLIC_FILES or key.startswith(PUBLIC_PREFIXES)


def is_admin_path(value: str) -> bool:
    key = policy_key(value)
    if key is None:
        return False
    return key in _ADMIN_FILES or key.startswith(_ADMIN_PREFIXES)


def is_sensitive_path(value: str) -> bool:
    """Allow only the reviewed web surface; everything else fails closed."""
    key = policy_key(value)
    if key is None:
        return True
    segments = [segment for segment in key.split("/") if segment]
    if any(segment.startswith(".") for segment in segments):
        return True
    if key.endswith(_DENIED_SUFFIXES):
        return True
    if key in PUBLIC_DOCUMENTS:
        return False
    if key in PUBLIC_FILES:
        return False
    return not key.startswith(_WEB_PREFIXES)


def target_relative_path(root: Path, canonical: str) -> str | None:
    """Resolve a requested path and return its project-relative form."""
    try:
        target = (Path(root) / canonical.lstrip("/")).resolve()
        relative = target.relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return None
    return "/" + relative.as_posix().lstrip("/")
