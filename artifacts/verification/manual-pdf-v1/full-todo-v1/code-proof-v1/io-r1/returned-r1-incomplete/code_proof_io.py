"""Private CODE evidence filesystem session for one complete command."""

from __future__ import annotations

import errno as errno_module
import fcntl
import os
import re
import stat as stat_module
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

_MAX_BUNDLE_PATH_BYTES = 16384
_MAX_OUTPUT_BYTES = 134217728
_MAX_REQUEST_BYTES = 65536
_MAX_INTENT_BYTES = 1048576
_MAX_BUNDLE_BYTES = 1048576
_MAX_OBSERVATION_BYTES = 2097152
_MAX_CONFIG_BYTES = 2097152
_MAX_HANDOFF_BYTES = 131072
_MAX_OBJECT_BYTES = 8388608
_MAX_TOTAL_OBJECT_BYTES = 33554432
_MAX_OBJECTS = 2048
_MAX_TARGETS = 32
_MAX_TREE_ENTRIES = 32768
_MAX_CONFIGS = 32
_MAX_HANDOFFS = 32
_MAX_NAMESPACE_ENTRIES = 7
_MAX_BUNDLE_ROOT_ENTRIES = 2
_MAX_REQUEST_INPUT_BYTES = 65536
_MAX_OBSERVE_INPUT_BYTES = 1048576
_MAX_GIT_MARKER_BYTES = 65536
_MAX_PYPROJECT_BYTES = 1048576
_WRITE_CHUNK = 65536
_CONTEXT_BOUND = 1024
_TEMP_PREFIX = ".ce-tmp-"

_BATCH_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?$"
)
_HEX40_BODY_RE = re.compile(r"^[0-9a-f]{40}\.body$")
_HEX64_BODY_RE = re.compile(r"^[0-9a-f]{64}\.body$")
_HEX64_JSON_RE = re.compile(r"^[0-9a-f]{64}\.json$")
_TEMP_NAME_RE = re.compile(r"^\.ce-tmp-[0-9a-f]{32}$")
_OID40_RE = re.compile(r"^[0-9a-f]{40}$")
_OID64_RE = re.compile(r"^[0-9a-f]{64}$")
_POINTER_RE = re.compile(
    r"^/(?:input|output|request|intent|bundle|observation|config|"
    r"handoffs|objects|bodies|objects/[0-9]+/body_size_bytes)$"
)

_IO_MESSAGES = {
    "WORKSPACE_ROOT_INVALID": "CODE workspace root is invalid",
    "INVALID_BATCH_ID": "CODE batch identifier is invalid",
    "WORK_PATH_UNSAFE": "CODE retained path is unsafe",
    "CODE_PROOF_IO_ERROR": "CODE evidence I/O failed",
    "CODE_PROOF_RESOURCE_INVALID": "CODE evidence resource is invalid",
    "CODE_PROOF_LIMIT_EXCEEDED": "CODE evidence limit exceeded",
    "CODE_PROOF_CONFLICT": "CODE evidence artifact conflicts",
    "CODE_PROOF_BUSY": "CODE evidence workspace is busy",
}
_NINE_FIELD_CODES = (
    "WORKSPACE_ROOT_INVALID",
    "INVALID_BATCH_ID",
    "WORK_PATH_UNSAFE",
    "CODE_PROOF_IO_ERROR",
    "CODE_PROOF_RESOURCE_INVALID",
    "CODE_PROOF_BUSY",
)
_LIMIT_CODE = "CODE_PROOF_LIMIT_EXCEEDED"
_CONFLICT_CODE = "CODE_PROOF_CONFLICT"
_ALL_IO_CODES = _NINE_FIELD_CODES + (_LIMIT_CODE, _CONFLICT_CODE)

_PHASES = (
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
    "installation",
    "final_verify",
    "closing",
)
_GROUP_ORDER = (
    "checkout",
    "ancestors",
    "resources",
    "metadata",
    "bundle",
    "output_layout",
    "output_files",
    "installation",
)
_OPERATIONS = (
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
)
_REASONS = (
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
)
_CONFLICT_REASONS = (
    "request_changed",
    "acquisition_changed",
    "config_format_changed",
    "artifact_changed",
)
_LIMIT_NAMES = (
    "max_request_bytes",
    "max_intent_bytes",
    "max_bundle_bytes",
    "max_observation_bytes",
    "max_config_document_bytes",
    "max_handoff_bytes",
    "max_output_peak_bytes",
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
    "max_request_input_bytes",
    "max_observe_input_bytes",
)
_OUTPUT_LIMIT_MAXIMA = {
    "max_request_bytes": _MAX_REQUEST_BYTES,
    "max_intent_bytes": _MAX_INTENT_BYTES,
    "max_bundle_bytes": _MAX_BUNDLE_BYTES,
    "max_observation_bytes": _MAX_OBSERVATION_BYTES,
    "max_config_document_bytes": _MAX_CONFIG_BYTES,
    "max_handoff_bytes": _MAX_HANDOFF_BYTES,
    "max_output_peak_bytes": _MAX_OUTPUT_BYTES,
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
_GIT_LIMIT_MAXIMA = {
    "max_targets": _MAX_TARGETS,
    "max_objects": _MAX_OBJECTS,
    "max_tree_entries": _MAX_TREE_ENTRIES,
    "max_object_bytes": _MAX_OBJECT_BYTES,
    "max_total_object_bytes": _MAX_TOTAL_OBJECT_BYTES,
}
_GIT_LIMIT_KEYS = (
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
)
_DIRECT_FILES = {
    "request.json": ("max_request_bytes", _MAX_REQUEST_BYTES, "/request"),
    "intent.json": ("max_intent_bytes", _MAX_INTENT_BYTES, "/intent"),
    "bundle.json": ("max_bundle_bytes", _MAX_BUNDLE_BYTES, "/bundle"),
    "observation.json": (
        "max_observation_bytes",
        _MAX_OBSERVATION_BYTES,
        "/observation",
    ),
}
_FAMILY_NAMES = ("objects", "configs", "handoffs")
_FAMILY_FILE_CAPS = {
    "objects": ("max_object_bytes", _MAX_OBJECT_BYTES, "/objects", _MAX_OBJECTS),
    "configs": (
        "max_config_document_bytes",
        _MAX_CONFIG_BYTES,
        "/config",
        _MAX_CONFIGS,
    ),
    "handoffs": (
        "max_handoff_bytes",
        _MAX_HANDOFF_BYTES,
        "/handoffs",
        _MAX_HANDOFFS,
    ),
}
_NINE_DETAIL_KEYS = (
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
_LIMIT_DETAIL_KEYS = (
    "instance_pointer",
    "limit_name",
    "limit",
    "observed",
)
_CONFLICT_DETAIL_KEYS = ("instance_pointer", "reason")
_PRIOR_CODES = frozenset(
    (
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
    )
)
_LINEAGE_REASONS = frozenset(
    (
        "missing",
        "unsafe_type",
        "unsafe_mode",
        "link_count",
        "edge_changed",
        "bytes_changed",
        "set_changed",
        "late_arrival",
        "temp_ownership_lost",
        "overlap",
        "path_spelling",
        "unknown_entry",
        "syscall_failed",
        "unavailable_primitive",
    )
)
_SPECIAL_BITS = (
    stat_module.S_ISUID | stat_module.S_ISGID | stat_module.S_ISVTX
)
_EXEC_BITS = stat_module.S_IXUSR | stat_module.S_IXGRP | stat_module.S_IXOTH
_GROUP_OTHER_WRITE = stat_module.S_IWGRP | stat_module.S_IWOTH


def _getcwd():
    return os.getcwd()


def _open(path, flags, mode=0o777, *, dir_fd=None):
    if dir_fd is None:
        return os.open(path, flags, mode)
    return os.open(path, flags, mode, dir_fd=dir_fd)


def _stat(path, *, dir_fd=None, follow_symlinks=True):
    if dir_fd is None:
        return os.stat(path, follow_symlinks=follow_symlinks)
    return os.stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)


def _fstat(fd):
    return os.fstat(fd)


def _scandir(fd):
    return os.scandir(fd)


def _read(fd, n):
    return os.read(fd, n)


def _seek(fd, pos, whence=os.SEEK_SET):
    return os.lseek(fd, pos, whence)


def _mkdir(path, mode=0o777, *, dir_fd=None):
    if dir_fd is None:
        os.mkdir(path, mode)
        return
    os.mkdir(path, mode, dir_fd=dir_fd)


def _write(fd, data):
    return os.write(fd, data)


def _link(src, dst, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True):
    return os.link(
        src,
        dst,
        src_dir_fd=src_dir_fd,
        dst_dir_fd=dst_dir_fd,
        follow_symlinks=follow_symlinks,
    )


def _unlink(path, *, dir_fd=None):
    if dir_fd is None:
        os.unlink(path)
        return
    os.unlink(path, dir_fd=dir_fd)


def _fsync(fd):
    os.fsync(fd)


def _flock(fd, op):
    fcntl.flock(fd, op)


def _dup(fd):
    return os.dup(fd)


def _close(fd):
    os.close(fd)


def _capability_snapshot():
    return {
        "O_RDONLY": os.O_RDONLY,
        "O_WRONLY": os.O_WRONLY,
        "O_RDWR": os.O_RDWR,
        "O_CREAT": os.O_CREAT,
        "O_EXCL": os.O_EXCL,
        "O_NOFOLLOW": os.O_NOFOLLOW,
        "O_DIRECTORY": os.O_DIRECTORY,
        "O_CLOEXEC": os.O_CLOEXEC,
        "O_NONBLOCK": os.O_NONBLOCK,
        "SEEK_SET": os.SEEK_SET,
        "LOCK_EX": fcntl.LOCK_EX,
        "LOCK_NB": fcntl.LOCK_NB,
        "LOCK_UN": fcntl.LOCK_UN,
        "supports_dir_fd": os.supports_dir_fd,
        "supports_follow_symlinks": os.supports_follow_symlinks,
        "supports_fd": os.supports_fd,
        "fstat": os.fstat,
        "read": os.read,
        "lseek": os.lseek,
        "write": os.write,
        "fsync": os.fsync,
        "dup": os.dup,
        "close": os.close,
        "flock": fcntl.flock,
        "open": os.open,
        "stat": os.stat,
        "mkdir": os.mkdir,
        "link": os.link,
        "unlink": os.unlink,
        "scandir": os.scandir,
    }


def _unsupported_errnos():
    codes = [errno_module.ENOSYS, errno_module.EINVAL]
    for name in ("ENOTSUP", "EOPNOTSUPP"):
        value = getattr(errno_module, name, None)
        if type(value) is int:
            codes.append(value)
    return frozenset(codes)


def _busy_errnos():
    codes = [errno_module.EACCES, errno_module.EAGAIN]
    value = getattr(errno_module, "EWOULDBLOCK", None)
    if type(value) is int:
        codes.append(value)
    return frozenset(codes)


_UNSUPPORTED_ERRNOS = _unsupported_errnos()
_BUSY_ERRNOS = _busy_errnos()


def _dir_flags():
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
    )


def _file_flags():
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _temp_flags():
    return (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
    )


def _is_builtin_str(value):
    return type(value) is str


def _is_builtin_int(value):
    return type(value) is int


def _is_builtin_bytes(value):
    return type(value) is bytes


def _is_builtin_dict(value):
    return type(value) is dict


def _is_builtin_list(value):
    return type(value) is list


def _bound_errno(value):
    if type(value) is int and 0 <= value <= 65535:
        return value
    return None


def _invalid_context():
    raise ValueError("Invalid CODE I/O error context") from None


def _tuple_contains(haystack, needle):
    index = 0
    while index < len(haystack):
        if haystack[index] == needle:
            return True
        index += 1
    return False


def _validate_failed_groups(value):
    if not _is_builtin_list(value):
        _invalid_context()
    if len(value) > 8:
        _invalid_context()
    last_index = -1
    index = 0
    while index < len(value):
        item = value[index]
        if not _is_builtin_str(item) or not _tuple_contains(_GROUP_ORDER, item):
            _invalid_context()
        order_index = 0
        while order_index < len(_GROUP_ORDER):
            if _GROUP_ORDER[order_index] == item:
                break
            order_index += 1
        if order_index <= last_index:
            _invalid_context()
        last_index = order_index
        index += 1


def _validate_optional_enum(value, allowed):
    if value is None:
        return
    if not _is_builtin_str(value) or not _tuple_contains(allowed, value):
        _invalid_context()


def _validate_optional_errno(value):
    if value is None:
        return
    if type(value) is not int or value < 0 or value > 65535:
        _invalid_context()


def _validate_instance_pointer(value):
    if not _is_builtin_str(value):
        _invalid_context()
    if len(value) < 1 or len(value) > _CONTEXT_BOUND:
        _invalid_context()
    if _POINTER_RE.fullmatch(value) is None:
        _invalid_context()


def _validate_nine_details(details):
    keys = tuple(details.keys())
    if len(keys) != len(_NINE_DETAIL_KEYS):
        _invalid_context()
    index = 0
    while index < len(_NINE_DETAIL_KEYS):
        expected = _NINE_DETAIL_KEYS[index]
        found = False
        key_index = 0
        while key_index < len(keys):
            key = keys[key_index]
            if not _is_builtin_str(key):
                _invalid_context()
            if key == expected:
                found = True
                break
            key_index += 1
        if not found:
            _invalid_context()
        index += 1
    phase = details["phase"]
    if not _is_builtin_str(phase) or not _tuple_contains(_PHASES, phase):
        _invalid_context()
    _validate_optional_enum(details["group"], _GROUP_ORDER)
    reason = details["reason"]
    if not _is_builtin_str(reason) or not _tuple_contains(_REASONS, reason):
        _invalid_context()
    _validate_optional_enum(details["operation"], _OPERATIONS)
    _validate_optional_errno(details["errno"])
    prior_code = details["prior_code"]
    if prior_code is not None:
        if not _is_builtin_str(prior_code) or prior_code not in _PRIOR_CODES:
            _invalid_context()
    _validate_optional_enum(details["prior_operation"], _OPERATIONS)
    _validate_optional_errno(details["prior_errno"])
    _validate_failed_groups(details["failed_groups"])


def _validate_limit_details(details):
    keys = tuple(details.keys())
    if len(keys) != len(_LIMIT_DETAIL_KEYS):
        _invalid_context()
    index = 0
    while index < len(_LIMIT_DETAIL_KEYS):
        expected = _LIMIT_DETAIL_KEYS[index]
        found = False
        key_index = 0
        while key_index < len(keys):
            key = keys[key_index]
            if not _is_builtin_str(key):
                _invalid_context()
            if key == expected:
                found = True
                break
            key_index += 1
        if not found:
            _invalid_context()
        index += 1
    _validate_instance_pointer(details["instance_pointer"])
    limit_name = details["limit_name"]
    if not _is_builtin_str(limit_name) or not _tuple_contains(
        _LIMIT_NAMES, limit_name
    ):
        _invalid_context()
    limit = details["limit"]
    observed = details["observed"]
    if type(limit) is not int or limit < 1:
        _invalid_context()
    if type(observed) is not int or observed < 0:
        _invalid_context()


def _validate_conflict_details(details):
    keys = tuple(details.keys())
    if len(keys) != len(_CONFLICT_DETAIL_KEYS):
        _invalid_context()
    index = 0
    while index < len(_CONFLICT_DETAIL_KEYS):
        expected = _CONFLICT_DETAIL_KEYS[index]
        found = False
        key_index = 0
        while key_index < len(keys):
            key = keys[key_index]
            if not _is_builtin_str(key):
                _invalid_context()
            if key == expected:
                found = True
                break
            key_index += 1
        if not found:
            _invalid_context()
        index += 1
    _validate_instance_pointer(details["instance_pointer"])
    reason = details["reason"]
    if not _is_builtin_str(reason) or not _tuple_contains(
        _CONFLICT_REASONS, reason
    ):
        _invalid_context()


def _copy_details(code, details):
    if code == _LIMIT_CODE:
        return {
            "instance_pointer": details["instance_pointer"],
            "limit_name": details["limit_name"],
            "limit": details["limit"],
            "observed": details["observed"],
        }
    if code == _CONFLICT_CODE:
        return {
            "instance_pointer": details["instance_pointer"],
            "reason": details["reason"],
        }
    groups = details["failed_groups"]
    copied_groups = []
    index = 0
    while index < len(groups):
        copied_groups.append(groups[index])
        index += 1
    return {
        "phase": details["phase"],
        "group": details["group"],
        "reason": details["reason"],
        "operation": details["operation"],
        "errno": details["errno"],
        "prior_code": details["prior_code"],
        "prior_operation": details["prior_operation"],
        "prior_errno": details["prior_errno"],
        "failed_groups": copied_groups,
    }


class CodeProofIOError(Exception):
    def __init__(self, code, details):
        if not _is_builtin_str(code) or not _tuple_contains(_ALL_IO_CODES, code):
            _invalid_context()
        if not _is_builtin_dict(details):
            _invalid_context()
        if code == _LIMIT_CODE:
            _validate_limit_details(details)
        elif code == _CONFLICT_CODE:
            _validate_conflict_details(details)
        else:
            _validate_nine_details(details)
        self._code = code
        self._message = _IO_MESSAGES[code]
        self._details = _copy_details(code, details)
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
        return _copy_details(self._code, self._details)

    @property
    def exit_code(self):
        return self._exit_code

    def __str__(self):
        return self._message

    def __repr__(self):
        return "CodeProofIOError(code=" + repr(self._code) + ")"


def _io_error(
    code,
    *,
    phase,
    group,
    reason,
    operation=None,
    errno_value=None,
    prior_code=None,
    prior_operation=None,
    prior_errno=None,
    failed_groups=None,
):
    groups = []
    if failed_groups is not None:
        index = 0
        while index < len(failed_groups):
            groups.append(failed_groups[index])
            index += 1
    return CodeProofIOError(
        code,
        {
            "phase": phase,
            "group": group,
            "reason": reason,
            "operation": operation,
            "errno": errno_value,
            "prior_code": prior_code,
            "prior_operation": prior_operation,
            "prior_errno": prior_errno,
            "failed_groups": groups,
        },
    )


def _limit_error(instance_pointer, limit_name, limit, observed):
    return CodeProofIOError(
        _LIMIT_CODE,
        {
            "instance_pointer": instance_pointer,
            "limit_name": limit_name,
            "limit": limit,
            "observed": observed,
        },
    )


def _conflict_error(instance_pointer, reason):
    return CodeProofIOError(
        _CONFLICT_CODE,
        {
            "instance_pointer": instance_pointer,
            "reason": reason,
        },
    )


def _raise_structure(reason):
    raise CodeProofStructureError(reason) from None


def _make_git_error(code, message, details):
    try:
        return CodeGitProofError(code, message, details, exit_code=2)
    except TypeError:
        try:
            return CodeGitProofError(code, details, exit_code=2)
        except TypeError:
            try:
                return CodeGitProofError(code, message, details)
            except TypeError:
                return CodeGitProofError(code, details)


def _prior_fields(exc):
    if exc is None:
        return None, None, None
    code = None
    operation = None
    errno_value = None
    raw_code = getattr(exc, "code", None)
    if _is_builtin_str(raw_code) and raw_code in _PRIOR_CODES:
        code = raw_code
    if isinstance(exc, CodeProofIOError):
        payload = exc.details
        operation = payload.get("operation")
        if operation is not None and not _tuple_contains(_OPERATIONS, operation):
            operation = None
        errno_value = _bound_errno(payload.get("errno"))
        return code, operation, errno_value
    if isinstance(exc, OSError):
        errno_value = _bound_errno(getattr(exc, "errno", None))
        return code, operation, errno_value
    details = getattr(exc, "details", None)
    if _is_builtin_dict(details):
        operation = details.get("operation")
        if operation is not None and (
            not _is_builtin_str(operation)
            or not _tuple_contains(_OPERATIONS, operation)
        ):
            operation = None
        errno_value = _bound_errno(details.get("errno"))
    return code, operation, errno_value


def _require_capabilities(snapshot):
    if not _is_builtin_dict(snapshot):
        raise _io_error(
            "CODE_PROOF_IO_ERROR",
            phase="setup",
            group=None,
            reason="unavailable_primitive",
        ) from None
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
        ("SEEK_SET", True),
        ("LOCK_EX", False),
        ("LOCK_NB", False),
        ("LOCK_UN", False),
    )
    index = 0
    while index < len(flags):
        name, allow_zero = flags[index]
        present = False
        for key in snapshot.keys():
            if not _is_builtin_str(key):
                raise _io_error(
                    "CODE_PROOF_IO_ERROR",
                    phase="setup",
                    group=None,
                    reason="unavailable_primitive",
                ) from None
            if key == name:
                present = True
                break
        if not present:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="setup",
                group=None,
                reason="unavailable_primitive",
            ) from None
        value = snapshot[name]
        if type(value) is not int:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="setup",
                group=None,
                reason="unavailable_primitive",
            ) from None
        if value == 0 and not allow_zero:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="setup",
                group=None,
                reason="unavailable_primitive",
            ) from None
        index += 1
    callables = (
        "fstat",
        "read",
        "lseek",
        "write",
        "fsync",
        "dup",
        "close",
        "flock",
        "open",
        "stat",
        "mkdir",
        "link",
        "unlink",
        "scandir",
    )
    index = 0
    while index < len(callables):
        name = callables[index]
        present = False
        for key in snapshot.keys():
            if key == name:
                present = True
                break
        if not present or not callable(snapshot[name]):
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="setup",
                group=None,
                reason="unavailable_primitive",
            ) from None
        index += 1
    dir_fd = snapshot.get("supports_dir_fd")
    follow = snapshot.get("supports_follow_symlinks")
    fd_set = snapshot.get("supports_fd")
    try:
        open_ok = snapshot["open"] in dir_fd
        stat_ok = snapshot["stat"] in dir_fd
        mkdir_ok = snapshot["mkdir"] in dir_fd
        link_dir_ok = snapshot["link"] in dir_fd
        unlink_ok = snapshot["unlink"] in dir_fd
        stat_follow_ok = snapshot["stat"] in follow
        link_follow_ok = snapshot["link"] in follow
        scandir_ok = snapshot["scandir"] in fd_set
    except Exception:
        raise _io_error(
            "CODE_PROOF_IO_ERROR",
            phase="setup",
            group=None,
            reason="unavailable_primitive",
        ) from None
    if not (
        open_ok
        and stat_ok
        and mkdir_ok
        and link_dir_ok
        and unlink_ok
        and stat_follow_ok
        and link_follow_ok
        and scandir_ok
    ):
        raise _io_error(
            "CODE_PROOF_IO_ERROR",
            phase="setup",
            group=None,
            reason="unavailable_primitive",
        ) from None


def _is_canonical_abs(value):
    if not _is_builtin_str(value) or "\x00" in value:
        return False
    if not value.startswith("/"):
        return False
    if value == "/":
        return True
    if value.endswith("/"):
        return False
    parts = value.split("/")
    if parts[0] != "":
        return False
    index = 1
    while index < len(parts):
        part = parts[index]
        if part == "" or part == "." or part == "..":
            return False
        index += 1
    return True


def _is_canonical_rel(value):
    if not _is_builtin_str(value) or "\x00" in value:
        return False
    if value == "" or value.startswith("/") or value.endswith("/"):
        return False
    parts = value.split("/")
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "" or part == "." or part == "..":
            return False
        index += 1
    return True


def _join_abs(base, *parts):
    current = base
    index = 0
    while index < len(parts):
        part = parts[index]
        if current.endswith("/"):
            current = current + part
        else:
            current = current + "/" + part
        index += 1
    return current


def _abs_components(path):
    if path == "/":
        return ()
    return tuple(path[1:].split("/"))


def _paths_overlap(left, right):
    if left == right:
        return True
    left_prefix = left if left.endswith("/") else left + "/"
    right_prefix = right if right.endswith("/") else right + "/"
    return left_prefix.startswith(right_prefix) or right_prefix.startswith(
        left_prefix
    )


def _plan_dir_str(value):
    if _is_builtin_str(value):
        text = value
    else:
        text = str(value)
    if not _is_canonical_abs(text):
        return None
    return text


def _file_stamp(st):
    mtime = getattr(st, "st_mtime_ns", None)
    ctime = getattr(st, "st_ctime_ns", None)
    if type(mtime) is not int or type(ctime) is not int:
        raise _io_error(
            "CODE_PROOF_IO_ERROR",
            phase="setup",
            group=None,
            reason="syscall_failed",
            operation="stat",
        ) from None
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        mtime,
        ctime,
        st.st_nlink,
    )


def _dir_stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode)


def _is_dir(st):
    return stat_module.S_ISDIR(st.st_mode) and not stat_module.S_ISLNK(
        st.st_mode
    )


def _is_reg(st):
    return stat_module.S_ISREG(st.st_mode) and not stat_module.S_ISLNK(
        st.st_mode
    )


def _unsafe_dir_reason(st, exact_mode=None):
    if stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISDIR(st.st_mode):
        return "unsafe_type"
    if exact_mode is not None and (st.st_mode & 0o777) != exact_mode:
        return "unsafe_mode"
    return None


def _unsafe_file_reason(st, exact_mode=None):
    if stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
        return "unsafe_type"
    if st.st_nlink != 1:
        return "link_count"
    if exact_mode is not None:
        if (st.st_mode & 0o777) != exact_mode:
            return "unsafe_mode"
        return None
    if st.st_mode & _EXEC_BITS:
        return "unsafe_mode"
    if st.st_mode & _GROUP_OTHER_WRITE:
        return "unsafe_mode"
    if st.st_mode & _SPECIAL_BITS:
        return "unsafe_mode"
    return None


def _control_forbidden(char):
    code = ord(char)
    if char == "\\" or char == "\x00":
        return True
    if code < 0x20 or code == 0x7F:
        return True
    if 0x80 <= code <= 0x9F:
        return True
    if code == 0x2028 or code == 0x2029:
        return True
    if 0xD800 <= code <= 0xDFFF:
        return True
    return False


def _object_body_name(name):
    return (
        _HEX40_BODY_RE.fullmatch(name) is not None
        or _HEX64_BODY_RE.fullmatch(name) is not None
    )


def _oid_from_body_name(name):
    if not name.endswith(".body"):
        return None
    oid = name[:-5]
    if _OID40_RE.fullmatch(oid) is not None or _OID64_RE.fullmatch(oid) is not None:
        return oid
    return None


def _parse_install_name(name):
    if name in _DIRECT_FILES:
        limit_name, hard, pointer = _DIRECT_FILES[name]
        return ("direct", name, None, limit_name, hard, pointer)
    if "/" not in name:
        return None
    family, sep, base = name.partition("/")
    if sep != "/" or "/" in base or base == "":
        return None
    if family == "objects" and _object_body_name(base):
        limit_name, hard, pointer, _max_files = _FAMILY_FILE_CAPS["objects"]
        return ("objects", base, "objects", limit_name, hard, pointer)
    if family == "configs" and _HEX64_JSON_RE.fullmatch(base) is not None:
        limit_name, hard, pointer, _max_files = _FAMILY_FILE_CAPS["configs"]
        return ("configs", base, "configs", limit_name, hard, pointer)
    if family == "handoffs" and _HEX64_JSON_RE.fullmatch(base) is not None:
        limit_name, hard, pointer, _max_files = _FAMILY_FILE_CAPS["handoffs"]
        return ("handoffs", base, "handoffs", limit_name, hard, pointer)
    return None


def _closed_positive_map(value, keys, maxima, kind):
    if not _is_builtin_dict(value):
        _raise_structure(kind)
    expected = keys
    keys_present = tuple(value.keys())
    if len(keys_present) != len(expected):
        _raise_structure(kind)
    index = 0
    while index < len(expected):
        wanted = expected[index]
        found = False
        key_index = 0
        while key_index < len(keys_present):
            key = keys_present[key_index]
            if not _is_builtin_str(key):
                _raise_structure(kind)
            if key == wanted:
                found = True
                break
            key_index += 1
        if not found:
            _raise_structure(kind)
        index += 1
    out = {}
    index = 0
    while index < len(expected):
        key = expected[index]
        item = value[key]
        if type(item) is not int or item < 1 or item > maxima[key]:
            _raise_structure(kind)
        out[key] = item
        index += 1
    return out


class _Node:
    __slots__ = (
        "path",
        "name",
        "parent_path",
        "fd",
        "first_stat",
        "absent",
        "stat_error",
        "role",
        "group",
        "authorized_created",
        "data",
        "unsafe_reason",
        "kind",
        "written",
    )

    def __init__(
        self,
        path,
        name,
        parent_path,
        role,
        group,
    ):
        self.path = path
        self.name = name
        self.parent_path = parent_path
        self.fd = None
        self.first_stat = None
        self.absent = False
        self.stat_error = None
        self.role = role
        self.group = group
        self.authorized_created = False
        self.data = None
        self.unsafe_reason = None
        self.kind = "unknown"
        self.written = 0


class _Scan:
    __slots__ = (
        "names",
        "complete",
        "over_cap",
        "error",
        "stats",
        "directory",
        "cap",
        "charged_bytes",
    )

    def __init__(self, directory, cap):
        self.directory = directory
        self.cap = cap
        self.names = []
        self.complete = False
        self.over_cap = False
        self.error = None
        self.stats = {}
        self.charged_bytes = 0


class _ResourceRecord:
    __slots__ = (
        "logical",
        "path",
        "pin",
        "node",
        "data",
        "initial_missing",
        "initial_unsafe",
        "initial_error",
    )

    def __init__(self, logical, path, pin):
        self.logical = logical
        self.path = path
        self.pin = pin
        self.node = None
        self.data = None
        self.initial_missing = False
        self.initial_unsafe = None
        self.initial_error = None


class _InstallRecord:
    __slots__ = (
        "phase",
        "relative_name",
        "payload",
        "temp_name",
        "temp_fd",
        "parent_path",
        "written",
        "link_returned",
        "cleaned_prefix",
        "unlink_attempted",
        "temp_dev",
        "temp_ino",
        "failed",
        "family",
        "final_name",
    )

    def __init__(self):
        self.phase = "idle"
        self.relative_name = None
        self.payload = None
        self.temp_name = None
        self.temp_fd = None
        self.parent_path = None
        self.written = 0
        self.link_returned = False
        self.cleaned_prefix = False
        self.unlink_attempted = False
        self.temp_dev = None
        self.temp_ino = None
        self.failed = False
        self.family = None
        self.final_name = None


class _CheckFailure:
    __slots__ = ("reason", "operation", "errno")

    def __init__(self, reason, operation=None, errno_value=None):
        self.reason = reason
        self.operation = operation
        self.errno = errno_value


class _CodeSession:
    def __init__(self, batch_id):
        self._batch_raw = batch_id
        self._state = "setup"
        self._nodes = {}
        self._fd_order = []
        self._lock_dup_fd = None
        self._checkout_path = None
        self._work_path = None
        self._batch_path = None
        self._output_path = None
        self._reached = set()
        self._resource_records = []
        self._resource_context = None
        self._resource_plan = None
        self._resource_setup_error = None
        self._output_limits = None
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
        self._scans = {}
        self._authorized_adds = {}
        self._authorized_removes = {}
        self._logical_c = 0
        self._install = _InstallRecord()
        self._input_path = None
        self._input_data = None
        self._bundle_rel = None
        self._bundle_root = None
        self._bundle_manifest = None
        self._bundle_bodies = None
        self._bundle_physical = None
        self._git_limits = None
        self._cleanup_error = None
        self._closed_fds = set()
        self._full_verify_count = 0
        self._names_verify_count = 0
        self._schemas_directory = None
        self._profiles_directory = None
        self._unchanged_resource_invalid = False
        self._scan_bytes = 0
        self._original_output_error = None

    def __enter__(self):
        self._state = "setup"
        try:
            self._setup()
            self._state = "active"
            return self
        except BaseException as exc:
            selected = self._finalize(exc)
            if selected is exc:
                raise
            raise selected from None

    def __exit__(self, exc_type, exc, tb):
        selected = self._finalize(exc)
        if selected is None or selected is exc:
            return False
        raise selected from None

    def _require_active(self):
        if self._state != "active":
            raise RuntimeError("CODE session is not active")

    def _require_idle_views(self):
        self._require_active()
        if self._install.phase != "idle":
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase=self._install.phase,
                group="installation",
                reason="phase_mismatch",
            ) from None

    def _mark(self, group):
        self._reached.add(group)

    def _track_fd(self, fd):
        self._fd_order.append(fd)
        return fd

    def _setup(self):
        _require_capabilities(_capability_snapshot())
        if not _is_builtin_str(self._batch_raw) or _BATCH_RE.fullmatch(
            self._batch_raw
        ) is None:
            raise _io_error(
                "INVALID_BATCH_ID",
                phase="setup",
                group=None,
                reason="batch_id",
            ) from None
        try:
            cwd = _getcwd()
        except OSError as exc:
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="syscall_failed",
                operation="stat",
                errno_value=_bound_errno(exc.errno),
            ) from None
        if not _is_canonical_abs(cwd):
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="path_spelling",
            ) from None
        self._checkout_path = cwd
        self._work_path = _join_abs(cwd, ".work")
        self._batch_path = _join_abs(self._work_path, self._batch_raw)
        self._output_path = _join_abs(self._batch_path, "code-evidence-v1")
        self._retain_abs_dir(
            cwd,
            role="checkout",
            group="checkout",
            required=True,
            root_code="WORKSPACE_ROOT_INVALID",
        )
        checkout = self._nodes[cwd]
        if checkout.absent or checkout.unsafe_reason or checkout.fd is None:
            reason = checkout.unsafe_reason or "missing"
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason=reason,
            ) from None
        self._lock_checkout(checkout)
        self._fsync_checkout(checkout)
        self._retain_markers(checkout)
        self._acquire_resources()
        self._scan_output_initial()
        self._verify_full()

    def _raise_os(
        self,
        exc,
        *,
        code,
        phase,
        group,
        operation,
        unsupported=False,
        busy=False,
    ):
        eno = _bound_errno(getattr(exc, "errno", None))
        if busy and eno is not None and eno in _BUSY_ERRNOS:
            raise _io_error(
                "CODE_PROOF_BUSY",
                phase=phase,
                group=group,
                reason="lock_busy",
                operation=operation,
                errno_value=eno,
            ) from None
        if unsupported and eno is not None and eno in _UNSUPPORTED_ERRNOS:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase=phase,
                group=group,
                reason="unavailable_primitive",
                operation=operation,
                errno_value=eno,
            ) from None
        raise _io_error(
            code,
            phase=phase,
            group=group,
            reason="syscall_failed",
            operation=operation,
            errno_value=eno,
        ) from None

    def _retain_root(self):
        self._mark("ancestors")
        if "/" in self._nodes:
            return self._nodes["/"]
        node = _Node("/", "/", None, "root", "ancestors")
        try:
            st = _stat("/", follow_symlinks=False)
        except OSError as exc:
            node.stat_error = exc
            node.absent = False
            self._nodes["/"] = node
            self._raise_os(
                exc,
                code="WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="ancestors",
                operation="stat",
            )
        unsafe = _unsafe_dir_reason(st)
        node.first_stat = st
        if unsafe is not None:
            node.unsafe_reason = unsafe
            node.kind = "unsafe"
            self._nodes["/"] = node
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="ancestors",
                reason=unsafe,
                operation="stat",
            ) from None
        try:
            fd = _open("/", _dir_flags())
        except OSError as exc:
            self._nodes["/"] = node
            self._raise_os(
                exc,
                code="WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="ancestors",
                operation="open",
            )
        self._track_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._nodes["/"] = node
            self._raise_os(
                exc,
                code="WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="ancestors",
                operation="fstat",
            )
        if _dir_stamp(fst) != _dir_stamp(st):
            node.unsafe_reason = "edge_changed"
            self._nodes["/"] = node
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="setup",
                group="ancestors",
                reason="edge_changed",
                operation="fstat",
            ) from None
        node.kind = "dir"
        self._nodes["/"] = node
        return node

    def _observe_child(self, parent, name, path, role, group):
        existing = self._nodes.get(path)
        if existing is not None:
            return existing
        node = _Node(path, name, parent.path, role, group)
        try:
            st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc.errno) == errno_module.ENOENT:
                node.absent = True
                node.kind = "absent"
                self._nodes[path] = node
                return node
            node.stat_error = exc
            self._nodes[path] = node
            self._raise_os(
                exc,
                code="WORK_PATH_UNSAFE",
                phase=self._phase_now(),
                group=group,
                operation="stat",
            )
        node.first_stat = st
        self._nodes[path] = node
        return node

    def _phase_now(self):
        if self._state == "setup":
            return "setup"
        if self._state == "finalizing":
            return "final_verify"
        if self._install.phase != "idle":
            return self._install.phase
        return "retaining"

    def _open_dir_node(self, node, *, exact_mode=None, code="WORK_PATH_UNSAFE"):
        if node.fd is not None:
            return
        parent = self._nodes[node.parent_path]
        unsafe = _unsafe_dir_reason(node.first_stat, exact_mode=exact_mode)
        if unsafe is not None:
            node.unsafe_reason = unsafe
            node.kind = "unsafe"
            raise _io_error(
                code,
                phase=self._phase_now(),
                group=node.group,
                reason=unsafe,
                operation="stat",
            ) from None
        try:
            fd = _open(node.name, _dir_flags(), dir_fd=parent.fd)
        except OSError as exc:
            self._raise_os(
                exc,
                code=code,
                phase=self._phase_now(),
                group=node.group,
                operation="open",
            )
        self._track_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            self._raise_os(
                exc,
                code=code,
                phase=self._phase_now(),
                group=node.group,
                operation="fstat",
            )
        if _dir_stamp(fst) != _dir_stamp(node.first_stat):
            node.unsafe_reason = "edge_changed"
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase=self._phase_now(),
                group=node.group,
                reason="edge_changed",
                operation="fstat",
            ) from None
        node.kind = "dir"

    def _retain_abs_dir(
        self,
        path,
        *,
        role,
        group,
        required,
        exact_mode=None,
        root_code="WORK_PATH_UNSAFE",
        open_dir=True,
    ):
        self._mark("ancestors")
        self._mark(group)
        if not _is_canonical_abs(path):
            raise _io_error(
                root_code,
                phase=self._phase_now(),
                group=group,
                reason="path_spelling",
            ) from None
        parent = self._retain_root()
        sofar = ""
        components = _abs_components(path)
        index = 0
        while index < len(components):
            name = components[index]
            sofar = sofar + "/" + name
            is_last = index == len(components) - 1
            node_role = role if is_last else "ancestor"
            node_group = group if is_last else "ancestors"
            node = self._observe_child(
                parent, name, sofar, node_role, node_group
            )
            if node.absent:
                if required and is_last:
                    raise _io_error(
                        root_code,
                        phase=self._phase_now(),
                        group=group,
                        reason="missing",
                        operation="stat",
                    ) from None
                return node
            if node.stat_error is not None:
                return node
            if not is_last:
                if node.first_stat is None or not _is_dir(node.first_stat):
                    node.unsafe_reason = "unsafe_type"
                    raise _io_error(
                        root_code,
                        phase=self._phase_now(),
                        group="ancestors",
                        reason="unsafe_type",
                        operation="stat",
                    ) from None
                self._open_dir_node(node, code=root_code)
                parent = node
            else:
                if open_dir:
                    self._open_dir_node(
                        node, exact_mode=exact_mode, code=root_code
                    )
                else:
                    unsafe = _unsafe_dir_reason(
                        node.first_stat, exact_mode=exact_mode
                    )
                    if unsafe is not None:
                        node.unsafe_reason = unsafe
                        if required:
                            raise _io_error(
                                root_code,
                                phase=self._phase_now(),
                                group=group,
                                reason=unsafe,
                                operation="stat",
                            ) from None
                return node
            index += 1
        return parent

    def _retain_abs_file(
        self,
        path,
        *,
        role,
        group,
        maximum,
        policy="resource",
        required=True,
        code="WORK_PATH_UNSAFE",
        pin_size=None,
        pin_hash=None,
    ):
        self._mark(group)
        parent_path = path.rsplit("/", 1)[0]
        if parent_path == "":
            parent_path = "/"
        name = path.rsplit("/", 1)[1]
        parent = self._retain_abs_dir(
            parent_path,
            role="ancestor",
            group="ancestors" if group != "checkout" else "checkout",
            required=True,
            root_code=code,
        )
        if parent.absent:
            node = _Node(path, name, parent.path, role, group)
            node.absent = True
            node.kind = "absent"
            self._nodes[path] = node
            return node
        node = self._observe_child(parent, name, path, role, group)
        if node.absent:
            if required:
                raise _io_error(
                    code,
                    phase=self._phase_now(),
                    group=group,
                    reason="missing",
                    operation="stat",
                ) from None
            return node
        exact_mode = 0o600 if policy == "output" else None
        unsafe = _unsafe_file_reason(node.first_stat, exact_mode=exact_mode)
        if unsafe is not None:
            node.unsafe_reason = unsafe
            node.kind = "unsafe"
            return node
        if pin_size is not None and node.first_stat.st_size != pin_size:
            node.unsafe_reason = "resource_hash"
            return node
        if node.first_stat.st_size > maximum:
            return node
        try:
            fd = _open(name, _file_flags(), dir_fd=parent.fd)
        except OSError as exc:
            node.stat_error = exc
            return node
        self._track_fd(fd)
        node.fd = fd
        try:
            fst = _fstat(fd)
        except OSError as exc:
            node.stat_error = exc
            return node
        try:
            if _file_stamp(fst) != _file_stamp(node.first_stat):
                node.unsafe_reason = "edge_changed"
                return node
        except CodeProofIOError:
            raise
        node.kind = "file"
        if node.first_stat.st_size > maximum:
            return node
        try:
            data = self._read_exact(fd, node.first_stat.st_size)
        except CodeProofIOError:
            raise
        except OSError as exc:
            node.stat_error = exc
            return node
        node.data = data
        return node

    def _read_exact(self, fd, size):
        chunks = []
        got = 0
        while got < size:
            try:
                buf = _read(fd, min(_WRITE_CHUNK, size - got))
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase=self._phase_now(),
                    group=None,
                    operation="read",
                )
            if buf == b"":
                raise _io_error(
                    "CODE_PROOF_IO_ERROR",
                    phase=self._phase_now(),
                    group=None,
                    reason="syscall_failed",
                    operation="read",
                ) from None
            chunks.append(buf)
            got += len(buf)
        return b"".join(chunks)

    def _lock_checkout(self, checkout):
        self._mark("checkout")
        try:
            _flock(checkout.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="setup",
                group="checkout",
                operation="flock",
                unsupported=True,
                busy=True,
            )
        try:
            dup_fd = _dup(checkout.fd)
        except OSError as exc:
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="setup",
                group="checkout",
                operation="dup",
                unsupported=True,
            )
        self._lock_dup_fd = dup_fd

    def _fsync_checkout(self, checkout):
        try:
            _fsync(checkout.fd)
        except OSError as exc:
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="setup",
                group="checkout",
                operation="fsync",
                unsupported=True,
            )

    def _retain_markers(self, checkout):
        git_path = _join_abs(self._checkout_path, ".git")
        py_path = _join_abs(self._checkout_path, "pyproject.toml")
        git = self._observe_child(
            checkout, ".git", git_path, "git_marker", "checkout"
        )
        if git.absent or git.stat_error is not None:
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="missing" if git.absent else "syscall_failed",
                operation="stat",
                errno_value=(
                    None
                    if git.stat_error is None
                    else _bound_errno(git.stat_error.errno)
                ),
            ) from None
        st = git.first_stat
        if _is_dir(st):
            self._open_dir_node(
                git, code="WORKSPACE_ROOT_INVALID"
            )
        elif _is_reg(st):
            unsafe = _unsafe_file_reason(st)
            if unsafe is not None:
                git.unsafe_reason = unsafe
                raise _io_error(
                    "WORKSPACE_ROOT_INVALID",
                    phase="setup",
                    group="checkout",
                    reason="marker_invalid",
                    operation="stat",
                ) from None
            if st.st_size > _MAX_GIT_MARKER_BYTES:
                raise _io_error(
                    "WORKSPACE_ROOT_INVALID",
                    phase="setup",
                    group="checkout",
                    reason="marker_invalid",
                    operation="stat",
                ) from None
            node = self._retain_abs_file(
                git_path,
                role="git_marker",
                group="checkout",
                maximum=_MAX_GIT_MARKER_BYTES,
                required=True,
                code="WORKSPACE_ROOT_INVALID",
            )
            if node.unsafe_reason is not None or node.data is None:
                raise _io_error(
                    "WORKSPACE_ROOT_INVALID",
                    phase="setup",
                    group="checkout",
                    reason="marker_invalid",
                    operation="open",
                ) from None
        else:
            git.unsafe_reason = "unsafe_type"
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="marker_invalid",
                operation="stat",
            ) from None
        py_node = self._retain_abs_file(
            py_path,
            role="pyproject",
            group="checkout",
            maximum=_MAX_PYPROJECT_BYTES,
            required=True,
            code="WORKSPACE_ROOT_INVALID",
        )
        if py_node.absent:
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="missing",
                operation="stat",
            ) from None
        if (
            py_node.unsafe_reason is not None
            or py_node.data is None
            or py_node.first_stat is None
            or py_node.first_stat.st_size > _MAX_PYPROJECT_BYTES
        ):
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="marker_invalid",
                operation="open",
            ) from None
        try:
            text = py_node.data.decode("utf-8")
            parsed = tomllib.loads(text)
        except (UnicodeDecodeError, tomllib.TOMLDecodeError, AttributeError):
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            ) from None
        if not _is_builtin_dict(parsed):
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            ) from None
        project = parsed.get("project")
        if not _is_builtin_dict(project) or project.get("name") != "video-paper-wiki":
            raise _io_error(
                "WORKSPACE_ROOT_INVALID",
                phase="setup",
                group="checkout",
                reason="marker_invalid",
            ) from None

    def _acquire_resources(self):
        self._mark("resources")
        try:
            plan = resource_origin_plan()
        except CodeProofResourceError as exc:
            reason = exc.reason
            if reason not in ("resource_origin", "resource_hash", "resource_shape"):
                reason = "resource_origin"
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason=reason,
            )
            self._resource_setup_error = error
            raise error from None
        layout = getattr(plan, "layout", None)
        if layout != "source" and layout != "installed":
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
            self._resource_setup_error = error
            raise error from None
        schemas = _plan_dir_str(plan.schemas_directory)
        profiles = _plan_dir_str(plan.profiles_directory)
        if schemas is None or profiles is None:
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
            self._resource_setup_error = error
            raise error from None
        self._schemas_directory = schemas
        self._profiles_directory = profiles
        self._resource_plan = plan
        if _paths_overlap(schemas, self._output_path) or _paths_overlap(
            profiles, self._output_path
        ):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="setup",
                group="resources",
                reason="overlap",
            ) from None
        pins = getattr(plan, "resources", None)
        try:
            pin_len = len(pins)
        except Exception:
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
            self._resource_setup_error = error
            raise error from None
        if pin_len != 11:
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason="resource_origin",
            )
            self._resource_setup_error = error
            raise error from None
        retained_bytes = {}
        index = 0
        while index < 11:
            pin = pins[index]
            relative = pin.relative_path
            if not _is_builtin_str(relative):
                error = _io_error(
                    "CODE_PROOF_RESOURCE_INVALID",
                    phase="setup",
                    group="resources",
                    reason="resource_origin",
                )
                self._resource_setup_error = error
                raise error from None
            filename = relative.rsplit("/", 1)[-1]
            if relative.startswith("schemas/"):
                directory = schemas
            elif relative.startswith("profiles/"):
                directory = profiles
            else:
                error = _io_error(
                    "CODE_PROOF_RESOURCE_INVALID",
                    phase="setup",
                    group="resources",
                    reason="resource_origin",
                )
                self._resource_setup_error = error
                raise error from None
            path = _join_abs(directory, filename)
            rec = _ResourceRecord(relative, path, pin)
            self._resource_records.append(rec)
            node = self._retain_abs_file(
                path,
                role="resource",
                group="resources",
                maximum=max(int(pin.size_bytes), 1),
                required=False,
                code="CODE_PROOF_RESOURCE_INVALID",
                pin_size=pin.size_bytes,
            )
            rec.node = node
            if node.absent:
                rec.initial_missing = True
                error = _io_error(
                    "CODE_PROOF_RESOURCE_INVALID",
                    phase="setup",
                    group="resources",
                    reason="missing",
                )
                self._resource_setup_error = error
                self._unchanged_resource_invalid = True
                raise error from None
            if node.unsafe_reason is not None:
                rec.initial_unsafe = node.unsafe_reason
                reason = node.unsafe_reason
                if reason not in (
                    "unsafe_type",
                    "unsafe_mode",
                    "link_count",
                    "resource_hash",
                    "edge_changed",
                ):
                    reason = "unsafe_type"
                if reason == "resource_hash":
                    mapped = "resource_hash"
                else:
                    mapped = reason
                code = (
                    "CODE_PROOF_RESOURCE_INVALID"
                    if mapped
                    in (
                        "unsafe_type",
                        "unsafe_mode",
                        "link_count",
                        "resource_hash",
                    )
                    else "WORK_PATH_UNSAFE"
                )
                error = _io_error(
                    code,
                    phase="setup",
                    group="resources",
                    reason=mapped,
                    operation="stat",
                )
                self._resource_setup_error = error
                self._unchanged_resource_invalid = True
                raise error from None
            if node.stat_error is not None:
                rec.initial_error = node.stat_error
                error = _io_error(
                    "CODE_PROOF_RESOURCE_INVALID",
                    phase="setup",
                    group="resources",
                    reason="syscall_failed",
                    operation="open",
                    errno_value=_bound_errno(node.stat_error.errno),
                )
                self._resource_setup_error = error
                self._unchanged_resource_invalid = True
                raise error from None
            if node.data is None:
                error = _io_error(
                    "CODE_PROOF_RESOURCE_INVALID",
                    phase="setup",
                    group="resources",
                    reason="syscall_failed",
                    operation="read",
                )
                self._resource_setup_error = error
                self._unchanged_resource_invalid = True
                raise error from None
            rec.data = node.data
            retained_bytes[relative] = node.data
            index += 1
        try:
            ctx = compile_code_proof_resources(dict(retained_bytes))
        except CodeProofResourceError as exc:
            reason = exc.reason
            if reason not in ("resource_origin", "resource_hash", "resource_shape"):
                reason = "resource_shape"
            error = _io_error(
                "CODE_PROOF_RESOURCE_INVALID",
                phase="setup",
                group="resources",
                reason=reason,
            )
            self._resource_setup_error = error
            self._unchanged_resource_invalid = True
            raise error from None
        self._resource_context = ctx

    def _logical_absent_descendants(self, missing_path):
        names = (
            self._work_path,
            self._batch_path,
            self._output_path,
            _join_abs(self._output_path, "objects"),
            _join_abs(self._output_path, "configs"),
            _join_abs(self._output_path, "handoffs"),
            _join_abs(self._output_path, "request.json"),
            _join_abs(self._output_path, "intent.json"),
            _join_abs(self._output_path, "bundle.json"),
            _join_abs(self._output_path, "observation.json"),
        )
        index = 0
        while index < len(names):
            path = names[index]
            if path == missing_path or path.startswith(missing_path + "/"):
                if path not in self._nodes:
                    name = path.rsplit("/", 1)[-1]
                    parent_path = path.rsplit("/", 1)[0]
                    node = _Node(path, name, parent_path, "output", "output_layout")
                    node.absent = True
                    node.kind = "absent"
                    self._nodes[path] = node
            index += 1

    def _scan_directory(self, node, cap, *, owned_temp=None, group="output_layout"):
        self._mark(group)
        scan = _Scan(node.path, cap)
        if node.absent or node.fd is None:
            scan.complete = False
            self._scans[node.path] = scan
            return scan
        allowance = 0
        if owned_temp is not None:
            allowance = 1
        try:
            iterator = _scandir(node.fd)
        except OSError as exc:
            scan.error = exc
            self._scans[node.path] = scan
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="scan",
                group=group,
                reason="syscall_failed",
                operation="scandir",
                errno_value=_bound_errno(exc.errno),
            ) from None
        count = 0
        try:
            with iterator as entries:
                for entry in entries:
                    count += 1
                    name = entry.name
                    is_owned_temp = (
                        owned_temp is not None and name == owned_temp
                    )
                    limit = cap + allowance
                    if count > limit:
                        scan.over_cap = True
                        if name not in scan.names:
                            scan.names.append(name)
                        break
                    if name not in scan.names:
                        scan.names.append(name)
                    try:
                        st = _stat(
                            name, dir_fd=node.fd, follow_symlinks=False
                        )
                    except OSError as exc:
                        scan.error = exc
                        self._scans[node.path] = scan
                        raise _io_error(
                            "WORK_PATH_UNSAFE",
                            phase="scan",
                            group=group,
                            reason="syscall_failed",
                            operation="stat",
                            errno_value=_bound_errno(exc.errno),
                        ) from None
                    scan.stats[name] = st
                    if _is_reg(st):
                        scan.charged_bytes += st.st_size
                        self._scan_bytes += st.st_size
                    if is_owned_temp:
                        continue
                    if count > cap and not is_owned_temp:
                        scan.over_cap = True
        except CodeProofIOError:
            raise
        except OSError as exc:
            scan.error = exc
            self._scans[node.path] = scan
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="scan",
                group=group,
                reason="syscall_failed",
                operation="scandir",
                errno_value=_bound_errno(exc.errno),
            ) from None
        if not scan.over_cap and scan.error is None:
            scan.complete = True
        self._scans[node.path] = scan
        return scan

    def _scan_output_initial(self):
        self._mark("output_layout")
        work = self._retain_abs_dir(
            self._work_path,
            role="work",
            group="output_layout",
            required=False,
            open_dir=True,
        )
        if work.absent:
            self._logical_absent_descendants(self._work_path)
            self._initial_namespace_present = False
            self._current_namespace_present = False
            return
        if work.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="setup",
                group="output_layout",
                reason=work.unsafe_reason,
                operation="stat",
            ) from None
        batch = self._retain_abs_dir(
            self._batch_path,
            role="batch",
            group="output_layout",
            required=False,
            open_dir=True,
        )
        if batch.absent:
            self._logical_absent_descendants(self._batch_path)
            return
        if batch.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="setup",
                group="output_layout",
                reason=batch.unsafe_reason,
                operation="stat",
            ) from None
        namespace = self._retain_abs_dir(
            self._output_path,
            role="namespace",
            group="output_layout",
            required=False,
            exact_mode=0o700,
            open_dir=True,
        )
        if namespace.absent:
            self._logical_absent_descendants(self._output_path)
            self._initial_namespace_present = False
            self._current_namespace_present = False
            return
        if namespace.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="setup",
                group="output_layout",
                reason=namespace.unsafe_reason,
                operation="stat",
            ) from None
        self._initial_namespace_present = True
        self._current_namespace_present = True
        scan = self._scan_directory(
            namespace, _MAX_NAMESPACE_ENTRIES, group="output_layout"
        )
        if scan.over_cap:
            extra = None
            index = 0
            while index < len(scan.names):
                candidate = scan.names[index]
                if candidate not in _DIRECT_FILES and candidate not in _FAMILY_NAMES:
                    extra = candidate
                    break
                index += 1
            if extra is None:
                extra = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="scan",
                group="output_layout",
                reason="unknown_entry",
                operation="scandir",
            ) from None
        if self._scan_bytes > _MAX_OUTPUT_BYTES:
            raise _limit_error(
                "/output",
                "max_output_peak_bytes",
                _MAX_OUTPUT_BYTES,
                self._scan_bytes,
            ) from None
        self._classify_namespace_scan(namespace, scan, initial=True)
        if self._logical_c > _MAX_OUTPUT_BYTES:
            raise _limit_error(
                "/output",
                "max_output_peak_bytes",
                _MAX_OUTPUT_BYTES,
                self._logical_c,
            ) from None

    def _classify_namespace_scan(self, namespace, scan, *, initial):
        allowed = set(_DIRECT_FILES.keys())
        allowed.update(_FAMILY_NAMES)
        index = 0
        while index < len(scan.names):
            name = scan.names[index]
            st = scan.stats.get(name)
            if name not in allowed:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="output_layout",
                    reason="unknown_entry",
                    operation="stat",
                ) from None
            if name in _FAMILY_NAMES:
                if st is None or not _is_dir(st):
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_layout",
                        reason="unsafe_type",
                        operation="stat",
                    ) from None
                if (st.st_mode & 0o777) != 0o700:
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_layout",
                        reason="unsafe_mode",
                        operation="stat",
                    ) from None
                family_path = _join_abs(self._output_path, name)
                family_node = self._retain_abs_dir(
                    family_path,
                    role="family",
                    group="output_layout",
                    required=True,
                    exact_mode=0o700,
                )
                if initial:
                    self._initial_families[name] = True
                self._current_families[name] = True
                cap = _FAMILY_FILE_CAPS[name][3]
                family_scan = self._scan_directory(
                    family_node, cap, group="output_layout"
                )
                if family_scan.over_cap:
                    pointer = "/objects" if name == "objects" else "/output"
                    limit_name = (
                        "max_objects" if name == "objects" else "max_output_peak_bytes"
                    )
                    limit = cap if name == "objects" else _MAX_OUTPUT_BYTES
                    observed = len(family_scan.names)
                    if name == "objects":
                        raise _limit_error(
                            pointer, limit_name, limit, observed
                        ) from None
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_layout",
                        reason="unknown_entry",
                        operation="scandir",
                    ) from None
                self._classify_family_scan(name, family_node, family_scan, initial=initial)
            else:
                if st is None or not _is_reg(st):
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_layout",
                        reason="unsafe_type",
                        operation="stat",
                    ) from None
                unsafe = _unsafe_file_reason(st, exact_mode=0o600)
                if unsafe is not None:
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_files",
                        reason=unsafe,
                        operation="stat",
                    ) from None
                limit_name, hard, _pointer = _DIRECT_FILES[name]
                if st.st_size > hard:
                    raise _limit_error(
                        "/output",
                        "max_output_peak_bytes",
                        _MAX_OUTPUT_BYTES,
                        st.st_size,
                    ) from None
                path = _join_abs(self._output_path, name)
                node = self._retain_abs_file(
                    path,
                    role="output_file",
                    group="output_files",
                    maximum=hard,
                    policy="output",
                    required=True,
                )
                if node.data is None or node.unsafe_reason is not None:
                    reason = node.unsafe_reason or "syscall_failed"
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="scan",
                        group="output_files",
                        reason=reason,
                        operation="open",
                    ) from None
                self._mark("output_files")
                if initial:
                    self._initial_files[name] = node.data
                self._current_files[name] = node.data
                self._logical_c += len(node.data)
            index += 1
        for family in _FAMILY_NAMES:
            path = _join_abs(self._output_path, family)
            if path not in self._nodes:
                node = _Node(path, family, self._output_path, "family", "output_layout")
                node.absent = True
                node.kind = "absent"
                self._nodes[path] = node
        for direct in _DIRECT_FILES:
            path = _join_abs(self._output_path, direct)
            if path not in self._nodes:
                node = _Node(
                    path, direct, self._output_path, "output_file", "output_files"
                )
                node.absent = True
                node.kind = "absent"
                self._nodes[path] = node

    def _classify_family_scan(self, family, family_node, scan, *, initial):
        agg = 0
        index = 0
        while index < len(scan.names):
            name = scan.names[index]
            st = scan.stats.get(name)
            valid = False
            if family == "objects":
                valid = _object_body_name(name)
            else:
                valid = _HEX64_JSON_RE.fullmatch(name) is not None
            if not valid:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="output_layout",
                    reason="unknown_entry",
                    operation="stat",
                ) from None
            if st is None or not _is_reg(st):
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="output_layout",
                    reason="unsafe_type",
                    operation="stat",
                ) from None
            unsafe = _unsafe_file_reason(st, exact_mode=0o600)
            if unsafe is not None:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="output_files",
                    reason=unsafe,
                    operation="stat",
                ) from None
            _limit_name, hard, _pointer, _max_files = _FAMILY_FILE_CAPS[family]
            if st.st_size > hard:
                raise _limit_error(
                    "/output",
                    "max_output_peak_bytes",
                    _MAX_OUTPUT_BYTES,
                    st.st_size,
                ) from None
            agg += st.st_size
            if family == "objects" and agg > _MAX_TOTAL_OBJECT_BYTES:
                raise _limit_error(
                    "/objects",
                    "max_total_object_bytes",
                    _MAX_TOTAL_OBJECT_BYTES,
                    agg,
                ) from None
            rel = family + "/" + name
            path = _join_abs(family_node.path, name)
            node = self._retain_abs_file(
                path,
                role="output_file",
                group="output_files",
                maximum=hard,
                policy="output",
                required=True,
            )
            if node.data is None or node.unsafe_reason is not None:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="output_files",
                    reason=node.unsafe_reason or "syscall_failed",
                    operation="open",
                ) from None
            self._mark("output_files")
            if initial:
                self._initial_files[rel] = node.data
            self._current_files[rel] = node.data
            self._logical_c += len(node.data)
            index += 1

    def _inode_of(self, node):
        if node is None or node.first_stat is None:
            return None
        return (node.first_stat.st_dev, node.first_stat.st_ino)

    def _overlap_with_output(self, path, node=None):
        if _paths_overlap(path, self._output_path):
            return True
        if node is not None and node.first_stat is not None:
            output_ids = []
            for key in (
                self._output_path,
                _join_abs(self._output_path, "objects"),
                _join_abs(self._output_path, "configs"),
                _join_abs(self._output_path, "handoffs"),
            ):
                other = self._nodes.get(key)
                if other is not None and other.first_stat is not None:
                    output_ids.append(self._inode_of(other))
            ident = self._inode_of(node)
            index = 0
            while index < len(output_ids):
                if ident == output_ids[index]:
                    return True
                index += 1
        return False

    def snapshot(self):
        self._require_idle_views()
        self._verify_names()
        out = {}
        for name in sorted(self._current_files.keys()):
            out[name] = bytes(self._current_files[name])
        return out

    def layout_state(self):
        self._require_idle_views()
        self._verify_names()
        current_bytes = {}
        for name in sorted(self._current_files.keys()):
            current_bytes[name] = len(self._current_files[name])
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
            "initial_files": sorted(self._initial_files.keys()),
            "current_files": sorted(self._current_files.keys()),
            "current_file_bytes": current_bytes,
        }

    def retain_input(self, path, *, maximum):
        self._require_active()
        if not _is_builtin_str(path):
            _raise_structure("type")
        if type(maximum) is not int or (
            maximum != _MAX_REQUEST_INPUT_BYTES
            and maximum != _MAX_OBSERVE_INPUT_BYTES
        ):
            _raise_structure("limits")
        self._mark("metadata")
        if self._input_path is not None:
            raise _conflict_error("/input", "acquisition_changed") from None
        if _is_canonical_abs(path):
            abs_path = path
        elif _is_canonical_rel(path):
            abs_path = _join_abs(self._checkout_path, path)
        else:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="metadata",
                reason="path_spelling",
            ) from None
        if self._overlap_with_output(abs_path):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="metadata",
                reason="overlap",
            ) from None
        limit_name = (
            "max_request_input_bytes"
            if maximum == _MAX_REQUEST_INPUT_BYTES
            else "max_observe_input_bytes"
        )
        node = self._retain_abs_file(
            abs_path,
            role="metadata",
            group="metadata",
            maximum=maximum,
            required=True,
            code="WORK_PATH_UNSAFE",
        )
        if node.absent:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="metadata",
                reason="missing",
                operation="stat",
            ) from None
        if node.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="metadata",
                reason=node.unsafe_reason,
                operation="stat",
            ) from None
        if node.first_stat is not None and node.first_stat.st_size > maximum:
            raise _limit_error(
                "/input",
                limit_name,
                maximum,
                node.first_stat.st_size,
            ) from None
        if node.data is None:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="retaining",
                group="metadata",
                reason="syscall_failed",
                operation="read",
            ) from None
        if len(node.data) > maximum:
            raise _limit_error(
                "/input",
                limit_name,
                maximum,
                len(node.data),
            ) from None
        self._input_path = abs_path
        self._input_data = node.data
        return bytes(node.data)

    def _check_bundle_spelling(self, relative_directory):
        if not _is_builtin_str(relative_directory):
            _raise_structure("type")
        value = relative_directory
        if len(value) > 4096:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        if not value.startswith(".work/"):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        if value.endswith("/") or "//" in value:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        rest = value[6:]
        if rest == "":
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        parts = rest.split("/")
        index = 0
        while index < len(parts):
            part = parts[index]
            if part == "" or part == "." or part == "..":
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="retaining",
                    group="bundle",
                    reason="path_spelling",
                ) from None
            char_index = 0
            while char_index < len(part):
                if _control_forbidden(part[char_index]):
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="retaining",
                        group="bundle",
                        reason="path_spelling",
                    ) from None
                char_index += 1
            index += 1
        nfc = unicodedata.normalize("NFC", value)
        if nfc != value:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        try:
            encoded = value.encode("utf-8")
            nfc_encoded = nfc.encode("utf-8")
        except UnicodeEncodeError:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None
        if len(encoded) > _MAX_BUNDLE_PATH_BYTES or len(nfc_encoded) > _MAX_BUNDLE_PATH_BYTES:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="path_spelling",
            ) from None

    def retain_bundle_manifest(self, relative_directory):
        self._require_active()
        self._mark("bundle")
        if self._bundle_rel is not None:
            raise _conflict_error("/bundle", "acquisition_changed") from None
        self._check_bundle_spelling(relative_directory)
        abs_root = _join_abs(self._checkout_path, relative_directory)
        if self._overlap_with_output(abs_root):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="overlap",
            ) from None
        root = self._retain_abs_dir(
            abs_root,
            role="bundle_root",
            group="bundle",
            required=True,
        )
        if root.absent:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="missing",
                operation="stat",
            ) from None
        root_scan = self._scan_directory(
            root, _MAX_BUNDLE_ROOT_ENTRIES, group="bundle"
        )
        if root_scan.over_cap:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="scan",
                group="bundle",
                reason="unknown_entry",
                operation="scandir",
            ) from None
        names = set(root_scan.names)
        if names != {"manifest.json", "objects"}:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="scan",
                group="bundle",
                reason="unknown_entry",
                operation="stat",
            ) from None
        objects_path = _join_abs(abs_root, "objects")
        objects_node = self._retain_abs_dir(
            objects_path,
            role="bundle_objects",
            group="bundle",
            required=True,
        )
        if objects_node.absent or not _is_dir(objects_node.first_stat):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="unsafe_type" if not objects_node.absent else "missing",
                operation="stat",
            ) from None
        obj_scan = self._scan_directory(
            objects_node, _MAX_OBJECTS, group="bundle"
        )
        if obj_scan.over_cap:
            raise _limit_error(
                "/objects",
                "max_objects",
                _MAX_OBJECTS,
                len(obj_scan.names),
            ) from None
        physical = {}
        agg = 0
        index = 0
        while index < len(obj_scan.names):
            name = obj_scan.names[index]
            st = obj_scan.stats[name]
            if not _object_body_name(name):
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="bundle",
                    reason="unknown_entry",
                    operation="stat",
                ) from None
            unsafe = _unsafe_file_reason(st)
            if unsafe is not None:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="scan",
                    group="bundle",
                    reason=unsafe,
                    operation="stat",
                ) from None
            if st.st_size > _MAX_OBJECT_BYTES:
                raise _limit_error(
                    "/objects",
                    "max_object_bytes",
                    _MAX_OBJECT_BYTES,
                    st.st_size,
                ) from None
            agg += st.st_size
            if agg > _MAX_TOTAL_OBJECT_BYTES:
                raise _limit_error(
                    "/objects",
                    "max_total_object_bytes",
                    _MAX_TOTAL_OBJECT_BYTES,
                    agg,
                ) from None
            oid = _oid_from_body_name(name)
            physical[oid] = name
            body_path = _join_abs(objects_path, name)
            if body_path not in self._nodes:
                node = _Node(
                    body_path, name, objects_path, "bundle_body", "bundle"
                )
                node.first_stat = st
                node.kind = "file"
                self._nodes[body_path] = node
            index += 1
        cap = _MAX_BUNDLE_BYTES
        if self._output_limits is not None:
            cap = self._output_limits["max_bundle_bytes"]
        manifest_path = _join_abs(abs_root, "manifest.json")
        manifest_node = self._retain_abs_file(
            manifest_path,
            role="bundle_manifest",
            group="bundle",
            maximum=cap,
            required=True,
            code="WORK_PATH_UNSAFE",
        )
        if manifest_node.absent:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="missing",
                operation="stat",
            ) from None
        if manifest_node.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason=manifest_node.unsafe_reason,
                operation="stat",
            ) from None
        if (
            manifest_node.first_stat is not None
            and manifest_node.first_stat.st_size > cap
        ):
            raise _limit_error(
                "/bundle",
                "max_bundle_bytes",
                cap,
                manifest_node.first_stat.st_size,
            ) from None
        if manifest_node.data is None:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="retaining",
                group="bundle",
                reason="syscall_failed",
                operation="read",
            ) from None
        self._bundle_rel = relative_directory
        self._bundle_root = abs_root
        self._bundle_manifest = manifest_node.data
        self._bundle_physical = physical
        return bytes(manifest_node.data)

    def retain_bundle_bodies(self, *, object_format, objects, limits):
        self._require_active()
        self._mark("bundle")
        if self._bundle_root is None or self._bundle_physical is None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="phase_mismatch",
            ) from None
        if self._bundle_bodies is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason="phase_mismatch",
            ) from None
        if not _is_builtin_str(object_format):
            _raise_structure("type")
        if object_format != "sha1" and object_format != "sha256":
            _raise_structure("shape")
        if not _is_builtin_list(objects):
            _raise_structure("type")
        git_limits = _closed_positive_map(
            limits, _GIT_LIMIT_KEYS, _GIT_LIMIT_MAXIMA, "limits"
        )
        width = 40 if object_format == "sha1" else 64
        declared = []
        declared_set = []
        index = 0
        while index < len(objects):
            item = objects[index]
            if not _is_builtin_dict(item):
                _raise_structure("type")
            oid = item.get("oid")
            object_type = item.get("object_type")
            body_size = item.get("body_size_bytes")
            body_sha = item.get("body_sha256")
            framed_sha = item.get("framed_sha256")
            if not _is_builtin_str(oid) or not _is_builtin_str(object_type):
                _raise_structure("type")
            if type(body_size) is not int:
                _raise_structure("type")
            if not _is_builtin_str(body_sha) or not _is_builtin_str(framed_sha):
                _raise_structure("type")
            if object_type != "commit" and object_type != "tree" and object_type != "blob":
                _raise_structure("shape")
            if len(oid) != width or (
                _OID40_RE.fullmatch(oid) is None and _OID64_RE.fullmatch(oid) is None
            ):
                _raise_structure("shape")
            if width == 40 and _OID40_RE.fullmatch(oid) is None:
                _raise_structure("shape")
            if width == 64 and _OID64_RE.fullmatch(oid) is None:
                _raise_structure("shape")
            if _OID64_RE.fullmatch(body_sha) is None or _OID64_RE.fullmatch(framed_sha) is None:
                _raise_structure("shape")
            if oid in declared_set:
                _raise_structure("shape")
            declared.append(
                {
                    "oid": oid,
                    "object_type": object_type,
                    "body_size_bytes": body_size,
                    "body_sha256": body_sha,
                    "framed_sha256": framed_sha,
                }
            )
            declared_set.append(oid)
            index += 1
        max_objects = git_limits["max_objects"]
        if len(declared) > max_objects:
            raise _limit_error(
                "/objects",
                "max_objects",
                max_objects,
                len(declared),
            ) from None
        index = 0
        agg = 0
        while index < len(declared):
            size = declared[index]["body_size_bytes"]
            if size < 0:
                _raise_structure("shape")
            if size > git_limits["max_object_bytes"]:
                raise _limit_error(
                    "/objects/" + str(index) + "/body_size_bytes",
                    "max_object_bytes",
                    git_limits["max_object_bytes"],
                    size,
                ) from None
            agg += size
            if agg > git_limits["max_total_object_bytes"]:
                raise _limit_error(
                    "/objects",
                    "max_total_object_bytes",
                    git_limits["max_total_object_bytes"],
                    agg,
                ) from None
            index += 1
        lineage = self._bundle_set_lineage()
        if lineage is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="retaining",
                group="bundle",
                reason=lineage.reason,
                operation=lineage.operation,
                errno_value=lineage.errno,
            ) from None
        physical = self._bundle_physical
        physical_count = len(physical)
        if physical_count > max_objects:
            raise _limit_error(
                "/bodies",
                "max_objects",
                max_objects,
                physical_count,
            ) from None
        for oid in physical.keys():
            if len(oid) != width:
                raise _make_git_error(
                    CODE_PROOF_INPUT_INVALID,
                    "code git proof input is invalid",
                    {
                        "instance_pointer": "/bodies",
                        "reason": "invalid_oid_key",
                    },
                ) from None
        extra = []
        for oid in physical.keys():
            if oid not in declared_set:
                extra.append(oid)
        if extra:
            extra_sorted = sorted(extra)
            raise _make_git_error(
                CODE_PROOF_OBJECT_EXTRA,
                "undeclared git object bodies were supplied",
                {
                    "instance_pointer": "/bodies",
                    "extra_oids": extra_sorted,
                },
            ) from None
        missing = []
        index = 0
        while index < len(declared_set):
            oid = declared_set[index]
            if oid not in physical:
                missing.append(oid)
            index += 1
        if missing:
            raise _make_git_error(
                CODE_PROOF_OBJECT_UNAVAILABLE,
                "required git object is unavailable",
                {
                    "instance_pointer": "/bodies",
                    "missing_oids": sorted(missing),
                },
            ) from None
        bodies = {}
        objects_path = _join_abs(self._bundle_root, "objects")
        objects_node = self._nodes[objects_path]
        running = 0
        index = 0
        while index < len(declared):
            rec = declared[index]
            oid = rec["oid"]
            name = physical[oid]
            path = _join_abs(objects_path, name)
            node = self._nodes[path]
            parent = objects_node
            try:
                fd = _open(name, _file_flags(), dir_fd=parent.fd)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="retaining",
                    group="bundle",
                    operation="open",
                )
            self._track_fd(fd)
            node.fd = fd
            try:
                fst = _fstat(fd)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="retaining",
                    group="bundle",
                    operation="fstat",
                )
            if _file_stamp(fst) != _file_stamp(node.first_stat):
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="retaining",
                    group="bundle",
                    reason="edge_changed",
                    operation="fstat",
                ) from None
            size = node.first_stat.st_size
            if size > git_limits["max_object_bytes"]:
                raise _limit_error(
                    "/objects/" + str(index) + "/body_size_bytes",
                    "max_object_bytes",
                    git_limits["max_object_bytes"],
                    size,
                ) from None
            running += size
            if running > git_limits["max_total_object_bytes"]:
                raise _limit_error(
                    "/objects",
                    "max_total_object_bytes",
                    git_limits["max_total_object_bytes"],
                    running,
                ) from None
            data = self._read_exact(fd, size)
            node.data = data
            bodies[oid] = data
            index += 1
        self._bundle_bodies = bodies
        self._git_limits = git_limits
        out = {}
        for oid in bodies.keys():
            out[oid] = bytes(bodies[oid])
        return out

    def _bundle_set_lineage(self):
        objects_path = _join_abs(self._bundle_root, "objects")
        node = self._nodes.get(objects_path)
        if node is None or node.fd is None:
            return _CheckFailure("set_changed", "stat")
        try:
            scan = self._scan_directory(node, _MAX_OBJECTS, group="bundle")
        except CodeProofIOError as exc:
            if exc.code == "WORK_PATH_UNSAFE":
                return _CheckFailure(
                    exc.details["reason"],
                    exc.details["operation"],
                    exc.details["errno"],
                )
            raise
        current = set(scan.names)
        expected = set()
        for oid in self._bundle_physical.keys():
            expected.add(self._bundle_physical[oid])
        if current != expected:
            return _CheckFailure("set_changed", "scandir")
        for name in scan.names:
            path = _join_abs(objects_path, name)
            first = self._nodes[path]
            st = scan.stats[name]
            try:
                if _file_stamp(st) != _file_stamp(first.first_stat):
                    return _CheckFailure("edge_changed", "stat")
            except CodeProofIOError as exc:
                return _CheckFailure("edge_changed", "stat")
        return None

    def set_output_limits(self, limits):
        self._require_active()
        if self._output_limits is not None:
            raise RuntimeError("CODE output limits are already set")
        selected = _closed_positive_map(
            limits, _OUTPUT_LIMIT_KEYS, _OUTPUT_LIMIT_MAXIMA, "limits"
        )
        total = 0
        for name in self._current_files.keys():
            data = self._current_files[name]
            size = len(data)
            total += size
            parsed = _parse_install_name(name)
            if parsed is None:
                continue
            _kind, _base, _family, limit_name, _hard, _pointer = parsed
            cap = selected[limit_name] if limit_name in selected else selected[
                "max_output_peak_bytes"
            ]
            if limit_name in selected and size > cap:
                raise _limit_error(
                    "/output",
                    limit_name,
                    cap,
                    size,
                ) from None
        if total > selected["max_output_peak_bytes"]:
            raise _limit_error(
                "/output",
                "max_output_peak_bytes",
                selected["max_output_peak_bytes"],
                total,
            ) from None
        if self._bundle_manifest is not None:
            size = len(self._bundle_manifest)
            if size > selected["max_bundle_bytes"]:
                raise _limit_error(
                    "/bundle",
                    "max_bundle_bytes",
                    selected["max_bundle_bytes"],
                    size,
                ) from None
        self._output_limits = selected

    def install(self, relative_name, payload):
        self._require_active()
        if self._install.phase != "idle" or self._install.failed:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase=self._install.phase,
                group="installation",
                reason="phase_mismatch",
            ) from None
        if self._output_limits is None:
            raise RuntimeError("CODE output limits are not set")
        if not _is_builtin_str(relative_name):
            _raise_structure("type")
        if not _is_builtin_bytes(payload):
            _raise_structure("type")
        parsed = _parse_install_name(relative_name)
        if parsed is None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="installation",
                group="installation",
                reason="path_spelling",
            ) from None
        kind, base, family, limit_name, hard, pointer = parsed
        cap = self._output_limits[limit_name] if limit_name in self._output_limits else hard
        if limit_name == "max_object_bytes":
            cap = min(hard, cap) if False else hard
            if self._git_limits is not None:
                cap = self._git_limits["max_object_bytes"]
            else:
                cap = hard
        elif limit_name in self._output_limits:
            cap = self._output_limits[limit_name]
        size = len(payload)
        if size > cap:
            raise _limit_error(pointer, limit_name, cap, size) from None
        reuse = False
        if relative_name in self._initial_files:
            if self._initial_files[relative_name] == payload:
                reuse = True
            else:
                raise _conflict_error(pointer, "artifact_changed") from None
        peak = self._output_limits["max_output_peak_bytes"]
        if not reuse:
            observed = self._logical_c + (2 * size)
            if observed > peak:
                raise _limit_error(
                    "/output",
                    "max_output_peak_bytes",
                    peak,
                    observed,
                ) from None
        self._verify_full()
        if reuse:
            path = self._output_file_path(relative_name, family, base)
            node = self._nodes.get(path)
            if node is None or node.data != payload:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_files",
                    reason="bytes_changed",
                ) from None
            return True
        self._mark("installation")
        rec = self._install
        rec.phase = "idle"
        rec.relative_name = relative_name
        rec.payload = payload
        rec.family = family
        rec.final_name = base if family is not None else relative_name
        rec.failed = False
        try:
            parent = self._ensure_install_parent(family)
            rec.parent_path = parent.path
            observed = self._logical_c + (2 * size)
            if observed > peak:
                raise _limit_error(
                    "/output",
                    "max_output_peak_bytes",
                    peak,
                    observed,
                ) from None
            self._create_temp_and_write(rec, parent, payload)
            self._publish_temp(rec, parent)
            rec.phase = "idle"
            return False
        except BaseException:
            rec.failed = True
            raise

    def _output_file_path(self, relative_name, family, base):
        if family is None:
            return _join_abs(self._output_path, relative_name)
        return _join_abs(self._output_path, family, base)

    def _ensure_named_dir(self, path, *, role, exact_mode, create_mode):
        parent_path = path.rsplit("/", 1)[0]
        name = path.rsplit("/", 1)[1]
        parent = self._nodes[parent_path]
        node = self._nodes.get(path)
        if node is None:
            node = self._observe_child(
                parent, name, path, role, "output_layout"
            )
        if node.absent:
            self._verify_names()
            if not node.absent:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    reason="late_arrival",
                    operation="stat",
                ) from None
            raised = None
            present_after = False
            try:
                _mkdir(name, create_mode, dir_fd=parent.fd)
            except OSError as exc:
                raised = exc
                try:
                    st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
                    present_after = True
                    if node.first_stat is None:
                        node.first_stat = st
                        node.absent = False
                except OSError:
                    present_after = False
                if present_after:
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="installation",
                        group="output_layout",
                        reason="late_arrival",
                        operation="mkdir",
                        errno_value=_bound_errno(exc.errno),
                    ) from None
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="installation",
                    group="output_layout",
                    operation="mkdir",
                )
            try:
                st = _stat(name, dir_fd=parent.fd, follow_symlinks=False)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    operation="stat",
                )
            node.absent = False
            node.first_stat = st
            unsafe = _unsafe_dir_reason(st, exact_mode=exact_mode)
            if unsafe is not None:
                node.unsafe_reason = unsafe
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    reason=unsafe,
                    operation="stat",
                ) from None
            try:
                fd = _open(name, _dir_flags(), dir_fd=parent.fd)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    operation="open",
                )
            self._track_fd(fd)
            node.fd = fd
            try:
                fst = _fstat(fd)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    operation="fstat",
                )
            if _dir_stamp(fst) != _dir_stamp(st):
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="installation",
                    group="output_layout",
                    reason="edge_changed",
                    operation="fstat",
                ) from None
            node.kind = "dir"
            node.authorized_created = True
            try:
                _fsync(parent.fd)
            except OSError as exc:
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="installation",
                    group="output_layout",
                    operation="fsync",
                    unsupported=True,
                )
            self._scan_directory(node, 2048, group="output_layout")
            return node
        if node.unsafe_reason is not None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="installation",
                group="output_layout",
                reason=node.unsafe_reason,
            ) from None
        if node.fd is None:
            self._open_dir_node(node, exact_mode=exact_mode)
        return node

    def _ensure_install_parent(self, family):
        checkout = self._nodes[self._checkout_path]
        if checkout.fd is None:
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="installation",
                group="checkout",
                reason="missing",
            ) from None
        work = self._ensure_named_dir(
            self._work_path, role="work", exact_mode=None, create_mode=0o700
        )
        batch = self._ensure_named_dir(
            self._batch_path, role="batch", exact_mode=None, create_mode=0o700
        )
        namespace = self._ensure_named_dir(
            self._output_path,
            role="namespace",
            exact_mode=0o700,
            create_mode=0o700,
        )
        self._current_namespace_present = True
        if family is None:
            return namespace
        family_path = _join_abs(self._output_path, family)
        family_node = self._ensure_named_dir(
            family_path,
            role="family",
            exact_mode=0o700,
            create_mode=0o700,
        )
        self._current_families[family] = True
        adds = self._authorized_adds.setdefault(self._output_path, set())
        adds.add(family)
        return family_node

    def _create_temp_and_write(self, rec, parent, payload):
        attempts = 0
        temp_name = None
        fd = None
        while attempts < 8:
            temp_name = _TEMP_PREFIX + os.urandom(16).hex()
            try:
                fd = _open(
                    temp_name,
                    _temp_flags(),
                    0o600,
                    dir_fd=parent.fd,
                )
                break
            except OSError as exc:
                if _bound_errno(exc.errno) == errno_module.EEXIST:
                    attempts += 1
                    continue
                rec.failed = True
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="installation",
                    group="installation",
                    operation="open",
                )
        if fd is None:
            rec.failed = True
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="installation",
                group="installation",
                reason="syscall_failed",
                operation="open",
            ) from None
        self._track_fd(fd)
        rec.temp_name = temp_name
        rec.temp_fd = fd
        rec.phase = "temp_created"
        path = _join_abs(parent.path, temp_name)
        node = _Node(path, temp_name, parent.path, "temp", "installation")
        try:
            st = _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
            fst = _fstat(fd)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="temp_created",
                group="installation",
                operation="stat",
            )
        if _file_stamp(st) != _file_stamp(fst):
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_created",
                group="installation",
                reason="edge_changed",
                operation="fstat",
            ) from None
        node.first_stat = st
        node.fd = fd
        node.kind = "file"
        rec.temp_dev = st.st_dev
        rec.temp_ino = st.st_ino
        self._nodes[path] = node
        rec.phase = "writing"
        view = memoryview(payload)
        written = 0
        while written < len(payload):
            end = written + _WRITE_CHUNK
            if end > len(payload):
                end = len(payload)
            chunk = bytes(view[written:end])
            try:
                n = _write(fd, chunk)
            except OSError as exc:
                rec.written = written
                rec.failed = True
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase="writing",
                    group="installation",
                    operation="write",
                )
            if n == 0:
                rec.written = written
                rec.failed = True
                raise _io_error(
                    "CODE_PROOF_IO_ERROR",
                    phase="writing",
                    group="installation",
                    reason="zero_write",
                    operation="write",
                ) from None
            written += n
            rec.written = written
            self._verify_names()
        rec.phase = "temp_ready"
        try:
            _seek(fd, 0, os.SEEK_SET)
            data = self._read_exact(fd, len(payload))
            fst = _fstat(fd)
            named = _stat(temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="temp_ready",
                group="installation",
                operation="read",
            )
        if data != payload:
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_ready",
                group="installation",
                reason="bytes_changed",
                operation="read",
            ) from None
        if (fst.st_mode & 0o777) != 0o600 or not _is_reg(fst) or fst.st_nlink != 1:
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_ready",
                group="installation",
                reason="unsafe_mode" if (fst.st_mode & 0o777) != 0o600 else "link_count",
                operation="fstat",
            ) from None
        if (fst.st_dev, fst.st_ino) != (rec.temp_dev, rec.temp_ino):
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_ready",
                group="installation",
                reason="temp_ownership_lost",
                operation="fstat",
            ) from None
        node.data = payload
        node.first_stat = named
        self._verify_full()
        try:
            _fsync(fd)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="temp_ready",
                group="installation",
                operation="fsync",
                unsupported=True,
            )

    def _publish_temp(self, rec, parent):
        final_name = rec.final_name
        final_path = _join_abs(parent.path, final_name)
        existing = self._nodes.get(final_path)
        if existing is not None and not existing.absent:
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_ready",
                group="installation",
                reason="late_arrival",
                operation="stat",
            ) from None
        self._verify_names()
        try:
            current = _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="temp_ready",
                group="installation",
                reason="late_arrival",
                operation="stat",
            ) from None
        except OSError as exc:
            if _bound_errno(exc.errno) != errno_module.ENOENT:
                rec.failed = True
                self._raise_os(
                    exc,
                    code="WORK_PATH_UNSAFE",
                    phase="temp_ready",
                    group="installation",
                    operation="stat",
                )
        try:
            _link(
                rec.temp_name,
                final_name,
                src_dir_fd=parent.fd,
                dst_dir_fd=parent.fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            present = False
            try:
                _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
                present = True
            except OSError:
                present = False
            rec.failed = True
            if present:
                raise _io_error(
                    "WORK_PATH_UNSAFE",
                    phase="temp_ready",
                    group="installation",
                    reason="late_arrival",
                    operation="link",
                    errno_value=_bound_errno(exc.errno),
                ) from None
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="temp_ready",
                group="installation",
                operation="link",
            )
        rec.link_returned = True
        try:
            named_final = _stat(
                final_name, dir_fd=parent.fd, follow_symlinks=False
            )
            named_temp = _stat(
                rec.temp_name, dir_fd=parent.fd, follow_symlinks=False
            )
            fst = _fstat(rec.temp_fd)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="WORK_PATH_UNSAFE",
                phase="linked",
                group="installation",
                operation="stat",
            )
        if (
            (named_final.st_dev, named_final.st_ino)
            != (rec.temp_dev, rec.temp_ino)
            or (named_temp.st_dev, named_temp.st_ino)
            != (rec.temp_dev, rec.temp_ino)
            or (fst.st_dev, fst.st_ino) != (rec.temp_dev, rec.temp_ino)
            or named_final.st_nlink != 2
            or fst.st_nlink != 2
            or (fst.st_mode & 0o777) != 0o600
        ):
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="linked",
                group="installation",
                reason="edge_changed",
                operation="stat",
            ) from None
        rec.phase = "linked"
        rec.unlink_attempted = True
        try:
            _unlink(rec.temp_name, dir_fd=parent.fd)
        except OSError as exc:
            rec.failed = True
            temp_present = False
            try:
                still = _stat(
                    rec.temp_name, dir_fd=parent.fd, follow_symlinks=False
                )
                temp_present = True
                same = (still.st_dev, still.st_ino) == (rec.temp_dev, rec.temp_ino)
            except OSError as absent_exc:
                if _bound_errno(absent_exc.errno) == errno_module.ENOENT:
                    temp_present = False
                    same = False
                else:
                    self._raise_os(
                        absent_exc,
                        code="CODE_PROOF_IO_ERROR",
                        phase="linked",
                        group="installation",
                        operation="stat",
                    )
            if not temp_present:
                try:
                    final_st = _stat(
                        final_name, dir_fd=parent.fd, follow_symlinks=False
                    )
                    if (
                        (final_st.st_dev, final_st.st_ino)
                        == (rec.temp_dev, rec.temp_ino)
                        and final_st.st_nlink == 1
                    ):
                        rec.cleaned_prefix = True
                        rec.phase = "cleaned"
                except OSError:
                    pass
                self._raise_os(
                    exc,
                    code="CODE_PROOF_IO_ERROR",
                    phase=rec.phase,
                    group="installation",
                    operation="unlink",
                )
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="linked",
                group="installation",
                operation="unlink",
            )
        try:
            _stat(rec.temp_name, dir_fd=parent.fd, follow_symlinks=False)
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="linked",
                group="installation",
                reason="temp_ownership_lost",
                operation="stat",
            ) from None
        except OSError as exc:
            if _bound_errno(exc.errno) != errno_module.ENOENT:
                rec.failed = True
                self._raise_os(
                    exc,
                    code="WORK_PATH_UNSAFE",
                    phase="linked",
                    group="installation",
                    operation="stat",
                )
        try:
            final_st = _stat(final_name, dir_fd=parent.fd, follow_symlinks=False)
            fst = _fstat(rec.temp_fd)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="WORK_PATH_UNSAFE",
                phase="cleaned",
                group="installation",
                operation="stat",
            )
        if (
            (final_st.st_dev, final_st.st_ino) != (rec.temp_dev, rec.temp_ino)
            or final_st.st_nlink != 1
            or not _is_reg(final_st)
            or (final_st.st_mode & 0o777) != 0o600
        ):
            rec.failed = True
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="cleaned",
                group="installation",
                reason="edge_changed",
                operation="stat",
            ) from None
        rec.phase = "cleaned"
        rec.cleaned_prefix = True
        final_node = _Node(
            final_path, final_name, parent.path, "output_file", "output_files"
        )
        final_node.first_stat = final_st
        final_node.fd = rec.temp_fd
        final_node.data = rec.payload
        final_node.kind = "file"
        final_node.authorized_created = True
        self._nodes[final_path] = final_node
        self._current_files[rec.relative_name] = rec.payload
        self._logical_c += len(rec.payload)
        adds = self._authorized_adds.setdefault(parent.path, set())
        adds.add(final_name)
        temp_path = _join_abs(parent.path, rec.temp_name)
        removes = self._authorized_removes.setdefault(parent.path, set())
        removes.add(rec.temp_name)
        self._verify_full()
        try:
            _fsync(parent.fd)
        except OSError as exc:
            rec.failed = True
            self._raise_os(
                exc,
                code="CODE_PROOF_IO_ERROR",
                phase="cleaned",
                group="installation",
                operation="fsync",
                unsupported=True,
            )
        self._verify_full()
        rec.phase = "durable"

    def verify(self):
        self._require_active()
        self._verify_full()

    def validate_structure(self, title, instance):
        self._require_active()
        return self._resource_context.validate_structure(title, instance)

    def materialize_limits(self, value):
        self._require_active()
        return self._resource_context.materialize_limits(value)

    @property
    def profile_sha256(self):
        self._require_active()
        return self._resource_context.profile_sha256

    def _owned_temp_name(self):
        if self._install.temp_name is None:
            return None
        if self._install.phase in (
            "temp_created",
            "writing",
            "temp_ready",
            "linked",
        ):
            return self._install.temp_name
        return None

    def _verify_names(self):
        self._names_verify_count += 1
        failure = self._collect_names_failure()
        if failure is not None:
            group, rec = failure
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase=self._phase_now(),
                group=group,
                reason=rec.reason,
                operation=rec.operation,
                errno_value=rec.errno,
            ) from None

    def _verify_full(self):
        self._full_verify_count += 1
        self._verify_names()
        byte_failure = self._collect_bytes_failure()
        if byte_failure is not None:
            group, rec = byte_failure
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase=self._phase_now(),
                group=group,
                reason=rec.reason,
                operation=rec.operation,
                errno_value=rec.errno,
            ) from None
        self._verify_names()

    def _collect_names_failure(self):
        index = 0
        while index < len(_GROUP_ORDER):
            group = _GROUP_ORDER[index]
            if group in self._reached:
                rec = self._verify_group_names(group)
                if rec is not None:
                    return group, rec
            index += 1
        return None

    def _collect_bytes_failure(self):
        index = 0
        while index < len(_GROUP_ORDER):
            group = _GROUP_ORDER[index]
            if group in self._reached:
                rec = self._verify_group_bytes(group)
                if rec is not None:
                    return group, rec
            index += 1
        return None

    def _check_node_dir(self, node, exact_mode=None):
        if node is None:
            return _CheckFailure("missing", "stat")
        if node.stat_error is not None and node.first_stat is None:
            return _CheckFailure(
                "syscall_failed",
                "stat",
                _bound_errno(node.stat_error.errno),
            )
        if node.absent:
            parent = self._nodes.get(node.parent_path)
            if parent is None or parent.fd is None:
                return _CheckFailure("missing", "stat")
            try:
                _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
                return _CheckFailure("late_arrival", "stat")
            except OSError as exc:
                if _bound_errno(exc.errno) == errno_module.ENOENT:
                    return None
                return _CheckFailure(
                    "syscall_failed",
                    "stat",
                    _bound_errno(exc.errno),
                )
        parent = self._nodes.get(node.parent_path)
        try:
            if parent is not None and parent.fd is not None and node.name != "/":
                st = _stat(node.name, dir_fd=parent.fd, follow_symlinks=False)
            else:
                st = _stat(node.path, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc.errno) == errno_module.ENOENT:
                return _CheckFailure("missing", "stat", _bound_errno(exc.errno))
            return _CheckFailure(
                "syscall_failed", "stat", _bound_errno(exc.errno)
            )
        try:
            if _is_dir(node.first_stat):
                if _dir_stamp(st) != _dir_stamp(node.first_stat):
                    return _CheckFailure("edge_changed", "stat")
            else:
                allow_temp = (
                    self._install.temp_name is not None
                    and node.name == self._install.temp_name
                    and self._install.phase in ("temp_created", "writing")
                )
                if allow_temp:
                    if (st.st_dev, st.st_ino, st.st_mode) != (
                        node.first_stat.st_dev,
                        node.first_stat.st_ino,
                        node.first_stat.st_mode,
                    ):
                        return _CheckFailure("edge_changed", "stat")
                elif _file_stamp(st) != _file_stamp(node.first_stat):
                    return _CheckFailure("edge_changed", "stat")
        except CodeProofIOError as exc:
            return _CheckFailure("edge_changed", "stat")
        if node.fd is not None:
            try:
                fst = _fstat(node.fd)
            except OSError as exc:
                return _CheckFailure(
                    "syscall_failed", "fstat", _bound_errno(exc.errno)
                )
            try:
                if _is_dir(node.first_stat):
                    if _dir_stamp(fst) != _dir_stamp(node.first_stat):
                        return _CheckFailure("edge_changed", "fstat")
                else:
                    allow_temp = (
                        self._install.temp_name is not None
                        and node.name == self._install.temp_name
                        and self._install.phase in ("temp_created", "writing")
                    )
                    if allow_temp:
                        if (fst.st_dev, fst.st_ino) != (
                            self._install.temp_dev,
                            self._install.temp_ino,
                        ):
                            return _CheckFailure("temp_ownership_lost", "fstat")
                    elif _file_stamp(fst) != _file_stamp(node.first_stat):
                        return _CheckFailure("edge_changed", "fstat")
            except CodeProofIOError:
                return _CheckFailure("edge_changed", "fstat")
        return None

    def _reread_node(self, node):
        if node is None or node.fd is None or node.data is None:
            return None
        if (
            self._install.temp_name is not None
            and node.name == self._install.temp_name
            and self._install.phase == "writing"
        ):
            try:
                _seek(node.fd, 0, os.SEEK_SET)
                prefix = self._read_exact(node.fd, self._install.written)
            except OSError as exc:
                return _CheckFailure(
                    "syscall_failed", "read", _bound_errno(exc.errno)
                )
            if prefix != self._install.payload[: self._install.written]:
                return _CheckFailure("bytes_changed", "read")
            return None
        try:
            _seek(node.fd, 0, os.SEEK_SET)
            data = self._read_exact(node.fd, len(node.data))
        except OSError as exc:
            return _CheckFailure(
                "syscall_failed", "read", _bound_errno(exc.errno)
            )
        except CodeProofIOError as exc:
            if exc.details.get("reason") == "syscall_failed":
                return _CheckFailure(
                    "syscall_failed", "read", exc.details.get("errno")
                )
            raise
        if data != node.data:
            return _CheckFailure("bytes_changed", "read")
        return None

    def _verify_group_names(self, group):
        if group == "checkout":
            node = self._nodes.get(self._checkout_path)
            rec = self._check_node_dir(node)
            if rec is not None:
                return rec
            git = self._nodes.get(_join_abs(self._checkout_path, ".git"))
            rec = self._check_node_dir(git)
            if rec is not None:
                return rec
            py_node = self._nodes.get(
                _join_abs(self._checkout_path, "pyproject.toml")
            )
            rec = self._check_node_dir(py_node)
            if rec is not None:
                return rec
            return None
        if group == "ancestors":
            for path in self._nodes.keys():
                node = self._nodes[path]
                if node.group == "ancestors":
                    rec = self._check_node_dir(node)
                    if rec is not None:
                        return rec
            return None
        if group == "resources":
            index = 0
            while index < len(self._resource_records):
                rec = self._resource_records[index]
                node = rec.node
                if rec.initial_missing:
                    if node is None:
                        return _CheckFailure("missing", "stat")
                    checked = self._check_node_dir(node)
                    if node.absent:
                        parent = self._nodes.get(node.parent_path)
                        if parent is not None and parent.fd is not None:
                            try:
                                _stat(
                                    node.name,
                                    dir_fd=parent.fd,
                                    follow_symlinks=False,
                                )
                                return _CheckFailure("late_arrival", "stat")
                            except OSError as exc:
                                if _bound_errno(exc.errno) == errno_module.ENOENT:
                                    index += 1
                                    continue
                                return _CheckFailure(
                                    "syscall_failed",
                                    "stat",
                                    _bound_errno(exc.errno),
                                )
                        index += 1
                        continue
                    return _CheckFailure("late_arrival", "stat")
                if rec.initial_unsafe is not None:
                    checked = self._check_node_dir(node)
                    if checked is None:
                        index += 1
                        continue
                    if checked.reason in _LINEAGE_REASONS:
                        return checked
                    index += 1
                    continue
                checked = self._check_node_dir(node)
                if checked is not None:
                    return checked
                index += 1
            return None
        if group == "metadata":
            if self._input_path is None:
                return None
            return self._check_node_dir(self._nodes.get(self._input_path))
        if group == "bundle":
            if self._bundle_root is None:
                return None
            root = self._nodes.get(self._bundle_root)
            rec = self._check_node_dir(root)
            if rec is not None:
                return rec
            if self._bundle_physical is not None:
                lineage = None
                try:
                    lineage = self._bundle_set_lineage()
                except CodeProofIOError as exc:
                    return _CheckFailure(
                        exc.details["reason"],
                        exc.details.get("operation"),
                        exc.details.get("errno"),
                    )
                return lineage
            return None
        if group == "output_layout":
            for key in (self._work_path, self._batch_path, self._output_path):
                node = self._nodes.get(key)
                if node is None:
                    continue
                rec = self._check_node_dir(node)
                if rec is not None:
                    return rec
            for family in _FAMILY_NAMES:
                node = self._nodes.get(_join_abs(self._output_path, family))
                if node is None:
                    continue
                rec = self._check_node_dir(node)
                if rec is not None:
                    return rec
            return None
        if group == "output_files":
            for name in self._current_files.keys():
                parsed = _parse_install_name(name)
                if parsed is None:
                    continue
                _kind, base, family, _ln, _hard, _ptr = parsed
                path = self._output_file_path(name, family, base)
                rec = self._check_node_dir(self._nodes.get(path))
                if rec is not None:
                    return rec
            return None
        if group == "installation":
            if self._install.temp_name is None or self._install.parent_path is None:
                return None
            if self._install.phase in ("cleaned", "durable", "idle"):
                return None
            path = _join_abs(self._install.parent_path, self._install.temp_name)
            return self._check_node_dir(self._nodes.get(path))
        return None

    def _verify_group_bytes(self, group):
        if group == "checkout":
            py_node = self._nodes.get(
                _join_abs(self._checkout_path, "pyproject.toml")
            )
            return self._reread_node(py_node)
        if group == "resources":
            index = 0
            while index < len(self._resource_records):
                rec = self._resource_records[index]
                if rec.data is not None:
                    checked = self._reread_node(rec.node)
                    if checked is not None:
                        return checked
                index += 1
            return None
        if group == "metadata":
            if self._input_path is None:
                return None
            return self._reread_node(self._nodes.get(self._input_path))
        if group == "bundle":
            if self._bundle_root is None:
                return None
            manifest = self._nodes.get(
                _join_abs(self._bundle_root, "manifest.json")
            )
            rec = self._reread_node(manifest)
            if rec is not None:
                return rec
            if self._bundle_bodies is not None:
                objects_path = _join_abs(self._bundle_root, "objects")
                for oid in self._bundle_bodies.keys():
                    name = self._bundle_physical[oid]
                    rec = self._reread_node(
                        self._nodes.get(_join_abs(objects_path, name))
                    )
                    if rec is not None:
                        return rec
            return None
        if group == "output_files":
            for name in sorted(self._current_files.keys()):
                parsed = _parse_install_name(name)
                if parsed is None:
                    continue
                _kind, base, family, _ln, _hard, _ptr = parsed
                path = self._output_file_path(name, family, base)
                rec = self._reread_node(self._nodes.get(path))
                if rec is not None:
                    return rec
            return None
        if group == "installation":
            if self._install.temp_fd is None:
                return None
            if self._install.phase == "writing":
                path = _join_abs(
                    self._install.parent_path, self._install.temp_name
                )
                return self._reread_node(self._nodes.get(path))
            if self._install.phase in ("temp_ready", "linked"):
                path = _join_abs(
                    self._install.parent_path, self._install.temp_name
                )
                return self._reread_node(self._nodes.get(path))
            return None
        return None

    def _cleanup_owned_temp(self):
        rec = self._install
        if rec.temp_name is None or rec.parent_path is None:
            return
        if rec.cleaned_prefix or rec.phase in ("cleaned", "durable", "idle"):
            if rec.phase == "idle" and rec.temp_name is not None and not rec.failed:
                return
            if rec.cleaned_prefix:
                return
        if rec.phase not in (
            "temp_created",
            "writing",
            "temp_ready",
            "linked",
        ):
            return
        parent = self._nodes.get(rec.parent_path)
        if parent is None or parent.fd is None:
            return
        try:
            st = _stat(rec.temp_name, dir_fd=parent.fd, follow_symlinks=False)
        except OSError as exc:
            if _bound_errno(exc.errno) == errno_module.ENOENT:
                if not rec.unlink_attempted:
                    raise _io_error(
                        "WORK_PATH_UNSAFE",
                        phase="closing",
                        group="installation",
                        reason="temp_ownership_lost",
                        operation="stat",
                    ) from None
                return
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="closing",
                group="installation",
                reason="syscall_failed",
                operation="stat",
                errno_value=_bound_errno(exc.errno),
            ) from None
        if (st.st_dev, st.st_ino) != (rec.temp_dev, rec.temp_ino):
            raise _io_error(
                "WORK_PATH_UNSAFE",
                phase="closing",
                group="installation",
                reason="temp_ownership_lost",
                operation="stat",
            ) from None
        try:
            _unlink(rec.temp_name, dir_fd=parent.fd)
        except OSError as exc:
            raise _io_error(
                "CODE_PROOF_IO_ERROR",
                phase="closing",
                group="installation",
                reason="syscall_failed",
                operation="unlink",
                errno_value=_bound_errno(exc.errno),
            ) from None

    def _close_all(self):
        self._state = "finalizing"
        index = len(self._fd_order) - 1
        while index >= 0:
            fd = self._fd_order[index]
            if fd in self._closed_fds:
                index -= 1
                continue
            self._closed_fds.add(fd)
            try:
                _close(fd)
            except OSError as exc:
                if self._cleanup_error is None:
                    self._cleanup_error = _io_error(
                        "CODE_PROOF_IO_ERROR",
                        phase="closing",
                        group=None,
                        reason="syscall_failed",
                        operation="close",
                        errno_value=_bound_errno(exc.errno),
                    )
            index -= 1
        if self._lock_dup_fd is not None and self._lock_dup_fd not in self._closed_fds:
            fd = self._lock_dup_fd
            self._closed_fds.add(fd)
            try:
                _close(fd)
            except OSError as exc:
                if self._cleanup_error is None:
                    self._cleanup_error = _io_error(
                        "CODE_PROOF_IO_ERROR",
                        phase="closing",
                        group="checkout",
                        reason="syscall_failed",
                        operation="close",
                        errno_value=_bound_errno(exc.errno),
                    )
            self._lock_dup_fd = None

    def _finalize(self, original):
        if self._state == "closed":
            return original
        self._state = "finalizing"
        group_failure = {}
        try:
            index = 0
            while index < len(_GROUP_ORDER):
                group = _GROUP_ORDER[index]
                if group in self._reached:
                    rec = self._verify_group_names(group)
                    if rec is None:
                        rec = self._verify_group_bytes(group)
                    if rec is not None:
                        skip = False
                        if (
                            group == "resources"
                            and self._unchanged_resource_invalid
                            and rec.reason
                            in (
                                "missing",
                                "unsafe_type",
                                "unsafe_mode",
                                "link_count",
                                "resource_hash",
                                "resource_shape",
                            )
                        ):
                            skip = True
                        if not skip:
                            group_failure[group] = rec
                index += 1
            index = 0
            while index < len(_GROUP_ORDER):
                group = _GROUP_ORDER[index]
                if group in self._reached:
                    rec = self._verify_group_names(group)
                    if rec is not None and group not in group_failure:
                        skip = False
                        if (
                            group == "resources"
                            and self._unchanged_resource_invalid
                            and rec.reason
                            in (
                                "missing",
                                "unsafe_type",
                                "unsafe_mode",
                                "link_count",
                                "resource_hash",
                            )
                        ):
                            skip = True
                        if not skip:
                            group_failure[group] = rec
                index += 1
        except BaseException as exc:
            if original is None:
                original = exc
        try:
            self._cleanup_owned_temp()
        except BaseException as exc:
            if self._cleanup_error is None:
                if isinstance(exc, CodeProofIOError):
                    self._cleanup_error = exc
                elif isinstance(exc, OSError):
                    self._cleanup_error = _io_error(
                        "CODE_PROOF_IO_ERROR",
                        phase="closing",
                        group="installation",
                        reason="syscall_failed",
                        operation="unlink",
                        errno_value=_bound_errno(exc.errno),
                    )
                else:
                    self._cleanup_error = _io_error(
                        "CODE_PROOF_IO_ERROR",
                        phase="closing",
                        group="installation",
                        reason="syscall_failed",
                        operation="unlink",
                    )
        try:
            self._close_all()
        except BaseException as exc:
            if self._cleanup_error is None and isinstance(exc, CodeProofIOError):
                self._cleanup_error = exc
        self._resource_context = None
        self._state = "closed"
        failed_groups = []
        index = 0
        while index < len(_GROUP_ORDER):
            group = _GROUP_ORDER[index]
            if group in group_failure:
                failed_groups.append(group)
            index += 1
        if failed_groups:
            group0 = failed_groups[0]
            rec = group_failure[group0]
            prior_code, prior_operation, prior_errno = _prior_fields(original)
            return _io_error(
                "WORK_PATH_UNSAFE",
                phase="final_verify",
                group=group0,
                reason=rec.reason,
                operation=rec.operation,
                errno_value=rec.errno,
                prior_code=prior_code,
                prior_operation=prior_operation,
                prior_errno=prior_errno,
                failed_groups=failed_groups,
            )
        if self._cleanup_error is not None:
            err = self._cleanup_error
            if isinstance(err, CodeProofIOError) and err.code in _NINE_FIELD_CODES:
                prior_code, prior_operation, prior_errno = _prior_fields(original)
                details = err.details
                return _io_error(
                    err.code,
                    phase=details["phase"],
                    group=details["group"],
                    reason=details["reason"],
                    operation=details["operation"],
                    errno_value=details["errno"],
                    prior_code=prior_code,
                    prior_operation=prior_operation,
                    prior_errno=prior_errno,
                    failed_groups=details["failed_groups"],
                )
            return err
        if original is not None:
            return original
        return None


def open_code_session(*, batch_id):
    return _CodeSession(batch_id)
