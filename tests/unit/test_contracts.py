from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.contract.paths import INVALID, VALID, load_json
from video_paper_wiki.contracts import (
    CLAIM_ID_COLLISION,
    CROSS_OBJECT_IDENTITY_MISMATCH,
    IDENTITY_CONFLICT,
    INVALID_PAPER_ID,
    PIPELINE_FINGERPRINT_MISMATCH,
    PLAN_HASH_MISMATCH,
    SCHEMA_INVALID,
    ContractError,
    validate_document,
)

EXPECTED = {
    "loopback_http.json": SCHEMA_INVALID,
    "wildcard_host.json": SCHEMA_INVALID,
    "wildcard_redirect.json": SCHEMA_INVALID,
    "max_pages_301.json": SCHEMA_INVALID,
    "max_bytes_over_64mib.json": SCHEMA_INVALID,
    "max_requests_over_4.json": SCHEMA_INVALID,
    "plan_subject_input_mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "plan_hash_mismatch.json": PLAN_HASH_MISMATCH,
    "prepared_empty_artifacts.json": SCHEMA_INVALID,
    "prepared_duplicate_kind.json": SCHEMA_INVALID,
    "prepared_wrong_docling_version.json": SCHEMA_INVALID,
    "prepared_absolute_artifact_path.json": SCHEMA_INVALID,
    "prepared_dotdot_artifact_path.json": SCHEMA_INVALID,
    "page_slug_as_paper_id.json": SCHEMA_INVALID,
    "paper_record_absolute_extraction_path.json": SCHEMA_INVALID,
    "official_without_evidence.json": SCHEMA_INVALID,
    "present_without_locator.json": SCHEMA_INVALID,
    "partial_without_locator.json": SCHEMA_INVALID,
    "human_without_predecessor.json": SCHEMA_INVALID,
    "invalidation_without_predecessor.json": SCHEMA_INVALID,
    "receipt_write_outside.json": SCHEMA_INVALID,
    "receipt_claimed_etc_passwd.json": SCHEMA_INVALID,
    "receipt_empty_writes.json": SCHEMA_INVALID,
    "loopback_pdf_url.json": SCHEMA_INVALID,
    "pdf_url_non_allowlist_host.json": SCHEMA_INVALID,
    "pdf_url_host_mismatch.json": SCHEMA_INVALID,
    "local_blob_garbage_arxiv_id.json": SCHEMA_INVALID,
    "local_blob_empty_arxiv_id.json": SCHEMA_INVALID,
    "local_blob_arxiv_id_mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "local_blob_arxiv_skipped_for_sha.json": IDENTITY_CONFLICT,
    "doi_non_ascii_uppercase.json": INVALID_PAPER_ID,
    "prepared_artifact_hash_mismatch.json": PIPELINE_FINGERPRINT_MISMATCH,
    "duplicate_claim_id_different_refs.json": CLAIM_ID_COLLISION,
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_independent_negative_fixtures_use_stable_codes(name: str) -> None:
    document = load_json(INVALID / name)
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema=document.get("schema"))
    assert exc.value.code == EXPECTED[name]
    assert isinstance(exc.value.message, str) and exc.value.message
    assert isinstance(exc.value.details, dict)


@pytest.mark.parametrize("path", sorted(VALID.glob("*.json")))
def test_valid_domain_fixtures_pass_production_validator(path: Path) -> None:
    document = load_json(path)
    validate_document(document, expected_schema=document["schema"])


def test_schema_error_details_include_pointer_and_keyword() -> None:
    document = json.loads((VALID / "video-paper-wiki.paper-analysis-draft.v1.json").read_text(encoding="utf-8"))
    document["paper_id"] = "arxiv-2311.15127"
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema="video-paper-wiki.paper-analysis-draft.v1")
    assert exc.value.code == SCHEMA_INVALID
    assert exc.value.details["schema"] == "video-paper-wiki.paper-analysis-draft.v1"
    assert exc.value.details["instance_pointer"] == "/paper_id"
    assert exc.value.details["keyword"]


def test_dotdot_artifact_schema_error_details() -> None:
    document = load_json(INVALID / "prepared_dotdot_artifact_path.json")
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema=document["schema"])
    assert exc.value.code == SCHEMA_INVALID
    assert exc.value.details["schema"] == "video-paper-wiki.prepared.v1"
    assert exc.value.details["instance_pointer"]
    assert exc.value.details["keyword"]


def test_registry_resolves_shared_refs_without_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    document = load_json(VALID / "video-paper-wiki.ingest-plan.v1.json")
    validate_document(document, expected_schema="video-paper-wiki.ingest-plan.v1")
