"""Windows DPAPI。明文只活在进程内存里。"""

from __future__ import annotations

import win32crypt


def protect(text: str) -> bytes:
    blob = win32crypt.CryptProtectData(text.encode("utf-8"), "katock", None, None, None, 0)
    if isinstance(blob, bytes):
        return blob
    return bytes(blob)


def unprotect(blob: bytes) -> str:
    result = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    data = result[1]
    if isinstance(data, str):
        return data
    return bytes(data).decode("utf-8")
