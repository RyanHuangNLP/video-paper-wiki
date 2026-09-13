"""Independent CLI/Skill routing for lightweight library commands.

STUBS ARE LABELLED and exist only to unblock argparse mapping, .work
policy, repeatable-flag, closed-JSON, and r2 routing/input checks. They
are not T1/T2 acceptance and do not constitute final integration.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

from tests.research.conftest import stdout_json
from video_paper_wiki_research.cli import (
    _read_json,
    _read_library_json,
    build_parser,
    main as research_main,
)
from video_paper_wiki_research.contracts import JSON_MAX_BYTES, ResearchError

READ = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "video-paper-read"


def _install_labelled_stub(monkeypatch: pytest.MonkeyPatch, name: str, **attrs):
    """STUB: independent CLI routing only. Not a live T1/T2 backend."""

    full = f"video_paper_wiki_research.{name}"
    module = types.ModuleType(full)
    module.__doc__ = "STUB: independent CLI routing only; not a live owner backend."
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, full, module)
    return module


def _workspace(checkout: Path, name: str = "light-library-cli") -> Path:
    path = checkout / ".work" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _paper(n: int = 1) -> str:
    return "sha256:" + (f"{n:02x}" * 32)


def _write_json(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _object_json(path: Path, payload: dict | None = None) -> Path:
    body = payload if payload is not None else {"ok": True, "schema": "video-paper-wiki.light-knowledge-context.v1"}
    return _write_json(path, json.dumps(body, ensure_ascii=False))


def _refuse_backend(*_args, **_kwargs):
    raise AssertionError("STUB must not run for a refused routing/input case")


def test_help_lists_library_knowledge_compare_backup_commands() -> None:
    parser = build_parser()
    text = parser.format_help()
    for name in ("library", "knowledge", "compare", "backup", "workspace", "workflow"):
        assert name in text
    choices = {action.dest: action for action in parser._actions if getattr(action, "dest", None) == "command"}
    command = choices["command"].choices
    assert {"library", "knowledge", "compare", "backup", "qa", "writing", "workflow"} <= set(command)
    library_help = command["library"].format_help()
    for item in ("list", "edit", "remove", "restore", "replace", "recover"):
        assert item in library_help
    edit_help = command["library"]._subparsers._group_actions[0].choices["edit"].format_help()
    assert "--tag" in edit_help
    assert "--clear-tags" in edit_help
    assert "--paper-id" in edit_help
    compare_export = command["compare"]._subparsers._group_actions[0].choices["export"].format_help()
    assert "--paper-id" in compare_export
    assert "--dimension" in compare_export
    backup_create = command["backup"]._subparsers._group_actions[0].choices["create"].format_help()
    assert "--include-output" in backup_create
    backup_verify = command["backup"]._subparsers._group_actions[0].choices["verify"].format_help()
    assert "--archive" in backup_verify
    assert "--workspace" not in backup_verify or backup_verify.count("--workspace") == 0


def test_missing_flags_and_exclusive_tags_are_usage(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    assert research_main(["library"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["library", "edit", "--workspace", str(workspace)]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert research_main(["compare", "export", "--workspace", str(workspace), "--query", "q"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"
    assert (
        research_main(
            [
                "library",
                "edit",
                "--workspace",
                str(workspace),
                "--paper-id",
                _paper(),
                "--tag",
                "video",
                "--clear-tags",
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert "clear-tags" in payload["error"]["message"]


def test_compare_export_requires_two_paper_ids(checkout: Path, monkeypatch, capsys) -> None:
    def export_comparison_context(*_args, **_kwargs):
        raise AssertionError("STUB must not run with a single --paper-id")

    _install_labelled_stub(monkeypatch, "light_compare", export_comparison_context=export_comparison_context)
    workspace = _workspace(checkout)
    assert (
        research_main(
            [
                "compare",
                "export",
                "--workspace",
                str(workspace),
                "--query",
                "method",
                "--paper-id",
                _paper(),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert "two" in payload["error"]["message"]


def test_repeatable_flags_take_one_value_each(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def update_paper_metadata(workspace_root, paper_id, *, title=None, tags=None):
        seen["edit"] = {"workspace": workspace_root, "paper_id": paper_id, "title": title, "tags": tags}
        return {"ok": True, "status": "OK", "message": "edited", "reused": False}

    def export_comparison_context(workspace_root, *, query, paper_ids, dimensions=None):
        seen["compare"] = {
            "workspace": workspace_root,
            "query": query,
            "paper_ids": paper_ids,
            "dimensions": dimensions,
        }
        return {"ok": True, "status": "OK", "schema": "video-paper-wiki.light-comparison-context.v1"}

    def create_backup(workspace_root, *, output, extra_outputs=None):
        seen["backup"] = {
            "workspace": workspace_root,
            "output": output,
            "extra_outputs": extra_outputs,
        }
        return {"ok": True, "status": "OK", "message": "created"}

    _install_labelled_stub(monkeypatch, "light_library", update_paper_metadata=update_paper_metadata)
    _install_labelled_stub(monkeypatch, "light_compare", export_comparison_context=export_comparison_context)
    _install_labelled_stub(monkeypatch, "light_backup", create_backup=create_backup)
    workspace = _workspace(checkout)
    extra_a = checkout / ".work" / "extra-a.md"
    extra_b = checkout / ".work" / "extra-b.md"
    extra_a.write_text("a\n", encoding="utf-8")
    extra_b.write_text("b\n", encoding="utf-8")
    output = checkout / ".work" / "backups" / "ws.zip"
    assert (
        research_main(
            [
                "library",
                "edit",
                "--workspace",
                str(workspace),
                "--paper-id",
                _paper(1),
                "--title",
                "Display",
                "--tag",
                "video",
                "--tag",
                "diffusion",
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["edit"]["tags"] == ["video", "diffusion"]
    assert seen["edit"]["title"] == "Display"
    assert (
        research_main(
            [
                "compare",
                "export",
                "--workspace",
                str(workspace),
                "--query",
                "training data",
                "--paper-id",
                _paper(1),
                "--paper-id",
                _paper(2),
                "--dimension",
                "method",
                "--dimension",
                "experiments",
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["compare"]["paper_ids"] == [_paper(1), _paper(2)]
    assert seen["compare"]["dimensions"] == ["method", "experiments"]
    assert (
        research_main(
            [
                "backup",
                "create",
                "--workspace",
                str(workspace),
                "--output",
                str(output),
                "--include-output",
                str(extra_a),
                "--include-output",
                str(extra_b),
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["backup"]["extra_outputs"] == [extra_a.resolve(), extra_b.resolve()]
    assert seen["backup"]["output"] == output.resolve()
    assert not output.exists()


def test_omitted_tag_preserves_and_clear_tags_sends_empty_list(checkout: Path, monkeypatch, capsys) -> None:
    seen: list[object] = []

    def update_paper_metadata(workspace_root, paper_id, *, title=None, tags=None):
        seen.append({"title": title, "tags": tags, "paper_id": paper_id})
        return {"ok": True, "status": "OK", "reused": True, "message": "ok"}

    _install_labelled_stub(monkeypatch, "light_library", update_paper_metadata=update_paper_metadata)
    workspace = _workspace(checkout)
    assert (
        research_main(
            ["library", "edit", "--workspace", str(workspace), "--paper-id", _paper(), "--title", "Only title"]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen[-1]["tags"] is None
    assert seen[-1]["title"] == "Only title"
    assert (
        research_main(
            ["library", "edit", "--workspace", str(workspace), "--paper-id", _paper(), "--clear-tags"]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen[-1]["tags"] == []


def test_library_remove_calls_archive_paper(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def archive_paper(workspace_root, paper_id):
        seen["archive"] = {"workspace": workspace_root, "paper_id": paper_id}
        return {
            "ok": True,
            "status": "OK",
            "archive_id": "ab" * 16,
            "paper_id": paper_id,
            "message": "archived; restore with library restore --archive-id",
        }

    _install_labelled_stub(monkeypatch, "light_library", archive_paper=archive_paper)
    workspace = _workspace(checkout)
    paper = _paper(3)
    assert research_main(["library", "remove", "--workspace", str(workspace), "--paper-id", paper]) == 0
    payload = stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["archive_id"] == "ab" * 16
    assert "restore" in payload["message"]
    assert seen["archive"]["paper_id"] == paper
    assert seen["archive"]["workspace"] == workspace.resolve()


def test_library_and_knowledge_list_do_not_create_missing_workspace(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, Path] = {}

    def list_papers(workspace_root):
        seen["papers"] = workspace_root
        return {"ok": True, "status": "OK", "papers": [], "message": "empty"}

    def list_knowledge(workspace_root):
        seen["knowledge"] = workspace_root
        return {"ok": True, "status": "OK", "records": [], "message": "empty"}

    _install_labelled_stub(monkeypatch, "light_library", list_papers=list_papers)
    _install_labelled_stub(monkeypatch, "light_knowledge", list_knowledge=list_knowledge)
    missing = checkout / ".work" / "absent-library"
    assert not missing.exists()
    assert research_main(["library", "list", "--workspace", str(missing)]) == 0
    stdout_json(capsys)
    assert research_main(["knowledge", "list", "--workspace", str(missing)]) == 0
    stdout_json(capsys)
    assert seen["papers"] == missing.resolve()
    assert seen["knowledge"] == missing.resolve()
    assert not missing.exists()


def test_path_policy_runs_before_backend(checkout: Path, monkeypatch, capsys) -> None:
    def list_papers(_workspace_root):
        raise AssertionError("STUB must not run for a path outside .work")

    def import_comparison(*_args, **_kwargs):
        raise AssertionError("STUB must not run for output outside .work")

    def create_backup(*_args, **_kwargs):
        raise AssertionError("STUB must not run for backup output inside the workspace")

    _install_labelled_stub(monkeypatch, "light_library", list_papers=list_papers)
    _install_labelled_stub(monkeypatch, "light_compare", import_comparison=import_comparison)
    _install_labelled_stub(monkeypatch, "light_backup", create_backup=create_backup)
    outside = checkout / "not-work"
    outside.mkdir()
    assert research_main(["library", "list", "--workspace", str(outside)]) == 2
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "WORKSPACE_INVALID"
    workspace = _workspace(checkout)
    context = workspace / "ctx.json"
    document = workspace / "doc.json"
    context.write_text(json.dumps({"schema": "video-paper-wiki.light-comparison-context.v1"}), encoding="utf-8")
    document.write_text(json.dumps({"schema": "video-paper-wiki.light-comparison-document.v1"}), encoding="utf-8")
    assert (
        research_main(
            [
                "compare",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context),
                "--document",
                str(document),
                "--output",
                str(outside / "table.md"),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "WORKSPACE_INVALID"
    inside = workspace / "inside-backup.zip"
    assert (
        research_main(
            ["backup", "create", "--workspace", str(workspace), "--output", str(inside)]
        )
        == 2
    )
    refused = stdout_json(capsys)
    assert refused["ok"] is False
    assert refused["error"]["code"] == "LIGHT_BACKUP_INVALID"
    assert not inside.exists()


def test_compare_output_requires_md_suffix(checkout: Path, monkeypatch, capsys) -> None:
    def import_comparison(*_args, **_kwargs):
        raise AssertionError("STUB must not run for a non-markdown output")

    _install_labelled_stub(monkeypatch, "light_compare", import_comparison=import_comparison)
    workspace = _workspace(checkout)
    context = workspace / "ctx.json"
    document = workspace / "doc.json"
    context.write_text("{}", encoding="utf-8")
    document.write_text("{}", encoding="utf-8")
    output = checkout / ".work" / "table.txt"
    assert (
        research_main(
            [
                "compare",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context),
                "--document",
                str(document),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "WORKSPACE_INVALID"
    assert not output.exists()


def test_backup_verify_is_read_only_and_does_not_create(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, Path] = {}

    def verify_backup(archive_path):
        seen["archive"] = archive_path
        return {"ok": True, "status": "OK", "message": "verified"}

    _install_labelled_stub(monkeypatch, "light_backup", verify_backup=verify_backup)
    missing = checkout / ".work" / "absent-archive.zip"
    assert research_main(["backup", "verify", "--archive", str(missing)]) == 2
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "WORKSPACE_INVALID"
    assert not missing.exists()
    assert "archive" not in seen
    archive = checkout / ".work" / "present.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"PK\x03\x04")
    before = archive.read_bytes()
    assert research_main(["backup", "verify", "--archive", str(archive)]) == 0
    stdout_json(capsys)
    assert seen["archive"] == archive.resolve()
    assert archive.read_bytes() == before


def test_knowledge_and_compare_import_reject_bad_json_without_backend(checkout: Path, monkeypatch, capsys) -> None:
    def import_knowledge(*_args, **_kwargs):
        raise AssertionError("STUB must not run for unreadable JSON")

    def import_comparison(*_args, **_kwargs):
        raise AssertionError("STUB must not run for unreadable JSON")

    _install_labelled_stub(monkeypatch, "light_knowledge", import_knowledge=import_knowledge)
    _install_labelled_stub(monkeypatch, "light_compare", import_comparison=import_comparison)
    workspace = _workspace(checkout)
    missing = workspace / "absent.json"
    document = workspace / "doc.json"
    document.write_text("[]", encoding="utf-8")
    assert (
        research_main(
            [
                "knowledge",
                "import",
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
    output = checkout / ".work" / "should-not-exist.md"
    assert (
        research_main(
            [
                "compare",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(document),
                "--document",
                str(document),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    assert not output.exists()


@pytest.mark.parametrize("kind", ["deep-array", "huge-integer"])
@pytest.mark.parametrize("command", ["knowledge", "compare"])
def test_parser_limits_are_closed_before_backend(
    checkout: Path,
    monkeypatch,
    capsys,
    kind: str,
    command: str,
) -> None:
    workspace = _workspace(checkout)
    path = checkout / f"caller-{command}-{kind}.json"
    payload = ("{" + '"a":' + "[" * 10000 + "0" + "]" * 10000 + "}") if kind == "deep-array" else ("{" + '"a":' + ("9" * 5001) + "}")
    original = payload.encode()
    path.write_bytes(original)
    calls: list[bool] = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("Malformed parser input reached a backend")

    monkeypatch.setattr("video_paper_wiki_research.cli._load_light", forbidden)
    args = [command, "import", "--workspace", str(workspace), "--context", str(path), "--document", str(path)]
    if command == "compare":
        args.extend(["--output", str(workspace / "reports" / "comparison.md")])
    result = research_main(args)
    captured = capsys.readouterr()
    assert result != 0
    parsed = json.loads(captured.out)
    assert parsed["ok"] is False
    assert parsed.get("error", {}).get("code", parsed.get("status")) == "LIGHT_HANDOFF_INVALID"
    assert "Traceback" not in captured.err
    assert path.read_bytes() == original
    assert not (workspace / "reports" / "comparison.md").exists()
    assert not calls


def test_legacy_workflow_json_loader_still_accepts_nan(checkout: Path) -> None:
    legacy = checkout / ".work" / "legacy-nan.json"
    _write_json(legacy, '{"a": NaN}')
    payload = _read_json(str(legacy))
    assert payload["a"] != payload["a"]
    with pytest.raises(ResearchError) as caught:
        _read_library_json(str(legacy))
    assert caught.value.code == "LIGHT_HANDOFF_INVALID"


@pytest.mark.parametrize(
    ("name", "writer"),
    [
        ("missing", None),
        ("malformed", lambda path: _write_json(path, "{not json")),
        ("non_object", lambda path: _write_json(path, "[]")),
        ("duplicate_key", lambda path: _write_json(path, '{"a": 1, "a": 2}')),
        ("nan", lambda path: _write_json(path, '{"a": NaN}')),
        ("infinity", lambda path: _write_json(path, '{"a": Infinity}')),
        (
            "parent_symlink",
            lambda path: _write_json(path, '{"ok": true}'),
        ),
        (
            "final_symlink",
            lambda path: _write_json(path, '{"ok": true}'),
        ),
        (
            "hardlink",
            lambda path: _write_json(path, '{"ok": true}'),
        ),
        ("directory", None),
        ("fifo", None),
        ("oversized", None),
    ],
)
def test_knowledge_compare_json_input_refusals_are_routing_only(
    checkout: Path,
    monkeypatch,
    capsys,
    name: str,
    writer,
) -> None:
    _install_labelled_stub(monkeypatch, "light_knowledge", import_knowledge=_refuse_backend)
    _install_labelled_stub(monkeypatch, "light_compare", import_comparison=_refuse_backend)
    workspace = _workspace(checkout)
    document = _object_json(workspace / "valid-doc.json", {"schema": "video-paper-wiki.light-knowledge-document.v1"})
    output = checkout / ".work" / f"should-not-exist-{name}.md"
    if name == "missing":
        context = workspace / "absent.json"
    elif name == "directory":
        context = workspace / "dir-input"
        context.mkdir()
    elif name == "fifo":
        context = workspace / "fifo.json"
        os.mkfifo(context)
    elif name == "oversized":
        context = workspace / "too-big.json"
        context.write_bytes(b"{" + (b"a" * (JSON_MAX_BYTES + 1)) + b"}")
    elif name == "parent_symlink":
        real_dir = checkout / "real-json"
        real_dir.mkdir()
        writer(real_dir / "ctx.json")
        linked = checkout / "via-json-parent"
        linked.symlink_to(real_dir)
        context = linked / "ctx.json"
    elif name == "final_symlink":
        real = writer(workspace / "real-ctx.json")
        context = workspace / "link-ctx.json"
        context.symlink_to(real)
    elif name == "hardlink":
        real = writer(workspace / "real-hard.json")
        context = workspace / "hard-ctx.json"
        os.link(real, context)
    else:
        context = writer(workspace / f"{name}.json")
    assert (
        research_main(
            [
                "knowledge",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context),
                "--document",
                str(document),
            ]
        )
        == 2
    )
    knowledge = stdout_json(capsys)
    assert knowledge["ok"] is False
    assert knowledge["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    assert (
        research_main(
            [
                "compare",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context),
                "--document",
                str(document),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    compared = stdout_json(capsys)
    assert compared["ok"] is False
    assert compared["error"]["code"] == "LIGHT_HANDOFF_INVALID"
    assert not output.exists()


def test_saved_export_object_and_outside_work_json_are_routing_wrappers(
    checkout: Path,
    monkeypatch,
    capsys,
) -> None:
    seen: dict[str, object] = {}

    def import_knowledge(workspace_root, context, document):
        seen["knowledge"] = {"workspace": workspace_root, "context": context, "document": document}
        return {"ok": True, "status": "OK", "record_id": "r2", "message": "imported"}

    def import_comparison(workspace_root, context, document, *, output):
        seen["compare"] = {
            "workspace": workspace_root,
            "context": context,
            "document": document,
            "output": output,
        }
        return {"ok": True, "status": "OK", "message": "imported"}

    _install_labelled_stub(monkeypatch, "light_knowledge", import_knowledge=import_knowledge)
    _install_labelled_stub(monkeypatch, "light_compare", import_comparison=import_comparison)
    workspace = _workspace(checkout)
    export_object = {
        "ok": True,
        "status": "OK",
        "schema": "video-paper-wiki.light-knowledge-context.v1",
        "paper_id": _paper(8),
        "score": 1.5,
    }
    document = {
        "schema": "video-paper-wiki.light-knowledge-document.v1",
        "paper_id": _paper(8),
        "sections": {},
        "concepts": [],
    }
    outside_ctx = _object_json(checkout / "outside-work" / "saved-export.json", export_object)
    document_path = _object_json(workspace / "saved-document.json", document)
    assert ".work" not in outside_ctx.parts
    assert (
        research_main(
            [
                "knowledge",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(outside_ctx),
                "--document",
                str(document_path),
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["knowledge"]["context"]["schema"] == "video-paper-wiki.light-knowledge-context.v1"
    assert seen["knowledge"]["context"]["paper_id"] == _paper(8)
    assert seen["knowledge"]["context"]["score"] == 1.5
    compare_ctx = {
        "ok": True,
        "status": "OK",
        "schema": "video-paper-wiki.light-comparison-context.v1",
        "query": "method",
        "paper_ids": [_paper(8), _paper(9)],
    }
    compare_doc = {"schema": "video-paper-wiki.light-comparison-document.v1", "rows": []}
    compare_ctx_path = _object_json(workspace / "compare-export.json", compare_ctx)
    compare_doc_path = _object_json(workspace / "compare-document.json", compare_doc)
    output = checkout / ".work" / "reports" / "compare.md"
    assert (
        research_main(
            [
                "compare",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(compare_ctx_path),
                "--document",
                str(compare_doc_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["compare"]["context"]["schema"] == "video-paper-wiki.light-comparison-context.v1"
    assert seen["compare"]["output"] == output.resolve()
    assert not output.exists()


@pytest.mark.parametrize(
    "name",
    ("missing", "parent_symlink", "final_symlink", "hardlink", "directory", "fifo", "oversized", "not_md"),
)
def test_include_output_refusals_keep_caller_path_and_skip_backend(
    checkout: Path,
    monkeypatch,
    capsys,
    name: str,
) -> None:
    seen: dict[str, object] = {}

    def create_backup(workspace_root, *, output, extra_outputs=None):
        seen["backup"] = extra_outputs
        raise AssertionError("STUB must not run for an unsafe extra Markdown path")

    _install_labelled_stub(monkeypatch, "light_backup", create_backup=create_backup)
    workspace = _workspace(checkout)
    zip_out = checkout / ".work" / "backups" / f"{name}.zip"
    if name == "missing":
        extra = checkout / "absent-extra.md"
    elif name == "directory":
        extra = checkout / "extra-dir.md"
        extra.mkdir()
    elif name == "fifo":
        extra = checkout / "extra-fifo.md"
        os.mkfifo(extra)
    elif name == "oversized":
        extra = checkout / "too-big.md"
        extra.write_bytes(b"x" * (JSON_MAX_BYTES + 1))
    elif name == "not_md":
        extra = checkout / "notes.txt"
        extra.write_text("plain\n", encoding="utf-8")
    elif name == "parent_symlink":
        real_dir = checkout / "real-extra"
        real_dir.mkdir()
        (real_dir / "draft.md").write_text("# draft\n", encoding="utf-8")
        linked = checkout / "via-extra-parent"
        linked.symlink_to(real_dir)
        extra = linked / "draft.md"
        assert extra.resolve() != extra
    elif name == "final_symlink":
        real = checkout / "real-draft.md"
        real.write_text("# draft\n", encoding="utf-8")
        extra = checkout / "link-draft.md"
        extra.symlink_to(real)
    else:
        real = checkout / "real-hard.md"
        real.write_text("# draft\n", encoding="utf-8")
        extra = checkout / "hard-draft.md"
        os.link(real, extra)
    assert (
        research_main(
            [
                "backup",
                "create",
                "--workspace",
                str(workspace),
                "--output",
                str(zip_out),
                "--include-output",
                str(extra),
            ]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIGHT_BACKUP_INVALID"
    assert "backup" not in seen
    assert not zip_out.exists()
    if name == "parent_symlink":
        assert payload["error"]["details"].get("edge") == str(extra.parent)
        assert payload["error"]["details"].get("path") == str(extra)


def test_include_output_outside_work_keeps_caller_path(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def create_backup(workspace_root, *, output, extra_outputs=None):
        seen["backup"] = {"workspace": workspace_root, "output": output, "extra_outputs": extra_outputs}
        return {"ok": True, "status": "OK", "message": "created"}

    _install_labelled_stub(monkeypatch, "light_backup", create_backup=create_backup)
    workspace = _workspace(checkout)
    extra = checkout / "outside-work-draft.md"
    extra.write_text("# outside\n", encoding="utf-8")
    zip_out = checkout / ".work" / "backups" / "outside-extra.zip"
    assert ".work" not in extra.parts
    assert (
        research_main(
            [
                "backup",
                "create",
                "--workspace",
                str(workspace),
                "--output",
                str(zip_out),
                "--include-output",
                str(extra),
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["backup"]["extra_outputs"] == [extra]
    assert seen["backup"]["output"] == zip_out.resolve()
    assert not zip_out.exists()


def test_closed_backend_result_is_nonzero(checkout: Path, monkeypatch, capsys) -> None:
    def export_knowledge_context(workspace_root, *, paper_id):
        del workspace_root, paper_id
        return {"ok": False, "status": "INSUFFICIENT_EVIDENCE", "message": "no evidence"}

    _install_labelled_stub(monkeypatch, "light_knowledge", export_knowledge_context=export_knowledge_context)
    workspace = _workspace(checkout)
    assert (
        research_main(["knowledge", "export", "--workspace", str(workspace), "--paper-id", _paper()])
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["status"] == "INSUFFICIENT_EVIDENCE"


def test_owner_modules_are_required_and_empty_list_is_live(checkout: Path, capsys) -> None:
    import video_paper_wiki_research.light_backup as light_backup
    import video_paper_wiki_research.light_compare as light_compare
    import video_paper_wiki_research.light_knowledge as light_knowledge
    import video_paper_wiki_research.light_library as light_library

    for module, attr in (
        (light_knowledge, "export_knowledge_context"),
        (light_compare, "export_comparison_context"),
        (light_library, "list_papers"),
        (light_backup, "create_backup"),
    ):
        assert callable(getattr(module, attr))
    workspace = _workspace(checkout)
    assert research_main(["library", "list", "--workspace", str(workspace)]) == 0
    payload = stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["papers"] == []


def test_remaining_library_commands_map_arguments(checkout: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def restore_paper(workspace_root, archive_id):
        seen["restore"] = {"workspace": workspace_root, "archive_id": archive_id}
        return {"ok": True, "status": "OK", "reused": False, "message": "restored"}

    def replace_paper(workspace_root, paper_id, pdf_path, *, title=None):
        seen["replace"] = {
            "workspace": workspace_root,
            "paper_id": paper_id,
            "pdf_path": pdf_path,
            "title": title,
        }
        return {"ok": True, "status": "OK", "old_paper_id": paper_id, "message": "replaced"}

    def recover_library(workspace_root, *, operation_id=None):
        seen["recover"] = {"workspace": workspace_root, "operation_id": operation_id}
        return {"ok": True, "status": "OK", "operations": [], "message": "idle"}

    def export_knowledge_context(workspace_root, *, paper_id):
        seen["kexport"] = {"workspace": workspace_root, "paper_id": paper_id}
        return {"ok": True, "status": "OK", "schema": "video-paper-wiki.light-knowledge-context.v1"}

    def import_knowledge(workspace_root, context, document):
        seen["kimport"] = {"workspace": workspace_root, "context": context, "document": document}
        return {"ok": True, "status": "OK", "record_id": "r1", "message": "imported"}

    def build_knowledge_views(workspace_root):
        seen["kbuild"] = workspace_root
        return {"ok": True, "status": "OK", "index_path": str(workspace_root / "knowledge" / "CURRENT.json")}

    def restore_backup(archive_path, *, destination):
        seen["brestore"] = {"archive": archive_path, "destination": destination}
        return {"ok": True, "status": "OK", "historical_session_root": str(destination / ".light-workflow" / "history")}

    _install_labelled_stub(
        monkeypatch,
        "light_library",
        restore_paper=restore_paper,
        replace_paper=replace_paper,
        recover_library=recover_library,
    )
    _install_labelled_stub(
        monkeypatch,
        "light_knowledge",
        export_knowledge_context=export_knowledge_context,
        import_knowledge=import_knowledge,
        build_knowledge_views=build_knowledge_views,
    )
    _install_labelled_stub(monkeypatch, "light_backup", restore_backup=restore_backup)
    workspace = _workspace(checkout)
    pdf = checkout / "replacement.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    archive = checkout / ".work" / "ok.zip"
    archive.write_bytes(b"PK\x03\x04")
    destination = checkout / ".work" / "restored-root"
    context = {"schema": "video-paper-wiki.light-knowledge-context.v1", "paper_id": _paper(4)}
    document = {
        "schema": "video-paper-wiki.light-knowledge-document.v1",
        "paper_id": _paper(4),
        "sections": {},
        "concepts": [],
    }
    context_path = workspace / "kctx.json"
    document_path = workspace / "kdoc.json"
    context_path.write_text(json.dumps(context), encoding="utf-8")
    document_path.write_text(json.dumps(document), encoding="utf-8")
    assert research_main(["library", "restore", "--workspace", str(workspace), "--archive-id", "cd" * 16]) == 0
    stdout_json(capsys)
    assert seen["restore"]["archive_id"] == "cd" * 16
    assert (
        research_main(
            [
                "library",
                "replace",
                "--workspace",
                str(workspace),
                "--paper-id",
                _paper(4),
                "--pdf",
                str(pdf),
                "--title",
                "New title",
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["replace"]["pdf_path"] == pdf
    assert seen["replace"]["title"] == "New title"
    assert research_main(["library", "recover", "--workspace", str(workspace), "--operation-id", "ef" * 16]) == 0
    stdout_json(capsys)
    assert seen["recover"]["operation_id"] == "ef" * 16
    assert research_main(["knowledge", "export", "--workspace", str(workspace), "--paper-id", _paper(4)]) == 0
    stdout_json(capsys)
    assert seen["kexport"]["paper_id"] == _paper(4)
    assert (
        research_main(
            [
                "knowledge",
                "import",
                "--workspace",
                str(workspace),
                "--context",
                str(context_path),
                "--document",
                str(document_path),
            ]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["kimport"]["document"]["schema"] == "video-paper-wiki.light-knowledge-document.v1"
    assert research_main(["knowledge", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert seen["kbuild"] == workspace.resolve()
    assert (
        research_main(
            ["backup", "restore", "--archive", str(archive), "--destination", str(destination)]
        )
        == 0
    )
    stdout_json(capsys)
    assert seen["brestore"]["archive"] == archive.resolve()
    assert seen["brestore"]["destination"] == destination.resolve()
    assert not destination.exists()


def test_skill_and_docs_keep_users_out_of_internal_json() -> None:
    skill = (READ / "SKILL.md").read_text(encoding="utf-8")
    library = (READ / "references" / "library.md").read_text(encoding="utf-8")
    workflow = (READ / "references" / "workflow.md").read_text(encoding="utf-8")
    openai = (READ / "agents" / "openai.yaml").read_text(encoding="utf-8")
    readme = Path(__file__).resolve().parents[2] / "README.md"
    quickstart = Path(__file__).resolve().parents[2] / "docs" / "lightweight-library-quickstart.md"
    pdf_quickstart = Path(__file__).resolve().parents[2] / "docs" / "lightweight-pdf-quickstart.md"
    assert "do not ask the user to author" in skill.lower() or "Create internal JSON yourself" in skill
    assert "references/library.md" in skill
    assert "knowledge export" in library
    assert "archive_paper" in library
    assert "evidence不足" in library or "证据不足" in library
    assert "summary" in library and "open_questions" in library
    assert "library remove" in library
    assert "reversible" in library.lower() or "archive" in library
    assert "scientifically verified" in library
    assert "qa|writing" in skill or "--kind qa|writing" in skill
    assert "Do not invent new session kinds" in skill or "do not add `workflow --kind`" in workflow.lower()
    assert "$video-paper-read" in openai
    assert "organize" in openai.lower() or "back up" in openai.lower()
    readme_text = readme.read_text(encoding="utf-8")
    assert "docs/lightweight-library-quickstart.md" in readme_text
    assert "lightweight-library-quickstart.md" in pdf_quickstart.read_text(encoding="utf-8")
    guide = quickstart.read_text(encoding="utf-8")
    assert "library remove" in guide
    assert "backup verify" in guide
    assert "不要把内部 JSON" in guide
    assert "reports/" in guide
    assert "8 MiB" in library or "8 MiB" in guide
    assert "stdout" in library.lower() or "export" in library.lower()
    assert "file-only" in library.lower() or "empty directory" in library.lower() or "空目录" in guide
    assert "no replacement" in library.lower() or "before staging" in library.lower() or "未替换" in guide
