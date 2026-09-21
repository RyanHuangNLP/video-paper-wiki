"""Receipt-backed research sources for the P3 rootless restore drill.

Code evidence, flow, domain, experiments, articles, draft, review, and plan
are created through their production entry points. The fixture does not call
the backup scanner.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from video_paper_wiki.article_revision import article_history, status_article_store
from video_paper_wiki.cli import main
from video_paper_wiki.code_proof_public import config_code_proof, status_code_proof
from video_paper_wiki.domain_store import status_domain_store
from video_paper_wiki.experiment_store import status_experiment_store
from video_paper_wiki.flow.prepare import prepare_flow
from video_paper_wiki.flow.selection import select_flow
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import CURRENT_EXACT, CURRENT_PREFIXES, audit_integrity
from video_paper_wiki.upstream_runtime import lint_vault

ROOT = Path(__file__).resolve().parents[2]
SEED = "arxiv:2209.14792"


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


def _file_inventory(root: Path) -> dict[str, dict[str, object]]:
    found = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        info = path.stat()
        found[path.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": stat.S_IMODE(info.st_mode),
        }
    return found


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    os.chmod(path.parent, 0o700)


def _frontmatter(title: str, kind: str) -> str:
    return (
        "---\n"
        f"title: {title}\n"
        f"type: {kind}\n"
        "status: active\n"
        "created: 2026-09-08\n"
        "updated: 2026-09-08\n"
        "tags: [research]\n"
        "---\n\n"
    )


def _claim_page_and_notes(vault: Path) -> None:
    """Give the existing claim ledger a real page, and keep notes linked."""

    ledger = json.loads((vault / "wiki/meta/ledgers/claim-ledger.json").read_text(encoding="utf-8"))
    blocks = ["# Paper", ""]
    for claim_id, row in sorted(ledger["claims"].items()):
        blocks.append(str(row.get("text") or claim_id))
        blocks.append("")
        anchor = (row.get("location") or {}).get("anchor")
        if isinstance(anchor, str) and anchor.startswith("^"):
            blocks.append(anchor)
            blocks.append("")
    _write_private(
        vault / "wiki" / "papers" / "paper.md",
        _frontmatter("Paper", "paper") + "\n".join(blocks) + "\nSee [[reading-notes/note]].\n",
    )
    _write_private(
        vault / "wiki" / "reading-notes" / "note.md",
        _frontmatter("Recoverable note", "note") + "# Recoverable note\n\nSee [[papers/paper]].\n",
    )


def _source_ledger(vault: Path) -> None:
    """Add the source ledger strict provenance requires, without rewriting claims."""

    claim = json.loads((vault / "wiki/meta/ledgers/claim-ledger.json").read_text(encoding="utf-8"))
    source_ids = []
    for row in claim["claims"].values():
        for item in row["evidence"]:
            source_ids.append(item["source_id"])
    unique = sorted(set(source_ids))
    if len(unique) != 1:
        raise RuntimeError("claim evidence does not share one source")
    source_id = unique[0]
    associations = list((vault / "wiki/meta/records/source-versions").glob("*.json"))
    matched = None
    for path in associations:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("source_id") == source_id:
            matched = document
            break
    if matched is None:
        raise RuntimeError("claim source is not an association")
    raw = matched["raw"]
    record = {
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
    document = {
        "schema": "claude-obsidian.source-ledger.v1",
        "generated_at": claim["generated_at"],
        "sources": {source_id: record},
    }
    _write_private(
        vault / "wiki/meta/ledgers/source-ledger.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
    )


def _operator_samples(checkout: Path) -> None:
    """Stage draft, review, and plan through the production CLI."""

    from tests.pdf_samples import sample_pdf_bytes
    from tests.support import paper_source_request, plant_blob

    blob_root = checkout / ".work" / "blobs"
    digest = plant_blob(blob_root, sample_pdf_bytes("tiny"))
    for batch in ("d1", "b2"):
        code = main(["draft", "export", "--sha256", digest, "--batch-id", batch])
        if code != 0:
            raise RuntimeError(f"draft export {batch} failed")
    draft = json.loads((ROOT / "tests/fixtures/drafts/minimal.json").read_text(encoding="utf-8"))
    draft["paper_id"] = SEED
    draft["title"] = "Make-A-Video"
    draft_path = checkout / "review-draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if main(["review", "export", "--draft", str(draft_path), "--batch-id", "d1"]) != 0:
        raise RuntimeError("review export failed")
    request = checkout / "plan-request.json"
    request.write_text(
        json.dumps(paper_source_request(batch_id="d1", local_sha256=digest)),
        encoding="utf-8",
    )
    if main(["ingest", "plan", "--request", str(request)]) != 0:
        raise RuntimeError("plan export failed")


def _stage_uninstalled(world: dict) -> dict:
    """Stage domain, review, and experiment records that are never applied."""

    from tests.unit.test_domain_proposal import valid_proposal
    from tests.unit.test_domain_store import _decision_for, _record, _review
    from tests.unit.test_experiment_store import _record_exp, valid_condition_input
    from video_paper_wiki.domain_store import load_domain_store

    store, heads, _authority = load_domain_store(str(world["vault"]))
    lineage_id, head = sorted(heads["heads"].items())[0]
    proposal = valid_proposal(world)
    proposal["relation"]["reason"] = proposal["relation"]["reason"] + " Kept only in staging."
    annotation = _record(
        world,
        proposal,
        name="uninstalled-proposal.json",
        previous=head["annotation_id"],
        recorded_at="2026-09-14T05:00:00Z",
        batch="du",
    )
    installed = store.annotations[head["annotation_id"]]
    decision = _decision_for(world, {"record": installed})
    decision["expected_previous_review_id"] = head["review_id"]
    decision["decided_at"] = "2026-09-14T06:00:00Z"
    decision["reason"] = "Uninstalled follow-up review."
    review = _review(world, decision, name="uninstalled-review.json", batch="dr")
    experiment = _record_exp(
        world,
        valid_condition_input(world, setting_key="uninstalled-only"),
        name="uninstalled-condition.json",
        batch="eu",
        recorded_at="2026-09-14T07:00:00Z",
    )
    return {
        "domain_batch": "du",
        "review_batch": "dr",
        "experiment_batch": "eu",
        "lineage_id": lineage_id,
        "annotation_id": annotation["record"]["annotation_id"],
        "review_id": review["record"]["review_id"],
        "experiment_record_id": experiment["record"]["record_id"],
        "experiment_condition_id": experiment["record"]["condition_id"],
    }


def _consumers(vault: Path) -> dict:
    installed = status_article_store(vault_root=str(vault))
    staged_articles = status_article_store(vault_root=str(vault), batch_id="ua")
    histories = [
        article_history(vault_root=str(vault), article_id=row["article_id"])
        for row in installed["articles"]
    ]
    histories.extend(
        article_history(vault_root=str(vault), article_id=row["article_id"], batch_id="ua")
        for row in staged_articles["articles"]
        if row.get("head_location") == "staged"
    )
    from video_paper_wiki.flow.status import build_flow_status

    return {
        "code": status_code_proof(batch_id="d1"),
        "flow": build_flow_status(vault_root=str(vault), batch_id="d1"),
        "articles": installed,
        "staged_articles": staged_articles,
        "histories": histories,
        "domain": status_domain_store(vault_root=str(vault)),
        "experiments": status_experiment_store(vault_root=str(vault)),
    }


def prepare_research_sources(tmp_path: Path, monkeypatch) -> dict:
    """Build separated receipt-backed vault and checkout. Capture bundle is moved aside."""

    from tests.unit.test_article_apply import _apply_art
    from tests.unit.test_article_publication import _compile as compile_articles
    from tests.unit.test_article_publication import _stage_complete
    from tests.unit.test_article_revision import _papers, _question
    from tests.unit.test_domain_proposal import make_world
    from tests.unit.test_graph_projection import _three_chain
    from tests.unit.test_reading_apply import _apply_reading
    from tests.unit.test_reading_apply import _compile as compile_reading
    from tests.unit.test_reading_view import _build

    world = make_world(tmp_path, monkeypatch)
    checkout = world["checkout"]
    vault = tmp_path / "vault"
    world["vault"].rename(vault)
    world["vault"] = vault
    bundle = checkout / ".work" / "raw"
    held_bundle = tmp_path / "capture-bundle"
    if bundle.exists():
        bundle.rename(held_bundle)
    monkeypatch.chdir(checkout)
    config_code_proof(path="config.json", config_format="json", batch_id="d1")
    _three_chain(world)
    staged = _stage_complete(world, batch="p1")
    compile_articles(world, "p1")
    _apply_art(world, "p1")
    uninstalled = _stage_complete(world, batch="ua", question="alternate recoverable question", hour=30)
    _build(world, "rd1")
    compile_reading(world, "rd1")
    _apply_reading(world, "rd1")
    paper_ids = _papers(world)
    question = _question(world)
    select_flow(vault_root=str(vault), batch_id="d1", paper_ids=paper_ids[:1], question=question)
    prepare_flow(
        vault_root=str(vault),
        batch_id="d1",
        kind="experiment",
        setting_key="table2-row3-vbench-512",
    )
    prepare_flow(
        vault_root=str(vault),
        batch_id="d1",
        kind="article",
        paper_ids=paper_ids[:1],
        question=question,
    )
    _operator_samples(checkout)
    uninstalled_records = _stage_uninstalled(world)
    _claim_page_and_notes(vault)
    _source_ledger(vault)
    report = lint_vault(vault_root=vault, upstream_root=ROOT / "vendor" / "claude-obsidian")
    lint_paths = []
    for key, rows in report["data"].items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                lint_paths.extend(row.get("paths") or [])
                if "path" in row:
                    lint_paths.append(row["path"])
                if "source" in row:
                    lint_paths.append(row["source"])
    for relative in (
        "wiki/meta/domain",
        "wiki/meta/experiments",
        "wiki/meta/articles",
        "wiki/reading",
    ):
        if not (vault / relative).is_dir():
            raise RuntimeError(f"missing apply product {relative}")
    revisions = [
        uninstalled["outline"]["record"]["revision_id"],
        uninstalled["section"]["record"]["revision_id"],
        uninstalled["full"]["record"]["revision_id"],
    ]
    if len(set(revisions)) < 2:
        raise RuntimeError("article revisions collapsed")
    receipt_sha = seal_receipt_vault(vault)
    consumers = _consumers(vault)
    return {
        "vault": vault,
        "checkout": checkout,
        "bundle": held_bundle,
        "receipt_sha256": receipt_sha,
        "code_status": consumers["code"],
        "consumers": consumers,
        "article_id": uninstalled["full"]["record"]["article_id"],
        "installed_article_id": staged["full"]["record"]["article_id"],
        "revision_ids": revisions,
        "question": question,
        "paper_ids": paper_ids[:1],
        "uninstalled": uninstalled_records,
        "lint_exit_code": report["exit_code"],
        "lint_counts": report["data"].get("summary", {}).get("category_counts", {}),
        "lint_issue_paths": sorted(set(lint_paths)),
        "vault_files": _sha_tree(vault),
        "checkout_files": _sha_tree(checkout),
        "vault_inventory": _file_inventory(vault),
        "checkout_inventory": _file_inventory(checkout),
    }
