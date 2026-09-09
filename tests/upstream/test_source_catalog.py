from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tests.research.test_source_admission import bootstrap_genesis
from tests.source_publication_fixture import knowledge_proposal, registered_source
from tests.upstream.test_markdown_source import _captured_fixture, _snapshot
from tests.upstream.test_source_publication import publish
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_catalog import (
    build_source_catalog, lookup_source_catalog, query_source_catalog, resolve_source_catalog, source_catalog_status,
)
from video_paper_wiki.source_catalog_contracts import digest
from video_paper_wiki.source_semantics_contracts import sha


def published(checkout):
    vault, capture, _, _ = registered_source(checkout)
    payloads, material, arguments = knowledge_proposal(vault, capture)
    publish(checkout, vault, payloads, "knowledge")
    return vault, capture, material, arguments


def read_catalog(result):
    return json.loads(Path(result["cache_path"]).read_bytes())


def test_empty_initialized_catalog_absence_creation_reuse_and_all_readers(checkout):
    vault = checkout / "empty-vault"
    bootstrap_genesis(checkout, vault, checkout)
    before = _snapshot(vault)
    absent = source_catalog_status(vault_root=vault, batch_id="catalog")
    assert absent["state"] == "absent" and absent["cache_sha256"] is None
    assert not (checkout / ".work/catalog").exists()
    built = build_source_catalog(vault_root=vault, batch_id="catalog")
    cache = Path(built["cache_path"])
    first = cache.stat()
    assert first.st_mode & 0o777 == 0o600 and built["state"] == "created"
    assert build_source_catalog(vault_root=vault, batch_id="catalog")["state"] == "reused"
    assert (cache.stat().st_ino, cache.stat().st_mtime_ns) == (first.st_ino, first.st_mtime_ns)
    status = source_catalog_status(vault_root=vault, batch_id="catalog")
    assert status["state"] == "current" and status["uncovered_count"] == 0
    assert status["catalog_sha256"] == absent["expected_catalog_sha256"] == built["catalog_sha256"]
    assert lookup_source_catalog(vault_root=vault, batch_id="catalog", kind="paper", key="absent")["matches"] == []
    assert query_source_catalog(vault_root=vault, batch_id="catalog", text="时序注意力")["total_matches"] == 0
    with pytest.raises(ContractError) as err:
        resolve_source_catalog(vault_root=vault, batch_id="catalog", claim_id="clm-" + "0" * 20, evidence_ordinal=0)
    assert err.value.code == "SOURCE_CATALOG_NOT_FOUND"
    assert _snapshot(vault) == before


def test_actual_markdown_publication_lookup_query_and_exact_citation(checkout):
    vault, capture, material, _ = published(checkout)
    before = _snapshot(vault)
    built = build_source_catalog(vault_root=vault, batch_id="catalog")
    doc = read_catalog(built)
    group = material["papers"][0]
    pid, cid = group["record"]["paper_id"], group["claims"][0]["claim_id"]
    assert doc["catalog_sha256"] == digest(doc)
    assert doc["basis"]["inventory_sha256"] == sha(canonicalize(doc["basis"]["inventory"]))
    managed = (".raw/captured/", ".raw/derived/", "wiki/papers/", "wiki/code/", "wiki/concepts/",
               "wiki/meta/ledgers/", "wiki/meta/records/", "wiki/meta/reviews/", "wiki/meta/gates/", "wiki/meta/operations/")
    from video_paper_wiki.receipt_audit import HEAD
    expected = {p for p in before if p.startswith(managed) or p in {HEAD, "wiki/meta/registries/gate-heads.json"}}
    assert {x["path"] for x in doc["basis"]["inventory"]} == expected
    for item in doc["basis"]["inventory"]:
        raw, mode = before[item["path"]]
        assert (item["sha256"], item["size_bytes"], item["mode"]) == (sha(raw), len(raw), mode)
    assert {x["path"] for x in doc["rows"]["artifacts"]} == {p for p in expected if p.startswith(".raw/")}
    assert len(doc["rows"]["coverage"]) == len(doc["rows"]["sources"]) + len(doc["rows"]["artifacts"])
    exact = lookup_source_catalog(vault_root=vault, batch_id="catalog", kind="paper", key=pid)
    title = lookup_source_catalog(vault_root=vault, batch_id="catalog", kind="paper", key="合成发布测试")
    assert exact["matches"] == title["matches"] == doc["rows"]["papers"]
    assert exact["evidence"][0]["association_id"] == group["associations"][0]["association_id"]
    assert exact["evidence"][0]["display_association_id"] is None
    resolved = resolve_source_catalog(vault_root=vault, batch_id="catalog", claim_id=cid, evidence_ordinal=0,
                                      catalog_sha256=built["catalog_sha256"])
    loc = group["claims"][0]["evidence"][0]
    excerpt = (vault / capture["stored_path"]).read_bytes().decode()[slice(*loc["charspan"])]
    assert resolved["evidence"]["resolution"]["excerpt"] == excerpt
    assert resolved["assessment"] == "provisional" and resolved["lifecycle"] == "active"
    result = query_source_catalog(vault_root=vault, batch_id="catalog", text="temporal attention", limit=1)
    whole = query_source_catalog(vault_root=vault, batch_id="catalog", text="temporal attention")
    assert result["hits"] == whole["hits"][:1] and result["total_matches"] > 0
    if result["next_offset"] is not None:
        rest = query_source_catalog(vault_root=vault, batch_id="catalog", text="temporal attention", offset=1)
        assert result["hits"] + rest["hits"] == whole["hits"]
    assert query_source_catalog(vault_root=vault, batch_id="catalog", text="temporal", assessment="accepted")["hits"] == []
    assert query_source_catalog(vault_root=vault, batch_id="catalog", text="temporal", paper_id="arxiv:2609.99999")["hits"] == []
    assert _snapshot(vault) == before


@pytest.mark.parametrize("stage", ["captured", "registered"])
def test_valid_unclaimed_source_and_unregistered_capture_coverage(checkout, stage):
    if stage == "captured":
        vault, _, capture, _ = _captured_fixture(checkout)
    else:
        vault, capture, _, _ = registered_source(checkout)
    built = build_source_catalog(vault_root=vault, batch_id="coverage")
    doc = read_catalog(built)
    coverage = {r["id"]: r for r in doc["rows"]["coverage"]}
    expected = "captured_unregistered" if stage == "captured" else "captured_registered"
    assert coverage[capture["stored_path"]]["state"] == expected
    if stage == "registered":
        assert coverage[capture["source_id"]]["state"] == "registered_unclaimed"
    status = source_catalog_status(vault_root=vault, batch_id="coverage")
    assert status["state"] == "current" and status["uncovered_count"] > 0


def test_current_reconstruction_detects_self_consistent_forgery_and_corruption(checkout):
    vault, _, _, _ = published(checkout)
    built = build_source_catalog(vault_root=vault, batch_id="catalog")
    path = Path(built["cache_path"])
    original = path.read_bytes()
    doc = json.loads(original)
    doc["rows"]["claims"][0]["text"] = "Self-consistent forged answer."
    doc["generation"]["rows_sha256"] = sha(canonicalize(doc["rows"]))
    doc["catalog_sha256"] = digest(doc)
    forged = canonicalize(doc)
    path.write_bytes(forged)
    assert source_catalog_status(vault_root=vault, batch_id="catalog")["state"] == "stale"
    with pytest.raises(ContractError) as err:
        query_source_catalog(vault_root=vault, batch_id="catalog", text="forged")
    assert err.value.code == "SOURCE_CATALOG_STALE"
    with pytest.raises(ContractError) as err:
        build_source_catalog(vault_root=vault, batch_id="catalog")
    assert err.value.code == "SOURCE_CATALOG_CONFLICT" and path.read_bytes() == forged
    for bad in (original + b"\n", b"{}", b"not json", b'{"schema":1,"schema":2}', original.replace(b'"rows_sha256":"', b'"rows_sha256":"f', 1)):
        path.write_bytes(bad)
        with pytest.raises(ContractError) as err:
            source_catalog_status(vault_root=vault, batch_id="catalog")
        assert err.value.code == "SOURCE_CATALOG_INVALID" and path.read_bytes() == bad


def test_restore_rebuild_has_equal_rows_and_digest(checkout):
    from video_paper_wiki.backup_archive import encode_backup_archive, restore_backup_archive
    from video_paper_wiki.backup_manifest import build_backup_manifest, verify_restored_tree
    vault, _, _, _ = published(checkout)
    before = build_source_catalog(vault_root=vault, batch_id="before")
    manifest = build_backup_manifest(vault)
    archive = checkout / ".work/catalog-backup.zip"
    archive.write_bytes(encode_backup_archive(vault_root=vault, manifest=manifest)); archive.chmod(0o600)
    restored = checkout / "restored"; restored.mkdir(mode=0o700)
    restore_backup_archive(archive=archive, source_root=vault, restore_root=restored, manifest=manifest)
    verify_restored_tree(restored, manifest, source_root=vault)
    after = build_source_catalog(vault_root=restored, batch_id="after")
    assert before["catalog_sha256"] == after["catalog_sha256"]
    assert Path(before["cache_path"]).read_bytes() == Path(after["cache_path"]).read_bytes()


def test_unknown_integer_ordinals_are_not_found_and_digest_guards_all_readers(checkout):
    vault, _, material, _ = published(checkout)
    build_source_catalog(vault_root=vault, batch_id="catalog")
    cid = material["papers"][0]["claims"][0]["claim_id"]
    for ordinal in (-1, 1000001, 10 ** 80):
        with pytest.raises(ContractError) as err:
            resolve_source_catalog(vault_root=vault, batch_id="catalog", claim_id=cid, evidence_ordinal=ordinal)
        assert err.value.code == "SOURCE_CATALOG_NOT_FOUND" and err.value.exit_code == 75
    for function, arguments in (
        (lookup_source_catalog, {"kind": "claim", "key": cid}),
        (query_source_catalog, {"text": "temporal"}),
        (resolve_source_catalog, {"claim_id": cid, "evidence_ordinal": 0}),
    ):
        with pytest.raises(ContractError) as err:
            function(vault_root=vault, batch_id="catalog", catalog_sha256="f" * 64, **arguments)
        assert err.value.code == "SOURCE_CATALOG_STALE"
        with pytest.raises(ContractError) as err:
            function(vault_root=vault, batch_id="missing-catalog", **arguments)
        assert err.value.code == "SOURCE_CATALOG_ABSENT"
    assert not (checkout / ".work/missing-catalog").exists()


def test_actual_display_selection_and_rollback_keep_the_original_citation(checkout, monkeypatch):
    import tests.upstream.test_source_publication as workflow
    original = workflow.publish
    observed = []
    def publish_and_read(checkout, vault, payloads, name):
        result = original(checkout, vault, payloads, name)
        if name in ("choose-2", "choose-3"):
            built = build_source_catalog(vault_root=vault, batch_id="catalog-" + name)
            doc = read_catalog(built)
            evidence = doc["rows"]["evidence"][0]
            resolved = resolve_source_catalog(vault_root=vault, batch_id="catalog-" + name,
                claim_id=evidence["claim_id"], evidence_ordinal=0)
            assert resolved["evidence"] == evidence
            assert len(doc["rows"]["associations"]) == 2
            observed.append(evidence)
        return result
    monkeypatch.setattr(workflow, "publish", publish_and_read)
    workflow.test_later_registration_keeps_display_and_full_typed_graph(checkout)
    forward, rollback = observed
    assert forward["association_id"] != forward["display_association_id"]
    assert rollback["association_id"] == rollback["display_association_id"]
    assert forward["association_id"] == rollback["association_id"]
    assert forward["wire"] == rollback["wire"] and forward["resolution"] == rollback["resolution"]


def test_actual_accepted_invalidation_and_retired_history_filters(checkout):
    from tests.research.test_source_conversion import conversion_fixture, publish_conversion
    from tests.upstream.test_source_conversion import capture_current, complete_payloads, synthetic_review
    kwargs, _, _, _ = conversion_fixture(checkout)
    publish_conversion(checkout, kwargs)
    cid, reviewed = synthetic_review(checkout, kwargs)
    vault = kwargs["vault_root"]
    accepted = read_catalog(build_source_catalog(vault_root=vault, batch_id="accepted-catalog"))
    assert accepted["rows"]["claims"][0]["assessment"] == "accepted"
    assert query_source_catalog(vault_root=vault, batch_id="accepted-catalog", text="temporal", assessment="accepted")["hits"]
    path, _ = capture_current(checkout, kwargs, batch="version-two", version="v2")
    kwargs.update(capture_authority=path, metadata=None, batch_id="convert-two", operation_id="convert-two",
                  proposed_at="2026-09-09T03:00:00Z")
    publish_conversion(checkout, kwargs)
    invalidated = read_catalog(build_source_catalog(vault_root=vault, batch_id="invalidated-catalog"))
    claim = invalidated["rows"]["claims"][0]
    assert claim["claim_id"] == cid and claim["assessment"] == "provisional" and claim["reviewed_at"] is None
    assert claim["head_event_id"] != reviewed["event_id"]
    assert source_catalog_status(vault_root=vault, batch_id="accepted-catalog")["state"] == "stale"
    assert query_source_catalog(vault_root=vault, batch_id="invalidated-catalog", text="temporal", assessment="accepted")["hits"] == []
    record_path = next((vault / "wiki/meta/records/papers").glob("*.json"))
    record = json.loads(record_path.read_bytes())
    record["section_claim_refs"][0]["lifecycle"] = "retired"
    publish(checkout, vault, complete_payloads(vault, {record_path.relative_to(vault).as_posix(): canonicalize(record)}), "retire")
    build_source_catalog(vault_root=vault, batch_id="retired-catalog")
    assert query_source_catalog(vault_root=vault, batch_id="retired-catalog", text="temporal")["hits"] == []
    hits = query_source_catalog(vault_root=vault, batch_id="retired-catalog", text="temporal", lifecycle="retired")["hits"]
    assert hits and all(h["lifecycle"] == "retired" and h["assessment"] == "provisional" for h in hits)


def test_actual_legacy_pdf_and_markdown_mixed_evidence_after_explicit_migration(checkout):
    from tests.research.test_source_admission import CLAIM_TEXT
    from tests.research.test_source_conversion import conversion_fixture, publish_conversion
    from tests.upstream.test_source_conversion import legacy_paper
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=True)
    legacy_claims, _, _ = legacy_paper(checkout, kwargs, document)
    publish_conversion(checkout, kwargs)
    vault = kwargs["vault_root"]
    before = _snapshot(vault)
    doc = read_catalog(build_source_catalog(vault_root=vault, batch_id="mixed"))
    assert {e["kind"] for e in doc["rows"]["evidence"]} == {"pdf", "markdown"}
    cid = legacy_claims[1]["claim_id"]
    evidence = resolve_source_catalog(vault_root=vault, batch_id="mixed", claim_id=cid, evidence_ordinal=0)["evidence"]
    assert evidence["association_id"] is None and evidence["resolution"]["state"] == "RESOLVED"
    assert evidence["resolution"]["excerpt"] == CLAIM_TEXT
    assert evidence["resolution"]["position"]["ref"] == "#/texts/0"
    assert _snapshot(vault) == before
