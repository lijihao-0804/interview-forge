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
CREATE TABLE IF NOT EXISTS review_cards (
    target_type TEXT NOT NULL CHECK (target_type IN ('problem', 'content')),
    target_id TEXT NOT NULL,
    stability REAL NOT NULL,
    difficulty REAL NOT NULL,
    due_date TEXT NOT NULL,
    last_reviewed_at TEXT NOT NULL,
    scheduled_days INTEGER NOT NULL,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    scheduler TEXT NOT NULL DEFAULT 'fsrs-4.5',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id)
);
CREATE INDEX IF NOT EXISTS ix_review_cards_due ON review_cards(due_date, target_type);
CREATE TABLE IF NOT EXISTS review_logs (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('problem', 'content')),
    target_id TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    rating_name TEXT NOT NULL CHECK (rating_name IN ('again', 'hard', 'good', 'easy')),
    reviewed_at TEXT NOT NULL,
    elapsed_days INTEGER NOT NULL,
    previous_stability REAL,
    next_stability REAL NOT NULL,
    previous_difficulty REAL,
    next_difficulty REAL NOT NULL,
    scheduled_days INTEGER NOT NULL,
    due_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_review_logs_target ON review_logs(target_type, target_id, id DESC);
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
