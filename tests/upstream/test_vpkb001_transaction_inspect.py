from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.transaction_contracts import transaction_declaration_hash
from video_paper_wiki.upstream_adapter import (
    inspect_pinned_transaction,
    verify_pinned_source_id,
)

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "vendor/claude-obsidian"
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json"
VECTORS = ROOT / "tests/fixtures/upstream-authority/source-id-vectors.json"
HEAD = "wiki/meta/registries/operation-head.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_bytes(proposal: dict) -> bytes:
    value = {
        "schema": "claude-obsidian.transaction.v1",
        "operation_id": proposal["operation_id"],
        "operation_type": proposal["operation_type"],
        "writes": [{
            "path": write["path"], "mode": write["mode"],
            "content_file": "content/" + write["sha256"], "sha256": write["sha256"],
        } for write in proposal["writes"]],
        "expected_hashes": proposal["expected_hashes"],
        "read_preconditions": proposal["read_preconditions"],
        "address_requests": [],
        "source_manifest_updates": {},
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def seal(proposal: dict, supplied: dict[str, bytes]) -> tuple[dict, bytes]:
    raw = bundle_bytes(proposal)
    proposal["input_bundle_sha256"] = sha(raw)
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    assert {write["path"] for write in proposal["writes"]} == set(supplied)
    return proposal, raw


def capture() -> tuple[dict, dict[str, bytes], bytes]:
    data = b"%PDF-vpkb001\n"
    digest = sha(data)
    path = f".raw/captured/{digest}.pdf"
    proposal = {
        "schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal",
        "operation_id": "adapter-capture", "operation_type": "capture",
        "writes": [{"path": path, "role": "business", "mode": "create", "sha256": digest,
                    "size_bytes": len(data), "original_size_bytes": 0, "original_mode": None}],
        "expected_hashes": {path: None}, "read_preconditions": {}, "claimed_inputs": [],
        "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
        "receipt": None, "head": None, "input_bundle_sha256": "0" * 64,
        "declaration_sha256": "0" * 64, "inspection": None, "runtime_result": None,
    }
    proposal, raw = seal(proposal, {path: data})
    return proposal, {path: data}, raw


def generic() -> tuple[dict, dict[str, bytes], bytes]:
    authority = json.loads(VALID.read_text(encoding="utf-8"))
    proposal = copy.deepcopy(authority["transaction"])
    proposal["phase"] = "proposal"
    proposal["inspection"] = None
    supplied = {}
    for write in proposal["writes"]:
        supplied[write["path"]] = b"{}" if write["role"] == "business" else canonicalize(proposal[write["role"]])
    proposal, raw = seal(proposal, supplied)
    return proposal, supplied, raw


def ingest(vault: Path) -> tuple[dict, dict[str, bytes], bytes]:
    genesis = json.loads(VALID.read_text(encoding="utf-8"))["transaction"]
    prior_receipt = canonicalize(genesis["receipt"])
    prior_head = canonicalize(genesis["head"])
    prior_path = genesis["head"]["receipt_path"]
    for path, data in ((prior_path, prior_receipt), (HEAD, prior_head)):
        target = vault / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o600)
    business = "wiki/meta/records/adapter-ingest.json"
    payload = b'{"adapter":"ingest"}'
    operation = "adapter-ingest"
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1", "sequence": 2,
        "previous": {"path": prior_path, "sha256": sha(prior_receipt)},
        "operation_id": operation, "operation_type": "ingest",
        "writes": [{"path": business, "mode": "create", "before_sha256": None, "after_sha256": sha(payload)}],
        "claimed_inputs": [],
    }
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_path = f"wiki/meta/operations/000000000002-{operation}.json"
    receipt_data = canonicalize(receipt)
    head = {"schema": "video-paper-wiki.operation-head.v1", "sequence": 2,
            "receipt_path": receipt_path, "receipt_sha256": sha(receipt_data)}
    head_data = canonicalize(head)
    supplied = {business: payload, receipt_path: receipt_data, HEAD: head_data}
    writes = []
    for path, data in supplied.items():
        old = prior_head if path == HEAD else None
        writes.append({"path": path, "role": "head" if path == HEAD else "receipt" if path == receipt_path else "business",
                       "mode": "replace" if old is not None else "create", "sha256": sha(data), "size_bytes": len(data),
                       "original_size_bytes": len(old) if old is not None else 0, "original_mode": 0o600 if old is not None else None})
    proposal = {
        "schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal", "operation_id": operation,
        "operation_type": "ingest", "writes": writes,
        "expected_hashes": {business: None, receipt_path: None, HEAD: sha(prior_head)},
        "read_preconditions": {prior_path: sha(prior_receipt)}, "claimed_inputs": [],
        "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
        "receipt": receipt, "head": head, "input_bundle_sha256": "0" * 64,
        "declaration_sha256": "0" * 64, "inspection": None, "runtime_result": None,
    }
    proposal, raw = seal(proposal, supplied)
    return proposal, supplied, raw


def stage(tmp_path: Path, proposal: dict, supplied: dict[str, bytes], raw: bytes) -> tuple[Path, Path]:
    work = tmp_path / ".work"
    directory = work / "adapter-batch" / "transaction-inspect"
    content = directory / "content"
    content.mkdir(parents=True)
    (directory / "bundle.json").write_bytes(raw)
    for write in proposal["writes"]:
        target = content / write["sha256"]
        if not target.exists():
            target.write_bytes(supplied[write["path"]])
    return work, directory / "bundle.json"


@pytest.mark.parametrize("kind", ["capture", "generic", "ingest"])
def test_real_private_snapshot_public_inspect_is_read_only(tmp_path: Path, kind: str) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    proposal, supplied, raw = ingest(vault) if kind == "ingest" else globals()[kind]()
    work, bundle = stage(tmp_path, proposal, supplied, raw)
    before = {path.relative_to(vault).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
              for path in vault.rglob("*") if path.is_file()}
    result = inspect_pinned_transaction(proposal, upstream_root=UPSTREAM, work_root=work,
                                        vault_root=vault, bundle_path=bundle)
    after = {path.relative_to(vault).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
             for path in vault.rglob("*") if path.is_file()}
    assert before == after
    assert result["transaction"]["phase"] == "inspected"
    assert result["transaction"]["inspection"]["changed_paths"] == [write["path"] for write in proposal["writes"]]
    assert result["transport"]["bundle_sha256"] == proposal["input_bundle_sha256"]
    assert result["transport"]["content_files"] == [
        {"write_path": write["path"], "content_file": "content/" + write["sha256"],
         "sha256": write["sha256"], "size_bytes": write["size_bytes"]}
        for write in proposal["writes"]
    ]


def test_real_isolated_source_id_vectors_and_expected_mismatch(tmp_path: Path) -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]
    for vector in vectors:
        assert verify_pinned_source_id(vector["stored_path"], vector["source_identity"],
                                       upstream_root=UPSTREAM, expected_source_id=vector["source_id"]) == vector["source_id"]
    with pytest.raises(ContractError) as caught:
        verify_pinned_source_id(vectors[0]["stored_path"], vectors[0]["source_identity"],
                                upstream_root=UPSTREAM, expected_source_id="src-" + "0" * 20)
    assert getattr(caught.value, "code", None) == "UPSTREAM_SOURCE_ID_MISMATCH"
