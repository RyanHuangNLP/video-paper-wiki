"""Private CODE evidence I/O session: one retained filesystem graph per command."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import re
import secrets
import stat
import tomllib
import unicodedata

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

WORKSPACE_ROOT_INVALID = "WORKSPACE_ROOT_INVALID"
INVALID_BATCH_ID = "INVALID_BATCH_ID"
WORK_PATH_UNSAFE = "WORK_PATH_UNSAFE"
CODE_PROOF_IO_ERROR = "CODE_PROOF_IO_ERROR"
CODE_PROOF_RESOURCE_INVALID = "CODE_PROOF_RESOURCE_INVALID"
CODE_PROOF_LIMIT_EXCEEDED = "CODE_PROOF_LIMIT_EXCEEDED"
CODE_PROOF_CONFLICT = "CODE_PROOF_CONFLICT"
CODE_PROOF_BUSY = "CODE_PROOF_BUSY"

_MESSAGES = {
    WORKSPACE_ROOT_INVALID: "CODE workspace root is invalid",
    INVALID_BATCH_ID: "CODE batch identifier is invalid",
    WORK_PATH_UNSAFE: "CODE retained path is unsafe",
    CODE_PROOF_IO_ERROR: "CODE evidence I/O failed",
    CODE_PROOF_RESOURCE_INVALID: "CODE evidence resource is invalid",
    CODE_PROOF_LIMIT_EXCEEDED: "CODE evidence limit exceeded",
    CODE_PROOF_CONFLICT: "CODE evidence artifact conflicts",
    CODE_PROOF_BUSY: "CODE evidence workspace is busy",
}

_IO_CODES = frozenset(_MESSAGES)
_NINE_FIELD_CODES = frozenset(
    {
        WORKSPACE_ROOT_INVALID,
        INVALID_BATCH_ID,
        WORK_PATH_UNSAFE,
        CODE_PROOF_IO_ERROR,
        CODE_PROOF_RESOURCE_INVALID,
        CODE_PROOF_BUSY,
    }
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
_GROUP_SET = frozenset(_GROUPS)
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
_OPS = frozenset(
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
_CONFLICT_REASONS = frozenset(
    {
        "request_changed",
        "acquisition_changed",
        "config_format_changed",
        "artifact_changed",
    }
)
_RESOURCE_REASONS = frozenset(
    {"resource_origin", "resource_hash", "resource_shape"}
)
_PRIOR_CODES = frozenset(
    {
        WORKSPACE_ROOT_INVALID,
        INVALID_BATCH_ID,
        WORK_PATH_UNSAFE,
        CODE_PROOF_IO_ERROR,
        CODE_PROOF_RESOURCE_INVALID,
        CODE_PROOF_LIMIT_EXCEEDED,
        CODE_PROOF_CONFLICT,
        CODE_PROOF_BUSY,
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
_LIMIT_KEYS = ("instance_pointer", "limit_name", "limit", "observed")
_CONFLICT_KEYS = ("instance_pointer", "reason")
_OBJECT_RECORD_KEYS = (
    "oid",
    "object_type",
    "body_size_bytes",
    "body_sha256",
    "framed_sha256",
)
_OBJECT_RECORD_KEY_SET = frozenset(_OBJECT_RECORD_KEYS)
_OUTPUT_LIMIT_KEYS = (
    "max_request_bytes",
    "max_intent_bytes",
    "max_bundle_bytes",
    "max_observation_bytes",
    "max_config_document_bytes",
    "max_handoff_bytes",
    "max_output_peak_bytes",
)
_GIT_LIMIT_KEYS = (
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
)
_MAX_REQUEST_BYTES = 65536
_MAX_INTENT_BYTES = 1048576
_MAX_BUNDLE_BYTES = 1048576
_MAX_OBSERVATION_BYTES = 2097152
_MAX_CONFIG_DOCUMENT_BYTES = 2097152
_MAX_HANDOFF_BYTES = 131072
_MAX_OUTPUT_PEAK_BYTES = 134217728
_MAX_OBJECTS = 2048
_MAX_OBJECT_BYTES = 8388608
_MAX_TOTAL_OBJECT_BYTES = 33554432
_MAX_TARGETS = 32
_MAX_TREE_ENTRIES = 32768
_MAX_CONFIGS = 32
_MAX_HANDOFFS = 32
_MAX_NAMESPACE_ENTRIES = 7
_MAX_BUNDLE_ROOT_ENTRIES = 2
_MAX_GIT_MARKER_BYTES = 65536
_MAX_PYPROJECT_BYTES = 1048576
_MAX_BUNDLE_PATH_CHARS = 4096
_MAX_BUNDLE_PATH_BYTES = 16384
_MAX_REQUEST_INPUT_BYTES = 65536
_MAX_OBSERVE_INPUT_BYTES = 1048576
_WRITE_CHUNK = 65536
_CONTEXT_BOUND = 1024
_TEMP_PREFIX = ".ce-tmp-"
_WORK_NAME = ".work"
_NS_NAME = "code-evidence-v1"
_DIRECT_FILES = {
    "request.json": _MAX_REQUEST_BYTES,
    "intent.json": _MAX_INTENT_BYTES,
    "bundle.json": _MAX_BUNDLE_BYTES,
    "observation.json": _MAX_OBSERVATION_BYTES,
}
_DIRECT_LIMIT_NAME = {
    "request.json": "max_request_bytes",
    "intent.json": "max_intent_bytes",
    "bundle.json": "max_bundle_bytes",
    "observation.json": "max_observation_bytes",
}
_DIRECT_POINTER = {
    "request.json": "/request",
    "intent.json": "/intent",
    "bundle.json": "/bundle",
    "observation.json": "/observation",
}
_DIRECT_NAMES = ("bundle.json", "intent.json", "observation.json", "request.json")
_FAMILY_NAMES = ("configs", "handoffs", "objects")
_NS_EXPECTED = frozenset(_DIRECT_FILES) | frozenset(_FAMILY_NAMES)
_OUTPUT_LIMIT_MAX = {
    "max_request_bytes": _MAX_REQUEST_BYTES,
    "max_intent_bytes": _MAX_INTENT_BYTES,
    "max_bundle_bytes": _MAX_BUNDLE_BYTES,
    "max_observation_bytes": _MAX_OBSERVATION_BYTES,
    "max_config_document_bytes": _MAX_CONFIG_DOCUMENT_BYTES,
    "max_handoff_bytes": _MAX_HANDOFF_BYTES,
    "max_output_peak_bytes": _MAX_OUTPUT_PEAK_BYTES,
}
_GIT_LIMIT_MAX = {
    "max_targets": _MAX_TARGETS,
    "max_objects": _MAX_OBJECTS,
    "max_tree_entries": _MAX_TREE_ENTRIES,
    "max_object_bytes": _MAX_OBJECT_BYTES,
    "max_total_object_bytes": _MAX_TOTAL_OBJECT_BYTES,
}
_HARD_OUTPUT_LIMITS = {
    "max_request_bytes": _MAX_REQUEST_BYTES,
    "max_intent_bytes": _MAX_INTENT_BYTES,
    "max_bundle_bytes": _MAX_BUNDLE_BYTES,
    "max_observation_bytes": _MAX_OBSERVATION_BYTES,
    "max_config_document_bytes": _MAX_CONFIG_DOCUMENT_BYTES,
    "max_handoff_bytes": _MAX_HANDOFF_BYTES,
    "max_output_peak_bytes": _MAX_OUTPUT_PEAK_BYTES,
}
_BAD_RESOURCE_BITS = (
    stat.S_IXUSR
    | stat.S_IXGRP
    | stat.S_IXOTH
    | stat.S_IWGRP
    | stat.S_IWOTH
    | stat.S_ISUID
    | stat.S_ISGID
    | stat.S_ISVTX
)
_BATCH_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$"
)
_HEX_DIGITS = "0123456789abcdef"
_TEMP_READY_PHASES = frozenset({"temp_created", "writing", "temp_ready", "linked"})
_ACTIVE_TEMP_FLEX = frozenset({"temp_created", "writing"})

_getcwd = os.getcwd
_open = os.open
_stat = os.stat
_fstat = os.fstat
_scandir = os.scandir
_read = os.read
_seek = os.lseek
_mkdir = os.mkdir
_write = os.write
_link = os.link
_unlink = os.unlink
_fsync = os.fsync
_flock = fcntl.flock
_dup = os.dup
_close = os.close


def _errno_values(*names):
    out = set()
    for name in names:
        value = getattr(errno, name, None)
        if type(value) is int:
            out.add(value)
    return frozenset(out)


_BUSY_ERRNOS = _errno_values("EACCES", "EAGAIN", "EWOULDBLOCK")
_UNSUP_ERRNOS = _errno_values("ENOSYS", "EINVAL", "ENOTSUP", "EOPNOTSUPP")
_ENOENT = getattr(errno, "ENOENT", 2)
_EEXIST = getattr(errno, "EEXIST", 17)
_ELOOP = getattr(errno, "ELOOP", 40)


def _capability_snapshot():
    try:
        flags = (
            ("O_RDONLY", True),
            ("O_WRONLY", False),
            ("O_RDWR", False),
            ("O_CREAT", False),
            ("O_EXCL", False),
            ("O_NOFOLLOW", False),
            ("O_DIRECTORY", False),
            ("O_CLOEXEC", False),
            ("O_NONBLOCK", False),
        )
        for name, allow_zero in flags:
            value = getattr(os, name)
            if type(value) is not int:
                return False
            if value == 0 and not allow_zero:
                return False
        dir_fd = os.supports_dir_fd
        for fn in (os.open, os.stat, os.mkdir, os.link, os.unlink):
            if fn not in dir_fd:
                return False
        follow = os.supports_follow_symlinks
        if os.stat not in follow or os.link not in follow:
            return False
        if os.scandir not in os.supports_fd:
            return False
        for fn in (
            os.fstat,
            os.read,
            os.lseek,
            os.write,
            os.fsync,
            os.dup,
            os.close,
            fcntl.flock,
        ):
            if not callable(fn):
                return False
        if type(os.SEEK_SET) is not int:
            return False
        if type(fcntl.LOCK_EX) is not int:
            return False
        if type(fcntl.LOCK_NB) is not int:
            return False
        if type(fcntl.LOCK_UN) is not int:
            return False
        return True
    except Exception:
        return False


def _dir_flags():
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _file_rd_flags():
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _temp_flags():
    return os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


def _bad_ctx():
    raise ValueError("Invalid CODE I/O error context") from None


def _copy_plain(value):
    if type(value) is dict:
        out = {}
        for key in value:
            out[key] = _copy_plain(value[key])
        return out
    if type(value) is list:
        return [_copy_plain(item) for item in value]
    return value


def _closed_keys(details, expected):
    if type(details) is not dict:
        _bad_ctx()
    seen = []
    for key in details:
        if type(key) is not str:
            _bad_ctx()
        seen.append(key)
    allowed = frozenset(expected)
    for key in seen:
        if key not in allowed:
            _bad_ctx()
    if len(seen) != len(expected):
        _bad_ctx()


def _require_phase(value):
    if type(value) is not str or value not in _PHASES:
        _bad_ctx()
    return value


def _require_group(value):
    if value is None:
        return None
    if type(value) is not str or value not in _GROUP_SET:
        _bad_ctx()
    return value


def _require_reason(value):
    if type(value) is not str or value not in _REASONS:
        _bad_ctx()
    return value


def _require_op(value):
    if value is None:
        return None
    if type(value) is not str or value not in _OPS:
        _bad_ctx()
    return value


def _require_errno(value):
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > 65535:
        _bad_ctx()
    return value


def _require_prior_code(value):
    if value is None:
        return None
    if type(value) is not str or value not in _PRIOR_CODES:
        _bad_ctx()
    return value


def _require_failed_groups(value):
    if type(value) is not list:
        _bad_ctx()
    seen = []
    present = set()
    for item in value:
        if type(item) is not str or item not in _GROUP_SET:
            _bad_ctx()
        if item in present:
            _bad_ctx()
        present.add(item)
        seen.append(item)
    if len(seen) > 8:
        _bad_ctx()
    expected = [name for name in _GROUPS if name in present]
    if seen != expected:
        _bad_ctx()
    return list(seen)


def _require_pointer(value):
    if type(value) is not str or not value or len(value) > _CONTEXT_BOUND:
        _bad_ctx()
    return value


def _validate_nine(details):
    _closed_keys(details, _NINE_KEYS)
    phase = _require_phase(details["phase"])
    group = _require_group(details["group"])
    reason = _require_reason(details["reason"])
    operation = _require_op(details["operation"])
    errn = _require_errno(details["errno"])
    prior_code = _require_prior_code(details["prior_code"])
    prior_operation = _require_op(details["prior_operation"])
    prior_errno = _require_errno(details["prior_errno"])
    failed_groups = _require_failed_groups(details["failed_groups"])
    return {
        "phase": phase,
        "group": group,
        "reason": reason,
        "operation": operation,
        "errno": errn,
        "prior_code": prior_code,
        "prior_operation": prior_operation,
        "prior_errno": prior_errno,
        "failed_groups": failed_groups,
    }


def _validate_limit(details):
    _closed_keys(details, _LIMIT_KEYS)
    pointer = _require_pointer(details["instance_pointer"])
    name = details["limit_name"]
    limit = details["limit"]
    observed = details["observed"]
    if type(name) is not str or not name or len(name) > _CONTEXT_BOUND:
        _bad_ctx()
    if type(limit) is not int or limit <= 0:
        _bad_ctx()
    if type(observed) is not int or observed < 0:
        _bad_ctx()
    return {
        "instance_pointer": pointer,
        "limit_name": name,
        "limit": limit,
        "observed": observed,
    }


def _validate_conflict(details):
    _closed_keys(details, _CONFLICT_KEYS)
    pointer = _require_pointer(details["instance_pointer"])
    reason = details["reason"]
    if type(reason) is not str or reason not in _CONFLICT_REASONS:
        _bad_ctx()
    return {"instance_pointer": pointer, "reason": reason}


class CodeProofIOError(Exception):
    def __init__(self, code, details):
        if type(code) is not str or code not in _IO_CODES:
            _bad_ctx()
        if code in _NINE_FIELD_CODES:
            stored = _validate_nine(details)
        elif code == CODE_PROOF_LIMIT_EXCEEDED:
            stored = _validate_limit(details)
        elif code == CODE_PROOF_CONFLICT:
            stored = _validate_conflict(details)
        else:
            _bad_ctx()
        message = _MESSAGES[code]
        Exception.__init__(self, message)
        self._code = code
        self._message = message
        self._details = stored
        self._exit_code = 2

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


def _normalize_failed(groups):
    present = set()
    if type(groups) is list or type(groups) is tuple:
        for item in groups:
            if item in _GROUP_SET:
                present.add(item)
    return [name for name in _GROUPS if name in present]


def _io_error(
    code,
    *,
    phase,
    group=None,
    reason,
    operation=None,
    errno=None,
    prior_code=None,
    prior_operation=None,
    prior_errno=None,
    failed_groups=None,
):
    if failed_groups is None:
        failed_groups = [] if group is None else [group]
    details = {
        "phase": phase,
        "group": group,
        "reason": reason,
        "operation": operation,
        "errno": errno,
        "prior_code": prior_code,
        "prior_operation": prior_operation,
        "prior_errno": prior_errno,
        "failed_groups": _normalize_failed(failed_groups),
    }
    return CodeProofIOError(code, details)


def _limit_error(pointer, name, limit, observed):
    return CodeProofIOError(
        CODE_PROOF_LIMIT_EXCEEDED,
        {
            "instance_pointer": pointer,
            "limit_name": name,
            "limit": limit,
            "observed": observed,
        },
    )


def _conflict_error(pointer, reason):
    return CodeProofIOError(
        CODE_PROOF_CONFLICT,
        {"instance_pointer": pointer, "reason": reason},
    )


def _raise_io(*args, **kwargs):
    raise _io_error(*args, **kwargs) from None


def _raise_limit(pointer, name, limit, observed):
    raise _limit_error(pointer, name, limit, observed) from None


def _raise_conflict(pointer, reason):
    raise _conflict_error(pointer, reason) from None


def _raise_struct(reason):
    raise CodeProofStructureError(reason) from None


def _raise_git(code, message, details):
    raise CodeGitProofError(code, message, details, exit_code=2) from None


def _bound_errno(exc):
    try:
        value = exc.errno
    except Exception:
        return None
    if type(value) is int and 0 <= value <= 65535:
        return value
    return None


def _safe_attr(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return _MISSING


_MISSING = object()


def _extract_prior(exc):
    if exc is None:
        return None, None, None
    code = None
    operation = None
    errn = None
    raw_code = _safe_attr(exc, "code")
    if raw_code is not _MISSING and type(raw_code) is str and raw_code in _PRIOR_CODES:
        code = raw_code
    details = _safe_attr(exc, "details")
    if details is not _MISSING and type(details) is dict:
        try:
            keys_ok = True
            for key in details:
                if type(key) is not str:
                    keys_ok = False
                    break
            if keys_ok:
                if "operation" in details:
                    op = details["operation"]
                    if op is None or (type(op) is str and op in _OPS):
                        operation = op
                if "errno" in details:
                    en = details["errno"]
                    if en is None or (type(en) is int and 0 <= en <= 65535):
                        errn = en
        except Exception:
            pass
    return code, operation, errn


def _is_hex(value, width):
    if type(value) is not str or len(value) != width:
        return False
    for char in value:
        if char not in _HEX_DIGITS:
            return False
    return True


def _join_abs(base, *parts):
    path = base
    for part in parts:
        path = "/" + part if path == "/" else path + "/" + part
    return path


def _split_abs(path):
    if path == "/":
        return []
    parts = path.split("/")
    if parts[0] != "":
        return None
    out = parts[1:]
    for part in out:
        if part == "" or part == "." or part == "..":
            return None
    return out


def _canonical_abs(path):
    if type(path) is not str or "\0" in path:
        return False
    if not path.startswith("/"):
        return False
    if path != "/" and path.endswith("/"):
        return False
    return _split_abs(path) is not None


def _canonical_rel(path):
    if type(path) is not str or "\0" in path:
        return False
    if path == "" or path.startswith("/") or path.endswith("/"):
        return False
    parts = path.split("/")
    for part in parts:
        if part == "" or part == "." or part == "..":
            return False
    return True


def _paths_overlap(first, second):
    if first == second:
        return True
    return first.startswith(second + "/") or second.startswith(first + "/")


def _dir_stamp(st):
    mt = st.st_mtime_ns
    ct = st.st_ctime_ns
    if type(mt) is not int or type(ct) is not int:
        return None
    return (st.st_dev, st.st_ino, st.st_mode)


def _file_stamp(st):
    mt = st.st_mtime_ns
    ct = st.st_ctime_ns
    if type(mt) is not int or type(ct) is not int:
        return None
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        mt,
        ct,
        st.st_nlink,
    )


def _identity(st):
    return (st.st_dev, st.st_ino)


def _is_dir(st):
    return stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode)


def _is_reg(st):
    return stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode)


def _dir_reason(st, exact_mode=None):
    if not _is_dir(st):
        return "unsafe_type"
    if exact_mode is not None and stat.S_IMODE(st.st_mode) != exact_mode:
        return "unsafe_mode"
    return None


def _file_reason(st, *, exact_mode=None, resource_policy=False):
    if not _is_reg(st):
        return "unsafe_type"
    if st.st_nlink != 1:
        return "link_count"
    if exact_mode is not None:
        if stat.S_IMODE(st.st_mode) != exact_mode:
            return "unsafe_mode"
    elif resource_policy:
        if (st.st_mode & _BAD_RESOURCE_BITS) != 0:
            return "unsafe_mode"
    return None


def _parse_closed_limits(value, keys, maxima):
    if type(value) is not dict:
        _raise_struct("limits")
    seen = []
    for key in value:
        if type(key) is not str:
            _raise_struct("limits")
        seen.append(key)
    allowed = frozenset(keys)
    for key in seen:
        if key not in allowed:
            _raise_struct("limits")
    if len(seen) != len(keys):
        _raise_struct("limits")
    out = {}
    for key in keys:
        item = value[key]
        if type(item) is not int or item <= 0 or item > maxima[key]:
            _raise_struct("limits")
        out[key] = item
    return out


def _family_member(family, basename):
    if family == "objects":
        if basename.endswith(".body"):
            oid = basename[:-5]
            if _is_hex(oid, 40) or _is_hex(oid, 64):
                return oid
        return None
    if family in ("configs", "handoffs"):
        if basename.endswith(".json") and _is_hex(basename[:-5], 64):
            return basename[:-5]
        return None
    return None


def _parse_output_name(name):
    if name in _DIRECT_FILES:
        return ("direct", name, None)
    if name.count("/") != 1:
        return None
    family, basename = name.split("/")
    if family not in _FAMILY_NAMES:
        return None
    if _family_member(family, basename) is None:
        return None
    return ("family", family, basename)


def _pointer_for_rel(rel):
    parsed = _parse_output_name(rel)
    if parsed is None:
        return "/output"
    kind, first, _second = parsed
    if kind == "direct":
        return _DIRECT_POINTER[first]
    if first == "objects":
        return "/objects"
    if first == "configs":
        return "/config"
    return "/handoffs"


def _cap_for_rel(rel, limits):
    parsed = _parse_output_name(rel)
    if parsed is None:
        return _MAX_OUTPUT_PEAK_BYTES, "max_output_peak_bytes"
    kind, first, _second = parsed
    if kind == "direct":
        key = _DIRECT_LIMIT_NAME[first]
        return limits[key], key
    if first == "objects":
        return _MAX_OBJECT_BYTES, "max_object_bytes"
    if first == "configs":
        return limits["max_config_document_bytes"], "max_config_document_bytes"
    return limits["max_handoff_bytes"], "max_handoff_bytes"


def _forbidden_bundle_char(char):
    code = ord(char)
    if char == "\\" or char == "\0":
        return True
    if code < 32 or code == 127:
        return True
    if 128 <= code <= 159:
        return True
    if code == 0x2028 or code == 0x2029:
        return True
    if 0xD800 <= code <= 0xDFFF:
        return True
    return False


def _temp_basename():
    return _TEMP_PREFIX + secrets.token_hex(16)


def _is_owned_temp_name(name):
    if type(name) is not str or not name.startswith(_TEMP_PREFIX):
        return False
    token = name[len(_TEMP_PREFIX) :]
    return _is_hex(token, 32)


class _Node:
    __slots__ = (
        "parent",
        "name",
        "lexical",
        "role",
        "group",
        "observed",
        "first_kind",
        "first_named_stamp",
        "first_fd_stamp",
        "first_error_op",
        "first_error_errno",
        "fd",
        "authorized_stamp",
        "authorized_removed",
        "bytes",
        "file_policy",
        "dir_mode",
        "flex_temp",
        "pin_size",
        "pin_sha256",
        "logical",
        "rel",
        "dev_ino",
    )

    def __init__(self, parent, name, lexical, role, group):
        self.parent = parent
        self.name = name
        self.lexical = lexical
        self.role = role
        self.group = group
        self.observed = False
        self.first_kind = None
        self.first_named_stamp = None
        self.first_fd_stamp = None
        self.first_error_op = None
        self.first_error_errno = None
        self.fd = None
        self.authorized_stamp = None
        self.authorized_removed = False
        self.bytes = None
        self.file_policy = None
        self.dir_mode = None
        self.flex_temp = False
        self.pin_size = None
        self.pin_sha256 = None
        self.logical = None
        self.rel = None
        self.dev_ino = None


class _Scan:
    __slots__ = (
        "dir_node",
        "cap",
        "names",
        "stamps",
        "kinds",
        "completed",
        "over_cap",
        "error_op",
        "error_errno",
        "refusal",
        "additions",
        "removals",
        "charged",
        "role",
    )

    def __init__(self, dir_node, cap, role):
        self.dir_node = dir_node
        self.cap = cap
        self.names = []
        self.stamps = {}
        self.kinds = {}
        self.completed = False
        self.over_cap = False
        self.error_op = None
        self.error_errno = None
        self.refusal = None
        self.additions = set()
        self.removals = set()
        self.charged = 0
        self.role = role


class _InstallRec:
    __slots__ = (
        "phase",
        "failed",
        "relative_name",
        "payload",
        "temp_name",
        "temp_fd",
        "temp_node",
        "parent_node",
        "target_node",
        "written",
        "link_succeeded",
        "cleaned",
        "temp_owned",
        "unlink_attempted",
        "final_stamp",
        "family",
        "parsed",
    )

    def __init__(self):
        self.phase = "idle"
        self.failed = False
        self.relative_name = None
        self.payload = None
        self.temp_name = None
        self.temp_fd = None
        self.temp_node = None
        self.parent_node = None
        self.target_node = None
        self.written = 0
        self.link_succeeded = False
        self.cleaned = False
        self.temp_owned = False
        self.unlink_attempted = False
        self.final_stamp = None
        self.family = None
        self.parsed = None

    def reset(self):
        self.phase = "idle"
        self.failed = False
        self.relative_name = None
        self.payload = None
        self.temp_name = None
        self.temp_fd = None
        self.temp_node = None
        self.parent_node = None
        self.target_node = None
        self.written = 0
        self.link_succeeded = False
        self.cleaned = False
        self.temp_owned = False
        self.unlink_attempted = False
        self.final_stamp = None
        self.family = None
        self.parsed = None


class _FdRec:
    __slots__ = ("fd", "lock_dup", "closed")

    def __init__(self, fd, lock_dup=False):
        self.fd = fd
        self.lock_dup = lock_dup
        self.closed = False


class _CodeSession:
    def __init__(self, batch_id):
        self._batch_id = batch_id
        self._lifetime = "setup"
        self._phase = "setup"
        self._nodes = {}
        self._fds = []
        self._scans = []
        self._install = _InstallRec()
        self._limits = dict(_HARD_OUTPUT_LIMITS)
        self._limits_set = False
        self._context = None
        self._plan = None
        self._resource_recs = []
        self._resource_bytes = None
        self._initial_snapshot = {}
        self._output_bytes = {}
        self._checkout = None
        self._cwd = None
        self._lock_dup = None
        self._input_used = False
        self._input_node = None
        self._bundle_used = False
        self._bodies_used = False
        self._bundle_root = None
        self._bundle_objects = None
        self._bundle_manifest = None
        self._bundle_body_bytes = None
        self._bundle_rel = None
        self._git_limits = None
        self._group_reached = set()
        self._logical_c = 0
        self._work_node = None
        self._batch_node = None
        self._ns_node = None
        self._family_nodes = {}
        self._output_file_nodes = {}
        self._slot_nodes = {}
        self._git_node = None
        self._pyproject_node = None
        self._root = None
        self._group_fail = {}
        self._scan_by_role = {}
        self._object_scan_charged = 0
        self._config_count = 0
        self._handoff_count = 0
        self._object_count = 0

    def __enter__(self):
        try:
            self._setup()
            self._lifetime = "active"
            self._phase = "idle"
            return self
        except BaseException as exc:
            selected = self._finalize(exc)
            if selected is exc:
                raise
            if selected is not None:
                raise selected from None
            raise

    def __exit__(self, exc_type, exc, traceback):
        selected = self._finalize(exc)
        if selected is None or selected is exc:
            return False
        raise selected from None

    def _require_active(self):
        if self._lifetime != "active":
            raise RuntimeError("CODE session is not active") from None

    def _reject_inflight(self):
        inst = self._install
        if inst.failed or inst.phase != "idle":
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=inst.phase,
                group="installation",
                reason="phase_mismatch",
            )

    def snapshot(self):
        self._require_active()
        self._reject_inflight()
        self._full_verify()
        out = {}
        for name in sorted(self._output_bytes):
            out[name] = self._output_bytes[name]
        return out

    def layout_state(self):
        self._require_active()
        self._reject_inflight()
        self._nameset_verify()
        initial_ns = self._ns_node is not None and self._ns_node.first_kind == "dir"
        current_ns = self._dir_currently_present(self._ns_node)
        initial_families = {}
        current_families = {}
        for name in ("objects", "configs", "handoffs"):
            node = self._family_nodes.get(name)
            initial_families[name] = node is not None and node.first_kind == "dir"
            current_families[name] = self._dir_currently_present(node)
        initial_files = []
        for name in sorted(self._initial_snapshot):
            initial_files.append(name)
        current_files = []
        current_file_bytes = {}
        for name in sorted(self._output_bytes):
            current_files.append(name)
            current_file_bytes[name] = len(self._output_bytes[name])
        return {
            "initial_namespace_present": initial_ns,
            "current_namespace_present": current_ns,
            "initial_families": initial_families,
            "current_families": current_families,
            "initial_files": initial_files,
            "current_files": current_files,
            "current_file_bytes": current_file_bytes,
        }

    def retain_input(self, path, *, maximum):
        self._require_active()
        self._reject_inflight()
        self._phase = "retaining"
        self._mark("metadata")
        if type(path) is not str:
            _raise_struct("type")
        if type(maximum) is not int or maximum not in (
            _MAX_REQUEST_INPUT_BYTES,
            _MAX_OBSERVE_INPUT_BYTES,
        ):
            _raise_struct("limits")
        if self._input_used:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="metadata",
                reason="phase_mismatch",
            )
        self._input_used = True
        if not _canonical_abs(path) and not _canonical_rel(path):
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="metadata",
                reason="path_spelling",
            )
        if _canonical_abs(path):
            abs_path = path
            components = _split_abs(path)
            start = self._root
        else:
            abs_path = _join_abs(self._cwd, *path.split("/"))
            components = path.split("/")
            start = self._checkout
        if _paths_overlap(abs_path, self._output_abs):
            node = self._walk(
                start,
                components,
                role="metadata",
                group="metadata",
                missing_ok=False,
                open_dirs=True,
                leaf="file",
                policy="resource",
            )
            self._input_node = node
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="metadata",
                reason="overlap",
            )
        node = self._walk(
            start,
            components,
            role="metadata",
            group="metadata",
            missing_ok=False,
            open_dirs=True,
            leaf="file",
            policy="resource",
        )
        self._input_node = node
        self._reject_alias(node, "metadata")
        limit_name = (
            "max_request_input_bytes"
            if maximum == _MAX_REQUEST_INPUT_BYTES
            else "max_observe_input_bytes"
        )
        self._read_node(
            node,
            maximum,
            group="metadata",
            limit_pointer="/input",
            limit_name=limit_name,
        )
        return node.bytes

    def retain_bundle_manifest(self, relative_directory):
        self._require_active()
        self._reject_inflight()
        self._phase = "retaining"
        self._mark("bundle")
        if type(relative_directory) is not str:
            _raise_struct("type")
        if self._bundle_used:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="phase_mismatch",
            )
        self._bundle_used = True
        self._validate_bundle_spelling(relative_directory)
        if _paths_overlap(relative_directory, self._output_rel):
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="overlap",
            )
        parts = relative_directory.split("/")
        root = self._walk(
            self._checkout,
            parts,
            role="bundle_root",
            group="bundle",
            missing_ok=False,
            open_dirs=True,
            leaf="dir",
            policy=None,
        )
        self._bundle_root = root
        self._bundle_rel = relative_directory
        self._reject_alias(root, "bundle")
        self._scan_bundle_root(root)
        objects = self._child(
            root,
            "objects",
            role="bundle_objects",
            group="bundle",
            missing_ok=False,
            open_dir=True,
            dir_mode=None,
        )
        self._bundle_objects = objects
        if objects.first_kind != "dir":
            self._unsafe_node(objects, "bundle")
        self._scan_bundle_objects(objects)
        manifest = self._child(
            root,
            "manifest.json",
            role="bundle_manifest",
            group="bundle",
            missing_ok=False,
            open_file=True,
            policy="resource",
        )
        self._bundle_manifest = manifest
        cap = self._limits["max_bundle_bytes"]
        self._read_node(
            manifest,
            cap,
            group="bundle",
            limit_pointer="/bundle",
            limit_name="max_bundle_bytes",
        )
        return manifest.bytes

    def retain_bundle_bodies(self, *, object_format, objects, limits):
        self._require_active()
        self._reject_inflight()
        self._phase = "retaining"
        self._mark("bundle")
        if self._bundle_root is None or self._bundle_manifest is None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="phase_mismatch",
            )
        if self._bodies_used:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="phase_mismatch",
            )
        self._bodies_used = True
        if type(object_format) is not str:
            _raise_struct("type")
        if object_format != "sha1" and object_format != "sha256":
            _raise_struct("shape")
        if type(objects) is not list:
            _raise_struct("type")
        parsed_limits = _parse_closed_limits(limits, _GIT_LIMIT_KEYS, _GIT_LIMIT_MAX)
        self._git_limits = parsed_limits
        width = 40 if object_format == "sha1" else 64
        records = []
        prev = None
        for index in range(len(objects)):
            rec = objects[index]
            parsed = self._parse_object_record(rec, width)
            oid = parsed["oid"]
            if prev is not None and not (oid > prev):
                _raise_struct("shape")
            prev = oid
            records.append(parsed)
        selected_max = parsed_limits["max_objects"]
        if len(records) > selected_max:
            _raise_limit("/objects", "max_objects", selected_max, len(records))
        for index, rec in enumerate(records):
            size = rec["body_size_bytes"]
            cap = parsed_limits["max_object_bytes"]
            if size > cap:
                _raise_limit(
                    "/objects/%d/body_size_bytes" % index,
                    "max_object_bytes",
                    cap,
                    size,
                )
        total_declared = 0
        for rec in records:
            total_declared += rec["body_size_bytes"]
            if total_declared > parsed_limits["max_total_object_bytes"]:
                _raise_limit(
                    "/objects",
                    "max_total_object_bytes",
                    parsed_limits["max_total_object_bytes"],
                    total_declared,
                )
        self._verify_bundle_nameset()
        scan = self._scan_by_role.get("bundle_objects")
        if scan is None or not scan.completed or scan.refusal is not None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="set_changed",
            )
        physical = []
        for name in scan.names:
            physical.append(name[:-5])
        if len(physical) > selected_max:
            _raise_limit("/bodies", "max_objects", selected_max, len(physical))
        for oid in physical:
            if len(oid) != width:
                _raise_git(
                    CODE_PROOF_INPUT_INVALID,
                    "code git proof input is invalid",
                    {"instance_pointer": "/bodies", "reason": "invalid_oid_key"},
                )
        declared = []
        declared_set = set()
        for rec in records:
            declared.append(rec["oid"])
            declared_set.add(rec["oid"])
        extra = []
        physical_set = set(physical)
        for oid in physical:
            if oid not in declared_set:
                extra.append(oid)
        if extra:
            extra.sort()
            _raise_git(
                CODE_PROOF_OBJECT_EXTRA,
                "undeclared git object bodies were supplied",
                {"instance_pointer": "/bodies", "extra_oids": extra},
            )
        missing = []
        for oid in declared:
            if oid not in physical_set:
                missing.append(oid)
        if missing:
            missing.sort()
            _raise_git(
                CODE_PROOF_OBJECT_UNAVAILABLE,
                "required git object is unavailable",
                {"instance_pointer": "/bodies", "missing_oids": missing},
            )
        out = {}
        total = 0
        for rec in records:
            oid = rec["oid"]
            name = oid + ".body"
            node = self._child(
                self._bundle_objects,
                name,
                role="bundle_body",
                group="bundle",
                missing_ok=False,
                open_file=True,
                policy="resource",
            )
            node.rel = name
            self._read_node(
                node,
                parsed_limits["max_object_bytes"],
                group="bundle",
                limit_pointer="/objects",
                limit_name="max_object_bytes",
            )
            total += len(node.bytes)
            if total > parsed_limits["max_total_object_bytes"]:
                _raise_limit(
                    "/objects",
                    "max_total_object_bytes",
                    parsed_limits["max_total_object_bytes"],
                    total,
                )
            out[oid] = node.bytes
        self._bundle_body_bytes = dict(out)
        return dict(out)

    def set_output_limits(self, limits):
        self._require_active()
        self._reject_inflight()
        if self._limits_set:
            raise RuntimeError("CODE output limits are already set") from None
        parsed = _parse_closed_limits(limits, _OUTPUT_LIMIT_KEYS, _OUTPUT_LIMIT_MAX)
        for name in sorted(self._output_bytes):
            cap, key = _cap_for_rel(name, parsed)
            observed = len(self._output_bytes[name])
            if observed > cap:
                _raise_limit("/output", key, cap, observed)
        if self._logical_c > parsed["max_output_peak_bytes"]:
            _raise_limit(
                "/output",
                "max_output_peak_bytes",
                parsed["max_output_peak_bytes"],
                self._logical_c,
            )
        if self._bundle_manifest is not None and self._bundle_manifest.bytes is not None:
            observed = len(self._bundle_manifest.bytes)
            cap = parsed["max_bundle_bytes"]
            if observed > cap:
                _raise_limit("/bundle", "max_bundle_bytes", cap, observed)
        self._limits = parsed
        self._limits_set = True

    def install(self, relative_name, payload):
        self._require_active()
        inst = self._install
        if inst.failed or inst.phase != "idle":
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=inst.phase,
                group="installation",
                reason="phase_mismatch",
            )
        if not self._limits_set:
            raise RuntimeError("CODE output limits are not set") from None
        if type(relative_name) is not str:
            _raise_struct("type")
        if type(payload) is not bytes:
            _raise_struct("type")
        parsed = _parse_output_name(relative_name)
        if parsed is None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="idle",
                group="installation",
                reason="path_spelling",
            )
        cap, key = _cap_for_rel(relative_name, self._limits)
        pointer = _pointer_for_rel(relative_name)
        if len(payload) > cap:
            _raise_limit(pointer, key, cap, len(payload))
        if relative_name in self._initial_snapshot:
            if self._initial_snapshot[relative_name] == payload:
                self._full_verify()
                return True
            _raise_conflict(pointer, "artifact_changed")
        if relative_name in self._output_bytes:
            _raise_conflict(pointer, "artifact_changed")
        nbytes = len(payload)
        peak = self._limits["max_output_peak_bytes"]
        projected = self._logical_c + 2 * nbytes
        if projected > peak:
            _raise_limit("/output", "max_output_peak_bytes", peak, projected)
        if parsed[0] == "family":
            family = parsed[1]
            if family == "objects" and self._object_count >= _MAX_OBJECTS:
                _raise_limit("/objects", "max_objects", _MAX_OBJECTS, self._object_count + 1)
            if family == "configs" and self._config_count >= _MAX_CONFIGS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="idle",
                    group="output_layout",
                    reason="unknown_entry",
                )
            if family == "handoffs" and self._handoff_count >= _MAX_HANDOFFS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="idle",
                    group="output_layout",
                    reason="unknown_entry",
                )
            if family == "objects":
                extra = self._object_scan_charged + nbytes
                if extra > _MAX_TOTAL_OBJECT_BYTES:
                    _raise_limit(
                        "/objects",
                        "max_total_object_bytes",
                        _MAX_TOTAL_OBJECT_BYTES,
                        extra,
                    )
        inst.reset()
        inst.relative_name = relative_name
        inst.payload = payload
        inst.parsed = parsed
        inst.family = parsed[1] if parsed[0] == "family" else None
        try:
            self._full_verify()
            self._ensure_output_dirs(inst.family)
            parent = self._ns_node if inst.family is None else self._family_nodes[inst.family]
            inst.parent_node = parent
            self._assert_target_absent(parent, parsed)
            self._create_temp(parent, payload)
            self._write_temp(payload)
            self._finish_temp_ready(payload)
            self._link_final(parent, parsed, payload)
            self._unlink_temp(parent, parsed, payload)
            self._durable_finish(parent, parsed, payload)
        except BaseException:
            inst.failed = True
            raise
        inst.reset()
        inst.phase = "idle"
        return False

    def verify(self):
        self._require_active()
        self._reject_inflight()
        self._full_verify()

    def validate_structure(self, title, instance):
        self._require_active()
        self._context.validate_structure(title, instance)

    def materialize_limits(self, value):
        self._require_active()
        return self._context.materialize_limits(value)

    @property
    def profile_sha256(self):
        self._require_active()
        return self._context.profile_sha256

    def _mark(self, group):
        if group is not None:
            self._group_reached.add(group)

    def _setup(self):
        self._lifetime = "setup"
        self._phase = "setup"
        if not _capability_snapshot():
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="setup",
                group=None,
                reason="unavailable_primitive",
            )
        self._validate_batch()
        self._retain_checkout()
        self._lock_checkout()
        self._fsync_checkout()
        self._retain_markers()
        self._retain_resources()
        self._phase = "scan"
        self._scan_output()
        self._full_verify()

    def _validate_batch(self):
        batch = self._batch_id
        if type(batch) is not str or _BATCH_RE.fullmatch(batch) is None:
            _raise_io(
                INVALID_BATCH_ID,
                phase="setup",
                group=None,
                reason="batch_id",
            )

    def _retain_checkout(self):
        self._mark("checkout")
        self._mark("ancestors")
        try:
            cwd = _getcwd()
        except OSError as exc:
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase="setup",
                group="checkout",
                reason="syscall_failed",
                errno=_bound_errno(exc),
            )
        if type(cwd) is not str or not _canonical_abs(cwd):
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="path_spelling",
            )
        self._cwd = cwd
        self._output_rel = _join_abs(_WORK_NAME, self._batch_id, _NS_NAME)[1:] if False else (
            _WORK_NAME + "/" + self._batch_id + "/" + _NS_NAME
        )
        self._output_abs = _join_abs(cwd, _WORK_NAME, self._batch_id, _NS_NAME)
        self._root = self._open_root()
        parts = _split_abs(cwd)
        self._checkout = self._walk(
            self._root,
            parts,
            role="checkout",
            group="checkout",
            missing_ok=False,
            open_dirs=True,
            leaf="dir",
            policy=None,
        )
        self._checkout.group = "checkout"

    def _open_root(self):
        node = _Node(None, "/", "/", "root", "ancestors")
        self._nodes["/"] = node
        node.observed = True
        try:
            st = _stat("/", follow_symlinks=False)
        except OSError as exc:
            node.first_kind = "stat_error"
            node.first_error_op = "stat"
            node.first_error_errno = _bound_errno(exc)
            raise _err_os("setup", "ancestors", "stat", exc) from None
        stamp = _dir_stamp(st)
        if stamp is None or _dir_reason(st) is not None:
            node.first_kind = "other"
            node.first_named_stamp = stamp
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="setup",
                group="ancestors",
                reason="unsafe_type" if stamp is not None else "edge_changed",
                operation="stat",
            )
        node.first_kind = "dir"
        node.first_named_stamp = stamp
        try:
            fd = _open("/", _dir_flags())
        except OSError as exc:
            raise _err_os("setup", "ancestors", "open", exc) from None
        self._register_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            raise _err_os("setup", "ancestors", "fstat", exc) from None
        fstamp = _dir_stamp(fst)
        if fstamp != stamp:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="setup",
                group="ancestors",
                reason="edge_changed",
                operation="fstat",
            )
        node.first_fd_stamp = fstamp
        node.dev_ino = _identity(fst)
        return node

    def _lock_checkout(self):
        fd = self._checkout.fd
        try:
            _flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            en = _bound_errno(exc)
            if en in _BUSY_ERRNOS:
                _raise_io(
                    CODE_PROOF_BUSY,
                    phase="setup",
                    group="checkout",
                    reason="lock_busy",
                    operation="flock",
                    errno=en,
                )
            if en in _UNSUP_ERRNOS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="setup",
                    group="checkout",
                    reason="unavailable_primitive",
                    operation="flock",
                    errno=en,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase="setup",
                group="checkout",
                reason="syscall_failed",
                operation="flock",
                errno=en,
            )
        try:
            dup = _dup(fd)
        except OSError as exc:
            raise _err_os("setup", "checkout", "dup", exc) from None
        rec = _FdRec(dup, lock_dup=True)
        self._fds.append(rec)
        self._lock_dup = rec

    def _fsync_checkout(self):
        try:
            _fsync(self._checkout.fd)
        except OSError as exc:
            en = _bound_errno(exc)
            if en in _UNSUP_ERRNOS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="setup",
                    group="checkout",
                    reason="unavailable_primitive",
                    operation="fsync",
                    errno=en,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase="setup",
                group="checkout",
                reason="syscall_failed",
                operation="fsync",
                errno=en,
            )

    def _retain_markers(self):
        git = self._child(
            self._checkout,
            ".git",
            role="git_marker",
            group="checkout",
            missing_ok=False,
            open_dir=False,
            open_file=False,
            workspace=True,
        )
        self._git_node = git
        if git.first_kind == "dir":
            reason = _dir_reason(self._stat_obj_from_stamp(git, directory=True))
            if reason is not None:
                _raise_io(
                    WORKSPACE_ROOT_INVALID,
                    phase="setup",
                    group="checkout",
                    reason=reason,
                    operation="stat",
                )
            self._open_dir_node(git, exact_mode=None, group="checkout", workspace=True)
        elif git.first_kind == "file":
            st_mode = git.first_named_stamp[2]
            fake = _StampView(git.first_named_stamp, directory=False)
            reason = _file_reason(fake, resource_policy=True)
            if reason is not None:
                _raise_io(
                    WORKSPACE_ROOT_INVALID,
                    phase="setup",
                    group="checkout",
                    reason=reason,
                    operation="stat",
                )
            if git.first_named_stamp[3] > _MAX_GIT_MARKER_BYTES:
                _raise_io(
                    WORKSPACE_ROOT_INVALID,
                    phase="setup",
                    group="checkout",
                    reason="marker_invalid",
                    operation="stat",
                )
            self._open_file_node(git, policy="resource", group="checkout", workspace=True)
        else:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="unsafe_type" if git.first_kind != "absent" else "missing",
                operation="stat",
            )
        pyproject = self._child(
            self._checkout,
            "pyproject.toml",
            role="pyproject",
            group="checkout",
            missing_ok=False,
            open_file=True,
            policy="resource",
            workspace=True,
        )
        self._pyproject_node = pyproject
        self._read_node(
            pyproject,
            _MAX_PYPROJECT_BYTES,
            group="checkout",
            workspace=True,
        )
        try:
            text = pyproject.bytes.decode("utf-8")
            parsed = tomllib.loads(text)
        except Exception:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            )
        if type(parsed) is not dict or "project" not in parsed:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            )
        project = parsed["project"]
        if type(project) is not dict or "name" not in project:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            )
        if project["name"] != "video-paper-wiki":
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            )

    def _retain_resources(self):
        self._mark("resources")
        try:
            plan = resource_origin_plan()
        except CodeProofResourceError as exc:
            reason = _resource_reason(exc, "resource_origin")
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason=reason,
            )
        except Exception:
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        self._plan = plan
        pins = self._plan_pins(plan)
        self._check_resource_overlap(pins)
        retained = {}
        for logical, abs_path, size, sha256 in pins:
            parts = _split_abs(abs_path)
            node = self._walk(
                self._root,
                parts,
                role="resource",
                group="resources",
                missing_ok=True,
                open_dirs=True,
                leaf="file",
                policy="resource",
            )
            node.logical = logical
            node.pin_size = size
            node.pin_sha256 = sha256
            rec = node
            self._resource_recs.append(rec)
            if node.first_kind == "absent":
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason="missing",
                    operation="stat",
                )
            if node.first_kind != "file":
                self._resource_unsafe(node)
            reason = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                resource_policy=True,
            )
            if reason is not None:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason=reason,
                    operation="stat",
                )
            if node.fd is None:
                self._open_file_node(node, policy="resource", group="resources")
            if node.first_named_stamp[3] != size:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason="resource_hash",
                )
            self._read_node(node, size, group="resources", resource=True)
            digest = hashlib.sha256(node.bytes).hexdigest()
            if digest != sha256:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason="resource_hash",
                )
            retained[logical] = node.bytes
        try:
            context = compile_code_proof_resources(dict(retained))
        except CodeProofResourceError as exc:
            reason = _resource_reason(exc, "resource_shape")
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason=reason,
            )
        self._context = context
        self._resource_bytes = dict(retained)

    def _plan_pins(self, plan):
        layout = _safe_attr(plan, "layout")
        schemas = _safe_attr(plan, "schemas_directory")
        profiles = _safe_attr(plan, "profiles_directory")
        resources = _safe_attr(plan, "resources")
        if layout not in ("source", "installed"):
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        if type(schemas) is not str or type(profiles) is not str:
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        if not _canonical_abs(schemas) or not _canonical_abs(profiles):
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        try:
            pins = list(resources)
        except Exception:
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        if len(pins) != 11:
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
        out = []
        for pin in pins:
            rel = _safe_attr(pin, "relative_path")
            size = _safe_attr(pin, "size_bytes")
            sha256 = _safe_attr(pin, "sha256")
            if type(rel) is not str or type(size) is not int or type(sha256) is not str:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason="resource_origin",
                )
            filename = rel.rsplit("/", 1)[-1]
            if rel.startswith("schemas/"):
                base = schemas
            elif rel.startswith("profiles/"):
                base = profiles
            else:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase="setup",
                    group="resources",
                    reason="resource_origin",
                )
            out.append((rel, _join_abs(base, filename), size, sha256))
        return out

    def _check_resource_overlap(self, pins):
        scoped = set()
        plan = self._plan
        for directory in (plan.schemas_directory, plan.profiles_directory):
            if _paths_overlap(directory, self._output_abs):
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="setup",
                    group="resources",
                    reason="overlap",
                )
            scoped.add(directory)
        for _logical, abs_path, _size, _sha in pins:
            if _paths_overlap(abs_path, self._output_abs):
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="setup",
                    group="resources",
                    reason="overlap",
                )

    def _scan_output(self):
        self._mark("output_layout")
        self._mark("output_files")
        work = self._child(
            self._checkout,
            _WORK_NAME,
            role="work",
            group="output_layout",
            missing_ok=True,
            open_dir=True,
            dir_mode=None,
        )
        self._work_node = work
        if work.first_kind == "absent":
            self._initial_snapshot = {}
            return
        if work.first_kind != "dir":
            self._unsafe_node(work, "output_layout")
        batch = self._child(
            work,
            self._batch_id,
            role="batch",
            group="output_layout",
            missing_ok=True,
            open_dir=True,
            dir_mode=None,
        )
        self._batch_node = batch
        if batch.first_kind == "absent":
            self._initial_snapshot = {}
            return
        if batch.first_kind != "dir":
            self._unsafe_node(batch, "output_layout")
        ns = self._child(
            batch,
            _NS_NAME,
            role="namespace",
            group="output_layout",
            missing_ok=True,
            open_dir=True,
            dir_mode=0o700,
        )
        self._ns_node = ns
        if ns.first_kind == "absent":
            self._initial_snapshot = {}
            return
        if ns.first_kind != "dir":
            self._unsafe_node(ns, "output_layout")
        self._scan_namespace(ns)

    def _scan_namespace(self, ns):
        scan = self._bounded_scan(ns, _MAX_NAMESPACE_ENTRIES, "namespace")
        charged = 0
        files = {}
        for name in scan.names:
            st_stamp = scan.stamps[name]
            kind = scan.kinds[name]
            if kind == "file":
                size = st_stamp[3]
                charged += size
                if charged > self._limits["max_output_peak_bytes"]:
                    scan.refusal = _limit_error(
                        "/output",
                        "max_output_peak_bytes",
                        self._limits["max_output_peak_bytes"],
                        charged,
                    )
                    self._raise_scan(scan)
                if name not in _DIRECT_FILES:
                    scan.refusal = _io_error(
                        WORK_PATH_UNSAFE,
                        phase="scan",
                        group="output_layout",
                        reason="unknown_entry",
                    )
                    self._raise_scan(scan)
                reason = _file_reason(
                    _StampView(st_stamp, directory=False),
                    exact_mode=0o600,
                )
                if reason is not None:
                    scan.refusal = _io_error(
                        WORK_PATH_UNSAFE,
                        phase="scan",
                        group="output_files",
                        reason=reason,
                        operation="stat",
                    )
                    self._raise_scan(scan)
                cap, key = _cap_for_rel(name, self._limits)
                if size > cap:
                    scan.refusal = _limit_error("/output", key, cap, size)
                    self._raise_scan(scan)
                files[name] = st_stamp
            elif kind == "dir":
                if name not in _FAMILY_NAMES:
                    scan.refusal = _io_error(
                        WORK_PATH_UNSAFE,
                        phase="scan",
                        group="output_layout",
                        reason="unknown_entry",
                    )
                    self._raise_scan(scan)
                reason = _dir_reason(_StampView(st_stamp, directory=True), exact_mode=0o700)
                if reason is not None:
                    scan.refusal = _io_error(
                        WORK_PATH_UNSAFE,
                        phase="scan",
                        group="output_layout",
                        reason=reason,
                        operation="stat",
                    )
                    self._raise_scan(scan)
            else:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="scan",
                    group="output_layout",
                    reason="unsafe_type",
                    operation="stat",
                )
                self._raise_scan(scan)
        if scan.over_cap or not scan.completed:
            if scan.refusal is None:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="scan",
                    group="output_layout",
                    reason="unknown_entry",
                )
            self._raise_scan(scan)
        for name in _DIRECT_NAMES:
            node = self._child(
                ns,
                name,
                role="output_file",
                group="output_files",
                missing_ok=True,
                open_file=name in files,
                policy="output",
            )
            node.rel = name
            self._slot_nodes[name] = node
            if name in files:
                if node.first_kind != "file":
                    self._unsafe_node(node, "output_files")
                self._read_node(
                    node,
                    self._limits[_DIRECT_LIMIT_NAME[name]],
                    group="output_files",
                    limit_pointer="/output",
                    limit_name=_DIRECT_LIMIT_NAME[name],
                )
                self._output_file_nodes[name] = node
                self._output_bytes[name] = node.bytes
                self._initial_snapshot[name] = node.bytes
                self._logical_c += len(node.bytes)
        for family in _FAMILY_NAMES:
            node = self._child(
                ns,
                family,
                role="family",
                group="output_layout",
                missing_ok=True,
                open_dir=family in scan.kinds and scan.kinds[family] == "dir",
                dir_mode=0o700,
            )
            self._family_nodes[family] = node
            if node.first_kind == "dir":
                self._scan_family(node, family)
        scan.charged = charged

    def _scan_family(self, node, family):
        if family == "objects":
            cap = _MAX_OBJECTS
        else:
            cap = _MAX_CONFIGS if family == "configs" else _MAX_HANDOFFS
        scan = self._bounded_scan(node, cap, "family:" + family)
        charged = 0
        count = 0
        for name in scan.names:
            st_stamp = scan.stamps[name]
            kind = scan.kinds[name]
            if kind != "file":
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="scan",
                    group="output_layout",
                    reason="unsafe_type",
                    operation="stat",
                )
                self._raise_scan(scan)
            size = st_stamp[3]
            charged += size
            self._logical_c += size
            if self._logical_c > self._limits["max_output_peak_bytes"]:
                scan.refusal = _limit_error(
                    "/output",
                    "max_output_peak_bytes",
                    self._limits["max_output_peak_bytes"],
                    self._logical_c,
                )
                self._raise_scan(scan)
            if _family_member(family, name) is None:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="scan",
                    group="output_layout",
                    reason="unknown_entry",
                )
                self._raise_scan(scan)
            reason = _file_reason(_StampView(st_stamp, directory=False), exact_mode=0o600)
            if reason is not None:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="scan",
                    group="output_files",
                    reason=reason,
                    operation="stat",
                )
                self._raise_scan(scan)
            rel = family + "/" + name
            cap_bytes, key = _cap_for_rel(rel, self._limits)
            if size > cap_bytes:
                scan.refusal = _limit_error("/output", key, cap_bytes, size)
                self._raise_scan(scan)
            if family == "objects":
                if charged > _MAX_TOTAL_OBJECT_BYTES:
                    scan.refusal = _limit_error(
                        "/objects",
                        "max_total_object_bytes",
                        _MAX_TOTAL_OBJECT_BYTES,
                        charged,
                    )
                    self._raise_scan(scan)
            count += 1
            child = self._child(
                node,
                name,
                role="output_file",
                group="output_files",
                missing_ok=False,
                open_file=True,
                policy="output",
            )
            child.rel = rel
            self._read_node(
                child,
                cap_bytes,
                group="output_files",
                limit_pointer="/output",
                limit_name=key,
            )
            self._output_file_nodes[rel] = child
            self._output_bytes[rel] = child.bytes
            self._initial_snapshot[rel] = child.bytes
        if scan.over_cap or not scan.completed:
            if scan.refusal is None:
                if family == "objects":
                    scan.refusal = _limit_error(
                        "/objects",
                        "max_objects",
                        _MAX_OBJECTS,
                        cap + 1,
                    )
                else:
                    scan.refusal = _io_error(
                        WORK_PATH_UNSAFE,
                        phase="scan",
                        group="output_layout",
                        reason="unknown_entry",
                    )
            self._raise_scan(scan)
        if family == "objects":
            self._object_count = count
            self._object_scan_charged = charged
        elif family == "configs":
            self._config_count = count
        else:
            self._handoff_count = count

    def _scan_bundle_root(self, root):
        scan = self._bounded_scan(root, _MAX_BUNDLE_ROOT_ENTRIES, "bundle_root")
        names = set(scan.names)
        if scan.over_cap or not scan.completed:
            scan.refusal = _io_error(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="unknown_entry",
            )
            self._raise_scan(scan)
        if names != {"manifest.json", "objects"}:
            extra = names - {"manifest.json", "objects"}
            reason = "unknown_entry" if extra else "missing"
            scan.refusal = _io_error(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason=reason,
            )
            self._raise_scan(scan)
        if scan.kinds.get("objects") != "dir":
            scan.refusal = _io_error(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="unsafe_type",
                operation="stat",
            )
            self._raise_scan(scan)
        if scan.kinds.get("manifest.json") != "file":
            scan.refusal = _io_error(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="unsafe_type",
                operation="stat",
            )
            self._raise_scan(scan)

    def _scan_bundle_objects(self, objects):
        scan = self._bounded_scan(objects, _MAX_OBJECTS, "bundle_objects")
        charged = 0
        if scan.over_cap:
            scan.refusal = _limit_error(
                "/objects", "max_objects", _MAX_OBJECTS, _MAX_OBJECTS + 1
            )
            self._raise_scan(scan)
        if not scan.completed:
            if scan.refusal is None:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="retaining",
                    group="bundle",
                    reason="syscall_failed",
                    operation=scan.error_op,
                    errno=scan.error_errno,
                )
            self._raise_scan(scan)
        for name in scan.names:
            kind = scan.kinds[name]
            st_stamp = scan.stamps[name]
            if kind != "file" or _family_member("objects", name) is None:
                reason = "unknown_entry" if kind == "file" else "unsafe_type"
                if kind == "file" and _family_member("objects", name) is None:
                    reason = "unknown_entry"
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="retaining",
                    group="bundle",
                    reason=reason,
                    operation="stat",
                )
                self._raise_scan(scan)
            reason = _file_reason(_StampView(st_stamp, directory=False), resource_policy=True)
            if reason is not None:
                scan.refusal = _io_error(
                    WORK_PATH_UNSAFE,
                    phase="retaining",
                    group="bundle",
                    reason=reason,
                    operation="stat",
                )
                self._raise_scan(scan)
            size = st_stamp[3]
            if size > _MAX_OBJECT_BYTES:
                scan.refusal = _limit_error(
                    "/objects", "max_object_bytes", _MAX_OBJECT_BYTES, size
                )
                self._raise_scan(scan)
            charged += size
            if charged > _MAX_TOTAL_OBJECT_BYTES:
                scan.refusal = _limit_error(
                    "/objects",
                    "max_total_object_bytes",
                    _MAX_TOTAL_OBJECT_BYTES,
                    charged,
                )
                self._raise_scan(scan)
            self._child(
                objects,
                name,
                role="bundle_body_edge",
                group="bundle",
                missing_ok=False,
                open_file=False,
                policy="resource",
            )
        if len(scan.names) > _MAX_OBJECTS:
            scan.refusal = _limit_error(
                "/objects", "max_objects", _MAX_OBJECTS, len(scan.names)
            )
            self._raise_scan(scan)

    def _raise_scan(self, scan):
        if scan.refusal is not None:
            raise scan.refusal from None
        _raise_io(
            WORK_PATH_UNSAFE,
            phase=self._phase,
            group="output_layout",
            reason="unknown_entry",
        )

    def _bounded_scan(self, dir_node, cap, role):
        scan = _Scan(dir_node, cap, role)
        self._scans.append(scan)
        self._scan_by_role[role] = scan
        allow = 0
        inst = self._install
        if (
            inst.temp_owned
            and inst.parent_node is dir_node
            and inst.phase in _TEMP_READY_PHASES
        ):
            allow = 1
        keep = cap + allow + 1
        try:
            iterator_cm = _scandir(dir_node.fd)
        except OSError as exc:
            scan.error_op = "scandir"
            scan.error_errno = _bound_errno(exc)
            scan.refusal = _err_os(self._phase, dir_node.group, "scandir", exc)
            return scan
        counted = 0
        try:
            with iterator_cm as iterator:
                for entry in iterator:
                    counted += 1
                    if counted > keep:
                        scan.over_cap = True
                        break
                    name = entry.name
                    if type(name) is not str:
                        scan.refusal = _io_error(
                            WORK_PATH_UNSAFE,
                            phase=self._phase,
                            group=dir_node.group,
                            reason="unknown_entry",
                        )
                        break
                    try:
                        st = _stat(name, dir_fd=dir_node.fd, follow_symlinks=False)
                    except OSError as exc:
                        scan.error_op = "stat"
                        scan.error_errno = _bound_errno(exc)
                        scan.refusal = _err_os(self._phase, dir_node.group, "stat", exc)
                        break
                    if _is_dir(st):
                        stamp = _dir_stamp(st)
                        kind = "dir"
                    elif _is_reg(st):
                        stamp = _file_stamp(st)
                        kind = "file"
                    else:
                        stamp = _file_stamp(st) or _dir_stamp(st)
                        kind = "other"
                    if stamp is None:
                        scan.refusal = _io_error(
                            WORK_PATH_UNSAFE,
                            phase=self._phase,
                            group=dir_node.group,
                            reason="edge_changed",
                            operation="stat",
                        )
                        break
                    scan.names.append(name)
                    scan.stamps[name] = stamp
                    scan.kinds[name] = kind
                    if counted > cap + allow:
                        scan.over_cap = True
                        break
        except OSError as exc:
            scan.error_op = "scandir"
            scan.error_errno = _bound_errno(exc)
            scan.refusal = _err_os(self._phase, dir_node.group, "scandir", exc)
            return scan
        if scan.refusal is None and scan.error_op is None and not scan.over_cap:
            scan.completed = True
        return scan

    def _walk(
        self,
        start,
        components,
        *,
        role,
        group,
        missing_ok,
        open_dirs,
        leaf,
        policy,
        workspace=False,
    ):
        node = start
        last = len(components) - 1
        for index, name in enumerate(components):
            is_leaf = index == last
            child_role = role if is_leaf else "ancestor"
            child_group = group if is_leaf else (
                "ancestors" if group != "checkout" or not is_leaf else "ancestors"
            )
            if not is_leaf:
                child_group = "ancestors" if start is self._root else group
                if role in ("checkout", "git_marker", "pyproject") and node is self._root:
                    child_group = "ancestors"
            node = self._child(
                node,
                name,
                role=child_role,
                group=child_group if not is_leaf else group,
                missing_ok=missing_ok if is_leaf else False,
                open_dir=open_dirs if (not is_leaf or leaf == "dir") else False,
                open_file=is_leaf and leaf == "file",
                policy=policy if is_leaf else None,
                dir_mode=None,
                workspace=workspace and is_leaf,
            )
            if is_leaf:
                return node
            if node.first_kind == "absent":
                if missing_ok:
                    return node
                self._missing(node, group)
            if node.first_kind != "dir":
                self._unsafe_node(node, node.group)
        return node

    def _child(
        self,
        parent,
        name,
        *,
        role,
        group,
        missing_ok,
        open_dir=False,
        open_file=False,
        policy=None,
        dir_mode=None,
        workspace=False,
    ):
        lexical = _join_abs(parent.lexical, name) if parent.lexical != "/" or True else "/" + name
        if parent.lexical == "/":
            lexical = "/" + name
        else:
            lexical = parent.lexical + "/" + name
        existing = self._nodes.get(lexical)
        if existing is None:
            node = _Node(parent, name, lexical, role, group)
            self._nodes[lexical] = node
        else:
            node = existing
            if node.group is None:
                node.group = group
        self._mark(group)
        if not node.observed:
            self._observe_named(node)
        if node.first_kind == "stat_error":
            code = WORKSPACE_ROOT_INVALID if workspace else (
                CODE_PROOF_RESOURCE_INVALID if group == "resources" else CODE_PROOF_IO_ERROR
            )
            reason = "syscall_failed" if code != CODE_PROOF_RESOURCE_INVALID else "syscall_failed"
            if workspace:
                _raise_io(
                    WORKSPACE_ROOT_INVALID,
                    phase=self._phase,
                    group=group,
                    reason="syscall_failed",
                    operation=node.first_error_op,
                    errno=node.first_error_errno,
                )
            if group == "resources":
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase=self._phase,
                    group=group,
                    reason="syscall_failed",
                    operation=node.first_error_op,
                    errno=node.first_error_errno,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase=self._phase,
                group=group,
                reason="syscall_failed",
                operation=node.first_error_op,
                errno=node.first_error_errno,
            )
        if node.first_kind == "absent":
            if missing_ok:
                return node
            self._missing(node, group, workspace=workspace)
        if open_dir and node.first_kind == "dir" and node.fd is None:
            self._open_dir_node(
                node, exact_mode=dir_mode, group=group, workspace=workspace
            )
        if open_file and node.first_kind == "file" and node.fd is None:
            self._open_file_node(
                node, policy=policy, group=group, workspace=workspace
            )
        if open_dir and node.first_kind != "dir" and node.first_kind != "absent":
            self._unsafe_node(node, group, workspace=workspace)
        if open_file and node.first_kind != "file" and node.first_kind != "absent":
            self._unsafe_node(node, group, workspace=workspace)
        if dir_mode is not None and node.first_kind == "dir":
            reason = _dir_reason(
                _StampView(node.first_named_stamp, directory=True),
                exact_mode=dir_mode,
            )
            if reason is not None:
                self._raise_reason(reason, group, workspace, "stat")
        if policy == "output" and node.first_kind == "file":
            reason = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                exact_mode=0o600,
            )
            if reason is not None:
                self._raise_reason(reason, group, workspace, "stat")
        if policy == "resource" and node.first_kind == "file":
            reason = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                resource_policy=True,
            )
            if reason is not None:
                if group == "resources":
                    _raise_io(
                        CODE_PROOF_RESOURCE_INVALID,
                        phase=self._phase,
                        group="resources",
                        reason=reason,
                        operation="stat",
                    )
                self._raise_reason(reason, group, workspace, "stat")
        return node

    def _observe_named(self, node):
        node.observed = True
        parent = node.parent
        try:
            if parent is None:
                st = _stat(node.lexical, follow_symlinks=False)
            else:
                st = _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            en = _bound_errno(exc)
            if en == _ENOENT:
                node.first_kind = "absent"
                return
            node.first_kind = "stat_error"
            node.first_error_op = "stat"
            node.first_error_errno = en
            return
        if _is_dir(st):
            stamp = _dir_stamp(st)
            node.first_kind = "dir"
            node.first_named_stamp = stamp
            node.dev_ino = _identity(st)
        elif _is_reg(st):
            stamp = _file_stamp(st)
            node.first_kind = "file"
            node.first_named_stamp = stamp
            node.dev_ino = _identity(st)
        else:
            stamp = _file_stamp(st) or _dir_stamp(st)
            node.first_kind = "other"
            node.first_named_stamp = stamp
            node.dev_ino = _identity(st) if stamp is not None else None
        if node.first_named_stamp is None and node.first_kind != "absent":
            node.first_kind = "stat_error"
            node.first_error_op = "stat"
            node.first_error_errno = None

    def _open_dir_node(self, node, exact_mode, group, workspace=False):
        reason = _dir_reason(
            _StampView(node.first_named_stamp, directory=True),
            exact_mode=exact_mode,
        )
        if reason is not None:
            self._raise_reason(reason, group, workspace, "stat")
        try:
            fd = _open(node.name, _dir_flags(), dir_fd=node.parent.fd)
        except OSError as exc:
            if workspace:
                raise _err_os(self._phase, group, "open", exc, workspace=True) from None
            raise _err_os(self._phase, group, "open", exc) from None
        self._register_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            raise _err_os(self._phase, group, "fstat", exc, workspace=workspace) from None
        fstamp = _dir_stamp(fst)
        if fstamp != node.first_named_stamp:
            _raise_io(
                WORKSPACE_ROOT_INVALID if workspace else WORK_PATH_UNSAFE,
                phase=self._phase,
                group=group,
                reason="edge_changed",
                operation="fstat",
            )
        node.first_fd_stamp = fstamp

    def _open_file_node(self, node, policy, group, workspace=False):
        if policy == "output":
            reason = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                exact_mode=0o600,
            )
        else:
            reason = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                resource_policy=True,
            )
        if reason is not None:
            if group == "resources":
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase=self._phase,
                    group="resources",
                    reason=reason,
                    operation="stat",
                )
            self._raise_reason(reason, group, workspace, "stat")
        try:
            fd = _open(node.name, _file_rd_flags(), dir_fd=node.parent.fd)
        except OSError as exc:
            if group == "resources":
                raise _err_os(self._phase, group, "open", exc, resource=True) from None
            raise _err_os(self._phase, group, "open", exc, workspace=workspace) from None
        self._register_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            raise _err_os(
                self._phase, group, "fstat", exc, workspace=workspace, resource=(group == "resources")
            ) from None
        fstamp = _file_stamp(fst)
        if fstamp != node.first_named_stamp:
            code = WORKSPACE_ROOT_INVALID if workspace else (
                CODE_PROOF_RESOURCE_INVALID if group == "resources" else WORK_PATH_UNSAFE
            )
            reason = "edge_changed"
            if group == "resources":
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase=self._phase,
                    group="resources",
                    reason="edge_changed",
                    operation="fstat",
                )
            _raise_io(
                code,
                phase=self._phase,
                group=group,
                reason=reason,
                operation="fstat",
            )
        node.first_fd_stamp = fstamp

    def _read_node(
        self,
        node,
        maximum,
        *,
        group,
        limit_pointer=None,
        limit_name=None,
        resource=False,
        workspace=False,
    ):
        if node.fd is None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=group,
                reason="edge_changed",
            )
        try:
            st = _fstat(node.fd)
        except OSError as exc:
            raise _err_os(
                self._phase, group, "fstat", exc, resource=resource, workspace=workspace
            ) from None
        stamp = _file_stamp(st)
        expected = node.authorized_stamp or node.first_fd_stamp or node.first_named_stamp
        if stamp != expected:
            if resource:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID
                    if node.first_named_stamp == stamp
                    else WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=group,
                    reason="edge_changed",
                    operation="fstat",
                )
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=group,
                reason="edge_changed",
                operation="fstat",
            )
        size = st.st_size
        if resource and node.pin_size is not None and size != node.pin_size:
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase=self._phase,
                group="resources",
                reason="resource_hash",
            )
        if size > maximum:
            if resource:
                _raise_io(
                    CODE_PROOF_RESOURCE_INVALID,
                    phase=self._phase,
                    group="resources",
                    reason="resource_hash",
                )
            if limit_pointer is not None:
                _raise_limit(limit_pointer, limit_name, maximum, size)
            _raise_limit("/output", "max_output_peak_bytes", maximum, size)
        try:
            _seek(node.fd, 0, os.SEEK_SET)
        except OSError as exc:
            raise _err_os(
                self._phase, group, "seek", exc, resource=resource, workspace=workspace
            ) from None
        data = self._read_exact(node.fd, size, group, resource=resource, workspace=workspace)
        if len(data) != size:
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase=self._phase,
                group=group,
                reason="syscall_failed",
                operation="read",
            )
        try:
            again = _fstat(node.fd)
        except OSError as exc:
            raise _err_os(
                self._phase, group, "fstat", exc, resource=resource, workspace=workspace
            ) from None
        if _file_stamp(again) != stamp:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=group,
                reason="edge_changed",
                operation="fstat",
            )
        node.bytes = data

    def _read_exact(self, fd, size, group, resource=False, workspace=False):
        chunks = []
        got = 0
        while got < size:
            try:
                buf = _read(fd, min(_WRITE_CHUNK, size - got))
            except OSError as exc:
                raise _err_os(
                    self._phase, group, "read", exc, resource=resource, workspace=workspace
                ) from None
            if buf == b"":
                break
            chunks.append(buf)
            got += len(buf)
        return b"".join(chunks)

    def _register_fd(self, fd):
        self._fds.append(_FdRec(fd))

    def _missing(self, node, group, workspace=False):
        if workspace:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase=self._phase,
                group=group,
                reason="missing",
                operation="stat",
            )
        if group == "resources":
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase=self._phase,
                group="resources",
                reason="missing",
                operation="stat",
            )
        _raise_io(
            WORK_PATH_UNSAFE,
            phase=self._phase,
            group=group,
            reason="missing",
            operation="stat",
        )

    def _unsafe_node(self, node, group, workspace=False):
        reason = "unsafe_type"
        if node.first_kind == "file":
            classified = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                resource_policy=group in ("resources", "metadata", "bundle"),
            )
            if classified is not None:
                reason = classified
        elif node.first_kind == "dir":
            classified = _dir_reason(_StampView(node.first_named_stamp, directory=True))
            if classified is not None:
                reason = classified
        self._raise_reason(reason, group, workspace, "stat")

    def _raise_reason(self, reason, group, workspace, operation):
        if workspace:
            _raise_io(
                WORKSPACE_ROOT_INVALID,
                phase=self._phase,
                group=group,
                reason=reason,
                operation=operation,
            )
        if group == "resources":
            _raise_io(
                CODE_PROOF_RESOURCE_INVALID,
                phase=self._phase,
                group="resources",
                reason=reason,
                operation=operation,
            )
        _raise_io(
            WORK_PATH_UNSAFE,
            phase=self._phase,
            group=group,
            reason=reason,
            operation=operation,
        )

    def _resource_unsafe(self, node):
        reason = "unsafe_type"
        if node.first_kind == "file":
            classified = _file_reason(
                _StampView(node.first_named_stamp, directory=False),
                resource_policy=True,
            )
            if classified is not None:
                reason = classified
        _raise_io(
            CODE_PROOF_RESOURCE_INVALID,
            phase=self._phase,
            group="resources",
            reason=reason,
            operation="stat",
        )

    def _reject_alias(self, node, group):
        if node.dev_ino is None:
            return
        for other in self._nodes.values():
            if other is node or other.dev_ino is None:
                continue
            if other.role in (
                "namespace",
                "family",
                "output_file",
                "work",
                "batch",
            ) and other.dev_ino == node.dev_ino:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=group,
                    reason="overlap",
                )
        if self._ns_node is not None and self._ns_node.dev_ino == node.dev_ino:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=group,
                reason="overlap",
            )

    def _validate_bundle_spelling(self, path):
        if len(path) > _MAX_BUNDLE_PATH_CHARS:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        if not path.startswith(".work/"):
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        if path.endswith("/") or "//" in path:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        for char in path:
            if _forbidden_bundle_char(char):
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="retaining",
                    group="bundle",
                    reason="path_spelling",
                )
        rest = path[6:]
        if rest == "":
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        for part in rest.split("/"):
            if part == "" or part == "." or part == "..":
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="retaining",
                    group="bundle",
                    reason="path_spelling",
                )
        nfc = unicodedata.normalize("NFC", path)
        if nfc != path:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        try:
            raw = path.encode("utf-8")
            nfc_raw = nfc.encode("utf-8")
        except UnicodeEncodeError:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )
        if len(raw) > _MAX_BUNDLE_PATH_BYTES or len(nfc_raw) > _MAX_BUNDLE_PATH_BYTES:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            )

    def _parse_object_record(self, rec, width):
        if type(rec) is not dict:
            _raise_struct("type")
        found = 0
        for key in rec:
            if type(key) is not str:
                _raise_struct("type")
            if key not in _OBJECT_RECORD_KEY_SET:
                _raise_struct("shape")
            found += 1
        if found != 5:
            _raise_struct("shape")
        oid = rec["oid"]
        object_type = rec["object_type"]
        body_size = rec["body_size_bytes"]
        body_sha = rec["body_sha256"]
        framed_sha = rec["framed_sha256"]
        if type(oid) is not str or type(object_type) is not str:
            _raise_struct("type")
        if type(body_size) is not int:
            _raise_struct("type")
        if type(body_sha) is not str or type(framed_sha) is not str:
            _raise_struct("type")
        if object_type not in ("commit", "tree", "blob"):
            _raise_struct("shape")
        if not _is_hex(oid, width):
            _raise_struct("shape")
        if not _is_hex(body_sha, 64) or not _is_hex(framed_sha, 64):
            _raise_struct("shape")
        if body_size < 0:
            _raise_struct("limits")
        return {
            "oid": oid,
            "object_type": object_type,
            "body_size_bytes": body_size,
            "body_sha256": body_sha,
            "framed_sha256": framed_sha,
        }

    def _dir_currently_present(self, node):
        if node is None:
            return False
        if node.authorized_removed:
            return False
        if node.authorized_stamp is not None:
            return True
        return node.first_kind == "dir"

    def _stat_obj_from_stamp(self, node, directory):
        return _StampView(node.first_named_stamp, directory=directory)

    def _ensure_output_dirs(self, family):
        self._mark("output_layout")
        self._mark("installation")
        work = self._work_node
        if work is None or work.first_kind == "absent":
            if work is None:
                work = self._child(
                    self._checkout,
                    _WORK_NAME,
                    role="work",
                    group="output_layout",
                    missing_ok=True,
                    open_dir=False,
                )
                self._work_node = work
            self._mkdir_authorized(self._checkout, work, 0o700)
        elif work.first_kind != "dir":
            self._unsafe_node(work, "output_layout")
        batch = self._batch_node
        if batch is None or batch.first_kind == "absent":
            if batch is None:
                batch = self._child(
                    work,
                    self._batch_id,
                    role="batch",
                    group="output_layout",
                    missing_ok=True,
                    open_dir=False,
                )
                self._batch_node = batch
            if batch.first_kind == "absent" and batch.authorized_stamp is None:
                self._mkdir_authorized(work, batch, 0o700)
        elif batch.first_kind != "dir":
            self._unsafe_node(batch, "output_layout")
        ns = self._ns_node
        if ns is None or (ns.first_kind == "absent" and ns.authorized_stamp is None):
            if ns is None:
                ns = self._child(
                    batch,
                    _NS_NAME,
                    role="namespace",
                    group="output_layout",
                    missing_ok=True,
                    open_dir=False,
                    dir_mode=0o700,
                )
                self._ns_node = ns
            if ns.first_kind == "absent" and ns.authorized_stamp is None:
                self._mkdir_authorized(batch, ns, 0o700)
            for name in _DIRECT_NAMES:
                if name not in self._slot_nodes:
                    slot = self._child(
                        ns,
                        name,
                        role="output_file",
                        group="output_files",
                        missing_ok=True,
                        open_file=False,
                    )
                    slot.rel = name
                    self._slot_nodes[name] = slot
            for fam in _FAMILY_NAMES:
                if fam not in self._family_nodes:
                    self._family_nodes[fam] = self._child(
                        ns,
                        fam,
                        role="family",
                        group="output_layout",
                        missing_ok=True,
                        open_dir=False,
                        dir_mode=0o700,
                    )
        elif ns.first_kind != "dir" and ns.authorized_stamp is None:
            self._unsafe_node(ns, "output_layout")
        if family is not None:
            fam_node = self._family_nodes.get(family)
            if fam_node is None or (
                fam_node.first_kind == "absent" and fam_node.authorized_stamp is None
            ):
                if fam_node is None:
                    fam_node = self._child(
                        self._ns_node,
                        family,
                        role="family",
                        group="output_layout",
                        missing_ok=True,
                        open_dir=False,
                        dir_mode=0o700,
                    )
                    self._family_nodes[family] = fam_node
                if fam_node.first_kind == "absent" and fam_node.authorized_stamp is None:
                    self._mkdir_authorized(self._ns_node, fam_node, 0o700)
                    ns_scan = self._scan_by_role.get("namespace")
                    if ns_scan is not None:
                        ns_scan.additions.add(family)

    def _mkdir_authorized(self, parent, node, mode):
        self._nameset_verify()
        self._verify_node(parent)
        if node.first_kind != "absent" or node.authorized_stamp is not None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group="output_layout",
                reason="late_arrival",
            )
        raised = None
        try:
            _mkdir(node.name, mode, dir_fd=parent.fd)
        except OSError as exc:
            raised = exc
        present = None
        try:
            st = _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
            present = st
        except OSError:
            present = None
        if raised is not None:
            if present is not None:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group="output_layout",
                    reason="late_arrival",
                    operation="mkdir",
                    errno=_bound_errno(raised),
                )
            raise _err_os(self._phase, "output_layout", "mkdir", raised) from None
        if present is None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group="output_layout",
                reason="edge_changed",
                operation="stat",
            )
        reason = _dir_reason(present, exact_mode=mode)
        if reason is not None:
            node.first_named_stamp = _dir_stamp(present)
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group="output_layout",
                reason=reason,
                operation="stat",
            )
        stamp = _dir_stamp(present)
        try:
            fd = _open(node.name, _dir_flags(), dir_fd=parent.fd)
        except OSError as exc:
            node.first_named_stamp = stamp
            raise _err_os(self._phase, "output_layout", "open", exc) from None
        self._register_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            node.first_named_stamp = stamp
            raise _err_os(self._phase, "output_layout", "fstat", exc) from None
        fstamp = _dir_stamp(fst)
        if fstamp != stamp:
            node.first_named_stamp = stamp
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group="output_layout",
                reason="edge_changed",
                operation="fstat",
            )
        node.authorized_stamp = stamp
        node.first_fd_stamp = fstamp
        node.dev_ino = _identity(fst)
        self._nameset_verify()
        try:
            _fsync(parent.fd)
        except OSError as exc:
            en = _bound_errno(exc)
            if en in _UNSUP_ERRNOS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group="output_layout",
                    reason="unavailable_primitive",
                    operation="fsync",
                    errno=en,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase=self._phase,
                group="output_layout",
                reason="syscall_failed",
                operation="fsync",
                errno=en,
            )
        self._nameset_verify()

    def _assert_target_absent(self, parent, parsed):
        if parsed[0] == "direct":
            name = parsed[1]
        else:
            name = parsed[2]
        node = self._child(
            parent,
            name,
            role="output_file",
            group="output_files",
            missing_ok=True,
            open_file=False,
        )
        if node.first_kind != "absent" or node.authorized_stamp is not None:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="idle",
                group="installation",
                reason="late_arrival",
            )
        try:
            _stat(name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) == _ENOENT:
                return
            raise _err_os(self._phase, "installation", "stat", exc) from None
        _raise_io(
            WORK_PATH_UNSAFE,
            phase="idle",
            group="installation",
            reason="late_arrival",
            operation="stat",
        )

    def _create_temp(self, parent, payload):
        inst = self._install
        self._mark("installation")
        self._nameset_verify()
        last_exc = None
        for _attempt in range(8):
            name = _temp_basename()
            node = self._child(
                parent,
                name,
                role="temp",
                group="installation",
                missing_ok=True,
                open_file=False,
            )
            if node.first_kind != "absent":
                continue
            try:
                fd = _open(name, _temp_flags(), 0o600, dir_fd=parent.fd)
            except OSError as exc:
                last_exc = exc
                if _bound_errno(exc) == _EEXIST:
                    continue
                present = False
                try:
                    _stat(name, dir_fd=parent.fd, follow_symlinks=False)
                    present = True
                except OSError:
                    present = False
                if present:
                    _raise_io(
                        WORK_PATH_UNSAFE,
                        phase="idle",
                        group="installation",
                        reason="late_arrival",
                        operation="open",
                        errno=_bound_errno(exc),
                    )
                raise _err_os(self._phase, "installation", "open", exc) from None
            self._register_fd(fd)
            inst.temp_fd = fd
            inst.temp_name = name
            inst.temp_node = node
            inst.temp_owned = True
            inst.parent_node = parent
            inst.phase = "temp_created"
            node.flex_temp = True
            try:
                named = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
                fst = _fstat(fd)
            except OSError as exc:
                raise _err_os(self._phase, "installation", "fstat", exc) from None
            nstamp = _file_stamp(named)
            fstamp = _file_stamp(fst)
            if nstamp is None or fstamp is None or nstamp != fstamp:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="temp_created",
                    group="installation",
                    reason="edge_changed",
                    operation="fstat",
                )
            reason = _file_reason(fst, exact_mode=0o600)
            if reason is not None:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="temp_created",
                    group="installation",
                    reason=reason,
                    operation="fstat",
                )
            node.authorized_stamp = fstamp
            node.first_fd_stamp = fstamp
            node.fd = fd
            node.dev_ino = _identity(fst)
            self._nameset_verify()
            return
        if last_exc is not None:
            raise _err_os(self._phase, "installation", "open", last_exc) from None
        _raise_io(
            WORK_PATH_UNSAFE,
            phase="idle",
            group="installation",
            reason="late_arrival",
            operation="open",
        )

    def _write_temp(self, payload):
        inst = self._install
        inst.phase = "writing"
        fd = inst.temp_fd
        offset = 0
        length = len(payload)
        while offset < length:
            chunk = payload[offset : offset + _WRITE_CHUNK]
            try:
                written = _write(fd, chunk)
            except OSError as exc:
                inst.written = offset
                self._verify_written_prefix(payload)
                raise _err_os("writing", "installation", "write", exc) from None
            if written == 0:
                inst.written = offset
                self._verify_written_prefix(payload)
                _raise_io(
                    CODE_PROOF_IO_ERROR,
                    phase="writing",
                    group="installation",
                    reason="zero_write",
                    operation="write",
                )
            if written < 0 or written > len(chunk):
                inst.written = offset
                _raise_io(
                    CODE_PROOF_IO_ERROR,
                    phase="writing",
                    group="installation",
                    reason="syscall_failed",
                    operation="write",
                )
            offset += written
            inst.written = offset
            try:
                st = _fstat(fd)
            except OSError as exc:
                raise _err_os("writing", "installation", "fstat", exc) from None
            if st.st_size != offset or _identity(st) != inst.temp_node.dev_ino:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="writing",
                    group="installation",
                    reason="edge_changed",
                    operation="fstat",
                )
            inst.temp_node.authorized_stamp = _file_stamp(st)
            self._nameset_verify()

    def _verify_written_prefix(self, payload):
        inst = self._install
        if inst.temp_fd is None or inst.written <= 0:
            return
        try:
            _seek(inst.temp_fd, 0, os.SEEK_SET)
            data = self._read_exact(
                inst.temp_fd, inst.written, "installation"
            )
        except Exception:
            return
        if data != payload[: inst.written]:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="writing",
                group="installation",
                reason="bytes_changed",
                operation="read",
            )

    def _finish_temp_ready(self, payload):
        inst = self._install
        fd = inst.temp_fd
        try:
            _seek(fd, 0, os.SEEK_SET)
            data = self._read_exact(fd, len(payload), "installation")
            st = _fstat(fd)
        except OSError as exc:
            raise _err_os("writing", "installation", "read", exc) from None
        if data != payload:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="writing",
                group="installation",
                reason="bytes_changed",
                operation="read",
            )
        reason = _file_reason(st, exact_mode=0o600)
        if reason is not None or st.st_size != len(payload) or st.st_nlink != 1:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="writing",
                group="installation",
                reason=reason or "link_count",
                operation="fstat",
            )
        try:
            _fsync(fd)
        except OSError as exc:
            en = _bound_errno(exc)
            if en in _UNSUP_ERRNOS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="writing",
                    group="installation",
                    reason="unavailable_primitive",
                    operation="fsync",
                    errno=en,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase="writing",
                group="installation",
                reason="syscall_failed",
                operation="fsync",
                errno=en,
            )
        inst.temp_node.authorized_stamp = _file_stamp(st)
        inst.temp_node.bytes = payload
        inst.phase = "temp_ready"
        self._full_verify()

    def _link_final(self, parent, parsed, payload):
        inst = self._install
        if parsed[0] == "direct":
            final_name = parsed[1]
        else:
            final_name = parsed[2]
        self._nameset_verify()
        try:
            _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) != _ENOENT:
                raise _err_os("temp_ready", "installation", "stat", exc) from None
        else:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="temp_ready",
                group="installation",
                reason="late_arrival",
                operation="stat",
            )
        raised = None
        try:
            _link(
                inst.temp_name,
                final_name,
                src_dir_fd=parent.fd,
                dst_dir_fd=parent.fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raised = exc
        present = None
        try:
            present = _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError:
            present = None
        if raised is not None:
            if present is not None:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="temp_ready",
                    group="installation",
                    reason="late_arrival",
                    operation="link",
                    errno=_bound_errno(raised),
                )
            raise _err_os("temp_ready", "installation", "link", raised) from None
        inst.link_succeeded = True
        inst.phase = "linked"
        try:
            temp_st = _stat(inst.temp_name, dir_fd=parent.fd, follow_symlinks=False)
            final_st = present
            fd_st = _fstat(inst.temp_fd)
        except OSError as exc:
            raise _err_os("linked", "installation", "stat", exc) from None
        if (
            _identity(temp_st) != inst.temp_node.dev_ino
            or _identity(final_st) != inst.temp_node.dev_ino
            or _identity(fd_st) != inst.temp_node.dev_ino
        ):
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="edge_changed",
                operation="stat",
            )
        if final_st.st_nlink != 2 or temp_st.st_nlink != 2 or fd_st.st_nlink != 2:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="link_count",
                operation="stat",
            )
        if final_st.st_size != len(payload) or stat.S_IMODE(final_st.st_mode) != 0o600:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="bytes_changed" if final_st.st_size != len(payload) else "unsafe_mode",
            )
        inst.temp_node.authorized_stamp = _file_stamp(fd_st)
        self._nameset_verify()

    def _unlink_temp(self, parent, parsed, payload):
        inst = self._install
        if parsed[0] == "direct":
            final_name = parsed[1]
        else:
            final_name = parsed[2]
        try:
            temp_st = _stat(inst.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) == _ENOENT:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="linked",
                    group="installation",
                    reason="temp_ownership_lost",
                    operation="stat",
                )
            raise _err_os("linked", "installation", "stat", exc) from None
        if _identity(temp_st) != inst.temp_node.dev_ino:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="temp_ownership_lost",
                operation="stat",
            )
        inst.unlink_attempted = True
        raised = None
        try:
            _unlink(inst.temp_name, dir_fd=parent.fd)
        except OSError as exc:
            raised = exc
        temp_now = None
        try:
            temp_now = _stat(inst.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) != _ENOENT:
                raise _err_os("linked", "installation", "stat", exc) from None
        try:
            final_st = _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
            fd_st = _fstat(inst.temp_fd)
        except OSError as exc:
            raise _err_os("linked", "installation", "stat", exc) from None
        cleaned_ok = (
            temp_now is None
            and _identity(final_st) == inst.temp_node.dev_ino
            and _identity(fd_st) == inst.temp_node.dev_ino
            and final_st.st_nlink == 1
            and fd_st.st_nlink == 1
            and final_st.st_size == len(payload)
            and _is_reg(final_st)
            and stat.S_IMODE(final_st.st_mode) == 0o600
        )
        if raised is not None:
            if cleaned_ok:
                self._record_cleaned_prefix(parent, parsed, payload, final_st, fd_st)
                raise _err_os("linked", "installation", "unlink", raised) from None
            if temp_now is not None and _identity(temp_now) == inst.temp_node.dev_ino:
                raise _err_os("linked", "installation", "unlink", raised) from None
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="temp_ownership_lost",
                operation="unlink",
                errno=_bound_errno(raised),
            )
        if not cleaned_ok:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase="linked",
                group="installation",
                reason="edge_changed",
                operation="unlink",
            )
        inst.temp_owned = False
        inst.temp_node.authorized_removed = True
        inst.temp_node.flex_temp = False
        self._record_cleaned_prefix(parent, parsed, payload, final_st, fd_st)
        inst.phase = "cleaned"
        self._nameset_verify()

    def _record_cleaned_prefix(self, parent, parsed, payload, final_st, fd_st):
        inst = self._install
        if parsed[0] == "direct":
            final_name = parsed[1]
            rel = final_name
        else:
            final_name = parsed[2]
            rel = parsed[1] + "/" + final_name
        node = self._child(
            parent,
            final_name,
            role="output_file",
            group="output_files",
            missing_ok=True,
            open_file=False,
        )
        stamp = _file_stamp(fd_st)
        node.authorized_stamp = stamp
        node.first_fd_stamp = stamp
        node.fd = inst.temp_fd
        node.bytes = payload
        node.dev_ino = _identity(fd_st)
        node.rel = rel
        inst.target_node = node
        inst.final_stamp = stamp
        inst.cleaned = True
        self._output_file_nodes[rel] = node
        self._output_bytes[rel] = payload
        self._logical_c += len(payload)
        if parsed[0] == "direct":
            self._slot_nodes[final_name] = node
        else:
            family = parsed[1]
            if family == "objects":
                self._object_count += 1
                self._object_scan_charged += len(payload)
            elif family == "configs":
                self._config_count += 1
            else:
                self._handoff_count += 1
            scan = self._scan_by_role.get("family:" + family)
            if scan is not None:
                scan.additions.add(final_name)
            ns_scan = self._scan_by_role.get("namespace")
            if ns_scan is not None and family not in ns_scan.names:
                ns_scan.additions.add(family)
        ns_scan = self._scan_by_role.get("namespace")
        if ns_scan is not None and parsed[0] == "direct":
            ns_scan.additions.add(final_name)

    def _durable_finish(self, parent, parsed, payload):
        inst = self._install
        self._full_verify()
        try:
            _fsync(parent.fd)
        except OSError as exc:
            en = _bound_errno(exc)
            if en in _UNSUP_ERRNOS:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase="cleaned",
                    group="installation",
                    reason="unavailable_primitive",
                    operation="fsync",
                    errno=en,
                )
            _raise_io(
                CODE_PROOF_IO_ERROR,
                phase="cleaned",
                group="installation",
                reason="syscall_failed",
                operation="fsync",
                errno=en,
            )
        self._full_verify()
        inst.phase = "durable"

    def _full_verify(self):
        self._nameset_verify()
        self._verify_bytes()
        self._nameset_verify()

    def _nameset_verify(self):
        self._verify_group_checkout(bytes_too=False)
        self._verify_group_ancestors(bytes_too=False)
        self._verify_group_resources(bytes_too=False)
        self._verify_group_metadata(bytes_too=False)
        self._verify_group_bundle(bytes_too=False)
        self._verify_group_output_layout()
        self._verify_group_output_files(bytes_too=False)
        self._verify_group_installation(bytes_too=False)

    def _verify_bytes(self):
        self._verify_group_checkout(bytes_too=True)
        self._verify_group_ancestors(bytes_too=True)
        self._verify_group_resources(bytes_too=True)
        self._verify_group_metadata(bytes_too=True)
        self._verify_group_bundle(bytes_too=True)
        self._verify_group_output_files(bytes_too=True)
        self._verify_group_installation(bytes_too=True)

    def _verify_node(self, node, bytes_too=False):
        if node is None or not node.observed:
            return
        if node.authorized_removed:
            self._expect_absent(node)
            return
        if node.first_kind == "absent" and node.authorized_stamp is None:
            self._expect_absent(node)
            return
        if node.first_kind == "stat_error":
            self._expect_stat_error(node)
            return
        parent = node.parent
        try:
            if parent is None:
                named = _stat("/", follow_symlinks=False)
            else:
                named = _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if node.first_kind in ("dir", "file") or node.authorized_stamp is not None:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=node.group,
                    reason="edge_changed",
                    operation="stat",
                    errno=_bound_errno(exc),
                )
            raise _err_os(self._phase, node.group, "stat", exc) from None
        if node.first_kind == "dir" or (
            node.authorized_stamp is not None and len(node.authorized_stamp) == 3
        ):
            stamp = _dir_stamp(named)
            expected = node.authorized_stamp or node.first_named_stamp
            if stamp != expected:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=node.group,
                    reason="edge_changed",
                    operation="stat",
                )
            if node.fd is not None:
                try:
                    fst = _fstat(node.fd)
                except OSError as exc:
                    _raise_io(
                        WORK_PATH_UNSAFE,
                        phase=self._phase,
                        group=node.group,
                        reason="edge_changed",
                        operation="fstat",
                        errno=_bound_errno(exc),
                    )
                if _dir_stamp(fst) != expected:
                    _raise_io(
                        WORK_PATH_UNSAFE,
                        phase=self._phase,
                        group=node.group,
                        reason="edge_changed",
                        operation="fstat",
                    )
            return
        stamp = _file_stamp(named)
        expected = node.authorized_stamp or node.first_named_stamp
        inst = self._install
        if node.flex_temp and inst.phase in _ACTIVE_TEMP_FLEX and node is inst.temp_node:
            if stamp is None or _identity(named) != node.dev_ino:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group="installation",
                    reason="edge_changed",
                    operation="stat",
                )
            if named.st_nlink != 1 or not _is_reg(named):
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group="installation",
                    reason="unsafe_type" if not _is_reg(named) else "link_count",
                )
            if named.st_size != inst.written:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group="installation",
                    reason="edge_changed",
                    operation="stat",
                )
            expected_flex = True
        else:
            expected_flex = False
            if stamp != expected:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=node.group,
                    reason="edge_changed",
                    operation="stat",
                )
        if node.fd is not None:
            try:
                fst = _fstat(node.fd)
            except OSError as exc:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=node.group,
                    reason="edge_changed",
                    operation="fstat",
                    errno=_bound_errno(exc),
                )
            fstamp = _file_stamp(fst)
            if expected_flex:
                if _identity(fst) != node.dev_ino or fst.st_size != inst.written:
                    _raise_io(
                        WORK_PATH_UNSAFE,
                        phase=self._phase,
                        group="installation",
                        reason="edge_changed",
                        operation="fstat",
                    )
            elif fstamp != expected:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=node.group,
                    reason="edge_changed",
                    operation="fstat",
                )
        if bytes_too and node.bytes is not None and node.fd is not None and not expected_flex:
            self._reread_bytes(node)

    def _reread_bytes(self, node):
        try:
            _seek(node.fd, 0, os.SEEK_SET)
            data = self._read_exact(node.fd, len(node.bytes), node.group)
            st = _fstat(node.fd)
        except OSError as exc:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=node.group,
                reason="edge_changed",
                operation="read",
                errno=_bound_errno(exc),
            )
        if data != node.bytes:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=node.group,
                reason="bytes_changed",
                operation="read",
            )
        expected = node.authorized_stamp or node.first_fd_stamp or node.first_named_stamp
        if _file_stamp(st) != expected:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=node.group,
                reason="edge_changed",
                operation="fstat",
            )

    def _expect_absent(self, node):
        parent = node.parent
        if parent is None or parent.fd is None:
            return
        try:
            _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) == _ENOENT:
                return
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=node.group,
                reason="edge_changed",
                operation="stat",
                errno=_bound_errno(exc),
            )
        _raise_io(
            WORK_PATH_UNSAFE,
            phase=self._phase,
            group=node.group,
            reason="late_arrival",
            operation="stat",
        )

    def _expect_stat_error(self, node):
        parent = node.parent
        try:
            if parent is None:
                _stat("/", follow_symlinks=False)
            else:
                _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) == node.first_error_errno:
                return
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=node.group,
                reason="edge_changed",
                operation="stat",
                errno=_bound_errno(exc),
            )
        _raise_io(
            WORK_PATH_UNSAFE,
            phase=self._phase,
            group=node.group,
            reason="edge_changed",
            operation="stat",
        )

    def _verify_group_checkout(self, bytes_too):
        if "checkout" not in self._group_reached:
            return
        if self._checkout is not None:
            self._verify_node(self._checkout, bytes_too=False)
        if self._git_node is not None:
            self._verify_node(self._git_node, bytes_too=bytes_too and self._git_node.bytes is not None)
        if self._pyproject_node is not None:
            self._verify_node(self._pyproject_node, bytes_too=bytes_too)

    def _verify_group_ancestors(self, bytes_too):
        if "ancestors" not in self._group_reached:
            return
        nodes = [
            node
            for node in self._nodes.values()
            if node.group == "ancestors"
        ]
        nodes.sort(key=lambda item: item.lexical)
        for node in nodes:
            self._verify_node(node, bytes_too=False)

    def _verify_group_resources(self, bytes_too):
        if "resources" not in self._group_reached:
            return
        recs = list(self._resource_recs)
        recs.sort(key=lambda item: item.logical or item.lexical)
        for node in recs:
            if node.first_kind == "absent":
                self._expect_absent(node)
                continue
            self._verify_node(node, bytes_too=bytes_too)

    def _verify_group_metadata(self, bytes_too):
        if "metadata" not in self._group_reached:
            return
        if self._input_node is not None:
            self._verify_node(self._input_node, bytes_too=bytes_too)

    def _verify_group_bundle(self, bytes_too):
        if "bundle" not in self._group_reached:
            return
        if self._bundle_root is not None:
            self._verify_node(self._bundle_root, bytes_too=False)
            self._rescan_check(self._scan_by_role.get("bundle_root"))
        if self._bundle_objects is not None:
            self._verify_node(self._bundle_objects, bytes_too=False)
            self._rescan_check(self._scan_by_role.get("bundle_objects"))
        if self._bundle_manifest is not None:
            self._verify_node(self._bundle_manifest, bytes_too=bytes_too)
        bodies = [
            node
            for node in self._nodes.values()
            if node.role in ("bundle_body", "bundle_body_edge")
        ]
        bodies.sort(key=lambda item: item.name)
        for node in bodies:
            self._verify_node(node, bytes_too=bytes_too and node.bytes is not None)

    def _verify_bundle_nameset(self):
        self._verify_group_bundle(bytes_too=False)

    def _verify_group_output_layout(self):
        if "output_layout" not in self._group_reached:
            return
        if self._work_node is not None:
            self._verify_node(self._work_node, bytes_too=False)
            if self._work_node.first_kind == "absent" and self._work_node.authorized_stamp is None:
                return
        if self._batch_node is not None:
            self._verify_node(self._batch_node, bytes_too=False)
            if self._batch_node.first_kind == "absent" and self._batch_node.authorized_stamp is None:
                return
        if self._ns_node is not None:
            self._verify_node(self._ns_node, bytes_too=False)
            if self._ns_node.first_kind == "absent" and self._ns_node.authorized_stamp is None:
                return
            self._rescan_check(self._scan_by_role.get("namespace"))
        for family in _FAMILY_NAMES:
            node = self._family_nodes.get(family)
            if node is None:
                continue
            self._verify_node(node, bytes_too=False)
            if node.first_kind == "dir" or node.authorized_stamp is not None:
                self._rescan_check(self._scan_by_role.get("family:" + family))

    def _verify_group_output_files(self, bytes_too):
        if "output_files" not in self._group_reached:
            return
        if self._ns_node is None or (
            self._ns_node.first_kind == "absent" and self._ns_node.authorized_stamp is None
        ):
            return
        for name in _DIRECT_NAMES:
            node = self._slot_nodes.get(name)
            if node is not None:
                self._verify_node(node, bytes_too=bytes_too)
        names = sorted(self._output_file_nodes)
        for rel in names:
            node = self._output_file_nodes[rel]
            if node.rel in _DIRECT_FILES:
                continue
            self._verify_node(node, bytes_too=bytes_too)

    def _verify_group_installation(self, bytes_too):
        if "installation" not in self._group_reached and self._install.phase == "idle":
            return
        inst = self._install
        if inst.temp_node is not None:
            self._verify_node(inst.temp_node, bytes_too=bytes_too and inst.phase == "temp_ready")
        if inst.target_node is not None:
            self._verify_node(inst.target_node, bytes_too=bytes_too)

    def _rescan_check(self, scan):
        if scan is None or scan.dir_node is None or scan.dir_node.fd is None:
            return
        allow = 0
        inst = self._install
        if (
            inst.temp_owned
            and inst.parent_node is scan.dir_node
            and inst.phase in _TEMP_READY_PHASES
        ):
            allow = 1
        fresh = self._bounded_scan_copy(scan.dir_node, scan.cap, allow)
        expected = set(scan.names)
        expected |= set(scan.additions)
        expected -= set(scan.removals)
        if allow and inst.temp_name is not None:
            expected.add(inst.temp_name)
        if scan.completed and not scan.over_cap and scan.refusal is None:
            if not fresh.completed or fresh.over_cap:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=scan.dir_node.group,
                    reason="set_changed",
                    operation="scandir",
                )
            if set(fresh.names) != expected:
                _raise_io(
                    WORK_PATH_UNSAFE,
                    phase=self._phase,
                    group=scan.dir_node.group,
                    reason="set_changed",
                    operation="scandir",
                )
            for name in expected:
                if name == inst.temp_name and inst.phase in _ACTIVE_TEMP_FLEX:
                    continue
                old = None
                if name in scan.stamps:
                    old = scan.stamps[name]
                node = self._nodes.get(_join_abs(scan.dir_node.lexical, name))
                if node is not None and node.authorized_stamp is not None and not node.authorized_removed:
                    old = node.authorized_stamp
                if old is None:
                    continue
                new = fresh.stamps.get(name)
                if new != old and not (
                    node is not None
                    and node.flex_temp
                    and inst.phase in _ACTIVE_TEMP_FLEX
                ):
                    _raise_io(
                        WORK_PATH_UNSAFE,
                        phase=self._phase,
                        group=scan.dir_node.group,
                        reason="edge_changed",
                        operation="stat",
                    )
            return
        old_set = set(scan.names)
        new_set = set(fresh.names)
        changed = old_set != new_set
        if not changed:
            for name in old_set:
                if scan.stamps.get(name) != fresh.stamps.get(name):
                    changed = True
                    break
        if changed:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=scan.dir_node.group,
                reason="set_changed",
                operation="scandir",
            )

    def _bounded_scan_copy(self, dir_node, cap, allow):
        keep = cap + allow + 1
        names = []
        stamps = {}
        kinds = {}
        over_cap = False
        completed = False
        try:
            iterator_cm = _scandir(dir_node.fd)
        except OSError as exc:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=dir_node.group,
                reason="edge_changed",
                operation="scandir",
                errno=_bound_errno(exc),
            )
        counted = 0
        try:
            with iterator_cm as iterator:
                for entry in iterator:
                    counted += 1
                    if counted > keep:
                        over_cap = True
                        break
                    name = entry.name
                    if type(name) is not str:
                        _raise_io(
                            WORK_PATH_UNSAFE,
                            phase=self._phase,
                            group=dir_node.group,
                            reason="unknown_entry",
                            operation="scandir",
                        )
                    try:
                        st = _stat(name, dir_fd=dir_node.fd, follow_symlinks=False)
                    except OSError as exc:
                        _raise_io(
                            WORK_PATH_UNSAFE,
                            phase=self._phase,
                            group=dir_node.group,
                            reason="edge_changed",
                            operation="stat",
                            errno=_bound_errno(exc),
                        )
                    if _is_dir(st):
                        stamp = _dir_stamp(st)
                        kind = "dir"
                    elif _is_reg(st):
                        stamp = _file_stamp(st)
                        kind = "file"
                    else:
                        stamp = _file_stamp(st) or _dir_stamp(st)
                        kind = "other"
                    names.append(name)
                    stamps[name] = stamp
                    kinds[name] = kind
                    if counted > cap + allow:
                        over_cap = True
                        break
        except OSError as exc:
            _raise_io(
                WORK_PATH_UNSAFE,
                phase=self._phase,
                group=dir_node.group,
                reason="edge_changed",
                operation="scandir",
                errno=_bound_errno(exc),
            )
        if not over_cap:
            completed = True
        result = _Scan(dir_node, cap, "rescan")
        result.names = names
        result.stamps = stamps
        result.kinds = kinds
        result.over_cap = over_cap
        result.completed = completed
        return result

    def _finalize(self, original):
        if self._lifetime == "closed":
            return original
        self._lifetime = "finalizing"
        self._phase = "final_verify"
        self._group_fail = {}
        lineage = self._run_final_groups()
        self._phase = "closing"
        cleanup = self._cleanup_temp()
        close_err = self._close_all()
        if cleanup is None:
            cleanup = close_err
        selected = None
        if lineage is not None:
            pc, po, pe = _extract_prior(original)
            first = lineage
            rec = self._group_fail[first]
            selected = _io_error(
                WORK_PATH_UNSAFE,
                phase="final_verify",
                group=first,
                reason=rec["reason"],
                operation=rec["operation"],
                errno=rec["errno"],
                prior_code=pc,
                prior_operation=po,
                prior_errno=pe,
                failed_groups=list(self._group_fail),
            )
        elif cleanup is not None:
            selected = cleanup
        elif original is not None:
            selected = original
        self._clear_graph()
        self._lifetime = "closed"
        return selected

    def _run_final_groups(self):
        for group in _GROUPS:
            self._run_final_group(group, bytes_too=True)
        for group in _GROUPS:
            self._run_final_group(group, bytes_too=False)
        failed = [name for name in _GROUPS if name in self._group_fail]
        if not failed:
            return None
        return failed[0]

    def _run_final_group(self, group, bytes_too):
        if group not in self._group_reached:
            return
        try:
            if group == "checkout":
                self._verify_group_checkout(bytes_too)
            elif group == "ancestors":
                self._verify_group_ancestors(bytes_too)
            elif group == "resources":
                self._verify_group_resources(bytes_too)
            elif group == "metadata":
                self._verify_group_metadata(bytes_too)
            elif group == "bundle":
                self._verify_group_bundle(bytes_too)
            elif group == "output_layout":
                self._verify_group_output_layout()
            elif group == "output_files":
                self._verify_group_output_files(bytes_too)
            elif group == "installation":
                self._verify_group_installation(bytes_too)
        except CodeProofIOError as exc:
            self._note_fail(group, exc)
        except BaseException:
            if group not in self._group_fail:
                self._group_fail[group] = {
                    "reason": "edge_changed",
                    "operation": None,
                    "errno": None,
                }

    def _note_fail(self, group, exc):
        if group in self._group_fail:
            return
        reason = "edge_changed"
        operation = None
        errn = None
        if exc.code == WORK_PATH_UNSAFE or exc.code in _NINE_FIELD_CODES:
            details = None
            try:
                details = exc.details
            except Exception:
                details = None
            if type(details) is dict:
                raw_reason = details.get("reason") if "reason" in details else None
                if type(raw_reason) is str and raw_reason in _REASONS:
                    reason = raw_reason
                raw_op = details.get("operation") if "operation" in details else None
                if raw_op is None or (type(raw_op) is str and raw_op in _OPS):
                    operation = raw_op
                raw_en = details.get("errno") if "errno" in details else None
                if raw_en is None or (type(raw_en) is int and 0 <= raw_en <= 65535):
                    errn = raw_en
        self._group_fail[group] = {
            "reason": reason,
            "operation": operation,
            "errno": errn,
        }

    def _cleanup_temp(self):
        inst = self._install
        if not inst.temp_owned or inst.temp_name is None or inst.parent_node is None:
            return None
        parent = inst.parent_node
        if parent.fd is None:
            return _io_error(
                CODE_PROOF_IO_ERROR,
                phase="closing",
                group="installation",
                reason="temp_ownership_lost",
                operation="unlink",
            )
        try:
            st = _stat(inst.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc) == _ENOENT:
                inst.temp_owned = False
                if inst.temp_node is not None:
                    inst.temp_node.authorized_removed = True
                return None
            return _err_os("closing", "installation", "stat", exc)
        if inst.temp_node is None or inst.temp_node.dev_ino != _identity(st):
            return _io_error(
                WORK_PATH_UNSAFE,
                phase="closing",
                group="installation",
                reason="temp_ownership_lost",
                operation="stat",
            )
        if not _is_reg(st):
            return _io_error(
                WORK_PATH_UNSAFE,
                phase="closing",
                group="installation",
                reason="temp_ownership_lost",
                operation="stat",
            )
        inst.unlink_attempted = True
        try:
            _unlink(inst.temp_name, dir_fd=parent.fd)
        except OSError as exc:
            still = None
            try:
                still = _stat(inst.temp_name, dir_fd=parent.fd, follow_symlinks=False)
            except OSError as absent:
                if _bound_errno(absent) == _ENOENT:
                    inst.temp_owned = False
                    if inst.temp_node is not None:
                        inst.temp_node.authorized_removed = True
                    return _err_os("closing", "installation", "unlink", exc)
            if still is not None and _identity(still) == inst.temp_node.dev_ino:
                return _err_os("closing", "installation", "unlink", exc)
            return _io_error(
                WORK_PATH_UNSAFE,
                phase="closing",
                group="installation",
                reason="temp_ownership_lost",
                operation="unlink",
                errno=_bound_errno(exc),
            )
        inst.temp_owned = False
        if inst.temp_node is not None:
            inst.temp_node.authorized_removed = True
        return None

    def _close_all(self):
        first = None
        others = [rec for rec in self._fds if not rec.lock_dup]
        dups = [rec for rec in self._fds if rec.lock_dup]
        for rec in reversed(others):
            err = self._close_one(rec)
            if first is None:
                first = err
        for rec in dups:
            err = self._close_one(rec)
            if first is None:
                first = err
        return first

    def _close_one(self, rec):
        if rec.closed:
            return None
        rec.closed = True
        try:
            _close(rec.fd)
        except OSError as exc:
            return _err_os("closing", None, "close", exc)
        except BaseException:
            return _io_error(
                CODE_PROOF_IO_ERROR,
                phase="closing",
                group=None,
                reason="syscall_failed",
                operation="close",
            )
        return None

    def _clear_graph(self):
        self._context = None
        self._plan = None
        self._resource_recs = []
        self._resource_bytes = None
        self._nodes = {}
        self._fds = []
        self._scans = []
        self._scan_by_role = {}
        self._checkout = None
        self._root = None
        self._work_node = None
        self._batch_node = None
        self._ns_node = None
        self._family_nodes = {}
        self._output_file_nodes = {}
        self._slot_nodes = {}
        self._git_node = None
        self._pyproject_node = None
        self._input_node = None
        self._bundle_root = None
        self._bundle_objects = None
        self._bundle_manifest = None
        self._bundle_body_bytes = None
        self._lock_dup = None
        self._install = _InstallRec()
        self._output_bytes = {}
        self._initial_snapshot = {}


class _StampView:
    __slots__ = ("st_mode", "st_nlink", "st_dev", "st_ino", "st_size")

    def __init__(self, stamp, directory):
        if stamp is None:
            self.st_mode = 0
            self.st_nlink = 0
            self.st_dev = 0
            self.st_ino = 0
            self.st_size = 0
            return
        self.st_dev = stamp[0]
        self.st_ino = stamp[1]
        self.st_mode = stamp[2]
        if directory:
            self.st_size = 0
            self.st_nlink = 2
        else:
            self.st_size = stamp[3]
            self.st_nlink = stamp[6]


def _resource_reason(exc, default):
    raw = _safe_attr(exc, "reason")
    if raw is not _MISSING and type(raw) is str and raw in _RESOURCE_REASONS:
        return raw
    return default


def _err_os(phase, group, operation, exc, workspace=False, resource=False):
    en = _bound_errno(exc)
    if workspace:
        return _io_error(
            WORKSPACE_ROOT_INVALID,
            phase=phase,
            group=group,
            reason="syscall_failed",
            operation=operation,
            errno=en,
        )
    if resource:
        return _io_error(
            CODE_PROOF_RESOURCE_INVALID,
            phase=phase,
            group="resources",
            reason="syscall_failed",
            operation=operation,
            errno=en,
        )
    if en == _ENOENT:
        return _io_error(
            WORK_PATH_UNSAFE,
            phase=phase,
            group=group,
            reason="missing",
            operation=operation,
            errno=en,
        )
    if en == _EEXIST:
        return _io_error(
            WORK_PATH_UNSAFE,
            phase=phase,
            group=group,
            reason="late_arrival",
            operation=operation,
            errno=en,
        )
    if en == _ELOOP:
        return _io_error(
            WORK_PATH_UNSAFE,
            phase=phase,
            group=group,
            reason="unsafe_type",
            operation=operation,
            errno=en,
        )
    return _io_error(
        CODE_PROOF_IO_ERROR,
        phase=phase,
        group=group,
        reason="syscall_failed",
        operation=operation,
        errno=en,
    )


def open_code_session(*, batch_id):
    return _CodeSession(batch_id)
