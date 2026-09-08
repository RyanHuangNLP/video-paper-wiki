"""Integrated library pipeline through the public CLI.

Live T1/T2 backends are required. Missing owner modules fail these tests.
Synthetic PDFs and labelled model-document fixtures are not current-model trials.
"""

from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

from tests.research.conftest import stdout_json
from tests.research.test_light_cli import _pdf_with_page_texts
from tests.research.test_light_compare import _comparison_document
from tests.research.test_light_knowledge import _knowledge_document
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.light_knowledge import SECTION_KEYS, UNKNOWN_TEXT

ROOT = Path(__file__).resolve().parents[2]
READ = ROOT / ".agents" / "skills" / "video-paper-read"

OWNER_APIS = (
    ("light_knowledge", "export_knowledge_context"),
    ("light_knowledge", "import_knowledge"),
    ("light_knowledge", "list_knowledge"),
    ("light_knowledge", "build_knowledge_views"),
    ("light_compare", "export_comparison_context"),
    ("light_compare", "import_comparison"),
    ("light_library", "list_papers"),
    ("light_library", "update_paper_metadata"),
    ("light_library", "archive_paper"),
    ("light_library", "restore_paper"),
    ("light_library", "replace_paper"),
    ("light_library", "recover_library"),
    ("light_backup", "create_backup"),
    ("light_backup", "verify_backup"),
    ("light_backup", "restore_backup"),
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
        raise AssertionError("owner modules/APIs are required for integrated T3 tests: " + ", ".join(missing))


def _run(args: list[str], capsys, *, expect: int = 0) -> dict:
    code = research_main(args)
    payload = stdout_json(capsys)
    assert code == expect, payload
    return payload


def _save_export(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


NESTED_CHINESE_NOTE = Path("笔记") / "深层" / "阅读.md"
NESTED_GREEK_CODE = Path("notes-α") / "deep" / "code-δ.py"
NESTED_EMPTY_DIR = Path("notes-α") / "deep" / "empty"
ASCII_NOTE = Path("notes.md")
CHINESE_EXTERNAL_REPORT = "外部报告.md"


def _add_nested_notes(paper: Path) -> None:
    (paper / NESTED_EMPTY_DIR).mkdir(parents=True)
    (paper / NESTED_GREEK_CODE).write_text("# Greek code-note\nprint('γ')\n", encoding="utf-8")
    (paper / NESTED_CHINESE_NOTE).parent.mkdir(parents=True)
    (paper / NESTED_CHINESE_NOTE).write_text("嵌套中文笔记\n", encoding="utf-8")


def _paper_inventory(paper: Path) -> tuple[dict[str, bytes], list[str]]:
    files = {
        path.relative_to(paper).as_posix(): path.read_bytes()
        for path in paper.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    directories = sorted(
        path.relative_to(paper).as_posix()
        for path in paper.rglob("*")
        if path.is_dir() and not path.is_symlink()
    )
    return files, directories


def test_owner_modules_must_be_present() -> None:
    _require_live_backends()


def test_existing_qa_writing_workflow_kinds_are_unchanged(checkout: Path, capsys) -> None:
    workspace = checkout / ".work" / "pipeline-kinds"
    workspace.mkdir(parents=True)
    assert (
        research_main(
            ["workflow", "prepare", "--workspace", str(workspace), "--kind", "notes", "--query", "q"]
        )
        == 2
    )
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "USAGE"
    help_text = __import__("video_paper_wiki_research.cli", fromlist=["build_parser"]).build_parser().format_help()
    assert "workflow" in help_text
    assert "library" in help_text


def test_skill_organize_and_compare_flows_are_documented() -> None:
    skill = (READ / "SKILL.md").read_text(encoding="utf-8")
    library = (READ / "references" / "library.md").read_text(encoding="utf-8")
    workflow = (READ / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "knowledge export" in skill or "knowledge export" in library
    assert "knowledge import" in library
    assert "knowledge build" in library
    assert "compare export" in library
    assert "compare import" in library
    assert "Create internal JSON yourself" in skill
    assert "8 MiB" in skill or "8 MiB" in library
    assert "CLI stdout" in library or "export JSON object" in library
    assert "file-only" in library
    assert "no replacement" in library
    assert "video-paper-ingest" in skill
    assert "video-paper-query" in skill
    assert "Never pick a real Vault implicitly" in skill
    assert "structural test fixture" in workflow
    assert "overwrite=True" in workflow or "never uses `overwrite=True`" in workflow
    for key in SECTION_KEYS:
        assert key in library
    assert "至少一节" in (ROOT / "docs" / "lightweight-library-quickstart.md").read_text(encoding="utf-8") or (
        "At least one section must be provisional" in library
    )


def test_live_library_knowledge_compare_backup_chain(checkout: Path, capsys) -> None:
    _require_live_backends()
    workspace = checkout / ".work" / "live-library-pipe"
    workspace.mkdir(parents=True)
    first = checkout / "one.pdf"
    second = checkout / "two.pdf"
    first.write_bytes(
        _pdf_with_page_texts(
            ["Alpha residual attention transformer architecture training experiment limitation uniquealpha."]
        )
    )
    second.write_bytes(
        _pdf_with_page_texts(
            ["Beta diffusion sampler transformer architecture training experiment limitation uniquebeta."]
        )
    )
    alpha = _run(
        ["pdf", "add", "--pdf", str(first), "--workspace", str(workspace), "--title", "Alpha"],
        capsys,
    )
    beta = _run(
        ["pdf", "add", "--pdf", str(second), "--workspace", str(workspace), "--title", "Beta"],
        capsys,
    )
    assert alpha["ok"] is True and beta["ok"] is True
    paper = Path(alpha["markdown_path"]).parent
    note = paper / ASCII_NOTE
    note.write_text("keep this user note\n", encoding="utf-8")
    _add_nested_notes(paper)
    nested_bytes = {
        ASCII_NOTE.as_posix(): note.read_bytes(),
        NESTED_CHINESE_NOTE.as_posix(): (paper / NESTED_CHINESE_NOTE).read_bytes(),
        NESTED_GREEK_CODE.as_posix(): (paper / NESTED_GREEK_CODE).read_bytes(),
    }
    live_inventory = _paper_inventory(paper)
    assert NESTED_EMPTY_DIR.as_posix() in live_inventory[1]
    assert NESTED_CHINESE_NOTE.as_posix() in live_inventory[0]
    assert NESTED_GREEK_CODE.as_posix() in live_inventory[0]
    built = _run(["index", "build", "--workspace", str(workspace)], capsys)
    assert built["ok"] is True
    prepared = _run(
        [
            "workflow",
            "prepare",
            "--workspace",
            str(workspace),
            "--kind",
            "qa",
            "--query",
            "residual attention transformer",
            "--paper-id",
            alpha["paper_id"],
        ],
        capsys,
    )
    assert prepared["ok"] is True
    session_dir = Path(prepared["context_path"]).parent
    session_files = {
        name: (session_dir / name).read_bytes() for name in ("request.json", "context.json", "manifest.json")
    }

    idle = _run(["library", "recover", "--workspace", str(workspace)], capsys)
    assert idle["ok"] is True
    assert idle["operations"] == []
    listed = _run(["library", "list", "--workspace", str(workspace)], capsys)
    assert listed["ok"] is True
    assert {item["paper_id"] for item in listed["papers"]} == {alpha["paper_id"], beta["paper_id"]}

    exported = _run(
        ["knowledge", "export", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
        capsys,
    )
    assert exported["ok"] is True
    assert exported["paper_id"] == alpha["paper_id"]
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    # LABELLED synthetic model-document fixture; not a current-model trial.
    document = _knowledge_document(alpha["paper_id"], chunk)
    context_path = _save_export(workspace / "kctx.json", exported)
    document_path = _save_export(workspace / "kdoc.json", document)
    imported = _run(
        [
            "knowledge",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(context_path),
            "--document",
            str(document_path),
        ],
        capsys,
    )
    assert imported["ok"] is True
    assert imported["source_status"] == "current"
    assert Path(imported["page_path"]).is_file()
    views = _run(["knowledge", "build", "--workspace", str(workspace)], capsys)
    assert views["ok"] is True
    knowledge = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    assert knowledge["ok"] is True
    assert knowledge["heads"][alpha["paper_id"]] == imported["record_id"]
    assert knowledge["records"][0]["source_status"] == "current"

    closed_doc = {
        "schema": document["schema"],
        "paper_id": alpha["paper_id"],
        "concepts": [],
        "sections": {key: {"citations": [], "status": "unknown", "text": UNKNOWN_TEXT} for key in SECTION_KEYS},
    }
    closed_path = _save_export(workspace / "all-unknown.json", closed_doc)
    closed = _run(
        [
            "knowledge",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(context_path),
            "--document",
            str(closed_path),
        ],
        capsys,
        expect=2,
    )
    assert closed["ok"] is False
    assert closed["status"] == "INSUFFICIENT_EVIDENCE"

    compared = _run(
        [
            "compare",
            "export",
            "--workspace",
            str(workspace),
            "--query",
            "transformer architecture",
            "--paper-id",
            alpha["paper_id"],
            "--paper-id",
            beta["paper_id"],
        ],
        capsys,
    )
    assert compared["ok"] is True
    by_paper = {item["paper_id"]: item["chunk_id"] for item in compared["context"]["evidence"]}
    # LABELLED synthetic comparison fixture; not a current-model trial.
    compare_doc = _comparison_document([alpha["paper_id"], beta["paper_id"]], by_paper)
    compare_ctx = _save_export(workspace / "cctx.json", compared)
    compare_doc_path = _save_export(workspace / "cdoc.json", compare_doc)
    compare_md = workspace / "reports" / "compare.md"
    table = _run(
        [
            "compare",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(compare_ctx),
            "--document",
            str(compare_doc_path),
            "--output",
            str(compare_md),
        ],
        capsys,
    )
    assert table["ok"] is True
    markdown = compare_md.read_text(encoding="utf-8")
    assert "|" in markdown
    assert "source.md#page-1" in markdown
    conflict = _run(
        [
            "compare",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(compare_ctx),
            "--document",
            str(compare_doc_path),
            "--output",
            str(compare_md),
        ],
        capsys,
        expect=2,
    )
    assert conflict["ok"] is False
    assert compare_md.read_text(encoding="utf-8") == markdown

    tagged = _run(
        [
            "library",
            "edit",
            "--workspace",
            str(workspace),
            "--paper-id",
            alpha["paper_id"],
            "--tag",
            "video",
            "--tag",
            "diffusion",
        ],
        capsys,
    )
    assert tagged["ok"] is True
    assert tagged["tags"] == ["video", "diffusion"]
    stale_export = _run(
        ["knowledge", "export", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
        capsys,
        expect=2,
    )
    assert stale_export["ok"] is False
    assert stale_export["status"] == "INDEX_STALE"
    cleared = _run(
        ["library", "edit", "--workspace", str(workspace), "--paper-id", alpha["paper_id"], "--clear-tags"],
        capsys,
    )
    assert cleared["ok"] is True
    assert cleared["tags"] == []
    rebuilt = _run(["index", "build", "--workspace", str(workspace)], capsys)
    assert rebuilt["ok"] is True
    live_inventory = _paper_inventory(paper)
    stale_listed = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    statuses = {item["record_id"]: item for item in stale_listed["records"]}
    assert statuses[imported["record_id"]]["source_status"] == "stale"

    archived = _run(
        ["library", "remove", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
        capsys,
    )
    assert archived["ok"] is True
    archive_id = archived["archive_id"]
    archive_paper = workspace / ".light-library" / "archive" / archive_id / "paper"
    assert not paper.exists()
    assert _paper_inventory(archive_paper) == live_inventory
    missing_list = _run(["knowledge", "list", "--workspace", str(workspace)], capsys)
    row = next(item for item in missing_list["records"] if item["record_id"] == imported["record_id"])
    assert row["source_status"] in {"missing-source", "stale"}
    restored_paper = _run(
        ["library", "restore", "--workspace", str(workspace), "--archive-id", archive_id],
        capsys,
    )
    assert restored_paper["ok"] is True
    assert paper.is_dir()
    assert _paper_inventory(paper) == live_inventory
    assert (paper / NESTED_EMPTY_DIR).is_dir()
    for rel, data in nested_bytes.items():
        assert (paper / rel).read_bytes() == data
        assert (paper / rel).name == Path(rel).name

    replacement_pdf = checkout / "replacement.pdf"
    replacement_pdf.write_bytes(_pdf_with_page_texts(["Replacement native extract body unique-replace."]))
    replaced = _run(
        [
            "library",
            "replace",
            "--workspace",
            str(workspace),
            "--paper-id",
            alpha["paper_id"],
            "--pdf",
            str(replacement_pdf),
            "--title",
            "Alpha replaced",
        ],
        capsys,
    )
    assert replaced["ok"] is True
    assert replaced["new_paper_id"] != alpha["paper_id"]
    assert replaced["retained_note_paths"]
    old_archive = workspace / ".light-library" / "archive" / replaced["archive_id"] / "paper"
    assert _paper_inventory(old_archive) == live_inventory
    current = workspace / "papers" / replaced["new_paper_id"].split(":", 1)[1]
    assert (current / "source.md").is_file()
    assert not (current / "notes-α").exists()
    assert not (current / "笔记").exists()
    prior = (current / "prior-paper-notes.md").read_text(encoding="utf-8")
    assert NESTED_GREEK_CODE.as_posix() in prior
    assert NESTED_CHINESE_NOTE.as_posix() in prior
    recovered = _run(["library", "recover", "--workspace", str(workspace)], capsys)
    assert recovered["ok"] is True
    assert recovered["operations"]
    assert all(item.get("ok") is True for item in recovered["operations"])

    extra = checkout / CHINESE_EXTERNAL_REPORT
    extra_bytes = "外部报告：中文与 Ελληνικά\n".encode("utf-8")
    extra.write_bytes(extra_bytes)
    extra_before = extra.read_bytes()
    (workspace / "empty-reports").mkdir()
    backup = checkout / ".work" / "pipe-backups" / "ws.zip"
    backup.parent.mkdir(parents=True)
    created = _run(
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup),
            "--include-output",
            str(extra),
        ],
        capsys,
    )
    assert created["ok"] is True
    assert created.get("reused") is False
    with zipfile.ZipFile(backup) as archive:
        names = archive.namelist()
        assert names[0] == "LIGHT-LIBRARY-MANIFEST.json"
        assert all(not name.endswith("/") for name in names)
        assert any(name.endswith(NESTED_CHINESE_NOTE.as_posix()) for name in names)
        assert any(name.endswith(NESTED_GREEK_CODE.as_posix()) for name in names)
        assert any(name.endswith(CHINESE_EXTERNAL_REPORT) for name in names)
        assert any(name.endswith(ASCII_NOTE.as_posix()) for name in names)
    first_backup = backup.read_bytes()
    reused_backup = _run(
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup),
            "--include-output",
            str(extra),
        ],
        capsys,
    )
    assert reused_backup["ok"] is True
    assert reused_backup.get("reused") is True
    assert backup.read_bytes() == first_backup
    verified = _run(["backup", "verify", "--archive", str(backup)], capsys)
    assert verified["ok"] is True
    destination = checkout / ".work" / "pipe-restored"
    restored = _run(
        ["backup", "restore", "--archive", str(backup), "--destination", str(destination)],
        capsys,
    )
    assert restored["ok"] is True
    hist = Path(restored["historical_session_root"])
    assert hist.is_dir()
    for name, data in session_files.items():
        assert (hist / session_dir.name / name).read_bytes() == data
    assert not (destination / ".light-workflow" / "sessions").exists() or not any(
        (destination / ".light-workflow" / "sessions").iterdir()
    )
    dest_notes = list(destination.joinpath("papers").glob("*/*note*"))
    dest_notes.extend(destination.joinpath(".light-library").glob("archive/*/paper/notes.md"))
    dest_chinese = list(destination.joinpath(".light-library").glob("archive/*/paper/笔记/深层/阅读.md"))
    dest_code = list(destination.joinpath(".light-library").glob("archive/*/paper/notes-α/deep/code-δ.py"))
    assert any("keep this user note" in path.read_text(encoding="utf-8") for path in dest_notes)
    assert dest_chinese
    assert all(path.name == "阅读.md" for path in dest_chinese)
    assert all(path.read_bytes() == nested_bytes[NESTED_CHINESE_NOTE.as_posix()] for path in dest_chinese)
    assert dest_code
    assert all(path.name == "code-δ.py" for path in dest_code)
    assert all(path.read_bytes() == nested_bytes[NESTED_GREEK_CODE.as_posix()] for path in dest_code)
    extra_rows = verified.get("extra_outputs") or []
    assert extra_rows
    assert extra_rows[0]["restore_path"].endswith(CHINESE_EXTERNAL_REPORT)
    assert (destination / extra_rows[0]["restore_path"]).read_bytes() == extra_bytes
    assert extra.read_bytes() == extra_before
    # Backup ZIP is file-only; empty directories are a library archive/restore property.
    duplicate = _run(
        [
            "compare",
            "export",
            "--workspace",
            str(workspace),
            "--query",
            "transformer",
            "--paper-id",
            beta["paper_id"],
            "--paper-id",
            beta["paper_id"],
        ],
        capsys,
        expect=2,
    )
    assert duplicate["ok"] is False
