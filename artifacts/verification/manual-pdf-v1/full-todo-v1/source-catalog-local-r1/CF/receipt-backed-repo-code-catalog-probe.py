"""Receipt-backed repository/code source-catalog probe.

The disposable fixture is deliberately built by the already reviewed
``source-state-legacy-r1`` capture path. Its PDF and code bytes, manifests,
capture receipts, and pinned transaction applies are therefore real fixture
outputs rather than hand-built inspected declarations. This script only adds
one repository-owned code claim in the temporary Vault and exercises the public
source-catalog readers against the resulting receipt-backed snapshot.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    import pytest  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - probe runtime convenience
    class _PytestMark:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: (lambda fn: fn)

    class _PytestStub:
        def __getattr__(self, _name):
            if _name == "mark":
                return _PytestMark()
            return lambda *args, **kwargs: (lambda fn: fn)

        def __call__(self, *args, **kwargs):
            return lambda fn: fn

    sys.modules["pytest"] = _PytestStub()  # type: ignore[assignment]

SOURCE_ROOT = Path(os.environ.get(
    "SOURCE_ROOT",
    "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/source-catalog-v1/terminal-1/source",
)).resolve()
PROJECT_ROOT = Path(__file__).resolve().parents[6]
if str(SOURCE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT / "src"))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from tests.research.conftest import UPSTREAM
from tests.source_semantics_fixture import event_for
from tests.upstream.test_markdown_source import _snapshot
from video_paper_wiki.identity import claim_id, repo_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import encode_ledger_evidence
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.source_catalog import (
    build_source_catalog,
    lookup_source_catalog,
    query_source_catalog,
    resolve_source_catalog,
)
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_state import collect_source_state

REPO_CLAIM_TEXT = "The repository exposes a training entry point for the temporal transformer."


def _load_reviewed_legacy_fixture():
    """Load the reviewed legacy builder with the frozen candidate imports."""
    path = PROJECT_ROOT / "artifacts/verification/manual-pdf-v1/full-todo-v1/probes/source-state-legacy-r1/source_state_legacy_probe.py"
    text = path.read_text(encoding="utf-8")
    old = (
        "REPO=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')\n"
        "SOURCE=REPO/'.work/parallel/source-publication-v1/terminal-1/source'"
    )
    replacement = (
        "REPO=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')\n"
        f"SOURCE=Path({str(SOURCE_ROOT)!r})"
    )
    if old not in text:
        raise RuntimeError("reviewed legacy fixture source-root declaration changed")
    namespace = {"__name__": "receipt_backed_legacy_fixture"}
    exec(compile(text.replace(old, replacement), str(path), "exec"), namespace)
    return namespace


def _apply_repo_claim_overlay(legacy: dict, result: dict) -> dict:
    """Add a real code-backed repository claim through pinned transaction apply."""
    checkout, vault = result["checkout"], result["vault"]
    triple = result["triple"]
    manifest = copy.deepcopy(triple["manifest"])
    alignment = copy.deepcopy(triple["alignment"])
    repo = copy.deepcopy(triple["repo_record"])
    code = result["code"]
    locator = next(
        loc
        for capability in alignment["capabilities"]
        if capability["name"] == "training"
        for loc in capability["locators"]
    )
    raw_sha = hashlib.sha256(code).hexdigest()
    assert manifest["capture"]["source_identity"] == raw_sha
    assert manifest["capture"]["stored_path"] in result["state"]["bytes"]
    assert result["state"]["bytes"][manifest["capture"]["stored_path"]] == code

    repo_id = repo["repo_id"]
    claim = {
        "claim_id": claim_id("repo:" + repo_id, REPO_CLAIM_TEXT),
        "stable_subject_id": "repo:" + repo_id,
        "canonical_claim_text": REPO_CLAIM_TEXT,
        "evidence": [{**locator, "relation": "supports"}],
        "assessment": "provisional",
        "reviewed_at": None,
    }
    event = event_for(claim, legacy=True)
    repo["capability_claim_refs"] = [{
        "capability": "training", "claim_id": claim["claim_id"], "lifecycle": "active",
    }]
    repo_path = "wiki/meta/records/repos/" + repo_page_slug(repo_id) + ".json"
    claim_row = {
        "text": REPO_CLAIM_TEXT,
        "risk": "normal",
        "assessment": "provisional",
        "confidence": "unknown",
        "reviewed_at": None,
        "location": {"path": "wiki/code/" + repo_page_slug(repo_id) + ".md"},
        "evidence": [encode_ledger_evidence({**locator, "relation": "supports"})],
        "notes": None,
        "supersedes": None,
    }
    ledger = json.loads((vault / CLAIM_LEDGER).read_bytes())
    ledger["claims"][claim["claim_id"]] = claim_row
    payloads = {
        repo_path: canonicalize(repo),
        CLAIM_LEDGER: canonicalize(ledger),
        f"wiki/meta/reviews/{claim['claim_id']}/{event['event_id']}.json": canonicalize(event),
    }
    legacy["_apply_direct_overlay"](checkout, vault, payloads, "repo-code-claim")
    return {
        "repo": repo,
        "repo_id": repo_id,
        "repo_path": repo_path,
        "claim": claim,
        "claim_id": claim["claim_id"],
        "event": event,
        "event_id": event["event_id"],
        "manifest": manifest,
        "alignment": alignment,
        "locator": locator,
        "raw_sha256": raw_sha,
        "raw_path": manifest["capture"]["stored_path"],
        "operation_id": manifest["capture"]["operation_id"],
        "manifest_sha256": manifest["manifest_sha256"],
    }


def _assert_code_resolution(resolved: dict, identity: dict, code: bytes) -> None:
    evidence = resolved["evidence"]
    resolution = evidence["resolution"]
    locator = identity["locator"]
    assert resolution["state"] == "RESOLVED"
    assert resolution["source_path"] == identity["raw_path"]
    assert resolution["source_sha256"] == identity["raw_sha256"]
    assert resolution["position"] == {"kind": "code", "lines": locator["lines"]}
    assert resolution["excerpt_sha256"] == sha(resolution["excerpt"].encode())
    assert resolution["excerpt_sha256"] == locator["snippet_sha256"]
    assert resolution["excerpt"].encode() in code


def main() -> None:
    legacy = _load_reviewed_legacy_fixture()
    temporary = Path(tempfile.mkdtemp(prefix="vpwiki-repo-code-catalog-r3-", dir="/private/tmp")).resolve()
    fixture_stdout = io.StringIO()
    fixture_stderr = io.StringIO()
    with contextlib.redirect_stdout(fixture_stdout), contextlib.redirect_stderr(fixture_stderr):
        result = legacy["build_legacy"](temporary)
    result["snap"].close()
    checkout, vault = result["checkout"], result["vault"]
    before_overlay = _snapshot(vault)
    identity = _apply_repo_claim_overlay(legacy, result)

    snapshot = _Snapshot(vault)
    try:
        audited = audit_integrity(vault, _snapshot=snapshot)
        state = collect_source_state(snapshot, audited, require_rendered=True)
        assert state["profile"] == "legacy-v1"
        assert identity["claim_id"] in state["owners"]
        assert state["owners"][identity["claim_id"]]["page"] == "wiki/code/" + repo_page_slug(identity["repo_id"]) + ".md"
        assert state["owners"][identity["claim_id"]]["kind"] == "repo"
        overlay_audit_head = audited["head"]
        after_overlay = _snapshot(vault)
    finally:
        snapshot.close()

    assert before_overlay != after_overlay
    catalog_before = _snapshot(vault)
    built = build_source_catalog(vault_root=vault, batch_id="repo-code-catalog")
    matching = query_source_catalog(
        vault_root=vault, batch_id="repo-code-catalog", text="line_10",
        scope="source_excerpts", paper_id=identity["repo"]["paper_ids"][0],
        catalog_sha256=built["catalog_sha256"],
    )
    excluded = query_source_catalog(
        vault_root=vault, batch_id="repo-code-catalog", text="line_10",
        scope="source_excerpts", paper_id="arxiv:9999.99999",
        catalog_sha256=built["catalog_sha256"],
    )
    resolved = resolve_source_catalog(
        vault_root=vault, batch_id="repo-code-catalog", claim_id=identity["claim_id"],
        evidence_ordinal=0, catalog_sha256=built["catalog_sha256"],
    )
    _assert_code_resolution(resolved, identity, result["code"])
    repo_lookup = lookup_source_catalog(
        vault_root=vault, batch_id="repo-code-catalog", kind="repository",
        key=identity["repo"]["canonical_repository"], catalog_sha256=built["catalog_sha256"],
    )
    catalog_after = _snapshot(vault)
    assert catalog_before == catalog_after
    assert matching["total_matches"] >= 1
    assert any(hit["claim_id"] == identity["claim_id"] for hit in matching["hits"])
    assert excluded["hits"] == [] and excluded["total_matches"] == 0
    assert any(item["claim_id"] == identity["claim_id"] for item in repo_lookup["evidence"])

    cache = json.loads(Path(built["cache_path"]).read_bytes())
    output = {
        "schema": "full-todo.receipt-backed-repo-code-catalog-probe.v2",
        "candidate_source_root": str(SOURCE_ROOT),
        "temporary_checkout": str(checkout),
        "temporary_vault": str(vault),
        "fixture_builder_stdout_sha256": hashlib.sha256(fixture_stdout.getvalue().encode()).hexdigest(),
        "fixture_builder_stderr_sha256": hashlib.sha256(fixture_stderr.getvalue().encode()).hexdigest(),
        "before_overlay_file_count": len(before_overlay),
        "after_overlay_file_count": len(after_overlay),
        "catalog_vault_unchanged": catalog_before == catalog_after,
        "receipt_backed": audited["classification"] == "receipt_backed",
        "receipt_head": audited["head"],
        "overlay_receipt_head": overlay_audit_head,
        "source_state": state["counts"] | {"profile": state["profile"], "structural_only": state["structural_only"]},
        "identities": {
            "repo_id": identity["repo_id"],
            "repository": identity["repo"]["canonical_repository"],
            "commit": identity["repo"]["canonical_commit"],
            "repo_paper_ids": identity["repo"]["paper_ids"],
            "repo_path": identity["repo_path"],
            "claim_id": identity["claim_id"],
            "event_id": identity["event_id"],
            "event_schema": identity["event"]["schema"],
            "code_manifest_path": next(path for path in state["bytes"] if path.startswith(".raw/derived/code-manifests/")),
            "code_manifest_sha256": identity["manifest_sha256"],
            "code_capture_operation_id": identity["operation_id"],
            "code_source_id": identity["manifest"]["capture"]["source_id"],
            "code_raw_path": identity["raw_path"],
            "code_raw_sha256": identity["raw_sha256"],
            "code_locator": identity["locator"],
        },
        "catalog": {
            "state": built.get("state"),
            "catalog_sha256": built["catalog_sha256"],
            "cache_path": built["cache_path"],
            "row_counts": {key: len(value) for key, value in cache["rows"].items()},
        },
        "queries": {
            "source_excerpts_matching_repo_paper_filter": matching,
            "source_excerpts_excluded_by_unrelated_paper_filter": excluded,
            "resolved_repo_code_evidence": resolved,
            "repository_lookup": repo_lookup,
        },
        "controls": {
            "real_vault": False,
            "network": False,
            "vpwiki_admin": False,
            "git_mutation": False,
            "source_tree_mutation": False,
            "actual_staged_code_capture": True,
            "actual_pinned_inspect_apply": True,
            "manual_manifest_construction": False,
            "source_profile_guard_disabled": False,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
