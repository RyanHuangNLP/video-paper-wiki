"""Generate the CODE-PROOF Draft 2020-12 schemas and installed profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


DRAFT = "https://json-schema.org/draft/2020-12/schema"
ID_PREFIX = "https://video-paper-wiki.dev/schemas/"

COMMON_FILENAME = "video-paper-wiki.code-proof-common.v1.schema.json"
REQUEST_INPUT_FILENAME = "video-paper-wiki.code-proof-request-input.v1.schema.json"
OBSERVE_INPUT_FILENAME = "video-paper-wiki.code-proof-observe-input.v1.schema.json"
COMMAND_RESULT_FILENAME = "video-paper-wiki.code-proof-command-result.v1.schema.json"

SCHEMA_FILENAMES: tuple[str, ...] = (
    COMMON_FILENAME,
    REQUEST_INPUT_FILENAME,
    OBSERVE_INPUT_FILENAME,
    COMMAND_RESULT_FILENAME,
    "video-paper-wiki.code-proof-request.v1.schema.json",
    "video-paper-wiki.code-git-bundle.v1.schema.json",
    "video-paper-wiki.code-acquisition-intent.v1.schema.json",
    "video-paper-wiki.code-proof-observation.v1.schema.json",
    "video-paper-wiki.code-config-evidence.v1.schema.json",
    "video-paper-wiki.code-source-handoff.v1.schema.json",
)

GIT_LIMITS: dict[str, int] = {
    "max_targets": 32,
    "max_objects": 2048,
    "max_tree_entries": 32768,
    "max_object_bytes": 8388608,
    "max_total_object_bytes": 33554432,
}
CONFIG_LIMITS: dict[str, int] = {
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
}
PUBLIC_LIMITS: dict[str, int] = {
    "max_bundle_bytes": 1048576,
    "max_inline_normalized_bytes": 16384,
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}

ROLES: tuple[str, ...] = (
    "readme",
    "citation",
    "license",
    "implementation",
    "configuration",
    "entrypoint",
)
GIT_MODES: tuple[str, ...] = (
    "40000",
    "100644",
    "100755",
    "120000",
    "160000",
)
UNSAFE_REASONS: tuple[str, ...] = (
    "executable_without_permission",
    "symlink",
    "gitlink",
    "directory",
    "non_directory_intermediate",
)
UNAVAILABLE_REASONS: tuple[str, ...] = (
    "not_returned",
    "capability_unavailable",
    "request_failed",
)

_SEGMENT = r"[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9])?"
_GIT_COMPONENT = (
    r"(?!(?:\.|\.\.|\.[Gg][Ii][Tt])(?:/|\Z))"
    r"[A-Za-z0-9._-]+"
)
_GIT_PATH = _GIT_COMPONENT + r"(?:/" + _GIT_COMPONENT + r"){0,31}"
_OWNER_SAVED = r"(?!(?:\.|\.\.)\Z)[a-z0-9._-]{1,100}"
_NAME_SAVED = r"(?!(?:\.|\.\.)\Z)(?!.*\.git\Z)[a-z0-9._-]{1,100}"
_OWNER_INPUT = r"(?!(?:\.|\.\.)\Z)[A-Za-z0-9._-]{1,100}"
_NAME_INPUT = r"(?!(?:\.|\.\.)\Z)(?!.*\.[Gg][Ii][Tt]\Z)[A-Za-z0-9._-]{1,100}"
_REPOSITORY_SAVED = _OWNER_SAVED + "/" + _NAME_SAVED
_REPOSITORY_INPUT = _OWNER_INPUT + "/" + _NAME_INPUT
_OID = r"[0-9a-f]{40}(?:[0-9a-f]{24})?"
_CHECKOUT_REL = r"\.work(?:/" + _SEGMENT + r")+"
_NO_CONTROLS = r"[^\x00-\x1F\x7F-\x9F\u2028\u2029]+"
_STATEMENT = r"[^\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\u2028\u2029]+"
_YEAR = r"(?:000[1-9]|00[1-9][0-9]|0[1-9][0-9]{2}|[1-9][0-9]{3})"
_MONTH = r"(?:0[1-9]|1[0-2])"
_DAY = r"(?:0[1-9]|[12][0-9]|3[01])"
_HMS = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
_DATETIME = _YEAR + "-" + _MONTH + "-" + _DAY + "T" + _HMS + "Z"
_JSON_POINTER = r"(?:|(?:/(?:[^/~]|~0|~1)*)+)"


def _schema_id(filename: str) -> str:
    return ID_PREFIX + filename


def _title(filename: str) -> str:
    return filename[: -len(".schema.json")]


def _anchored(pattern: str) -> str:
    return r"\A(?:" + pattern + r")\Z"


def _str_pattern(
    pattern: str,
    *,
    min_length: int | None = None,
    max_length: int | None = None,
) -> dict:
    out: dict = {"type": "string", "pattern": _anchored(pattern)}
    if min_length is not None:
        out["minLength"] = min_length
    if max_length is not None:
        out["maxLength"] = max_length
    return out


def _integer(minimum: int | None = None, maximum: int | None = None) -> dict:
    out: dict = {"type": "integer"}
    if minimum is not None:
        out["minimum"] = minimum
    if maximum is not None:
        out["maximum"] = maximum
    return out


def _closed(
    properties: dict,
    *,
    required: list[str] | None = None,
    extras: dict | None = None,
) -> dict:
    schema: dict = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties if required is None else required),
    }
    if extras:
        schema.update(extras)
    return schema


def _lref(name: str) -> dict:
    return {"$ref": "#/$defs/" + name}


def _cref(name: str) -> dict:
    return {"$ref": _schema_id(COMMON_FILENAME) + "#/$defs/" + name}


def _hex(n: int) -> dict:
    return _str_pattern(rf"[0-9a-f]{{{n}}}", min_length=n, max_length=n)


def _ce1_id(kind: str) -> dict:
    size = 4 + len(kind) + 1 + 64
    return _str_pattern(rf"ce1:{kind}:[0-9a-f]{{64}}", min_length=size, max_length=size)


def _limit_map(spec: dict[str, int]) -> dict:
    return _closed(
        {key: _integer(minimum=1, maximum=maximum) for key, maximum in spec.items()}
    )


def _const_limit_map(spec: dict[str, int]) -> dict:
    return _closed(
        {
            key: {"type": "integer", "const": maximum}
            for key, maximum in spec.items()
        }
    )


def _nullable(schema: dict) -> dict:
    return {"oneOf": [schema, {"type": "null"}]}


def _array(items: dict, *, min_items: int | None = None, max_items: int | None = None, unique: bool = False) -> dict:
    out: dict = {"type": "array", "items": items}
    if min_items is not None:
        out["minItems"] = min_items
    if max_items is not None:
        out["maxItems"] = max_items
    if unique:
        out["uniqueItems"] = True
    return out


def _dump(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _common_defs() -> dict:
    blob_url = _str_pattern(
        r"https://github.com/"
        + _REPOSITORY_SAVED
        + r"/blob/"
        + _OID
        + "/"
        + _GIT_PATH,
        min_length=1,
        max_length=2048,
    )
    raw_url = _str_pattern(
        r"https://raw.githubusercontent.com/"
        + _REPOSITORY_SAVED
        + "/"
        + _OID
        + "/"
        + _GIT_PATH,
        min_length=1,
        max_length=2048,
    )
    commit_url = _str_pattern(
        r"https://github.com/" + _REPOSITORY_SAVED + r"/commit/" + _OID,
        min_length=1,
        max_length=2048,
    )
    defs: dict = {}
    defs["sha256"] = _hex(64)
    defs["oid"] = {"oneOf": [_hex(40), _hex(64)]}
    defs["name_hex"] = _str_pattern(
        r"(?:[0-9a-f]{2})+", min_length=2, max_length=1024
    )
    defs["paper_id"] = {
        "oneOf": [
            _str_pattern(
                r"arxiv:(?:[0-9]{4}\.[0-9]{4,5}|[a-z-]+(?:\.[a-z]{2})?/[0-9]{7})",
                min_length=1,
                max_length=512,
            ),
            _str_pattern(
                r"doi:10\.[0-9]{4,9}/[\x21-\x40\x5b-\x7e]+",
                min_length=1,
                max_length=512,
            ),
            _str_pattern(r"openalex:W[0-9]+", min_length=1, max_length=512),
            _str_pattern(r"sha256:[0-9a-f]{64}", min_length=71, max_length=71),
        ]
    }
    defs["repository_input"] = _str_pattern(
        _REPOSITORY_INPUT, min_length=3, max_length=201
    )
    defs["repository_saved"] = _str_pattern(
        _REPOSITORY_SAVED, min_length=3, max_length=201
    )
    defs["git_path"] = _str_pattern(_GIT_PATH, min_length=1, max_length=512)
    defs["object_format"] = {"enum": ["sha1", "sha256"]}
    defs["batch_id"] = _str_pattern(_SEGMENT, min_length=1, max_length=128)
    defs["utc_datetime"] = _str_pattern(_DATETIME, min_length=20, max_length=20)
    defs["json_pointer"] = _str_pattern(_JSON_POINTER, max_length=16384)
    defs["git_role"] = {"enum": list(ROLES)}
    defs["git_roles"] = _array(
        defs["git_role"], min_items=1, max_items=6, unique=True
    )
    defs["request_target"] = _closed(
        {
            "path": _lref("git_path"),
            "roles": _lref("git_roles"),
            "allow_executable_source": {"type": "boolean"},
        },
        extras={
            "if": {
                "properties": {"allow_executable_source": {"const": True}},
                "required": ["allow_executable_source"],
            },
            "then": {
                "properties": {
                    "roles": {
                        "items": {"enum": ["implementation", "entrypoint"]}
                    }
                }
            },
        },
    )
    defs["request_targets"] = _array(
        _lref("request_target"), min_items=1, max_items=32
    )
    defs["git_limits"] = _limit_map(GIT_LIMITS)
    defs["config_limits"] = _limit_map(CONFIG_LIMITS)
    defs["public_limits"] = _limit_map(PUBLIC_LIMITS)
    defs["limits"] = _closed(
        {
            "git": _lref("git_limits"),
            "config": _lref("config_limits"),
            "public": _lref("public_limits"),
        }
    )
    defs["source_association"] = _nullable(
        _closed(
            {
                "association_id": _str_pattern(
                    r"sva-[0-9a-f]{64}", min_length=68, max_length=68
                ),
                "sha256": _lref("sha256"),
            }
        )
    )
    for kind in (
        "code-proof-request",
        "code-git-bundle",
        "code-acquisition-intent",
        "code-proof-observation",
        "code-config-evidence",
        "code-source-handoff",
    ):
        key = "ref_" + kind.replace("-", "_")
        defs[key] = _closed({"id": _ce1_id(kind), "sha256": _lref("sha256")})
        defs["nullable_" + key] = _nullable(_lref(key))
    defs["executor"] = {
        "oneOf": [
            _closed(
                {
                    "kind": {"enum": ["human", "host_tool"]},
                    "id": _str_pattern(_NO_CONTROLS, min_length=1, max_length=128),
                }
            ),
            _closed({"kind": {"const": "unknown"}, "id": {"type": "null"}}),
        ]
    }
    defs["hosting_assertion"] = _nullable(
        _closed(
            {
                "provider": {"const": "github"},
                "actor": _lref("executor"),
                "repository": _lref("repository_saved"),
                "object_format": _lref("object_format"),
                "commit_oid": _lref("oid"),
                "locator": commit_url,
                "statement": _str_pattern(
                    _STATEMENT, min_length=1, max_length=2048
                ),
            }
        )
    )
    defs["text_metadata"] = _closed(
        {
            "normalized_size_bytes": _integer(minimum=0, maximum=8388608),
            "normalized_sha256": _lref("sha256"),
            "newline_style": {"enum": ["none", "lf", "crlf", "mixed"]},
            "ends_with_newline": {"type": "boolean"},
            "line_count": _integer(minimum=0, maximum=8388608),
        }
    )
    defs["github_blob_url"] = blob_url
    defs["github_raw_url"] = raw_url
    defs["github_commit_url"] = commit_url
    defs["acquisition_locator"] = {"oneOf": [blob_url, raw_url]}
    defs["nullable_acquisition_locator"] = _nullable(_lref("acquisition_locator"))
    defs["object_declaration"] = _closed(
        {
            "oid": _lref("oid"),
            "object_type": {"enum": ["commit", "tree", "blob"]},
            "body_size_bytes": _integer(minimum=0, maximum=8388608),
            "body_sha256": _lref("sha256"),
            "framed_sha256": _lref("sha256"),
        }
    )
    defs["git_blob"] = _closed(
        {
            "oid": _lref("oid"),
            "body_size_bytes": _integer(minimum=0, maximum=8388608),
            "body_sha256": _lref("sha256"),
            "framed_sha256": _lref("sha256"),
        }
    )
    defs["git_walk_edge"] = _closed(
        {
            "tree_oid": _lref("oid"),
            "name_hex": _lref("name_hex"),
            "mode": {"enum": list(GIT_MODES)},
            "oid": _lref("oid"),
        }
    )
    defs["git_stopped_at"] = _closed(
        {
            "component_index": _integer(minimum=0, maximum=31),
            "tree_oid": _lref("oid"),
            "name_hex": _lref("name_hex"),
            "mode": _nullable({"enum": list(GIT_MODES)}),
            "oid": _nullable(_lref("oid")),
        },
        extras={
            "allOf": [
                {
                    "if": {
                        "properties": {"mode": {"type": "null"}},
                        "required": ["mode"],
                    },
                    "then": {"properties": {"oid": {"type": "null"}}},
                },
                {
                    "if": {
                        "properties": {"mode": {"enum": list(GIT_MODES)}},
                        "required": ["mode"],
                    },
                    "then": {"properties": {"oid": _lref("oid")}},
                },
            ]
        },
    )
    defs["git_target_permitted"] = _closed(
        {
            "path": _lref("git_path"),
            "outcome": {"const": "permitted_regular_blob"},
            "reason": {"type": "null"},
            "walk": _array(_lref("git_walk_edge"), min_items=1, max_items=32),
            "stopped_at": _lref("git_stopped_at"),
            "blob": _lref("git_blob"),
        }
    )
    defs["git_target_missing"] = _closed(
        {
            "path": _lref("git_path"),
            "outcome": {"const": "missing"},
            "reason": {"const": "absent_entry"},
            "walk": _array(_lref("git_walk_edge"), min_items=0, max_items=32),
            "stopped_at": _lref("git_stopped_at"),
            "blob": {"type": "null"},
        }
    )
    defs["git_target_unsafe"] = _closed(
        {
            "path": _lref("git_path"),
            "outcome": {"const": "unsafe"},
            "reason": {"enum": list(UNSAFE_REASONS)},
            "walk": _array(_lref("git_walk_edge"), min_items=1, max_items=32),
            "stopped_at": _lref("git_stopped_at"),
            "blob": {"type": "null"},
        }
    )
    defs["git_target"] = {
        "oneOf": [
            _lref("git_target_permitted"),
            _lref("git_target_missing"),
            _lref("git_target_unsafe"),
        ]
    }
    defs["git_budget"] = _closed(
        {
            "object_count": _integer(minimum=1, maximum=2048),
            "declared_body_bytes": _integer(minimum=0, maximum=33554432),
            "actual_body_bytes": _integer(minimum=0, maximum=33554432),
            "parsed_tree_entries": _integer(minimum=0, maximum=32768),
            "target_count": _integer(minimum=1, maximum=32),
            "walk_edges": _integer(minimum=0, maximum=1024),
        }
    )
    defs["git_proof"] = _closed(
        {
            "object_format": _lref("object_format"),
            "commit_oid": _lref("oid"),
            "root_tree_oid": _lref("oid"),
            "object_records": _array(
                _lref("object_declaration"), min_items=1, max_items=2048
            ),
            "consumed_oids": _array(
                _lref("oid"), min_items=1, max_items=2048, unique=True
            ),
            "budget": _lref("git_budget"),
            "targets": _array(_lref("git_target"), min_items=1, max_items=32),
        }
    )
    defs["span"] = _closed(
        {
            "byte_start": _integer(minimum=0, maximum=262144),
            "byte_end": _integer(minimum=1, maximum=262144),
            "codepoint_start": _integer(minimum=0, maximum=262144),
            "codepoint_end": _integer(minimum=1, maximum=262144),
            "line_start": _integer(minimum=1, maximum=262144),
            "column_start": _integer(minimum=1, maximum=262144),
            "line_end": _integer(minimum=1, maximum=262144),
            "column_end": _integer(minimum=1, maximum=262144),
            "raw_sha256": _lref("sha256"),
            "snippet_sha256": _lref("sha256"),
        }
    )
    defs["config_declaration"] = _closed(
        {
            "kind": {"enum": ["json_key", "toml_key", "toml_table"]},
            "span": _lref("span"),
        }
    )
    defs["config_declarations"] = _array(
        _lref("config_declaration"), min_items=0, max_items=4096
    )
    defs["config_node_object"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "object"},
            "value": {"type": "null"},
            "numeric_lexeme": {"type": "null"},
            "children": _array(_lref("json_pointer"), min_items=0, max_items=1024),
            "value_span": _nullable(_lref("span")),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_array"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "array"},
            "value": {"type": "null"},
            "numeric_lexeme": {"type": "null"},
            "children": _array(_lref("json_pointer"), min_items=0, max_items=256),
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_string"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "string"},
            "value": {"type": "string", "maxLength": 16384},
            "numeric_lexeme": {"type": "null"},
            "children": {"const": []},
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_integer"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "integer"},
            "value": {"type": "string", "minLength": 1, "maxLength": 256},
            "numeric_lexeme": {"type": "string", "minLength": 1, "maxLength": 128},
            "children": {"const": []},
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_decimal"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "decimal"},
            "value": {"type": "string", "minLength": 1, "maxLength": 256},
            "numeric_lexeme": {"type": "string", "minLength": 1, "maxLength": 128},
            "children": {"const": []},
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_boolean"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "boolean"},
            "value": {"type": "boolean"},
            "numeric_lexeme": {"type": "null"},
            "children": {"const": []},
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node_null"] = _closed(
        {
            "path": _lref("json_pointer"),
            "kind": {"const": "null"},
            "value": {"type": "null"},
            "numeric_lexeme": {"type": "null"},
            "children": {"const": []},
            "value_span": _lref("span"),
            "declarations": _lref("config_declarations"),
        }
    )
    defs["config_node"] = {
        "oneOf": [
            _lref("config_node_object"),
            _lref("config_node_array"),
            _lref("config_node_string"),
            _lref("config_node_integer"),
            _lref("config_node_decimal"),
            _lref("config_node_boolean"),
            _lref("config_node_null"),
        ]
    }
    defs["config_source"] = _closed(
        {
            "body_size_bytes": _integer(minimum=1, maximum=262144),
            "body_sha256": _lref("sha256"),
            "normalized_sha256": _lref("sha256"),
            "newline_style": {"enum": ["none", "lf", "crlf", "mixed"]},
            "ends_with_newline": {"type": "boolean"},
            "line_count": _integer(minimum=0, maximum=262144),
        }
    )
    defs["config_budget"] = _closed(
        {
            "node_count": _integer(minimum=1, maximum=1024),
            "scalar_count": _integer(minimum=0, maximum=512),
            "max_depth_observed": _integer(minimum=0, maximum=32),
            "declaration_count": _integer(minimum=0, maximum=4096),
            "max_array_items_observed": _integer(minimum=0, maximum=256),
            "max_object_keys_observed": _integer(minimum=0, maximum=1024),
        }
    )
    defs["config_result"] = _closed(
        {
            "config_format": {"enum": ["json", "toml"]},
            "source": _lref("config_source"),
            "budget": _lref("config_budget"),
            "nodes": _array(_lref("config_node"), min_items=1, max_items=1024),
        }
    )
    defs["stored_body_path"] = _str_pattern(
        _CHECKOUT_REL
        + r"/code-evidence-v1/objects/"
        + _OID
        + r"\.body",
        min_length=1,
        max_length=512,
    )
    defs["stored_derived_path"] = _str_pattern(
        _CHECKOUT_REL
        + r"/code-evidence-v1/(?:configs|handoffs)/[0-9a-f]{64}\.json",
        min_length=1,
        max_length=512,
    )
    defs["bundle_directory"] = _str_pattern(
        _CHECKOUT_REL, min_length=8, max_length=512
    )
    defs["raw_body"] = _closed(
        {
            "path": _lref("stored_body_path"),
            "size_bytes": _integer(minimum=0, maximum=8388608),
            "sha256": _lref("sha256"),
        }
    )
    defs["observe_present_target"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "present"},
            "locator": _lref("acquisition_locator"),
            "text": {"type": "string", "maxLength": 16384},
        }
    )
    defs["observe_missing_target"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "missing"},
            "locator": _lref("nullable_acquisition_locator"),
            "reason": {"const": "host_reported_missing"},
        }
    )
    defs["observe_inaccessible_target"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "inaccessible"},
            "locator": _lref("nullable_acquisition_locator"),
            "reason": {"const": "permission_denied"},
        }
    )
    defs["observe_unavailable_target"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "unavailable"},
            "locator": _lref("nullable_acquisition_locator"),
            "reason": {"enum": list(UNAVAILABLE_REASONS)},
        }
    )
    defs["normalized_observe_target"] = {
        "oneOf": [
            _lref("observe_present_target"),
            _lref("observe_missing_target"),
            _lref("observe_inaccessible_target"),
            _lref("observe_unavailable_target"),
        ]
    }
    defs["observe_input_git_objects"] = _closed(
        {
            "mode": {"const": "git_objects"},
            "observed_at": _lref("utc_datetime"),
            "executor": _lref("executor"),
            "hosting_assertion": _lref("hosting_assertion"),
        }
    )
    defs["observe_input_normalized"] = _closed(
        {
            "mode": {"const": "normalized_text"},
            "observed_at": _lref("utc_datetime"),
            "executor": _lref("executor"),
            "hosting_assertion": _lref("hosting_assertion"),
            "targets": _array(
                _lref("normalized_observe_target"), min_items=1, max_items=32
            ),
        }
    )
    defs["observe_input"] = {
        "oneOf": [
            _lref("observe_input_git_objects"),
            _lref("observe_input_normalized"),
        ]
    }
    defs["observation_source_text"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "source_text"},
            "reason": {"type": "null"},
            "text": _lref("text_metadata"),
        }
    )
    defs["observation_unsupported"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "unsupported_source_bytes"},
            "reason": {"const": "unsupported_source_bytes"},
            "text": {"type": "null"},
        }
    )
    defs["observation_missing"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "missing"},
            "reason": {"const": "absent_entry"},
            "text": {"type": "null"},
        }
    )
    defs["observation_unsafe"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "unsafe"},
            "reason": {"enum": list(UNSAFE_REASONS)},
            "text": {"type": "null"},
        }
    )
    defs["observation_normalized_text"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "normalized_text"},
            "reason": {"type": "null"},
            "text": _lref("text_metadata"),
        }
    )
    defs["observation_host_missing"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "host_missing"},
            "reason": {"const": "host_reported_missing"},
            "text": {"type": "null"},
        }
    )
    defs["observation_host_inaccessible"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "host_inaccessible"},
            "reason": {"const": "permission_denied"},
            "text": {"type": "null"},
        }
    )
    defs["observation_host_unavailable"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "host_unavailable"},
            "reason": {"enum": list(UNAVAILABLE_REASONS)},
            "text": {"type": "null"},
        }
    )
    defs["raw_observation_target"] = {
        "oneOf": [
            _lref("observation_source_text"),
            _lref("observation_unsupported"),
            _lref("observation_missing"),
            _lref("observation_unsafe"),
        ]
    }
    defs["normalized_observation_target"] = {
        "oneOf": [
            _lref("observation_normalized_text"),
            _lref("observation_host_missing"),
            _lref("observation_host_inaccessible"),
            _lref("observation_host_unavailable"),
        ]
    }
    defs["observation_target"] = {
        "oneOf": [
            _lref("raw_observation_target"),
            _lref("normalized_observation_target"),
        ]
    }
    defs["unobserved_target"] = _closed(
        {
            "path": _lref("git_path"),
            "status": {"const": "unobserved"},
            "reason": {"type": "null"},
            "text": {"type": "null"},
        }
    )
    defs["status_target"] = {
        "oneOf": [_lref("unobserved_target"), _lref("observation_target")]
    }
    defs["capabilities_raw"] = _closed(
        {
            "git_objects_verified": {"const": True, "type": "boolean"},
            "raw_bytes_retained": {"const": True, "type": "boolean"},
            "repository_assertion": {"enum": ["host_asserted", "unverified"]},
            "source_association_verified": {"const": False, "type": "boolean"},
        }
    )
    defs["capabilities_normalized"] = _closed(
        {
            "git_objects_verified": {"const": False, "type": "boolean"},
            "raw_bytes_retained": {"const": False, "type": "boolean"},
            "repository_assertion": {"enum": ["host_asserted", "unverified"]},
            "source_association_verified": {"const": False, "type": "boolean"},
        }
    )
    defs["capabilities"] = {
        "oneOf": [_lref("capabilities_raw"), _lref("capabilities_normalized")]
    }
    defs["eligibility"] = _closed(
        {
            "complete_target_set": {"type": "boolean"},
            "repository_requirement_met": {"type": "boolean"},
            "source_handoff_eligible": {"type": "boolean"},
        }
    )
    defs["request_input"] = _closed(
        {
            "paper_id": _lref("paper_id"),
            "source_association": _lref("source_association"),
            "repository": _lref("repository_input"),
            "object_format": _lref("object_format"),
            "commit_oid": _lref("oid"),
            "targets": _lref("request_targets"),
            "require_repository_assertion": {"type": "boolean"},
            "limits": _lref("limits"),
        },
        required=[
            "paper_id",
            "source_association",
            "repository",
            "object_format",
            "commit_oid",
            "targets",
            "require_repository_assertion",
        ],
    )
    defs["request_data"] = _closed(
        {
            "paper_id": _lref("paper_id"),
            "source_association": _lref("source_association"),
            "repository": _lref("repository_saved"),
            "object_format": _lref("object_format"),
            "commit_oid": _lref("oid"),
            "targets": _lref("request_targets"),
            "require_repository_assertion": {"type": "boolean"},
            "limits": _lref("limits"),
            "profile_sha256": _lref("sha256"),
        }
    )
    defs["bundle_data"] = _closed(
        {
            "request": _lref("ref_code_proof_request"),
            "object_format": _lref("object_format"),
            "repository": _lref("repository_saved"),
            "commit_oid": _lref("oid"),
            "root_tree_oid": _lref("oid"),
            "objects": _array(
                _lref("object_declaration"), min_items=1, max_items=2048
            ),
        }
    )
    defs["intent_bundle"] = _closed(
        {
            "directory": _lref("bundle_directory"),
            "reference": _lref("ref_code_git_bundle"),
        }
    )
    defs["intent_data"] = {
        "oneOf": [
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "mode": {"const": "git_objects"},
                    "acquisition": _lref("observe_input_git_objects"),
                    "bundle": _lref("intent_bundle"),
                }
            ),
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "mode": {"const": "normalized_text"},
                    "acquisition": _lref("observe_input_normalized"),
                    "bundle": {"type": "null"},
                }
            ),
        ]
    }
    defs["observation_data"] = {
        "oneOf": [
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "intent": _lref("ref_code_acquisition_intent"),
                    "bundle": _lref("ref_code_git_bundle"),
                    "mode": {"const": "git_objects"},
                    "git_proof": _lref("git_proof"),
                    "targets": _array(
                        _lref("raw_observation_target"), min_items=1, max_items=32
                    ),
                    "capabilities": _lref("capabilities_raw"),
                    "eligibility": _lref("eligibility"),
                }
            ),
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "intent": _lref("ref_code_acquisition_intent"),
                    "bundle": {"type": "null"},
                    "mode": {"const": "normalized_text"},
                    "git_proof": {"type": "null"},
                    "targets": _array(
                        _lref("normalized_observation_target"),
                        min_items=1,
                        max_items=32,
                    ),
                    "capabilities": _lref("capabilities_normalized"),
                    "eligibility": _lref("eligibility"),
                }
            ),
        ]
    }
    defs["config_data"] = {
        "oneOf": [
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "observation": _lref("ref_code_proof_observation"),
                    "bundle": _lref("ref_code_git_bundle"),
                    "path": _lref("git_path"),
                    "object_format": _lref("object_format"),
                    "blob_oid": _lref("oid"),
                    "raw_body": _lref("raw_body"),
                    "format": {"const": "source-only"},
                    "result": {"type": "null"},
                    "source_only_reason": {"const": "explicit_source_only"},
                }
            ),
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "observation": _lref("ref_code_proof_observation"),
                    "bundle": _lref("ref_code_git_bundle"),
                    "path": _lref("git_path"),
                    "object_format": _lref("object_format"),
                    "blob_oid": _lref("oid"),
                    "raw_body": _lref("raw_body"),
                    "format": {"const": "json"},
                    "result": _lref("config_result"),
                    "source_only_reason": {"type": "null"},
                }
            ),
            _closed(
                {
                    "request": _lref("ref_code_proof_request"),
                    "observation": _lref("ref_code_proof_observation"),
                    "bundle": _lref("ref_code_git_bundle"),
                    "path": _lref("git_path"),
                    "object_format": _lref("object_format"),
                    "blob_oid": _lref("oid"),
                    "raw_body": _lref("raw_body"),
                    "format": {"const": "toml"},
                    "result": _lref("config_result"),
                    "source_only_reason": {"type": "null"},
                }
            ),
        ]
    }
    defs["handoff_data"] = _closed(
        {
            "successor_only": {"const": True, "type": "boolean"},
            "request": _lref("ref_code_proof_request"),
            "observation": _lref("ref_code_proof_observation"),
            "bundle": _lref("ref_code_git_bundle"),
            "paper_id": _lref("paper_id"),
            "source_association": _lref("source_association"),
            "repository": _lref("repository_saved"),
            "object_format": _lref("object_format"),
            "commit_oid": _lref("oid"),
            "root_tree_oid": _lref("oid"),
            "path": _lref("git_path"),
            "roles": _lref("git_roles"),
            "allow_executable_source": {"type": "boolean"},
            "blob": _lref("git_blob"),
            "raw_body": _lref("raw_body"),
            "text": _lref("text_metadata"),
            "proof": _lref("git_target_permitted"),
            "repository_assertion": {"enum": ["host_asserted", "unverified"]},
            "source_association_verified": {"const": False, "type": "boolean"},
        }
    )
    defs["missing_name"] = _str_pattern(
        r"intent\.json|bundle\.json|observation\.json|objects/"
        + _OID
        + r"\.body",
        min_length=11,
        max_length=77,
    )
    defs["derived_config"] = _closed(
        {
            "path": _lref("git_path"),
            "reference": _lref("ref_code_config_evidence"),
            "stored_path": _lref("stored_derived_path"),
        }
    )
    defs["derived_handoff"] = _closed(
        {
            "path": _lref("git_path"),
            "reference": _lref("ref_code_source_handoff"),
            "stored_path": _lref("stored_derived_path"),
        }
    )
    defs["status_payload"] = _closed(
        {
            "batch_id": _lref("batch_id"),
            "state": {
                "enum": [
                    "empty",
                    "requested",
                    "pending_normalized",
                    "pending_raw_bundle",
                    "pending_raw_bodies",
                    "observed",
                ]
            },
            "request": _lref("nullable_ref_code_proof_request"),
            "intent": _lref("nullable_ref_code_acquisition_intent"),
            "bundle": _lref("nullable_ref_code_git_bundle"),
            "observation": _lref("nullable_ref_code_proof_observation"),
            "mode": _nullable({"enum": ["git_objects", "normalized_text"]}),
            "missing": _array(_lref("missing_name"), min_items=0, max_items=2049),
            "targets": _array(_lref("status_target"), min_items=0, max_items=32),
            "capabilities": _nullable(_lref("capabilities")),
            "eligibility": _nullable(_lref("eligibility")),
            "configs": _array(_lref("derived_config"), min_items=0, max_items=32),
            "handoffs": _array(_lref("derived_handoff"), min_items=0, max_items=32),
            "next_action": {
                "enum": [
                    "prepare_request",
                    "supply_observation",
                    "resume_same_observation",
                    "prepare_source_handoff",
                    "successor_capture",
                    "new_request_or_acquisition_required",
                ]
            },
        },
        extras={
            "allOf": [
                {
                    "if": {
                        "properties": {"state": {"const": "empty"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": {"type": "null"},
                            "intent": {"type": "null"},
                            "bundle": {"type": "null"},
                            "observation": {"type": "null"},
                            "mode": {"type": "null"},
                            "missing": {"type": "array", "maxItems": 0},
                            "targets": {"type": "array", "maxItems": 0},
                            "capabilities": {"type": "null"},
                            "eligibility": {"type": "null"},
                            "configs": {"type": "array", "maxItems": 0},
                            "handoffs": {"type": "array", "maxItems": 0},
                            "next_action": {"const": "prepare_request"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "requested"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": _lref("ref_code_proof_request"),
                            "intent": {"type": "null"},
                            "bundle": {"type": "null"},
                            "observation": {"type": "null"},
                            "mode": {"type": "null"},
                            "missing": {"const": ["intent.json"]},
                            "targets": _array(
                                _lref("unobserved_target"),
                                min_items=1,
                                max_items=32,
                            ),
                            "capabilities": {"type": "null"},
                            "eligibility": {"type": "null"},
                            "configs": {"type": "array", "maxItems": 0},
                            "handoffs": {"type": "array", "maxItems": 0},
                            "next_action": {"const": "supply_observation"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "pending_normalized"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": _lref("ref_code_proof_request"),
                            "intent": _lref("ref_code_acquisition_intent"),
                            "bundle": {"type": "null"},
                            "observation": {"type": "null"},
                            "mode": {"const": "normalized_text"},
                            "missing": {"const": ["observation.json"]},
                            "targets": _array(
                                _lref("unobserved_target"),
                                min_items=1,
                                max_items=32,
                            ),
                            "capabilities": {"type": "null"},
                            "eligibility": {"type": "null"},
                            "configs": {"type": "array", "maxItems": 0},
                            "handoffs": {"type": "array", "maxItems": 0},
                            "next_action": {"const": "resume_same_observation"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "pending_raw_bundle"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": _lref("ref_code_proof_request"),
                            "intent": _lref("ref_code_acquisition_intent"),
                            "bundle": {"type": "null"},
                            "observation": {"type": "null"},
                            "mode": {"const": "git_objects"},
                            "missing": {
                                "const": ["bundle.json", "observation.json"]
                            },
                            "targets": _array(
                                _lref("unobserved_target"),
                                min_items=1,
                                max_items=32,
                            ),
                            "capabilities": {"type": "null"},
                            "eligibility": {"type": "null"},
                            "configs": {"type": "array", "maxItems": 0},
                            "handoffs": {"type": "array", "maxItems": 0},
                            "next_action": {"const": "resume_same_observation"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "pending_raw_bodies"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": _lref("ref_code_proof_request"),
                            "intent": _lref("ref_code_acquisition_intent"),
                            "bundle": _lref("ref_code_git_bundle"),
                            "observation": {"type": "null"},
                            "mode": {"const": "git_objects"},
                            "missing": _array(
                                _lref("missing_name"), min_items=1, max_items=2049
                            ),
                            "targets": _array(
                                _lref("unobserved_target"),
                                min_items=1,
                                max_items=32,
                            ),
                            "capabilities": {"type": "null"},
                            "eligibility": {"type": "null"},
                            "configs": {"type": "array", "maxItems": 0},
                            "handoffs": {"type": "array", "maxItems": 0},
                            "next_action": {"const": "resume_same_observation"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"state": {"const": "observed"}},
                        "required": ["state"],
                    },
                    "then": {
                        "properties": {
                            "request": _lref("ref_code_proof_request"),
                            "intent": _lref("ref_code_acquisition_intent"),
                            "observation": _lref("ref_code_proof_observation"),
                            "mode": {"enum": ["git_objects", "normalized_text"]},
                            "missing": {"type": "array", "maxItems": 0},
                            "targets": _array(
                                _lref("observation_target"),
                                min_items=1,
                                max_items=32,
                            ),
                            "capabilities": _lref("capabilities"),
                            "eligibility": _lref("eligibility"),
                            "next_action": {
                                "enum": [
                                    "prepare_source_handoff",
                                    "successor_capture",
                                    "new_request_or_acquisition_required",
                                ]
                            },
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "state": {"const": "observed"},
                            "mode": {"const": "git_objects"},
                        },
                        "required": ["state", "mode"],
                    },
                    "then": {
                        "properties": {
                            "bundle": _lref("ref_code_git_bundle"),
                            "capabilities": _lref("capabilities_raw"),
                            "targets": _array(
                                _lref("raw_observation_target"),
                                min_items=1,
                                max_items=32,
                            ),
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "state": {"const": "observed"},
                            "mode": {"const": "normalized_text"},
                        },
                        "required": ["state", "mode"],
                    },
                    "then": {
                        "properties": {
                            "bundle": {"type": "null"},
                            "capabilities": _lref("capabilities_normalized"),
                            "targets": _array(
                                _lref("normalized_observation_target"),
                                min_items=1,
                                max_items=32,
                            ),
                        }
                    },
                },
            ]
        },
    )
    defs["acquisition_target"] = _closed(
        {
            "path": _lref("git_path"),
            "github_url": _lref("github_blob_url"),
            "raw_url": _lref("github_raw_url"),
        }
    )
    defs["command_result_request"] = _closed(
        {
            "batch_id": _lref("batch_id"),
            "request": _lref("ref_code_proof_request"),
            "already_staged": {"type": "boolean"},
            "acquisition_targets": _array(
                _lref("acquisition_target"), min_items=1, max_items=32
            ),
        }
    )
    defs["command_result_observe"] = _closed(
        {
            "batch_id": _lref("batch_id"),
            "observation": _lref("ref_code_proof_observation"),
            "status": _lref("status_payload"),
        }
    )
    defs["command_result_status"] = _lref("status_payload")
    defs["command_result_config"] = _closed(
        {
            "batch_id": _lref("batch_id"),
            "path": _lref("git_path"),
            "config": _lref("ref_code_config_evidence"),
            "stored_path": _lref("stored_derived_path"),
            "already_staged": {"type": "boolean"},
        }
    )
    defs["command_result_handoff_row"] = _closed(
        {
            "path": _lref("git_path"),
            "handoff": _lref("ref_code_source_handoff"),
            "stored_path": _lref("stored_derived_path"),
            "source_body_path": _lref("stored_body_path"),
            "already_staged": {"type": "boolean"},
        }
    )
    defs["command_result_handoff"] = _closed(
        {
            "batch_id": _lref("batch_id"),
            "handoffs": _array(
                _lref("command_result_handoff_row"), min_items=1, max_items=32
            ),
        }
    )
    defs["command_result"] = {
        "oneOf": [
            _lref("command_result_request"),
            _lref("command_result_observe"),
            _lref("command_result_status"),
            _lref("command_result_config"),
            _lref("command_result_handoff"),
        ]
    }
    defs["profile_git_limits"] = _const_limit_map(GIT_LIMITS)
    defs["profile_config_limits"] = _const_limit_map(CONFIG_LIMITS)
    defs["profile_public_limits"] = _const_limit_map(PUBLIC_LIMITS)
    defs["profile_limits"] = _closed(
        {
            "git": _lref("profile_git_limits"),
            "config": _lref("profile_config_limits"),
            "public": _lref("profile_public_limits"),
        }
    )
    defs["profile_admission"] = _closed(
        {
            "max_request_input_bytes": {"type": "integer", "const": 65536},
            "max_observe_input_bytes": {"type": "integer", "const": 1048576},
        }
    )
    defs["profile_schema_row"] = {
        "oneOf": [
            _closed(
                {
                    "title": {"const": _title(filename)},
                    "filename": {"const": filename},
                    "size_bytes": _integer(minimum=1),
                    "sha256": _lref("sha256"),
                }
            )
            for filename in SCHEMA_FILENAMES
        ]
    }
    defs["profile"] = _closed(
        {
            "schema": {"const": "video-paper-wiki.code-proof-profile.v1"},
            "profile": {"const": "code-proof-v1"},
            "revision": {"type": "integer", "const": 1},
            "limits": _lref("profile_limits"),
            "admission": _lref("profile_admission"),
            "schemas": _array(
                _lref("profile_schema_row"), min_items=10, max_items=10
            ),
        }
    )
    return defs


def _root(filename: str, extra: dict) -> dict:
    document = {
        "$schema": DRAFT,
        "$id": _schema_id(filename),
        "title": _title(filename),
    }
    document.update(extra)
    return document


def _envelope(kind: str, data_def: str) -> dict:
    filename = f"video-paper-wiki.{kind}.v1.schema.json"
    return _root(
        filename,
        _closed(
            {
                "schema": {"const": f"video-paper-wiki.{kind}.v1"},
                "kind": {"const": kind},
                "id": _ce1_id(kind),
                "data": _cref(data_def),
            }
        ),
    )


def build_schema_documents() -> dict[str, dict]:
    common = _root(COMMON_FILENAME, {"$defs": _common_defs()})
    documents = {
        COMMON_FILENAME: common,
        REQUEST_INPUT_FILENAME: _root(
            REQUEST_INPUT_FILENAME, _cref("request_input")
        ),
        OBSERVE_INPUT_FILENAME: _root(
            OBSERVE_INPUT_FILENAME, _cref("observe_input")
        ),
        COMMAND_RESULT_FILENAME: _root(
            COMMAND_RESULT_FILENAME, _cref("command_result")
        ),
        "video-paper-wiki.code-proof-request.v1.schema.json": _envelope(
            "code-proof-request", "request_data"
        ),
        "video-paper-wiki.code-git-bundle.v1.schema.json": _envelope(
            "code-git-bundle", "bundle_data"
        ),
        "video-paper-wiki.code-acquisition-intent.v1.schema.json": _envelope(
            "code-acquisition-intent", "intent_data"
        ),
        "video-paper-wiki.code-proof-observation.v1.schema.json": _envelope(
            "code-proof-observation", "observation_data"
        ),
        "video-paper-wiki.code-config-evidence.v1.schema.json": _envelope(
            "code-config-evidence", "config_data"
        ),
        "video-paper-wiki.code-source-handoff.v1.schema.json": _envelope(
            "code-source-handoff", "handoff_data"
        ),
    }
    if tuple(documents) != SCHEMA_FILENAMES:
        raise RuntimeError("schema document inventory does not match R12")
    return documents


def build_profile(inventory: list[dict]) -> dict:
    return {
        "schema": "video-paper-wiki.code-proof-profile.v1",
        "profile": "code-proof-v1",
        "revision": 1,
        "limits": {
            "git": dict(GIT_LIMITS),
            "config": dict(CONFIG_LIMITS),
            "public": dict(PUBLIC_LIMITS),
        },
        "admission": {
            "max_request_input_bytes": 65536,
            "max_observe_input_bytes": 1048576,
        },
        "schemas": inventory,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise SystemExit(f"refusing existing output path: {output_dir}")
    try:
        output_dir.mkdir()
        schema_dir = output_dir / "schemas"
        schema_dir.mkdir()
        profile_dir = output_dir / "src" / "video_paper_wiki" / "profiles"
        profile_dir.mkdir(parents=True)
        documents = build_schema_documents()
        inventory = []
        for filename in sorted(documents):
            blob = _dump(documents[filename])
            (schema_dir / filename).write_bytes(blob)
            inventory.append(
                {
                    "title": _title(filename),
                    "filename": filename,
                    "size_bytes": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest(),
                }
            )
        profile_blob = _dump(build_profile(inventory))
        (profile_dir / "code-proof-v1.json").write_bytes(profile_blob)
    except OSError as exc:
        raise SystemExit(f"failed to write resources: {exc}") from exc


if __name__ == "__main__":
    main()
