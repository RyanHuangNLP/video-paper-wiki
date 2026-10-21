from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from .paths import FIXTURES, load_json


@pytest.mark.parametrize("name", ["success", "refusal", "unexpected"])
def test_cli_envelope_fixture(name: str) -> None:
    schema = load_json(Path("schemas/video-paper-wiki.cli-envelope.v1.schema.json"))
    payload = load_json(FIXTURES / "envelope" / f"{name}.json")
    Draft202012Validator(schema).validate(payload)
    assert isinstance(payload["command"], str)
    assert "schema" not in payload


def test_envelope_branches_reject_extra_fields() -> None:
    schema = load_json(Path("schemas/video-paper-wiki.cli-envelope.v1.schema.json"))
    validator = Draft202012Validator(schema)
    payload = load_json(FIXTURES / "envelope" / "success.json")
    payload["unexpected_field"] = True
    assert not validator.is_valid(payload)
