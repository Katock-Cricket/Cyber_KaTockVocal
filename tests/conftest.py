"""测试共用夹具。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from katock.config import AppConfig

ROOT = Path(__file__).resolve().parents[1]
FAKES = ROOT / "tests" / "fakes"
LAUNCHER = FAKES / "launcher.exe"
FFMPEG_DIR = Path(r"D:\ffmpeg\bin")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: 需要本机服务或外网")
    config.addinivalue_line("markers", "slow: 需要 GPU 与分离模型")


@pytest.fixture(scope="session")
def launcher() -> Path:
    if not LAUNCHER.is_file():
        subprocess.run(
            ["go", "build", "-o", str(LAUNCHER), "."],
            cwd=FAKES / "launcher",
            check=True,
        )
    return LAUNCHER


def install_launcher(root: Path, launcher: Path) -> None:
    targets = [
        root / "tools" / "amd" / "amd.exe",
        root / "tools" / "audio-separator" / ".venv" / "Scripts" / "audio-separator.exe",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(launcher, target)


def make_config(root: Path) -> AppConfig:
    return AppConfig(
        root=str(root),
        output_root=str(root / "videos"),
        ffmpeg_dir=str(FFMPEG_DIR),
        gpac_dir=r"D:\GPAC",
        docker_desktop=str(root / "Docker Desktop.exe"),
    )


def make_flac(path: Path, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(FFMPEG_DIR / "ffmpeg.exe"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={seconds}",
            "-ac",
            "2",
            "-c:a",
            "flac",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(FFMPEG_DIR / "ffmpeg.exe"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def fake_env(monkeypatch: pytest.MonkeyPatch, audio: Path) -> None:
    monkeypatch.setenv("KATOCK_FAKE_PY", sys.executable)
    monkeypatch.setenv("KATOCK_FAKE_AMD", str(FAKES / "amd.py"))
    monkeypatch.setenv("KATOCK_FAKE_SEP", str(FAKES / "separator.py"))
    monkeypatch.setenv("KATOCK_FAKE_DOCKER", str(FAKES / "docker.py"))
    monkeypatch.setenv("KATOCK_FAKE_FFMPEG", str(FFMPEG_DIR / "ffmpeg.exe"))
    monkeypatch.setenv("KATOCK_FAKE_AUDIO", str(audio))
    monkeypatch.setenv("KATOCK_FAKE_TOKEN", "test-token-value")
    monkeypatch.setenv("KATOCK_FAKE_AMD_MODE", "ok")
