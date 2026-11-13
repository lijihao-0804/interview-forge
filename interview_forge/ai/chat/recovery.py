"""Recover abandoned chat requests, including sessions whose browser never returns."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading

from interview_forge.ai.chat.request_ledger import reconcile_session
from interview_forge.core.paths import USERS_DIR
from interview_forge.observability.logging import log_event
from interview_forge.runtime.shared import FileLock


def _pending_sessions(database: Path) -> list[str]:
    # Opening a normal service connection migrates old databases. Discovery only
    # reads existing files, including installations that predate request keys.
    uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_request_ledger'"
        ).fetchone():
            return []
        return [row[0] for row in conn.execute(
            "SELECT DISTINCT session_id FROM chat_request_ledger WHERE status IN ('reserved','started')"
        )]


def reconcile_accounts(users_dir: Path, *, dry_run: bool = True, stop: threading.Event | None = None) -> dict[str, int]:
    """Inspect aggregate counts. Each repair rechecks ownership under the writer's session lock."""
    counts: Counter[str] = Counter(accounts=0, sessions=0, failures=0)
    for database in users_dir.glob("*/hot100-study.db"):
        if stop is not None and stop.is_set():
            break
        if database.parent.is_symlink() or database.is_symlink() or not database.is_file():
            continue
        try:
            counts["accounts"] += 1
            sessions = _pending_sessions(database)
        except (OSError, sqlite3.Error):
            counts["failures"] += 1
            continue
        for session_id in sessions:
            if stop is not None and stop.is_set():
                break
            counts["sessions"] += 1
            try:
                counts.update(reconcile_session(database, session_id, dry_run=dry_run))
            except (OSError, sqlite3.Error, RuntimeError):
                # An inconsistent receipt is rolled back by the ledger. Report
                # it and keep reconciling other sessions without fabricating a debit.
                counts["failures"] += 1
    return dict(counts)


def _recovery_worker(users_dir: Path, stop: threading.Event) -> None:
    # Keep the election between scans. If the elected process dies, the OS
    # drops the lock and a surviving worker can take over on its next pass.
    while not stop.is_set():
        lease = FileLock("chat-recovery", str(users_dir.resolve()))
        try:
            if lease.acquire():
                while not stop.is_set():
                    stats = reconcile_accounts(users_dir, dry_run=False, stop=stop)
                    if stats["sessions"] or stats["failures"]:
                        log_event("chat_request_reconciliation", **stats)
                    stop.wait(300)
        except (OSError, sqlite3.Error) as exc:
            log_event("chat_request_reconciliation_failed", level="WARNING", error_type=type(exc).__name__)
        finally:
            lease.release()
        stop.wait(60)


async def run_recovery(users_dir: Path, stop: threading.Event) -> None:
    await asyncio.to_thread(_recovery_worker, users_dir, stop)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users-dir", type=Path, default=USERS_DIR)
    parser.add_argument("--apply", action="store_true", help="repair abandoned requests (default: dry run)")
    args = parser.parse_args()
    if not args.users_dir.is_dir():
        parser.error("account database directory does not exist")
    result = reconcile_accounts(args.users_dir, dry_run=not args.apply)
    print(json.dumps({"dry_run": not args.apply, **result}, ensure_ascii=False))
    return int(bool(result["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
