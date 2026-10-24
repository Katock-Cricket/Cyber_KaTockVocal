"""HTTP 接口。只绑定在应用里的 /api 前缀。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from katock.adapters.catalog import Catalog, CatalogError
from katock.adapters.shell import open_folder
from katock.adapters.translator import Translator
from katock.adapters.wrapper import WrapperAdapter
from katock.config import AppConfig, load_config, save_config
from katock.domain.apple_url import parse_apple_url
from katock.domain.status import JOB_ACTIVE
from katock.domain.versions import version_tags
from katock.logging_setup import read_job_log
from katock.storage.db import session
from katock.storage.meta import read_meta
from katock.storage.repo import (
    SECRET_APPLE_ID,
    SECRET_APPLE_PASSWORD,
    SECRET_MEDIA_TOKEN,
    SECRET_TRANSLATOR_KEY,
    clear_history,
    delete_secret,
    enqueue_command,
    events_after,
    get_job,
    get_lyrics_cache,
    list_env,
    list_jobs,
    prepared_ids,
    put_secret,
    queue_paused,
    secret_flags,
    set_queue_paused,
    steps_for,
    update_job,
)
from katock.web.services.submit import SubmitError, rerun_job, submit_tracks
from katock.worker.scheduler import queue_eta_snapshot

router = APIRouter(prefix="/api")

_ITEM_ORDER = [
    "docker",
    "wrapper",
    "wrapper_ports",
    "wrapper_login",
    "mp4box",
    "ffmpeg",
    "separator",
    "output_root",
    "disk",
]


class TrackIn(BaseModel):
    trackId: str
    title: str
    artist: str
    album: str = ""
    albumArtist: str = ""
    year: int | None = None
    durationS: float = 0
    trackNumber: int = 1
    discNumber: int = 1
    artworkUrl: str = ""
    storefront: str = "cn"
    url: str
    audioLocale: str = ""


class JobsIn(BaseModel):
    tracks: list[TrackIn]


class ResolveIn(BaseModel):
    text: str


class RerunIn(BaseModel):
    step: str | None = None
    force: bool = False


class TranslateChoiceIn(BaseModel):
    enabled: bool


class LoginIn(BaseModel):
    appleId: str
    password: str
    restart: bool = False


class TwoFaIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class SettingsIn(BaseModel):
    outputRoot: str | None = None
    dockerDesktop: str | None = None
    wrapperDir: str | None = None
    gpacDir: str | None = None
    ffmpegDir: str | None = None
    uvrDir: str | None = None
    downloaderSrc: str | None = None
    storefront: str | None = None
    separationConcurrency: int | None = None
    translateConcurrency: int | None = None
    pass1Model: str | None = None
    pass2Model: str | None = None
    translatorBaseUrl: str | None = None
    translatorModel: str | None = None
    autoTranslateLyrics: bool | None = None
    appleId: str | None = None
    applePassword: str | None = None
    mediaUserToken: str | None = None
    translatorApiKey: str | None = None


class TranslatorTestIn(BaseModel):
    baseUrl: str | None = None
    model: str | None = None
    apiKey: str | None = None


def _config(request: Request) -> AppConfig:
    return request.app.state.config


def _catalog(config: AppConfig) -> Catalog:
    return Catalog(config.var_dir / "cache")


def estimated_bytes(duration_s: float) -> int:
    return int(max(duration_s, 0) * (44100 * 2 * 2 * 3 + 1_000_000))


def _decorate(track: dict[str, Any], prepared: set[str]) -> dict[str, Any]:
    track = dict(track)
    track["prepared"] = track["trackId"] in prepared
    track["versionTags"] = version_tags(str(track.get("title") or ""))
    track["estimatedBytes"] = estimated_bytes(float(track.get("durationS") or 0))
    return track


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    config = _config(request)
    with session(config.db_path) as conn:
        rows = {str(item["item"]): item for item in list_env(conn)}
        paused = queue_paused(conn)
    items = []
    for name in _ITEM_ORDER:
        row = rows.get(name)
        items.append(
            {
                "item": name,
                "ok": bool(row["ok"]) if row else False,
                "level": row["level"] if row else "wait",
                "detail": row["detail"] if row else "尚未检查",
                "checkedAt": row["checked_at"] if row else None,
            }
        )
    auth = request.app.state.auth
    return {
        "items": items,
        "canStartJobs": not request.app.state.health.blockers(),
        "queuePaused": paused,
        "auth": {
            "phase": auth["phase"],
            "message": auth["message"],
            "deadlineEpoch": auth["deadline"],
        },
    }


@router.post("/health/recheck")
async def recheck(request: Request) -> dict[str, str]:
    asyncio.create_task(request.app.state.health.run_once())
    return {"status": "started"}


@router.post("/env/docker/start")
async def start_docker(request: Request) -> dict[str, str]:
    asyncio.create_task(request.app.state.health.run_once())
    return {"status": "started"}


@router.post("/auth/apple/login")
async def apple_login(body: LoginIn, request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        put_secret(conn, SECRET_APPLE_ID, body.appleId)
        put_secret(conn, SECRET_APPLE_PASSWORD, body.password)
    auth = request.app.state.auth
    auth["phase"] = "starting"
    auth["message"] = "正在登录 Wrapper"
    auth["deadline"] = None
    task = auth.get("task")
    if task is not None and not task.done():
        task.cancel()
    auth["task"] = asyncio.create_task(_watch_login(config, auth, body.restart))
    return {"status": "started"}


async def _watch_login(config: AppConfig, auth: dict[str, Any], restart: bool) -> None:
    wrapper = WrapperAdapter(config.wrapper_dir)
    with session(config.db_path) as conn:
        apple_id = get_secret_safe(conn, SECRET_APPLE_ID)
        password = get_secret_safe(conn, SECRET_APPLE_PASSWORD)
    if restart:
        await asyncio.to_thread(wrapper.reset_login_files)
        await asyncio.to_thread(wrapper._compose, "down", timeout=60)
    started = await asyncio.to_thread(wrapper.ensure_up, apple_id, password)
    if not started.ok:
        auth["phase"] = "error"
        auth["message"] = started.detail
        return
    for _ in range(45):
        state = await asyncio.to_thread(wrapper.login_state)
        if state.ok:
            auth["phase"] = "ok"
            auth["message"] = state.detail
            return
        if "2FA" in state.detail or "验证码" in state.detail:
            auth["phase"] = "need_2fa"
            auth["message"] = "请输入 6 位验证码"
            return
        await asyncio.sleep(2)
    auth["phase"] = "error"
    auth["message"] = "登录超时，请重新发起"


def get_secret_safe(conn: Any, key: str) -> str:
    from katock.storage.repo import get_secret

    return get_secret(conn, key) or ""


@router.post("/auth/apple/2fa")
async def apple_2fa(body: TwoFaIn, request: Request) -> dict[str, str]:
    config = _config(request)
    wrapper = WrapperAdapter(config.wrapper_dir)
    written = await asyncio.to_thread(wrapper.write_2fa, body.code)
    if not written.ok:
        raise HTTPException(status_code=400, detail=written.detail)
    auth = request.app.state.auth
    auth["phase"] = "checking"
    auth["deadline"] = time.time() + 60
    auth["message"] = "正在确认验证码"
    task = auth.get("task")
    if task is not None and not task.done():
        task.cancel()
    auth["task"] = asyncio.create_task(_watch_2fa(wrapper, auth))
    return {"status": "started"}


async def _watch_2fa(wrapper: WrapperAdapter, auth: dict[str, Any]) -> None:
    deadline = float(auth["deadline"] or 0)
    while time.time() < deadline:
        state = await asyncio.to_thread(wrapper.login_state)
        if state.ok:
            auth["phase"] = "ok"
            auth["message"] = "登录成功"
            auth["deadline"] = None
            return
        await asyncio.sleep(2)
    auth["phase"] = "expired"
    auth["message"] = "验证码已过期，重新发起"
    auth["deadline"] = None


@router.get("/search")
async def search(request: Request, q: str, offset: int = 0) -> dict[str, Any]:
    config = _config(request)
    query = q.strip()
    if not query:
        return {"tracks": [], "hasMore": False}
    try:
        tracks = await _catalog(config).search(
            config.storefront, query, limit=10, offset=max(0, offset)
        )
    except CatalogError as exc:
        raise HTTPException(status_code=502, detail=exc.summary) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="连接 Apple Music 失败") from exc
    payload = [track.as_dict() for track in tracks]
    with session(config.db_path) as conn:
        ready = prepared_ids(conn, [str(item["trackId"]) for item in payload])
    return {"tracks": [_decorate(item, ready) for item in payload], "hasMore": len(tracks) == 10}


@router.post("/resolve")
async def resolve(body: ResolveIn, request: Request) -> dict[str, Any]:
    config = _config(request)
    lines = [line.strip() for line in body.text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="请输入歌名或链接")
    if len(lines) > 50:
        raise HTTPException(status_code=400, detail="单次最多 50 首，请分批")
    only = parse_apple_url(lines[0]) if len(lines) == 1 else None
    direct = only is not None and only.kind == "song"
    catalog = _catalog(config)
    tracks: list[dict[str, Any]] = []
    notes: list[str] = []
    try:
        for line in lines:
            ref = parse_apple_url(line)
            if ref is None:
                found = await catalog.search(config.storefront, line, limit=1)
                if not found:
                    notes.append(f"未找到：{line}。建议改用「歌手 + 歌名」或直接粘贴链接。")
                    continue
                tracks.append(found[0].as_dict())
                continue
            if ref.kind == "song" and ref.track_id:
                tracks.append((await catalog.song(ref.storefront, ref.track_id)).as_dict())
            elif ref.kind == "album" and ref.album_id:
                for item in await catalog.collection(ref.storefront, "album", ref.album_id):
                    tracks.append(item.as_dict())
            elif ref.kind == "playlist" and ref.playlist_id:
                for item in await catalog.collection(ref.storefront, "playlist", ref.playlist_id):
                    tracks.append(item.as_dict())
    except CatalogError as exc:
        raise HTTPException(status_code=502, detail=exc.summary) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="连接 Apple Music 失败") from exc
    with session(config.db_path) as conn:
        ready = prepared_ids(conn, [str(item["trackId"]) for item in tracks])
    return {
        "tracks": [_decorate(item, ready) for item in tracks],
        "notes": notes,
        "direct": direct and len(tracks) == 1,
    }


@router.post("/jobs")
def create_jobs(body: JobsIn, request: Request) -> dict[str, Any]:
    config = _config(request)
    blockers = request.app.state.health.blockers()
    if blockers:
        raise HTTPException(status_code=400, detail="；".join(blockers))
    try:
        created = submit_tracks(config, [track.model_dump() for track in body.tracks])
    except SubmitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"jobs": created}


@router.get("/jobs")
def jobs(request: Request) -> dict[str, Any]:
    config = _config(request)
    with session(config.db_path) as conn:
        rows = list_jobs(conn)
        detailed = []
        for row in rows:
            steps = steps_for(conn, str(row["id"]))
            detailed.append(_job_view(row, steps, None))
        paused = queue_paused(conn)
    eta = queue_eta_snapshot(config)
    return {"jobs": detailed, "queuePaused": paused, "etaSeconds": eta}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, request: Request) -> dict[str, Any]:
    config = _config(request)
    with session(config.db_path) as conn:
        row = get_job(conn, job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        steps = steps_for(conn, job_id)
        cache = get_lyrics_cache(conn, str(row["track_id"]))
    meta = read_meta(Path(row["dir_path"])) if row.get("dir_path") else None
    view = _job_view(row, steps, meta)
    view["log"] = read_job_log(config.logs_dir, job_id)
    view["tokenUsage"] = int(cache["token_usage"]) if cache else 0
    view["bilingualFailed"] = bool(cache and cache["bilingual_failed"])
    raw_choice = row.get("translate_lyrics")
    explicit = None if raw_choice is None else bool(int(raw_choice))
    view["translateLyrics"] = explicit
    view["translateEnabled"] = config.auto_translate_lyrics if explicit is None else explicit
    return view


@router.get("/jobs/{job_id}/log")
def job_log(job_id: str, request: Request) -> dict[str, str]:
    return {"log": read_job_log(_config(request).logs_dir, job_id)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        if get_job(conn, job_id) is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        enqueue_command(conn, "cancel", {"jobId": job_id})
    return {"status": "ok"}


@router.post("/jobs/{job_id}/rerun")
def rerun(job_id: str, body: RerunIn, request: Request) -> dict[str, str]:
    try:
        rerun_job(_config(request), job_id, body.step, body.force)
    except SubmitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "queued"}


@router.put("/jobs/{job_id}/translate")
def set_job_translate(job_id: str, body: TranslateChoiceIn, request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        row = get_job(conn, job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        update_job(conn, job_id, translate_lyrics=1 if body.enabled else 0)
        status = str(row["status"])
        lyrics_ready = any(
            item["name"] == "lyrics" and item["status"] in {"done", "skipped"}
            for item in steps_for(conn, job_id)
        )
    if status not in JOB_ACTIVE and lyrics_ready:
        try:
            rerun_job(config, job_id, "lyrics", False)
        except SubmitError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {"status": "queued"}
    return {"status": "saved"}


@router.post("/queue/pause")
def pause_queue(request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        set_queue_paused(conn, True)
        enqueue_command(conn, "pause", {})
    return {"status": "paused"}


@router.post("/queue/resume")
def resume_queue(request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        set_queue_paused(conn, False)
        enqueue_command(conn, "resume", {})
    return {"status": "resumed"}


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    config = load_config(_config(request).root_path)
    with session(config.db_path) as conn:
        flags = secret_flags(conn)
    return {
        "outputRoot": config.output_root,
        "dockerDesktop": config.docker_desktop,
        "wrapperDir": config.wrapper_dir,
        "gpacDir": config.gpac_dir,
        "ffmpegDir": config.ffmpeg_dir,
        "uvrDir": config.uvr_dir,
        "downloaderSrc": config.downloader_src,
        "storefront": config.storefront,
        "separationConcurrency": config.separation_concurrency,
        "translateConcurrency": config.translate_concurrency,
        "pass1Model": config.pass1_model,
        "pass2Model": config.pass2_model,
        "translatorBaseUrl": config.translator_base_url,
        "translatorModel": config.translator_model,
        "autoTranslateLyrics": config.auto_translate_lyrics,
        **flags,
    }


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request) -> dict[str, str]:
    config = load_config(_config(request).root_path)
    mapping = {
        "outputRoot": "output_root",
        "dockerDesktop": "docker_desktop",
        "wrapperDir": "wrapper_dir",
        "gpacDir": "gpac_dir",
        "ffmpegDir": "ffmpeg_dir",
        "uvrDir": "uvr_dir",
        "downloaderSrc": "downloader_src",
        "storefront": "storefront",
        "separationConcurrency": "separation_concurrency",
        "translateConcurrency": "translate_concurrency",
        "pass1Model": "pass1_model",
        "pass2Model": "pass2_model",
        "translatorBaseUrl": "translator_base_url",
        "translatorModel": "translator_model",
        "autoTranslateLyrics": "auto_translate_lyrics",
    }
    payload = body.model_dump(exclude_none=True)
    data = config.model_dump()
    for source, target in mapping.items():
        if source in payload:
            data[target] = payload[source]
    try:
        updated = AppConfig.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_config(updated)
    request.app.state.config = updated
    with session(updated.db_path) as conn:
        _save_secret(conn, SECRET_APPLE_ID, body.appleId)
        _save_secret(conn, SECRET_APPLE_PASSWORD, body.applePassword)
        _save_secret(conn, SECRET_MEDIA_TOKEN, body.mediaUserToken)
        _save_secret(conn, SECRET_TRANSLATOR_KEY, body.translatorApiKey)
    return {"status": "saved"}


def _save_secret(conn: Any, key: str, value: str | None) -> None:
    if value is None:
        return
    if value == "":
        delete_secret(conn, key)
        return
    put_secret(conn, key, value)


@router.post("/settings/translator/test")
async def test_translator(body: TranslatorTestIn, request: Request) -> dict[str, Any]:
    config = _config(request)
    with session(config.db_path) as conn:
        stored = get_secret_safe(conn, SECRET_TRANSLATOR_KEY)
    result = await Translator().test_connection(
        body.baseUrl or config.translator_base_url,
        body.model or config.translator_model,
        body.apiKey if body.apiKey is not None else stored,
    )
    return {"ok": result.ok, "failedAt": result.failed_at, "detail": result.detail}


@router.post("/settings/history/clear")
def clear(request: Request) -> dict[str, str]:
    with session(_config(request).db_path) as conn:
        clear_history(conn)
    return {"status": "cleared"}


@router.post("/tracks/{track_id}/open-folder")
def open_track_folder(track_id: str, request: Request) -> dict[str, str]:
    config = _config(request)
    with session(config.db_path) as conn:
        row = conn.execute("SELECT dir_path FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    if row is None or not row["dir_path"]:
        raise HTTPException(status_code=404, detail="还没有这首歌的目录")
    path = Path(str(row["dir_path"]))
    try:
        open_folder(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": str(path)}


@router.get("/events")
async def events(request: Request, after: int = 0) -> StreamingResponse:
    config = _config(request)

    async def stream() -> Any:
        last = after
        while True:
            if await request.is_disconnected():
                break
            with session(config.db_path) as conn:
                rows = events_after(conn, last)
            for row in rows:
                last = int(row["id"])
                payload = json.dumps(row, ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
            yield ": ping\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _job_view(
    row: dict[str, Any], steps: list[dict[str, Any]], meta: dict[str, Any] | None
) -> dict[str, Any]:
    visible = [step for step in steps if step["name"] != "finalize"]
    progress = 0.0
    if visible:
        progress = sum(float(step["progress"] or 0) for step in visible) / len(visible)
    missing = []
    if meta and isinstance(meta.get("missing"), list):
        missing = meta["missing"]
    source = meta.get("source") if meta else None
    return {
        "id": row["id"],
        "trackId": row["track_id"],
        "title": row.get("title"),
        "artist": row.get("artist"),
        "album": row.get("album"),
        "year": row.get("year"),
        "durationS": row.get("duration_s"),
        "artworkUrl": row.get("artwork_url"),
        "dirPath": row.get("dir_path"),
        "status": row["status"],
        "errorSummary": row.get("error_summary"),
        "errorKind": row.get("error_kind"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "progress": progress,
        "missing": missing,
        "source": source,
        "lyrics": meta.get("lyrics") if meta else None,
        "steps": [
            {
                "name": step["name"],
                "status": step["status"],
                "progress": step["progress"],
                "estimated": bool(step["progress_estimated"]),
                "etaSeconds": step.get("eta_s"),
                "etaLabel": step.get("eta_label") or "",
                "elapsedS": step.get("elapsed_s"),
                "errorDetail": step.get("error_detail"),
                "errorKind": step.get("error_kind"),
                "note": step.get("note") or "",
                "startedAt": step.get("started_at"),
                "endedAt": step.get("ended_at"),
            }
            for step in steps
        ],
    }
