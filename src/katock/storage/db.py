"""数据库连接与迁移。损坏时重建空库。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT NOT NULL DEFAULT '',
    album_artist TEXT NOT NULL DEFAULT '',
    year INTEGER,
    duration_s REAL NOT NULL DEFAULT 0,
    track_number INTEGER NOT NULL DEFAULT 1,
    disc_number INTEGER NOT NULL DEFAULT 1,
    artwork_url TEXT NOT NULL DEFAULT '',
    storefront TEXT NOT NULL DEFAULT 'cn',
    song_url TEXT NOT NULL DEFAULT '',
    audio_locale TEXT NOT NULL DEFAULT '',
    dir_path TEXT,
    origin TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    status TEXT NOT NULL,
    force_steps TEXT NOT NULL DEFAULT '[]',
    error_summary TEXT,
    error_kind TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
    job_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    progress REAL NOT NULL DEFAULT 0,
    progress_estimated INTEGER NOT NULL DEFAULT 0,
    eta_s REAL,
    eta_label TEXT NOT NULL DEFAULT '',
    elapsed_s REAL,
    error_detail TEXT,
    error_kind TEXT,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (job_id, name)
);

CREATE TABLE IF NOT EXISTS step_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    audio_duration_s REAL NOT NULL,
    elapsed_s REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lyrics_cache (
    track_id TEXT PRIMARY KEY,
    language TEXT,
    timed INTEGER NOT NULL DEFAULT 1,
    original TEXT NOT NULL,
    translation TEXT,
    token_usage INTEGER NOT NULL DEFAULT 0,
    bilingual_failed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets (
    key TEXT PRIMARY KEY,
    dpapi_blob BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS env_status (
    item TEXT PRIMARY KEY,
    ok INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT 'error',
    detail TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    handled_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""

INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_active
    ON jobs(track_id) WHERE status IN ('queued', 'running', 'interrupted');
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS step_samples_lookup ON step_samples(step, model, id);
CREATE INDEX IF NOT EXISTS commands_open ON commands(handled_at, id);
CREATE INDEX IF NOT EXISTS events_created ON events(created_at);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executescript(INDEXES)
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (1)")
    conn.commit()


def open_database(path: Path) -> sqlite3.Connection:
    try:
        conn = connect(path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        migrate(conn)
        return conn
    except sqlite3.DatabaseError:
        if path.exists():
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            path.rename(path.with_name(f"katock.db.corrupt-{stamp}"))
        conn = connect(path)
        migrate(conn)
        return conn


@contextmanager
def session(path: Path) -> Iterator[sqlite3.Connection]:
    conn = open_database(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
