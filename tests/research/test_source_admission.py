from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import make_checkout, staged_pdf_capture_input
from tests.upstream._transaction_fixture import Runner, init
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import inspect_publication, prepare_publication_source, stage_publication_request
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.staged_capture import inspect_staged_pdf_capture
from video_paper_wiki_research.source_admission import (
    SOURCE_AUTHORITY_INVALID,
    SOURCE_DUPLICATE,
    SOURCE_MISSING,
    admit_source,
)

from tests.research.conftest import UPSTREAM
LEDGERS = ["wiki/meta/ledgers/claim-ledger.json", "wiki/meta/ledgers/source-ledger.json"]
CLAIM_TEXT = "The model uses a diffusion transformer."


def _apply_bundle(vault: Path, bundle: Path, approval: str) -> dict:
    process = subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", str(UPSTREAM / "scripts/claude-obsidian.py"),
         "transaction", "apply", str(bundle), "--vault", str(vault),
         "--approved-plan-sha256", approval],
        check=True, capture_output=True, text=True,
    )
    return json.loads(process.stdout)


def apply_publication(checkout: Path, vault: Path, authority: dict) -> dict:
    bundle = Path(authority["transaction_staging"]["bundle_file"])
    if not bundle.is_absolute():
        bundle = checkout / ".work" / authority["request"]["batch_id"] / bundle
    approval = authority["transaction"]["inspection"]["approval_sha256"]
    return _apply_bundle(vault, bundle, approval)


def apply_capture(checkout: Path, vault: Path, authority: dict) -> dict:
    bundle = Path(authority["transaction_staging"]["bundle_file"])
    if not bundle.is_absolute():
        bundle = checkout / ".work" / authority["request"]["batch_id"] / bundle
    approval = authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"]
    return _apply_bundle(vault, bundle, approval)


def bootstrap_genesis(checkout: Path, vault: Path, tmp_path: Path) -> None:
    runner_root = tmp_path / "runner"
    runner_root.mkdir()
    runner = Runner(runner_root)
    init(runner, vault, "research-init")
    staged = stage_publication_request(
        batch_id="research-genesis", operation_id="research-genesis", operation_type="generic",
        payloads={"wiki/meta/records/research-genesis.json": canonicalize({"fixture": 1})},
        claimed_input_paths=LEDGERS,
    )
    authority = inspect_publication(
        prepared=staged["request_path"], operation_id="research-genesis",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    apply_publication(checkout, vault, authority)


def capture_pdf(checkout: Path, vault: Path, *, batch_id: str = "research-capture") -> tuple[bytes, dict, dict]:
    prepared, pdf, _request = staged_pdf_capture_input(checkout, batch_id=batch_id)
    authority = inspect_staged_pdf_capture(
        prepared=prepared, operation_id=batch_id, upstream_root=UPSTREAM, vault_root=vault,
    )
    assert authority["disposition"] == "create"
    applied = apply_capture(checkout, vault, authority)
    return pdf, authority, applied


def intake_for(pdf: bytes) -> dict[str, object]:
    digest = hashlib.sha256(pdf).hexdigest()
    return {
        "paper_id": "sha256:" + digest,
        "pdf_sha256": digest,
        "size_bytes": len(pdf),
        "page_count": 1,
        "media_type": "application/pdf",
        "blob_path": ".work/blobs/" + digest,
        "original_name": "manual-paper.pdf",
        "provided_identity": None,
    }


def bind_snapshots(authority: dict, applied: dict, pdf: bytes) -> tuple[dict, dict, str]:
    digest = hashlib.sha256(pdf).hexdigest()
    stored = authority["inspection"]["stored_path"]
    before = {path: None for path in applied["changed_paths"]}
    after = {
        path: {"sha256": applied["hashes"][path], "mode": applied["modes"][path]}
        for path in applied["changed_paths"]
    }
    assert stored in after and after[stored]["sha256"] == digest
    return before, after, stored


def test_admit_source_stages_inspectable_request_without_planted_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, capture, applied = capture_pdf(checkout, vault)
    intake = intake_for(pdf)
    admitted = admit_source(
        intake=intake, capture_authority=capture, vault_root=vault, upstream_root=UPSTREAM,
        batch_id="research-admit", operation_id="research-admit",
    )
    assert admitted["pdf_sha256"] == intake["pdf_sha256"]
    assert admitted["paper_id"] == intake["paper_id"]
    assert admitted["source_id"].startswith("src-")
    assert admitted["prospective_source_id"] == admitted["source_id"]
    assert admitted["next_action"] == "awaiting_operator_apply"
    assert admitted["agent_may_run_vpwiki_admin"] is False
    assert admitted["receipt_backed"] is False
    assert any(step["action"] == "apply_inspected_transaction" for step in admitted["remaining_operator_steps"])
    prepared = prepare_publication_source(
        request_path=admitted["request_path"], batch_id="research-admit",
    )
    assert prepared["request_sha256"] == admitted["request_sha256"]
    inspected = inspect_publication(
        prepared=admitted["request_path"], operation_id="research-admit",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    assert inspected["transaction"]["phase"] == "inspected"
    assert inspected["transaction"]["operation_type"] == "ingest"
    apply_publication(checkout, vault, inspected)
    report = audit_integrity(vault)
    assert admitted["stored_path"] in report["ever_claimed_raw"]
    assert not (checkout / "wiki/meta/operations").exists()
    assert not (checkout / "wiki/meta/registries/operation-head.json").exists()


def test_admit_source_missing_source_is_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    digest = "ab" * 32
    intake = {
        "paper_id": "sha256:" + digest, "pdf_sha256": digest, "size_bytes": 1,
        "page_count": 1, "media_type": "application/pdf",
    }
    with pytest.raises(ContractError) as caught:
        admit_source(
            intake=intake, capture_authority=None, vault_root=vault, upstream_root=UPSTREAM,
            batch_id="missing-source", operation_id="missing-source",
        )
    assert caught.value.code == SOURCE_MISSING


def test_admit_source_invalid_authority_is_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, capture, _applied = capture_pdf(checkout, vault)
    intake = intake_for(pdf)
    broken = copy.deepcopy(capture)
    broken["request"]["approval_ref"]["plan_approval_hash"] = "0" * 64
    with pytest.raises(ContractError) as caught:
        admit_source(
            intake=intake, capture_authority=broken, vault_root=vault, upstream_root=UPSTREAM,
            batch_id="bad-authority", operation_id="bad-authority",
        )
    assert caught.value.code == SOURCE_AUTHORITY_INVALID
    planted = intake_for(pdf)
    with pytest.raises(ContractError) as caught:
        admit_source(
            intake=planted, capture_authority=None, vault_root=vault, upstream_root=UPSTREAM,
            batch_id="planted-pdf", operation_id="planted-pdf",
        )
    assert caught.value.code == SOURCE_AUTHORITY_INVALID


def test_admit_source_duplicate_submission_is_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, capture, _applied = capture_pdf(checkout, vault)
    intake = intake_for(pdf)
    first = admit_source(
        intake=intake, capture_authority=capture, vault_root=vault, upstream_root=UPSTREAM,
        batch_id="admit-once", operation_id="admit-once",
    )
    inspected = inspect_publication(
        prepared=first["request_path"], operation_id="admit-once",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    apply_publication(checkout, vault, inspected)
    with pytest.raises(ContractError) as caught:
        admit_source(
            intake=intake, capture_authority=capture, vault_root=vault, upstream_root=UPSTREAM,
            batch_id="admit-twice", operation_id="admit-twice",
        )
    assert caught.value.code == SOURCE_DUPLICATE
