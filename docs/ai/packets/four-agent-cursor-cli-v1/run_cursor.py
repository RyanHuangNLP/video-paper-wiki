#!/usr/bin/env python3
"""Run one pinned Cursor CLI lane with append-only evidence.

This module deliberately has no executable override in its command-line
interface.  The small dependency-injection seams on ``run_attempt`` and
``build_argv`` are for the local harmless-stub check only; a real invocation
always uses the pinned executable, root, source directory, and model ID.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Callable, Mapping, Sequence


# These values are intentionally absolute and stable.  A different checkout
# must not silently become the source of a lane's evidence.
PINNED_ROOT = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
ROOT = PINNED_ROOT
PINNED_EXECUTABLE = Path("/Users/huangzhanpeng/.local/bin/agent")
REQUESTED_MODEL = "cursor-grok-4.6-xhigh-fast"
# Exact ID/display-name pair observed in this account catalog and runtime init.
# Do not normalize or accept partial/generic model names. Raw observations stay intact.
VERIFIED_MODEL_NAMES = frozenset({REQUESTED_MODEL, "Cursor Grok 4.6 Extra High Fast"})
EVIDENCE_ROOT = ROOT / "artifacts/verification/manual-pdf-v1/lightweight-workflow-v2"
INTERRUPTION_GRACE_SECONDS = 30.0
CHILD_REAP_TIMEOUT_SECONDS = 30.0
READER_JOIN_TIMEOUT_SECONDS = 10.0
LANE_SOURCES = {
    1: ROOT / ".work/parallel/lightweight-workflow-v2/terminal-1/source",
    2: ROOT / ".work/parallel/lightweight-workflow-v2/terminal-2/source",
    3: ROOT / ".work/parallel/lightweight-workflow-v2/terminal-3/source",
    4: ROOT / ".work/parallel/lightweight-workflow-v2/terminal-4/source",
}


class RunnerError(RuntimeError):
    """A controlled runner failure that can be included in final evidence."""


class LeaseConflict(RunnerError):
    """The lane already has an active lease."""


def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_bytes(path: Path, data: bytes) -> None:
    """Create a file exactly once and fail rather than overwrite anything."""

    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_new_bytes(path, data)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _safe_component(value: str, field: str) -> str:
    # Controller and chat IDs are argv/JSON values, not path components.  Keep
    # opaque IDs exact; only reject values that cannot safely be an argv item.
    if not value or value in {".", ".."} or "\x00" in value:
        raise RunnerError(f"invalid {field}")
    return value


def _new_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f"Z-{uuid.uuid4().hex}"


def _new_attempt_dir(lane: int) -> tuple[str, Path]:
    controller_root = EVIDENCE_ROOT / f"terminal-{lane}" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    # UUID makes collisions vanishingly unlikely; mkdir without exist_ok is
    # still the authoritative collision check and never overwrites a run.
    for _ in range(20):
        run_id = _new_run_id()
        attempt = controller_root / run_id
        try:
            attempt.mkdir()
        except FileExistsError:
            continue
        return run_id, attempt
    raise RunnerError("could not allocate a unique evidence directory")


def _source_identity(lane: int) -> dict[str, Any]:
    source = LANE_SOURCES[lane]
    if not source.is_dir():
        raise RunnerError(f"pinned lane source does not exist: {source}")
    resolved = source.resolve(strict=True)
    expected = PINNED_ROOT.joinpath(".work", "parallel", "lightweight-workflow-v2", f"terminal-{lane}", "source").resolve(
        strict=True
    )
    if resolved != expected:
        raise RunnerError(f"lane source realpath drifted: {resolved}")
    stat = resolved.stat()
    return {
        "source": str(source),
        "source_realpath": str(resolved),
        "source_dev": int(stat.st_dev),
        "source_ino": int(stat.st_ino),
    }


class LaneLease:
    """Exclusive per-lane lease with immutable identity and append-only events."""

    def __init__(self, lane: int, run_id: str, controller_id: str, attempt: Path, source: Mapping[str, Any]) -> None:
        self.lane = lane
        self.run_id = run_id
        self.controller_id = controller_id
        self.attempt = attempt
        self.path = EVIDENCE_ROOT / f"terminal-{lane}" / "controller" / "active-lease"
        self.identity_path = self.path / "lease.json"
        self.events_path = self.path / "events.jsonl"
        self.identity: dict[str, Any] = {
            "schema": "cursor-lane-lease-v1",
            "lane": lane,
            "controller_id": controller_id,
            "run_id": run_id,
            "runner_pid": os.getpid(),
            "created_at": _utc_now(),
            **source,
        }
        self._owned = False
        self._event_lock = threading.Lock()

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # mkdir is the atomic ownership operation.  Existing stale or
            # unknown content is never inspected for automatic deletion.
            self.path.mkdir()
        except FileExistsError as exc:
            raise LeaseConflict(f"lane {self.lane} has an active lease: {self.path}") from exc
        try:
            _write_new_json(self.identity_path, self.identity)
            _write_new_bytes(self.events_path, b"")
        except Exception:
            # Preserve a partially-created lease for explicit controller
            # recovery; this runner must never remove unknown state.
            raise
        self._owned = True
        self.event("lease_acquired")

    def event(self, event: str, **fields: Any) -> bool:
        # A failed mkdir means this object never owns the lane.  In
        # particular, a conflict attempt must never append to the existing
        # owner's event stream during finalization.
        if not self._owned:
            return False
        payload: dict[str, Any] = {"at": _utc_now(), "event": event, "run_id": self.run_id}
        payload.update(fields)
        with self._event_lock:
            _append_jsonl(self.events_path, payload)
        return True

    def release(self) -> bool:
        """Remove only this runner's empty, known lease after finalization."""

        if not self._owned:
            return False
        try:
            current = json.loads(self.identity_path.read_text(encoding="utf-8"))
            if current != self.identity:
                return False
            names = {entry.name for entry in self.path.iterdir()}
            if names != {"lease.json", "events.jsonl"}:
                return False
            self.identity_path.unlink()
            self.events_path.unlink()
            self.path.rmdir()
        except (FileNotFoundError, OSError, ValueError):
            return False
        self._owned = False
        return True


class _Observations:
    _RUNTIME_EVENT_TYPES = frozenset(
        {"system", "init", "model_init", "session_init", "chat_started", "session_started"}
    )

    def __init__(self, lease: LaneLease) -> None:
        self.lease = lease
        self.lock = threading.Lock()
        self.models: list[str] = []
        self.sessions: list[str] = []
        self.last_type: str | None = None
        self.lines = 0

    @staticmethod
    def _top_level_values(payload: Mapping[str, Any], names: tuple[str, ...]) -> list[str]:
        # Cursor's runtime envelope carries these identifiers at the event's
        # top level.  Never recurse into tool arguments/results: those may
        # contain arbitrary user strings that are not runtime observations.
        return [
            value
            for name in names
            if isinstance(value := payload.get(name), str) and value
        ]

    def observe_line(self, line: bytes) -> None:
        self.lines += 1
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, Mapping):
            return
        event_type = payload.get("type")
        if event_type not in self._RUNTIME_EVENT_TYPES:
            return
        with self.lock:
            if isinstance(event_type, str) and event_type:
                self.last_type = event_type
            for model in self._top_level_values(payload, ("model", "model_id", "modelId")):
                if model not in self.models:
                    self.models.append(model)
                    self.lease.event("model_observed", observed_model=model)
                    print(f"cursor-run observed model={model}", flush=True)
            for session in self._top_level_values(payload, ("session_id", "sessionId", "chat_id", "chatId")):
                if session not in self.sessions:
                    self.sessions.append(session)
                    self.lease.event("session_observed", observed_session_id=session)
                    print(f"cursor-run observed session={session}", flush=True)


def build_argv(
    lane: int,
    prompt_text: str,
    resume: str | None = None,
    *,
    executable: Path = PINNED_EXECUTABLE,
    workspace: Path | None = None,
) -> list[str]:
    """Build the exact argv; ``executable``/``workspace`` are test seams only."""

    if lane not in LANE_SOURCES:
        raise RunnerError("lane must be 1, 2, 3, or 4")
    if "\x00" in prompt_text:
        raise RunnerError("prompt contains a NUL byte")
    argv = [
        str(executable),
        "--print",
        "--output-format",
        "stream-json",
        "--auto-review",
        "--workspace",
        str(workspace or LANE_SOURCES[lane]),
        "--model",
        REQUESTED_MODEL,
    ]
    if resume is not None:
        _safe_component(resume, "resume chat ID")
        argv.extend(("--resume", resume))
    argv.append(prompt_text)
    return argv


def _copy_prompt(prompt_file: Path, destination: Path) -> tuple[int, str]:
    if not prompt_file.is_absolute():
        raise RunnerError("--prompt-file must be an absolute path")
    if not prompt_file.is_file():
        raise RunnerError(f"prompt file is not a regular file: {prompt_file}")
    data = prompt_file.read_bytes()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunnerError("prompt file must be UTF-8") from exc
    _write_new_bytes(destination, data)
    return len(data), _sha256_bytes(data)


def _append_log(path: Path, data: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()


def _reader(stream: Any, log_path: Path, observations: _Observations | None, stdout: bool) -> None:
    try:
        while True:
            chunk = stream.readline()
            if chunk in (b"", ""):
                break
            if isinstance(chunk, str):
                raw = chunk.encode("utf-8", "replace")
            else:
                raw = bytes(chunk)
            _append_log(log_path, raw)
            if stdout and observations is not None:
                observations.observe_line(raw)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _progress(attempt: Path, child_pid: int, observations: _Observations, state: str) -> None:
    detail = observations.last_type or "no-json-event"
    print(
        f"cursor-run state={state} pid={child_pid} run_dir={attempt} events={observations.lines} last={detail}",
        flush=True,
    )


def _signal_child(child: Any, signum: int, lease: LaneLease) -> bool:
    # Popen owns the child handle.  poll() prevents signalling an exited PID
    # that could have been recycled by the operating system.
    try:
        if child.poll() is None:
            child.send_signal(signum)
            lease.event("child_signalled", signal=signal.Signals(signum).name)
            return True
    except (OSError, ValueError):
        return False
    return False


def run_attempt(
    *,
    lane: int,
    prompt_file: Path,
    resume: str | None = None,
    controller_id: str | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    executable: Path = PINNED_EXECUTABLE,
    workspace: Path | None = None,
    progress_interval: float = 5.0,
) -> dict[str, Any]:
    """Run one attempt and return its final evidence object.

    ``popen_factory``, ``executable``, and ``workspace`` are intentionally
    injectable only for the harmless local stub check.  ``main`` never exposes
    those seams and always uses the pinned values.
    """

    if lane not in LANE_SOURCES:
        raise RunnerError("lane must be 1, 2, 3, or 4")
    source_identity = _source_identity(lane)
    controller = controller_id or os.environ.get("CURSOR_CONTROLLER_ID") or f"lane-{lane}-controller"
    _safe_component(controller, "controller identifier")
    if resume is not None:
        _safe_component(resume, "resume chat ID")
    run_id, attempt = _new_attempt_dir(lane)
    stdout_path = attempt / "stdout.jsonl"
    stderr_path = attempt / "stderr.log"
    metadata_path = attempt / "metadata.json"
    final_path = attempt / "final.json"
    prompt_copy_path = attempt / "prompt.txt"
    _write_new_bytes(stdout_path, b"")
    _write_new_bytes(stderr_path, b"")
    prompt_size, prompt_sha = _copy_prompt(prompt_file, prompt_copy_path)

    actual_workspace = workspace or LANE_SOURCES[lane]
    argv = build_argv(lane, prompt_copy_path.read_text(encoding="utf-8"), resume, executable=executable, workspace=actual_workspace)
    display_argv = argv[:-1] + ["<prompt>"]
    lease = LaneLease(lane, run_id, controller, attempt, source_identity)
    metadata: dict[str, Any] = {
        "schema": "cursor-lane-run-metadata-v1",
        "run_id": run_id,
        "lane": lane,
        "controller_id": controller,
        "root": str(ROOT),
        "evidence_root": str(EVIDENCE_ROOT),
        "source": source_identity,
        "executable": str(executable),
        "workspace": str(actual_workspace),
        "requested_model": REQUESTED_MODEL,
        "resume_chat_id": resume,
        "argv_without_prompt": display_argv,
        "prompt_file": str(prompt_file),
        "prompt_copy": str(prompt_copy_path),
        "prompt_bytes": prompt_size,
        "prompt_sha256": prompt_sha,
        "runner_pid": os.getpid(),
        "started_at": _utc_now(),
    }
    _write_new_json(metadata_path, metadata)

    child: Any = None
    observations = _Observations(lease)
    interrupted = {"signal": None}
    previous_handlers: dict[int, Any] = {}
    threads: list[threading.Thread] = []
    status = "launch_error"
    exit_code: int | None = None
    error: str | None = None
    child_pid: int | None = None
    child_wait_timed_out = False
    reader_threads_alive = False
    started_at = metadata["started_at"]
    try:
        lease.acquire()
        def on_signal(signum: int, _frame: Any) -> None:
            if interrupted["signal"] is None:
                interrupted["signal"] = signal.Signals(signum).name
                lease.event("runner_interrupted", signal=interrupted["signal"])
            if child is not None:
                _signal_child(child, signum, lease)

        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, on_signal)

        lease.event("launching", requested_model=REQUESTED_MODEL, argv_without_prompt=display_argv)
        child = popen_factory(
            argv,
            cwd=str(actual_workspace),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        child_pid = int(child.pid)
        lease.event("child_started", child_pid=child_pid)
        print(f"cursor-run started run_dir={attempt} pid={child_pid}", flush=True)
        threads = [
            threading.Thread(target=_reader, args=(child.stdout, stdout_path, observations, True), daemon=True),
            threading.Thread(target=_reader, args=(child.stderr, stderr_path, None, False), daemon=True),
        ]
        for thread in threads:
            thread.start()

        last_progress = 0.0
        interrupt_deadline: float | None = None
        while child.poll() is None:
            now = time.monotonic()
            if interrupted["signal"] and interrupt_deadline is None:
                interrupt_deadline = now + INTERRUPTION_GRACE_SECONDS
            if interrupt_deadline is not None and now >= interrupt_deadline:
                child_wait_timed_out = True
                error = f"owned child did not exit after {interrupted['signal']}"
                break
            if now - last_progress >= progress_interval:
                _progress(attempt, child_pid, observations, "running")
                last_progress = now
            time.sleep(min(0.25, max(progress_interval / 20.0, 0.05)))
        if not child_wait_timed_out:
            exit_code = int(child.wait())
        reader_join_timeout = 0.0 if child_wait_timed_out else READER_JOIN_TIMEOUT_SECONDS
        for thread in threads:
            thread.join(timeout=reader_join_timeout)
        reader_threads_alive = any(thread.is_alive() for thread in threads)
        if reader_threads_alive:
            raise RunnerError("child output reader did not finish")
        if not child_wait_timed_out:
            lease.event("child_exited", child_pid=child_pid, exit_code=exit_code)
            status = "interrupted" if interrupted["signal"] else ("succeeded" if exit_code == 0 else "failed")
    except LeaseConflict as exc:
        error = str(exc)
        status = "lease_conflict"
    except Exception as exc:  # final evidence still records controlled launch/runtime failures
        error = f"{type(exc).__name__}: {exc}"
        status = "interrupted" if interrupted["signal"] else status
    finally:
        for signum, previous in previous_handlers.items():
            try:
                signal.signal(signum, previous)
            except (ValueError, OSError):
                pass

    if child is not None and exit_code is None and not child_wait_timed_out:
        # A runtime exception should not leave a running owned child.  The
        # only signal path is still the Popen-owned handle, never a raw PID.
        _signal_child(child, signal.SIGTERM, lease)
        try:
            exit_code = int(child.wait(timeout=CHILD_REAP_TIMEOUT_SECONDS))
        except subprocess.TimeoutExpired:
            error = (error + "; " if error else "") + "owned child did not exit after SIGTERM"
            child_wait_timed_out = True
        reader_join_timeout = 0.0 if child_wait_timed_out else READER_JOIN_TIMEOUT_SECONDS
        for thread in threads:
            thread.join(timeout=reader_join_timeout)
        reader_threads_alive = any(thread.is_alive() for thread in threads)
    if child is not None and exit_code is not None:
        child_pid = int(child.pid)

    child_alive = bool(child is not None and child.poll() is None)
    if child_wait_timed_out or child_alive or reader_threads_alive:
        incomplete_path = attempt / "incomplete.json"
        incomplete_blockers = [
            reason
            for reason, condition in (
                ("owned_child_live", child_alive),
                ("child_exit_timeout", child_wait_timed_out),
                ("reader_threads_live", reader_threads_alive),
                ("logs_not_finalized", True),
            )
            if condition
        ]
        incomplete: dict[str, Any] = {
            "schema": "cursor-lane-run-incomplete-v1",
            "run_id": run_id,
            "lane": lane,
            "controller_id": controller,
            "attempt_dir": str(attempt),
            "lease_path": str(lease.path),
            "runner_pid": os.getpid(),
            "child_pid": child_pid,
            "status": "incomplete_live",
            "exit_code": exit_code,
            "interrupted_signal": interrupted["signal"],
            "requested_model": REQUESTED_MODEL,
            "observed_model": observations.models[0] if observations.models else None,
            "observed_session_id": observations.sessions[0] if observations.sessions else None,
            "model_observation": "observed" if observations.models else "unknown",
            "session_observation": "observed" if observations.sessions else "unknown",
            "run_verified": False,
            "architect_accepted": False,
            "verification_blockers": incomplete_blockers,
            "logs_finalized": False,
            "metadata_sha256": _sha256_file(metadata_path),
            "prompt_sha256": _sha256_file(prompt_copy_path),
            "recorded_at": _utc_now(),
            "error": error,
        }
        try:
            _write_new_json(incomplete_path, incomplete)
        except Exception as exc:
            incomplete["record_error"] = f"{type(exc).__name__}: {exc}"
        lease.event("incomplete", **incomplete)
        # Never hash moving logs, write final.json, or release active-lease
        # while the child or an output reader is still live.
        print(f"cursor-run incomplete run_dir={attempt} blockers={incomplete_blockers}", flush=True)
        return incomplete

    # Compute observations only from parsed stream-json events; missing values
    # remain absent/null and can never be promoted to acceptance claims.
    observed_model = observations.models[0] if observations.models else None
    observed_session = observations.sessions[0] if observations.sessions else None
    model_mismatch = bool(observations.models) and any(model not in VERIFIED_MODEL_NAMES for model in observations.models)
    run_verified = bool(
        status == "succeeded"
        and exit_code == 0
        and observed_model in VERIFIED_MODEL_NAMES
        and not model_mismatch
    )
    finished_at = _utc_now()
    if error is not None:
        lease_event_error = {"error": error}
    else:
        lease_event_error = {}
    try:
        lease.event("finalizing", status=status, exit_code=exit_code, **lease_event_error)
    except Exception:
        # If lease event writing is unavailable, preserve evidence and do not
        # attempt lease cleanup.
        error = (error + "; " if error else "") + "lease finalization event failed"
    hashes = {
        "stdout_jsonl_sha256": _sha256_file(stdout_path),
        "stderr_log_sha256": _sha256_file(stderr_path),
        "metadata_sha256": _sha256_file(metadata_path),
        "prompt_sha256": _sha256_file(prompt_copy_path),
    }
    final: dict[str, Any] = {
        "schema": "cursor-lane-run-final-v1",
        "run_id": run_id,
        "lane": lane,
        "controller_id": controller,
        "attempt_dir": str(attempt),
        "lease_path": str(lease.path),
        "runner_pid": os.getpid(),
        "child_pid": child_pid,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "exit_code": exit_code,
        "interrupted_signal": interrupted["signal"],
        "requested_model": REQUESTED_MODEL,
        "observed_model": observed_model,
        "observed_models": observations.models,
        "observed_session_id": observed_session,
        "observed_session_ids": observations.sessions,
        "model_mismatch": model_mismatch,
        "model_observation": "observed" if observed_model is not None else "unknown",
        "session_observation": "observed" if observed_session is not None else "unknown",
        "run_verified": run_verified,
        "architect_accepted": False,
        "verification_blockers": [
            reason
            for reason, condition in (
                ("nonzero_exit", exit_code != 0),
                ("interrupted", bool(interrupted["signal"])),
                ("model_not_observed", observed_model is None),
                ("model_mismatch", model_mismatch),
            )
            if condition
        ],
        "argv_without_prompt": display_argv,
        "prompt_sha256": prompt_sha,
        "hashes": hashes,
        "error": error,
    }
    _write_new_json(final_path, final)
    try:
        lease.event("logs_finalized", hashes=hashes, final_path=str(final_path))
    except Exception:
        pass
    if interrupted["signal"]:
        # An interrupted runner deliberately leaves active-lease for explicit
        # controller recovery after checking that the child is truly dead.
        pass
    else:
        try:
            if lease.release():
                print(f"cursor-run finalized run_dir={attempt} run_verified={run_verified}", flush=True)
        except OSError:
            pass
    return final


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", type=int, choices=sorted(LANE_SOURCES), required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--resume", metavar="CHAT_ID")
    parser.add_argument("--controller-id", "--controller", dest="controller_id")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        final = run_attempt(
            lane=args.lane,
            prompt_file=args.prompt_file,
            resume=args.resume,
            controller_id=args.controller_id,
            # No CLI switch reaches these values: production execution is
            # always pinned to the known executable and source workspace.
            executable=PINNED_EXECUTABLE,
            workspace=LANE_SOURCES[args.lane],
        )
    except (RunnerError, OSError) as exc:
        print(f"cursor-run refused: {exc}", file=sys.stderr, flush=True)
        return 2
    print(
        json.dumps(
            {
                "run_dir": final["attempt_dir"],
                "status": final["status"],
                "exit_code": final["exit_code"],
                "run_verified": final["run_verified"],
                "architect_accepted": final["architect_accepted"],
                "observed_model": final["observed_model"],
                "observed_session_id": final["observed_session_id"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if final["run_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
