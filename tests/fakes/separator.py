"""假分离器。把输入转成调用方要求的 44100 Hz WAV，并打印百分比。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    source = Path(args[0])
    output_dir = Path.cwd()
    names: dict[str, str] = {}
    index = 1
    while index < len(args):
        flag = args[index]
        if flag in {"--output_dir", "--custom_output_names"} and index + 1 < len(args):
            value = args[index + 1]
            if flag == "--output_dir":
                output_dir = Path(value)
            else:
                loaded = json.loads(value)
                if isinstance(loaded, dict):
                    names = {str(key): str(item) for key, item in loaded.items()}
            index += 2
            continue
        index += 1
    print("progress 40%", file=sys.stderr, flush=True)
    print("progress 100%", file=sys.stderr, flush=True)
    ffmpeg = os.environ["KATOCK_FAKE_FFMPEG"]
    output_dir.mkdir(parents=True, exist_ok=True)
    for stem_name in names.values():
        target = output_dir / f"{stem_name}.wav"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-ac",
                "2",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
