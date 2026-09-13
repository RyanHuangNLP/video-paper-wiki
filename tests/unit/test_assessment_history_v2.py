"""Explicit synthetic mixed histories, with unchanged v1 predecessor objects."""
from __future__ import annotations

import copy
import json

import pytest

from tests.source_semantics_fixture import FIXTURES, claim_for, event_for, locator_for, source_fixture
from video_paper_wiki.assessment_history import derive_assessment_heads as legacy_heads
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import assessment_event_id, claim_id


def migration_fixture():
    a, raw, _ = source_fixture()
    old_evidence = json.loads((FIXTURES.parents[1] / "assessment-history/complete-vectors.json").read_bytes())["evidence"]["code"]
    claim = claim_for([old_evidence])
    genesis = event_for(claim, legacy=True)
    approved = event_for(claim, previous=genesis, legacy=True, human=True)
    history = [genesis, approved]
    claim["evidence"].append({**locator_for(a, raw), "relation": "supports"})
    invalidated = event_for(claim, previous=approved)
    history.append(invalidated)
    return claim, history


def test_migration_requires_real_v1_predecessors_and_new_review():
    claim, history = migration_fixture()
    old = copy.deepcopy(history[:2])
    assert derive_assessment_heads(claims=[claim], events=list(reversed(history))) == {claim["claim_id"]: history[-1]["event_id"]}
    reviewed = event_for(claim, previous=history[-1], human=True, state="contested")
    history.append(reviewed)
    claim.update(assessment="contested", reviewed_at="2026-09-09")
    assert derive_assessment_heads(claims=[claim], events=history)[claim["claim_id"]] == reviewed["event_id"]
    assert history[:2] == old
    assert claim["claim_id"] == claim_id(claim["stable_subject_id"], claim["canonical_claim_text"])


def test_pure_legacy_histories_retain_heads_and_identity():
    claim, history = migration_fixture()
    claim["evidence"] = claim["evidence"][:1]
    claim.update(assessment="accepted", reviewed_at="2026-09-09")
    old = history[:2]
    assert derive_assessment_heads(claims=[claim], events=old) == legacy_heads(claims=[claim], events=old)


@pytest.mark.parametrize("case", ["human_migration", "human_profile_change", "same_evidence_invalidation", "schema_reentry", "missing_predecessor", "duplicate", "branch", "foreign_claim", "backwards", "wrong_text", "wrong_state", "wrong_date", "wrong_evidence", "empty_history", "same_human_state"])
def test_invalid_migration_transition_and_mirror_refuse(case):
    claim, history = migration_fixture()
    if case == "human_migration":
        history[-1] = event_for(claim, previous=history[1], human=True)
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
    elif case == "human_profile_change":
        history.append(event_for(claim, previous=history[-1], human=True, evidence_profile="legacy-v1"))
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
    elif case == "same_evidence_invalidation":
        history.append(event_for(claim, previous=history[-1]))
    elif case == "schema_reentry":
        history.append(event_for(claim, previous=history[-1], human=True, legacy=True))
    elif case == "missing_predecessor":
        history.pop(1)
    elif case == "duplicate":
        history.append(history[-1])
    elif case == "branch":
        history.append(event_for(claim, previous=history[1], reason="Competing synthetic branch."))
    elif case == "foreign_claim":
        history[-1]["claim_id"] = "clm-" + "0" * 20
    elif case == "backwards":
        history[-1]["decided_at"] = "2026-09-08T23:59:59Z"
    elif case == "wrong_text":
        history[-1]["claim_text_sha256"] = "0" * 64
    elif case == "wrong_state":
        claim["assessment"] = "accepted"
    elif case == "wrong_date":
        claim["reviewed_at"] = "2026-09-09"
    elif case == "wrong_evidence":
        claim["evidence"][-1]["relation"] = "contradicts"
    elif case == "empty_history":
        history = []
    else:
        one = event_for(claim, previous=history[-1], human=True)
        history.extend([one, event_for(claim, previous=one, human=True, reason="Same-state synthetic event.")])
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
    if history:
        history[-1]["event_id"] = assessment_event_id(history[-1])
    with pytest.raises(ContractError) as caught:
        derive_assessment_heads(claims=[claim], events=history)
    assert caught.value.code in {"ASSESSMENT_CHAIN_INVALID", "EVIDENCE_FINGERPRINT_MISMATCH", "CROSS_OBJECT_IDENTITY_MISMATCH"}


@pytest.mark.parametrize("field,value", [("evidence", None), ("reviewed_at", "2026-02-30"), ("assessment", []), ("canonical_claim_text", " "), ("stable_subject_id", "paper:invalid")])
def test_claim_shape_fails_before_graph_traversal(field, value):
    claim, history = migration_fixture()
    claim[field] = value
    with pytest.raises(ContractError) as caught:
        derive_assessment_heads(claims=[claim], events=history)
    assert caught.value.code in {"SCHEMA_INVALID", "MARKDOWN_LOCATOR_INVALID"}


def test_duplicate_claims_and_identity_changes_are_not_reassigned():
    claim, history = migration_fixture()
    with pytest.raises(ContractError):
        derive_assessment_heads(claims=[claim, claim], events=history)
    claim["claim_id"] = "clm-" + "0" * 20
    with pytest.raises(ContractError) as caught:
        derive_assessment_heads(claims=[claim], events=history)
    assert caught.value.code == "CLAIM_ID_MISMATCH"


def test_subsecond_order_is_exact_without_float_rounding():
    claim, history = migration_fixture()
    history[0]["decided_at"] = "2026-09-09T00:00:00.000000002Z"
    history[0]["event_id"] = assessment_event_id(history[0])
    history[1]["previous_event_id"] = history[0]["event_id"]
    history[1]["decided_at"] = "2026-09-09T00:00:00.000000001Z"
    history[1]["event_id"] = assessment_event_id(history[1])
    history[2]["previous_event_id"] = history[1]["event_id"]
    history[2]["event_id"] = assessment_event_id(history[2])
    with pytest.raises(ContractError) as caught:
        derive_assessment_heads(claims=[claim], events=history)
    assert caught.value.code == "ASSESSMENT_CHAIN_INVALID"
