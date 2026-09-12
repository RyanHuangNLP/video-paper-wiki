from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_backup import create_backup, restore_backup, verify_backup
from video_paper_wiki_research.light_index import build_index
from video_paper_wiki_research.light_library import archive_paper
from video_paper_wiki_research.light_library_state import (
    LIGHT_BACKUP_CONFLICT,
    LIGHT_BACKUP_INVALID,
    LIGHT_LIBRARY_NEEDS_RECOVERY,
    set_library_inject_hook,
)
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_workflow import prepare_workflow, workflow_status


def _workspace(tmp_path: Path, name: str = "ws") -> Path:
    root = tmp_path / ".work" / name
    root.mkdir(parents=True)
    return root


def _add(tmp_path: Path, workspace: Path, name: str, text: str) -> dict:
    pdf = _write_pdf(tmp_path / f"{name}.pdf", _pdf_with_page_texts([text]))
    result = extract_pdf(pdf, workspace, title=name)
    assert result["ok"] is True
    return result


def _output(tmp_path: Path, name: str = "backup.zip") -> Path:
    folder = tmp_path / ".work" / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def test_backup_exclusions_and_byte_exact_restore(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "bk", "Backup lexical body token.")
    paper_id = added["paper_id"]
    Path(added["markdown_path"]).parent.joinpath("notes.md").write_text("workspace note\n", encoding="utf-8")
    (workspace / "reports").mkdir()
    (workspace / "reports" / "draft.md").write_text("inside report\n", encoding="utf-8")
    built = build_index(workspace)
    assert built["ok"] is True
    prepared = prepare_workflow(workspace, kind="writing", query="Backup lexical", paper_ids=[paper_id])
    assert prepared["ok"] is True
    session_dir = Path(prepared["context_path"]).parent
    session_files = {name: (session_dir / name).read_bytes() for name in ("request.json", "context.json", "manifest.json")}
    extra = tmp_path / ".work" / "external.md"
    extra.write_text("external draft\n", encoding="utf-8")
    output = _output(tmp_path)
    created = create_backup(workspace, output=output, extra_outputs=[extra])
    assert created["ok"] is True
    assert created["reused"] is False
    excluded = {item["path"] for item in created["exclusions"]}
    assert any(path.endswith("index.v1.json") or path.startswith(".light-index") for path in excluded)
    verified = verify_backup(output)
    assert verified["ok"] is True
    assert verified["workspace_id"] == created["workspace_id"]
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "LIGHT-LIBRARY-MANIFEST.json"
        assert all(not name.endswith("/") for name in names)
        assert ".light-index/index.v1.json" not in names
        history_prefix = f".light-workflow/history/{created['workspace_id']}/sessions/"
        assert any(name.startswith(history_prefix) for name in names)
        assert not any(name.startswith(".light-workflow/sessions/") for name in names)
        info = archive.getinfo(history_prefix + f"{session_dir.name}/context.json")
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.compress_type == zipfile.ZIP_STORED
    dest = tmp_path / ".work" / "restored"
    restored = restore_backup(output, destination=dest)
    assert restored["ok"] is True
    new_paper = dest / "papers" / paper_id.split(":", 1)[1]
    assert (new_paper / "notes.md").read_bytes() == b"workspace note\n"
    assert (new_paper / "source.md").read_bytes() == Path(added["markdown_path"]).read_bytes()
    assert (dest / "reports" / "draft.md").read_text(encoding="utf-8") == "inside report\n"
    hist = Path(restored["historical_session_root"])
    assert hist.is_dir()
    for name, data in session_files.items():
        assert (hist / session_dir.name / name).read_bytes() == data
    assert not (dest / ".light-workflow" / "sessions").exists() or not any((dest / ".light-workflow" / "sessions").iterdir())
    status = workflow_status(dest)
    assert status["ok"] is True
    assert status["sessions"] == []
    exported = dest / "exports" / "external" / created["extra_outputs"][0]["hash"] / "external.md"
    assert exported.read_text(encoding="utf-8") == "external draft\n"
    assert not (dest / ".light-index" / "index.v1.json").exists()
    empty_conflict = restore_backup(output, destination=dest)
    assert empty_conflict["ok"] is False
    assert empty_conflict["status"] == LIGHT_BACKUP_CONFLICT


def test_backup_refuses_pending_and_binary_and_links(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "unsafe")
    added = _add(tmp_path, workspace, "bad", "Unsafe backup body.")
    paper_id = added["paper_id"]

    def _stop(_point: str) -> None:
        raise RuntimeError("leave pending archive")

    set_library_inject_hook("after_intent", _stop)
    with pytest.raises(RuntimeError, match="leave pending archive"):
        archive_paper(workspace, paper_id)
    set_library_inject_hook(None)
    pending = create_backup(workspace, output=_output(tmp_path, "pending.zip"))
    assert pending["ok"] is False
    assert pending["status"] in {LIGHT_LIBRARY_NEEDS_RECOVERY, LIGHT_BACKUP_INVALID}

    workspace2 = _workspace(tmp_path, "binary")
    added2 = _add(tmp_path, workspace2, "bin", "Binary extra body.")
    (Path(added2["markdown_path"]).parent / "secret.pdf").write_bytes(b"%PDF-1.4 extra")
    binary = create_backup(workspace2, output=_output(tmp_path, "binary.zip"))
    assert binary["ok"] is False
    assert binary["status"] == LIGHT_BACKUP_INVALID

    workspace3 = _workspace(tmp_path, "link")
    added3 = _add(tmp_path, workspace3, "lnk", "Symlink extra body.")
    (Path(added3["markdown_path"]).parent / "alias.md").symlink_to("notes.md")
    linked = create_backup(workspace3, output=_output(tmp_path, "link.zip"))
    assert linked["ok"] is False

    workspace4 = _workspace(tmp_path, "hard")
    added4 = _add(tmp_path, workspace4, "hl", "Hardlink extra body.")
    src = Path(added4["markdown_path"]).parent / "notes.md"
    src.write_text("note\n", encoding="utf-8")
    os.link(src, Path(added4["markdown_path"]).parent / "copy.md")
    hard = create_backup(workspace4, output=_output(tmp_path, "hard.zip"))
    assert hard["ok"] is False


def test_backup_oversize_tamper_and_create_only(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "size")
    added = _add(tmp_path, workspace, "sz", "Oversize body.")
    huge = Path(added["markdown_path"]).parent / "huge.txt"
    huge.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    oversize = create_backup(workspace, output=_output(tmp_path, "huge.zip"))
    assert oversize["ok"] is False
    assert oversize["status"] == LIGHT_BACKUP_INVALID
    huge.unlink()
    (Path(added["markdown_path"]).parent / "notes.md").write_text("ok\n", encoding="utf-8")
    output = _output(tmp_path, "good.zip")
    first = create_backup(workspace, output=output)
    assert first["ok"] is True
    reused = create_backup(workspace, output=output)
    assert reused["ok"] is True
    assert reused["reused"] is True
    (Path(added["markdown_path"]).parent / "notes.md").write_text("changed\n", encoding="utf-8")
    conflict = create_backup(workspace, output=output)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_BACKUP_CONFLICT
    assert output.read_bytes() == Path(first["archive_path"]).read_bytes()
    with zipfile.ZipFile(output, "r") as original:
        members = {info.filename: original.read(info.filename) for info in original.infolist()}
    target = next(name for name in members if name.endswith("notes.md"))
    members[target] = b"tampered notes\n"
    from video_paper_wiki_research.light_backup import _zip_info

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, data in members.items():
            archive.writestr(_zip_info(name), data)
    bad = verify_backup(output)
    assert bad["ok"] is False
    assert bad["status"] == LIGHT_BACKUP_INVALID


def test_backup_source_race_is_detected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "race")
    added = _add(tmp_path, workspace, "race", "Race body.")
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("before\n", encoding="utf-8")

    def _flip(_point: str) -> None:
        note.write_text("after\n", encoding="utf-8")

    set_library_inject_hook("after_backup_snapshot", _flip)
    result = create_backup(workspace, output=_output(tmp_path, "race.zip"))
    set_library_inject_hook(None)
    assert result["ok"] is False
    assert result["status"] == LIGHT_BACKUP_CONFLICT
    assert not (_output(tmp_path, "race.zip")).exists()


def test_backup_rejects_output_inside_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "inside")
    _add(tmp_path, workspace, "in", "Inside output body.")
    with pytest.raises(ResearchError):
        create_backup(workspace, output=workspace / "out.zip")


def test_verify_refuses_traversal_and_internal_extra(tmp_path: Path) -> None:
    from video_paper_wiki_research.light_backup import _zip_info

    archive = _output(tmp_path, "traverse.zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as zf:
        zf.writestr(_zip_info("LIGHT-LIBRARY-MANIFEST.json"), b"{}\n")
        zf.writestr(_zip_info("../evil.md"), b"no\n")
    bad = verify_backup(archive)
    assert bad["ok"] is False
    assert bad["status"] == LIGHT_BACKUP_INVALID
    workspace = _workspace(tmp_path, "extra-in")
    _add(tmp_path, workspace, "ex", "Extra inside body.")
    inside = workspace / "reports"
    inside.mkdir()
    report = inside / "dup.md"
    report.write_text("already inside\n", encoding="utf-8")
    refused = create_backup(workspace, output=_output(tmp_path, "dup.zip"), extra_outputs=[report])
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BACKUP_INVALID
