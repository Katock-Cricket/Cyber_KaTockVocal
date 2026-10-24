"""ETA 自学习与队列剩余时间。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from katock.domain.status import (
    POOL_DOWNLOAD,
    POOL_LIGHT,
    POOL_SEPARATION,
    POOL_TRANSLATE,
    STEP_DEPS,
    STEP_POOL,
)

Kind = Literal["point", "range", "cold"]


@dataclass(frozen=True)
class Sample:
    elapsed_s: float
    audio_duration_s: float


@dataclass(frozen=True)
class EtaEstimate:
    kind: Kind
    seconds: float
    low_s: float
    high_s: float
    label: str


@dataclass(frozen=True)
class PendingWork:
    key: str
    step: str
    estimate_s: float
    deps: tuple[str, ...]


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


def estimate_stage(
    samples: list[Sample],
    audio_duration_s: float,
    default_coeff: float,
) -> EtaEstimate:
    """最近 10 个单位耗时的中位数。样本不足 3 个时用默认系数。"""
    duration = max(audio_duration_s, 0.001)
    recent = samples[-10:]
    units = [
        item.elapsed_s / item.audio_duration_s
        for item in recent
        if item.audio_duration_s > 0 and item.elapsed_s >= 0
    ]
    if len(units) < 3:
        seconds = duration * default_coeff
        if not units:
            return EtaEstimate(
                kind="cold",
                seconds=seconds,
                low_s=seconds,
                high_s=seconds,
                label="首次执行，暂用默认估算",
            )
        return EtaEstimate(
            kind="range",
            seconds=seconds,
            low_s=seconds * 0.7,
            high_s=seconds * 1.6,
            label=f"预计剩余 {_format_duration(seconds * 0.7)}~{_format_duration(seconds * 1.6)}",
        )
    ordered = sorted(units)
    median = _percentile(ordered, 0.5)
    low = _percentile(ordered, 0.25)
    high = _percentile(ordered, 0.75)
    seconds = duration * median
    spread = (high - low) / median if median > 0 else 1.0
    if len(units) >= 5 and spread <= 0.25:
        return EtaEstimate(
            kind="point",
            seconds=seconds,
            low_s=seconds,
            high_s=seconds,
            label=f"预计剩余 {_format_duration(seconds)}",
        )
    return EtaEstimate(
        kind="range",
        seconds=seconds,
        low_s=duration * low,
        high_s=duration * high,
        label=(f"预计剩余 {_format_duration(duration * low)}~{_format_duration(duration * high)}"),
    )


def queue_remaining_seconds(items: list[PendingWork], capacities: dict[str, int]) -> float:
    """按依赖与资源池并行度模拟未完成阶段，得到整体剩余秒数。"""
    if not items:
        return 0.0
    finish: dict[str, float] = {}
    pool_slots: dict[str, list[float]] = {}
    pending = {item.key: item for item in items}
    guard = 0
    while pending:
        guard += 1
        if guard > len(items) + 5:
            return sum(item.estimate_s for item in pending.values()) + sum(finish.values())
        ready = [item for item in pending.values() if all(dep not in pending for dep in item.deps)]
        if not ready:
            return sum(finish.values()) + sum(item.estimate_s for item in pending.values())

        def earliest(item: PendingWork) -> float:
            pool = STEP_POOL[item.step]
            capacity = max(1, capacities.get(pool, 1))
            slots = pool_slots.setdefault(pool, [0.0] * capacity)
            dep_ready = max((finish[dep] for dep in item.deps if dep in finish), default=0.0)
            return max(min(slots), dep_ready)

        ready.sort(key=lambda item: (earliest(item), item.key))
        item = ready[0]
        pool = STEP_POOL[item.step]
        capacity = max(1, capacities.get(pool, 1))
        slots = pool_slots.setdefault(pool, [0.0] * capacity)
        dep_ready = max((finish[dep] for dep in item.deps if dep in finish), default=0.0)
        slot_index = min(range(len(slots)), key=lambda index: slots[index])
        start = max(slots[slot_index], dep_ready)
        end = start + max(0.0, item.estimate_s)
        slots[slot_index] = end
        finish[item.key] = end
        del pending[item.key]
    return max(finish.values(), default=0.0)


def default_capacities(separation: int, translate: int) -> dict[str, int]:
    return {
        POOL_DOWNLOAD: 1,
        POOL_SEPARATION: separation,
        POOL_TRANSLATE: translate,
        POOL_LIGHT: 4,
    }


def dependency_keys(job_key: str, step: str) -> tuple[str, ...]:
    return tuple(f"{job_key}:{dep}" for dep in STEP_DEPS[step])
