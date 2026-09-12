from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.light_context import LIGHT_WORKSPACE_MISMATCH, export_context
from video_paper_wiki_research.light_index import INDEX_STALE, OK, build_index
from video_paper_wiki_research.light_qa import CONTEXT_SCHEMA
from video_paper_wiki_research.light_workflow import _exclusive_lock, _workspace_lock_path
from video_paper_wiki_research.light_writing import export_writing_context, render_draft
from video_paper_wiki_research.light_writing_project import (
    EXPORT_SCHEMA,
    HEAD_NAME,
    HISTORY_SCHEMA,
    LIGHT_WORKSPACE_BUSY,
    LIGHT_WRITING_PROJECT_CONFLICT,
    LIGHT_WRITING_PROJECT_INVALID,
    OUTLINE_CONTEXT_SCHEMA,
    RESULT_SCHEMA,
    SECTION_CONTEXT_SCHEMA,
    WORKSPACE_INVALID,
    WRITING_DIRNAME,
    export_writing_outline,
    export_writing_project,
    export_writing_section,
    import_writing_outline,
    import_writing_section,
    writing_backup_blockers,
    writing_project_history,
)

PAPER_A = "sha256:" + SHA_A
PAPER_B = "sha256:" + SHA_B
TOPIC = "quasar method nebula writing"
REQUIREMENTS = "用中文写提纲并修订章节。"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / ".work" / "ws"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Alpha paper", ["Synthetic quasar method evidence."])
    _write_paper(workspace, SHA_B, "Beta paper", ["Nebula writing token evidence."])
    built = build_index(workspace)
    assert built["ok"] is True
    return workspace


def _writing_context(workspace: Path) -> dict:
    context = export_context(workspace, kind="writing", query=TOPIC, requirements=REQUIREMENTS)
    assert context["ok"] is True
    assert context["kind"] == "writing"
    return context


def _chunk(context: dict, index: int = 0) -> str:
    return str(context["evidence"][index]["chunk_id"])


def _outline_document(context: dict) -> dict:
    first = _chunk(context, 0)
    second = _chunk(context, 1) if len(context["evidence"]) > 1 else first
    return {
        "schema": "video-paper-wiki.light-writing-outline.v1",
        "sections": [
            {
                "citations": [first],
                "goal": "说明方法证据。",
                "section_id": "s1",
                "status": "provisional",
                "title": "方法",
            },
            {
                "citations": [second],
                "goal": "说明实验证据。",
                "section_id": "s2",
                "status": "provisional",
                "title": "实验",
            },
        ],
        "title": "训练阶段写作提纲",
    }


def _create_project(workspace: Path) -> tuple[dict, dict, dict]:
    context = _writing_context(workspace)
    wrapper = export_writing_outline(workspace, context)
    assert wrapper["ok"] is True
    imported = import_writing_outline(workspace, wrapper, _outline_document(context))
    assert imported["ok"] is True
    assert imported["schema"] == RESULT_SCHEMA
    assert imported["reused"] is False
    assert imported["progress"] == {
        "total": 2,
        "written": 0,
        "unknown": 0,
        "unwritten": 2,
        "complete": False,
    }
    return context, wrapper, imported


def _section_document(project_id: str, section_id: str, chunk_id: str, text: str) -> dict:
    return {
        "citations": [chunk_id],
        "markdown": f"{text} [@{chunk_id}]",
        "project_id": project_id,
        "schema": "video-paper-wiki.light-writing-section.v1",
        "section_id": section_id,
        "status": "provisional",
    }


def _revision_dir(workspace: Path, project_id: str, revision_id: str) -> Path:
    return workspace / WRITING_DIRNAME / "projects" / project_id / "revisions" / revision_id


def _snapshot_revision(workspace: Path, project_id: str, revision_id: str) -> dict[str, bytes]:
    directory = _revision_dir(workspace, project_id, revision_id)
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def test_outline_and_two_section_edits_preserve_history(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, wrapper, imported = _create_project(workspace)
    assert set(wrapper) == {
        "ok",
        "status",
        "message",
        "schema",
        "context",
        "context_sha256",
        "prompt",
    }
    assert wrapper["schema"] == OUTLINE_CONTEXT_SCHEMA
    project_id = imported["project_id"]
    outline_revision = imported["revision_id"]
    outline_bytes = _snapshot_revision(workspace, project_id, outline_revision)

    first_chunk = _chunk(context, 0)
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    assert exported["ok"] is True
    assert exported["schema"] == SECTION_CONTEXT_SCHEMA
    assert exported["parent_revision_id"] == outline_revision
    assert exported["previous_section"] == {
        "citations": [],
        "markdown": "",
        "section_id": "s1",
        "status": "unwritten",
    }
    first = import_writing_section(
        workspace,
        exported,
        _section_document(project_id, "s1", first_chunk, "第一段方法。"),
    )
    assert first["ok"] is True
    assert first["parent_revision_id"] == outline_revision
    assert first["progress"]["written"] == 1
    assert first["progress"]["unwritten"] == 1
    assert first["progress"]["complete"] is False
    assert _snapshot_revision(workspace, project_id, outline_revision) == outline_bytes

    first_bytes = _snapshot_revision(workspace, project_id, first["revision_id"])
    second_chunk = _chunk(context, 1)
    again = export_writing_section(
        workspace,
        project_id=project_id,
        section_id="s2",
        instructions="补实验段。",
    )
    assert again["parent_revision_id"] == first["revision_id"]
    assert again["previous_section"]["status"] == "unwritten"
    second = import_writing_section(
        workspace,
        again,
        _section_document(project_id, "s2", second_chunk, "第二段实验。"),
    )
    assert second["ok"] is True
    assert second["progress"]["complete"] is True
    assert second["progress"]["unwritten"] == 0
    assert _snapshot_revision(workspace, project_id, first["revision_id"]) == first_bytes

    history = writing_project_history(workspace, project_id=project_id)
    assert history["ok"] is True
    assert history["schema"] == HISTORY_SCHEMA
    assert history["head_revision_id"] == second["revision_id"]
    assert [row["kind"] for row in history["revisions"]] == ["outline", "section", "section"]
    assert [row["is_head"] for row in history["revisions"]] == [False, False, True]
    assert all(row["source_status"] == "current" for row in history["revisions"])
    assert history["revisions"][1]["target_section_id"] == "s1"
    assert history["revisions"][2]["target_section_id"] == "s2"

    output = tmp_path / ".work" / "reports" / "draft.md"
    exported_md = export_writing_project(workspace, project_id=project_id, output=output)
    assert exported_md["ok"] is True
    assert exported_md["schema"] == EXPORT_SCHEMA
    assert exported_md["reused"] is False
    assert exported_md["progress"]["complete"] is True
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "训练阶段写作提纲" in text
    assert "模型建议草稿，非正式科学评审。" in text
    assert "第一段方法。" in text
    assert "第二段实验。" in text
    assert "尚未撰写" not in text
    assert "papers/" in text or "source.md#page-" in text
    reused = export_writing_project(workspace, project_id=project_id, output=output)
    assert reused["ok"] is True
    assert reused["reused"] is True
    assert output.read_bytes() == text.encode("utf-8")
    assert writing_backup_blockers(workspace) == []


def test_outline_validation_and_failed_export_are_not_importable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = _writing_context(workspace)
    wrapper = export_writing_outline(workspace, context)
    bad_unknown = {
        "schema": "video-paper-wiki.light-writing-outline.v1",
        "sections": [
            {
                "citations": [],
                "goal": "证据不足",
                "section_id": "s1",
                "status": "unknown",
                "title": "空",
            }
        ],
        "title": "全未知",
    }
    assert import_writing_outline(workspace, wrapper, bad_unknown)["status"] == LIGHT_WRITING_PROJECT_INVALID
    invented = _outline_document(context)
    invented["sections"][0]["citations"] = ["chk-missing"]
    assert import_writing_outline(workspace, wrapper, invented)["status"] == LIGHT_WRITING_PROJECT_INVALID
    marked = _outline_document(context)
    marked["sections"][0]["title"] = "方法[@chunk]"
    assert import_writing_outline(workspace, wrapper, marked)["status"] == LIGHT_WRITING_PROJECT_INVALID
    failed = dict(wrapper)
    failed["ok"] = False
    failed["status"] = LIGHT_WRITING_PROJECT_INVALID
    assert import_writing_outline(workspace, failed, _outline_document(context))["status"] == LIGHT_WRITING_PROJECT_INVALID
    extra = dict(wrapper)
    extra["bonus"] = True
    assert import_writing_outline(workspace, extra, _outline_document(context))["status"] == LIGHT_WRITING_PROJECT_INVALID
    qa = export_context(workspace, kind="qa", query="quasar method")
    assert export_writing_outline(workspace, qa)["status"] == LIGHT_WRITING_PROJECT_INVALID


def test_exact_retry_and_stale_parent_conflict(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    retry = import_writing_outline(workspace, export_writing_outline(workspace, context), _outline_document(context))
    assert retry["ok"] is True
    assert retry["reused"] is True
    assert retry["revision_id"] == imported["revision_id"]

    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    document = _section_document(project_id, "s1", _chunk(context, 0), "方法段。")
    first = import_writing_section(workspace, exported, document)
    assert first["ok"] is True
    same = import_writing_section(workspace, exported, document)
    assert same["ok"] is True
    assert same["reused"] is True
    assert same["revision_id"] == first["revision_id"]

    stale = import_writing_section(
        workspace,
        exported,
        _section_document(project_id, "s1", _chunk(context, 0), "另一段。"),
    )
    assert stale["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    history = writing_project_history(workspace, project_id=project_id)
    assert history["head_revision_id"] == first["revision_id"]
    assert len(history["revisions"]) == 2


def test_user_edits_and_extra_files_are_preserved(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    draft = _revision_dir(workspace, project_id, imported["revision_id"]) / "draft.md"
    original = draft.read_bytes()
    draft.write_text(draft.read_text(encoding="utf-8") + "user note\n", encoding="utf-8")
    edited = draft.read_bytes()
    assert edited != original
    conflict = export_writing_section(workspace, project_id=project_id, section_id="s1")
    assert conflict["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert draft.read_bytes() == edited

    extra = workspace / WRITING_DIRNAME / "projects" / project_id / "notes.md"
    extra.write_text("keep me\n", encoding="utf-8")
    assert writing_project_history(workspace, project_id=project_id)["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert extra.read_text(encoding="utf-8") == "keep me\n"
    blockers = writing_backup_blockers(workspace)
    assert blockers
    assert extra.read_text(encoding="utf-8") == "keep me\n"


def test_head_pointer_retry_after_orphan_revision(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    head = workspace / WRITING_DIRNAME / "projects" / project_id / HEAD_NAME
    assert head.is_file()
    head.unlink()
    blockers = writing_backup_blockers(workspace)
    assert any(item["status"] == "pending" for item in blockers)
    pending = writing_project_history(workspace, project_id=project_id)
    assert pending["ok"] is False
    assert pending["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    recovered = import_writing_outline(workspace, wrapper, _outline_document(context))
    assert recovered["ok"] is True
    assert recovered["revision_id"] == imported["revision_id"]
    assert json.loads(head.read_text(encoding="utf-8"))["revision_id"] == imported["revision_id"]
    assert writing_backup_blockers(workspace) == []


def test_stale_source_cannot_resume_and_history_survives_relocation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    first = import_writing_section(
        workspace,
        exported,
        _section_document(project_id, "s1", _chunk(context, 0), "方法段。"),
    )
    assert first["ok"] is True

    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar method evidence", "changed evidence"), encoding="utf-8")
    stale = export_writing_section(workspace, project_id=project_id, section_id="s2")
    assert stale["status"] == INDEX_STALE
    rebuilt = build_index(workspace)
    assert rebuilt["ok"] is True
    stale_after = export_writing_section(workspace, project_id=project_id, section_id="s2")
    assert stale_after["status"] == INDEX_STALE

    moved = tmp_path / ".work" / "relocated"
    shutil.copytree(workspace, moved)
    history = writing_project_history(moved, project_id=project_id)
    assert history["ok"] is True
    assert {row["source_status"] for row in history["revisions"]} == {"historical"}
    live = export_writing_section(moved, project_id=project_id, section_id="s2")
    assert live["status"] == LIGHT_WORKSPACE_MISMATCH
    assert writing_backup_blockers(moved) == []
    shutil.rmtree(workspace / "papers")
    missing = writing_project_history(workspace, project_id=project_id)
    assert missing["ok"] is True
    assert {row["source_status"] for row in missing["revisions"]} == {"missing-source"}


def test_export_refuses_unwritten_and_preserves_different_bytes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _context, _wrapper, imported = _create_project(workspace)
    output = tmp_path / ".work" / "empty.md"
    refused = export_writing_project(workspace, project_id=imported["project_id"], output=output)
    assert refused["status"] == LIGHT_WRITING_PROJECT_INVALID
    assert not output.exists()

    context = _writing_context(workspace)
    project_id = imported["project_id"]
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    written = import_writing_section(
        workspace,
        exported,
        _section_document(project_id, "s1", _chunk(context, 0), "已写。"),
    )
    assert written["ok"] is True
    incomplete = tmp_path / ".work" / "incomplete.md"
    exported_md = export_writing_project(workspace, project_id=project_id, output=incomplete)
    assert exported_md["ok"] is True
    assert exported_md["progress"]["complete"] is False
    assert "尚未撰写" in incomplete.read_text(encoding="utf-8")
    output.write_text("external edit\n", encoding="utf-8")
    conflict = export_writing_project(workspace, project_id=project_id, output=output)
    assert conflict["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert output.read_text(encoding="utf-8") == "external edit\n"


def test_foreign_citations_and_instruction_bound(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    foreign = _section_document(project_id, "s1", "chk-missing", "伪造。")
    foreign["citations"] = ["chk-missing"]
    foreign["markdown"] = "伪造。 [@chk-missing]"
    assert import_writing_section(workspace, exported, foreign)["status"] == LIGHT_WRITING_PROJECT_INVALID
    mismatch = _section_document(project_id, "s1", _chunk(context, 0), "缺标记。")
    mismatch["markdown"] = "缺标记。"
    assert import_writing_section(workspace, exported, mismatch)["status"] == LIGHT_WRITING_PROJECT_INVALID
    unknown = {
        "citations": [],
        "markdown": "证据不足",
        "project_id": project_id,
        "schema": "video-paper-wiki.light-writing-section.v1",
        "section_id": "s1",
        "status": "unknown",
    }
    accepted = import_writing_section(workspace, exported, unknown)
    assert accepted["ok"] is True
    assert accepted["progress"]["unknown"] == 1
    too_long = export_writing_section(
        workspace,
        project_id=project_id,
        section_id="s2",
        instructions="x" * 4001,
    )
    assert too_long["status"] == LIGHT_WRITING_PROJECT_INVALID


def test_backup_blockers_and_workspace_rules(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert writing_backup_blockers(workspace) == []
    writing = workspace / WRITING_DIRNAME
    writing.mkdir()
    (writing / "staging").mkdir()
    assert writing_backup_blockers(workspace) == []
    (writing / "staging" / "orphan.txt").write_text("x\n", encoding="utf-8")
    assert writing_backup_blockers(workspace)
    outside = tmp_path / "not-work" / "ws"
    outside.mkdir(parents=True)
    missing = export_writing_outline(outside, {"schema": CONTEXT_SCHEMA, "kind": "writing"})
    assert missing["status"] == WORKSPACE_INVALID


def test_workspace_busy_is_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = _writing_context(workspace)
    started = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with _exclusive_lock(_workspace_lock_path(workspace), workspace):
            started.set()
            release.wait(2)

    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(2)
    try:
        result = export_writing_outline(workspace, context)
        assert result["status"] == LIGHT_WORKSPACE_BUSY
    finally:
        release.set()
        thread.join()


def test_repeated_edit_of_same_section_keeps_other_section(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    first = import_writing_section(
        workspace,
        export_writing_section(workspace, project_id=project_id, section_id="s1"),
        _section_document(project_id, "s1", _chunk(context, 0), "初稿。"),
    )
    assert first["ok"] is True
    other = import_writing_section(
        workspace,
        export_writing_section(workspace, project_id=project_id, section_id="s2"),
        _section_document(project_id, "s2", _chunk(context, 1), "实验初稿。"),
    )
    assert other["ok"] is True
    other_bytes = _snapshot_revision(workspace, project_id, other["revision_id"])
    second = import_writing_section(
        workspace,
        export_writing_section(workspace, project_id=project_id, section_id="s1"),
        _section_document(project_id, "s1", _chunk(context, 0), "修订稿。"),
    )
    assert second["ok"] is True
    assert second["parent_revision_id"] == other["revision_id"]
    assert second["revision_id"] != other["revision_id"]
    assert _snapshot_revision(workspace, project_id, other["revision_id"]) == other_bytes
    document = json.loads((_revision_dir(workspace, project_id, second["revision_id"]) / "document.json").read_text(encoding="utf-8"))
    by_id = {item["section_id"]: item for item in document["sections"]}
    assert by_id["s2"]["markdown"] == "实验初稿。 [@" + _chunk(context, 1) + "]"
    assert "修订稿。" in by_id["s1"]["markdown"]


def test_legacy_writing_helpers_remain_unchanged(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="writing", query=TOPIC, requirements=REQUIREMENTS)
    draft = render_draft(
        context,
        {
            "citations": [{"chunk_id": _chunk(context, 0)}],
            "markdown": f"旧写作路径。 [@{_chunk(context, 0)}]",
        },
    )
    assert draft["ok"] is True
    retrieval = {
        "evidence": context["evidence"],
        "index_id": context["index_id"],
        "message": "",
        "ok": True,
        "query": TOPIC,
        "status": OK,
    }
    legacy = export_writing_context(TOPIC, REQUIREMENTS, [PAPER_A], retrieval)
    assert legacy["kind"] == "writing"
    assert legacy["schema"] == CONTEXT_SCHEMA
