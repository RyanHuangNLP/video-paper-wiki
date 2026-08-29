from __future__ import annotations

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from .paths import VALID, load_json


def _fixture_for(schema: dict) -> Path:
    return VALID / f"{schema['title']}.json"


def _first_nested_object(document: dict) -> dict | None:
    for value in document.values():
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return None


def test_all_schemas_are_draft_2020_12_and_well_formed(schema_paths: list[Path]) -> None:
    assert len(schema_paths) == 11
    for path in schema_paths:
        schema = load_json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"https://video-paper-wiki.dev/schemas/{path.name}"
        assert schema["title"] == path.name.removesuffix(".schema.json")
        Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("schema_name", [
    "video-paper-wiki.ingest-plan.v1", "video-paper-wiki.prepared.v1",
    "video-paper-wiki.paper-analysis-draft.v1", "video-paper-wiki.paper-code-alignment.v1",
    "video-paper-wiki.paper-record.v1", "video-paper-wiki.repo-record.v1",
    "video-paper-wiki.assessment-event.v1", "video-paper-wiki.gate-decision.v1",
    "video-paper-wiki.operation-receipt.v1", "video-paper-wiki.run-manifest.v1",
])
def test_domain_valid_fixture_and_closed_top_level(schema_name: str) -> None:
    schema = load_json(Path("schemas") / f"{schema_name}.schema.json")
    document = load_json(_fixture_for(schema))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(document)
    invalid = copy.deepcopy(document)
    invalid["unexpected_field"] = true_value = True
    assert true_value
    with pytest.raises(ValidationError):
        validator.validate(invalid)


@pytest.mark.parametrize("schema_name", [
    "video-paper-wiki.ingest-plan.v1", "video-paper-wiki.prepared.v1",
    "video-paper-wiki.paper-analysis-draft.v1", "video-paper-wiki.paper-code-alignment.v1",
    "video-paper-wiki.paper-record.v1", "video-paper-wiki.repo-record.v1",
    "video-paper-wiki.operation-receipt.v1", "video-paper-wiki.run-manifest.v1",
])
def test_nested_objects_reject_extra_fields(schema_name: str) -> None:
    schema = load_json(Path("schemas") / f"{schema_name}.schema.json")
    invalid = copy.deepcopy(load_json(_fixture_for(schema)))
    nested = _first_nested_object(invalid)
    assert nested is not None
    nested["unexpected_field"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(invalid)
