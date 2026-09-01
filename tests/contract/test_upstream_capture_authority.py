from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.upstream_adapter import validate_upstream_capture_authority


ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-capture-authority.v1.json"


def valid() -> dict:
    return json.loads(VALID.read_text(encoding="utf-8"))


def test_public_and_central_validation_return_independent_data() -> None:
    document = valid()
    public = validate_upstream_capture_authority(document)
    central = validate_document(document)
    public["request"]["source_path"] = "changed"
    assert central["request"]["source_path"] != "changed"
    assert document["request"]["source_path"] != "changed"


@pytest.mark.parametrize("field", ["source_identity", "stored_path"])
def test_cross_field_mismatch_is_normalized(field: str) -> None:
    document = valid()
    document["observation"]["item"][field] = (
        ".raw/captured/" + "0" * 64 + ".pdf" if field == "stored_path" else "0" * 64
    )
    with pytest.raises(ContractError) as caught:
        validate_upstream_capture_authority(document)
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"


def test_shape_non_string_key_and_cycle_are_schema_invalid() -> None:
    cases = [valid(), valid()]
    cases[0][1] = True
    cycle: dict = {}
    cycle["cycle"] = cycle
    cases[1]["extra"] = cycle
    for document in cases:
        with pytest.raises(ContractError) as caught:
            validate_upstream_capture_authority(document)
        assert caught.value.code == "SCHEMA_INVALID"


def test_nested_inspection_semantics_are_normalized() -> None:
    document = valid()
    document["inspection"]["approval_hash"] = "0" * 64
    with pytest.raises(ContractError) as caught:
        validate_document(document)
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"


@pytest.mark.parametrize("case", [
    "request-operation", "request-time", "item-source", "metadata-name",
    "operation-path", "operation-write-sha", "approval", "observation-time",
])
def test_complete_authority_correlations(case: str) -> None:
    document = valid()
    digest = document["inspection"]["payload"]["sha256"]
    changes = {
        "request-operation": (document["request"], "operation_id", "capture-other"),
        "request-time": (document["request"], "generated_at", "2026-09-01T04:00:01Z"),
        "item-source": (document["observation"]["item"], "source", "inbox/other.pdf"),
        "metadata-name": (document["observation"]["item"]["metadata"], "name", "other.pdf"),
        "operation-path": (document["observation"]["operation"], "expected_path",
                           f".raw/captured/{digest}.bin"),
        "operation-write-sha": (document["observation"]["operation"]["write"], "sha256", "0" * 64),
        "approval": (document["observation"], "approved_plan_sha256", "0" * 64),
        "observation-time": (document["observation"], "generated_at", "2026-09-01T04:00:01Z"),
    }
    target, field, value = changes[case]
    target[field] = value
    with pytest.raises(ContractError) as caught:
        validate_upstream_capture_authority(document)
    assert caught.value.code == "UPSTREAM_CONTRACT_MISMATCH"
