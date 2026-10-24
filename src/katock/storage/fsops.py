"""歌曲目录写盘。只允许交付物、状态文件和备份目录。"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from katock.domain.stems import ALLOWED_NAMES

BACKUP_PREFIX = "_backup_"


class FsOpsError(Exception):
    pass


def assert_allowed(name: str) -> None:
    if name not in ALLOWED_NAMES:
        raise FsOpsError(f"拒绝写入歌曲目录中的非交付物：{name}")


def file_ready(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def backup_existing(song_dir: Path, name: str) -> Path | None:
    assert_allowed(name)
    target = song_dir / name
    if not target.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = song_dir / f"{BACKUP_PREFIX}{stamp}"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / name
    if destination.exists():
        destination = folder / f"{target.stem}_{stamp}{target.suffix}"
    shutil.move(str(target), str(destination))
    return destination


def publish(
    work_file: Path,
    song_dir: Path,
    name: str,
    *,
    origin: str,
) -> str:
    """把工作目录里的完整文件原子移动到歌曲目录。

    返回 placed / kept / missing。
    """
    assert_allowed(name)
    song_dir.mkdir(parents=True, exist_ok=True)
    target = song_dir / name
    if origin == "external" and target.exists():
        return "kept"
    if not work_file.is_file() or work_file.stat().st_size <= 0:
        return "missing"
    if target.exists():
        backup_existing(song_dir, name)
    os.replace(work_file, target)
    return "placed"


def same_volume(left: Path, right: Path) -> bool:
    left_drive = left.anchor.lower()
    right_drive = right.anchor.lower()
    if left_drive and right_drive:
        return left_drive == right_drive
    return True
