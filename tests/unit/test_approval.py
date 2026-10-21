from __future__ import annotations

import json
from copy import deepcopy

import pytest

from tests.support import (
    ROOT,
    code_evidence_request,
    complete_ingest_plan,
    make_approval_ref,
    paper_source_request,
)
from video_paper_wiki.approval import (
    APPROVAL_REF_INVALID,
    APPROVAL_REF_MISMATCH,
    PIPELINE_FINGERPRINT_MISMATCH,
    ApprovalError,
    approval_ref_sha256,
    bind_approval_ref,
    parse_approval_ref,
)
from video_paper_wiki.identity import pipeline_fingerprint, plan_approval_hash

PREFLIGHT = ROOT / "tests" / "fixtures" / "preflight"


def _paper_pair() -> tuple[dict, dict]:
    plan = complete_ingest_plan(paper_source_request(local_sha256="a" * 64))
    return plan, make_approval_ref(plan)


def test_fixture_refs_bind_to_completed_fixture_requests() -> None:
    paper_req = json.loads((PREFLIGHT / "paper-source.request.json").read_text(encoding="utf-8"))
    paper_plan = complete_ingest_plan(paper_req)
    paper_ref = json.loads((PREFLIGHT / "paper-source.approval-ref.json").read_text(encoding="utf-8"))
    digest = bind_approval_ref(paper_plan, paper_ref)
    assert digest == approval_ref_sha256(parse_approval_ref(paper_ref))
    code_req = json.loads((PREFLIGHT / "code-evidence.request.json").read_text(encoding="utf-8"))
    code_plan = complete_ingest_plan(code_req)
    code_ref = json.loads((PREFLIGHT / "code-evidence.approval-ref.json").read_text(encoding="utf-8"))
    bind_approval_ref(code_plan, code_ref)


@pytest.mark.parametrize("field", [
    "format",
    "plan_approval_hash",
    "plan_kind",
    "batch_id",
    "stable_subject_id",
    "input_sha256",
    "limits_sha256",
    "network_targets_sha256",
    "pipeline_fingerprint",
])
def test_ref_missing_or_extra_field_is_invalid(field: str) -> None:
    _plan, ref = _paper_pair()
    missing = dict(ref)
    missing.pop(field)
    with pytest.raises(ApprovalError) as exc:
        parse_approval_ref(missing)
    assert exc.value.code == APPROVAL_REF_INVALID
    extra = dict(ref)
    extra["note"] = "no"
    with pytest.raises(ApprovalError) as extra_exc:
        parse_approval_ref(extra)
    assert extra_exc.value.code == APPROVAL_REF_INVALID


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "video-paper-wiki.approval-ref.v0"),
        ("plan_kind", "paper"),
        ("plan_approval_hash", "AA" + "a" * 62),
        ("plan_approval_hash", "z" * 64),
        ("input_sha256", "a" * 63),
        ("batch_id", "batch.1"),
        ("batch_id", "../x"),
        ("stable_subject_id", "paper:not-an-id"),
        ("pipeline_fingerprint", "1" * 63),
    ],
)
def test_ref_grammar_errors_are_invalid(field: str, value: str) -> None:
    _plan, ref = _paper_pair()
    ref[field] = value
    with pytest.raises(ApprovalError) as exc:
        parse_approval_ref(ref)
    assert exc.value.code == APPROVAL_REF_INVALID


@pytest.mark.parametrize(
    "field",
    [
        "plan_approval_hash",
        "plan_kind",
        "batch_id",
        "stable_subject_id",
        "input_sha256",
        "limits_sha256",
        "network_targets_sha256",
        "pipeline_fingerprint",
    ],
)
def test_each_binding_field_mismatch(field: str) -> None:
    plan, ref = _paper_pair()
    if field == "plan_kind":
        ref[field] = "code-evidence"
    elif field == "batch_id":
        ref[field] = "other-batch"
    elif field == "stable_subject_id":
        ref[field] = "paper:arxiv:2204.03458"
    else:
        ref[field] = "e" * 64
    with pytest.raises(ApprovalError) as exc:
        bind_approval_ref(plan, ref)
    assert exc.value.code == APPROVAL_REF_MISMATCH
    assert exc.value.details["field"] == field


def test_recomputed_plan_hash_does_not_rescue_old_ref() -> None:
    plan, ref = _paper_pair()
    tampered = deepcopy(plan)
    tampered["batch_id"] = "other-batch"
    tampered.pop("approval_hash")
    tampered["approval_hash"] = plan_approval_hash(tampered)
    assert tampered["approval_hash"] != plan["approval_hash"]
    with pytest.raises(ApprovalError) as exc:
        bind_approval_ref(tampered, ref)
    assert exc.value.code == APPROVAL_REF_MISMATCH


@pytest.mark.parametrize(
    "mutator,field",
    [
        (lambda p: p.__setitem__("stable_subject_id", "paper:arxiv:2204.03458") or p, "stable_subject_id"),
        (lambda p: p["input"].__setitem__("local_sha256", "f" * 64) or p, "input_sha256"),
        (lambda p: p["limits"].__setitem__("max_pages", 12) or p, "limits_sha256"),
        (lambda p: p.__setitem__("network_targets", [{"url": "https://arxiv.org/pdf/x", "host": "arxiv.org", "method": "GET", "redirect_hosts": [], "max_bytes": 1}]) or p, "network_targets_sha256"),
        (lambda p: p["parser"].__setitem__("config_sha256", "0" * 64) or p, "pipeline_fingerprint"),
    ],
)
def test_tampered_plan_material_rejects_old_ref(mutator, field) -> None:
    request = paper_source_request(local_sha256="a" * 64)
    plan = complete_ingest_plan(request)
    ref = make_approval_ref(plan)
    mutated = deepcopy(plan)
    mutator(mutated)
    mutated.pop("approval_hash", None)
    mutated.pop("pipeline_fingerprint", None)
    mutated["pipeline_fingerprint"] = pipeline_fingerprint(mutated["parser"])
    mutated["approval_hash"] = plan_approval_hash(mutated)
    ref["plan_approval_hash"] = mutated["approval_hash"]
    with pytest.raises(ApprovalError) as exc:
        bind_approval_ref(mutated, ref)
    assert exc.value.code == APPROVAL_REF_MISMATCH
    assert exc.value.details["field"] == field


def test_bind_requires_pipeline_fingerprint_present() -> None:
    plan, ref = _paper_pair()
    plan.pop("pipeline_fingerprint")
    plan["approval_hash"] = plan_approval_hash(plan)
    ref["plan_approval_hash"] = plan["approval_hash"]
    with pytest.raises(ApprovalError) as exc:
        bind_approval_ref(plan, ref)
    assert exc.value.code == PIPELINE_FINGERPRINT_MISMATCH
    assert exc.value.exit_code == 2


def test_bind_plan_fingerprint_mismatch_is_pipeline_error() -> None:
    plan, ref = _paper_pair()
    plan["pipeline_fingerprint"] = "0" * 64
    plan["approval_hash"] = plan_approval_hash(plan)
    ref["plan_approval_hash"] = plan["approval_hash"]
    with pytest.raises(ApprovalError) as exc:
        bind_approval_ref(plan, ref)
    assert exc.value.code == PIPELINE_FINGERPRINT_MISMATCH
    assert exc.value.exit_code == 2


def test_code_evidence_ref_does_not_require_local_sha256() -> None:
    plan = complete_ingest_plan(code_evidence_request())
    ref = make_approval_ref(plan, input_sha256="d" * 64)
    digest = bind_approval_ref(plan, ref)
    assert len(digest) == 64
