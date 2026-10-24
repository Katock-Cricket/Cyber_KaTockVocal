"""真实 GPU 分离。默认跳过，设置 KATOCK_GPU=1 后执行。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from katock.adapters.ffmpeg import Ffmpeg, wav_matches
from katock.adapters.separator import Separator
from katock.domain.status import STEP_PASS1, STEP_PASS2
from tests.conftest import FFMPEG_DIR, ROOT, make_flac


@pytest.mark.slow
def test_real_separator_writes_44100_stereo(tmp_path: Path) -> None:
    if os.environ.get("KATOCK_GPU") != "1":
        pytest.skip("设置 KATOCK_GPU=1 后才跑真实分离")
    executable = ROOT / "tools" / "audio-separator" / ".venv" / "Scripts" / "audio-separator.exe"
    models = ROOT / "var" / "models"
    if not executable.is_file():
        pytest.skip("分离工具未安装")
    source = tmp_path / "tone.flac"
    make_flac(source, 1.0)
    ffmpeg = Ffmpeg(FFMPEG_DIR / "ffmpeg.exe", FFMPEG_DIR / "ffprobe.exe")
    original = ffmpeg.probe(source)
    separator = Separator(executable, models)
    seen: list[float] = []

    async def on_progress(value: float) -> None:
        seen.append(value)

    async def run() -> None:
        for step in (STEP_PASS1, STEP_PASS2):
            model = (
                "melband_roformer_inst_v2.ckpt"
                if step == STEP_PASS1
                else "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
            )
            produced = await separator.separate(
                source, model, step, tmp_path / step, on_progress
            )
            for path in produced.values():
                probe = ffmpeg.probe(path)
                assert wav_matches(probe)
                assert abs(probe.duration_s - original.duration_s) <= 0.05

    asyncio.run(run())
    assert seen
    assert all(value == -1 or 0 <= value <= 100 for value in seen)
