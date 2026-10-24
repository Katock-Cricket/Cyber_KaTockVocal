"""调用 audio-separator，并按附录 A 接收产物。"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from katock.adapters.proc import run_cmd, stream_cmd
from katock.domain.failures import SEPARATION, suggestion
from katock.domain.stems import output_names

_PERCENT = re.compile(r"(?<!\d)(\d{1,3})%")


class SeparationError(Exception):
    def __init__(self, summary: str, detail: str = "") -> None:
        super().__init__(summary)
        self.kind = SEPARATION
        self.summary = summary
        self.suggestion = suggestion(SEPARATION)
        self.detail = detail


class Separator:
    def __init__(self, executable: Path, model_dir: Path) -> None:
        self.executable = executable
        self.model_dir = model_dir

    def version(self) -> str:
        if not self.executable.is_file():
            raise SeparationError(f"找不到分离工具：{self.executable}")
        result = run_cmd([str(self.executable), "--version"], timeout=30)
        if result.code != 0:
            raise SeparationError("audio-separator --version 失败", result.text[:400])
        return result.stdout.strip() or result.stderr.strip()

    def models_present(self, filenames: list[str]) -> list[str]:
        missing = [name for name in filenames if not (self.model_dir / name).exists()]
        return missing

    async def separate(
        self,
        source: Path,
        model_filename: str,
        step: str,
        output_dir: Path,
        on_progress: Callable[[float], Awaitable[None]] | None = None,
    ) -> dict[str, Path]:
        if not self.executable.is_file():
            raise SeparationError(f"找不到分离工具：{self.executable}")
        output_dir.mkdir(parents=True, exist_ok=True)
        names = output_names(step)
        args = [
            str(self.executable),
            str(source),
            "--model_filename",
            model_filename,
            "--model_file_dir",
            str(self.model_dir),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "WAV",
            "--sample_rate",
            "44100",
            "--normalization",
            "1",
            "--amplification",
            "0",
            "--custom_output_names",
            json.dumps(names, ensure_ascii=False),
        ]
        seen_real = False

        async def on_line(line: str) -> None:
            nonlocal seen_real
            match = _PERCENT.search(line)
            if match and on_progress is not None:
                seen_real = True
                await on_progress(float(match.group(1)))

        result = await stream_cmd(args, cwd=output_dir, on_line=on_line, timeout=3600)
        if result.code != 0:
            raise SeparationError("分离进程失败", (result.stderr or result.stdout)[-800:])
        produced: dict[str, Path] = {}
        for stem, stem_name in names.items():
            path = output_dir / f"{stem_name}.wav"
            if not path.is_file():
                raise SeparationError(
                    f"分离结果缺少 {stem_name}.wav（{stem}）", result.stderr[-400:]
                )
            produced[stem] = path
        if on_progress is not None and not seen_real:
            await on_progress(-1)
        return produced
