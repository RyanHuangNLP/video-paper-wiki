"""Complete synthetic golden pages and hostile prospective compiler material."""
from __future__ import annotations

import copy
import json

import pytest

from tests.source_semantics_fixture import (
    GOLDEN_AUTHORITY, GOLDEN_LEGACY, GOLDEN_LEGACY_PAGES, GOLDEN_MIXED, GOLDEN_MIXED_PAGES,
    claim_for, compile_fixture, event_for, inventory_arguments, locator_for, selection,
)
from video_paper_wiki.canonical_compiler import compile_pages as compile_v1
from video_paper_wiki.canonical_compiler_v2 import compile_pages, concept_items_for_papers
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_semantics_contracts import COMPILE, association_reference, decision_reference
from video_paper_wiki.source_versions import associate_source

EMPTY = {"raw_sources": {}, "extraction_artifacts": {}, "registration_ledgers": {}, "head_bytes": None, "receipt_bytes": {}}


def test_complete_independently_reviewed_legacy_and_mixed_golden_pages():
    expected_old = {p: text.encode() for p, text in GOLDEN_LEGACY_PAGES.items()}
    expected_mixed = {p: text.encode() for p, text in GOLDEN_MIXED_PAGES.items()}
    assert compile_v1(GOLDEN_LEGACY) == expected_old
    assert compile_pages(GOLDEN_LEGACY | {"schema": COMPILE}, **EMPTY) == expected_old
    actual = compile_pages(GOLDEN_MIXED, **GOLDEN_AUTHORITY)
    assert actual == expected_mixed
    assert list(actual) == sorted(actual)
    for path in expected_old:
        if path.startswith(("wiki/papers/", "wiki/code/")):
            assert actual[path] == expected_old[path]


def test_provisional_unselected_claim_keeps_evidence_without_inventing_conclusion():
    material, kwargs = compile_fixture()
    group = material["papers"][0]
    output = next(iter(compile_pages(material, **kwargs).values())).decode()
    conclusion = output.split("## 一句话结论\n", 1)[1].split("\n## ", 1)[0]
    assert conclusion == "\n- 暂无已审核的核心结论。\n"
    assert "- 展示版本：未选择。" in output and "未知版本 (unknown)" in output
    assert "display_head: null" in output and "active_extraction_path: null" in output
    assert output.count("^" + group["claims"][0]["claim_id"]) == 1
    evidence = output.split("## 证据状态\n", 1)[1]
    assert "assessment: `provisional`" in evidence and "[Markdown]" in evidence


def test_selected_version_does_not_rewrite_old_claim_evidence_or_assessment():
    material, kwargs = compile_fixture(selected=True, accepted=True)
    group = material["papers"][0]
    old = group["associations"][0]
    prior_claims = copy.deepcopy((group["claims"], group["events"]))
    observation = copy.deepcopy(old["observation"])
    observation["version"] = {"kind": "declared", "label": "newer local label"}
    authority = {"head_bytes": kwargs["head_bytes"], "receipt_bytes": kwargs["receipt_bytes"], "ledger_bytes": next(iter(kwargs["registration_ledgers"].values()))}
    raw = kwargs["raw_sources"][old["raw"]["path"]]
    new = associate_source(observation, raw_bytes=raw, existing=[old], **authority)["association"]
    group["associations"] = sorted([old, new], key=lambda x: x["association_id"])
    group["record"]["source_associations"] = [association_reference(a) for a in group["associations"]]
    decision = selection(new, previous=group["display_decisions"][-1])
    group["display_decisions"].append(decision)
    group["record"].update(display_head=decision_reference(decision), active_extraction_path=new["extraction"]["path"], active_extraction_sha256=new["extraction"]["sha256"])
    kwargs = inventory_arguments([old, new], raw, authority)
    output = next(iter(compile_pages(material, **kwargs).values())).decode()
    assert f"- 展示版本：newer local label；association: `{new['association_id']}`" in output
    evidence_line = next(line for line in output.splitlines() if line.startswith("  - evidence:"))
    assert old["association_id"] in evidence_line and new["association_id"] not in evidence_line
    assert prior_claims == (group["claims"], group["events"])


def test_escaping_and_related_links_do_not_rewrite_untrusted_claim_text():
    material = copy.deepcopy(GOLDEN_MIXED)
    group = material["papers"][1]
    group["record"]["title_zh"] = '[title] `x` <script>alert(1)</script>\n---'
    text = 'A [[wiki]] `code` <script>x</script> - 暂无已发布的关联索引。'
    claim = claim_for(group["claims"][0]["evidence"], text=text, subject="paper:" + group["record"]["paper_id"])
    events = [event_for(claim)]
    events.append(event_for(claim, previous=events[0], human=True))
    claim.update(assessment="accepted", reviewed_at="2026-09-09")
    group["claims"], group["events"] = [claim], events
    group.pop("assessment_heads", None)
    group["record"]["section_claim_refs"][0]["claim_id"] = claim["claim_id"]
    output = compile_pages(material, **GOLDEN_AUTHORITY)["wiki/papers/arxiv-2311.15128.md"].decode()
    assert '# \\[title\\] \\`x\\` &lt;script&gt;alert(1)&lt;/script&gt; ---' in output
    assert 'A \\[\\[wiki\\]\\] \\`code\\` &lt;script&gt;x&lt;/script&gt; - 暂无已发布的关联索引。' in output
    assert output.count("[[../concepts/backbone-dit|backbone-dit]]") == 1
    fm = output.split("---\n", 2)[1]
    title_json = next(line for line in fm.splitlines() if line.startswith("title_zh: "))[10:]
    assert json.loads(title_json) == group["record"]["title_zh"]


@pytest.mark.parametrize("case", ["duplicate_paper", "claim_owner", "missing_claim", "duplicate_ref", "canonical_alias", "explicit_arxiv", "unknown_taxonomy", "missing_concept", "forged_label", "orphan_concept", "missing_association", "association_hash", "display_hash", "extraction_mirror", "source_ids", "assessment_head", "missing_evidence_association", "duplicate_code"])
def test_prospective_cross_object_failures(case):
    material = copy.deepcopy(GOLDEN_MIXED)
    group = material["papers"][1]
    if case == "duplicate_paper":
        material["papers"].append(copy.deepcopy(group))
    elif case == "claim_owner":
        group["claims"][0]["stable_subject_id"] = "paper:arxiv:2311.15127"
    elif case == "missing_claim":
        group["claims"] = []
    elif case == "duplicate_ref":
        group["record"]["section_claim_refs"].append(group["record"]["section_claim_refs"][0])
    elif case == "canonical_alias":
        group["record"]["aliases"].append("arxiv:2311.15127")
    elif case == "explicit_arxiv":
        group["record"]["arxiv_id"] = "2311.15129"
    elif case == "unknown_taxonomy":
        group["record"]["taxonomy"][0]["slug"] = "unknown-term"
    elif case == "missing_concept":
        material["concepts"] = []
    elif case == "forged_label":
        material["concepts"][0]["label_zh"] = "Forged label"
    elif case == "orphan_concept":
        material["concepts"].append({"axis": "task/conditioning", "slug": "text-to-video", "label_zh": "文生视频", "label_en": "text-to-video"})
    elif case == "missing_association":
        group["record"]["source_associations"] = []
    elif case == "association_hash":
        group["record"]["source_associations"][0]["sha256"] = "0" * 64
    elif case == "display_hash":
        group["record"]["display_head"]["sha256"] = "0" * 64
    elif case == "extraction_mirror":
        group["record"]["active_extraction_sha256"] = "0" * 64
    elif case == "source_ids":
        group["record"]["source_ids"] = []
    elif case == "assessment_head":
        group["assessment_heads"] = {}
    elif case == "missing_evidence_association":
        loc = next(x for x in group["claims"][0]["evidence"] if x["kind"] == "markdown")
        loc["association"]["association_id"] = "sva-" + "0" * 64
    else:
        material["code"].append(copy.deepcopy(material["code"][0]))
    with pytest.raises(ContractError) as caught:
        compile_pages(material, **GOLDEN_AUTHORITY)
    assert caught.value.code in {"COMPILE_INPUT_INVALID", "SOURCE_DISPLAY_INVALID", "SOURCE_ASSOCIATION_INVALID", "SCHEMA_INVALID", "EVIDENCE_FINGERPRINT_MISMATCH"}


@pytest.mark.parametrize("case", ["empty", "retired", "other_section", "noncore"])
def test_provisional_and_retired_pages_still_show_honest_status(case):
    material, kwargs = compile_fixture(accepted=True)
    group = material["papers"][0]
    if case == "empty":
        group["claims"], group["events"], group["record"]["section_claim_refs"] = [], [], []
    elif case == "retired":
        group["record"]["section_claim_refs"][0]["lifecycle"] = "retired"
    elif case == "other_section":
        group["record"]["section_claim_refs"][0]["section"] = "method"
    else:
        group["record"]["section_claim_refs"][0]["core"] = False
    output = next(iter(compile_pages(material, **kwargs).values())).decode()
    assert "- 暂无已审核的核心结论。" in output
    if case != "empty":
        assert output.count("^" + group["claims"][0]["claim_id"]) == 1
        assert "  - evidence:" in output


def test_four_eligible_core_conclusions_are_refused():
    material, kwargs = compile_fixture()
    group = material["papers"][0]
    evidence = group["claims"][0]["evidence"]
    group["claims"], group["events"], group["record"]["section_claim_refs"] = [], [], []
    for number in range(4):
        claim = claim_for(evidence, text=f"Synthetic conclusion {number}.")
        genesis = event_for(claim)
        human = event_for(claim, previous=genesis, human=True)
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
        group["claims"].append(claim)
        group["events"].extend([genesis, human])
        group["record"]["section_claim_refs"].append({"section": "one_sentence_conclusion", "claim_id": claim["claim_id"], "core": True, "lifecycle": "active"})
    with pytest.raises(ContractError) as caught:
        compile_pages(material, **kwargs)
    assert caught.value.code == "COMPILE_INPUT_INVALID"


def test_concept_inventory_is_complete_pinned_and_order_independent():
    records = [g["record"] for g in GOLDEN_MIXED["papers"]]
    assert concept_items_for_papers(records) == GOLDEN_MIXED["concepts"]
    assert concept_items_for_papers(list(reversed(records))) == GOLDEN_MIXED["concepts"]
    assert compile_pages({"schema": COMPILE, "operation_id": "empty", "papers": [], "code": [], "concepts": []}, **EMPTY) == {}


def test_legacy_only_cannot_smuggle_unrelated_source_authority():
    with pytest.raises(ContractError) as caught:
        compile_pages(GOLDEN_LEGACY | {"schema": COMPILE}, **GOLDEN_AUTHORITY)
    assert caught.value.code == "SOURCE_INVENTORY_INVALID"


@pytest.mark.parametrize("field", ["record", "claim", "event", "decision"])
def test_calendar_errors_precede_actual_competing_owner_graph_error(field):
    material = copy.deepcopy(GOLDEN_MIXED)
    group = material["papers"][1]
    group["record"]["aliases"].append(material["papers"][0]["record"]["paper_id"])
    if field == "record":
        group["record"]["updated_at"] = "2026-02-30T00:00:00Z"
    elif field == "claim":
        group["claims"][0]["reviewed_at"] = "2026-02-30"
    elif field == "event":
        group["events"][0]["decided_at"] = "2026-02-30T00:00:00Z"
    else:
        group["display_decisions"][0]["decided_at"] = "2026-02-30T00:00:00Z"
    with pytest.raises(ContractError) as caught:
        compile_pages(material, **GOLDEN_AUTHORITY)
    assert caught.value.code == "SCHEMA_INVALID"
    assert caught.value.details["instance_pointer"].startswith("/papers/1/")


@pytest.mark.parametrize("case", ["claim", "code_officiality"])
def test_legacy_float_bbox_slots_keep_exact_v1_compiler_behavior(case):
    from tests.source_semantics_fixture import FIXTURES
    material = copy.deepcopy(GOLDEN_LEGACY)
    if case == "code_officiality":
        material["code"][0]["alignment"]["officiality"]["evidence"][0]["bbox"] = [0.5, 2.5, 10.25, 20.75]
    else:
        group = material["papers"][0]
        claim = group["claims"][0]
        pdf = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["pdf"]
        claim["evidence"] = [pdf]
        genesis = event_for(claim, legacy=True)
        human = event_for(claim, legacy=True, previous=genesis, human=True)
        group["events"] = [genesis, human]
        group["assessment_heads"] = {claim["claim_id"]: human["event_id"]}
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
    assert compile_pages(material | {"schema": COMPILE}, **EMPTY) == compile_v1(material)


@pytest.mark.parametrize("case", ["metadata", "event", "association", "wrong_code_slot", "markdown_bbox"])
def test_coincidental_pdf_object_elsewhere_does_not_bypass_preflight(case):
    material = copy.deepcopy(GOLDEN_MIXED)
    group = material["papers"][1]
    fake = {"kind": "pdf", "bbox": [0.5, 1.0, 2.0, 3.0]}
    if case == "metadata":
        group["record"]["extra"] = fake
    elif case == "event":
        group["events"][0]["extra"] = fake
    elif case == "association":
        group["associations"][0]["extra"] = fake
    elif case == "wrong_code_slot":
        material["code"][0]["extra"] = fake
    else:
        next(x for x in group["claims"][0]["evidence"] if x["kind"] == "markdown")["bbox"] = fake["bbox"]
    with pytest.raises(ContractError) as caught:
        compile_pages(material, **GOLDEN_AUTHORITY)
    assert caught.value.code == "SOURCE_SEMANTICS_INVALID"


def test_mixed_compiler_accepts_old_pdf_display_bbox_and_exact_markdown_evidence():
    from tests.source_semantics_fixture import FIXTURES
    material = copy.deepcopy(GOLDEN_MIXED)
    group = material["papers"][1]
    pdf = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["pdf"]
    claim = group["claims"][0]
    claim["evidence"].append(pdf)
    genesis = event_for(claim)
    human = event_for(claim, previous=genesis, human=True)
    group["events"], group["assessment_heads"] = [genesis, human], {claim["claim_id"]: human["event_id"]}
    claim.update(assessment="accepted", reviewed_at="2026-09-09")
    group["record"]["source_ids"] = sorted({*group["record"]["source_ids"], pdf["source_id"]})
    page = compile_pages(material, **GOLDEN_AUTHORITY)["wiki/papers/arxiv-2311.15128.md"].decode()
    assert "[PDF text artifact]" in page and "[Markdown]" in page
    assert page.count("  - evidence:") == 3
