from __future__ import annotations

import copy
import json

import pytest

from tests.research.conftest import UPSTREAM
from tests.research.test_source_admission import apply_publication
from tests.source_publication_fixture import knowledge_proposal, registered_source, render_proposal
from tests.upstream.test_markdown_source import _snapshot
from video_paper_wiki.source_publication import audit_source_state, inspect_source_publication, prepare_source_publication
from video_paper_wiki.source_publication_contracts import SOURCE_LEDGER
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_semantics_contracts import decision_reference, sha


def test_actual_capture_registration_knowledge_and_typed_audit(checkout):
    vault, capture, _, admitted = registered_source(checkout)
    assert admitted["publication_profile"] == "source-v1"
    state = audit_source_state(vault_root=vault)
    assert state["profile"] == "legacy-v1" and state["counts"]["ledger_snapshots"] == 2
    payloads, material, _ = knowledge_proposal(vault, capture)
    before = _snapshot(vault)
    prepared = prepare_source_publication(batch_id="knowledge", operation_id="knowledge", vault_root=vault, payloads=payloads)
    assert _snapshot(vault) == before
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id="knowledge",
                                           vault_root=vault, upstream_root=UPSTREAM)
    assert _snapshot(vault) == before
    tx = authority["transaction"]
    assert tx["claimed_inputs"] == [] and SOURCE_LEDGER not in tx["read_preconditions"]
    assert tx["operation_type"] == "ingest" and tx["phase"] == "inspected"
    apply_publication(checkout, vault, authority)
    audit = audit_source_state(vault_root=vault)
    assert audit["profile"] == "source-v1" and audit["receipt_backed"] and not audit["upstream_validated"]
    assert audit["counts"]["papers"] == audit["counts"]["claims"] == audit["counts"]["associations"] == 1
    assert audit["display_heads"]["heads"] == []
    noop = prepare_source_publication(batch_id="noop", operation_id="noop", vault_root=vault, payloads={})
    assert noop["state"] == "no_change" and noop["request_path"] is None and not (checkout / ".work/noop").exists()


def publish(checkout, vault, payloads, name):
    prepared = prepare_source_publication(batch_id=name, operation_id=name, vault_root=vault, payloads=payloads)
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id=name,
                                           vault_root=vault, upstream_root=UPSTREAM)
    apply_publication(checkout, vault, authority)
    return authority


def test_explicit_fixture_display_history_and_assessment_preserve_prior_bytes(checkout):
    from tests.source_semantics_fixture import event_for, selection
    vault, capture, _, _ = registered_source(checkout)
    payloads, material, arguments = knowledge_proposal(vault, capture)
    publish(checkout, vault, payloads, "knowledge")
    prior = _snapshot(vault)
    group = material["papers"][0]
    association = group["associations"][0]
    chosen = selection(association)
    group["display_decisions"] = [chosen]
    group["record"].update(display_head=decision_reference(chosen), active_extraction_path=association["extraction"]["path"],
                           active_extraction_sha256=association["extraction"]["sha256"])
    publish(checkout, vault, render_proposal(material, arguments), "select")
    after = audit_source_state(vault_root=vault)
    assert after["display_heads"]["heads"][0]["decision_id"] == chosen["decision_id"]
    assert after["counts"]["events"] == 1
    claim = group["claims"][0]
    review = event_for(claim, previous=group["events"][-1], human=True)
    group["events"].append(review)
    claim.update(assessment="accepted", reviewed_at="2026-09-09")
    reviewed_payloads = render_proposal(material, arguments)
    unreviewed = prepare_source_publication(batch_id="unreviewed", operation_id="unreviewed",
        vault_root=vault, payloads=reviewed_payloads)
    with pytest.raises(ContractError) as refused:
        inspect_source_publication(prepared=unreviewed["request_path"], operation_id="unreviewed",
            vault_root=vault, upstream_root=UPSTREAM)
    assert refused.value.code == "UPSTREAM_INSPECT_REFUSED"
    assert refused.value.details["upstream_code"] == "INVALID_PROVENANCE_LEDGER"
    # This explicit synthetic proposal also supplies its source review metadata.
    ledger = json.loads((vault / SOURCE_LEDGER).read_bytes())
    ledger["sources"][association["source_id"]]["review_status"] = "active"
    reviewed_payloads[SOURCE_LEDGER] = canonicalize(ledger)
    publish(checkout, vault, reviewed_payloads, "fixture-review")
    audit = audit_source_state(vault_root=vault)
    assert audit["assessment_heads"]["heads"][claim["claim_id"]]["event_id"] == review["event_id"]
    for path, (raw, mode) in prior.items():
        if path.startswith(("wiki/meta/reviews/", "wiki/meta/operations/", "wiki/meta/records/source-versions/", ".raw/derived/")):
            assert (vault / path).read_bytes() == raw
    # A supplied older choice cannot silently roll back the current registry.
    bad = {"wiki/meta/records/source-display-heads.json": canonicalize({"schema": "video-paper-wiki.source-display-heads.v1", "heads": []})}
    with pytest.raises(ContractError):
        prepare_source_publication(batch_id="bad-rollback", operation_id="bad-rollback", vault_root=vault, payloads=bad)


def capture_another(checkout, vault):
    from tests.markdown_source_fixture import LIGHT_ID, approval_fixture, light_source
    from tests.research.test_source_admission import _apply_bundle
    from video_paper_wiki.markdown_source import bind_markdown_capture_result, inspect_markdown_capture
    from video_paper_wiki_research.formal_source import plan_markdown_source, prepare_markdown_source
    workspace, md, _ = light_source(checkout / ".work/second-input", text="Another synthetic source version.")
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="second-capture")
    from pathlib import Path
    plan = json.loads(Path(planned["plan_path"]).read_bytes())
    approval = checkout / ".work/second-approval.json"
    approval.write_bytes(canonicalize(approval_fixture(plan)))
    prepared = prepare_markdown_source(plan=planned["plan_path"], approval_ref=approval)
    capture = inspect_markdown_capture(prepared=prepared["request_path"], operation_id="second-capture",
        vault_root=vault, upstream_root=UPSTREAM)["authority"]
    result = _apply_bundle(vault, checkout / ".work/second-capture" / capture["transaction_staging"]["bundle_file"],
                           capture["upstream_authority"]["transaction"]["inspection"]["approval_sha256"])
    target = capture["stored_path"]
    bound = bind_markdown_capture_result(capture, result, before={target: None},
        after={target: {"sha256": sha(md.read_bytes()), "mode": 0o600}})
    return capture, bound


def test_later_registration_keeps_display_and_full_typed_graph(checkout):
    from tests.upstream.test_markdown_source import _admit
    from tests.source_semantics_fixture import selection
    vault, capture, _, _ = registered_source(checkout)
    payloads, material, arguments = knowledge_proposal(vault, capture)
    publish(checkout, vault, payloads, "knowledge")
    group = material["papers"][0]
    association = group["associations"][0]
    chosen = selection(association)
    group["display_decisions"] = [chosen]
    group["record"].update(display_head=decision_reference(chosen), active_extraction_path=association["extraction"]["path"],
                           active_extraction_sha256=association["extraction"]["sha256"])
    publish(checkout, vault, render_proposal(material, arguments), "select")
    before = audit_source_state(vault_root=vault)
    captured, result = capture_another(checkout, vault)
    admitted = _admit(vault, captured, result, batch_id="second-admit", operation_id="second-admit", publication_profile="source-v1")
    tx = admitted["publication_authority"]["transaction"]
    assert [x["path"] for x in tx["claimed_inputs"]] == [captured["stored_path"]]
    assert all(x["path"] == SOURCE_LEDGER or x["path"].startswith(".raw/derived/source-ledgers/") for x in tx["writes"] if x["role"] == "business")
    apply_publication(checkout, vault, admitted["publication_authority"])
    after = audit_source_state(vault_root=vault)
    assert before["display_heads"] == after["display_heads"] and before["assessment_heads"] == after["assessment_heads"]
    assert after["counts"]["associations"] == 1
    already = _admit(vault, captured, batch_id="already", operation_id="already", publication_profile="source-v1")
    assert already["publication_profile"] == "source-v1" and already["state"] == "source_already_registered"
    assert not (checkout / ".work/already").exists()
    # Explicitly associate the second version, then select it and roll back to
    # the first through new decisions. Evidence keeps its original association.
    from video_paper_wiki.receipt_audit import HEAD, audit_integrity
    from video_paper_wiki.source_versions import associate_source
    from video_paper_wiki.source_semantics_contracts import association_reference
    from video_paper_wiki.identity import paper_page_slug
    audit = audit_integrity(vault)
    current_ledger = (vault / SOURCE_LEDGER).read_bytes()
    arguments["head_bytes"] = (vault / HEAD).read_bytes()
    arguments["receipt_bytes"] = {p: (vault / p).read_bytes() for p in audit["receipts"]}
    second = associate_source(captured["request"]["plan"]["observation"],
        raw_bytes=(vault / captured["stored_path"]).read_bytes(), ledger_bytes=current_ledger,
        head_bytes=arguments["head_bytes"], receipt_bytes=arguments["receipt_bytes"],
        existing=[association])["association"]
    group["associations"].append(second)
    group["record"]["source_associations"] = [association_reference(x) for x in sorted(group["associations"], key=lambda a: a["association_id"])]
    group["record"]["source_ids"] = sorted([association["source_id"], second["source_id"]])
    arguments["raw_sources"][second["raw"]["path"]] = (vault / second["raw"]["path"]).read_bytes()
    arguments["extraction_artifacts"][second["extraction"]["path"]] = canonicalize(second["observation"])
    arguments["registration_ledgers"][second["registration"]["source_ledger_path"]] = current_ledger
    second_payloads = render_proposal(material, arguments)
    ledger = json.loads(current_ledger)
    ledger["sources"][second["source_id"]]["pages"] = ["wiki/papers/" + paper_page_slug(second["paper_id"]) + ".md"]
    second_payloads[SOURCE_LEDGER] = canonicalize(ledger)
    publish(checkout, vault, second_payloads, "associate-second")
    evidence_before = group["claims"][0]["evidence"]
    previous = chosen
    for sequence, target in enumerate((second, association), 2):
        choice = selection(target, previous=previous, reason="Explicit synthetic version switch/rollback.")
        group["display_decisions"].append(choice)
        group["record"].update(display_head=decision_reference(choice), active_extraction_path=target["extraction"]["path"],
                               active_extraction_sha256=target["extraction"]["sha256"])
        publish(checkout, vault, render_proposal(material, arguments), "choose-" + str(sequence))
        state = audit_source_state(vault_root=vault)
        assert state["display_heads"]["heads"][0]["sequence"] == sequence
        assert state["display_heads"]["heads"][0]["association"] == association_reference(target)
        assert group["claims"][0]["evidence"] == evidence_before
        previous = choice


def test_backup_and_isolated_restore_preserve_every_source_namespace(checkout):
    from video_paper_wiki.backup_archive import encode_backup_archive, restore_backup_archive
    from video_paper_wiki.backup_manifest import build_backup_manifest, verify_restored_tree
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    publish(checkout, vault, payloads, "knowledge")
    manifest = build_backup_manifest(vault)
    files = {x["path"] for x in manifest["files"]}
    assert set(payloads) <= files
    archive = checkout / ".work/fixture-backup.zip"
    archive.write_bytes(encode_backup_archive(vault_root=vault, manifest=manifest))
    archive.chmod(0o600)
    restored = checkout / "isolated-restored"
    restored.mkdir(mode=0o700)
    restore_backup_archive(archive=archive, source_root=vault, restore_root=restored, manifest=manifest)
    verify_restored_tree(restored, manifest, source_root=vault)
    assert audit_source_state(vault_root=restored) == audit_source_state(vault_root=vault)
