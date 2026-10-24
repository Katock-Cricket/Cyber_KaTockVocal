"""Wrapper 容器、端口与 Apple 登录。"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path

from katock.adapters.docker import CheckResult
from katock.adapters.proc import run_cmd

_CONTAINER_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DATA_REL = Path("rootfs/data/data/com.apple.android.music/files")


class WrapperAdapter:
    def __init__(self, wrapper_dir: str) -> None:
        self.wrapper_dir = Path(wrapper_dir)

    def _compose(
        self, *args: str, timeout: float = 60, env: dict[str, str] | None = None
    ) -> CheckResult:
        if not (self.wrapper_dir / "compose.yaml").is_file():
            return CheckResult(False, "error", f"找不到 compose.yaml：{self.wrapper_dir}")
        try:
            result = run_cmd(
                ["docker", "compose", *args],
                timeout=timeout,
                cwd=self.wrapper_dir,
                env=env,
            )
        except FileNotFoundError:
            return CheckResult(False, "error", "找不到 docker 命令")
        if result.code != 0:
            return CheckResult(
                False, "error", f"docker compose {' '.join(args)} 失败：{result.text[:500]}"
            )
        return CheckResult(True, "ok", result.text[:500] or "完成")

    def container_id(self) -> str | None:
        result = run_cmd(
            ["docker", "compose", "ps", "-a", "--format", "{{.ID}}"],
            timeout=20,
            cwd=self.wrapper_dir,
        )
        if result.code != 0:
            return None
        for line in result.stdout.splitlines():
            candidate = line.strip()
            if candidate:
                return candidate
        return None

    def container_running(self) -> bool:
        result = run_cmd(
            ["docker", "compose", "ps", "--status", "running", "--format", "{{.ID}}"],
            timeout=20,
            cwd=self.wrapper_dir,
        )
        return result.code == 0 and bool(result.stdout.strip())

    def ensure_up(self, username: str | None = None, password: str | None = None) -> CheckResult:
        import os

        env = os.environ.copy()
        if username:
            env["USERNAME"] = username
        if password:
            env["PASSWORD"] = password
        if not self.container_running():
            started = self._compose("up", "-d", timeout=180, env=env)
            if not started.ok and "no such image" in started.detail.lower():
                built = self._compose("build", timeout=1800, env=env)
                if not built.ok:
                    return built
                started = self._compose("up", "-d", timeout=180, env=env)
            return started
        return CheckResult(True, "ok", "Wrapper 容器正在运行")

    def ports(self) -> CheckResult:
        failed: list[str] = []
        for port in (10020, 20020):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    continue
            except OSError as exc:
                failed.append(f"{port}（{exc}）")
        if failed:
            return CheckResult(False, "error", "端口不可达：" + "，".join(failed))
        return CheckResult(True, "ok", "10020 与 20020 可连通")

    def logs(self, tail: int = 80) -> str:
        container = self.container_id()
        if not container or not _CONTAINER_OK.match(container):
            return ""
        result = run_cmd(["docker", "logs", "--tail", str(tail), container], timeout=20)
        return result.text

    def login_state(self) -> CheckResult:
        text = self.logs(120).lower()
        if "listening" in text and "10020" in text:
            return CheckResult(True, "ok", "Wrapper 已监听 10020，登录态可用")
        if "2fa" in text or "verification code" in text or "security code" in text:
            return CheckResult(False, "warn", "需要 2FA 验证码")
        if "login required" in text or "username and password" in text:
            return CheckResult(False, "warn", "需重新登录 Apple ID")
        if not self.container_running():
            return CheckResult(False, "warn", "Wrapper 容器未运行，需重新登录 Apple ID")
        return CheckResult(False, "warn", "尚未看到 listening，请查看容器日志")

    def write_2fa(self, code: str) -> CheckResult:
        if not re.fullmatch(r"\d{6}", code):
            return CheckResult(False, "error", "验证码必须是 6 位数字")
        container = self.container_id()
        if not container or not _CONTAINER_OK.match(container):
            return CheckResult(False, "error", "找不到正在运行的 Wrapper 容器")
        target = "/app/rootfs/data/data/com.apple.android.music/files/2fa.txt"
        result = run_cmd(
            ["docker", "exec", container, "sh", "-c", f"echo -n '{code}' > {target}"],
            timeout=20,
        )
        if result.code != 0:
            return CheckResult(False, "error", f"写入验证码失败：{result.text[:300]}")
        return CheckResult(True, "ok", "验证码已写入容器")

    def reset_login_files(self) -> None:
        files = self.wrapper_dir / _DATA_REL
        twofa = files / "2fa.txt"
        if twofa.exists():
            twofa.unlink()
        db_dir = files / "mpl_db"
        if db_dir.exists():
            import shutil

            shutil.rmtree(db_dir, ignore_errors=True)

    def restart(self) -> CheckResult:
        stopped = self._compose("down", timeout=60)
        if not stopped.ok:
            return stopped
        return self._compose("up", "-d", timeout=180)

    def describe_ps(self) -> str:
        result = run_cmd(["docker", "compose", "ps", "-a"], timeout=20, cwd=self.wrapper_dir)
        if result.code != 0:
            return result.text[:500]
        try:
            parsed = json.loads(result.stdout) if result.stdout.strip().startswith("{") else None
        except json.JSONDecodeError:
            parsed = None
        return (json.dumps(parsed, ensure_ascii=False) if parsed else result.stdout)[:500]
