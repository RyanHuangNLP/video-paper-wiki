"""Integrated research CLI routing, secure handoffs, and live owner wiring.

Live T1/T2/T3 backends are required. Missing owner modules fail these tests.
No mocked owner APIs. Synthetic fixtures are not current-model trials.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

from tests.research.conftest import stdout_json
from tests.research.test_light_cli import _pdf_with_page_texts
from video_paper_wiki_research.cli import build_parser, main as research_main
from video_paper_wiki_research.contracts import JSON_MAX_BYTES
from video_paper_wiki_research.light_query import REWRITE_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
READ = ROOT / ".agents" / "skills" / "video-paper-read"

OWNER_APIS = (
    ("light_query", "export_rewritten_context"),
    ("light_knowledge_batch", "plan_knowledge_batches"),
    ("light_knowledge_batch", "export_knowledge_batch"),
    ("light_knowledge_batch", "import_knowledge_batch"),
    ("light_knowledge_batch", "knowledge_batch_status"),
    ("light_knowledge_batch", "export_knowledge_merge_context"),
    ("light_knowledge_batch", "import_knowledge_merge"),
    ("light_knowledge_batch", "finalize_knowledge_batches"),
    ("light_knowledge_refresh", "plan_knowledge_refresh"),
    ("light_knowledge_refresh", "export_knowledge_diff"),
    ("light_knowledge_refresh", "apply_knowledge_refresh"),
    ("light_writing_project", "export_writing_outline"),
    ("light_writing_project", "import_writing_outline"),
    ("light_writing_project", "export_writing_section"),
    ("light_writing_project", "import_writing_section"),
    ("light_writing_project", "writing_project_history"),
    ("light_writing_project", "export_writing_project"),
    ("light_writing_project", "writing_backup_blockers"),
    ("light_backup", "create_backup"),
)


def _require_live_backends() -> None:
    missing: list[str] = []
    for module_name, attr in OWNER_APIS:
        try:
            module = importlib.import_module(f"video_paper_wiki_research.{module_name}")
        except ModuleNotFoundError:
            missing.append(f"{module_name}.{attr}")
            continue
        if not callable(getattr(module, attr, None)):
            missing.append(f"{module_name}.{attr}")
    if missing:
        raise AssertionError("owner modules/APIs are required for integrated research tests: " + ", ".join(missing))


def _workspace(checkout: Path, name: str = "research-cli") -> Path:
    path = checkout / ".work" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _rewrite_payload(query: str, rewritten: str) -> dict[str, str]:
    return {
        "language": "en",
        "original_query": query,
        "rewritten_query": rewritten,
        "schema": REWRITE_SCHEMA,
    }


def test_owner_modules_must_be_present() -> None:
    _require_live_backends()


def test_help_lists_research_commands_and_apply_choices() -> None:
    parser = build_parser()
    text = parser.format_help()
    for name in ("qa", "writing", "knowledge", "backup", "workflow"):
        assert name in text
    command = {action.dest: action for action in parser._actions if getattr(action, "dest", None) == "command"}
    writing = command["command"].choices["writing"]
    writing_help = writing.format_help()
    for item in ("outline-export", "outline-import", "section-export", "section-import", "history", "project-export"):
        assert item in writing_help
    qa_export = command["command"].choices["qa"]._subparsers._group_actions[0].choices["export"].format_help()
    assert "--rewrite" in qa_export
    writing_export = writing._subparsers._group_actions[0].choices["export"].format_help()
    assert "--rewrite" in writing_export
    knowledge = command["command"].choices["knowledge"]
    knowledge_help = knowledge.format_help()
    for item in (
        "batch-plan",
        "batch-export",
        "batch-import",
        "batch-status",
        "merge-export",
        "merge-import",
        "finalize",
        "refresh-plan",
        "diff",
        "apply",
    ):
        assert item in knowledge_help
    apply_help = knowledge._subparsers._group_actions[0].choices["apply"].format_help()
    assert "--accept-section" in apply_help
    assert "--keep-sections" in apply_help
    assert "--accept-concepts" in apply_help
    assert "--keep-concepts" in apply_help
    assert "--diff" in apply_help
    section_export = writing._subparsers._group_actions[0].choices["section-export"].format_help()
    assert "--project-id" in section_export
    assert "--section-id" in section_export
    assert "--instructions" in section_export


def test_missing_flags_and_apply_groups_are_usage(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    assert research_main(["writing", "outline-export", "--workspace", str(workspace)]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["knowledge", "batch-export", "--workspace", str(workspace), "--plan-id", "ab" * 32]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--accept-concepts",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--keep-sections",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--keep-sections",
                "--accept-concepts",
                "--keep-concepts",
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert "accept-concepts" in payload["error"]["message"]
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(workspace / "missing.json"),
                "--accept-section",
                "summary",
                "--accept-section",
                "summary",
                "--keep-concepts",
            ]
        )
        == 2
    )
    duplicated = stdout_json(capsys)
    assert duplicated["error"]["code"] == "USAGE"
    assert "duplicate" in duplicated["error"]["message"]


def test_rewrite_is_rejected_on_vault_route_and_duplicate_paper_ids(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    rewrite = _save(workspace / "rewrite.json", _rewrite_payload("方法是什么", "quasar method"))
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--rewrite",
                str(rewrite),
                "--vault-root",
                str(workspace),
                "--upstream-root",
                str(workspace),
                "--config",
                str(workspace / "cfg.json"),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert "--rewrite" in payload["error"]["message"]
    paper = "sha256:" + ("01" * 32)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--workspace",
                str(workspace),
                "--rewrite",
                str(rewrite),
                "--paper-id",
                paper,
                "--paper-id",
                paper,
            ]
        )
        == 2
    )
    duplicated = stdout_json(capsys)
    assert duplicated["error"]["code"] == "USAGE"
    assert "duplicate" in duplicated["error"]["message"]


def test_secure_handoffs_refuse_before_owner_work(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    document = _save(workspace / "doc.json", {"schema": "video-paper-wiki.light-writing-outline.v1"})
    missing = workspace / "absent.json"
    assert (
        research_main(
            [
                "writing",
                "outline-import",
                "--workspace",
                str(workspace),
                "--context",
                str(missing),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    duplicate = workspace / "dup.json"
    duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    assert (
        research_main(
            [
                "knowledge",
                "batch-import",
                "--workspace",
                str(workspace),
                "--context",
                str(duplicate),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    nan = workspace / "nan.json"
    nan.write_text('{"a": NaN}', encoding="utf-8")
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(nan),
                "--keep-sections",
                "--keep-concepts",
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    linked = workspace / "link.json"
    real = _save(workspace / "real.json", {"ok": True})
    linked.symlink_to(real)
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                "方法是什么",
                "--workspace",
                str(workspace),
                "--rewrite",
                str(linked),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    hard = workspace / "hard.json"
    os.link(real, hard)
    assert (
        research_main(
            [
                "writing",
                "section-import",
                "--workspace",
                str(workspace),
                "--context",
                str(hard),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    huge = workspace / "huge.json"
    huge.write_bytes(b"{" + (b"a" * (JSON_MAX_BYTES + 1)) + b"}")
    assert (
        research_main(
            [
                "knowledge",
                "merge-import",
                "--workspace",
                str(workspace),
                "--context",
                str(huge),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"


def test_live_rewrite_export_and_keep_sections_reach_owner(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = _workspace(checkout, "live-rewrite")
    pdf = checkout / "alpha.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence uniquealpha."]))
    added = research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace), "--title", "Alpha"])
    payload = stdout_json(capsys)
    assert added == 0 and payload["ok"] is True
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    question = "这篇论文的方法是什么"
    rewrite = _save(workspace / "rewrite.json", _rewrite_payload(question, "quasar method"))
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                question,
                "--workspace",
                str(workspace),
                "--rewrite",
                str(rewrite),
            ]
        )
        == 0
    )
    exported = stdout_json(capsys)
    assert exported["ok"] is True
    assert exported["query"] == question
    assert exported["query_plan"]["rewrite"]["rewritten_query"] == "quasar method"
    assert exported["evidence"]
    assert (
        research_main(
            [
                "knowledge",
                "apply",
                "--workspace",
                str(workspace),
                "--diff",
                str(_save(workspace / "not-a-diff.json", {"schema": "not-a-diff"})),
                "--keep-sections",
                "--keep-concepts",
            ]
        )
        == 2
    )
    refused = stdout_json(capsys)
    assert refused["ok"] is False
    assert refused.get("status") or refused.get("error", {}).get("code")
    assert "Traceback" not in refused.get("message", "")


LIGHT_CONTEXT_STUB = {"schema": "video-paper-wiki.light-context.v1"}
HEX64 = "ab" * 32
PAPER_STUB = "sha256:" + ("01" * 32)
WORKSPACE_HANDLERS = (
    "qa-export-rewrite",
    "writing-export-rewrite",
    "qa-import",
    "writing-import",
    "knowledge-batch-plan",
    "knowledge-batch-export",
    "knowledge-batch-import",
    "knowledge-batch-status",
    "knowledge-merge-export",
    "knowledge-merge-import",
    "knowledge-finalize",
    "knowledge-refresh-plan",
    "knowledge-diff",
    "knowledge-apply",
    "writing-outline-export",
    "writing-outline-import",
    "writing-section-export",
    "writing-section-import",
    "writing-history",
    "writing-project-export",
)


def _closed_payload(capsys) -> dict:
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    return json.loads(lines[0])


def _error_code(payload: dict) -> str:
    error = payload.get("error") if type(payload.get("error")) is dict else {}
    return str(payload.get("status") or error.get("code") or "")


def _edge_workspace(workspace: Path, kind: str) -> Path:
    parent = workspace.parent
    alias = parent / "alias"
    if kind in {"symlink", "symlink-dotdot"} and not alias.exists():
        alias.symlink_to(workspace)
    if kind == "symlink":
        return alias
    if kind == "symlink-dotdot":
        return alias / ".." / workspace.name
    if kind == "dotdot":
        return workspace / ".." / workspace.name
    raise AssertionError(kind)


def _handler_argv(name: str, workspace: Path, files: dict[str, Path]) -> list[str]:
    common = ["--workspace", str(workspace)]
    if name == "qa-export-rewrite":
        return [
            "qa",
            "export",
            "--question",
            "这篇论文的方法是什么",
            "--rewrite",
            str(files["rewrite_qa"]),
            *common,
        ]
    if name == "writing-export-rewrite":
        return [
            "writing",
            "export",
            "--topic",
            "请按证据写提纲",
            "--requirements",
            "用中文写提纲并修订章节。",
            "--rewrite",
            str(files["rewrite_writing"]),
            *common,
        ]
    if name == "qa-import":
        return ["qa", "import", "--context", str(files["light"]), "--answer", str(files["answer"]), *common]
    if name == "writing-import":
        return ["writing", "import", "--context", str(files["light"]), "--draft", str(files["draft"]), *common]
    if name == "knowledge-batch-plan":
        return ["knowledge", "batch-plan", "--paper-id", PAPER_STUB, *common]
    if name == "knowledge-batch-export":
        return ["knowledge", "batch-export", "--plan-id", HEX64, "--batch-index", "0", *common]
    if name == "knowledge-batch-import":
        return ["knowledge", "batch-import", "--context", str(files["light"]), "--document", str(files["document"]), *common]
    if name == "knowledge-batch-status":
        return ["knowledge", "batch-status", *common]
    if name == "knowledge-merge-export":
        return ["knowledge", "merge-export", "--plan-id", HEX64, *common]
    if name == "knowledge-merge-import":
        return ["knowledge", "merge-import", "--context", str(files["light"]), "--document", str(files["document"]), *common]
    if name == "knowledge-finalize":
        return ["knowledge", "finalize", "--plan-id", HEX64, *common]
    if name == "knowledge-refresh-plan":
        return ["knowledge", "refresh-plan", "--paper-id", PAPER_STUB, *common]
    if name == "knowledge-diff":
        return ["knowledge", "diff", "--base-record-id", HEX64, "--candidate-record-id", HEX64, *common]
    if name == "knowledge-apply":
        return [
            "knowledge",
            "apply",
            "--diff",
            str(files["diff"]),
            "--keep-sections",
            "--keep-concepts",
            *common,
        ]
    if name == "writing-outline-export":
        return ["writing", "outline-export", "--context", str(files["light"]), *common]
    if name == "writing-outline-import":
        return ["writing", "outline-import", "--context", str(files["light"]), "--document", str(files["document"]), *common]
    if name == "writing-section-export":
        return ["writing", "section-export", "--project-id", HEX64, "--section-id", "s1", *common]
    if name == "writing-section-import":
        return ["writing", "section-import", "--context", str(files["light"]), "--document", str(files["document"]), *common]
    if name == "writing-history":
        return ["writing", "history", "--project-id", HEX64, *common]
    if name == "writing-project-export":
        return ["writing", "project-export", "--project-id", HEX64, "--output", str(files["output"]), *common]
    raise AssertionError(name)


def _research_files(workspace: Path) -> dict[str, Path]:
    return {
        "rewrite_qa": _save(workspace / "qa.rewrite.json", _rewrite_payload("这篇论文的方法是什么", "quasar method")),
        "rewrite_writing": _save(workspace / "writing.rewrite.json", _rewrite_payload("请按证据写提纲", "quasar method")),
        "light": _save(workspace / "light-context.json", LIGHT_CONTEXT_STUB),
        "answer": _save(workspace / "answer.json", {"text": "x", "citations": []}),
        "draft": _save(workspace / "draft.json", {"markdown": "x", "citations": []}),
        "document": _save(workspace / "document.json", {"schema": "video-paper-wiki.light-writing-outline.v1"}),
        "diff": _save(workspace / "diff.json", {"schema": "not-a-diff"}),
        "output": workspace / "safe-output.md",
    }


def test_new_routes_refuse_raw_workspace_edges(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout, "edge-ws")
    files = _research_files(workspace)
    for handler in WORKSPACE_HANDLERS:
        for kind in ("symlink", "symlink-dotdot", "dotdot"):
            unsafe = _edge_workspace(workspace, kind)
            code = research_main(_handler_argv(handler, unsafe, files))
            payload = _closed_payload(capsys)
            assert code == 2, (handler, kind, payload)
            assert payload["ok"] is False
            assert _error_code(payload) == "WORKSPACE_INVALID"
            assert "Traceback" not in payload.get("message", "")


def test_safe_workspace_positive_and_legacy_dotdot_control(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout, "safe-ws")
    assert research_main(["knowledge", "batch-status", "--workspace", str(workspace)]) == 0
    safe = stdout_json(capsys)
    assert safe["ok"] is True
    legacy = workspace / ".." / workspace.name
    assert research_main(["knowledge", "list", "--workspace", str(legacy)]) == 0
    listed = stdout_json(capsys)
    assert listed["ok"] is True
    assert research_main(["library", "list", "--workspace", str(legacy)]) == 0
    library = stdout_json(capsys)
    assert library["ok"] is True
    assert research_main(["knowledge", "batch-status", "--workspace", str(legacy)]) == 2
    refused = _closed_payload(capsys)
    assert refused["ok"] is False
    assert _error_code(refused) == "WORKSPACE_INVALID"


def test_no_workspace_import_closes_decoder_exceptions(checkout: Path, capsys) -> None:
    root = checkout / ".work" / "decoder"
    root.mkdir(parents=True)
    answer = _save(root / "answer.json", {"text": "x", "citations": []})
    draft = _save(root / "draft.json", {"markdown": "x", "citations": []})
    arrays = root / "nested-10000.json"
    arrays.write_text("[" * 10000 + "]" * 10000, encoding="utf-8")
    integer = root / "digits-5000.json"
    integer.write_text('{"n": ' + ("1" * 5000) + "}", encoding="utf-8")
    shallow = root / "nested-1400.json"
    shallow.write_text("[" * 1400 + "]" * 1400, encoding="utf-8")
    for kind, context, extra in (
        ("qa", arrays, ["--answer", str(answer)]),
        ("writing", arrays, ["--draft", str(draft)]),
        ("qa", integer, ["--answer", str(answer)]),
        ("writing", integer, ["--draft", str(draft)]),
        ("qa", shallow, ["--answer", str(answer)]),
        ("writing", shallow, ["--draft", str(draft)]),
    ):
        code = research_main([kind, "import", "--context", str(context), *extra])
        payload = _closed_payload(capsys)
        assert code == 2, (kind, context.name, payload)
        assert payload["ok"] is False
        assert _error_code(payload) == "LIGHT_HANDOFF_INVALID"
        assert not Path(str(context)[:-5] + ".md").exists()


def test_no_workspace_vault_shaped_import_still_routes(checkout: Path, monkeypatch, capsys) -> None:
    root = checkout / ".work" / "vault-route"
    root.mkdir(parents=True)
    context = _save(root / "old-context.json", {"ok": True, "kind": "qa-context", "evidence": []})
    answer = _save(root / "old-answer.json", {"text": "x", "citations": []})
    draft = _save(root / "old-draft.json", {"markdown": "x", "citations": []})

    def fake_qa(*, context, answer):
        return {"ok": True, "status": "OK", "kind": "qa-answer", "text": "legacy"}

    def fake_writing(*, context, draft):
        return {"ok": True, "status": "OK", "kind": "writing-draft", "markdown": "legacy"}

    monkeypatch.setattr("video_paper_wiki_research.qa.import_and_check", fake_qa)
    monkeypatch.setattr("video_paper_wiki_research.writing.import_and_render", fake_writing)
    assert research_main(["qa", "import", "--context", str(context), "--answer", str(answer)]) == 0
    qa = stdout_json(capsys)
    assert qa["kind"] == "qa-answer"
    assert qa["text"] == "legacy"
    assert research_main(["writing", "import", "--context", str(context), "--draft", str(draft)]) == 0
    writing = stdout_json(capsys)
    assert writing["kind"] == "writing-draft"


def test_live_safe_workspace_rewrite_and_inferred_import(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = _workspace(checkout, "live-safe")
    pdf = checkout / "alpha.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence uniquealpha."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace), "--title", "Alpha"]) == 0
    added = stdout_json(capsys)
    assert added["ok"] is True
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    question = "这篇论文的方法是什么"
    rewrite = _save(workspace / "rewrite.json", _rewrite_payload(question, "quasar method"))
    assert (
        research_main(
            [
                "qa",
                "export",
                "--question",
                question,
                "--workspace",
                str(workspace),
                "--rewrite",
                str(rewrite),
            ]
        )
        == 0
    )
    exported = stdout_json(capsys)
    assert exported["ok"] is True
    context = _save(workspace / "qa-ctx.json", exported)
    chunk = exported["evidence"][0]["chunk_id"]
    answer = _save(
        workspace / "qa-answer.json",
        {"citations": [{"chunk_id": chunk}], "text": f"方法见证据。 [@{chunk}]"},
    )
    output = workspace / "inferred.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--context",
                str(context),
                "--answer",
                str(answer),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    inferred = stdout_json(capsys)
    assert inferred["ok"] is True
    assert output.is_file()
    assert "source.md#page-1" in output.read_text(encoding="utf-8")
    explicit_out = workspace / "explicit.md"
    assert (
        research_main(
            [
                "qa",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context),
                "--answer",
                str(answer),
                "--output",
                str(explicit_out),
            ]
        )
        == 0
    )
    explicit = stdout_json(capsys)
    assert explicit["ok"] is True
    assert explicit_out.is_file()
