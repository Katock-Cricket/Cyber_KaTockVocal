"""SQLite 读写。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from katock.domain.status import JOB_ACTIVE, STEP_ORDER
from katock.security.dpapi import protect, unprotect
from katock.storage.db import now_iso

SECRET_APPLE_ID = "apple_id"
SECRET_APPLE_PASSWORD = "apple_password"
SECRET_MEDIA_TOKEN = "media_user_token"
SECRET_TRANSLATOR_KEY = "translator_api_key"


def _dump(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def upsert_track(conn: sqlite3.Connection, fields: dict[str, Any]) -> None:
    fields = dict(fields)
    fields["updated_at"] = now_iso()
    columns = list(fields)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "track_id")
    conn.execute(
        f"INSERT INTO tracks ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(track_id) DO UPDATE SET {updates}",
        [fields[column] for column in columns],
    )


def get_track(conn: sqlite3.Connection, track_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    return _dump(row)


def prepared_ids(conn: sqlite3.Connection, track_ids: list[str]) -> set[str]:
    if not track_ids:
        return set()
    marks = ",".join("?" for _ in track_ids)
    rows = conn.execute(
        f"SELECT track_id FROM tracks WHERE track_id IN ({marks}) "
        "AND dir_path IS NOT NULL AND status IN ('done', 'partial')",
        track_ids,
    ).fetchall()
    return {row["track_id"] for row in rows}


def active_job_for_track(conn: sqlite3.Connection, track_id: str) -> dict[str, Any] | None:
    marks = ",".join("?" for _ in JOB_ACTIVE)
    sql = (
        "SELECT * FROM jobs WHERE track_id = ? AND status IN "
        f"({marks}) ORDER BY created_at DESC LIMIT 1"
    )
    row = conn.execute(sql, (track_id, *JOB_ACTIVE)).fetchone()
    return _dump(row)


def latest_job_for_track(conn: sqlite3.Connection, track_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM jobs WHERE track_id = ? ORDER BY created_at DESC LIMIT 1",
        (track_id,),
    ).fetchone()
    return _dump(row)


def insert_job(
    conn: sqlite3.Connection, job_id: str, track_id: str, force_steps: list[str]
) -> None:
    stamp = now_iso()
    conn.execute(
        "INSERT INTO jobs (id, track_id, status, force_steps, created_at, updated_at) "
        "VALUES (?, ?, 'queued', ?, ?, ?)",
        (job_id, track_id, json.dumps(force_steps), stamp, stamp),
    )
    for name in STEP_ORDER:
        conn.execute(
            "INSERT INTO steps (job_id, name, status) VALUES (?, ?, 'pending')",
            (job_id, name),
        )


def reset_job(
    conn: sqlite3.Connection, job_id: str, force_steps: list[str], status: str = "queued"
) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, force_steps = ?, error_summary = NULL, error_kind = NULL, "
        "updated_at = ? WHERE id = ?",
        (status, json.dumps(force_steps), now_iso(), job_id),
    )
    conn.execute(
        "UPDATE steps SET status = 'pending', started_at = NULL, ended_at = NULL, progress = 0, "
        "progress_estimated = 0, eta_s = NULL, eta_label = '', elapsed_s = NULL, "
        "error_detail = NULL, error_kind = NULL, note = '' WHERE job_id = ?",
        (job_id,),
    )


def list_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT jobs.*, tracks.title, tracks.artist, tracks.album, tracks.duration_s, "
        "tracks.artwork_url, tracks.dir_path, tracks.year "
        "FROM jobs JOIN tracks ON tracks.track_id = jobs.track_id "
        "ORDER BY jobs.created_at ASC"
    ).fetchall()
    return [_dump(row) or {} for row in rows]


def get_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT jobs.*, tracks.title, tracks.artist, tracks.album, tracks.album_artist, "
        "tracks.duration_s, tracks.artwork_url, tracks.dir_path, tracks.year, tracks.storefront, "
        "tracks.song_url, tracks.track_number, tracks.disc_number, tracks.audio_locale, "
        "tracks.origin AS track_origin "
        "FROM jobs JOIN tracks ON tracks.track_id = jobs.track_id WHERE jobs.id = ?",
        (job_id,),
    ).fetchone()
    return _dump(row)


def steps_for(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM steps WHERE job_id = ?", (job_id,)).fetchall()
    order = {name: index for index, name in enumerate(STEP_ORDER)}
    dumped = [_dump(row) or {} for row in rows]
    dumped.sort(key=lambda item: order.get(str(item["name"]), 99))
    return dumped


def update_job(conn: sqlite3.Connection, job_id: str, **fields: Any) -> None:
    fields["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE jobs SET {assignments} WHERE id = ?",
        [*fields.values(), job_id],
    )


def update_step(conn: sqlite3.Connection, job_id: str, name: str, **fields: Any) -> None:
    assignments = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE steps SET {assignments} WHERE job_id = ? AND name = ?",
        [*fields.values(), job_id, name],
    )


def add_sample(
    conn: sqlite3.Connection,
    step: str,
    model: str,
    audio_duration_s: float,
    elapsed_s: float,
) -> None:
    conn.execute(
        "INSERT INTO step_samples (step, model, audio_duration_s, elapsed_s, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (step, model, audio_duration_s, elapsed_s, now_iso()),
    )


def recent_samples(
    conn: sqlite3.Connection, step: str, model: str, limit: int = 10
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT elapsed_s, audio_duration_s FROM step_samples WHERE step = ? AND model = ? "
        "ORDER BY id DESC LIMIT ?",
        (step, model, limit),
    ).fetchall()


def put_secret(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO secrets (key, dpapi_blob) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET dpapi_blob = excluded.dpapi_blob",
        (key, protect(value)),
    )


def get_secret(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT dpapi_blob FROM secrets WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return unprotect(bytes(row["dpapi_blob"]))


def secret_flags(conn: sqlite3.Connection) -> dict[str, bool]:
    rows = conn.execute("SELECT key FROM secrets").fetchall()
    present = {row["key"] for row in rows}
    return {
        "appleIdSet": SECRET_APPLE_ID in present,
        "applePasswordSet": SECRET_APPLE_PASSWORD in present,
        "mediaUserTokenSet": SECRET_MEDIA_TOKEN in present,
        "translatorKeySet": SECRET_TRANSLATOR_KEY in present,
    }


def delete_secret(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM secrets WHERE key = ?", (key,))


def upsert_env(
    conn: sqlite3.Connection,
    item: str,
    ok: bool,
    level: str,
    detail: str,
) -> None:
    conn.execute(
        "INSERT INTO env_status (item, ok, level, detail, checked_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(item) DO UPDATE SET ok = excluded.ok, level = excluded.level, "
        "detail = excluded.detail, checked_at = excluded.checked_at",
        (item, 1 if ok else 0, level, detail, now_iso()),
    )


def list_env(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM env_status ORDER BY item").fetchall()
    return [_dump(row) or {} for row in rows]


def enqueue_command(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO commands (kind, payload, created_at) VALUES (?, ?, ?)",
        (kind, json.dumps(payload, ensure_ascii=False), now_iso()),
    )


def take_commands(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM commands WHERE handled_at IS NULL ORDER BY id ASC"
    ).fetchall()
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    marks = ",".join("?" for _ in ids)
    conn.execute(
        f"UPDATE commands SET handled_at = ? WHERE id IN ({marks})",
        (now_iso(), *ids),
    )
    result = []
    for row in rows:
        item = _dump(row) or {}
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


def emit_event(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict[str, Any],
    job_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events (job_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
        (job_id, kind, json.dumps(payload, ensure_ascii=False), now_iso()),
    )


def events_after(conn: sqlite3.Connection, after_id: int, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
        (after_id, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = _dump(row) or {}
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


def purge_old_events(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM events WHERE created_at < datetime('now', '-7 days')")


def get_lyrics_cache(conn: sqlite3.Connection, track_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM lyrics_cache WHERE track_id = ?", (track_id,)).fetchone()
    return _dump(row)


def put_lyrics_cache(conn: sqlite3.Connection, fields: dict[str, Any]) -> None:
    fields = dict(fields)
    fields["updated_at"] = now_iso()
    columns = list(fields)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "track_id")
    conn.execute(
        f"INSERT INTO lyrics_cache ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(track_id) DO UPDATE SET {updates}",
        [fields[column] for column in columns],
    )


def clear_history(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM steps")
    conn.execute("DELETE FROM jobs")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM commands")
    conn.execute("DELETE FROM lyrics_cache")
    conn.execute("DELETE FROM tracks")


def queue_paused(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT detail FROM env_status WHERE item = 'queue_paused'").fetchone()
    return bool(row and row["detail"] == "1")


def set_queue_paused(conn: sqlite3.Connection, paused: bool) -> None:
    upsert_env(conn, "queue_paused", True, "info", "1" if paused else "0")


def runnable_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT jobs.*, tracks.title, tracks.artist, tracks.album, tracks.album_artist, "
        "tracks.duration_s, tracks.artwork_url, tracks.dir_path, tracks.year, tracks.storefront, "
        "tracks.song_url, tracks.track_number, tracks.disc_number, tracks.audio_locale, "
        "tracks.origin AS track_origin, tracks.track_id "
        "FROM jobs JOIN tracks ON tracks.track_id = jobs.track_id "
        "WHERE jobs.status IN ('queued', 'running') ORDER BY jobs.created_at ASC"
    ).fetchall()
    return [_dump(row) or {} for row in rows]
