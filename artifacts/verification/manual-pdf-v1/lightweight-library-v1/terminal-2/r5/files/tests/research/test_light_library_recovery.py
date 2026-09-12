from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_backup import create_backup
from video_paper_wiki_research.light_library import (
    archive_paper,
    library_backup_blockers,
    recover_library,
    replace_paper,
    restore_paper,
)
import video_paper_wiki_research.light_library as library
from video_paper_wiki_research.light_library_state import (
    LIGHT_LIBRARY_INVALID,
    LIGHT_LIBRARY_NEEDS_RECOVERY,
    OUTCOME_ABORTED_BEFORE_STAGING,
    persisted_bytes,
    set_library_inject_hook,
)
from video_paper_wiki_research.light_pdf import extract_pdf


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / ".work" / "library"
    root.mkdir(parents=True)
    return root


def _add(tmp_path: Path, workspace: Path, name: str, text: str) -> dict:
    pdf = _write_pdf(tmp_path / f"{name}.pdf", _pdf_with_page_texts([text]))
    result = extract_pdf(pdf, workspace, title=name)
    assert result["ok"] is True
    return result


def test_archive_interrupt_before_and_after_move(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "rec-arc", "Recovery archive body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("recover me\n", encoding="utf-8")
    before = note.read_bytes()

    def _before(_point: str) -> None:
        raise RuntimeError("stop before archive move")

    set_library_inject_hook("before_archive_move", _before)
    with __import__("pytest").raises(RuntimeError, match="stop before archive move"):
        archive_paper(workspace, paper_id)
    set_library_inject_hook(None)
    assert (workspace / "papers" / digest / "notes.md").read_bytes() == before
    recovered = recover_library(workspace)
    assert recovered["ok"] is True
    assert not (workspace / "papers" / digest).exists()
    listed_ops = recovered["operations"]
    assert listed_ops[0]["ok"] is True

    added2 = _add(tmp_path, workspace, "rec-arc2", "Second recovery archive body.")
    paper_id2 = added2["paper_id"]
    digest2 = paper_id2.split(":", 1)[1]
    (Path(added2["markdown_path"]).parent / "notes.md").write_text("after-move note\n", encoding="utf-8")

    def _after(_point: str) -> None:
        raise RuntimeError("stop after archive move")

    set_library_inject_hook("after_archive_move", _after)
    with __import__("pytest").raises(RuntimeError, match="stop after archive move"):
        archive_paper(workspace, paper_id2)
    set_library_inject_hook(None)
    assert not (workspace / "papers" / digest2).exists()
    recovered2 = recover_library(workspace)
    assert recovered2["ok"] is True
    archives = list((workspace / ".light-library" / "archive").iterdir())
    assert any((item / "paper" / "notes.md").exists() for item in archives if item.is_dir())


def test_restore_interrupt_and_exact_recovery(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "rec-res", "Restore recovery body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("restore note\n", encoding="utf-8")
    archived = archive_paper(workspace, paper_id)
    archive_id = archived["archive_id"]

    def _after(_point: str) -> None:
        raise RuntimeError("stop after restore move")

    set_library_inject_hook("after_restore_move", _after)
    with __import__("pytest").raises(RuntimeError, match="stop after restore move"):
        restore_paper(workspace, archive_id)
    set_library_inject_hook(None)
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "restore note\n"
    recovered = recover_library(workspace)
    assert recovered["ok"] is True
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "restore note\n"


def test_replace_interrupt_keeps_good_copy(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "rec-rep", "Replace old body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("old only\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "rep-new.pdf", _pdf_with_page_texts(["Replace new body."]))

    def _before_old(_point: str) -> None:
        raise RuntimeError("stop before old archive")

    set_library_inject_hook("before_old_archive", _before_old)
    with __import__("pytest").raises(RuntimeError, match="stop before old archive"):
        replace_paper(workspace, paper_id, new_pdf, title="New")
    set_library_inject_hook(None)
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "old only\n"
    recovered = recover_library(workspace)
    assert recovered["ok"] is True
    assert not (workspace / "papers" / digest).exists()
    archived_old = next(
        item / "paper" / "notes.md"
        for item in (workspace / ".light-library" / "archive").iterdir()
        if item.is_dir() and (item / "paper" / "notes.md").exists()
    )
    assert archived_old.read_text(encoding="utf-8") == "old only\n"

    def _after_old(_point: str) -> None:
        raise RuntimeError("stop after old archive")

    added2 = _add(tmp_path, workspace, "rec-rep2", "Second replace old body.")
    paper_id2 = added2["paper_id"]
    (Path(added2["markdown_path"]).parent / "notes.md").write_text("second old\n", encoding="utf-8")
    new_pdf2 = _write_pdf(tmp_path / "rep-new2.pdf", _pdf_with_page_texts(["Second replace new body."]))
    set_library_inject_hook("after_old_archive", _after_old)
    with __import__("pytest").raises(RuntimeError, match="stop after old archive"):
        replace_paper(workspace, paper_id2, new_pdf2, title="New2")
    set_library_inject_hook(None)
    recovered2 = recover_library(workspace)
    assert recovered2["ok"] is True
    assert not (workspace / "papers" / paper_id2.split(":", 1)[1]).exists()
    new_dirs = [path for path in (workspace / "papers").iterdir() if path.is_dir() and path.name != digest]
    assert new_dirs
    assert (new_dirs[0] / "prior-paper-notes.md").is_file()


def test_foreign_journal_is_preserved(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _add(tmp_path, workspace, "foreign", "Foreign journal body.")
    ops = workspace / ".light-library" / "operations"
    ops.mkdir(parents=True)
    foreign = ops / "deadbeefdeadbeefdeadbeefdeadbeef.json"
    foreign.write_text("{not-a-journal\n", encoding="utf-8")
    before = foreign.read_bytes()
    result = recover_library(workspace)
    assert result["ok"] is False
    assert result["status"] in {LIGHT_LIBRARY_INVALID, LIGHT_LIBRARY_NEEDS_RECOVERY, "LIGHT_LIBRARY_INVALID"}
    assert foreign.read_bytes() == before
    assert json.loads(json.dumps(result["operations"][0]))["ok"] is False


def _interrupt(point: str, call) -> None:
    def _stop(_point: str) -> None:
        raise RuntimeError("stop at " + point)

    set_library_inject_hook(point, _stop)
    with pytest.raises(RuntimeError, match="stop at " + point):
        call()
    set_library_inject_hook(None)


def test_archive_recovery_checks_moved_payload_again(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "edit-arc", "Edited archive recovery body.")
    paper_id = added["paper_id"]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("original archive note\n", encoding="utf-8")
    _interrupt("after_archive_move", lambda: archive_paper(workspace, paper_id))
    archive = next((workspace / ".light-library" / "archive").iterdir())
    note = archive / "paper" / "notes.md"
    changed = b"Modified after interruption\n"
    note.write_bytes(changed)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert note.read_bytes() == changed


def test_restore_recovery_checks_live_payload_again(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "edit-res", "Edited restore recovery body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("restore original\n", encoding="utf-8")
    archived = archive_paper(workspace, paper_id)
    _interrupt("after_restore_move", lambda: restore_paper(workspace, archived["archive_id"]))
    note = workspace / "papers" / digest / "notes.md"
    changed = b"Modified after restore interruption\n"
    note.write_bytes(changed)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert note.read_bytes() == changed


def test_replace_recovery_validates_staged_inventory_before_old_move(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "edit-rep", "Edited replace old body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("old stay\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "edit-rep-new.pdf", _pdf_with_page_texts(["Edited replace new body."]))
    _interrupt("after_replace_staged", lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    stage = next((workspace / ".light-library" / "staging").iterdir())
    new_digest = next((stage / "workspace" / "papers").iterdir()).name
    note = stage / "workspace" / "papers" / new_digest / "prior-paper-notes.md"
    changed = b"User edited staged attribution; preserve it\n"
    note.write_bytes(changed)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert (workspace / "papers" / digest).is_dir()
    assert note.read_bytes() == changed


def test_pre_staging_recovery_preserves_foreign_nested_content(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "foreign-stage", "Foreign stage body.")
    paper_id = added["paper_id"]
    new_pdf = _write_pdf(tmp_path / "foreign-stage-new.pdf", _pdf_with_page_texts(["Foreign stage new body."]))
    _interrupt("after_intent", lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    stage = next((workspace / ".light-library" / "staging").iterdir())
    extra = stage / "workspace" / "user-note.md"
    extra.parent.mkdir(exist_ok=True)
    extra.write_bytes(b"Unrecognized user addition\n")
    result = recover_library(workspace)
    assert result["ok"] is False
    assert extra.is_file() and extra.read_bytes() == b"Unrecognized user addition\n"


def test_clean_pre_staging_settles_aborted_before_staging(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "abort-clean", "Clean abort body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("keep live\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "abort-clean-new.pdf", _pdf_with_page_texts(["Clean abort new body."]))
    _interrupt("after_intent", lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    recovered = recover_library(workspace)
    assert recovered["ok"] is True
    op = recovered["operations"][0]
    assert op["ok"] is True
    assert op.get("outcome") == OUTCOME_ABORTED_BEFORE_STAGING
    assert op.get("replaced") is False
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "keep live\n"
    assert not (workspace / ".light-library" / "staging").exists() or not any((workspace / ".light-library" / "staging").iterdir())
    assert library_backup_blockers(workspace) is None
    backup = create_backup(workspace, output=tmp_path / ".work" / "abort-clean.zip")
    assert backup["ok"] is True


def test_changed_journal_paths_are_refused_before_move(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "paths", "Changed journal path body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    (Path(added["markdown_path"]).parent / "notes.md").write_text("stay live\n", encoding="utf-8")
    _interrupt("after_intent", lambda: archive_paper(workspace, paper_id))
    path = next((workspace / ".light-library" / "operations").glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    value["owned_relative_paths"] = ["../../foreign/"]
    changed = persisted_bytes(value)
    path.write_bytes(changed)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert path.read_bytes() == changed
    assert (workspace / "papers" / digest).is_dir()


def test_pre_staging_preserves_unknown_empty_directory(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "emptydir", "Empty dir body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    new_pdf = _write_pdf(tmp_path / "emptydir-new.pdf", _pdf_with_page_texts(["Empty dir new body."]))
    _interrupt("after_intent", lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    stage = next((workspace / ".light-library" / "staging").iterdir())
    unknown = stage / "workspace" / "user-folder" / "empty-child"
    unknown.mkdir(parents=True)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert unknown.is_dir()
    assert (workspace / "papers" / digest).is_dir()


@pytest.mark.parametrize("foreign", ["foreign-paper", "edited-lock"])
def test_final_stage_cleanup_validates_actual_producer_ownership(tmp_path: Path, foreign: str) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "ownstage", "Owner stage body.")
    paper_id = added["paper_id"]
    new_pdf = _write_pdf(tmp_path / "ownstage-new.pdf", _pdf_with_page_texts(["Owner stage new body."]))
    _interrupt("after_new_publish", lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    stage = next((workspace / ".light-library" / "staging").iterdir())
    if foreign == "foreign-paper":
        path = stage / "workspace" / "papers" / ("f" * 64) / "source.md"
        path.parent.mkdir(parents=True)
    else:
        path = stage / "workspace" / ".light-workflow" / "locks" / "workspace.lock"
        assert path.is_file()
    original = b"User-owned content introduced before recovery; preserve.\n"
    path.write_bytes(original)
    result = recover_library(workspace)
    assert result["ok"] is False
    assert path.is_file() and path.read_bytes() == original


def _refused(call):
    try:
        result = call()
    except ResearchError:
        return None
    assert result.get("ok") is False, result
    return result


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("addition", ["unknown-file", "unknown-empty-dir", "prior-note"])
def test_after_intent_addition_is_preserved_before_capture_and_publication(tmp_path: Path, addition: str) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "precapture", "Precapture old body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("keep the live old note\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "precapture-new.pdf", _pdf_with_page_texts(["Precapture new body."]))
    new_digest = _sha256_file(new_pdf)
    added_paths: list[Path] = []
    content = b"User addition before extraction; never adopt or overwrite.\n"

    def introduce(_point: str) -> None:
        stage = next((workspace / ".light-library" / "staging").iterdir())
        if addition == "unknown-empty-dir":
            path = stage / "workspace" / "user-empty"
            path.mkdir(parents=True)
        elif addition == "prior-note":
            path = stage / "workspace" / "papers" / new_digest / "prior-paper-notes.md"
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
        else:
            path = stage / "workspace" / "user-note.md"
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
        added_paths.append(path)

    set_library_inject_hook("after_intent", introduce)
    try:
        _refused(lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    finally:
        set_library_inject_hook(None)
    assert len(added_paths) == 1
    if addition == "unknown-empty-dir":
        assert added_paths[0].is_dir()
    else:
        assert added_paths[0].is_file() and added_paths[0].read_bytes() == content
    assert (workspace / "papers" / digest / "notes.md").is_file()
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "keep the live old note\n"


@pytest.mark.parametrize("addition", ["unknown-file", "unknown-empty-dir", "prior-note", "changed-lock"])
def test_postextract_foreign_bytes_are_preserved_before_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    addition: str,
) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "postextract", "Postextract old body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("keep the live old note\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "postextract-new.pdf", _pdf_with_page_texts(["Postextract new body."]))
    new_digest = _sha256_file(new_pdf)
    original = library.extract_pdf
    added_paths: list[Path] = []
    content = b"User content introduced before producer inventory capture.\n"

    def inject(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result.get("ok") is True
        stage_ws = args[1]
        if addition == "unknown-empty-dir":
            target = stage_ws / "user-empty"
            target.mkdir()
        elif addition == "prior-note":
            target = stage_ws / "papers" / new_digest / "prior-paper-notes.md"
            target.write_bytes(content)
        elif addition == "changed-lock":
            target = stage_ws / ".light-workflow" / "locks" / "workspace.lock"
            assert target.is_file()
            target.write_bytes(content)
        else:
            target = stage_ws / "user-note.md"
            target.write_bytes(content)
        added_paths.append(target)
        return result

    monkeypatch.setattr(library, "extract_pdf", inject)
    _refused(lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    assert len(added_paths) == 1
    if addition == "unknown-empty-dir":
        assert added_paths[0].is_dir()
    else:
        assert added_paths[0].is_file() and added_paths[0].read_bytes() == content
    assert (workspace / "papers" / digest / "notes.md").is_file()
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "keep the live old note\n"


@pytest.mark.parametrize("point", ["after_replace_staged", "before_old_archive"])
@pytest.mark.parametrize("addition", ["unknown-file", "unknown-empty-dir", "changed-lock"])
def test_known_stage_ownership_is_rechecked_before_old_move(tmp_path: Path, point: str, addition: str) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "premove", "Premove old body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("keep the live old note\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "premove-new.pdf", _pdf_with_page_texts(["Premove new body."]))
    added_paths: list[Path] = []
    content = b"User content introduced after ownership inventory.\n"

    def inject(_point: str) -> None:
        stage = next((workspace / ".light-library" / "staging").iterdir())
        if addition == "unknown-empty-dir":
            target = stage / "workspace" / "user-empty"
            target.mkdir()
        elif addition == "changed-lock":
            target = stage / "workspace" / ".light-workflow" / "locks" / "workspace.lock"
            target.write_bytes(content)
        else:
            target = stage / "workspace" / "user-note.md"
            target.write_bytes(content)
        added_paths.append(target)

    set_library_inject_hook(point, inject)
    try:
        _refused(lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    finally:
        set_library_inject_hook(None)
    assert len(added_paths) == 1
    if addition == "unknown-empty-dir":
        assert added_paths[0].is_dir()
    else:
        assert added_paths[0].is_file() and added_paths[0].read_bytes() == content
    assert (workspace / "papers" / digest / "notes.md").is_file()
    assert (workspace / "papers" / digest / "notes.md").read_text(encoding="utf-8") == "keep the live old note\n"


def test_before_old_archive_old_paper_edit_keeps_live_payload(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "late-old", "Late old-paper body.")
    paper_id = added["paper_id"]
    digest = paper_id.split(":", 1)[1]
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("original live note\n", encoding="utf-8")
    new_pdf = _write_pdf(tmp_path / "late-old-new.pdf", _pdf_with_page_texts(["Late old-paper new body."]))
    changed = b"User edited the old live paper after the stale inventory check.\n"

    def inject(_point: str) -> None:
        note.write_bytes(changed)

    set_library_inject_hook("before_old_archive", inject)
    try:
        _refused(lambda: replace_paper(workspace, paper_id, new_pdf, title="New"))
    finally:
        set_library_inject_hook(None)
    assert note.is_file() and note.read_bytes() == changed
    assert (workspace / "papers" / digest).is_dir()
