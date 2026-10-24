"""用假下载器和假分离器把六段流水线跑完。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from katock.adapters.catalog import Catalog
from katock.adapters.ffmpeg import Ffmpeg
from katock.adapters.translator import Translation, Translator
from katock.domain.naming import original_filename
from katock.domain.status import STEP_ORDER
from katock.domain.stems import (
    FILE_COVER,
    FILE_HARMONY,
    FILE_INSTRUMENTAL,
    FILE_LEAD,
    FILE_LRC,
    FILE_SRT,
)
from katock.storage.db import session
from katock.storage.meta import empty_meta, read_meta, write_meta
from katock.storage.repo import (
    SECRET_MEDIA_TOKEN,
    SECRET_TRANSLATOR_KEY,
    get_job,
    put_secret,
    reset_job,
    steps_for,
    update_job,
    upsert_env,
)
from katock.web.services.submit import submit_tracks
from katock.worker.execute import StepFailed, execute_step, fail_job, should_skip
from tests.conftest import fake_env, install_launcher, make_config, make_flac, make_jpeg

TTML = """<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="en" itunes:timing="Line">
  <body><div>
    <p begin="0:00.000">Is this the real life?</p>
    <p begin="0:00.500">(Ooh)</p>
  </div></body>
</tt>"""


def _prepare(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[object, Path]:
    audio = tmp_path / "source.flac"
    make_flac(audio)
    jpeg = tmp_path / "tiny.jpg"
    make_jpeg(jpeg)
    install_launcher(tmp_path, launcher)
    fake_env(monkeypatch, audio)
    config = make_config(tmp_path)
    image = jpeg.read_bytes()

    async def fake_cover(self: Catalog, _url: str) -> tuple[bytes, int, int]:
        return image, 64, 64

    async def fake_lyrics(self: Catalog, _storefront: str, _track_id: str, _media: str) -> str:
        return TTML

    async def fake_translate(
        self: Translator,
        lines: list[str],
        *,
        base_url: str,
        model: str,
        api_key: str,
    ) -> Translation:
        assert lines == ["Is this the real life?", "(Ooh)"]
        assert api_key == "translator-key"
        return Translation(lines=("这是真实的人生吗？", "（呜）"), token_usage=18)

    monkeypatch.setattr(Catalog, "cover_bytes", fake_cover)
    monkeypatch.setattr(Catalog, "lyrics_ttml", fake_lyrics)
    monkeypatch.setattr(Translator, "translate", fake_translate)
    with session(config.db_path) as conn:
        upsert_env(conn, "docker", True, "ok", "ready")
        upsert_env(conn, "wrapper_login", True, "ok", "ready")
        put_secret(conn, SECRET_MEDIA_TOKEN, "test-token-value")
        put_secret(conn, SECRET_TRANSLATOR_KEY, "translator-key")
    return config, audio


def test_pipeline_publishes_seven_files(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, audio = _prepare(tmp_path, launcher, monkeypatch)
    ffmpeg = Ffmpeg(config.ffmpeg_path, config.ffprobe_path)
    duration = ffmpeg.probe(audio).duration_s
    created = submit_tracks(
        config,
        [
            {
                "trackId": "6781027645",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "Bohemian Rhapsody",
                "albumArtist": "Queen",
                "year": 2018,
                "durationS": duration,
                "url": "https://music.apple.com/cn/album/bohemian-rhapsody/6781027361?i=6781027645",
                "audioLocale": "en-US",
                "artworkUrl": "https://example.invalid/{w}x{h}.{f}",
            }
        ],
    )[0]
    song = Path(str(created["dirPath"]))
    (song / "notes.txt").write_text("keep", encoding="utf-8")

    def run(step: str) -> None:
        with session(config.db_path) as conn:
            job = get_job(conn, str(created["jobId"]))
        assert job is not None
        asyncio.run(execute_step(config, config.db_path, job, step))

    for step in STEP_ORDER:
        run(step)

    original = original_filename("Bohemian Rhapsody", song)
    for name in (
        original,
        FILE_INSTRUMENTAL,
        FILE_LEAD,
        FILE_HARMONY,
        FILE_COVER,
        FILE_LRC,
        FILE_SRT,
    ):
        assert (song / name).stat().st_size > 0
    lrc = (song / FILE_LRC).read_text(encoding="utf-8")
    assert lrc.count("Is this the real life?") == 1
    assert "这是真实的人生吗？" in lrc
    assert "(Ooh)" in lrc
    assert (song / "notes.txt").read_text(encoding="utf-8") == "keep"
    meta = read_meta(song)
    assert meta is not None
    assert meta["lyrics"]["bilingual"] is True
    assert meta["lyrics"]["tokenUsage"] == 18
    assert meta["originalFile"] == original
    assert not (song / "原曲.flac").exists()
    probe = ffmpeg.probe(song / original)
    assert abs(probe.duration_s - duration) <= 1
    tagged = ffmpeg.probe(song / original)
    assert tagged.sample_rate > 0
    with session(config.db_path) as conn:
        job = get_job(conn, str(created["jobId"]))
    assert job is not None
    assert job["status"] == "done"
    assert not (config.work_dir / str(created["jobId"])).exists()

    with session(config.db_path) as conn:
        reset_job(conn, str(created["jobId"]), [])
    run("download")
    with session(config.db_path) as conn:
        download = next(
            item for item in steps_for(conn, str(created["jobId"])) if item["name"] == "download"
        )
    assert download["status"] == "skipped"

    with session(config.db_path) as conn:
        reset_job(conn, str(created["jobId"]), ["download"])
    run("download")
    assert list(song.glob("_backup_*"))


def test_download_failure_cancels_downstream(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, audio = _prepare(tmp_path, launcher, monkeypatch)
    ffmpeg = Ffmpeg(config.ffmpeg_path, config.ffprobe_path)
    created = submit_tracks(
        config,
        [
            {
                "trackId": "9",
                "title": "失败曲",
                "artist": "Queen",
                "album": "A",
                "durationS": ffmpeg.probe(audio).duration_s,
                "url": "https://music.apple.com/cn/album/x/1?i=9",
            }
        ],
    )[0]
    monkeypatch.setenv("KATOCK_FAKE_AMD_MODE", "auth")
    with session(config.db_path) as conn:
        job = get_job(conn, str(created["jobId"]))
    assert job is not None
    with pytest.raises(StepFailed) as caught:
        asyncio.run(execute_step(config, config.db_path, job, "download"))
    assert caught.value.kind == "auth"
    fail_job(config, config.db_path, job, caught.value.summary, caught.value.kind, "download")
    with session(config.db_path) as conn:
        job = get_job(conn, str(created["jobId"]))
        statuses = {item["name"]: item["status"] for item in steps_for(conn, str(created["jobId"]))}
    assert job is not None
    assert job["status"] == "failed"
    assert statuses["download"] == "failed"
    assert statuses["cover"] == "cancelled"
    assert not (config.work_dir / str(created["jobId"]) / "config.yaml").exists()


def _submit_lyrics_job(config: object) -> dict[str, object]:
    created = submit_tracks(
        config,  # type: ignore[arg-type]
        [
            {
                "trackId": "6781027645",
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "album": "Bohemian Rhapsody",
                "durationS": 1,
                "url": "https://music.apple.com/cn/album/bohemian-rhapsody/6781027361?i=6781027645",
                "audioLocale": "en-US",
            }
        ],
    )[0]
    return created


def test_lyrics_follow_auto_switch_and_job_choice(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _audio = _prepare(tmp_path, launcher, monkeypatch)
    config.auto_translate_lyrics = False  # type: ignore[attr-defined]
    created = _submit_lyrics_job(config)
    song = Path(str(created["dirPath"]))

    def run_lyrics() -> str:
        with session(config.db_path) as conn:  # type: ignore[attr-defined]
            job = get_job(conn, str(created["jobId"]))
        assert job is not None
        asyncio.run(execute_step(config, config.db_path, job, "lyrics"))  # type: ignore[attr-defined]
        return (song / FILE_LRC).read_text(encoding="utf-8")

    monolingual = run_lyrics()
    assert "Is this the real life?" in monolingual
    assert "这是真实的人生吗？" not in monolingual

    with session(config.db_path) as conn:  # type: ignore[attr-defined]
        update_job(conn, str(created["jobId"]), translate_lyrics=1)
        reset_job(conn, str(created["jobId"]), ["lyrics"])
    bilingual = run_lyrics()
    assert "这是真实的人生吗？" in bilingual

    config.auto_translate_lyrics = True  # type: ignore[attr-defined]
    with session(config.db_path) as conn:  # type: ignore[attr-defined]
        update_job(conn, str(created["jobId"]), translate_lyrics=0)
        reset_job(conn, str(created["jobId"]), ["lyrics"])
    forced_off = run_lyrics()
    assert "这是真实的人生吗？" not in forced_off


def test_skipped_separation_is_not_repeated(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    song = tmp_path / "videos" / "歌"
    song.mkdir(parents=True)
    for name in (FILE_INSTRUMENTAL, FILE_LEAD, FILE_HARMONY):
        (song / name).write_bytes(b"wav")
    meta = empty_meta(
        track_id="1",
        title="歌",
        artist="人",
        album="专",
        year=1975,
        duration_s=1,
        origin="created",
        pass1_model="a",
        pass2_model="b",
    )
    meta["steps"] = {
        "pass1": {"status": "skipped"},
        "pass2": {"status": "skipped"},
    }
    write_meta(song, meta)
    job = {
        "id": "job",
        "dir_path": str(song),
        "title": "歌",
        "force_steps": '["lyrics"]',
        "origin": "created",
    }
    assert should_skip(config, job, "pass1") is True
    assert should_skip(config, job, "pass2") is True
    assert should_skip(config, job, "lyrics") is False
