"""单个阶段的执行。"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from katock.adapters.catalog import COVER_KIND, LYRICS_KIND, Catalog, CatalogError
from katock.adapters.downloader import Downloader, DownloadError
from katock.adapters.ffmpeg import Ffmpeg, wav_matches
from katock.adapters.separator import SeparationError, Separator
from katock.adapters.translator import TranslationError, Translator
from katock.config import AppConfig
from katock.domain.eta import Sample, estimate_stage
from katock.domain.failures import ENV_NOT_READY, UNKNOWN, suggestion
from katock.domain.language import needs_translation
from katock.domain.lyrics import parse_ttml, render_lrc, render_srt
from katock.domain.status import (
    STEP_COVER,
    STEP_DOWNLOAD,
    STEP_FINALIZE,
    STEP_LYRICS,
    STEP_PASS1,
    STEP_PASS2,
    STEP_PENDING,
)
from katock.domain.stems import (
    FILE_COVER,
    FILE_FULL_VOCAL,
    FILE_HARMONY,
    FILE_INSTRUMENTAL,
    FILE_LEAD,
    FILE_LRC,
    FILE_ORIGINAL,
    FILE_SRT,
    STEM_INSTRUMENTAL,
    STEM_VOCALS,
)
from katock.logging_setup import append_job_log
from katock.storage.db import now_iso, session
from katock.storage.fsops import file_ready, publish
from katock.storage.meta import read_meta, write_meta
from katock.storage.repo import (
    SECRET_MEDIA_TOKEN,
    SECRET_TRANSLATOR_KEY,
    add_sample,
    emit_event,
    get_lyrics_cache,
    get_secret,
    list_env,
    put_lyrics_cache,
    update_step,
)


class StepFailed(Exception):
    def __init__(self, kind: str, summary: str, detail: str = "") -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary
        self.suggestion = suggestion(kind)
        self.detail = detail


def _meta(song_dir: Path) -> dict[str, Any]:
    return read_meta(song_dir) or {}


def _step_done(meta: dict[str, Any], name: str) -> bool:
    return meta.get("steps", {}).get(name, {}).get("status") == "done"


def _origin(job: dict[str, Any], meta: dict[str, Any]) -> str:
    return str(meta.get("origin") or job.get("track_origin") or job.get("origin") or "created")


def _force(job: dict[str, Any]) -> set[str]:
    raw = job.get("force_steps") or "[]"
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw
    return set(data)


def should_skip(config: AppConfig, job: dict[str, Any], step: str) -> bool:
    if step in _force(job) or step == STEP_FINALIZE:
        return False
    song_dir = Path(str(job["dir_path"]))
    work = config.work_dir / str(job["id"])
    meta = _meta(song_dir)
    origin = _origin(job, meta)

    def trusted(name: str, filename: str) -> bool:
        if not file_ready(song_dir / filename):
            return False
        return origin == "external" or _step_done(meta, name)

    if step == STEP_DOWNLOAD:
        return trusted(STEP_DOWNLOAD, FILE_ORIGINAL)
    if step == STEP_COVER:
        return trusted(STEP_COVER, FILE_COVER)
    if step == STEP_LYRICS:
        return trusted(STEP_LYRICS, FILE_LRC) and file_ready(song_dir / FILE_SRT)
    if step == STEP_PASS2:
        return trusted(STEP_PASS2, FILE_LEAD) and file_ready(song_dir / FILE_HARMONY)
    if step == STEP_PASS1:
        if not trusted(STEP_PASS1, FILE_INSTRUMENTAL):
            return False
        pass2_ready = should_skip(config, job, STEP_PASS2)
        if pass2_ready:
            return True
        return file_ready(work / FILE_FULL_VOCAL)
    return False


def predict_seconds(
    config: AppConfig, db_path: Path, step: str, duration_s: float
) -> tuple[float, str]:
    model = _model_name(config, step)
    with session(db_path) as conn:
        rows = conn.execute(
            "SELECT elapsed_s, audio_duration_s FROM step_samples WHERE step = ? AND model = ? "
            "ORDER BY id DESC LIMIT 10",
            (step, model),
        ).fetchall()
    samples = [
        Sample(elapsed_s=float(row["elapsed_s"]), audio_duration_s=float(row["audio_duration_s"]))
        for row in reversed(rows)
    ]
    duration = max(duration_s, 1)
    if step == STEP_PASS1:
        estimate = estimate_stage(samples, duration, config.eta_pass1)
        return estimate.seconds, estimate.label
    if step == STEP_PASS2:
        estimate = estimate_stage(samples, duration, config.eta_pass2)
        return estimate.seconds, estimate.label
    if step == STEP_DOWNLOAD:
        coeff = config.eta_bytes_per_audio_s / max(config.eta_download_bps, 1)
        estimate = estimate_stage(samples, duration, coeff)
        return estimate.seconds, estimate.label
    if step == STEP_LYRICS:
        seconds = duration * 0.4 * config.eta_lyrics_per_line + config.eta_translate_s
        return seconds, "首次执行，暂用默认估算" if not samples else f"预计剩余 {int(seconds)} 秒"
    if step == STEP_COVER:
        return config.eta_cover_s, f"预计剩余 {int(config.eta_cover_s)} 秒"
    return config.eta_finalize_s, f"预计剩余 {int(config.eta_finalize_s)} 秒"


def _model_name(config: AppConfig, step: str) -> str:
    if step == STEP_PASS1:
        return config.pass1_model
    if step == STEP_PASS2:
        return config.pass2_model
    if step == STEP_LYRICS:
        return config.translator_model
    return ""


async def execute_step(config: AppConfig, db_path: Path, job: dict[str, Any], step: str) -> None:
    job_id = str(job["id"])
    if should_skip(config, job, step):
        _mark(
            db_path,
            config,
            job_id,
            step,
            status="skipped",
            progress=100,
            progress_estimated=0,
            elapsed_s=0,
        )
        return
    eta_s, eta_label = predict_seconds(config, db_path, step, float(job.get("duration_s") or 0))
    _mark(
        db_path,
        config,
        job_id,
        step,
        status="running",
        started_at=now_iso(),
        progress=0,
        progress_estimated=1,
        eta_s=eta_s,
        eta_label=eta_label,
    )
    started = time.monotonic()
    try:
        note = await _run(config, db_path, job, step)
    except StepFailed as exc:
        elapsed = time.monotonic() - started
        _mark(
            db_path,
            config,
            job_id,
            step,
            status="failed",
            ended_at=now_iso(),
            elapsed_s=elapsed,
            progress=0,
            progress_estimated=0,
            error_detail=f"{exc.summary}\n{exc.suggestion}\n{exc.detail}".strip(),
            error_kind=exc.kind,
        )
        append_job_log(config.logs_dir, job_id, step, "error", exc.summary, kind=exc.kind)
        raise
    elapsed = time.monotonic() - started
    _mark(
        db_path,
        config,
        job_id,
        step,
        status="done",
        ended_at=now_iso(),
        elapsed_s=elapsed,
        progress=100,
        progress_estimated=0,
        note=note or "",
        error_detail=None,
        error_kind=None,
    )
    with session(db_path) as conn:
        add_sample(
            conn,
            step,
            _model_name(config, step),
            float(job.get("duration_s") or 0) or elapsed,
            elapsed,
        )


async def _run(config: AppConfig, db_path: Path, job: dict[str, Any], step: str) -> str:
    if step == STEP_DOWNLOAD:
        return await _download(config, db_path, job)
    if step == STEP_COVER:
        return await _cover(config, db_path, job)
    if step == STEP_LYRICS:
        return await _lyrics(config, db_path, job)
    if step == STEP_PASS1:
        return await _separate(config, db_path, job, STEP_PASS1)
    if step == STEP_PASS2:
        return await _separate(config, db_path, job, STEP_PASS2)
    if step == STEP_FINALIZE:
        return _finalize(config, db_path, job)
    raise StepFailed(UNKNOWN, f"未知阶段 {step}")


async def _download(config: AppConfig, db_path: Path, job: dict[str, Any]) -> str:
    await _wait_environment(config, db_path, str(job["id"]))
    _mark(db_path, config, str(job["id"]), STEP_DOWNLOAD, status="running")
    song_dir = Path(str(job["dir_path"]))
    origin = _origin(job, _meta(song_dir))
    if origin == "external" and file_ready(song_dir / FILE_ORIGINAL):
        return "外部目录已有原曲，保持原样"
    work = config.work_dir / str(job["id"])
    work.mkdir(parents=True, exist_ok=True)
    with session(db_path) as conn:
        token = get_secret(conn, SECRET_MEDIA_TOKEN) or ""
    downloader = Downloader(config.amd_path, config.ffmpeg_path.parent, config.mp4box_path.parent)
    ffmpeg = Ffmpeg(config.ffmpeg_path, config.ffprobe_path)
    last: DownloadError | None = None
    audio: Path | None = None
    for attempt in (1, 2):
        try:
            audio = await downloader.download(
                str(job["song_url"]),
                work,
                str(job.get("storefront") or config.storefront),
                token,
            )
            last = None
            break
        except DownloadError as exc:
            last = exc
            append_job_log(
                config.logs_dir,
                str(job["id"]),
                STEP_DOWNLOAD,
                "warning",
                f"第 {attempt} 次下载失败：{exc.summary}",
            )
    if last is not None or audio is None:
        assert last is not None
        raise StepFailed(last.kind, last.summary, last.detail)
    flac = work / FILE_ORIGINAL
    if audio.suffix.lower() != ".flac":
        ffmpeg.to_flac(audio, flac)
    elif audio != flac:
        shutil.copyfile(audio, flac)
    ffmpeg.decode_ok(flac)
    probe = ffmpeg.probe(flac)
    expected = float(job.get("duration_s") or 0)
    if expected and abs(probe.duration_s - expected) > 1:
        raise StepFailed(
            UNKNOWN, f"原曲时长 {probe.duration_s:.1f}s 与曲目信息 {expected:.1f}s 相差超过 1 秒"
        )
    publish(flac, song_dir, FILE_ORIGINAL, origin=origin)
    meta = _meta(song_dir)
    meta["source"] = {"sampleRate": probe.sample_rate, "bitDepth": probe.bit_depth}
    write_meta(song_dir, meta)
    return f"{probe.sample_rate} Hz / {probe.bit_depth} bit"


async def _wait_environment(config: AppConfig, db_path: Path, job_id: str) -> None:
    for _ in range(60):
        with session(db_path) as conn:
            rows = {str(item["item"]): item for item in list_env(conn)}
        docker_ok = bool(rows.get("docker", {}).get("ok"))
        login_ok = bool(rows.get("wrapper_login", {}).get("ok"))
        if docker_ok and login_ok:
            return
        detail = "正在等待 Docker 与 Wrapper 登录"
        if rows.get("docker", {}).get("detail"):
            detail = str(rows["docker"]["detail"])
        _mark(db_path, config, job_id, STEP_DOWNLOAD, status="waiting_env", note=detail)
        import asyncio

        await asyncio.sleep(2)
    raise StepFailed(ENV_NOT_READY, "等待 Docker / Wrapper 超过 120 秒")


async def _cover(config: AppConfig, db_path: Path, job: dict[str, Any]) -> str:
    song_dir = Path(str(job["dir_path"]))
    origin = _origin(job, _meta(song_dir))
    work = config.work_dir / str(job["id"])
    work.mkdir(parents=True, exist_ok=True)
    catalog = Catalog(config.var_dir / "cache")
    try:
        content, width, height = await catalog.cover_bytes(str(job.get("artwork_url") or ""))
    except CatalogError as exc:
        raise StepFailed(COVER_KIND, exc.summary) from exc
    image = work / FILE_COVER
    image.write_bytes(content)
    publish(image, song_dir, FILE_COVER, origin=origin)
    note = f"{width}x{height}"
    original = song_dir / FILE_ORIGINAL
    if origin != "external" and file_ready(original):
        ffmpeg = Ffmpeg(config.ffmpeg_path, config.ffprobe_path)
        tagged = work / "原曲.tagged.flac"
        tags = {
            "title": str(job.get("title") or ""),
            "artist": str(job.get("artist") or ""),
            "album": str(job.get("album") or ""),
            "album_artist": str(job.get("album_artist") or job.get("artist") or ""),
            "track": str(job.get("track_number") or 1),
            "disc": str(job.get("disc_number") or 1),
        }
        if job.get("year"):
            tags["date"] = str(job["year"])
        ffmpeg.tag_flac(original, tagged, tags, image if image.is_file() else None)
        publish(tagged, song_dir, FILE_ORIGINAL, origin=origin)
    meta = _meta(song_dir)
    meta.setdefault("steps", {})
    cover_info = meta["steps"].get(STEP_COVER, {})
    if not isinstance(cover_info, dict):
        cover_info = {}
    cover_info["size"] = note
    meta["steps"][STEP_COVER] = cover_info
    write_meta(song_dir, meta)
    if min(width, height) < 1000:
        return f"{note}，短边低于 1000"
    return note


async def _lyrics(config: AppConfig, db_path: Path, job: dict[str, Any]) -> str:
    song_dir = Path(str(job["dir_path"]))
    origin = _origin(job, _meta(song_dir))
    if origin == "external" and file_ready(song_dir / FILE_LRC) and file_ready(song_dir / FILE_SRT):
        return "外部目录已有歌词，保持原样"
    with session(db_path) as conn:
        media = get_secret(conn, SECRET_MEDIA_TOKEN) or ""
        api_key = get_secret(conn, SECRET_TRANSLATOR_KEY) or ""
    catalog = Catalog(config.var_dir / "cache")
    try:
        ttml = await catalog.lyrics_ttml(
            str(job.get("storefront") or config.storefront),
            str(job["track_id"]),
            media,
        )
    except CatalogError as exc:
        raise StepFailed(LYRICS_KIND, exc.summary) from exc
    document = parse_ttml(ttml)
    language = document.language or str(job.get("audio_locale") or "") or None
    original = [{"text": line.text, "startMs": line.start_ms} for line in document.lines]
    original_json = json.dumps(original, ensure_ascii=False)
    text = "\n".join(line.text for line in document.lines)
    translate = needs_translation(language, text)
    translations: tuple[str, ...] | None = None
    tokens = 0
    note = ""
    bilingual_failed = False
    if translate:
        cached_lines = _cached_translation(db_path, str(job["track_id"]), original_json)
        if cached_lines is not None:
            translations = cached_lines
            note = "复用已缓存译文"
        elif not api_key:
            note = "未配置翻译密钥，已输出单语歌词。请到设置页填写。"
        else:
            try:
                result = await Translator().translate(
                    [line.text for line in document.lines],
                    base_url=config.translator_base_url,
                    model=config.translator_model,
                    api_key=api_key,
                )
                translations = result.lines
                tokens = result.token_usage
                note = f"翻译 {tokens} token"
            except TranslationError as exc:
                bilingual_failed = True
                note = f"双语失败：{exc.summary}"
    work = config.work_dir / str(job["id"])
    work.mkdir(parents=True, exist_ok=True)
    lrc_path = work / FILE_LRC
    srt_path = work / FILE_SRT
    lrc_path.write_text(render_lrc(document.lines, translations), encoding="utf-8")
    srt_path.write_text(render_srt(document.lines, translations), encoding="utf-8")
    publish(lrc_path, song_dir, FILE_LRC, origin=origin)
    publish(srt_path, song_dir, FILE_SRT, origin=origin)
    with session(db_path) as conn:
        put_lyrics_cache(
            conn,
            {
                "track_id": str(job["track_id"]),
                "language": language or "",
                "timed": 1 if document.timed else 0,
                "original": original_json,
                "translation": json.dumps(translations, ensure_ascii=False)
                if translations
                else None,
                "token_usage": tokens,
                "bilingual_failed": 1 if bilingual_failed else 0,
            },
        )
    meta = _meta(song_dir)
    meta["lyrics"] = {
        "language": language,
        "bilingual": translations is not None,
        "timed": document.timed,
        "note": note,
        "tokenUsage": tokens,
    }
    write_meta(song_dir, meta)
    if not document.timed:
        note = (note + "；" if note else "") + "无时间轴"
    return note


def _cached_translation(db_path: Path, track_id: str, original_json: str) -> tuple[str, ...] | None:
    with session(db_path) as conn:
        cached = get_lyrics_cache(conn, track_id)
    if not cached or cached.get("original") != original_json or not cached.get("translation"):
        return None
    data = json.loads(str(cached["translation"]))
    if not isinstance(data, list):
        return None
    return tuple(str(item) for item in data)


async def _separate(config: AppConfig, db_path: Path, job: dict[str, Any], step: str) -> str:
    song_dir = Path(str(job["dir_path"]))
    origin = _origin(job, _meta(song_dir))
    work = config.work_dir / str(job["id"])
    work.mkdir(parents=True, exist_ok=True)
    if step == STEP_PASS1:
        source = song_dir / FILE_ORIGINAL
        model = config.pass1_model
    else:
        source = work / FILE_FULL_VOCAL
        model = config.pass2_model
        if not file_ready(source):
            await _separate(config, db_path, job, STEP_PASS1)
    if not file_ready(source):
        raise StepFailed(UNKNOWN, f"分离输入不存在：{source.name}")
    separator = Separator(config.separator_path, config.models_dir)
    ffmpeg = Ffmpeg(config.ffmpeg_path, config.ffprobe_path)
    original = ffmpeg.probe(song_dir / FILE_ORIGINAL)

    async def on_progress(value: float) -> None:
        if value < 0:
            return
        _mark(
            db_path,
            config,
            str(job["id"]),
            step,
            progress=value,
            progress_estimated=0,
        )

    try:
        produced = await separator.separate(
            source,
            model,
            step,
            work / step,
            on_progress,
        )
    except SeparationError as exc:
        raise StepFailed(exc.kind, exc.summary, exc.detail) from exc
    for stem, path in produced.items():
        probe = ffmpeg.probe(path)
        current = path
        if not wav_matches(probe):
            converted = work / step / f"{path.stem}.pcm.wav"
            ffmpeg.to_pcm16(
                path,
                converted,
                resample=probe.sample_rate != 44100 or probe.channels != 2,
            )
            current = converted
            probe = ffmpeg.probe(current)
        if abs(probe.duration_s - original.duration_s) > 0.05:
            raise StepFailed(
                UNKNOWN,
                f"{current.name} 时长 {probe.duration_s:.3f}s 与原曲相差超过 0.05 秒",
            )
        if not wav_matches(probe):
            raise StepFailed(UNKNOWN, f"{current.name} 不是 44100 Hz / 16 bit / 立体声")
        if step == STEP_PASS1 and stem == STEM_VOCALS:
            target = work / FILE_FULL_VOCAL
            shutil.copyfile(current, target)
        elif step == STEP_PASS1 and stem == STEM_INSTRUMENTAL:
            publish(current, song_dir, FILE_INSTRUMENTAL, origin=origin)
        elif step == STEP_PASS2 and stem == STEM_VOCALS:
            publish(current, song_dir, FILE_LEAD, origin=origin)
        elif step == STEP_PASS2 and stem == STEM_INSTRUMENTAL:
            publish(current, song_dir, FILE_HARMONY, origin=origin)
    return model


def _finalize(config: AppConfig, db_path: Path, job: dict[str, Any]) -> str:
    from katock.storage.repo import get_job, steps_for, update_job

    song_dir = Path(str(job["dir_path"]))
    with session(db_path) as conn:
        fresh = get_job(conn, str(job["id"])) or job
        steps = steps_for(conn, str(job["id"]))
    meta = _meta(song_dir)
    missing: list[str] = []
    if not file_ready(song_dir / FILE_COVER):
        missing.append("封面")
    if not (file_ready(song_dir / FILE_LRC) and file_ready(song_dir / FILE_SRT)):
        missing.append("歌词")
    critical: list[str] = []
    for filename, label in (
        (FILE_ORIGINAL, "原曲"),
        (FILE_INSTRUMENTAL, "伴奏"),
        (FILE_LEAD, "主音"),
        (FILE_HARMONY, "和声"),
    ):
        if not file_ready(song_dir / filename):
            critical.append(label)
    meta["missing"] = missing + critical
    meta["lastRunAt"] = now_iso()
    meta_steps = meta.setdefault("steps", {})
    for item in steps:
        if item["name"] == STEP_FINALIZE:
            continue
        meta_steps[str(item["name"])] = {
            "status": item["status"],
            "elapsedS": item.get("elapsed_s"),
            "note": item.get("note") or "",
        }
    if critical:
        status = "failed"
        meta["lastError"] = "缺少关键物料：" + "、".join(critical)
    elif missing:
        status = "partial"
        meta["lastError"] = "缺少：" + "、".join(missing)
    else:
        status = "done"
        meta["lastError"] = None
    write_meta(song_dir, meta)
    with session(db_path) as conn:
        update_job(
            conn,
            str(job["id"]),
            status=status,
            error_summary=meta["lastError"],
            error_kind=None if status != "failed" else UNKNOWN,
        )
        from katock.storage.repo import upsert_track

        upsert_track(
            conn,
            {
                "track_id": fresh["track_id"],
                "title": fresh["title"],
                "artist": fresh["artist"],
                "album": fresh.get("album") or "",
                "dir_path": str(song_dir),
                "status": status,
                "origin": _origin(fresh, meta),
            },
        )
        emit_event(conn, "job", {"status": status, "missing": meta["missing"]}, str(job["id"]))
    if status in {"done", "partial"}:
        shutil.rmtree(config.work_dir / str(job["id"]), ignore_errors=True)
    return status


def fail_job(
    config: AppConfig,
    db_path: Path,
    job: dict[str, Any],
    summary: str,
    kind: str,
    failed_step: str,
) -> None:
    from katock.domain.status import DOWNSTREAM
    from katock.storage.repo import update_job

    song_dir = Path(str(job["dir_path"]))
    meta = _meta(song_dir)
    with session(db_path) as conn:
        for name in DOWNSTREAM[failed_step]:
            row = conn.execute(
                "SELECT status FROM steps WHERE job_id = ? AND name = ?",
                (job["id"], name),
            ).fetchone()
            if row and row["status"] in {STEP_PENDING, "waiting_env"}:
                update_step(conn, str(job["id"]), name, status="cancelled")
        update_job(conn, str(job["id"]), status="failed", error_summary=summary, error_kind=kind)
        emit_event(conn, "job", {"status": "failed", "error": summary}, str(job["id"]))
        from katock.storage.repo import upsert_track

        if job.get("track_id") and job.get("title"):
            upsert_track(
                conn,
                {
                    "track_id": job["track_id"],
                    "title": job["title"],
                    "artist": job.get("artist") or "",
                    "album": job.get("album") or "",
                    "dir_path": str(song_dir),
                    "status": "failed",
                    "origin": _origin(job, meta),
                },
            )
    if meta:
        meta["lastError"] = summary
        meta["lastRunAt"] = now_iso()
        write_meta(song_dir, meta)


def _mark(db_path: Path, config: AppConfig, job_id: str, step: str, **fields: Any) -> None:
    with session(db_path) as conn:
        update_step(conn, job_id, step, **fields)
        emit_event(conn, "step", {"step": step, **_public(fields)}, job_id)


def _public(fields: dict[str, Any]) -> dict[str, Any]:
    hidden = {"error_detail"}
    return {key: value for key, value in fields.items() if key not in hidden}
