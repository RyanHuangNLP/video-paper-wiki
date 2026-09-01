"""Pinned, read-only claude-obsidian transaction inspection adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.staging import StagingError, validate_batch_id
from video_paper_wiki.transaction_contracts import (
    _json_preflight,
    attach_upstream_inspection,
    validate_transaction,
)

AUTHORITY_SCHEMA = "video-paper-wiki.upstream-authority.v1"
PROFILE_NAME = "claude-obsidian-transaction-inspect-9f8c119-v1"
PROFILE_FILE = f"{PROFILE_NAME}.profile.json"
PROFILE_SHA256 = "776f6c4e0d6c327c3237dc1821628007a3d9082dca9e70511a81eee0f1e1f6a1"
SOURCE_SNAPSHOT_SHA256 = "94148615f5aec9c137a7b449d869de0ca2a85e92e10581eafb7de4f799a18c34"
UPSTREAM_COMMIT = "9f8c1199047eac2c3828496279fbb7ba9540b90b"
UPSTREAM_TREE = "b00665e266988fe99138e761dbbf4da04b2ddb5a"
UPSTREAM_VERSION = "2.1.1"

MAX_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_CONTENT_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 30
_HASH = re.compile(r"[0-9a-f]{64}")
_SOURCE_ID = re.compile(r"src-[0-9a-f]{20}")
_CAPTURED = re.compile(r"\.raw/captured/([0-9a-f]{64})\.[A-Za-z0-9][A-Za-z0-9._-]*")
_UPSTREAM_ERROR = re.compile(rb"ERR ([A-Z][A-Z0-9_]{0,63}): [^\r\n]*(?:\n)?")
_PLAN_FIELDS = frozenset({
    "schema", "operation_id", "operation_type", "valid", "changed_paths",
    "hashes", "modes", "input_bundle_sha256", "expanded_bundle_sha256",
    "vault_identity", "approval_sha256",
})


def _fail(code: str, message: str, *, exit_code: int = 2, details: dict[str, Any] | None = None) -> None:
    raise ContractError(code, message, details, exit_code=exit_code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(data: bytes, *, code: str, label: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        _fail(code, f"{label} is not strict UTF-8")
    duplicate = False

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        nonlocal duplicate
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                duplicate = True
            result[key] = value
        return result

    def no_float(_value: str) -> object:
        raise ValueError("floating-point JSON is forbidden")

    def bounded_int(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > 1024:
            raise ValueError("JSON integer is too large")
        return int(value)

    decoder = json.JSONDecoder(
        object_pairs_hook=pairs,
        parse_float=no_float,
        parse_int=bounded_int,
        parse_constant=no_float,
    )
    try:
        value, end = decoder.raw_decode(text)
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError):
        _fail(code, f"{label} is not strict JSON")
    if duplicate or any(character not in " \t\r\n" for character in text[end:]):
        _fail(code, f"{label} has duplicate keys or trailing data")
    return value


def _profile() -> tuple[bytes, dict[str, Any]]:
    raw = read_projection_resource_bytes("catalog", PROFILE_FILE)
    if raw is None or _sha(raw) != PROFILE_SHA256:
        _fail("UPSTREAM_PIN_MISMATCH", "packaged upstream profile differs")
    value = _strict_json(raw, code="UPSTREAM_PIN_MISMATCH", label="upstream profile")
    if not isinstance(value, dict):
        _fail("UPSTREAM_PIN_MISMATCH", "upstream profile is not an object")
    files = value.get("verified_files")
    if (
        value.get("profile") != PROFILE_NAME
        or value.get("git_commit") != UPSTREAM_COMMIT
        or value.get("git_tree") != UPSTREAM_TREE
        or value.get("version") != UPSTREAM_VERSION
        or value.get("source_snapshot_sha256") != SOURCE_SNAPSHOT_SHA256
        or not isinstance(files, list)
        or len(files) != 21
    ):
        _fail("UPSTREAM_PIN_MISMATCH", "upstream profile fields differ")
    return raw, value


def _path_argument(value: object, label: str, *, check_realpath: bool = True) -> Path:
    if type(value) is str:
        text = value
    elif isinstance(value, Path):
        text = str(value)
    else:
        _fail("ADAPTER_PATH_INVALID", f"{label} must be a str or Path")
    if "\0" in text or any(0xD800 <= ord(character) <= 0xDFFF for character in text):
        _fail("ADAPTER_PATH_INVALID", f"{label} is not filesystem-encodable")
    try:
        os.fsencode(text)
        normalized = os.path.normpath(text)
    except (ValueError, UnicodeError):
        _fail("ADAPTER_PATH_INVALID", f"{label} is not filesystem-encodable")
    if not text or not os.path.isabs(text) or normalized != text:
        _fail("ADAPTER_PATH_INVALID", f"{label} must be absolute and lexically normalized")
    path = Path(text)
    if check_realpath:
        try:
            if Path(os.path.realpath(text)) != path:
                _fail("ADAPTER_PATH_INVALID", f"{label} contains a symlink component")
        except (OSError, ValueError, UnicodeError):
            _fail("ADAPTER_PATH_INVALID", f"{label} cannot be resolved")
    return path


def _directory_argument(value: object, label: str) -> Path:
    path = _path_argument(value, label)
    try:
        info = path.lstat()
    except (OSError, ValueError, UnicodeError):
        _fail("ADAPTER_PATH_INVALID", f"{label} is not an existing directory")
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        _fail("ADAPTER_PATH_INVALID", f"{label} is not a no-follow directory")
    return path


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _roots_are_disjoint(vault: Path, work: Path, upstream: Path) -> None:
    for other in (work, upstream):
        if _contains(vault, other) or _contains(other, vault):
            _fail("ADAPTER_PATH_INVALID", "vault_root must be disjoint from other roots")


def _read_fd(fd: int, maximum: int, *, limit_code: str, mismatch_code: str, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            chunk = os.read(fd, min(1024 * 1024, maximum + 1 - total))
        except OSError:
            _fail(mismatch_code, f"cannot read {label}")
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            _fail(limit_code, f"{label} exceeds its byte limit")


def _open_dir(name: str | Path, *, dir_fd: int | None = None, code: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            _fail(code, "path component is not a directory")
        return fd
    except ContractError:
        raise
    except OSError:
        _fail(code, "cannot open a no-follow directory")


def _open_file(name: str | Path, *, dir_fd: int | None = None, code: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            _fail(code, "path component is not a regular file")
        return fd
    except ContractError:
        raise
    except OSError:
        _fail(code, "cannot open a no-follow regular file")


def _git(root: Path, *arguments: str) -> bytes:
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        _fail("UPSTREAM_PIN_MISMATCH", "git is unavailable for pin authentication")
    try:
        result = subprocess.run(
            [executable, "--no-optional-locks", "--no-replace-objects", "-c", "core.fsmonitor=false",
             "-C", str(root), *arguments],
            env={
                "PATH": os.defpath,
                "HOME": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _fail("UPSTREAM_PIN_MISMATCH", "git pin authentication failed")
    if result.returncode or len(result.stdout) > MAX_OUTPUT_BYTES or len(result.stderr) > MAX_OUTPUT_BYTES:
        _fail("UPSTREAM_PIN_MISMATCH", "git pin authentication failed")
    return result.stdout


def _profile_entries(profile: Mapping[str, Any]) -> list[tuple[str, int, str]]:
    result: list[tuple[str, int, str]] = []
    for item in profile["verified_files"]:
        if (
            type(item) is not dict
            or set(item) != {"path", "sha256", "size_bytes"}
            or type(item["path"]) is not str
            or type(item["size_bytes"]) is not int
            or type(item["sha256"]) is not str
            or not _HASH.fullmatch(item["sha256"])
        ):
            _fail("UPSTREAM_PIN_MISMATCH", "upstream profile file entry differs")
        parts = item["path"].split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            _fail("UPSTREAM_PIN_MISMATCH", "upstream profile path differs")
        result.append((item["path"], item["size_bytes"], item["sha256"]))
    if [entry[0] for entry in result] != sorted(entry[0] for entry in result) or len({entry[0] for entry in result}) != 21:
        _fail("UPSTREAM_PIN_MISMATCH", "upstream profile paths differ")
    return result


def _read_source(root_fd: int, relative: str, size: int, digest: str) -> bytes:
    owned: list[int] = []
    current = root_fd
    try:
        parts = relative.split("/")
        for component in parts[:-1]:
            current = _open_dir(component, dir_fd=current, code="UPSTREAM_PIN_MISMATCH")
            owned.append(current)
        fd = _open_file(parts[-1], dir_fd=current, code="UPSTREAM_PIN_MISMATCH")
        try:
            data = _read_fd(fd, size, limit_code="UPSTREAM_PIN_MISMATCH", mismatch_code="UPSTREAM_PIN_MISMATCH", label="upstream source")
        finally:
            os.close(fd)
    finally:
        for fd in reversed(owned):
            os.close(fd)
    if len(data) != size or _sha(data) != digest:
        _fail("UPSTREAM_PIN_MISMATCH", "upstream source snapshot differs")
    return data


def _authenticate(root: Path, profile: Mapping[str, Any]) -> dict[str, bytes]:
    if _git(root, "rev-parse", "HEAD^{commit}").strip() != UPSTREAM_COMMIT.encode():
        _fail("UPSTREAM_PIN_MISMATCH", "upstream commit differs")
    if _git(root, "rev-parse", "HEAD^{tree}").strip() != UPSTREAM_TREE.encode():
        _fail("UPSTREAM_PIN_MISMATCH", "upstream tree differs")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("UPSTREAM_PIN_MISMATCH", "upstream checkout is not clean")
    root_fd = _open_dir(root, code="UPSTREAM_PIN_MISMATCH")
    try:
        sources = {path: _read_source(root_fd, path, size, digest) for path, size, digest in _profile_entries(profile)}
    finally:
        os.close(root_fd)
    material = b"".join(path.encode("utf-8") + b"\0" + _sha(sources[path]).encode("ascii") + b"\n" for path in sorted(sources))
    if _sha(material) != SOURCE_SNAPSHOT_SHA256:
        _fail("UPSTREAM_PIN_MISMATCH", "upstream source snapshot differs")
    return sources


def _temp_base(roots: tuple[Path, ...]) -> Path:
    for candidate in (Path("/private/tmp"), Path("/tmp")):
        try:
            resolved = Path(os.path.realpath(candidate))
            if candidate.is_dir() and all(not _contains(root, resolved) for root in roots):
                return candidate
        except OSError:
            pass
    _fail("UPSTREAM_PIN_MISMATCH", "no disjoint private temporary base is available")


@dataclass
class _Allocation:
    root: Path
    execution: Path
    scratch: Path


def _make_allocation(sources: Mapping[str, bytes], roots: tuple[Path, ...]) -> _Allocation:
    try:
        root = Path(tempfile.mkdtemp(prefix="vpkb-upstream-", dir=_temp_base(roots)))
        os.chmod(root, 0o700)
        execution = root / "execution"
        scratch = root / "scratch"
        execution.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        os.chmod(execution, 0o700)
        os.chmod(scratch, 0o700)
        for relative, data in sources.items():
            target = execution / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            parent = target.parent
            while parent != root:
                os.chmod(parent, 0o700)
                parent = parent.parent
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(target, 0o400)
        allocation = _Allocation(root, execution, scratch)
        _verify_allocation(allocation, sources, code="UPSTREAM_PIN_MISMATCH")
        return allocation
    except ContractError:
        if "root" in locals():
            try:
                shutil.rmtree(root)
            except OSError:
                _fail("UPSTREAM_CONTRACT_MISMATCH", "cannot remove partial private execution tree")
        raise
    except (OSError, ValueError):
        if "root" in locals():
            try:
                shutil.rmtree(root)
            except OSError:
                _fail("UPSTREAM_CONTRACT_MISMATCH", "cannot remove partial private execution tree")
        _fail("UPSTREAM_PIN_MISMATCH", "cannot construct private execution tree")


def _verify_allocation(
    allocation: _Allocation,
    sources: Mapping[str, bytes],
    *,
    code: str = "UPSTREAM_CONTRACT_MISMATCH",
) -> None:
    expected_files = set(sources)
    expected_dirs = {""}
    for relative in expected_files:
        parts = relative.split("/")[:-1]
        expected_dirs.update("/".join(parts[:index]) for index in range(1, len(parts) + 1))
    actual_files: set[str] = set()
    actual_dirs = {""}
    try:
        for path, label in (
            (allocation.root, "root"),
            (allocation.execution, "execution directory"),
            (allocation.scratch, "scratch directory"),
        ):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o700):
                _fail(code, f"private {label} shape or mode changed")
        if {path.name for path in allocation.root.iterdir()} != {"execution", "scratch"}:
            _fail(code, "private allocation entries changed")
        for base, dirs, files in os.walk(allocation.execution, topdown=True, followlinks=False):
            base_path = Path(base)
            if stat.S_IMODE(base_path.lstat().st_mode) != 0o700:
                _fail(code, "private execution directory mode changed")
            for name in dirs:
                path = base_path / name
                if path.is_symlink():
                    _fail(code, "private execution tree contains a symlink")
                actual_dirs.add(path.relative_to(allocation.execution).as_posix())
            for name in files:
                path = base_path / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o400:
                    _fail(code, "private execution file mode changed")
                relative = path.relative_to(allocation.execution).as_posix()
                actual_files.add(relative)
                if relative not in sources or path.read_bytes() != sources[relative]:
                    _fail(code, "private execution file changed")
        if actual_files != expected_files or actual_dirs != expected_dirs:
            _fail(code, "private execution tree entries changed")
    except ContractError:
        raise
    except OSError:
        _fail(code, "cannot verify private execution tree")


def _cleanup(allocation: _Allocation) -> None:
    try:
        shutil.rmtree(allocation.root)
    except OSError:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "cannot remove private execution tree")


@dataclass
class _ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _run_bounded(argv: list[str], allocation: _Allocation) -> _ProcessResult:
    environment = {key: str(allocation.scratch) for key in ("HOME", "TEMP", "TMP", "TMPDIR")}
    try:
        process = subprocess.Popen(
            argv,
            cwd=allocation.execution,
            env=environment,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        _fail("UPSTREAM_EXECUTION_FAILED", "cannot start pinned upstream child", exit_code=1)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()

    def read(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            buffer = buffers[name]
            remaining = MAX_OUTPUT_BYTES + 1 - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(buffer) > MAX_OUTPUT_BYTES:
                overflow.set()
                try:
                    process.kill()
                except OSError:
                    pass
                return

    threads = [threading.Thread(target=read, args=(name, stream), daemon=True) for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        _fail("UPSTREAM_EXECUTION_FAILED", "pinned upstream child timed out", exit_code=1)
    for thread in threads:
        thread.join()
    if overflow.is_set():
        _fail("UPSTREAM_LIMIT_EXCEEDED", "pinned upstream output exceeds its byte limit")
    return _ProcessResult(process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]))


@dataclass
class _Transport:
    bundle: dict[str, Any]
    bundle_bytes: bytes
    content: list[dict[str, Any]]
    fingerprint: tuple[tuple[str, int, int, int, int], ...]


def _staging_batch(work: Path, bundle_path: Path) -> str:
    try:
        relative = bundle_path.relative_to(work)
    except ValueError:
        _fail("ADAPTER_PATH_INVALID", "bundle_path is outside work_root")
    parts = relative.parts
    if len(parts) != 3 or parts[1:] != ("transaction-inspect", "bundle.json"):
        _fail("ADAPTER_PATH_INVALID", "bundle_path does not use the fixed staging layout")
    try:
        validate_batch_id(parts[0])
    except StagingError:
        _fail("ADAPTER_PATH_INVALID", "bundle_path has an invalid batch id")
    if work.name != ".work":
        _fail("ADAPTER_PATH_INVALID", "work_root must be named .work")
    return parts[0]


def _bundle_value(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "claude-obsidian.transaction.v1",
        "operation_id": proposal["operation_id"],
        "operation_type": proposal["operation_type"],
        "writes": [
            {
                "path": item["path"],
                "mode": item["mode"],
                "content_file": "content/" + item["sha256"],
                "sha256": item["sha256"],
            }
            for item in proposal["writes"]
        ],
        "expected_hashes": proposal["expected_hashes"],
        "read_preconditions": proposal["read_preconditions"],
        "address_requests": [],
        "source_manifest_updates": {},
    }


def _compact_bundle_bytes(proposal: Mapping[str, Any], *, code: str) -> bytes:
    try:
        return json.dumps(
            _bundle_value(proposal), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail(code, "bundle cannot be encoded canonically")


def _fingerprint(label: str, info: os.stat_result) -> tuple[str, int, int, int, int]:
    return (label, info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode), info.st_size)


def _transport(
    proposal: Mapping[str, Any], work: Path, bundle_path: Path, batch_name: str | None = None,
) -> _Transport:
    lexical_batch = _staging_batch(work, bundle_path)
    if batch_name is not None and lexical_batch != batch_name:
        _fail("UPSTREAM_TRANSPORT_MISMATCH", "staging layout changed")
    batch_name = lexical_batch
    work_fd = _open_dir(work, code="UPSTREAM_TRANSPORT_MISMATCH")
    owned: list[int] = [work_fd]
    try:
        batch_fd = _open_dir(batch_name, dir_fd=work_fd, code="UPSTREAM_TRANSPORT_MISMATCH"); owned.append(batch_fd)
        stage_fd = _open_dir("transaction-inspect", dir_fd=batch_fd, code="UPSTREAM_TRANSPORT_MISMATCH"); owned.append(stage_fd)
        content_fd = _open_dir("content", dir_fd=stage_fd, code="UPSTREAM_TRANSPORT_MISMATCH"); owned.append(content_fd)
        directory_fingerprints = [
            _fingerprint("work_root", os.fstat(work_fd)),
            _fingerprint("batch", os.fstat(batch_fd)),
            _fingerprint("transaction-inspect", os.fstat(stage_fd)),
            _fingerprint("content", os.fstat(content_fd)),
        ]
        bundle_fd = _open_file("bundle.json", dir_fd=stage_fd, code="UPSTREAM_TRANSPORT_MISMATCH")
        try:
            bundle_info = os.fstat(bundle_fd)
            raw = _read_fd(bundle_fd, MAX_BUNDLE_BYTES, limit_code="UPSTREAM_LIMIT_EXCEEDED", mismatch_code="UPSTREAM_TRANSPORT_MISMATCH", label="bundle")
        finally:
            os.close(bundle_fd)
        value = _strict_json(raw, code="UPSTREAM_TRANSPORT_MISMATCH", label="bundle")
        if not isinstance(value, dict):
            _fail("UPSTREAM_TRANSPORT_MISMATCH", "bundle root is not an object")
        writes = proposal["writes"]
        expected = _bundle_value(proposal)
        canonical = _compact_bundle_bytes(proposal, code="UPSTREAM_TRANSPORT_MISMATCH")
        if value != expected or raw != canonical or _sha(raw) != proposal["input_bundle_sha256"]:
            _fail("UPSTREAM_TRANSPORT_MISMATCH", "bundle bytes or facade correlation differ")
        cached: dict[str, bytes] = {}
        cached_info: dict[str, os.stat_result] = {}
        entries: list[dict[str, Any]] = []
        for write in writes:
            digest = write["sha256"]
            if digest not in cached:
                fd = _open_file(digest, dir_fd=content_fd, code="UPSTREAM_TRANSPORT_MISMATCH")
                try:
                    cached_info[digest] = os.fstat(fd)
                    cached[digest] = _read_fd(fd, MAX_CONTENT_BYTES, limit_code="UPSTREAM_LIMIT_EXCEEDED", mismatch_code="UPSTREAM_TRANSPORT_MISMATCH", label="content file")
                finally:
                    os.close(fd)
            data = cached[digest]
            if len(data) != write["size_bytes"] or _sha(data) != digest:
                _fail("UPSTREAM_TRANSPORT_MISMATCH", "content bytes or facade correlation differ")
            entries.append({"write_path": write["path"], "content_file": "content/" + digest, "sha256": digest, "size_bytes": len(data)})
        fingerprints = directory_fingerprints + [_fingerprint("bundle.json", bundle_info)]
        fingerprints.extend(_fingerprint("content/" + digest, info) for digest, info in sorted(cached_info.items()))
        return _Transport(value, raw, entries, tuple(fingerprints))
    finally:
        for fd in reversed(owned):
            os.close(fd)


def _failure(result: _ProcessResult) -> None:
    if result.returncode == 0:
        return
    if result.returncode not in {2, 75}:
        _fail("UPSTREAM_EXECUTION_FAILED", "pinned upstream child failed", exit_code=1)
    if result.stdout or not _UPSTREAM_ERROR.fullmatch(result.stderr):
        _fail("UPSTREAM_EXECUTION_FAILED", "pinned upstream failure transport is malformed", exit_code=1)
    code = _UPSTREAM_ERROR.fullmatch(result.stderr).group(1).decode("ascii")  # type: ignore[union-attr]
    mapped = "UPSTREAM_CONFLICT" if result.returncode == 75 else "UPSTREAM_INSPECT_REFUSED"
    _fail(mapped, "pinned upstream refused inspection", exit_code=result.returncode, details={"upstream_code": code, "upstream_exit_code": result.returncode})


def _success_plan(result: _ProcessResult) -> dict[str, Any]:
    _failure(result)
    if result.stderr or not result.stdout:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "pinned upstream success transport differs")
    value = _strict_json(result.stdout, code="UPSTREAM_CONTRACT_MISMATCH", label="upstream stdout")
    if not isinstance(value, dict) or set(value) != _PLAN_FIELDS or value.get("schema") != "claude-obsidian.transaction-plan.v1" or value.get("valid") is not True:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "pinned upstream plan shape differs")
    return value


def _postcheck(
    allocation: _Allocation,
    sources: Mapping[str, bytes],
    upstream: Path,
    profile: Mapping[str, Any],
    before_transport: _Transport | None = None,
    work: Path | None = None,
    bundle_path: Path | None = None,
    proposal: Mapping[str, Any] | None = None,
    batch_name: str | None = None,
) -> None:
    try:
        _verify_allocation(allocation, sources)
        _profile()
        if _authenticate(upstream, profile) != sources:
            raise ValueError("source bytes changed")
        if before_transport is not None:
            assert work is not None and bundle_path is not None and proposal is not None
            after = _transport(proposal, work, bundle_path, batch_name)
            if after != before_transport:
                raise ValueError("transport changed")
    except Exception:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authenticated inputs changed during child execution")


def _authority(transaction: dict[str, Any], transport: _Transport, stdout: bytes) -> dict[str, Any]:
    return {
        "schema": AUTHORITY_SCHEMA,
        "profile": PROFILE_NAME,
        "upstream": {
            "distribution": "claude-obsidian",
            "version": UPSTREAM_VERSION,
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
            "tracked_and_untracked_clean": True,
            "profile_sha256": PROFILE_SHA256,
            "source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        },
        "transport": {
            "bundle_file": "bundle.json",
            "bundle_sha256": _sha(transport.bundle_bytes),
            "bundle_size_bytes": len(transport.bundle_bytes),
            "content_files": copy.deepcopy(transport.content),
            "stdout_sha256": _sha(stdout),
            "stdout_size_bytes": len(stdout),
        },
        "transaction": transaction,
    }


def inspect_pinned_transaction(
    proposal: object,
    *,
    upstream_root: Path | str,
    work_root: Path | str,
    vault_root: Path | str,
    bundle_path: Path | str,
) -> dict[str, object]:
    """Inspect one frozen facade proposal through the authenticated public CLI."""

    document = validate_transaction(proposal)
    if document["phase"] != "proposal":
        _fail("TRANSACTION_UPSTREAM_MISMATCH", "inspection accepts only a proposal")
    upstream = _directory_argument(upstream_root, "upstream_root")
    work = _directory_argument(work_root, "work_root")
    vault = _directory_argument(vault_root, "vault_root")
    bundle = _path_argument(bundle_path, "bundle_path", check_realpath=False)
    _roots_are_disjoint(vault, work, upstream)
    batch_name = _staging_batch(work, bundle)
    _raw_profile, profile = _profile()
    sources = _authenticate(upstream, profile)
    allocation = _make_allocation(sources, (upstream, work, vault))
    try:
        transport = _transport(document, work, bundle, batch_name)
        # The public selector requires an existing Obsidian/claude-obsidian sentinel.
        sentinel = False
        for name in (".obsidian", ".raw"):
            try:
                info = (vault / name).lstat()
                sentinel = sentinel or (stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode))
            except OSError:
                pass
        if not sentinel:
            _fail("UPSTREAM_VAULT_INVALID", "vault_root lacks an existing Vault sentinel")
        argv = [sys.executable, "-I", "-B", "-X", "utf8", str(allocation.execution / "scripts" / "claude-obsidian.py"), "transaction", "inspect", str(bundle), "--vault", str(vault)]
        try:
            result = _run_bounded(argv, allocation)
        except ContractError:
            _postcheck(allocation, sources, upstream, profile, transport, work, bundle, document, batch_name)
            raise
        _postcheck(allocation, sources, upstream, profile, transport, work, bundle, document, batch_name)
        plan = _success_plan(result)
        try:
            inspected = attach_upstream_inspection(document, plan)
            authority = _authority(inspected, transport, result.stdout)
            return validate_upstream_authority(authority)
        except ContractError:
            _fail("UPSTREAM_CONTRACT_MISMATCH", "upstream plan or constructed authority differs")
    finally:
        _cleanup(allocation)


_SOURCE_PROGRAM = r'''import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import claude_obsidian
from claude_obsidian import ledgers
assert claude_obsidian.__version__ == "2.1.1"
assert pathlib.Path(claude_obsidian.__file__).resolve() == root / "claude_obsidian/__init__.py"
assert pathlib.Path(ledgers.__file__).resolve() == root / "claude_obsidian/ledgers.py"
assert ledgers.stable_source_id("file", ".raw/captured/" + "a" * 64 + ".pdf", "a" * 64) == "src-42baa0cddcfa30cdd5af"
value = ledgers.stable_source_id("file", sys.argv[2], sys.argv[3])
print(json.dumps({"schema":"video-paper-wiki.source-id-result.v1","source_id":value}, sort_keys=True, separators=(",", ":")))
'''


def verify_pinned_source_id(
    stored_path: str,
    source_identity: str,
    *,
    upstream_root: Path | str,
    expected_source_id: str | None = None,
) -> str:
    """Call the one authorized upstream source-ID function in an isolated child."""

    if type(stored_path) is not str or type(source_identity) is not str:
        _fail("ADAPTER_PATH_INVALID", "stored_path and source_identity must be strings")
    captured = _CAPTURED.fullmatch(stored_path)
    if captured is None or not _HASH.fullmatch(source_identity) or captured.group(1) != source_identity:
        _fail("ADAPTER_PATH_INVALID", "stored_path and source_identity do not form a captured file")
    if expected_source_id is not None and (type(expected_source_id) is not str or not _SOURCE_ID.fullmatch(expected_source_id)):
        _fail("ADAPTER_PATH_INVALID", "expected_source_id is invalid")
    upstream = _directory_argument(upstream_root, "upstream_root")
    _raw_profile, profile = _profile()
    sources = _authenticate(upstream, profile)
    allocation = _make_allocation(sources, (upstream,))
    try:
        argv = [sys.executable, "-I", "-B", "-X", "utf8", "-c", _SOURCE_PROGRAM, str(allocation.execution), stored_path, source_identity]
        try:
            result = _run_bounded(argv, allocation)
        except ContractError:
            _postcheck(allocation, sources, upstream, profile)
            raise
        _postcheck(allocation, sources, upstream, profile)
        _failure(result)
        if result.stderr or not result.stdout:
            _fail("UPSTREAM_CONTRACT_MISMATCH", "source-ID helper success transport differs")
        value = _strict_json(result.stdout, code="UPSTREAM_CONTRACT_MISMATCH", label="source-ID stdout")
        if type(value) is not dict or set(value) != {"schema", "source_id"} or value.get("schema") != "video-paper-wiki.source-id-result.v1" or type(value.get("source_id")) is not str or not _SOURCE_ID.fullmatch(value["source_id"]):
            _fail("UPSTREAM_CONTRACT_MISMATCH", "source-ID helper result differs")
        source_id = value["source_id"]
        if expected_source_id is not None and source_id != expected_source_id:
            _fail("UPSTREAM_SOURCE_ID_MISMATCH", "source ID differs from expected value")
        return source_id
    finally:
        _cleanup(allocation)


def _check_upstream_authority(document: Mapping[str, Any]) -> None:
    """Object-only cross-field checks called by the central registry."""

    _raw_profile, _value = _profile()
    transaction = validate_transaction(document["transaction"])
    if transaction["phase"] != "inspected" or transaction["runtime_result"] is not None:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authority transaction phase differs")
    transport = document["transport"]
    if transport["bundle_sha256"] != transaction["input_bundle_sha256"]:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authority bundle digest differs")
    bundle_bytes = _compact_bundle_bytes(transaction, code="UPSTREAM_CONTRACT_MISMATCH")
    if (_sha(bundle_bytes) != transport["bundle_sha256"]
            or len(bundle_bytes) != transport["bundle_size_bytes"]):
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authority bundle bytes differ")
    inspection = transaction["inspection"]
    if inspection is None or inspection["input_bundle_sha256"] != transport["bundle_sha256"] or inspection["expanded_bundle_sha256"] != transport["bundle_sha256"]:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authority plan bundle digests differ")
    expected = [
        {"write_path": write["path"], "content_file": "content/" + write["sha256"], "sha256": write["sha256"], "size_bytes": write["size_bytes"]}
        for write in transaction["writes"]
    ]
    if transport["content_files"] != expected:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "authority content transport differs")


def validate_upstream_authority(document: object) -> dict[str, object]:
    """Validate supplied authority data and return a deep independent copy."""

    _json_preflight(document)
    return copy.deepcopy(validate_document(document, AUTHORITY_SCHEMA))
