"""Private code-proof resource pins, origin plan, and structural validators."""

from __future__ import annotations

import copy
import enum
import hashlib
import json
from dataclasses import dataclass
from typing import Final, NoReturn

from jsonschema.validators import Draft202012Validator, extend
from referencing import Registry
from referencing.jsonschema import DRAFT202012

__all__ = [
    "CodeProofResourceError",
    "CodeProofResources",
    "CodeProofStructureError",
    "ResourceOriginPlan",
    "ResourcePin",
    "compile_code_proof_resources",
    "resource_origin_plan",
]

_DRAFT_2020_12: Final[str] = "https://json-schema.org/draft/2020-12/schema"
_SCHEMA_ID_PREFIX: Final[str] = "https://video-paper-wiki.dev/schemas/"
_PROFILE_LOGICAL_KEY: Final[str] = "profiles/code-proof-v1.json"
_PROFILE_SCHEMA_NAME: Final[str] = "video-paper-wiki.code-proof-profile.v1"
_PROFILE_NAME: Final[str] = "code-proof-v1"
_PROFILE_REVISION: Final[int] = 1
_INVALID_ERROR_REASON: Final[str] = "Invalid CODE proof error reason"
_RESOURCE_MESSAGE: Final[str] = "CODE proof resource: "
_STRUCTURE_MESSAGE: Final[str] = "CODE proof structure: "

_FORBIDDEN_SCHEMA_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "$anchor",
        "$dynamicAnchor",
        "$dynamicRef",
        "$recursiveAnchor",
        "$recursiveRef",
    }
)
_PROFILE_KEYS: Final[tuple[str, ...]] = (
    "schema",
    "profile",
    "revision",
    "limits",
    "admission",
    "schemas",
)
_PROFILE_ROW_KEYS: Final[tuple[str, ...]] = (
    "title",
    "filename",
    "size_bytes",
    "sha256",
)
_ADMISSION_KEYS: Final[tuple[str, ...]] = (
    "max_request_input_bytes",
    "max_observe_input_bytes",
)
_LIMIT_GROUP_KEYS: Final[tuple[str, ...]] = ("git", "config", "public")
_GIT_LIMIT_KEYS: Final[tuple[str, ...]] = (
    "max_targets",
    "max_objects",
    "max_tree_entries",
    "max_object_bytes",
    "max_total_object_bytes",
)
_CONFIG_LIMIT_KEYS: Final[tuple[str, ...]] = (
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
_PUBLIC_LIMIT_KEYS: Final[tuple[str, ...]] = (
    "max_bundle_bytes",
    "max_inline_normalized_bytes",
    "max_request_bytes",
    "max_intent_bytes",
    "max_observation_bytes",
    "max_config_document_bytes",
    "max_handoff_bytes",
    "max_output_peak_bytes",
)
_HARD_LIMITS: Final[dict[str, dict[str, int]]] = {
    "git": {
        "max_targets": 32,
        "max_objects": 2048,
        "max_tree_entries": 32768,
        "max_object_bytes": 8388608,
        "max_total_object_bytes": 33554432,
    },
    "config": {
        "max_source_bytes": 262144,
        "max_depth": 32,
        "max_nodes": 1024,
        "max_array_items": 256,
        "max_object_keys": 1024,
        "max_key_bytes": 256,
        "max_string_codepoints": 16384,
        "max_scalars": 512,
        "max_numeric_lexeme_bytes": 128,
        "max_numeric_coefficient_digits": 64,
        "max_numeric_abs_exponent": 128,
        "max_numeric_canonical_bytes": 256,
        "max_declarations": 4096,
    },
    "public": {
        "max_bundle_bytes": 1048576,
        "max_inline_normalized_bytes": 16384,
        "max_request_bytes": 65536,
        "max_intent_bytes": 1048576,
        "max_observation_bytes": 2097152,
        "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072,
        "max_output_peak_bytes": 134217728,
    },
}
_LIMIT_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "git": _GIT_LIMIT_KEYS,
    "config": _CONFIG_LIMIT_KEYS,
    "public": _PUBLIC_LIMIT_KEYS,
}
_ADMISSION: Final[dict[str, int]] = {
    "max_request_input_bytes": 65536,
    "max_observe_input_bytes": 1048576,
}
_SCHEMA_STEMS: Final[tuple[tuple[str, int, str], ...]] = (
    (
        "code-acquisition-intent",
        818,
        "acf785648ef3e8c085db3ec0863b0c67230464a15a24aa93f5e5a27418fedbef",
    ),
    (
        "code-config-evidence",
        803,
        "86be2b14d9ef748283aa0c5671ac6b94ea038cc04eee553e1f5a93dd1ce2821b",
    ),
    (
        "code-git-bundle",
        778,
        "69f112e15e430a537bf05417281013bc1ce9d674c9dfc0521f3adb4884cf9aac",
    ),
    (
        "code-proof-command-result",
        353,
        "a9040ea7362d2ca8d9f6a16a3e05f7d80b02a91c5ba086d4c925988c059641d2",
    ),
    (
        "code-proof-common",
        96085,
        "e151c80eba28e8a0ee8346a64bb7969fd0be03db64b90b282e5fa6b86498ea82",
    ),
    (
        "code-proof-observation",
        818,
        "da1f61febafe8a7601b63114c15c8523ff381db47549b072965066e14a8cb85b",
    ),
    (
        "code-proof-observe-input",
        350,
        "146459e1da831ec6c7fb26382608686047085fe3de98f4101a1ba19f5e7be137",
    ),
    (
        "code-proof-request-input",
        350,
        "a0492606c26a681ef9c457d27708b7b797ea3de3bff11f0d6525fc5d48913339",
    ),
    (
        "code-proof-request",
        794,
        "d3f34854069567640564ae000f6b7f71c77f903cf92588704bc579deb7429ad7",
    ),
    (
        "code-source-handoff",
        799,
        "27f5388be15eb78e3aced47f72832468d3a7b6b54bc352263afb7f5534402876",
    ),
)
_PROFILE_SIZE_BYTES: Final[int] = 3761
_PROFILE_SHA256: Final[str] = (
    "650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32"
)


class _ResourceReason(enum.StrEnum):
    resource_origin = "resource_origin"
    resource_hash = "resource_hash"
    resource_shape = "resource_shape"


class _StructureReason(enum.StrEnum):
    type = "type"
    shape = "shape"
    limits = "limits"


def _validated_reason(reason: object, members: type[enum.StrEnum]) -> enum.StrEnum:
    try:
        if type(reason) is not str:
            raise TypeError
        return members(reason)
    except (TypeError, ValueError):
        raise ValueError(_INVALID_ERROR_REASON) from None


class CodeProofResourceError(Exception):
    """Private resource-origin, pin, parse, profile, or schema failure."""

    def __init__(self, reason: str) -> None:
        parsed = _validated_reason(reason, _ResourceReason)
        self._reason = parsed
        super().__init__(_RESOURCE_MESSAGE + parsed.value)

    @property
    def reason(self) -> str:
        return self._reason.value


class CodeProofStructureError(Exception):
    """Private instance type, title/schema, or limits failure."""

    def __init__(self, reason: str) -> None:
        parsed = _validated_reason(reason, _StructureReason)
        self._reason = parsed
        super().__init__(_STRUCTURE_MESSAGE + parsed.value)

    @property
    def reason(self) -> str:
        return self._reason.value


@dataclass(frozen=True, slots=True)
class ResourcePin:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ResourceOriginPlan:
    layout: str
    package_directory: str
    schemas_directory: str
    profiles_directory: str
    resources: tuple[ResourcePin, ...]


def _schema_filename(stem: str) -> str:
    return f"video-paper-wiki.{stem}.v1.schema.json"


def _schema_title(stem: str) -> str:
    return f"video-paper-wiki.{stem}.v1"


def _schema_id(stem: str) -> str:
    return _SCHEMA_ID_PREFIX + _schema_filename(stem)


def _schema_logical_key(stem: str) -> str:
    return "schemas/" + _schema_filename(stem)


def _build_production_pins() -> tuple[ResourcePin, ...]:
    pins = [
        ResourcePin(
            relative_path=_schema_logical_key(stem),
            size_bytes=size_bytes,
            sha256=digest,
        )
        for stem, size_bytes, digest in _SCHEMA_STEMS
    ]
    pins.append(
        ResourcePin(
            relative_path=_PROFILE_LOGICAL_KEY,
            size_bytes=_PROFILE_SIZE_BYTES,
            sha256=_PROFILE_SHA256,
        )
    )
    return tuple(sorted(pins, key=lambda pin: pin.relative_path))


_PRODUCTION_PINS: Final[tuple[ResourcePin, ...]] = _build_production_pins()
_PIN_BY_PATH: Final[dict[str, ResourcePin]] = {
    pin.relative_path: pin for pin in _PRODUCTION_PINS
}
_RESOURCE_KEYS_SORTED: Final[tuple[str, ...]] = tuple(
    pin.relative_path for pin in _PRODUCTION_PINS
)
_RESOURCE_KEY_SET: Final[frozenset[str]] = frozenset(_RESOURCE_KEYS_SORTED)
_SCHEMA_IDS: Final[frozenset[str]] = frozenset(
    _schema_id(stem) for stem, _size, _digest in _SCHEMA_STEMS
)
_COMMON_SCHEMA_ID: Final[str] = _schema_id("code-proof-common")
_PROFILE_DEF_REF: Final[str] = _COMMON_SCHEMA_ID + "#/$defs/profile"
_EXPECTED_PROFILE_ROWS: Final[tuple[dict[str, object], ...]] = tuple(
    {
        "title": _schema_title(stem),
        "filename": _schema_filename(stem),
        "size_bytes": size_bytes,
        "sha256": digest,
    }
    for stem, size_bytes, digest in _SCHEMA_STEMS
)


def _strict_is_integer(_checker: object, instance: object) -> bool:
    return type(instance) is int


_STRICT_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer",
    _strict_is_integer,
)
_StrictDraft202012Validator = extend(
    Draft202012Validator,
    type_checker=_STRICT_TYPE_CHECKER,
)


def _join_absolute(parts: tuple[str, ...]) -> str:
    return "/" + "/".join(parts)


def _absolute_lexical_parts(path: str) -> tuple[str, ...]:
    if type(path) is not str or "\0" in path:
        raise CodeProofResourceError("resource_origin") from None
    if not path.startswith("/") or path.endswith("/"):
        raise CodeProofResourceError("resource_origin") from None
    parts = tuple(path.split("/")[1:])
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise CodeProofResourceError("resource_origin") from None
    return parts


def resource_origin_plan() -> ResourceOriginPlan:
    try:
        parts = _absolute_lexical_parts(__file__)
    except CodeProofResourceError:
        raise
    except Exception:
        raise CodeProofResourceError("resource_origin") from None
    if len(parts) < 2 or parts[-2] != "video_paper_wiki":
        raise CodeProofResourceError("resource_origin") from None
    package_parts = parts[:-1]
    package_directory = _join_absolute(package_parts)
    profiles_directory = _join_absolute(package_parts + ("profiles",))
    package_parent = package_parts[-2] if len(package_parts) >= 2 else None
    if package_parent == "src":
        layout = "source"
        schemas_directory = _join_absolute(package_parts[:-2] + ("schemas",))
    else:
        layout = "installed"
        schemas_directory = _join_absolute(package_parts + ("schemas",))
    return ResourceOriginPlan(
        layout=layout,
        package_directory=package_directory,
        schemas_directory=schemas_directory,
        profiles_directory=profiles_directory,
        resources=_PRODUCTION_PINS,
    )


def _contains_surrogate(text: str) -> bool:
    for char in text:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            return True
    return False


def _reject_json_number(_lexeme: str) -> None:
    raise ValueError("non-integer JSON number")


def _strict_object_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ValueError("invalid JSON object")
        result[key] = value
    return result


def _require_plain_json_tree(root: object) -> None:
    ancestors: set[int] = set()
    completed: set[int] = set()
    stack: list[tuple[object, bool]] = [(root, False)]
    while stack:
        node, exiting = stack.pop()
        kind = type(node)
        if exiting:
            ident = id(node)
            ancestors.discard(ident)
            completed.add(ident)
            continue
        if kind is dict or kind is list:
            ident = id(node)
            if ident in ancestors:
                raise CodeProofResourceError("resource_shape") from None
            if ident in completed:
                continue
            ancestors.add(ident)
            stack.append((node, True))
            if kind is dict:
                for key, child in node.items():
                    if type(key) is not str:
                        raise CodeProofResourceError("resource_shape") from None
                    if _contains_surrogate(key):
                        raise CodeProofResourceError("resource_shape") from None
                    stack.append((child, False))
            else:
                for child in node:
                    stack.append((child, False))
        elif kind is str:
            if _contains_surrogate(node):
                raise CodeProofResourceError("resource_shape") from None
        elif kind is int or kind is bool or kind is type(None):
            continue
        else:
            raise CodeProofResourceError("resource_shape") from None


def _parse_resource_bytes(data: bytes) -> dict:
    if type(data) is not bytes or data.startswith(b"\xef\xbb\xbf"):
        raise CodeProofResourceError("resource_shape") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CodeProofResourceError("resource_shape") from None
    if text.startswith("\ufeff"):
        raise CodeProofResourceError("resource_shape") from None
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except Exception:
        raise CodeProofResourceError("resource_shape") from None
    if type(parsed) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    _require_plain_json_tree(parsed)
    try:
        rendered = json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
    except Exception:
        raise CodeProofResourceError("resource_shape") from None
    if rendered != text:
        raise CodeProofResourceError("resource_shape") from None
    return parsed


def _unescape_pointer_token(token: str) -> str:
    index = 0
    length = len(token)
    while index < length:
        if token[index] == "~":
            if index + 1 >= length or token[index + 1] not in "01":
                raise CodeProofResourceError("resource_shape") from None
            index += 2
            continue
        index += 1
    return token.replace("~1", "/").replace("~0", "~")


def _canonical_list_index(token: str) -> int:
    if type(token) is not str:
        raise CodeProofResourceError("resource_shape") from None
    if token == "":
        raise CodeProofResourceError("resource_shape") from None
    if token[0] == "0":
        if len(token) != 1:
            raise CodeProofResourceError("resource_shape") from None
    else:
        for char in token:
            if char < "0" or char > "9":
                raise CodeProofResourceError("resource_shape") from None
    try:
        return int(token)
    except Exception:
        raise CodeProofResourceError("resource_shape") from None


def _resolve_json_pointer(document: object, fragment: str) -> None:
    if fragment == "":
        return
    if type(fragment) is not str or not fragment.startswith("/"):
        raise CodeProofResourceError("resource_shape") from None
    current = document
    for raw_token in fragment.split("/")[1:]:
        token = _unescape_pointer_token(raw_token)
        if type(current) is dict:
            if token not in current:
                raise CodeProofResourceError("resource_shape") from None
            current = current[token]
            continue
        if type(current) is list:
            index = _canonical_list_index(token)
            if index >= len(current):
                raise CodeProofResourceError("resource_shape") from None
            current = current[index]
            continue
        raise CodeProofResourceError("resource_shape") from None


def _resolve_ref(
    ref: object,
    current_root: dict,
    schemas: dict[str, dict],
) -> None:
    if type(ref) is not str or "%" in ref:
        raise CodeProofResourceError("resource_shape") from None
    if ref.startswith("#"):
        _resolve_json_pointer(current_root, ref[1:])
        return
    if ref in schemas:
        return
    base, separator, fragment = ref.partition("#")
    if separator == "" or base not in schemas:
        raise CodeProofResourceError("resource_shape") from None
    _resolve_json_pointer(schemas[base], fragment)


def _walk_schema_document(document: dict, current_root: dict, schemas: dict[str, dict]) -> None:
    visited: set[int] = set()
    stack: list[object] = [document]
    while stack:
        node = stack.pop()
        kind = type(node)
        if kind is dict:
            ident = id(node)
            if ident in visited:
                continue
            visited.add(ident)
            nested = node is not document
            for key, child in node.items():
                if key == "$id" and nested:
                    raise CodeProofResourceError("resource_shape") from None
                if key in _FORBIDDEN_SCHEMA_KEYWORDS:
                    raise CodeProofResourceError("resource_shape") from None
                if key == "$ref":
                    _resolve_ref(child, current_root, schemas)
                stack.append(child)
        elif kind is list:
            ident = id(node)
            if ident in visited:
                continue
            visited.add(ident)
            for child in node:
                stack.append(child)


def _validate_schema_references(schemas: dict[str, dict]) -> None:
    if type(schemas) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    try:
        _require_plain_json_tree(schemas)
        if frozenset(schemas) != frozenset(_SCHEMA_IDS):
            raise CodeProofResourceError("resource_shape") from None
        for schema_id in _SCHEMA_IDS:
            document = schemas[schema_id]
            if type(document) is not dict:
                raise CodeProofResourceError("resource_shape") from None
            if "$id" not in document:
                raise CodeProofResourceError("resource_shape") from None
            identified = document["$id"]
            if type(identified) is not str or identified != schema_id:
                raise CodeProofResourceError("resource_shape") from None
        for schema_id in sorted(_SCHEMA_IDS):
            document = schemas[schema_id]
            _walk_schema_document(document, document, schemas)
    except CodeProofResourceError:
        raise
    except Exception:
        raise CodeProofResourceError("resource_shape") from None


def _require_exact_int(value: object, expected: int) -> None:
    if type(value) is not int or value != expected:
        raise CodeProofResourceError("resource_shape") from None


def _require_exact_str(value: object, expected: str) -> None:
    if type(value) is not str or value != expected:
        raise CodeProofResourceError("resource_shape") from None


def _require_exact_mapping(value: object, expected_keys: tuple[str, ...]) -> dict:
    if type(value) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    keys: list[str] = []
    for key in value:
        if type(key) is not str:
            raise CodeProofResourceError("resource_shape") from None
        keys.append(key)
    if frozenset(keys) != frozenset(expected_keys):
        raise CodeProofResourceError("resource_shape") from None
    return value


def _validate_hard_limits(limits: object) -> None:
    document = _require_exact_mapping(limits, _LIMIT_GROUP_KEYS)
    for group in _LIMIT_GROUP_KEYS:
        inner = _require_exact_mapping(document[group], _LIMIT_KEYS[group])
        for key in _LIMIT_KEYS[group]:
            _require_exact_int(inner[key], _HARD_LIMITS[group][key])


def _validate_profile_inventory(profile: dict) -> None:
    if type(profile) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    document = _require_exact_mapping(profile, _PROFILE_KEYS)
    _require_exact_str(document["schema"], _PROFILE_SCHEMA_NAME)
    _require_exact_str(document["profile"], _PROFILE_NAME)
    _require_exact_int(document["revision"], _PROFILE_REVISION)
    _validate_hard_limits(document["limits"])
    admission = _require_exact_mapping(document["admission"], _ADMISSION_KEYS)
    for key in _ADMISSION_KEYS:
        _require_exact_int(admission[key], _ADMISSION[key])
    rows = document["schemas"]
    if type(rows) is not list or len(rows) != len(_EXPECTED_PROFILE_ROWS):
        raise CodeProofResourceError("resource_shape") from None
    seen_filenames: set[str] = set()
    seen_titles: set[str] = set()
    for index, expected in enumerate(_EXPECTED_PROFILE_ROWS):
        row = rows[index]
        if type(row) is not dict:
            raise CodeProofResourceError("resource_shape") from None
        closed = _require_exact_mapping(row, _PROFILE_ROW_KEYS)
        title = closed["title"]
        filename = closed["filename"]
        _require_exact_str(title, expected["title"])  # type: ignore[arg-type]
        _require_exact_str(filename, expected["filename"])  # type: ignore[arg-type]
        _require_exact_int(closed["size_bytes"], expected["size_bytes"])  # type: ignore[arg-type]
        _require_exact_str(closed["sha256"], expected["sha256"])  # type: ignore[arg-type]
        if filename in seen_filenames or title in seen_titles:
            raise CodeProofResourceError("resource_shape") from None
        seen_filenames.add(filename)  # type: ignore[arg-type]
        seen_titles.add(title)  # type: ignore[arg-type]
    return None


def _require_retained_mapping(retained_bytes: object) -> list[tuple[str, bytes]]:
    if type(retained_bytes) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    items = list(retained_bytes.items())
    for key, value in items:
        if type(key) is not str or type(value) is not bytes:
            raise CodeProofResourceError("resource_shape") from None
    if {key for key, _value in items} != _RESOURCE_KEY_SET:
        raise CodeProofResourceError("resource_shape") from None
    by_key = {key: value for key, value in items}
    return [(key, by_key[key]) for key in _RESOURCE_KEYS_SORTED]


def _check_production_pins(snapshot: list[tuple[str, bytes]]) -> None:
    for key, blob in snapshot:
        pin = _PIN_BY_PATH[key]
        digest = hashlib.sha256(blob).hexdigest()
        if len(blob) != pin.size_bytes or digest != pin.sha256:
            raise CodeProofResourceError("resource_hash") from None


def _require_schema_header(document: object, stem: str) -> dict:
    if type(document) is not dict:
        raise CodeProofResourceError("resource_shape") from None
    if "$schema" not in document or "$id" not in document or "title" not in document:
        raise CodeProofResourceError("resource_shape") from None
    _require_exact_str(document["$schema"], _DRAFT_2020_12)
    _require_exact_str(document["$id"], _schema_id(stem))
    _require_exact_str(document["title"], _schema_title(stem))
    return document


def _deny_registry_retrieve(_uri: object) -> NoReturn:
    raise CodeProofResourceError("resource_shape") from None


def _build_registry(schemas_by_id: dict[str, dict]) -> Registry:
    registry = Registry(retrieve=_deny_registry_retrieve)
    for schema_id in sorted(schemas_by_id):
        registry = registry.with_resource(
            schema_id,
            DRAFT202012.create_resource(copy.deepcopy(schemas_by_id[schema_id])),
        )
    return registry


def _copy_hard_limits(source: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {
        "git": dict(source["git"]),
        "config": dict(source["config"]),
        "public": dict(source["public"]),
    }


def _preflight_instance(instance: object) -> None:
    stack: list[tuple[object, bool]] = [(instance, False)]
    ancestors: set[int] = set()
    done: set[int] = set()
    while stack:
        value, leaving = stack.pop()
        if leaving:
            ancestors.remove(id(value))
            done.add(id(value))
            continue
        ty = type(value)
        if ty is bool or value is None or ty is int:
            continue
        if ty is str:
            if _contains_surrogate(value):
                raise CodeProofStructureError("type") from None
            continue
        if ty is dict:
            ident = id(value)
            if ident in ancestors:
                raise CodeProofStructureError("type") from None
            if ident in done:
                continue
            for key in value:
                if type(key) is not str or _contains_surrogate(key):
                    raise CodeProofStructureError("type") from None
            ancestors.add(ident)
            stack.append((value, True))
            for nested in value.values():
                stack.append((nested, False))
            continue
        if ty is list:
            ident = id(value)
            if ident in ancestors:
                raise CodeProofStructureError("type") from None
            if ident in done:
                continue
            ancestors.add(ident)
            stack.append((value, True))
            for nested in value:
                stack.append((nested, False))
            continue
        raise CodeProofStructureError("type") from None


class CodeProofResources:
    __slots__ = ("_hard_limits", "_profile_sha256", "_resource_pins", "_validators")

    def __init__(self) -> None:
        raise CodeProofResourceError("resource_shape") from None

    @property
    def profile_sha256(self) -> str:
        return self._profile_sha256

    @property
    def resource_pins(self) -> tuple:
        return self._resource_pins

    def validate_structure(self, title: object, instance: object) -> None:
        if type(title) is not str or title not in self._validators:
            raise CodeProofStructureError("shape") from None
        _preflight_instance(instance)
        try:
            self._validators[title].validate(instance)
        except Exception:
            raise CodeProofStructureError("shape") from None

    def materialize_limits(self, value: object) -> dict[str, dict[str, int]]:
        if value is None:
            return _copy_hard_limits(self._hard_limits)
        if type(value) is not dict:
            raise CodeProofStructureError("limits") from None
        groups: list[str] = []
        for key in value:
            if type(key) is not str:
                raise CodeProofStructureError("limits") from None
            groups.append(key)
        if frozenset(groups) != frozenset(_LIMIT_GROUP_KEYS):
            raise CodeProofStructureError("limits") from None
        materialized: dict[str, dict[str, int]] = {}
        for group in groups:
            inner = value[group]
            if type(inner) is not dict:
                raise CodeProofStructureError("limits") from None
            fields: list[str] = []
            for key in inner:
                if type(key) is not str:
                    raise CodeProofStructureError("limits") from None
                fields.append(key)
            if frozenset(fields) != frozenset(_LIMIT_KEYS[group]):
                raise CodeProofStructureError("limits") from None
            materialized_inner: dict[str, int] = {}
            for key in fields:
                raw = inner[key]
                if type(raw) is not int:
                    raise CodeProofStructureError("limits") from None
                if raw <= 0 or raw > self._hard_limits[group][key]:
                    raise CodeProofStructureError("limits") from None
                materialized_inner[key] = raw
            materialized[group] = materialized_inner
        return materialized


def compile_code_proof_resources(retained_bytes: object) -> CodeProofResources:
    snapshot = _require_retained_mapping(retained_bytes)
    _check_production_pins(snapshot)
    parsed: dict = {}
    for key, payload in snapshot:
        parsed[key] = _parse_resource_bytes(payload)
    schemas: dict[str, dict] = {}
    for stem, size, digest in _SCHEMA_STEMS:
        document = parsed[_schema_logical_key(stem)]
        _require_schema_header(document, stem)
        schemas[_schema_id(stem)] = document
        try:
            Draft202012Validator.check_schema(document)
        except Exception:
            raise CodeProofResourceError("resource_shape") from None
    _validate_schema_references(schemas)
    profile = parsed[_PROFILE_LOGICAL_KEY]
    _validate_profile_inventory(profile)
    try:
        registry = _build_registry(schemas)
        _StrictDraft202012Validator({"$ref": _PROFILE_DEF_REF}, registry=registry).validate(profile)
        validators = {}
        for stem, size, digest in _SCHEMA_STEMS:
            validators[_schema_title(stem)] = _StrictDraft202012Validator(
                copy.deepcopy(schemas[_schema_id(stem)]),
                registry=registry,
            )
    except Exception:
        raise CodeProofResourceError("resource_shape") from None
    compiled = object.__new__(CodeProofResources)
    compiled._profile_sha256 = _PROFILE_SHA256
    compiled._resource_pins = _PRODUCTION_PINS
    compiled._validators = validators
    compiled._hard_limits = _copy_hard_limits(_HARD_LIMITS)
    return compiled
