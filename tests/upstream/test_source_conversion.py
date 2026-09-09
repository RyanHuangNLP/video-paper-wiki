from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.markdown_source_fixture import LIGHT_ID, approval_fixture
from tests.research.conftest import UPSTREAM
from tests.research.test_source_admission import _apply_bundle, apply_publication
from tests.research.test_source_conversion import conversion_fixture, publish_conversion
from tests.source_semantics_fixture import event_for
from tests.upstream.test_markdown_source import _admit, _snapshot
from tests.upstream.test_source_publication import publish
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source import bind_markdown_capture_result, inspect_markdown_capture
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.source_publication import _vault, audit_source_state
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_state import collect_source_state
from video_paper_wiki_research.formal_source import plan_markdown_source, prepare_markdown_source
from video_paper_wiki_research.light_index import _locate_pages, build_index
from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge
from video_paper_wiki_research.source_conversion import convert_source_knowledge


def capture_current(checkout, kwargs, *, batch, version, canonical_id=None):
    planned = plan_markdown_source(workspace_root=kwargs["workspace_root"], paper_id=LIGHT_ID,
        batch_id=batch, version_label=version, canonical_paper_id=canonical_id)
    plan = json.loads(Path(planned["plan_path"]).read_bytes())
    approval = checkout / (batch + "-synthetic-approval.json")
    approval.write_bytes(canonicalize(approval_fixture(plan)))
    prepared = prepare_markdown_source(plan=planned["plan_path"], approval_ref=approval)
    capture = inspect_markdown_capture(prepared=prepared["request_path"], operation_id=batch,
        vault_root=kwargs["vault_root"], upstream_root=UPSTREAM)["authority"]
    bound = None
    if capture["disposition"] == "create":
        result = _apply_bundle(kwargs["vault_root"], checkout / ".work" / batch / capture["transaction_staging"]["bundle_file"],
            capture["upstream_authority"]["transaction"]["inspection"]["approval_sha256"])
        target = capture["stored_path"]
        bound = bind_markdown_capture_result(capture, result, before={target: None},
            after={target: {"sha256": sha((kwargs["vault_root"] / target).read_bytes()), "mode": 0o600}})
        admitted = _admit(kwargs["vault_root"], capture, bound, batch_id=batch + "-admit", operation_id=batch + "-admit",
                         publication_profile="source-v1")
        apply_publication(checkout, kwargs["vault_root"], admitted["publication_authority"])
    path = checkout / (batch + "-authority.json")
    path.write_bytes(canonicalize(capture))
    return path, capture


def complete_payloads(vault, payloads):
    """Test caller assembles an explicit synthetic review, through real checks."""
    with _vault(vault, None) as (root, snapshot, _):
        audit = audit_integrity(root, _snapshot=snapshot)
        state = collect_source_state(snapshot, audit, overlay=payloads, require_rendered=False)
        return payloads | state["pages"] | {ASSESSMENT_HEADS: canonicalize(state["assessment_heads"]),
                                            DISPLAY_HEADS: canonicalize(state["display_heads"])}


def synthetic_review(checkout, kwargs):
    vault = kwargs["vault_root"]
    with _vault(vault, None) as (root, snapshot, _):
        current = collect_source_state(snapshot, audit_integrity(root, _snapshot=snapshot))
    claim = current["claims"][0]
    prior = next(e for e in current["documents"]["event"].values() if e["claim_id"] == claim["claim_id"])
    event = event_for(claim, previous=prior, human=True, decided_at="2026-09-09T02:00:00Z")
    ledger = copy.deepcopy(current["claim_ledger"])
    ledger["generated_at"] = "2026-09-09T02:00:00Z"
    ledger["claims"][claim["claim_id"]].update(assessment="accepted", reviewed_at="2026-09-09")
    sources = copy.deepcopy(current["source_ledger"])
    for row in sources["sources"].values():
        row["review_status"] = "active"
    payloads = {CLAIM_LEDGER: canonicalize(ledger), SOURCE_LEDGER: canonicalize(sources),
        f"wiki/meta/reviews/{claim['claim_id']}/{event['event_id']}.json": canonicalize(event)}
    publish(checkout, vault, complete_payloads(vault, payloads), "synthetic-review")
    return claim["claim_id"], event


@pytest.mark.parametrize("same_raw", [False, True])
def test_source_version_change_invalidates_once_and_preserves_all_prior_history(checkout, same_raw):
    kwargs, document, _, _ = conversion_fixture(checkout)
    first, _ = publish_conversion(checkout, kwargs)
    cid, reviewed = synthetic_review(checkout, kwargs)
    vault = kwargs["vault_root"]
    reviewed_snapshot = _snapshot(vault)
    accepted_noop = convert_source_knowledge(**(kwargs | dict(batch_id="accepted-noop", operation_id="accepted-noop",
                                                             metadata=None, proposed_at="1999-01-01T00:00:00Z")))
    assert accepted_noop["state"] == "no_change"
    assert reviewed_snapshot == _snapshot(vault)
    if not same_raw:
        directory = kwargs["workspace_root"] / "papers" / ("a" * 64)
        md = directory / "source.md"
        text = md.read_bytes().decode().replace("A temporal transformer", "An updated temporal transformer")
        text = text.replace("第二行 evidence.", "第二行 e\u0301vidence. 👩🏽‍💻 Exact Unicode spans.").replace("frames.\n", "frames.\r\n")
        md.write_bytes(text.encode())
        meta_path = directory / "source.json"
        meta = json.loads(meta_path.read_bytes())
        meta["document"]["sha256"] = sha(md.read_bytes())
        meta["pages"] = [{k: v for k, v in p.items() if k != "text"} for p in _locate_pages(text, page_count=1)]
        meta_path.write_bytes(canonicalize(meta))
        assert build_index(kwargs["workspace_root"])["ok"]
        context = export_knowledge_context(kwargs["workspace_root"], paper_id=LIGHT_ID)
        citation = context["context"]["evidence"][0]["chunk_id"]
        document["sections"]["summary"]["citations"] = [citation]
        document["concepts"][0]["citations"] = [citation]
        imported = import_knowledge(kwargs["workspace_root"], context, document)
        assert imported["ok"]
        kwargs["record_id"] = imported["record_id"]
    path, capture = capture_current(checkout, kwargs, batch="capture-version-two", version="v2")
    kwargs.update(capture_authority=path, metadata=None, batch_id="convert-two", operation_id="convert-two",
                  proposed_at="2026-09-09T03:00:00Z")
    second, _ = publish_conversion(checkout, kwargs)
    summary = second["conversion"]
    assert summary["association_id"] != first["conversion"]["association_id"]
    assert summary["invalidated_claim_ids"] == [cid]
    assert summary["created_claim_ids"] == summary["unchanged_claim_ids"] == []
    state = audit_source_state(vault_root=vault)
    assert state["counts"]["associations"] == 2 and state["counts"]["events"] == 3
    assert state["display_heads"]["heads"] == []
    ledger = json.loads((vault / CLAIM_LEDGER).read_bytes())
    assert ledger["claims"][cid]["assessment"] == "provisional"
    assert ledger["claims"][cid]["reviewed_at"] is None
    if not same_raw:
        from video_paper_wiki.markdown_locator import decode_evidence, resolve_markdown_locator
        evidence = decode_evidence(ledger["claims"][cid]["evidence"][0])
        association = json.loads((vault / f"wiki/meta/records/source-versions/{summary['association_id']}.json").read_bytes())
        raw = (vault / association["raw"]["path"]).read_bytes()
        assert b"\r\n" in raw and "e\u0301" in raw.decode()
        resolve_markdown_locator({k: v for k, v in evidence.items() if k != "relation"}, association, raw)
        start, end = evidence["charspan"]
        assert sha(raw.decode()[start:end].encode()) == evidence["excerpt_sha256"]
    eid = state["assessment_heads"]["heads"][cid]["event_id"]
    event = json.loads((vault / f"wiki/meta/reviews/{cid}/{eid}.json").read_bytes())
    assert event["previous_event_id"] == reviewed["event_id"]
    assert event["actor_kind"] == "system" and event["decided_by"] == "source-conversion-v1"
    assert event["reason"] == f"Evidence changed by lightweight record {kwargs['record_id']}; source association {summary['association_id']}."
    for path, (raw, _) in reviewed_snapshot.items():
        if path.startswith(("wiki/meta/reviews/", ".raw/", "wiki/meta/records/source-versions/", "wiki/meta/operations/")):
            assert (vault / path).read_bytes() == raw
    record = json.loads(next((vault / "wiki/meta/records/papers").glob("*.json")).read_bytes())
    assert len(record["source_ids"]) == (1 if same_raw else 2)
    assert record["active_extraction_path"] is record["display_head"] is None
    noop = convert_source_knowledge(**(kwargs | dict(batch_id="v2-noop", operation_id="v2-noop")))
    assert noop["state"] == "no_change" and noop["conversion"]["association_state"] == "reused"


def test_canonical_paper_identity_can_differ_from_light_content_id(checkout):
    kwargs, _, _, _ = conversion_fixture(checkout)
    authority, _ = capture_current(checkout, kwargs, batch="arxiv-capture", version="v1", canonical_id="arxiv:2401.01234")
    metadata = json.loads(kwargs["metadata"].read_bytes())
    metadata.update(paper_id="arxiv:2401.01234", arxiv_id="2401.01234")
    kwargs["metadata"].write_bytes(canonicalize(metadata))
    kwargs["capture_authority"] = authority
    prepared, _ = publish_conversion(checkout, kwargs)
    assert prepared["conversion"]["canonical_paper_id"] == "arxiv:2401.01234"
    assert prepared["conversion"]["light_paper_id"] == LIGHT_ID
    assert (kwargs["vault_root"] / "wiki/papers/arxiv-2401.01234.md").exists()
    prior = _snapshot(kwargs["vault_root"])
    metadata["arxiv_id"] = "2402.01234"
    kwargs["metadata"].write_bytes(canonicalize(metadata))
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**(kwargs | dict(batch_id="bad-identifier", operation_id="bad-identifier")))
    assert err.value.code == "SOURCE_CONVERSION_INVALID"
    assert prior == _snapshot(kwargs["vault_root"])


def test_existing_source_page_links_sort_and_unrelated_legacy_rows_only_gain_explicit_null(checkout):
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=True)
    legacy_paper(checkout, kwargs, document, attach_markdown_page=True)
    vault = kwargs["vault_root"]
    before = _snapshot(vault)
    authority, _ = capture_current(checkout, kwargs, batch="second-paper-capture", version="v1",
                                   canonical_id="arxiv:2401.01234")
    metadata = json.loads(kwargs["metadata"].read_bytes())
    metadata.update(paper_id="arxiv:2401.01234", arxiv_id="2401.01234")
    kwargs["metadata"].write_bytes(canonicalize(metadata))
    kwargs.update(capture_authority=authority, batch_id="second-paper", operation_id="second-paper")
    publish_conversion(checkout, kwargs)
    state = audit_source_state(vault_root=vault)
    assert state["counts"]["papers"] == 2 and state["counts"]["associations"] == 1
    sources = json.loads((vault / SOURCE_LEDGER).read_bytes())["sources"]
    assert len(sources) == 2
    pages = next(row for row in sources.values() if row["origin"]["locator"].endswith(".md"))["pages"]
    assert len(pages) == 2 and pages == sorted(set(pages))
    old_rows = json.loads(before[CLAIM_LEDGER][0])["claims"]
    new_rows = json.loads((vault / CLAIM_LEDGER).read_bytes())["claims"]
    assert any("reviewed_at" not in row for row in old_rows.values())
    for cid, row in old_rows.items():
        expected = copy.deepcopy(row)
        expected.setdefault("reviewed_at", None)
        assert new_rows[cid] == expected
    for path, (raw, _) in before.items():
        if path.startswith((".raw/", "wiki/meta/reviews/", "wiki/meta/records/", "wiki/meta/operations/")):
            assert (vault / path).read_bytes() == raw


def test_missing_earliest_registration_snapshot_cannot_use_modified_current_ledger(checkout):
    from video_paper_wiki_research.source_conversion_model import source_association
    kwargs, _, _, capture = conversion_fixture(checkout)
    publish_conversion(checkout, kwargs)
    vault = kwargs["vault_root"]
    with _vault(vault, None) as (root, retained, _):
        current = collect_source_state(retained, audit_integrity(root, _snapshot=retained))
    association = next(iter(current["documents"]["association"].values()))
    historical_path = association["registration"]["source_ledger_path"]
    assert current["bytes"][historical_path] != current["bytes"][SOURCE_LEDGER]
    del current["bytes"][historical_path]
    with pytest.raises(ContractError) as err:
        source_association(current, capture["request"]["plan"]["observation"], (vault / capture["stored_path"]).read_bytes())
    assert err.value.code == "SOURCE_REGISTRATION_INVALID"
    assert err.value.details["instance_pointer"] == historical_path


def test_retired_reference_cannot_be_reactivated_by_conversion(checkout):
    kwargs, _, _, _ = conversion_fixture(checkout)
    publish_conversion(checkout, kwargs)
    vault = kwargs["vault_root"]
    record_path = next((vault / "wiki/meta/records/papers").glob("*.json"))
    record = json.loads(record_path.read_bytes())
    record["section_claim_refs"][0]["lifecycle"] = "retired"
    publish(checkout, vault, complete_payloads(vault, {record_path.relative_to(vault).as_posix(): canonicalize(record)}), "retire")
    before = _snapshot(vault)
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**(kwargs | dict(batch_id="retired-convert", operation_id="retired-convert")))
    assert err.value.code == "SOURCE_CONVERSION_INVALID"
    assert before == _snapshot(vault)


def legacy_paper(checkout, kwargs, document, *, preserve_cited_claim=True, empty_claim=False,
                 attach_markdown_page=False, taxonomy=()):
    """Create actual legacy PDF capture, parser package and receipt-backed paper.

    PDF bytes and the synthetic Docling run exist only in this disposable fixture.
    The parser package is a fixture, not an invocation of Docling or a model.
    """
    from tests.research.test_publication_bridge import four_file_run
    from tests.research.test_source_admission import CLAIM_TEXT, admit_source, capture_pdf, intake_for
    from tests.source_semantics_fixture import claim_for, fixture
    from video_paper_wiki.canonical_compiler import compile_pages, concept_items_for_papers
    from video_paper_wiki.identity import paper_page_slug
    from video_paper_wiki.markdown_locator import encode_evidence
    from video_paper_wiki.publication import _assemble_publication_transaction, inspect_publication
    from video_paper_wiki.receipt_audit import _Snapshot
    from video_paper_wiki.staging import _open_batch_session
    from video_paper_wiki_research.publication_bridge import package_extraction_run

    vault = kwargs["vault_root"]
    first_markdown_registration_ledger = (vault / SOURCE_LEDGER).read_bytes()
    pdf, captured, _ = capture_pdf(checkout, vault, batch_id="legacy-pdf-capture")
    admitted = admit_source(intake=intake_for(pdf), capture_authority=captured, vault_root=vault,
        upstream_root=UPSTREAM, batch_id="legacy-pdf-admit", operation_id="legacy-pdf-admit",
        ingested_at="2026-09-09T00:00:00Z")
    apply_publication(checkout, vault, inspect_publication(prepared=admitted["request_path"],
        operation_id="legacy-pdf-admit", upstream_root=UPSTREAM, vault_root=vault))
    runs = four_file_run(checkout / "synthetic-parser-run", pdf)
    packaged = package_extraction_run(captured_pdf=vault / admitted["stored_path"],
        **runs, vault_root=vault, batch_id="legacy-package", operation_id="legacy-package")
    apply_publication(checkout, vault, inspect_publication(prepared=packaged["request_path"],
        operation_id="legacy-package", upstream_root=UPSTREAM, vault_root=vault))
    artifact = next(x for x in packaged["artifact_set"]["artifacts"] if x["kind"] == "document_json")
    evidence = {"kind": "pdf", "relation": "supports", "source_id": admitted["source_id"], "page": 1,
        "ref": "#/texts/0", "bbox": [0, 1, 40, 20], "charspan": [0, len(CLAIM_TEXT)],
        "artifact_path": artifact["path"], "artifact_sha256": artifact["sha256"], "text_sha256": sha(CLAIM_TEXT.encode())}
    claims = [claim_for([evidence], subject="paper:" + LIGHT_ID, text=document["sections"]["summary"]["text"])]
    sections = [("one_sentence_conclusion", True)]
    if preserve_cited_claim:
        claims.append(claim_for([evidence], subject="paper:" + LIGHT_ID, text="An older cited legacy limitation."))
        sections.append(("limitations", False))
    if empty_claim:
        claims.append(claim_for([], subject="paper:" + LIGHT_ID, text="An old uncited statement remains unresolved."))
        sections.append(("evidence_status", False))
    events = [event_for(c, legacy=True) for c in claims]
    events.append(event_for(claims[0], previous=events[0], human=True, legacy=True))
    claims[0].update(assessment="accepted", reviewed_at="2026-09-09")
    record = fixture("video-paper-wiki.paper-record.v1")
    record.pop("arxiv_id", None)
    record.pop("doi", None)
    record.update(paper_id=LIGHT_ID, title="Legacy paper", title_zh="旧版论文", authors=[], aliases=[], taxonomy=list(taxonomy),
        source_ids=[admitted["source_id"]], active_extraction_path=artifact["path"],
        active_extraction_sha256=artifact["sha256"], created_at="2026-09-09T00:00:00Z", updated_at="2026-09-09T00:00:00Z",
        section_claim_refs=[{"claim_id": c["claim_id"], "section": section, "core": core, "lifecycle": "active"}
                            for c, (section, core) in zip(claims, sections)])
    page = "wiki/papers/" + paper_page_slug(LIGHT_ID) + ".md"
    ledger = json.loads((vault / CLAIM_LEDGER).read_bytes())
    for claim in claims:
        ledger["claims"][claim["claim_id"]] = {"text": claim["canonical_claim_text"], "risk": "normal",
            "assessment": claim["assessment"], "confidence": "low", "location": {"path": page},
            "evidence": [encode_evidence(e) for e in claim["evidence"]], "notes": "Historical notes remain exact."}
        if claim["assessment"] == "accepted":
            ledger["claims"][claim["claim_id"]]["reviewed_at"] = claim["reviewed_at"]
    sources = json.loads((vault / SOURCE_LEDGER).read_bytes())
    sources["sources"][admitted["source_id"]]["pages"] = [page]
    sources["sources"][admitted["source_id"]]["review_status"] = "active"
    if attach_markdown_page:
        for row in sources["sources"].values():
            if row["origin"]["locator"].endswith(".md"):
                row["pages"] = [page]
    material = {"schema": "video-paper-wiki.compile-input.v1", "operation_id": "legacy-paper",
        "papers": [{"record": record, "claims": claims, "events": events}], "code": [],
        "concepts": concept_items_for_papers([record])}
    render_material = copy.deepcopy(material)
    if empty_claim:
        # Historical structural states may contain uncited rows that the
        # modern compiler refuses. Their handwritten page remains observable.
        render_material["papers"][0]["claims"] = claims[:-1]
        render_material["papers"][0]["events"] = [e for e in events if e["claim_id"] != claims[-1]["claim_id"]]
        render_material["papers"][0]["record"]["section_claim_refs"] = record["section_claim_refs"][:-1]
    payloads = compile_pages(render_material)
    if empty_claim:
        payloads[page] += ("\n" + claims[-1]["canonical_claim_text"] + "\n").encode()
    payloads.update({CLAIM_LEDGER: canonicalize(ledger), SOURCE_LEDGER: canonicalize(sources),
        "wiki/meta/records/papers/" + paper_page_slug(LIGHT_ID) + ".json": canonicalize(record)})
    # Explicitly preserve known first-registration bytes in this historical
    # fixture transaction, before subsequent source-row page changes.
    payloads[".raw/derived/source-ledgers/" + sha(first_markdown_registration_ledger) + ".json"] = first_markdown_registration_ledger
    for event in events:
        payloads[f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json"] = canonicalize(event)
    # The modern publication facade refuses a legacy graph carrying source
    # snapshots. Build this synthetic historical fixture through the shared
    # pinned transaction assembler, retaining real inspection and receipts.
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        previous = {audit["head"]["receipt_path"]: snapshot.read(audit["head"]["receipt_path"])}
        with _open_batch_session("legacy-paper", create=True) as session:
            authority = _assemble_publication_transaction(operation_id="legacy-paper", operation_type="ingest",
                batch="legacy-paper", payload_bytes=payloads, claimed_input_paths=[], read_bytes=previous,
                audit=audit, snapshot=snapshot, session=session, upstream_root=UPSTREAM, checkout=checkout, vault=vault)
        bundle = Path(authority["transaction_staging"]["bundle_file"])
        if not bundle.is_absolute():
            bundle = checkout / ".work/legacy-paper" / bundle
        _apply_bundle(vault, bundle, authority["transaction"]["inspection"]["approval_sha256"])
    finally:
        snapshot.close()
    with _vault(vault, None) as (root, retained, _):
        state = collect_source_state(retained, audit_integrity(root, _snapshot=retained), allow_legacy_structural=True)
        assert state["profile"] == "legacy-v1" and state["structural_only"]
    return claims, events, record


def test_actual_legacy_upgrade_preserves_unselected_evidence_events_and_source_inventory(checkout):
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=True)
    claims, events, _ = legacy_paper(checkout, kwargs, document)
    before = _snapshot(kwargs["vault_root"])
    prepared, _ = publish_conversion(checkout, kwargs)
    result = prepared["conversion"]
    assert result["invalidated_claim_ids"] == [claims[0]["claim_id"]]
    assert result["created_claim_ids"] == result["unchanged_claim_ids"] == []
    assert result["location_migrated_claim_ids"] == sorted(c["claim_id"] for c in claims)
    vault = kwargs["vault_root"]
    state = audit_source_state(vault_root=vault)
    assert state["profile"] == "source-v1" and state["counts"]["events"] == 4
    rows = json.loads((vault / CLAIM_LEDGER).read_bytes())["claims"]
    original_rows = json.loads(before[CLAIM_LEDGER][0])["claims"]
    preserved_id = claims[1]["claim_id"]
    expected = copy.deepcopy(original_rows[preserved_id])
    expected["location"]["anchor"] = "^" + preserved_id
    expected["reviewed_at"] = None
    assert rows[preserved_id] == expected
    for path, (raw, _) in before.items():
        if path.startswith((".raw/", "wiki/meta/reviews/", "wiki/meta/operations/")):
            assert (vault / path).read_bytes() == raw
    record = json.loads(next((vault / "wiki/meta/records/papers").glob("*.json")).read_bytes())
    assert record["active_extraction_path"] is record["active_extraction_sha256"] is record["display_head"] is None
    assert len(record["source_ids"]) == 2


@pytest.mark.parametrize("failure", ["empty-preserved-claim", "unrepresented-source"])
def test_unrepresentable_legacy_upgrade_refuses_without_dropping_any_history(checkout, failure):
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=True)
    legacy_paper(checkout, kwargs, document, preserve_cited_claim=failure != "unrepresented-source",
                 empty_claim=failure == "empty-preserved-claim")
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**kwargs)
    assert err.value.code == "SOURCE_CONVERSION_UNSUPPORTED_CHANGE" and err.value.exit_code == 75
    assert before == _snapshot(kwargs["vault_root"])
    assert not (checkout / ".work/convert/source-publication").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_taxonomy_page_retirement_has_explicit_unsupported_refusal(checkout, legacy):
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=legacy)
    taxonomy = [{"axis": "backbone", "slug": "dit"}]
    if legacy:
        legacy_paper(checkout, kwargs, document, taxonomy=taxonomy)
    else:
        metadata = kwargs["metadata"].read_bytes()
        value = json.loads(metadata)
        value["taxonomy"] = taxonomy
        kwargs["metadata"].write_bytes(canonicalize(value))
        publish_conversion(checkout, kwargs)
        kwargs["metadata"].write_bytes(metadata)
    kwargs.update(batch_id="retirement", operation_id="retirement")
    vault = kwargs["vault_root"]
    assert (vault / "wiki/concepts/backbone-dit.md").exists()
    # The explicit complete metadata document drops the only use of this term.
    assert json.loads(kwargs["metadata"].read_bytes())["taxonomy"] == []
    before = _snapshot(vault)
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**kwargs)
    assert err.value.code == "SOURCE_PUBLICATION_UNSUPPORTED_CHANGE" and err.value.exit_code == 75
    assert before == _snapshot(vault)
    assert not (checkout / ".work/retirement/source-publication").exists()
