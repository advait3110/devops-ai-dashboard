"""
Safe helper for running real DevOps CLIs (docker, kubectl, journalctl, wevtutil).

Design decisions:
* Commands are passed as a LIST, never as one string, and shell=False.
  The OS receives arguments directly, so user input can never be interpreted
  as shell syntax (no command injection through ";", "&&", "|", ...).
* subprocess.run() is executed in a worker thread (asyncio.to_thread) so a slow
  command never blocks the FastAPI event loop. This also works on Windows with
  every asyncio event-loop type (asyncio's own subprocess API does not).
* Every command has a timeout so a hung tool cannot hang the dashboard.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class CommandError(Exception):
    """Raised when a command is missing, fails or times out."""


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _run_sync(cmd: list[str], timeout: float, merge_stderr: bool) -> str:
    if not tool_available(cmd[0]):
        raise CommandError(f"'{cmd[0]}' is not installed or not on PATH")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"'{' '.join(cmd[:3])}' timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise CommandError(str(exc)) from exc

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        message = stderr.strip() or stdout.strip() or f"exit code {proc.returncode}"
        raise CommandError(message.splitlines()[-1][:500])
    if merge_stderr and stderr:
        return stdout + stderr
    return stdout


async def run(cmd: list[str], timeout: float = 20, merge_stderr: bool = False) -> str:
    """Run a command asynchronously and return its stdout as text."""
    return await asyncio.to_thread(_run_sync, cmd, timeout, merge_stderr)
