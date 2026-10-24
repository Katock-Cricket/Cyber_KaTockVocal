"""网页进程。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from katock.config import ensure_config
from katock.logging_setup import setup_logging
from katock.storage.db import session
from katock.storage.repo import SECRET_TRANSLATOR_KEY, get_secret, put_secret
from katock.web.api import router
from katock.web.services.health import HealthService
from katock.web.services.supervisor import Supervisor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = ensure_config()
    setup_logging(config.logs_dir)
    _import_translator_key(config.db_path)
    app.state.config = config
    app.state.auth = {"phase": "idle", "message": "", "deadline": None, "task": None}
    app.state.health = HealthService(config)
    app.state.supervisor = Supervisor(config)
    app.state.health.start()
    await app.state.supervisor.start()
    yield
    await app.state.supervisor.stop()
    await app.state.health.stop()


def _import_translator_key(db_path: Path) -> None:
    with session(db_path) as conn:
        if get_secret(conn, SECRET_TRANSLATOR_KEY):
            return
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if key:
            put_secret(conn, SECRET_TRANSLATOR_KEY, key)


app = FastAPI(title="Cyber_KaTockVocal", lifespan=lifespan)
app.include_router(router)


def _mount_frontend(application: FastAPI) -> None:
    dist = ensure_config().root_path / "frontend" / "dist"
    if not dist.is_dir():
        return
    application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


_mount_frontend(app)
