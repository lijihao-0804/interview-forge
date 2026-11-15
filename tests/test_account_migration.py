"""Upgrade and rollback against synthetic copies of the previous public schema."""
from contextlib import closing
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from interview_forge.core.runtime import server_runtime
from interview_forge.services import auth, registration
from scripts.prepare_account_rollback import prepare_rollback_copy

OLD_SCHEMA = (Path(__file__).parent / "fixtures/auth_schema_before_account_security.sql").read_text(encoding="utf-8")


def snapshot(source, destination):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)


def seed_old(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript(OLD_SCHEMA)
        db.executescript("""
            ALTER TABLE users ADD COLUMN nickname TEXT NOT NULL DEFAULT '';
            ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT 'java';
            ALTER TABLE users ADD COLUMN last_seen TEXT;
        """)
        for name, email, role in [("legacy", None, "user"), ("permanent", "owner@example.com", "admin"),
                                  ("ordinary_admin", "admin@example.com", "admin")]:
            db.execute("INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                       (name, email, auth.hash_password("old-password"), role, "2026-01-01T00:00:00"))
        db.execute("INSERT INTO sessions VALUES(?,1,'2026-01-01','2099-01-01')", (auth._session_digest("legacy-token"),))
        db.execute("INSERT INTO registration_send_attempts(id,ip_hash,email_hash,requested_at,status) VALUES(1,'fixture','fixture',1,'sent')")
        salt = b"synthetic-fixture-salt"
        db.execute("INSERT INTO registration_email_codes(id,email,code_hash,code_salt,status,created_at,expires_at,send_attempt_id) "
                   "VALUES(1,'pending@example.com',?,?,'active',1,9999999999,1)",
                   (registration._code_digest("123456", salt), salt.hex()))
        db.commit()


@pytest.fixture
def migrated(tmp_path):
    source, working = tmp_path / "old.db", tmp_path / "upgraded.db"
    seed_old(source)
    snapshot(source, working)
    with patch.dict(server_runtime._values, {"AUTH_DB_PATH": working, "USERS_DIR": tmp_path / "users",
                     "_AUTH_READY": False, "PERMANENT_ADMIN_USERNAME": "permanent"}), \
         patch("interview_forge.runtime.shared.enabled", return_value=False):
        with closing(auth.connect_auth()):
            pass
        yield source, working


def rows(db, table):
    return db.execute("SELECT * FROM " + table + " ORDER BY 1").fetchall()


def test_upgrade_preserves_existing_users_sessions_and_scopes_old_codes(migrated):
    source, working = migrated
    with closing(sqlite3.connect(source)) as old, closing(sqlite3.connect(working)) as new:
        assert rows(old, "users") == rows(new, "users")
        assert rows(old, "sessions") == rows(new, "sessions")
        assert new.execute("SELECT purpose,user_id FROM registration_email_codes").fetchone() == ("register", None)
        assert new.execute("SELECT purpose,domain_hash FROM registration_send_attempts").fetchone() == ("register", "")
        schema = new.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        codes = rows(new, "registration_email_codes")
    server_runtime._values["_AUTH_READY"] = False
    with closing(auth.connect_auth()) as again:
        assert [tuple(r) for r in again.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")] == schema
        assert [tuple(r) for r in rows(again, "registration_email_codes")] == codes
        assert again.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert auth.auth_login("legacy", "old-password")["email"] is None
    assert auth.session_user("legacy-token")["username"] == "legacy"


def test_old_registration_code_still_redeems_as_registration_after_upgrade(migrated):
    registration.register_with_email_code("pending@example.com", "migrated_registration", "new-password", "123456", "203.0.113.8")
    assert auth.auth_login("pending@example.com", "new-password")["username"] == "migrated_registration"
    with closing(auth.connect_auth()) as db:
        assert db.execute("SELECT status FROM registration_email_codes WHERE id=1").fetchone()[0] == "consumed"


def test_old_schema_fails_with_parallel_purposes_then_rollback_retains_new_security_state(migrated, tmp_path):
    _source, working = migrated
    with closing(auth.connect_auth()) as db:
        db.execute("INSERT INTO registration_email_codes(email,code_hash,code_salt,purpose,user_id,status,created_at,expires_at,send_attempt_id) "
                   "VALUES('pending@example.com','fixture','fixture','email_change',1,'active',1,9999999999,1)")
        # State produced after upgrade must not be lost on a code rollback.
        db.execute("UPDATE users SET password_hash=?,email='bound@example.com' WHERE id=1", (auth.hash_password("new-password"),))
        db.execute("DELETE FROM sessions WHERE user_id=1")
        db.execute("INSERT INTO users(username,password_hash,created_at) VALUES('new_account',?,'2026-01-01')",
                   (auth.hash_password("new-password"),))
        users, sessions = [tuple(r) for r in rows(db, "users")], [tuple(r) for r in rows(db, "sessions")]
    naive = tmp_path / "naive.db"
    snapshot(working, naive)
    with closing(sqlite3.connect(naive)) as db, pytest.raises(sqlite3.IntegrityError):
        db.executescript(OLD_SCHEMA)
    destination = tmp_path / "rollback.db"
    result = prepare_rollback_copy(working, destination, writers_stopped=True)
    assert result["invalidated_codes"] == 2
    with closing(sqlite3.connect(destination)) as db:
        assert rows(db, "users") == users
        assert rows(db, "sessions") == sessions
        assert db.execute("SELECT COUNT(*) FROM registration_email_codes WHERE status IN ('pending','active')").fetchone()[0] == 0
        db.executescript(OLD_SCHEMA)  # Old startup's unique index now succeeds.
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with closing(sqlite3.connect(working)) as original:
        assert original.execute("SELECT COUNT(*) FROM registration_email_codes WHERE status='active'").fetchone()[0] == 2
    with patch.dict(server_runtime._values, {"AUTH_DB_PATH": destination, "_AUTH_READY": True}):
        assert auth.auth_login("legacy", "new-password")["email"] == "bound@example.com"
        with pytest.raises(ValueError):
            auth.auth_login("legacy", "old-password")
        assert auth.session_user("legacy-token") is None
    # Preparing from an already prepared copy is safe and retains all rows.
    assert prepare_rollback_copy(destination, tmp_path / "again.db", writers_stopped=True)["invalidated_codes"] == 0


def test_rollback_refuses_live_or_existing_targets(migrated, tmp_path):
    _source, working = migrated
    with pytest.raises(ValueError):
        prepare_rollback_copy(working, tmp_path / "never.db", writers_stopped=False)
    assert not (tmp_path / "never.db").exists()
    with pytest.raises(ValueError):
        prepare_rollback_copy(working, working, writers_stopped=True)
    existing = tmp_path / "keep.db"
    existing.write_bytes(b"fixture-preserve")
    with pytest.raises(FileExistsError):
        prepare_rollback_copy(working, existing, writers_stopped=True)
    assert existing.read_bytes() == b"fixture-preserve"
