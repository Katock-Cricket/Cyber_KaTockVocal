"""曲名里的版本关键词，用于候选列表高亮。"""

from __future__ import annotations

import re

_KEYWORDS = ("Live", "Remix", "Acoustic", "Instrumental", "Demo")
_PATTERN = re.compile(r"\b(" + "|".join(_KEYWORDS) + r")\b", re.IGNORECASE)


def version_tags(title: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(title):
        label = match.group(1)
        canonical = next(item for item in _KEYWORDS if item.lower() == label.lower())
        if canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    return found
