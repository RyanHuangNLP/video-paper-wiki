"""Public code-evidence request, observe, status, config, and handoff."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from video_paper_wiki.code_config_parser import CodeConfigError, parse_code_config_bytes
from video_paper_wiki.code_evidence_contracts import (
    code_text_metadata,
    normalize_code_bytes,
)
from video_paper_wiki.code_git_objects import (
    CodeGitProofError,
    git_object_ids,
    verify_code_git_objects,
)
from video_paper_wiki.code_proof_io import CodeProofIOError, open_code_session
from video_paper_wiki.code_proof_resources import (
    CodeProofResourceError,
    CodeProofStructureError,
)
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize

__all__ = [
    "CodeProofPublicError",
    "config_code_proof",
    "handoff_code_proof",
    "observe_code_proof",
    "request_code_proof",
    "run_code_evidence_command",
    "status_code_proof",
]

_MESSAGES = {
    "CODE_PROOF_JSON_INVALID": "CODE evidence JSON is invalid",
    "CODE_PROOF_DOCUMENT_INVALID": "CODE evidence document is invalid",
    "CODE_PROOF_BINDING_MISMATCH": "CODE evidence binding mismatch",
    "CODE_PROOF_STATE_INVALID": "CODE evidence state is invalid",
    "CODE_PROOF_NOT_READY": "CODE evidence is not ready",
    "CODE_PROOF_TARGET_INELIGIBLE": "CODE evidence target is ineligible",
}
_JSON_REASONS = frozenset(
    {
        "utf8",
        "bom",
        "duplicate_key",
        "float",
        "nonfinite",
        "integer_range",
        "depth",
        "syntax",
        "trailing",
        "surrogate",
    }
)
_DOCUMENT_REASONS = frozenset(
    {
        "shape",
        "type",
        "string_bound",
        "integer_bound",
        "enum",
        "noncanonical_text",
        "repository",
        "path",
        "target_order",
        "role_permission",
        "limits",
        "datetime",
        "identity",
        "canonical_bytes",
    }
)
_BINDING_REASONS = frozenset(
    {
        "reference_kind",
        "reference_hash",
        "request",
        "repository",
        "object_format",
        "commit_oid",
        "root_tree_oid",
        "path",
        "blob",
        "raw_body",
        "profile",
        "derived",
    }
)
_STATE_REASONS = frozenset(
    {
        "missing_dependency",
        "forbidden_slot",
        "forbidden_family",
        "nonprefix_objects",
        "nonprefix_handoffs",
        "orphan_derived",
    }
)
_NOT_READY_REASONS = frozenset(
    {
        "request_absent",
        "observation_incomplete",
        "raw_evidence_required",
    }
)
_INELIGIBLE_REASONS = frozenset(
    {
        "path_not_requested",
        "missing",
        "unsafe",
        "unsupported_source_bytes",
        "configuration_role_required",
        "repository_assertion_required",
        "complete_target_set_required",
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
_KINDS = {
    "code-proof-request": "video-paper-wiki.code-proof-request.v1",
    "code-git-bundle": "video-paper-wiki.code-git-bundle.v1",
    "code-acquisition-intent": "video-paper-wiki.code-acquisition-intent.v1",
    "code-proof-observation": "video-paper-wiki.code-proof-observation.v1",
    "code-config-evidence": "video-paper-wiki.code-config-evidence.v1",
    "code-source-handoff": "video-paper-wiki.code-source-handoff.v1",
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
_GIT_LIMIT_KEYS = (
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
)
_CONFIG_LIMIT_KEYS = (
    "max_source_bytes",
    "max_depth",
    "max_nodes",
    "max_array_items",
    "max_object_keys",
    "max_key_bytes",
    "max_string_codepoints",
    "max_scalars",
    "max_numeric_lexeme_bytes",
    "max_numeric_coefficient_digits",
    "max_numeric_abs_exponent",
    "max_numeric_canonical_bytes",
    "max_declarations",
)
_PUBLIC_LIMIT_KEYS = (
    "max_bundle_bytes",
    "max_inline_normalized_bytes",
    "max_request_bytes",
    "max_intent_bytes",
    "max_observation_bytes",
    "max_config_document_bytes",
    "max_handoff_bytes",
    "max_output_peak_bytes",
)
_ROLE_ORDER = (
    "citation",
    "configuration",
    "entrypoint",
    "implementation",
    "license",
    "readme",
)
_ROLE_SET = frozenset(_ROLE_ORDER)
_EXEC_ROLES = frozenset({"implementation", "entrypoint"})
_HEX = frozenset("0123456789abcdef")
_REPO_PART = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_PATH_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_UTC = re.compile(
    r"^(?:[0-9]{4})-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_JSON_DEPTH = 64
_INT_MIN = -9223372036854775808
_INT_MAX = 9223372036854775807
_NAMESPACE = "code-evidence-v1"
_SLOT_POINTERS = {
    "request.json": "/request",
    "intent.json": "/intent",
    "bundle.json": "/bundle",
    "observation.json": "/observation",
}
_UNSAFE_REASONS = frozenset(
    {
        "executable_without_permission",
        "symlink",
        "gitlink",
        "directory",
        "non_directory_intermediate",
    }
)
_HOST_UNAVAILABLE = frozenset(
    {"not_returned", "capability_unavailable", "request_failed"}
)
_CONTROL_C0 = frozenset(range(0x20)) | {0x7F}
_CONTROL_C1 = frozenset(range(0x80, 0xA0)) | {0x2028, 0x2029}


class _JsonFail(Exception):
    def __init__(self, reason):
        self.reason = reason


class CodeProofPublicError(Exception):
    """Closed public CODE semantic refusal."""

    def __init__(self, code, details):
        if type(code) is not str or code not in _MESSAGES:
            raise ValueError("Invalid CODE public error context") from None
        if type(details) is not dict:
            raise ValueError("Invalid CODE public error context") from None
        copied = _plain(details)
        if code == "CODE_PROOF_TARGET_INELIGIBLE":
            if frozenset(copied) != frozenset(
                ("instance_pointer", "reason", "blockers")
            ):
                raise ValueError("Invalid CODE public error context") from None
            if type(copied["instance_pointer"]) is not str:
                raise ValueError("Invalid CODE public error context") from None
            if copied["reason"] not in _INELIGIBLE_REASONS:
                raise ValueError("Invalid CODE public error context") from None
            if type(copied["blockers"]) is not list:
                raise ValueError("Invalid CODE public error context") from None
        else:
            if frozenset(copied) != frozenset(("instance_pointer", "reason")):
                raise ValueError("Invalid CODE public error context") from None
            if type(copied["instance_pointer"]) is not str:
                raise ValueError("Invalid CODE public error context") from None
            allowed = {
                "CODE_PROOF_JSON_INVALID": _JSON_REASONS,
                "CODE_PROOF_DOCUMENT_INVALID": _DOCUMENT_REASONS,
                "CODE_PROOF_BINDING_MISMATCH": _BINDING_REASONS,
                "CODE_PROOF_STATE_INVALID": _STATE_REASONS,
                "CODE_PROOF_NOT_READY": _NOT_READY_REASONS,
            }[code]
            if copied["reason"] not in allowed:
                raise ValueError("Invalid CODE public error context") from None
        self._code = code
        self._message = _MESSAGES[code]
        self._details = copied
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
        return _plain(self._details)

    @property
    def exit_code(self):
        return self._exit_code


def _plain(value):
    ty = type(value)
    if ty is dict:
        out = {}
        for key in value:
            out[key] = _plain(value[key])
        return out
    if ty is list:
        return [_plain(item) for item in value]
    return value


def _json_invalid(pointer, reason):
    raise CodeProofPublicError(
        "CODE_PROOF_JSON_INVALID",
        {"instance_pointer": pointer, "reason": reason},
    )


def _document(pointer, reason):
    raise CodeProofPublicError(
        "CODE_PROOF_DOCUMENT_INVALID",
        {"instance_pointer": pointer, "reason": reason},
    )


def _binding(pointer, reason):
    raise CodeProofPublicError(
        "CODE_PROOF_BINDING_MISMATCH",
        {"instance_pointer": pointer, "reason": reason},
    )


def _state(pointer, reason):
    raise CodeProofPublicError(
        "CODE_PROOF_STATE_INVALID",
        {"instance_pointer": pointer, "reason": reason},
    )


def _not_ready(pointer, reason):
    raise CodeProofPublicError(
        "CODE_PROOF_NOT_READY",
        {"instance_pointer": pointer, "reason": reason},
    )


def _ineligible(pointer, reason, blockers):
    raise CodeProofPublicError(
        "CODE_PROOF_TARGET_INELIGIBLE",
        {
            "instance_pointer": pointer,
            "reason": reason,
            "blockers": blockers,
        },
    )


def _limit(pointer, limit_name, limit, observed):
    raise CodeProofIOError(
        "CODE_PROOF_LIMIT_EXCEEDED",
        {
            "instance_pointer": pointer,
            "limit_name": limit_name,
            "limit": limit,
            "observed": observed,
        },
    )


def _conflict(pointer, reason):
    if reason not in _CONFLICT_REASONS:
        reason = "artifact_changed"
    raise CodeProofIOError(
        "CODE_PROOF_CONFLICT",
        {"instance_pointer": pointer, "reason": reason},
    )


def _is_hex(value, width):
    if type(value) is not str or len(value) != width:
        return False
    for char in value:
        if char not in _HEX:
            return False
    return True


def _utf8_len(text):
    return len(text.encode("utf-8"))


def _has_surrogate(text):
    for char in text:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            return True
    return False


def _nfc(text):
    return unicodedata.normalize("NFC", text) == text


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if type(key) is not str:
            raise _JsonFail("syntax")
        if key in result:
            raise _JsonFail("duplicate_key")
        result[key] = value
    return result


def _parse_float(_lexeme):
    raise _JsonFail("float")


def _parse_const(_lexeme):
    raise _JsonFail("nonfinite")


def _parse_int(lexeme):
    if type(lexeme) is not str:
        raise _JsonFail("syntax")
    try:
        value = int(lexeme, 10)
    except ValueError:
        raise _JsonFail("syntax") from None
    if value < _INT_MIN or value > _INT_MAX:
        raise _JsonFail("integer_range")
    return value


def _walk_json(root, pointer):
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > _JSON_DEPTH:
            _json_invalid(pointer, "depth")
        ty = type(node)
        if ty is dict:
            for key in node:
                if type(key) is not str or _has_surrogate(key):
                    _json_invalid(pointer, "surrogate")
                stack.append((node[key], depth + 1))
        elif ty is list:
            for item in node:
                stack.append((item, depth + 1))
        elif ty is str:
            if _has_surrogate(node):
                _json_invalid(pointer, "surrogate")
        elif ty is int or ty is bool or node is None:
            continue
        else:
            _json_invalid(pointer, "syntax")


def _parse_json_bytes(payload, pointer):
    if type(payload) is not bytes:
        _json_invalid(pointer, "syntax")
    if payload.startswith(b"\xef\xbb\xbf"):
        _json_invalid(pointer, "bom")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _json_invalid(pointer, "utf8")
    if text.startswith("\ufeff"):
        _json_invalid(pointer, "bom")
    start = 0
    length = len(text)
    while start < length and text[start] in " \t\n\r":
        start += 1
    if start >= length:
        _json_invalid(pointer, "syntax")
    decoder = json.JSONDecoder(
        object_pairs_hook=_pairs,
        parse_float=_parse_float,
        parse_int=_parse_int,
        parse_constant=_parse_const,
        strict=True,
    )
    try:
        parsed, index = decoder.raw_decode(text, start)
    except _JsonFail as exc:
        _json_invalid(pointer, exc.reason)
    except RecursionError:
        _json_invalid(pointer, "depth")
    except json.JSONDecodeError:
        _json_invalid(pointer, "syntax")
    trailing = text[index:]
    for char in trailing:
        if char not in " \t\n\r":
            _json_invalid(pointer, "trailing")
    try:
        _walk_json(parsed, pointer)
    except RecursionError:
        _json_invalid(pointer, "depth")
    return parsed


def _object(value, pointer, required, optional=()):
    if type(value) is not dict:
        _document(pointer, "type")
    allowed = frozenset(required) | frozenset(optional)
    for key in value:
        if type(key) is not str:
            _document(pointer, "type")
        if key not in allowed:
            _document(pointer, "shape")
    for key in required:
        if key not in value:
            _document(pointer, "shape")
    return value


def _bool(value, pointer):
    if type(value) is not bool:
        _document(pointer, "type")
    return value


def _str(value, pointer):
    if type(value) is not str:
        _document(pointer, "type")
    if _has_surrogate(value):
        _document(pointer, "noncanonical_text")
    return value


def _int(value, pointer, minimum, maximum):
    if type(value) is not int:
        _document(pointer, "type")
    if value < minimum or value > maximum:
        _document(pointer, "integer_bound")
    return value


def _require_kw_str(value, pointer):
    if type(value) is not str:
        _document(pointer, "type")
    return value


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _datetime(value, pointer):
    text = _str(value, pointer)
    if _UTC.fullmatch(text) is None:
        _document(pointer, "datetime")
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    if year < 1:
        _document(pointer, "datetime")
    days = _MONTH_DAYS[month - 1]
    if month == 2 and _leap(year):
        days = 29
    if day > days:
        _document(pointer, "datetime")
    return text


def _paper_id(value, pointer):
    text = _str(value, pointer)
    if not _nfc(text):
        _document(pointer, "noncanonical_text")
    if _utf8_len(text) > 512:
        _document(pointer, "string_bound")
    if not is_canonical_paper_id(text):
        _document(pointer, "identity")
    return text


def _repository_input(value, pointer):
    text = _str(value, pointer)
    if "/" not in text:
        _document(pointer, "repository")
    owner, name = text.split("/", 1)
    if "/" in name:
        _document(pointer, "repository")
    if _REPO_PART.fullmatch(owner) is None or _REPO_PART.fullmatch(name) is None:
        _document(pointer, "repository")
    if owner in (".", "..") or name in (".", ".."):
        _document(pointer, "repository")
    if name.casefold().endswith(".git"):
        _document(pointer, "repository")
    return text.lower()


def _repository_saved(value, pointer):
    text = _str(value, pointer)
    saved = _repository_input(text, pointer)
    if saved != text:
        _document(pointer, "repository")
    return text


def _object_format(value, pointer):
    text = _str(value, pointer)
    if text != "sha1" and text != "sha256":
        _document(pointer, "enum")
    return text


def _oid(value, pointer, object_format):
    text = _str(value, pointer)
    width = 40 if object_format == "sha1" else 64
    if not _is_hex(text, width):
        _document(pointer, "identity")
    return text


def _sha256(value, pointer):
    text = _str(value, pointer)
    if not _is_hex(text, 64):
        _document(pointer, "identity")
    return text


def _git_path(value, pointer):
    text = _str(value, pointer)
    if not text.isascii() or "\\" in text or len(text) > 512:
        _document(pointer, "path")
    parts = text.split("/")
    if not parts or len(parts) > 32:
        _document(pointer, "path")
    folded = []
    for part in parts:
        if (
            part == ""
            or part == "."
            or part == ".."
            or part.casefold() == ".git"
            or _PATH_PART.fullmatch(part) is None
        ):
            _document(pointer, "path")
        folded.append(part.casefold())
    return text, tuple(parts), tuple(folded)


def _roles(value, pointer):
    if type(value) is not list:
        _document(pointer, "type")
    if not value or len(value) > 6:
        _document(pointer, "shape")
    seen = []
    previous = None
    for index, item in enumerate(value):
        role = _str(item, pointer + "/" + str(index))
        if role not in _ROLE_SET:
            _document(pointer + "/" + str(index), "enum")
        if role in seen:
            _document(pointer, "shape")
        if previous is not None and role <= previous:
            _document(pointer, "target_order")
        seen.append(role)
        previous = role
    return list(seen)


def _request_targets(value, pointer, max_targets):
    if type(value) is not list:
        _document(pointer, "type")
    if not value:
        _document(pointer, "shape")
    if len(value) > max_targets:
        _document(pointer, "integer_bound")
    owned = []
    seen = set()
    previous = None
    prefixes = {}
    components_list = []
    for index, item in enumerate(value):
        ip = pointer + "/" + str(index)
        rec = _object(item, ip, ("path", "roles", "allow_executable_source"))
        path, components, folded_parts = _git_path(rec["path"], ip + "/path")
        roles = _roles(rec["roles"], ip + "/roles")
        flag = _bool(rec["allow_executable_source"], ip + "/allow_executable_source")
        if flag:
            for role in roles:
                if role not in _EXEC_ROLES:
                    _document(ip + "/allow_executable_source", "role_permission")
        if path in seen:
            _document(ip + "/path", "target_order")
        seen.add(path)
        if previous is not None and path <= previous:
            _document(ip + "/path", "target_order")
        previous = path
        for depth in range(1, len(components) + 1):
            exact = tuple(components[:depth])
            folded = tuple(folded_parts[:depth])
            existing = prefixes.get(folded)
            if existing is not None and existing != exact:
                _document(ip + "/path", "path")
            prefixes[folded] = exact
        for earlier in components_list:
            if len(earlier) < len(components) and components[: len(earlier)] == earlier:
                _document(ip + "/path", "path")
            if len(components) < len(earlier) and earlier[: len(components)] == components:
                _document(ip + "/path", "path")
        components_list.append(components)
        owned.append(
            {
                "path": path,
                "roles": roles,
                "allow_executable_source": flag,
            }
        )
    return owned


def _limit_group(value, pointer, keys, hard):
    rec = _object(value, pointer, keys)
    out = {}
    for key in keys:
        out[key] = _int(rec[key], pointer + "/" + key, 1, hard[key])
    return out


def _limits_map(value, pointer, hard):
    rec = _object(value, pointer, ("git", "config", "public"))
    return {
        "git": _limit_group(rec["git"], pointer + "/git", _GIT_LIMIT_KEYS, hard["git"]),
        "config": _limit_group(
            rec["config"], pointer + "/config", _CONFIG_LIMIT_KEYS, hard["config"]
        ),
        "public": _limit_group(
            rec["public"], pointer + "/public", _PUBLIC_LIMIT_KEYS, hard["public"]
        ),
    }


def _association(value, pointer):
    if value is None:
        return None
    rec = _object(value, pointer, ("association_id", "sha256"))
    ident = _str(rec["association_id"], pointer + "/association_id")
    if len(ident) != 68 or not ident.startswith("sva-") or not _is_hex(ident[4:], 64):
        _document(pointer + "/association_id", "identity")
    digest = _sha256(rec["sha256"], pointer + "/sha256")
    return {"association_id": ident, "sha256": digest}


def _executor(value, pointer):
    if type(value) is not dict:
        _document(pointer, "type")
    if value.get("kind") == "unknown":
        rec = _object(value, pointer, ("kind", "id"))
        if rec["id"] is not None:
            _document(pointer + "/id", "type")
        return {"kind": "unknown", "id": None}
    rec = _object(value, pointer, ("kind", "id"))
    kind = _str(rec["kind"], pointer + "/kind")
    if kind != "human" and kind != "host_tool":
        _document(pointer + "/kind", "enum")
    ident = _str(rec["id"], pointer + "/id")
    if not _nfc(ident):
        _document(pointer + "/id", "noncanonical_text")
    size = _utf8_len(ident)
    if size < 1 or size > 128:
        _document(pointer + "/id", "string_bound")
    for char in ident:
        code = ord(char)
        if code in _CONTROL_C0 or code in _CONTROL_C1:
            _document(pointer + "/id", "noncanonical_text")
    return {"kind": kind, "id": ident}


def _split_repo(repository):
    owner, name = repository.split("/", 1)
    return owner, name


def _commit_url(repository, commit_oid):
    owner, name = _split_repo(repository)
    return "https://github.com/" + owner + "/" + name + "/commit/" + commit_oid


def _blob_url(repository, commit_oid, path):
    owner, name = _split_repo(repository)
    return (
        "https://github.com/"
        + owner
        + "/"
        + name
        + "/blob/"
        + commit_oid
        + "/"
        + path
    )


def _raw_url(repository, commit_oid, path):
    owner, name = _split_repo(repository)
    return (
        "https://raw.githubusercontent.com/"
        + owner
        + "/"
        + name
        + "/"
        + commit_oid
        + "/"
        + path
    )


def _hosting(value, pointer, request_data):
    if value is None:
        return None
    rec = _object(
        value,
        pointer,
        (
            "provider",
            "actor",
            "repository",
            "object_format",
            "commit_oid",
            "locator",
            "statement",
        ),
    )
    provider = _str(rec["provider"], pointer + "/provider")
    if provider != "github":
        _document(pointer + "/provider", "enum")
    actor = _executor(rec["actor"], pointer + "/actor")
    repository = _repository_saved(rec["repository"], pointer + "/repository")
    if repository != request_data["repository"]:
        _binding(pointer + "/repository", "repository")
    object_format = _object_format(rec["object_format"], pointer + "/object_format")
    if object_format != request_data["object_format"]:
        _binding(pointer + "/object_format", "object_format")
    commit_oid = _oid(rec["commit_oid"], pointer + "/commit_oid", object_format)
    if commit_oid != request_data["commit_oid"]:
        _binding(pointer + "/commit_oid", "commit_oid")
    locator = _str(rec["locator"], pointer + "/locator")
    expected = _commit_url(repository, commit_oid)
    if locator != expected:
        _document(pointer + "/locator", "identity")
    statement = _str(rec["statement"], pointer + "/statement")
    if not _nfc(statement):
        _document(pointer + "/statement", "noncanonical_text")
    size = _utf8_len(statement)
    if size < 1 or size > 2048:
        _document(pointer + "/statement", "string_bound")
    for char in statement:
        code = ord(char)
        if char in ("\n", "\t"):
            continue
        if code in _CONTROL_C0 or code in _CONTROL_C1:
            _document(pointer + "/statement", "noncanonical_text")
    return {
        "provider": "github",
        "actor": actor,
        "repository": repository,
        "object_format": object_format,
        "commit_oid": commit_oid,
        "locator": locator,
        "statement": statement,
    }


def _locator_for_path(value, pointer, request_data, path):
    if value is None:
        return None
    text = _str(value, pointer)
    blob = _blob_url(request_data["repository"], request_data["commit_oid"], path)
    raw = _raw_url(request_data["repository"], request_data["commit_oid"], path)
    if text != blob and text != raw:
        _document(pointer, "identity")
    return text


def _materialize(session, raw_limits, pointer):
    try:
        limits = session.materialize_limits(raw_limits)
    except CodeProofStructureError as exc:
        reason = exc.reason
        if reason == "limits":
            _document(pointer, "limits")
        _document(pointer, "type" if reason == "type" else "shape")
    return {
        "git": dict(limits["git"]),
        "config": dict(limits["config"]),
        "public": dict(limits["public"]),
    }


def _output_limits(limits):
    public = limits["public"]
    out = {}
    for key in _OUTPUT_LIMIT_KEYS:
        out[key] = public[key]
    return out


def _validate_request_input(session, parsed):
    rec = _object(
        parsed,
        "",
        (
            "paper_id",
            "source_association",
            "repository",
            "object_format",
            "commit_oid",
            "targets",
            "require_repository_assertion",
        ),
        optional=("limits",),
    )
    paper_id = _paper_id(rec["paper_id"], "/paper_id")
    association = _association(rec["source_association"], "/source_association")
    repository = _repository_input(rec["repository"], "/repository")
    object_format = _object_format(rec["object_format"], "/object_format")
    commit_oid = _oid(rec["commit_oid"], "/commit_oid", object_format)
    require = _bool(
        rec["require_repository_assertion"], "/require_repository_assertion"
    )
    hard = _materialize(session, None, "/limits")
    if "limits" in rec:
        limits = _limits_map(rec["limits"], "/limits", hard)
        limits = _materialize(session, limits, "/limits")
    else:
        limits = hard
    max_targets = limits["git"]["max_targets"]
    targets = _request_targets(rec["targets"], "/targets", max_targets)
    data = {
        "paper_id": paper_id,
        "source_association": association,
        "repository": repository,
        "object_format": object_format,
        "commit_oid": commit_oid,
        "targets": targets,
        "require_repository_assertion": require,
        "limits": limits,
        "profile_sha256": session.profile_sha256,
    }
    try:
        session.validate_structure("video-paper-wiki.code-proof-request-input.v1", rec)
    except CodeProofStructureError:
        _document("", "shape")
    return data


def _normalized_targets(value, pointer, request_data, limits):
    if type(value) is not list:
        _document(pointer, "type")
    requested = [item["path"] for item in request_data["targets"]]
    if len(value) != len(requested):
        _document(pointer, "target_order")
    rows = []
    cap = limits["public"]["max_inline_normalized_bytes"]
    for index, item in enumerate(value):
        ip = pointer + "/" + str(index)
        if type(item) is not dict:
            _document(ip, "type")
        path = _str(item.get("path"), ip + "/path") if "path" in item else None
        if path is None:
            _document(ip, "shape")
        if path != requested[index]:
            _document(ip + "/path", "target_order")
        status = _str(item.get("status"), ip + "/status") if "status" in item else None
        if status == "present":
            rec = _object(item, ip, ("path", "status", "locator", "text"))
            locator = _locator_for_path(
                rec["locator"], ip + "/locator", request_data, path
            )
            if locator is None:
                _document(ip + "/locator", "shape")
            text = _str(rec["text"], ip + "/text")
            if "\r" in text:
                _document(ip + "/text", "noncanonical_text")
            encoded = text.encode("utf-8")
            if len(encoded) > cap:
                _limit(ip + "/text", "max_inline_normalized_bytes", cap, len(encoded))
            rows.append(
                {
                    "path": path,
                    "status": "present",
                    "locator": locator,
                    "text": text,
                }
            )
        elif status == "missing":
            rec = _object(item, ip, ("path", "status", "locator", "reason"))
            locator = _locator_for_path(
                rec["locator"], ip + "/locator", request_data, path
            )
            reason = _str(rec["reason"], ip + "/reason")
            if reason != "host_reported_missing":
                _document(ip + "/reason", "enum")
            rows.append(
                {
                    "path": path,
                    "status": "missing",
                    "locator": locator,
                    "reason": reason,
                }
            )
        elif status == "inaccessible":
            rec = _object(item, ip, ("path", "status", "locator", "reason"))
            locator = _locator_for_path(
                rec["locator"], ip + "/locator", request_data, path
            )
            reason = _str(rec["reason"], ip + "/reason")
            if reason != "permission_denied":
                _document(ip + "/reason", "enum")
            rows.append(
                {
                    "path": path,
                    "status": "inaccessible",
                    "locator": locator,
                    "reason": reason,
                }
            )
        elif status == "unavailable":
            rec = _object(item, ip, ("path", "status", "locator", "reason"))
            locator = _locator_for_path(
                rec["locator"], ip + "/locator", request_data, path
            )
            reason = _str(rec["reason"], ip + "/reason")
            if reason not in _HOST_UNAVAILABLE:
                _document(ip + "/reason", "enum")
            rows.append(
                {
                    "path": path,
                    "status": "unavailable",
                    "locator": locator,
                    "reason": reason,
                }
            )
        else:
            _document(ip + "/status", "enum")
    return rows


def _validate_observe_input(parsed, request_data, limits, pointer=""):
    rec = _object(
        parsed,
        pointer,
        ("mode", "observed_at", "executor", "hosting_assertion"),
        optional=("targets",),
    )
    mode = _str(rec["mode"], pointer + "/mode")
    if mode != "git_objects" and mode != "normalized_text":
        _document(pointer + "/mode", "enum")
    observed_at = _datetime(rec["observed_at"], pointer + "/observed_at")
    executor = _executor(rec["executor"], pointer + "/executor")
    hosting = _hosting(
        rec["hosting_assertion"], pointer + "/hosting_assertion", request_data
    )
    if mode == "git_objects":
        if "targets" in rec:
            _document(pointer, "shape")
        return {
            "mode": "git_objects",
            "observed_at": observed_at,
            "executor": executor,
            "hosting_assertion": hosting,
        }
    if "targets" not in rec:
        _document(pointer + "/targets", "shape")
    targets = _normalized_targets(
        rec["targets"], pointer + "/targets", request_data, limits
    )
    return {
        "mode": "normalized_text",
        "observed_at": observed_at,
        "executor": executor,
        "hosting_assertion": hosting,
        "targets": targets,
    }


def _seal(kind, data):
    schema = _KINDS[kind]
    core = {"schema": schema, "kind": kind, "data": data}
    try:
        digest = hashlib.sha256(canonicalize(core)).hexdigest()
    except CanonicalJsonError:
        _document("", "canonical_bytes")
    ident = "ce1:" + kind + ":" + digest
    envelope = {"schema": schema, "kind": kind, "id": ident, "data": data}
    try:
        saved = canonicalize(envelope) + b"\n"
    except CanonicalJsonError:
        _document("", "canonical_bytes")
    return envelope, saved, {"id": ident, "sha256": hashlib.sha256(saved).hexdigest()}


def _reference(saved, ident):
    return {"id": ident, "sha256": hashlib.sha256(saved).hexdigest()}


def _parse_saved(session, payload, kind, pointer):
    parsed = _parse_json_bytes(payload, pointer)
    rec = _object(parsed, pointer, ("schema", "kind", "id", "data"))
    schema = _str(rec["schema"], pointer + "/schema")
    got_kind = _str(rec["kind"], pointer + "/kind")
    ident = _str(rec["id"], pointer + "/id")
    if got_kind != kind:
        _binding(pointer + "/kind", "reference_kind")
    if schema != _KINDS[kind]:
        _document(pointer + "/schema", "identity")
    try:
        rendered = canonicalize(
            {
                "schema": schema,
                "kind": got_kind,
                "id": ident,
                "data": rec["data"],
            }
        ) + b"\n"
    except CanonicalJsonError:
        _document(pointer, "canonical_bytes")
    if rendered != payload:
        _document(pointer, "canonical_bytes")
    core = {"schema": schema, "kind": got_kind, "data": rec["data"]}
    digest = hashlib.sha256(canonicalize(core)).hexdigest()
    expected = "ce1:" + kind + ":" + digest
    if ident != expected:
        _document(pointer + "/id", "identity")
    try:
        session.validate_structure(_KINDS[kind], rec)
    except CodeProofStructureError:
        _document(pointer, "shape")
    if kind == "code-proof-request":
        rec["data"] = _validate_saved_request_data(session, rec["data"], pointer)
    return rec, _reference(payload, ident)


def _validate_saved_request_data(session, data, pointer):
    rec = _object(
        data,
        pointer,
        (
            "paper_id",
            "source_association",
            "repository",
            "object_format",
            "commit_oid",
            "targets",
            "require_repository_assertion",
            "limits",
            "profile_sha256",
        ),
    )
    paper_id = _paper_id(rec["paper_id"], pointer + "/paper_id")
    association = _association(
        rec["source_association"], pointer + "/source_association"
    )
    repository = _repository_saved(rec["repository"], pointer + "/repository")
    object_format = _object_format(rec["object_format"], pointer + "/object_format")
    commit_oid = _oid(rec["commit_oid"], pointer + "/commit_oid", object_format)
    require = _bool(
        rec["require_repository_assertion"],
        pointer + "/require_repository_assertion",
    )
    hard = _materialize(session, None, pointer + "/limits")
    limits = _limits_map(rec["limits"], pointer + "/limits", hard)
    limits = _materialize(session, limits, pointer + "/limits")
    if limits != rec["limits"]:
        _document(pointer + "/limits", "limits")
    max_targets = limits["git"]["max_targets"]
    targets = _request_targets(rec["targets"], pointer + "/targets", max_targets)
    profile = _sha256(rec["profile_sha256"], pointer + "/profile_sha256")
    rebuilt = {
        "paper_id": paper_id,
        "source_association": association,
        "repository": repository,
        "object_format": object_format,
        "commit_oid": commit_oid,
        "targets": targets,
        "require_repository_assertion": require,
        "limits": limits,
        "profile_sha256": profile,
    }
    if rebuilt != rec:
        _document(pointer, "canonical_bytes")
    if profile != session.profile_sha256:
        _binding(pointer + "/profile_sha256", "profile")
    return rebuilt


def _path_key(path):
    if type(path) is not str:
        _document("/path", "type")
    try:
        encoded = path.encode("ascii")
    except UnicodeEncodeError:
        _document("/path", "path")
    return hashlib.sha256(encoded).hexdigest() + ".json"


def _stored_body(batch_id, oid):
    return ".work/" + batch_id + "/" + _NAMESPACE + "/objects/" + oid + ".body"


def _stored_derived(batch_id, family, filename):
    return ".work/" + batch_id + "/" + _NAMESPACE + "/" + family + "/" + filename


def _text_metadata(payload):
    normalized = normalize_code_bytes(payload)
    meta = code_text_metadata(payload)
    return {
        "normalized_size_bytes": len(normalized),
        "normalized_sha256": meta["normalized_sha256"],
        "newline_style": meta["newline_style"],
        "ends_with_newline": meta["ends_with_newline"],
        "line_count": meta["line_count"],
    }


def _raw_rows(request_data, git_proof, bodies):
    by_path = {}
    for row in git_proof["targets"]:
        by_path[row["path"]] = row
    rows = []
    for target in request_data["targets"]:
        path = target["path"]
        proof = by_path[path]
        outcome = proof["outcome"]
        if outcome == "permitted_regular_blob":
            oid = proof["blob"]["oid"]
            try:
                text = _text_metadata(bodies[oid])
            except ContractError:
                rows.append(
                    {
                        "path": path,
                        "status": "unsupported_source_bytes",
                        "reason": "unsupported_source_bytes",
                        "text": None,
                    }
                )
                continue
            rows.append(
                {
                    "path": path,
                    "status": "source_text",
                    "reason": None,
                    "text": text,
                }
            )
            continue
        if outcome == "missing":
            rows.append(
                {
                    "path": path,
                    "status": "missing",
                    "reason": proof["reason"],
                    "text": None,
                }
            )
            continue
        rows.append(
            {
                "path": path,
                "status": "unsafe",
                "reason": proof["reason"],
                "text": None,
            }
        )
    return rows


def _normalized_rows(acquisition):
    rows = []
    for item in acquisition["targets"]:
        path = item["path"]
        status = item["status"]
        if status == "present":
            encoded = item["text"].encode("utf-8")
            rows.append(
                {
                    "path": path,
                    "status": "normalized_text",
                    "reason": None,
                    "text": _text_metadata(encoded),
                }
            )
        elif status == "missing":
            rows.append(
                {
                    "path": path,
                    "status": "host_missing",
                    "reason": "host_reported_missing",
                    "text": None,
                }
            )
        elif status == "inaccessible":
            rows.append(
                {
                    "path": path,
                    "status": "host_inaccessible",
                    "reason": "permission_denied",
                    "text": None,
                }
            )
        else:
            rows.append(
                {
                    "path": path,
                    "status": "host_unavailable",
                    "reason": item["reason"],
                    "text": None,
                }
            )
    return rows


def _capabilities(mode, hosting):
    raw = mode == "git_objects"
    assertion = "host_asserted" if hosting is not None else "unverified"
    return {
        "git_objects_verified": raw,
        "raw_bytes_retained": raw,
        "repository_assertion": assertion,
        "source_association_verified": False,
    }


def _eligibility(mode, request_data, rows, hosting):
    if mode != "git_objects":
        complete = False
        handoff_ok = False
    else:
        complete = True
        for row in rows:
            if row["status"] != "source_text":
                complete = False
                break
        handoff_ok = complete
    repo_met = (not request_data["require_repository_assertion"]) or (
        hosting is not None
    )
    if not repo_met:
        handoff_ok = False
    if mode != "git_objects":
        handoff_ok = False
        complete = False
    return {
        "complete_target_set": complete,
        "repository_requirement_met": repo_met,
        "source_handoff_eligible": complete and repo_met and mode == "git_objects",
    }


def _git_targets(request_data):
    rows = []
    for item in request_data["targets"]:
        rows.append(
            {
                "path": item["path"],
                "allow_executable_source": item["allow_executable_source"],
            }
        )
    return rows


def _raw_body(batch_id, oid, payload):
    return {
        "path": _stored_body(batch_id, oid),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _unobserved_targets(request_data):
    rows = []
    for item in request_data["targets"]:
        rows.append(
            {
                "path": item["path"],
                "status": "unobserved",
                "reason": None,
                "text": None,
            }
        )
    return rows


def _family_names(snapshot, family):
    prefix = family + "/"
    names = []
    for name in snapshot:
        if name.startswith(prefix):
            names.append(name)
    names.sort()
    return names


def _objects_prefix(expected_oids, snapshot):
    present = []
    for name in _family_names(snapshot, "objects"):
        oid = name[8:-5]
        present.append(oid)
    present_set = set(present)
    expected_set = set(expected_oids)
    if present_set - expected_set:
        return False, present
    seen_missing = False
    for oid in expected_oids:
        if oid in present_set:
            if seen_missing:
                return False, present
        else:
            seen_missing = True
    return True, present


def _bind_present_bodies(bundle_data, present_oids, snapshot):
    by_oid = {}
    for record in bundle_data["objects"]:
        by_oid[record["oid"]] = record
    object_format = bundle_data["object_format"]
    for oid in present_oids:
        name = "objects/" + oid + ".body"
        payload = snapshot[name]
        record = by_oid[oid]
        if type(payload) is not bytes:
            _binding("/objects", "raw_body")
        if (
            type(record.get("body_size_bytes")) is not int
            or len(payload) != record["body_size_bytes"]
        ):
            _binding("/objects", "raw_body")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != record.get("body_sha256"):
            _binding("/objects", "raw_body")
        try:
            got_oid, body_sha, framed_sha = git_object_ids(
                object_format, record["object_type"], payload
            )
        except (CodeGitProofError, KeyError, TypeError):
            _binding("/objects", "raw_body")
        if (
            got_oid != oid
            or body_sha != record.get("body_sha256")
            or framed_sha != record.get("framed_sha256")
        ):
            _binding("/objects", "raw_body")


def _handoff_prefix(paths, snapshot):
    expected = ["handoffs/" + _path_key(path) for path in paths]
    present = set(_family_names(snapshot, "handoffs"))
    extra = present - set(expected)
    if extra:
        return False, []
    prefix = []
    seen_missing = False
    for path, name in zip(paths, expected):
        if name in present:
            if seen_missing:
                return False, prefix
            prefix.append(path)
        else:
            seen_missing = True
    return True, prefix


def _bind_profile(session, request_data):
    if request_data["profile_sha256"] != session.profile_sha256:
        _binding("/request/profile_sha256", "profile")


def _bind_ref(got, expected, pointer, reason):
    if type(got) is not dict or got.get("id") != expected["id"]:
        _binding(pointer, reason)
    if got.get("sha256") != expected["sha256"]:
        _binding(pointer, "reference_hash")


def _conflict_name(name):
    if name == "request.json":
        _conflict("/request", "request_changed")
    if name in ("intent.json", "bundle.json", "observation.json") or name.startswith(
        "objects/"
    ):
        pointer = _SLOT_POINTERS.get(name, "/observation")
        _conflict(pointer, "acquisition_changed")
    if name.startswith("configs/"):
        _conflict("/config", "artifact_changed")
    if name.startswith("handoffs/"):
        _conflict("/handoffs", "artifact_changed")
    _conflict("/output", "artifact_changed")


def _check_size(payload, cap, pointer, limit_name):
    size = len(payload)
    if size > cap:
        _limit(pointer, limit_name, cap, size)


def _install_plan(session, planned, peak):
    snap = session.snapshot()
    writes = []
    reused = {}
    for name, payload in planned:
        if name in snap:
            if snap[name] == payload:
                reused[name] = True
                continue
            _conflict_name(name)
        reused[name] = False
        writes.append((name, payload))
    layout = session.layout_state()
    current = layout["current_file_bytes"]
    for name, payload in writes:
        size = len(payload)
        needed = current + 2 * size
        if needed > peak:
            _limit("/output", "max_output_peak_bytes", peak, needed)
        current += size
    for name, payload in writes:
        session.install(name, payload)
    return reused


def _derive_observation(
    *,
    request_data,
    request_ref,
    intent_ref,
    bundle_ref,
    mode,
    acquisition,
    git_proof,
    bodies,
    batch_id,
):
    hosting = acquisition["hosting_assertion"]
    if mode == "git_objects":
        rows = _raw_rows(request_data, git_proof, bodies)
        data = {
            "request": request_ref,
            "intent": intent_ref,
            "bundle": bundle_ref,
            "mode": "git_objects",
            "git_proof": _plain(git_proof),
            "targets": rows,
            "capabilities": _capabilities(mode, hosting),
            "eligibility": _eligibility(mode, request_data, rows, hosting),
        }
    else:
        rows = _normalized_rows(acquisition)
        data = {
            "request": request_ref,
            "intent": intent_ref,
            "bundle": None,
            "mode": "normalized_text",
            "git_proof": None,
            "targets": rows,
            "capabilities": _capabilities(mode, hosting),
            "eligibility": _eligibility(mode, request_data, rows, hosting),
        }
    return _seal("code-proof-observation", data)


def _derive_config(
    *,
    batch_id,
    request_data,
    request_ref,
    observation_ref,
    bundle_ref,
    observation_data,
    git_proof,
    bodies,
    path,
    config_format,
):
    requested = None
    for item in request_data["targets"]:
        if item["path"] == path:
            requested = item
            break
    if requested is None:
        _ineligible("/path", "path_not_requested", [])
    if observation_data["mode"] != "git_objects":
        _not_ready("/config", "raw_evidence_required")
    target_row = None
    for row in observation_data["targets"]:
        if row["path"] == path:
            target_row = row
            break
    if target_row is None:
        _ineligible("/path", "path_not_requested", [])
    status = target_row["status"]
    if status == "missing":
        _ineligible(
            "/path",
            "missing",
            [{"path": path, "status": "missing", "reason": target_row["reason"]}],
        )
    if status == "unsafe":
        _ineligible(
            "/path",
            "unsafe",
            [{"path": path, "status": "unsafe", "reason": target_row["reason"]}],
        )
    if status == "unsupported_source_bytes":
        _ineligible(
            "/path",
            "unsupported_source_bytes",
            [
                {
                    "path": path,
                    "status": "unsupported_source_bytes",
                    "reason": "unsupported_source_bytes",
                }
            ],
        )
    if "configuration" not in requested["roles"]:
        _ineligible(
            "/path",
            "configuration_role_required",
            [
                {
                    "path": path,
                    "status": "source_text",
                    "reason": "configuration_role_required",
                }
            ],
        )
    proof_row = None
    for row in git_proof["targets"]:
        if row["path"] == path:
            proof_row = row
            break
    blob_oid = proof_row["blob"]["oid"]
    payload = bodies[blob_oid]
    raw_body = _raw_body(batch_id, blob_oid, payload)
    if config_format == "source-only":
        data = {
            "request": request_ref,
            "observation": observation_ref,
            "bundle": bundle_ref,
            "path": path,
            "object_format": request_data["object_format"],
            "blob_oid": blob_oid,
            "raw_body": raw_body,
            "format": "source-only",
            "result": None,
            "source_only_reason": "explicit_source_only",
        }
        return _seal("code-config-evidence", data)
    result = parse_code_config_bytes(
        payload=payload,
        config_format=config_format,
        limits=request_data["limits"]["config"],
    )
    data = {
        "request": request_ref,
        "observation": observation_ref,
        "bundle": bundle_ref,
        "path": path,
        "object_format": request_data["object_format"],
        "blob_oid": blob_oid,
        "raw_body": raw_body,
        "format": config_format,
        "result": result,
        "source_only_reason": None,
    }
    return _seal("code-config-evidence", data)


def _derive_handoff(
    *,
    batch_id,
    request_data,
    request_ref,
    observation_ref,
    bundle_ref,
    observation_data,
    git_proof,
    bodies,
    path,
):
    requested = None
    for item in request_data["targets"]:
        if item["path"] == path:
            requested = item
            break
    proof_row = None
    for row in git_proof["targets"]:
        if row["path"] == path:
            proof_row = row
            break
    blob = proof_row["blob"]
    payload = bodies[blob["oid"]]
    data = {
        "successor_only": True,
        "request": request_ref,
        "observation": observation_ref,
        "bundle": bundle_ref,
        "paper_id": request_data["paper_id"],
        "source_association": request_data["source_association"],
        "repository": request_data["repository"],
        "object_format": request_data["object_format"],
        "commit_oid": request_data["commit_oid"],
        "root_tree_oid": git_proof["root_tree_oid"],
        "path": path,
        "roles": list(requested["roles"]),
        "allow_executable_source": requested["allow_executable_source"],
        "blob": {
            "oid": blob["oid"],
            "body_size_bytes": blob["body_size_bytes"],
            "body_sha256": blob["body_sha256"],
            "framed_sha256": blob["framed_sha256"],
        },
        "raw_body": _raw_body(batch_id, blob["oid"], payload),
        "text": _text_metadata(payload),
        "proof": _plain(proof_row),
        "repository_assertion": observation_data["capabilities"]["repository_assertion"],
        "source_association_verified": False,
    }
    return _seal("code-source-handoff", data)


def _non_source_blockers(observation_data):
    blockers = []
    for row in observation_data["targets"]:
        if row["status"] != "source_text":
            blockers.append(
                {
                    "path": row["path"],
                    "status": row["status"],
                    "reason": row["reason"],
                }
            )
    blockers.sort(key=lambda item: item["path"])
    return blockers[:32]


def _replay_observation(session, batch_id, view):
    request_data = view["request_data"]
    request_ref = view["request_ref"]
    intent_data = view["intent_data"]
    mode = intent_data["mode"]
    acquisition = intent_data["acquisition"]
    git_proof = None
    bodies = {}
    bundle_ref = None
    if mode == "git_objects":
        bundle_ref = view["bundle_ref"]
        inventory = view["bundle_data"]["objects"]
        snap = view["snapshot"]
        for record in inventory:
            name = "objects/" + record["oid"] + ".body"
            bodies[record["oid"]] = snap[name]
        git_proof = verify_code_git_objects(
            object_format=request_data["object_format"],
            commit_oid=request_data["commit_oid"],
            root_tree_oid=view["bundle_data"]["root_tree_oid"],
            objects=inventory,
            bodies=bodies,
            targets=_git_targets(request_data),
            limits=request_data["limits"]["git"],
        )
    envelope, saved, ref = _derive_observation(
        request_data=request_data,
        request_ref=request_ref,
        intent_ref=view["intent_ref"],
        bundle_ref=bundle_ref,
        mode=mode,
        acquisition=acquisition,
        git_proof=git_proof,
        bodies=bodies,
        batch_id=batch_id,
    )
    return envelope, saved, ref, git_proof, bodies


def _inspect(session, batch_id):
    snapshot = session.snapshot()
    layout = session.layout_state()
    families = layout["current_families"]
    view = {
        "snapshot": snapshot,
        "layout": layout,
        "state": None,
        "request_env": None,
        "request_ref": None,
        "request_data": None,
        "intent_env": None,
        "intent_ref": None,
        "intent_data": None,
        "bundle_env": None,
        "bundle_ref": None,
        "bundle_data": None,
        "observation_env": None,
        "observation_ref": None,
        "observation_data": None,
        "mode": None,
        "git_proof": None,
        "bodies": {},
        "configs": [],
        "handoffs": [],
        "handoff_prefix": [],
    }
    has_request = "request.json" in snapshot
    has_intent = "intent.json" in snapshot
    has_bundle = "bundle.json" in snapshot
    has_observation = "observation.json" in snapshot
    object_names = _family_names(snapshot, "objects")
    config_names = _family_names(snapshot, "configs")
    handoff_names = _family_names(snapshot, "handoffs")
    if not has_request:
        if (
            has_intent
            or has_bundle
            or has_observation
            or object_names
            or config_names
            or handoff_names
            or families["objects"]
            or families["configs"]
            or families["handoffs"]
        ):
            if has_intent or has_bundle or has_observation:
                _state("/request", "missing_dependency")
            _state("/output", "forbidden_family")
        view["state"] = "empty"
        return view
    request_env, request_ref = _parse_saved(
        session, snapshot["request.json"], "code-proof-request", "/request"
    )
    request_data = request_env["data"]
    _bind_profile(session, request_data)
    view["request_env"] = request_env
    view["request_ref"] = request_ref
    view["request_data"] = request_data
    if not has_intent:
        if (
            has_bundle
            or has_observation
            or object_names
            or config_names
            or handoff_names
            or families["objects"]
            or families["configs"]
            or families["handoffs"]
        ):
            if has_bundle or has_observation:
                _state("/intent", "missing_dependency")
            _state("/output", "forbidden_family")
        view["state"] = "requested"
        view["mode"] = None
        return view
    intent_env, intent_ref = _parse_saved(
        session, snapshot["intent.json"], "code-acquisition-intent", "/intent"
    )
    intent_data = intent_env["data"]
    _bind_ref(intent_data["request"], request_ref, "/intent/request", "request")
    acquisition = _validate_observe_input(
        intent_data["acquisition"],
        request_data,
        request_data["limits"],
        "/intent/acquisition",
    )
    if acquisition != intent_data["acquisition"]:
        _document("/intent/acquisition", "canonical_bytes")
    mode = intent_data["mode"]
    if mode != acquisition["mode"]:
        _document("/intent/mode", "shape")
    view["intent_env"] = intent_env
    view["intent_ref"] = intent_ref
    view["intent_data"] = intent_data
    view["mode"] = mode
    if mode == "normalized_text":
        if (
            has_bundle
            or object_names
            or config_names
            or handoff_names
            or families["objects"]
            or families["configs"]
            or families["handoffs"]
        ):
            if has_bundle:
                _state("/bundle", "forbidden_slot")
            _state("/output", "forbidden_family")
        if intent_data["bundle"] is not None:
            _binding("/intent/bundle", "derived")
        if not has_observation:
            view["state"] = "pending_normalized"
            return view
        observation_env, observation_ref = _parse_saved(
            session, snapshot["observation.json"], "code-proof-observation", "/observation"
        )
        view["observation_env"] = observation_env
        view["observation_ref"] = observation_ref
        view["observation_data"] = observation_env["data"]
        envelope, saved, ref, git_proof, bodies = _replay_observation(
            session, batch_id, view
        )
        if saved != snapshot["observation.json"]:
            _binding("/observation", "derived")
        view["git_proof"] = git_proof
        view["bodies"] = bodies
        view["state"] = "observed"
        return view
    if mode != "git_objects":
        _document("/intent/mode", "enum")
    if intent_data["bundle"] is None:
        _binding("/intent/bundle", "derived")
    if not has_bundle:
        if has_observation:
            _state("/bundle", "missing_dependency")
        if object_names or families["objects"]:
            _state("/objects", "forbidden_family")
        if config_names or handoff_names or families["configs"] or families["handoffs"]:
            _state("/output", "forbidden_family")
        view["state"] = "pending_raw_bundle"
        return view
    bundle_env, bundle_ref = _parse_saved(
        session, snapshot["bundle.json"], "code-git-bundle", "/bundle"
    )
    bundle_data = bundle_env["data"]
    _bind_ref(bundle_data["request"], request_ref, "/bundle/request", "request")
    _bind_ref(
        intent_data["bundle"]["reference"], bundle_ref, "/intent/bundle/reference", "derived"
    )
    if bundle_data["repository"] != request_data["repository"]:
        _binding("/bundle/repository", "repository")
    if bundle_data["object_format"] != request_data["object_format"]:
        _binding("/bundle/object_format", "object_format")
    if bundle_data["commit_oid"] != request_data["commit_oid"]:
        _binding("/bundle/commit_oid", "commit_oid")
    view["bundle_env"] = bundle_env
    view["bundle_ref"] = bundle_ref
    view["bundle_data"] = bundle_data
    previous_oid = None
    for index, record in enumerate(bundle_data["objects"]):
        oid = record["oid"]
        if previous_oid is not None and oid <= previous_oid:
            _document("/bundle/objects/" + str(index) + "/oid", "target_order")
        previous_oid = oid
    expected_oids = [record["oid"] for record in bundle_data["objects"]]
    prefix_ok, present_oids = _objects_prefix(expected_oids, snapshot)
    if not prefix_ok:
        _state("/objects", "nonprefix_objects")
    _bind_present_bodies(bundle_data, present_oids, snapshot)
    complete_objects = present_oids == expected_oids
    if not has_observation:
        if config_names or handoff_names or families["configs"] or families["handoffs"]:
            _state("/output", "forbidden_family")
        view["state"] = "pending_raw_bodies"
        return view
    if not complete_objects:
        _state("/observation", "missing_dependency")
    observation_env, observation_ref = _parse_saved(
        session, snapshot["observation.json"], "code-proof-observation", "/observation"
    )
    view["observation_env"] = observation_env
    view["observation_ref"] = observation_ref
    view["observation_data"] = observation_env["data"]
    envelope, saved, ref, git_proof, bodies = _replay_observation(
        session, batch_id, view
    )
    if saved != snapshot["observation.json"]:
        _binding("/observation", "derived")
    view["git_proof"] = git_proof
    view["bodies"] = bodies
    paths = [item["path"] for item in request_data["targets"]]
    ok_prefix, prefix_paths = _handoff_prefix(paths, snapshot)
    if not ok_prefix:
        _state("/handoffs", "nonprefix_handoffs")
    view["handoff_prefix"] = prefix_paths
    configs = []
    for name in config_names:
        env, ref = _parse_saved(session, snapshot[name], "code-config-evidence", "/config")
        path = env["data"]["path"]
        expected_name = "configs/" + _path_key(path)
        if expected_name != name:
            _state("/config", "orphan_derived")
        if path not in paths:
            _state("/config", "orphan_derived")
        fresh_env, fresh_saved, fresh_ref = _derive_config(
            batch_id=batch_id,
            request_data=request_data,
            request_ref=request_ref,
            observation_ref=observation_ref,
            bundle_ref=bundle_ref,
            observation_data=observation_env["data"],
            git_proof=git_proof,
            bodies=bodies,
            path=path,
            config_format=env["data"]["format"],
        )
        if fresh_saved != snapshot[name]:
            _binding("/config", "derived")
        configs.append(
            {
                "path": path,
                "reference": fresh_ref,
                "stored_path": _stored_derived(batch_id, "configs", _path_key(path)),
                "name": name,
                "format": env["data"]["format"],
            }
        )
    configs.sort(key=lambda item: item["path"])
    view["configs"] = configs
    handoffs = []
    for path in prefix_paths:
        name = "handoffs/" + _path_key(path)
        env, ref = _parse_saved(session, snapshot[name], "code-source-handoff", "/handoffs")
        if env["data"]["path"] != path:
            _state("/handoffs", "orphan_derived")
        fresh_env, fresh_saved, fresh_ref = _derive_handoff(
            batch_id=batch_id,
            request_data=request_data,
            request_ref=request_ref,
            observation_ref=observation_ref,
            bundle_ref=bundle_ref,
            observation_data=observation_env["data"],
            git_proof=git_proof,
            bodies=bodies,
            path=path,
        )
        if fresh_saved != snapshot[name]:
            _binding("/handoffs", "derived")
        blob_oid = fresh_env["data"]["blob"]["oid"]
        handoffs.append(
            {
                "path": path,
                "reference": fresh_ref,
                "stored_path": _stored_derived(batch_id, "handoffs", _path_key(path)),
                "source_body_path": _stored_body(batch_id, blob_oid),
                "name": name,
            }
        )
    view["handoffs"] = handoffs
    view["state"] = "observed"
    return view


def _missing_list(view):
    state = view["state"]
    if state in ("empty", "observed"):
        return []
    if state == "requested":
        return ["intent.json"]
    if state == "pending_normalized":
        return ["observation.json"]
    if state == "pending_raw_bundle":
        return ["bundle.json", "observation.json"]
    expected = [record["oid"] for record in view["bundle_data"]["objects"]]
    present = set()
    for name in _family_names(view["snapshot"], "objects"):
        present.add(name[8:-5])
    missing = []
    for oid in expected:
        if oid not in present:
            missing.append("objects/" + oid + ".body")
    missing.append("observation.json")
    return missing


def _next_action(view):
    state = view["state"]
    if state == "empty":
        return "prepare_request"
    if state == "requested":
        return "supply_observation"
    if state in (
        "pending_normalized",
        "pending_raw_bundle",
        "pending_raw_bodies",
    ):
        return "resume_same_observation"
    eligibility = view["observation_data"]["eligibility"]
    if not eligibility["source_handoff_eligible"]:
        return "new_request_or_acquisition_required"
    paths = [item["path"] for item in view["request_data"]["targets"]]
    if len(view["handoff_prefix"]) < len(paths):
        return "prepare_source_handoff"
    return "successor_capture"


def _status_payload(batch_id, view):
    state = view["state"]
    request_ref = view["request_ref"]
    intent_ref = view["intent_ref"]
    bundle_ref = view["bundle_ref"]
    observation_ref = view["observation_ref"]
    mode = view["mode"]
    if state == "empty":
        targets = []
        capabilities = None
        eligibility = None
    elif state == "observed":
        targets = _plain(view["observation_data"]["targets"])
        capabilities = _plain(view["observation_data"]["capabilities"])
        eligibility = _plain(view["observation_data"]["eligibility"])
    else:
        targets = _unobserved_targets(view["request_data"])
        capabilities = None
        eligibility = None
    configs = []
    for item in view["configs"]:
        configs.append(
            {
                "path": item["path"],
                "reference": item["reference"],
                "stored_path": item["stored_path"],
            }
        )
    handoffs = []
    for item in view["handoffs"]:
        handoffs.append(
            {
                "path": item["path"],
                "reference": item["reference"],
                "stored_path": item["stored_path"],
            }
        )
    return {
        "batch_id": batch_id,
        "state": state,
        "request": request_ref,
        "intent": intent_ref,
        "bundle": bundle_ref,
        "observation": observation_ref,
        "mode": mode,
        "missing": _missing_list(view),
        "targets": targets,
        "capabilities": capabilities,
        "eligibility": eligibility,
        "configs": configs,
        "handoffs": handoffs,
        "next_action": _next_action(view),
    }


def _acquisition_targets(request_data):
    rows = []
    repository = request_data["repository"]
    commit_oid = request_data["commit_oid"]
    for item in request_data["targets"]:
        path = item["path"]
        rows.append(
            {
                "path": path,
                "github_url": _blob_url(repository, commit_oid, path),
                "raw_url": _raw_url(repository, commit_oid, path),
            }
        )
    return rows


def _ensure_limits(session, limits):
    session.set_output_limits(_output_limits(limits))


def request_code_proof(*, input_path, batch_id):
    _require_kw_str(input_path, "/input")
    _require_kw_str(batch_id, "/batch_id")
    with open_code_session(batch_id=batch_id) as session:
        raw = session.retain_input(input_path, maximum=65536)
        parsed = _parse_json_bytes(raw, "/input")
        data = _validate_request_input(session, parsed)
        _inspect(session, batch_id)
        _ensure_limits(session, data["limits"])
        envelope, saved, ref = _seal("code-proof-request", data)
        _check_size(
            saved,
            data["limits"]["public"]["max_request_bytes"],
            "/request",
            "max_request_bytes",
        )
        try:
            session.validate_structure(
                "video-paper-wiki.code-proof-request.v1", envelope
            )
        except CodeProofStructureError:
            _document("/request", "shape")
        reused = _install_plan(
            session,
            [("request.json", saved)],
            data["limits"]["public"]["max_output_peak_bytes"],
        )
        session.verify()
        return {
            "batch_id": batch_id,
            "request": ref,
            "already_staged": reused["request.json"],
            "acquisition_targets": _acquisition_targets(data),
        }


def observe_code_proof(*, input_path, batch_id, bundle_dir=None):
    _require_kw_str(input_path, "/input")
    _require_kw_str(batch_id, "/batch_id")
    if bundle_dir is not None:
        _require_kw_str(bundle_dir, "/bundle")
    with open_code_session(batch_id=batch_id) as session:
        snap = session.snapshot()
        if "request.json" not in snap:
            _not_ready("/request", "request_absent")
        request_env, request_ref = _parse_saved(
            session, snap["request.json"], "code-proof-request", "/request"
        )
        request_data = request_env["data"]
        _bind_profile(session, request_data)
        limits = request_data["limits"]
        _ensure_limits(session, limits)
        raw = session.retain_input(input_path, maximum=1048576)
        acquisition = _validate_observe_input(
            _parse_json_bytes(raw, "/input"), request_data, limits
        )
        mode = acquisition["mode"]
        if mode == "git_objects":
            if bundle_dir is None:
                _document("", "shape")
        else:
            if bundle_dir is not None:
                _document("", "shape")
        git_proof = None
        bodies = {}
        bundle_saved = None
        bundle_ref = None
        bundle_data = None
        if mode == "git_objects":
            manifest = session.retain_bundle_manifest(bundle_dir)
            bundle_env, bundle_ref = _parse_saved(
                session, manifest, "code-git-bundle", "/bundle"
            )
            bundle_data = bundle_env["data"]
            _bind_ref(bundle_data["request"], request_ref, "/bundle/request", "request")
            if bundle_data["repository"] != request_data["repository"]:
                _binding("/bundle/repository", "repository")
            if bundle_data["object_format"] != request_data["object_format"]:
                _binding("/bundle/object_format", "object_format")
            if bundle_data["commit_oid"] != request_data["commit_oid"]:
                _binding("/bundle/commit_oid", "commit_oid")
            _check_size(
                manifest,
                limits["public"]["max_bundle_bytes"],
                "/bundle",
                "max_bundle_bytes",
            )
            bodies = session.retain_bundle_bodies(
                object_format=request_data["object_format"],
                objects=bundle_data["objects"],
                limits=limits["git"],
            )
            git_proof = verify_code_git_objects(
                object_format=request_data["object_format"],
                commit_oid=request_data["commit_oid"],
                root_tree_oid=bundle_data["root_tree_oid"],
                objects=bundle_data["objects"],
                bodies=bodies,
                targets=_git_targets(request_data),
                limits=limits["git"],
            )
            bundle_saved = manifest
        _inspect(session, batch_id)
        intent_data = {
            "request": request_ref,
            "mode": mode,
            "acquisition": acquisition,
            "bundle": None
            if mode != "git_objects"
            else {"directory": bundle_dir, "reference": bundle_ref},
        }
        intent_env, intent_saved, intent_ref = _seal(
            "code-acquisition-intent", intent_data
        )
        _check_size(
            intent_saved,
            limits["public"]["max_intent_bytes"],
            "/intent",
            "max_intent_bytes",
        )
        obs_env, obs_saved, obs_ref = _derive_observation(
            request_data=request_data,
            request_ref=request_ref,
            intent_ref=intent_ref,
            bundle_ref=bundle_ref,
            mode=mode,
            acquisition=acquisition,
            git_proof=git_proof,
            bodies=bodies,
            batch_id=batch_id,
        )
        _check_size(
            obs_saved,
            limits["public"]["max_observation_bytes"],
            "/observation",
            "max_observation_bytes",
        )
        if "intent.json" in snap and snap["intent.json"] != intent_saved:
            _parse_saved(
                session, snap["intent.json"], "code-acquisition-intent", "/intent"
            )
            _conflict("/intent", "acquisition_changed")
        if mode == "git_objects":
            if "bundle.json" in snap and snap["bundle.json"] != bundle_saved:
                _conflict("/bundle", "acquisition_changed")
            for record in bundle_data["objects"]:
                name = "objects/" + record["oid"] + ".body"
                if name in snap and snap[name] != bodies[record["oid"]]:
                    _conflict("/observation", "acquisition_changed")
        if "observation.json" in snap and snap["observation.json"] != obs_saved:
            _parse_saved(
                session,
                snap["observation.json"],
                "code-proof-observation",
                "/observation",
            )
            _binding("/observation", "derived")
        planned = [("intent.json", intent_saved)]
        if mode == "git_objects":
            planned.append(("bundle.json", bundle_saved))
            for record in bundle_data["objects"]:
                planned.append(
                    ("objects/" + record["oid"] + ".body", bodies[record["oid"]])
                )
        planned.append(("observation.json", obs_saved))
        _install_plan(session, planned, limits["public"]["max_output_peak_bytes"])
        session.verify()
        view = _inspect(session, batch_id)
        return {
            "batch_id": batch_id,
            "observation": obs_ref,
            "status": _status_payload(batch_id, view),
        }


def status_code_proof(*, batch_id):
    _require_kw_str(batch_id, "/batch_id")
    with open_code_session(batch_id=batch_id) as session:
        snap = session.snapshot()
        if "request.json" in snap:
            request_env, request_ref = _parse_saved(
                session, snap["request.json"], "code-proof-request", "/request"
            )
            _bind_profile(session, request_env["data"])
            _ensure_limits(session, request_env["data"]["limits"])
        view = _inspect(session, batch_id)
        session.verify()
        return _status_payload(batch_id, view)


def config_code_proof(*, path, config_format, batch_id):
    _require_kw_str(path, "/path")
    _require_kw_str(config_format, "/format")
    _require_kw_str(batch_id, "/batch_id")
    if config_format not in ("json", "toml", "source-only"):
        _document("/format", "enum")
    _git_path(path, "/path")
    with open_code_session(batch_id=batch_id) as session:
        snap = session.snapshot()
        if "request.json" not in snap:
            _not_ready("/request", "request_absent")
        request_env, request_ref = _parse_saved(
            session, snap["request.json"], "code-proof-request", "/request"
        )
        _bind_profile(session, request_env["data"])
        _ensure_limits(session, request_env["data"]["limits"])
        view = _inspect(session, batch_id)
        if view["state"] != "observed":
            _not_ready("/observation", "observation_incomplete")
        if view["mode"] != "git_objects":
            _not_ready("/config", "raw_evidence_required")
        name = "configs/" + _path_key(path)
        if name in snap:
            existing, existing_ref = _parse_saved(
                session, snap[name], "code-config-evidence", "/config"
            )
            if existing["data"]["format"] != config_format:
                _conflict("/config", "config_format_changed")
        envelope, saved, ref = _derive_config(
            batch_id=batch_id,
            request_data=view["request_data"],
            request_ref=view["request_ref"],
            observation_ref=view["observation_ref"],
            bundle_ref=view["bundle_ref"],
            observation_data=view["observation_data"],
            git_proof=view["git_proof"],
            bodies=view["bodies"],
            path=path,
            config_format=config_format,
        )
        _check_size(
            saved,
            view["request_data"]["limits"]["public"]["max_config_document_bytes"],
            "/config",
            "max_config_document_bytes",
        )
        reused = _install_plan(
            session,
            [(name, saved)],
            view["request_data"]["limits"]["public"]["max_output_peak_bytes"],
        )
        session.verify()
        return {
            "batch_id": batch_id,
            "path": path,
            "config": ref,
            "stored_path": _stored_derived(batch_id, "configs", _path_key(path)),
            "already_staged": reused[name],
        }


def handoff_code_proof(*, batch_id):
    _require_kw_str(batch_id, "/batch_id")
    with open_code_session(batch_id=batch_id) as session:
        snap = session.snapshot()
        if "request.json" not in snap:
            _not_ready("/request", "request_absent")
        request_env, request_ref = _parse_saved(
            session, snap["request.json"], "code-proof-request", "/request"
        )
        _bind_profile(session, request_env["data"])
        _ensure_limits(session, request_env["data"]["limits"])
        view = _inspect(session, batch_id)
        if view["state"] != "observed":
            _not_ready("/observation", "observation_incomplete")
        if view["mode"] != "git_objects":
            _not_ready("/handoffs", "raw_evidence_required")
        eligibility = view["observation_data"]["eligibility"]
        if not eligibility["complete_target_set"]:
            _ineligible(
                "/targets",
                "complete_target_set_required",
                _non_source_blockers(view["observation_data"]),
            )
        if not eligibility["repository_requirement_met"]:
            _ineligible("/hosting_assertion", "repository_assertion_required", [])
        paths = [item["path"] for item in view["request_data"]["targets"]]
        planned = []
        rows = []
        cap = view["request_data"]["limits"]["public"]["max_handoff_bytes"]
        for index, path in enumerate(paths):
            envelope, saved, ref = _derive_handoff(
                batch_id=batch_id,
                request_data=view["request_data"],
                request_ref=view["request_ref"],
                observation_ref=view["observation_ref"],
                bundle_ref=view["bundle_ref"],
                observation_data=view["observation_data"],
                git_proof=view["git_proof"],
                bodies=view["bodies"],
                path=path,
            )
            _check_size(saved, cap, "/handoffs/" + str(index), "max_handoff_bytes")
            name = "handoffs/" + _path_key(path)
            planned.append((name, saved))
            blob_oid = envelope["data"]["blob"]["oid"]
            rows.append(
                {
                    "path": path,
                    "handoff": ref,
                    "stored_path": _stored_derived(
                        batch_id, "handoffs", _path_key(path)
                    ),
                    "source_body_path": _stored_body(batch_id, blob_oid),
                    "name": name,
                    "saved": saved,
                }
            )
        reused = _install_plan(
            session,
            planned,
            view["request_data"]["limits"]["public"]["max_output_peak_bytes"],
        )
        session.verify()
        result_rows = []
        for row in rows:
            result_rows.append(
                {
                    "path": row["path"],
                    "handoff": row["handoff"],
                    "stored_path": row["stored_path"],
                    "source_body_path": row["source_body_path"],
                    "already_staged": reused[row["name"]],
                }
            )
        return {"batch_id": batch_id, "handoffs": result_rows}


def _emit_known(command, exc):
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    details = getattr(exc, "details", None)
    exit_code = getattr(exc, "exit_code", 2)
    if type(code) is not str or type(message) is not str:
        raise exc
    if type(details) is not dict:
        details = {}
    return emit_error(command, code, message, details, exit_code=exit_code)


def run_code_evidence_command(args):
    leaf = getattr(args, "code_evidence_cmd", None)
    if type(leaf) is not str:
        return emit_error("code-evidence", "USAGE", "missing command")
    command = "code-evidence." + leaf
    try:
        if leaf == "request":
            data = request_code_proof(
                input_path=args.input, batch_id=args.batch_id
            )
        elif leaf == "observe":
            data = observe_code_proof(
                input_path=args.input,
                batch_id=args.batch_id,
                bundle_dir=getattr(args, "bundle_dir", None),
            )
        elif leaf == "status":
            data = status_code_proof(batch_id=args.batch_id)
        elif leaf == "config":
            data = config_code_proof(
                path=args.path,
                config_format=args.format,
                batch_id=args.batch_id,
            )
        elif leaf == "handoff":
            data = handoff_code_proof(batch_id=args.batch_id)
        else:
            return emit_error(command, "USAGE", "missing command")
        return emit_success(command, data)
    except CodeProofPublicError as exc:
        return _emit_known(command, exc)
    except CodeProofIOError as exc:
        return _emit_known(command, exc)
    except CodeGitProofError as exc:
        return _emit_known(command, exc)
    except CodeConfigError as exc:
        return _emit_known(command, exc)
    except CodeProofResourceError as exc:
        return emit_error(
            command,
            "CODE_PROOF_RESOURCE_INVALID",
            "CODE evidence resource is invalid",
            {
                "phase": "setup",
                "group": "resources",
                "reason": exc.reason,
                "operation": None,
                "errno": None,
                "prior_code": None,
                "prior_operation": None,
                "prior_errno": None,
                "failed_groups": [],
            },
        )
    except CodeProofStructureError as exc:
        mapped = "limits" if exc.reason == "limits" else (
            "type" if exc.reason == "type" else "shape"
        )
        return emit_error(
            command,
            "CODE_PROOF_DOCUMENT_INVALID",
            _MESSAGES["CODE_PROOF_DOCUMENT_INVALID"],
            {"instance_pointer": "", "reason": mapped},
        )
