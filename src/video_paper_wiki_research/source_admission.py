"""Admit a captured PDF into the canonical source ledger via existing publication inspect.

This adapter never plants receipts or heads and never applies a transaction.
Agent-side work stops at a staged, inspectable publication request.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import stage_publication_request
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json, read_regular_file
from video_paper_wiki.staged_capture import validate_staged_pdf_capture_authority
from video_paper_wiki.upstream_adapter import verify_pinned_source_id

SOURCE_MISSING = "SOURCE_MISSING"
SOURCE_AUTHORITY_INVALID = "SOURCE_AUTHORITY_INVALID"
SOURCE_DUPLICATE = "SOURCE_DUPLICATE"
SOURCE_LEDGER = "wiki/meta/ledgers/source-ledger.json"
CLAIM_LEDGER = "wiki/meta/ledgers/claim-ledger.json"
_HASH = re.compile(r"[0-9a-f]{64}")
_CAPTURED = re.compile(r"^\.raw/captured/([0-9a-f]{64})\.pdf$")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def _fail(code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
    raise ContractError(code, message, dict(details or {}))


def remaining_operator_steps(*, capture_authorized: bool = True) -> list[dict[str, str]]:
    """Name the operator/user steps this adapter must not perform."""
    steps: list[dict[str, str]] = []
    if not capture_authorized:
        steps.append({
            "actor": "user",
            "action": "supply_external_approval_ref",
            "detail": "Real capture requires an external approval-ref; this adapter never creates one.",
        })
    steps.append({
        "actor": "operator",
        "action": "apply_inspected_transaction",
        "detail": "Apply the inspected bundle with the existing vendor transaction apply helper.",
    })
    steps.append({
        "actor": "operator",
        "action": "mutate_vault",
        "detail": "Vault mutation is operator-owned. Agent-side work stops at prepare/inspect.",
    })
    steps.append({
        "actor": "operator",
        "action": "do_not_run_vpwiki_admin",
        "detail": "Agents must not run vpwiki-admin against a real or disposable Vault.",
    })
    return steps


def _intake_data(intake: object) -> dict[str, Any]:
    if type(intake) is not dict:
        _fail(SOURCE_MISSING, "staged intake is missing")
    data = intake["data"] if type(intake.get("data")) is dict else intake
    if type(data) is not dict:
        _fail(SOURCE_MISSING, "staged intake is missing")
    digest = data.get("pdf_sha256")
    paper_id = data.get("paper_id")
    if type(digest) is not str or _HASH.fullmatch(digest) is None:
        _fail(SOURCE_MISSING, "intake PDF digest is missing or invalid")
    if type(paper_id) is not str or not is_canonical_paper_id(paper_id):
        _fail(SOURCE_MISSING, "intake paper identity is missing or invalid")
    if data.get("media_type") not in {None, "application/pdf"}:
        _fail(SOURCE_MISSING, "intake is not a PDF")
    return data


def _validate_capture_authority(capture_authority: object, digest: str) -> dict[str, Any]:
    if capture_authority is None:
        _fail(SOURCE_AUTHORITY_INVALID, "capture authority is missing")
    try:
        authority = validate_staged_pdf_capture_authority(capture_authority)
    except (ContractError, TypeError, ValueError) as exc:
        _fail(SOURCE_AUTHORITY_INVALID, "capture authority is invalid", {
            "cause": getattr(exc, "code", type(exc).__name__),
        })
    request = authority["request"]
    ref = request.get("approval_ref")
    if type(ref) is not dict or ref.get("format") != "video-paper-wiki.approval-ref.v1":
        _fail(SOURCE_AUTHORITY_INVALID, "approval-ref is missing")
    if type(ref.get("plan_approval_hash")) is not str or _HASH.fullmatch(ref["plan_approval_hash"]) is None:
        _fail(SOURCE_AUTHORITY_INVALID, "approval-ref is invalid")
    payload = request["payload"]
    inspection = authority["inspection"]
    if payload["sha256"] != digest or inspection["source_identity"] != digest:
        _fail(SOURCE_AUTHORITY_INVALID, "capture authority does not bind the intake PDF digest")
    stored = inspection["stored_path"]
    if type(stored) is not str or _CAPTURED.fullmatch(stored) is None or _CAPTURED.fullmatch(stored).group(1) != digest:
        _fail(SOURCE_AUTHORITY_INVALID, "captured PDF path is not the digest-addressed slot")
    return authority


def _read_captured_pdf(vault: Path, stored_path: str, digest: str) -> bytes:
    target = vault / stored_path
    try:
        data = read_regular_file(
            target,
            missing_code=SOURCE_MISSING,
            unsafe_code=SOURCE_AUTHORITY_INVALID,
            changed_code=SOURCE_AUTHORITY_INVALID,
            max_bytes=64 * 1024 * 1024,
            limit_code=SOURCE_MISSING,
        )
    except (ContractError, SecureIOError) as exc:
        if getattr(exc, "code", None) == SOURCE_MISSING:
            _fail(SOURCE_MISSING, "captured PDF is not present in the Vault")
        _fail(SOURCE_AUTHORITY_INVALID, "captured PDF is unsafe or changed", {
            "cause": getattr(exc, "code", type(exc).__name__),
        })
    except (OSError, ValueError, TypeError):
        _fail(SOURCE_MISSING, "captured PDF is not present in the Vault")
    if hashlib.sha256(data).hexdigest() != digest:
        _fail(SOURCE_AUTHORITY_INVALID, "captured PDF bytes differ from the intake digest")
    return data


def _load_source_ledger(vault: Path) -> dict[str, Any]:
    try:
        raw = read_regular_file(
            vault / SOURCE_LEDGER,
            missing_code=SOURCE_MISSING,
            unsafe_code=SOURCE_AUTHORITY_INVALID,
            changed_code=SOURCE_AUTHORITY_INVALID,
            max_bytes=16 * 1024 * 1024,
            limit_code=SOURCE_MISSING,
        )
        ledger = parse_strict_json(raw, invalid_code=SOURCE_AUTHORITY_INVALID)
    except (ContractError, SecureIOError) as exc:
        if getattr(exc, "code", None) == SOURCE_MISSING:
            _fail(SOURCE_MISSING, "source ledger is missing")
        if getattr(exc, "code", None) == SOURCE_AUTHORITY_INVALID:
            raise
        _fail(SOURCE_AUTHORITY_INVALID, "source ledger is unreadable", {
            "cause": getattr(exc, "code", type(exc).__name__),
        })
    if type(ledger) is not dict or type(ledger.get("sources")) is not dict:
        _fail(SOURCE_AUTHORITY_INVALID, "source ledger is malformed")
    return ledger


def _source_record(*, stored_path: str, digest: str, title: str, ingested_at: str) -> dict[str, Any]:
    day = ingested_at[:10]
    return {
        "origin": {"kind": "file", "locator": stored_path},
        "content_kind": "document",
        "title": title,
        "authority": "primary",
        "content_sha256": digest,
        "ingested_at": day,
        "retrieved_at": None,
        "refresh_due": "2099-01-01",
        "review_status": "unreviewed",
        "independence_key": None,
        "pages": [],
        "supersedes": None,
    }


def admit_source(
    *,
    intake: object,
    capture_authority: object,
    vault_root: Path | str,
    upstream_root: Path | str,
    batch_id: object,
    operation_id: str,
    ingested_at: str = "2026-09-01T00:00:00Z",
    title: str | None = None,
) -> dict[str, Any]:
    """Stage a source-ledger publication that existing inspect/prepare can consume."""
    if type(ingested_at) is not str or _TIMESTAMP.fullmatch(ingested_at) is None:
        _fail(SOURCE_AUTHORITY_INVALID, "ingested_at must be a canonical UTC timestamp")
    data = _intake_data(intake)
    digest = data["pdf_sha256"]
    paper_id = data["paper_id"]
    vault = Path(vault_root)
    expected_path = f".raw/captured/{digest}.pdf"
    if capture_authority is None:
        if not (vault / expected_path).is_file():
            _fail(SOURCE_MISSING, "captured PDF is not present in the Vault")
        _fail(SOURCE_AUTHORITY_INVALID, "capture authority is missing")
    authority = _validate_capture_authority(capture_authority, digest)
    stored_path = authority["inspection"]["stored_path"]
    _read_captured_pdf(vault, stored_path, digest)
    try:
        audit = audit_integrity(vault)
    except ContractError as exc:
        if exc.code == "RECEIPT_BOOTSTRAP_REQUIRED":
            raise
        _fail(SOURCE_AUTHORITY_INVALID, "Vault integrity is not receipt-backed", {"cause": exc.code})
    if audit.get("classification") != "receipt_backed":
        _fail(SOURCE_AUTHORITY_INVALID, "Vault is not receipt-backed; genesis must precede source admission")
    try:
        source_id = verify_pinned_source_id(stored_path, digest, upstream_root=upstream_root)
    except ContractError as exc:
        _fail(SOURCE_AUTHORITY_INVALID, "prospective source ID could not be verified", {"cause": exc.code})
    ledger = _load_source_ledger(vault)
    sources = ledger["sources"]
    for existing_id, record in sources.items():
        if type(record) is not dict:
            continue
        same_digest = record.get("content_sha256") == digest
        same_locator = type(record.get("origin")) is dict and record["origin"].get("locator") == stored_path
        if existing_id == source_id or same_digest or same_locator:
            _fail(SOURCE_DUPLICATE, "PDF or source is already admitted", {
                "source_id": existing_id,
                "pdf_sha256": digest,
            })
    if stored_path in audit.get("ever_claimed_raw", []):
        _fail(SOURCE_DUPLICATE, "captured PDF is already receipt-claimed")
    record_title = title or data.get("original_name") or f"Manual PDF {digest[:12]}"
    if type(record_title) is not str or not record_title.strip():
        record_title = f"Manual PDF {digest[:12]}"
    updated = copy.deepcopy(ledger)
    updated["generated_at"] = ingested_at
    updated["sources"][source_id] = _source_record(
        stored_path=stored_path, digest=digest, title=record_title.strip(), ingested_at=ingested_at,
    )
    staged = stage_publication_request(
        batch_id=batch_id,
        operation_id=operation_id,
        operation_type="ingest",
        payloads={SOURCE_LEDGER: canonicalize(updated)},
        claimed_input_paths=[stored_path],
        additional_read_paths=[],
        prospective_groups=[],
    )
    return {
        "state": "source_registration_prepared",
        "source_id": source_id,
        "paper_id": paper_id,
        "pdf_sha256": digest,
        "stored_path": stored_path,
        "prospective_source_id": source_id,
        "operation_id": operation_id,
        "operation_type": "ingest",
        "publication_request": staged,
        "request_path": staged["request_path"],
        "request_sha256": staged["request_sha256"],
        "next_action": "awaiting_operator_apply",
        "remaining_operator_steps": remaining_operator_steps(capture_authorized=True),
        "agent_may_run_vpwiki_admin": False,
        "capture_authorized": True,
        "receipt_backed": False,
        "published": False,
    }
