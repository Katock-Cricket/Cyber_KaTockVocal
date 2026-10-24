"""拉起并守住工作进程。退出时不改 Docker 的运行状态。"""

from __future__ import annotations

import asyncio
import subprocess
import sys

from katock.adapters.proc import creation_flags, kill_tree
from katock.config import AppConfig
from katock.logging_setup import logger
from katock.storage.db import session
from katock.storage.repo import enqueue_command


class Supervisor:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self._watch: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._spawn()
        self._watch = asyncio.create_task(self._loop())

    def _spawn(self) -> None:
        self.process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "katock.worker"],
            cwd=str(self.config.root_path),
            creationflags=creation_flags(),
        )
        logger().info("工作进程已启动 pid=%s", self.process.pid)

    async def _loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(2)
            process = self.process
            if process is not None and process.poll() is not None and not self._stopping:
                logger().warning("工作进程退出 code=%s，5 秒后重启", process.returncode)
                await asyncio.sleep(5)
                if not self._stopping:
                    self._spawn()

    async def stop(self) -> None:
        self._stopping = True
        if self._watch:
            self._watch.cancel()
            await asyncio.gather(self._watch, return_exceptions=True)
        with session(self.config.db_path) as conn:
            enqueue_command(conn, "shutdown", {})
        process = self.process
        if process is None or process.poll() is not None:
            return
        for _ in range(8):
            await asyncio.sleep(1)
            if process.poll() is not None:
                return
        await kill_tree(process.pid)
