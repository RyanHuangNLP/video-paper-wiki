"""Receipt-backed research sources for the P3 rootless restore drill.

Code evidence uses the production request, observe, config, and handoff
commands. Draft, review, and plan bytes go through ``stage_bytes`` at the
same relative paths those export commands write. The export commands also
require a blob store and a seed-catalog paper, which this drill does not
invent.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from video_paper_wiki.code_proof_public import config_code_proof, status_code_proof
from video_paper_wiki.commands.draft import DRAFT_FILENAME
from video_paper_wiki.commands.plan import PLAN_FILENAME
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import CURRENT_EXACT, CURRENT_PREFIXES, audit_integrity
from video_paper_wiki.staging import stage_bytes


def _private(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _managed(relative: str) -> bool:
    if relative in CURRENT_EXACT:
        return True
    return any(relative.startswith(prefix) and len(relative) > len(prefix) for prefix in CURRENT_PREFIXES)


def seal_receipt_vault(root: Path) -> str:
    """Seal one synthetic receipt over the current managed tree. Returns the receipt SHA-256."""
    _private(root)
    writes = []
    claims = []
    for file in sorted(path for path in root.rglob("*") if path.is_file()):
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
        "operation_id": "p3-genesis",
        "operation_type": "generic",
        "intent_sha256": "0" * 64,
        "writes": writes,
        "claimed_inputs": claims,
    }
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    raw = canonicalize(receipt)
    relative = "wiki/meta/operations/000000000001-p3-genesis.json"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(0o600)
    head = {
        "schema": "video-paper-wiki.operation-head.v1",
        "sequence": 1,
        "receipt_path": relative,
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


def _sha_tree(root: Path) -> dict[str, str]:
    found = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        found[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def prepare_research_sources(tmp_path: Path, monkeypatch) -> dict:
    """Build separated receipt-backed vault and checkout. Capture bundle is moved aside."""
    from tests.unit.test_domain_proposal import make_world

    world = make_world(tmp_path, monkeypatch)
    checkout = world["checkout"]
    vault = tmp_path / "vault"
    world["vault"].rename(vault)
    bundle = checkout / ".work" / "raw"
    held_bundle = tmp_path / "capture-bundle"
    if bundle.exists():
        bundle.rename(held_bundle)
    monkeypatch.chdir(checkout)
    config_code_proof(path="config.json", config_format="json", batch_id="d1")
    stage_bytes(batch_id="d1", relative=("draft", DRAFT_FILENAME), data=b'{"draft":"p3-r1"}\n')
    stage_bytes(batch_id="d1", relative=("review", "paper.md"), data=b"p3 review\n")
    stage_bytes(batch_id="d1", relative=("plan", PLAN_FILENAME), data=b'{"plan":"p3-r1"}\n')
    stage_bytes(batch_id="b2", relative=("draft", DRAFT_FILENAME), data=b'{"draft":"second"}\n')
    note = vault / "wiki" / "reading-notes" / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_bytes(
        b"---\ntitle: Reading note\ntype: note\nstatus: draft\ncreated: 2026-09-02\nupdated: 2026-09-02\ntags: []\n---\n\nRecovered note.\n"
    )
    note.chmod(0o600)
    receipt_sha = seal_receipt_vault(vault)
    before = status_code_proof(batch_id="d1")
    return {
        "vault": vault,
        "checkout": checkout,
        "bundle": held_bundle,
        "receipt_sha256": receipt_sha,
        "code_status": before,
        "vault_files": _sha_tree(vault),
        "checkout_files": _sha_tree(checkout),
    }
