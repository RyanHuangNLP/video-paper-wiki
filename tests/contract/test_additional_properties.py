from __future__ import annotations

from pathlib import Path

from .paths import load_json

ENVELOPE_EXCEPTIONS = {
    ("oneOf", "0", "properties", "data"),
    ("oneOf", "1", "properties", "error", "properties", "details"),
}


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
                else:
                    assert node.get("additionalProperties") is False, f"{schema_path}:{'/'.join(path)}"


def test_envelope_open_payloads_are_the_only_exceptions() -> None:
    schema = load_json(Path("schemas/video-paper-wiki.cli-envelope.v1.schema.json"))
    open_paths = {path for node, path in _walk(schema) if node.get("additionalProperties") is True}
    assert open_paths == ENVELOPE_EXCEPTIONS
    assert all(branch["additionalProperties"] is False for branch in schema["oneOf"])
