"""适配器用假可执行文件覆盖退出码、进度和密钥清理。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from katock.adapters.docker import DockerAdapter
from katock.adapters.downloader import Downloader, classify_download_output, render_config
from katock.adapters.separator import Separator
from katock.domain.failures import AUTH, ENV_NOT_READY, UNAVAILABLE
from katock.domain.status import STEP_PASS1
from tests.conftest import fake_env, install_launcher, make_flac


def test_classify_download_reasons() -> None:
    assert classify_download_output("401 token rejected", 1).kind == AUTH
    assert classify_download_output("not available in this region", 1).kind == UNAVAILABLE
    assert classify_download_output("connection refused on 10020", 1).kind == ENV_NOT_READY


def test_render_config_keeps_folder_and_token(tmp_path: Path) -> None:
    text = render_config("cn", "test-token-value", tmp_path / "work")
    assert 'media-user-token: "test-token-value"' in text
    assert 'storefront: "cn"' in text
    assert "song-file-format" in text
    assert str(tmp_path / "work").replace("\\", "\\\\") in text


def test_downloader_removes_config_and_classifies(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "source.flac"
    make_flac(audio)
    install_launcher(tmp_path, launcher)
    fake_env(monkeypatch, audio)
    monkeypatch.setenv("KATOCK_FAKE_AMD_MODE", "auth")
    work = tmp_path / "job"
    downloader = Downloader(
        tmp_path / "tools" / "amd" / "amd.exe",
        Path(r"D:\ffmpeg\bin"),
        Path(r"D:\GPAC"),
    )
    with pytest.raises(Exception, match="令牌") as caught:
        asyncio.run(
            downloader.download(
                "https://music.apple.com/cn/album/x/1?i=6781027645",
                work,
                "cn",
                "test-token-value",
            )
        )
    assert getattr(caught.value, "kind", "") == AUTH
    assert not (work / "config.yaml").exists()

    monkeypatch.setenv("KATOCK_FAKE_AMD_MODE", "ok")
    produced = asyncio.run(
        downloader.download(
            "https://music.apple.com/cn/album/x/1?i=6781027645",
            work,
            "cn",
            "test-token-value",
        )
    )
    assert produced.name == "6781027645.flac"
    assert produced.stat().st_size > 0
    assert (work / "token-flag.txt").read_text(encoding="utf-8") == "yes"
    assert not (work / "config.yaml").exists()
    leftover = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in work.iterdir()
        if path.suffix in {".txt", ".yaml", ".log"}
    )
    assert "test-token-value" not in leftover


def test_separator_parses_percent_and_writes_wavs(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "source.flac"
    make_flac(audio)
    install_launcher(tmp_path, launcher)
    fake_env(monkeypatch, audio)
    separator = Separator(
        tmp_path / "tools" / "audio-separator" / ".venv" / "Scripts" / "audio-separator.exe",
        tmp_path / "models",
    )
    seen: list[float] = []

    async def on_progress(value: float) -> None:
        seen.append(value)

    produced = asyncio.run(
        separator.separate(audio, "model.ckpt", STEP_PASS1, tmp_path / "out", on_progress)
    )
    assert seen == [40.0, 100.0]
    assert produced["Instrumental"].name == "伴奏.wav"
    assert produced["Vocals"].name == "完整人声.wav"
    assert produced["Instrumental"].stat().st_size > 0


def test_docker_probe_uses_fake_binary(
    tmp_path: Path, launcher: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_env(monkeypatch, tmp_path / "unused.flac")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker.exe").write_bytes(launcher.read_bytes())
    desktop = tmp_path / "Docker Desktop.exe"
    desktop.write_bytes(b"not-a-real-installer")
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    result = DockerAdapter(str(desktop)).probe()
    assert result.ok is True
    assert "29.7.2" in result.detail
