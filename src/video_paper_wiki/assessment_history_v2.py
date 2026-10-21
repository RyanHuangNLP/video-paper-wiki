"""One assessment chain across explicit legacy and mixed evidence profiles.

These pure inputs do not prove completeness of published history or authenticate
human actors. A retained publisher must preserve the actual stored event prefix.
"""
from __future__ import annotations

import re

from video_paper_wiki import identity
from video_paper_wiki.assessment_history import _event_shape
from video_paper_wiki.markdown_locator import evidence_fingerprint_versioned, evidence_profile
from video_paper_wiki.source_semantics_contracts import EVENT, LIMIT, calendar, fail, preflight, sha, validate

LEGACY_EVENT = "video-paper-wiki.assessment-event.v1"
STATES = {"provisional", "accepted", "contested", "unsupported", "deprecated"}
CLAIM_FIELDS = {"claim_id", "stable_subject_id", "canonical_claim_text", "evidence", "assessment", "reviewed_at"}
CLAIM_ID = re.compile(r"clm-[0-9a-f]{20}")


def validate_claim(claim, at=""):
    preflight(claim, evidence_scope="claim")
    if type(claim) is not dict or set(claim) != CLAIM_FIELDS:
        fail("SCHEMA_INVALID", "claim material must have exactly six canonical fields", at)
    if type(claim["claim_id"]) is not str or not CLAIM_ID.fullmatch(claim["claim_id"]):
        fail("SCHEMA_INVALID", "claim ID grammar is invalid", at + "/claim_id")
    subject, text = claim["stable_subject_id"], claim["canonical_claim_text"]
    if (type(subject) is not str or not subject.startswith(("paper:", "repo:"))
            or not identity.is_stable_subject_id(subject)):
        fail("SCHEMA_INVALID", "claim subject must be a canonical paper or repository", at + "/stable_subject_id")
    if type(text) is not str or not text.strip():
        fail("SCHEMA_INVALID", "claim text must contain a non-whitespace character", at + "/canonical_claim_text")
    if len(text.encode("utf-8")) > 65536:
        fail(LIMIT, "claim text exceeds its UTF-8 byte limit", at + "/canonical_claim_text")
    if type(claim["assessment"]) is not str or claim["assessment"] not in STATES:
        fail("SCHEMA_INVALID", "claim assessment is invalid", at + "/assessment")
    if claim["reviewed_at"] is not None:
        calendar(claim["reviewed_at"], at + "/reviewed_at", timestamp=False)
    evidence_profile(claim["evidence"])
    return claim


def _profile(event):
    return "legacy-v1" if event["schema"] == LEGACY_EVENT else event["evidence_profile"]


def derive_assessment_heads(*, claims, events):
    preflight({"claims": claims, "events": events}, evidence_scope="history")
    if type(claims) is not list or type(events) is not list:
        fail("SCHEMA_INVALID", "claim/history material requires arrays")
    if len(claims) > 4096 or len(events) > 8192:
        fail(LIMIT, "assessment inventory exceeds its bound")
    for index, claim in enumerate(claims):
        validate_claim(claim, f"/claims/{index}")
    for index, event in enumerate(events):
        if type(event) is not dict or type(event.get("schema")) is not str:
            fail("SCHEMA_INVALID", "assessment event discriminator is missing", f"/events/{index}")
        if event["schema"] == LEGACY_EVENT:
            _event_shape(event, f"/events/{index}")
        elif event["schema"] == EVENT:
            validate(event, EVENT)
        else:
            fail("SCHEMA_INVALID", "assessment event schema is unsupported", f"/events/{index}/schema")
    materials, bindings = {}, {}
    for index, claim in enumerate(claims):
        cid = claim["claim_id"]
        material = identity.claim_identity_material(claim["stable_subject_id"], claim["canonical_claim_text"])
        if cid in materials:
            collision = materials[cid] != material
            fail("CLAIM_ID_COLLISION" if collision else "PRIMARY_OWNER_INVALID",
                 "claim ID has duplicate or conflicting owners", f"/claims/{index}/claim_id", exit_code=75 if collision else 2)
        materials[cid] = material
        if cid != identity.claim_id(claim["stable_subject_id"], claim["canonical_claim_text"]):
            fail("CLAIM_ID_MISMATCH", "claim identity material differs", f"/claims/{index}/claim_id")
        bindings[cid] = (claim, sha(claim["canonical_claim_text"].encode("utf-8")),
                         evidence_profile(claim["evidence"]), evidence_fingerprint_versioned(claim["evidence"]))
    by_id, groups = {}, {}
    for index, event in enumerate(events):
        if event["event_id"] in by_id or event["claim_id"] not in bindings:
            fail("ASSESSMENT_CHAIN_INVALID", "event is duplicated or belongs to an unknown claim", f"/events/{index}")
        if event["claim_text_sha256"] != bindings[event["claim_id"]][1]:
            fail("CROSS_OBJECT_IDENTITY_MISMATCH", "event must bind the exact current claim text", f"/events/{index}/claim_text_sha256")
        by_id[event["event_id"]] = event
        groups.setdefault(event["claim_id"], []).append(event)
    heads = {}
    for cid, (claim, _, profile, fingerprint) in sorted(bindings.items()):
        chain = groups.get(cid, [])
        roots, children = [], {}
        for event in chain:
            previous_id = event["previous_event_id"]
            if previous_id is None:
                roots.append(event["event_id"])
                continue
            previous = by_id.get(previous_id)
            if previous is None or previous["claim_id"] != cid or previous_id in children:
                fail("ASSESSMENT_CHAIN_INVALID", "history has a missing, foreign or branching predecessor", "/events")
            children[previous_id] = event["event_id"]
            if (previous["to_assessment"] != event["from_assessment"]
                    or calendar(previous["decided_at"]) > calendar(event["decided_at"])):
                fail("ASSESSMENT_CHAIN_INVALID", "history state or timestamp does not continue its predecessor", "/events")
            if previous["schema"] == EVENT and event["schema"] == LEGACY_EVENT:
                fail("ASSESSMENT_CHAIN_INVALID", "v2 history cannot re-enter the v1 event schema", "/events")
            if (previous["schema"] == LEGACY_EVENT and event["schema"] == EVENT
                    and event["transition_kind"] != "evidence_invalidation"):
                fail("ASSESSMENT_CHAIN_INVALID", "first v2 successor requires explicit evidence invalidation", "/events")
            same_evidence = (_profile(previous), previous["evidence_fingerprint"]) == (_profile(event), event["evidence_fingerprint"])
            if event["transition_kind"] == "human_assessment":
                if previous["to_assessment"] == event["to_assessment"]:
                    fail("ASSESSMENT_CHAIN_INVALID", "human assessment must change state", "/events")
                if not same_evidence:
                    fail("EVIDENCE_FINGERPRINT_MISMATCH", "human review cannot change evidence profile or fingerprint", "/events")
            elif same_evidence:
                fail("EVIDENCE_FINGERPRINT_MISMATCH", "invalidation must change profile or evidence", "/events")
        if len(roots) != 1:
            fail("ASSESSMENT_CHAIN_INVALID", "each claim requires exactly one genesis", "/events")
        seen, cursor = set(), roots[0]
        while cursor not in seen:
            seen.add(cursor)
            if cursor not in children:
                break
            cursor = children[cursor]
        else:
            fail("ASSESSMENT_CHAIN_INVALID", "history contains a cycle", "/events")
        if len(seen) != len(chain):
            fail("ASSESSMENT_CHAIN_INVALID", "history contains disconnected events", "/events")
        head = by_id[cursor]
        if (_profile(head), head["evidence_fingerprint"]) != (profile, fingerprint):
            fail("EVIDENCE_FINGERPRINT_MISMATCH", "history head differs from current evidence", "/events")
        reviewed = head["decided_at"][:10] if head["actor_kind"] == "human" else None
        if claim["assessment"] != head["to_assessment"] or claim["reviewed_at"] != reviewed:
            fail("CROSS_OBJECT_IDENTITY_MISMATCH", "claim assessment or review date differs from its head", "/claims")
        heads[cid] = cursor
    return heads
