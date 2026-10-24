"""本机 amd.exe 下载单曲到工作目录。"""

from __future__ import annotations

import os
from pathlib import Path

from katock.adapters.proc import stream_cmd
from katock.domain.failures import AUTH, ENV_NOT_READY, UNAVAILABLE, suggestion


class DownloadError(Exception):
    def __init__(self, kind: str, summary: str, detail: str = "") -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary
        self.suggestion = suggestion(kind)
        self.detail = detail


def render_config(storefront: str, media_token: str, save_dir: Path) -> str:
    token = media_token.replace('"', "")
    folder = str(save_dir).replace("\\", "\\\\")
    return "\n".join(
        [
            f'media-user-token: "{token}"',
            'authorization-token: ""',
            'language: ""',
            'lrc-type: "lyrics"',
            'lrc-format: "lrc"',
            "embed-lrc: false",
            "save-lrc-file: false",
            "save-artist-cover: false",
            "save-animated-artwork: false",
            "embed-cover: false",
            "cover-size: 3000x3000",
            "cover-format: jpg",
            f'alac-save-folder: "{folder}"',
            f'atmos-save-folder: "{folder}"',
            f'aac-save-folder: "{folder}"',
            "max-memory-limit: 256",
            'decrypt-m3u8-port: "127.0.0.1:10020"',
            'get-m3u8-port: "127.0.0.1:20020"',
            "get-m3u8-from-device: true",
            "exit-on-error: true",
            "get-m3u8-mode: hires",
            "aac-type: aac",
            "alac-max: 192000",
            "atmos-max: 2768",
            "limit-max: 80",
            'album-folder-format: ""',
            'playlist-folder-format: ""',
            'song-file-format: "{SongId}"',
            'artist-folder-format: ""',
            'explicit-choice: ""',
            'clean-choice: ""',
            'apple-master-choice: ""',
            "use-songinfo-for-playlist: false",
            "dl-albumcover-for-playlist: false",
            f'storefront: "{storefront}"',
            "convert-after-download: false",
            "",
        ]
    )


def classify_download_output(text: str, code: int) -> DownloadError:
    lowered = text.lower()
    if "token" in lowered or "unauthorized" in lowered or "login" in lowered or "401" in lowered:
        return DownloadError(AUTH, "下载被账号或令牌拒绝", text[-500:])
    if (
        "unavailable" in lowered
        or "not available" in lowered
        or "region" in lowered
        or "failed to get manifest" in lowered
    ):
        return DownloadError(UNAVAILABLE, "该曲目在当前地区不可获取", text[-500:])
    if "connection refused" in lowered or "10020" in lowered or "docker" in lowered:
        return DownloadError(ENV_NOT_READY, "Wrapper 或 Docker 未就绪", text[-500:])
    summary = "下载失败" if code else "下载结束但没有得到音频文件"
    return DownloadError(ENV_NOT_READY if code else UNAVAILABLE, summary, text[-500:])


class Downloader:
    def __init__(self, executable: Path, ffmpeg_dir: Path, gpac_dir: Path) -> None:
        self.executable = executable
        self.ffmpeg_dir = ffmpeg_dir
        self.gpac_dir = gpac_dir

    async def download(self, url: str, work_dir: Path, storefront: str, media_token: str) -> Path:
        if not self.executable.is_file():
            raise DownloadError(ENV_NOT_READY, f"找不到下载器：{self.executable}")
        work_dir.mkdir(parents=True, exist_ok=True)
        config_path = work_dir / "config.yaml"
        config_path.write_text(
            render_config(storefront, media_token, work_dir),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PATH"] = (
            str(self.gpac_dir)
            + os.pathsep
            + str(self.ffmpeg_dir)
            + os.pathsep
            + env.get("PATH", "")
        )
        try:
            result = await stream_cmd(
                [str(self.executable), "--song", url],
                cwd=work_dir,
                env=env,
                timeout=1200,
            )
        finally:
            if config_path.exists():
                config_path.unlink()
        files = [
            path for path in work_dir.rglob("*.m4a") if path.is_file() and path.stat().st_size > 0
        ]
        files.extend(
            path for path in work_dir.rglob("*.flac") if path.is_file() and path.stat().st_size > 0
        )
        if result.code != 0 or not files:
            raise classify_download_output(result.text, result.code)
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[0]
