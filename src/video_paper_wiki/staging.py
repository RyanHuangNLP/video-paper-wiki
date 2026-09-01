"""Stage agent-safe writes under <checkout>/.work/<batch-id>/. Zero network."""

from __future__ import annotations

import errno
import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Mapping, NamedTuple, NoReturn

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


class _TransactionInspectStageResult(NamedTuple):
    content_already_staged: tuple[bool, ...]
    bundle_already_staged: bool


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
        if not isinstance(data, dict):
            raise StagingError(
                CODE_WORKSPACE_ROOT_INVALID,
                "cwd is not a video-paper-wiki checkout root",
                {"cwd": root.as_posix()},
            )
        project = data.get("project", {})
        if not isinstance(project, dict):
            raise StagingError(
                CODE_WORKSPACE_ROOT_INVALID,
                "cwd is not a video-paper-wiki checkout root",
                {"cwd": root.as_posix()},
            )
        name = project.get("name")
    except StagingError:
        raise
    except (OSError, tomllib.TOMLDecodeError, AttributeError, TypeError, ValueError):
        raise StagingError(
            CODE_WORKSPACE_ROOT_INVALID,
            "cwd is not a video-paper-wiki checkout root",
            {"cwd": root.as_posix()},
        ) from None
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
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(path, exc)


def _is_special(st: os.stat_result) -> bool:
    mode = st.st_mode
    return bool(
        stat.S_ISFIFO(mode)
        or stat.S_ISSOCK(mode)
        or stat.S_ISCHR(mode)
        or stat.S_ISBLK(mode)
    )


def _raise_unsafe(path: Path, reason: str) -> NoReturn:
    raise StagingError(
        CODE_WORK_PATH_UNSAFE,
        reason,
        {"path": path.as_posix()},
    )


def _map_oserror(path: Path, exc: BaseException) -> NoReturn:
    if isinstance(exc, StagingError):
        raise exc
    err = getattr(exc, "errno", None)
    if err in {errno.ELOOP, getattr(errno, "EMLINK", 31), getattr(errno, "ELOOP", 40)}:
        _raise_unsafe(path, "path component is a symlink")
    if isinstance(exc, NotADirectoryError) or err == errno.ENOTDIR:
        _raise_unsafe(path, "directory slot is not a directory")
    if isinstance(exc, FileExistsError) or err == errno.EEXIST:
        _raise_unsafe(path, "directory slot is unsafe")
    _raise_unsafe(path, "directory slot is unsafe")


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


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _dir_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _file_read_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _fd_proc_path(fd: int) -> str | None:
    try:
        return os.readlink(f"/proc/self/fd/{int(fd)}")
    except OSError:
        return None


def _parent_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        pass


def _require_live_dir_fd(fd: int, path: Path) -> os.stat_result:
    try:
        st = os.fstat(fd)
    except OSError:
        _raise_unsafe(path, "directory slot is unsafe")
    if not stat.S_ISDIR(st.st_mode):
        _raise_unsafe(path, "directory slot is not a directory")
    raw = _fd_proc_path(fd)
    if raw is not None and " (deleted)" in raw:
        _raise_unsafe(path, "directory slot is unsafe")
    return st


def _require_fd_inside_work(fd: int, work_fd: int, path: Path) -> None:
    st = _require_live_dir_fd(fd, path)
    work_st = _require_live_dir_fd(work_fd, path)
    raw = _fd_proc_path(fd)
    work_raw = _fd_proc_path(work_fd)
    if raw is not None and work_raw is not None:
        work_n = os.path.normpath(work_raw)
        fd_n = os.path.normpath(raw)
        if fd_n != work_n and not _is_strict_child(fd_n, work_n):
            _raise_unsafe(path, "directory slot is unsafe")
    if _same_inode(st, work_st):
        return
    current = os.dup(fd)
    try:
        seen = {(st.st_dev, st.st_ino)}
        parent_flags = _parent_open_flags()
        while True:
            try:
                parent = os.open("..", parent_flags, dir_fd=current)
            except OSError:
                _raise_unsafe(path, "directory slot is unsafe")
            try:
                pst = os.fstat(parent)
            except OSError:
                _close_fd(parent)
                _raise_unsafe(path, "directory slot is unsafe")
            if _same_inode(pst, work_st):
                _close_fd(parent)
                return
            key = (pst.st_dev, pst.st_ino)
            if key in seen:
                _close_fd(parent)
                _raise_unsafe(path, "directory slot is unsafe")
            seen.add(key)
            _close_fd(current)
            current = parent
    finally:
        _close_fd(current)


def _require_work_still_in_checkout(work_fd: int, checkout_fd: int, path: Path) -> None:
    """Prove *work_fd* is still the real `.work` child of *checkout_fd*."""
    work_st = _require_live_dir_fd(work_fd, path)
    checkout_st = _require_live_dir_fd(checkout_fd, path)
    if _same_inode(work_st, checkout_st):
        _raise_unsafe(path, "directory slot is unsafe")
    work_raw = _fd_proc_path(work_fd)
    checkout_raw = _fd_proc_path(checkout_fd)
    if work_raw is not None:
        work_n = os.path.normpath(work_raw)
        if os.path.basename(work_n) != WORK_DIRNAME:
            _raise_unsafe(path, "directory slot is unsafe")
        if checkout_raw is not None:
            checkout_n = os.path.normpath(checkout_raw)
            expected = os.path.normpath(os.path.join(checkout_n, WORK_DIRNAME))
            if work_n != expected or not _is_strict_child(work_n, checkout_n):
                _raise_unsafe(path, "directory slot is unsafe")
    parent: int | None = None
    try:
        try:
            parent = os.open("..", _parent_open_flags(), dir_fd=work_fd)
            pst = os.fstat(parent)
        except OSError:
            _raise_unsafe(path, "directory slot is unsafe")
        if not _same_inode(pst, checkout_st):
            _raise_unsafe(path, "directory slot is unsafe")
    finally:
        _close_fd(parent)
    named: int | None = None
    try:
        try:
            named = os.open(WORK_DIRNAME, _dir_open_flags(), dir_fd=checkout_fd)
            named_st = os.fstat(named)
        except StagingError:
            raise
        except OSError as exc:
            _map_oserror(path, exc)
        if not stat.S_ISDIR(named_st.st_mode) or not _same_inode(named_st, work_st):
            _raise_unsafe(path, "directory slot is unsafe")
    finally:
        _close_fd(named)


def _require_staging_fds(
    *,
    parent_fd: int,
    work_fd: int,
    checkout_fd: int,
    path: Path,
) -> None:
    _require_fd_inside_work(parent_fd, work_fd, path)
    _require_work_still_in_checkout(work_fd, checkout_fd, path)


def _stat_at(parent_fd: int, name: str, path: Path) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(path, exc)


def _open_dir_path(path: Path) -> int:
    try:
        return os.open(os.fspath(path), _dir_open_flags())
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(path, exc)


def _open_dir_at(parent_fd: int, name: str, path: Path) -> int:
    try:
        fd = os.open(name, _dir_open_flags(), dir_fd=parent_fd)
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(path, exc)
    try:
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            _raise_unsafe(path, "directory slot is not a directory")
        return fd
    except StagingError:
        _close_fd(fd)
        raise
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _close_fd(fd)
        _map_oserror(path, exc)


def _ensure_dir_at(parent_fd: int, name: str, path: Path, *, work_fd: int | None) -> int:
    st = _stat_at(parent_fd, name, path)
    created = False
    if st is None:
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
        except (NotADirectoryError, OSError) as exc:
            _map_oserror(path, exc)
    elif stat.S_ISLNK(st.st_mode):
        _raise_unsafe(path, "path component is a symlink")
    elif _is_special(st) or stat.S_ISREG(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        _raise_unsafe(path, "directory slot is not a directory")
    if created:
        _fsync_fd(parent_fd)
    fd = _open_dir_at(parent_fd, name, path)
    try:
        if work_fd is not None:
            _require_fd_inside_work(fd, work_fd, path)
        return fd
    except StagingError:
        _close_fd(fd)
        raise


def _read_regular_file_at(parent_fd: int, name: str, path: Path) -> bytes:
    try:
        fd = os.open(name, _file_read_flags(), dir_fd=parent_fd)
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        if getattr(exc, "errno", None) in {errno.ELOOP, getattr(errno, "EMLINK", 31)}:
            _raise_unsafe(path, "path component is a symlink")
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "target is not a readable regular file",
            {"path": path.as_posix()},
        ) from exc
    try:
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            _raise_unsafe(path, "target is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except StagingError:
        raise
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(path, exc)
    finally:
        _close_fd(fd)


def _mkstemp_at(dir_fd: int, path: Path) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    for _ in range(10000):
        name = ".tmp." + os.urandom(8).hex()
        try:
            fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
        except FileExistsError:
            continue
        except (NotADirectoryError, OSError) as exc:
            _map_oserror(path, exc)
        return fd, name
    _raise_unsafe(path, "directory slot is unsafe")


def _link_at(*, src_name: str, dst_name: str, src_dir_fd: int, dst_dir_fd: int) -> None:
    try:
        os.link(
            src_name,
            dst_name,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=False,
        )
    except TypeError:
        os.link(src_name, dst_name, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def _unlink_at(parent_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=parent_fd)
    except OSError:
        pass


def _atomic_install(
    work_fd: int,
    parent_fd: int,
    filename: str,
    data: bytes,
    *,
    target: Path,
    checkout_fd: int,
) -> bool:
    """Install *data* as *filename* in *parent_fd*.

    Temp is a sibling under *parent_fd* (not the `.work` root). Re-check that
    *parent_fd* is still a real directory inside *work_fd* and that *work_fd*
    is still checkout's real `.work` immediately before and after the link.
    If the post-link check fails, unlink dest via *parent_fd* and raise
    WORK_PATH_UNSAFE.

    Returns True when the target already held the same bytes, False when this
    call created the file.
    """
    tmp_fd: int | None = None
    tmp_name: str | None = None
    linked = False
    try:
        _require_staging_fds(
            parent_fd=parent_fd,
            work_fd=work_fd,
            checkout_fd=checkout_fd,
            path=target,
        )
        tmp_fd, tmp_name = _mkstemp_at(parent_fd, target)
        try:
            offset = 0
            while offset < len(data):
                offset += os.write(tmp_fd, data[offset:])
            os.fsync(tmp_fd)
        except (NotADirectoryError, FileExistsError, OSError) as exc:
            _map_oserror(target, exc)
        _close_fd(tmp_fd)
        tmp_fd = None
        _require_staging_fds(
            parent_fd=parent_fd,
            work_fd=work_fd,
            checkout_fd=checkout_fd,
            path=target,
        )
        try:
            _link_at(
                src_name=tmp_name,
                dst_name=filename,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            linked = True
        except FileExistsError:
            existing = _stat_at(parent_fd, filename, target)
            if existing is None:
                raise StagingError(
                    CODE_STAGING_CONFLICT,
                    "target exists with different bytes",
                    {"path": target.as_posix()},
                )
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                _raise_unsafe(target, "target is not a regular file")
            current = _read_regular_file_at(parent_fd, filename, target)
            if current == data:
                _require_staging_fds(
                    parent_fd=parent_fd,
                    work_fd=work_fd,
                    checkout_fd=checkout_fd,
                    path=target,
                )
                return True
            raise StagingError(
                CODE_STAGING_CONFLICT,
                "target exists with different bytes",
                {"path": target.as_posix()},
            )
        except (NotADirectoryError, OSError) as exc:
            _map_oserror(target, exc)
        try:
            _require_staging_fds(
                parent_fd=parent_fd,
                work_fd=work_fd,
                checkout_fd=checkout_fd,
                path=target,
            )
        except StagingError:
            if linked:
                _unlink_at(parent_fd, filename)
            raise
        _fsync_fd(parent_fd)
        _fsync_fd(work_fd)
        return False
    finally:
        _close_fd(tmp_fd)
        if tmp_name is not None:
            _unlink_at(parent_fd, tmp_name)


def _existing_same_bytes(parent_fd: int, filename: str, data: bytes, path: Path) -> bool:
    existing = _stat_at(parent_fd, filename, path)
    if existing is None:
        return False
    if stat.S_ISLNK(existing.st_mode):
        _raise_unsafe(path, "path component is a symlink")
    if _is_special(existing) or stat.S_ISDIR(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
        _raise_unsafe(path, "target is not a regular file")
    current = _read_regular_file_at(parent_fd, filename, path)
    if current == data:
        return True
    raise StagingError(
        CODE_STAGING_CONFLICT,
        "target exists with different bytes",
        {"path": path.as_posix()},
    )


def _rewalk_parent(
    checkout_fd: int,
    names: tuple[str, ...],
    paths: tuple[Path, ...],
    work_root: Path,
) -> tuple[int, int, list[int]]:
    """Re-open checkout → .work → names with O_NOFOLLOW. Return work, parent, owned fds."""
    owned: list[int] = []
    try:
        work_fd = _open_dir_at(checkout_fd, WORK_DIRNAME, work_root)
        owned.append(work_fd)
        _require_work_still_in_checkout(work_fd, checkout_fd, work_root)
        current = work_fd
        for name, path in zip(names, paths, strict=True):
            nxt = _open_dir_at(current, name, path)
            owned.append(nxt)
            _require_fd_inside_work(nxt, work_fd, path)
            _require_work_still_in_checkout(work_fd, checkout_fd, path)
            current = nxt
        return work_fd, current, owned
    except StagingError:
        for fd in reversed(owned):
            _close_fd(fd)
        raise
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        for fd in reversed(owned):
            _close_fd(fd)
        _map_oserror(work_root if not paths else paths[-1], exc)


def _require_same_directory(
    fd: int,
    expected: os.stat_result,
    path: Path,
) -> None:
    current = _require_live_dir_fd(fd, path)
    if not _same_inode(current, expected):
        _raise_unsafe(path, "directory identity changed")


def _verify_transaction_inspect_session(
    *,
    checkout: Path,
    checkout_fd: int,
    work_fd: int,
    batch_fd: int,
    transport_fd: int,
    content_fd: int,
    batch: str,
    work_root: Path,
    batch_path: Path,
    transport_path: Path,
    content_path: Path,
    identities: tuple[os.stat_result, ...],
) -> None:
    """Re-prove one retained transaction-inspect directory lineage."""
    retained = (
        (checkout_fd, identities[0], checkout),
        (work_fd, identities[1], work_root),
        (batch_fd, identities[2], batch_path),
        (transport_fd, identities[3], transport_path),
        (content_fd, identities[4], content_path),
    )
    for fd, expected, path in retained:
        _require_same_directory(fd, expected, path)
    for fd, path in (
        (batch_fd, batch_path),
        (transport_fd, transport_path),
        (content_fd, content_path),
    ):
        _require_fd_inside_work(fd, work_fd, path)
    _require_work_still_in_checkout(work_fd, checkout_fd, work_root)

    compared: list[int] = []
    try:
        named_checkout = _open_dir_path(checkout)
        compared.append(named_checkout)
        _require_same_directory(named_checkout, identities[0], checkout)
        named_work = _open_dir_at(named_checkout, WORK_DIRNAME, work_root)
        compared.append(named_work)
        _require_same_directory(named_work, identities[1], work_root)
        named_batch = _open_dir_at(named_work, batch, batch_path)
        compared.append(named_batch)
        _require_same_directory(named_batch, identities[2], batch_path)
        named_transport = _open_dir_at(
            named_batch, "transaction-inspect", transport_path,
        )
        compared.append(named_transport)
        _require_same_directory(named_transport, identities[3], transport_path)
        named_content = _open_dir_at(named_transport, "content", content_path)
        compared.append(named_content)
        _require_same_directory(named_content, identities[4], content_path)
    finally:
        for fd in reversed(compared):
            _close_fd(fd)


def _require_exact_staged_file(
    parent_fd: int,
    filename: str,
    expected: bytes,
    path: Path,
) -> None:
    if _read_regular_file_at(parent_fd, filename, path) != expected:
        _raise_unsafe(path, "staged file bytes changed")


def _require_safe_transaction_inspect_entries(
    *,
    transport_fd: int,
    content_fd: int,
    transport_path: Path,
    content_path: Path,
    bundle_required: bool,
) -> None:
    """Close directory shapes while allowing safe digest-addressed orphans."""
    try:
        transport_names = set(os.listdir(transport_fd))
    except OSError as exc:
        _map_oserror(transport_path, exc)
    required = {"content", "bundle.json"} if bundle_required else {"content"}
    allowed = {"content", "bundle.json"}
    if not required <= transport_names or not transport_names <= allowed:
        _raise_unsafe(transport_path, "transaction staging directory has unsafe entries")
    for name in transport_names:
        info = _stat_at(transport_fd, name, transport_path / name)
        if info is None:
            _raise_unsafe(transport_path / name, "transaction staging entry changed")
        if name == "content":
            if not stat.S_ISDIR(info.st_mode):
                _raise_unsafe(content_path, "content slot is not a directory")
        elif not stat.S_ISREG(info.st_mode):
            _raise_unsafe(transport_path / name, "bundle slot is not a regular file")

    try:
        content_names = os.listdir(content_fd)
    except OSError as exc:
        _map_oserror(content_path, exc)
    for name in content_names:
        target = content_path / name
        if re.fullmatch(r"[0-9a-f]{64}", name) is None:
            _raise_unsafe(target, "content directory has an unsafe entry")
        info = _stat_at(content_fd, name, target)
        if info is None or not stat.S_ISREG(info.st_mode):
            _raise_unsafe(target, "content entry is not a regular file")


def _stage_transaction_inspect_files(
    *,
    batch_id: object,
    content: tuple[tuple[str, bytes], ...],
    bundle: bytes,
) -> _TransactionInspectStageResult:
    """Stage one fixed transaction-inspect transport in one retained session."""
    batch = validate_batch_id(batch_id)
    if type(content) is not tuple or not content:
        raise StagingError(CODE_WORK_PATH_UNSAFE, "invalid content request")
    previous = ""
    for item in content:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", item[0]) is None
            or item[0] <= previous
            or type(item[1]) is not bytes
        ):
            raise StagingError(CODE_WORK_PATH_UNSAFE, "invalid content request")
        previous = item[0]
    if type(bundle) is not bytes:
        raise StagingError(CODE_WORK_PATH_UNSAFE, "invalid bundle request")

    checkout = resolve_checkout_root()
    work_root = checkout / WORK_DIRNAME
    batch_path = work_root / batch
    transport_path = batch_path / "transaction-inspect"
    content_path = transport_path / "content"
    bundle_path = transport_path / "bundle.json"
    for target in (batch_path, transport_path, content_path, bundle_path):
        _assert_inside_work(target, work_root)

    checkout_fd: int | None = None
    retained: list[int] = []
    try:
        checkout_fd = _open_dir_path(checkout)
        work_fd = _ensure_dir_at(
            checkout_fd, WORK_DIRNAME, work_root, work_fd=None,
        )
        retained.append(work_fd)
        _require_work_still_in_checkout(work_fd, checkout_fd, work_root)
        batch_fd = _ensure_dir_at(
            work_fd, batch, batch_path, work_fd=work_fd,
        )
        retained.append(batch_fd)
        transport_fd = _ensure_dir_at(
            batch_fd, "transaction-inspect", transport_path, work_fd=work_fd,
        )
        retained.append(transport_fd)
        content_fd = _ensure_dir_at(
            transport_fd, "content", content_path, work_fd=work_fd,
        )
        retained.append(content_fd)
        identities = tuple(
            _require_live_dir_fd(fd, path)
            for fd, path in (
                (checkout_fd, checkout),
                (work_fd, work_root),
                (batch_fd, batch_path),
                (transport_fd, transport_path),
                (content_fd, content_path),
            )
        )

        def verify() -> None:
            _verify_transaction_inspect_session(
                checkout=checkout,
                checkout_fd=checkout_fd,
                work_fd=work_fd,
                batch_fd=batch_fd,
                transport_fd=transport_fd,
                content_fd=content_fd,
                batch=batch,
                work_root=work_root,
                batch_path=batch_path,
                transport_path=transport_path,
                content_path=content_path,
                identities=identities,
            )

        verify()
        reused: list[bool] = []
        for digest, data in content:
            target = content_path / digest
            verify()
            if _existing_same_bytes(content_fd, digest, data, target):
                was_reused = True
            else:
                was_reused = _atomic_install(
                    work_fd, content_fd, digest, data,
                    target=target, checkout_fd=checkout_fd,
                )
            verify()
            reused.append(was_reused)

        verify()
        _require_safe_transaction_inspect_entries(
            transport_fd=transport_fd,
            content_fd=content_fd,
            transport_path=transport_path,
            content_path=content_path,
            bundle_required=False,
        )
        for digest, data in content:
            _require_exact_staged_file(
                content_fd, digest, data, content_path / digest,
            )
        verify()
        if _existing_same_bytes(
            transport_fd, "bundle.json", bundle, bundle_path,
        ):
            bundle_reused = True
        else:
            bundle_reused = _atomic_install(
                work_fd, transport_fd, "bundle.json", bundle,
                target=bundle_path, checkout_fd=checkout_fd,
            )
        verify()
        _require_safe_transaction_inspect_entries(
            transport_fd=transport_fd,
            content_fd=content_fd,
            transport_path=transport_path,
            content_path=content_path,
            bundle_required=True,
        )
        for digest, data in content:
            _require_exact_staged_file(
                content_fd, digest, data, content_path / digest,
            )
        _require_exact_staged_file(
            transport_fd, "bundle.json", bundle, bundle_path,
        )
        verify()
        return _TransactionInspectStageResult(tuple(reused), bundle_reused)
    except StagingError:
        raise
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(bundle_path, exc)
    finally:
        for fd in reversed(retained):
            _close_fd(fd)
        _close_fd(checkout_fd)


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
    target = work_root.joinpath(batch, *parts)
    work_st = _lstat(work_root)
    if work_st is not None:
        if stat.S_ISLNK(work_st.st_mode):
            _raise_unsafe(work_root, "path component is a symlink")
        if _is_special(work_st) or stat.S_ISREG(work_st.st_mode) or not stat.S_ISDIR(work_st.st_mode):
            _raise_unsafe(work_root, "directory slot is not a directory")
    current = work_root
    segments = (batch, *parts)
    for index, part in enumerate(segments):
        current = current / part
        st = _lstat(current)
        if st is None:
            continue
        if stat.S_ISLNK(st.st_mode):
            _raise_unsafe(current, "path component is a symlink")
        last = index == len(segments) - 1
        if not last and (
            _is_special(st) or stat.S_ISREG(st.st_mode) or not stat.S_ISDIR(st.st_mode)
        ):
            _raise_unsafe(current, "directory slot is not a directory")
    _assert_inside_work(target, work_root)

    checkout_fd: int | None = None
    created: list[int] = []
    rewalked: list[int] = []
    try:
        checkout_fd = _open_dir_path(checkout)
        work_created = _ensure_dir_at(checkout_fd, WORK_DIRNAME, work_root, work_fd=None)
        created.append(work_created)
        _require_work_still_in_checkout(work_created, checkout_fd, work_root)
        current = work_created
        intermediate_names = (batch, *parts[:-1])
        intermediate_paths: list[Path] = []
        current_path = work_root
        for part in intermediate_names:
            current_path = current_path / part
            intermediate_paths.append(current_path)
            nxt = _ensure_dir_at(current, part, current_path, work_fd=work_created)
            created.append(nxt)
            _require_staging_fds(
                parent_fd=nxt,
                work_fd=work_created,
                checkout_fd=checkout_fd,
                path=current_path,
            )
            current = nxt
        _assert_inside_work(target, work_root)

        work_fd, parent_fd, rewalked = _rewalk_parent(
            checkout_fd,
            intermediate_names,
            tuple(intermediate_paths),
            work_root,
        )
        if _existing_same_bytes(parent_fd, parts[-1], data, target):
            _require_staging_fds(
                parent_fd=parent_fd,
                work_fd=work_fd,
                checkout_fd=checkout_fd,
                path=target,
            )
            return StageResult(path=target, already_staged=True)
        already = _atomic_install(
            work_fd,
            parent_fd,
            parts[-1],
            data,
            target=target,
            checkout_fd=checkout_fd,
        )
        return StageResult(path=target, already_staged=already)
    except StagingError:
        raise
    except (NotADirectoryError, FileExistsError, OSError) as exc:
        _map_oserror(target, exc)
    finally:
        for fd in reversed(rewalked):
            _close_fd(fd)
        for fd in reversed(created):
            _close_fd(fd)
        _close_fd(checkout_fd)
