"""歌曲目录里的 .ktvmeta.json。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from katock.domain.stems import FILE_META
from katock.storage.db import now_iso

SCHEMA_VERSION = 1


def empty_meta(
    *,
    track_id: str,
    title: str,
    artist: str,
    album: str,
    year: int | None,
    duration_s: float,
    origin: str,
    pass1_model: str,
    pass2_model: str,
) -> dict[str, Any]:
    stamp = now_iso()
    return {
        "schema": SCHEMA_VERSION,
        "origin": origin,
        "trackId": track_id,
        "title": title,
        "artist": artist,
        "album": album,
        "year": year,
        "durationS": duration_s,
        "source": {"sampleRate": None, "bitDepth": None},
        "lyrics": {"language": None, "bilingual": False, "timed": True, "note": ""},
        "models": {"pass1": pass1_model, "pass2": pass2_model},
        "steps": {},
        "missing": [],
        "createdAt": stamp,
        "lastRunAt": stamp,
        "lastError": None,
    }


def read_meta(song_dir: Path) -> dict[str, Any] | None:
    path = song_dir / FILE_META
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def write_meta(song_dir: Path, meta: dict[str, Any]) -> None:
    song_dir.mkdir(parents=True, exist_ok=True)
    path = song_dir / FILE_META
    _show(path)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _hide(path)


def _show(path: Path) -> None:
    if not path.exists():
        return
    import ctypes

    ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)


def _hide(path: Path) -> None:
    import ctypes

    ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
