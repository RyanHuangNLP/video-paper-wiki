from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.research.conftest import UPSTREAM
from tests.research.test_source_admission import apply_publication
from tests.source_publication_fixture import knowledge_proposal, registered_source
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication import inspect_source_publication, prepare_source_publication, prepare_source_publication_source
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, PROPOSAL, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import sha


def prepare(vault, payloads, **kwargs):
    return prepare_source_publication(batch_id="knowledge", operation_id="knowledge", vault_root=vault, payloads=payloads, **kwargs)


@pytest.mark.parametrize("payloads", [None, [], {3: b"x"}, {"wiki/papers/a.md": "text"}, {"wiki/papers/../a.md": b"x"}, {"wiki/meta/gates/a.json": b"{}"}, {".raw/captured/a.md": b"x"}])
def test_payload_shape_rejects_before_vault_access(checkout, payloads):
    with pytest.raises(ContractError) as err:
        prepare(checkout / "does-not-exist", payloads)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"
    assert "instance_pointer" in err.value.details
    assert not (checkout / ".work/knowledge").exists()


@pytest.mark.parametrize("field,value", [("generated_at", "2026-02-30T00:00:00Z"), ("generated_at", "2026-09-09T25:00:00Z"), ("generated_at", "2026-09-09T00:00:00.1Z")])
def test_calendar_errors_precede_missing_vault(checkout, field, value):
    ledger = {"schema": "claude-obsidian.claim-ledger.v1", "generated_at": value, "claims": {}}
    with pytest.raises(ContractError) as err:
        prepare(checkout / "missing", {CLAIM_LEDGER: canonicalize(ledger)})
    assert err.value.code in {"SCHEMA_INVALID", "SOURCE_PUBLICATION_INVALID"}
    assert "generated_at" in err.value.details["instance_pointer"]


def test_complete_reads_and_original_write_preconditions(checkout):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    prepared = prepare(vault, payloads)
    request = json.loads(Path(prepared["request_path"]).read_bytes())
    assert prepare(vault, payloads) == prepared
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id="knowledge", vault_root=vault, upstream_root=UPSTREAM)
    tx = authority["transaction"]
    writes = {x["path"] for x in tx["writes"]}
    from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory
    snap = _Snapshot(vault)
    try:
        inventory = _walk_inventory(snap, read_bytes=True)
    finally:
        snap.close()
    assert set(tx["read_preconditions"]) == set(inventory) - writes
    assert {x["path"] for x in tx["writes"] if x["role"] == "business"} == {x["path"] for x in request["payloads"]}
    for write in tx["writes"]:
        path = vault / write["path"]
        assert tx["expected_hashes"][write["path"]] == (sha(path.read_bytes()) if path.exists() else None)


@pytest.mark.parametrize("missing", [ASSESSMENT_HEADS, DISPLAY_HEADS, CLAIM_LEDGER, "page", "observation", "association"])
def test_incomplete_graph_or_mirrors_refuse_before_staging(checkout, missing):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    prefixes = {"page": "wiki/papers/", "observation": ".raw/derived/markdown-source/", "association": "wiki/meta/records/source-versions/"}
    path = next(p for p in payloads if p.startswith(prefixes[missing])) if missing in prefixes else missing
    del payloads[path]
    with pytest.raises(ContractError):
        prepare(vault, payloads)
    assert not (checkout / ".work/knowledge").exists()


def test_stale_basis_after_actual_publication(checkout):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    first = prepare(vault, payloads)
    second = prepare_source_publication(batch_id="second", operation_id="second", vault_root=vault, payloads=payloads)
    authority = inspect_source_publication(prepared=second["request_path"], operation_id="second", vault_root=vault, upstream_root=UPSTREAM)
    apply_publication(checkout, vault, authority)
    with pytest.raises(ContractError) as err:
        inspect_source_publication(prepared=first["request_path"], operation_id="knowledge", vault_root=vault, upstream_root=UPSTREAM)
    assert err.value.code == "SOURCE_PUBLICATION_STALE" and err.value.exit_code == 75


def test_external_proposal_exact_layout_and_complete_content(checkout):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    root = checkout / "proposal-input/source-publication"
    (root / "content").mkdir(parents=True)
    for raw in payloads.values():
        (root / "content" / sha(raw)).write_bytes(raw)
    doc = {"schema": PROPOSAL, "kind": "knowledge", "registration": None,
           "payloads": [{"path": p, "content_file": "content/" + sha(raw)} for p, raw in sorted(payloads.items())]}
    path = root / "proposal.json"
    path.write_bytes(canonicalize(doc))
    prepared = prepare_source_publication_source(proposal_path=path, batch_id="knowledge", operation_id="knowledge", vault_root=vault)
    assert prepared == prepare(vault, payloads)
    (root / "content" / ("a" * 64)).write_bytes(b"orphan")
    with pytest.raises(ContractError) as err:
        prepare_source_publication_source(proposal_path=path, batch_id="other", operation_id="other", vault_root=vault)
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("change", ["added-source", "removed-source", "identity", "source-page", "claim-owner", "page-bytes"])
def test_knowledge_cannot_rewrite_registration_or_owner_semantics(checkout, change):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    source = json.loads(payloads[SOURCE_LEDGER])
    sid = capture["source_id"]
    if change == "added-source":
        source["sources"]["src-unregistered"] = copy.deepcopy(source["sources"][sid])
    elif change == "removed-source":
        source["sources"].clear()
    elif change == "identity":
        source["sources"][sid]["ingested_at"] = "2026-09-08"
    elif change == "source-page":
        source["sources"][sid]["pages"] = []
    elif change == "claim-owner":
        ledger = json.loads(payloads[CLAIM_LEDGER])
        next(iter(ledger["claims"].values()))["location"]["path"] = "wiki/papers/wrong.md"
        payloads[CLAIM_LEDGER] = canonicalize(ledger)
    else:
        path = next(p for p in payloads if p.startswith("wiki/papers/"))
        payloads[path] += b"uncompiled text\n"
    payloads[SOURCE_LEDGER] = canonicalize(source)
    with pytest.raises(ContractError):
        prepare(vault, payloads)
    assert not (checkout / ".work/knowledge").exists()


def test_cli_audit_envelopes_success_and_refusal_without_tracebacks(checkout, capsys):
    from video_paper_wiki.cli import main
    vault, _, _, _ = registered_source(checkout)
    assert main(["source-publication", "audit", "--vault-root", str(vault)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] and output["command"] == "source-publication.audit"
    assert output["data"]["state"] == "source_state_audited"
    assert main(["source-publication", "audit", "--vault-root", str(checkout / "missing")]) == 2
    result = capsys.readouterr()
    error = json.loads(result.out)
    assert not error["ok"] and error["error"]["code"] == "WORK_PATH_UNSAFE"
    assert "Traceback" not in result.err


def test_cli_inspection_preserves_stale_exit_code(checkout, capsys):
    from video_paper_wiki.cli import main
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    pending = prepare(vault, payloads)
    authority = inspect_source_publication(prepared=pending["request_path"], operation_id="knowledge", vault_root=vault, upstream_root=UPSTREAM)
    apply_publication(checkout, vault, authority)
    assert main(["source-publication", "inspect", "--prepared", pending["request_path"], "--operation-id", "knowledge",
                 "--vault-root", str(vault), "--upstream-root", str(UPSTREAM)]) == 75
    output = json.loads(capsys.readouterr().out)
    assert output["error"]["code"] == "SOURCE_PUBLICATION_STALE"


def test_registration_rejects_independently_valid_capture_from_another_checkout(checkout, monkeypatch):
    from tests.support import make_checkout
    from tests.upstream.test_markdown_source import _captured_fixture
    from video_paper_wiki.source_publication_contracts import validate_registration
    _, _, authority, result = _captured_fixture(checkout)
    registration = {"authority": authority, "capture_result": result, "ingested_at": "2026-09-09T00:00:00Z"}
    assert validate_registration(registration) == registration
    other = checkout / "independent"
    other.mkdir()
    make_checkout(other)
    with monkeypatch.context() as context:
        context.chdir(other)
        _, _, _, foreign_result = _captured_fixture(other)
    with pytest.raises(ContractError) as err:
        validate_registration({**registration, "capture_result": foreign_result})
    assert err.value.code == "MARKDOWN_AUTHORITY_MISMATCH"


@pytest.mark.parametrize("change", ["claim-text", "claim-ref", "aliases"])
def test_immutable_history_refusal_precedes_broken_prospective_graph(checkout, change):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    prepared = prepare(vault, payloads)
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id="knowledge", vault_root=vault, upstream_root=UPSTREAM)
    apply_publication(checkout, vault, authority)
    paper_path = next(p for p in payloads if p.startswith("wiki/meta/records/papers/"))
    path = CLAIM_LEDGER if change == "claim-text" else paper_path
    doc = json.loads((vault / path).read_bytes())
    if change == "claim-text":
        next(iter(doc["claims"].values()))["text"] += " Rewritten historical text."
    elif change == "claim-ref":
        doc["section_claim_refs"] = []
    else:
        doc["aliases"] = ["synthetic-history-alias"]
    page = next(p for p in payloads if p.startswith("wiki/papers/"))
    with pytest.raises(ContractError) as err:
        prepare_source_publication(batch_id="changed", operation_id="changed", vault_root=vault,
                                   payloads={path: canonicalize(doc), page: b"Uncompiled page\n"})
    assert err.value.code == "SOURCE_HISTORY_CONFLICT" and err.value.exit_code == 75
    assert not (checkout / ".work/changed").exists()


def test_inspect_rederives_prospective_inventory_before_transaction_staging(checkout):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    prepared = prepare(vault, payloads)
    path = Path(prepared["request_path"])
    request = json.loads(path.read_bytes())
    request["prospective_inventory_sha256"] = "0" * 64
    path.write_bytes(canonicalize(request))
    with pytest.raises(ContractError) as err:
        inspect_source_publication(prepared=path, operation_id="knowledge", vault_root=vault, upstream_root=UPSTREAM)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"
    assert err.value.details["instance_pointer"] == "/prospective_inventory_sha256"
    assert not (checkout / ".work/knowledge/transaction-inspect").exists()


@pytest.mark.parametrize("payloads", [None, [], {3: b"x"}, {"wiki/papers/a.md": "text"}, {"wiki/papers/a.md": b"x", 3: b"y"}])
def test_legacy_profile_guard_keeps_invalid_payloads_structured(checkout, payloads):
    from video_paper_wiki.publication import stage_publication_request
    with pytest.raises(ContractError) as err:
        stage_publication_request(batch_id="legacy-invalid", operation_id="legacy-invalid", operation_type="generic", payloads=payloads)
    assert err.value.code == "PUBLICATION_REQUEST_INVALID"
    assert not (checkout / ".work/legacy-invalid").exists()
