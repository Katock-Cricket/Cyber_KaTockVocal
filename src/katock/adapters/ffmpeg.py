"""ffmpeg / ffprobe：转码、标签、校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from katock.adapters.proc import run_cmd
from katock.domain.failures import UNKNOWN, suggestion


class AudioError(Exception):
    def __init__(self, summary: str, detail: str = "") -> None:
        super().__init__(summary)
        self.kind = UNKNOWN
        self.summary = summary
        self.suggestion = suggestion(UNKNOWN)
        self.detail = detail


@dataclass(frozen=True)
class Probe:
    duration_s: float
    sample_rate: int
    channels: int
    bit_depth: int
    codec: str


class Ffmpeg:
    def __init__(self, ffmpeg: Path, ffprobe: Path) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def version(self) -> str:
        if not self.ffmpeg.is_file() or not self.ffprobe.is_file():
            raise AudioError(f"找不到 ffmpeg 或 ffprobe：{self.ffmpeg.parent}")
        result = run_cmd([str(self.ffmpeg), "-version"], timeout=10)
        if result.code != 0:
            raise AudioError("ffmpeg -version 失败", result.text[:300])
        return result.stdout.splitlines()[0] if result.stdout else "ffmpeg"

    def probe(self, path: Path) -> Probe:
        if not self.ffprobe.is_file():
            raise AudioError(f"找不到 ffprobe：{self.ffprobe}")
        result = run_cmd(
            [
                str(self.ffprobe),
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            timeout=30,
        )
        if result.code != 0:
            raise AudioError(f"ffprobe 无法解析 {path.name}", result.text[:400])
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams") or []
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if not isinstance(audio, dict):
            raise AudioError(f"{path.name} 里没有音频流")
        format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
        duration = float(format_info.get("duration") or audio.get("duration") or 0)
        bit_depth = int(audio.get("bits_per_raw_sample") or 0)
        if bit_depth <= 0:
            sample_fmt = str(audio.get("sample_fmt") or "")
            if sample_fmt.startswith("s16"):
                bit_depth = 16
            elif sample_fmt.startswith("s32") or sample_fmt.startswith("flt"):
                bit_depth = 32
        return Probe(
            duration_s=duration,
            sample_rate=int(audio.get("sample_rate") or 0),
            channels=int(audio.get("channels") or 0),
            bit_depth=bit_depth,
            codec=str(audio.get("codec_name") or ""),
        )

    def decode_ok(self, path: Path, timeout: float = 180) -> None:
        result = run_cmd(
            [str(self.ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"],
            timeout=timeout,
        )
        if result.code != 0:
            raise AudioError(f"{path.name} 无法完整解码", result.text[:400])

    def to_flac(self, source: Path, target: Path) -> None:
        if not self.ffmpeg.is_file():
            raise AudioError(f"找不到 ffmpeg：{self.ffmpeg}")
        target.parent.mkdir(parents=True, exist_ok=True)
        result = run_cmd(
            [str(self.ffmpeg), "-y", "-i", str(source), "-c:a", "flac", str(target)],
            timeout=600,
        )
        if result.code != 0 or not target.is_file():
            raise AudioError("ALAC 转 FLAC 失败", result.text[:400])

    def tag_flac(
        self,
        source: Path,
        target: Path,
        tags: dict[str, str],
        cover: Path | None = None,
    ) -> None:
        args = [str(self.ffmpeg), "-y", "-i", str(source)]
        if cover and cover.is_file():
            args.extend(["-i", str(cover), "-map", "0:a", "-map", "1:0", "-c:v", "mjpeg"])
            args.extend(["-disposition:v:0", "attached_pic"])
        else:
            args.extend(["-map", "0:a"])
        args.extend(["-c:a", "copy"])
        for key, value in tags.items():
            args.extend(["-metadata", f"{key}={value}"])
        args.append(str(target))
        result = run_cmd(args, timeout=180)
        if result.code != 0 or not target.is_file():
            raise AudioError("写入 FLAC 元数据失败", result.text[:400])

    def to_pcm16(self, source: Path, target: Path, resample: bool) -> None:
        args = [str(self.ffmpeg), "-y", "-i", str(source)]
        if resample:
            args.extend(["-ar", "44100", "-ac", "2"])
        args.extend(["-c:a", "pcm_s16le", str(target)])
        result = run_cmd(args, timeout=600)
        if result.code != 0 or not target.is_file():
            raise AudioError("WAV 转为 16 bit 失败", result.text[:400])


def wav_matches(probe: Probe) -> bool:
    return probe.sample_rate == 44100 and probe.channels == 2 and probe.bit_depth == 16
