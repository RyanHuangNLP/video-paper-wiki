from __future__ import annotations

import copy
import json

import pytest

from tests.source_semantics_fixture import STAMP, compile_fixture, fixture
from tests.source_publication_fixture import knowledge_proposal, registered_source
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import encode_evidence
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_state import (
    _claim_ledger, _role, _snapshots, authorize_catalog_profile, collect_source_state,
    inventory_digest, require_legacy_profile,
)


def claim_ledger():
    material, _ = compile_fixture()
    claim = material["papers"][0]["claims"][0]
    row = {"text": claim["canonical_claim_text"], "risk": "normal", "confidence": "unknown",
           "assessment": "provisional", "reviewed_at": None, "location": {"path": "wiki/papers/paper.md"},
           "evidence": [encode_evidence(x) for x in claim["evidence"]]}
    return {"schema": "claude-obsidian.claim-ledger.v1", "generated_at": STAMP, "claims": {claim["claim_id"]: row}}


@pytest.mark.parametrize("field,value", [("text", ""), ("text", 1), ("risk", "critical"), ("confidence", "certain"),
    ("assessment", "approved"), ("reviewed_at", "2026-02-30"), ("reviewed_at", "2026-09-09T00:00:00Z"),
    ("notes", []), ("supersedes", "../../bad"), ("location", {"path": "wiki/p.md", "extra": True}),
    ("location", {"path": "wiki/p.md", "anchor": []}), ("evidence", None), ("evidence", [{"source_id": "src-a", "relation": "supports", "locator": None}]),
    ("evidence", [{"source_id": "src-a", "relation": "supports"}])])
def test_closed_claim_projection_rejects_unusable_values(field, value):
    ledger = claim_ledger()
    next(iter(ledger["claims"].values()))[field] = value
    with pytest.raises(ContractError) as err:
        _claim_ledger(canonicalize(ledger), structural=False)
    assert "instance_pointer" in err.value.details


@pytest.mark.parametrize("field", ["text", "risk", "assessment", "confidence", "location", "evidence", "reviewed_at"])
def test_full_claim_projection_requires_each_key(field):
    ledger = claim_ledger()
    del next(iter(ledger["claims"].values()))[field]
    with pytest.raises(ContractError):
        _claim_ledger(canonicalize(ledger), structural=False)


def test_legacy_optional_review_presence_preserves_original_bytes():
    ledger = claim_ledger()
    del next(iter(ledger["claims"].values()))["reviewed_at"]
    raw = json.dumps(ledger, indent=2).encode() + b"\n"
    assert "reviewed_at" not in next(iter(_claim_ledger(raw, structural=True)["claims"].values()))
    with pytest.raises(ContractError):
        _claim_ledger(raw, structural=False)


def test_accepted_date_and_contested_rationale_are_required():
    ledger = claim_ledger()
    row = next(iter(ledger["claims"].values()))
    for assessment in ("accepted", "contested"):
        row["assessment"] = assessment
        with pytest.raises(ContractError):
            _claim_ledger(canonicalize(ledger), structural=True)
    row["notes"] = "Explicit synthetic rationale."
    assert _claim_ledger(canonicalize(ledger), structural=False)["claims"] == ledger["claims"]


@pytest.mark.parametrize("path", ["wiki/meta/records/papers/bad.txt", "wiki/meta/records/repos/bad.txt",
    "wiki/meta/records/source-versions/other.json", "wiki/meta/reviews/clm-bad/event.json",
    "wiki/meta/reviews/source-display/bad.json", ".raw/derived/source-ledgers/bad.json",
    ".raw/derived/markdown-source/bad.json", ".raw/derived/code-manifests/bad.json",
    ".raw/derived/" + "a" * 64 + "/docling/unknown.json", "wiki/meta/ledgers/extra.json"])
def test_semantic_namespaces_reject_unknown_filenames(path):
    with pytest.raises(ContractError) as err:
        _role(path)
    assert err.value.code == "SOURCE_PUBLICATION_INVALID"


@pytest.mark.parametrize("path", [ASSESSMENT_HEADS, DISPLAY_HEADS, "wiki/meta/records/source-versions/invalid.json",
    "wiki/meta/reviews/source-display/invalid.json", ".raw/derived/source-ledgers/invalid.json",
    ".raw/derived/markdown-source/invalid.json"])
def test_legacy_guard_runs_before_namespace_filtering(path):
    with pytest.raises(ContractError) as err:
        require_legacy_profile({path: b"invalid json"})
    assert err.value.code == "SOURCE_PROFILE_REQUIRED" and err.value.exit_code == 75


@pytest.mark.parametrize("schema", ["video-paper-wiki.paper-record.v2", "video-paper-wiki.assessment-event.v2"])
def test_legacy_guard_detects_actual_versioned_objects(schema):
    with pytest.raises(ContractError) as err:
        require_legacy_profile({"wiki/meta/records/old-name.json": canonicalize(fixture(schema))})
    assert err.value.code == "SOURCE_PROFILE_REQUIRED"
    require_legacy_profile({"wiki/meta/records/old-opaque.json": b"legacy non-JSON material"})


def test_inventory_hash_binds_mode_exact_bytes_and_utf8_order():
    entries = {"wiki/meta/records/z.json": (sha(b"z"), 1, 0o600), "wiki/meta/records/a.json": (sha(b"a"), 1, 0o600)}
    expected = sha(canonicalize([{"path": p, "sha256": v[0], "size_bytes": v[1], "mode": v[2]} for p, v in sorted(entries.items())]))
    assert inventory_digest(entries) == expected == inventory_digest(dict(reversed(list(entries.items()))))
    entries["wiki/meta/records/a.json"] = (sha(b"a"), 1, 0o400)
    assert inventory_digest(entries) != expected


def test_actual_genesis_and_first_ledger_write_snapshots(checkout):
    vault, _, _, _ = registered_source(checkout)
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        state = collect_source_state(snapshot, audit)
        assert len(state["ledger_snapshots"]) == 2
        _snapshots(state["ledger_snapshots"], state["chain"], None)
        # A later arbitrary claimed/read path does not grant ledger snapshot provenance.
        raw = canonicalize({"schema": "claude-obsidian.source-ledger.v1", "generated_at": "2026-09-08T00:00:00Z", "sources": {}})
        path = ".raw/derived/source-ledgers/" + sha(raw) + ".json"
        with pytest.raises(ContractError) as err:
            _snapshots({path: raw}, state["chain"], None)
        assert err.value.code == "SOURCE_HISTORY_CONFLICT"
    finally:
        snapshot.close()


def test_legacy_registration_migrates_from_actual_historical_bytes(checkout):
    vault, capture, _, _ = registered_source(checkout, legacy=True)
    payloads, _, _ = knowledge_proposal(vault, capture)
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        state = collect_source_state(snapshot, audit, overlay=payloads)
        assert state["profile"] == "source-v1" and len(state["pages"]) == 1
        assert state["claims"][0]["reviewed_at"] is None
        assert state["display_heads"]["heads"] == []
        assert len(state["ledger_snapshots"]) == 1
    finally:
        snapshot.close()


@pytest.mark.parametrize("field", ["event_sha256", "event_id", "evidence_profile"])
def test_derived_assessment_registry_cannot_lie(checkout, field):
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    doc = json.loads(payloads[ASSESSMENT_HEADS])
    next(iter(doc["heads"].values()))[field] = {"event_sha256": "b" * 64, "event_id": "ase-" + "b" * 20, "evidence_profile": "legacy-v1"}[field]
    payloads[ASSESSMENT_HEADS] = canonicalize(doc)
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        with pytest.raises(ContractError) as err:
            collect_source_state(snapshot, audit, overlay=payloads)
        assert err.value.code == "SOURCE_PUBLICATION_INVALID"
    finally:
        snapshot.close()


@pytest.mark.parametrize("schema", ["video-paper-wiki.paper-record.v1", "video-paper-wiki.paper-record.v2"])
@pytest.mark.parametrize("published", ["2026-09-09", "2026-09-09T00:00:00Z", "2026-09-09T00:00:00.123456789Z"])
def test_published_date_retains_both_existing_schema_branches(schema, published):
    from video_paper_wiki.source_state import validate_payload_documents
    doc = fixture(schema)
    doc["published_at"] = published
    raw = canonicalize(doc)
    payloads = {"wiki/meta/records/papers/fixture.json": raw}
    assert validate_payload_documents(payloads) == payloads


@pytest.mark.parametrize("schema", ["video-paper-wiki.paper-record.v1", "video-paper-wiki.paper-record.v2"])
@pytest.mark.parametrize("published", ["2026-02-30", "2026-02-30T00:00:00Z", "2026-09-09T24:00:00Z", "2026-09-09T00:00:00.1234567890Z"])
def test_published_dates_still_require_real_calendar_and_utc_precision(schema, published):
    from video_paper_wiki.source_state import validate_payload_documents
    doc = fixture(schema)
    doc["published_at"] = published
    with pytest.raises(ContractError):
        validate_payload_documents({"wiki/meta/records/papers/fixture.json": canonicalize(doc)})


def _source_catalog_bytes():
    from tests.source_semantics_fixture import claim_for, event_for, locator_for, source_fixture
    from video_paper_wiki.source_publication_contracts import HEADS

    association, raw, _authority = source_fixture()
    evidence = [{**locator_for(association, raw), "relation": "supports"}]
    claim = claim_for(evidence)
    event = event_for(claim)
    ledger = {"schema": "claude-obsidian.claim-ledger.v1", "generated_at": STAMP, "claims": {claim["claim_id"]: {
        "text": claim["canonical_claim_text"], "risk": "normal", "confidence": "unknown", "assessment": "provisional",
        "reviewed_at": None, "location": {"path": "wiki/papers/paper.md", "anchor": "^" + claim["claim_id"]},
        "evidence": [encode_evidence(item) for item in claim["evidence"]], "notes": None, "supersedes": None}}}
    source = {"schema": "claude-obsidian.source-ledger.v1", "generated_at": STAMP, "sources": {association["source_id"]: {
        "origin": {"kind": "file", "locator": association["raw"]["path"]}, "content_kind": "document", "title": "Fixture source",
        "authority": "primary", "review_status": "unreviewed", "pages": [], "content_sha256": association["raw"]["sha256"],
        "ingested_at": "2026-09-08", "retrieved_at": None, "refresh_due": None, "independence_key": None, "supersedes": None}}}
    heads = {"schema": HEADS, "heads": {claim["claim_id"]: {
        "event_id": event["event_id"], "event_sha256": sha(canonicalize(event)), "evidence_profile": event["evidence_profile"]}}}
    return {
        "wiki/meta/records/source-versions/" + association["association_id"] + ".json": canonicalize(association),
        association["raw"]["path"]: raw,
        CLAIM_LEDGER: canonicalize(ledger),
        SOURCE_LEDGER: canonicalize(source),
        ASSESSMENT_HEADS: canonicalize(heads),
        "wiki/meta/reviews/" + claim["claim_id"] + "/" + event["event_id"] + ".json": canonicalize(event),
    }, association


def test_catalog_authorization_checks_source_bytes_and_keeps_the_publication_guard():
    from pathlib import Path

    data, _association = _source_catalog_bytes()
    with pytest.raises(ContractError) as guard:
        require_legacy_profile(data)
    assert guard.value.code == "SOURCE_PROFILE_REQUIRED"
    auth = authorize_catalog_profile(data)
    assert auth["profile"] == "source-v1"
    assert any(item["path"] == ASSESSMENT_HEADS and item["sha256"] == sha(data[ASSESSMENT_HEADS]) for item in auth["bindings"])
    assert all(not item["path"].startswith("video_paper_wiki/") for item in auth["bindings"])
    legacy = authorize_catalog_profile({CLAIM_LEDGER: b"{}"})
    assert legacy == {"profile": "legacy-v1", "skip": frozenset(), "bindings": ()}
    broken = dict(data)
    broken[ASSESSMENT_HEADS] = b"{"
    with pytest.raises(ContractError) as heads:
        authorize_catalog_profile(broken)
    assert heads.value.code != "SOURCE_PROFILE_REQUIRED"
    unknown = dict(data)
    unknown["wiki/meta/records/source-versions/nope.json"] = b"{}"
    with pytest.raises(ContractError):
        authorize_catalog_profile(unknown)
    stray = {"wiki/meta/records/old-name.json": canonicalize(fixture("video-paper-wiki.paper-record.v2"))}
    with pytest.raises(ContractError) as outside:
        authorize_catalog_profile(stray)
    assert outside.value.code != "SOURCE_PROFILE_REQUIRED"
    publication = Path(__file__).resolve().parents[2] / "src/video_paper_wiki/publication.py"
    text = publication.read_text(encoding="utf-8")
    assert "require_legacy_profile" in text
    assert "authorize_catalog_profile" not in text
