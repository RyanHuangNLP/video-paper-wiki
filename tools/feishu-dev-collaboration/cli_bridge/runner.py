"""Bounded subprocess runner. argv/cwd/env come only from trusted callers."""

import asyncio
import os
import signal
import time
from dataclasses import dataclass
from typing import List, Mapping, Optional

from .constants import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_PROCESS_TIMEOUT_SEC,
    KILL_GRACE_SEC,
    STREAM_CHUNK_BYTES,
)
from .models import (
    KIND_CANCELLED,
    KIND_EMPTY,
    KIND_MAX_TURNS,
    KIND_NONZERO,
    KIND_OK,
    KIND_OVERFLOW,
    KIND_TIMEOUT,
    ClientResult,
)

MAX_TURNS_MARKERS = ("Max turns reached", "max turns reached")


@dataclass
class RunLimits:
    timeout_sec: float = DEFAULT_PROCESS_TIMEOUT_SEC
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES


class AsyncProcessRunner:
    def __init__(self, limits=None):
        self.limits = limits or RunLimits()
        self._proc = None
        self._pgid = None
        self._owned = False

    async def run(
        self,
        argv,
        cwd,
        env=None,
        stdin_bytes=None,
        merge_stderr=False,
    ):
        if not argv or not isinstance(argv, (list, tuple)):
            return ClientResult(kind=KIND_NONZERO, text="", extra={"reason": "argv"})
        trusted_env = {} if env is None else dict(env)
        deadline = time.monotonic() + float(self.limits.timeout_sec)

        def remaining():
            return max(0.01, deadline - time.monotonic())

        def timed_out():
            return time.monotonic() >= deadline

        try:
            self._proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *list(argv),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=trusted_env,
                    start_new_session=True,
                ),
                timeout=remaining(),
            )
        except asyncio.TimeoutError:
            return ClientResult(kind=KIND_TIMEOUT, text="", extra={"reason": "spawn_timeout"})
        except Exception:
            return ClientResult(kind=KIND_NONZERO, text="", extra={"reason": "spawn"})
        try:
            self._pgid = os.getpgid(self._proc.pid)
        except OSError:
            self._pgid = None
        self._owned = True
        stdout_buf = bytearray()
        stderr_buf = bytearray()
        overflow = False

        async def _drain(stream, buf):
            nonlocal overflow
            while True:
                chunk = await stream.read(STREAM_CHUNK_BYTES)
                if not chunk:
                    return
                remaining = self.limits.max_output_bytes - (len(stdout_buf) + len(stderr_buf))
                if remaining <= 0:
                    overflow = True
                    return
                buf.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow = True
                    return


        async def _feed():
            if self._proc.stdin is None:
                return
            try:
                if stdin_bytes is not None:
                    self._proc.stdin.write(stdin_bytes)
                    await asyncio.wait_for(self._proc.stdin.drain(), timeout=remaining())
            except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError, Exception):
                pass
            finally:
                if self._proc.stdin:
                    self._proc.stdin.close()

        feed_task = asyncio.create_task(_feed())
        drain_task = asyncio.ensure_future(
            asyncio.gather(
                _drain(self._proc.stdout, stdout_buf),
                _drain(self._proc.stderr, stderr_buf),
                return_exceptions=True,
            )
        )
        wait_task = asyncio.create_task(self._proc.wait())
        try:
            while True:
                if timed_out():
                    await self.terminate_group()
                    return ClientResult(kind=KIND_TIMEOUT, text="", extra={"reason": "timeout"})
                if overflow:
                    await self.terminate_group()
                    return ClientResult(kind=KIND_OVERFLOW, text="", extra={"reason": "output_cap"})
                pending = {t for t in (feed_task, drain_task, wait_task) if not t.done()}
                if not pending:
                    break
                done, _ = await asyncio.wait(pending, timeout=min(0.05, remaining()), return_when=asyncio.FIRST_COMPLETED)
                if overflow:
                    await self.terminate_group()
                    return ClientResult(kind=KIND_OVERFLOW, text="", extra={"reason": "output_cap"})
                if timed_out():
                    await self.terminate_group()
                    return ClientResult(kind=KIND_TIMEOUT, text="", extra={"reason": "timeout"})
                if wait_task.done() and drain_task.done():
                    break
        except asyncio.CancelledError:
            await self.terminate_group()
            raise
        finally:
            for task in (feed_task, drain_task, wait_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(feed_task, drain_task, wait_task, return_exceptions=True)
        if overflow:
            return ClientResult(kind=KIND_OVERFLOW, text="", extra={"reason": "output_cap"})
        stdout = bytes(stdout_buf).decode("utf-8", errors="replace")
        stderr = bytes(stderr_buf).decode("utf-8", errors="replace")
        code = self._proc.returncode if self._proc.returncode is not None else 1
        combined = stdout
        if merge_stderr and stderr:
            combined = (stdout + "\n" + stderr).strip() + ("\n" if stdout or stderr else "")
            stdout = combined
        if any(m in stdout or m in stderr for m in MAX_TURNS_MARKERS):
            return ClientResult(
                kind=KIND_MAX_TURNS,
                text=stdout,
                exit_code=code,
                extra={"stderr_len": len(stderr)},
            )
        if code != 0:
            return ClientResult(
                kind=KIND_NONZERO,
                text="",
                exit_code=code,
                extra={"stderr_len": len(stderr)},
            )
        if not combined.strip():
            return ClientResult(kind=KIND_EMPTY, text="", exit_code=code)
        return ClientResult(kind=KIND_OK, text=combined, exit_code=code)

    async def terminate_group(self):
        proc = self._proc
        if proc is None and self._pgid is None:
            return
        pgid = self._pgid
        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGTERM)
            elif proc.returncode is None:
                proc.terminate()
        except OSError:
            pass
        try:
            if proc is not None:
                await asyncio.wait_for(proc.wait(), timeout=KILL_GRACE_SEC)
        except (asyncio.TimeoutError, ProcessLookupError):
            pass
        try:
            if pgid is not None and self._owned:
                os.killpg(pgid, signal.SIGKILL)
            elif proc is not None and proc.returncode is None:
                proc.kill()
        except OSError:
            pass
        try:
            if proc is not None:
                await asyncio.wait_for(proc.wait(), timeout=KILL_GRACE_SEC)
        except Exception:
            pass
        self._owned = False
        self._proc = None
        self._pgid = None
