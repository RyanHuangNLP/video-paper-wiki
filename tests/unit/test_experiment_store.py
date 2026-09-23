from __future__ import annotations

import copy
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import SRC_BODY, write_bytes
from tests.source_semantics_fixture import event_for, source_fixture
from tests.unit.test_domain_apply import _apply, _compile
from tests.unit.test_domain_proposal import _snapshot, _write, make_world, valid_proposal
from tests.unit.test_domain_store import (
    LATER_AT,
    RECORDED_AT,
    RECORDED_BY,
    _record,
    _successor_proposal,
)
from tests.unit.test_domain_versions import _reseal_association
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_store import DomainStoreError, load_domain_store, status_domain_store
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_store import (
    ExperimentStoreError,
    condition_id_from_record,
    content_sha256_from_record,
    experiment_inventory_digest,
    load_experiment_store,
    record_experiment_condition,
    record_id_from_record,
    status_experiment_store,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import evidence_fingerprint_versioned
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

BATCH = "e1"
DOC_BODY = b'{"text":"512x512 vbench table"}'


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _apply_staged_experiments(world, batch=BATCH):
    staged_root = world["checkout"] / ".work" / batch / "experiments"
    dest_root = world["vault"] / "wiki/meta/experiments"
    for path in sorted(p for p in staged_root.rglob("*") if p.is_file()):
        target = dest_root / path.relative_to(staged_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        os.chmod(target, 0o600)


def _document(world):
    digest = sha(DOC_BODY)
    rel = ".raw/derived/" + digest + "/document.json"
    _write(world["vault"] / rel, DOC_BODY)
    return rel, digest


def _empirical(world):
    return next(item for item in world["annotated"] if item[0] == "empirical_result")


def _paper_direct(world, rel, digest, context="table 2"):
    return {
        "kind": "paper_direct",
        "locator": {
            "kind": "pdf",
            "source_id": world["association"]["source_id"],
            "page": 1,
            "ref": "#/texts/1",
            "artifact_path": rel,
            "artifact_sha256": digest,
            "text_sha256": digest,
            "context": context,
        },
        "quote_sha256": digest,
    }


def _project_page(world):
    return {
        "kind": "project_page",
        "locator": {
            "kind": "project_page",
            "url": "https://example.invalid/paper",
            "local_digest": {
                "path": world["page_rel"],
                "sha256": sha(world["page_body"]),
                "size_bytes": len(world["page_body"]),
            },
            "fragment": {
                "start": 0,
                "end": len(world["page_body"]),
                "text_sha256": sha(world["page_body"]),
            },
        },
        "quote_sha256": sha(world["page_body"]),
    }


def _repo_text(world):
    body = SRC_BODY
    return {
        "kind": "repository_text",
        "locator": {
            "kind": "repository_text",
            "path": "src.py",
            "commit": world["repo"]["commit_oid"],
            "local_digest": {"sha256": sha(body), "size_bytes": len(body)},
            "fragment": {"start": 0, "end": len(body), "text_sha256": sha(body)},
        },
        "quote_sha256": sha(body),
    }


def _reported(value, source):
    return {"status": "reported", "value": value, "basis_note": None, "sources": [source], "search_scope": None}


def _derived(value, source, note):
    return {"status": "derived", "value": value, "basis_note": note, "sources": [source], "search_scope": None}


def _unknown():
    return {
        "status": "unknown",
        "value": None,
        "basis_note": None,
        "sources": [],
        "search_scope": {"artifact_paths": ["wiki/papers/paper.md"], "search_terms": ["resolution"]},
    }


def _n_a():
    return {"status": "not_applicable", "value": None, "basis_note": None, "sources": [], "search_scope": None}


def valid_condition_input(world, **overrides):
    rel, digest = _document(world)
    paper = _paper_direct(world, rel, digest)
    page = _project_page(world)
    _kind, claim, event = _empirical(world)
    payload = {
        "paper_id": world["association"]["paper_id"],
        "source_association": {
            "association_id": world["association"]["association_id"],
            "sha256": sha(world["assoc_raw"]),
        },
        "source_digest": {
            "path": world["association"]["raw"]["path"],
            "sha256": world["association"]["raw"]["sha256"],
            "size_bytes": world["association"]["raw"]["size_bytes"],
        },
        "code_binding": None,
        "setting_key": "table2-row3-vbench-512",
        "conditions": {
            "model_checkpoint": _reported(
                {"name": "demo-vbench", "checkpoint_ref": "hf:demo", "checkpoint_sha256": "1" * 64},
                paper,
            ),
            "parameter_count": _derived({"count": 1000000, "basis": "total"}, page, "From the model card."),
            "dataset_split": _reported({"dataset": "vbench", "split": "test", "subset": None}, paper),
            "metrics": _reported(
                [
                    {
                        "name": "fvd",
                        "unit": "fvd",
                        "value": 100,
                        "higher_is_better": False,
                        "definition_source": paper,
                    }
                ],
                paper,
            ),
            "resolution": _reported({"width": 512, "height": 512}, paper),
            "frames": _reported({"count": 16, "fps": 8}, paper),
            "inference_steps": _n_a(),
            "sampling_guidance": _reported({"guidance_scale": 7, "sampler": "ddim", "seed": 1}, paper),
            "evaluation_setup": _reported(
                {"protocol": "vbench-official", "num_samples": 100, "evaluator": "vbench"},
                page,
            ),
        },
        "claim_refs": [
            {
                "claim_id": claim["claim_id"],
                "claim_kind": "empirical_result",
                "claim_text": claim["canonical_claim_text"],
                "evidence_fingerprint": evidence_fingerprint_versioned(claim["evidence"]),
                "assessment_head": {
                    "event_id": event["event_id"],
                    "event_sha256": sha(canonicalize(event)),
                    "evidence_profile": event.get("evidence_profile", "legacy-v1"),
                },
            }
        ],
    }
    for key, value in overrides.items():
        if key == "conditions":
            payload["conditions"].update(copy.deepcopy(value))
        else:
            payload[key] = copy.deepcopy(value)
    return payload


def _write_input(world, payload, name="condition.json"):
    path = world["checkout"] / name
    write_bytes(path, canonicalize(payload) + b"\n")
    return path


def _record_exp(world, payload=None, *, name="condition.json", previous=None, recorded_at=RECORDED_AT, batch=BATCH, **overrides):
    payload = valid_condition_input(world, **overrides) if payload is None else payload
    path = _write_input(world, payload, name)
    return record_experiment_condition(
        input_path=str(path),
        vault_root=str(world["vault"]),
        batch_id=batch,
        recorded_by=RECORDED_BY,
        recorded_at=recorded_at,
        previous_record_id=previous,
    )


def _status(world, paper_id=None):
    return status_experiment_store(vault_root=str(world["vault"]), paper_id=paper_id)


def _expect(fn, code):
    with pytest.raises((ExperimentStoreError, DomainStoreError, StagingError)) as err:
        fn()
    assert err.value.code == code
    details = getattr(err.value, "details", {}) or {}
    assert details.get("next_action")
    if code != "WORK_PATH_UNSAFE":
        assert details.get("instance_pointer") is not None
    return err.value


def _consts(data):
    assert data["publication"] == "unpublished"
    assert data["audit_coverage"] == "not_wired"
    assert data["code_freshness"] == "not_checked"
    assert data["code_source_verification"] == "not_checked"
    assert data["ranking"] == "not_ranked"
    assert data["typed_fact_promotion"] == "none"
    assert data["canonical_official"] is False
    assert data["current_supported_typed_fact"] is False


def _work_outside_experiments(world, batch=BATCH):
    work = world["checkout"] / ".work"
    out = {}
    if not work.exists():
        return out
    for path in work.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(work)
        if rel.parts[:2] == (batch, "experiments"):
            continue
        out[str(rel)] = path.read_bytes()
    return out


def test_record_positive_example(world):
    payload = valid_condition_input(world)
    vault_before = _snapshot(world["vault"])
    work_before = _work_outside_experiments(world)
    data = _record_exp(world, payload)
    record = data["record"]
    validate_document(record, "video-paper-wiki.experiment-condition-record.v1")
    assert record["record_id"] == record_id_from_record(record)
    assert record["condition_id"] == condition_id_from_record(record)
    assert record["content_sha256"] == content_sha256_from_record(record)
    assert record["previous_record_id"] is None
    _consts(data)
    assert data["next_action"] == "publication_requires_later_slice"
    assert len(data["heads"]["heads"]) == 1
    staged = {item["relative"]: item for item in data["staged"]}
    cid = record["condition_id"]
    rid = record["record_id"]
    rec_rel = "experiments/records/" + cid + "/" + rid + ".json"
    assert rec_rel in staged
    assert staged[rec_rel]["destination"] == "wiki/meta/experiments/records/" + cid + "/" + rid + ".json"
    assert "experiments/heads.json" in staged
    assert staged["experiments/heads.json"]["destination"] == "wiki/meta/experiments/heads.json"
    raw = (world["checkout"] / ".work" / BATCH / rec_rel).read_bytes()
    assert data["heads"]["heads"][cid]["record_sha256"] == sha(raw)
    assert _snapshot(world["vault"]) == vault_before
    assert _work_outside_experiments(world) == work_before
    again = _record_exp(world, name="condition-again.json")
    assert canonicalize(again["record"]) == canonicalize(record)


def test_search_scope_raw_captured_derived_and_rejected_paths(world):
    captured = world["association"]["raw"]["path"]
    derived, _digest = _document(world)
    for path, key, batch in (
        (captured, "raw-captured", "rawcap"),
        (derived, "raw-derived", "rawder"),
        ("wiki/papers/paper.md", "raw-portable", "rawport"),
    ):
        payload = valid_condition_input(world, setting_key=key, claim_refs=[])
        payload["conditions"]["resolution"] = _unknown()
        payload["conditions"]["resolution"]["search_scope"] = {
            "artifact_paths": [path],
            "search_terms": ["resolution"],
        }
        data = _record_exp(world, payload, name=key + ".json", batch=batch)
        assert data["record"]["conditions"]["resolution"]["search_scope"]["artifact_paths"] == [path]
        assert data["record"]["record_id"] == record_id_from_record(data["record"])
    payload = valid_condition_input(world, setting_key="raw-bad", claim_refs=[])
    payload["conditions"]["resolution"] = _unknown()
    payload["conditions"]["resolution"]["search_scope"] = {
        "artifact_paths": ["/tmp/x.md"],
        "search_terms": ["resolution"],
    }
    err = _expect(lambda: _record_exp(world, payload, name="raw-bad.json", batch="rawbad"), "EXPERIMENT_RECORD_INVALID")
    assert "artifact_paths" in err.details.get("instance_pointer", "")
    for path in (".work/x.json", ".git/config", "wiki/papers/../code/x.md", "https://example.invalid/x"):
        bad = valid_condition_input(world, setting_key="raw-rej", claim_refs=[])
        bad["conditions"]["resolution"] = _unknown()
        bad["conditions"]["resolution"]["search_scope"] = {
            "artifact_paths": [path],
            "search_terms": ["resolution"],
        }
        err = _expect(lambda: _record_exp(world, bad, name="raw-rej.json", batch="rawrej"), "EXPERIMENT_RECORD_INVALID")
        assert "artifact_paths" in err.details.get("instance_pointer", "")


def test_successor_and_new_lineages(world):
    first = _record_exp(world, batch="s1")
    _apply_staged_experiments(world, "s1")
    changed = valid_condition_input(world, conditions={"resolution": _reported({"width": 256, "height": 256}, valid_condition_input(world)["conditions"]["resolution"]["sources"][0])})
    second = _record_exp(
        world,
        changed,
        name="succ.json",
        previous=first["record"]["record_id"],
        recorded_at=LATER_AT,
        batch="s2",
    )
    assert second["record"]["previous_record_id"] == first["record"]["record_id"]
    assert second["record"]["condition_id"] == first["record"]["condition_id"]
    assert list(second["heads"]["heads"]) == [first["record"]["condition_id"]]
    assert second["heads"]["heads"][first["record"]["condition_id"]]["record_id"] == second["record"]["record_id"]
    _expect(lambda: _record_exp(world, changed, name="noprev.json", recorded_at=LATER_AT, batch="s3"), "EXPERIMENT_RECORD_PREVIOUS_MISMATCH")
    err = _expect(
        lambda: _record_exp(
            world,
            changed,
            name="wrongprev.json",
            previous="exr-" + "a" * 20,
            recorded_at=LATER_AT,
            batch="s4",
        ),
        "EXPERIMENT_RECORD_PREVIOUS_MISMATCH",
    )
    assert err.details["next_action"] == "supply_previous"
    assert err.details["expected"] == first["record"]["record_id"]
    _expect(
        lambda: _record_exp(
            world,
            valid_condition_input(world),
            name="unchanged.json",
            previous=first["record"]["record_id"],
            recorded_at=LATER_AT,
            batch="s5",
        ),
        "EXPERIMENT_RECORD_UNCHANGED",
    )
    _expect(
        lambda: _record_exp(
            world,
            changed,
            name="early.json",
            previous=first["record"]["record_id"],
            recorded_at="2026-09-13T00:00:00Z",
            batch="s6",
        ),
        "EXPERIMENT_STORE_CHAIN_INVALID",
    )
    other_key = valid_condition_input(world, setting_key="table3-row1-vbench-256")
    genesis_err = _expect(
        lambda: _record_exp(world, other_key, name="newprev.json", previous=first["record"]["record_id"], batch="s7"),
        "EXPERIMENT_RECORD_PREVIOUS_MISMATCH",
    )
    assert genesis_err.details["next_action"] == "omit_previous"
    other = _record_exp(world, other_key, name="otherkey.json", batch="s8")
    assert other["record"]["condition_id"] != first["record"]["condition_id"]
    association, raw, _authority = source_fixture(label="v2")
    assoc_raw = canonicalize(association)
    _write(world["vault"] / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"), assoc_raw)
    _write(world["vault"] / association["raw"]["path"], raw)
    v2 = valid_condition_input(world)
    v2["source_association"] = {"association_id": association["association_id"], "sha256": sha(assoc_raw)}
    v2["source_digest"] = {
        "path": association["raw"]["path"],
        "sha256": association["raw"]["sha256"],
        "size_bytes": association["raw"]["size_bytes"],
    }
    rel, digest = _document(world)
    for cond in v2["conditions"].values():
        for source in cond["sources"]:
            if source["kind"] == "paper_direct":
                source["locator"]["source_id"] = association["source_id"]
                source["locator"]["artifact_path"] = rel
                source["locator"]["artifact_sha256"] = digest
        value = cond.get("value")
        if isinstance(value, list):
            for metric in value:
                ds = metric.get("definition_source")
                if ds and ds["kind"] == "paper_direct":
                    ds["locator"]["source_id"] = association["source_id"]
                    ds["locator"]["artifact_path"] = rel
                    ds["locator"]["artifact_sha256"] = digest
    v2_record = _record_exp(world, v2, name="v2.json", batch="s9")
    assert v2_record["record"]["condition_id"] != first["record"]["condition_id"]
    assert v2_record["record"]["previous_record_id"] is None


def test_input_and_shape_failures(world):
    extra = valid_condition_input(world)
    extra["record_id"] = "exr-" + "a" * 20
    _expect(lambda: _record_exp(world, extra, name="extra.json"), "EXPERIMENT_RECORD_INVALID")
    missing = valid_condition_input(world)
    missing.pop("setting_key")
    _expect(lambda: _record_exp(world, missing, name="missing.json"), "EXPERIMENT_RECORD_INVALID")
    upper = valid_condition_input(world, setting_key="Table2")
    _expect(lambda: _record_exp(world, upper, name="upper.json"), "EXPERIMENT_RECORD_INVALID")
    short = valid_condition_input(world)
    short["conditions"] = dict(short["conditions"])
    short["conditions"].pop("frames")
    _expect(lambda: _record_exp(world, short, name="short.json"), "EXPERIMENT_RECORD_INVALID")
    unknown_value = valid_condition_input(world, conditions={"resolution": _unknown()})
    unknown_value["conditions"]["resolution"]["value"] = {"width": 1, "height": 1}
    _expect(lambda: _record_exp(world, unknown_value, name="unk-val.json"), "EXPERIMENT_RECORD_INVALID")
    derived = valid_condition_input(world)
    derived["conditions"]["parameter_count"]["basis_note"] = None
    err = _expect(lambda: _record_exp(world, derived, name="derived.json"), "EXPERIMENT_RECORD_INVALID")
    assert err.details["reason"] == "derived_basis"
    dup = valid_condition_input(world)
    metrics = dup["conditions"]["metrics"]["value"]
    dup["conditions"]["metrics"]["value"] = [metrics[0], dict(metrics[0])]
    err = _expect(lambda: _record_exp(world, dup, name="dup.json"), "EXPERIMENT_RECORD_INVALID")
    assert err.details["reason"] == "duplicate_metric"
    empty = valid_condition_input(world)
    empty["conditions"]["sampling_guidance"]["value"] = {"guidance_scale": None, "sampler": None, "seed": None}
    err = _expect(lambda: _record_exp(world, empty, name="empty.json"), "EXPERIMENT_RECORD_INVALID")
    assert err.details["reason"] == "empty_value"
    repo = valid_condition_input(world, conditions={"frames": _reported({"count": 16, "fps": 8}, _repo_text(world))})
    err = _expect(lambda: _record_exp(world, repo, name="repo.json"), "EXPERIMENT_RECORD_INVALID")
    assert err.details["reason"] == "repository_text_requires_code_binding"
    _expect(
        lambda: record_experiment_condition(
            input_path=str(world["checkout"] / "missing-input.json"),
            vault_root=str(world["vault"]),
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at=RECORDED_AT,
        ),
        "EXPERIMENT_RECORD_INPUT_MISSING",
    )
    target = world["checkout"] / "real.json"
    write_bytes(target, canonicalize(valid_condition_input(world)) + b"\n")
    link = world["checkout"] / "link.json"
    os.symlink(target, link)
    _expect(
        lambda: record_experiment_condition(
            input_path=str(link),
            vault_root=str(world["vault"]),
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at=RECORDED_AT,
        ),
        "WORK_PATH_UNSAFE",
    )
    write_bytes(world["checkout"] / "list.json", b"[1]\n")
    err = _expect(
        lambda: record_experiment_condition(
            input_path=str(world["checkout"] / "list.json"),
            vault_root=str(world["vault"]),
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at=RECORDED_AT,
        ),
        "EXPERIMENT_RECORD_INVALID",
    )
    assert err.details["reason"] == "type"
    _expect(
        lambda: record_experiment_condition(
            input_path=str(_write_input(world, valid_condition_input(world), "ts.json")),
            vault_root=str(world["vault"]),
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at="not-a-timestamp",
        ),
        "EXPERIMENT_RECORD_INVALID",
    )
    _expect(
        lambda: record_experiment_condition(
            input_path=str(_write_input(world, valid_condition_input(world), "prev.json")),
            vault_root=str(world["vault"]),
            batch_id=BATCH,
            recorded_by=RECORDED_BY,
            recorded_at=RECORDED_AT,
            previous_record_id="nope",
        ),
        "EXPERIMENT_RECORD_INVALID",
    )
    for name, association, reason in (
        ("sa-str.json", "sva-not-a-dict", "type"),
        ("sa-missing.json", {"sha256": "0" * 64}, "input_keys"),
        ("sa-null.json", None, "type"),
    ):
        payload = valid_condition_input(world)
        payload["source_association"] = association
        err = _expect(lambda p=payload, n=name: _record_exp(world, p, name=n), "EXPERIMENT_RECORD_INVALID")
        assert type(err) is ExperimentStoreError
        assert err.exit_code == 2
        assert err.details["reason"] == reason
        assert err.details["instance_pointer"].startswith("/source_association")
        assert err.details["next_action"] == "repair_input"


def test_binding_failures(world):
    payload = valid_condition_input(world)
    payload["source_association"] = dict(payload["source_association"])
    payload["source_association"]["sha256"] = "b" * 64
    err = _expect(lambda: _record_exp(world, payload, name="sha.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "source_association"
    assert err.details["reason"] == "sha256"
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (world["association"]["association_id"] + ".json")
    original = assoc_path.read_bytes()
    assoc_path.unlink()
    err = _expect(lambda: _record_exp(world, name="missing-assoc.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["reason"] == "missing"
    _write(assoc_path, original)
    mutated = copy.deepcopy(world["association"])
    mutated["observation"]["title"] = "Rewritten"
    _resealed, mismatch_raw = _reseal_association(mutated)
    _write(assoc_path, mismatch_raw)
    ident = valid_condition_input(world)
    ident["source_association"] = dict(ident["source_association"])
    ident["source_association"]["sha256"] = sha(mismatch_raw)
    err = _expect(lambda: _record_exp(world, ident, name="ident.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["reason"] == "association_identity"
    _write(assoc_path, original)
    digest = valid_condition_input(world)
    digest["source_digest"] = dict(digest["source_digest"])
    digest["source_digest"]["sha256"] = "c" * 64
    err = _expect(lambda: _record_exp(world, digest, name="digest.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "source_digest"
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    err = _expect(lambda: _record_exp(world, name="src-changed.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "source_digest"
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    paper = valid_condition_input(world)
    loc = paper["conditions"]["model_checkpoint"]["sources"][0]
    loc["locator"] = dict(loc["locator"])
    loc["locator"]["artifact_sha256"] = "d" * 64
    err = _expect(lambda: _record_exp(world, paper, name="artsha.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "paper_direct"
    missing_art = valid_condition_input(world)
    art_rel = missing_art["conditions"]["model_checkpoint"]["sources"][0]["locator"]["artifact_path"]
    art_path = world["vault"] / art_rel
    art_bytes = art_path.read_bytes()
    art_path.unlink()
    err = _expect(lambda: _record_exp(world, missing_art, name="artmiss.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "paper_direct"
    assert err.details["reason"] == "missing"
    _write(art_path, art_bytes)
    sid = valid_condition_input(world)
    sloc = sid["conditions"]["model_checkpoint"]["sources"][0]
    sloc["locator"] = dict(sloc["locator"])
    sloc["locator"]["source_id"] = "src-other-id"
    err = _expect(lambda: _record_exp(world, sid, name="sid.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["reason"] == "source_id"
    frag = valid_condition_input(world)
    ploc = frag["conditions"]["parameter_count"]["sources"][0]
    ploc["locator"] = dict(ploc["locator"])
    ploc["locator"]["fragment"] = dict(ploc["locator"]["fragment"])
    ploc["locator"]["fragment"]["text_sha256"] = "e" * 64
    err = _expect(lambda: _record_exp(world, frag, name="frag.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "project_page"
    assert err.details["reason"] == "fragment"
    size = valid_condition_input(world)
    sl = size["conditions"]["parameter_count"]["sources"][0]
    sl["locator"] = dict(sl["locator"])
    sl["locator"]["local_digest"] = dict(sl["locator"]["local_digest"])
    sl["locator"]["local_digest"]["size_bytes"] = sl["locator"]["local_digest"]["size_bytes"] + 1
    err = _expect(lambda: _record_exp(world, size, name="size.json"), "EXPERIMENT_RECORD_BINDING_MISMATCH")
    assert err.details["field"] == "project_page"


def _publish_lineage(world, batch="cb1"):
    first = _record(world, valid_proposal(world), name="g.json", batch=batch)
    _compile(world, batch)
    _apply(world, batch, confirm=lambda _s: True)
    return first


def test_code_binding_and_superseded(world):
    first = _publish_lineage(world)
    report = first["record"]["report"]
    binding = {
        "lineage_id": first["record"]["lineage_id"],
        "annotation_id": first["record"]["annotation_id"],
        "repository": report["repository"],
        "commit": report["commit"],
    }
    data = _record_exp(world, valid_condition_input(world, code_binding=binding), name="bound.json", batch="eb1")
    assert data["record"]["code_binding"]["lineage_id"] == binding["lineage_id"]
    missing = dict(binding)
    missing["lineage_id"] = "dln-" + "a" * 20
    err = _expect(
        lambda: _record_exp(world, valid_condition_input(world, code_binding=missing), name="noline.json", batch="eb2"),
        "EXPERIMENT_RECORD_BINDING_MISMATCH",
    )
    assert err.details["reason"] == "lineage_missing"
    missing_ann = dict(binding)
    missing_ann["annotation_id"] = "dan-" + "a" * 20
    err = _expect(
        lambda: _record_exp(world, valid_condition_input(world, code_binding=missing_ann), name="noann.json", batch="eb3"),
        "EXPERIMENT_RECORD_BINDING_MISMATCH",
    )
    assert err.details["reason"] == "annotation_missing"
    bad_commit = dict(binding)
    bad_commit["commit"] = "c" * 40
    err = _expect(
        lambda: _record_exp(world, valid_condition_input(world, code_binding=bad_commit), name="commit.json", batch="eb4"),
        "EXPERIMENT_RECORD_BINDING_MISMATCH",
    )
    assert err.details["reason"] == "report_mismatch"
    bad_repo = dict(binding)
    bad_repo["repository"] = "Owner/Name" if report["repository"] != "Owner/Name" else "owner/NAME"
    err = _expect(
        lambda: _record_exp(world, valid_condition_input(world, code_binding=bad_repo), name="repo.json", batch="eb5"),
        "EXPERIMENT_RECORD_BINDING_MISMATCH",
    )
    assert err.details["reason"] == "report_mismatch"
    _apply_staged_experiments(world, "eb1")
    successor = _record(
        world,
        _successor_proposal(world),
        name="succ.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="cb2",
    )
    _compile(world, "cb2")
    _apply(world, "cb2", confirm=lambda _s: True)
    status = _status(world)
    row = status["conditions"][0]
    assert row["code_binding"]["binding_status"] == "superseded"
    assert row["record_status"] == "current"
    repo_payload = valid_condition_input(
        world,
        code_binding=binding,
        conditions={"frames": _reported({"count": 16, "fps": 8}, _repo_text(world))},
    )
    repo_payload["conditions"]["frames"]["sources"][0]["locator"]["commit"] = report["commit"]
    recorded = _record_exp(
        world,
        repo_payload,
        name="repotext.json",
        previous=data["record"]["record_id"],
        recorded_at=LATER_AT,
        batch="eb6",
    )
    assert recorded["code_source_verification"] == "not_checked"


def test_claim_freshness(world):
    missing = valid_condition_input(world)
    missing["claim_refs"][0] = dict(missing["claim_refs"][0])
    missing["claim_refs"][0]["claim_id"] = "clm-" + "a" * 20
    err = _expect(lambda: _record_exp(world, missing, name="noclm.json"), "EXPERIMENT_HEAD_STALE")
    assert err.details["stale_reason"] == "claim_missing"
    first = _record_exp(world, batch="f1")
    _apply_staged_experiments(world, "f1")
    _kind, claim, old_event = _empirical(world)
    new_event = event_for(claim, previous=old_event, human=True, state="contested")
    _write(
        world["vault"] / "wiki/meta/reviews" / claim["claim_id"] / (new_event["event_id"] + ".json"),
        canonicalize(new_event),
    )
    heads_path = world["vault"] / ASSESSMENT_HEADS
    heads = json.loads(heads_path.read_bytes())
    heads["heads"][claim["claim_id"]] = {
        "event_id": new_event["event_id"],
        "event_sha256": sha(canonicalize(new_event)),
        "evidence_profile": new_event.get("evidence_profile", "legacy-v1"),
    }
    _write(heads_path, canonicalize(heads))
    err = _expect(lambda: _record_exp(world, name="stale.json", batch="f2"), "EXPERIMENT_HEAD_STALE")
    assert err.details["stale_reason"] == "assessment_head_changed"
    status = _status(world)
    row = status["conditions"][0]
    assert row["claims"][0]["freshness"] == "stale"
    assert row["claim_freshness"]["stale"] == 1
    assert row["record_status"] == "stale"
    assert status["next_action"] == "re_record_condition"
    heads["heads"][claim["claim_id"]] = {
        "event_id": old_event["event_id"],
        "event_sha256": sha(canonicalize(old_event)),
        "evidence_profile": old_event.get("evidence_profile", "legacy-v1"),
    }
    _write(heads_path, canonicalize(heads))
    ledger_path = world["vault"] / CLAIM_LEDGER
    ledger = json.loads(ledger_path.read_bytes())
    ledger["claims"][claim["claim_id"]]["text"] = "changed claim text"
    _write(ledger_path, canonicalize(ledger))
    err = _expect(lambda: _record_exp(world, name="text.json", batch="f3"), "EXPERIMENT_HEAD_STALE")
    assert err.details["stale_reason"] == "claim_text_changed"
    empty = valid_condition_input(world, claim_refs=[], setting_key="empty-claims")
    recorded = _record_exp(world, empty, name="empty-claims.json", batch="f4")
    assert recorded["record"]["claim_refs"] == []


def test_store_load_refusals(world):
    data = _record_exp(world, batch="m1")
    _apply_staged_experiments(world, "m1")
    record = data["record"]
    cid = record["condition_id"]
    rid = record["record_id"]
    path = world["vault"] / "wiki/meta/experiments/records" / cid / (rid + ".json")
    heads_path = world["vault"] / "wiki/meta/experiments/heads.json"

    renamed = path.parent / ("exr-" + "a" * 20 + ".json")
    path.rename(renamed)
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    renamed.rename(path)

    fake = json.loads(path.read_bytes())
    fake["record_id"] = "exr-" + "b" * 20
    fake_path = path.parent / (fake["record_id"] + ".json")
    _write(fake_path, canonicalize(fake))
    path.unlink()
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    fake_path.unlink()
    _write(path, canonicalize(record))

    wrong_cid = json.loads(path.read_bytes())
    wrong_cid["condition_id"] = "exc-" + "c" * 20
    _write(path, canonicalize(wrong_cid))
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    _write(path, canonicalize(record))

    wrong_sha = json.loads(path.read_bytes())
    wrong_sha["content_sha256"] = "d" * 64
    _write(path, canonicalize(wrong_sha))
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    _write(path, canonicalize(record))

    _write(path, json.dumps(json.loads(path.read_bytes()), indent=2).encode("utf-8"))
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    _write(path, canonicalize(record))

    notes = world["vault"] / "wiki/meta/experiments/notes.txt"
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    err = _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    assert err.details["reason"] == "unknown_entry"
    assert str(err.details["instance_pointer"]).startswith("/wiki/meta/experiments/")
    notes.unlink()

    reviews = world["vault"] / "wiki/meta/experiments/reviews"
    reviews.mkdir()
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    reviews.rmdir()

    empty_dir = world["vault"] / "wiki/meta/experiments/records" / ("exc-" + "e" * 20)
    empty_dir.mkdir()
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    empty_dir.rmdir()

    link = world["vault"] / "wiki/meta/experiments/records" / cid / "link.json"
    os.symlink(path, link)
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_INVALID")
    link.unlink()

    heads_path.unlink()
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_HEADS_MISSING")
    _write(heads_path, canonicalize({"schema": "video-paper-wiki.experiment-heads.v1", "heads": {}}))
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_HEADS_MISMATCH")
    _write(heads_path, canonicalize(data["heads"]))

    extra_heads = copy.deepcopy(data["heads"])
    extra_heads["heads"]["exc-" + "f" * 20] = extra_heads["heads"][cid]
    _write(heads_path, canonicalize(extra_heads))
    _expect(lambda: load_experiment_store(str(world["vault"])), "EXPERIMENT_STORE_HEADS_MISMATCH")
    _write(heads_path, canonicalize(data["heads"]))

    import video_paper_wiki.experiment_store as experiment_store

    original = experiment_store.MAX_PER_LINEAGE
    experiment_store.MAX_PER_LINEAGE = 1
    try:
        changed = valid_condition_input(world)
        changed["conditions"]["resolution"] = _reported(
            {"width": 256, "height": 256},
            changed["conditions"]["resolution"]["sources"][0],
        )
        _expect(
            lambda: _record_exp(
                world,
                changed,
                name="limit.json",
                previous=rid,
                recorded_at=LATER_AT,
                batch="m2",
            ),
            "EXPERIMENT_STORE_LIMIT",
        )
    finally:
        experiment_store.MAX_PER_LINEAGE = original


def test_empty_store_and_passthrough_domain_errors(world):
    status = _status(world)
    assert status["condition_count"] == 0
    assert status["heads"]["heads"] == {}
    assert set(status["basis"]) == {
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
        "experiment_store_inventory_sha256",
    }
    (world["vault"] / CLAIM_LEDGER).unlink()
    err = _expect(lambda: _status(world), "DOMAIN_STORE_INVALID")
    assert err.details.get("reason") == "authority"
    _write(world["vault"] / CLAIM_LEDGER, world["ledger_bytes"])
    notes = world["vault"] / "wiki/meta/domain/notes.txt"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("nope", encoding="utf-8")
    os.chmod(notes, 0o600)
    _expect(lambda: _status(world), "DOMAIN_STORE_INVALID")
    notes.unlink()


def test_status_three_chains_and_filters(world):
    first = _publish_lineage(world, "st1")
    domain_before = status_domain_store(vault_root=str(world["vault"]))
    view_before = build_domain_source_version_view(vault_root=str(world["vault"]))
    successor = _record(
        world,
        _successor_proposal(world),
        name="succ.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="st2",
    )
    compiled = _compile(world, "st2")
    a = _record_exp(world, batch="ea")
    _apply_staged_experiments(world, "ea")
    other_key = valid_condition_input(world, setting_key="table3-row1-vbench-256")
    b = _record_exp(world, other_key, name="b.json", batch="eb")
    _apply_staged_experiments(world, "eb")
    association, raw, _authority = source_fixture(paper_id="sha256:" + "b" * 64, text="second paper body")
    assoc_raw = canonicalize(association)
    _write(world["vault"] / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"), assoc_raw)
    _write(world["vault"] / association["raw"]["path"], raw)
    second_paper = valid_condition_input(world, paper_id=association["paper_id"], claim_refs=[])
    second_paper["source_association"] = {"association_id": association["association_id"], "sha256": sha(assoc_raw)}
    second_paper["source_digest"] = {
        "path": association["raw"]["path"],
        "sha256": association["raw"]["sha256"],
        "size_bytes": association["raw"]["size_bytes"],
    }
    rel, digest = _document(world)
    for cond in second_paper["conditions"].values():
        for source in cond["sources"]:
            if source["kind"] == "paper_direct":
                source["locator"]["source_id"] = association["source_id"]
                source["locator"]["artifact_path"] = rel
                source["locator"]["artifact_sha256"] = digest
        value = cond.get("value")
        if isinstance(value, list):
            for metric in value:
                ds = metric.get("definition_source")
                if ds and ds["kind"] == "paper_direct":
                    ds["locator"]["source_id"] = association["source_id"]
                    ds["locator"]["artifact_path"] = rel
                    ds["locator"]["artifact_sha256"] = digest
    c = _record_exp(world, second_paper, name="c.json", batch="ec")
    _apply_staged_experiments(world, "ec")
    status = _status(world)
    ids = [row["condition_id"] for row in status["conditions"]]
    assert ids == sorted(ids, key=lambda item: item.encode("utf-8"))
    assert status["condition_count"] == 3
    assert status["basis"]["domain_store_inventory_sha256"] == compiled["basis"]["domain_store_inventory_sha256"]
    assert status["basis"]["claim_ledger_sha256"] == compiled["basis"]["claim_ledger_sha256"]
    assert status["basis"]["assessment_heads_sha256"] == compiled["basis"]["assessment_heads_sha256"]
    view = build_domain_source_version_view(vault_root=str(world["vault"]))
    assert status["basis"]["domain_store_inventory_sha256"] == view["basis"]["domain_store_inventory_sha256"]
    store, _heads, _authority = load_experiment_store(str(world["vault"]))
    assert status["basis"]["experiment_store_inventory_sha256"] == experiment_inventory_digest(store)
    unknown = valid_condition_input(world, setting_key="table4-unknown-res", conditions={"resolution": _unknown()})
    u = _record_exp(world, unknown, name="u.json", batch="eu")
    _apply_staged_experiments(world, "eu")
    filtered = _status(world, paper_id=world["association"]["paper_id"])
    assert filtered["paper_filter"] == world["association"]["paper_id"]
    assert all(row["paper_id"] == world["association"]["paper_id"] for row in filtered["conditions"])
    unknown_row = next(row for row in filtered["conditions"] if row["condition_id"] == u["record"]["condition_id"])
    assert unknown_row["critical_unknown"] == ["resolution"]
    assert filtered["next_action"] == "supply_missing_conditions"
    err = _expect(lambda: _status(world, paper_id="sha256:" + "f" * 64), "EXPERIMENT_STATUS_PAPER_UNKNOWN")
    assert err.details["next_action"] == "check_paper_id"
    assert "known_paper_count" in err.details
    _expect(lambda: _status(world, paper_id=""), "EXPERIMENT_STATUS_INVALID")
    domain_after = status_domain_store(vault_root=str(world["vault"]))
    view_after = build_domain_source_version_view(vault_root=str(world["vault"]))
    assert canonicalize(domain_before) == canonicalize(domain_after)
    assert canonicalize(view_before) == canonicalize(view_after)
    assoc_path = world["vault"] / "wiki/meta/records/source-versions" / (world["association"]["association_id"] + ".json")
    original = assoc_path.read_bytes()
    assoc_path.unlink()
    stale = _status(world, paper_id=world["association"]["paper_id"])
    assert {row["association_status"] for row in stale["conditions"]} == {"missing"}
    assert all(row["record_status"] == "stale" for row in stale["conditions"])
    _write(assoc_path, original)
    src_path = world["vault"] / world["association"]["raw"]["path"]
    src_original = src_path.read_bytes()
    src_path.write_bytes(src_original + b"x")
    os.chmod(src_path, 0o600)
    changed = _status(world, paper_id=world["association"]["paper_id"])
    assert {row["source_status"] for row in changed["conditions"]} == {"changed"}
    src_path.write_bytes(src_original)
    os.chmod(src_path, 0o600)
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first_status = _status(world)
    second_status = _status(world)
    assert canonicalize(first_status) == canonicalize(second_status)
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before


def test_determinism_zero_network_and_changed(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    payload = valid_condition_input(world)
    vault_before = _snapshot(world["vault"])
    first = _record_exp(world, payload, name="a.json")
    second = _record_exp(world, payload, name="b.json")
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    _apply_staged_experiments(world)
    from video_paper_wiki.receipt_audit import _Snapshot

    original = _Snapshot.read

    def mutating(self, relative, **kwargs):
        raw = original(self, relative, **kwargs)
        if "wiki/meta/experiments" in relative and relative.endswith(".json"):
            path = self.root / relative
            path.write_bytes(raw)
            os.chmod(path, 0o600)
        return raw

    monkeypatch.setattr(_Snapshot, "read", mutating)
    with pytest.raises((ExperimentStoreError, DomainStoreError)) as err:
        _status(world)
    assert err.value.code in {"EXPERIMENT_STORE_CHANGED", "DOMAIN_STORE_CHANGED"}
    assert err.value.exit_code == 75
    assert err.value.details.get("next_action") == "repeat_read"
