from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.paths import PROSPECTIVE, load_json
from video_paper_wiki.contracts import (
    ASSESSMENT_CHAIN_INVALID,
    CLAIM_ID_COLLISION,
    CLAIM_ID_MISMATCH,
    CROSS_OBJECT_IDENTITY_MISMATCH,
    EVIDENCE_FINGERPRINT_MISMATCH,
    IDENTITY_CONFLICT,
    PIPELINE_FINGERPRINT_MISMATCH,
    PRIMARY_OWNER_INVALID,
    RECEIPT_INTENT_MISMATCH,
    ContractError,
    validate_prospective,
)

CASES = {
    "valid-bundle.json": None,
    "same-paper-different-pdf.json": IDENTITY_CONFLICT,
    "claim-id-mismatch.json": CLAIM_ID_MISMATCH,
    "claim-id-collision.json": CLAIM_ID_COLLISION,
    "claim-id-duplicate-refs.json": CLAIM_ID_COLLISION,
    "claim-missing-fields.json": CLAIM_ID_MISMATCH,
    "owner-missing.json": PRIMARY_OWNER_INVALID,
    "owner-duplicate.json": PRIMARY_OWNER_INVALID,
    "active-extraction-path-mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "active-extraction-hash-mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "plan-subject-draft-mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "event-fork.json": ASSESSMENT_CHAIN_INVALID,
    "event-dangling.json": ASSESSMENT_CHAIN_INVALID,
    "event-cross-claim-parent.json": ASSESSMENT_CHAIN_INVALID,
    "event-wrong-head.json": ASSESSMENT_CHAIN_INVALID,
    "event-assessment-chain-mismatch.json": ASSESSMENT_CHAIN_INVALID,
    "evidence-fingerprint-mismatch.json": EVIDENCE_FINGERPRINT_MISMATCH,
    "empty-evidence-fingerprint.json": EVIDENCE_FINGERPRINT_MISMATCH,
    "receipt-intent-mismatch.json": RECEIPT_INTENT_MISMATCH,
    "prepared-artifact-hash-mismatch.json": PIPELINE_FINGERPRINT_MISMATCH,
    "run-manifest-hash-mismatch.json": CROSS_OBJECT_IDENTITY_MISMATCH,
    "locator-document-hash-mismatch.json": EVIDENCE_FINGERPRINT_MISMATCH,
    "claim-id-null-evidence.json": CLAIM_ID_COLLISION,
    "local-blob-arxiv-skipped-for-sha.json": IDENTITY_CONFLICT,
}


def _load_bundle(name: str) -> tuple[dict, dict, dict]:
    payload = load_json(PROSPECTIVE / name)
    assert isinstance(payload, dict)
    paper = payload.pop("existing_paper_bindings", {}) or {}
    claims = payload.pop("existing_claim_bindings", {}) or {}
    return payload, paper, claims


@pytest.mark.parametrize("name, code", sorted(CASES.items()))
def test_prospective_fixtures(name: str, code: str | None) -> None:
    bundle, paper, claims = _load_bundle(name)
    if code is None:
        validate_prospective(bundle, existing_paper_bindings=paper, existing_claim_bindings=claims)
        return
    with pytest.raises(ContractError) as exc:
        validate_prospective(bundle, existing_paper_bindings=paper, existing_claim_bindings=claims)
    assert exc.value.code == code
    if code in {IDENTITY_CONFLICT, CLAIM_ID_COLLISION}:
        assert exc.value.exit_code == 75
