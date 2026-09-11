"""Read-only SQLite query primitives for learning analytics.

The query layer contains no business-rule aggregation; it preserves the
facade's constants and exception type through lazy runtime lookup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from collections.abc import Mapping


def _runtime():
    from interview_forge.analytics import learning_analytics
    return learning_analytics

def _is_lock_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _raise_if_lock_error(exc: sqlite3.OperationalError) -> None:
    if _is_lock_error(exc):
        raise _runtime().AnalyticsUnavailableError(
            "learning analytics database is locked; retry the read"
        ) from exc


def _resolve_db_path(db_path: Any, allowed_db_root: Any | None) -> Any:
    """Resolve and constrain a database path without weakening read-only mode."""

    if allowed_db_root is None:
        return db_path
    if isinstance(db_path, str) and db_path == ":memory:":
        raise ValueError(":memory: is not allowed with allowed_db_root")
    try:
        root_input = Path(allowed_db_root)
        db_input = Path(db_path)
    except TypeError as exc:
        raise TypeError("db_path and allowed_db_root must be path-like") from exc
    if ".." in db_input.parts:
        raise ValueError("db_path must not contain a parent traversal component")
    root = root_input.resolve()
    if not root.is_dir():
        raise ValueError("allowed_db_root must point to a directory")
    resolved_db = db_input.resolve()
    try:
        resolved_db.relative_to(root)
    except ValueError as exc:
        raise ValueError("db_path must resolve inside allowed_db_root") from exc
    return resolved_db


def _open_read_only(db_path: Any) -> sqlite3.Connection | None:
    """Open an existing SQLite file with short, query-only read settings."""

    connection: sqlite3.Connection | None = None
    try:
        if isinstance(db_path, str) and db_path == ":memory:":
            connection = sqlite3.connect(
                db_path,
                timeout=_runtime().ANALYTICS_DB_TIMEOUT_SECONDS,
            )
        else:
            path = Path(db_path)
            if not path.exists():
                return None
            if not path.is_file():
                raise ValueError("db_path must point to an SQLite file")
            # Open in SQLite's URI mode=ro first, then keep query_only enabled
            # as a second guard.  This prevents an accidental schema/table
            # mutation even if this module is reused by a caller with a
            # writable file.
            connection = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=_runtime().ANALYTICS_DB_TIMEOUT_SECONDS,
            )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {_runtime().ANALYTICS_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.OperationalError as exc:
        if connection is not None:
            connection.close()
        _raise_if_lock_error(exc)
        raise


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    try:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is not None
        )
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _read_compatible_rows(
    connection: sqlite3.Connection | None,
    table: str,
    quality: dict[str, Any],
) -> list[sqlite3.Row]:
    if connection is None:
        quality["missing_tables"].append(table)
        return []
    schema = _runtime().READ_TABLE_SCHEMAS[table]
    if not _table_exists(connection, table):
        quality["missing_tables"].append(table)
        return []
    columns = _table_columns(connection, table)
    missing_core = [name for name in schema["core"] if name not in columns]
    if missing_core:
        quality["schema_incompatible_details"][table] = {
            "missing_core_columns": missing_core,
        }
        return []
    select_parts = [_quoted_identifier(name) for name in schema["core"]]
    for name, default_sql in schema["optional"].items():
        if name in columns:
            select_parts.append(_quoted_identifier(name))
        else:
            select_parts.append(f"{default_sql} AS {_quoted_identifier(name)}")
    try:
        return connection.execute(
            f"SELECT {', '.join(select_parts)} FROM {_quoted_identifier(table)}"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise
