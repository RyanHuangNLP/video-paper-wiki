from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import build_index, search
from video_paper_wiki_research.light_library import (
    archive_paper,
    list_papers,
    recover_library,
    replace_paper,
    restore_paper,
    update_paper_metadata,
)
from video_paper_wiki_research.light_library_state import (
    LIGHT_LIBRARY_CONFLICT,
    LIGHT_LIBRARY_INVALID,
    LIGHT_WORKSPACE_BUSY,
    persisted_bytes,
    try_workspace_lock,
    write_persisted_atomic,
)
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_workflow import _exclusive_lock, _workspace_lock_path, prepare_workflow, workflow_status


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / ".work" / "library"
    root.mkdir(parents=True)
    return root


def _add_paper(tmp_path: Path, workspace: Path, name: str, text: str, *, title: str) -> dict:
    pdf = _write_pdf(tmp_path / f"{name}.pdf", _pdf_with_page_texts([text]))
    result = extract_pdf(pdf, workspace, title=title)
    assert result["ok"] is True
    return result


def test_title_and_tags_noop_and_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "meta", "Metadata body token.", title="Original")
    paper_id = added["paper_id"]
    meta_path = Path(added["metadata_path"])
    md_path = Path(added["markdown_path"])
    before_md = md_path.read_bytes()
    before_json = meta_path.read_bytes()
    listed = list_papers(workspace)
    assert listed["ok"] is True
    assert listed["papers"][0]["title"] == "Original"
    assert listed["papers"][0]["tags"] == []
    noop = update_paper_metadata(workspace, paper_id, title="Original", tags=[])
    assert noop["ok"] is True
    assert noop["reused"] is True
    assert meta_path.read_bytes() == before_json
    assert md_path.read_bytes() == before_md
    preserve = update_paper_metadata(workspace, paper_id)
    assert preserve["reused"] is True
    changed = update_paper_metadata(workspace, paper_id, title="Renamed", tags=["alpha", "beta"])
    assert changed["ok"] is True
    assert changed["reused"] is False
    assert changed["title"] == "Renamed"
    assert changed["tags"] == ["alpha", "beta"]
    assert md_path.read_bytes() == before_md
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["title"] == "Renamed"
    assert meta["tags"] == ["alpha", "beta"]
    assert meta["source"]["sha256"] == paper_id.split(":", 1)[1]
    listed = list_papers(workspace)
    assert listed["index_state"] == "missing"
    assert listed["papers"][0]["tags"] == ["alpha", "beta"]


def test_metadata_preserves_notes_and_stales_index_and_session(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "stale", "Stale session lexical token.", title="Live")
    paper_id = added["paper_id"]
    paper_dir = Path(added["markdown_path"]).parent
    note = paper_dir / "notes.md"
    note.write_text("user note remains\n", encoding="utf-8")
    built = build_index(workspace)
    assert built["ok"] is True
    prepared = prepare_workflow(workspace, kind="qa", query="lexical token", paper_ids=[paper_id])
    assert prepared["ok"] is True
    session_id = prepared["session_id"]
    context_before = Path(prepared["context_path"]).read_bytes()
    updated = update_paper_metadata(workspace, paper_id, title="After edit")
    assert updated["ok"] is True
    assert note.read_text(encoding="utf-8") == "user note remains\n"
    listed = list_papers(workspace)
    assert listed["index_state"] == "stale"
    searched = search(workspace, "lexical token")
    assert searched["ok"] is False
    assert searched["status"] == "INDEX_STALE"
    status = workflow_status(workspace, session_id=session_id)
    assert status["ok"] is True
    assert status["state"] == "stale"
    assert Path(prepared["context_path"]).read_bytes() == context_before


def test_active_workspace_lock_refuses_mutation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "busy", "Busy lock body.", title="Busy")
    held = try_workspace_lock(workspace)
    assert held is not None
    try:
        result = archive_paper(workspace, added["paper_id"])
        assert result["ok"] is False
        assert result["status"] == LIGHT_WORKSPACE_BUSY
        assert (workspace / "papers" / added["paper_id"].split(":", 1)[1]).is_dir()
    finally:
        held.release()


def test_archive_restore_roundtrip_and_conflicts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "arc", "Archive body token.", title="Archivable")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    paper_dir = Path(added["markdown_path"]).parent
    (paper_dir / "notes.md").write_text("keep this note\n", encoding="utf-8")
    source_md = (paper_dir / "source.md").read_bytes()
    source_json = (paper_dir / "source.json").read_bytes()
    build_index(workspace)
    archived = archive_paper(workspace, paper_id)
    assert archived["ok"] is True
    assert archived["reused"] is False
    archive_id = archived["archive_id"]
    assert not (workspace / "papers" / digest).exists()
    payload = workspace / ".light-library" / "archive" / archive_id / "paper"
    assert (payload / "notes.md").read_text(encoding="utf-8") == "keep this note\n"
    assert (payload / "source.md").read_bytes() == source_md
    assert (payload / "source.json").read_bytes() == source_json
    meta = json.loads((payload / "source.json").read_text(encoding="utf-8"))
    assert meta["document"]["path"] == f"papers/{digest}/source.md"
    listed = list_papers(workspace)
    assert listed["papers"] == []
    assert listed["archives"][0]["archive_id"] == archive_id
    searched = search(workspace, "Archive body")
    assert searched["ok"] is False
    assert searched["status"] in {"INDEX_STALE", "LIGHT_SELECTION_INVALID"}
    again = archive_paper(workspace, paper_id)
    assert again["ok"] is True
    assert again["reused"] is True
    restored = restore_paper(workspace, archive_id)
    assert restored["ok"] is True
    assert restored["reused"] is False
    live = workspace / "papers" / digest
    assert (live / "notes.md").read_text(encoding="utf-8") == "keep this note\n"
    assert (live / "source.md").read_bytes() == source_md
    assert not (payload).exists()
    reused = restore_paper(workspace, archive_id)
    assert reused["ok"] is True
    assert reused["reused"] is True
    (workspace / "papers" / digest / "notes.md").write_text("changed after restore\n", encoding="utf-8")
    conflict = restore_paper(workspace, archive_id)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_LIBRARY_CONFLICT
    assert (live / "notes.md").read_text(encoding="utf-8") == "changed after restore\n"


def test_replace_duplicate_conflict_and_old_note_attribution(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = _add_paper(tmp_path, workspace, "old", "Old paper lexical body.", title="Old")
    second = _add_paper(tmp_path, workspace, "other", "Other live paper body.", title="Other")
    old_id = first["paper_id"]
    other_id = second["paper_id"]
    paper_dir = Path(first["markdown_path"]).parent
    notes = paper_dir / "notes.md"
    notes.write_text("notes about the old PDF only\n", encoding="utf-8")
    same = replace_paper(workspace, old_id, tmp_path / "old.pdf")
    assert same["ok"] is True
    assert same["reused"] is True
    assert notes.read_text(encoding="utf-8") == "notes about the old PDF only\n"
    conflict = replace_paper(workspace, old_id, tmp_path / "other.pdf")
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_LIBRARY_CONFLICT
    assert notes.read_text(encoding="utf-8") == "notes about the old PDF only\n"
    replacement_pdf = _write_pdf(tmp_path / "new.pdf", _pdf_with_page_texts(["Brand new replacement body."]))
    replaced = replace_paper(workspace, old_id, replacement_pdf, title="New")
    assert replaced["ok"] is True
    assert replaced["reused"] is False
    assert replaced["paper_id"] == old_id
    assert replaced["new_paper_id"] != old_id
    assert not (workspace / "papers" / old_id.split(":", 1)[1]).exists()
    new_dir = workspace / "papers" / replaced["new_paper_id"].split(":", 1)[1]
    prior = new_dir / "prior-paper-notes.md"
    assert prior.is_file()
    text = prior.read_text(encoding="utf-8")
    assert "not statements about the current PDF" in text
    assert old_id in text
    assert replaced["archive_id"] in text
    assert "notes.md" in text
    assert not (new_dir / "notes.md").exists()
    archive_notes = workspace / ".light-library" / "archive" / replaced["archive_id"] / "paper" / "notes.md"
    assert archive_notes.read_text(encoding="utf-8") == "notes about the old PDF only\n"
    assert any(path.endswith("paper/notes.md") for path in replaced["retained_note_paths"])
    assert (new_dir / "source.md").read_text(encoding="utf-8").find("notes about the old PDF") == -1
    listed = list_papers(workspace)
    ids = {item["paper_id"] for item in listed["papers"]}
    assert replaced["new_paper_id"] in ids
    assert other_id in ids
    assert old_id not in ids


def test_invalid_workspace_and_paper_id(tmp_path: Path) -> None:
    outside = tmp_path / "not-work"
    outside.mkdir()
    with pytest.raises(ResearchError) as caught:
        list_papers(outside)
    assert caught.value.code == "WORKSPACE_INVALID"
    workspace = _workspace(tmp_path)
    with pytest.raises(ResearchError):
        update_paper_metadata(workspace, "not-a-paper")
    missing = archive_paper(workspace, "sha256:" + ("a" * 64))
    assert missing["ok"] is False
    assert missing["status"] == LIGHT_LIBRARY_INVALID


@pytest.mark.parametrize("hardlink", [False, True])
def test_metadata_never_overwrites_unowned_temporary_file(tmp_path: Path, hardlink: bool) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "tmpown", "Unowned temp body.", title="Tmp")
    paper_dir = Path(added["markdown_path"]).parent
    path = paper_dir / "source.json.tmp"
    original = b"User-owned temporary note; never discard\n"
    alias = tmp_path / ".work" / "unrelated-note.md"
    if hardlink:
        alias.write_bytes(original)
        os.link(alias, path)
    else:
        path.write_bytes(original)
    try:
        update_paper_metadata(workspace, added["paper_id"], title="Changed title")
    except ResearchError:
        pass
    assert path.is_file() and path.read_bytes() == original
    if hardlink:
        assert alias.read_bytes() == original


def test_native_add_workspace_lock_precedes_paper_layout(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _add_paper(tmp_path, workspace, "lockroot", "Existing library body.", title="Root")
    pdf = _write_pdf(tmp_path / "empty-add.pdf", _pdf_with_page_texts(["Empty target body."]))
    target = workspace.parent / "empty"
    target.mkdir()
    with _exclusive_lock(_workspace_lock_path(target), target):
        result = extract_pdf(pdf, target)
        assert result["ok"] is False
        assert result["status"] == LIGHT_WORKSPACE_BUSY
        assert not (target / "papers").exists()
        assert not (target / ".light-transactions").exists()


def test_exact_replace_retry_reuses_same_event(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = _add_paper(tmp_path, workspace, "old-retry", "Old retry body.", title="Old")
    new_pdf = _write_pdf(tmp_path / "new-retry.pdf", _pdf_with_page_texts(["Brand new retry body."]))
    replaced = replace_paper(workspace, first["paper_id"], new_pdf, title="New")
    assert replaced["ok"] is True
    again = replace_paper(workspace, first["paper_id"], new_pdf, title="New")
    assert again["ok"] is True
    assert again.get("reused") is True
    assert again["archive_id"] == replaced["archive_id"]


def test_forged_complete_journal_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _add_paper(tmp_path, workspace, "forge", "Forged journal body.", title="Forge")
    ops = workspace / ".light-library" / "operations"
    ops.mkdir(parents=True)
    path = ops / "deadbeefdeadbeefdeadbeefdeadbeef.json"
    forged = {
        "schema": "video-paper-wiki.light-library-operation.v1",
        "operation_id": None,
        "kind": "archive",
        "paper_id": None,
        "archive_id": None,
        "phase": "complete",
        "owned_relative_paths": [],
        "source_inventory": [],
        "file_inventory": [],
        "extra": "not-documented",
    }
    path.write_bytes((json.dumps(forged) + "\n").encode("utf-8"))
    before = path.read_bytes()
    result = recover_library(workspace)
    assert result["ok"] is False
    assert path.read_bytes() == before


def test_complete_journal_both_sides_is_conflict(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "both", "Both sides body.", title="Both")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    live = workspace / "papers" / digest
    note = live / "notes.md"
    note.write_text("keep both sides\n", encoding="utf-8")
    archived = archive_paper(workspace, paper_id)
    assert archived["ok"] is True
    archive_payload = workspace / ".light-library" / "archive" / archived["archive_id"] / "paper"
    live.mkdir()
    for name in ("source.md", "source.json", "notes.md"):
        (live / name).write_bytes((archive_payload / name).read_bytes())
    result = recover_library(workspace)
    assert result["ok"] is False
    assert result["status"] == LIGHT_LIBRARY_CONFLICT
    assert (archive_payload / "notes.md").read_text(encoding="utf-8") == "keep both sides\n"
    assert (live / "notes.md").read_text(encoding="utf-8") == "keep both sides\n"


def test_archive_manifest_unknown_id_and_empty_directories_are_invalid(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add_paper(tmp_path, workspace, "man", "Manifest shape body.", title="Man")
    paper_id = added["paper_id"]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("note\n", encoding="utf-8")
    archived = archive_paper(workspace, paper_id)
    archive_id = archived["archive_id"]
    manifest_path = workspace / ".light-library" / "archive" / archive_id / "manifest.json"
    original = json.loads(manifest_path.read_text(encoding="utf-8"))

    extra = dict(original)
    extra["unexpected"] = True
    manifest_path.write_bytes(persisted_bytes(extra))
    refused_extra = restore_paper(workspace, archive_id)
    assert refused_extra["ok"] is False
    assert (workspace / ".light-library" / "archive" / archive_id / "paper" / "notes.md").read_text(encoding="utf-8") == "note\n"

    mismatch = dict(original)
    mismatch["archive_id"] = "0" * 32
    manifest_path.write_bytes(persisted_bytes(mismatch))
    refused_id = restore_paper(workspace, archive_id)
    assert refused_id["ok"] is False

    empty_dirs = dict(original)
    empty_dirs["directories"] = []
    manifest_path.write_bytes(persisted_bytes(empty_dirs))
    refused_dirs = restore_paper(workspace, archive_id)
    assert refused_dirs["ok"] is False
    assert (workspace / ".light-library" / "archive" / archive_id / "paper" / "notes.md").read_text(encoding="utf-8") == "note\n"


def test_write_persisted_atomic_does_not_reuse_existing_tmp(tmp_path: Path) -> None:
    parent = tmp_path / ".work" / "json"
    parent.mkdir(parents=True)
    dest = parent / "managed.json"
    dest.write_text("{}\n", encoding="utf-8")
    tmp = parent / "managed.json.tmp"
    original = b"unrelated tmp bytes\n"
    tmp.write_bytes(original)
    write_persisted_atomic(dest, {"schema": "video-paper-wiki.light-library.v1", "ok": True})
    assert tmp.read_bytes() == original
    assert json.loads(dest.read_text(encoding="utf-8"))["ok"] is True
