from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.upstream_adapter import validate_upstream_authority

ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json"


def authority() -> dict:
    return json.loads(VALID.read_text(encoding="utf-8"))


def error(document: object, code: str | tuple[str, ...] = "UPSTREAM_CONTRACT_MISMATCH") -> None:
    with pytest.raises(ContractError) as caught:
        validate_upstream_authority(document)
    assert caught.value.code in ((code,) if isinstance(code, str) else code)
    assert caught.value.exit_code == 2


def test_public_and_central_validation_are_independent() -> None:
    document = authority()
    public = validate_upstream_authority(document)
    central = validate_document(document, "video-paper-wiki.upstream-authority.v1")
    assert public == central == document
    assert public is not document and public["transaction"] is not document["transaction"]
    public["transport"]["content_files"].clear()
    assert document["transport"]["content_files"]


@pytest.mark.parametrize("change", ["bundle", "bundle_size", "expanded", "order", "file", "size", "phase", "runtime"])
def test_cross_field_refusals(change: str) -> None:
    document = authority()
    if change == "bundle":
        document["transport"]["bundle_sha256"] = "0" * 64
    elif change == "bundle_size":
        document["transport"]["bundle_size_bytes"] += 1
    elif change == "expanded":
        document["transaction"]["inspection"]["expanded_bundle_sha256"] = "0" * 64
    elif change == "order":
        document["transport"]["content_files"].reverse()
    elif change == "file":
        document["transport"]["content_files"][0]["content_file"] = "content/" + "0" * 64
    elif change == "size":
        document["transport"]["content_files"][0]["size_bytes"] += 1
    elif change == "phase":
        document["transaction"]["phase"] = "proposal"
        document["transaction"]["inspection"] = None
    else:
        plan = document["transaction"]["inspection"]
        document["transaction"]["runtime_result"] = {
            "schema": "claude-obsidian.transaction-result.v1",
            "status": "complete",
            "operation_id": plan["operation_id"],
            "operation_type": plan["operation_type"],
            "changed_paths": copy.deepcopy(plan["changed_paths"]),
            "hashes": copy.deepcopy(plan["hashes"]),
            "modes": copy.deepcopy(plan["modes"]),
            "bundle_sha256": plan["input_bundle_sha256"],
            "expanded_bundle_sha256": plan["expanded_bundle_sha256"],
            "approval_sha256": plan["approval_sha256"],
        }
    error(document, ("UPSTREAM_CONTRACT_MISMATCH", "TRANSACTION_UPSTREAM_MISMATCH"))


def test_profile_constants_and_schema_closure() -> None:
    document = authority()
    document["upstream"]["profile_sha256"] = "0" * 64
    error(document, "SCHEMA_INVALID")
    document = authority()
    document["transport"]["content_files"][0]["extra"] = True
    error(document, "SCHEMA_INVALID")


@pytest.mark.parametrize("bad", [1.0, b"x", (), object()])
def test_non_json_values_are_typed_schema_errors(bad: object) -> None:
    document = authority()
    document["extra_python"] = bad
    error(document, "SCHEMA_INVALID")


def test_non_string_keys_and_cycles_are_typed_schema_errors() -> None:
    document = authority()
    document[1] = True
    error(document, "SCHEMA_INVALID")
    document = authority()
    document["cycle"] = document
    error(document, "SCHEMA_INVALID")
