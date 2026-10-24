"""日志脱敏。"""

from __future__ import annotations

import re

_SECRET_ASSIGN = re.compile(
    r"(?i)(api[_-]?key|media-user-token|authorization|password|passwd|token|bearer)"
    r"(\s*[:=]\s*[\"']?)([^\s\"']+)"
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def redact(text: str, secrets: list[str] | None = None) -> str:
    cleaned = _SECRET_ASSIGN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", text)
    cleaned = _JWT.sub("***", cleaned)
    for secret in secrets or []:
        if secret and len(secret) >= 6:
            cleaned = cleaned.replace(secret, "***")
    return cleaned
