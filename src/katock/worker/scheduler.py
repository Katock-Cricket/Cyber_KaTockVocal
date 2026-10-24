"""队列调度。每秒看一次指令、配额和阶段依赖。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from katock.config import AppConfig, load_config
from katock.domain.eta import (
    PendingWork,
    default_capacities,
    dependency_keys,
    queue_remaining_seconds,
)
from katock.domain.failures import UNKNOWN
from katock.domain.status import (
    CRITICAL_STEPS,
    JOB_QUEUED,
    JOB_RUNNING,
    STEP_DEPS,
    STEP_FINISHED,
    STEP_LYRICS,
    STEP_ORDER,
    STEP_POOL,
    STEP_RUNNING,
)
from katock.logging_setup import append_job_log, setup_logging
from katock.storage.db import session
from katock.storage.repo import (
    emit_event,
    list_jobs,
    purge_old_events,
    queue_paused,
    runnable_jobs,
    set_queue_paused,
    steps_for,
    take_commands,
    update_job,
    update_step,
)
from katock.worker.execute import StepFailed, execute_step, fail_job, predict_seconds

_TICK = 0


async def serve(config: AppConfig) -> None:
    setup_logging(config.logs_dir)
    _recover(config)
    stop = asyncio.Event()
    tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
    modes: dict[str, str] = {}
    batch = False
    seen: set[str] = set()
    while not stop.is_set():
        current = load_config(config.root_path)
        _handle_commands(current, tasks, modes, stop)
        if not queue_paused_now(current):
            _dispatch(current, tasks, modes)
        _tick_estimates(current)
        batch, seen = _maybe_notify(current, batch, seen)
        global _TICK
        _TICK += 1
        if _TICK % 3600 == 0:
            with session(current.db_path) as conn:
                purge_old_events(conn)
        await asyncio.sleep(1)
    for task in tasks.values():
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks.values(), return_exceptions=True)


def queue_paused_now(config: AppConfig) -> bool:
    with session(config.db_path) as conn:
        return queue_paused(conn)


def _recover(config: AppConfig) -> None:
    with session(config.db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status IN ('running', 'interrupted')"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE steps SET status = 'pending', progress_estimated = 0 "
                "WHERE job_id = ? AND status IN ('running', 'waiting_env', 'interrupted')",
                (row["id"],),
            )
            update_job(conn, row["id"], status=JOB_QUEUED)
            emit_event(conn, "job", {"status": JOB_QUEUED, "recovered": True}, row["id"])


def _handle_commands(
    config: AppConfig,
    tasks: dict[tuple[str, str], asyncio.Task[None]],
    modes: dict[str, str],
    stop: asyncio.Event,
) -> None:
    with session(config.db_path) as conn:
        commands = take_commands(conn)
    for command in commands:
        kind = str(command["kind"])
        payload = command["payload"] if isinstance(command["payload"], dict) else {}
        if kind == "pause":
            with session(config.db_path) as conn:
                set_queue_paused(conn, True)
            _stop_running(tasks, modes, "pause")
        elif kind == "resume":
            with session(config.db_path) as conn:
                set_queue_paused(conn, False)
        elif kind == "cancel":
            job_id = str(payload.get("jobId") or "")
            modes[job_id] = "cancel"
            for (running_job, _step), task in tasks.items():
                if running_job == job_id:
                    task.cancel()
            if not any(running_job == job_id for running_job, _step in tasks):
                with session(config.db_path) as conn:
                    update_job(conn, job_id, status="cancelled")
                    conn.execute(
                        "UPDATE steps SET status = 'cancelled' "
                        "WHERE job_id = ? AND status = 'pending'",
                        (job_id,),
                    )
        elif kind == "shutdown":
            _stop_running(tasks, modes, "shutdown")
            stop.set()


def _stop_running(
    tasks: dict[tuple[str, str], asyncio.Task[None]],
    modes: dict[str, str],
    mode: str,
) -> None:
    for job_id, _step in tasks:
        modes[job_id] = mode
    for task in tasks.values():
        task.cancel()


def _dispatch(
    config: AppConfig, tasks: dict[tuple[str, str], asyncio.Task[None]], modes: dict[str, str]
) -> None:
    with session(config.db_path) as conn:
        jobs = runnable_jobs(conn)
        step_map = {str(job["id"]): steps_for(conn, str(job["id"])) for job in jobs}
    capacities = default_capacities(config.separation_concurrency, config.translate_concurrency)
    for job in jobs:
        job_id = str(job["id"])
        if not job.get("dir_path"):
            fail_job(config, config.db_path, job, "歌曲目录还没有准备好", UNKNOWN, "download")
            continue
        statuses = {str(item["name"]): str(item["status"]) for item in step_map.get(job_id, [])}
        if job["status"] == JOB_QUEUED and any(key[0] == job_id for key in tasks):
            with session(config.db_path) as conn:
                update_job(conn, job_id, status=JOB_RUNNING)
        for step in STEP_ORDER:
            if (job_id, step) in tasks or statuses.get(step) not in {"pending", "waiting_env"}:
                continue
            if not _deps_ready(step, statuses):
                continue
            pool = STEP_POOL[step]
            used = sum(1 for key in tasks if STEP_POOL[key[1]] == pool)
            if used >= capacities.get(pool, 1):
                continue
            if step == STEP_LYRICS:
                lyrics_used = sum(1 for key in tasks if key[1] == STEP_LYRICS)
                if lyrics_used >= config.translate_concurrency:
                    continue
            if job["status"] == JOB_QUEUED:
                with session(config.db_path) as conn:
                    update_job(conn, job_id, status=JOB_RUNNING)
                job["status"] = JOB_RUNNING
            tasks[(job_id, step)] = asyncio.create_task(_guard(config, job, step, tasks, modes))
            statuses[step] = STEP_RUNNING


def _deps_ready(step: str, statuses: dict[str, str]) -> bool:
    for dep in STEP_DEPS[step]:
        state = statuses.get(dep, "pending")
        if state not in STEP_FINISHED:
            return False
        if state == "failed" and dep in CRITICAL_STEPS:
            return False
        if state == "cancelled":
            return False
    return True


async def _guard(
    config: AppConfig,
    job: dict[str, Any],
    step: str,
    tasks: dict[tuple[str, str], asyncio.Task[None]],
    modes: dict[str, str],
) -> None:
    job_id = str(job["id"])
    try:
        await execute_step(config, config.db_path, job, step)
    except asyncio.CancelledError:
        mode = modes.get(job_id, "shutdown")
        if mode == "cancel":
            _settle(config, job_id, step, "cancelled", "cancelled")
        elif mode == "pause":
            _settle(config, job_id, step, "pending", JOB_QUEUED)
        else:
            _settle(config, job_id, step, "interrupted", "interrupted")
        raise
    except StepFailed as exc:
        if step in CRITICAL_STEPS:
            fail_job(config, config.db_path, job, exc.summary, exc.kind, step)
    except Exception as exc:
        append_job_log(config.logs_dir, job_id, step, "error", str(exc))
        with session(config.db_path) as conn:
            update_step(
                conn,
                job_id,
                step,
                status="failed",
                error_kind=UNKNOWN,
                error_detail=str(exc),
                ended_at=_now(),
            )
        if step in CRITICAL_STEPS:
            fail_job(config, config.db_path, job, str(exc), UNKNOWN, step)
    finally:
        tasks.pop((job_id, step), None)


def _settle(config: AppConfig, job_id: str, step: str, step_status: str, job_status: str) -> None:
    with session(config.db_path) as conn:
        update_step(conn, job_id, step, status=step_status, progress_estimated=0)
        update_job(conn, job_id, status=job_status)
        if job_status == "cancelled":
            conn.execute(
                "UPDATE steps SET status = 'cancelled' "
                "WHERE job_id = ? AND status IN ('pending', 'waiting_env')",
                (job_id,),
            )


def _tick_estimates(config: AppConfig) -> None:
    now = datetime.now(UTC)
    with session(config.db_path) as conn:
        rows = conn.execute(
            "SELECT job_id, name, started_at, eta_s FROM steps "
            "WHERE status = 'running' AND progress_estimated = 1 AND eta_s IS NOT NULL"
        ).fetchall()
        for row in rows:
            if not row["started_at"]:
                continue
            started = datetime.fromisoformat(str(row["started_at"]))
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            elapsed = (now - started).total_seconds()
            eta = float(row["eta_s"] or 0)
            if eta <= 0:
                continue
            progress = min(95.0, max(0.0, elapsed / eta * 100))
            update_step(conn, str(row["job_id"]), str(row["name"]), progress=progress)


def _maybe_notify(config: AppConfig, batch: bool, seen: set[str]) -> tuple[bool, set[str]]:
    with session(config.db_path) as conn:
        jobs = list_jobs(conn)
    active = [job for job in jobs if job["status"] in {JOB_QUEUED, JOB_RUNNING}]
    if active:
        seen.update(str(job["id"]) for job in active)
        return True, seen
    if not batch or not seen:
        return False, seen
    finished = [job for job in jobs if str(job["id"]) in seen]
    done = sum(1 for job in finished if job["status"] == "done")
    partial = sum(1 for job in finished if job["status"] == "partial")
    failed = sum(1 for job in finished if job["status"] == "failed")
    if done and not partial and not failed:
        title, body = "物料已经齐备", f"{done} 首全部完成"
    else:
        title = "队列结束"
        body = f"{done} 首完成，{partial} 首部分完成，{failed} 首失败"
    try:
        from katock.adapters.notifier import notify

        notify(title, body)
    except Exception:
        append_job_log(config.logs_dir, "queue", "notify", "warning", body)
    with session(config.db_path) as conn:
        emit_event(conn, "queue", {"title": title, "body": body})
    return False, set()


def queue_eta_snapshot(config: AppConfig) -> float:
    with session(config.db_path) as conn:
        jobs = runnable_jobs(conn)
        items: list[PendingWork] = []
        for job in jobs:
            job_id = str(job["id"])
            for step in steps_for(conn, job_id):
                if step["status"] in STEP_FINISHED or step["status"] == "cancelled":
                    continue
                if step["status"] == STEP_RUNNING and step.get("eta_s"):
                    seconds = float(step["eta_s"])
                else:
                    seconds, _label = predict_seconds(
                        config, config.db_path, str(step["name"]), float(job.get("duration_s") or 0)
                    )
                items.append(
                    PendingWork(
                        key=f"{job_id}:{step['name']}",
                        step=str(step["name"]),
                        estimate_s=seconds,
                        deps=dependency_keys(job_id, str(step["name"])),
                    )
                )
    return queue_remaining_seconds(
        items,
        default_capacities(config.separation_concurrency, config.translate_concurrency),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
