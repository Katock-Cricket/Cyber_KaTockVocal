"""启动时体检。Docker 等待单独计时，其余检查并行返回。"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path

from katock.adapters.docker import DockerAdapter
from katock.adapters.ffmpeg import Ffmpeg
from katock.adapters.proc import run_cmd
from katock.adapters.separator import Separator
from katock.adapters.wrapper import WrapperAdapter
from katock.config import AppConfig
from katock.storage.db import session
from katock.storage.fsops import same_volume
from katock.storage.repo import emit_event, upsert_env


class HealthService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(30)

    async def run_once(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            await asyncio.gather(
                self._docker_stack(),
                self._mp4box(),
                self._ffmpeg(),
                self._separator(),
                self._output(),
                self._disk(),
            )

    def _write(self, item: str, ok: bool, level: str, detail: str) -> None:
        with session(self.config.db_path) as conn:
            upsert_env(conn, item, ok, level, detail)
            emit_event(conn, "health", {"item": item, "ok": ok, "level": level, "detail": detail})

    async def _docker_stack(self) -> None:
        docker = DockerAdapter(self.config.docker_desktop)
        probe = await asyncio.to_thread(docker.probe)
        if not probe.ok:
            self._write("docker", False, "wait", "正在启动 Docker（预计 30~60 秒）")
            try:
                await asyncio.to_thread(docker.launch)
            except FileNotFoundError as exc:
                self._write("docker", False, "error", str(exc))
                self._write("wrapper", False, "error", "Docker 未就绪，Wrapper 无法检查")
                self._write("wrapper_ports", False, "error", "Docker 未就绪，端口无法检查")
                self._write("wrapper_login", False, "warn", "Docker 未就绪，需稍后登录")
                return
            started = time.monotonic()
            while time.monotonic() - started < 120:
                await asyncio.sleep(2)
                probe = await asyncio.to_thread(docker.probe)
                waited = int(time.monotonic() - started)
                if probe.ok:
                    self._write("docker", True, "ok", f"{probe.detail}，冷启动用了 {waited} 秒")
                    break
                self._write("docker", False, "wait", f"正在启动 Docker，已等待 {waited} 秒")
            else:
                self._write(
                    "docker",
                    False,
                    "error",
                    "Docker 启动失败，已超过 120 秒。可点「重新拉起」或查看 Docker 日志。",
                )
                self._write("wrapper", False, "error", "Docker 未就绪")
                self._write("wrapper_ports", False, "error", "Docker 未就绪")
                self._write("wrapper_login", False, "warn", "Docker 未就绪")
                return
        else:
            self._write("docker", True, "ok", probe.detail)
        await self._wrapper()

    async def _wrapper(self) -> None:
        wrapper = WrapperAdapter(self.config.wrapper_dir)
        up = await asyncio.to_thread(wrapper.ensure_up)
        if not up.ok:
            self._write("wrapper", False, "error", up.detail)
            self._write("wrapper_ports", False, "error", "容器未就绪，端口无法检查")
            self._write("wrapper_login", False, "warn", "需重新登录 Apple ID")
            return
        running = await asyncio.to_thread(wrapper.container_running)
        detail = "容器正在运行" if running else up.detail
        self._write("wrapper", running, "ok" if running else "error", detail or "容器状态未知")
        ports = await asyncio.to_thread(wrapper.ports)
        self._write("wrapper_ports", ports.ok, "ok" if ports.ok else "error", ports.detail)
        login = await asyncio.to_thread(wrapper.login_state)
        self._write(
            "wrapper_login",
            login.ok,
            "ok" if login.ok else "warn",
            login.detail,
        )

    async def _mp4box(self) -> None:
        path = self.config.mp4box_path
        if not path.is_file():
            self._write("mp4box", False, "error", f"找不到 MP4Box：{path}")
            return
        try:
            result = await asyncio.to_thread(run_cmd, [str(path), "-version"], 8)
        except subprocess.TimeoutExpired:
            self._write("mp4box", False, "error", f"命令超时：{path} -version")
            return
        if result.code != 0:
            self._write("mp4box", False, "error", f"{path} -version 失败：{result.text[:240]}")
            return
        first = result.stdout.splitlines()[0] if result.stdout else "MP4Box"
        self._write("mp4box", True, "ok", f"{first}（{path}）")

    async def _ffmpeg(self) -> None:
        tool = Ffmpeg(self.config.ffmpeg_path, self.config.ffprobe_path)
        try:
            line = await asyncio.to_thread(tool.version)
        except Exception as exc:
            self._write("ffmpeg", False, "error", str(exc))
            return
        self._write("ffmpeg", True, "ok", f"{line}（{self.config.ffmpeg_path}）")

    async def _separator(self) -> None:
        separator = Separator(self.config.separator_path, self.config.models_dir)
        missing = separator.models_present(
            [
                self.config.pass1_model,
                self.config.pass2_model,
                self.config.pass1_yaml,
                self.config.pass2_yaml,
            ]
        )
        if missing:
            listed = "、".join(missing)
            self._write(
                "separator",
                False,
                "error",
                f"模型目录 {self.config.models_dir} 缺少：{listed}",
            )
            return
        try:
            version = await asyncio.to_thread(separator.version)
        except Exception as exc:
            self._write("separator", False, "error", str(exc))
            return
        self._write("separator", True, "ok", f"{version}；模型目录 {self.config.models_dir}")

    async def _output(self) -> None:
        root = Path(self.config.output_root)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".katock-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            self._write("output_root", False, "error", f"输出目录不可写：{root}（{exc}）")
            return
        if not same_volume(root, self.config.work_dir):
            self._write(
                "output_root",
                False,
                "error",
                f"输出目录 {root} 与工作目录 {self.config.work_dir} 不在同一磁盘，无法原子落盘",
            )
            return
        self._write("output_root", True, "ok", f"可写，且与工作目录同盘：{root}")

    async def _disk(self) -> None:
        root = Path(self.config.output_root)
        target = root if root.exists() else root.parent
        if not target.exists():
            self._write("disk", False, "error", f"无法检查磁盘空间：{root}")
            return
        usage = shutil.disk_usage(target)
        free_gb = usage.free / (1024**3)
        if free_gb < 1:
            self._write("disk", False, "error", f"剩余 {free_gb:.1f} GB，不足 1 GB，已禁止新任务")
            return
        if free_gb < 5:
            self._write("disk", True, "warn", f"剩余 {free_gb:.1f} GB，低于 5 GB")
            return
        self._write("disk", True, "ok", f"剩余 {free_gb:.1f} GB")

    def blockers(self) -> list[str]:
        with session(self.config.db_path) as conn:
            rows = conn.execute(
                "SELECT item, ok, level FROM env_status WHERE item IN ('output_root', 'disk')"
            ).fetchall()
        reasons = []
        for row in rows:
            if row["item"] == "output_root" and not row["ok"]:
                reasons.append("输出目录不可写")
            if row["item"] == "disk" and not row["ok"]:
                reasons.append("磁盘空间不足")
        if not os.access(self.config.output_root, os.W_OK):
            if "输出目录不可写" not in reasons:
                reasons.append("输出目录不可写")
        return reasons
