"""应用日志与单曲结构化日志。"""

from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from katock.security.redact import redact
from katock.storage.db import now_iso

_READY = False


def setup_logging(log_dir: Path) -> None:
    global _READY
    log_dir.mkdir(parents=True, exist_ok=True)
    if _READY:
        return
    handler = TimedRotatingFileHandler(
        log_dir / "app.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("katock")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _READY = True


def logger() -> logging.Logger:
    return logging.getLogger("katock")


def append_job_log(
    log_dir: Path, job_id: str, step: str, level: str, message: str, **extra: Any
) -> None:
    folder = log_dir / "jobs"
    folder.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "time": now_iso(),
        "step": step,
        "level": level,
        "message": redact(message),
    }
    for key, value in extra.items():
        if isinstance(value, str):
            record[key] = redact(value)
        else:
            record[key] = value
    with (folder / f"{job_id}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_job_log(log_dir: Path, job_id: str) -> str:
    path = log_dir / "jobs" / f"{job_id}.jsonl"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")
