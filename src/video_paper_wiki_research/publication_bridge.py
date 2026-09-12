"""Bind a capture result, package staged Docling artifacts, and prepare paper records.

Paper/concept Markdown pages still require accepted core conclusion claims in the
existing compiler. This adapter stages inspectable records/events/ledgers from a
provisional draft and names the remaining human review step. It never plants
receipts or heads and never applies a transaction.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.canonical_compiler import concept_items_for_papers
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.extraction_artifact import prepare_docling_publication
from video_paper_wiki.identity import (
    assessment_event_id,
    claim_id,
    evidence_fingerprint,
    is_canonical_paper_id,
    paper_page_slug,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import encode_ledger_evidence
from video_paper_wiki.operation_result import bind_operation_result
from video_paper_wiki.projection_runtime import parse_projection_json
from video_paper_wiki.publication import stage_publication_request
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json, read_regular_file

from video_paper_wiki_research.source_admission import (
    SOURCE_AUTHORITY_INVALID,
    SOURCE_DUPLICATE,
    SOURCE_LEDGER,
    SOURCE_MISSING,
    remaining_operator_steps,
)

CLAIM_LEDGER = "wiki/meta/ledgers/claim-ledger.json"


def _fail(code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
    raise ContractError(code, message, dict(details or {}))


def _paper_operator_steps() -> list[dict[str, str]]:
    steps = remaining_operator_steps(capture_authorized=True)
    steps.insert(-1, {
        "actor": "user",
        "action": "human_claim_assessment",
        "detail": (
            "Canonical paper/concept pages require accepted or contested core "
            "conclusion claims. Review remains a human/operator gate."
        ),
    })
    return steps


def bind_capture_operation(
    *,
    inspected_transaction: object,
    apply_result: object,
    vault_before: object,
    vault_after: object,
    expected_pdf_sha256: str,
    stored_path: str,
) -> dict[str, Any]:
    """Bind an externally applied capture result to the intake PDF digest."""
    if type(expected_pdf_sha256) is not str or type(stored_path) is not str:
        _fail(SOURCE_AUTHORITY_INVALID, "capture digest binding requires exact path and digest")
    try:
        bound = bind_operation_result(
            inspected_transaction, apply_result, vault_before=vault_before, vault_after=vault_after,
        )
    except ContractError as exc:
        _fail(SOURCE_AUTHORITY_INVALID, "capture operation result could not be bound", {
            "cause": exc.code,
        })
    after = bound["vault_after"].get(stored_path)
    result = bound["result"]
    if type(after) is not dict or after.get("sha256") != expected_pdf_sha256:
        _fail(SOURCE_AUTHORITY_INVALID, "bound capture result does not match the intake PDF digest")
    if result["hashes"].get(stored_path) != expected_pdf_sha256:
        _fail(SOURCE_AUTHORITY_INVALID, "applied capture hash differs from the intake PDF digest")
    return bound


def package_extraction_run(
    *,
    captured_pdf: Path | str,
    document_json: Path | str,
    parser_config: Path | str,
    model_manifest: Path | str,
    run_manifest: Path | str,
    vault_root: Path | str,
    batch_id: object,
    operation_id: str,
    claimed_input_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Call existing package after confirming the captured PDF is receipt-backed."""
    vault = Path(vault_root)
    try:
        audit = audit_integrity(vault)
    except ContractError as exc:
        if exc.code == "RECEIPT_BOOTSTRAP_REQUIRED":
            raise
        _fail(SOURCE_AUTHORITY_INVALID, "Vault integrity is not receipt-backed", {"cause": exc.code})
    captured = Path(captured_pdf)
    if not captured.is_file():
        _fail(SOURCE_MISSING, "captured PDF is not present")
    try:
        relative = captured.resolve().relative_to(vault.resolve()).as_posix()
    except (OSError, ValueError, TypeError):
        _fail(SOURCE_MISSING, "captured PDF path is not Vault-relative")
    if relative not in audit.get("ever_claimed_raw", []):
        _fail(SOURCE_AUTHORITY_INVALID, "captured PDF is not receipt-backed")
    context = {
        "operation_id": operation_id,
        "claimed_input_paths": list(claimed_input_paths or []),
        "prospective_groups": [],
    }
    try:
        packaged = prepare_docling_publication(
            captured_pdf=captured_pdf,
            document_json=document_json,
            parser_config=parser_config,
            model_manifest=model_manifest,
            run_manifest=run_manifest,
            publication_context=context,
            batch_id=batch_id,
            vault_root=vault,
        )
    except ContractError as exc:
        if exc.code == "NONDETERMINISTIC_EXTRACTION":
            _fail(SOURCE_DUPLICATE, "derived artifact path already holds different bytes")
        if exc.code == "DOCLING_ARTIFACT_INVALID" and "receipt-backed" in exc.message:
            _fail(SOURCE_AUTHORITY_INVALID, "captured PDF is not receipt-backed")
        if exc.code in {SOURCE_MISSING, "DOCLING_ARTIFACT_INVALID"} and "unavailable" in exc.message:
            _fail(SOURCE_MISSING, "staged extraction artifact is missing")
        raise
    request = packaged.get("publication_request")
    return {
        "state": "already_packaged" if packaged.get("already_packaged") else "artifact_package_prepared",
        "artifact_set": packaged["artifact_set"],
        "publication_request": request,
        "request_path": None if request is None else request["request_path"],
        "request_sha256": None if request is None else request["request_sha256"],
        "already_packaged": bool(packaged.get("already_packaged")),
        "operation_id": operation_id,
        "operation_type": "ingest",
        "next_action": "already_packaged" if packaged.get("already_packaged") else "awaiting_operator_apply",
        "remaining_operator_steps": remaining_operator_steps(capture_authorized=True),
        "agent_may_run_vpwiki_admin": False,
        "receipt_backed": True,
        "published": False,
        "external_gate_satisfied": bool(packaged.get("external_gate_satisfied")),
    }


def _load_draft(legacy_draft: object) -> dict[str, Any]:
    if isinstance(legacy_draft, (bytes, bytearray)):
        parsed = parse_projection_json(bytes(legacy_draft))
    elif isinstance(legacy_draft, Path):
        raw = read_regular_file(
            legacy_draft,
            missing_code=SOURCE_MISSING,
            unsafe_code=SOURCE_AUTHORITY_INVALID,
            changed_code=SOURCE_AUTHORITY_INVALID,
            max_bytes=8 * 1024 * 1024,
            limit_code=SOURCE_MISSING,
        )
        parsed = parse_projection_json(raw)
    elif type(legacy_draft) is dict:
        parsed = copy.deepcopy(legacy_draft)
    else:
        _fail(SOURCE_MISSING, "legacy draft is missing")
    if type(parsed) is not dict:
        _fail(SOURCE_AUTHORITY_INVALID, "legacy draft is not an object")
    try:
        return validate_document(parsed, "video-paper-wiki.paper-analysis-draft.v1")
    except ContractError as exc:
        _fail(SOURCE_AUTHORITY_INVALID, "legacy draft is invalid", {"cause": exc.code})


def _integer_bbox(value: object) -> list[int] | None:
    if type(value) is not list or len(value) != 4:
        return None
    out: list[int] = []
    for item in value:
        if type(item) is int and not isinstance(item, bool):
            out.append(item)
        elif type(item) is float and item.is_integer():
            out.append(int(item))
        else:
            return None
    return out


def _domain_evidence(locator: Mapping[str, Any], *, source_id: str, artifact_path: str, artifact_sha256: str) -> dict[str, Any]:
    evidence = {
        "relation": "supports",
        "kind": "pdf",
        "source_id": source_id,
        "page": locator["page"],
        "ref": locator["ref"],
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "text_sha256": locator["text_sha256"],
    }
    bbox = _integer_bbox(locator.get("bbox"))
    if bbox is not None:
        evidence["bbox"] = bbox
    charspan = locator.get("charspan")
    if type(charspan) is list and len(charspan) == 2 and all(type(x) is int and not isinstance(x, bool) for x in charspan):
        evidence["charspan"] = [charspan[0], charspan[1]]
    return evidence


def _load_claim_ledger(vault: Path) -> dict[str, Any]:
    try:
        raw = read_regular_file(
            vault / CLAIM_LEDGER,
            missing_code=SOURCE_MISSING,
            unsafe_code=SOURCE_AUTHORITY_INVALID,
            changed_code=SOURCE_AUTHORITY_INVALID,
            max_bytes=16 * 1024 * 1024,
            limit_code=SOURCE_MISSING,
        )
        ledger = parse_strict_json(raw, invalid_code=SOURCE_AUTHORITY_INVALID)
    except (ContractError, SecureIOError) as exc:
        if getattr(exc, "code", None) == SOURCE_MISSING:
            _fail(SOURCE_MISSING, "claim ledger is missing")
        if getattr(exc, "code", None) == SOURCE_AUTHORITY_INVALID:
            raise
        _fail(SOURCE_AUTHORITY_INVALID, "claim ledger is unreadable", {
            "cause": getattr(exc, "code", type(exc).__name__),
        })
    if type(ledger) is not dict or type(ledger.get("claims")) is not dict:
        _fail(SOURCE_AUTHORITY_INVALID, "claim ledger is malformed")
    return ledger


def prepare_paper_concept_publication(
    *,
    intake: object,
    legacy_draft: object,
    source_id: str,
    artifact_set: Mapping[str, Any],
    vault_root: Path | str,
    batch_id: object,
    operation_id: str,
    created_at: str = "2026-09-01T00:00:00Z",
) -> dict[str, Any]:
    """Rebound paper/claim identity onto existing publication inspect inputs."""
    from video_paper_wiki_research.source_admission import _intake_data

    data = _intake_data(intake)
    paper_id = data["paper_id"]
    digest = data["pdf_sha256"]
    if type(source_id) is not str or not source_id.startswith("src-"):
        _fail(SOURCE_MISSING, "admitted source ID is missing")
    if not is_canonical_paper_id(paper_id):
        _fail(SOURCE_MISSING, "intake paper identity is invalid")
    artifacts = {item["kind"]: item for item in artifact_set.get("artifacts", [])}
    document = artifacts.get("document_json")
    if type(document) is not dict:
        _fail(SOURCE_MISSING, "artifact set is missing the derived document")
    artifact_path = document["path"]
    artifact_sha256 = document["sha256"]
    vault = Path(vault_root)
    try:
        audit = audit_integrity(vault)
    except ContractError as exc:
        _fail(SOURCE_AUTHORITY_INVALID, "Vault integrity is not receipt-backed", {"cause": exc.code})
    stored_path = f".raw/captured/{digest}.pdf"
    if stored_path not in audit.get("ever_claimed_raw", []):
        _fail(SOURCE_AUTHORITY_INVALID, "captured PDF is not receipt-backed")
    try:
        source_ledger = parse_strict_json(
            read_regular_file(
                vault / SOURCE_LEDGER,
                missing_code=SOURCE_MISSING,
                unsafe_code=SOURCE_AUTHORITY_INVALID,
                changed_code=SOURCE_AUTHORITY_INVALID,
                max_bytes=16 * 1024 * 1024,
                limit_code=SOURCE_MISSING,
            ),
            invalid_code=SOURCE_AUTHORITY_INVALID,
        )
    except (ContractError, SecureIOError) as exc:
        _fail(SOURCE_MISSING if getattr(exc, "code", None) == SOURCE_MISSING else SOURCE_AUTHORITY_INVALID,
              "source ledger is missing or invalid")
    sources = source_ledger.get("sources") if type(source_ledger) is dict else None
    if type(sources) is not dict or source_id not in sources:
        _fail(SOURCE_MISSING, "admitted source is not in the source ledger")
    record = sources[source_id]
    if type(record) is not dict or record.get("content_sha256") != digest:
        _fail(SOURCE_AUTHORITY_INVALID, "admitted source does not bind the intake PDF digest")
    draft = _load_draft(legacy_draft)
    if draft["paper_id"] != paper_id:
        _fail(SOURCE_AUTHORITY_INVALID, "legacy draft paper identity differs from intake")
    slug = paper_page_slug(paper_id)
    record_path = f"wiki/meta/records/papers/{slug}.json"
    existing = vault / record_path
    if existing.is_file():
        _fail(SOURCE_DUPLICATE, "paper record already exists at the fixed path")
    subject = "paper:" + paper_id
    compiler_claims: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    ledger_claims: dict[str, Any] = {}
    for claim in draft["claims"]:
        text = claim["claim_text"]
        expected = claim_id(subject, text)
        if claim["claim_id"] != expected:
            _fail(SOURCE_AUTHORITY_INVALID, "draft claim identity differs")
        locators = claim.get("locators") or []
        if not locators:
            _fail(SOURCE_AUTHORITY_INVALID, "draft claim is missing locators")
        evidence = [
            _domain_evidence(locator, source_id=source_id, artifact_path=artifact_path, artifact_sha256=artifact_sha256)
            for locator in locators
        ]
        compiler_claim = {
            "claim_id": expected,
            "stable_subject_id": subject,
            "canonical_claim_text": text,
            "evidence": evidence,
            "assessment": "provisional",
            "reviewed_at": None,
        }
        compiler_claims.append(compiler_claim)
        fingerprint = evidence_fingerprint(evidence)
        event = {
            "schema": "video-paper-wiki.assessment-event.v1",
            "event_id": "ase-" + ("0" * 20),
            "claim_id": expected,
            "previous_event_id": None,
            "actor_kind": "system",
            "transition_kind": "genesis",
            "from_assessment": None,
            "to_assessment": "provisional",
            "claim_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "evidence_fingerprint": fingerprint,
            "decided_by": "vpwiki-research-bridge",
            "decided_at": created_at,
            "reason": "Staged analysis proposal genesis; not a human acceptance.",
        }
        event["event_id"] = assessment_event_id(event)
        events.append(event)
        refs.append({
            "section": claim["section"],
            "claim_id": expected,
            "core": bool(claim.get("core")),
            "lifecycle": "active",
        })
        ledger_claims[expected] = {
            "text": text,
            "risk": "normal",
            "assessment": "provisional",
            "confidence": "low",
            "location": {"path": record_path, "anchor": None},
            "reviewed_at": None,
            "notes": None,
            "supersedes": None,
            "evidence": [encode_ledger_evidence(item) for item in evidence],
        }
    paper_record = {
        "schema": "video-paper-wiki.paper-record.v1",
        "paper_id": paper_id,
        "title": draft["title"],
        "title_zh": draft["title_zh"],
        "authors": [],
        "published_at": created_at[:10],
        "aliases": [],
        "source_ids": [source_id],
        "taxonomy": list(draft.get("taxonomy") or []),
        "active_extraction_path": artifact_path,
        "active_extraction_sha256": artifact_sha256,
        "section_claim_refs": refs,
        "created_at": created_at,
        "updated_at": created_at,
    }
    paper_record = validate_document(paper_record, "video-paper-wiki.paper-record.v1")
    concept_items = concept_items_for_papers([paper_record])
    claim_ledger = _load_claim_ledger(vault)
    updated_claims = copy.deepcopy(claim_ledger)
    updated_claims["generated_at"] = created_at
    for claim_id_key, row in ledger_claims.items():
        if claim_id_key in updated_claims["claims"]:
            _fail(SOURCE_DUPLICATE, "claim is already present in the claim ledger")
        updated_claims["claims"][claim_id_key] = row
    payloads: dict[str, bytes] = {
        record_path: canonicalize(paper_record),
        CLAIM_LEDGER: canonicalize(updated_claims),
    }
    for event in events:
        payloads[f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json"] = canonicalize(event)
    staged = stage_publication_request(
        batch_id=batch_id,
        operation_id=operation_id,
        operation_type="ingest",
        payloads=payloads,
        claimed_input_paths=sorted({stored_path, SOURCE_LEDGER}),
        additional_read_paths=[],
        prospective_groups=[],
    )
    compile_input = {
        "schema": "video-paper-wiki.compile-input.v1",
        "operation_id": operation_id,
        "papers": [{"record": paper_record, "claims": compiler_claims, "events": events}],
        "code": [],
        "concepts": concept_items,
    }
    return {
        "state": "paper_records_prepared",
        "paper_id": paper_id,
        "source_id": source_id,
        "pdf_sha256": digest,
        "paper_record": paper_record,
        "claims": compiler_claims,
        "events": events,
        "concept_items": concept_items,
        "compile_input": compile_input,
        "pages_included": False,
        "page_publication_blocked": (
            "Existing canonical compiler requires one to three accepted or contested "
            "core conclusion claims before paper/concept pages can be published."
        ),
        "publication_request": staged,
        "request_path": staged["request_path"],
        "request_sha256": staged["request_sha256"],
        "operation_id": operation_id,
        "operation_type": "ingest",
        "next_action": "awaiting_operator_apply",
        "remaining_operator_steps": _paper_operator_steps(),
        "agent_may_run_vpwiki_admin": False,
        "receipt_backed": True,
        "published": False,
    }


def bridge_publication(
    *,
    intake: object,
    capture_bind: Mapping[str, Any] | None,
    captured_pdf: Path | str,
    document_json: Path | str,
    parser_config: Path | str,
    model_manifest: Path | str,
    run_manifest: Path | str,
    legacy_draft: object,
    source_id: str,
    vault_root: Path | str,
    package_batch_id: object,
    package_operation_id: str,
    paper_batch_id: object,
    paper_operation_id: str,
    created_at: str = "2026-09-01T00:00:00Z",
) -> dict[str, Any]:
    """Package staged extraction then prepare paper/concept publication records."""
    if capture_bind is not None and capture_bind.get("result", {}).get("status") != "complete":
        _fail(SOURCE_AUTHORITY_INVALID, "capture operation result is not complete")
    packaged = package_extraction_run(
        captured_pdf=captured_pdf,
        document_json=document_json,
        parser_config=parser_config,
        model_manifest=model_manifest,
        run_manifest=run_manifest,
        vault_root=vault_root,
        batch_id=package_batch_id,
        operation_id=package_operation_id,
    )
    paper = prepare_paper_concept_publication(
        intake=intake,
        legacy_draft=legacy_draft,
        source_id=source_id,
        artifact_set=packaged["artifact_set"],
        vault_root=vault_root,
        batch_id=paper_batch_id,
        operation_id=paper_operation_id,
        created_at=created_at,
    )
    return {
        "state": "publication_bridge_prepared",
        "capture_bind": None if capture_bind is None else dict(capture_bind),
        "package": packaged,
        "paper": paper,
        "next_action": "awaiting_operator_apply",
        "remaining_operator_steps": paper["remaining_operator_steps"],
        "agent_may_run_vpwiki_admin": False,
        "published": False,
    }
