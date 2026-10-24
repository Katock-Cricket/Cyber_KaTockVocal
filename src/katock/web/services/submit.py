"""提交曲目：解析目录、写入队列。"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from katock.config import AppConfig
from katock.domain.naming import Probe, resolve_directory
from katock.domain.status import DOWNSTREAM, JOB_ACTIVE, STEP_ORDER
from katock.domain.stems import PASS1_MODEL, PASS2_MODEL
from katock.storage.db import session
from katock.storage.meta import empty_meta, read_meta, write_meta
from katock.storage.repo import (
    active_job_for_track,
    insert_job,
    latest_job_for_track,
    reset_job,
    upsert_track,
)


class SubmitError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def submit_tracks(config: AppConfig, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(tracks) > 50:
        raise SubmitError("单次最多勾选 50 首，请分批提交")
    if not tracks:
        raise SubmitError("没有可提交的曲目")
    results = []
    for track in tracks:
        results.append(_submit_one(config, track))
    return results


def _submit_one(config: AppConfig, track: dict[str, Any]) -> dict[str, Any]:
    track_id = str(track["trackId"])
    with session(config.db_path) as conn:
        active = active_job_for_track(conn, track_id)
        if active:
            return {"jobId": active["id"], "trackId": track_id, "reused": True}
        known = None
        existing = conn.execute(
            "SELECT dir_path FROM tracks WHERE track_id = ?", (track_id,)
        ).fetchone()
        if existing and existing["dir_path"]:
            known = Path(str(existing["dir_path"]))

        def inspect(path: Path) -> Probe:
            if not path.exists():
                return "missing"
            if not path.is_dir():
                return "other"
            meta = read_meta(path)
            if meta is None:
                return "no_meta"
            if str(meta.get("trackId")) == track_id:
                return "same"
            return "other"

        choice = resolve_directory(
            Path(config.output_root),
            str(track["title"]),
            str(track.get("artist") or ""),
            inspect,
            known_dir=known,
        )
        if choice.created:
            choice.path.mkdir(parents=True, exist_ok=True)
        meta = read_meta(choice.path)
        if meta is None:
            meta = empty_meta(
                track_id=track_id,
                title=str(track["title"]),
                artist=str(track.get("artist") or ""),
                album=str(track.get("album") or ""),
                year=track.get("year"),
                duration_s=float(track.get("durationS") or 0),
                origin=choice.origin,
                pass1_model=PASS1_MODEL,
                pass2_model=PASS2_MODEL,
            )
            write_meta(choice.path, meta)
        upsert_track(
            conn,
            {
                "track_id": track_id,
                "title": str(track["title"]),
                "artist": str(track.get("artist") or ""),
                "album": str(track.get("album") or ""),
                "album_artist": str(track.get("albumArtist") or track.get("artist") or ""),
                "year": track.get("year"),
                "duration_s": float(track.get("durationS") or 0),
                "track_number": int(track.get("trackNumber") or 1),
                "disc_number": int(track.get("discNumber") or 1),
                "artwork_url": str(track.get("artworkUrl") or ""),
                "storefront": str(track.get("storefront") or config.storefront),
                "song_url": str(track.get("url") or ""),
                "audio_locale": str(track.get("audioLocale") or ""),
                "dir_path": str(choice.path),
                "origin": str(meta.get("origin") or choice.origin),
                "status": "queued",
            },
        )
        latest = latest_job_for_track(conn, track_id)
        try:
            if latest and latest["status"] not in JOB_ACTIVE:
                reset_job(conn, str(latest["id"]), [])
                job_id = str(latest["id"])
            else:
                job_id = uuid.uuid4().hex
                insert_job(conn, job_id, track_id, [])
        except sqlite3.IntegrityError:
            conn.rollback()
            active = active_job_for_track(conn, track_id)
            if active is None:
                raise
            return {"jobId": active["id"], "trackId": track_id, "reused": True}
    return {"jobId": job_id, "trackId": track_id, "reused": False, "dirPath": str(choice.path)}


def rerun_job(config: AppConfig, job_id: str, step: str | None, force: bool) -> None:
    with session(config.db_path) as conn:
        row = conn.execute("SELECT status, track_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise SubmitError("任务不存在", 404)
        if row["status"] in JOB_ACTIVE:
            raise SubmitError("该曲目正在执行", 409)
        if force:
            steps = list(STEP_ORDER)
        elif step:
            if step not in STEP_ORDER:
                raise SubmitError("未知阶段")
            steps = [step, *DOWNSTREAM[step]]
        else:
            steps = []
        reset_job(conn, job_id, steps)
