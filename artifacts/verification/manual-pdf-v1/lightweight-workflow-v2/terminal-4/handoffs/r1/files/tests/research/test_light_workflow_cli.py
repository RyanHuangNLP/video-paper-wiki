"""CLI protocol and integrated workflow regression.

Protocol tests inject interface stubs and check argparse mapping, help,
mixed-flag rejection, and legacy dispatch. Integrated cases use real
T1/T2/T3 backends when those modules are present; they do not mock success.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from tests.research.conftest import stdout_json
from tests.research.test_light_cli import _assert_markdown_links_resolve, _pdf_with_page_texts
from video_paper_wiki_research.cli import build_parser, main as research_main


def _install_light_module(monkeypatch: pytest.MonkeyPatch, name: str, **attrs):
    full = f"video_paper_wiki_research.{name}"
    module = types.ModuleType(full)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, full, module)
    return module


def _workspace(checkout: Path, name: str = "light-workflow-cli") -> Path:
    path = checkout / ".work" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _live_backends():
    workspace = pytest.importorskip("video_paper_wiki_research.light_workspace")
    context = pytest.importorskip("video_paper_wiki_research.light_context")
    workflow = pytest.importorskip("video_paper_wiki_research.light_workflow")
    missing = [
        name
        for name, module, attr in (
            ("inspect_workspace", workspace, "inspect_workspace"),
            ("export_context", context, "export_context"),
            ("import_document", context, "import_document"),
            ("prepare_workflow", workflow, "prepare_workflow"),
            ("workflow_status", workflow, "workflow_status"),
            ("complete_workflow", workflow, "complete_workflow"),
        )
        if not callable(getattr(module, attr, None))
    ]
    if missing:
        pytest.skip("live workflow backends are incomplete: " + ", ".join(missing))
    return workspace, context, workflow


def test_protocol_help_lists_workspace_and_workflow_commands() -> None:
    parser = build_parser()
    text = parser.format_help()
    assert "workspace" in text
    assert "workflow" in text
    sub = {action.dest: action for action in parser._actions if getattr(action, "dest", None) in {"command"}}
    assert "command" in sub
    choices = set(sub["command"].choices or [])
    assert {"pdf", "index", "qa", "writing", "workspace", "workflow"} <= choices
    workspace_help = sub["command"].choices["workspace"].format_help()
    workflow_help = sub["command"].choices["workflow"].format_help()
    assert "inspect" in workspace_help
    assert "prepare" in workflow_help
    assert "status" in workflow_help
    assert "complete" in workflow_help
    prepare_help = sub["command"].choices["workflow"]._subparsers._group_actions[0].choices["prepare"].format_help()
    assert "--paper-id" in prepare_help
    assert "--pdf" in prepare_help
    qa_help = sub["command"].choices["qa"]._subparsers._group_actions[0].choices["export"].format_help()
    assert "--paper-id" in qa_help


def test_protocol_missing_and_invalid_flags_are_usage(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    assert research_main(["workspace"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["workflow", "prepare", "--workspace", str(workspace), "--kind", "qa"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            ["workflow", "prepare", "--workspace", str(workspace), "--kind", "notes", "--query", "q"]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["workflow", "complete", "--workspace", str(workspace), "--session-id", "ab"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"


def test_protocol_workspace_inspect_maps_path_and_does_not_create(checkout: Path, monkeypatch, capsys) -> None:
    captured: dict[str, Path] = {}

    def inspect_workspace(workspace_root: Path) -> dict:
        captured["root"] = workspace_root
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-workspace.v1",
            "state": "empty",
            "message": "empty workspace",
        }

    _install_light_module(monkeypatch, "light_workspace", inspect_workspace=inspect_workspace)
    missing = checkout / ".work" / "absent-inspect"
    assert not missing.exists()
    assert research_main(["workspace", "inspect", "--workspace", str(missing)]) == 0
    payload = stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["state"] == "empty"
    assert captured["root"] == missing.resolve()
    assert not missing.exists()


def test_protocol_workflow_prepare_status_complete_map_arguments(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def prepare_workflow(workspace_root, *, kind, query, requirements="", paper_ids=None, pdf_paths=None):
        seen["prepare"] = {
            "workspace": workspace_root,
            "kind": kind,
            "query": query,
            "requirements": requirements,
            "paper_ids": paper_ids,
            "pdf_paths": pdf_paths,
        }
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-workflow.v1",
            "session_id": "a" * 64,
            "state": "awaiting_model",
            "reused": False,
            "message": "prepared",
        }

    def workflow_status(workspace_root, *, session_id=None):
        seen["status"] = {"workspace": workspace_root, "session_id": session_id}
        return {"ok": True, "status": "OK", "state": "awaiting_model", "session_id": session_id, "message": "open"}

    def complete_workflow(workspace_root, session_id, document, *, output):
        seen["complete"] = {
            "workspace": workspace_root,
            "session_id": session_id,
            "document": document,
            "output": output,
        }
        return {
            "ok": True,
            "status": "OK",
            "state": "complete",
            "session_id": session_id,
            "path": str(output),
            "reused": False,
            "message": "completed",
        }

    _install_light_module(
        monkeypatch,
        "light_workflow",
        prepare_workflow=prepare_workflow,
        workflow_status=workflow_status,
        complete_workflow=complete_workflow,
    )
    workspace = checkout / ".work" / "prepare-missing"
    pdf_a = checkout / "one.pdf"
    pdf_b = checkout / "two.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    paper = "sha256:" + ("ab" * 32)
    other = "sha256:" + ("cd" * 32)
    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "writing",
                "--query",
                "compare methods",
                "--requirements",
                "one paragraph",
                "--paper-id",
                paper,
                "--paper-id",
                other,
                "--pdf",
                str(pdf_a),
                "--pdf",
                str(pdf_b),
            ]
        )
        == 0
    )
    prepared = stdout_json(capsys)
    assert prepared["schema"] == "video-paper-wiki.light-workflow.v1"
    assert prepared["session_id"] == "a" * 64
    assert not workspace.exists()
    assert seen["prepare"]["workspace"] == workspace.resolve()
    assert seen["prepare"]["kind"] == "writing"
    assert seen["prepare"]["query"] == "compare methods"
    assert seen["prepare"]["requirements"] == "one paragraph"
    assert seen["prepare"]["paper_ids"] == [paper, other]
    assert seen["prepare"]["pdf_paths"] == [pdf_a, pdf_b]

    workspace.mkdir(parents=True)
    assert research_main(["workflow", "status", "--workspace", str(workspace), "--session-id", "a" * 64]) == 0
    assert stdout_json(capsys)["state"] == "awaiting_model"
    assert seen["status"]["session_id"] == "a" * 64

    document = {"text": "answer", "citations": []}
    document_path = workspace / "model-document.json"
    document_path.write_text(json.dumps(document), encoding="utf-8")
    output = checkout / ".work" / "out" / "answer.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                "a" * 64,
                "--document",
                str(document_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    completed = stdout_json(capsys)
    assert completed["state"] == "complete"
    assert seen["complete"]["document"] == document
    assert seen["complete"]["output"] == output
    assert not output.exists()


def test_protocol_complete_rejects_missing_document_file_without_output(checkout: Path, monkeypatch, capsys) -> None:
    def complete_workflow(*_args, **_kwargs):
        raise AssertionError("complete_workflow must not run for a missing document file")

    _install_light_module(monkeypatch, "light_workflow", complete_workflow=complete_workflow)
    workspace = _workspace(checkout)
    missing = workspace / "absent-document.json"
    output = workspace / "should-not-exist.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                "c" * 64,
                "--document",
                str(missing),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    assert not output.exists()


def test_protocol_complete_rejects_non_object_document_without_output(checkout: Path, monkeypatch, capsys) -> None:
    def complete_workflow(*_args, **_kwargs):
        raise AssertionError("complete_workflow must not run for invalid document JSON")

    _install_light_module(monkeypatch, "light_workflow", complete_workflow=complete_workflow)
    workspace = _workspace(checkout)
    document = workspace / "not-object.json"
    document.write_text("[]", encoding="utf-8")
    output = workspace / "should-not-exist.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                "b" * 64,
                "--document",
                str(document),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    assert not output.exists()


def test_protocol_export_and_import_route_to_context_api(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def export_context(workspace_root, *, kind, query, requirements="", paper_ids=None):
        seen["export"] = {
            "workspace": workspace_root,
            "kind": kind,
            "query": query,
            "requirements": requirements,
            "paper_ids": paper_ids,
        }
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-context.v1",
            "kind": kind,
            "query": query,
            "message": "exported",
        }

    def import_document(workspace_root, context, document, *, output, overwrite=True):
        seen["import"] = {
            "workspace": workspace_root,
            "context": context,
            "document": document,
            "output": output,
            "overwrite": overwrite,
        }
        return {
            "ok": True,
            "status": "OK",
            "markdown": "# ok\n",
            "path": str(output),
            "output_sha256": "0" * 64,
            "message": "imported",
        }

    _install_light_module(monkeypatch, "light_context", export_context=export_context, import_document=import_document)
    workspace = _workspace(checkout)
    paper = "sha256:" + ("11" * 32)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "what method",
                "--workspace",
                str(workspace),
                "--paper-id",
                paper,
                "--paper-id",
                paper,
            ]
        )
        == 0
    )
    exported = stdout_json(capsys)
    assert exported["schema"] == "video-paper-wiki.light-context.v1"
    assert Path(exported["workspace_root"]) == workspace.resolve()
    assert seen["export"]["kind"] == "qa"
    assert seen["export"]["query"] == "what method"
    assert seen["export"]["paper_ids"] == [paper, paper]

    context_path = workspace / "ctx.json"
    answer_path = workspace / "ans.json"
    output = checkout / ".work" / "notes" / "qa.md"
    context_path.write_text(json.dumps(exported), encoding="utf-8")
    answer_path.write_text(json.dumps({"text": "x", "citations": []}), encoding="utf-8")
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--output",
                str(output),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )
    imported = stdout_json(capsys)
    assert imported["ok"] is True
    assert imported["path"] == str(output)
    assert seen["import"]["overwrite"] is True
    assert seen["import"]["output"] == output
    assert not output.exists()


def test_protocol_closed_backend_failure_is_nonzero_and_creates_no_output(checkout: Path, monkeypatch, capsys) -> None:
    def import_document(workspace_root, context, document, *, output, overwrite=True):
        del workspace_root, context, document, overwrite
        return {"ok": False, "status": "LIGHT_CONTEXT_INVALID", "message": "forged evidence", "path": None}

    _install_light_module(monkeypatch, "light_context", import_document=import_document)
    workspace = _workspace(checkout)
    context = {
        "ok": True,
        "schema": "video-paper-wiki.light-context.v1",
        "kind": "qa",
        "workspace_root": str(workspace),
    }
    context_path = workspace / "ctx.json"
    answer_path = workspace / "ans.json"
    output = workspace / "forged.md"
    context_path.write_text(json.dumps(context), encoding="utf-8")
    answer_path.write_text(json.dumps({"text": "no", "citations": []}), encoding="utf-8")
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["status"] == "LIGHT_CONTEXT_INVALID"
    assert not output.exists()


def test_protocol_writing_export_maps_topic_and_repeatable_paper_ids(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def export_context(workspace_root, *, kind, query, requirements="", paper_ids=None):
        seen["export"] = {
            "workspace": workspace_root,
            "kind": kind,
            "query": query,
            "requirements": requirements,
            "paper_ids": paper_ids,
        }
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-context.v1",
            "kind": kind,
            "message": "exported",
        }

    _install_light_module(monkeypatch, "light_context", export_context=export_context)
    workspace = _workspace(checkout)
    first = "sha256:" + ("22" * 32)
    second = "sha256:" + ("33" * 32)
    assert (
        research_main(
            [
                "writing",
                "export",
                "--topic",
                "related work",
                "--requirements",
                "two sentences",
                "--workspace",
                str(workspace),
                "--paper-id",
                first,
                "--paper-id",
                second,
            ]
        )
        == 0
    )
    payload = stdout_json(capsys)
    assert payload["kind"] == "writing"
    assert seen["export"]["kind"] == "writing"
    assert seen["export"]["query"] == "related work"
    assert seen["export"]["requirements"] == "two sentences"
    assert seen["export"]["paper_ids"] == [first, second]


def test_protocol_inspect_rejects_path_outside_work_without_backend(checkout: Path, monkeypatch, capsys) -> None:
    def inspect_workspace(_workspace_root: Path) -> dict:
        raise AssertionError("inspect_workspace must not run for unsafe roots")

    _install_light_module(monkeypatch, "light_workspace", inspect_workspace=inspect_workspace)
    outside = checkout / "not-work"
    outside.mkdir()
    assert research_main(["workspace", "inspect", "--workspace", str(outside)]) == 2
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORKSPACE_INVALID"


def test_protocol_legacy_vault_dispatch_still_used_without_workspace(checkout: Path, monkeypatch, capsys) -> None:
    def fake_qa(**kwargs):
        assert kwargs["vault_root"] == "vault"
        return {"ok": True, "status": "OK", "kind": "qa-context", "question": kwargs["question"]}

    monkeypatch.setattr("video_paper_wiki_research.qa.export_from_question", fake_qa)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "legacy",
                "--vault-root",
                "vault",
                "--upstream-root",
                "upstream",
                "--config",
                "config.json",
            ]
        )
        == 0
    )
    assert stdout_json(capsys)["kind"] == "qa-context"


def test_live_workspace_prepare_complete_status_and_repeat_add(checkout: Path, capsys) -> None:
    _live_backends()
    workspace = _workspace(checkout, "live-flow")
    notes = workspace / "notes.md"
    notes.write_text("keep these notes\n", encoding="utf-8")
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Hybrid linear attention residual video generation."]))
    assert research_main(["workspace", "inspect", "--workspace", str(workspace)]) == 0
    inspected = stdout_json(capsys)
    assert inspected["ok"] is True
    assert inspected["schema"] == "video-paper-wiki.light-workspace.v1"

    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "qa",
                "--query",
                "hybrid linear attention",
                "--pdf",
                str(pdf),
            ]
        )
        == 0
    )
    prepared = stdout_json(capsys)
    assert prepared["ok"] is True
    assert prepared["status"] == "OK"
    assert prepared["state"] == "awaiting_model"
    session_id = prepared["session_id"]
    context = prepared["context"]
    assert context["evidence"]
    chunk_id = context["evidence"][0]["chunk_id"]
    assert notes.read_text(encoding="utf-8") == "keep these notes\n"

    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "qa",
                "--query",
                "hybrid linear attention",
                "--pdf",
                str(pdf),
            ]
        )
        == 0
    )
    repeated = stdout_json(capsys)
    assert repeated["ok"] is True
    assert repeated["session_id"] == session_id
    assert notes.read_text(encoding="utf-8") == "keep these notes\n"

    document = {"text": f"Hybrid linear attention. [@{chunk_id}]", "citations": [{"chunk_id": chunk_id}]}
    document_path = workspace / "qa-document.json"
    document_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    output = checkout / ".work" / "path with spaces" / "qa answer.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                session_id,
                "--document",
                str(document_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    completed = stdout_json(capsys)
    assert completed["ok"] is True
    assert completed["state"] == "complete"
    written = Path(completed["path"])
    assert written == output.resolve()
    assert written.is_file()
    _assert_markdown_links_resolve(written, workspace)
    first_sha = completed["output_sha256"]

    assert research_main(["workflow", "status", "--workspace", str(workspace), "--session-id", session_id]) == 0
    status = stdout_json(capsys)
    assert status["ok"] is True
    assert status["state"] == "complete"

    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                session_id,
                "--document",
                str(document_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    reused = stdout_json(capsys)
    assert reused["ok"] is True
    assert reused.get("reused") is True
    assert reused["output_sha256"] == first_sha
    assert written.read_text(encoding="utf-8")


def _live_context():
    try:
        from video_paper_wiki_research import light_context
    except ModuleNotFoundError as exc:
        pytest.fail(f"T2 light_context is not integrated: {exc}")
    if not callable(getattr(light_context, "import_document", None)) or not callable(
        getattr(light_context, "export_context", None)
    ):
        pytest.fail("light_context export/import APIs are not integrated")
    return light_context


def test_live_import_gap_cases_are_closed_and_control_succeeds(checkout: Path, capsys) -> None:
    _live_context()
    workspace = _workspace(checkout, "import-gaps")
    pdf = checkout / "gap.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    added = stdout_json(capsys)
    assert added["ok"] is True
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["qa", "export", "--question", "quasar method", "--workspace", str(workspace)]) == 0
    context = stdout_json(capsys)
    assert context["ok"] is True
    chunk = context["evidence"][0]["chunk_id"]
    context_path = workspace / "context.json"
    answer_path = workspace / "answer.json"
    context_path.write_text(json.dumps(context), encoding="utf-8")
    answer_path.write_text(
        json.dumps({"text": f"Synthetic method [@{chunk}].", "citations": [{"chunk_id": chunk}]}),
        encoding="utf-8",
    )

    control = workspace / "valid_control.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(control),
            ]
        )
        == 0
    )
    imported = stdout_json(capsys)
    assert imported["ok"] is True
    assert control.is_file()
    control_bytes = control.read_bytes()

    tampered = json.loads(context_path.read_text(encoding="utf-8"))
    row = tampered["evidence"][0]
    row["text"] = "Synthetic fabricated evidence absent from source."
    row["text_sha256"] = __import__("hashlib").sha256(row["text"].encode("utf-8")).hexdigest()
    tampered_path = workspace / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    forged = workspace / "tampered_context_text_and_hash.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(tampered_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(forged),
            ]
        )
        == 2
    )
    forged_payload = stdout_json(capsys)
    assert forged_payload["ok"] is False
    assert forged_payload.get("status") in {"LIGHT_CONTEXT_INVALID", "INDEX_STALE"}
    assert not forged.exists()

    source = Path(added["markdown_path"])
    source.write_text(source.read_text(encoding="utf-8").replace("quasar method evidence", "nebula changed evidence"), encoding="utf-8")
    stale = workspace / "source_changed_without_reindex.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(stale),
            ]
        )
        == 2
    )
    stale_payload = stdout_json(capsys)
    assert stale_payload["ok"] is False
    assert stale_payload.get("status") == "INDEX_STALE"
    assert not stale.exists()

    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    old_after = workspace / "old_context_after_reindex.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(old_after),
            ]
        )
        == 2
    )
    old_payload = stdout_json(capsys)
    assert old_payload["ok"] is False
    assert old_payload.get("status") in {"INDEX_STALE", "LIGHT_CONTEXT_INVALID"}
    assert not old_after.exists()
    assert control.read_bytes() == control_bytes


def test_live_selected_paper_no_results_and_conflict_preserve_output(checkout: Path, capsys) -> None:
    _live_backends()
    workspace = _workspace(checkout, "selection")
    first = checkout / "one.pdf"
    second = checkout / "two.pdf"
    first.write_bytes(_pdf_with_page_texts(["Alpha residual attention keeps generation stable."]))
    second.write_bytes(_pdf_with_page_texts(["Beta diffusion sampler uses a different schedule."]))
    assert research_main(["pdf", "add", "--pdf", str(first), "--workspace", str(workspace), "--title", "Alpha"]) == 0
    alpha = stdout_json(capsys)
    assert research_main(["pdf", "add", "--pdf", str(second), "--workspace", str(workspace), "--title", "Beta"]) == 0
    beta = stdout_json(capsys)
    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "qa",
                "--query",
                "diffusion sampler",
                "--paper-id",
                alpha["paper_id"],
            ]
        )
        == 2
    )
    empty = stdout_json(capsys)
    assert empty["ok"] is False
    assert empty["status"] in {"NO_RESULTS", "INSUFFICIENT_EVIDENCE"}
    assert empty.get("session_id") in {None, ""}

    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "writing",
                "--query",
                "diffusion sampler",
                "--requirements",
                "one sentence",
                "--paper-id",
                beta["paper_id"],
            ]
        )
        == 0
    )
    prepared = stdout_json(capsys)
    assert prepared["ok"] is True
    context = prepared["context"]
    assert all(item["paper_id"] == beta["paper_id"] for item in context["evidence"])
    chunk_id = context["evidence"][0]["chunk_id"]
    document = {
        "markdown": f"Beta sampler. [@{chunk_id}]",
        "citations": [{"chunk_id": chunk_id}],
    }
    document_path = workspace / "draft.json"
    document_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    output = checkout / ".work" / "out (draft)" / "writing draft.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                prepared["session_id"],
                "--document",
                str(document_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    first_complete = stdout_json(capsys)
    original = Path(first_complete["path"]).read_bytes()
    other_doc = workspace / "other.json"
    other_doc.write_text(json.dumps({"markdown": "different", "citations": [{"chunk_id": chunk_id}]}), encoding="utf-8")
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                prepared["session_id"],
                "--document",
                str(other_doc),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    conflict = stdout_json(capsys)
    assert conflict["ok"] is False
    assert conflict["status"] == "LIGHT_SESSION_CONFLICT"
    assert Path(first_complete["path"]).read_bytes() == original


def test_live_bad_citation_and_edited_output_are_refused(checkout: Path, capsys) -> None:
    _live_backends()
    workspace = _workspace(checkout, "bad-cite")
    pdf = checkout / "cite.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Citation slice must match the current source bytes."]))
    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "qa",
                "--query",
                "citation slice",
                "--pdf",
                str(pdf),
            ]
        )
        == 0
    )
    prepared = stdout_json(capsys)
    session_id = prepared["session_id"]
    chunk_id = prepared["context"]["evidence"][0]["chunk_id"]
    bad = workspace / "bad.json"
    bad.write_text(
        json.dumps({"text": "Invented page. [@missing-chunk]", "citations": [{"chunk_id": "missing-chunk"}]}),
        encoding="utf-8",
    )
    output = checkout / ".work" / "cite-out" / "bad.md"
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                session_id,
                "--document",
                str(bad),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    refused = stdout_json(capsys)
    assert refused["ok"] is False
    assert refused.get("status") in {"INVALID_CITATION", "CITATION_MISMATCH", "LIGHT_CONTEXT_INVALID", "LIGHT_SESSION_INVALID"}
    assert not output.exists()

    good = workspace / "good.json"
    good.write_text(
        json.dumps({"text": f"Slice matches. [@{chunk_id}]", "citations": [{"chunk_id": chunk_id}]}),
        encoding="utf-8",
    )
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                session_id,
                "--document",
                str(good),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    completed = stdout_json(capsys)
    original = Path(completed["path"]).read_bytes()
    Path(completed["path"]).write_text(Path(completed["path"]).read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
    assert (
        research_main(
            [
                "workflow",
                "complete",
                "--workspace",
                str(workspace),
                "--session-id",
                session_id,
                "--document",
                str(good),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    edited = stdout_json(capsys)
    assert edited["ok"] is False
    assert edited.get("status") in {"LIGHT_SESSION_CONFLICT", "LIGHT_OUTPUT_CONFLICT", "LIGHT_SESSION_INVALID"}
    assert Path(completed["path"]).read_bytes() != original
    assert "user edit" in Path(completed["path"]).read_text(encoding="utf-8")


def test_live_source_edit_makes_export_and_status_stale(checkout: Path, capsys) -> None:
    _live_backends()
    workspace = _workspace(checkout, "stale-source")
    pdf = checkout / "stale.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Original lexical token remains until the source is edited."]))
    assert (
        research_main(
            [
                "workflow",
                "prepare",
                "--workspace",
                str(workspace),
                "--kind",
                "qa",
                "--query",
                "lexical token",
                "--pdf",
                str(pdf),
            ]
        )
        == 0
    )
    prepared = stdout_json(capsys)
    markdown = Path(prepared["context"]["evidence"][0]["markdown_path"])
    markdown.write_text(markdown.read_text(encoding="utf-8").replace("lexical token", "replaced token"), encoding="utf-8")
    assert research_main(["qa", "export", "--question", "lexical token", "--workspace", str(workspace)]) == 2
    exported = stdout_json(capsys)
    assert exported["ok"] is False
    assert exported.get("status") == "INDEX_STALE"
    assert research_main(["workflow", "status", "--workspace", str(workspace), "--session-id", prepared["session_id"]]) == 0
    status = stdout_json(capsys)
    assert status["ok"] is True
    assert status.get("state") in {"stale", "needs_attention"}


def test_live_inspect_missing_workspace_and_repeat_add_preserve_notes(checkout: Path, capsys) -> None:
    try:
        from video_paper_wiki_research import light_pdf, light_workspace
    except ModuleNotFoundError as exc:
        pytest.fail(f"T1 modules are not integrated: {exc}")
    if not callable(getattr(light_workspace, "inspect_workspace", None)) or not callable(
        getattr(light_pdf, "extract_pdf", None)
    ):
        pytest.fail("T1 inspect/extract APIs are not integrated")
    missing = checkout / ".work" / "absent-live-inspect"
    assert not missing.exists()
    assert research_main(["workspace", "inspect", "--workspace", str(missing)]) == 0
    inspected = stdout_json(capsys)
    assert inspected["ok"] is True
    assert inspected.get("state") == "empty"
    assert not missing.exists()

    workspace = _workspace(checkout, "repeat-add")
    notes = workspace / "notes.md"
    notes.write_text("keep user notes\n", encoding="utf-8")
    pdf = checkout / "repeat.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Repeat add must keep user notes."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    first = stdout_json(capsys)
    assert first["ok"] is True
    assert first.get("disposition") in {"created", "reused", "recovered"}
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    second = stdout_json(capsys)
    assert second["ok"] is True
    assert second.get("disposition") == "reused"
    assert notes.read_text(encoding="utf-8") == "keep user notes\n"
    source = Path(first["markdown_path"])
    original_source = source.read_bytes()
    source.write_bytes(original_source + b"\xff\xfe")
    assert research_main(["workspace", "inspect", "--workspace", str(workspace)]) == 0
    diagnosed = stdout_json(capsys)
    assert diagnosed["ok"] is True
    assert diagnosed.get("state") == "needs_attention"
    assert source.read_bytes() == original_source + b"\xff\xfe"
    assert notes.read_text(encoding="utf-8") == "keep user notes\n"


def test_live_malformed_context_and_bad_selection_are_closed_json(checkout: Path, capsys) -> None:
    _live_context()
    workspace = _workspace(checkout, "malformed-context")
    pdf = checkout / "shape.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Closed JSON must describe a malformed context."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "malformed context",
                "--workspace",
                str(workspace),
                "--paper-id",
                "not-a-paper-id",
            ]
        )
        == 2
    )
    bad_id = stdout_json(capsys)
    assert bad_id["ok"] is False
    assert bad_id.get("status") == "LIGHT_SELECTION_INVALID"

    assert research_main(["qa", "export", "--question", "malformed context", "--workspace", str(workspace)]) == 0
    context = stdout_json(capsys)
    assert context["ok"] is True
    context["evidence"] = "not-a-list"
    context_path = workspace / "bad-shape.json"
    answer_path = workspace / "answer.json"
    output = workspace / "should-not-exist.md"
    context_path.write_text(json.dumps(context), encoding="utf-8")
    answer_path.write_text(json.dumps({"text": "no", "citations": []}), encoding="utf-8")
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    closed = stdout_json(capsys)
    assert closed["ok"] is False
    assert closed.get("status") == "LIGHT_CONTEXT_INVALID"
    assert not output.exists()


def test_live_import_refusal_preserves_existing_output(checkout: Path, capsys) -> None:
    _live_context()
    workspace = _workspace(checkout, "preserve-output")
    pdf = checkout / "keep.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Existing user markdown must survive a refused import."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["qa", "export", "--question", "existing markdown", "--workspace", str(workspace)]) == 0
    context = stdout_json(capsys)
    chunk = context["evidence"][0]["chunk_id"]
    context_path = workspace / "context.json"
    answer_path = workspace / "answer.json"
    output = checkout / ".work" / "kept (notes)" / "existing answer.md"
    output.parent.mkdir(parents=True)
    output.write_text("user kept this file\n", encoding="utf-8")
    original = output.read_bytes()
    context_path.write_text(json.dumps(context), encoding="utf-8")
    answer_path.write_text(
        json.dumps({"text": f"ok [@{chunk}]", "citations": [{"chunk_id": chunk}]}),
        encoding="utf-8",
    )
    tampered = json.loads(context_path.read_text(encoding="utf-8"))
    row = tampered["evidence"][0]
    row["text"] = "forged slice that is not in the source"
    row["text_sha256"] = __import__("hashlib").sha256(row["text"].encode("utf-8")).hexdigest()
    tampered_path = workspace / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(tampered_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    refused = stdout_json(capsys)
    assert refused["ok"] is False
    assert refused.get("status") in {"LIGHT_CONTEXT_INVALID", "INDEX_STALE"}
    assert output.read_bytes() == original


def test_live_invalid_utf8_source_is_closed_json(checkout: Path, capsys) -> None:
    _live_context()
    workspace = _workspace(checkout, "utf8-source")
    pdf = checkout / "utf8.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Source bytes must decode as UTF-8."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    added = stdout_json(capsys)
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["qa", "export", "--question", "decode source", "--workspace", str(workspace)]) == 0
    context = stdout_json(capsys)
    assert context["ok"] is True
    context_path = workspace / "valid-before-utf8.json"
    answer_path = workspace / "utf8-answer.json"
    output = workspace / "utf8-out.md"
    context_path.write_text(json.dumps(context), encoding="utf-8")
    answer_path.write_text(json.dumps({"text": "no", "citations": []}), encoding="utf-8")
    source = Path(added["markdown_path"])
    source.write_bytes(source.read_bytes() + b"\xff\xfe")
    assert research_main(["qa", "export", "--question", "decode source", "--workspace", str(workspace)]) == 2
    exported = stdout_json(capsys)
    assert exported["ok"] is False
    assert exported.get("status") in {"SOURCE_INVALID", "INDEX_STALE"}
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context_path),
                "--answer",
                str(answer_path),
                "--workspace",
                str(workspace),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    imported = stdout_json(capsys)
    assert imported["ok"] is False
    assert imported.get("status") in {"SOURCE_INVALID", "INDEX_STALE"}
    assert not output.exists()
