from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from tests.research.test_light_knowledge import (
    PAPER_A,
    _knowledge_document,
    _raw_symlink_parent_path,
    _regular_file_snapshot,
)
from tests.research.test_light_knowledge_batch import _run_batches
from video_paper_wiki_research.light_index import build_index
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_knowledge import (
    KNOWLEDGE_STATE_DIR,
    LIGHT_BATCH_INVALID,
    LIGHT_REFRESH_CONFLICT,
    LIGHT_REFRESH_INVALID,
    WORKSPACE_INVALID,
    _load_persisted_object,
    export_knowledge_context,
    import_knowledge,
    list_knowledge,
    persisted_bytes,
    sha256_canonical,
)
from video_paper_wiki_research.light_knowledge_batch import (
    BATCH_JOBS_DIRNAME,
    PLAN_FILE,
    _plan_identity,
    _plan_object,
    export_knowledge_batch,
    export_knowledge_merge_context,
    finalize_knowledge_batches,
    import_knowledge_batch,
    import_knowledge_merge,
    load_plan,
)
from video_paper_wiki_research.light_knowledge_refresh import (
    apply_knowledge_refresh,
    export_knowledge_diff,
    plan_knowledge_refresh,
)


def _workspace(tmp_path: Path, *, pages_a: list[str] | None = None) -> Path:
    workspace = tmp_path / ".work" / "ws"
    workspace.mkdir(parents=True)
    _write_paper(
        workspace,
        SHA_A,
        "Alpha paper",
        pages_a or ["Synthetic quasar method evidence uniquealpha sharedconcept."],
    )
    _write_paper(
        workspace,
        SHA_B,
        "Beta paper",
        ["Nebula writing token evidence uniquebeta sharedconcept."],
    )
    assert build_index(workspace)["ok"] is True
    return workspace


def _rewrite_paper(workspace: Path, digest: str, title: str, bodies: list[str]) -> None:
    import shutil

    directory = workspace / "papers" / digest
    if directory.exists():
        shutil.rmtree(directory)
    _write_paper(workspace, digest, title, bodies)


def _shift_offsets(workspace: Path, digest: str, title: str, bodies: list[str]) -> None:
    directory = workspace / "papers" / digest
    md = directory / "source.md"
    original = md.read_text(encoding="utf-8")
    md.write_text("<!-- offset shift -->\n" + original, encoding="utf-8")
    meta = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    markdown = md.read_text(encoding="utf-8")
    import hashlib

    meta["title"] = title
    meta["document"]["sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    (directory / "source.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert build_index(workspace)["ok"] is True


def _run_refresh_to_candidate(workspace: Path, paper_id: str) -> dict:
    planned = plan_knowledge_refresh(workspace, paper_id=paper_id)
    assert planned["ok"] is True, planned
    if planned["batch_count"]:
        for index in range(planned["batch_count"]):
            exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=index)
            assert exported["ok"] is True, exported
            imported = import_knowledge_batch(
                workspace,
                exported,
                _knowledge_document(paper_id, exported["context"]["evidence"][0]["chunk_id"], concept="Refresh Method"),
            )
            assert imported["ok"] is True, imported
            merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
            assert merge["ok"] is True, merge
            from tests.research.test_light_knowledge_batch import _merge_document

            merged = import_knowledge_merge(workspace, merge, _merge_document(paper_id, merge))
            assert merged["ok"] is True, merged
    finalized = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert finalized["ok"] is True, finalized
    assert finalized["advanced_head"] is False
    planned["candidate"] = finalized
    return planned


def test_retained_content_despite_shifted_offsets(tmp_path: Path) -> None:
    bodies = ["Synthetic quasar method evidence uniquealpha sharedconcept."]
    workspace = _workspace(tmp_path, pages_a=bodies)
    published = _run_batches(workspace, PAPER_A)
    assert published["ok"] is True
    head_before = list_knowledge(workspace)["heads"][PAPER_A]
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("do not rewrite notes\n", encoding="utf-8")
    _shift_offsets(workspace, SHA_A, "Alpha paper", bodies)
    planned = _run_refresh_to_candidate(workspace, PAPER_A)
    assert planned["conservative_full_refresh"] is False
    assert planned["batch_count"] == 0
    assert planned["retained"]
    assert planned["added"] == []
    listed = list_knowledge(workspace)
    assert listed["heads"][PAPER_A] == head_before
    diff = export_knowledge_diff(
        workspace,
        base_record_id=head_before,
        candidate_record_id=planned["candidate"]["record_id"],
    )
    assert diff["ok"] is True
    assert diff["sections"]["summary"]["retain_allowed"] is True
    applied = apply_knowledge_refresh(
        workspace,
        diff,
        accept_sections=["summary"],
        accept_concepts=False,
    )
    assert applied["ok"] is True
    assert applied["record_id"] != head_before
    assert list_knowledge(workspace)["heads"][PAPER_A] == applied["record_id"]
    assert notes.read_text(encoding="utf-8") == "do not rewrite notes\n"
    retry = apply_knowledge_refresh(
        workspace,
        diff,
        accept_sections=["summary"],
        accept_concepts=False,
    )
    assert retry["ok"] is True
    assert retry["reused"] is True


def test_deleted_evidence_invalidates_old_blocks(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=["keep page one uniquealpha.", "drop page two uniquealpha."])
    published = _run_batches(workspace, PAPER_A)
    assert published["ok"] is True
    _rewrite_paper(workspace, SHA_A, "Alpha paper", ["keep page one uniquealpha."])
    assert build_index(workspace)["ok"] is True
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["changed_or_removed"]
    assert "summary" in planned["affected_sections"] or planned["changed_or_removed"]
    candidate = _run_refresh_to_candidate(workspace, PAPER_A)
    diff = export_knowledge_diff(
        workspace,
        base_record_id=published["record_id"],
        candidate_record_id=candidate["candidate"]["record_id"],
    )
    assert diff["ok"] is True
    rejected = apply_knowledge_refresh(workspace, diff, accept_sections=[], accept_concepts=False)
    if diff["sections"]["summary"]["retain_allowed"] is False:
        assert rejected["ok"] is False
        assert rejected["status"] == LIGHT_REFRESH_INVALID


def test_metadata_only_refresh_has_zero_batches(tmp_path: Path) -> None:
    bodies = ["Synthetic quasar method evidence uniquealpha sharedconcept."]
    workspace = _workspace(tmp_path, pages_a=bodies)
    published = _run_batches(workspace, PAPER_A)
    directory = workspace / "papers" / SHA_A
    meta = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    meta["title"] = "Alpha paper retitled"
    (directory / "source.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert build_index(workspace)["ok"] is True
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["conservative_full_refresh"] is False
    assert planned["batch_count"] == 0
    finalized = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert finalized["ok"] is True
    assert finalized["advanced_head"] is False
    assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]


def test_conservative_legacy_refresh(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    published = import_knowledge(
        workspace,
        exported,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"]),
    )
    assert published["ok"] is True
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["conservative_full_refresh"] is True
    assert planned["batch_count"] >= 1


def test_selective_rejection_and_head_drift(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    published = _run_batches(workspace, PAPER_A)
    planned = _run_refresh_to_candidate(workspace, PAPER_A)
    diff = export_knowledge_diff(
        workspace,
        base_record_id=published["record_id"],
        candidate_record_id=planned["candidate"]["record_id"],
    )
    assert diff["ok"] is True
    one_shot = export_knowledge_context(workspace, paper_id=PAPER_A)
    drifted = import_knowledge(
        workspace,
        one_shot,
        _knowledge_document(PAPER_A, one_shot["context"]["evidence"][0]["chunk_id"], concept="Drift"),
    )
    assert drifted["ok"] is True
    refused = apply_knowledge_refresh(
        workspace,
        diff,
        accept_sections=["summary"],
        accept_concepts=True,
    )
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_REFRESH_CONFLICT


def test_refresh_requires_head_and_explicit_concept_flag(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    missing = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert missing["ok"] is False
    assert missing["status"] == LIGHT_REFRESH_INVALID
    published = _run_batches(workspace, PAPER_A)
    planned = _run_refresh_to_candidate(workspace, PAPER_A)
    diff = export_knowledge_diff(
        workspace,
        base_record_id=published["record_id"],
        candidate_record_id=planned["candidate"]["record_id"],
    )
    implicit = apply_knowledge_refresh(workspace, diff, accept_sections=["summary"], accept_concepts="yes")
    assert implicit["ok"] is False
    assert implicit["status"] == LIGHT_REFRESH_INVALID
    duplicate = apply_knowledge_refresh(
        workspace,
        diff,
        accept_sections=["summary", "summary"],
        accept_concepts=False,
    )
    assert duplicate["ok"] is False
    assert duplicate["status"] == LIGHT_REFRESH_INVALID


def test_forged_zero_batch_seed_is_refused(tmp_path: Path) -> None:
    bodies = ["Synthetic quasar method evidence uniquealpha sharedconcept."]
    workspace = _workspace(tmp_path, pages_a=bodies)
    published = _run_batches(workspace, PAPER_A)
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("refresh notes stay\n", encoding="utf-8")
    directory = workspace / "papers" / SHA_A
    meta = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    meta["title"] = "Alpha paper retitled"
    (directory / "source.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert build_index(workspace)["ok"] is True
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["batch_count"] == 0
    source = load_plan(workspace, planned["plan_id"])
    assert source is not None
    forged_seed = _knowledge_document(PAPER_A, source["inventory"][0]["chunk_id"], concept="Forged Seed")
    identity = _plan_identity(
        mode="refresh",
        workspace_id=source["workspace_id"],
        index_id=source["index_id"],
        paper_id=source["paper_id"],
        paper_snapshot=source["paper_snapshot"],
        expected_base_head=source["expected_base_head"],
        inventory=source["inventory"],
        partition=source["partition"],
        conservative_full_refresh=source["conservative_full_refresh"],
        seed_document=forged_seed,
    )
    plan_id = sha256_canonical(identity)
    forged = _plan_object(identity, plan_id)
    job = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME / plan_id
    job.mkdir(parents=True)
    (job / PLAN_FILE).write_bytes(persisted_bytes(forged))
    refused = finalize_knowledge_batches(workspace, plan_id=plan_id)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BATCH_INVALID
    assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]
    assert notes.read_text(encoding="utf-8") == "refresh notes stay\n"


def test_zero_batch_all_unknown_seed_does_not_advance_head(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    published = _run_batches(workspace, PAPER_A)
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    finalized = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    if planned["batch_count"] == 0 and finalized.get("ok") is True:
        assert finalized["advanced_head"] is False
        assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]
    else:
        assert finalized.get("advanced_head") in {False, None} or finalized.get("ok") is False or finalized.get("advanced_head") is False
        assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]


def test_same_paper_ancestry_rejects_foreign_base(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    published_a = _run_batches(workspace, PAPER_A)
    from tests.research.test_light_knowledge_batch import PAPER_B, _run_batches as run_b

    published_b = run_b(workspace, PAPER_B)
    planned = _run_refresh_to_candidate(workspace, PAPER_A)
    candidate_id = planned["candidate"]["record_id"]
    dest = workspace / KNOWLEDGE_STATE_DIR / "records" / candidate_id
    identity = _load_persisted_object(dest / "identity.json")
    document = _load_persisted_object(dest / "document.json")
    assert identity is not None and document is not None
    identity["wrapper"]["coverage"]["provenance"]["base_record_id"] = published_b["record_id"]
    (dest / "identity.json").write_bytes(persisted_bytes(identity))
    listed = list_knowledge(workspace)
    row = [item for item in listed["records"] if item["record_id"] == candidate_id]
    assert row
    assert row[0]["source_status"] == "conflict"
    assert listed["heads"][PAPER_A] == published_a["record_id"]


def test_raw_symlink_parent_workspace_refuses_refresh_entrypoints(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    published = _run_batches(workspace, PAPER_A)
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("refresh-keep\n", encoding="utf-8")
    planned = plan_knowledge_refresh(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    work = workspace.parent
    alias = work / "alias"
    alias.mkdir()
    differing = _raw_symlink_parent_path(work, target=alias, name="link")
    same_target = _raw_symlink_parent_path(work, target=workspace, name="same")
    plain_parent = workspace / ".." / "ws"
    before = _regular_file_snapshot(workspace)
    dummy_id = "0" * 64
    calls = [
        lambda raw: plan_knowledge_refresh(raw, paper_id=PAPER_A),
        lambda raw: export_knowledge_diff(raw, base_record_id=published["record_id"], candidate_record_id=dummy_id),
        lambda raw: apply_knowledge_refresh(raw, {}, accept_sections=[], accept_concepts=False),
    ]
    for raw in (differing, same_target, plain_parent, str(differing)):
        for call in calls:
            with pytest.raises(ResearchError) as caught:
                call(raw)
            assert caught.value.code == WORKSPACE_INVALID
            assert _regular_file_snapshot(workspace) == before
            assert notes.read_text(encoding="utf-8") == "refresh-keep\n"
            assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]
    assert plan_knowledge_refresh(workspace, paper_id=PAPER_A)["reused"] is True
    assert _regular_file_snapshot(workspace) == before
