"""SQLite DDL fragment for the existing per-user AI tables.

The schema belongs to the database layer; the AI service imports this constant
for its compatibility export and migration helper.
"""

AI_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_tasks (
    task_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    snapshot_hash TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    worker_id TEXT,
    error_category TEXT,
    error_message TEXT,
    context_preview TEXT NOT NULL,
    result_json TEXT,
    fallback_json TEXT NOT NULL,
    insight_id TEXT,
    quota_limit INTEGER
);
CREATE TABLE IF NOT EXISTS ai_insights (
    insight_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_key TEXT NOT NULL,
    data_as_of TEXT,
    result_json TEXT NOT NULL,
    helpful INTEGER,
    feedback_at TEXT
);
CREATE TABLE IF NOT EXISTS ai_daily_quota (
    day_key TEXT PRIMARY KEY,
    used INTEGER NOT NULL DEFAULT 0 CHECK (used >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    reset_offset INTEGER NOT NULL DEFAULT 0 CHECK (reset_offset >= 0),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_updated
    ON chat_sessions(updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id
    ON chat_messages(session_id, id ASC);
"""


def ensure_ai_schema(connection) -> None:
    """Idempotently create/upgrade AI tables in one user's learning DB."""
    connection.executescript(AI_DB_SCHEMA)
    required = {
        "started_at": "TEXT",
        "finished_at": "TEXT",
        "worker_id": "TEXT",
        "error_category": "TEXT",
        "error_message": "TEXT",
        "context_preview": "TEXT NOT NULL DEFAULT '{}'",
        "result_json": "TEXT",
        "fallback_json": "TEXT NOT NULL DEFAULT '{}'",
        "insight_id": "TEXT",
        "quota_day": "TEXT",
        "quota_state": "TEXT NOT NULL DEFAULT 'none'",
        "quota_limit": "INTEGER",
    }
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(ai_tasks)").fetchall()
    }
    for name, declaration in required.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE ai_tasks ADD COLUMN {name} {declaration}")
    quota_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(ai_daily_quota)").fetchall()
    }
    if "reset_offset" not in quota_columns:
        connection.execute(
            "ALTER TABLE ai_daily_quota ADD COLUMN reset_offset INTEGER NOT NULL DEFAULT 0"
        )
    connection.execute("CREATE INDEX IF NOT EXISTS ix_ai_tasks_created ON ai_tasks(created_at DESC)")
    connection.execute(
        """CREATE INDEX IF NOT EXISTS ix_ai_tasks_dedupe
           ON ai_tasks(task, snapshot_hash, prompt_version, model_key, status)"""
    )
    connection.execute("CREATE INDEX IF NOT EXISTS ix_ai_insights_created ON ai_insights(created_at DESC)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_updated "
        "ON chat_sessions(updated_at DESC, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id "
        "ON chat_messages(session_id, id ASC)"
    )
    connection.commit()
