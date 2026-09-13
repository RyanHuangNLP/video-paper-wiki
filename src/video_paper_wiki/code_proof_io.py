"""Private retained I/O session for the code-evidence workflow."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import re
import stat
import tomllib
import unicodedata
from contextlib import contextmanager
from typing import Iterator

from video_paper_wiki.code_git_objects import (
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CodeGitProofError,
)
from video_paper_wiki.code_proof_resources import (
    CodeProofResourceError,
    CodeProofStructureError,
    compile_code_proof_resources,
    resource_origin_plan,
)

__all__ = ["CodeProofIOError", "open_code_session"]

_MAX_BUNDLE_PATH_BYTES = 16384
_BATCH_ID_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$"
)
_OBJECT_BODY_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})\.body$")
_HEX64_JSON_RE = re.compile(r"^[0-9a-f]{64}\.json$")
_HEX_CHARS = frozenset("0123456789abcdef")
_OUTPUT_NAMESPACE = "code-evidence-v1"
_SLOT_NAMES = ("bundle.json", "intent.json", "observation.json", "request.json")
_FAMILY_NAMES = ("configs", "handoffs", "objects")
_GROUPS = (
    "checkout",
    "ancestors",
    "resources",
    "metadata",
    "bundle",
    "output_layout",
    "output_files",
    "installation",
)
_PHASES = frozenset(
    {
        "setup",
        "scan",
        "retaining",
        "idle",
        "temp_created",
        "writing",
        "temp_ready",
        "linked",
        "cleaned",
        "durable",
        "final_verify",
        "closing",
    }
)
_REASONS = frozenset(
    {
        "unavailable_primitive",
        "lock_busy",
        "missing",
        "unsafe_type",
        "unsafe_mode",
        "link_count",
        "edge_changed",
        "bytes_changed",
        "set_changed",
        "late_arrival",
        "temp_ownership_lost",
        "phase_mismatch",
        "syscall_failed",
        "zero_write",
        "path_spelling",
        "overlap",
        "unknown_entry",
        "batch_id",
        "marker_invalid",
        "resource_hash",
        "resource_shape",
        "resource_origin",
    }
)
_OPERATIONS = frozenset(
    {
        "open",
        "stat",
        "fstat",
        "scandir",
        "read",
        "seek",
        "mkdir",
        "write",
        "link",
        "unlink",
        "fsync",
        "flock",
        "dup",
        "close",
    }
)
_MESSAGES = {
    "WORKSPACE_ROOT_INVALID": "CODE workspace root is invalid",
    "INVALID_BATCH_ID": "CODE batch identifier is invalid",
    "WORK_PATH_UNSAFE": "CODE retained path is unsafe",
    "CODE_PROOF_IO_ERROR": "CODE evidence I/O failed",
    "CODE_PROOF_RESOURCE_INVALID": "CODE evidence resource is invalid",
    "CODE_PROOF_LIMIT_EXCEEDED": "CODE evidence limit exceeded",
    "CODE_PROOF_CONFLICT": "CODE evidence artifact conflicts",
    "CODE_PROOF_BUSY": "CODE evidence workspace is busy",
}
_NINE_CODES = frozenset(_MESSAGES) - {
    "CODE_PROOF_LIMIT_EXCEEDED",
    "CODE_PROOF_CONFLICT",
}
_NINE_KEYS = (
    "phase",
    "group",
    "reason",
    "operation",
    "errno",
    "prior_code",
    "prior_operation",
    "prior_errno",
    "failed_groups",
)
_LIMIT_DETAIL_KEYS = ("instance_pointer", "limit_name", "limit", "observed")
_CONFLICT_DETAIL_KEYS = ("instance_pointer", "reason")
_CONFLICT_REASONS = frozenset(
    {
        "request_changed",
        "acquisition_changed",
        "config_format_changed",
        "artifact_changed",
    }
)
_PRIOR_CODES = frozenset(
    {
        "WORKSPACE_ROOT_INVALID",
        "INVALID_BATCH_ID",
        "WORK_PATH_UNSAFE",
        "CODE_PROOF_IO_ERROR",
        "CODE_PROOF_RESOURCE_INVALID",
        "CODE_PROOF_LIMIT_EXCEEDED",
        "CODE_PROOF_CONFLICT",
        "CODE_PROOF_BUSY",
        "CODE_PROOF_INPUT_INVALID",
        "CODE_PROOF_OBJECT_EXTRA",
        "CODE_PROOF_OBJECT_UNAVAILABLE",
        "CODE_PROOF_OBJECT_SIZE_MISMATCH",
        "CODE_PROOF_OBJECT_HASH_MISMATCH",
        "CODE_PROOF_OBJECT_TYPE_MISMATCH",
        "CODE_PROOF_COMMIT_INVALID",
        "CODE_PROOF_TREE_INVALID",
        "CODE_PROOF_CONSUMED_SET_MISMATCH",
        "CODE_CONFIG_INPUT_INVALID",
        "CODE_CONFIG_BYTES_INVALID",
        "CODE_CONFIG_EMPTY",
        "CODE_CONFIG_SYNTAX_INVALID",
        "CODE_CONFIG_UNSUPPORTED",
        "CODE_CONFIG_DUPLICATE_KEY",
        "CODE_CONFIG_LIMIT_EXCEEDED",
        "CODE_CONFIG_NUMBER_INVALID",
        "CODE_CONFIG_DYNAMIC_UNSUPPORTED",
        "CODE_CONFIG_PARSER_MISMATCH",
        "CODE_PROOF_JSON_INVALID",
        "CODE_PROOF_DOCUMENT_INVALID",
        "CODE_PROOF_BINDING_MISMATCH",
        "CODE_PROOF_STATE_INVALID",
        "CODE_PROOF_NOT_READY",
        "CODE_PROOF_TARGET_INELIGIBLE",
    }
)
_SLOT_SPECS = {
    "request.json": ("max_request_bytes", 65536, "/request"),
    "intent.json": ("max_intent_bytes", 1048576, "/intent"),
    "bundle.json": ("max_bundle_bytes", 1048576, "/bundle"),
    "observation.json": ("max_observation_bytes", 2097152, "/observation"),
}
_OUTPUT_LIMIT_KEYS = (
    "max_request_bytes",
    "max_intent_bytes",
    "max_bundle_bytes",
    "max_observation_bytes",
    "max_config_document_bytes",
    "max_handoff_bytes",
    "max_output_peak_bytes",
)
_OUTPUT_HARD = {
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_bundle_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}
_GIT_LIMIT_KEYS = (
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
)
_GIT_HARD = {
    "max_targets": 32,
    "max_objects": 2048,
    "max_tree_entries": 32768,
    "max_object_bytes": 8388608,
    "max_total_object_bytes": 33554432,
}
_OBJECT_RECORD_KEYS = (
    "oid",
    "object_type",
    "body_size_bytes",
    "body_sha256",
    "framed_sha256",
)
_OBJECT_TYPES = frozenset({"commit", "tree", "blob"})
_FAMILY_CAPS = {"objects": 2048, "configs": 32, "handoffs": 32}
_FAMILY_FILE_CAPS = {
    "objects": ("max_object_bytes", 8388608, "/objects"),
    "configs": ("max_config_document_bytes", 2097152, "/config"),
    "handoffs": ("max_handoff_bytes", 131072, "/handoffs"),
}
_RESOURCE_FORBIDDEN = (
    stat.S_IXUSR
    | stat.S_IXGRP
    | stat.S_IXOTH
    | stat.S_IWGRP
    | stat.S_IWOTH
    | stat.S_ISUID
    | stat.S_ISGID
    | stat.S_ISVTX
)
_INVALID_ERROR_CONTEXT = "Invalid CODE I/O error context"
_INACTIVE = "CODE session is not active"
_LIMITS_UNSET = "CODE output limits are not set"
_LIMITS_SET = "CODE output limits are already set"
_PROJECT_NAME = "video-paper-wiki"
_GIT_MARKER_MAX = 65536
_PROJECT_MAX = 1048576
_WRITE_CHUNK = 65536
_NAMESPACE_CAP = 7
_RAW_ROOT_CAP = 2
_RAW_OBJECTS_CAP = 2048
_HARD_PEAK = 134217728


def _getcwd():
    return os.getcwd()


def _open(*args, **kwargs):
    return os.open(*args, **kwargs)


def _stat(*args, **kwargs):
    return os.stat(*args, **kwargs)


def _fstat(fd):
    return os.fstat(fd)


def _scandir(fd):
    return os.scandir(fd)


def _read(fd, n):
    return os.read(fd, n)


def _seek(fd, pos, how):
    return os.lseek(fd, pos, how)


def _mkdir(*args, **kwargs):
    return os.mkdir(*args, **kwargs)


def _write(fd, data):
    return os.write(fd, data)


def _link(*args, **kwargs):
    return os.link(*args, **kwargs)


def _unlink(*args, **kwargs):
    return os.unlink(*args, **kwargs)


def _fsync(fd):
    return os.fsync(fd)


def _flock(fd, flags):
    return fcntl.flock(fd, flags)


def _dup(fd):
    return os.dup(fd)


def _close(fd):
    return os.close(fd)


def _capability_snapshot():
    return {
        "O_RDONLY": getattr(os, "O_RDONLY", None),
        "O_WRONLY": getattr(os, "O_WRONLY", None),
        "O_RDWR": getattr(os, "O_RDWR", None),
        "O_CREAT": getattr(os, "O_CREAT", None),
        "O_EXCL": getattr(os, "O_EXCL", None),
        "O_NOFOLLOW": getattr(os, "O_NOFOLLOW", None),
        "O_DIRECTORY": getattr(os, "O_DIRECTORY", None),
        "O_CLOEXEC": getattr(os, "O_CLOEXEC", None),
        "O_NONBLOCK": getattr(os, "O_NONBLOCK", None),
        "supports_dir_fd": getattr(os, "supports_dir_fd", None),
        "supports_follow_symlinks": getattr(os, "supports_follow_symlinks", None),
        "supports_fd": getattr(os, "supports_fd", None),
        "fstat": getattr(os, "fstat", None),
        "read": getattr(os, "read", None),
        "lseek": getattr(os, "lseek", None),
        "write": getattr(os, "write", None),
        "fsync": getattr(os, "fsync", None),
        "dup": getattr(os, "dup", None),
        "close": getattr(os, "close", None),
        "SEEK_SET": getattr(os, "SEEK_SET", None),
        "flock": getattr(fcntl, "flock", None),
        "LOCK_EX": getattr(fcntl, "LOCK_EX", None),
        "LOCK_NB": getattr(fcntl, "LOCK_NB", None),
        "LOCK_UN": getattr(fcntl, "LOCK_UN", None),
    }


def _unsupported_errnos():
    values = {errno.ENOSYS, errno.EINVAL}
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno, name, None)
        if type(value) is int:
            values.add(value)
    return values


def _busy_errnos():
    values = {errno.EACCES, errno.EAGAIN}
    value = getattr(errno, "EWOULDBLOCK", None)
    if type(value) is int:
        values.add(value)
    return values


def _errno_of(exc):
    if isinstance(exc, OSError) and type(exc.errno) is int and 0 <= exc.errno <= 65535:
        return exc.errno
    return None


def _is_dir_mode(mode):
    return stat.S_ISDIR(mode) and not stat.S_ISLNK(mode)


def _is_reg_mode(mode):
    return stat.S_ISREG(mode) and not stat.S_ISLNK(mode)


def _dir_stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode)


def _file_stamp(st):
    mtime = st.st_mtime_ns
    ctime = st.st_ctime_ns
    if type(mtime) is not int or type(ctime) is not int:
        raise CodeProofIOError(
            "WORK_PATH_UNSAFE",
            _nine(
                "setup",
                None,
                "unsafe_type",
                "stat",
                None,
            ),
        )
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        mtime,
        ctime,
        st.st_nlink,
    )


def _resource_mode_ok(mode):
    return (mode & _RESOURCE_FORBIDDEN) == 0


def _output_file_mode_ok(mode):
    return stat.S_IMODE(mode) == 0o600


def _output_dir_mode_ok(mode):
    return stat.S_IMODE(mode) == 0o700


def _is_hex(value, width):
    if type(value) is not str or len(value) != width:
        return False
    for char in value:
        if char not in _HEX_CHARS:
            return False
    return True


def _oid_width(name):
    if type(name) is not str or not name.endswith(".body"):
        return None
    stem = name[:-5]
    if _is_hex(stem, 40):
        return 40
    if _is_hex(stem, 64):
        return 64
    return None


def _copy_plain(details):
    copied = {}
    for key in details:
        value = details[key]
        if type(value) is list:
            copied[key] = list(value)
        elif type(value) is dict:
            inner = {}
            for inner_key in value:
                inner[inner_key] = value[inner_key]
            copied[key] = inner
        else:
            copied[key] = value
    return copied


def _invalid_context():
    raise ValueError(_INVALID_ERROR_CONTEXT) from None


def _require_exact_keys(details, expected):
    if type(details) is not dict:
        _invalid_context()
    keys = []
    for key in details:
        if type(key) is not str:
            _invalid_context()
        keys.append(key)
    if frozenset(keys) != frozenset(expected):
        _invalid_context()
    return keys


def _validate_nine(details):
    _require_exact_keys(details, _NINE_KEYS)
    phase = details["phase"]
    if type(phase) is not str or phase not in _PHASES:
        _invalid_context()
    group = details["group"]
    if group is not None and (type(group) is not str or group not in _GROUPS):
        _invalid_context()
    reason = details["reason"]
    if type(reason) is not str or reason not in _REASONS:
        _invalid_context()
    operation = details["operation"]
    if operation is not None and (
        type(operation) is not str or operation not in _OPERATIONS
    ):
        _invalid_context()
    errn = details["errno"]
    if errn is not None and (type(errn) is not int or errn < 0 or errn > 65535):
        _invalid_context()
    prior_code = details["prior_code"]
    if prior_code is not None and (
        type(prior_code) is not str or prior_code not in _PRIOR_CODES
    ):
        _invalid_context()
    prior_operation = details["prior_operation"]
    if prior_operation is not None and (
        type(prior_operation) is not str or prior_operation not in _OPERATIONS
    ):
        _invalid_context()
    prior_errno = details["prior_errno"]
    if prior_errno is not None and (
        type(prior_errno) is not int or prior_errno < 0 or prior_errno > 65535
    ):
        _invalid_context()
    failed = details["failed_groups"]
    if type(failed) is not list:
        _invalid_context()
    seen = set()
    last = -1
    for item in failed:
        if type(item) is not str or item not in _GROUPS:
            _invalid_context()
        index = _GROUPS.index(item)
        if item in seen or index < last:
            _invalid_context()
        seen.add(item)
        last = index
    if len(failed) > 8:
        _invalid_context()


def _validate_limit(details):
    _require_exact_keys(details, _LIMIT_DETAIL_KEYS)
    pointer = details["instance_pointer"]
    name = details["limit_name"]
    limit = details["limit"]
    observed = details["observed"]
    if type(pointer) is not str or len(pointer) > 1024 or not pointer:
        _invalid_context()
    if type(name) is not str or not name:
        _invalid_context()
    if type(limit) is not int or limit <= 0:
        _invalid_context()
    if type(observed) is not int or observed < 0:
        _invalid_context()


def _validate_conflict(details):
    _require_exact_keys(details, _CONFLICT_DETAIL_KEYS)
    pointer = details["instance_pointer"]
    reason = details["reason"]
    if type(pointer) is not str or len(pointer) > 1024 or not pointer:
        _invalid_context()
    if type(reason) is not str or reason not in _CONFLICT_REASONS:
        _invalid_context()


def _nine(phase, group, reason, operation, errn, **extra):
    return {
        "phase": phase,
        "group": group,
        "reason": reason,
        "operation": operation,
        "errno": errn,
        "prior_code": extra.get("prior_code"),
        "prior_operation": extra.get("prior_operation"),
        "prior_errno": extra.get("prior_errno"),
        "failed_groups": list(extra.get("failed_groups") or []),
    }


class CodeProofIOError(Exception):
    """Closed CODE retained-I/O facade."""

    def __init__(self, code, details):
        if type(code) is not str or code not in _MESSAGES:
            _invalid_context()
        if type(details) is not dict:
            _invalid_context()
        if code == "CODE_PROOF_LIMIT_EXCEEDED":
            _validate_limit(details)
        elif code == "CODE_PROOF_CONFLICT":
            _validate_conflict(details)
        elif code in _NINE_CODES:
            _validate_nine(details)
        else:
            _invalid_context()
        self._code = code
        self._message = _MESSAGES[code]
        self._details = _copy_plain(details)
        self._exit_code = 2
        super().__init__(self._message)

    @property
    def code(self):
        return self._code

    @property
    def message(self):
        return self._message

    @property
    def details(self):
        return _copy_plain(self._details)

    @property
    def exit_code(self):
        return self._exit_code


def _prior_fields(exc):
    prior_code = None
    prior_operation = None
    prior_errno = None
    if exc is None:
        return prior_code, prior_operation, prior_errno
    code = None
    try:
        code = exc.code
    except Exception:
        code = None
    if type(code) is str and code in _PRIOR_CODES:
        prior_code = code
    details = None
    try:
        details = exc.details
    except Exception:
        details = None
    if type(details) is dict:
        operation = None
        errn = None
        for key in details:
            if type(key) is not str:
                continue
            if key == "operation":
                try:
                    operation = details[key]
                except Exception:
                    operation = None
            elif key == "errno":
                try:
                    errn = details[key]
                except Exception:
                    errn = None
        if type(operation) is str and operation in _OPERATIONS:
            prior_operation = operation
        if type(errn) is int and 0 <= errn <= 65535:
            prior_errno = errn
    return prior_code, prior_operation, prior_errno


class _Node:
    __slots__ = (
        "key",
        "parent",
        "name",
        "role",
        "group",
        "first_kind",
        "first_stat",
        "first_stamp",
        "first_errno",
        "fd",
        "payload",
        "authorized_stamp",
        "authorized_kind",
        "is_dir",
        "logical_absent",
    )

    def __init__(self, key, parent, name, role, group):
        self.key = key
        self.parent = parent
        self.name = name
        self.role = role
        self.group = group
        self.first_kind = "unobserved"
        self.first_stat = None
        self.first_stamp = None
        self.first_errno = None
        self.fd = None
        self.payload = None
        self.authorized_stamp = None
        self.authorized_kind = None
        self.is_dir = False
        self.logical_absent = False


class _Scan:
    __slots__ = (
        "parent",
        "cap",
        "names",
        "complete",
        "over_cap",
        "error",
        "additions",
        "removals",
        "group",
        "charged",
    )

    def __init__(self, parent, cap, group):
        self.parent = parent
        self.cap = cap
        self.names = []
        self.complete = False
        self.over_cap = False
        self.error = None
        self.additions = set()
        self.removals = set()
        self.group = group
        self.charged = 0


class _InstallRecord:
    __slots__ = (
        "phase",
        "failed",
        "target",
        "payload",
        "temp_name",
        "temp_fd",
        "temp_node",
        "written",
        "link_success",
        "cleaned_prefix",
        "unlink_attempted",
        "parent_node",
        "final_node",
        "owned_temp",
    )

    def __init__(self):
        self.phase = "idle"
        self.failed = False
        self.target = None
        self.payload = None
        self.temp_name = None
        self.temp_fd = None
        self.temp_node = None
        self.written = 0
        self.link_success = False
        self.cleaned_prefix = False
        self.unlink_attempted = False
        self.parent_node = None
        self.final_node = None
        self.owned_temp = False


class _ResourceRecord:
    __slots__ = (
        "logical_path",
        "pin",
        "node",
        "original_reason",
        "original_code",
        "bytes_ok",
    )

    def __init__(self, logical_path, pin):
        self.logical_path = logical_path
        self.pin = pin
        self.node = None
        self.original_reason = None
        self.original_code = None
        self.bytes_ok = False


class _Failure:
    __slots__ = ("reason", "operation", "errno", "group", "lineage", "code")

    def __init__(
        self,
        reason,
        operation,
        errn,
        group,
        *,
        lineage=True,
        code="WORK_PATH_UNSAFE",
    ):
        self.reason = reason
        self.operation = operation
        self.errno = errn
        self.group = group
        self.lineage = lineage
        self.code = code


def _parse_output_name(relative_name):
    if relative_name in _SLOT_SPECS:
        return ("slot", relative_name, None)
    if "/" not in relative_name:
        return None
    family, base = relative_name.split("/", 1)
    if "/" in base or not base:
        return None
    if family == "objects" and _OBJECT_BODY_RE.fullmatch(base) is not None:
        return ("family", family, base)
    if family in ("configs", "handoffs") and _HEX64_JSON_RE.fullmatch(base) is not None:
        return ("family", family, base)
    return None


def _family_limit(family):
    return _FAMILY_FILE_CAPS[family]


class _CodeSession:
    def __init__(self):
        self._state = "setup"
        self._phase = "setup"
        self._batch_id = None
        self._checkout_parts = None
        self._output_parts = None
        self._nodes = []
        self._by_key = {}
        self._fd_order = []
        self._lock_dup_fd = None
        self._lock_fd = None
        self._scans = []
        self._resource_plan = None
        self._resource_records = None
        self._resource_context = None
        self._schemas_directory = None
        self._profiles_directory = None
        self._output_limits = None
        self._logical_bytes = 0
        self._install = _InstallRecord()
        self._reached_groups = set()
        self._initial_files = {}
        self._current_files = {}
        self._initial_namespace_present = False
        self._current_namespace_present = False
        self._initial_families = {
            "objects": False,
            "configs": False,
            "handoffs": False,
        }
        self._current_families = {
            "objects": False,
            "configs": False,
            "handoffs": False,
        }
        self._input_used = False
        self._input_node = None
        self._bundle_used = False
        self._bundle_root = None
        self._bundle_objects_dir = None
        self._bundle_manifest = None
        self._bundle_bodies = None
        self._bundle_physical = []
        self._git_limits = None
        self._checkout_node = None
        self._work_node = None
        self._batch_node = None
        self._namespace_node = None
        self._family_nodes = {}
        self._slot_nodes = {}
        self._git_node = None
        self._project_node = None
        self._root_node = None
        self._scan_error = None
        self._setup_complete = False
        self._dir_flags = 0
        self._file_flags = 0
        self._temp_flags = 0
        self._final_selected = None
        self._cleanup_error = None
        self._group_failures = {}
        self._closed_cleared = False
        self._scan_failed = False

    def _require_active(self):
        if self._state != "active":
            raise RuntimeError(_INACTIVE)

    def _require_idle_views(self):
        self._require_active()
        if self._install.failed or self._install.phase != "idle":
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="phase_mismatch",
                group="installation",
            )

    def _raise(self, code, **kwargs):
        phase = kwargs.pop("phase", None)
        if phase is None:
            phase = self._phase
        if code == "CODE_PROOF_LIMIT_EXCEEDED":
            raise CodeProofIOError(
                code,
                {
                    "instance_pointer": kwargs["instance_pointer"],
                    "limit_name": kwargs["limit_name"],
                    "limit": kwargs["limit"],
                    "observed": kwargs["observed"],
                },
            ) from None
        if code == "CODE_PROOF_CONFLICT":
            raise CodeProofIOError(
                code,
                {
                    "instance_pointer": kwargs["instance_pointer"],
                    "reason": kwargs.get("reason", "artifact_changed"),
                },
            ) from None
        raise CodeProofIOError(
            code,
            _nine(
                phase,
                kwargs.get("group"),
                kwargs["reason"],
                kwargs.get("operation"),
                kwargs.get("errno"),
                prior_code=kwargs.get("prior_code"),
                prior_operation=kwargs.get("prior_operation"),
                prior_errno=kwargs.get("prior_errno"),
                failed_groups=kwargs.get("failed_groups"),
            ),
        ) from None

    def _track_fd(self, fd):
        self._fd_order.append(fd)
        return fd

    def _register(self, node):
        self._nodes.append(node)
        self._by_key[node.key] = node
        if node.group is not None:
            self._reached_groups.add(node.group)
        return node

    def _limits(self):
        if self._output_limits is not None:
            return self._output_limits
        return dict(_OUTPUT_HARD)

    def snapshot(self):
        self._require_idle_views()
        if self._scan_failed or not self._setup_complete:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="set_changed",
                group="output_layout",
            )
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        result = {}
        for name in sorted(self._current_files):
            result[name] = self._current_files[name]
        return result

    def layout_state(self):
        self._require_idle_views()
        if self._scan_failed or not self._setup_complete:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="set_changed",
                group="output_layout",
            )
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        current_bytes = 0
        for name in self._current_files:
            current_bytes += len(self._current_files[name])
        return {
            "initial_namespace_present": self._initial_namespace_present,
            "current_namespace_present": self._current_namespace_present,
            "initial_families": {
                "objects": self._initial_families["objects"],
                "configs": self._initial_families["configs"],
                "handoffs": self._initial_families["handoffs"],
            },
            "current_families": {
                "objects": self._current_families["objects"],
                "configs": self._current_families["configs"],
                "handoffs": self._current_families["handoffs"],
            },
            "initial_files": sorted(self._initial_files),
            "current_files": sorted(self._current_files),
            "current_file_bytes": current_bytes,
        }

    def verify(self):
        self._require_active()
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None

    def validate_structure(self, title, instance):
        self._require_active()
        self._resource_context.validate_structure(title, instance)

    def materialize_limits(self, value):
        self._require_active()
        return self._resource_context.materialize_limits(value)

    @property
    def profile_sha256(self):
        self._require_active()
        return self._resource_context.profile_sha256

    def _setup(self, batch_id):
        self._phase = "setup"
        self._preflight()
        if type(batch_id) is not str or _BATCH_ID_RE.fullmatch(batch_id) is None:
            self._raise(
                "INVALID_BATCH_ID",
                reason="batch_id",
                group="checkout",
            )
        self._batch_id = batch_id
        self._retain_checkout()
        self._lock_checkout()
        self._fsync_checkout()
        self._retain_markers()
        self._retain_resources()
        self._phase = "scan"
        self._scan_output()
        self._phase = "setup"
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        self._setup_complete = True

    def _preflight(self):
        snap = _capability_snapshot()
        int_flags = (
            "O_RDONLY",
            "O_WRONLY",
            "O_RDWR",
            "O_CREAT",
            "O_EXCL",
            "O_NOFOLLOW",
            "O_DIRECTORY",
            "O_CLOEXEC",
            "O_NONBLOCK",
        )
        for name in int_flags:
            value = snap.get(name)
            if type(value) is not int:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    group=None,
                )
            if name != "O_RDONLY" and value == 0:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    group=None,
                )
        supports_dir = snap.get("supports_dir_fd")
        supports_follow = snap.get("supports_follow_symlinks")
        supports_fd = snap.get("supports_fd")
        try:
            dir_ok = (
                os.open in supports_dir
                and os.stat in supports_dir
                and os.mkdir in supports_dir
                and os.link in supports_dir
                and os.unlink in supports_dir
            )
            follow_ok = os.stat in supports_follow and os.link in supports_follow
            fd_ok = os.scandir in supports_fd
        except Exception:
            dir_ok = False
            follow_ok = False
            fd_ok = False
        if not dir_ok or not follow_ok or not fd_ok:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="unavailable_primitive",
                group=None,
            )
        for name in (
            "fstat",
            "read",
            "lseek",
            "write",
            "fsync",
            "dup",
            "close",
            "flock",
        ):
            if not callable(snap.get(name)):
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    group=None,
                )
        if type(snap.get("SEEK_SET")) is not int:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="unavailable_primitive",
                group=None,
            )
        for name in ("LOCK_EX", "LOCK_NB", "LOCK_UN"):
            if type(snap.get(name)) is not int:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    group=None,
                )
        self._dir_flags = (
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        self._file_flags = (
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        )
        self._temp_flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC
        )

    def _absolute_parts(self, path, *, group, reason_code="WORKSPACE_ROOT_INVALID"):
        if type(path) is not str or "\0" in path:
            self._raise(reason_code, reason="path_spelling", group=group)
        if not path.startswith("/") or (path != "/" and path.endswith("/")):
            self._raise(reason_code, reason="path_spelling", group=group)
        if path == "/":
            return ()
        parts = tuple(path.split("/")[1:])
        if not parts or any(part in ("", ".", "..") for part in parts):
            self._raise(reason_code, reason="path_spelling", group=group)
        return parts

    def _open_root(self):
        self._reached_groups.add("checkout")
        node = _Node((), None, "", "root", "checkout")
        try:
            fd = _open("/", self._dir_flags)
        except OSError as exc:
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="syscall_failed",
                operation="open",
                errno=_errno_of(exc),
                group="checkout",
            )
        try:
            st = _fstat(fd)
        except OSError as exc:
            try:
                _close(fd)
            except OSError:
                pass
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group="checkout",
            )
        if not _is_dir_mode(st.st_mode):
            try:
                _close(fd)
            except OSError:
                pass
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="unsafe_type",
                operation="stat",
                group="checkout",
            )
        node.first_kind = "stat"
        node.first_stat = st
        node.first_stamp = _dir_stamp(st)
        node.fd = self._track_fd(fd)
        node.is_dir = True
        self._register(node)
        self._root_node = node
        return node

    def _stat_named(self, parent, name, *, group, operation="stat"):
        try:
            return _stat(name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                return None
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation=operation,
                errno=errn,
                group=group,
            )

    def _observe_child(
        self,
        parent,
        name,
        *,
        role,
        group,
        want_dir=False,
        want_file=False,
        optional=False,
        open_it=False,
        output_dir=False,
        output_file=False,
        resource_file=False,
        input_file=False,
    ):
        key = parent.key + (name,)
        existing = self._by_key.get(key)
        if existing is not None:
            if output_dir or output_file or resource_file or input_file:
                existing.role = role
                existing.group = group
            if existing.first_kind == "stat" and existing.first_stat is not None:
                self._apply_observe_policy(
                    existing,
                    existing.first_stat,
                    want_dir=want_dir,
                    want_file=want_file,
                    output_dir=output_dir,
                    output_file=output_file,
                    resource_file=resource_file,
                    input_file=input_file,
                )
            if open_it and existing.fd is None and existing.first_kind == "stat":
                self._open_existing(existing, want_dir=want_dir, want_file=want_file)
            return existing
        node = _Node(key, parent, name, role, group)
        self._register(node)
        if parent.logical_absent or parent.first_kind == "absent" or parent.fd is None:
            node.logical_absent = True
            node.first_kind = "absent"
            return node
        st = None
        try:
            st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                node.first_kind = "absent"
                return node
            node.first_kind = "stat_error"
            node.first_errno = errn
            if optional:
                return node
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="stat",
                errno=errn,
                group=group,
            )
        node.first_kind = "stat"
        node.first_stat = st
        is_dir = _is_dir_mode(st.st_mode)
        is_reg = _is_reg_mode(st.st_mode)
        node.is_dir = is_dir
        if is_dir:
            node.first_stamp = _dir_stamp(st)
        elif is_reg:
            try:
                node.first_stamp = _file_stamp(st)
            except CodeProofIOError:
                raise
        else:
            node.first_stamp = (st.st_dev, st.st_ino, st.st_mode)
        self._apply_observe_policy(
            node,
            st,
            want_dir=want_dir,
            want_file=want_file,
            output_dir=output_dir,
            output_file=output_file,
            resource_file=resource_file,
            input_file=input_file,
        )
        if not open_it:
            return node
        self._open_existing(node, want_dir=want_dir, want_file=want_file)
        return node

    def _apply_observe_policy(
        self,
        node,
        st,
        *,
        want_dir=False,
        want_file=False,
        output_dir=False,
        output_file=False,
        resource_file=False,
        input_file=False,
    ):
        is_dir = _is_dir_mode(st.st_mode)
        is_reg = _is_reg_mode(st.st_mode)
        group = node.group
        if want_dir and not is_dir:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                operation="stat",
                group=group,
            )
        if want_file and not is_reg:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                operation="stat",
                group=group,
            )
        if output_dir:
            if not is_dir:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_type",
                    operation="stat",
                    group=group,
                )
            if not _output_dir_mode_ok(st.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_mode",
                    operation="stat",
                    group=group,
                )
        if output_file or resource_file or input_file:
            if not is_reg:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_type",
                    operation="stat",
                    group=group,
                )
            if st.st_nlink != 1:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="link_count",
                    operation="stat",
                    group=group,
                )
            if output_file and not _output_file_mode_ok(st.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_mode",
                    operation="stat",
                    group=group,
                )
            if (resource_file or input_file) and not _resource_mode_ok(st.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_mode",
                    operation="stat",
                    group=group,
                )

    def _open_existing(self, node, *, want_dir=False, want_file=False):
        if node.fd is not None or node.parent is None or node.parent.fd is None:
            return
        st = node.first_stat
        if st is None:
            return
        is_dir = _is_dir_mode(st.st_mode)
        flags = self._dir_flags if is_dir else self._file_flags
        try:
            fd = _open(node.name, flags, dir_fd=node.parent.fd)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="open",
                errno=_errno_of(exc),
                group=node.group,
            )
        node.fd = self._track_fd(fd)
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group=node.group,
            )
        if is_dir:
            if _dir_stamp(fst) != node.first_stamp:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="edge_changed",
                    operation="fstat",
                    group=node.group,
                )
        else:
            if _file_stamp(fst) != node.first_stamp:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="edge_changed",
                    operation="fstat",
                    group=node.group,
                )

    def _walk_parts(self, parts, *, role, group, file=False, **policy):
        node = self._root_node
        if node is None:
            node = self._open_root()
        last = len(parts) - 1
        for index, name in enumerate(parts):
            is_last = index == last
            want_file = bool(file and is_last)
            want_dir = not want_file
            open_it = True
            node = self._observe_child(
                node,
                name,
                role=role if is_last else "ancestor",
                group=group,
                want_dir=want_dir,
                want_file=want_file,
                open_it=open_it,
                **({} if not is_last else policy),
            )
            if node.first_kind == "absent" or node.logical_absent:
                return node
        return node

    def _retain_checkout(self):
        cwd = _getcwd()
        parts = self._absolute_parts(cwd, group="checkout")
        self._checkout_parts = parts
        self._output_parts = parts + (".work", self._batch_id, _OUTPUT_NAMESPACE)
        if self._root_node is None:
            self._open_root()
        node = self._root_node
        for name in parts:
            node = self._observe_child(
                node,
                name,
                role="checkout" if name == parts[-1] else "ancestor",
                group="checkout",
                want_dir=True,
                open_it=True,
            )
        self._checkout_node = node
        self._reached_groups.add("checkout")

    def _lock_checkout(self):
        fd = self._checkout_node.fd
        try:
            _flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn in _busy_errnos():
                self._raise(
                    "CODE_PROOF_BUSY",
                    reason="lock_busy",
                    operation="flock",
                    errno=errn,
                    group="checkout",
                )
            if errn in _unsupported_errnos():
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    operation="flock",
                    errno=errn,
                    group="checkout",
                )
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="flock",
                errno=errn,
                group="checkout",
            )
        self._lock_fd = fd
        try:
            dup = _dup(fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="dup",
                errno=_errno_of(exc),
                group="checkout",
            )
        self._lock_dup_fd = dup

    def _fsync_checkout(self):
        try:
            _fsync(self._checkout_node.fd)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn in _unsupported_errnos():
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="unavailable_primitive",
                    operation="fsync",
                    errno=errn,
                    group="checkout",
                )
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fsync",
                errno=errn,
                group="checkout",
            )

    def _read_fd(self, node, maximum, *, group):
        fd = node.fd
        try:
            _seek(fd, 0, os.SEEK_SET)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="seek",
                errno=_errno_of(exc),
                group=group,
            )
        size = node.first_stamp[3]
        if size > maximum:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/output" if group in {
                    "output_files",
                    "output_layout",
                } else "/input",
                limit_name="max_observe_input_bytes",
                limit=maximum,
                observed=size,
            )
        chunks = []
        remaining = size
        while remaining > 0:
            n = remaining if remaining < _WRITE_CHUNK else _WRITE_CHUNK
            try:
                data = _read(fd, n)
            except OSError as exc:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="syscall_failed",
                    operation="read",
                    errno=_errno_of(exc),
                    group=group,
                )
            if not data:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="bytes_changed",
                    operation="read",
                    group=group,
                )
            chunks.append(data)
            remaining -= len(data)
        payload = b"".join(chunks)
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group=group,
            )
        if _file_stamp(fst) != node.first_stamp:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="edge_changed",
                operation="fstat",
                group=group,
            )
        node.payload = payload
        return payload

    def _retain_markers(self):
        git = self._observe_child(
            self._checkout_node,
            ".git",
            role="git",
            group="checkout",
            open_it=False,
        )
        self._git_node = git
        if git.first_kind == "absent":
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="missing",
                operation="stat",
                group="checkout",
            )
        st = git.first_stat
        if _is_dir_mode(st.st_mode):
            node = self._observe_child(
                self._checkout_node,
                ".git",
                role="git",
                group="checkout",
                want_dir=True,
                open_it=True,
            )
            self._git_node = node
        elif _is_reg_mode(st.st_mode):
            if st.st_nlink != 1:
                self._raise(
                    "WORKSPACE_ROOT_INVALID",
                    reason="link_count",
                    operation="stat",
                    group="checkout",
                )
            if not _resource_mode_ok(st.st_mode):
                self._raise(
                    "WORKSPACE_ROOT_INVALID",
                    reason="unsafe_mode",
                    operation="stat",
                    group="checkout",
                )
            if st.st_size > _GIT_MARKER_MAX:
                self._raise(
                    "WORKSPACE_ROOT_INVALID",
                    reason="marker_invalid",
                    group="checkout",
                )
            node = self._observe_child(
                self._checkout_node,
                ".git",
                role="git",
                group="checkout",
                want_file=True,
                open_it=True,
                input_file=True,
            )
            self._git_node = node
            self._read_fd(node, _GIT_MARKER_MAX, group="checkout")
        else:
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="unsafe_type",
                operation="stat",
                group="checkout",
            )
        project = self._observe_child(
            self._checkout_node,
            "pyproject.toml",
            role="project",
            group="checkout",
            want_file=True,
            open_it=True,
            input_file=True,
        )
        self._project_node = project
        if project.first_kind == "absent":
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="missing",
                operation="stat",
                group="checkout",
            )
        if project.first_stamp[3] > _PROJECT_MAX:
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="marker_invalid",
                group="checkout",
            )
        payload = self._read_fd(project, _PROJECT_MAX, group="checkout")
        try:
            parsed = tomllib.loads(payload.decode("utf-8"))
        except Exception:
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="marker_invalid",
                group="checkout",
            )
        name = None
        if type(parsed) is dict:
            project_tbl = parsed.get("project")
            if type(project_tbl) is dict:
                name = project_tbl.get("name")
        if name != _PROJECT_NAME:
            self._raise(
                "WORKSPACE_ROOT_INVALID",
                reason="marker_invalid",
                group="checkout",
            )

    def _join_dir(self, directory, filename):
        if directory == "/":
            return "/" + filename
        return directory + "/" + filename

    def _retain_resources(self):
        self._reached_groups.add("resources")
        self._phase = "setup"
        try:
            plan = resource_origin_plan()
        except CodeProofResourceError as exc:
            self._raise(
                "CODE_PROOF_RESOURCE_INVALID",
                reason=exc.reason,
                group="resources",
            )
        except Exception:
            self._raise(
                "CODE_PROOF_RESOURCE_INVALID",
                reason="resource_origin",
                group="resources",
            )
        self._resource_plan = plan
        self._schemas_directory = plan.schemas_directory
        self._profiles_directory = plan.profiles_directory
        schema_parts = self._absolute_parts(
            plan.schemas_directory,
            group="resources",
            reason_code="CODE_PROOF_RESOURCE_INVALID",
        )
        profile_parts = self._absolute_parts(
            plan.profiles_directory,
            group="resources",
            reason_code="CODE_PROOF_RESOURCE_INVALID",
        )
        self._reject_resource_overlap(schema_parts)
        self._reject_resource_overlap(profile_parts)
        records = []
        retained_bytes = {}
        original_error = None
        for pin in plan.resources:
            record = _ResourceRecord(pin.relative_path, pin)
            records.append(record)
            if pin.relative_path.startswith("schemas/"):
                directory_parts = schema_parts
                filename = pin.relative_path.split("/", 1)[1]
            else:
                directory_parts = profile_parts
                filename = pin.relative_path.split("/", 1)[1]
            try:
                parent = self._walk_parts(
                    directory_parts,
                    role="resource_dir",
                    group="resources",
                )
                if parent.first_kind == "absent" or parent.logical_absent:
                    node = _Node(
                        parent.key + (filename,),
                        parent,
                        filename,
                        "resource",
                        "resources",
                    )
                    node.first_kind = "absent"
                    node.logical_absent = True
                    self._register(node)
                    record.node = node
                    record.original_reason = "missing"
                    record.original_code = "CODE_PROOF_RESOURCE_INVALID"
                    if original_error is None:
                        original_error = CodeProofIOError(
                            "CODE_PROOF_RESOURCE_INVALID",
                            _nine(
                                "setup",
                                "resources",
                                "missing",
                                "stat",
                                None,
                            ),
                        )
                    continue
                node = self._observe_resource_file(parent, filename, record)
                record.node = node
                if record.original_reason is not None:
                    if original_error is None:
                        original_error = CodeProofIOError(
                            record.original_code or "CODE_PROOF_RESOURCE_INVALID",
                            _nine(
                                "setup",
                                "resources",
                                record.original_reason,
                                "stat" if record.original_reason != "resource_hash" else "read",
                                None,
                            ),
                        )
                    continue
                if node.payload is not None:
                    retained_bytes[pin.relative_path] = node.payload
                    record.bytes_ok = True
            except CodeProofIOError as exc:
                if original_error is None:
                    original_error = exc
                if record.node is None:
                    continue
            except Exception as exc:
                if original_error is None:
                    mapped = CodeProofIOError(
                        "CODE_PROOF_IO_ERROR",
                        _nine(
                            "setup",
                            "resources",
                            "syscall_failed",
                            "stat",
                            None,
                        ),
                    )
                    original_error = mapped
                    original_error.__cause__ = exc
        self._resource_records = tuple(records)
        if original_error is not None:
            raise original_error from None
        if len(retained_bytes) != 11:
            self._raise(
                "CODE_PROOF_RESOURCE_INVALID",
                reason="missing",
                group="resources",
            )
        payload = {}
        for key in retained_bytes:
            payload[key] = retained_bytes[key]
        try:
            compiled = compile_code_proof_resources(payload)
        except CodeProofResourceError as exc:
            self._raise(
                "CODE_PROOF_RESOURCE_INVALID",
                reason=exc.reason,
                group="resources",
            )
        self._resource_context = compiled

    def _observe_resource_file(self, parent, filename, record):
        node = _Node(
            parent.key + (filename,),
            parent,
            filename,
            "resource",
            "resources",
        )
        self._register(node)
        try:
            st = _stat(filename, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                node.first_kind = "absent"
                record.original_reason = "missing"
                record.original_code = "CODE_PROOF_RESOURCE_INVALID"
                return node
            node.first_kind = "stat_error"
            node.first_errno = errn
            record.original_reason = "syscall_failed"
            record.original_code = "CODE_PROOF_IO_ERROR"
            return node
        node.first_kind = "stat"
        node.first_stat = st
        if not _is_reg_mode(st.st_mode):
            node.first_stamp = (st.st_dev, st.st_ino, st.st_mode)
            record.original_reason = "unsafe_type"
            record.original_code = "CODE_PROOF_RESOURCE_INVALID"
            return node
        node.first_stamp = _file_stamp(st)
        if st.st_nlink != 1:
            record.original_reason = "link_count"
            record.original_code = "CODE_PROOF_RESOURCE_INVALID"
            return node
        if not _resource_mode_ok(st.st_mode):
            record.original_reason = "unsafe_mode"
            record.original_code = "CODE_PROOF_RESOURCE_INVALID"
            return node
        try:
            fd = _open(filename, self._file_flags, dir_fd=parent.fd)
        except OSError as exc:
            node.first_errno = _errno_of(exc)
            record.original_reason = "syscall_failed"
            record.original_code = "CODE_PROOF_IO_ERROR"
            return node
        node.fd = self._track_fd(fd)
        try:
            fst = _fstat(fd)
        except OSError as exc:
            node.first_errno = _errno_of(exc)
            record.original_reason = "syscall_failed"
            record.original_code = "CODE_PROOF_IO_ERROR"
            return node
        if _file_stamp(fst) != node.first_stamp:
            record.original_reason = "edge_changed"
            record.original_code = "WORK_PATH_UNSAFE"
            return node
        pin = record.pin
        if fst.st_size != pin.size_bytes:
            try:
                payload = self._read_all(fd, fst.st_size)
            except CodeProofIOError:
                record.original_reason = "syscall_failed"
                record.original_code = "CODE_PROOF_IO_ERROR"
                return node
            node.payload = payload
            record.original_reason = "resource_hash"
            record.original_code = "CODE_PROOF_RESOURCE_INVALID"
            return node
        try:
            payload = self._read_all(fd, fst.st_size)
        except CodeProofIOError:
            record.original_reason = "syscall_failed"
            record.original_code = "CODE_PROOF_IO_ERROR"
            return node
        node.payload = payload
        digest = hashlib.sha256(payload).hexdigest()
        if digest != pin.sha256:
            record.original_reason = "resource_hash"
            record.original_code = "CODE_PROOF_RESOURCE_INVALID"
            return node
        return node

    def _read_all(self, fd, size):
        try:
            _seek(fd, 0, os.SEEK_SET)
        except OSError as exc:
            raise CodeProofIOError(
                "WORK_PATH_UNSAFE",
                _nine(self._phase, "resources", "syscall_failed", "seek", _errno_of(exc)),
            ) from None
        chunks = []
        remaining = size
        while remaining > 0:
            n = remaining if remaining < _WRITE_CHUNK else _WRITE_CHUNK
            try:
                data = _read(fd, n)
            except OSError as exc:
                raise CodeProofIOError(
                    "WORK_PATH_UNSAFE",
                    _nine(
                        self._phase,
                        "resources",
                        "syscall_failed",
                        "read",
                        _errno_of(exc),
                    ),
                ) from None
            if not data:
                raise CodeProofIOError(
                    "WORK_PATH_UNSAFE",
                    _nine(self._phase, "resources", "bytes_changed", "read", None),
                ) from None
            chunks.append(data)
            remaining -= len(data)
        return b"".join(chunks)

    def _paths_overlap(self, left, right):
        if not left or not right:
            return False
        if left == right:
            return True
        if len(left) < len(right):
            return right[: len(left)] == left
        return left[: len(right)] == right

    def _reject_resource_overlap(self, parts):
        if self._paths_overlap(parts, self._output_parts):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="overlap",
                group="resources",
            )

    def _scan_directory(self, parent, cap, group, *, charge=False):
        scan = _Scan(parent, cap, group)
        self._scans.append(scan)
        if parent is None or parent.fd is None or parent.first_kind != "stat":
            scan.error = _Failure("missing", "scandir", None, group)
            self._scan_failed = True
            return scan
        names = []
        try:
            with _scandir(parent.fd) as iterator:
                for entry in iterator:
                    names.append(entry.name)
                    if len(names) > cap:
                        scan.over_cap = True
                        break
        except OSError as exc:
            scan.error = _Failure(
                "syscall_failed",
                "scandir",
                _errno_of(exc),
                group,
            )
            scan.names = names
            self._scan_failed = True
            return scan
        scan.names = names
        if scan.over_cap:
            scan.complete = False
            self._scan_failed = True
            return scan
        for name in names:
            try:
                st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
            except OSError as exc:
                scan.error = _Failure(
                    "syscall_failed",
                    "stat",
                    _errno_of(exc),
                    group,
                )
                self._scan_failed = True
                return scan
            if charge and _is_reg_mode(st.st_mode):
                scan.charged += st.st_size
                self._logical_bytes += st.st_size
                if self._logical_bytes > _HARD_PEAK:
                    self._raise(
                        "CODE_PROOF_LIMIT_EXCEEDED",
                        instance_pointer="/output",
                        limit_name="max_output_peak_bytes",
                        limit=_HARD_PEAK,
                        observed=self._logical_bytes,
                    )
            child_key = parent.key + (name,)
            if child_key not in self._by_key:
                child = _Node(child_key, parent, name, "scan", group)
                child.first_kind = "stat"
                child.first_stat = st
                child.is_dir = _is_dir_mode(st.st_mode)
                if child.is_dir:
                    child.first_stamp = _dir_stamp(st)
                elif _is_reg_mode(st.st_mode):
                    child.first_stamp = _file_stamp(st)
                else:
                    child.first_stamp = (st.st_dev, st.st_ino, st.st_mode)
                self._register(child)
        scan.complete = scan.error is None and not scan.over_cap
        return scan

    def _scan_output(self):
        self._reached_groups.add("ancestors")
        self._reached_groups.add("output_layout")
        self._reached_groups.add("output_files")
        work = self._observe_child(
            self._checkout_node,
            ".work",
            role="work",
            group="ancestors",
            want_dir=True,
            open_it=True,
        )
        self._work_node = work
        if work.first_kind == "absent" or work.logical_absent:
            self._batch_node = self._logical_child(work, self._batch_id, "batch", "ancestors")
            self._namespace_node = self._logical_child(
                self._batch_node,
                _OUTPUT_NAMESPACE,
                "namespace",
                "output_layout",
            )
            self._record_absent_slots()
            return
        batch = self._observe_child(
            work,
            self._batch_id,
            role="batch",
            group="ancestors",
            want_dir=True,
            open_it=True,
        )
        self._batch_node = batch
        if batch.first_kind == "absent" or batch.logical_absent:
            self._namespace_node = self._logical_child(
                batch,
                _OUTPUT_NAMESPACE,
                "namespace",
                "output_layout",
            )
            self._record_absent_slots()
            return
        namespace = self._observe_child(
            batch,
            _OUTPUT_NAMESPACE,
            role="namespace",
            group="output_layout",
            open_it=False,
        )
        self._namespace_node = namespace
        if namespace.first_kind == "absent" or namespace.logical_absent:
            self._record_absent_slots()
            return
        namespace = self._observe_child(
            batch,
            _OUTPUT_NAMESPACE,
            role="namespace",
            group="output_layout",
            output_dir=True,
            open_it=True,
        )
        self._namespace_node = namespace
        self._initial_namespace_present = True
        self._current_namespace_present = True
        scan = self._scan_directory(
            namespace,
            _NAMESPACE_CAP,
            "output_layout",
            charge=True,
        )
        if scan.over_cap:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unknown_entry",
                group="output_layout",
            )
        if scan.error is not None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason=scan.error.reason,
                operation=scan.error.operation,
                errno=scan.error.errno,
                group="output_layout",
            )
        known = set(_SLOT_NAMES) | set(_FAMILY_NAMES)
        for name in scan.names:
            if name not in known:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unknown_entry",
                    group="output_layout",
                )
            child = self._by_key[namespace.key + (name,)]
            if name in _SLOT_NAMES:
                self._accept_slot(name, child)
            else:
                self._accept_family(name, child)
        for name in _SLOT_NAMES:
            if name not in scan.names:
                self._slot_nodes[name] = self._observe_child(
                    namespace,
                    name,
                    role="slot",
                    group="output_files",
                    open_it=False,
                )
        for name in _FAMILY_NAMES:
            if name not in scan.names:
                node = self._observe_child(
                    namespace,
                    name,
                    role="family",
                    group="output_layout",
                    open_it=False,
                )
                self._family_nodes[name] = node
                self._initial_families[name] = False
                self._current_families[name] = False
            else:
                self._initial_families[name] = True
                self._current_families[name] = True

    def _logical_child(self, parent, name, role, group):
        node = _Node(parent.key + (name,), parent, name, role, group)
        node.first_kind = "absent"
        node.logical_absent = True
        return self._register(node)

    def _record_absent_slots(self):
        parent = self._namespace_node
        for name in _SLOT_NAMES:
            self._slot_nodes[name] = self._logical_child(
                parent, name, "slot", "output_files"
            )
        for name in _FAMILY_NAMES:
            self._family_nodes[name] = self._logical_child(
                parent, name, "family", "output_layout"
            )
            self._initial_families[name] = False
            self._current_families[name] = False

    def _accept_slot(self, name, child):
        spec = _SLOT_SPECS[name]
        limit_name, hard, pointer = spec
        if child.first_kind != "stat" or child.is_dir or not _is_reg_mode(
            child.first_stat.st_mode
        ):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                group="output_files",
            )
        st = child.first_stat
        if st.st_nlink != 1:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="link_count",
                group="output_files",
            )
        if not _output_file_mode_ok(st.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_mode",
                group="output_files",
            )
        if st.st_size > hard:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/output",
                limit_name=limit_name,
                limit=hard,
                observed=st.st_size,
            )
        opened = self._observe_child(
            child.parent,
            name,
            role="slot",
            group="output_files",
            output_file=True,
            open_it=True,
        )
        self._slot_nodes[name] = opened
        payload = self._read_fd(opened, hard, group="output_files")
        self._initial_files[name] = payload
        self._current_files[name] = payload

    def _accept_family(self, name, child):
        if child.first_kind != "stat" or not child.is_dir:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                group="output_layout",
            )
        opened = self._observe_child(
            child.parent,
            name,
            role="family",
            group="output_layout",
            output_dir=True,
            open_it=True,
        )
        self._family_nodes[name] = opened
        cap = _FAMILY_CAPS[name]
        scan = self._scan_directory(
            opened,
            cap,
            "output_files",
            charge=True,
        )
        if scan.over_cap:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unknown_entry",
                group="output_files",
            )
        if scan.error is not None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason=scan.error.reason,
                operation=scan.error.operation,
                errno=scan.error.errno,
                group="output_files",
            )
        limit_name, hard, pointer = _family_limit(name)
        for entry_name in scan.names:
            ok = False
            if name == "objects":
                ok = _OBJECT_BODY_RE.fullmatch(entry_name) is not None
            else:
                ok = _HEX64_JSON_RE.fullmatch(entry_name) is not None
            if not ok:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unknown_entry",
                    group="output_files",
                )
            node = self._by_key[opened.key + (entry_name,)]
            if node.is_dir or not _is_reg_mode(node.first_stat.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_type",
                    group="output_files",
                )
            st = node.first_stat
            if st.st_nlink != 1:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="link_count",
                    group="output_files",
                )
            if not _output_file_mode_ok(st.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_mode",
                    group="output_files",
                )
            if st.st_size > hard:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/output",
                    limit_name=limit_name,
                    limit=hard,
                    observed=st.st_size,
                )
            opened_file = self._observe_child(
                opened,
                entry_name,
                role="output_file",
                group="output_files",
                output_file=True,
                open_it=True,
            )
            payload = self._read_fd(opened_file, hard, group="output_files")
            rel = name + "/" + entry_name
            self._initial_files[rel] = payload
            self._current_files[rel] = payload

    def set_output_limits(self, limits):
        self._require_active()
        if self._output_limits is not None:
            raise RuntimeError(_LIMITS_SET)
        if type(limits) is not dict:
            raise CodeProofStructureError("limits") from None
        keys = []
        for key in limits:
            if type(key) is not str:
                raise CodeProofStructureError("limits") from None
            keys.append(key)
        if frozenset(keys) != frozenset(_OUTPUT_LIMIT_KEYS):
            raise CodeProofStructureError("limits") from None
        copied = {}
        for key in _OUTPUT_LIMIT_KEYS:
            raw = limits[key]
            if type(raw) is not int or raw <= 0 or raw > _OUTPUT_HARD[key]:
                raise CodeProofStructureError("limits") from None
            copied[key] = raw
        self._recheck_selected_limits(copied)
        self._output_limits = copied

    def _recheck_selected_limits(self, limits):
        total = 0
        for name, payload in self._current_files.items():
            size = len(payload)
            total += size
            parsed = _parse_output_name(name)
            if parsed is None:
                continue
            kind, first, base = parsed
            if kind == "slot":
                limit_name, hard, pointer = _SLOT_SPECS[first]
                cap = limits[limit_name]
                if size > cap:
                    self._raise(
                        "CODE_PROOF_LIMIT_EXCEEDED",
                        instance_pointer="/output",
                        limit_name=limit_name,
                        limit=cap,
                        observed=size,
                    )
            else:
                limit_name, hard, pointer = _family_limit(first)
                cap = limits[limit_name] if limit_name in limits else hard
                if size > cap:
                    self._raise(
                        "CODE_PROOF_LIMIT_EXCEEDED",
                        instance_pointer="/output",
                        limit_name=limit_name,
                        limit=cap,
                        observed=size,
                    )
        if total > limits["max_output_peak_bytes"]:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/output",
                limit_name="max_output_peak_bytes",
                limit=limits["max_output_peak_bytes"],
                observed=total,
            )
        if self._bundle_manifest is not None:
            size = len(self._bundle_manifest)
            if size > limits["max_bundle_bytes"]:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/bundle",
                    limit_name="max_bundle_bytes",
                    limit=limits["max_bundle_bytes"],
                    observed=size,
                )

    def retain_input(self, path, *, maximum):
        self._require_active()
        self._phase = "retaining"
        if type(path) is not str:
            raise CodeProofStructureError("type") from None
        if type(maximum) is not int or maximum not in (65536, 1048576):
            raise CodeProofStructureError("limits") from None
        if self._input_used:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="overlap",
                group="metadata",
            )
        self._reached_groups.add("metadata")
        self._validate_input_spelling(path)
        if path.startswith("/"):
            parts = self._absolute_parts(
                path,
                group="metadata",
                reason_code="WORK_PATH_UNSAFE",
            )
        else:
            rel = self._relative_parts(path, group="metadata")
            parts = self._checkout_parts + rel
        self._reject_output_overlap(parts, group="metadata")
        node = self._walk_parts(
            parts,
            role="input",
            group="metadata",
            file=True,
            input_file=True,
        )
        self._input_node = node
        self._input_used = True
        if node.first_kind == "absent" or node.logical_absent:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="missing",
                operation="stat",
                group="metadata",
            )
        limit_name = (
            "max_request_input_bytes" if maximum == 65536 else "max_observe_input_bytes"
        )
        size = node.first_stamp[3]
        if size > maximum:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/input",
                limit_name=limit_name,
                limit=maximum,
                observed=size,
            )
        payload = self._read_fd(node, maximum, group="metadata")
        self._phase = "idle"
        return payload

    def _relative_parts(self, path, *, group):
        if type(path) is not str or "\0" in path:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group=group,
            )
        if path.startswith("/") or path.endswith("/") or "//" in path:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group=group,
            )
        parts = tuple(path.split("/"))
        if any(part in ("", ".", "..") for part in parts):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group=group,
            )
        return parts

    def _validate_input_spelling(self, path):
        if "\0" in path:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="metadata",
            )
        if path == "" or path == "." or path == "..":
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="metadata",
            )

    def _reject_output_overlap(self, parts, *, group):
        if self._paths_overlap(parts, self._output_parts):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="overlap",
                group=group,
            )

    def retain_bundle_manifest(self, relative_directory):
        self._require_active()
        self._phase = "retaining"
        if type(relative_directory) is not str:
            raise CodeProofStructureError("type") from None
        if self._bundle_used:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="overlap",
                group="bundle",
            )
        self._reached_groups.add("bundle")
        self._validate_bundle_path(relative_directory)
        rel = tuple(relative_directory.split("/"))
        parts = self._checkout_parts + rel
        self._reject_output_overlap(parts, group="bundle")
        root = self._walk_parts(parts, role="bundle_root", group="bundle")
        self._bundle_root = root
        if root.first_kind == "absent" or root.logical_absent:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="missing",
                operation="stat",
                group="bundle",
            )
        scan = self._scan_directory(root, _RAW_ROOT_CAP, "bundle", charge=False)
        if scan.over_cap or set(scan.names) != {"manifest.json", "objects"}:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="set_changed" if scan.complete else "unknown_entry",
                group="bundle",
            )
        if scan.error is not None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason=scan.error.reason,
                operation=scan.error.operation,
                errno=scan.error.errno,
                group="bundle",
            )
        objects = self._observe_child(
            root,
            "objects",
            role="bundle_objects",
            group="bundle",
            want_dir=True,
            open_it=True,
        )
        self._bundle_objects_dir = objects
        obj_scan = self._scan_directory(
            objects,
            _RAW_OBJECTS_CAP,
            "bundle",
            charge=False,
        )
        if obj_scan.over_cap:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/objects",
                limit_name="max_objects",
                limit=_GIT_HARD["max_objects"],
                observed=_RAW_OBJECTS_CAP + 1,
            )
        if obj_scan.error is not None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason=obj_scan.error.reason,
                operation=obj_scan.error.operation,
                errno=obj_scan.error.errno,
                group="bundle",
            )
        total = 0
        physical = []
        for name in obj_scan.names:
            width = _oid_width(name)
            if width is None:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unknown_entry",
                    group="bundle",
                )
            node = self._by_key[objects.key + (name,)]
            if node.is_dir or not _is_reg_mode(node.first_stat.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_type",
                    group="bundle",
                )
            st = node.first_stat
            if st.st_nlink != 1:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="link_count",
                    group="bundle",
                )
            if not _resource_mode_ok(st.st_mode):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="unsafe_mode",
                    group="bundle",
                )
            if st.st_size > _GIT_HARD["max_object_bytes"]:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/objects",
                    limit_name="max_object_bytes",
                    limit=_GIT_HARD["max_object_bytes"],
                    observed=st.st_size,
                )
            total += st.st_size
            if total > _GIT_HARD["max_total_object_bytes"]:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/objects",
                    limit_name="max_total_object_bytes",
                    limit=_GIT_HARD["max_total_object_bytes"],
                    observed=total,
                )
            physical.append(name[:-5])
        self._bundle_physical = physical
        cap = self._limits()["max_bundle_bytes"]
        manifest_node = self._observe_child(
            root,
            "manifest.json",
            role="bundle_manifest",
            group="bundle",
            want_file=True,
            open_it=True,
            input_file=True,
        )
        if manifest_node.first_stamp[3] > cap:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/bundle",
                limit_name="max_bundle_bytes",
                limit=cap,
                observed=manifest_node.first_stamp[3],
            )
        payload = self._read_fd(manifest_node, cap, group="bundle")
        self._bundle_manifest = payload
        self._bundle_used = True
        self._phase = "idle"
        return payload

    def _validate_bundle_path(self, path):
        if len(path) > 4096:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        if not path.startswith(".work/"):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        if path.endswith("/") or "//" in path:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        for char in path:
            code = ord(char)
            if (
                code < 0x20
                or code == 0x7F
                or (0x80 <= code <= 0x9F)
                or code in (0x2028, 0x2029)
                or 0xD800 <= code <= 0xDFFF
                or char == "\\"
            ):
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="path_spelling",
                    group="bundle",
                )
        try:
            encoded = path.encode("utf-8")
        except Exception:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        if len(encoded) > _MAX_BUNDLE_PATH_BYTES:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        if unicodedata.normalize("NFC", path) != path:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        components = path.split("/")
        if any(part in ("", ".", "..") for part in components):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )
        if len(components) < 2:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="bundle",
            )

    def retain_bundle_bodies(self, *, object_format, objects, limits):
        self._require_active()
        self._phase = "retaining"
        if self._bundle_root is None or self._bundle_objects_dir is None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="missing",
                group="bundle",
            )
        if type(object_format) is not str:
            raise CodeProofStructureError("type") from None
        if object_format not in ("sha1", "sha256"):
            raise CodeProofStructureError("shape") from None
        if type(objects) is not list:
            raise CodeProofStructureError("type") from None
        if type(limits) is not dict:
            raise CodeProofStructureError("limits") from None
        git_keys = []
        for key in limits:
            if type(key) is not str:
                raise CodeProofStructureError("limits") from None
            git_keys.append(key)
        if frozenset(git_keys) != frozenset(_GIT_LIMIT_KEYS):
            raise CodeProofStructureError("limits") from None
        git = {}
        for key in _GIT_LIMIT_KEYS:
            raw = limits[key]
            if type(raw) is not int or raw <= 0 or raw > _GIT_HARD[key]:
                raise CodeProofStructureError("limits") from None
            git[key] = raw
        self._git_limits = dict(git)
        width = 40 if object_format == "sha1" else 64
        records = []
        prev = None
        seen = set()
        for item in objects:
            if type(item) is not dict:
                raise CodeProofStructureError("type") from None
            keys = []
            for key in item:
                if type(key) is not str:
                    raise CodeProofStructureError("type") from None
                keys.append(key)
            if frozenset(keys) != frozenset(_OBJECT_RECORD_KEYS):
                raise CodeProofStructureError("shape") from None
            oid = item["oid"]
            object_type = item["object_type"]
            body_size = item["body_size_bytes"]
            body_sha = item["body_sha256"]
            framed = item["framed_sha256"]
            if type(oid) is not str or type(object_type) is not str:
                raise CodeProofStructureError("type") from None
            if type(body_size) is not int or type(body_sha) is not str or type(framed) is not str:
                raise CodeProofStructureError("type") from None
            if not _is_hex(oid, width):
                raise CodeProofStructureError("shape") from None
            if object_type not in _OBJECT_TYPES:
                raise CodeProofStructureError("shape") from None
            if not _is_hex(body_sha, 64) or not _is_hex(framed, 64):
                raise CodeProofStructureError("shape") from None
            if prev is not None and oid <= prev:
                raise CodeProofStructureError("shape") from None
            if oid in seen:
                raise CodeProofStructureError("shape") from None
            seen.add(oid)
            prev = oid
            records.append(
                {
                    "oid": oid,
                    "object_type": object_type,
                    "body_size_bytes": body_size,
                    "body_sha256": body_sha,
                    "framed_sha256": framed,
                }
            )
        err = self._verify_group_names("bundle")
        if err is not None:
            raise self._failure_to_error(err) from None
        physical = list(self._bundle_physical)
        max_objects = git["max_objects"]
        if len(records) > max_objects:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/objects",
                limit_name="max_objects",
                limit=max_objects,
                observed=len(records),
            )
        if len(physical) > max_objects:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/bodies",
                limit_name="max_objects",
                limit=max_objects,
                observed=len(physical),
            )
        for oid in physical:
            if len(oid) != width:
                raise CodeGitProofError(
                    CODE_PROOF_INPUT_INVALID,
                    "code git proof input is invalid",
                    {"instance_pointer": "/bodies", "reason": "invalid_oid_key"},
                    2,
                ) from None
        declared = {record["oid"] for record in records}
        extra = [oid for oid in physical if oid not in declared]
        if extra:
            raise CodeGitProofError(
                CODE_PROOF_OBJECT_EXTRA,
                "undeclared git object bodies were supplied",
                {"instance_pointer": "/bodies", "extra_oids": sorted(extra)},
                2,
            ) from None
        missing = [record["oid"] for record in records if record["oid"] not in set(physical)]
        if missing:
            raise CodeGitProofError(
                CODE_PROOF_OBJECT_UNAVAILABLE,
                "required git object is unavailable",
                {"instance_pointer": "/bodies", "missing_oids": list(missing)},
                2,
            ) from None
        total = 0
        bodies = {}
        parent = self._bundle_objects_dir
        for index, record in enumerate(records):
            size = record["body_size_bytes"]
            if size > git["max_object_bytes"]:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/objects/" + str(index) + "/body_size_bytes",
                    limit_name="max_object_bytes",
                    limit=git["max_object_bytes"],
                    observed=size,
                )
            filename = record["oid"] + ".body"
            node = self._observe_child(
                parent,
                filename,
                role="bundle_body",
                group="bundle",
                want_file=True,
                open_it=True,
                input_file=True,
            )
            payload = self._read_fd(node, git["max_object_bytes"], group="bundle")
            total += len(payload)
            if total > git["max_total_object_bytes"]:
                self._raise(
                    "CODE_PROOF_LIMIT_EXCEEDED",
                    instance_pointer="/objects",
                    limit_name="max_total_object_bytes",
                    limit=git["max_total_object_bytes"],
                    observed=total,
                )
            bodies[record["oid"]] = payload
        self._bundle_bodies = dict(bodies)
        self._phase = "idle"
        return dict(bodies)

    def install(self, relative_name, payload):
        self._require_active()
        if self._install.failed or self._install.phase != "idle":
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="phase_mismatch",
                group="installation",
            )
        if self._output_limits is None:
            raise RuntimeError(_LIMITS_UNSET)
        if type(relative_name) is not str:
            raise CodeProofStructureError("type") from None
        if type(payload) is not bytes:
            raise CodeProofStructureError("type") from None
        parsed = _parse_output_name(relative_name)
        if parsed is None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="path_spelling",
                group="installation",
            )
        kind, first, base = parsed
        if kind == "slot":
            limit_name, hard, pointer = _SLOT_SPECS[first]
            cap = self._output_limits[limit_name]
        else:
            limit_name, hard, pointer = _family_limit(first)
            cap = self._output_limits[limit_name] if limit_name in self._output_limits else hard
        size = len(payload)
        if size > cap:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer=pointer,
                limit_name=limit_name,
                limit=cap,
                observed=size,
            )
        if relative_name in self._initial_files:
            if self._initial_files[relative_name] == payload:
                err = self._verify_full_result(isolate=False)
                if err is not None:
                    raise err from None
                return True
            self._raise(
                "CODE_PROOF_CONFLICT",
                instance_pointer=pointer,
                reason="artifact_changed",
            )
        if relative_name in self._current_files:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="late_arrival",
                group="installation",
            )
        peak = self._output_limits["max_output_peak_bytes"]
        needed = self._logical_bytes + 2 * size
        if needed > peak:
            self._raise(
                "CODE_PROOF_LIMIT_EXCEEDED",
                instance_pointer="/output",
                limit_name="max_output_peak_bytes",
                limit=peak,
                observed=needed,
            )
        self._reached_groups.add("installation")
        record = _InstallRecord()
        record.target = relative_name
        record.payload = payload
        self._install = record
        try:
            self._ensure_install_parent(relative_name)
            self._install_file(relative_name, payload, parsed)
        except BaseException:
            self._install.failed = True
            raise
        self._install.phase = "idle"
        self._install.failed = False
        self._phase = "idle"
        return False

    def _ensure_install_parent(self, relative_name):
        if self._work_node is None or self._work_node.fd is None:
            self._work_node = self._mkdir_authorized(
                self._checkout_node,
                ".work",
                role="work",
                group="ancestors",
            )
        if self._batch_node is None or self._batch_node.fd is None:
            self._batch_node = self._mkdir_authorized(
                self._work_node,
                self._batch_id,
                role="batch",
                group="ancestors",
            )
        if self._namespace_node is None or self._namespace_node.fd is None:
            self._namespace_node = self._mkdir_authorized(
                self._batch_node,
                _OUTPUT_NAMESPACE,
                role="namespace",
                group="output_layout",
            )
            self._current_namespace_present = True
            scan = _Scan(self._namespace_node, _NAMESPACE_CAP, "output_layout")
            scan.complete = True
            self._scans.append(scan)
        parsed = _parse_output_name(relative_name)
        if parsed[0] == "family":
            family = parsed[1]
            node = self._family_nodes.get(family)
            if node is None or node.fd is None:
                created = self._mkdir_authorized(
                    self._namespace_node,
                    family,
                    role="family",
                    group="output_layout",
                )
                self._family_nodes[family] = created
                self._current_families[family] = True
                scan = _Scan(created, _FAMILY_CAPS[family], "output_files")
                scan.complete = True
                self._scans.append(scan)

    def _capture_created_dir(self, parent, name, *, role, group):
        key = parent.key + (name,)
        node = self._by_key.get(key)
        if node is None:
            node = _Node(key, parent, name, role, group)
            node.first_kind = "absent"
            self._register(node)
        try:
            st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="stat",
                errno=_errno_of(exc),
                group=group,
            )
        if not _is_dir_mode(st.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                operation="stat",
                group=group,
            )
        if not _output_dir_mode_ok(st.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_mode",
                operation="stat",
                group=group,
            )
        try:
            fd = _open(name, self._dir_flags, dir_fd=parent.fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="open",
                errno=_errno_of(exc),
                group=group,
            )
        node.fd = self._track_fd(fd)
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group=group,
            )
        stamp = _dir_stamp(st)
        if _dir_stamp(fst) != stamp:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="edge_changed",
                operation="fstat",
                group=group,
            )
        node.is_dir = True
        node.logical_absent = False
        node.authorized_stamp = stamp
        node.authorized_kind = "dir"
        return node

    def _mkdir_authorized(self, parent, name, *, role, group):
        err = self._verify_names_result(isolate=False)
        if err is not None:
            raise err from None
        if parent.fd is None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="missing",
                group=group,
            )
        existing = self._by_key.get(parent.key + (name,))
        if existing is not None and existing.first_kind == "stat":
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="late_arrival",
                group=group,
            )
        try:
            _mkdir(name, 0o700, dir_fd=parent.fd)
        except OSError as exc:
            errn = _errno_of(exc)
            present = False
            try:
                _stat(name, dir_fd=parent.fd, follow_symlinks=False)
                present = True
            except OSError:
                present = False
            if present:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="late_arrival",
                    operation="mkdir",
                    errno=errn,
                    group=group,
                )
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="mkdir",
                errno=errn,
                group=group,
            )
        node = self._capture_created_dir(parent, name, role=role, group=group)
        for scan in self._scans:
            if scan.parent is parent and scan.complete:
                scan.additions.add(name)
        try:
            _fsync(parent.fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fsync",
                errno=_errno_of(exc),
                group=group,
            )
        err = self._verify_names_result(isolate=False)
        if err is not None:
            raise err from None
        return node

    def _install_file(self, relative_name, payload, parsed):
        if parsed[0] == "slot":
            parent = self._namespace_node
            base = relative_name
        else:
            parent = self._family_nodes[parsed[1]]
            base = parsed[2]
        if parent is None or parent.fd is None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="missing",
                group="installation",
            )
        target = self._by_key.get(parent.key + (base,))
        if target is not None and target.first_kind == "stat" and target.authorized_stamp is None:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="late_arrival",
                group="installation",
            )
        self._install.parent_node = parent
        temp_name = ".ce-tmp-" + os.urandom(16).hex()
        self._install.temp_name = temp_name
        err = self._verify_names_result(isolate=False)
        if err is not None:
            raise err from None
        try:
            fd = _open(
                temp_name,
                self._temp_flags,
                0o600,
                dir_fd=parent.fd,
            )
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="open",
                errno=_errno_of(exc),
                group="installation",
            )
        self._install.owned_temp = True
        self._install.temp_fd = self._track_fd(fd)
        self._install.phase = "temp_created"
        self._phase = "temp_created"
        temp_node = _Node(
            parent.key + (temp_name,),
            parent,
            temp_name,
            "temp",
            "installation",
        )
        try:
            st = _fstat(fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group="installation",
            )
        try:
            named = _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="stat",
                errno=_errno_of(exc),
                group="installation",
            )
        temp_node.first_kind = "stat"
        temp_node.first_stat = named
        temp_node.first_stamp = _file_stamp(named)
        temp_node.fd = fd
        temp_node.authorized_stamp = temp_node.first_stamp
        temp_node.authorized_kind = "temp"
        self._register(temp_node)
        self._install.temp_node = temp_node
        for scan in self._scans:
            if scan.parent is parent:
                scan.additions.add(temp_name)
        self._install.phase = "writing"
        self._phase = "writing"
        offset = 0
        while offset < len(payload):
            err = self._verify_names_result(isolate=False)
            if err is not None:
                raise err from None
            chunk = payload[offset : offset + _WRITE_CHUNK]
            try:
                n = _write(fd, chunk)
            except OSError as exc:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="syscall_failed",
                    operation="write",
                    errno=_errno_of(exc),
                    group="installation",
                )
            if n == 0:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="zero_write",
                    operation="write",
                    group="installation",
                )
            offset += n
            self._install.written = offset
        self._install.phase = "temp_ready"
        self._phase = "temp_ready"
        try:
            _seek(fd, 0, os.SEEK_SET)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="seek",
                errno=_errno_of(exc),
                group="installation",
            )
        read_back = self._read_all(fd, len(payload))
        if read_back != payload:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="bytes_changed",
                operation="read",
                group="installation",
            )
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group="installation",
            )
        if not _is_reg_mode(fst.st_mode) or not _output_file_mode_ok(fst.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_mode",
                group="installation",
            )
        if fst.st_nlink != 1 or fst.st_size != len(payload):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="link_count" if fst.st_nlink != 1 else "bytes_changed",
                group="installation",
            )
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        try:
            _fsync(fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fsync",
                errno=_errno_of(exc),
                group="installation",
            )
        try:
            _link(
                temp_name,
                base,
                src_dir_fd=parent.fd,
                dst_dir_fd=parent.fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            errn = _errno_of(exc)
            present = False
            try:
                _stat(base, dir_fd=parent.fd, follow_symlinks=False)
                present = True
            except OSError:
                present = False
            if present:
                self._raise(
                    "WORK_PATH_UNSAFE",
                    reason="late_arrival",
                    operation="link",
                    errno=errn,
                    group="installation",
                )
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="link",
                errno=errn,
                group="installation",
            )
        self._install.link_success = True
        self._install.phase = "linked"
        self._phase = "linked"
        for scan in self._scans:
            if scan.parent is parent:
                scan.additions.add(base)
        try:
            final_st = _stat(base, dir_fd=parent.fd, follow_symlinks=False)
            temp_st = _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
            fst = _fstat(fd)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="stat",
                errno=_errno_of(exc),
                group="installation",
            )
        if (
            final_st.st_dev != fst.st_dev
            or final_st.st_ino != fst.st_ino
            or temp_st.st_dev != fst.st_dev
            or temp_st.st_ino != fst.st_ino
            or fst.st_nlink != 2
            or final_st.st_nlink != 2
        ):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="edge_changed",
                group="installation",
            )
        final_node = _Node(
            parent.key + (base,),
            parent,
            base,
            "output_file",
            "output_files",
        )
        final_node.first_kind = "absent"
        final_node.authorized_stamp = _file_stamp(final_st)
        final_node.authorized_kind = "file"
        final_node.first_stat = final_st
        final_node.is_dir = False
        existing_final = self._by_key.get(final_node.key)
        if existing_final is not None:
            existing_final.authorized_stamp = final_node.authorized_stamp
            existing_final.authorized_kind = "file"
            existing_final.first_stat = final_st
            final_node = existing_final
        else:
            self._register(final_node)
        self._install.final_node = final_node
        self._install.unlink_attempted = True
        try:
            _unlink(temp_name, dir_fd=parent.fd)
        except OSError as exc:
            errn = _errno_of(exc)
            still = False
            try:
                _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
                still = True
            except OSError:
                still = False
            if still:
                self._raise(
                    "CODE_PROOF_IO_ERROR",
                    reason="syscall_failed",
                    operation="unlink",
                    errno=errn,
                    group="installation",
                )
            final_st = self._require_final_matches_temp_fd(
                parent,
                base,
                fd,
                nlink=1,
            )
            self._mark_cleaned_prefix(
                parent,
                base,
                temp_name,
                payload,
                final_node,
                final_st,
            )
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="unlink",
                errno=errn,
                group="installation",
            )
        try:
            _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
            gone = False
        except OSError as exc:
            gone = _errno_of(exc) == errno.ENOENT
        if not gone:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="temp_ownership_lost",
                group="installation",
            )
        final_st = self._require_final_matches_temp_fd(
            parent,
            base,
            fd,
            nlink=1,
        )
        self._mark_cleaned_prefix(
            parent,
            base,
            temp_name,
            payload,
            final_node,
            final_st,
        )
        try:
            opened = _open(base, self._file_flags, dir_fd=parent.fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="open",
                errno=_errno_of(exc),
                group="installation",
            )
        try:
            opened_st = _fstat(opened)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group="installation",
            )
        if (
            opened_st.st_dev != final_st.st_dev
            or opened_st.st_ino != final_st.st_ino
        ):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="edge_changed",
                operation="fstat",
                group="installation",
            )
        final_node.fd = self._track_fd(opened)
        final_node.payload = payload
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        try:
            _fsync(parent.fd)
        except OSError as exc:
            self._raise(
                "CODE_PROOF_IO_ERROR",
                reason="syscall_failed",
                operation="fsync",
                errno=_errno_of(exc),
                group="installation",
            )
        err = self._verify_full_result(isolate=False)
        if err is not None:
            raise err from None
        self._install.phase = "durable"
        self._phase = "durable"

    def _require_final_matches_temp_fd(self, parent, base, temp_fd, *, nlink):
        try:
            fst = _fstat(temp_fd)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="fstat",
                errno=_errno_of(exc),
                group="installation",
            )
        try:
            final_st = _stat(base, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="syscall_failed",
                operation="stat",
                errno=_errno_of(exc),
                group="installation",
            )
        if not _is_reg_mode(final_st.st_mode) or not _is_reg_mode(fst.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_type",
                group="installation",
            )
        if (
            final_st.st_dev != fst.st_dev
            or final_st.st_ino != fst.st_ino
        ):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="edge_changed",
                group="installation",
            )
        if fst.st_nlink != nlink or final_st.st_nlink != nlink:
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="link_count",
                group="installation",
            )
        if not _output_file_mode_ok(final_st.st_mode):
            self._raise(
                "WORK_PATH_UNSAFE",
                reason="unsafe_mode",
                group="installation",
            )
        return final_st

    def _mark_cleaned_prefix(
        self,
        parent,
        base,
        temp_name,
        payload,
        final_node,
        final_st,
    ):
        self._install.phase = "cleaned"
        self._phase = "cleaned"
        self._install.cleaned_prefix = True
        if final_node is not None:
            final_node.authorized_stamp = _file_stamp(final_st)
            final_node.authorized_kind = "file"
            final_node.first_stat = final_st
        for scan in self._scans:
            if scan.parent is parent:
                if temp_name is not None:
                    scan.additions.discard(temp_name)
                scan.additions.add(base)
                scan.removals.discard(base)
        target = self._install.target
        if type(target) is str and target not in self._current_files:
            self._current_files[target] = payload
            self._logical_bytes += len(payload)
        self._install.owned_temp = False

    def _temp_identity(self, record):
        expected = None
        if record.temp_node is not None and record.temp_node.first_stamp is not None:
            expected = record.temp_node.first_stamp
        if expected is None and record.temp_fd is not None:
            try:
                fst = _fstat(record.temp_fd)
            except OSError:
                return None
            expected = (fst.st_dev, fst.st_ino)
        return expected

    def _cleanup_owned_temp(self):
        record = self._install
        if not record.owned_temp or record.temp_name is None or record.parent_node is None:
            return None
        parent = record.parent_node
        if parent.fd is None:
            return _Failure("temp_ownership_lost", "unlink", None, "installation")
        expected = self._temp_identity(record)
        if expected is None:
            return _Failure("temp_ownership_lost", "unlink", None, "installation")
        try:
            st = _stat(record.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _errno_of(exc) == errno.ENOENT:
                record.owned_temp = False
                for scan in self._scans:
                    if scan.parent is parent:
                        scan.additions.discard(record.temp_name)
                return None
            return _Failure(
                "syscall_failed",
                "stat",
                _errno_of(exc),
                "installation",
                lineage=False,
                code="CODE_PROOF_IO_ERROR",
            )
        if not _is_reg_mode(st.st_mode) or st.st_dev != expected[0] or st.st_ino != expected[1]:
            return _Failure(
                "temp_ownership_lost",
                "unlink",
                None,
                "installation",
            )
        if record.temp_fd is not None:
            try:
                fst = _fstat(record.temp_fd)
            except OSError as exc:
                return _Failure(
                    "syscall_failed",
                    "fstat",
                    _errno_of(exc),
                    "installation",
                    lineage=False,
                    code="CODE_PROOF_IO_ERROR",
                )
            if fst.st_dev != expected[0] or fst.st_ino != expected[1]:
                return _Failure(
                    "temp_ownership_lost",
                    "fstat",
                    None,
                    "installation",
                )
        try:
            _unlink(record.temp_name, dir_fd=parent.fd)
        except OSError as exc:
            return _Failure(
                "syscall_failed",
                "unlink",
                _errno_of(exc),
                "installation",
                lineage=False,
                code="CODE_PROOF_IO_ERROR",
            )
        for scan in self._scans:
            if scan.parent is parent:
                scan.additions.discard(record.temp_name)
        record.owned_temp = False
        return None

    def _verify_group_names(self, group):
        try:
            return self._check_group_names(group)
        except CodeProofIOError as exc:
            reason = None
            operation = None
            errn = None
            try:
                details = exc.details
                reason = details.get("reason")
                operation = details.get("operation")
                errn = details.get("errno")
            except Exception:
                reason = "edge_changed"
            return _Failure(
                reason if type(reason) is str else "edge_changed",
                operation if type(operation) is str else None,
                errn if type(errn) is int else None,
                group,
                lineage=exc.code == "WORK_PATH_UNSAFE",
                code=exc.code,
            )

    def _verify_group_bytes(self, group):
        try:
            return self._check_group_bytes(group)
        except CodeProofIOError as exc:
            reason = None
            operation = None
            errn = None
            try:
                details = exc.details
                reason = details.get("reason")
                operation = details.get("operation")
                errn = details.get("errno")
            except Exception:
                reason = "bytes_changed"
            return _Failure(
                reason if type(reason) is str else "bytes_changed",
                operation if type(operation) is str else None,
                errn if type(errn) is int else None,
                group,
                lineage=True,
                code="WORK_PATH_UNSAFE",
            )

    def _check_named_node(self, node, *, allow_temp_write=False):
        if node is None:
            return None
        if node.logical_absent or node.first_kind == "absent":
            if node.authorized_stamp is not None:
                return self._check_authorized(node)
            if node.parent is None or node.parent.fd is None:
                if node.parent is not None and (
                    node.parent.logical_absent or node.parent.first_kind == "absent"
                ):
                    return None
                return _Failure("missing", "stat", None, node.group)
            try:
                _stat(node.name, dir_fd=node.parent.fd, follow_symlinks=False)
            except OSError as exc:
                if _errno_of(exc) == errno.ENOENT:
                    return None
                return _Failure(
                    "syscall_failed",
                    "stat",
                    _errno_of(exc),
                    node.group,
                )
            return _Failure("late_arrival", "stat", None, node.group)
        if node.first_kind != "stat" or node.parent is None or node.parent.fd is None:
            if node.first_kind == "stat_error":
                if node.parent is None or node.parent.fd is None:
                    return _Failure("missing", "stat", node.first_errno, node.group)
                try:
                    _stat(node.name, dir_fd=node.parent.fd, follow_symlinks=False)
                except OSError as exc:
                    if _errno_of(exc) == node.first_errno:
                        return None
                    return _Failure(
                        "edge_changed",
                        "stat",
                        _errno_of(exc),
                        node.group,
                    )
                return _Failure("edge_changed", "stat", None, node.group)
            if node.first_kind == "stat" and node.fd is not None:
                try:
                    fst = _fstat(node.fd)
                except OSError as exc:
                    return _Failure(
                        "syscall_failed",
                        "fstat",
                        _errno_of(exc),
                        node.group,
                    )
                expected = node.authorized_stamp or node.first_stamp
                if node.is_dir:
                    if expected is not None and _dir_stamp(fst) != expected:
                        return _Failure("edge_changed", "fstat", None, node.group)
                elif expected is not None:
                    try:
                        if _file_stamp(fst) != expected and not allow_temp_write:
                            return _Failure("edge_changed", "fstat", None, node.group)
                    except CodeProofIOError:
                        return _Failure("edge_changed", "fstat", None, node.group)
                if node.parent is None:
                    return None
                return _Failure("missing", "stat", None, node.group)
            return None
        try:
            st = _stat(node.name, dir_fd=node.parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                return _Failure("missing", "stat", errn, node.group)
            return _Failure("syscall_failed", "stat", errn, node.group)
        if node.is_dir:
            stamp = _dir_stamp(st)
            expected = node.authorized_stamp or node.first_stamp
            if stamp != expected:
                return _Failure("edge_changed", "stat", None, node.group)
        else:
            stamp = _file_stamp(st) if _is_reg_mode(st.st_mode) else None
            if stamp is None:
                return _Failure("unsafe_type", "stat", None, node.group)
            expected = node.authorized_stamp or node.first_stamp
            if allow_temp_write and node.authorized_kind == "temp":
                if stamp[0] != expected[0] or stamp[1] != expected[1] or stamp[2] != expected[2]:
                    return _Failure("edge_changed", "stat", None, node.group)
            elif stamp != expected:
                return _Failure("edge_changed", "stat", None, node.group)
        if node.fd is not None:
            try:
                fst = _fstat(node.fd)
            except OSError as exc:
                return _Failure(
                    "syscall_failed",
                    "fstat",
                    _errno_of(exc),
                    node.group,
                )
            if node.is_dir:
                if _dir_stamp(fst) != (node.authorized_stamp or node.first_stamp):
                    return _Failure("edge_changed", "fstat", None, node.group)
            else:
                fd_stamp = _file_stamp(fst)
                expected = node.authorized_stamp or node.first_stamp
                if allow_temp_write and node.authorized_kind == "temp":
                    if (
                        fd_stamp[0] != expected[0]
                        or fd_stamp[1] != expected[1]
                        or fd_stamp[2] != expected[2]
                    ):
                        return _Failure("edge_changed", "fstat", None, node.group)
                elif fd_stamp != expected and not (
                    allow_temp_write and node.authorized_kind == "temp"
                ):
                    if not allow_temp_write:
                        return _Failure("edge_changed", "fstat", None, node.group)
        mode_err = self._role_mode_failure(node, st)
        if mode_err is not None:
            return mode_err
        return None

    def _role_mode_failure(self, node, st):
        if node.role in ("namespace", "family"):
            if not _is_dir_mode(st.st_mode):
                return _Failure("unsafe_type", "stat", None, node.group)
            if not _output_dir_mode_ok(st.st_mode):
                return _Failure("unsafe_mode", "stat", None, node.group)
        if node.role in ("slot", "output_file"):
            if not _is_reg_mode(st.st_mode):
                return _Failure("unsafe_type", "stat", None, node.group)
            if not _output_file_mode_ok(st.st_mode):
                return _Failure("unsafe_mode", "stat", None, node.group)
        if node.role == "bundle_manifest":
            if not _is_reg_mode(st.st_mode):
                return _Failure("unsafe_type", "stat", None, node.group)
            if st.st_nlink != 1:
                return _Failure("link_count", "stat", None, node.group)
            if not _resource_mode_ok(st.st_mode):
                return _Failure("unsafe_mode", "stat", None, node.group)
        return None

    def _check_authorized(self, node):
        if node.parent is None or node.parent.fd is None:
            return _Failure("missing", "stat", None, node.group)
        try:
            st = _stat(node.name, dir_fd=node.parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                return _Failure("missing", "stat", errn, node.group)
            return _Failure("syscall_failed", "stat", errn, node.group)
        if node.authorized_kind == "dir":
            if _dir_stamp(st) != node.authorized_stamp:
                return _Failure("edge_changed", "stat", None, node.group)
        else:
            if not _is_reg_mode(st.st_mode):
                return _Failure("unsafe_type", "stat", None, node.group)
            if _file_stamp(st) != node.authorized_stamp:
                return _Failure("edge_changed", "stat", None, node.group)
        if node.fd is not None:
            try:
                fst = _fstat(node.fd)
            except OSError as exc:
                return _Failure(
                    "syscall_failed",
                    "fstat",
                    _errno_of(exc),
                    node.group,
                )
            if node.authorized_kind == "dir":
                if _dir_stamp(fst) != node.authorized_stamp:
                    return _Failure("edge_changed", "fstat", None, node.group)
            else:
                if _file_stamp(fst) != node.authorized_stamp:
                    return _Failure("edge_changed", "fstat", None, node.group)
        return None

    def _rescan_compare(self, scan):
        parent = scan.parent
        if parent is None or parent.fd is None:
            if scan.complete and not (
                parent is not None
                and (parent.logical_absent or parent.first_kind == "absent")
            ):
                return _Failure("missing", "scandir", None, scan.group)
            return None
        names = []
        extra = 1 if (
            self._install.owned_temp
            and self._install.parent_node is parent
            and self._install.temp_name is not None
        ) else 0
        bound = scan.cap + extra + 1
        try:
            with _scandir(parent.fd) as iterator:
                for entry in iterator:
                    names.append(entry.name)
                    if len(names) >= bound:
                        break
        except OSError as exc:
            return _Failure(
                "syscall_failed",
                "scandir",
                _errno_of(exc),
                scan.group,
            )
        current = set(names)
        if scan.complete:
            expected = (set(scan.names) | scan.additions) - scan.removals
            if current != expected:
                return _Failure("set_changed", "scandir", None, scan.group)
            return None
        original = set(scan.names)
        if current != original:
            return _Failure("set_changed", "scandir", None, scan.group)
        return None

    def _check_group_nodes(self, group, *, skip=None):
        skipped = skip if skip is not None else ()
        for node in self._nodes:
            if node.group != group or node in skipped:
                continue
            err = self._check_named_node(
                node,
                allow_temp_write=(
                    group == "installation"
                    and self._install.phase in ("temp_created", "writing")
                ),
            )
            if err is not None:
                return err
        return None

    def _check_group_names(self, group):
        if group == "checkout":
            return self._check_group_nodes("checkout")
        if group == "ancestors":
            return self._check_group_nodes("ancestors")
        if group == "resources":
            record_nodes = []
            if self._resource_records is not None:
                for record in self._resource_records:
                    if record.node is not None:
                        record_nodes.append(record.node)
            err = self._check_group_nodes("resources", skip=record_nodes)
            if err is not None:
                return err
            if self._resource_records is None:
                return None
            for record in self._resource_records:
                err = self._check_resource_names(record)
                if err is not None:
                    return err
            return None
        if group == "metadata":
            return self._check_group_nodes("metadata")
        if group == "bundle":
            err = self._check_group_nodes("bundle")
            if err is not None:
                return err
            for scan in self._scans:
                if scan.group == "bundle":
                    err = self._rescan_compare(scan)
                    if err is not None:
                        return err
            return None
        if group == "output_layout":
            err = self._check_group_nodes("output_layout")
            if err is not None:
                return err
            for scan in self._scans:
                if scan.group in ("output_layout", "output_files"):
                    err = self._rescan_compare(scan)
                    if err is not None:
                        return err
            return None
        if group == "output_files":
            for name in _SLOT_NAMES:
                err = self._check_named_node(self._slot_nodes.get(name))
                if err is not None:
                    return err
            return self._check_group_nodes("output_files")
        if group == "installation":
            return self._check_install_nodes()
        return None

    def _check_install_nodes(self):
        record = self._install
        node = record.temp_node
        phase = record.phase
        if node is None or record.temp_name is None or record.parent_node is None:
            if record.final_node is not None:
                return self._check_named_node(record.final_node)
            return None
        parent = record.parent_node
        if parent.fd is None:
            return _Failure("missing", "stat", None, "installation")
        if phase in ("cleaned", "durable", "idle") and record.cleaned_prefix:
            try:
                _stat(record.temp_name, dir_fd=parent.fd, follow_symlinks=False)
            except OSError as exc:
                if _errno_of(exc) == errno.ENOENT:
                    if record.final_node is not None:
                        err = self._check_named_node(record.final_node)
                        if err is not None:
                            return err
                    if (
                        record.temp_fd is not None
                        and record.final_node is not None
                        and record.final_node.authorized_stamp is not None
                    ):
                        try:
                            fst = _fstat(record.temp_fd)
                        except OSError as exc2:
                            return _Failure(
                                "syscall_failed",
                                "fstat",
                                _errno_of(exc2),
                                "installation",
                            )
                        expected = record.final_node.authorized_stamp
                        if fst.st_dev != expected[0] or fst.st_ino != expected[1]:
                            return _Failure(
                                "edge_changed",
                                "fstat",
                                None,
                                "installation",
                            )
                    return None
                return _Failure(
                    "syscall_failed",
                    "stat",
                    _errno_of(exc),
                    "installation",
                )
            return _Failure("temp_ownership_lost", "stat", None, "installation")
        try:
            st = _stat(record.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            errn = _errno_of(exc)
            if errn == errno.ENOENT:
                return _Failure("temp_ownership_lost", "stat", errn, "installation")
            return _Failure("syscall_failed", "stat", errn, "installation")
        if not _is_reg_mode(st.st_mode):
            return _Failure("unsafe_type", "stat", None, "installation")
        expected = node.first_stamp
        if expected is None:
            return _Failure("edge_changed", "stat", None, "installation")
        if st.st_dev != expected[0] or st.st_ino != expected[1]:
            return _Failure("temp_ownership_lost", "stat", None, "installation")
        if not _output_file_mode_ok(st.st_mode):
            return _Failure("unsafe_mode", "stat", None, "installation")
        if phase in ("temp_created", "writing"):
            if record.temp_fd is not None:
                try:
                    fst = _fstat(record.temp_fd)
                except OSError as exc:
                    return _Failure(
                        "syscall_failed",
                        "fstat",
                        _errno_of(exc),
                        "installation",
                    )
                if fst.st_dev != expected[0] or fst.st_ino != expected[1]:
                    return _Failure("temp_ownership_lost", "fstat", None, "installation")
            return None
        payload = record.payload or b""
        if phase == "temp_ready":
            if st.st_nlink != 1 or st.st_size != len(payload):
                return _Failure(
                    "link_count" if st.st_nlink != 1 else "bytes_changed",
                    "stat",
                    None,
                    "installation",
                )
        if phase == "linked":
            if st.st_nlink != 2:
                return _Failure("link_count", "stat", None, "installation")
        if record.final_node is not None:
            err = self._check_named_node(record.final_node)
            if err is not None:
                return err
        return None

    def _check_resource_names(self, record):
        node = record.node
        if node is None:
            return None
        if node.first_kind == "absent":
            if node.parent is None or node.parent.fd is None:
                if node.parent is not None and (
                    node.parent.logical_absent or node.parent.first_kind == "absent"
                ):
                    return None
                return _Failure("missing", "stat", errno.ENOENT, "resources")
            try:
                _stat(node.name, dir_fd=node.parent.fd, follow_symlinks=False)
            except OSError as exc:
                if _errno_of(exc) == errno.ENOENT:
                    return None
                return _Failure(
                    "missing" if _errno_of(exc) == errno.ENOENT else "edge_changed",
                    "stat",
                    _errno_of(exc),
                    "resources",
                )
            return _Failure("edge_changed", "stat", None, "resources")
        err = self._check_named_node(node)
        if err is not None:
            return err
        return None

    def _check_group_bytes(self, group):
        if group == "checkout":
            if self._project_node is not None and self._project_node.payload is not None:
                return self._reread_node(self._project_node, group)
            if (
                self._git_node is not None
                and self._git_node.payload is not None
                and self._git_node.fd is not None
            ):
                return self._reread_node(self._git_node, group)
            return None
        if group == "resources":
            if self._resource_records is None:
                return None
            for record in self._resource_records:
                node = record.node
                if node is None or node.payload is None or node.fd is None:
                    continue
                err = self._reread_node(node, "resources")
                if err is not None:
                    return err
            return None
        if group == "metadata":
            if self._input_node is not None and self._input_node.payload is not None:
                return self._reread_node(self._input_node, "metadata")
            return None
        if group == "bundle":
            for node in self._nodes:
                if node.group == "bundle" and node.payload is not None and node.fd is not None:
                    err = self._reread_node(node, "bundle")
                    if err is not None:
                        return err
            return None
        if group == "output_files":
            for node in self._nodes:
                if (
                    node.group == "output_files"
                    and node.payload is not None
                    and node.fd is not None
                ):
                    err = self._reread_node(node, "output_files")
                    if err is not None:
                        return err
            return None
        if group == "installation":
            record = self._install
            if (
                record.phase in ("temp_ready", "linked", "cleaned", "durable")
                and record.temp_fd is not None
                and record.payload is not None
                and record.phase != "cleaned"
                and record.phase != "durable"
            ):
                try:
                    _seek(record.temp_fd, 0, os.SEEK_SET)
                    data = self._read_all(record.temp_fd, len(record.payload))
                except Exception:
                    return _Failure("bytes_changed", "read", None, "installation")
                if data != record.payload[: record.written or len(record.payload)]:
                    return _Failure("bytes_changed", "read", None, "installation")
            if record.final_node is not None and record.final_node.payload is not None:
                return self._reread_node(record.final_node, "installation")
            return None
        return None

    def _reread_node(self, node, group):
        if node.fd is None or node.payload is None:
            return None
        try:
            data = self._read_all(node.fd, len(node.payload))
        except CodeProofIOError:
            return _Failure("bytes_changed", "read", None, group)
        except OSError as exc:
            return _Failure("syscall_failed", "read", _errno_of(exc), group)
        if data != node.payload:
            return _Failure("bytes_changed", "read", None, group)
        try:
            fst = _fstat(node.fd)
        except OSError as exc:
            return _Failure("syscall_failed", "fstat", _errno_of(exc), group)
        expected = node.authorized_stamp or node.first_stamp
        if expected is not None and not node.is_dir:
            if _file_stamp(fst) != expected:
                return _Failure("edge_changed", "fstat", None, group)
        return None

    def _failure_to_error(self, failure, *, phase=None, prior=None, failed_groups=None):
        p_code = p_op = p_err = None
        if prior is not None:
            p_code, p_op, p_err = _prior_fields(prior)
        code = "WORK_PATH_UNSAFE" if failure.lineage else failure.code
        if failure.lineage:
            code = "WORK_PATH_UNSAFE"
        return CodeProofIOError(
            code,
            _nine(
                phase or self._phase,
                failure.group,
                failure.reason,
                failure.operation,
                failure.errno,
                prior_code=p_code,
                prior_operation=p_op,
                prior_errno=p_err,
                failed_groups=failed_groups,
            ),
        )

    def _verify_names_result(self, *, isolate):
        return self._run_verify(names_only=True, isolate=isolate)

    def _verify_full_result(self, *, isolate):
        return self._run_verify(names_only=False, isolate=isolate)

    def _run_verify(self, *, names_only, isolate):
        failures = {}
        groups = [group for group in _GROUPS if group in self._reached_groups]
        def record(group, failure):
            if failure is None:
                return
            if group not in failures:
                failures[group] = failure

        for group in groups:
            try:
                failure = self._verify_group_names(group)
            except BaseException:
                failure = _Failure("edge_changed", None, None, group, lineage=True)
                if not isolate:
                    return self._failure_to_error(failure)
            record(group, failure)
            if failure is not None and not isolate:
                return self._failure_to_error(failure)
            if names_only:
                continue
            try:
                failure = self._verify_group_bytes(group)
            except BaseException:
                failure = _Failure("bytes_changed", "read", None, group, lineage=True)
                if not isolate:
                    return self._failure_to_error(failure)
            record(group, failure)
            if failure is not None and not isolate:
                return self._failure_to_error(failure)
        if not names_only:
            for group in groups:
                try:
                    failure = self._verify_group_names(group)
                except BaseException:
                    failure = _Failure("edge_changed", None, None, group, lineage=True)
                    if not isolate:
                        return self._failure_to_error(failure)
                record(group, failure)
                if failure is not None and not isolate:
                    return self._failure_to_error(failure)
        if not failures:
            return None
        ordered = [group for group in _GROUPS if group in failures]
        first = failures[ordered[0]]
        return self._failure_to_error(first, failed_groups=ordered)

    def _close_all(self):
        cleanup = None
        interrupt = None
        for fd in reversed(list(self._fd_order)):
            try:
                _close(fd)
            except OSError as exc:
                if cleanup is None:
                    cleanup = _Failure(
                        "syscall_failed",
                        "close",
                        _errno_of(exc),
                        None,
                        lineage=False,
                        code="CODE_PROOF_IO_ERROR",
                    )
            except Exception:
                if cleanup is None:
                    cleanup = _Failure(
                        "syscall_failed",
                        "close",
                        None,
                        None,
                        lineage=False,
                        code="CODE_PROOF_IO_ERROR",
                    )
            except BaseException as exc:
                if interrupt is None:
                    interrupt = exc
        self._fd_order = []
        if self._lock_dup_fd is not None:
            try:
                _close(self._lock_dup_fd)
            except OSError as exc:
                if cleanup is None:
                    cleanup = _Failure(
                        "syscall_failed",
                        "close",
                        _errno_of(exc),
                        None,
                        lineage=False,
                        code="CODE_PROOF_IO_ERROR",
                    )
            except Exception:
                if cleanup is None:
                    cleanup = _Failure(
                        "syscall_failed",
                        "close",
                        None,
                        None,
                        lineage=False,
                        code="CODE_PROOF_IO_ERROR",
                    )
            except BaseException as exc:
                if interrupt is None:
                    interrupt = exc
            self._lock_dup_fd = None
        return cleanup, interrupt

    def _clear_install_refs(self):
        record = self._install
        record.temp_node = None
        record.temp_fd = None
        record.parent_node = None
        record.final_node = None
        record.payload = None
        record.temp_name = None

    def _clear_graph(self):
        self._clear_install_refs()
        self._resource_context = None
        self._resource_plan = None
        self._resource_records = None
        self._schemas_directory = None
        self._profiles_directory = None
        self._nodes = []
        self._by_key = {}
        self._fd_order = []
        self._scans = []
        self._root_node = None
        self._checkout_node = None
        self._work_node = None
        self._batch_node = None
        self._namespace_node = None
        self._family_nodes = {}
        self._slot_nodes = {}
        self._git_node = None
        self._project_node = None
        self._input_node = None
        self._bundle_root = None
        self._bundle_objects_dir = None
        self._lock_fd = None
        self._lock_dup_fd = None
        self._closed_cleared = True

    def _finalize(self, original):
        if self._state == "closed":
            return None
        self._state = "finalizing"
        self._phase = "final_verify"
        failures = {}
        interrupt = None

        def record(group, failure):
            if failure is None:
                return
            if group not in failures:
                failures[group] = failure

        def capture_interrupt(exc):
            nonlocal interrupt
            if type(exc) is KeyboardInterrupt or type(exc) is SystemExit:
                if interrupt is None:
                    interrupt = exc

        groups = [group for group in _GROUPS if group in self._reached_groups]
        for group in groups:
            try:
                failure = self._verify_group_names(group)
            except BaseException as exc:
                capture_interrupt(exc)
                failure = _Failure("edge_changed", None, None, group, lineage=True)
            record(group, failure)
            try:
                failure = self._verify_group_bytes(group)
            except BaseException as exc:
                capture_interrupt(exc)
                failure = _Failure("bytes_changed", "read", None, group, lineage=True)
            record(group, failure)
        for group in groups:
            try:
                failure = self._verify_group_names(group)
            except BaseException as exc:
                capture_interrupt(exc)
                failure = _Failure("edge_changed", None, None, group, lineage=True)
            record(group, failure)
        self._phase = "closing"
        cleanup = None
        try:
            cleanup = self._cleanup_owned_temp()
        except BaseException as exc:
            capture_interrupt(exc)
            if cleanup is None and type(exc) is not KeyboardInterrupt and type(exc) is not SystemExit:
                cleanup = _Failure(
                    "syscall_failed",
                    "unlink",
                    _errno_of(exc) if isinstance(exc, OSError) else None,
                    "installation",
                    lineage=False,
                    code="CODE_PROOF_IO_ERROR",
                )
        close_err = None
        try:
            close_err, close_interrupt = self._close_all()
        except BaseException as exc:
            capture_interrupt(exc)
            close_err = None
            close_interrupt = exc if type(exc) is KeyboardInterrupt or type(exc) is SystemExit else None
            if close_interrupt is None and cleanup is None:
                cleanup = _Failure(
                    "syscall_failed",
                    "close",
                    None,
                    None,
                    lineage=False,
                    code="CODE_PROOF_IO_ERROR",
                )
        else:
            if interrupt is None:
                interrupt = close_interrupt
        if cleanup is None:
            cleanup = close_err
        try:
            self._clear_graph()
        except BaseException as exc:
            capture_interrupt(exc)
        self._state = "closed"
        self._phase = "closing"
        lineage_groups = [
            group
            for group in _GROUPS
            if group in failures and failures[group].lineage
        ]
        all_failed = [group for group in _GROUPS if group in failures]
        selected = None
        if lineage_groups:
            first = failures[lineage_groups[0]]
            selected = self._failure_to_error(
                first,
                phase="final_verify",
                prior=original,
                failed_groups=lineage_groups,
            )
        elif cleanup is not None:
            selected = self._failure_to_error(
                cleanup,
                phase="closing",
                prior=original,
                failed_groups=all_failed,
            )
        elif original is not None:
            selected = original
        elif interrupt is not None:
            selected = interrupt
        self._final_selected = selected
        return selected


@contextmanager
def open_code_session(*, batch_id) -> Iterator[_CodeSession]:
    session = _CodeSession()
    original = None
    try:
        session._setup(batch_id)
        session._state = "active"
        session._phase = "idle"
        yield session
    except BaseException as exc:
        original = exc
        selected = session._finalize(original)
        if selected is original:
            raise
        if selected is not None:
            raise selected from None
        raise
    else:
        selected = session._finalize(None)
        if selected is not None:
            raise selected from None
