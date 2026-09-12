"""Read-only probes for the draft SOURCE-SEMANTICS registration helpers.

This probe imports the draft from the isolated parallel checkout, constructs an
in-memory genesis -> ingest receipt chain, and records malformed-byte behavior.
It does not read or mutate a Vault and does not modify production source.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


CHECKOUT = Path(__file__).resolve().parents[6] / ".work/parallel/source-semantics-v1/terminal-1/source"
sys.path.insert(0, str(CHECKOUT / "src"))

from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_registration import (
    LEDGER,
    historical_source_ledger,
    receipt_chain,
    registration_proof,
)
from video_paper_wiki.source_semantics_contracts import sha, source_id


def _exc(callable_, *args, **kwargs):
    try:
        value = callable_(*args, **kwargs)
    except BaseException as exc:  # record exact lower-level behavior for review
        return {
            "status": "error",
            "exception": type(exc).__name__,
            "code": getattr(exc, "code", None),
            "details": getattr(exc, "details", None),
        }
    return {"status": "ok", "value": value}


def _receipt(*, sequence, operation_id, operation_type, previous, writes, claimed_inputs):
    value = {
        "schema": "video-paper-wiki.operation-receipt.v1",
        "sequence": sequence,
        "previous": previous,
        "operation_id": operation_id,
        "operation_type": operation_type,
        "writes": writes,
        "claimed_inputs": claimed_inputs,
        "intent_sha256": "0" * 64,
    }
    value["intent_sha256"] = receipt_intent_sha256(value)
    return canonicalize(value)


def main() -> dict:
    payload = b"# deterministic registration probe\n"
    raw_hash = hashlib.sha256(payload).hexdigest()
    raw = {"path": f".raw/captured/{raw_hash}.md", "sha256": raw_hash, "size_bytes": len(payload)}
    sid = source_id(raw)
    empty_claim = canonicalize({"schema": "claude-obsidian.claim-ledger.v1", "generated_at": "2026-09-09T00:00:00Z", "claims": {}})
    empty_source = canonicalize({"schema": "claude-obsidian.source-ledger.v1", "generated_at": "2026-09-09T00:00:00Z", "sources": {}})
    ledger = canonicalize({
        "schema": "claude-obsidian.source-ledger.v1",
        "generated_at": "2026-09-09T00:00:00Z",
        "sources": {
            sid: {
                "origin": {"kind": "file", "locator": raw["path"]},
                "content_kind": "document",
                "title": "Registration probe",
                "authority": "primary",
                "content_sha256": raw_hash,
                "ingested_at": "2026-09-09",
                "retrieved_at": None,
                "refresh_due": "2099-01-01",
                "review_status": "unreviewed",
                "independence_key": None,
                "pages": [],
                "supersedes": None,
            }
        },
    })
    first_path = "wiki/meta/operations/000000000001-genesis.json"
    first_bytes = _receipt(
        sequence=1,
        operation_id="genesis",
        operation_type="generic",
        previous=None,
        writes=[
            {"path": LEDGER, "mode": "create", "before_sha256": None, "after_sha256": sha(empty_source)},
            {"path": "wiki/meta/ledgers/claim-ledger.json", "mode": "create", "before_sha256": None, "after_sha256": sha(empty_claim)},
        ],
        claimed_inputs=[],
    )
    second_path = "wiki/meta/operations/000000000002-register.json"
    second_bytes = _receipt(
        sequence=2,
        operation_id="register",
        operation_type="ingest",
        previous={"path": first_path, "sha256": sha(first_bytes)},
        writes=[{"path": LEDGER, "mode": "replace", "before_sha256": sha(empty_source), "after_sha256": sha(ledger)}],
        claimed_inputs=[{"path": raw["path"], "mode": "read", "sha256": raw_hash}],
    )
    head = canonicalize({
        "schema": "video-paper-wiki.operation-head.v1",
        "sequence": 2,
        "receipt_path": second_path,
        "receipt_sha256": sha(second_bytes),
    })
    receipts = {first_path: first_bytes, second_path: second_bytes}
    result = {
        "checkout": str(CHECKOUT),
        "malformed_historical_json": _exc(historical_source_ledger, b"xxx"),
        "parser_depth_over_secure_bound": _exc(historical_source_ledger, (b"[" * 65) + b"0" + (b"]" * 65)),
        "malformed_head_json": _exc(receipt_chain, b"xxx", {}),
        "malformed_receipt_map": _exc(receipt_chain, head, {"bad": b"{}"}),
        "historical_optional_fields_absent": _exc(
            historical_source_ledger,
            canonicalize({
                "schema": "claude-obsidian.source-ledger.v1",
                "generated_at": "2026-09-09T00:00:00Z",
                "sources": {"src-probe": {"origin": {"kind": "manual", "locator": "fixture"},
                                                "content_kind": "document", "title": "Probe",
                                                "authority": "primary", "review_status": "unreviewed", "pages": []}},
            }),
        ),
        "valid_receipt_chain": _exc(receipt_chain, head, receipts),
        "valid_registration_proof": _exc(
            registration_proof, raw, sid, head_bytes=head, receipt_bytes=receipts, ledger_bytes=ledger
        ),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True, indent=2))
