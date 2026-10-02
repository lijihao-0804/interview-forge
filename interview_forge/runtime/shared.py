"""Single-host worker coordination, without introducing another job queue.

Enabled by the server's multi-worker launcher. OS file locks are released on
process death; SQLite stores only the existing LeetCode task's public snapshot.
This is for local disks on one host, not NFS or multi-host deployment.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path

from interview_forge.core.runtime import server_runtime
from interview_forge.db.tuning import configure_connection


def enabled() -> bool:
    return os.environ.get("IF_SHARED_RUNTIME", "0") == "1"


def root() -> Path:
    configured = os.environ.get("IF_RUNTIME_DIR")
    path = Path(configured) if configured else Path(server_runtime.AUTH_DB_PATH).parent / "runtime"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


class FileLock:
    def __init__(self, namespace: str, key: str):
        self.name = hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()
        self.file = None

    def acquire(self) -> bool:
        if self.file is not None:
            return True
        path = root() / f"{self.name}.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        try:
            if os.name == "nt":
                import msvcrt
                # Byte-range locks can extend past EOF; no lock-file content.
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        self.file = handle
        return True

    def release(self) -> None:
        handle, self.file = self.file, None
        if handle is not None:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            # Closing also releases flock on Linux (including on process death).
            handle.close()


@contextmanager
def mutex(namespace: str, key: str, timeout: float = 10):
    if not enabled():
        yield
        return
    lock = FileLock(namespace, key)
    deadline = time.monotonic() + timeout
    delay = 0.001
    while not lock.acquire():
        if time.monotonic() >= deadline:
            raise TimeoutError("worker coordination timed out")
        # Log writes are normally sub-millisecond. Starting at 20ms made short
        # requests pay an artificial scheduling floor under worker contention.
        time.sleep(delay)
        delay = min(0.02, delay * 1.5)
    try:
        yield
    finally:
        lock.release()


_PROCESS_LOCKS: dict[tuple[str, str], FileLock] = {}
_PROCESS_GUARD = threading.Lock()


def register_process(process_id: str) -> None:
    key = (str(root()), process_id)
    with _PROCESS_GUARD:
        if key not in _PROCESS_LOCKS:
            lease = FileLock("process", process_id)
            if not lease.acquire():
                raise RuntimeError("duplicate worker identity")
            _PROCESS_LOCKS[key] = lease


def process_alive(process_id: str | None) -> bool:
    if not process_id:
        return False
    probe = FileLock("process", str(process_id))
    if not probe.acquire():
        return True
    probe.release()
    return False


def lock_held(namespace: str, key: str) -> bool:
    probe = FileLock(namespace, key)
    if not probe.acquire():
        return True
    probe.release()
    return False


def db_signature(path: Path) -> tuple:
    """Detect external commits/checkpoints on supported local filesystems."""
    values = []
    for candidate in (Path(path), Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
            values.append((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except FileNotFoundError:
            values.append(None)
    return tuple(values)


def _state_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(root() / "sync-state.db", timeout=10)
    configure_connection(connection, auth=True)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS sync_states "
                       "(task_id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL)")
    return connection


def save_sync_state(task_id: str, task: dict) -> None:
    # Callers supply public status only: never persist credentials or exceptions.
    with closing(_state_connection()) as connection:
        connection.execute("INSERT OR REPLACE INTO sync_states VALUES (?, ?, ?, ?)",
                           (task_id, str(task.get("owner", "")), json.dumps(task), time.time()))
        connection.execute("DELETE FROM sync_states WHERE task_id IN "
                           "(SELECT task_id FROM sync_states ORDER BY updated DESC LIMIT -1 OFFSET 1000) "
                           "AND json_extract(body, '$.running') = 0")
        connection.commit()


def sync_states(owner: str | None = None) -> dict[str, dict]:
    with closing(_state_connection()) as connection:
        if owner is None:
            rows = connection.execute("SELECT task_id, body FROM sync_states ORDER BY updated DESC").fetchall()
        else:
            rows = connection.execute("SELECT task_id, body FROM sync_states WHERE owner=? ORDER BY updated DESC",
                                      (owner,)).fetchall()
    return {task_id: json.loads(body) for task_id, body in rows}
