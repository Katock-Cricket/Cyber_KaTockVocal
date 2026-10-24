from __future__ import annotations

from pathlib import Path

import pytest

from katock.security.redact import redact
from katock.storage.fsops import FsOpsError, file_ready, publish
from katock.storage.meta import empty_meta, read_meta, write_meta


def test_redact_secrets() -> None:
    text = redact(
        "password=supersecret token: abcdefgh Authorization: Bearer "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue",
        secrets=["media-token-value"],
    )
    assert "supersecret" not in text
    assert "eyJhbGci" not in text
    assert "***" in text
    assert "media-token-value" not in redact("see media-token-value", ["media-token-value"])


def test_external_keeps_existing_and_created_replaces(tmp_path: Path) -> None:
    song = tmp_path / "song"
    song.mkdir()
    name = "示例.flac"
    original = song / name
    original.write_bytes(b"old-audio")
    user_file = song / "project.aup3"
    user_file.write_text("user", encoding="utf-8")
    work = tmp_path / "new.flac"
    work.write_bytes(b"new-audio")

    assert publish(work, song, name, origin="external", original=name) == "kept"
    assert original.read_bytes() == b"old-audio"
    assert user_file.read_text(encoding="utf-8") == "user"

    work.write_bytes(b"new-audio")
    assert publish(work, song, name, origin="created", original=name) == "placed"
    assert original.read_bytes() == b"new-audio"
    backups = list(song.glob("_backup_*"))
    assert backups
    assert (backups[0] / name).read_bytes() == b"old-audio"
    assert user_file.read_text(encoding="utf-8") == "user"
    assert file_ready(original)


def test_reject_original_label(tmp_path: Path) -> None:
    work = tmp_path / "new.flac"
    work.write_bytes(b"audio")
    with pytest.raises(FsOpsError):
        publish(work, tmp_path / "song", "原曲.flac", origin="created")


def test_reject_unknown_name(tmp_path: Path) -> None:
    work = tmp_path / "x.bin"
    work.write_bytes(b"hi")
    with pytest.raises(FsOpsError):
        publish(work, tmp_path / "song", "notes.txt", origin="created")


def test_hidden_meta_can_be_rewritten(tmp_path: Path) -> None:
    song = tmp_path / "song"
    meta = empty_meta(
        track_id="1",
        title="歌",
        artist="人",
        album="专",
        year=2018,
        duration_s=1,
        origin="created",
        pass1_model="a",
        pass2_model="b",
    )
    write_meta(song, meta)
    meta["source"] = {"sampleRate": 44100, "bitDepth": 16}
    write_meta(song, meta)
    stored = read_meta(song)
    assert stored is not None
    assert stored["source"]["sampleRate"] == 44100
