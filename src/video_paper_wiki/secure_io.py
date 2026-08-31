"""No-follow regular-file reads with same-fd snapshots. Zero network."""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

SOURCE_CHANGED = "SOURCE_CHANGED"
PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
PLAN_PATH_UNSAFE = "PLAN_PATH_UNSAFE"
APPROVAL_REF_NOT_FOUND = "APPROVAL_REF_NOT_FOUND"
BLOB_NOT_FOUND = "BLOB_NOT_FOUND"
BLOB_PATH_UNSAFE = "BLOB_PATH_UNSAFE"
BLOB_HASH_MISMATCH = "BLOB_HASH_MISMATCH"
BLOB_LIMIT_EXCEEDED = "BLOB_LIMIT_EXCEEDED"

READ_CHUNK = 1024 * 1024
JSON_MAX_BYTES = 1_048_576


class SecureIOError(Exception):
    """Fail-closed I/O error with a stable envelope code."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details) if details is not None else {}
        if exit_code is None:
            self.exit_code = 75 if code == SOURCE_CHANGED else 2
        else:
            self.exit_code = exit_code


def close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def dir_open_flags(*, nofollow: bool = True) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if nofollow and hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def file_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def is_special(st: os.stat_result) -> bool:
    mode = st.st_mode
    return bool(
        stat.S_ISFIFO(mode)
        or stat.S_ISSOCK(mode)
        or stat.S_ISCHR(mode)
        or stat.S_ISBLK(mode)
    )


def stamp(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(st.st_dev),
        int(st.st_ino),
        int(st.st_mode),
        int(st.st_size),
        int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
        int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000))),
    )


def _raise(code: str, message: str, path: Path, extra: Mapping[str, Any] | None = None) -> None:
    details: dict[str, Any] = {"path": path.as_posix()}
    if extra:
        details.update(dict(extra))
    raise SecureIOError(code, message, details)


def _map_open_error(path: Path, exc: OSError, *, missing_code: str, unsafe_code: str) -> None:
    err = getattr(exc, "errno", None)
    if isinstance(exc, FileNotFoundError) or err == errno.ENOENT:
        _raise(missing_code, "path does not exist", path)
    if err in {errno.ELOOP, getattr(errno, "EMLINK", 31)}:
        _raise(unsafe_code, "path component is a symlink", path)
    if isinstance(exc, NotADirectoryError) or err in {errno.ENOTDIR, errno.EISDIR}:
        _raise(unsafe_code, "path component is not a regular file", path)
    if err in {errno.ENXIO, errno.EEXIST}:
        _raise(unsafe_code, "path is not a regular file", path)
    _raise(unsafe_code, "path is not a readable regular file", path)


def _is_presence_or_type_race(exc: OSError) -> bool:
    err = getattr(exc, "errno", None)
    if isinstance(exc, FileNotFoundError) or err == errno.ENOENT:
        return True
    if err in {errno.ELOOP, getattr(errno, "EMLINK", 31)}:
        return True
    if isinstance(exc, (NotADirectoryError, IsADirectoryError)) or err in {
        errno.ENOTDIR,
        errno.EISDIR,
    }:
        return True
    if err in {errno.ENXIO, errno.EEXIST}:
        return True
    return False


def lexical_abs(path: Path | str) -> Path:
    """Absolute path with lexical `..` collapse. Does not follow symlinks."""

    return Path(os.path.normpath(os.path.abspath(os.fspath(path))))


def open_dir_nofollow(path: Path, *, missing_code: str, unsafe_code: str) -> int:
    """Open *path* as a directory, never following any component."""

    target = lexical_abs(path)
    owned: list[int] = []
    try:
        if target.is_absolute():
            fd = os.open("/", dir_open_flags(nofollow=False))
            parts = target.parts[1:]
        else:
            fd = os.open(".", dir_open_flags(nofollow=False))
            parts = target.parts
        owned.append(fd)
        for part in parts:
            if part in {"", "."}:
                continue
            if part == "..":
                _raise(unsafe_code, "path component is unsafe", target)
            nxt = os.open(part, dir_open_flags(nofollow=True), dir_fd=fd)
            owned.append(nxt)
            fd = nxt
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or is_special(st):
            _raise(unsafe_code, "path is not a directory", target)
        owned.pop()
        for extra in owned:
            close_fd(extra)
        return fd
    except SecureIOError:
        for extra in owned:
            close_fd(extra)
        raise
    except OSError as exc:
        for extra in owned:
            close_fd(extra)
        _map_open_error(target, exc, missing_code=missing_code, unsafe_code=unsafe_code)
        raise AssertionError("unreachable") from exc


def open_parent_nofollow(
    path: Path, *, missing_code: str, unsafe_code: str
) -> tuple[int, str, list[int]]:
    """Open the parent directory of *path* with O_NOFOLLOW. Caller owns returned fds."""

    target = lexical_abs(path)
    name = target.name
    if not name or name in {".", ".."} or "/" in name or os.sep in name:
        _raise(unsafe_code, "path is not a regular file", target)
    parent = target.parent
    if parent == target:
        _raise(unsafe_code, "path is not a regular file", target)
    fd = open_dir_nofollow(parent, missing_code=missing_code, unsafe_code=unsafe_code)
    return fd, name, [fd]


def read_child_regular(
    parent_fd: int,
    name: str,
    *,
    path: Path,
    missing_code: str,
    unsafe_code: str,
    changed_code: str = SOURCE_CHANGED,
    max_bytes: int | None = None,
    limit_code: str = BLOB_LIMIT_EXCEEDED,
) -> bytes:
    """Read *name* under *parent_fd* from one fd snapshot."""

    target = Path(path)
    try:
        lst = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        _raise(missing_code, "path does not exist", target)
    except OSError as exc:
        _map_open_error(target, exc, missing_code=missing_code, unsafe_code=unsafe_code)
        raise AssertionError("unreachable") from exc
    if stat.S_ISLNK(lst.st_mode):
        _raise(unsafe_code, "path is a symlink", target)
    if stat.S_ISDIR(lst.st_mode):
        _raise(unsafe_code, "path is a directory", target)
    if is_special(lst) or not stat.S_ISREG(lst.st_mode):
        _raise(unsafe_code, "path is not a regular file", target)
    if max_bytes is not None and lst.st_size > max_bytes:
        raise SecureIOError(
            limit_code,
            "byte count exceeds approved limit",
            {"path": target.as_posix(), "byte_count": int(lst.st_size), "max_bytes": max_bytes},
        )
    fd: int | None = None
    try:
        fd = os.open(name, file_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        if _is_presence_or_type_race(exc):
            _raise(changed_code, "file changed during open", target)
        _map_open_error(target, exc, missing_code=missing_code, unsafe_code=unsafe_code)
        raise AssertionError("unreachable") from exc
    try:
        fst = os.fstat(fd)
        if stat.S_ISLNK(fst.st_mode) or not stat.S_ISREG(fst.st_mode) or is_special(fst):
            _raise(changed_code, "file changed during open", target)
        if stamp(lst) != stamp(fst):
            _raise(changed_code, "file changed during open", target)
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(fd, READ_CHUNK)
            except OSError as exc:
                _map_open_error(target, exc, missing_code=missing_code, unsafe_code=unsafe_code)
                raise AssertionError("unreachable") from exc
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                post = os.fstat(fd)
                if stamp(fst) != stamp(post):
                    _raise(changed_code, "file changed during read", target)
                raise SecureIOError(
                    limit_code,
                    "byte count exceeds approved limit",
                    {
                        "path": target.as_posix(),
                        "byte_count": total,
                        "max_bytes": max_bytes,
                    },
                )
            chunks.append(chunk)
        post = os.fstat(fd)
        if stamp(fst) != stamp(post):
            _raise(changed_code, "file changed during read", target)
        if post.st_size != total:
            _raise(changed_code, "file changed during read", target)
        try:
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            _raise(changed_code, "file changed during read", target)
        except OSError as exc:
            _map_open_error(target, exc, missing_code=missing_code, unsafe_code=unsafe_code)
            raise AssertionError("unreachable") from exc
        if stamp(named) != stamp(post):
            _raise(changed_code, "file changed during read", target)
        return b"".join(chunks)
    finally:
        close_fd(fd)


def read_regular_file(
    path: Path,
    *,
    missing_code: str,
    unsafe_code: str,
    changed_code: str = SOURCE_CHANGED,
    max_bytes: int | None = None,
    limit_code: str = BLOB_LIMIT_EXCEEDED,
) -> bytes:
    parent_fd: int | None = None
    owned: list[int] = []
    target = Path(path)
    try:
        parent_fd, name, owned = open_parent_nofollow(
            target, missing_code=missing_code, unsafe_code=unsafe_code
        )
        return read_child_regular(
            parent_fd,
            name,
            path=target,
            missing_code=missing_code,
            unsafe_code=unsafe_code,
            changed_code=changed_code,
            max_bytes=max_bytes,
            limit_code=limit_code,
        )
    finally:
        for fd in owned:
            close_fd(fd)


def parse_strict_json(data: bytes, *, invalid_code: str) -> Any:
    """Parse UTF-8 JSON. Reject duplicate keys, floats, NaN/Infinity, trailing data."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecureIOError(invalid_code, "JSON is not valid UTF-8", {"reason": "utf-8"}) from exc

    def _reject_float(_value: str) -> Any:
        raise SecureIOError(invalid_code, "JSON must not contain floats", {"reason": "float"})

    def _reject_constant(_value: str) -> Any:
        raise SecureIOError(
            invalid_code,
            "JSON must not contain NaN or Infinity",
            {"reason": "constant"},
        )

    def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise SecureIOError(
                    invalid_code,
                    "JSON must not contain duplicate keys",
                    {"reason": "duplicate_key"},
                )
            out[key] = value
        return out

    decoder = json.JSONDecoder(
        parse_float=_reject_float,
        parse_constant=_reject_constant,
        object_pairs_hook=_no_duplicate_keys,
    )
    try:
        stripped = text.lstrip("\ufeff")
        if stripped != text:
            raise SecureIOError(invalid_code, "JSON must not contain a UTF-8 BOM", {"reason": "bom"})
        obj, index = decoder.raw_decode(text)
    except SecureIOError:
        raise
    except json.JSONDecodeError as exc:
        raise SecureIOError(invalid_code, "JSON is invalid", {"reason": "syntax"}) from exc
    except ValueError as exc:
        raise SecureIOError(invalid_code, "JSON is invalid", {"reason": "value"}) from exc
    trailing = text[index:]
    if trailing.strip():
        raise SecureIOError(invalid_code, "JSON has trailing data", {"reason": "trailing"})
    return obj


def load_strict_json(
    path: Path,
    *,
    missing_code: str,
    unsafe_code: str,
    invalid_code: str,
    changed_code: str = SOURCE_CHANGED,
    max_bytes: int = JSON_MAX_BYTES,
) -> Any:
    data = read_regular_file(
        path,
        missing_code=missing_code,
        unsafe_code=unsafe_code,
        changed_code=changed_code,
        max_bytes=max_bytes,
        limit_code=invalid_code,
    )
    return parse_strict_json(data, invalid_code=invalid_code)
