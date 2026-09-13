from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tests.research.conftest import stdout_json
from video_paper_wiki_research.cli import main as research_main


def _pdf_with_page_texts(texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    for raw in texts:
        page = writer.add_blank_page(width=400, height=400)
        if not raw:
            continue
        payload = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in raw)
        payload = payload.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 24 200 Td ({payload}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font_ref
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _workspace(checkout: Path) -> Path:
    path = checkout / ".work" / "light-cli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_light_commands_are_accepted_with_workspace(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Hybrid linear attention residual video generation."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace), "--title", "Fixture"]) == 0
    added = stdout_json(capsys)
    assert added["ok"] is True
    assert added["page_count"] == 1
    paper_id = added["paper_id"]
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    built = stdout_json(capsys)
    assert built["ok"] is True
    assert built["paper_count"] == 1
    assert research_main(
        ["qa", "export", "--question", "hybrid linear attention", "--workspace", str(workspace)]
    ) == 0
    qa_context = stdout_json(capsys)
    assert qa_context["schema"] == "video-paper-wiki.light-context.v1"
    assert qa_context["kind"] == "qa"
    assert Path(qa_context["workspace_root"]) == workspace.resolve()
    assert research_main(
        [
            "writing",
            "export",
            "--topic",
            "hybrid linear attention",
            "--requirements",
            "one paragraph",
            "--workspace",
            str(workspace),
            "--paper-id",
            paper_id,
        ]
    ) == 0
    writing_context = stdout_json(capsys)
    assert writing_context["schema"] == "video-paper-wiki.light-context.v1"
    assert writing_context["kind"] == "writing"
    assert Path(writing_context["workspace_root"]) == workspace.resolve()


def test_old_qa_and_writing_modes_still_work_without_workspace(checkout: Path, monkeypatch, capsys) -> None:
    def fake_qa(**kwargs):
        assert kwargs["vault_root"] == "vault"
        assert kwargs["upstream_root"] == "upstream"
        assert kwargs["retrieval_config"] == "config.json"
        return {"ok": True, "status": "OK", "kind": "qa-context", "question": kwargs["question"]}

    def fake_writing(**kwargs):
        assert kwargs["paper_ids"] == ["arxiv:1"]
        return {"ok": True, "status": "OK", "kind": "writing-context", "topic": kwargs["topic"]}

    monkeypatch.setattr("video_paper_wiki_research.qa.export_from_question", fake_qa)
    monkeypatch.setattr("video_paper_wiki_research.writing.export_from_request", fake_writing)
    assert research_main(
        [
            "qa",
            "export",
            "--question",
            "q",
            "--vault-root",
            "vault",
            "--upstream-root",
            "upstream",
            "--config",
            "config.json",
        ]
    ) == 0
    assert stdout_json(capsys)["kind"] == "qa-context"
    assert research_main(
        [
            "writing",
            "export",
            "--topic",
            "t",
            "--requirements",
            "r",
            "--paper-id",
            "arxiv:1",
            "--vault-root",
            "vault",
            "--upstream-root",
            "upstream",
            "--config",
            "config.json",
        ]
    ) == 0
    assert stdout_json(capsys)["kind"] == "writing-context"


def test_workspace_cannot_mix_with_old_vault_args(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    code = research_main(
        [
            "qa",
            "export",
            "--question",
            "q",
            "--workspace",
            str(workspace),
            "--vault-root",
            "vault",
            "--upstream-root",
            "upstream",
            "--config",
            "config.json",
        ]
    )
    assert code == 2
    payload = stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    code = research_main(
        [
            "writing",
            "export",
            "--topic",
            "t",
            "--requirements",
            "r",
            "--workspace",
            str(workspace),
            "--vault-root",
            "vault",
        ]
    )
    assert code == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"


def test_workspace_outside_work_is_rejected(checkout: Path, capsys) -> None:
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["text on page"]))
    outside = checkout / "not-work"
    outside.mkdir()
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(outside)]) == 2
    payload = stdout_json(capsys)
    assert payload["error"]["code"] == "WORKSPACE_INVALID"


def test_light_import_routes_by_schema_and_writes_markdown(checkout: Path, capsys) -> None:
    workspace = _workspace(checkout)
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Attention residuals keep video generation stable."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(
        ["qa", "export", "--question", "attention residuals", "--workspace", str(workspace)]
    ) == 0
    context = stdout_json(capsys)
    assert context["ok"] is True
    chunk_id = context["evidence"][0]["chunk_id"]
    context_path = workspace / "qa-context.json"
    answer_path = workspace / "qa-answer.json"
    output_path = workspace / "qa.md"
    context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
    answer_path.write_text(
        json.dumps(
            {
                "text": f"Residuals stabilize generation. [@{chunk_id}]",
                "citations": [{"chunk_id": chunk_id}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert research_main(
        [
            "qa",
            "import",
            "--context",
            str(context_path),
            "--answer",
            str(answer_path),
            "--output",
            str(output_path),
        ]
    ) == 0
    imported = stdout_json(capsys)
    assert imported["ok"] is True
    assert Path(imported["path"]) == output_path.resolve()
    markdown = output_path.read_text(encoding="utf-8")
    assert imported["markdown"] == markdown
    assert "PDF 第" in markdown
    _assert_markdown_links_resolve(output_path, workspace)


def test_old_import_still_used_without_light_schema(checkout: Path, monkeypatch, capsys) -> None:
    context = checkout / ".work" / "old-context.json"
    answer = checkout / ".work" / "old-answer.json"
    context.parent.mkdir(parents=True, exist_ok=True)
    context.write_text(json.dumps({"ok": True, "kind": "qa-context", "evidence": []}), encoding="utf-8")
    answer.write_text(json.dumps({"text": "x", "citations": []}), encoding="utf-8")

    def fake_import(*, context, answer):
        return {"ok": True, "status": "OK", "kind": "qa-answer", "text": "legacy"}

    monkeypatch.setattr("video_paper_wiki_research.qa.import_and_check", fake_import)
    assert research_main(["qa", "import", "--context", str(context), "--answer", str(answer)]) == 0
    payload = stdout_json(capsys)
    assert payload["kind"] == "qa-answer"
    assert payload["text"] == "legacy"
    assert research_main(
        ["qa", "import", "--context", str(context), "--answer", str(answer), "--workspace", str(context.parent)]
    ) == 2
    assert stdout_json(capsys)["error"]["code"] == "USAGE"


def _assert_markdown_links_resolve(output: Path, workspace: Path) -> None:
    text = output.read_text(encoding="utf-8")
    hrefs = re.findall(r"\]\(<([^>]+#page-\d+)>\)", text) + re.findall(r"\]\(([^()<>]+#page-\d+)\)", text)
    ticks = re.findall(r"`([^`]+#page-\d+)`", text)
    found = hrefs + ticks
    assert found
    workspace = workspace.resolve()
    for raw in found:
        path, anchor = raw.split("#", 1)
        target = (output.parent / path).resolve()
        assert target.is_file(), raw
        assert target == workspace or workspace in target.parents
        assert f'id="{anchor}"' in target.read_text(encoding="utf-8")


def _seed_light_context(checkout: Path, capsys, *, workspace_name: str = "light-cli"):
    workspace = checkout / ".work" / workspace_name
    workspace.mkdir(parents=True, exist_ok=True)
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(_pdf_with_page_texts(["Hybrid linear attention residual video generation."]))
    assert research_main(["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace), "--title", "Fixture"]) == 0
    stdout_json(capsys)
    assert research_main(["index", "build", "--workspace", str(workspace)]) == 0
    stdout_json(capsys)
    assert research_main(["qa", "export", "--question", "hybrid linear attention", "--workspace", str(workspace)]) == 0
    qa_context = stdout_json(capsys)
    assert research_main(
        [
            "writing",
            "export",
            "--topic",
            "hybrid linear attention",
            "--requirements",
            "one paragraph",
            "--workspace",
            str(workspace),
        ]
    ) == 0
    writing_context = stdout_json(capsys)
    return workspace, qa_context, writing_context


def test_import_workspace_root_and_output_locations(checkout: Path, capsys) -> None:
    workspace, qa_context, writing_context = _seed_light_context(checkout, capsys)
    chunk = qa_context["evidence"][0]["chunk_id"]
    writing_chunk = writing_context["evidence"][0]["chunk_id"]
    spaced = checkout / ".work" / "path with spaces" / "out"
    notes = workspace / "notes"
    sibling_dir = checkout / ".work" / "handoff"
    sibling_dir.mkdir(parents=True)
    cases = [
        ("qa", qa_context, "--answer", {"text": f"Hybrid linear attention. [@{chunk}]", "citations": [{"chunk_id": chunk}]}, checkout / "qa.md"),
        ("qa", qa_context, "--answer", {"text": f"Hybrid linear attention. [@{chunk}]", "citations": [{"chunk_id": chunk}]}, None),
        ("qa", qa_context, "--answer", {"text": f"Hybrid linear attention. [@{chunk}]", "citations": [{"chunk_id": chunk}]}, notes / "qa.md"),
        ("qa", qa_context, "--answer", {"text": f"Hybrid linear attention. [@{chunk}]", "citations": [{"chunk_id": chunk}]}, spaced / "qa.md"),
        ("writing", writing_context, "--draft", {"markdown": f"Draft. [@{writing_chunk}]", "citations": [{"chunk_id": writing_chunk}]}, checkout / "draft.md"),
        ("writing", writing_context, "--draft", {"markdown": f"Draft. [@{writing_chunk}]", "citations": [{"chunk_id": writing_chunk}]}, None),
        ("writing", writing_context, "--draft", {"markdown": f"Draft. [@{writing_chunk}]", "citations": [{"chunk_id": writing_chunk}]}, notes / "draft.md"),
        ("writing", writing_context, "--draft", {"markdown": f"Draft. [@{writing_chunk}]", "citations": [{"chunk_id": writing_chunk}]}, spaced / "draft.md"),
    ]
    for kind, context, flag, document, output in cases:
        context_path = sibling_dir / f"{kind}-context.json"
        input_path = sibling_dir / f"{kind}-input.json"
        context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
        input_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        argv = [kind, "import", "--context", str(context_path), flag, str(input_path)]
        expected = output if output is not None else context_path.with_suffix(".md")
        if output is not None:
            argv.extend(["--output", str(output)])
        assert research_main(argv) == 0
        imported = stdout_json(capsys)
        assert imported["ok"] is True
        written = Path(imported["path"])
        assert written == expected.resolve()
        assert imported["markdown"] == written.read_text(encoding="utf-8")
        _assert_markdown_links_resolve(written, workspace)


def test_import_workspace_mismatch_neither_and_legacy_context(checkout: Path, capsys) -> None:
    workspace, qa_context, _writing = _seed_light_context(checkout, capsys, workspace_name="root-cases")
    chunk = qa_context["evidence"][0]["chunk_id"]
    context_path = workspace / "qa-context.json"
    answer_path = workspace / "qa-answer.json"
    answer_path.write_text(
        json.dumps({"text": f"Hybrid linear attention. [@{chunk}]", "citations": [{"chunk_id": chunk}]}),
        encoding="utf-8",
    )
    other = checkout / ".work" / "other"
    other.mkdir()
    context_path.write_text(json.dumps(qa_context, ensure_ascii=False), encoding="utf-8")
    assert research_main(
        [
            "qa",
            "import",
            "--context",
            str(context_path),
            "--answer",
            str(answer_path),
            "--workspace",
            str(other),
            "--output",
            str(workspace / "mismatch.md"),
        ]
    ) == 2
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_WORKSPACE_MISMATCH"
    stripped = dict(qa_context)
    stripped.pop("workspace_root")
    early = workspace / "early-context.json"
    early.write_text(json.dumps(stripped, ensure_ascii=False), encoding="utf-8")
    assert research_main(["qa", "import", "--context", str(early), "--answer", str(answer_path)]) == 2
    assert stdout_json(capsys)["error"]["code"] == "LIGHT_WORKSPACE_REQUIRED"
    assert research_main(
        [
            "qa",
            "import",
            "--context",
            str(early),
            "--answer",
            str(answer_path),
            "--workspace",
            str(workspace),
            "--output",
            str(workspace / "compat.md"),
        ]
    ) == 0
    imported = stdout_json(capsys)
    assert imported["ok"] is True
    _assert_markdown_links_resolve(Path(imported["path"]), workspace)
