"""配置。非敏感项在 var/config.toml，密钥只进 DPAPI。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


def project_root() -> Path:
    env = os.environ.get("KATOCK_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
    return Path.cwd()


class AppConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    output_root: str = r"D:\Videos"
    docker_desktop: str = (
        r"C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
    )
    wrapper_dir: str = r"D:\Download\Wrapper.x86_64.latest"
    gpac_dir: str = r"D:\GPAC"
    ffmpeg_dir: str = r"D:\ffmpeg\bin"
    uvr_dir: str = r"D:\Ultimate Vocal Remover"
    downloader_src: str = r"D:\Download\apple-music-downloader-main"
    storefront: str = "cn"
    separation_concurrency: int = 2
    translate_concurrency: int = 1
    pass1_model: str = "melband_roformer_inst_v2.ckpt"
    pass2_model: str = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
    pass1_yaml: str = "config_melbandroformer_inst_v2.yaml"
    pass2_yaml: str = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml"
    translator_base_url: str = "https://api.chatanywhere.tech/v1"
    translator_model: str = "deepseek-v4.1-flash-1017"
    eta_pass1: float = 1.5
    eta_pass2: float = 1.2
    eta_download_bps: float = 2_000_000
    eta_bytes_per_audio_s: float = 1_500_000
    eta_lyrics_per_line: float = 0.2
    eta_translate_s: float = 12.0
    eta_cover_s: float = 4.0
    eta_finalize_s: float = 2.0
    root: str = Field(default_factory=lambda: str(project_root()))

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("服务只允许绑定 127.0.0.1")
        return value

    @field_validator("separation_concurrency")
    @classmethod
    def _separation_limit(cls, value: int) -> int:
        if value not in (1, 2):
            raise ValueError("分离并发只能是 1 或 2")
        return value

    @field_validator("translate_concurrency")
    @classmethod
    def _translate_limit(cls, value: int) -> int:
        if value not in (1, 2, 3):
            raise ValueError("翻译并发只能是 1 到 3")
        return value

    @property
    def root_path(self) -> Path:
        return Path(self.root)

    @property
    def var_dir(self) -> Path:
        return self.root_path / "var"

    @property
    def db_path(self) -> Path:
        return self.var_dir / "katock.db"

    @property
    def work_dir(self) -> Path:
        return self.var_dir / "work"

    @property
    def models_dir(self) -> Path:
        return self.var_dir / "models"

    @property
    def logs_dir(self) -> Path:
        return self.var_dir / "logs"

    @property
    def config_path(self) -> Path:
        return self.var_dir / "config.toml"

    @property
    def amd_path(self) -> Path:
        return self.root_path / "tools" / "amd" / "amd.exe"

    @property
    def separator_path(self) -> Path:
        return (
            self.root_path
            / "tools"
            / "audio-separator"
            / ".venv"
            / "Scripts"
            / "audio-separator.exe"
        )

    @property
    def ffmpeg_path(self) -> Path:
        return Path(self.ffmpeg_dir) / "ffmpeg.exe"

    @property
    def ffprobe_path(self) -> Path:
        return Path(self.ffmpeg_dir) / "ffprobe.exe"

    @property
    def mp4box_path(self) -> Path:
        return Path(self.gpac_dir) / "mp4box.exe"

    @property
    def uvr_ckpt_dir(self) -> Path:
        return Path(self.uvr_dir) / "models" / "MDX_Net_Models"

    @property
    def uvr_yaml_dir(self) -> Path:
        return self.uvr_ckpt_dir / "model_data" / "mdx_c_configs"


def load_config(root: Path | None = None) -> AppConfig:
    base = root or project_root()
    path = base / "var" / "config.toml"
    data: dict[str, object] = {"root": str(base)}
    if path.is_file():
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        data.update(loaded)
        data["root"] = str(base)
    return AppConfig.model_validate(data)


def dump_config(config: AppConfig) -> str:
    fields = [
        "host",
        "port",
        "output_root",
        "docker_desktop",
        "wrapper_dir",
        "gpac_dir",
        "ffmpeg_dir",
        "uvr_dir",
        "downloader_src",
        "storefront",
        "separation_concurrency",
        "translate_concurrency",
        "pass1_model",
        "pass2_model",
        "pass1_yaml",
        "pass2_yaml",
        "translator_base_url",
        "translator_model",
        "eta_pass1",
        "eta_pass2",
        "eta_download_bps",
        "eta_bytes_per_audio_s",
        "eta_lyrics_per_line",
        "eta_translate_s",
        "eta_cover_s",
        "eta_finalize_s",
    ]
    lines = [
        "# Cyber_KaTockVocal 本机配置。密钥不写在这里。",
        "",
    ]
    payload = config.model_dump()
    for name in fields:
        value = payload[name]
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{name} = "{escaped}"')
        elif isinstance(value, float):
            lines.append(f"{name} = {value}")
        else:
            lines.append(f"{name} = {value}")
    lines.append("")
    return "\n".join(lines)


def save_config(config: AppConfig) -> None:
    config.var_dir.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(dump_config(config), encoding="utf-8")


def ensure_config(root: Path | None = None) -> AppConfig:
    config = load_config(root)
    config.var_dir.mkdir(parents=True, exist_ok=True)
    config.work_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    (config.logs_dir / "jobs").mkdir(parents=True, exist_ok=True)
    config.models_dir.mkdir(parents=True, exist_ok=True)
    if not config.config_path.is_file():
        save_config(config)
    return config
