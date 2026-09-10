"""SQLite DDL owned by the database layer.

The statements are unchanged from the original study server.  AI tables are
appended by the existing AI schema fragment, preserving the current database
initialization order and migration behavior.
"""
from interview_forge.db.ai_schema import AI_DB_SCHEMA

SCHEMA = """
CREATE TABLE IF NOT EXISTS study_events (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('view', 'complete')),
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER,
    source TEXT NOT NULL DEFAULT 'learning-site',
    CHECK ((action = 'complete' AND round_no IS NOT NULL) OR
           (action = 'view' AND round_no IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_problem_round
    ON study_events(problem_id, round_no) WHERE action = 'complete';
CREATE INDEX IF NOT EXISTS ix_study_date ON study_events(study_date DESC);
CREATE INDEX IF NOT EXISTS ix_problem_activity ON study_events(problem_id, studied_at DESC);
CREATE TABLE IF NOT EXISTS content_events (
    id INTEGER PRIMARY KEY,
    module_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('view', 'complete')),
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER,
    CHECK ((action = 'complete' AND round_no IS NOT NULL) OR
           (action = 'view' AND round_no IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_round
    ON content_events(content_id, round_no) WHERE action = 'complete';
CREATE INDEX IF NOT EXISTS ix_content_date ON content_events(study_date DESC);
CREATE INDEX IF NOT EXISTS ix_content_activity ON content_events(content_id, studied_at DESC);
CREATE TABLE IF NOT EXISTS marks (
    target_type TEXT NOT NULL CHECK (target_type IN ('problem', 'content')),
    target_id TEXT NOT NULL,
    mark TEXT NOT NULL CHECK (mark IN ('mastered', 'reviewing', 'weak')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ac', 'wa')),
    lang TEXT NOT NULL DEFAULT '',
    runtime_ms INTEGER,
    memory_kb INTEGER,
    submitted_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'bookmarklet', 'extension', 'sync')),
    lc_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_submissions_problem ON submissions(problem_id, submitted_at DESC);
CREATE TABLE IF NOT EXISTS plan_pins (
    problem_id INTEGER PRIMARY KEY,
    for_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""" + AI_DB_SCHEMA
