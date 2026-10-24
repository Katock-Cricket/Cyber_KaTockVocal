"""领域逻辑测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from katock.domain.apple_url import parse_apple_url
from katock.domain.eta import PendingWork, Sample, estimate_stage, queue_remaining_seconds
from katock.domain.language import han_ratio, needs_translation, translation_enabled
from katock.domain.lyrics import LyricLine, parse_timecode, parse_ttml, render_lrc, render_srt
from katock.domain.naming import (
    locate_original,
    original_filename,
    resolve_directory,
    sanitize_title,
)
from katock.domain.state import InvalidTransition, transit
from katock.domain.stems import PASS_OUTPUT_NAMES, output_names
from katock.domain.versions import version_tags


def test_sanitize_illegal_and_length() -> None:
    assert sanitize_title('a/b:c*?"<>|') == "a／b：c＊？＂＜＞｜"
    assert sanitize_title("  结尾点. ") == "结尾点"
    long = "歌" * 90
    assert len(sanitize_title(long)) == 80
    assert sanitize_title(long).endswith("…")


def test_original_filename_uses_title(tmp_path: Path) -> None:
    song = tmp_path / "Bohemian Rhapsody"
    song.mkdir()
    assert original_filename("Bohemian Rhapsody", song) == "Bohemian Rhapsody.flac"
    assert original_filename("a/b", song) == "a／b.flac"
    kept = song / "酒干倘卖无-苏芮.flac"
    kept.write_bytes(b"flac")
    found = locate_original(song, "酒干倘卖无", None, "external")
    assert found == kept


def test_directory_conflict_and_external(tmp_path: Path) -> None:
    root = tmp_path
    existing = root / "波西米亚狂想曲"
    existing.mkdir()
    (existing / "notes.txt").write_text("keep", encoding="utf-8")

    def inspect(path: Path) -> str:
        if path == existing:
            return "no_meta"
        if path.name.endswith("(Queen)"):
            return "other"
        return "missing"

    choice = resolve_directory(root, "波西米亚狂想曲", "Queen", inspect)
    assert choice.origin == "external"
    assert choice.path == existing

    def inspect_other(path: Path) -> str:
        if path.name == "波西米亚狂想曲":
            return "other"
        return "missing"

    choice = resolve_directory(root, "波西米亚狂想曲", "Queen", inspect_other)
    assert choice.path.name == "波西米亚狂想曲 (Queen)"
    assert choice.created is True


def test_same_track_reuses_known_dir(tmp_path: Path) -> None:
    known = tmp_path / "自定义"
    known.mkdir()

    def inspect(path: Path) -> str:
        return "same" if path == known else "missing"

    choice = resolve_directory(tmp_path, "别的名字", "某人", inspect, known_dir=known)
    assert choice.path == known
    assert choice.created is False


def test_apple_song_link() -> None:
    ref = parse_apple_url(
        "https://music.apple.com/cn/album/bohemian-rhapsody/6781027361?i=6781027645"
    )
    assert ref is not None
    assert ref.kind == "song"
    assert ref.storefront == "cn"
    assert ref.album_id == "6781027361"
    assert ref.track_id == "6781027645"


def test_playlist_link() -> None:
    ref = parse_apple_url("https://music.apple.com/cn/playlist/night/pl.abc-def")
    assert ref is not None
    assert ref.kind == "playlist"
    assert ref.playlist_id == "pl.abc-def"


def test_version_tags() -> None:
    assert version_tags("Bohemian Rhapsody (Live)") == ["Live"]
    assert version_tags("Delivery") == []
    assert version_tags("Song Instrumental Remix") == ["Instrumental", "Remix"]


def test_language() -> None:
    assert needs_translation("zh-Hant", "酒矸倘賣無") is False
    assert needs_translation("en", "Is this the real life") is True
    assert needs_translation(None, "是否我真的一无所有") is False
    assert needs_translation(None, "Is this the real life") is True
    assert translation_enabled(True, None) is True
    assert translation_enabled(False, None) is False
    assert translation_enabled(False, 1) is True
    assert translation_enabled(True, 0) is False
    assert han_ratio("これはテスト") == 0


def test_ttml_and_bilingual_layout() -> None:
    ttml = """<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="en" itunes:timing="Line">
  <body><div>
    <p begin="0:34.200">Is this the real life?</p>
    <p begin="0:38.500">(Ooh)</p>
  </div></body>
</tt>"""
    doc = parse_ttml(ttml)
    assert doc.language == "en"
    assert doc.timed is True
    assert doc.lines[1].text == "(Ooh)"
    translated = ("这是真实的人生吗？", "（呜）")
    lrc = render_lrc(doc.lines, translated).strip().splitlines()
    assert lrc == [
        "[00:34.20]Is this the real life?",
        "[00:34.20]这是真实的人生吗？",
        "[00:38.50](Ooh)",
        "[00:38.50]（呜）",
    ]
    srt = render_srt(doc.lines, translated)
    assert "Is this the real life?\n这是真实的人生吗？" in srt
    assert srt.strip().splitlines()[0] == "1"


def test_untimed_lyrics() -> None:
    ttml = """<tt itunes:timing="None"><body><div><p>plain</p></div></body></tt>"""
    doc = parse_ttml(ttml)
    assert doc.timed is False
    assert render_lrc(doc.lines).startswith("[00:00.00]plain")


def test_timecode() -> None:
    assert parse_timecode("00:01:02.500") == 62500
    assert parse_timecode("1:02.5") == 62500


def test_translation_count_mismatch() -> None:
    lines = (LyricLine("a", 0),)
    with pytest.raises(ValueError):
        render_lrc(lines, ("x", "y"))


def test_eta_median_resists_outlier() -> None:
    samples = [Sample(elapsed_s=10, audio_duration_s=10) for _ in range(9)]
    samples.append(Sample(elapsed_s=30, audio_duration_s=10))
    estimate = estimate_stage(samples, 10, default_coeff=9)
    assert estimate.kind == "point"
    assert estimate.seconds == pytest.approx(10)


def test_eta_cold_start() -> None:
    estimate = estimate_stage([], 100, default_coeff=1.5)
    assert estimate.kind == "cold"
    assert "首次执行" in estimate.label
    assert estimate.seconds == pytest.approx(150)


def test_queue_eta_respects_separation_pool() -> None:
    items = [
        PendingWork("a:pass1", "pass1", 100, ()),
        PendingWork("b:pass1", "pass1", 100, ()),
        PendingWork("a:pass2", "pass2", 80, ("a:pass1",)),
    ]
    serial = queue_remaining_seconds(items, {"separation": 1, "download": 1, "light": 4})
    parallel = queue_remaining_seconds(items, {"separation": 2, "download": 1, "light": 4})
    assert serial == pytest.approx(280)
    assert parallel == pytest.approx(180)


def test_state_machine() -> None:
    assert transit("", "enqueue") == "queued"
    assert transit("queued", "dispatch") == "running"
    assert transit("running", "partial") == "partial"
    assert transit("interrupted", "recover") == "queued"
    assert transit("done", "rerun") == "queued"
    with pytest.raises(InvalidTransition):
        transit("done", "dispatch")


def test_stem_map() -> None:
    assert output_names("pass1")["Instrumental"] == "伴奏"
    assert output_names("pass1")["Vocals"] == "完整人声"
    assert output_names("pass2")["Vocals"] == "主音"
    assert output_names("pass2")["Instrumental"] == "和声"
    assert PASS_OUTPUT_NAMES["pass2"]["Instrumental"] == "和声"
