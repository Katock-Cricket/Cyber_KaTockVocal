"""假下载器。由 launcher.exe 拉起，用来模拟退出码和产物。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    mode = os.environ.get("KATOCK_FAKE_AMD_MODE", "ok")
    if mode == "auth":
        print("401 unauthorized token", file=sys.stderr)
        sys.exit(1)
    if mode == "unavailable":
        print("track not available in this region", file=sys.stderr)
        sys.exit(1)
    if mode == "docker":
        print("connection refused 10020", file=sys.stderr)
        sys.exit(1)
    token = os.environ.get("KATOCK_FAKE_TOKEN", "")
    config = Path("config.yaml")
    present = config.is_file() and token and token in config.read_text(encoding="utf-8")
    Path("token-flag.txt").write_text("yes" if present else "no", encoding="utf-8")
    source = Path(os.environ["KATOCK_FAKE_AUDIO"])
    shutil.copyfile(source, Path("6781027645.flac"))


if __name__ == "__main__":
    main()
