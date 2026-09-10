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
"""
