"""Pure in-memory CODE Git object kernel.

Standard-library hashing and parsing only. No filesystem, network, Git,
subprocess, schema, or resource-loader operations occur in this module.
"""

from __future__ import annotations

import hashlib
import re
from types import MappingProxyType

CODE_PROOF_INPUT_INVALID = "CODE_PROOF_INPUT_INVALID"
CODE_PROOF_LIMIT_EXCEEDED = "CODE_PROOF_LIMIT_EXCEEDED"
CODE_PROOF_OBJECT_EXTRA = "CODE_PROOF_OBJECT_EXTRA"
CODE_PROOF_OBJECT_UNAVAILABLE = "CODE_PROOF_OBJECT_UNAVAILABLE"
CODE_PROOF_OBJECT_SIZE_MISMATCH = "CODE_PROOF_OBJECT_SIZE_MISMATCH"
CODE_PROOF_OBJECT_HASH_MISMATCH = "CODE_PROOF_OBJECT_HASH_MISMATCH"
CODE_PROOF_OBJECT_TYPE_MISMATCH = "CODE_PROOF_OBJECT_TYPE_MISMATCH"
CODE_PROOF_COMMIT_INVALID = "CODE_PROOF_COMMIT_INVALID"
CODE_PROOF_TREE_INVALID = "CODE_PROOF_TREE_INVALID"
CODE_PROOF_CONSUMED_SET_MISMATCH = "CODE_PROOF_CONSUMED_SET_MISMATCH"

_ERROR_MESSAGES = {
    CODE_PROOF_INPUT_INVALID: "code git proof input is invalid",
    CODE_PROOF_LIMIT_EXCEEDED: "code git proof limit exceeded",
    CODE_PROOF_OBJECT_EXTRA: "undeclared git object bodies were supplied",
    CODE_PROOF_OBJECT_UNAVAILABLE: "required git object is unavailable",
    CODE_PROOF_OBJECT_SIZE_MISMATCH: "git object size does not match declaration",
    CODE_PROOF_OBJECT_HASH_MISMATCH: "git object identity does not match declaration",
    CODE_PROOF_OBJECT_TYPE_MISMATCH: "git object type does not match requirement",
    CODE_PROOF_COMMIT_INVALID: "git commit object is invalid",
    CODE_PROOF_TREE_INVALID: "git tree object is invalid",
    CODE_PROOF_CONSUMED_SET_MISMATCH: "declared git objects were not exactly consumed",
}

CODE_GIT_PROFILE_LIMITS = MappingProxyType(
    {
        "max_targets": 32,
        "max_objects": 2048,
        "max_tree_entries": 32768,
        "max_object_bytes": 8388608,
        "max_total_object_bytes": 33554432,
    }
)

_OBJECT_TYPES = frozenset({"commit", "tree", "blob"})
_FORMAT_WIDTHS = {"sha1": 40, "sha256": 64}
_OBJECT_RECORD_KEYS = frozenset(
    {"oid", "object_type", "body_size_bytes", "body_sha256", "framed_sha256"}
)
_TARGET_KEYS = frozenset({"path", "allow_executable_source"})
_HEX_CHARS = frozenset("0123456789abcdef")
_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
_HEADER_KEY = re.compile(rb"^[A-Za-z0-9-]+$")
_MODE_DIR = "40000"
_MODE_FILE = "100644"
_MODE_EXEC = "100755"
_MODE_LINK = "120000"
_MODE_GITLINK = "160000"
_VALID_MODES = frozenset(
    {_MODE_DIR, _MODE_FILE, _MODE_EXEC, _MODE_LINK, _MODE_GITLINK}
)
_COMMIT_HEADER_MAX_BYTES = 65536
_COMMIT_HEADER_MAX_LINES = 1024
_PATH_MAX_BYTES = 512
_PATH_MAX_COMPONENTS = 32
_HASH_FIELDS = ("oid", "body_sha256", "framed_sha256")


class CodeGitProofError(ValueError):
    """Closed CODE Git kernel refusal."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)
        self.exit_code = exit_code


def _raise(code: str, details: dict) -> None:
    raise CodeGitProofError(code, _ERROR_MESSAGES[code], details, 2)


def _input_invalid(instance_pointer: str, reason: str) -> None:
    _raise(
        CODE_PROOF_INPUT_INVALID,
        {"instance_pointer": instance_pointer, "reason": reason},
    )


def _limit_exceeded(
    instance_pointer: str,
    limit_name: str,
    limit: int,
    observed: int,
) -> None:
    _raise(
        CODE_PROOF_LIMIT_EXCEEDED,
        {
            "instance_pointer": instance_pointer,
            "limit_name": limit_name,
            "limit": limit,
            "observed": observed,
        },
    )


def _is_oid_str(value: object, width: int) -> bool:
    if type(value) is not str or len(value) != width:
        return False
    for char in value:
        if char not in _HEX_CHARS:
            return False
    return True


def _is_oid_bytes(value: bytes, width: int) -> bool:
    if len(value) != width:
        return False
    for byte in value:
        if byte not in b"0123456789abcdef":
            return False
    return True


def _require_str_enum(value: object, pointer: str, allowed: frozenset[str] | dict) -> str:
    if type(value) is not str:
        _input_invalid(pointer, "invalid_type")
    if value not in allowed:
        _input_invalid(pointer, "unsupported_value")
    return value


def _require_bytes(value: object, pointer: str) -> bytes:
    if type(value) is not bytes:
        _input_invalid(pointer, "invalid_type")
    return value


def _sha1_hex(data: bytes) -> str:
    try:
        return hashlib.sha1(data, usedforsecurity=False).hexdigest()
    except TypeError:
        return hashlib.sha1(data).hexdigest()


def _canonical_frame(object_type: str, body: bytes) -> bytes:
    return (
        object_type.encode("ascii")
        + b" "
        + str(len(body)).encode("ascii")
        + b"\0"
        + body
    )


def _reject_helper_body_cap(body: bytes) -> None:
    limit = CODE_GIT_PROFILE_LIMITS["max_object_bytes"]
    observed = len(body)
    if observed > limit:
        _raise(
            CODE_PROOF_LIMIT_EXCEEDED,
            {
                "instance_pointer": "/body",
                "limit_name": "max_object_bytes",
                "limit": 8388608,
                "observed": observed,
            },
        )


def frame_git_object(object_type: str, body: bytes) -> bytes:
    _require_str_enum(object_type, "/object_type", _OBJECT_TYPES)
    _require_bytes(body, "/body")
    _reject_helper_body_cap(body)
    return _canonical_frame(object_type, body)


def git_object_ids(
    object_format: str,
    object_type: str,
    body: bytes,
) -> tuple[str, str, str]:
    _require_str_enum(object_format, "/object_format", _FORMAT_WIDTHS)
    _require_str_enum(object_type, "/object_type", _OBJECT_TYPES)
    _require_bytes(body, "/body")
    _reject_helper_body_cap(body)
    frame = _canonical_frame(object_type, body)
    body_sha256 = hashlib.sha256(body).hexdigest()
    framed_sha256 = hashlib.sha256(frame).hexdigest()
    if object_format == "sha1":
        git_oid = _sha1_hex(frame)
    else:
        git_oid = framed_sha256
    return git_oid, body_sha256, framed_sha256


def _snapshot_object_record(record: dict) -> dict:
    return {
        "oid": record["oid"],
        "object_type": record["object_type"],
        "body_size_bytes": record["body_size_bytes"],
        "body_sha256": record["body_sha256"],
        "framed_sha256": record["framed_sha256"],
    }


def _validate_limits(limits: object) -> dict[str, int]:
    if type(limits) is not dict:
        _input_invalid("/limits", "invalid_type")
    if len(limits) != 5:
        _input_invalid("/limits", "limits_key_set")
    for key in limits:
        if type(key) is not str:
            _input_invalid("/limits", "limits_key_set")
    owned: dict[str, int] = {}
    for key, maximum in CODE_GIT_PROFILE_LIMITS.items():
        if key not in limits:
            _input_invalid("/limits", "limits_key_set")
        value = limits[key]
        pointer = "/limits/" + key
        if type(value) is not int:
            _input_invalid(pointer, "invalid_type")
        if value < 1 or value > maximum:
            _input_invalid(pointer, "out_of_range")
        owned[key] = value
    return owned


def _validate_oid_arg(value: object, pointer: str, width: int) -> str:
    if type(value) is not str:
        _input_invalid(pointer, "invalid_type")
    if not _is_oid_str(value, width):
        _input_invalid(pointer, "invalid_oid")
    return value


def _validate_path(path: object, pointer: str) -> list[str]:
    if type(path) is not str:
        _input_invalid(pointer, "invalid_type")
    if not path.isascii():
        _input_invalid(pointer, "invalid_path")
    if len(path) > _PATH_MAX_BYTES or "\\" in path:
        _input_invalid(pointer, "invalid_path")
    parts = path.split("/")
    if len(parts) < 1 or len(parts) > _PATH_MAX_COMPONENTS:
        _input_invalid(pointer, "invalid_path")
    for part in parts:
        if (
            part == ""
            or part == "."
            or part == ".."
            or part.casefold() == ".git"
            or _PATH_COMPONENT.fullmatch(part) is None
        ):
            _input_invalid(pointer, "invalid_path")
    return parts


def _validate_targets(targets: object, max_targets: int) -> list[dict]:
    if type(targets) is not list:
        _input_invalid("/targets", "invalid_type")
    count = len(targets)
    if count == 0:
        _input_invalid("/targets", "empty")
    if count > max_targets:
        _limit_exceeded("/targets", "max_targets", max_targets, count)
    owned: list[dict] = []
    seen_exact: set[str] = set()
    previous_path: str | None = None
    component_lists: list[list[str]] = []
    prefix_spellings: dict[tuple[str, ...], tuple[str, ...]] = {}
    for index, item in enumerate(targets):
        pointer = "/targets/" + str(index)
        if type(item) is not dict or len(item) != 2:
            _input_invalid(pointer, "not_closed_record")
        for key in item:
            if type(key) is not str:
                _input_invalid(pointer, "not_closed_record")
        if set(item) != _TARGET_KEYS:
            _input_invalid(pointer, "not_closed_record")
        path_pointer = pointer + "/path"
        components = _validate_path(item["path"], path_pointer)
        flag = item["allow_executable_source"]
        if type(flag) is not bool:
            _input_invalid(pointer + "/allow_executable_source", "invalid_type")
        path = item["path"]
        if path in seen_exact:
            _input_invalid(path_pointer, "duplicate_path")
        seen_exact.add(path)
        if previous_path is not None and path <= previous_path:
            _input_invalid(path_pointer, "not_sorted")
        previous_path = path
        for depth in range(1, len(components) + 1):
            exact = tuple(components[:depth])
            folded = tuple(part.casefold() for part in exact)
            existing = prefix_spellings.get(folded)
            if existing is not None and existing != exact:
                _input_invalid(path_pointer, "casefold_conflict")
            prefix_spellings[folded] = exact
        for earlier in component_lists:
            if len(earlier) < len(components) and components[: len(earlier)] == earlier:
                _input_invalid(path_pointer, "ancestor_conflict")
        component_lists.append(components)
        owned.append(
            {
                "path": path,
                "allow_executable_source": flag,
                "components": components,
            }
        )
    return owned


def _validate_objects(
    objects: object,
    commit_oid: str,
    width: int,
    max_objects: int,
) -> list[dict]:
    if type(objects) is not list:
        _input_invalid("/objects", "invalid_type")
    count = len(objects)
    if count == 0:
        _input_invalid("/objects", "empty")
    if count > max_objects:
        _limit_exceeded("/objects", "max_objects", max_objects, count)
    owned: list[dict] = []
    previous_oid: str | None = None
    commit_count = 0
    commit_record_oid: str | None = None
    for index, item in enumerate(objects):
        pointer = "/objects/" + str(index)
        if type(item) is not dict or len(item) != 5:
            _input_invalid(pointer, "not_closed_record")
        for key in item:
            if type(key) is not str:
                _input_invalid(pointer, "not_closed_record")
        if set(item) != _OBJECT_RECORD_KEYS:
            _input_invalid(pointer, "not_closed_record")
        oid = item["oid"]
        if not _is_oid_str(oid, width):
            _input_invalid(pointer + "/oid", "invalid_oid")
        if previous_oid is not None and oid <= previous_oid:
            _input_invalid(pointer + "/oid", "not_sorted_or_duplicate")
        previous_oid = oid
        object_type = item["object_type"]
        if type(object_type) is not str or object_type not in _OBJECT_TYPES:
            _input_invalid(pointer + "/object_type", "unsupported_value")
        size = item["body_size_bytes"]
        if type(size) is not int:
            _input_invalid(pointer + "/body_size_bytes", "invalid_type")
        if size < 0:
            _input_invalid(pointer + "/body_size_bytes", "out_of_range")
        body_sha256 = item["body_sha256"]
        if not _is_oid_str(body_sha256, 64):
            _input_invalid(pointer + "/body_sha256", "invalid_oid")
        framed_sha256 = item["framed_sha256"]
        if not _is_oid_str(framed_sha256, 64):
            _input_invalid(pointer + "/framed_sha256", "invalid_oid")
        if object_type == "commit":
            commit_count += 1
            if commit_count > 1:
                _input_invalid(pointer + "/object_type", "multiple_commits")
            commit_record_oid = oid
        owned.append(
            {
                "oid": oid,
                "object_type": object_type,
                "body_size_bytes": size,
                "body_sha256": body_sha256,
                "framed_sha256": framed_sha256,
            }
        )
    if commit_count != 1:
        _input_invalid("/objects", "missing_commit")
    if commit_record_oid != commit_oid:
        _input_invalid("/commit_oid", "commit_oid_mismatch")
    return owned


def _check_declared_sizes(records: list[dict], limits: dict[str, int]) -> int:
    declared_sum = 0
    max_object_bytes = limits["max_object_bytes"]
    max_total = limits["max_total_object_bytes"]
    for index, record in enumerate(records):
        size = record["body_size_bytes"]
        if size > max_object_bytes:
            _limit_exceeded(
                "/objects/" + str(index) + "/body_size_bytes",
                "max_object_bytes",
                max_object_bytes,
                size,
            )
        declared_sum += size
    if declared_sum > max_total:
        _limit_exceeded(
            "/objects",
            "max_total_object_bytes",
            max_total,
            declared_sum,
        )
    return declared_sum


def _validate_bodies_map(
    bodies: object,
    records: list[dict],
    width: int,
    max_objects: int,
) -> None:
    if type(bodies) is not dict:
        _input_invalid("/bodies", "invalid_type")
    observed = len(bodies)
    if observed > max_objects:
        _limit_exceeded("/bodies", "max_objects", max_objects, observed)
    declared = {record["oid"] for record in records}
    extra: list[str] = []
    for key in bodies:
        if not _is_oid_str(key, width):
            _input_invalid("/bodies", "invalid_oid_key")
        if key not in declared:
            extra.append(key)
    if extra:
        _raise(
            CODE_PROOF_OBJECT_EXTRA,
            {
                "instance_pointer": "/bodies",
                "extra_oids": sorted(extra),
            },
        )
    missing = [record["oid"] for record in records if record["oid"] not in bodies]
    if missing:
        _raise(
            CODE_PROOF_OBJECT_UNAVAILABLE,
            {
                "instance_pointer": "/bodies",
                "missing_oids": sorted(missing),
            },
        )


def _validate_actual_bodies(
    records: list[dict],
    bodies: dict,
    limits: dict[str, int],
) -> tuple[dict[str, bytes], int]:
    owned_bodies: dict[str, bytes] = {}
    actual_sum = 0
    max_object_bytes = limits["max_object_bytes"]
    max_total = limits["max_total_object_bytes"]
    first_object_cap: tuple[str, int, int] | None = None
    total_observed: int | None = None
    first_mismatch: tuple[str, int, int, int] | None = None
    for index, record in enumerate(records):
        oid = record["oid"]
        body = bodies[oid]
        if type(body) is not bytes:
            _input_invalid("/bodies/" + oid, "invalid_type")
        actual = len(body)
        if first_object_cap is None and actual > max_object_bytes:
            first_object_cap = (oid, index, actual)
        actual_sum += actual
        if total_observed is None and actual_sum > max_total:
            total_observed = actual_sum
        if first_mismatch is None and actual != record["body_size_bytes"]:
            first_mismatch = (oid, index, record["body_size_bytes"], actual)
        owned_bodies[oid] = body
    if first_object_cap is not None:
        oid, index, actual = first_object_cap
        _limit_exceeded(
            "/bodies/" + oid,
            "max_object_bytes",
            max_object_bytes,
            actual,
        )
    if total_observed is not None:
        _limit_exceeded(
            "/bodies",
            "max_total_object_bytes",
            max_total,
            total_observed,
        )
    if first_mismatch is not None:
        oid, index, declared_size, actual_size = first_mismatch
        _raise(
            CODE_PROOF_OBJECT_SIZE_MISMATCH,
            {
                "instance_pointer": "/objects/" + str(index) + "/body_size_bytes",
                "oid": oid,
                "declared_size": declared_size,
                "actual_size": actual_size,
            },
        )
    return owned_bodies, actual_sum


def _verify_hashes(
    object_format: str,
    records: list[dict],
    bodies: dict[str, bytes],
) -> None:
    for index, record in enumerate(records):
        oid = record["oid"]
        computed_oid, computed_body, computed_framed = git_object_ids(
            object_format,
            record["object_type"],
            bodies[oid],
        )
        computed = {
            "oid": computed_oid,
            "body_sha256": computed_body,
            "framed_sha256": computed_framed,
        }
        for field in _HASH_FIELDS:
            if record[field] != computed[field]:
                _raise(
                    CODE_PROOF_OBJECT_HASH_MISMATCH,
                    {
                        "instance_pointer": "/objects/" + str(index) + "/" + field,
                        "oid": oid,
                        "field": field,
                    },
                )


def _commit_invalid(oid: str, reason: str) -> None:
    _raise(
        CODE_PROOF_COMMIT_INVALID,
        {
            "instance_pointer": "/objects",
            "oid": oid,
            "reason": reason,
        },
    )


def _parse_commit(
    oid: str,
    body: bytes,
    object_format: str,
    root_tree_oid: str,
) -> None:
    width = _FORMAT_WIDTHS[object_format]
    separator = body.find(b"\n\n")
    if separator < 0:
        _commit_invalid(oid, "missing_header_terminator")
    header_section = body[: separator + 2]
    if len(header_section) > _COMMIT_HEADER_MAX_BYTES:
        _commit_invalid(oid, "header_too_large")
    if b"\0" in header_section:
        _commit_invalid(oid, "header_contains_nul")
    if b"\r" in header_section:
        _commit_invalid(oid, "header_contains_cr")
    raw_lines = header_section.split(b"\n")
    if len(raw_lines) < 2 or raw_lines[-1] != b"" or raw_lines[-2] != b"":
        _commit_invalid(oid, "missing_header_terminator")
    lines = raw_lines[:-2]
    if len(lines) > _COMMIT_HEADER_MAX_LINES:
        _commit_invalid(oid, "too_many_header_lines")
    if not lines:
        _commit_invalid(oid, "missing_tree_header")
    prev_kind = None
    tree_seen = False
    for index, line in enumerate(lines):
        if line.startswith(b"\t"):
            _commit_invalid(oid, "tab_prefixed_header")
        if line.startswith(b" "):
            if prev_kind != "ordinary":
                _commit_invalid(oid, "invalid_continuation")
            continue
        space = line.find(b" ")
        if space <= 0:
            _commit_invalid(oid, "malformed_header")
        key = line[:space]
        value = line[space + 1 :]
        if _HEADER_KEY.fullmatch(key) is None:
            _commit_invalid(oid, "malformed_header")
        if index == 0:
            if key != b"tree" or not _is_oid_bytes(value, width):
                _commit_invalid(oid, "invalid_tree_header")
            parsed_tree = value.decode("ascii")
            if parsed_tree != root_tree_oid:
                _commit_invalid(oid, "root_tree_mismatch")
            tree_seen = True
            prev_kind = "structural"
            continue
        if key == b"tree":
            _commit_invalid(oid, "duplicate_tree_header")
        if key == b"parent":
            if not _is_oid_bytes(value, width):
                _commit_invalid(oid, "invalid_parent_header")
            prev_kind = "structural"
            continue
        prev_kind = "ordinary"
    if not tree_seen:
        _commit_invalid(oid, "missing_tree_header")


def _tree_invalid(oid: str, reason: str, byte_offset: int) -> None:
    _raise(
        CODE_PROOF_TREE_INVALID,
        {
            "instance_pointer": "/objects",
            "oid": oid,
            "reason": reason,
            "byte_offset": byte_offset,
        },
    )


def _parse_tree(
    oid: str,
    body: bytes,
    object_format: str,
    max_tree_entries: int,
    parsed_count: int,
) -> tuple[dict[bytes, dict], int]:
    oid_raw_len = 20 if object_format == "sha1" else 32
    by_name: dict[bytes, dict] = {}
    offset = 0
    length = len(body)
    previous_key: bytes | None = None
    while offset < length:
        entry_start = offset
        space = body.find(b" ", offset)
        if space < 0:
            _tree_invalid(oid, "truncated_mode", entry_start)
        mode_bytes = body[offset:space]
        try:
            mode = mode_bytes.decode("ascii")
        except UnicodeDecodeError:
            _tree_invalid(oid, "invalid_mode", entry_start)
        if mode not in _VALID_MODES:
            _tree_invalid(oid, "invalid_mode", entry_start)
        name_start = space + 1
        nul = body.find(b"\0", name_start)
        if nul < 0:
            _tree_invalid(oid, "truncated_name", entry_start)
        name = body[name_start:nul]
        if name == b"" or b"/" in name or name == b"." or name == b"..":
            _tree_invalid(oid, "invalid_name", entry_start)
        if name in by_name:
            _tree_invalid(oid, "duplicate_name", entry_start)
        oid_start = nul + 1
        oid_end = oid_start + oid_raw_len
        if oid_end > length:
            _tree_invalid(oid, "truncated_oid", entry_start)
        hex_oid = body[oid_start:oid_end].hex()
        sort_key = name + (b"/" if mode == _MODE_DIR else b"\0")
        if previous_key is not None and sort_key <= previous_key:
            _tree_invalid(oid, "invalid_order", entry_start)
        parsed_count += 1
        if parsed_count > max_tree_entries:
            _limit_exceeded(
                "/objects",
                "max_tree_entries",
                max_tree_entries,
                parsed_count,
            )
        by_name[name] = {
            "mode": mode,
            "name": name,
            "oid": hex_oid,
        }
        previous_key = sort_key
        offset = oid_end
    return by_name, parsed_count


def _require_declared_type(
    oid: str,
    expected_type: str,
    records_by_oid: dict[str, dict],
) -> dict:
    record = records_by_oid.get(oid)
    if record is None:
        _raise(
            CODE_PROOF_OBJECT_UNAVAILABLE,
            {
                "instance_pointer": "/objects",
                "missing_oids": sorted([oid]),
            },
        )
    actual_type = record["object_type"]
    if actual_type != expected_type:
        _raise(
            CODE_PROOF_OBJECT_TYPE_MISMATCH,
            {
                "instance_pointer": "/objects",
                "oid": oid,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
        )
    return record


def _blob_subrecord(record: dict) -> dict:
    return {
        "oid": record["oid"],
        "body_size_bytes": record["body_size_bytes"],
        "body_sha256": record["body_sha256"],
        "framed_sha256": record["framed_sha256"],
    }


def _walk_targets(
    targets: list[dict],
    root_tree_oid: str,
    parsed_trees: dict[str, dict[bytes, dict]],
    records_by_oid: dict[str, dict],
    consumed: set[str],
) -> tuple[list[dict], int]:
    results: list[dict] = []
    walk_edges = 0
    for target in targets:
        components = target["components"]
        allow_exec = target["allow_executable_source"]
        current_tree_oid = root_tree_oid
        walk: list[dict] = []
        outcome = None
        reason = None
        stopped_at = None
        blob = None
        for index, component in enumerate(components):
            name = component.encode("ascii")
            entry = parsed_trees[current_tree_oid].get(name)
            is_last = index == len(components) - 1
            if entry is None:
                outcome = "missing"
                reason = "absent_entry"
                stopped_at = {
                    "component_index": index,
                    "tree_oid": current_tree_oid,
                    "name_hex": name.hex(),
                    "mode": None,
                    "oid": None,
                }
                break
            edge = {
                "tree_oid": current_tree_oid,
                "name_hex": entry["name"].hex(),
                "mode": entry["mode"],
                "oid": entry["oid"],
            }
            walk.append(edge)
            if not is_last:
                if entry["mode"] != _MODE_DIR:
                    outcome = "unsafe"
                    reason = "non_directory_intermediate"
                    stopped_at = {
                        "component_index": index,
                        "tree_oid": current_tree_oid,
                        "name_hex": edge["name_hex"],
                        "mode": entry["mode"],
                        "oid": entry["oid"],
                    }
                    break
                _require_declared_type(entry["oid"], "tree", records_by_oid)
                consumed.add(entry["oid"])
                current_tree_oid = entry["oid"]
                continue
            mode = entry["mode"]
            stopped_at = {
                "component_index": index,
                "tree_oid": current_tree_oid,
                "name_hex": edge["name_hex"],
                "mode": mode,
                "oid": entry["oid"],
            }
            if mode == _MODE_FILE or (mode == _MODE_EXEC and allow_exec):
                record = _require_declared_type(entry["oid"], "blob", records_by_oid)
                consumed.add(entry["oid"])
                outcome = "permitted_regular_blob"
                reason = None
                blob = _blob_subrecord(record)
            elif mode == _MODE_EXEC:
                outcome = "unsafe"
                reason = "executable_without_permission"
            elif mode == _MODE_LINK:
                outcome = "unsafe"
                reason = "symlink"
            elif mode == _MODE_GITLINK:
                outcome = "unsafe"
                reason = "gitlink"
            else:
                outcome = "unsafe"
                reason = "directory"
        walk_edges += len(walk)
        results.append(
            {
                "path": target["path"],
                "outcome": outcome,
                "reason": reason,
                "walk": walk,
                "stopped_at": stopped_at,
                "blob": blob,
            }
        )
    return results, walk_edges


def verify_code_git_objects(
    *,
    object_format: str,
    commit_oid: str,
    root_tree_oid: str,
    objects: list[dict],
    bodies: dict[str, bytes],
    targets: list[dict],
    limits: dict[str, int],
) -> dict:
    if type(objects) is not list:
        _input_invalid("/objects", "invalid_type")
    if type(bodies) is not dict:
        _input_invalid("/bodies", "invalid_type")
    if type(targets) is not list:
        _input_invalid("/targets", "invalid_type")
    object_format = _require_str_enum(
        object_format, "/object_format", _FORMAT_WIDTHS
    )
    width = _FORMAT_WIDTHS[object_format]
    commit_oid = _validate_oid_arg(commit_oid, "/commit_oid", width)
    root_tree_oid = _validate_oid_arg(root_tree_oid, "/root_tree_oid", width)
    owned_limits = _validate_limits(limits)
    owned_targets = _validate_targets(targets, owned_limits["max_targets"])
    owned_records = _validate_objects(
        objects,
        commit_oid,
        width,
        owned_limits["max_objects"],
    )
    declared_body_bytes = _check_declared_sizes(owned_records, owned_limits)
    _validate_bodies_map(
        bodies,
        owned_records,
        width,
        owned_limits["max_objects"],
    )
    owned_bodies, actual_body_bytes = _validate_actual_bodies(
        owned_records,
        bodies,
        owned_limits,
    )
    _verify_hashes(object_format, owned_records, owned_bodies)
    records_by_oid = {record["oid"]: record for record in owned_records}
    _parse_commit(
        commit_oid,
        owned_bodies[commit_oid],
        object_format,
        root_tree_oid,
    )
    _require_declared_type(root_tree_oid, "tree", records_by_oid)
    parsed_trees: dict[str, dict[bytes, dict]] = {}
    parsed_tree_entries = 0
    for record in owned_records:
        if record["object_type"] != "tree":
            continue
        by_name, parsed_tree_entries = _parse_tree(
            record["oid"],
            owned_bodies[record["oid"]],
            object_format,
            owned_limits["max_tree_entries"],
            parsed_tree_entries,
        )
        parsed_trees[record["oid"]] = by_name
    consumed = {commit_oid, root_tree_oid}
    target_results, walk_edges = _walk_targets(
        owned_targets,
        root_tree_oid,
        parsed_trees,
        records_by_oid,
        consumed,
    )
    declared_oids = [record["oid"] for record in owned_records]
    unused = [oid for oid in declared_oids if oid not in consumed]
    if unused:
        _raise(
            CODE_PROOF_CONSUMED_SET_MISMATCH,
            {
                "instance_pointer": "/objects",
                "unused_oids": sorted(unused),
            },
        )
    object_records = [_snapshot_object_record(record) for record in owned_records]
    return {
        "object_format": object_format,
        "commit_oid": commit_oid,
        "root_tree_oid": root_tree_oid,
        "object_records": object_records,
        "consumed_oids": sorted(consumed),
        "budget": {
            "object_count": len(owned_records),
            "declared_body_bytes": declared_body_bytes,
            "actual_body_bytes": actual_body_bytes,
            "parsed_tree_entries": parsed_tree_entries,
            "target_count": len(owned_targets),
            "walk_edges": walk_edges,
        },
        "targets": target_results,
    }
