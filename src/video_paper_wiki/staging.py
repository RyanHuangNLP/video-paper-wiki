"""Stage agent-safe writes under <checkout>/.work/<batch-id>/. Zero network."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Mapping, NamedTuple

BATCH_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$")
BATCH_ID_MAX = 128
WORK_DIRNAME = ".work"
PROJECT_NAME = "video-paper-wiki"
CODE_WORKSPACE_ROOT_INVALID = "WORKSPACE_ROOT_INVALID"
CODE_INVALID_BATCH_ID = "INVALID_BATCH_ID"
CODE_WORK_PATH_ESCAPE = "WORK_PATH_ESCAPE"
CODE_WORK_PATH_UNSAFE = "WORK_PATH_UNSAFE"
CODE_STAGING_CONFLICT = "STAGING_CONFLICT"


class StagingError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details) if details is not None else {}


class StageResult(NamedTuple):
    path: Path
    already_staged: bool


def validate_batch_id(raw: object) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > BATCH_ID_MAX:
        raise StagingError(
            CODE_INVALID_BATCH_ID,
            "batch-id must be 1-128 characters matching "
            r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$",
            {"batch_id": raw if isinstance(raw, str) else None},
        )
    if not BATCH_ID_RE.fullmatch(raw):
        raise StagingError(
            CODE_INVALID_BATCH_ID,
            "batch-id must be 1-128 characters matching "
            r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$",
            {"batch_id": raw},
        )
    return raw


def resolve_checkout_root(cwd: Path | None = None) -> Path:
    root = Path.cwd() if cwd is None else Path(cwd)
    git = root / ".git"
    if git.is_symlink() or not git.exists():
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        )
    try:
        st = os.lstat(git)
    except OSError:
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        ) from None
    if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        )
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        )
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        ) from None
    name = data.get("project", {}).get("name") if isinstance(data, dict) else None
    if name != PROJECT_NAME:
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        )
    return root


def _is_strict_child(child: str, parent: str) -> bool:
    child_n = os.path.normpath(child)
    parent_n = os.path.normpath(parent)
    prefix = parent_n if parent_n.endswith(os.sep) else parent_n + os.sep
    return child_n.startswith(prefix) and child_n != parent_n


def _validate_segment(name: str) -> str:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or os.sep in name
        or name.startswith("/")
    ):
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "unsafe path component",
            {"name": name},
        )
    return name


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _is_special(st: os.stat_result) -> bool:
    mode = st.st_mode
    return bool(
        stat.S_ISFIFO(mode)
        or stat.S_ISSOCK(mode)
        or stat.S_ISCHR(mode)
        or stat.S_ISBLK(mode)
    )


def _raise_unsafe(path: Path, reason: str) -> None:
    raise StagingError(
        CODE_WORK_PATH_UNSAFE,
        reason,
        {"path": path.as_posix()},
    )


def _ensure_real_dir(path: Path) -> None:
    st = _lstat(path)
    if st is None:
        try:
            os.mkdir(path, 0o755)
        except FileExistsError:
            st = _lstat(path)
            if st is None:
                _raise_unsafe(path, "directory slot is unsafe")
        else:
            st = _lstat(path)
            if st is None:
                _raise_unsafe(path, "directory slot is unsafe")
    assert st is not None
    if stat.S_ISLNK(st.st_mode):
        _raise_unsafe(path, "path component is a symlink")
    if _is_special(st) or stat.S_ISREG(st.st_mode):
        _raise_unsafe(path, "directory slot is not a directory")
    if not stat.S_ISDIR(st.st_mode):
        _raise_unsafe(path, "directory slot is not a directory")


def _assert_inside_work(target: Path, work_root: Path) -> None:
    work_abs = os.path.abspath(work_root)
    target_abs = os.path.abspath(target)
    work_norm = os.path.normpath(work_abs)
    target_norm = os.path.normpath(target_abs)
    if not _is_strict_child(target_norm, work_norm):
        raise StagingError(
            CODE_WORK_PATH_ESCAPE,
            "resolved path escapes .work",
            {"path": target.as_posix()},
        )
    work_real = os.path.realpath(work_root)
    parent_real = os.path.realpath(target.parent)
    planned = os.path.normpath(os.path.join(parent_real, target.name))
    if not _is_strict_child(planned, work_real):
        raise StagingError(
            CODE_WORK_PATH_ESCAPE,
            "resolved path escapes .work",
            {"path": target.as_posix()},
        )
    existing = _lstat(target)
    if existing is not None and not stat.S_ISLNK(existing.st_mode):
        target_real = os.path.realpath(target)
        if not _is_strict_child(target_real, work_real):
            raise StagingError(
                CODE_WORK_PATH_ESCAPE,
                "resolved path escapes .work",
                {"path": target.as_posix()},
            )


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {getattr(os, "ELOOP", 40), getattr(os, "EMLINK", 31)}:
            _raise_unsafe(path, "path component is a symlink")
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "target is not a readable regular file",
            {"path": path.as_posix()},
        ) from exc
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_install(work_root: Path, target: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp.", dir=work_root)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp_name, target)
    except FileExistsError:
        existing = _lstat(target)
        if existing is None:
            raise StagingError(
                CODE_STAGING_CONFLICT,
                "target exists with different bytes",
                {"path": target.as_posix()},
            )
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            _raise_unsafe(target, "target is not a regular file")
        current = _read_regular_file(target)
        if current == data:
            return
        raise StagingError(
            CODE_STAGING_CONFLICT,
            "target exists with different bytes",
            {"path": target.as_posix()},
        )
    except OSError as exc:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "atomic install failed",
            {"path": target.as_posix(), "reason": str(exc)},
        ) from exc
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    _fsync_dir(target.parent)
    _fsync_dir(work_root)


def stage_bytes(*, batch_id: object, relative: tuple[str, ...], data: bytes) -> StageResult:
    """Write *data* to <checkout>/.work/<batch-id>/<relative...>."""
    checkout = resolve_checkout_root()
    batch = validate_batch_id(batch_id)
    if not relative:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "unsafe path component",
            {"name": ""},
        )
    parts = tuple(_validate_segment(part) for part in relative)
    work_root = checkout / WORK_DIRNAME
    work_st = _lstat(work_root)
    if work_st is not None:
        if stat.S_ISLNK(work_st.st_mode):
            _raise_unsafe(work_root, "path component is a symlink")
        if not stat.S_ISDIR(work_st.st_mode):
            _raise_unsafe(work_root, "directory slot is not a directory")
    target = work_root.joinpath(batch, *parts)
    current = work_root
    for part in (batch, *parts):
        current = current / part
        st = _lstat(current)
        if st is not None and stat.S_ISLNK(st.st_mode):
            _raise_unsafe(current, "path component is a symlink")
    _assert_inside_work(target, work_root)
    _ensure_real_dir(work_root)
    _assert_inside_work(target, work_root)
    current = work_root
    for part in (batch, *parts[:-1]):
        current = current / part
        _ensure_real_dir(current)
        st = _lstat(current)
        if st is not None and stat.S_ISLNK(st.st_mode):
            _raise_unsafe(current, "path component is a symlink")
        _assert_inside_work(target, work_root)
    existing = _lstat(target)
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode):
            _raise_unsafe(target, "path component is a symlink")
        if _is_special(existing) or stat.S_ISDIR(existing.st_mode):
            _raise_unsafe(target, "target is not a regular file")
        if not stat.S_ISREG(existing.st_mode):
            _raise_unsafe(target, "target is not a regular file")
        current_bytes = _read_regular_file(target)
        if current_bytes == data:
            return StageResult(path=target, already_staged=True)
        raise StagingError(
            CODE_STAGING_CONFLICT,
            "target exists with different bytes",
            {"path": target.as_posix()},
        )
    _atomic_install(work_root, target, data)
    return StageResult(path=target, already_staged=False)
