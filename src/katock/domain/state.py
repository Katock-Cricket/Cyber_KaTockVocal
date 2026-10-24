"""任务状态机。非法迁移直接拒绝。"""

from __future__ import annotations

from katock.domain.status import (
    JOB_CANCELLED,
    JOB_DONE,
    JOB_FAILED,
    JOB_INTERRUPTED,
    JOB_PARTIAL,
    JOB_QUEUED,
    JOB_RUNNING,
)

Action = str

ENQUEUE = "enqueue"
DISPATCH = "dispatch"
SUCCESS = "success"
PARTIAL = "partial"
CRITICAL_FAIL = "critical_fail"
CANCEL = "cancel"
CRASH = "crash"
RECOVER = "recover"
RERUN = "rerun"

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("", ENQUEUE): JOB_QUEUED,
    (JOB_QUEUED, DISPATCH): JOB_RUNNING,
    (JOB_RUNNING, SUCCESS): JOB_DONE,
    (JOB_RUNNING, PARTIAL): JOB_PARTIAL,
    (JOB_RUNNING, CRITICAL_FAIL): JOB_FAILED,
    (JOB_RUNNING, CANCEL): JOB_CANCELLED,
    (JOB_RUNNING, CRASH): JOB_INTERRUPTED,
    (JOB_INTERRUPTED, RECOVER): JOB_QUEUED,
    (JOB_DONE, RERUN): JOB_QUEUED,
    (JOB_PARTIAL, RERUN): JOB_QUEUED,
    (JOB_FAILED, RERUN): JOB_QUEUED,
    (JOB_CANCELLED, RERUN): JOB_QUEUED,
    (JOB_QUEUED, CANCEL): JOB_CANCELLED,
}


class InvalidTransition(Exception):
    def __init__(self, current: str, action: str) -> None:
        super().__init__(f"不能从「{current or '空'}」执行「{action}」")
        self.current = current
        self.action = action


def transit(current: str, action: str) -> str:
    key = (current, action)
    if key not in _TRANSITIONS:
        raise InvalidTransition(current, action)
    return _TRANSITIONS[key]
