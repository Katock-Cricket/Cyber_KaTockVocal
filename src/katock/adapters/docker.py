"""Docker Desktop 拉起与就绪探测。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from katock.adapters.proc import creation_flags, run_cmd


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    level: str
    detail: str


class DockerAdapter:
    def __init__(self, desktop_path: str) -> None:
        self.desktop_path = desktop_path

    def probe(self) -> CheckResult:
        desktop = Path(self.desktop_path)
        if not desktop.is_file():
            return CheckResult(False, "error", f"找不到 Docker Desktop：{desktop}")
        try:
            result = run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=8)
        except subprocess.TimeoutExpired:
            return CheckResult(False, "error", "命令超时：docker info")
        except FileNotFoundError:
            return CheckResult(False, "error", "找不到 docker 命令，请确认 Docker Desktop 已安装")
        version = result.stdout.strip()
        if result.code == 0 and version:
            return CheckResult(True, "ok", f"守护进程已就绪，服务端版本 {version}")
        detail = result.text or "守护进程没有响应"
        return CheckResult(False, "error", f"docker info 失败：{detail[:400]}")

    def launch(self) -> None:
        desktop = Path(self.desktop_path)
        if not desktop.is_file():
            raise FileNotFoundError(f"找不到 Docker Desktop：{desktop}")
        subprocess.Popen(  # noqa: S603
            [str(desktop)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags() | getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
        )
