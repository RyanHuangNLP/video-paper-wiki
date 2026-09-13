from __future__ import annotations

from pathlib import Path

from .paths import load_json

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


def _walk(value: object, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        yield value, path
        for key, child in value.items():
            yield from _walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))


def test_every_declared_object_schema_is_closed(schema_paths: list[Path]) -> None:
    for schema_path in schema_paths:
        schema = load_json(schema_path)
        for node, path in _walk(schema):
            if node.get("type") == "object" or "properties" in node:
                if schema_path.name == "video-paper-wiki.cli-envelope.v1.schema.json" and path in ENVELOPE_EXCEPTIONS:
                    assert node.get("additionalProperties") is True
                elif (schema_path.name == "video-paper-wiki.projection-generation.v1.schema.json"
                      and path in RUNTIME_OVERLAYS):
                    assert "additionalProperties" not in node
                elif schema_path.name == CODE_COMMON_SCHEMA and path in CODE_CONDITIONAL_OVERLAYS:
                    _assert_code_overlay_is_inside_closed_object(schema, node, path)
                else:
                    assert node.get("additionalProperties") is False, f"{schema_path}:{'/'.join(path)}"


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
