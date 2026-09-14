from __future__ import annotations

import copy
import json
import os
import socket
from pathlib import Path

import pytest

from tests.unit.test_domain_proposal import (
    _snapshot,
    _write,
    inspect_file,
    make_world,
    valid_proposal,
)
from tests.unit.test_domain_store import (
    BATCH,
    LATER_AT,
    RECORDED_AT,
    RECORDED_BY,
    REVIEW_AT,
    _add_code_batch,
    _apply_staged,
    _authority_bytes,
    _decision_for,
    _proposal_from,
    _record,
    _relation_review,
    _review,
    _successor_proposal,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_publication import (
    DomainPublicationError,
    compile_domain_publication,
    inspect_domain_publication,
)
from video_paper_wiki.domain_store import (
    DomainStoreError,
    derive_domain_heads,
    load_domain_store,
    review_id_from_record,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA = "video-paper-wiki.domain-proposal-report.v1"
REPORT_SCHEMA_PATH = REPO_ROOT / "schemas" / "video-paper-wiki.domain-proposal-report.v1.schema.json"
B_REF = (
    "https://video-paper-wiki.dev/schemas/video-paper-wiki.domain-proposal.v1.schema.json"
    "#/$defs/project_page_evidence"
)
D_REF = (
    "https://video-paper-wiki.dev/schemas/video-paper-wiki.domain-proposal.v1.schema.json"
    "#/$defs/author_control_evidence"
)
AUTHOR_CONTROL = {
    "kind": "author_control",
    "account": "owner",
    "organization": None,
    "control_evidence": "Synthetic owner control evidence.",
    "context": "Synthetic author-control context.",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _compile(world, batch=BATCH):
    return compile_domain_publication(vault_root=str(world["vault"]), batch_id=batch)


def _inspect(world, batch=BATCH):
    prepared = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return inspect_domain_publication(prepared=str(prepared), vault_root=str(world["vault"]))


def _request(world, batch=BATCH):
    path = world["checkout"] / ".work" / batch / "domain-publication" / "request.json"
    return json.loads(path.read_bytes())


def _expect(fn, code):
    with pytest.raises((DomainPublicationError, DomainStoreError, StagingError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
        assert details.get("next_action")
    return err.value


def _walk(value, path=()):
    if isinstance(value, dict):
        yield value, path
        for key, child in value.items():
            yield from _walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))


def _publication_files(world, batch=BATCH):
    root = world["checkout"] / ".work" / batch / "domain-publication"
    return sorted(str(path.relative_to(world["checkout"])) for path in root.rglob("*") if path.is_file())


def _plant_review_batch(world, annotation_data, *, relied, officiality="official", batch="planted"):
    record = annotation_data["record"]
    lid = record["lineage_id"]
    body = {
        "schema": "video-paper-wiki.domain-review-record.v1",
        "lineage_id": lid,
        "annotation_id": record["annotation_id"],
        "annotation_sha256": sha(canonicalize(record)),
        "previous_review_id": None,
        "actor_kind": "human",
        "decision": "accepted",
        "decided_by": RECORDED_BY,
        "decided_at": REVIEW_AT,
        "reason": "Synthetic planted review.",
        "relation_review": _relation_review(record["report"], officiality, relied=relied),
    }
    review_id = review_id_from_record(body)
    review = {"review_id": review_id, **body}
    raw = canonicalize(review)
    _write(
        world["checkout"] / ".work" / batch / "domain" / "reviews" / lid / (review_id + ".json"),
        raw,
    )
    store, _heads, _authority = load_domain_store(str(world["vault"]))
    store.reviews[review_id] = review
    store.review_raw[review_id] = raw
    chain = store.chains[lid]
    store.chains[lid] = {
        "annotation_order": list(chain["annotation_order"]),
        "review_order": list(chain["review_order"]) + [review_id],
    }
    heads = derive_domain_heads(store)
    _write(world["checkout"] / ".work" / batch / "domain" / "heads.json", canonicalize(heads))
    return review


def test_report_locator_b_and_d_are_closed_refs():
    schema = json.loads(REPORT_SCHEMA_PATH.read_bytes())
    locators = schema["$defs"]["relation_row"]["properties"]["locators"]["properties"]
    assert locators["B"]["anyOf"][0] == {"$ref": B_REF}
    assert locators["D"]["anyOf"][0] == {"$ref": D_REF}
    open_nodes = []
    for node, path in _walk(schema):
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                open_nodes.append("/".join(path))
    assert open_nodes == []


def test_report_locator_b_and_d_samples_and_extra_keys(world):
    report = inspect_file(world, valid_proposal(world))
    validate_document(report, REPORT_SCHEMA)
    nulls = copy.deepcopy(report)
    nulls["relation"]["locators"]["B"] = None
    nulls["relation"]["locators"]["D"] = None
    validate_document(nulls, REPORT_SCHEMA)
    with_d = copy.deepcopy(report)
    with_d["relation"]["locators"]["D"] = dict(AUTHOR_CONTROL)
    validate_document(with_d, REPORT_SCHEMA)
    extra_b = copy.deepcopy(report)
    extra_b["relation"]["locators"]["B"]["extra"] = True
    with pytest.raises(ContractError) as err_b:
        validate_document(extra_b, REPORT_SCHEMA)
    assert err_b.value.code == "SCHEMA_INVALID"
    extra_d = copy.deepcopy(with_d)
    extra_d["relation"]["locators"]["D"]["extra"] = True
    with pytest.raises(ContractError) as err_d:
        validate_document(extra_d, REPORT_SCHEMA)
    assert err_d.value.code == "SCHEMA_INVALID"


def test_compile_record_review_successor_and_idempotent(world):
    vault_before = _snapshot(world["vault"])
    authority_before = _authority_bytes(world)
    first = _record(world, valid_proposal(world), name="g.json", batch="g1")
    prepared = _compile(world, "g1")
    assert prepared["state"] == "domain_publication_prepared"
    assert prepared["publication"] == "unpublished"
    assert prepared["applied"] is False
    assert prepared["receipt_backed"] is False
    assert prepared["audit_coverage"] == "not_wired"
    assert prepared["transaction_authority"] == "not_wired"
    assert prepared["canonical_official"] is False
    assert prepared["current_supported_typed_fact"] is False
    assert prepared["next_action"] == "inspect_domain_publication"
    assert prepared["touched_lineages"] == [first["record"]["lineage_id"]]
    request = _request(world, "g1")
    validate_document(request, "video-paper-wiki.domain-publication-request.v1")
    assert request["kind"] == "domain"
    assert request["publication"] == "unpublished"
    assert request["applied"] is False
    modes = {item["path"]: item for item in request["payloads"]}
    annotation_path = (
        "wiki/meta/domain/annotations/"
        + first["record"]["lineage_id"]
        + "/"
        + first["record"]["annotation_id"]
        + ".json"
    )
    assert set(modes) == {annotation_path, "wiki/meta/domain/heads.json"}
    assert modes[annotation_path]["mode"] == "create"
    assert modes[annotation_path]["before_sha256"] is None
    assert modes["wiki/meta/domain/heads.json"]["mode"] == "create"
    assert modes["wiki/meta/domain/heads.json"]["before_sha256"] is None
    assert prepared["payload_count"] == 2
    assert _snapshot(world["vault"]) == vault_before
    assert _authority_bytes(world) == authority_before
    pub_files = _publication_files(world, "g1")
    assert pub_files
    assert all("/domain-publication/" in path for path in pub_files)
    again = _compile(world, "g1")
    assert canonicalize(again) == canonicalize(prepared)
    assert _request(world, "g1") == request
    assert _publication_files(world, "g1") == pub_files
    inspection = _inspect(world, "g1")
    validate_document(inspection, "video-paper-wiki.domain-publication-inspection.v1")
    assert inspection["basis_verified"] is True
    assert inspection["content_verified"] is True
    assert inspection["publication"] == "unpublished"
    assert inspection["applied"] is False
    assert inspection["receipt_backed"] is False
    assert inspection["audit_coverage"] == "not_wired"
    assert inspection["backup_coverage"] == "not_wired"
    assert inspection["transaction_authority"] == "not_wired"
    assert inspection["canonical_official"] is False
    assert inspection["current_supported_typed_fact"] is False
    assert inspection["next_action"] == "apply_requires_later_slice"
    inspect_again = _inspect(world, "g1")
    assert canonicalize(inspect_again) == canonicalize(inspection)
    old_heads = (world["checkout"] / ".work/g1/domain/heads.json").read_bytes()
    _apply_staged(world, "g1")
    review = _review(world, _decision_for(world, first, officiality="official"), batch="r1")
    reviewed = _compile(world, "r1")
    review_request = _request(world, "r1")
    review_path = (
        "wiki/meta/domain/reviews/"
        + review["record"]["lineage_id"]
        + "/"
        + review["record"]["review_id"]
        + ".json"
    )
    by_path = {item["path"]: item for item in review_request["payloads"]}
    assert by_path[review_path]["mode"] == "create"
    assert by_path["wiki/meta/domain/heads.json"]["mode"] == "replace"
    assert by_path["wiki/meta/domain/heads.json"]["before_sha256"] == sha(old_heads)
    assert reviewed["touched_lineages"] == [first["record"]["lineage_id"]]
    _inspect(world, "r1")
    _apply_staged(world, "r1")
    successor = _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="s1",
    )
    _compile(world, "s1")
    successor_request = _request(world, "s1")
    successor_path = (
        "wiki/meta/domain/annotations/"
        + successor["record"]["lineage_id"]
        + "/"
        + successor["record"]["annotation_id"]
        + ".json"
    )
    successor_map = {item["path"]: item for item in successor_request["payloads"]}
    assert successor_map[successor_path]["mode"] == "create"
    assert successor_map["wiki/meta/domain/heads.json"]["mode"] == "replace"
    assert _snapshot(world["vault"]) != vault_before
    vault_mid = _snapshot(world["vault"])
    _compile(world, "s1")
    assert _snapshot(world["vault"]) == vault_mid
    assert _authority_bytes(world)["taxonomy"] == authority_before["taxonomy"]


def test_compile_refusals_from_valid_batch(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="c1")
    domain = world["checkout"] / ".work/c1/domain"
    heads = domain / "heads.json"
    heads_bytes = heads.read_bytes()
    annotation = next(domain.joinpath("annotations").rglob("*.json"))
    annotation_bytes = annotation.read_bytes()

    heads.unlink()
    err = _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    assert err.details["next_action"]
    _write(heads, heads_bytes)

    extra = domain / "notes.txt"
    extra.write_text("nope", encoding="utf-8")
    os.chmod(extra, 0o600)
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    extra.unlink()

    empty = domain / "annotations" / ("dln-" + "e" * 20)
    empty.mkdir()
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    empty.rmdir()

    link = domain / "link.json"
    os.symlink(annotation, link)
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    link.unlink()

    hard = world["checkout"] / "hardlink-extra"
    os.link(annotation, hard)
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    hard.unlink()

    _write(annotation, json.dumps(json.loads(annotation_bytes), indent=2).encode("utf-8"))
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    _write(annotation, annotation_bytes)

    renamed = annotation.parent / ("dan-" + "a" * 20 + ".json")
    annotation.rename(renamed)
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    renamed.rename(annotation)

    foreign = domain / "annotations" / ("dln-" + "d" * 20)
    foreign.mkdir()
    moved = foreign / annotation.name
    annotation.rename(moved)
    _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_INVALID")
    moved.rename(annotation)
    foreign.rmdir()

    _compile(world, "c1")
    _apply_staged(world, "c1")
    err = _expect(lambda: _compile(world, "c1"), "DOMAIN_COMPILE_ALREADY_PUBLISHED")
    assert err.details["next_action"] == "discard_batch"


def test_compile_stale_after_other_lineage_published(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="st1")
    _apply_staged(world, "st1")
    _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="st2",
    )
    other = _add_code_batch(world, "other", repository="Other/Repo")
    other_proposal = _proposal_from(world, other, repository="Other/Repo")
    _record(world, other_proposal, name="o.json", batch="st3")
    _apply_staged(world, "st3")
    err = _expect(lambda: _compile(world, "st2"), "DOMAIN_COMPILE_STALE")
    assert err.exit_code == 75
    assert err.details["next_action"] == "re_record_or_re_review"


def test_compile_chain_and_officiality_and_freshness_refusals(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="ch1")
    _apply_staged(world, "ch1")
    lid = first["record"]["lineage_id"]
    missing = {
        "schema": "video-paper-wiki.domain-review-record.v1",
        "lineage_id": lid,
        "annotation_id": "dan-" + "0" * 20,
        "annotation_sha256": "a" * 64,
        "previous_review_id": None,
        "actor_kind": "human",
        "decision": "rejected",
        "decided_by": RECORDED_BY,
        "decided_at": REVIEW_AT,
        "reason": "Missing annotation target.",
    }
    missing["review_id"] = review_id_from_record(missing)
    _write(
        world["checkout"] / ".work/miss/domain/reviews" / lid / (missing["review_id"] + ".json"),
        canonicalize(missing),
    )
    _write(
        world["checkout"] / ".work/miss/domain/heads.json",
        canonicalize({"schema": "video-paper-wiki.domain-heads.v1", "heads": {}}),
    )
    _expect(lambda: _compile(world, "miss"), "DOMAIN_STORE_CHAIN_INVALID")

    wrong = {
        "schema": "video-paper-wiki.domain-review-record.v1",
        "lineage_id": lid,
        "annotation_id": first["record"]["annotation_id"],
        "annotation_sha256": "b" * 64,
        "previous_review_id": None,
        "actor_kind": "human",
        "decision": "rejected",
        "decided_by": RECORDED_BY,
        "decided_at": REVIEW_AT,
        "reason": "Wrong annotation digest.",
    }
    wrong["review_id"] = review_id_from_record(wrong)
    _write(
        world["checkout"] / ".work/sha/domain/reviews" / lid / (wrong["review_id"] + ".json"),
        canonicalize(wrong),
    )
    _write(
        world["checkout"] / ".work/sha/domain/heads.json",
        canonicalize({"schema": "video-paper-wiki.domain-heads.v1", "heads": {}}),
    )
    _expect(lambda: _compile(world, "sha"), "DOMAIN_STORE_CHAIN_INVALID")

    _plant_review_batch(world, first, relied=["C"], batch="onlyc")
    err = _expect(lambda: _compile(world, "onlyc"), "DOMAIN_REVIEW_INVALID")
    assert err.details["next_action"] == "repair_review"

    _record(
        world,
        _successor_proposal(world),
        name="fresh.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="fr1",
    )
    kind, claim, old_event = world["annotated"][0]
    from tests.source_semantics_fixture import event_for

    new_event = event_for(claim, previous=old_event, human=True, state="contested")
    _write(
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (new_event["event_id"] + ".json"),
        canonicalize(new_event),
    )
    heads = json.loads((world["vault"] / ASSESSMENT_HEADS).read_bytes())
    heads["heads"][claim["claim_id"]] = {
        "event_id": new_event["event_id"],
        "event_sha256": sha(canonicalize(new_event)),
        "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
    }
    _write(world["vault"] / ASSESSMENT_HEADS, canonicalize(heads))
    err = _expect(lambda: _compile(world, "fr1"), "DOMAIN_HEAD_STALE")
    assert err.details["next_action"] == "re_record_annotation"


def test_compile_empty_limit_and_changed(world, monkeypatch):
    _write(
        world["checkout"] / ".work/empty/domain/heads.json",
        canonicalize({"schema": "video-paper-wiki.domain-heads.v1", "heads": {}}),
    )
    _expect(lambda: _compile(world, "empty"), "DOMAIN_COMPILE_EMPTY")
    _record(world, valid_proposal(world), name="g.json", batch="lim")
    import video_paper_wiki.domain_publication as domain_publication

    original = domain_publication.MAX_STAGED_RECORDS
    domain_publication.MAX_STAGED_RECORDS = 0
    try:
        _expect(lambda: _compile(world, "lim"), "DOMAIN_COMPILE_LIMIT")
    finally:
        domain_publication.MAX_STAGED_RECORDS = original
    from video_paper_wiki.receipt_audit import _Snapshot

    first_read = _Snapshot.read

    def mutating(self, relative, **kwargs):
        raw = first_read(self, relative, **kwargs)
        if relative == "heads.json":
            path = self.root / relative
            path.write_bytes(raw)
            os.chmod(path, 0o600)
        return raw

    monkeypatch.setattr(_Snapshot, "read", mutating)
    err = _expect(lambda: _compile(world, "lim"), "DOMAIN_COMPILE_CHANGED")
    assert err.exit_code == 75
    assert err.details["next_action"] == "repeat_read"


def test_publish_inspect_refusals_and_zero_writes(world):
    first = _record(world, valid_proposal(world), name="g.json", batch="p1")
    _compile(world, "p1")
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    inspection = _inspect(world, "p1")
    assert inspection["request_sha256"] == sha(
        (world["checkout"] / ".work/p1/domain-publication/request.json").read_bytes()
    )
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    request_path = world["checkout"] / ".work/p1/domain-publication/request.json"
    request = json.loads(request_path.read_bytes())
    content_dir = world["checkout"] / ".work/p1/domain-publication/content"
    digest = request["payloads"][0]["after_sha256"]
    content_path = content_dir / digest
    original = content_path.read_bytes()
    content_path.write_bytes(original + b"x")
    os.chmod(content_path, 0o600)
    _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    extra = content_dir / ("c" * 64)
    extra.write_bytes(b"{}")
    os.chmod(extra, 0o600)
    _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_CONTENT_MISMATCH")
    extra.unlink()
    content_path.unlink()
    _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_CONTENT_MISMATCH")
    content_path.write_bytes(original)
    os.chmod(content_path, 0o600)
    _write(request_path, json.dumps(request, indent=2).encode("utf-8"))
    _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_INVALID")
    _write(request_path, canonicalize(request))
    tampered = dict(request)
    tampered["batch_id"] = "other-batch"
    _write(request_path, canonicalize(tampered))
    _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_INVALID")
    _write(request_path, canonicalize(request))
    other = _add_code_batch(world, "pubo", repository="Pub/Other")
    other_proposal = _proposal_from(world, other, repository="Pub/Other")
    _record(world, other_proposal, name="o.json", batch="p2")
    _apply_staged(world, "p2")
    err = _expect(lambda: _inspect(world, "p1"), "DOMAIN_PUBLICATION_STALE")
    assert err.exit_code == 75
    assert err.details["next_action"] == "recompile"
    _record(world, valid_proposal(world), name="g2.json", batch="p3")
    _compile(world, "p3")
    request3_path = world["checkout"] / ".work/p3/domain-publication/request.json"
    request3 = json.loads(request3_path.read_bytes())
    payloads = copy.deepcopy(request3["payloads"])
    for item in payloads:
        if "/annotations/" in item["path"]:
            item["mode"] = "replace"
    request3["payloads"] = payloads
    _write(request3_path, canonicalize(request3))
    _expect(lambda: _inspect(world, "p3"), "DOMAIN_PUBLICATION_MISMATCH")
    err = _expect(
        lambda: inspect_domain_publication(
            prepared=str(world["checkout"] / "proposal.json"),
            vault_root=str(world["vault"]),
        ),
        "WORK_PATH_UNSAFE",
    )
    assert first["publication"] == "unpublished"


def test_compile_zero_network_and_const_guards(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    _record(world, valid_proposal(world), name="n.json", batch="net")
    vault_before = _snapshot(world["vault"])
    first = _compile(world, "net")
    second = _compile(world, "net")
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    inspection = _inspect(world, "net")
    assert inspection["canonical_official"] is False
    assert inspection["current_supported_typed_fact"] is False
    assert (world["vault"] / CLAIM_LEDGER).is_file()
