"""Shared lightweight-library policy, locks, inventories, and journals.

T2 helper used by light_library and light_backup. extract_pdf acquires the
same workspace lock path through try_workspace_lock; a replacement staging
workspace uses its own lock file and does not reacquire the live lock.

Journals use schema video-paper-wiki.light-library-operation.v1. The documented
versioned shape is a closed field set: schema, operation_id, kind, paper_id,
archive_id, phase, owned_relative_paths, source_inventory, file_inventory,
directories, and replace-only new_paper_id/pdf_sha256/title/new_file_inventory/
new_directories/stage_file_inventory/stage_directories. A complete journal may
add outcome. kind, phase and outcome are strings; booleans are not integer
schema versions. Recognized outcomes are archived, restored, replaced, and
aborted-before-staging. The aborted outcome is a settled failed pre-staging
replacement: the old live paper is unchanged, no replacement is claimed, and
the event is not a backup blocker. Unknown fields, null identifiers, or
mismatched filename/IDs are invalid.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from video_paper_wiki_research.contracts import ResearchError

OK = "OK"
WORKSPACE_INVALID = "WORKSPACE_INVALID"
SOURCE_INVALID = "SOURCE_INVALID"
LIGHT_WORKSPACE_BUSY = "LIGHT_WORKSPACE_BUSY"
LIGHT_LIBRARY_INVALID = "LIGHT_LIBRARY_INVALID"
LIGHT_LIBRARY_CONFLICT = "LIGHT_LIBRARY_CONFLICT"
LIGHT_LIBRARY_NEEDS_RECOVERY = "LIGHT_LIBRARY_NEEDS_RECOVERY"
LIGHT_BACKUP_INVALID = "LIGHT_BACKUP_INVALID"
LIGHT_BACKUP_CONFLICT = "LIGHT_BACKUP_CONFLICT"

LIBRARY_DIRNAME = ".light-library"
ARCHIVE_DIRNAME = "archive"
OPERATIONS_DIRNAME = "operations"
STAGING_DIRNAME = "staging"
KNOWLEDGE_DIRNAME = ".light-knowledge"
KNOWLEDGE_STAGING = "staging"
WORKFLOW_DIRNAME = ".light-workflow"
LOCKS_DIRNAME = "locks"
SESSIONS_DIRNAME = "sessions"
WORKFLOW_STAGING = "staging"
HISTORY_DIRNAME = "history"
WORKSPACE_LOCK_NAME = "workspace.lock"
PAPER_DIRNAME = "papers"
INDEX_DIRNAME = ".light-index"
TRANSACTIONS_DIR = ".light-transactions"

OPERATION_SCHEMA = "video-paper-wiki.light-library-operation.v1"
ARCHIVE_SCHEMA = "video-paper-wiki.light-paper-archive.v1"
ARCHIVE_EVENT_SCHEMA = "video-paper-wiki.light-paper-archive-event.v1"
BACKUP_SCHEMA = "video-paper-wiki.light-backup.v1"
RESTORATION_SCHEMA = "video-paper-wiki.light-backup-restoration.v1"
STAGING_OWNER_SCHEMA = "video-paper-wiki.light-library-staging.v1"
LIBRARY_SCHEMA = "video-paper-wiki.light-library.v1"
OUTCOME_ARCHIVED = "archived"
OUTCOME_RESTORED = "restored"
OUTCOME_REPLACED = "replaced"
OUTCOME_ABORTED_BEFORE_STAGING = "aborted-before-staging"
JOURNAL_COMMON_FIELDS = frozenset(
    {
        "schema",
        "operation_id",
        "kind",
        "paper_id",
        "archive_id",
        "phase",
        "owned_relative_paths",
        "source_inventory",
        "file_inventory",
        "directories",
    }
)
JOURNAL_REPLACE_FIELDS = JOURNAL_COMMON_FIELDS | frozenset(
    {
        "new_paper_id",
        "pdf_sha256",
        "title",
        "new_file_inventory",
        "new_directories",
        "stage_file_inventory",
        "stage_directories",
    }
)
JOURNAL_OUTCOME_FIELD = "outcome"
ARCHIVE_KIND_PHASES = frozenset({"intent", "archived", "complete"})
RESTORE_KIND_PHASES = frozenset({"intent", "restored", "complete"})
REPLACE_KIND_PHASES = frozenset({"intent", "staged", "old_archived", "new_published", "complete"})
STAGING_OWNER_FIELDS = frozenset(
    {
        "schema",
        "version",
        "kind",
        "operation_id",
        "target_id",
        "intended_relative_target",
        "allowed_payload_set",
    }
)
ARCHIVE_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "archive_id",
        "paper_id",
        "original_directory",
        "transport_directory",
        "files",
        "directories",
    }
)
SOURCE_INVENTORY_FIELDS = frozenset({"path", "size_bytes", "sha256"})
FILE_INVENTORY_FIELDS = frozenset(
    {"original_relative_path", "archive_relative_path", "size_bytes", "sha256"}
)
ARCHIVE_EVENT_FIELDS = frozenset({"schema", "archive_id", "paper_id", "operation_id", "state"})

PAPER_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX_ID = re.compile(r"^[0-9a-f]{32}$")
HEX_ID_FLEX = re.compile(r"^[0-9a-f]{16,64}$")

MAX_FILES = 10_000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ZIP_BYTES = 136 * 1024 * 1024
MAX_TITLE = 500
MAX_TAG_LEN = 100
MAX_TAGS = 30

ALLOWED_TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".css",
        ".html",
        ".sh",
        ".sql",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".cu",
        ".cuh",
        ".go",
        ".java",
        ".r",
        ".tex",
        ".bib",
        ".csv",
        ".tsv",
        ".xml",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
    }
)
ALLOWED_TEXT_BASENAMES = frozenset({"readme", "license", "notice", "makefile"})
FORBIDDEN_MEDIA_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".bin",
        ".pt",
        ".pth",
        ".onnx",
        ".safetensors",
        ".gguf",
        ".pkl",
        ".pickle",
        ".npy",
        ".npz",
        ".h5",
        ".hdf5",
        ".ckpt",
        ".weights",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".ico",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".wasm",
        ".whl",
        ".egg",
        ".model",
    }
)
BINARY_PREFIXES = (
    b"%PDF-",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"PK\x03\x04",
    b"RIFF",
    b"\x7fELF",
    b"\x00\x00\x01\x00",
)

LIBRARY_INJECT_POINTS = (
    "after_intent",
    "before_archive_move",
    "after_archive_move",
    "before_restore_move",
    "after_restore_move",
    "after_replace_staged",
    "before_old_archive",
    "after_old_archive",
    "before_new_publish",
    "after_new_publish",
    "after_metadata_tmp",
    "after_backup_snapshot",
    "before_backup_publish",
    "before_backup_rename",
    "before_restore_publish",
)
_inject_hooks: dict[str, Callable[[str], None]] = {}


class _Busy(Exception):
    pass


class _AdvisoryLock:
    def __init__(self, fd: int) -> None:
        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None  # type: ignore[assignment]


def set_library_inject_hook(point: str | None, hook: Callable[[str], None] | None = None) -> None:
    """Test-only seam. Production callers must not set this."""
    _inject_hooks.clear()
    if point is not None and hook is not None:
        if point not in LIBRARY_INJECT_POINTS:
            raise ValueError(f"unknown inject point: {point}")
        _inject_hooks[point] = hook


def run_library_inject(point: str) -> None:
    hook = _inject_hooks.get(point)
    if hook is not None:
        hook(point)


def fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def closed(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": status, "message": message}
    payload.update(extra)
    return payload


def ok_result(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "status": OK, "message": message}
    payload.update(extra)
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def persisted_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def sha256_canonical(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def new_hex_id() -> str:
    return secrets.token_hex(16)


def is_hex_id(value: object) -> bool:
    return type(value) is str and HEX_ID_FLEX.fullmatch(value) is not None


def is_paper_id(value: object) -> bool:
    return type(value) is str and PAPER_ID_PATTERN.fullmatch(value) is not None


def paper_digest(paper_id: str) -> str:
    return paper_id.split(":", 1)[1]


def require_paper_id(value: object) -> str:
    if not is_paper_id(value):
        fail(LIGHT_LIBRARY_INVALID, "paper_id must be sha256:<64 lowercase hex>")
    return str(value)


def require_hex_id(value: object, *, name: str) -> str:
    if not is_hex_id(value):
        fail(LIGHT_LIBRARY_INVALID, f"{name} must be a lowercase hexadecimal id")
    return str(value)


def _as_path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        return value
    if type(value) is str:
        return Path(value)
    fail(LIGHT_LIBRARY_INVALID, f"{name} must be a path")
    raise AssertionError("unreachable")


def absolute_path(value: object, name: str) -> Path:
    path = _as_path(value, name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.normpath(path))


def chain_has_symlink(path: Path, *, stop_at: Path | None = None) -> bool:
    cursor = path
    while True:
        try:
            if cursor.is_symlink():
                return True
        except OSError:
            return True
        if stop_at is not None and cursor == stop_at:
            return False
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent


def has_work_component(path: Path) -> bool:
    return ".work" in path.parts


def require_work_path(
    value: object,
    *,
    name: str,
    must_exist: bool,
    allow_missing: bool = False,
    kind: str = "dir",
) -> Path:
    given = absolute_path(value, name)
    if not has_work_component(given):
        fail(WORKSPACE_INVALID, f"{name} must be under .work/**", {"path": str(given)})
    if chain_has_symlink(given):
        fail(WORKSPACE_INVALID, f"{name} must not traverse a symlink", {"path": str(given)})
    if given.exists() or os.path.lexists(given):
        if given.is_symlink():
            fail(WORKSPACE_INVALID, f"{name} must not be a symlink", {"path": str(given)})
        if kind == "dir" and not given.is_dir():
            fail(WORKSPACE_INVALID, f"{name} must be a regular directory under .work/**", {"path": str(given)})
        if kind == "file" and not given.is_file():
            fail(WORKSPACE_INVALID, f"{name} must be a regular file under .work/**", {"path": str(given)})
    elif must_exist and not allow_missing:
        fail(WORKSPACE_INVALID, f"{name} must be a regular {'directory' if kind == 'dir' else 'file'} under .work/**", {"path": str(given)})
    resolved = given.resolve()
    if not has_work_component(resolved):
        fail(WORKSPACE_INVALID, f"{name} must be under .work/**", {"path": str(resolved)})
    if chain_has_symlink(resolved):
        fail(WORKSPACE_INVALID, f"{name} must not traverse a symlink", {"path": str(resolved)})
    return resolved if (given.exists() or allow_missing) else resolved


def require_explicit_extra_markdown(value: object, *, name: str = "extra_outputs item") -> Path:
    """Caller-selected read-only extra Markdown; may be outside .work."""
    given = absolute_path(value, name)
    if chain_has_symlink(given):
        fail(WORKSPACE_INVALID, f"{name} must not traverse a symlink", {"path": str(given)})
    if given.is_symlink() or not given.is_file():
        fail(LIGHT_BACKUP_INVALID, f"{name} must be a regular .md file", {"path": str(given)})
    if file_is_hardlinked(given):
        fail(LIGHT_BACKUP_INVALID, f"{name} must not be hardlinked", {"path": str(given)})
    if given.suffix.casefold() != ".md":
        fail(LIGHT_BACKUP_INVALID, f"{name} must be a regular .md text file", {"path": str(given)})
    resolved = given.resolve()
    if chain_has_symlink(resolved) or resolved.is_symlink() or not resolved.is_file() or file_is_hardlinked(resolved):
        fail(LIGHT_BACKUP_INVALID, f"{name} must be a regular file without symlink or hardlink", {"path": str(resolved)})
    return resolved


def exclusive_rename(source: Path, dest: Path) -> None:
    """Rename source to dest only if dest does not exist. Raises FileExistsError."""
    if os.path.lexists(dest):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(dest))
    src_b = os.fsencode(source)
    dest_b = os.fsencode(dest)
    if sys.platform == "darwin":
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        rc = libc.renamex_np(src_b, dest_b, ctypes.c_uint(0x00000004))
        if rc != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), str(dest))
        return
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rc = renameat2(-100, src_b, -100, dest_b, 1)
        if rc != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), str(dest))
        return
    fail(LIGHT_BACKUP_CONFLICT, "exclusive directory publication is unsupported on this platform", {"path": str(dest)})


def require_workspace(workspace_root: Path, *, create: bool = False) -> Path:
    given = absolute_path(workspace_root, "workspace_root")
    if create and not os.path.lexists(given):
        if not has_work_component(given):
            fail(WORKSPACE_INVALID, "workspace_root must be under .work/**", {"path": str(given)})
        given.mkdir(parents=True, exist_ok=True)
    return require_work_path(given, name="workspace_root", must_exist=True, kind="dir")


def is_regular_dir(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_dir()


def is_regular_file(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_file()


def entry_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.is_dir():
        return "dir"
    return "other"


def list_names(directory: Path) -> list[str]:
    try:
        return sorted(item.name for item in directory.iterdir())
    except OSError:
        return []


def file_is_hardlinked(path: Path) -> bool:
    try:
        return path.is_file() and (not path.is_symlink()) and path.stat().st_nlink > 1
    except OSError:
        return True


def text_name_allowed(name: str) -> bool:
    folded = name.casefold()
    if folded in ALLOWED_TEXT_BASENAMES:
        return True
    suffix = Path(folded).suffix
    return suffix in ALLOWED_TEXT_EXTENSIONS


def media_name_forbidden(name: str) -> bool:
    return Path(name.casefold()).suffix in FORBIDDEN_MEDIA_EXTENSIONS


def looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    for prefix in BINARY_PREFIXES:
        if data.startswith(prefix):
            return True
    return False


def decode_utf8_text(data: bytes) -> str | None:
    if looks_binary(data):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeError:
        return None


def classify_text_file(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink():
        return {"kind": "unsafe", "reason": f"{label} is a symlink", "path": str(path)}
    if not path.is_file():
        return {"kind": "unsafe", "reason": f"{label} is not a regular file", "path": str(path)}
    if file_is_hardlinked(path):
        return {"kind": "unsafe", "reason": f"{label} is hardlinked", "path": str(path)}
    if media_name_forbidden(path.name):
        return {"kind": "unsupported", "reason": f"{label} uses a forbidden media extension", "path": str(path)}
    if not text_name_allowed(path.name):
        return {"kind": "unsupported", "reason": f"{label} is not an allowed text/code file", "path": str(path)}
    try:
        size = path.stat().st_size
    except OSError:
        return {"kind": "unsafe", "reason": f"{label} is unreadable", "path": str(path)}
    if size > MAX_FILE_BYTES:
        return {"kind": "unsupported-size", "reason": f"{label} exceeds the 8 MiB text limit", "path": str(path), "size_bytes": size}
    try:
        data = path.read_bytes()
    except OSError:
        return {"kind": "unsafe", "reason": f"{label} is unreadable", "path": str(path)}
    if len(data) != size:
        return {"kind": "unsafe", "reason": f"{label} changed while reading", "path": str(path)}
    if decode_utf8_text(data) is None:
        return {"kind": "unsupported", "reason": f"{label} is not UTF-8 text or contains binary bytes", "path": str(path)}
    return {"kind": "ok", "size_bytes": size, "sha256": sha256_bytes(data), "data": data}


def workspace_lock_path(workspace: Path) -> Path:
    return workspace / WORKFLOW_DIRNAME / LOCKS_DIRNAME / WORKSPACE_LOCK_NAME


def ensure_workspace_lock_file(workspace: Path) -> Path:
    root = workspace / WORKFLOW_DIRNAME
    if root.is_symlink():
        fail(WORKSPACE_INVALID, ".light-workflow must not be a symlink", {"path": str(root)})
    if os.path.lexists(root) and not root.is_dir():
        fail(WORKSPACE_INVALID, ".light-workflow must be a regular directory", {"path": str(root)})
    if not os.path.lexists(root):
        root.mkdir(exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        fail(WORKSPACE_INVALID, ".light-workflow must be a regular directory", {"path": str(root)})
    locks = root / LOCKS_DIRNAME
    if locks.is_symlink():
        fail(WORKSPACE_INVALID, "workflow locks must not be a symlink", {"path": str(locks)})
    if os.path.lexists(locks) and not locks.is_dir():
        fail(WORKSPACE_INVALID, "workflow locks must be a regular directory", {"path": str(locks)})
    if not os.path.lexists(locks):
        locks.mkdir(exist_ok=True)
    if locks.is_symlink() or not locks.is_dir():
        fail(WORKSPACE_INVALID, "workflow locks must be a regular directory", {"path": str(locks)})
    path = locks / WORKSPACE_LOCK_NAME
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        fail(WORKSPACE_INVALID, "workspace lock path must be a regular file", {"path": str(path)})
    return path


def try_workspace_lock(workspace: Path) -> _AdvisoryLock | None:
    """Acquire `.light-workflow/locks/workspace.lock` for the given workspace only."""
    path = ensure_workspace_lock_file(workspace)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except OSError:
        fail(WORKSPACE_INVALID, "workspace lock path is not a writable regular file", {"path": str(path)})
        raise AssertionError("unreachable")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except OSError:
        os.close(fd)
        return None
    return _AdvisoryLock(fd)


@contextmanager
def exclusive_workspace_lock(workspace: Path) -> Iterator[None]:
    lock = try_workspace_lock(workspace)
    if lock is None:
        raise _Busy()
    try:
        yield
    finally:
        lock.release()


def load_json_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict:
        return None
    return value


def load_persisted_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict:
        return None
    try:
        if raw != persisted_bytes(value):
            return None
    except (TypeError, ValueError):
        return None
    return value


def write_bytes_atomic(path: Path, data: bytes, *, inject: str | None = None) -> None:
    """Write data through an exclusively created owned temp. Never reuse dest.tmp."""
    if chain_has_symlink(path):
        fail(LIGHT_LIBRARY_INVALID, "managed path must not traverse a symlink", {"path": str(path)})
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        fail(LIGHT_LIBRARY_INVALID, "managed path must be a regular file", {"path": str(path)})
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        fail(LIGHT_LIBRARY_INVALID, "managed parent must be a regular directory", {"path": str(parent)})
    if chain_has_symlink(parent):
        fail(LIGHT_LIBRARY_INVALID, "managed parent must not traverse a symlink", {"path": str(parent)})
    dest_identity: tuple[int, int] | None = None
    if os.path.lexists(path):
        try:
            dest_stat = path.stat()
        except OSError:
            fail(LIGHT_LIBRARY_INVALID, "managed destination is unreadable", {"path": str(path)})
            raise AssertionError("unreachable")
        dest_identity = (dest_stat.st_dev, dest_stat.st_ino)
    created_tmp: Path | None = None
    fd: int | None = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        for _ in range(16):
            candidate = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
            if os.path.lexists(candidate) or candidate.is_symlink():
                continue
            try:
                fd = os.open(candidate, flags, 0o600)
            except OSError:
                continue
            created_tmp = candidate
            break
        if fd is None or created_tmp is None:
            fail(LIGHT_LIBRARY_CONFLICT, "could not exclusively create an owned temporary file", {"path": str(path)})
            raise AssertionError("unreachable")
        st = os.fstat(fd)
        if st.st_nlink != 1:
            fail(LIGHT_LIBRARY_CONFLICT, "owned temporary file became hardlinked", {"path": str(created_tmp)})
        view = memoryview(data)
        written = 0
        while written < len(data):
            n = os.write(fd, view[written:])
            if n <= 0:
                fail(LIGHT_LIBRARY_INVALID, "owned temporary write failed", {"path": str(created_tmp)})
            written += n
        os.fsync(fd)
        os.close(fd)
        fd = None
        if created_tmp.is_symlink() or not created_tmp.is_file() or created_tmp.stat().st_nlink != 1:
            fail(LIGHT_LIBRARY_CONFLICT, "owned temporary file identity changed", {"path": str(created_tmp)})
        if created_tmp.read_bytes() != data:
            fail(LIGHT_LIBRARY_INVALID, "owned temporary file bytes do not match the write", {"path": str(created_tmp)})
        if inject:
            run_library_inject(inject)
        if dest_identity is not None:
            if not os.path.lexists(path) or path.is_symlink() or not path.is_file():
                fail(LIGHT_LIBRARY_CONFLICT, "managed destination identity changed before replace", {"path": str(path)})
            now = path.stat()
            if (now.st_dev, now.st_ino) != dest_identity:
                fail(LIGHT_LIBRARY_CONFLICT, "managed destination identity changed before replace", {"path": str(path)})
        os.replace(created_tmp, path)
        created_tmp = None
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if created_tmp is not None and is_regular_file(created_tmp):
            try:
                if created_tmp.stat().st_nlink == 1:
                    created_tmp.unlink()
            except OSError:
                pass
        raise
    if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
        fail(LIGHT_LIBRARY_INVALID, "managed destination is not the written regular file", {"path": str(path)})


def write_bytes_create_only(path: Path, data: bytes) -> None:
    """Create dest only if absent. Never replace or overwrite an existing file."""
    if chain_has_symlink(path):
        fail(LIGHT_LIBRARY_INVALID, "managed path must not traverse a symlink", {"path": str(path)})
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        fail(LIGHT_LIBRARY_INVALID, "managed path must be a regular file", {"path": str(path)})
    if os.path.lexists(path):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(path))
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        fail(LIGHT_LIBRARY_INVALID, "managed parent must be a regular directory", {"path": str(parent)})
    if chain_has_symlink(parent):
        fail(LIGHT_LIBRARY_INVALID, "managed parent must not traverse a symlink", {"path": str(parent)})
    created_tmp: Path | None = None
    fd: int | None = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        for _ in range(16):
            candidate = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
            if os.path.lexists(candidate) or candidate.is_symlink():
                continue
            try:
                fd = os.open(candidate, flags, 0o600)
            except OSError:
                continue
            created_tmp = candidate
            break
        if fd is None or created_tmp is None:
            fail(LIGHT_LIBRARY_CONFLICT, "could not exclusively create an owned temporary file", {"path": str(path)})
            raise AssertionError("unreachable")
        st = os.fstat(fd)
        if st.st_nlink != 1:
            fail(LIGHT_LIBRARY_CONFLICT, "owned temporary file became hardlinked", {"path": str(created_tmp)})
        view = memoryview(data)
        written = 0
        while written < len(data):
            n = os.write(fd, view[written:])
            if n <= 0:
                fail(LIGHT_LIBRARY_INVALID, "owned temporary write failed", {"path": str(created_tmp)})
            written += n
        os.fsync(fd)
        os.close(fd)
        fd = None
        if created_tmp.is_symlink() or not created_tmp.is_file() or created_tmp.stat().st_nlink != 1:
            fail(LIGHT_LIBRARY_CONFLICT, "owned temporary file identity changed", {"path": str(created_tmp)})
        if created_tmp.read_bytes() != data:
            fail(LIGHT_LIBRARY_INVALID, "owned temporary file bytes do not match the write", {"path": str(created_tmp)})
        if os.path.lexists(path):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(path))
        try:
            os.link(created_tmp, path)
        except FileExistsError:
            raise
        except OSError:
            fail(LIGHT_LIBRARY_CONFLICT, "could not create-only publish the managed file", {"path": str(path)})
        created_tmp.unlink()
        created_tmp = None
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if created_tmp is not None and is_regular_file(created_tmp):
            try:
                if created_tmp.stat().st_nlink == 1:
                    created_tmp.unlink()
            except OSError:
                pass
        raise
    if path.is_symlink() or not path.is_file() or file_is_hardlinked(path) or path.read_bytes() != data:
        fail(LIGHT_LIBRARY_INVALID, "managed destination is not the written regular file", {"path": str(path)})


def write_persisted_atomic(path: Path, value: Mapping[str, Any], *, inject: str | None = None) -> bytes:
    encoded = persisted_bytes(value)
    write_bytes_atomic(path, encoded, inject=inject)
    return encoded


def ensure_library_dirs(workspace: Path) -> Path:
    root = workspace / LIBRARY_DIRNAME
    if root.is_symlink():
        fail(WORKSPACE_INVALID, ".light-library must not be a symlink", {"path": str(root)})
    if os.path.lexists(root) and not root.is_dir():
        fail(WORKSPACE_INVALID, ".light-library must be a regular directory", {"path": str(root)})
    if not os.path.lexists(root):
        root.mkdir(exist_ok=True)
    for name in (ARCHIVE_DIRNAME, OPERATIONS_DIRNAME, STAGING_DIRNAME):
        child = root / name
        if child.is_symlink():
            fail(WORKSPACE_INVALID, f".light-library/{name} must not be a symlink", {"path": str(child)})
        if os.path.lexists(child) and not child.is_dir():
            fail(WORKSPACE_INVALID, f".light-library/{name} must be a regular directory", {"path": str(child)})
        if not os.path.lexists(child):
            child.mkdir(exist_ok=True)
    return root


def operations_dir(workspace: Path) -> Path:
    return workspace / LIBRARY_DIRNAME / OPERATIONS_DIRNAME


def archive_dir(workspace: Path, archive_id: str) -> Path:
    return workspace / LIBRARY_DIRNAME / ARCHIVE_DIRNAME / archive_id


def staging_dir(workspace: Path, operation_id: str) -> Path:
    return workspace / LIBRARY_DIRNAME / STAGING_DIRNAME / operation_id


def operation_path(workspace: Path, operation_id: str) -> Path:
    return operations_dir(workspace) / f"{operation_id}.json"


def file_inventory_entry(*, relative: str, path: Path) -> dict[str, Any] | dict[str, Any]:
    classified = classify_text_file(path, label=relative)
    if classified["kind"] != "ok":
        return classified
    return {
        "kind": "ok",
        "path": relative,
        "size_bytes": classified["size_bytes"],
        "sha256": classified["sha256"],
    }


def inventory_row(relative: str, path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": relative, "size_bytes": len(data), "sha256": sha256_bytes(data)}


def walk_regular_tree(root: Path) -> tuple[list[Path], list[str], list[str]]:
    """Return (directories, file_relpaths, problems). Does not follow symlinks."""
    files: list[str] = []
    directories: list[Path] = []
    problems: list[str] = []
    if not os.path.lexists(root):
        return directories, files, problems
    if root.is_symlink() or not root.is_dir():
        problems.append("root is not a regular directory")
        return directories, files, problems
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        directories.append(base)
        dirnames.sort()
        filenames.sort()
        for name in list(dirnames):
            child = base / name
            if child.is_symlink() or not child.is_dir():
                problems.append(f"unsafe directory {child}")
                dirnames.remove(name)
        for name in filenames:
            child = base / name
            rel = str(child.relative_to(root)).replace("\\", "/")
            if child.is_symlink() or not child.is_file():
                problems.append(f"unsafe file {rel}")
                continue
            files.append(rel)
    directories.sort(key=lambda item: str(item))
    files.sort()
    return directories, files, problems


def posix_rel(path: str) -> str:
    return path.replace("\\", "/")


def validate_relpath(relative: str) -> str | None:
    if type(relative) is not str or not relative or relative.startswith("/") or "\\" in relative:
        return "path must be a relative POSIX member"
    if "\x00" in relative:
        return "path contains NUL"
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "path must not contain empty, dot, or parent segments"
    return None


def limits_ok(file_count: int, total_bytes: int) -> str | None:
    if file_count > MAX_FILES:
        return "inventory exceeds the 10,000 file limit"
    if total_bytes > MAX_UNCOMPRESSED_BYTES:
        return "inventory exceeds the 128 MiB uncompressed limit"
    return None


def control_chars(text: str) -> bool:
    return any(ord(char) < 32 for char in text)


def normalize_title(value: object) -> str | None:
    if type(value) is not str:
        return None
    text = value.strip()
    if not text or len(text) > MAX_TITLE or control_chars(text):
        return None
    return text


def normalize_tags(value: object) -> list[str] | None:
    if type(value) is not list:
        return None
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        if type(item) is not str:
            return None
        tag = item.strip()
        if not tag or len(tag) > MAX_TAG_LEN or control_chars(tag):
            return None
        if tag in seen:
            return None
        seen.add(tag)
        tags.append(tag)
        if len(tags) > MAX_TAGS:
            return None
    return tags


def library_root(workspace: Path) -> Path:
    return workspace / LIBRARY_DIRNAME


def _is_hex_digest(value: object) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def validate_source_inventory(value: object) -> bool:
    if type(value) is not list:
        return False
    seen: set[str] = set()
    for item in value:
        if type(item) is not dict or set(item) != SOURCE_INVENTORY_FIELDS:
            return False
        path = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if type(path) is not str or validate_relpath(path) is not None:
            return False
        if type(size) is not int or type(size) is bool or size < 0 or size > MAX_FILE_BYTES:
            return False
        if not _is_hex_digest(digest):
            return False
        if path in seen:
            return False
        seen.add(path)
    return True


def validate_file_inventory(value: object) -> bool:
    if type(value) is not list:
        return False
    originals: set[str] = set()
    transports: set[str] = set()
    for item in value:
        if type(item) is not dict or set(item) != FILE_INVENTORY_FIELDS:
            return False
        original = item.get("original_relative_path")
        archive_rel = item.get("archive_relative_path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if type(original) is not str or validate_relpath(original) is not None:
            return False
        if type(archive_rel) is not str or validate_relpath(archive_rel) is not None:
            return False
        if not archive_rel.startswith("paper/"):
            return False
        if type(size) is not int or type(size) is bool or size < 0 or size > MAX_FILE_BYTES:
            return False
        if not _is_hex_digest(digest):
            return False
        if original in originals or archive_rel in transports:
            return False
        originals.add(original)
        transports.add(archive_rel)
    return True


def validate_directory_inventory(value: object) -> bool:
    if type(value) is not list:
        return False
    seen: set[str] = set()
    for item in value:
        if type(item) is not str or validate_relpath(item) is not None:
            return False
        if item in seen:
            return False
        seen.add(item)
    return list(value) == sorted(value)


def validate_stage_file_inventory(value: object) -> bool:
    if type(value) is not list:
        return False
    seen: set[str] = set()
    rows: list[str] = []
    for item in value:
        if type(item) is not dict or set(item) != SOURCE_INVENTORY_FIELDS:
            return False
        path = item.get("path")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if type(path) is not str or validate_relpath(path) is not None:
            return False
        if type(size) is not int or type(size) is bool or size < 0 or size > MAX_FILE_BYTES:
            return False
        if not _is_hex_digest(digest):
            return False
        if path in seen:
            return False
        seen.add(path)
        rows.append(path)
    return rows == sorted(rows)


def source_from_file_inventory(files: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"path": item["original_relative_path"], "size_bytes": item["size_bytes"], "sha256": item["sha256"]}
        for item in files
    ]


def file_inventory_matches_source(files: list[Mapping[str, Any]], source: list[Mapping[str, Any]]) -> bool:
    return same_inventory(source_from_file_inventory(files), source)


def expected_owned_relative_paths(operation: Mapping[str, Any]) -> list[str] | None:
    kind = operation.get("kind")
    operation_id = operation.get("operation_id")
    archive_id = operation.get("archive_id")
    paper_id = operation.get("paper_id")
    if not is_hex_id(operation_id) or not is_hex_id(archive_id) or not is_paper_id(paper_id):
        return None
    if kind == "archive":
        return [
            f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
            f"{LIBRARY_DIRNAME}/{OPERATIONS_DIRNAME}/{operation_id}.json",
        ]
    if kind == "restore":
        return [
            f"{PAPER_DIRNAME}/{paper_digest(str(paper_id))}/",
            f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
        ]
    if kind == "replace":
        new_paper_id = operation.get("new_paper_id")
        if not is_paper_id(new_paper_id):
            return None
        return [
            f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}/{operation_id}/",
            f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}/{archive_id}/",
            f"{PAPER_DIRNAME}/{paper_digest(str(new_paper_id))}/",
        ]
    return None


def recognized_operation(value: Mapping[str, Any] | None, *, filename: str | None = None) -> dict[str, Any] | None:
    if value is None or type(value) is not dict or value.get("schema") != OPERATION_SCHEMA:
        return None
    operation_id = value.get("operation_id")
    kind = value.get("kind")
    phase = value.get("phase")
    paper_id = value.get("paper_id")
    archive_id = value.get("archive_id")
    owned = value.get("owned_relative_paths")
    if not is_hex_id(operation_id):
        return None
    if filename is not None and filename != f"{operation_id}.json":
        return None
    if type(kind) is not str or kind not in {"archive", "restore", "replace"}:
        return None
    if kind == "archive":
        allowed = set(JOURNAL_COMMON_FIELDS)
        required = set(JOURNAL_COMMON_FIELDS)
        phases = ARCHIVE_KIND_PHASES
        allowed_outcomes = {OUTCOME_ARCHIVED}
    elif kind == "restore":
        allowed = set(JOURNAL_COMMON_FIELDS)
        required = set(JOURNAL_COMMON_FIELDS)
        phases = RESTORE_KIND_PHASES
        allowed_outcomes = {OUTCOME_RESTORED}
    else:
        allowed = set(JOURNAL_REPLACE_FIELDS)
        required = set(JOURNAL_COMMON_FIELDS) | {
            "new_paper_id",
            "pdf_sha256",
            "title",
            "stage_file_inventory",
            "stage_directories",
        }
        phases = REPLACE_KIND_PHASES
        allowed_outcomes = {OUTCOME_REPLACED, OUTCOME_ABORTED_BEFORE_STAGING}
    if type(phase) is not str or phase not in phases:
        return None
    if phase == "complete":
        allowed.add(JOURNAL_OUTCOME_FIELD)
        required.add(JOURNAL_OUTCOME_FIELD)
    keys = set(value)
    if not required <= keys or not keys <= allowed:
        return None
    if not is_paper_id(paper_id) or not is_hex_id(archive_id):
        return None
    if type(owned) is not list or any(type(item) is not str for item in owned):
        return None
    if any(validate_relpath(item.rstrip("/")) is not None or not item.endswith("/") and not item.endswith(".json") for item in owned):
        return None
    expected = expected_owned_relative_paths(value)
    if expected is None or owned != expected:
        return None
    if not validate_source_inventory(value.get("source_inventory")):
        return None
    if not validate_file_inventory(value.get("file_inventory")):
        return None
    if not file_inventory_matches_source(list(value["file_inventory"]), list(value["source_inventory"])):
        return None
    if not validate_directory_inventory(value.get("directories")):
        return None
    directories = list(value["directories"])
    if not directories:
        return None
    paper_prefix = f"{PAPER_DIRNAME}/{paper_digest(str(paper_id))}"
    if directories[0] != paper_prefix and paper_prefix not in directories:
        return None
    if kind == "replace":
        new_paper_id = value.get("new_paper_id")
        pdf_sha256 = value.get("pdf_sha256")
        title = value.get("title")
        if not is_paper_id(new_paper_id) or not _is_hex_digest(pdf_sha256):
            return None
        if paper_digest(str(new_paper_id)) != pdf_sha256:
            return None
        if title is not None and normalize_title(title) != title:
            return None
        new_files = value.get("new_file_inventory")
        new_dirs = value.get("new_directories")
        outcome = value.get("outcome") if phase == "complete" else None
        needs_new = phase in {"staged", "old_archived", "new_published"} or (
            phase == "complete" and outcome == OUTCOME_REPLACED
        )
        if needs_new:
            if not validate_file_inventory(new_files) or not validate_directory_inventory(new_dirs):
                return None
            if not new_dirs or f"{PAPER_DIRNAME}/{paper_digest(str(new_paper_id))}" not in new_dirs:
                return None
        else:
            if new_files is not None or new_dirs is not None:
                return None
        if not validate_stage_file_inventory(value.get("stage_file_inventory")):
            return None
        if not validate_directory_inventory(value.get("stage_directories")):
            return None
    if phase == "complete":
        outcome = value.get("outcome")
        if type(outcome) is not str or outcome not in allowed_outcomes:
            return None
    return dict(value)


def iter_operation_files(workspace: Path) -> list[Path]:
    root = operations_dir(workspace)
    if not is_regular_dir(root):
        return []
    found: list[Path] = []
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if item.suffix != ".json":
            continue
        found.append(item)
    return found


def pending_operation_ids(workspace: Path) -> list[str]:
    ids: list[str] = []
    for path in iter_operation_files(workspace):
        loaded = recognized_operation(load_persisted_object(path), filename=path.name)
        if loaded is None:
            continue
        if loaded.get("phase") != "complete":
            ids.append(str(loaded["operation_id"]))
    return ids


def library_diagnostics(workspace: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    root = library_root(workspace)
    if not os.path.lexists(root):
        return rows
    if root.is_symlink() or not root.is_dir():
        rows.append(
            {
                "relative_path": LIBRARY_DIRNAME,
                "code": "LIBRARY_JOURNAL_FOREIGN",
                "message": ".light-library is not a regular directory",
            }
        )
        return rows
    ops = root / OPERATIONS_DIRNAME
    if os.path.lexists(ops):
        if ops.is_symlink() or not ops.is_dir():
            rows.append(
                {
                    "relative_path": f"{LIBRARY_DIRNAME}/{OPERATIONS_DIRNAME}",
                    "code": "LIBRARY_JOURNAL_FOREIGN",
                    "message": "operations directory is not regular",
                }
            )
        else:
            for item in sorted(ops.iterdir(), key=lambda path: path.name):
                rel = f"{LIBRARY_DIRNAME}/{OPERATIONS_DIRNAME}/{item.name}"
                if item.is_symlink() or not item.is_file() or not item.name.endswith(".json"):
                    rows.append({"relative_path": rel, "code": "LIBRARY_JOURNAL_FOREIGN", "message": "foreign operations entry"})
                    continue
                loaded = recognized_operation(load_persisted_object(item), filename=item.name)
                if loaded is None:
                    rows.append({"relative_path": rel, "code": "LIBRARY_JOURNAL_FOREIGN", "message": "malformed or foreign operation journal"})
                    continue
                if loaded.get("phase") != "complete":
                    rows.append(
                        {
                            "relative_path": rel,
                            "code": "LIBRARY_OPERATION_PENDING",
                            "message": f"pending {loaded['kind']} operation {loaded['operation_id']}",
                        }
                    )
    staging = root / STAGING_DIRNAME
    if os.path.lexists(staging):
        if staging.is_symlink() or not staging.is_dir():
            rows.append(
                {
                    "relative_path": f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}",
                    "code": "LIBRARY_JOURNAL_FOREIGN",
                    "message": "library staging is not a regular directory",
                }
            )
        elif list_names(staging):
            rows.append(
                {
                    "relative_path": f"{LIBRARY_DIRNAME}/{STAGING_DIRNAME}",
                    "code": "LIBRARY_STAGING_NONEMPTY",
                    "message": "owned library staging is nonempty; call recover_library",
                }
            )
    archives = root / ARCHIVE_DIRNAME
    if os.path.lexists(archives) and (archives.is_symlink() or not archives.is_dir()):
        rows.append(
            {
                "relative_path": f"{LIBRARY_DIRNAME}/{ARCHIVE_DIRNAME}",
                "code": "LIBRARY_JOURNAL_FOREIGN",
                "message": "archive directory is not regular",
            }
        )
    return rows


def knowledge_staging_nonempty(workspace: Path) -> bool:
    path = workspace / KNOWLEDGE_DIRNAME / KNOWLEDGE_STAGING
    if not os.path.lexists(path):
        return False
    if path.is_symlink() or not path.is_dir():
        return True
    return bool(list_names(path))


def same_inventory(left: list[Mapping[str, Any]], right: list[Mapping[str, Any]]) -> bool:
    def _rows(items: list[Mapping[str, Any]]) -> list[tuple[str, int, str]]:
        rows: list[tuple[str, int, str]] = []
        for item in items:
            path = item.get("path")
            size = item.get("size_bytes")
            digest = item.get("sha256")
            if type(path) is not str or type(size) is not int or type(size) is bool or type(digest) is not str:
                return []
            rows.append((path, size, digest))
        rows.sort()
        return rows

    return _rows(list(left)) == _rows(list(right))
