"""队列恢复与密钥往返。"""

from __future__ import annotations

from pathlib import Path

from katock.domain.status import JOB_QUEUED, JOB_RUNNING, STEP_PENDING, STEP_RUNNING
from katock.storage.db import session
from katock.storage.repo import (
    SECRET_TRANSLATOR_KEY,
    get_job,
    get_secret,
    insert_job,
    put_secret,
    steps_for,
    update_job,
    update_step,
    upsert_track,
)
from katock.worker.scheduler import _recover
from tests.conftest import make_config


def test_secret_roundtrip_and_recover(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    with session(config.db_path) as conn:
        put_secret(conn, SECRET_TRANSLATOR_KEY, "not-the-real-key")
        assert get_secret(conn, SECRET_TRANSLATOR_KEY) == "not-the-real-key"
        upsert_track(
            conn,
            {
                "track_id": "1",
                "title": "歌",
                "artist": "人",
                "album": "专",
                "dir_path": str(tmp_path / "song"),
                "origin": "created",
                "status": JOB_RUNNING,
            },
        )
        insert_job(conn, "job1", "1", [])
        update_job(conn, "job1", status=JOB_RUNNING)
        update_step(conn, "job1", "download", status=STEP_RUNNING)
    _recover(config)
    with session(config.db_path) as conn:
        job = get_job(conn, "job1")
        assert job is not None
        assert job["status"] == JOB_QUEUED
        download = next(item for item in steps_for(conn, "job1") if item["name"] == "download")
        assert download["status"] == STEP_PENDING
