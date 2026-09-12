"""Protocol tests for the resumable research workflow. This file uses a labeled stub."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_workflow import (
    CONTEXT_NAME,
    HEX64,
    INTENT_NAME,
    LIGHT_OUTPUT_CONFLICT,
    LIGHT_SELECTION_INVALID,
    LIGHT_SESSION_CONFLICT,
    LIGHT_SESSION_INVALID,
    MANIFEST_NAME,
    NO_RESULTS,
    RECEIPT_NAME,
    REQUEST_NAME,
    STATE_AWAITING,
    STATE_COMPLETE,
    STATE_NEEDS_ATTENTION,
    STATE_STALE,
    WORKFLOW_DIRNAME,
    WORKSPACE_INVALID,
    build_manifest,
    canonical_bytes,
    complete_workflow,
    persisted_bytes,
    prepare_workflow,
    session_identity,
    sha256_bytes,
    sha256_canonical,
    sha256_persisted,
    workflow_status,
)

PROTOCOL_STUB = "protocol-test stub; not a product backend"


def _hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _evidence(chunk: str, paper: str, text: str) -> dict:
    digest = _hex(paper)
    return {
        "chunk_id": chunk,
        "paper_id": f"sha256:{digest}",
        "title": paper,
        "source_sha256": digest,
        "page": 1,
        "markdown_path": f"papers/{digest}/source.md",
        "markdown_sha256": _hex(f"md:{paper}"),
        "text_start": 10,
        "text_end": 10 + len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
        "score": 1.5,
    }


class ProtocolWorkflowBackend:
    """Protocol-test stub; not a product backend."""

    def __init__(self) -> None:
        self.label = PROTOCOL_STUB
        self.snapshot = "snap-1"
        self.export_status: str | None = None
        self.validate_status: str | None = None
        self.render_status: str | None = None
        self.import_status: str | None = None
        self.import_calls = 0
        self.extract_calls: list[str] = []
        self.fail_extract_after = 0
        self.created_outputs: list[str] = []

    def bump(self) -> None:
        self.snapshot = f"snap-{int(self.snapshot.rsplit('-', 1)[-1]) + 1}"

    def _index_id(self) -> str:
        return _hex(f"index:{self.snapshot}")

    def extract_pdf(self, pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict:
        self.extract_calls.append(str(pdf_path))
        if self.fail_extract_after and len(self.extract_calls) > self.fail_extract_after:
            return {"ok": False, "status": "MANUAL_PDF_INVALID", "message": "injected later PDF failure"}
        digest = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
        paper = workspace_root / "papers" / digest
        paper.mkdir(parents=True, exist_ok=True)
        (paper / "source.md").write_text(f"# {title or Path(pdf_path).stem}\n{self.snapshot}\n", encoding="utf-8")
        (paper / "source.json").write_text("{}\n", encoding="utf-8")
        return {
            "ok": True,
            "status": "OK",
            "paper_id": f"sha256:{digest}",
            "disposition": "created",
            "message": "protocol add",
        }

    def inspect_workspace(self, workspace_root: Path) -> dict:
        papers = workspace_root / "papers"
        paper_rows = []
        if papers.is_dir() and not papers.is_symlink():
            for item in sorted(papers.iterdir()):
                if item.is_dir() and not item.is_symlink():
                    paper_rows.append({"paper_id": f"sha256:{item.name}", "title": item.name})
        state = "empty" if not paper_rows else "ready"
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-workspace.v1",
            "workspace_root": str(workspace_root),
            "state": state,
            "index_state": "current" if paper_rows else "missing",
            "index_id": self._index_id() if paper_rows else None,
            "papers": paper_rows,
            "diagnostics": [],
            "next_actions": [],
        }

    def build_index(self, workspace_root: Path) -> dict:
        target = workspace_root / ".light-index"
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.v1.json").write_text("{}\n", encoding="utf-8")
        return {"ok": True, "status": "OK", "index_id": self._index_id(), "message": "protocol index"}

    def export_context(
        self,
        workspace_root: Path,
        *,
        kind: str,
        query: str,
        requirements: str = "",
        paper_ids: list[str] | None = None,
    ) -> dict:
        selected = list(paper_ids or [])
        if self.export_status:
            return {
                "ok": False,
                "status": self.export_status,
                "schema": "video-paper-wiki.light-context.v1",
                "kind": kind,
                "query": query,
                "requirements": requirements,
                "paper_ids": selected,
                "selected_paper_ids": selected,
                "index_id": self._index_id(),
                "workspace_root": str(workspace_root),
                "evidence": [],
                "prompt": "",
                "message": f"protocol {self.export_status}",
            }
        text = f"native evidence for {query} under {self.snapshot}"
        item = _evidence("chk-protocol-1", "Protocol Paper", text)
        return {
            "ok": True,
            "status": "OK",
            "schema": "video-paper-wiki.light-context.v1",
            "kind": kind,
            "query": query,
            "requirements": requirements,
            "paper_ids": selected or [item["paper_id"]],
            "selected_paper_ids": selected,
            "index_id": self._index_id(),
            "workspace_root": str(workspace_root),
            "evidence": [item],
            "prompt": "Use only the evidence. Do not invent sources.",
            "message": "exported local context for the current conversation model",
        }

    def validate_live_context(self, workspace_root: Path, context: dict) -> dict:
        if self.validate_status:
            return {"ok": False, "status": self.validate_status, "message": f"protocol {self.validate_status}"}
        if context.get("index_id") != self._index_id():
            return {"ok": False, "status": "INDEX_STALE", "message": "protocol snapshot changed"}
        if context.get("workspace_root") not in {None, str(workspace_root)}:
            return {"ok": False, "status": "LIGHT_WORKSPACE_MISMATCH", "message": "workspace mismatch"}
        return {
            "ok": True,
            "status": "OK",
            "index_id": self._index_id(),
            "workspace_root": str(workspace_root),
            "message": "live context matches the current snapshot",
        }

    def render_document(self, workspace_root: Path, context: dict, document: dict, *, output: Path) -> dict:
        del workspace_root, context
        if self.render_status:
            return {"ok": False, "status": self.render_status, "message": f"protocol {self.render_status}", "markdown": ""}
        body = document.get("text")
        if body is None:
            body = document.get("markdown")
        if type(body) is not str:
            return {"ok": False, "status": LIGHT_SESSION_INVALID, "message": "document body missing", "markdown": ""}
        markdown = f"{body.rstrip()}\n\n## 参考文献\n\n1. Protocol Paper — PDF 第 1 页\n"
        return {
            "ok": True,
            "status": "OK",
            "markdown": markdown,
            "citations": [{"chunk_id": "chk-protocol-1", "page": 1}],
            "path": str(output),
            "output_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "message": "structural citation check, not a factual-correctness review",
        }

    def import_document(
        self,
        workspace_root: Path,
        context: dict,
        document: dict,
        *,
        output: Path,
        overwrite: bool = True,
    ) -> dict:
        del workspace_root
        self.import_calls += 1
        rendered = self.render_document(workspace_root=Path("."), context=context, document=document, output=output)
        if rendered.get("ok") is not True:
            return rendered
        if self.import_status:
            return {"ok": False, "status": self.import_status, "message": f"protocol {self.import_status}"}
        target = Path(output)
        if target.exists() and not overwrite:
            return {"ok": False, "status": LIGHT_OUTPUT_CONFLICT, "message": "output exists"}
        target.parent.mkdir(parents=True, exist_ok=True)
        data = str(rendered["markdown"]).encode("utf-8")
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        self.created_outputs.append(str(target))
        return {
            "ok": True,
            "status": "OK",
            "path": str(target),
            "output_sha256": hashlib.sha256(data).hexdigest(),
            "markdown": rendered["markdown"],
            "citations": rendered["citations"],
        }


def _prepare(tmp_path: Path, backend: ProtocolWorkflowBackend, **extra):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    kwargs = {"kind": "qa", "query": "What method is used?", "requirements": "", "_backend": backend}
    kwargs.update(extra)
    return workspace, prepare_workflow(workspace, **kwargs)


def test_canonical_encoding_forbids_nonfinite_and_matches_b_form() -> None:
    value = {"b": 1, "a": "论文"}
    encoded = canonical_bytes(value)
    assert encoded == '{"a":"论文","b":1}'.encode("utf-8")
    assert not encoded.endswith(b"\n")
    assert persisted_bytes(value) == encoded + b"\n"
    with pytest.raises(ResearchError) as exc:
        canonical_bytes({"score": float("nan")})
    assert exc.value.code == LIGHT_SESSION_INVALID


def test_session_identity_is_digest_of_request_and_context_bytes() -> None:
    request_sha = sha256_persisted({"schema": "r", "q": 1})
    context_sha = sha256_persisted({"schema": "c", "q": 2})
    first = session_identity(request_sha, context_sha)
    second = session_identity(request_sha, context_sha)
    assert first == second
    assert HEX64.fullmatch(first)
    assert first == sha256_canonical(
        {
            "context_sha256": context_sha,
            "request_sha256": request_sha,
            "schema": "video-paper-wiki.light-workflow-identity.v1",
        }
    )
    assert session_identity(request_sha, sha256_persisted({"schema": "c", "q": 3})) != first


def test_missing_workspace_status_is_readonly_and_prepare_without_pdfs_does_not_create(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    backend = ProtocolWorkflowBackend()
    listed = workflow_status(missing, _backend=backend)
    assert listed["ok"] is True
    assert listed["status"] == "OK"
    assert listed["sessions"] == []
    assert any(row["code"] == "WORKSPACE_MISSING" for row in listed["diagnostics"])
    assert not missing.exists()
    refused = prepare_workflow(missing, kind="qa", query="hello", _backend=backend)
    assert refused["ok"] is False
    assert refused["status"] == WORKSPACE_INVALID
    assert refused["session_id"] is None
    assert not missing.exists()


def test_empty_workspace_status_has_no_missing_diagnostic(tmp_path: Path) -> None:
    workspace = tmp_path / "empty"
    workspace.mkdir()
    listed = workflow_status(workspace, _backend=ProtocolWorkflowBackend())
    assert listed["ok"] is True
    assert listed["sessions"] == []
    assert all(row.get("code") != "WORKSPACE_MISSING" for row in listed["diagnostics"])


def test_prepare_reuses_identical_request_and_snapshot(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, first = _prepare(tmp_path, backend)
    assert first["ok"] is True
    assert first["status"] == "OK"
    assert first["schema"] == "video-paper-wiki.light-workflow.v1"
    assert first["state"] == STATE_AWAITING
    assert first["reused"] is False
    assert HEX64.fullmatch(first["session_id"])
    assert first["context"]["ok"] is True
    session = Path(first["request_path"]).parent
    names = sorted(path.name for path in session.iterdir())
    assert names == [CONTEXT_NAME, MANIFEST_NAME, REQUEST_NAME]
    request_raw = (session / REQUEST_NAME).read_bytes()
    context_raw = (session / CONTEXT_NAME).read_bytes()
    manifest_raw = (session / MANIFEST_NAME).read_bytes()
    assert request_raw.endswith(b"\n") and request_raw.count(b"\n") == 1
    assert request_raw == persisted_bytes(json.loads(request_raw.decode("utf-8")))
    expected_id = session_identity(sha256_bytes(request_raw), sha256_bytes(context_raw))
    assert session.name == expected_id
    assert manifest_raw == persisted_bytes(json.loads(manifest_raw.decode("utf-8")))
    second = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
    assert second["ok"] is True
    assert second["session_id"] == first["session_id"]
    assert second["reused"] is True
    assert (session / REQUEST_NAME).read_bytes() == request_raw
    assert (session / CONTEXT_NAME).read_bytes() == context_raw


def test_source_change_creates_new_session_and_keeps_history(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, first = _prepare(tmp_path, backend)
    old_id = first["session_id"]
    backend.bump()
    second = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
    assert second["ok"] is True
    assert second["session_id"] != old_id
    sessions = {path.name for path in (workspace / WORKFLOW_DIRNAME / "sessions").iterdir()}
    assert sessions == {old_id, second["session_id"]}
    listed = workflow_status(workspace, _backend=backend)
    ids = [row["session_id"] for row in listed["sessions"]]
    assert ids == sorted(ids)
    assert set(ids) == sessions


def test_no_results_does_not_create_a_session(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    backend.export_status = NO_RESULTS
    workspace, result = _prepare(tmp_path, backend)
    assert result["ok"] is False
    assert result["status"] == NO_RESULTS
    assert result["session_id"] is None
    assert "do not ask the current model to invent" in " ".join(result["next_actions"])
    sessions = workspace / WORKFLOW_DIRNAME / "sessions"
    assert not sessions.exists() or list(sessions.iterdir()) == []


def test_malformed_selection_is_rejected_before_session_publish(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(ResearchError) as exc:
        prepare_workflow(workspace, kind="qa", query="hello", paper_ids=["", "sha256:" + "a" * 64], _backend=backend)
    assert exc.value.code == LIGHT_SELECTION_INVALID
    assert not (workspace / WORKFLOW_DIRNAME / "sessions").exists()


def test_bad_hash_unknown_entry_symlink_and_traversal_cannot_be_ready(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session = Path(prepared["request_path"]).parent
    request = session / REQUEST_NAME
    request.write_bytes(request.read_bytes() + b" ")
    damaged = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert damaged["ok"] is True
    assert damaged["status"] == "OK"
    assert damaged["state"] == STATE_NEEDS_ATTENTION
    request.write_bytes(persisted_bytes(json.loads(request.read_text(encoding="utf-8"))))
    extra = session / "notes.txt"
    extra.write_text("user", encoding="utf-8")
    unknown = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert unknown["state"] == STATE_NEEDS_ATTENTION
    extra.unlink()
    sessions = workspace / WORKFLOW_DIRNAME / "sessions"
    link = sessions / ("b" * 64)
    link.symlink_to(session)
    with pytest.raises(ResearchError) as exc:
        workflow_status(workspace, session_id="b" * 64, _backend=backend)
    assert exc.value.code == LIGHT_SESSION_INVALID
    listed = workflow_status(workspace, _backend=backend)
    assert all(row["state"] != STATE_AWAITING or row["session_id"] != "b" * 64 for row in listed["sessions"])
    with pytest.raises(ResearchError) as exc:
        workflow_status(workspace, session_id="../" + prepared["session_id"], _backend=backend)
    assert exc.value.code == LIGHT_SESSION_INVALID
    missing = workflow_status(workspace, session_id="c" * 64, _backend=backend)
    assert missing["ok"] is False
    assert missing["status"] == LIGHT_SESSION_INVALID


def test_status_does_not_create_workflow_dirs_on_empty_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "plain"
    workspace.mkdir()
    before = {path.name for path in workspace.iterdir()}
    workflow_status(workspace, _backend=ProtocolWorkflowBackend())
    after = {path.name for path in workspace.iterdir()}
    assert before == after


def test_complete_and_status_roundtrip_from_protocol_document(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "answers" / "out.md"
    document = {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]}
    completed = complete_workflow(workspace, prepared["session_id"], document, output=output, _backend=backend)
    assert completed["ok"] is True
    assert completed["status"] == "OK"
    assert completed["state"] == STATE_COMPLETE
    assert completed["reused"] is False
    assert output.is_file()
    assert completed["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    session = Path(prepared["request_path"]).parent
    assert (session / INTENT_NAME).is_file()
    assert (session / RECEIPT_NAME).is_file()
    intent = json.loads((session / INTENT_NAME).read_text(encoding="utf-8"))
    assert intent["document_sha256"] == sha256_canonical(document)
    assert intent["output_path"] == str(output)
    restarted = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert restarted["ok"] is True
    assert restarted["state"] == STATE_COMPLETE
    reused = complete_workflow(workspace, prepared["session_id"], document, output=output, _backend=backend)
    assert reused["ok"] is True
    assert reused["reused"] is True
    other = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "A different answer. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=output,
        _backend=backend,
    )
    assert other["ok"] is False
    assert other["status"] == LIGHT_SESSION_CONFLICT
    original = completed["output_sha256"]
    assert hashlib.sha256(output.read_bytes()).hexdigest() == original


def test_existing_output_without_intent_is_conflict(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "already.md"
    output.write_text("user draft\n", encoding="utf-8")
    before = output.read_bytes()
    result = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=output,
        _backend=backend,
    )
    assert result["ok"] is False
    assert result["status"] == LIGHT_OUTPUT_CONFLICT
    assert output.read_bytes() == before
    session = Path(prepared["request_path"]).parent
    assert not (session / INTENT_NAME).exists()
    assert not (session / RECEIPT_NAME).exists()


def test_invalid_model_document_does_not_write_intent(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    backend.render_status = "INVALID_CITATION"
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "bad.md"
    result = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "no citation", "citations": []},
        output=output,
        _backend=backend,
    )
    assert result["ok"] is False
    assert result["status"] == "INVALID_CITATION"
    assert not output.exists()
    session = Path(prepared["request_path"]).parent
    assert not (session / INTENT_NAME).exists()


def test_later_pdf_failure_keeps_completed_additions_and_skips_session(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    backend.fail_extract_after = 1
    workspace = tmp_path / "ws"
    workspace.mkdir()
    first = tmp_path / "one.pdf"
    second = tmp_path / "two.pdf"
    first.write_bytes(b"%PDF-1.4 fixture-one")
    second.write_bytes(b"%PDF-1.4 fixture-two")
    result = prepare_workflow(
        workspace,
        kind="qa",
        query="compare",
        pdf_paths=[first, second],
        _backend=backend,
    )
    assert result["ok"] is False
    assert result["session_id"] is None
    assert len(result["additions"]) == 2
    assert result["additions"][0]["ok"] is True
    assert result["additions"][1]["ok"] is False
    assert not (workspace / WORKFLOW_DIRNAME / "sessions").exists()


def test_prepare_creates_missing_workspace_only_when_pdfs_are_given(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    missing = tmp_path / "created"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 created-workspace")
    result = prepare_workflow(missing, kind="writing", query="related work", pdf_paths=[pdf], _backend=backend)
    assert result["ok"] is True
    assert missing.is_dir()
    assert result["additions"][0]["ok"] is True


def test_stale_live_context_is_not_published_as_awaiting_model(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    backend.validate_status = "INDEX_STALE"
    workspace, result = _prepare(tmp_path, backend)
    assert result["ok"] is False
    assert result["status"] == "INDEX_STALE"
    assert result["session_id"] is None
    assert not (workspace / WORKFLOW_DIRNAME / "sessions").exists()


def test_relative_output_resolves_against_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    monkeypatch.chdir(tmp_path)
    result = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=Path("rel-out.md"),
        _backend=backend,
    )
    assert result["ok"] is True
    assert Path(result["path"]) == tmp_path / "rel-out.md"
    assert (tmp_path / "rel-out.md").is_file()


def _live_pdf(path: Path, texts: list[str]) -> Path:
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    for raw in texts:
        page = writer.add_blank_page(width=400, height=400)
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
    path.write_bytes(buf.getvalue())
    return path


def test_live_t2_prepare_reuses_and_rejects_no_results(tmp_path: Path) -> None:
    from video_paper_wiki_research.light_context import export_context

    workspace = tmp_path / "live-ws"
    pdf = _live_pdf(tmp_path / "live.pdf", ["Hybrid linear attention with attention residuals."])
    first = prepare_workflow(
        workspace,
        kind="qa",
        query="hybrid linear attention",
        pdf_paths=[pdf],
    )
    assert first["ok"] is True
    assert first["state"] == STATE_AWAITING
    assert first["reused"] is False
    assert first["context"]["schema"] == "video-paper-wiki.light-context.v1"
    assert first["context"]["evidence"]
    second = prepare_workflow(workspace, kind="qa", query="hybrid linear attention")
    assert second["session_id"] == first["session_id"]
    assert second["reused"] is True
    empty = prepare_workflow(workspace, kind="qa", query="zzzznotatokenqqqq")
    assert empty["ok"] is False
    assert empty["status"] == NO_RESULTS
    assert empty["session_id"] is None
    sessions = list((workspace / WORKFLOW_DIRNAME / "sessions").iterdir())
    assert {path.name for path in sessions} == {first["session_id"]}
    exported = export_context(workspace, kind="qa", query="hybrid linear attention")
    assert exported["ok"] is True
    assert exported["index_id"] == first["context"]["index_id"]


def test_live_t2_prepare_status_complete_restart_chain(tmp_path: Path) -> None:
    workspace = tmp_path / "chain-ws"
    pdf = _live_pdf(tmp_path / "chain.pdf", ["Hybrid linear attention with attention residuals."])
    prepared = prepare_workflow(
        workspace,
        kind="qa",
        query="hybrid linear attention",
        pdf_paths=[pdf],
    )
    assert prepared["ok"] is True
    item = prepared["context"]["evidence"][0]
    document = {
        "text": f"The paper uses hybrid linear attention. [@{item['chunk_id']}]",
        "citations": [{"chunk_id": item["chunk_id"]}],
    }
    output = tmp_path / "chain-out.md"
    completed = complete_workflow(workspace, prepared["session_id"], document, output=output)
    assert completed["ok"] is True
    assert completed["state"] == STATE_COMPLETE
    assert output.is_file()
    assert "hybrid linear attention" in output.read_text(encoding="utf-8").lower()
    restarted = workflow_status(workspace, session_id=prepared["session_id"])
    assert restarted["ok"] is True
    assert restarted["status"] == "OK"
    assert restarted["state"] == STATE_COMPLETE
    assert restarted["output_sha256"] == completed["output_sha256"]
    reused = complete_workflow(workspace, prepared["session_id"], document, output=output)
    assert reused["ok"] is True
    assert reused["reused"] is True


def test_live_t2_writing_kind_complete(tmp_path: Path) -> None:
    workspace = tmp_path / "write-ws"
    pdf = _live_pdf(tmp_path / "write.pdf", ["Hybrid linear attention with attention residuals."])
    prepared = prepare_workflow(
        workspace,
        kind="writing",
        query="related work on hybrid linear attention",
        requirements="one short paragraph",
        pdf_paths=[pdf],
    )
    assert prepared["ok"] is True
    assert prepared["context"]["kind"] == "writing"
    item = prepared["context"]["evidence"][0]
    document = {
        "markdown": f"Related work uses hybrid linear attention. [@{item['chunk_id']}]",
        "citations": [{"chunk_id": item["chunk_id"]}],
    }
    output = tmp_path / "related.md"
    completed = complete_workflow(workspace, prepared["session_id"], document, output=output)
    assert completed["ok"] is True
    text = output.read_text(encoding="utf-8")
    assert "hybrid linear attention" in text.lower()
    assert "page-1" in text


def _rewrite_request_and_rehash(workspace: Path, session_dir: Path, mutate) -> str:
    request = json.loads((session_dir / REQUEST_NAME).read_bytes().decode("utf-8"))
    context = json.loads((session_dir / CONTEXT_NAME).read_bytes().decode("utf-8"))
    mutate(request)
    request_sha = sha256_persisted(request)
    context_sha = sha256_persisted(context)
    new_id = session_identity(request_sha, context_sha)
    manifest = build_manifest(
        session_id=new_id,
        workspace_root=workspace,
        index_id=context.get("index_id"),
        request_sha256=request_sha,
        context_sha256=context_sha,
    )
    (session_dir / REQUEST_NAME).write_bytes(persisted_bytes(request))
    (session_dir / MANIFEST_NAME).write_bytes(persisted_bytes(manifest))
    new_dir = session_dir.with_name(new_id)
    session_dir.rename(new_dir)
    return new_id


def test_symlink_state_paths_are_refused_and_do_not_leak_files(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    for edge in (".light-workflow", ".light-workflow/sessions", ".light-workflow/staging", ".light-workflow/locks"):
        base = tmp_path / ("case-" + edge.replace("/", "-"))
        workspace = base / "ws"
        workspace.mkdir(parents=True)
        external = base / "outside"
        external.mkdir()
        link = workspace / edge
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(external, target_is_directory=True)
        result = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
        assert result["ok"] is False
        assert result["status"] == LIGHT_SESSION_INVALID
        assert result["session_id"] is None
        leaked = [path for path in external.rglob("*") if path.is_file()]
        assert leaked == []
        listed = workflow_status(workspace, _backend=backend)
        assert listed["ok"] is True
        assert listed["sessions"] == []
        assert any(row["code"] == LIGHT_SESSION_INVALID for row in listed["diagnostics"])


def test_unowned_fixed_temporary_file_is_preserved(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    staging = workspace / WORKFLOW_DIRNAME / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    leftover = staging / f".{prepared['session_id']}.completion-intent.json.tmp"
    leftover.write_text("unrecognized user-owned file\n", encoding="utf-8")
    before = leftover.read_bytes()
    output = tmp_path / "owned-tmp.md"
    completed = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=output,
        _backend=backend,
    )
    assert completed["ok"] is True
    assert leftover.exists()
    assert leftover.read_bytes() == before
    assert leftover.read_text(encoding="utf-8") == "unrecognized user-owned file\n"


def test_failed_pre_publish_revalidate_keeps_existing_history(tmp_path: Path) -> None:
    from video_paper_wiki_research import light_workflow as lw

    backend = ProtocolWorkflowBackend()
    workspace, first = _prepare(tmp_path, backend)
    original = lw._write_persisted

    def write_and_bump(path, value):
        data = original(path, value)
        if path.name == MANIFEST_NAME:
            backend.bump()
        return data

    lw._write_persisted = write_and_bump
    try:
        result = prepare_workflow(workspace, kind="qa", query="A second query", _backend=backend)
    finally:
        lw._write_persisted = original
    assert result["ok"] is False
    assert result["status"] == "INDEX_STALE"
    assert result["session_id"] is None
    sessions = {path.name for path in (workspace / WORKFLOW_DIRNAME / "sessions").iterdir()}
    assert sessions == {first["session_id"]}


def test_source_change_after_staging_does_not_publish_session(tmp_path: Path) -> None:
    from video_paper_wiki_research import light_workflow as lw

    backend = ProtocolWorkflowBackend()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    original = lw._write_persisted
    injected = False

    def write_and_bump(path, value):
        nonlocal injected
        data = original(path, value)
        if path.name == MANIFEST_NAME and not injected:
            injected = True
            backend.bump()
        return data

    lw._write_persisted = write_and_bump
    try:
        result = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
    finally:
        lw._write_persisted = original
    assert injected is True
    assert result["ok"] is False
    assert result["status"] == "INDEX_STALE"
    assert result["session_id"] is None
    sessions = workspace / WORKFLOW_DIRNAME / "sessions"
    assert not sessions.exists() or list(sessions.iterdir()) == []


def test_rehashed_invalid_request_fields_cannot_complete(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session = Path(prepared["request_path"]).parent

    def mutate(request: dict) -> None:
        request["kind"] = "invalid-kind"
        request["query"] = []
        request["selected_paper_ids"] = ["invalid-selection"]
        request["extra"] = "not allowed by contract"

    new_id = _rewrite_request_and_rehash(workspace, session, mutate)
    status = workflow_status(workspace, session_id=new_id, _backend=backend)
    assert status["ok"] is True
    assert status["state"] == STATE_NEEDS_ATTENTION
    output = tmp_path / "invalid-request.md"
    result = complete_workflow(
        workspace,
        new_id,
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=output,
        _backend=backend,
    )
    assert result["ok"] is False
    assert result["status"] == LIGHT_SESSION_INVALID
    assert not output.exists()
    new_dir = workspace / WORKFLOW_DIRNAME / "sessions" / new_id
    assert not (new_dir / INTENT_NAME).exists()
    assert not (new_dir / RECEIPT_NAME).exists()


def test_request_missing_or_extra_fields_need_attention(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session = Path(prepared["request_path"]).parent

    def add_extra(request: dict) -> None:
        request["extra"] = "not allowed"

    extra_id = _rewrite_request_and_rehash(workspace, session, add_extra)
    extra_status = workflow_status(workspace, session_id=extra_id, _backend=backend)
    assert extra_status["state"] == STATE_NEEDS_ATTENTION
    extra_complete = complete_workflow(
        workspace,
        extra_id,
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=tmp_path / "extra.md",
        _backend=backend,
    )
    assert extra_complete["ok"] is False
    assert extra_complete["status"] == LIGHT_SESSION_INVALID
    assert not (tmp_path / "extra.md").exists()

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    workspace, prepared = _prepare(missing_root, backend)
    session = Path(prepared["request_path"]).parent

    def drop_requirements(request: dict) -> None:
        del request["requirements"]

    missing_id = _rewrite_request_and_rehash(workspace, session, drop_requirements)
    missing_status = workflow_status(workspace, session_id=missing_id, _backend=backend)
    assert missing_status["state"] == STATE_NEEDS_ATTENTION
    missing_complete = complete_workflow(
        workspace,
        missing_id,
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=tmp_path / "missing.md",
        _backend=backend,
    )
    assert missing_complete["ok"] is False
    assert missing_complete["status"] == LIGHT_SESSION_INVALID
    assert not (tmp_path / "missing.md").exists()


def test_type_valid_request_inconsistent_with_context_needs_attention(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session = Path(prepared["request_path"]).parent

    def change_query(request: dict) -> None:
        request["query"] = "A different nonempty query"

    new_id = _rewrite_request_and_rehash(workspace, session, change_query)
    status = workflow_status(workspace, session_id=new_id, _backend=backend)
    assert status["ok"] is True
    assert status["state"] == STATE_NEEDS_ATTENTION
    output = tmp_path / "mismatch.md"
    result = complete_workflow(
        workspace,
        new_id,
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=output,
        _backend=backend,
    )
    assert result["ok"] is False
    assert result["status"] == LIGHT_SESSION_INVALID
    assert not output.exists()
    new_dir = workspace / WORKFLOW_DIRNAME / "sessions" / new_id
    assert not (new_dir / INTENT_NAME).exists()
    assert not (new_dir / RECEIPT_NAME).exists()


def test_live_t1_inspect_and_repeated_pdf_reuse(tmp_path: Path) -> None:
    from video_paper_wiki_research.light_workspace import inspect_workspace

    workspace = tmp_path / "inspect-ws"
    workspace.mkdir()
    listed = workflow_status(workspace)
    assert listed["ok"] is True
    assert listed["sessions"] == []
    assert listed["workspace"]["schema"] == "video-paper-wiki.light-workspace.v1"
    assert inspect_workspace(workspace)["state"] in {"empty", "needs_index"}
    pdf = _live_pdf(tmp_path / "inspect.pdf", ["Hybrid linear attention with attention residuals."])
    first = prepare_workflow(workspace, kind="qa", query="hybrid linear attention", pdf_paths=[pdf])
    assert first["ok"] is True
    assert first["additions"][0]["ok"] is True
    assert first["additions"][0].get("disposition") in {"created", "reused", "recovered"}
    second = prepare_workflow(workspace, kind="qa", query="hybrid linear attention", pdf_paths=[pdf])
    assert second["ok"] is True
    assert second["session_id"] == first["session_id"]
    assert second["reused"] is True
    assert second["additions"][0]["ok"] is True
    assert second["additions"][0].get("disposition") == "reused"
    after = workflow_status(workspace)
    assert after["ok"] is True
    assert after["workspace"]["ok"] is True
    assert after["workspace"]["schema"] == "video-paper-wiki.light-workspace.v1"
    assert after["workspace"]["state"] in {"ready", "needs_index"}
    assert inspect_workspace(workspace)["papers"]
