"""歌词语种判定。中文语系只保留原文。"""

from __future__ import annotations

_CHINESE_PREFIXES = ("zh", "yue")


def _is_han(char: str) -> bool:
    code = ord(char)
    return 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF


def han_ratio(text: str) -> float:
    meaningful = [char for char in text if not char.isspace()]
    if not meaningful:
        return 0.0
    han = sum(1 for char in meaningful if _is_han(char))
    return han / len(meaningful)


def is_chinese_family(language: str | None, text: str) -> bool:
    if language:
        lowered = language.strip().lower().replace("_", "-")
        return any(
            lowered == prefix or lowered.startswith(prefix + "-") for prefix in _CHINESE_PREFIXES
        )
    return han_ratio(text) >= 0.30


def needs_translation(language: str | None, text: str) -> bool:
    return not is_chinese_family(language, text)
