from __future__ import annotations

import copy
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document

from .paths import VALID, load_json

ENVELOPE_EXCEPTIONS = {
    ("oneOf", "0", "properties", "data"),
    ("oneOf", "1", "properties", "error", "properties", "details"),
}
RUNTIME_OVERLAYS = {
    ("properties", "runtime", "oneOf", str(index)) for index in range(3)
}
CODE_COMMON_SCHEMA = "video-paper-wiki.code-proof-common.v1.schema.json"
CODE_CONDITIONAL_OVERLAYS = {
    ("$defs", "request_target", branch) for branch in ("if", "then")
} | {
    ("$defs", name, "allOf", str(index), branch)
    for name, count in (("git_stopped_at", 2), ("status_payload", 8))
    for index in range(count)
    for branch in ("if", "then")
}
FLOW_STATUS_SCHEMA = "video-paper-wiki.flow-status.v1.schema.json"
# Exact Cartesian suffixes from the frozen CI-4MATRIX-R1 allowance. Empty
# suffix is the applicator node itself. No blanket if/then/allOf exemption.
_FLOW_OVERLAY_SUFFIXES = (
    ("allOf/0/if", ("", "properties/stages", "properties/stages/properties/compare")),
    (
        "allOf/0/then",
        (
            "",
            "properties/counts",
            "properties/stages",
            "properties/stages/properties/compare",
        ),
    ),
    ("allOf/1/if/not", ("", "properties/stages", "properties/stages/properties/compare")),
    (
        "allOf/1/then",
        (
            "",
            "properties/counts",
            "properties/stages",
            "properties/stages/properties/compare",
        ),
    ),
)
PDF_BINDING_SCHEMA = "video-paper-wiki.pdf-binding.v1.schema.json"
PDF_BINDING_TITLE = "video-paper-wiki.pdf-binding.v1"
# Exact frozen allowance: the existing-note predicate only. No blanket
# if/then/allOf or whole-schema exemption.
_PDF_BINDING_OVERLAY_SUFFIXES = (("properties/identity_basis/allOf/0/if", ("",)),)
_APPLICATOR_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "if", "then", "else", "not"})
_INDEXED_APPLICATORS = frozenset({"allOf", "anyOf", "oneOf"})


def _cartesian_overlays(rows: tuple[tuple[str, tuple[str, ...]], ...]) -> set[tuple[str, ...]]:
    overlays: set[tuple[str, ...]] = set()
    for prefix, suffixes in rows:
        base = tuple(prefix.split("/"))
        for suffix in suffixes:
            extra = tuple(part for part in suffix.split("/") if part)
            overlays.add(base + extra)
    return overlays


FLOW_OVERLAYS = _cartesian_overlays(_FLOW_OVERLAY_SUFFIXES)
PDF_BINDING_OVERLAYS = _cartesian_overlays(_PDF_BINDING_OVERLAY_SUFFIXES)


def _assert_code_overlay_is_inside_closed_object(schema, node, path) -> None:
    parent = schema["$defs"][path[1]]
    assert parent["type"] == "object"
    assert parent["additionalProperties"] is False
    expected_keys = {"properties", "required"} if path[-1] == "if" else {"properties"}
    assert set(node) == expected_keys
    assert node["properties"]
    assert set(node["properties"]) <= set(parent["properties"])
    if path[-1] == "if":
        assert node["required"] == list(node["properties"])


def _resolve_local_ref(schema: dict, node: dict) -> dict:
    seen: set[str] = set()
    current = node
    while isinstance(current, dict) and set(current) == {"$ref"}:
        ref = current["$ref"]
        assert isinstance(ref, str) and ref.startswith("#/"), ref
        assert ref not in seen, ref
        seen.add(ref)
        current = schema
        for part in ref[2:].split("/"):
            current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _closed_object(node: dict, where: str) -> dict:
    assert node.get("type") == "object", where
    assert node.get("additionalProperties") is False, f"{where} is not an already closed instance"
    assert isinstance(node.get("properties"), dict) and node["properties"], where
    return node


def _closed_instance_schema(schema: dict, path: tuple[str, ...]) -> dict:
    """Closed instance object that this applicator path refines."""

    current = schema
    index = 0
    while index < len(path):
        key = path[index]
        if key in _APPLICATOR_KEYWORDS:
            index += 1
            continue
        if key.isdigit() and index > 0 and path[index - 1] in _INDEXED_APPLICATORS:
            index += 1
            continue
        assert key == "properties" and index + 1 < len(path), "/".join(path)
        name = path[index + 1]
        parent = _closed_object(_resolve_local_ref(schema, current), "/".join(path[:index]) or "<root>")
        assert name in parent["properties"], name
        current = parent["properties"][name]
        index += 2
    return _closed_object(_resolve_local_ref(schema, current), "/".join(path))


def _assert_guarded_overlay(schema: dict, node: dict, path: tuple[str, ...]) -> None:
    parent = _closed_instance_schema(schema, path)
    assert set(node) <= {"type", "properties", "required"}, "/".join(path)
    assert "additionalProperties" not in node, "/".join(path)
    if "type" in node:
        assert node["type"] == "object", "/".join(path)
    assert isinstance(node.get("properties"), dict) and node["properties"], "/".join(path)
    refined = set(node["properties"])
    declared = set(parent["properties"])
    assert refined <= declared, f"{'/'.join(path)} refines undeclared {sorted(refined - declared)}"
    if "required" in node:
        assert set(node["required"]) == refined, "/".join(path)


def _walk(value: object, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        yield value, path
        for key, child in value.items():
            yield from _walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))


def _assert_schema_objects_closed(schema: dict, schema_label: Path | str) -> None:
    schema_name = schema_label.name if isinstance(schema_label, Path) else schema_label
    for node, path in _walk(schema):
        if node.get("type") == "object" or "properties" in node:
            if schema_name == "video-paper-wiki.cli-envelope.v1.schema.json" and path in ENVELOPE_EXCEPTIONS:
                assert node.get("additionalProperties") is True
            elif (
                schema_name == "video-paper-wiki.projection-generation.v1.schema.json"
                and path in RUNTIME_OVERLAYS
            ):
                assert "additionalProperties" not in node
            elif schema_name == CODE_COMMON_SCHEMA and path in CODE_CONDITIONAL_OVERLAYS:
                _assert_code_overlay_is_inside_closed_object(schema, node, path)
            elif schema_name == FLOW_STATUS_SCHEMA and path in FLOW_OVERLAYS:
                _assert_guarded_overlay(schema, node, path)
            elif schema_name == PDF_BINDING_SCHEMA and path in PDF_BINDING_OVERLAYS:
                _assert_guarded_overlay(schema, node, path)
            else:
                assert node.get("additionalProperties") is False, f"{schema_label}:{'/'.join(path)}"


def test_every_declared_object_schema_is_closed(schema_paths: list[Path]) -> None:
    for schema_path in schema_paths:
        _assert_schema_objects_closed(load_json(schema_path), schema_path)


def test_flow_conditional_overlays_only_refine_closed_objects() -> None:
    schema = load_json(Path("schemas") / FLOW_STATUS_SCHEMA)
    assert len(FLOW_OVERLAYS) == 14
    observed: set[tuple[str, ...]] = set()
    for node, path in _walk(schema):
        if (node.get("type") == "object" or "properties" in node) and node.get("additionalProperties") is not False:
            assert path in FLOW_OVERLAYS
            _assert_guarded_overlay(schema, node, path)
            observed.add(path)
    assert observed == FLOW_OVERLAYS


def test_unlisted_flow_overlay_is_rejected() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / FLOW_STATUS_SCHEMA))
    schema["allOf"].append({"if": {"properties": {"publication": {"const": "unpublished"}}}})
    with pytest.raises(AssertionError, match="allOf/2/if"):
        _assert_schema_objects_closed(schema, FLOW_STATUS_SCHEMA)


def test_flow_overlay_cannot_refine_an_undeclared_field() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / FLOW_STATUS_SCHEMA))
    schema["allOf"][0]["if"]["properties"]["not_declared"] = {"const": True}
    with pytest.raises(AssertionError, match="refines undeclared"):
        _assert_schema_objects_closed(schema, FLOW_STATUS_SCHEMA)


def test_opened_flow_instance_is_rejected() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / FLOW_STATUS_SCHEMA))
    del schema["$defs"]["stages"]["properties"]["compare"]["additionalProperties"]
    with pytest.raises(AssertionError, match="not an already closed instance"):
        _assert_schema_objects_closed(schema, FLOW_STATUS_SCHEMA)


def test_pdf_binding_conditional_overlay_only_refines_closed_object() -> None:
    schema = load_json(Path("schemas") / PDF_BINDING_SCHEMA)
    assert len(PDF_BINDING_OVERLAYS) == 1
    observed: set[tuple[str, ...]] = set()
    for node, path in _walk(schema):
        if (node.get("type") == "object" or "properties" in node) and node.get("additionalProperties") is not False:
            assert path in PDF_BINDING_OVERLAYS
            _assert_guarded_overlay(schema, node, path)
            observed.add(path)
    assert observed == PDF_BINDING_OVERLAYS


def test_unlisted_pdf_binding_overlay_is_rejected() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / PDF_BINDING_SCHEMA))
    schema["properties"]["identity_basis"]["allOf"][0]["then"] = {
        "properties": {"scanned_text": {"minLength": 1}}
    }
    with pytest.raises(AssertionError, match="properties/identity_basis/allOf/0/then"):
        _assert_schema_objects_closed(schema, PDF_BINDING_SCHEMA)


def test_pdf_binding_overlay_cannot_refine_an_undeclared_field() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / PDF_BINDING_SCHEMA))
    schema["properties"]["identity_basis"]["allOf"][0]["if"]["properties"]["not_declared"] = {"const": True}
    with pytest.raises(AssertionError, match="refines undeclared"):
        _assert_schema_objects_closed(schema, PDF_BINDING_SCHEMA)


def test_opened_pdf_binding_instance_is_rejected() -> None:
    schema = copy.deepcopy(load_json(Path("schemas") / PDF_BINDING_SCHEMA))
    del schema["properties"]["identity_basis"]["additionalProperties"]
    with pytest.raises(AssertionError, match="properties/identity_basis"):
        _assert_schema_objects_closed(schema, PDF_BINDING_SCHEMA)


def test_existing_note_conditional_keeps_declared_scanned_text() -> None:
    document = load_json(VALID / f"{PDF_BINDING_TITLE}.json")
    validate_document(document, expected_schema=PDF_BINDING_TITLE)
    missing = copy.deepcopy(document)
    missing["identity_basis"]["kind"] = "existing-note"
    with pytest.raises(ContractError) as missing_text:
        validate_document(missing, expected_schema=PDF_BINDING_TITLE)
    assert missing_text.value.code == "SCHEMA_INVALID"
    present = copy.deepcopy(missing)
    present["identity_basis"]["scanned_text"] = "kept note\n"
    validate_document(present, expected_schema=PDF_BINDING_TITLE)
    unknown = copy.deepcopy(document)
    unknown["identity_basis"]["not_declared"] = True
    with pytest.raises(ContractError) as extra_field:
        validate_document(unknown, expected_schema=PDF_BINDING_TITLE)
    assert extra_field.value.code == "SCHEMA_INVALID"


def test_code_conditional_overlays_only_refine_closed_objects() -> None:
    schema = load_json(Path("schemas") / CODE_COMMON_SCHEMA)
    observed = set()
    for node, path in _walk(schema):
        if (node.get("type") == "object" or "properties" in node) and node.get("additionalProperties") is not False:
            assert path in CODE_CONDITIONAL_OVERLAYS
            _assert_code_overlay_is_inside_closed_object(schema, node, path)
            observed.add(path)
    assert observed == CODE_CONDITIONAL_OVERLAYS


def test_envelope_open_payloads_are_the_only_exceptions() -> None:
    schema = load_json(Path("schemas/video-paper-wiki.cli-envelope.v1.schema.json"))
    open_paths = {path for node, path in _walk(schema) if node.get("additionalProperties") is True}
    assert open_paths == ENVELOPE_EXCEPTIONS
    assert all(branch["additionalProperties"] is False for branch in schema["oneOf"])


def test_projection_runtime_is_closed_with_exact_conditional_overlays() -> None:
    schema = load_json(Path("schemas/video-paper-wiki.projection-generation.v1.schema.json"))
    runtime = schema["properties"]["runtime"]
    assert runtime["additionalProperties"] is False
    assert len(runtime["oneOf"]) == 3
    expected = [
        {"python_version": "3.12.14", "unicode_version": "15.0.0"},
        {"python_version": "3.13.13", "unicode_version": "15.1.0"},
        {"python_version": "3.13.15", "unicode_version": "15.1.0"},
    ]
    for branch, values in zip(runtime["oneOf"], expected):
        assert set(branch) == {"properties"}
        assert set(branch["properties"]) == {"python_version", "unicode_version"}
        assert {key: value["const"] for key, value in branch["properties"].items()} == values
