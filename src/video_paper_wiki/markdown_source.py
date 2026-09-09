"""Markdown capture and source registration; generated writes stay in .work."""
from __future__ import annotations

import copy
import re
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from video_paper_wiki.captured_snapshot import capture_snapshot
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import (
    AUTHORITY, PLAN, REQUEST, bind_approval, digest, fail, sha, validate,
)
from video_paper_wiki.markdown_source_io import (
    checked_path, fixed_batch, json_bytes, markdown_slots, retain_files, retain_directory_arguments,
)
from video_paper_wiki.operation_result import bind_operation_result, validate_operation_result_authority
from video_paper_wiki.publication import inspect_publication, stage_publication_request
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.staging import validate_batch_id
from video_paper_wiki.transaction_contracts import HEAD_PATH, transaction_declaration_hash, validate_transaction
from video_paper_wiki.transaction_staging import _stage_transaction_inspect_transport, encode_transaction_inspect_bundle
from video_paper_wiki.upstream_adapter import inspect_pinned_transaction, verify_pinned_source_id

SOURCE_LEDGER = "wiki/meta/ledgers/source-ledger.json"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def operation_name(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        fail("MARKDOWN_REQUEST_MISMATCH", "operation ID must be a bounded portable name")
    return value


def validate_payload(payload: bytes, observation: dict) -> None:
    if type(payload) is not bytes or {"sha256": sha(payload), "size_bytes": len(payload)} != observation["markdown"]:
        fail("MARKDOWN_REQUEST_MISMATCH", "Markdown payload does not bind observation")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        fail("MARKDOWN_SOURCE_INVALID", "Markdown must be UTF-8")
    if "\0" in text:
        fail("MARKDOWN_SOURCE_INVALID", "Markdown cannot contain NUL")
    matches = list(re.finditer(r'<a id="page-(\d+)"></a>', text))
    if len(matches) != len(observation["pages"]):
        fail("MARKDOWN_SOURCE_INVALID", "Markdown page anchors differ")
    usable = False
    for index, (match, page) in enumerate(zip(matches, observation["pages"], strict=True)):
        heading = f'\n\n## PDF 第 {page["page"]} 页\n\n'
        start = match.end() + len(heading)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        while end > start and text[end - 1] == "\n":
            end -= 1
        if (match.group(1) != str(page["page"]) or not text.startswith(heading, match.end())
                or page["text_start"] != start or page["text_end"] != end
                or page["text_sha256"] != sha(text[start:end].encode("utf-8"))):
            fail("MARKDOWN_SOURCE_INVALID", "Markdown page anchors, spans or hashes differ")
        usable |= bool(text[start:end].strip())
    if not usable:
        fail("MARKDOWN_SOURCE_INVALID", "Markdown contains no usable page text")


def stage_markdown_plan(plan: object, *, slots) -> dict:
    value = validate(plan, PLAN)
    if slots.session.batch != value["batch_id"]:
        fail("MARKDOWN_PLAN_INVALID", "plan batch differs from retained staging")
    slots.payload_slot(value["observation"]["markdown"]["sha256"])
    raw = canonicalize(value)
    reused = slots.install("plan.json", raw)
    return {"state": "awaiting_external_approval", "plan_path": str(slots.path / "plan.json"),
            "plan_sha256": sha(raw), "observation": value["observation"], "reused": reused}


def prepare_markdown_capture(plan: object, approval_ref: object, payload: bytes, *, slots) -> dict:
    value = validate(plan, PLAN)
    if canonicalize(value) != slots.read("plan.json") or value["batch_id"] != slots.session.batch:
        fail("MARKDOWN_PLAN_INVALID", "plan differs from retained fixed slot")
    approval = bind_approval(value, approval_ref)
    validate_payload(payload, value["observation"])
    name = slots.payload_slot(sha(payload))
    request = validate({"schema": REQUEST, "plan": value, "plan_sha256": digest(value),
                        "approval_ref": approval, "approval_ref_sha256": digest(approval),
                        "payload_file": "markdown-source/" + name}, REQUEST)
    raw = canonicalize(request)
    # Preflight both existing slots before any write; retries preserve partial work.
    for slot, data in ((name, payload), ("request.json", raw)):
        if slots.files[slot].data not in (None, data):
            fail("MARKDOWN_CAPTURE_CONFLICT", "prepared slot already contains competing bytes")
    slots.install(name, payload)
    reused = slots.install("request.json", raw)
    return {"state": "awaiting_capture_inspect", "request_path": str(slots.path / "request.json"),
            "request_sha256": sha(raw), "request": request, "reused": reused}


def _proposal(operation_id: str, payload: bytes) -> dict:
    content_sha = sha(payload)
    target = f".raw/captured/{content_sha}.md"
    material = {"operation_id": operation_id, "operation_type": "capture",
                "writes": [{"path": target, "mode": "create", "sha256": content_sha}],
                "expected_hashes": {target: None}, "read_preconditions": {}}
    bundle = encode_transaction_inspect_bundle(material)
    value = {"schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal",
             "operation_id": operation_id, "operation_type": "capture",
             "writes": [{"path": target, "role": "business", "mode": "create", "sha256": content_sha,
                         "size_bytes": len(payload), "original_size_bytes": 0, "original_mode": None}],
             "expected_hashes": {target: None}, "read_preconditions": {}, "claimed_inputs": [],
             "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
             "receipt": None, "head": None, "input_bundle_sha256": sha(bundle),
             "declaration_sha256": "0" * 64, "inspection": None, "runtime_result": None}
    value["declaration_sha256"] = transaction_declaration_hash(value)
    return validate_transaction(value)


@retain_directory_arguments("vault_root", "upstream_root")
def inspect_markdown_capture(*, prepared: Path | str, operation_id: object,
                             upstream_root: Path | str, vault_root: Path | str) -> dict:
    operation = operation_name(operation_id)
    _path, batch = fixed_batch(prepared, "request.json")
    vault = checked_path(vault_root)
    upstream_root = checked_path(upstream_root)
    with markdown_slots(batch, create=False) as slots:
        # All original slots are retained before parsing; plan errors precede request errors.
        plan_raw = slots.read("plan.json")
        plan = validate(json_bytes(plan_raw, code="MARKDOWN_PLAN_INVALID"), PLAN)
        if canonicalize(plan) != plan_raw or plan["batch_id"] != batch:
            fail("MARKDOWN_PLAN_INVALID", "plan is not canonical or batch-bound")
        payload_name = slots.payload_slot(plan["observation"]["markdown"]["sha256"])
        request_raw = slots.read("request.json")
        request = validate(json_bytes(request_raw, code="MARKDOWN_REQUEST_MISMATCH"), REQUEST)
        if canonicalize(request) != request_raw or request["plan"] != plan:
            fail("MARKDOWN_REQUEST_MISMATCH", "request differs from its staged plan")
        payload = slots.read(payload_name)
        validate_payload(payload, plan["observation"])
        content_sha = sha(payload)
        target = f".raw/captured/{content_sha}.md"
        with ExitStack() as retained, capture_snapshot(vault, content_sha) as snapshot:
            if snapshot.sibling is not None:
                if snapshot.sibling["path"] != target or snapshot.payload != payload:
                    fail("MARKDOWN_CAPTURE_CONFLICT", "captured sibling is not the exact Markdown slot")
                raw = retained.enter_context(retain_files([(vault / target, 8388608, True)]))[0]
                if raw.data != snapshot.payload:
                    fail("WORK_PATH_UNSAFE", "captured Markdown changed while retaining its file")
                staging = upstream = None
                disposition = "reuse"
            else:
                proposal = _proposal(operation, payload)
                staging = _stage_transaction_inspect_transport(
                    proposal, write_bytes={target: payload}, original_bytes={target: None}, read_bytes={},
                    batch_id=batch, session=slots.session)
                slots.verify()
                upstream = inspect_pinned_transaction(
                    proposal, upstream_root=upstream_root, work_root=slots.session.work_root,
                    vault_root=vault, bundle_path=slots.session.batch_path / "transaction-inspect/bundle.json")
                disposition = "create"
            source_id = verify_pinned_source_id(target, content_sha, upstream_root=upstream_root)
            authority = validate({"schema": AUTHORITY, "requested_operation_id": operation,
                                  "request": request, "request_sha256": sha(request_raw),
                                  "disposition": disposition, "stored_path": target, "source_id": source_id,
                                  "transaction_staging": staging, "upstream_authority": upstream}, AUTHORITY)
            snapshot.verify()
            slots.verify()
            return {"state": "awaiting_operator_capture" if disposition == "create" else "capture_reused",
                    "authority": authority}


def bind_markdown_capture_result(authority: object, result: object, *, before: object, after: object) -> dict:
    value = validate(authority, AUTHORITY)
    if value["disposition"] != "create":
        fail("MARKDOWN_AUTHORITY_MISMATCH", "reuse has no transaction to bind")
    return bind_operation_result(value["upstream_authority"]["transaction"], result,
                                 vault_before=before, vault_after=after)


def _capture_proof(authority: dict, result: object, *, mode: int) -> dict:
    if result is None:
        fail("MARKDOWN_AUTHORITY_MISMATCH", "first admission requires an external generic capture result")
    proof = validate_operation_result_authority(result)
    tx = proof["transaction"]
    payload = authority["request"]["plan"]["observation"]["markdown"]
    target = authority["stored_path"]
    business = [{"path": target, "role": "business", "mode": "create", "sha256": payload["sha256"],
                 "size_bytes": payload["size_bytes"], "original_size_bytes": 0, "original_mode": None}]
    if (tx["operation_type"] != "capture" or tx["writes"] != business
            or tx["expected_hashes"] != {target: None} or tx["read_preconditions"] or tx["claimed_inputs"]
            or proof["vault_before"] != {target: None}
            or proof["vault_after"] != {target: {"sha256": payload["sha256"], "mode": mode}}):
        fail("MARKDOWN_AUTHORITY_MISMATCH", "capture result does not bind retained raw bytes and mode")
    if authority["disposition"] == "create":
        detached = copy.deepcopy(tx)
        detached["runtime_result"] = None
        if detached != authority["upstream_authority"]["transaction"]:
            fail("MARKDOWN_AUTHORITY_MISMATCH", "capture result belongs to a different inspected transaction")
    return proof


@retain_directory_arguments("vault_root", "upstream_root")
def admit_markdown_source(*, authority: object, batch_id: object, operation_id: object,
                          vault_root: Path | str, upstream_root: Path | str, ingested_at: object,
                          capture_result: object = None) -> dict:
    value = validate(authority, AUTHORITY)
    batch, operation = validate_batch_id(batch_id), operation_name(operation_id)
    plan = value["request"]["plan"]
    if batch == plan["batch_id"] or operation == value["requested_operation_id"]:
        fail("MARKDOWN_SOURCE_CONFLICT", "admission requires a distinct batch and operation")
    try:
        if type(ingested_at) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ingested_at) is None:
            raise ValueError
        datetime.strptime(ingested_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        fail("MARKDOWN_SOURCE_INVALID", "ingested_at must be an actual canonical UTC timestamp")
    vault, upstream = checked_path(vault_root), checked_path(upstream_root)
    observation = plan["observation"]
    payload = observation["markdown"]
    target, source_id = value["stored_path"], value["source_id"]
    verify_pinned_source_id(target, payload["sha256"], upstream_root=upstream, expected_source_id=source_id)
    snap = _Snapshot(vault)
    try:
        with capture_snapshot(vault, payload["sha256"]) as captured:
            if captured.sibling is None or captured.sibling["path"] != target:
                fail("MARKDOWN_CAPTURE_CONFLICT", "exact captured Markdown must exist before admission")
            validate_payload(captured.payload, observation)
            if snap.read_optional(HEAD_PATH) is None:
                fail("RECEIPT_BOOTSTRAP_REQUIRED", "an existing valid genesis receipt chain is required before admission")
            audit = audit_integrity(vault, _snapshot=snap)
            if audit["classification"] != "receipt_backed":
                fail("RECEIPT_BOOTSTRAP_REQUIRED", "genesis publication must precede source admission")
            with retain_files([(vault / SOURCE_LEDGER, 16777216, True),
                               (vault / target, 8388608, True)]) as held:
                ledger_raw = held[0].data
                if ledger_raw != snap.read(SOURCE_LEDGER) or held[1].data != captured.payload:
                    fail("MARKDOWN_SOURCE_CONFLICT", "retained source ledger or raw file differs")
                ledger = json_bytes(ledger_raw, code="MARKDOWN_SOURCE_CONFLICT")
                if type(ledger) is not dict or type(ledger.get("sources")) is not dict:
                    fail("MARKDOWN_SOURCE_CONFLICT", "source ledger is invalid")
                matching = False
                for existing_id, record in ledger["sources"].items():
                    origin = record.get("origin", {}) if type(record) is dict else {}
                    same_path = origin.get("locator") == target
                    same_hash = type(record) is dict and record.get("content_sha256") == payload["sha256"]
                    if existing_id == source_id or same_path or same_hash:
                        if (existing_id != source_id or not same_path or not same_hash
                                or origin.get("kind") != "file" or record.get("content_kind") != "document"):
                            fail("MARKDOWN_SOURCE_CONFLICT", "source ID, path or digest conflicts with existing registration")
                        matching = True
                claimed = target in audit["ever_claimed_raw"]
                if matching and claimed:
                    return {"state": "source_already_registered", "source_id": source_id, "stored_path": target,
                            "paper_id": observation["paper_id"], "published": True, "receipt_backed": True}
                if matching or claimed:
                    fail("MARKDOWN_SOURCE_CONFLICT", "source registration and raw receipt claim disagree")
                proof = _capture_proof(value, capture_result, mode=captured.sibling["mode"])
                if operation == proof["transaction"]["operation_id"]:
                    fail("MARKDOWN_SOURCE_CONFLICT", "admission cannot reuse capture operation ID")
                updated = copy.deepcopy(ledger)
                updated["generated_at"] = ingested_at
                updated["sources"][source_id] = {
                    "origin": {"kind": "file", "locator": target}, "content_kind": "document",
                    "title": observation["title"], "authority": "primary", "content_sha256": payload["sha256"],
                    "ingested_at": ingested_at[:10], "retrieved_at": None, "refresh_due": "2099-01-01",
                    "review_status": "unreviewed", "independence_key": None, "pages": [], "supersedes": None}
                staged = stage_publication_request(
                    batch_id=batch, operation_id=operation, operation_type="ingest",
                    payloads={SOURCE_LEDGER: canonicalize(updated)}, claimed_input_paths=[target],
                    additional_read_paths=[], prospective_groups=[])
                for item in held:
                    item.verify()
                snap.verify()
                inspected = inspect_publication(prepared=staged["request_path"], operation_id=operation,
                                                upstream_root=upstream, vault_root=vault)
                snap.verify()
                return {"state": "source_registration_prepared", "next_action": "awaiting_operator_publication",
                        "source_id": source_id, "stored_path": target, "paper_id": observation["paper_id"],
                        "batch_id": batch, "operation_id": operation, "publication_request": staged,
                        "publication_authority": inspected, "published": False, "receipt_backed": False}
    finally:
        try:
            snap.verify()
        finally:
            snap.close()
