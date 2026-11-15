-- Public schema from content commit c628146; fixture has no real rows.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT,
    ai_daily_limit INTEGER CHECK (ai_daily_limit IS NULL OR (ai_daily_limit >= 0 AND ai_daily_limit <= 100))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS invite_codes (
    code TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unused' CHECK (status IN ('unused', 'used', 'revoked')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT,
    used_by INTEGER,
    used_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_invite_status ON invite_codes(status);
CREATE TABLE IF NOT EXISTS registration_send_attempts (
    id INTEGER PRIMARY KEY,
    ip_hash TEXT NOT NULL,
    email_hash TEXT NOT NULL,
    requested_at INTEGER NOT NULL,
    completed_at INTEGER,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'sent', 'failed')),
    failure_category TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_registration_attempt_time
    ON registration_send_attempts(requested_at);
CREATE INDEX IF NOT EXISTS ix_registration_attempt_ip
    ON registration_send_attempts(ip_hash, requested_at);
CREATE INDEX IF NOT EXISTS ix_registration_attempt_email
    ON registration_send_attempts(email_hash, requested_at);
CREATE TABLE IF NOT EXISTS registration_email_codes (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    code_salt TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'consumed', 'invalidated')),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    send_attempt_id INTEGER NOT NULL REFERENCES registration_send_attempts(id),
    consumed_at INTEGER,
    invalidated_at INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_code_active_email
    ON registration_email_codes(email COLLATE NOCASE)
    WHERE status IN ('pending', 'active');
CREATE INDEX IF NOT EXISTS ix_registration_code_email
    ON registration_email_codes(email COLLATE NOCASE, id DESC);
CREATE TABLE IF NOT EXISTS public_rate_events (
    id INTEGER PRIMARY KEY,
    namespace TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    occurred_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_public_rate_events_lookup
    ON public_rate_events(namespace, subject_hash, occurred_at);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    page TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_feedback_status ON feedback(status, id DESC);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avatars (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mime TEXT NOT NULL,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_quota_reset_audit (
    id INTEGER PRIMARY KEY,
    actor_admin_id INTEGER NOT NULL REFERENCES users(id),
    target_user_id INTEGER NOT NULL REFERENCES users(id),
    reset_at TEXT NOT NULL,
    before_used INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('city', 'geolocation')),
    display_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
