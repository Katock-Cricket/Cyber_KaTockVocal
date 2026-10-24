"""逐句歌词到 LRC / SRT。原文原样保留。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class LyricLine:
    text: str
    start_ms: int | None


@dataclass(frozen=True)
class LyricDocument:
    lines: tuple[LyricLine, ...]
    language: str | None
    timed: bool


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(element: ET.Element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def parse_timecode(value: str) -> int:
    text = value.strip()
    if text.endswith("s") and ":" not in text:
        return max(0, int(round(float(text[:-1]) * 1000)))
    parts = text.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        total = int(minutes) * 60 + float(seconds)
    else:
        total = float(text)
    return max(0, int(round(total * 1000)))


def parse_ttml(ttml: str) -> LyricDocument:
    text = ttml
    if "itunes:" in text and "xmlns:itunes" not in text:
        text = text.replace(
            "<tt",
            '<tt xmlns:itunes="http://music.apple.com/lyric-ttml-internal"',
            1,
        )
    root = ET.fromstring(text)
    language = _attr(root, "lang")
    timing = (_attr(root, "timing") or "").lower()
    lines: list[LyricLine] = []
    for element in root.iter():
        if _local(element.tag) != "p":
            continue
        text = "".join(element.itertext()).strip()
        if not text:
            continue
        begin = _attr(element, "begin")
        start = parse_timecode(begin) if begin else None
        lines.append(LyricLine(text=text, start_ms=start))
    timed = timing != "none" and any(line.start_ms is not None for line in lines)
    if not timed:
        lines = [LyricLine(text=line.text, start_ms=None) for line in lines]
    return LyricDocument(lines=tuple(lines), language=language, timed=timed)


def _lrc_stamp(ms: int | None) -> str:
    value = 0 if ms is None else max(0, ms)
    centiseconds = value // 10
    seconds, cs = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    return f"[{minutes:02d}:{seconds:02d}.{cs:02d}]"


def _srt_stamp(ms: int) -> str:
    value = max(0, ms)
    hours, rem = divmod(value, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _end_ms(lines: tuple[LyricLine, ...], index: int) -> int:
    current = lines[index].start_ms
    start = 0 if current is None else current
    for follower in lines[index + 1 :]:
        begin = follower.start_ms
        if begin is not None and begin > start:
            return begin
    return start + 4000


def render_lrc(lines: tuple[LyricLine, ...], translations: tuple[str, ...] | None = None) -> str:
    _require_translation_count(lines, translations)
    rows: list[str] = []
    for index, line in enumerate(lines):
        stamp = _lrc_stamp(line.start_ms)
        rows.append(f"{stamp}{line.text}")
        if translations is not None:
            rows.append(f"{stamp}{translations[index]}")
    return "\n".join(rows) + ("\n" if rows else "")


def render_srt(lines: tuple[LyricLine, ...], translations: tuple[str, ...] | None = None) -> str:
    _require_translation_count(lines, translations)
    blocks: list[str] = []
    for index, line in enumerate(lines):
        start = 0 if line.start_ms is None else line.start_ms
        end = max(_end_ms(lines, index), start + 1)
        body = line.text if translations is None else f"{line.text}\n{translations[index]}"
        blocks.append(f"{index + 1}\n{_srt_stamp(start)} --> {_srt_stamp(end)}\n{body}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _require_translation_count(
    lines: tuple[LyricLine, ...], translations: tuple[str, ...] | None
) -> None:
    if translations is not None and len(translations) != len(lines):
        raise ValueError("译文句数与原文不一致")
