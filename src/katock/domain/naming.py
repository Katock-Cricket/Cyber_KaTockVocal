"""歌曲目录名。规则见 PRD FR-09。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_ILLEGAL = str.maketrans(
    {
        "\\": "＼",
        "/": "／",
        ":": "：",
        "*": "＊",
        "?": "？",
        '"': "＂",
        "<": "＜",
        ">": "＞",
        "|": "｜",
    }
)

Probe = Literal["missing", "no_meta", "same", "other"]
Origin = Literal["created", "external"]


@dataclass(frozen=True)
class DirChoice:
    path: Path
    origin: Origin
    created: bool


def sanitize_title(title: str, limit: int = 80) -> str:
    name = title.translate(_ILLEGAL).strip().rstrip(".").strip()
    if not name or name in {".", ".."}:
        name = "未命名"
    if len(name) > limit:
        name = name[: limit - 1] + "…"
    return name


def _with_note(base: str, note: str, limit: int = 80) -> str:
    suffix = f" ({note})"
    room = limit - len(suffix)
    if room < 1:
        return sanitize_title(suffix.strip(), limit)
    head = base if len(base) <= room else (base[: room - 1] + "…")
    return head + suffix


def name_candidates(title: str, artist: str, limit: int = 50) -> list[str]:
    base = sanitize_title(title)
    names = [base]
    artist_name = sanitize_title(artist) if artist.strip() else ""
    if artist_name and artist_name != "未命名":
        names.append(_with_note(base, artist_name))
    index = 2
    while len(names) < limit:
        names.append(_with_note(base, str(index)))
        index += 1
    return names


def original_filename(title: str, song_dir: Path) -> str:
    """原曲使用曲名，不使用固定名 原曲.flac。"""
    stem = sanitize_title(title)
    backup = "_backup_20990101T000000Z"
    while True:
        filename = f"{stem}.flac"
        if len(str(song_dir / backup / filename)) < 260 or len(stem) <= 1:
            return filename
        stem = sanitize_title(stem[:-2], limit=max(1, len(stem) - 2))


def locate_original(
    song_dir: Path, title: str, meta: dict[str, Any] | None, origin: str
) -> Path | None:
    stored = meta or {}
    recorded = stored.get("originalFile")
    if (
        isinstance(recorded, str)
        and recorded == Path(recorded).name
        and recorded not in {"", ".", ".."}
    ):
        path = song_dir / recorded
        if path.is_file() and path.stat().st_size > 0:
            return path
    expected = song_dir / original_filename(title, song_dir)
    if expected.is_file() and expected.stat().st_size > 0:
        return expected
    if origin == "external":
        flacs = [
            path for path in song_dir.glob("*.flac") if path.is_file() and path.stat().st_size > 0
        ]
        if len(flacs) == 1:
            return flacs[0]
    return None


def fit_directory_name(output_root: Path, name: str) -> str:
    """保证歌曲目录加交付物文件名后的路径短于 260。"""
    longest_leaf = "_backup_20990101T000000Z/" + ("x" * 80) + ".flac"
    fitted = name
    while len(str(output_root / fitted / longest_leaf)) >= 260 and len(fitted) > 1:
        fitted = sanitize_title(fitted[:-2], limit=max(1, len(fitted) - 2))
    return fitted


def resolve_directory(
    output_root: Path,
    title: str,
    artist: str,
    inspect: Callable[[Path], Probe],
    known_dir: Path | None = None,
) -> DirChoice:
    if known_dir is not None and inspect(known_dir) == "same":
        return DirChoice(path=known_dir, origin="created", created=False)

    for raw in name_candidates(title, artist):
        name = fit_directory_name(output_root, raw)
        path = output_root / name
        probe = inspect(path)
        if probe == "missing":
            return DirChoice(path=path, origin="created", created=True)
        if probe == "same":
            return DirChoice(path=path, origin="created", created=False)
        if probe == "no_meta":
            return DirChoice(path=path, origin="external", created=False)
    raise RuntimeError("目录名候选已用尽，无法为该曲目分配歌曲目录")
