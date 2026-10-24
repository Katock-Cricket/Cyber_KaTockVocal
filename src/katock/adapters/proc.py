"""外部程序启动。参数列表传递，兼容中文路径。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcResult:
    code: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


def take_lines(pending: bytearray, *, final: bool) -> list[str]:
    """按换行或回车切分。进度条只回车不换行，不能交给 readline。"""
    lines: list[str] = []
    while True:
        newline = pending.find(b"\n")
        carriage = pending.find(b"\r")
        cuts = [index for index in (newline, carriage) if index >= 0]
        if not cuts:
            break
        cut = min(cuts)
        if pending[cut] == ord("\r") and cut + 1 >= len(pending) and not final:
            break
        raw = bytes(pending[:cut])
        drop = 1
        if pending[cut] == ord("\r") and cut + 1 < len(pending) and pending[cut + 1] == ord("\n"):
            drop = 2
        del pending[: cut + drop]
        if raw:
            lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
    if final and pending:
        text = bytes(pending).decode("utf-8", errors="replace").rstrip("\r\n")
        pending.clear()
        if text:
            lines.append(text)
    elif len(pending) > 1_048_576:
        lines.append(bytes(pending).decode("utf-8", errors="replace"))
        pending.clear()
    return lines


def creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_cmd(
    args: list[str],
    timeout: float,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> ProcResult:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        timeout=timeout,
        check=False,
        creationflags=creation_flags(),
    )
    return ProcResult(
        code=completed.returncode,
        stdout=completed.stdout.decode("utf-8", errors="replace"),
        stderr=completed.stderr.decode("utf-8", errors="replace"),
    )


async def stream_cmd(
    args: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    on_line: Callable[[str], Awaitable[None]] | None = None,
    timeout: float | None = None,
) -> ProcResult:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=creation_flags(),
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def _read(stream: asyncio.StreamReader | None, bucket: list[str]) -> None:
        if stream is None:
            return
        pending = bytearray()

        async def emit(final: bool) -> None:
            for line in take_lines(pending, final=final):
                bucket.append(line)
                if on_line is not None:
                    await on_line(line)

        while True:
            chunk = await stream.read(65536)
            if not chunk:
                await emit(True)
                break
            pending.extend(chunk)
            await emit(False)

    async def _wait() -> int:
        assert process.stdout is not None
        assert process.stderr is not None
        await asyncio.gather(
            _read(process.stdout, stdout_lines), _read(process.stderr, stderr_lines)
        )
        return await process.wait()

    try:
        code = await asyncio.wait_for(_wait(), timeout) if timeout else await _wait()
    except TimeoutError:
        await kill_tree(process.pid)
        raise
    return ProcResult(code=code, stdout="\n".join(stdout_lines), stderr="\n".join(stderr_lines))


async def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/F",
            "/T",
            "/PID",
            str(pid),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
        await killer.wait()
        return
    try:
        process = await asyncio.create_subprocess_exec("kill", "-TERM", str(pid))
        await process.wait()
    except ProcessLookupError:
        return
