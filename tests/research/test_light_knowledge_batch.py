from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from tests.research.test_light_knowledge import (
    PAPER_A,
    PAPER_B,
    _knowledge_document,
    _raw_symlink_parent_path,
    _regular_file_snapshot,
    _unknown,
)
from video_paper_wiki_research.light_backup import create_backup, restore_backup, verify_backup
from video_paper_wiki_research.light_index import INDEX_STALE, LIGHT_SELECTION_INVALID, build_index
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_knowledge import (
    KNOWLEDGE_STATE_DIR,
    LIGHT_BATCH_CONFLICT,
    LIGHT_BATCH_INCOMPLETE,
    LIGHT_BATCH_INVALID,
    RECORDS_DIRNAME,
    SECTION_KEYS,
    UNKNOWN_TEXT,
    WORKSPACE_INVALID,
    _load_live_papers,
    _load_persisted_object,
    _paper_by_id,
    _record_bundle_ok,
    _record_files,
    build_knowledge_views,
    list_knowledge,
    persisted_bytes,
    sha256_canonical,
)
from video_paper_wiki_research.light_knowledge_batch import (
    BATCHES_DIRNAME,
    BATCH_JOBS_DIRNAME,
    COMPLETION_FILE,
    PLAN_FILE,
    _plan_identity,
    _plan_object,
    classify_batch_job,
    export_knowledge_batch,
    export_knowledge_merge_context,
    finalize_knowledge_batches,
    import_knowledge_batch,
    import_knowledge_merge,
    knowledge_batch_backup_blockers,
    knowledge_batch_status,
    load_plan,
    partition_chunks,
    plan_knowledge_batches,
    _record_wrapper,
)
from video_paper_wiki_research.light_qa import INSUFFICIENT_EVIDENCE


def _workspace(tmp_path: Path, *, pages_a: list[str] | None = None, pages_b: list[str] | None = None) -> Path:
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
        pages_b or ["Nebula writing token evidence uniquebeta sharedconcept."],
    )
    built = build_index(workspace)
    assert built["ok"] is True
    return workspace


def _many_pages(count: int, prefix: str = "chunkbody") -> list[str]:
    return [f"{prefix} {index:04d} uniquealpha token." for index in range(count)]


def _all_unknown(paper_id: str) -> dict:
    return {
        "concepts": [],
        "paper_id": paper_id,
        "schema": "video-paper-wiki.light-knowledge-document.v1",
        "sections": {key: _unknown() for key in SECTION_KEYS},
    }


def _cites(document: dict | None) -> list[str]:
    if not document:
        return []
    used: list[str] = []
    for key in SECTION_KEYS:
        block = document["sections"][key]
        used.extend(block.get("citations") or [])
    for item in document.get("concepts") or []:
        used.extend(item.get("citations") or [])
    return used


def _merge_document(paper_id: str, wrapper: dict) -> dict:
    ids = list(dict.fromkeys(_cites(wrapper.get("accumulator")) + _cites(wrapper.get("next_batch_document"))))
    if not ids:
        return _all_unknown(paper_id)
    return _knowledge_document(paper_id, ids[0], concept="Batch Method")


def _run_batches(workspace: Path, paper_id: str, *, unknown: bool = False) -> dict:
    planned = plan_knowledge_batches(workspace, paper_id=paper_id)
    assert planned["ok"] is True, planned
    for index in range(planned["batch_count"]):
        exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=index)
        assert exported["ok"] is True, exported
        evidence = exported["context"]["evidence"]
        document = _all_unknown(paper_id) if unknown else _knowledge_document(paper_id, evidence[0]["chunk_id"])
        imported = import_knowledge_batch(workspace, exported, document)
        assert imported["ok"] is True, imported
        merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
        assert merge["ok"] is True, merge
        merged = import_knowledge_merge(workspace, merge, _merge_document(paper_id, merge) if not unknown else _all_unknown(paper_id))
        assert merged["ok"] is True, merged
    return finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])


def test_complete_partition_and_record_integration(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(50))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["batch_count"] == 2
    assert planned["planned_chunks"] == 50
    assert planned["processing_complete"] is False
    assigned: list[str] = []
    for index in range(planned["batch_count"]):
        exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=index)
        assert exported["ok"] is True
        assert exported["plan_id"] == planned["plan_id"]
        ids = [item["chunk_id"] for item in exported["context"]["evidence"]]
        assert ids == exported["coverage"]["batch_chunk_ids"]
        assigned.extend(ids)
        imported = import_knowledge_batch(
            workspace,
            exported,
            _knowledge_document(PAPER_A, ids[0]),
        )
        assert imported["ok"] is True
        merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
        assert merge["ok"] is True
        assert "text" not in json.dumps(merge["coverage"])
        imported_merge = import_knowledge_merge(workspace, merge, _merge_document(PAPER_A, merge))
        assert imported_merge["ok"] is True
    assert len(assigned) == 50
    assert len(set(assigned)) == 50
    status = knowledge_batch_status(workspace, plan_id=planned["plan_id"])
    assert status["missing_batches"] == []
    assert status["accepted_batches"] == 2
    assert "uniquealpha" not in json.dumps(status)
    finalized = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert finalized["ok"] is True
    assert finalized["advanced_head"] is True
    assert finalized["processing_complete"] is True
    assert finalized["processed_chunks"] == 50
    listed = list_knowledge(workspace)
    assert listed["ok"] is True
    assert listed["heads"][PAPER_A] == finalized["record_id"]
    assert listed["records"][0]["source_status"] == "current"
    views = build_knowledge_views(workspace)
    assert views["ok"] is True
    retry = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert retry["ok"] is True
    assert retry["reused"] is True
    assert retry["record_id"] == finalized["record_id"]


def test_all_unknown_batch_and_final_close_without_head(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    imported = import_knowledge_batch(workspace, exported, _all_unknown(PAPER_A))
    assert imported["ok"] is True
    listed = list_knowledge(workspace)
    assert listed["heads"] == {}
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    merged = import_knowledge_merge(workspace, merge, _all_unknown(PAPER_A))
    assert merged["ok"] is True
    finalized = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert finalized["ok"] is False
    assert finalized["status"] == INSUFFICIENT_EVIDENCE
    assert finalized["processing_complete"] is True
    assert list_knowledge(workspace)["heads"] == {}


def test_foreign_citation_and_duplicate_conflict(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    other = plan_knowledge_batches(workspace, paper_id=PAPER_B)
    other_export = export_knowledge_batch(workspace, plan_id=other["plan_id"], batch_index=0)
    foreign = other_export["context"]["evidence"][0]["chunk_id"]
    refused = import_knowledge_batch(workspace, exported, _knowledge_document(PAPER_A, foreign))
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BATCH_INVALID
    first = import_knowledge_batch(
        workspace,
        exported,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"]),
    )
    assert first["ok"] is True
    conflict = import_knowledge_batch(
        workspace,
        exported,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"], extra_provisional="method"),
    )
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_BATCH_CONFLICT
    reused = import_knowledge_batch(
        workspace,
        exported,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"]),
    )
    assert reused["reused"] is True


def test_source_drift_and_boolean_index_refuse(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(2))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("uniquealpha", "changedalpha"), encoding="utf-8")
    stale = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    assert stale["ok"] is False
    assert stale["status"] == INDEX_STALE
    clean = _workspace(tmp_path / "clean-missing")
    missing = plan_knowledge_batches(clean, paper_id="sha256:" + ("c" * 64))
    assert missing["status"] == LIGHT_SELECTION_INVALID
    bad_index = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=True)
    assert bad_index["ok"] is False
    assert bad_index["status"] == LIGHT_BATCH_INVALID


def test_skip_merge_and_missing_batch_are_visible(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(50))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    status = knowledge_batch_status(workspace, plan_id=planned["plan_id"])
    assert status["status"] == LIGHT_BATCH_INCOMPLETE
    assert status["missing_batches"] == [0, 1]
    finalize = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert finalize["status"] == LIGHT_BATCH_INCOMPLETE
    first = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=1)
    imported = import_knowledge_batch(
        workspace,
        first,
        _knowledge_document(PAPER_A, first["context"]["evidence"][0]["chunk_id"]),
    )
    assert imported["ok"] is True
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    assert merge["status"] == LIGHT_BATCH_INCOMPLETE
    assert 0 in merge["missing_batches"]


def test_partition_limits_do_not_create_a_job(tmp_path: Path) -> None:
    oversized = {
        "chunk_id": "chk-oversized",
        "page": 1,
        "paper_id": PAPER_A,
        "text": "x" * 80_001,
        "text_end": 80001,
        "text_sha256": "a" * 64,
        "text_start": 0,
    }
    batches, gaps = partition_chunks([oversized])
    assert batches == []
    assert gaps == ["chk-oversized"]
    too_many = [
        {
            "chunk_id": f"chk-{index:04d}",
            "page": index,
            "paper_id": PAPER_A,
            "text": "x",
            "text_end": 1,
            "text_sha256": "b" * 64,
            "text_start": 0,
        }
        for index in range(128 * 48 + 1)
    ]
    batches, gaps = partition_chunks(too_many)
    assert batches == []
    assert gaps
    workspace = _workspace(tmp_path)
    jobs = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME
    assert not jobs.exists() or not list(jobs.iterdir())


def test_no_derived_evidence_has_no_job(tmp_path: Path) -> None:
    workspace = tmp_path / ".work" / "empty"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Empty", [""])
    build_index(workspace)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    assert planned["status"] == INSUFFICIENT_EVIDENCE
    assert not (workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME).exists() or not list(
        (workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME).iterdir()
    )


def test_unknown_extra_job_file_conflicts_and_blocks_backup(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    job = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME / planned["plan_id"]
    extra = job / "notes.txt"
    extra.write_text("foreign extra state\n", encoding="utf-8")
    status = knowledge_batch_status(workspace, plan_id=planned["plan_id"])
    assert status["status"] == LIGHT_BATCH_CONFLICT
    blockers = knowledge_batch_backup_blockers(workspace)
    assert blockers
    assert blockers[0]["status"] == LIGHT_BATCH_CONFLICT
    output = tmp_path / ".work" / "backups" / "blocked.zip"
    output.parent.mkdir(parents=True)
    backup = create_backup(workspace, output=output)
    assert backup["ok"] is False
    assert extra.read_text(encoding="utf-8") == "foreign extra state\n"


def test_interrupted_batch_publish_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    document = _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"])
    from video_paper_wiki_research import light_knowledge_batch as batch

    original = batch.publish_managed_file

    def crash_once(*args, **kwargs):
        relative = kwargs.get("relative_target") or ""
        result = original(*args, **kwargs)
        if str(relative).endswith("batches/0.json"):
            raise RuntimeError("interrupted batch publication")
        return result

    monkeypatch.setattr(batch, "publish_managed_file", crash_once)
    with pytest.raises(RuntimeError, match="interrupted batch publication"):
        import_knowledge_batch(workspace, exported, document)
    monkeypatch.setattr(batch, "publish_managed_file", original)
    recovered = import_knowledge_batch(workspace, exported, document)
    assert recovered["ok"] is True
    staging = workspace / KNOWLEDGE_STATE_DIR / "staging"
    assert not staging.exists() or not list(staging.iterdir())


def test_completed_job_backup_roundtrip_is_historical(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    finalized = _run_batches(workspace, PAPER_A)
    assert finalized["ok"] is True
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("keep user notes\n", encoding="utf-8")
    output = tmp_path / ".work" / "backups" / "knowledge.zip"
    output.parent.mkdir(parents=True)
    created = create_backup(workspace, output=output)
    assert created["ok"] is True
    verified = verify_backup(output)
    assert verified["ok"] is True
    job_prefix = f".light-knowledge/batch-jobs/{finalized['plan_id']}/"
    with zipfile.ZipFile(output) as archive:
        assert any(name.startswith(job_prefix) for name in archive.namelist())
    dest = tmp_path / ".work" / "restored"
    restored = restore_backup(output, destination=dest)
    assert restored["ok"] is True
    assert (dest / "knowledge" / "notes.md").read_text(encoding="utf-8") == "keep user notes\n"
    listed = list_knowledge(dest)
    assert listed["ok"] is True
    assert any(item["record_id"] == finalized["record_id"] for item in listed["records"])
    status = knowledge_batch_status(dest, plan_id=finalized["plan_id"])
    assert status["workspace_status"] == "historical"
    assert status["processing_complete"] is True
    refused = export_knowledge_batch(dest, plan_id=finalized["plan_id"], batch_index=0)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BATCH_INVALID
    assert knowledge_batch_backup_blockers(dest) == []


def test_resurrected_merge_citation_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(50))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    first = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    unused = first["context"]["evidence"][1]["chunk_id"]
    cited = first["context"]["evidence"][0]["chunk_id"]
    import_knowledge_batch(workspace, first, _knowledge_document(PAPER_A, cited))
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    bad = _knowledge_document(PAPER_A, unused)
    refused = import_knowledge_merge(workspace, merge, bad)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BATCH_INVALID


def test_relocated_absolute_context_cannot_resume(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    copied = tmp_path / ".work" / "copied"
    copied.mkdir(parents=True)
    import shutil

    shutil.copytree(workspace, copied, dirs_exist_ok=True)
    refused = export_knowledge_batch(copied, plan_id=planned["plan_id"], batch_index=0)
    assert refused["status"] == LIGHT_BATCH_INVALID
    assert "workspace identity" in refused["message"]


def _write_plan(workspace: Path, plan: dict) -> Path:
    directory = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME / plan["plan_id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / PLAN_FILE).write_bytes(persisted_bytes(plan))
    return directory


def _forged_subset_plan(workspace: Path, source_plan: dict) -> dict:
    row = source_plan["inventory"][0]
    identity = _plan_identity(
        mode="full",
        workspace_id=source_plan["workspace_id"],
        index_id=source_plan["index_id"],
        paper_id=source_plan["paper_id"],
        paper_snapshot=source_plan["paper_snapshot"],
        expected_base_head=source_plan["expected_base_head"],
        inventory=[row],
        partition=[
            {
                "batch_index": 0,
                "chunk_count": 1,
                "chunk_ids": [row["chunk_id"]],
                "text_chars": 12,
            }
        ],
        conservative_full_refresh=False,
        seed_document=None,
    )
    plan_id = sha256_canonical(identity)
    return _plan_object(identity, plan_id)


def test_rehashed_subset_plan_cannot_finalize_as_complete(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(50))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    assert planned["planned_chunks"] == 50
    assert planned["batch_count"] == 2
    source = load_plan(workspace, planned["plan_id"])
    assert source is not None
    forged = _forged_subset_plan(workspace, source)
    assert forged["planned_chunks"] == 1
    assert forged["batch_count"] == 1
    _write_plan(workspace, forged)
    exported = export_knowledge_batch(workspace, plan_id=forged["plan_id"], batch_index=0)
    assert exported["ok"] is False
    assert exported["status"] == LIGHT_BATCH_INVALID
    imported = import_knowledge_batch(
        workspace,
        {
            "ok": True,
            "status": "OK",
            "message": "forged",
            "schema": "video-paper-wiki.light-knowledge-batch-context.v1",
            "plan_id": forged["plan_id"],
            "plan_sha256": forged["plan_sha256"],
            "batch_index": 0,
            "batch_count": 1,
            "coverage": {},
            "paper_snapshot": forged["paper_snapshot"],
            "context": {},
            "prompt": "",
            "context_sha256": "a" * 64,
            "wrapper_sha256": "b" * 64,
        },
        _knowledge_document(PAPER_A, forged["inventory"][0]["chunk_id"]),
    )
    assert imported["ok"] is False
    assert imported["status"] == LIGHT_BATCH_INVALID
    finalized = finalize_knowledge_batches(workspace, plan_id=forged["plan_id"])
    assert finalized["ok"] is False
    assert finalized["status"] == LIGHT_BATCH_INVALID
    assert list_knowledge(workspace)["heads"] == {}


def test_cross_partition_persisted_batch_citation_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, pages_a=_many_pages(50))
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    first = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    second = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=1)
    foreign = second["context"]["evidence"][0]["chunk_id"]
    imported = import_knowledge_batch(
        workspace,
        first,
        _knowledge_document(PAPER_A, first["context"]["evidence"][0]["chunk_id"]),
    )
    assert imported["ok"] is True
    imported_second = import_knowledge_batch(
        workspace,
        second,
        _knowledge_document(PAPER_A, foreign),
    )
    assert imported_second["ok"] is True
    batch_path = (
        workspace
        / KNOWLEDGE_STATE_DIR
        / BATCH_JOBS_DIRNAME
        / planned["plan_id"]
        / BATCHES_DIRNAME
        / "0.json"
    )
    accepted = _load_persisted_object(batch_path)
    assert accepted is not None
    accepted["document"] = _knowledge_document(PAPER_A, foreign)
    accepted["document_sha256"] = sha256_canonical(accepted["document"])
    batch_path.write_bytes(persisted_bytes(accepted))
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    assert merge["ok"] is False
    assert merge["status"] in {LIGHT_BATCH_INVALID, LIGHT_BATCH_CONFLICT, LIGHT_BATCH_INCOMPLETE}
    classified = classify_batch_job(workspace, planned["plan_id"])
    assert classified["kind"] == "conflict"


def test_interruption_after_head_exact_retry_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("keep user notes across interruption\n", encoding="utf-8")
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    document = _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"])
    assert import_knowledge_batch(workspace, exported, document)["ok"] is True
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    assert import_knowledge_merge(workspace, merge, _merge_document(PAPER_A, merge))["ok"] is True
    from video_paper_wiki_research import light_knowledge_batch as batch

    original = batch._publish_job_file

    def crash_before_completion(workspace_root, plan_id, relative, payload):
        if relative == COMPLETION_FILE:
            raise OSError("synthetic interruption before completion publication")
        return original(workspace_root, plan_id, relative, payload)

    monkeypatch.setattr(batch, "_publish_job_file", crash_before_completion)
    with pytest.raises(OSError, match="synthetic interruption before completion publication"):
        finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    monkeypatch.setattr(batch, "_publish_job_file", original)
    heads_after = list_knowledge(workspace)["heads"]
    assert PAPER_A in heads_after
    blockers = knowledge_batch_backup_blockers(workspace)
    assert blockers
    assert blockers[0]["status"] == LIGHT_BATCH_INCOMPLETE
    output = tmp_path / ".work" / "backups" / "blocked.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = create_backup(workspace, output=output)
    assert backup["ok"] is False
    recovered = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert recovered["ok"] is True
    assert recovered["advanced_head"] is True
    assert recovered["record_id"] == heads_after[PAPER_A]
    assert Path(recovered["page_path"]).is_file()
    assert list_knowledge(workspace)["heads"][PAPER_A] == recovered["record_id"]
    assert notes.read_text(encoding="utf-8") == "keep user notes across interruption\n"
    assert knowledge_batch_backup_blockers(workspace) == []


def test_interruption_after_record_before_head_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    document = _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"])
    assert import_knowledge_batch(workspace, exported, document)["ok"] is True
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    assert import_knowledge_merge(workspace, merge, _merge_document(PAPER_A, merge))["ok"] is True
    from video_paper_wiki_research import light_knowledge_batch as batch

    original = batch._set_head

    def crash_before_head(*args, **kwargs):
        raise OSError("synthetic interruption before head adoption")

    monkeypatch.setattr(batch, "_set_head", crash_before_head)
    with pytest.raises(OSError, match="synthetic interruption before head adoption"):
        finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    monkeypatch.setattr(batch, "_set_head", original)
    assert list_knowledge(workspace)["heads"] == {}
    recovered = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert recovered["ok"] is True
    assert recovered["advanced_head"] is True
    assert Path(recovered["page_path"]).is_file()
    assert list_knowledge(workspace)["heads"][PAPER_A] == recovered["record_id"]


def test_completion_nonexistent_record_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    finalized = _run_batches(workspace, PAPER_A)
    assert finalized["ok"] is True
    job = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME / finalized["plan_id"]
    completion_path = job / COMPLETION_FILE
    completion = _load_persisted_object(completion_path)
    assert completion is not None
    fake = "f" * 64
    completion["record_id"] = fake
    completion_path.write_bytes(persisted_bytes(completion))
    classified = classify_batch_job(workspace, finalized["plan_id"])
    assert classified["kind"] == "conflict"
    retry = finalize_knowledge_batches(workspace, plan_id=finalized["plan_id"])
    assert retry["ok"] is False
    assert retry["status"] == LIGHT_BATCH_CONFLICT
    page = Path(workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME / fake / "knowledge.md")
    assert page.exists() is False
    listed = list_knowledge(workspace)
    assert listed["heads"][PAPER_A] == finalized["record_id"]
    assert Path(finalized["page_path"]).is_file()


def test_completed_job_unknown_empty_directory_conflicts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    finalized = _run_batches(workspace, PAPER_A)
    job = workspace / KNOWLEDGE_STATE_DIR / BATCH_JOBS_DIRNAME / finalized["plan_id"]
    extra = job / "mystery"
    extra.mkdir()
    classified = classify_batch_job(workspace, finalized["plan_id"])
    assert classified["kind"] == "conflict"
    blockers = knowledge_batch_backup_blockers(workspace)
    assert blockers
    assert blockers[0]["status"] == LIGHT_BATCH_CONFLICT
    output = tmp_path / ".work" / "backups" / "blocked-dir.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = create_backup(workspace, output=output)
    assert backup["ok"] is False
    assert extra.is_dir()
    assert not any(extra.iterdir())


def test_rehashed_record_diverging_from_final_merge_is_not_current(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    finalized = _run_batches(workspace, PAPER_A)
    original = workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME / finalized["record_id"]
    document = _load_persisted_object(original / "document.json")
    context = _load_persisted_object(original / "context.json")
    identity = _load_persisted_object(original / "identity.json")
    assert document is not None and context is not None and identity is not None
    document["sections"]["summary"]["text"] = "Unrelated forged prose that is not the final merge."
    wrapper = dict(identity["wrapper"])
    wrapper["context_sha256"] = sha256_canonical(context)
    papers = _load_live_papers(workspace)
    assert type(papers) is list
    paper = _paper_by_id(papers, PAPER_A)
    assert paper is not None
    record_id = sha256_canonical({"document": document, "wrapper": _record_wrapper(
        schema=str(wrapper["schema"]),
        paper_id=PAPER_A,
        context=context,
        coverage=wrapper["coverage"],
        paper_snapshot=wrapper["paper_snapshot"],
        prompt=str(wrapper["prompt"]),
    )})
    files = _record_files(
        workspace=workspace,
        record_id=record_id,
        document=document,
        context=context,
        paper=paper,
        wrapper=wrapper,
    )
    dest = workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME / record_id
    dest.mkdir()
    for name, data in files.items():
        (dest / name).write_bytes(data)
    assert dest.is_dir()
    listed = list_knowledge(workspace)
    assert listed["ok"] is True
    forged = [row for row in listed["records"] if row["record_id"] == record_id]
    assert forged
    assert forged[0]["source_status"] == "conflict"
    assert listed["heads"][PAPER_A] == finalized["record_id"]
    assert _record_bundle_ok(workspace, dest) is None


def test_malformed_batch_inputs_close_without_traceback(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    bad_enum = import_knowledge_batch(
        workspace,
        exported,
        {
            "concepts": [],
            "paper_id": PAPER_A,
            "schema": "video-paper-wiki.light-knowledge-document.v1",
            "sections": {
                key: {"citations": [], "status": "maybe", "text": "证据不足"}
                for key in SECTION_KEYS
            },
        },
    )
    assert bad_enum["ok"] is False
    assert bad_enum["status"] == LIGHT_BATCH_INVALID
    assert export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index="0")["status"] == LIGHT_BATCH_INVALID
    assert finalize_knowledge_batches(workspace, plan_id="not-a-hex")["status"] == LIGHT_BATCH_INVALID
    assert knowledge_batch_status(workspace, plan_id=True)["status"] == LIGHT_BATCH_INVALID
    assert export_knowledge_merge_context(workspace, plan_id=123)["status"] == LIGHT_BATCH_INVALID
    assert plan_knowledge_batches(workspace, paper_id="paper-a")["status"] == LIGHT_BATCH_INVALID


def test_intervening_head_is_not_treated_as_own_publication(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    exported = export_knowledge_batch(workspace, plan_id=planned["plan_id"], batch_index=0)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    assert import_knowledge_batch(workspace, exported, _knowledge_document(PAPER_A, chunk))["ok"] is True
    merge = export_knowledge_merge_context(workspace, plan_id=planned["plan_id"])
    assert import_knowledge_merge(workspace, merge, _merge_document(PAPER_A, merge))["ok"] is True
    from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge

    one_shot = export_knowledge_context(workspace, paper_id=PAPER_A)
    intervening = import_knowledge(
        workspace,
        one_shot,
        _knowledge_document(PAPER_A, one_shot["context"]["evidence"][0]["chunk_id"], concept="Intervening"),
    )
    assert intervening["ok"] is True
    refused = finalize_knowledge_batches(workspace, plan_id=planned["plan_id"])
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BATCH_CONFLICT
    assert list_knowledge(workspace)["heads"][PAPER_A] == intervening["record_id"]
    assert Path(intervening["page_path"]).is_file()


def test_raw_symlink_parent_workspace_refuses_all_batch_entrypoints(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    notes = workspace / "knowledge" / "notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("keep-notes\n", encoding="utf-8")
    planned = plan_knowledge_batches(workspace, paper_id=PAPER_A)
    assert planned["ok"] is True
    work = workspace.parent
    alias = work / "alias"
    alias.mkdir()
    differing = _raw_symlink_parent_path(work, target=alias, name="link")
    same_target = _raw_symlink_parent_path(work, target=workspace, name="same")
    plain_parent = workspace / ".." / "ws"
    before = _regular_file_snapshot(workspace)
    dummy = {"schema": "video-paper-wiki.light-knowledge-document.v1"}
    calls = [
        lambda raw: plan_knowledge_batches(raw, paper_id=PAPER_A),
        lambda raw: export_knowledge_batch(raw, plan_id=planned["plan_id"], batch_index=0),
        lambda raw: import_knowledge_batch(raw, dummy, dummy),
        lambda raw: knowledge_batch_status(raw),
        lambda raw: knowledge_batch_status(raw, plan_id=planned["plan_id"]),
        lambda raw: export_knowledge_merge_context(raw, plan_id=planned["plan_id"]),
        lambda raw: import_knowledge_merge(raw, dummy, dummy),
        lambda raw: finalize_knowledge_batches(raw, plan_id=planned["plan_id"]),
        lambda raw: knowledge_batch_backup_blockers(raw),
    ]
    for raw in (differing, same_target, plain_parent, str(differing)):
        for call in calls:
            with pytest.raises(ResearchError) as caught:
                call(raw)
            assert caught.value.code == WORKSPACE_INVALID
            assert _regular_file_snapshot(workspace) == before
            assert notes.read_text(encoding="utf-8") == "keep-notes\n"
            assert list_knowledge(workspace)["heads"] == {}
            assert knowledge_batch_status(workspace, plan_id=planned["plan_id"])["ok"] is True
            assert knowledge_batch_backup_blockers(workspace)
    assert plan_knowledge_batches(workspace, paper_id=PAPER_A)["reused"] is True
    assert _regular_file_snapshot(workspace) == before
