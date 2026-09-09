"""Prepare and inspect complete source publication; never apply a transaction."""
from __future__ import annotations

import copy
from contextlib import ExitStack, contextmanager
from functools import wraps

from video_paper_wiki.captured_snapshot import capture_snapshot
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source import _capture_proof, validate_payload
from video_paper_wiki.markdown_source_io import RetainedDirectory
from video_paper_wiki.publication import _assemble_publication_transaction
from video_paper_wiki.receipt_audit import HEAD, _Snapshot, audit_integrity
from video_paper_wiki.source_publication_contracts import (
    ASSESSMENT_HEADS, AUTHORITY, DISPLAY_HEADS, IMMUTABLE, MAX_FILE, MAX_JSON, MAX_TOTAL,
    PROPOSAL, REQUEST, SOURCE_LEDGER, invalid, kind_for_path, operation_name,
    parse_json, payload_map, validate, validate_registration,
)
from video_paper_wiki.source_publication_io import checked_path, prepared_path, proposal_tree, staged_tree
from video_paper_wiki.source_semantics_contracts import fail, sha
from video_paper_wiki.source_state import (
    collect_source_state, inventory_digest, preserve_history, snapshot_material,
    validate_payload_documents,
)
from video_paper_wiki.staging import resolve_checkout_root, validate_batch_id
from video_paper_wiki.transaction_staging import MAX_BUNDLE_BYTES, encode_transaction_inspect_bundle


def _boundary(function):
    @wraps(function)
    def call(**kwargs):
        try:
            return function(**kwargs)
        except ContractError as exc:
            if "instance_pointer" in exc.details:
                raise
            raise ContractError(exc.code, exc.message, {"instance_pointer": "", **exc.details}, exit_code=exc.exit_code) from exc
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            invalid("publication input or filesystem operation is invalid: " + type(exc).__name__)
    return call


@contextmanager
def _directory(path):
    held = RetainedDirectory(checked_path(path))
    try:
        yield held.path
    finally:
        try:
            held.verify()
        finally:
            held.close()


@contextmanager
def _vault(vault_root, registration):
    with _directory(vault_root) as vault:
        snapshot = _Snapshot(vault)
        try:
            with ExitStack() as stack:
                captured = None
                if registration is not None:
                    digest = registration["authority"]["request"]["plan"]["observation"]["markdown"]["sha256"]
                    captured = stack.enter_context(capture_snapshot(vault, digest))
                yield vault, snapshot, captured
        finally:
            try:
                snapshot.verify()
            finally:
                snapshot.close()


def _registration_material(current, audit, registration, captured, *, batch, operation):
    authority, result = registration["authority"], registration["capture_result"]
    observation = authority["request"]["plan"]["observation"]
    target, sid = authority["stored_path"], authority["source_id"]
    if (batch == authority["request"]["plan"]["batch_id"]
            or operation in {authority["requested_operation_id"], result["transaction"]["operation_id"]}):
        invalid("source registration must have a distinct batch and operation", "/registration")
    if captured is None or captured.sibling is None or captured.sibling["path"] != target:
        invalid("registration has no exact retained raw capture", "/registration")
    validate_payload(captured.payload, observation)
    if current["bytes"].get(target) != captured.payload:
        invalid("capture and audited raw bytes differ", "/registration")
    proof = _capture_proof(authority, result, mode=captured.sibling["mode"])
    if target in audit["ever_claimed_raw"]:
        fail("SOURCE_HISTORY_CONFLICT", "raw source already has a receipt claim", "/registration", exit_code=75)
    sources = current["source_ledger"]["sources"]
    if any(existing_id == sid or row["origin"]["locator"] == target or row.get("content_sha256") == observation["markdown"]["sha256"]
           for existing_id, row in sources.items()):
        fail("SOURCE_HISTORY_CONFLICT", "source ID, path or digest is already registered", "/registration", exit_code=75)
    updated = copy.deepcopy(current["source_ledger"])
    updated["generated_at"] = registration["ingested_at"]
    updated["sources"][sid] = {
        "origin": {"kind": "file", "locator": target}, "content_kind": "document",
        "title": observation["title"], "authority": "primary", "content_sha256": observation["markdown"]["sha256"],
        "ingested_at": registration["ingested_at"][:10], "retrieved_at": None, "refresh_due": "2099-01-01",
        "review_status": "unreviewed", "independence_key": None, "pages": [], "supersedes": None}
    ledger_bytes = canonicalize(updated)
    path = ".raw/derived/source-ledgers/" + sha(ledger_bytes) + ".json"
    old = current["bytes"][SOURCE_LEDGER]
    expected = {SOURCE_LEDGER: ledger_bytes, path: ledger_bytes,
                ".raw/derived/source-ledgers/" + sha(old) + ".json": old}
    pending = {"ledger_bytes": ledger_bytes, "snapshot_path": path,
               "capture_proof": proof, "source_id": sid, "raw_bytes": captured.payload}
    return expected, pending


def _raw_history(current, writes, *, registration=False):
    for path, raw in writes.items():
        if path in current["bytes"] and kind_for_path(path) in IMMUTABLE and raw != current["bytes"][path]:
            fail("SOURCE_HISTORY_CONFLICT", "immutable stored history cannot be replaced", path, exit_code=75)
    for path, record in current["documents"]["paper"].items():
        if path not in writes:
            continue
        target = parse_json(writes[path], maximum=MAX_FILE)
        if (target["paper_id"] != record["paper_id"] or target["aliases"] != record["aliases"]
                or record["schema"].endswith(".v2") and target["schema"] != record["schema"]):
            fail("SOURCE_HISTORY_CONFLICT", "paper identity, aliases or schema history changed", path, exit_code=75)
        refs = {ref["claim_id"]: ref for ref in target["section_claim_refs"]}
        for old in record["section_claim_refs"]:
            new = refs.get(old["claim_id"])
            if new is None or any(new[k] != v for k, v in old.items() if k != "lifecycle") or (old["lifecycle"] == "retired" and new["lifecycle"] != "retired"):
                fail("SOURCE_HISTORY_CONFLICT", "existing claim reference was removed or rebound", path, exit_code=75)
    from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
    if CLAIM_LEDGER in writes:
        rows = parse_json(writes[CLAIM_LEDGER], maximum=MAX_FILE)["claims"]
        for cid, row in current["claim_ledger"]["claims"].items():
            if cid not in rows or rows[cid]["text"] != row["text"]:
                fail("SOURCE_HISTORY_CONFLICT", "existing claim text or identity changed", CLAIM_LEDGER, exit_code=75)
    if SOURCE_LEDGER in writes and not registration:
        rows = parse_json(writes[SOURCE_LEDGER], maximum=MAX_FILE)["sources"]
        previous = current["source_ledger"]["sources"]
        if set(rows) != set(previous):
            fail("SOURCE_HISTORY_CONFLICT", "knowledge cannot add or remove source identities", SOURCE_LEDGER, exit_code=75)
        for sid, row in previous.items():
            for field in ("origin", "content_kind", "content_sha256", "ingested_at"):
                if (field in row) != (field in rows[sid]) or row.get(field) != rows[sid].get(field):
                    fail("SOURCE_HISTORY_CONFLICT", "registered source identity fields changed", SOURCE_LEDGER, exit_code=75)


def _mirrors(state, *, knowledge):
    if knowledge and (ASSESSMENT_HEADS not in state["bytes"] or DISPLAY_HEADS not in state["bytes"]):
        invalid("knowledge state requires both explicit derived-head registries", "/heads")
    if state["structural_only"]:
        return
    actual = {p: raw for p, raw in state["bytes"].items() if p.startswith(("wiki/papers/", "wiki/code/", "wiki/concepts/"))}
    if actual != state["pages"]:
        invalid("complete generated page set or bytes differ from the compiler", "/compiled_pages")
    if state["profile"] == "source-v1":
        docs = state["documents"]
        if (docs["assessment_heads"].get(ASSESSMENT_HEADS) != state["assessment_heads"]
                or docs["display_heads"].get(DISPLAY_HEADS) != state["display_heads"]):
            invalid("derived heads differ from the complete stored history", "/heads")


def _prospective(snapshot, audit, current, payloads, registration, captured, *, batch, operation, preparing):
    writes = dict(payloads)
    pending = None
    expected = None
    if registration is not None:
        expected, pending = _registration_material(current, audit, registration, captured, batch=batch, operation=operation)
        for path, raw in writes.items():
            if expected.get(path) != raw:
                invalid("registration payloads differ from the exact recomputed ledger/snapshots", path)
        if SOURCE_LEDGER not in writes:
            invalid("registration must explicitly supply its proposed source ledger", "/payloads")
        if preparing:
            writes.update(expected)
    elif SOURCE_LEDGER in writes and writes[SOURCE_LEDGER] != current["bytes"][SOURCE_LEDGER]:
        old = current["bytes"][SOURCE_LEDGER]
        path = ".raw/derived/source-ledgers/" + sha(old) + ".json"
        if path in writes and writes[path] != old:
            fail("SOURCE_HISTORY_CONFLICT", "old source-ledger snapshot bytes differ", path, exit_code=75)
        if preparing:
            writes[path] = old
    _raw_history(current, writes, registration=registration is not None)
    writes = payload_map({p: raw for p, raw in writes.items() if current["bytes"].get(p) != raw})
    if not preparing and writes != payloads:
        invalid("durable request includes ineffective duplicate writes", "/payloads")
    if expected is not None:
        effective = {p: raw for p, raw in expected.items() if current["bytes"].get(p) != raw}
        if writes != effective:
            invalid("durable registration is missing its exact snapshot set", "/payloads")
    prospective = collect_source_state(snapshot, audit, overlay=writes, require_rendered=False,
        pending_registration=pending, allow_legacy_structural=registration is not None)
    preserve_history(current, prospective, writes, registration=registration is not None)
    _mirrors(prospective, knowledge=registration is None)
    return writes, prospective


def _transport_limits(current, writes, audit, operation, registration):
    """Check the exact compact bundle size before staging any source request.

Only bundle descriptors are constructed here. Receipt/head hashes have fixed
width, so placeholders give the exact encoded size without a second authority.
"""
    sequence = audit["head"]["sequence"] + 1
    if sequence > 8192:
        fail("TRANSACTION_LIMIT_EXCEEDED", "publication would exceed the complete receipt bound", "/basis")
    receipt_path = f"wiki/meta/operations/{sequence:012d}-{operation}.json"
    current_bytes = current["bytes"]
    slots = [{"path": p, "mode": "replace" if p in current_bytes else "create", "sha256": sha(raw)}
             for p, raw in writes.items()]
    expected = {p: sha(current_bytes[p]) if p in current_bytes else None for p in writes}
    reads = {p: sha(raw) for p, raw in current_bytes.items() if p not in writes and p not in {HEAD, receipt_path}}
    claims = [] if registration is None else [{"path": registration["authority"]["stored_path"], "mode": "read",
        "sha256": registration["authority"]["request"]["plan"]["observation"]["markdown"]["sha256"]}]
    receipt = {"schema": "video-paper-wiki.operation-receipt.v1", "sequence": sequence,
        "previous": {"path": audit["head"]["receipt_path"], "sha256": audit["head"]["receipt_sha256"]},
        "operation_id": operation, "operation_type": "ingest", "intent_sha256": "0" * 64,
        "writes": [{"path": x["path"], "mode": x["mode"], "before_sha256": expected[x["path"]], "after_sha256": x["sha256"]} for x in slots],
        "claimed_inputs": claims}
    receipt_size = len(canonicalize(receipt))
    head_size = len(canonicalize({"schema": "video-paper-wiki.operation-head.v1", "sequence": sequence,
                                 "receipt_path": receipt_path, "receipt_sha256": "0" * 64}))
    if (sum(map(len, writes.values())) + receipt_size + head_size > MAX_TOTAL
            or sum(len(current_bytes.get(p, b"")) for p in writes) + len(current_bytes[HEAD]) > MAX_TOTAL):
        fail("TRANSACTION_LIMIT_EXCEEDED", "transaction bytes including receipt/head exceed the limit", "/payloads")
    slots += [{"path": receipt_path, "mode": "create", "sha256": "0" * 64}, {"path": HEAD, "mode": "replace", "sha256": "0" * 64}]
    expected.update({receipt_path: None, HEAD: sha(current_bytes[HEAD])})
    bundle = encode_transaction_inspect_bundle({"operation_id": operation, "operation_type": "ingest",
        "writes": slots, "expected_hashes": expected, "read_preconditions": reads})
    if len(bundle) > MAX_BUNDLE_BYTES:
        fail("TRANSACTION_LIMIT_EXCEEDED", "complete transaction bundle exceeds the limit", "/payloads")


def _envelope(batch, operation, current, prospective, writes, *, path=None, checksum=None):
    changed = bool(writes)
    return {"state": "source_publication_prepared" if changed else "no_change",
            "kind": "knowledge", "batch_id": batch, "operation_id": operation,
            "basis": current["basis"], "prospective_inventory_sha256": inventory_digest(prospective["inventory"]),
            "request_path": path, "request_sha256": checksum, "changed_paths": list(writes),
            "published": False, "applied": False,
            "next_action": "inspect_source_publication" if changed else "no_change"}


@_boundary
def prepare_source_publication(*, batch_id, operation_id, vault_root, payloads, registration=None):
    batch, operation = validate_batch_id(batch_id), operation_name(operation_id)
    payloads = validate_payload_documents(payloads)
    registration = None if registration is None else validate_registration(registration)
    with _vault(vault_root, registration) as (vault, snapshot, captured):
        audit = audit_integrity(vault, _snapshot=snapshot)
        current = collect_source_state(snapshot, audit, allow_legacy_structural=True)
        writes, prospective = _prospective(snapshot, audit, current, payloads, registration, captured,
            batch=batch, operation=operation, preparing=True)
        if not writes:
            return _envelope(batch, operation, current, prospective, writes)
        _transport_limits(current, writes, audit, operation, registration)
        kind = "knowledge" if registration is None else "registration"
        request = validate({"schema": REQUEST, "batch_id": batch, "operation_id": operation, "kind": kind,
            "basis": current["basis"], "prospective_inventory_sha256": inventory_digest(prospective["inventory"]),
            "payloads": [{"path": p, "content_file": "source-publication/content/" + sha(raw),
                          "sha256": sha(raw), "size_bytes": len(raw)} for p, raw in writes.items()],
            "registration": registration}, REQUEST)
        raw = canonicalize(request)
        if len(raw) > MAX_JSON:
            invalid("canonical request exceeds its byte limit")
        with staged_tree(batch, create=True) as tree:
            tree.install(raw, {sha(value): value for value in writes.values()})
            snapshot.verify()
            result = _envelope(batch, operation, current, prospective, writes,
                               path=(tree.path / "request.json").as_posix(), checksum=sha(raw))
            result["kind"] = kind
            return result


@_boundary
def prepare_source_publication_source(*, proposal_path, batch_id, operation_id, vault_root):
    batch, operation = validate_batch_id(batch_id), operation_name(operation_id)
    with proposal_tree(proposal_path) as tree:
        doc = parse_json(tree.request_bytes(), schema=PROPOSAL, exact=True)
        contents = tree.bind({item["content_file"][8:]: None for item in doc["payloads"]})
        return prepare_source_publication(batch_id=batch, operation_id=operation, vault_root=vault_root,
            payloads={item["path"]: contents[item["content_file"][8:]] for item in doc["payloads"]},
            registration=doc["registration"])


@_boundary
def inspect_source_publication(*, prepared, operation_id, vault_root, upstream_root):
    operation = operation_name(operation_id)
    path, batch = prepared_path(prepared)
    with staged_tree(batch, create=False) as tree:
        request_raw = tree.request_bytes()
        request = parse_json(request_raw, schema=REQUEST, exact=True)
        if request["batch_id"] != batch or request["operation_id"] != operation or path != tree.path / "request.json":
            invalid("prepared identity differs from the requested operation", "/operation_id")
        contents = tree.bind({x["sha256"]: x["size_bytes"] for x in request["payloads"]})
        payloads = validate_payload_documents({x["path"]: contents[x["sha256"]] for x in request["payloads"]})
        registration = request["registration"]
        with _directory(upstream_root) as upstream:
            with _vault(vault_root, registration) as (vault, snapshot, captured):
                audit = audit_integrity(vault, _snapshot=snapshot)
                inventory, data = snapshot_material(snapshot)
                basis = {"operation_head_sha256": sha(data[HEAD]), "inventory_sha256": inventory_digest(inventory)}
                if basis != request["basis"]:
                    fail("SOURCE_PUBLICATION_STALE", "current audited publication basis changed", "/basis", exit_code=75)
                current = collect_source_state(snapshot, audit, allow_legacy_structural=True)
                writes, prospective = _prospective(snapshot, audit, current, payloads, registration, captured,
                    batch=batch, operation=operation, preparing=False)
                if inventory_digest(prospective["inventory"]) != request["prospective_inventory_sha256"]:
                    invalid("request prospective inventory digest differs", "/prospective_inventory_sha256")
                _transport_limits(current, writes, audit, operation, registration)
                receipt_path = f"wiki/meta/operations/{audit['head']['sequence'] + 1:012d}-{operation}.json"
                read_bytes = {p: raw for p, raw in data.items() if p not in writes and p not in {HEAD, receipt_path}}
                children = _assemble_publication_transaction(operation_id=operation, operation_type="ingest",
                    batch=batch, payload_bytes=dict(writes), claimed_input_paths=[] if registration is None else [registration["authority"]["stored_path"]],
                    read_bytes=read_bytes, audit=audit, snapshot=snapshot, session=tree.session,
                    upstream_root=upstream, checkout=resolve_checkout_root(), vault=vault)
                tx = children["transaction"]
                actual = {w["path"]: (w["sha256"], w["size_bytes"]) for w in tx["writes"] if w["role"] == "business"}
                if actual != {p: (sha(raw), len(raw)) for p, raw in writes.items()}:
                    invalid("shared transaction construction changed the requested business set")
                if tx["read_preconditions"] != {p: sha(raw) for p, raw in read_bytes.items()}:
                    invalid("shared transaction does not bind the complete current read set")
                result = validate({"schema": AUTHORITY, "request_sha256": sha(request_raw), "request": request,
                    "prospective_inventory_sha256": request["prospective_inventory_sha256"], **children}, AUTHORITY)
                snapshot.verify()
                tree.verify()
                return result


@_boundary
def audit_source_state(*, vault_root):
    with _vault(vault_root, None) as (vault, snapshot, _captured):
        audit = audit_integrity(vault, _snapshot=snapshot)
        state = collect_source_state(snapshot, audit)
        return {"state": "source_state_audited", "basis": state["basis"], "profile": state["profile"],
                "counts": state["counts"], "assessment_heads": state["assessment_heads"],
                "display_heads": state["display_heads"], "receipt_backed": True, "upstream_validated": False}


def run_source_publication_command(args):
    command = "source-publication." + args.source_publication_cmd
    try:
        if args.source_publication_cmd == "prepare":
            result = prepare_source_publication_source(proposal_path=args.proposal, batch_id=args.batch_id,
                operation_id=args.operation_id, vault_root=args.vault_root)
        elif args.source_publication_cmd == "inspect":
            result = inspect_source_publication(prepared=args.prepared, operation_id=args.operation_id,
                vault_root=args.vault_root, upstream_root=args.upstream_root)
        else:
            result = audit_source_state(vault_root=args.vault_root)
        return emit_success(command, result)
    except ContractError as exc:
        return emit_error(command, exc.code, exc.message, exc.details, exit_code=exc.exit_code)
