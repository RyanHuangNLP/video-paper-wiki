"""Catalog compatibility on a research-shaped vault, without the P3 backup product."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from tests.unit.test_domain_proposal import make_world
from video_paper_wiki.catalog_collector import collect_current_catalog_material
from video_paper_wiki.catalog_reporting import catalog_report
from video_paper_wiki.catalog_store import build_current_catalog, catalog_status, query_catalog
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import CURRENT_EXACT, CURRENT_PREFIXES, audit_integrity
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "vendor" / "claude-obsidian"
POLICY = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.retrieval-policy.v1.json"


def _private(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _managed(relative: str) -> bool:
    if relative in CURRENT_EXACT:
        return True
    return any(relative.startswith(prefix) and len(relative) > len(prefix) for prefix in CURRENT_PREFIXES)


def seal_receipt_vault(root: Path) -> str:
    _private(root)
    writes = []
    claims = []
    for file in sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink()):
        relative = file.relative_to(root).as_posix()
        if relative.startswith("wiki/meta/operations/") or relative == "wiki/meta/registries/operation-head.json":
            continue
        if relative.startswith(".vault-meta/"):
            continue
        data = file.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if relative.startswith(".raw/captured/"):
            claims.append({"path": relative, "mode": "read", "sha256": digest})
        if _managed(relative):
            writes.append({"path": relative, "mode": "create", "before_sha256": None, "after_sha256": digest})
    receipt = {
        "schema": "video-paper-wiki.operation-receipt.v1",
        "sequence": 1,
        "previous": None,
        "operation_id": "s6-genesis",
        "operation_type": "generic",
        "intent_sha256": "0" * 64,
        "writes": writes,
        "claimed_inputs": claims,
    }
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    raw = canonicalize(receipt)
    target = root / "wiki/meta/operations/000000000001-s6-genesis.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(0o600)
    head = {
        "schema": "video-paper-wiki.operation-head.v1",
        "sequence": 1,
        "receipt_path": "wiki/meta/operations/000000000001-s6-genesis.json",
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }
    head_path = root / "wiki/meta/registries/operation-head.json"
    head_path.parent.mkdir(parents=True, exist_ok=True)
    head_path.write_bytes(canonicalize(head))
    head_path.chmod(0o600)
    audit = audit_integrity(root)
    if audit["classification"] != "receipt_backed":
        raise RuntimeError(audit["classification"])
    return hashlib.sha256(raw).hexdigest()


def _source_ledger(vault: Path) -> None:
    claim = json.loads((vault / CLAIM_LEDGER).read_text(encoding="utf-8"))
    source_ids = sorted({item["source_id"] for row in claim["claims"].values() for item in row["evidence"]})
    if len(source_ids) != 1:
        raise RuntimeError("claim evidence does not share one source")
    source_id = source_ids[0]
    matched = None
    for path in (vault / "wiki/meta/records/source-versions").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("source_id") == source_id:
            matched = document
            break
    if matched is None:
        raise RuntimeError("claim source is not an association")
    raw = matched["raw"]
    document = {
        "schema": "claude-obsidian.source-ledger.v1",
        "generated_at": claim["generated_at"],
        "sources": {
            source_id: {
                "origin": {"kind": "file", "locator": raw["path"]},
                "content_kind": "document",
                "title": "Fixture source",
                "authority": "primary",
                "review_status": "unreviewed",
                "pages": [],
                "content_sha256": raw["sha256"],
                "ingested_at": "2026-09-08",
                "retrieved_at": None,
                "refresh_due": None,
                "independence_key": None,
                "supersedes": None,
            }
        },
    }
    path = vault / "wiki/meta/ledgers/source-ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize(document))
    os.chmod(path, 0o600)


def _claim_page(vault: Path) -> None:
    ledger = json.loads((vault / CLAIM_LEDGER).read_text(encoding="utf-8"))
    blocks = [
        "---",
        "title: Paper",
        "type: paper",
        "status: active",
        "created: 2026-09-08",
        "updated: 2026-09-08",
        "tags: [paper]",
        "---",
        "",
        "# Paper",
        "",
    ]
    for claim_id, row in sorted(ledger["claims"].items()):
        blocks.append(str(row["text"]))
        blocks.append("")
        anchor = (row.get("location") or {}).get("anchor")
        if isinstance(anchor, str) and anchor.startswith("^"):
            blocks.append(anchor)
            blocks.append("")
    path = vault / "wiki" / "papers" / "paper.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def test_research_catalog_rebuilds_without_dropping_source_bytes(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    vault = world["vault"]
    _source_ledger(vault)
    _claim_page(vault)
    heads = (vault / ASSESSMENT_HEADS).read_bytes()
    association = next((vault / "wiki/meta/records/source-versions").glob("*.json"))
    association_bytes = association.read_bytes()
    raw_path = json.loads(association_bytes)["raw"]["path"]
    raw_bytes = (vault / raw_path).read_bytes()
    meta = vault / ".vault-meta"
    meta.mkdir(mode=0o700)
    os.chmod(meta, 0o700)
    seal_receipt_vault(vault)
    built = build_current_catalog(vault_root=vault, upstream_root=UPSTREAM, retrieval_config=POLICY)
    config = tmp_path / "retrieval-config.json"
    config.write_bytes(canonicalize(built["retrieval_config"]))
    os.chmod(config, 0o600)
    assert (vault / ASSESSMENT_HEADS).read_bytes() == heads
    assert association.read_bytes() == association_bytes
    assert (vault / raw_path).read_bytes() == raw_bytes
    material = collect_current_catalog_material(
        vault_root=vault, upstream_root=UPSTREAM, retrieval_config=built["retrieval_config"]
    )
    bound = {item["path"] for item in material["builder_files"]}
    assert "wiki/meta/records/assessment-heads.json" in bound
    assert association.relative_to(vault).as_posix() in bound
    status = catalog_status(vault, UPSTREAM, config)
    assert status["state"] == "current"
    query = query_catalog(vault, UPSTREAM, config, "视频论文")
    assert query["catalog_generation_sha256"] == status["catalog_generation_sha256"]
    report = catalog_report(vault_root=vault, upstream_root=UPSTREAM, retrieval_config=config, report_kind="evidence-coverage")
    assert report["catalog_state"] == "current"
    assert report["rows"] == []
    ledger_path = vault / "wiki/meta/ledgers/source-ledger.json"
    original_ledger = ledger_path.read_bytes()
    changed = json.loads(original_ledger)
    changed["sources"][next(iter(changed["sources"]))]["title"] = "Fixture source changed"
    ledger_path.write_bytes(canonicalize(changed))
    seal_receipt_vault(vault)
    stale = catalog_status(vault, UPSTREAM, config)
    assert stale["state"] == "stale"
    ledger_path.write_bytes(original_ledger)
    seal_receipt_vault(vault)
    assert catalog_status(vault, UPSTREAM, config)["state"] == "current"
    (vault / ASSESSMENT_HEADS).write_bytes(b"{")
    os.chmod(vault / ASSESSMENT_HEADS, 0o600)
    seal_receipt_vault(vault)
    with pytest.raises(ContractError) as err:
        catalog_status(vault, UPSTREAM, config)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"
    assert (vault / ASSESSMENT_HEADS).is_file()
    assert stat.S_ISREG((vault / ASSESSMENT_HEADS).stat().st_mode)
