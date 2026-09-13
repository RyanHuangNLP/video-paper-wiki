from __future__ import annotations

import copy
import enum
import hashlib
import json
import shutil
import threading
from pathlib import Path

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import LIGHT_CONTEXT_INVALID, LIGHT_WORKSPACE_MISMATCH, export_context
from video_paper_wiki_research.light_index import INDEX_STALE, OK, build_index
from video_paper_wiki_research.light_qa import CONTEXT_SCHEMA
from video_paper_wiki_research.light_workflow import _exclusive_lock, _workspace_lock_path, persisted_bytes, sha256_canonical
from video_paper_wiki_research.light_writing import export_writing_context, render_draft
from video_paper_wiki_research import light_writing_project as writing
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
    context = _writing_context(workspace)
    wrapper = export_writing_outline(workspace, context)
    document = _outline_document(context)
    real_publish = writing._publish_head

    def fail_head(*_args: object, **_kwargs: object) -> None:
        raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic pointer interruption")

    writing._publish_head = fail_head
    try:
        interrupted = import_writing_outline(workspace, wrapper, document)
    finally:
        writing._publish_head = real_publish
    assert interrupted["ok"] is False
    assert interrupted["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    blockers = writing_backup_blockers(workspace)
    assert any(item["status"] == "pending" for item in blockers)
    projects = workspace / WRITING_DIRNAME / "projects"
    project_id = next(path.name for path in projects.iterdir() if path.is_dir())
    pending = writing_project_history(workspace, project_id=project_id)
    assert pending["ok"] is False
    assert pending["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert any(item["status"] == "pending" for item in pending["diagnostics"])
    recovered = import_writing_outline(workspace, wrapper, document)
    assert recovered["ok"] is True
    assert recovered["revision_id"]
    head = workspace / WRITING_DIRNAME / "projects" / recovered["project_id"] / HEAD_NAME
    assert json.loads(head.read_text(encoding="utf-8"))["revision_id"] == recovered["revision_id"]
    assert writing_backup_blockers(workspace) == []

    head.unlink()
    blockers = writing_backup_blockers(workspace)
    assert blockers
    assert all(item["status"] != "pending" for item in blockers)
    missing = writing_project_history(workspace, project_id=recovered["project_id"])
    assert missing["ok"] is False
    assert all(item["status"] != "pending" for item in missing["diagnostics"])
    refused_outline = import_writing_outline(workspace, wrapper, document)
    assert refused_outline["ok"] is False
    assert refused_outline["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    exported = export_writing_section(workspace, project_id=recovered["project_id"], section_id="s1")
    assert exported["ok"] is False


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


def test_ordinary_multiline_markdown_and_instructions(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    chunk = _chunk(context)
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    document = _section_document(project_id, "s1", chunk, "第一段。")
    document["markdown"] = f"First paragraph.\n\n- Second paragraph. [@{chunk}]"
    first = import_writing_section(workspace, exported, document)
    assert first["ok"] is True
    stored = json.loads((_revision_dir(workspace, project_id, first["revision_id"]) / "document.json").read_text(encoding="utf-8"))
    assert stored["sections"][0]["markdown"] == document["markdown"]
    same = import_writing_section(workspace, exported, document)
    assert same["ok"] is True
    assert same["reused"] is True
    assert same["revision_id"] == first["revision_id"]
    again = export_writing_section(
        workspace,
        project_id=project_id,
        section_id="s2",
        instructions="Explain method.\nPreserve uncertainty.",
    )
    assert again["ok"] is True
    assert again["instructions"] == "Explain method.\nPreserve uncertainty."
    second = import_writing_section(
        workspace,
        again,
        _section_document(project_id, "s2", _chunk(context, 1), "列表段。"),
    )
    assert second["ok"] is True
    outline = _outline_document(context)
    outline["sections"][0]["title"] = "方法\n换行"
    assert import_writing_outline(workspace, export_writing_outline(workspace, context), outline)["status"] == LIGHT_WRITING_PROJECT_INVALID
    bad = _section_document(project_id, "s2", _chunk(context, 1), "坏。")
    bad["markdown"] = f"bad{chr(0xD800)} [@ {_chunk(context, 1)}]"
    bad["citations"] = [_chunk(context, 1)]
    assert import_writing_section(workspace, again, bad)["ok"] is False


def test_section_publication_interruptions_and_missing_head(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    outline_id = imported["revision_id"]
    outline_bytes = _snapshot_revision(workspace, project_id, outline_id)
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    document = _section_document(project_id, "s1", _chunk(context), "Synthetic method")
    head = workspace / WRITING_DIRNAME / "projects" / project_id / HEAD_NAME
    head_bytes = head.read_bytes()

    real_revision = writing._publish_revision

    def fail_revision(*_args: object, **_kwargs: object) -> bool:
        raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic revision interruption")

    writing._publish_revision = fail_revision
    try:
        before_revision = import_writing_section(workspace, exported, document)
    finally:
        writing._publish_revision = real_revision
    assert before_revision["ok"] is False
    assert before_revision["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert head.read_bytes() == head_bytes
    assert _snapshot_revision(workspace, project_id, outline_id) == outline_bytes

    after_revision = import_writing_section(workspace, exported, document)
    assert after_revision["ok"] is True
    first_id = after_revision["revision_id"]
    first_bytes = _snapshot_revision(workspace, project_id, first_id)

    real_head = writing._publish_head

    def fail_head(*_args: object, **_kwargs: object) -> None:
        raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic pointer interruption")

    workspace_retry = _workspace(tmp_path / "retry")
    context_retry, _wrapper_retry, imported_retry = _create_project(workspace_retry)
    exported_retry = export_writing_section(workspace_retry, project_id=imported_retry["project_id"], section_id="s1")
    document_retry = _section_document(imported_retry["project_id"], "s1", _chunk(context_retry), "Synthetic method")
    writing._publish_head = fail_head
    try:
        interrupted = import_writing_section(workspace_retry, exported_retry, document_retry)
    finally:
        writing._publish_head = real_head
    assert interrupted["ok"] is False
    retried = import_writing_section(workspace_retry, exported_retry, document_retry)
    assert retried["ok"] is True
    different_retry = import_writing_section(
        workspace_retry,
        exported_retry,
        _section_document(imported_retry["project_id"], "s1", _chunk(context_retry), "另一段。"),
    )
    assert different_retry["status"] == LIGHT_WRITING_PROJECT_CONFLICT

    real_cleanup = writing._cleanup_empty_staging
    s2_export = export_writing_section(workspace, project_id=project_id, section_id="s2")
    s2_document = _section_document(project_id, "s2", _chunk(context, 1), "实验。")
    writing._cleanup_empty_staging = lambda *_args, **_kwargs: None
    try:
        leftover = import_writing_section(workspace, s2_export, s2_document)
    finally:
        writing._cleanup_empty_staging = real_cleanup
    assert leftover["ok"] is True
    reused = import_writing_section(workspace, s2_export, s2_document)
    assert reused["ok"] is True
    assert reused["reused"] is True
    assert _snapshot_revision(workspace, project_id, first_id) == first_bytes

    missing_ws = _workspace(tmp_path / "missing")
    context_m, _wrapper_m, imported_m = _create_project(missing_ws)
    exported_m = export_writing_section(missing_ws, project_id=imported_m["project_id"], section_id="s1")
    document_m = _section_document(imported_m["project_id"], "s1", _chunk(context_m), "Synthetic method")
    writing._head_path(missing_ws, imported_m["project_id"]).unlink()
    missing = import_writing_section(missing_ws, exported_m, document_m)
    assert missing["ok"] is False
    assert missing["status"] == LIGHT_WRITING_PROJECT_CONFLICT

    foreign = _workspace(tmp_path / "foreign")
    context_f, _wrapper_f, imported_f = _create_project(foreign)
    exported_f = export_writing_section(foreign, project_id=imported_f["project_id"], section_id="s1")
    document_f = _section_document(imported_f["project_id"], "s1", _chunk(context_f), "Synthetic method")
    staging = foreign / WRITING_DIRNAME / "staging" / "foreign-dir"
    staging.mkdir(parents=True)
    (staging / "x.txt").write_text("nope\n", encoding="utf-8")
    edited = import_writing_section(foreign, exported_f, document_f)
    assert edited["ok"] is False
    assert edited["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert (staging / "x.txt").read_text(encoding="utf-8") == "nope\n"

    boom_ws = _workspace(tmp_path / "boom")
    context_b, _wrapper_b, imported_b = _create_project(boom_ws)
    exported_b = export_writing_section(boom_ws, project_id=imported_b["project_id"], section_id="s1")
    document_b = _section_document(imported_b["project_id"], "s1", _chunk(context_b), "Synthetic method")
    outline_b = imported_b["revision_id"]
    outline_b_bytes = _snapshot_revision(boom_ws, imported_b["project_id"], outline_b)
    head_b = boom_ws / WRITING_DIRNAME / "projects" / imported_b["project_id"] / HEAD_NAME
    head_b_bytes = head_b.read_bytes()

    def boom(*_args: object, **_kwargs: object) -> bool:
        raise OSError("disk full")

    writing._publish_revision = boom
    try:
        failed_fs = import_writing_section(boom_ws, exported_b, document_b)
    finally:
        writing._publish_revision = real_revision
    assert failed_fs["ok"] is False
    assert failed_fs["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert head_b.read_bytes() == head_b_bytes
    assert _snapshot_revision(boom_ws, imported_b["project_id"], outline_b) == outline_b_bytes


def test_raw_path_safety_and_managed_output_parents(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    document = _section_document(project_id, "s1", _chunk(context), "已写。")
    assert import_writing_section(workspace, exported, document)["ok"] is True

    target = workspace / ".light-index" / "new-parent" / "draft.md"
    refused = export_writing_project(workspace, project_id=project_id, output=target)
    assert refused["ok"] is False
    assert not target.exists()
    assert not target.parent.exists()

    other = tmp_path / "outside" / "subdir"
    other.mkdir(parents=True)
    link = tmp_path / ".work" / "link"
    link.symlink_to(other, target_is_directory=True)
    unsafe = link / ".." / "unexpected.md"
    raw = export_writing_project(workspace, project_id=project_id, output=unsafe)
    assert raw["ok"] is False
    assert not (tmp_path / ".work" / "unexpected.md").exists()
    assert not (tmp_path / "outside" / "unexpected.md").exists()

    reports = tmp_path / ".work" / "reports" / "draft.md"
    exported_md = export_writing_project(workspace, project_id=project_id, output=reports)
    assert exported_md["ok"] is True
    assert reports.is_file()

    traversal = workspace / ".." / workspace.name
    assert export_writing_outline(traversal, context)["ok"] is False
    assert export_writing_section(traversal, project_id=project_id, section_id="s1")["ok"] is False
    assert writing_project_history(traversal, project_id=project_id)["ok"] is False
    assert writing_backup_blockers(traversal)


def test_history_replay_rejects_rehashed_draft_and_invalid_transition(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    revision_id = imported["revision_id"]
    directory = _revision_dir(workspace, project_id, revision_id)
    draft = directory / "draft.md"
    draft.write_text("Synthetic edited historical draft.\n", encoding="utf-8")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if row["path"] == "draft.md":
            data = draft.read_bytes()
            row["sha256"] = hashlib.sha256(data).hexdigest()
            row["size_bytes"] = len(data)
    (directory / "manifest.json").write_bytes(persisted_bytes(manifest))
    history = writing_project_history(workspace, project_id=project_id)
    assert history["ok"] is False
    blockers = writing_backup_blockers(workspace)
    assert blockers

    transition = _workspace(tmp_path / "transition")
    context_t, _wrapper_t, imported_t = _create_project(transition)
    pid, parent = imported_t["project_id"], imported_t["revision_id"]
    parentdir = _revision_dir(transition, pid, parent)
    parentdoc = json.loads((parentdir / "document.json").read_text(encoding="utf-8"))
    childdoc = copy.deepcopy(parentdoc)
    childdoc.update(kind="section", target_section_id="s1", parent_revision_id=parent)
    childdoc["sections"][1].update(
        status="provisional",
        markdown="Fabricated unrelated-section change [@chk-missing]",
        citations=["chk-missing"],
    )
    rid = writing._revision_identity(
        project_id=pid,
        parent_revision_id=parent,
        context_sha256=sha256_canonical(context_t),
        document=childdoc,
    )
    files = writing._revision_files(
        workspace=transition,
        project_id=pid,
        revision_id=rid,
        parent_revision_id=parent,
        context=context_t,
        document=childdoc,
    )
    childdir = writing._revision_dir(transition, pid, rid)
    childdir.mkdir()
    for name, data in files.items():
        (childdir / name).write_bytes(data)
    writing._head_path(transition, pid).write_bytes(
        persisted_bytes({"schema": writing.HEAD_SCHEMA, "project_id": pid, "revision_id": rid})
    )
    assert writing_project_history(transition, project_id=pid)["ok"] is False
    assert export_writing_section(transition, project_id=pid, section_id="s1")["ok"] is False
    assert writing_backup_blockers(transition)

    class Boom(enum.Enum):
        X = "x"

    live = _workspace(tmp_path / "enum")
    context_e, _wrapper_e, imported_e = _create_project(live)
    exported_e = export_writing_section(live, project_id=imported_e["project_id"], section_id="s1")
    wrapper = copy.deepcopy(exported_e)
    wrapper["context"]["query"] = Boom.X
    closed = import_writing_section(
        live,
        wrapper,
        _section_document(imported_e["project_id"], "s1", _chunk(context_e), "方法。"),
    )
    assert closed["ok"] is False


def _writing_tree(workspace: Path) -> dict[str, bytes]:
    root = workspace / WRITING_DIRNAME
    if not root.exists():
        return {}
    rows: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rows[str(path.relative_to(workspace))] = path.read_bytes()
    return rows


def _revision_count(workspace: Path, project_id: str) -> int:
    root = workspace / WRITING_DIRNAME / "projects" / project_id / "revisions"
    if not root.exists():
        return 0
    return sum(1 for item in root.iterdir() if item.is_dir() and not item.is_symlink())


def _persist_mutated(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_bytes(persisted_bytes(payload))


def test_first_outline_interruptions_recover_owned_intent(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "before-own")
    context = _writing_context(workspace)
    wrapper = export_writing_outline(workspace, context)
    document = _outline_document(context)
    real_create = writing._create_staging

    def fail_before_ownership(*args: object, kind: object, **kwargs: object):
        if kind == writing.PENDING_HEAD_KIND:
            raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic before ownership")
        return real_create(*args, kind=kind, **kwargs)

    writing._create_staging = fail_before_ownership
    try:
        before_own = import_writing_outline(workspace, wrapper, document)
    finally:
        writing._create_staging = real_create
    assert before_own["ok"] is False
    assert before_own["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    recovered = import_writing_outline(workspace, wrapper, document)
    assert recovered["ok"] is True
    assert recovered["reused"] is False
    project_id = recovered["project_id"]
    revision_id = recovered["revision_id"]
    assert _revision_count(workspace, project_id) == 1
    assert json.loads((workspace / WRITING_DIRNAME / "projects" / project_id / HEAD_NAME).read_text(encoding="utf-8"))[
        "revision_id"
    ] == revision_id

    payload_ws = _workspace(tmp_path / "payload")
    payload_context = _writing_context(payload_ws)
    payload_wrapper = export_writing_outline(payload_ws, payload_context)
    payload_document = _outline_document(payload_context)
    real_write = writing._write_payload_tree

    def fail_intent_payload(payload: Path, files: dict[str, bytes]) -> None:
        if set(files) == {writing.INTENT_NAME}:
            raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic intent payload interruption")
        real_write(payload, files)

    writing._write_payload_tree = fail_intent_payload
    try:
        before_payload = import_writing_outline(payload_ws, payload_wrapper, payload_document)
    finally:
        writing._write_payload_tree = real_write
    assert before_payload["ok"] is False
    assert before_payload["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    payload_retry = import_writing_outline(payload_ws, payload_wrapper, payload_document)
    assert payload_retry["ok"] is True
    assert _revision_count(payload_ws, payload_retry["project_id"]) == 1

    after_rev_ws = _workspace(tmp_path / "after-rev")
    after_context = _writing_context(after_rev_ws)
    after_wrapper = export_writing_outline(after_rev_ws, after_context)
    after_document = _outline_document(after_context)
    real_revision = writing._publish_revision

    def fail_after_revision(*args: object, **kwargs: object) -> bool:
        result = real_revision(*args, **kwargs)
        raise OSError("synthetic failure immediately after revision publication before pending intent")

    writing._publish_revision = fail_after_revision
    try:
        after_revision = import_writing_outline(after_rev_ws, after_wrapper, after_document)
    finally:
        writing._publish_revision = real_revision
    assert after_revision["ok"] is False
    assert after_revision["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert "publication filesystem failure" in after_revision["message"]
    projects = after_rev_ws / WRITING_DIRNAME / "projects"
    after_pid = next(path.name for path in projects.iterdir() if path.is_dir())
    assert _revision_count(after_rev_ws, after_pid) == 1
    assert not writing._head_path(after_rev_ws, after_pid).exists()
    after_retry = import_writing_outline(after_rev_ws, after_wrapper, after_document)
    assert after_retry["ok"] is True
    assert after_retry["project_id"] == after_pid
    assert _revision_count(after_rev_ws, after_pid) == 1
    assert after_retry["revision_id"] == next(
        path.name for path in (projects / after_pid / "revisions").iterdir() if path.is_dir()
    )

    cleanup_ws = _workspace(tmp_path / "cleanup")
    cleanup_context = _writing_context(cleanup_ws)
    cleanup_wrapper = export_writing_outline(cleanup_ws, cleanup_context)
    cleanup_document = _outline_document(cleanup_context)
    real_cleanup = writing._cleanup_pending_head_intent

    def fail_cleanup(*_args: object, **_kwargs: object) -> None:
        raise ResearchError(LIGHT_WRITING_PROJECT_CONFLICT, "synthetic after HEAD before cleanup")

    writing._cleanup_pending_head_intent = fail_cleanup
    try:
        after_head = import_writing_outline(cleanup_ws, cleanup_wrapper, cleanup_document)
    finally:
        writing._cleanup_pending_head_intent = real_cleanup
    assert after_head["ok"] is False
    cleanup_retry = import_writing_outline(cleanup_ws, cleanup_wrapper, cleanup_document)
    assert cleanup_retry["ok"] is True
    assert _revision_count(cleanup_ws, cleanup_retry["project_id"]) == 1

    unowned_ws = _workspace(tmp_path / "unowned")
    unowned_context = _writing_context(unowned_ws)
    unowned_wrapper = export_writing_outline(unowned_ws, unowned_context)
    unowned_document = _outline_document(unowned_context)
    writing._publish_revision = fail_after_revision
    try:
        unowned_first = import_writing_outline(unowned_ws, unowned_wrapper, unowned_document)
    finally:
        writing._publish_revision = real_revision
    assert unowned_first["ok"] is False
    staging = unowned_ws / WRITING_DIRNAME / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    refused_unowned = import_writing_outline(unowned_ws, unowned_wrapper, unowned_document)
    assert refused_unowned["ok"] is False
    assert refused_unowned["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    unowned_pid = next(path.name for path in (unowned_ws / WRITING_DIRNAME / "projects").iterdir() if path.is_dir())
    assert not writing._head_path(unowned_ws, unowned_pid).exists()
    assert _revision_count(unowned_ws, unowned_pid) == 1

    edited_ws = _workspace(tmp_path / "edited")
    edited_context = _writing_context(edited_ws)
    edited_wrapper = export_writing_outline(edited_ws, edited_context)
    edited_document = _outline_document(edited_context)
    writing._publish_revision = fail_after_revision
    try:
        edited_first = import_writing_outline(edited_ws, edited_wrapper, edited_document)
    finally:
        writing._publish_revision = real_revision
    assert edited_first["ok"] is False
    edited_staging = edited_ws / WRITING_DIRNAME / "staging"
    touched = False
    for item in edited_staging.rglob("*"):
        if item.is_file() and item.name == writing.INTENT_NAME:
            item.write_bytes(item.read_bytes() + b" ")
            touched = True
            break
    assert touched
    edited_retry = import_writing_outline(edited_ws, edited_wrapper, edited_document)
    assert edited_retry["ok"] is False
    assert edited_retry["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    edited_pid = next(path.name for path in (edited_ws / WRITING_DIRNAME / "projects").iterdir() if path.is_dir())
    assert not writing._head_path(edited_ws, edited_pid).exists()

    different = copy.deepcopy(after_document)
    different["title"] = "另一提纲"
    different_result = import_writing_outline(after_rev_ws, after_wrapper, different)
    assert different_result.get("project_id") != after_pid or different_result["ok"] is False
    assert json.loads((projects / after_pid / HEAD_NAME).read_text(encoding="utf-8"))["revision_id"] == after_retry[
        "revision_id"
    ]
    assert _revision_count(after_rev_ws, after_pid) == 1


def test_malformed_boundaries_do_not_mutate_or_raise(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    before = _writing_tree(workspace)
    output = tmp_path / ".work" / "malformed.md"

    live = copy.deepcopy(context)
    live["evidence"][0]["score"] = 10**400
    huge = export_writing_outline(workspace, live)
    assert huge["ok"] is False
    assert huge["status"] == LIGHT_CONTEXT_INVALID
    assert _writing_tree(workspace) == before
    assert not output.exists()

    for score in (True, float("nan"), float("inf")):
        tainted = copy.deepcopy(context)
        tainted["evidence"][0]["score"] = score
        closed = export_writing_outline(workspace, tainted)
        assert closed["ok"] is False
        assert closed["status"] == LIGHT_CONTEXT_INVALID
        assert _writing_tree(workspace) == before

    listed = copy.deepcopy(wrapper)
    listed["schema"] = ["video-paper-wiki.light-writing-outline-context.v1"]
    listed_result = import_writing_outline(workspace, listed, _outline_document(context))
    assert listed_result["status"] == LIGHT_WRITING_PROJECT_INVALID
    assert _writing_tree(workspace) == before

    missing = copy.deepcopy(_outline_document(context))
    del missing["sections"][0]["goal"]
    missing_result = import_writing_outline(workspace, wrapper, missing)
    assert missing_result["status"] == LIGHT_WRITING_PROJECT_INVALID
    assert _writing_tree(workspace) == before

    surrogate = _outline_document(context)
    surrogate["title"] = "坏" + chr(0xD800)
    surrogate_result = import_writing_outline(workspace, wrapper, surrogate)
    assert surrogate_result["ok"] is False
    assert _writing_tree(workspace) == before

    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    enum_doc = _section_document(project_id, "s1", _chunk(context), "方法。")
    enum_doc["status"] = ["provisional"]
    enum_result = import_writing_section(workspace, exported, enum_doc)
    assert enum_result["status"] == LIGHT_WRITING_PROJECT_INVALID
    assert _writing_tree(workspace) == before

    object_doc = _section_document(project_id, "s1", _chunk(context), "方法。")
    object_doc["citations"] = {"chunk": _chunk(context)}
    object_result = import_writing_section(workspace, exported, object_doc)
    assert object_result["status"] == LIGHT_WRITING_PROJECT_INVALID
    assert _writing_tree(workspace) == before

    kind_ws = _workspace(tmp_path / "kind")
    _context_k, _wrapper_k, imported_k = _create_project(kind_ws)
    kind_dir = _revision_dir(kind_ws, imported_k["project_id"], imported_k["revision_id"])
    _persist_mutated(kind_dir / "document.json", lambda payload: payload.__setitem__("kind", []))
    history = writing_project_history(kind_ws, project_id=imported_k["project_id"])
    assert history["ok"] is False
    assert history["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    blockers = writing_backup_blockers(kind_ws)
    assert blockers
    assert all(set(item) == {"path", "status", "message"} for item in blockers)
    assert writing._head_path(kind_ws, imported_k["project_id"]).exists()

    missing_ws = _workspace(tmp_path / "missing-stored")
    _context_m, _wrapper_m, imported_m = _create_project(missing_ws)
    missing_dir = _revision_dir(missing_ws, imported_m["project_id"], imported_m["revision_id"])
    _persist_mutated(missing_dir / "document.json", lambda payload: payload["sections"][0].pop("markdown"))
    assert writing_project_history(missing_ws, project_id=imported_m["project_id"])["ok"] is False
    assert writing_backup_blockers(missing_ws)

    score_ws = _workspace(tmp_path / "stored-score")
    _context_s, _wrapper_s, imported_s = _create_project(score_ws)
    score_dir = _revision_dir(score_ws, imported_s["project_id"], imported_s["revision_id"])
    _persist_mutated(
        score_dir / "context.json",
        lambda payload: payload["evidence"][0].__setitem__("score", 10**400),
    )
    score_history = writing_project_history(score_ws, project_id=imported_s["project_id"])
    assert score_history["ok"] is False
    assert score_history["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert writing_backup_blockers(score_ws)

    boom_ws = _workspace(tmp_path / "fs")
    boom_context = _writing_context(boom_ws)
    boom_wrapper = export_writing_outline(boom_ws, boom_context)
    boom_document = _outline_document(boom_context)
    before_boom = _writing_tree(boom_ws)
    real_revision = writing._publish_revision

    def boom(*_args: object, **_kwargs: object) -> bool:
        raise OSError("disk full")

    writing._publish_revision = boom
    try:
        failed_fs = import_writing_outline(boom_ws, boom_wrapper, boom_document)
    finally:
        writing._publish_revision = real_revision
    assert failed_fs["ok"] is False
    assert failed_fs["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    assert not any(path.endswith("/HEAD.json") for path in _writing_tree(boom_ws))
    assert all(
        path.endswith(writing.INTENT_NAME) or path.endswith(writing.OWNERSHIP_NAME) or "/staging/" in path
        for path in set(_writing_tree(boom_ws)) - set(before_boom)
    ) or _writing_tree(boom_ws).keys() >= before_boom.keys()


def test_selected_unwritten_successor_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context, _wrapper, imported = _create_project(workspace)
    project_id = imported["project_id"]
    parent = imported["revision_id"]
    parentdir = _revision_dir(workspace, project_id, parent)
    parentdoc = json.loads((parentdir / "document.json").read_text(encoding="utf-8"))
    childdoc = copy.deepcopy(parentdoc)
    childdoc.update(kind="section", target_section_id="s1", parent_revision_id=parent)
    rid = writing._revision_identity(
        project_id=project_id,
        parent_revision_id=parent,
        context_sha256=sha256_canonical(context),
        document=childdoc,
    )
    files = writing._revision_files(
        workspace=workspace,
        project_id=project_id,
        revision_id=rid,
        parent_revision_id=parent,
        context=context,
        document=childdoc,
    )
    childdir = writing._revision_dir(workspace, project_id, rid)
    childdir.mkdir()
    for name, data in files.items():
        (childdir / name).write_bytes(data)
    writing._head_path(workspace, project_id).write_bytes(
        persisted_bytes({"schema": writing.HEAD_SCHEMA, "project_id": project_id, "revision_id": rid})
    )
    history = writing_project_history(workspace, project_id=project_id)
    assert history["ok"] is False
    assert history["status"] == LIGHT_WRITING_PROJECT_CONFLICT
    exported = export_writing_section(workspace, project_id=project_id, section_id="s1")
    assert exported["ok"] is False
    assert writing_backup_blockers(workspace)
    retry = import_writing_section(
        workspace,
        {
            "ok": True,
            "status": "OK",
            "message": writing.SECTION_MESSAGE,
            "schema": SECTION_CONTEXT_SCHEMA,
            "project_id": project_id,
            "parent_revision_id": parent,
            "section_id": "s1",
            "context": context,
            "context_sha256": sha256_canonical(context),
            "outline": parentdoc["outline"],
            "previous_section": parentdoc["sections"][0],
            "instructions": "",
            "prompt": writing.SECTION_PROMPT,
            "wrapper_sha256": "0" * 64,
        },
        {
            "citations": [],
            "markdown": "",
            "project_id": project_id,
            "schema": "video-paper-wiki.light-writing-section.v1",
            "section_id": "s1",
            "status": "unwritten",
        },
    )
    assert retry["ok"] is False

    legal = _workspace(tmp_path / "legal")
    legal_context, _legal_wrapper, legal_imported = _create_project(legal)
    legal_pid = legal_imported["project_id"]
    unknown = {
        "citations": [],
        "markdown": "证据不足",
        "project_id": legal_pid,
        "schema": "video-paper-wiki.light-writing-section.v1",
        "section_id": "s1",
        "status": "unknown",
    }
    parent_export = export_writing_section(legal, project_id=legal_pid, section_id="s1")
    first_unknown = import_writing_section(legal, parent_export, unknown)
    assert first_unknown["ok"] is True
    reused_unknown = import_writing_section(legal, parent_export, unknown)
    assert reused_unknown["ok"] is True
    assert reused_unknown["reused"] is True
    assert reused_unknown["revision_id"] == first_unknown["revision_id"]
    same_unknown = import_writing_section(
        legal,
        export_writing_section(legal, project_id=legal_pid, section_id="s1"),
        unknown,
    )
    assert same_unknown["ok"] is True
    original_export = export_writing_section(legal, project_id=legal_pid, section_id="s2")

    provisional = _section_document(legal_pid, "s2", _chunk(legal_context, 1), "实验。")
    first_prov = import_writing_section(legal, original_export, provisional)
    assert first_prov["ok"] is True
    reused_prov = import_writing_section(legal, original_export, provisional)
    assert reused_prov["ok"] is True
    assert reused_prov["reused"] is True
    assert reused_prov["revision_id"] == first_prov["revision_id"]
    again = export_writing_section(legal, project_id=legal_pid, section_id="s2")
    identical = import_writing_section(legal, again, provisional)
    assert identical["ok"] is True
    assert identical["revision_id"] != first_prov["revision_id"]
