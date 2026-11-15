"""Prepare a private SQLite copy for old account code; never replace a live DB.

Stop all application writers before taking the source snapshot or using the copy.
Keep the source as the pre-rollback backup. Deployment/service switching is a
separate reviewed operation. Do not restore a pre-upgrade snapshot after traffic:
that would undo password changes and resurrect revoked sessions.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time


def prepare_rollback_copy(source: Path, destination: Path, *, writers_stopped: bool) -> dict[str, int]:
    if not writers_stopped:
        raise ValueError("Stop all writers and acknowledge the offline snapshot first")
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("Database paths must not be symbolic links")
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Rollback must use a new copy, never the source database")
    repository = Path(__file__).resolve().parents[1]
    if destination.is_relative_to(repository):
        raise ValueError("Keep database snapshots outside the repository and web roots")
    if any(Path(str(destination) + suffix).exists() for suffix in ("", "-wal", "-shm", "-journal")):
        raise FileExistsError("Rollback destination or SQLite sidecar already exists")
    # Exclusive creation prevents accidentally truncating an operator's backup.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, \
             closing(sqlite3.connect(destination, isolation_level=None)) as out:
            src.backup(out)
            if out.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Source database integrity check failed")
            # Materialize the private copy as a single file, without stale WAL.
            out.execute("PRAGMA journal_mode = DELETE")
            out.execute("BEGIN IMMEDIATE")
            try:
                # Old code selects codes by address only. Invalidate all live
                # purposes, not just duplicates, to prevent cross-flow reuse.
                changed = out.execute(
                    "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? "
                    "WHERE status IN ('pending', 'active')", (int(time.time()),)
                ).rowcount
                out.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_code_active_email "
                    "ON registration_email_codes(email COLLATE NOCASE) "
                    "WHERE status IN ('pending', 'active')"
                )
                out.execute("COMMIT")
            except BaseException:
                out.execute("ROLLBACK")
                raise
            if out.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Rollback copy integrity check failed")
        return {"invalidated_codes": changed}
    except BaseException:
        # Only this newly created, unpublished copy is removed on failure.
        destination.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--writers-stopped", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_rollback_copy(args.source, args.destination, writers_stopped=args.writers_stopped)))


if __name__ == "__main__":
    main()
