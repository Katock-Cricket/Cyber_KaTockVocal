"""模型输出到业务文件的映射。只按 PRD 附录 A。"""

from __future__ import annotations

from katock.domain.status import STEP_PASS1, STEP_PASS2

FILE_INSTRUMENTAL = "伴奏.wav"
FILE_LEAD = "主音.wav"
FILE_HARMONY = "和声.wav"
FILE_COVER = "封面.jpg"
FILE_LRC = "歌词.lrc"
FILE_SRT = "歌词.srt"
FILE_META = ".ktvmeta.json"
FILE_FULL_VOCAL = "完整人声.wav"

DELIVERABLE_FILES = (
    FILE_INSTRUMENTAL,
    FILE_LEAD,
    FILE_HARMONY,
    FILE_COVER,
    FILE_LRC,
    FILE_SRT,
)

ALLOWED_NAMES = frozenset(DELIVERABLE_FILES) | {FILE_META}

STEM_VOCALS = "Vocals"
STEM_INSTRUMENTAL = "Instrumental"

PASS1_MODEL = "melband_roformer_inst_v2"
PASS2_MODEL = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956"
PASS1_CKPT = f"{PASS1_MODEL}.ckpt"
PASS2_CKPT = f"{PASS2_MODEL}.ckpt"
PASS1_YAML = "config_melbandroformer_inst_v2.yaml"
PASS2_YAML = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml"
PASS2_YAML_SOURCE = "config_mel_band_roformer_karaoke.yaml"

# 分离工具自定义输出名（不含扩展名）。落盘前仍停在工作目录。
PASS_OUTPUT_NAMES: dict[str, dict[str, str]] = {
    STEP_PASS1: {
        STEM_INSTRUMENTAL: "伴奏",
        STEM_VOCALS: "完整人声",
    },
    STEP_PASS2: {
        STEM_VOCALS: "主音",
        STEM_INSTRUMENTAL: "和声",
    },
}

PASS_DELIVERABLES: dict[str, tuple[str, ...]] = {
    STEP_PASS1: (FILE_INSTRUMENTAL,),
    STEP_PASS2: (FILE_LEAD, FILE_HARMONY),
}


def output_names(step: str) -> dict[str, str]:
    if step not in PASS_OUTPUT_NAMES:
        raise ValueError(f"未知分离阶段: {step}")
    return dict(PASS_OUTPUT_NAMES[step])
