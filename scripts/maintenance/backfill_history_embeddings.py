"""Precompute the passage index for one existing per-user chat database."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from interview_forge.ai.history_search import backfill_session
from interview_forge.db.ai_schema import ensure_ai_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="Existing account learning database")
    parser.add_argument("--session", help="Restrict to one session in this database")
    args = parser.parse_args()
    uri = args.database.resolve().as_uri() + "?mode=rw"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_sessions'").fetchone():
            parser.error("not a chat learning database")
        ensure_ai_schema(db)
        sql = "SELECT id FROM chat_sessions"
        sessions = db.execute(sql + " WHERE id=?", (args.session,)).fetchall() if args.session else db.execute(sql).fetchall()
        if args.session and not sessions:
            parser.error("session does not exist in this database")
    totals = {"sessions": len(sessions), "passages": 0, "new_vectors": 0}
    for (session_id,) in sessions:
        stats = backfill_session(args.database, session_id)
        for key in ("passages", "new_vectors"):
            totals[key] += stats[key]
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
