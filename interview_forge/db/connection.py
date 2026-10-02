"""Learning-database connection and one-time schema initialization.

This is the existing study database plumbing extracted from the HTTP server.
The server supplies its business timezone and AI schema initializer so import
timing, migration order, and the single process-wide schema state stay intact.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

from interview_forge.ai.ai_coach import ensure_ai_schema as _default_ensure_ai_schema
from interview_forge.core.paths import DB_PATH
from interview_forge.db.schema import SCHEMA
from interview_forge.db.tuning import configure_connection
from interview_forge.services.review import review_interval, review_interval_content
from interview_forge.runtime.shared import mutex

_SCHEMA_DONE: set[str] = set()
_SCHEMA_LOCK = threading.Lock()


def _prepare_legacy_study_events_schema(connection: sqlite3.Connection) -> None:
    """Add the current ``action`` column to the pre-AC event schema."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_events'"
    ).fetchone()
    if table is None:
        return
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(study_events)")}
    if "action" in columns or "event_type" not in columns:
        return
    connection.execute("ALTER TABLE study_events ADD COLUMN action TEXT NOT NULL DEFAULT 'view'")
    connection.execute(
        "UPDATE study_events SET action = CASE WHEN event_type = 'complete' THEN 'complete' ELSE 'view' END"
    )


def _legacy_business_date(
    timestamp: object,
    fallback: object = "",
    business_tz: tzinfo | None = None,
) -> str:
    """Normalize a historical event timestamp to the business date."""
    if business_tz is None:
        business_tz = timezone(timedelta(hours=8), "Asia/Shanghai")
    try:
        parsed = datetime.fromisoformat(str(timestamp))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=business_tz)
        return parsed.astimezone(business_tz).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(fallback or "")[:10]


def _legacy_submission_timestamp(
    timestamp: object,
    study_date: str,
    business_tz: tzinfo | None = None,
) -> str:
    """Return a valid aware timestamp for a migrated AC submission."""
    if business_tz is None:
        business_tz = timezone(timedelta(hours=8), "Asia/Shanghai")
    try:
        parsed = datetime.fromisoformat(str(timestamp))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=business_tz)
        return parsed.astimezone(business_tz).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return f"{study_date}T00:00:00+08:00"


def _backfill_legacy_completes(
    connection: sqlite3.Connection,
    business_tz: tzinfo | None = None,
) -> None:
    """Idempotently mirror historical complete events into AC submissions."""
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(study_events)")}
    if not {"problem_id", "studied_at"}.issubset(columns):
        return
    if "action" in columns:
        kind_sql = "action"
    elif "event_type" in columns:
        kind_sql = "event_type"
    else:
        return
    date_sql = "study_date" if "study_date" in columns else "NULL"
    events = connection.execute(
        f"SELECT problem_id, studied_at, {date_sql} AS study_date, {kind_sql} AS event_kind "
        "FROM study_events WHERE " + kind_sql + " = 'complete' ORDER BY rowid"
    ).fetchall()
    if not events:
        return
    existing_dates = {
        (int(row["problem_id"]), _legacy_business_date(row["submitted_at"], business_tz=business_tz))
        for row in connection.execute(
            "SELECT problem_id, submitted_at FROM submissions WHERE status = 'ac'"
        )
    }
    migrated: set[tuple[int, str]] = set()
    for row in events:
        problem_id = int(row["problem_id"])
        study_date = _legacy_business_date(row["studied_at"], row["study_date"], business_tz)
        if not study_date:
            continue
        key = (problem_id, study_date)
        if key in existing_dates or key in migrated:
            continue
        connection.execute(
            """INSERT INTO submissions(
                   problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               ) VALUES (?, 'ac', '', NULL, NULL, ?, 'manual')""",
            (
                problem_id,
                _legacy_submission_timestamp(row["studied_at"], study_date, business_tz),
            ),
        )
        migrated.add(key)
    if migrated:
        connection.commit()


def _migrate_legacy_review_cards(
    connection: sqlite3.Connection,
    business_tz: tzinfo | None = None,
) -> None:
    """Seed FSRS state from legacy schedules without inventing old ratings.

    Existing due dates are preserved by mapping the old scheduled interval to
    FSRS stability at the default 90% retention. New review logs begin only
    when a user supplies one of the four explicit ratings.
    """
    if business_tz is None:
        business_tz = timezone(timedelta(hours=8), "Asia/Shanghai")

    def seed_cards(target_type: str, rows: list[sqlite3.Row], content: bool) -> None:
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            target_id = str(row["target_id"])
            stamp = _legacy_submission_timestamp(
                row["reviewed_at"], str(row["study_date"] or ""), business_tz
            )
            study_date = _legacy_business_date(stamp, row["study_date"], business_tz)
            if not study_date:
                continue
            state = grouped.setdefault(target_id, {"dates": set(), "latest": ("", "")})
            dates = state["dates"]
            assert isinstance(dates, set)
            dates.add(study_date)
            latest = state["latest"]
            assert isinstance(latest, tuple)
            if study_date >= str(latest[0]):
                state["latest"] = (study_date, stamp)

        for target_id, state in grouped.items():
            dates = state["dates"]
            latest = state["latest"]
            assert isinstance(dates, set) and isinstance(latest, tuple)
            rounds = len(dates)
            last_date = date.fromisoformat(str(latest[0]))
            interval = review_interval_content(rounds) if content else review_interval(rounds)
            due_date = (last_date + timedelta(days=interval)).isoformat()
            reviewed_at = str(latest[1])
            connection.execute(
                """INSERT OR IGNORE INTO review_cards(
                       target_type, target_id, stability, difficulty, due_date,
                       last_reviewed_at, scheduled_days, reps, lapses, scheduler, updated_at
                   ) VALUES (?, ?, ?, 5.0, ?, ?, ?, ?, 0, 'fsrs-4.5', ?)""",
                (target_type, target_id, float(interval), due_date, reviewed_at,
                 interval, rounds, reviewed_at),
            )

    problem_rows = connection.execute(
        """SELECT CAST(problem_id AS TEXT) AS target_id, submitted_at AS reviewed_at,
                  date(submitted_at, '+8 hours') AS study_date
           FROM submissions WHERE status = 'ac' ORDER BY id"""
    ).fetchall()
    seed_cards("problem", problem_rows, content=False)

    content_rows = connection.execute(
        """SELECT content_id AS target_id, studied_at AS reviewed_at, study_date
           FROM content_events
           WHERE action = 'complete' AND module_id <> 'hot100'
           ORDER BY id"""
    ).fetchall()
    seed_cards("content", content_rows, content=True)


def connect(
    db_path: Path = DB_PATH,
    *,
    business_tz: tzinfo | None = None,
    ensure_ai_schema: Callable[[sqlite3.Connection], None] = _default_ensure_ai_schema,
) -> sqlite3.Connection:
    """Open a learning database and initialize its schema exactly once per path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    configure_connection(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    schema_key = str(db_path)
    if schema_key not in _SCHEMA_DONE:
        with _SCHEMA_LOCK, mutex("schema", str(db_path.resolve())):
            if schema_key not in _SCHEMA_DONE:
                connection.execute("PRAGMA journal_mode = WAL")
                _prepare_legacy_study_events_schema(connection)
                connection.executescript(SCHEMA)
                ensure_ai_schema(connection)
                try:
                    connection.execute("ALTER TABLE submissions ADD COLUMN lc_id INTEGER")
                except sqlite3.OperationalError:
                    pass
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_lc ON submissions(lc_id) WHERE lc_id IS NOT NULL"
                )
                _backfill_legacy_completes(connection, business_tz)
                _migrate_legacy_review_cards(connection, business_tz)
                connection.commit()
                _SCHEMA_DONE.add(schema_key)
    return connection
