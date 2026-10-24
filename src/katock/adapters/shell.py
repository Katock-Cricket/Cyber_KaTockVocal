"""打开歌曲目录。"""

from __future__ import annotations

import os
from pathlib import Path


def open_folder(path: Path) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"歌曲目录不存在：{path}")
    os.startfile(path)
