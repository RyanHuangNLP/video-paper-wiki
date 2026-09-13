"""Interrupt, restart, and conflict recovery tests for the research workflow."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from video_paper_wiki_research.light_workflow import (
    HOOK_AFTER_INTENT,
    HOOK_AFTER_INTENT_STAGED,
    HOOK_AFTER_OUTPUT,
    HOOK_AFTER_RECEIPT_STAGED,
    HOOK_BEFORE_RECEIPT,
    HOOK_BEFORE_SESSION_PUBLISH,
    INTENT_NAME,
    LIGHT_OUTPUT_CONFLICT,
    LIGHT_SESSION_CONFLICT,
    LIGHT_WORKSPACE_BUSY,
    RECEIPT_NAME,
    STATE_AWAITING,
    STATE_COMPLETE,
    STATE_NEEDS_ATTENTION,
    STATE_STALE,
    WORKFLOW_DIRNAME,
    complete_workflow,
    persisted_bytes,
    prepare_workflow,
    sha256_canonical,
    workflow_status,
)
from tests.research.test_light_workflow import ProtocolWorkflowBackend, _live_pdf, _prepare


class InjectedStop(RuntimeError):
    pass


def _document() -> dict:
    return {
        "text": "The paper uses the protocol method. [@chk-protocol-1]",
        "citations": [{"chunk_id": "chk-protocol-1"}],
    }


def test_restart_after_prepare_can_status_read_and_complete(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session_id = prepared["session_id"]
    restarted = workflow_status(workspace, session_id=session_id, _backend=backend)
    assert restarted["ok"] is True
    assert restarted["state"] == STATE_AWAITING
    assert restarted["context"]["evidence"][0]["text"]
    output = tmp_path / "restart.md"
    completed = complete_workflow(workspace, session_id, _document(), output=output, _backend=backend)
    assert completed["ok"] is True
    again = workflow_status(workspace, session_id=session_id, _backend=backend)
    assert again["state"] == STATE_COMPLETE
    assert hashlib.sha256(output.read_bytes()).hexdigest() == completed["output_sha256"]


def test_intent_interrupt_allows_exact_retry_and_does_not_mark_complete(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "intent.md"

    def hook(name: str) -> None:
        if name == HOOK_AFTER_INTENT:
            raise InjectedStop("stop after intent")

    try:
        complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend, _hook=hook)
    except InjectedStop:
        pass
    session = Path(prepared["request_path"]).parent
    assert (session / INTENT_NAME).is_file()
    assert not (session / RECEIPT_NAME).exists()
    assert not output.exists()
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["ok"] is True
    assert status["state"] == STATE_AWAITING
    assert status["document_sha256"] == sha256_canonical(_document())
    assert "retry complete_workflow" in " ".join(status["next_actions"])
    retried = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert retried["ok"] is True
    assert retried["state"] == STATE_COMPLETE
    assert output.is_file()


def test_output_interrupt_before_receipt_retries_without_overwrite_conflict(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "output.md"

    def hook(name: str) -> None:
        if name == HOOK_AFTER_OUTPUT:
            raise InjectedStop("stop after output")

    try:
        complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend, _hook=hook)
    except InjectedStop:
        pass
    assert output.is_file()
    session = Path(prepared["request_path"]).parent
    assert (session / INTENT_NAME).is_file()
    assert not (session / RECEIPT_NAME).exists()
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["state"] == STATE_AWAITING
    retried = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert retried["ok"] is True
    assert retried["reused"] is True
    assert (session / RECEIPT_NAME).is_file()


def test_receipt_interrupt_leaves_unfinished_not_false_complete(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "receipt.md"

    def hook(name: str) -> None:
        if name == HOOK_BEFORE_RECEIPT:
            raise InjectedStop("stop before receipt")

    try:
        complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend, _hook=hook)
    except InjectedStop:
        pass
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["state"] == STATE_AWAITING
    assert status["ok"] is True
    retried = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert retried["ok"] is True
    assert retried["state"] == STATE_COMPLETE


def test_user_edited_output_is_never_overwritten(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "edited.md"

    def hook(name: str) -> None:
        if name == HOOK_AFTER_OUTPUT:
            output.write_text("user changed the generated draft\n", encoding="utf-8")
            raise InjectedStop("user edit")

    try:
        complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend, _hook=hook)
    except InjectedStop:
        pass
    before = output.read_bytes()
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["state"] == STATE_NEEDS_ATTENTION
    refused = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_SESSION_CONFLICT
    assert output.read_bytes() == before
    session = Path(prepared["request_path"]).parent
    assert not (session / RECEIPT_NAME).exists()


def test_completed_then_source_change_is_stale_and_keeps_output(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "kept.md"
    completed = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert completed["ok"] is True
    before = output.read_bytes()
    backend.bump()
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["ok"] is True
    assert status["state"] == STATE_STALE
    assert output.read_bytes() == before
    stale_complete = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert stale_complete["ok"] is False
    assert stale_complete["status"] == "INDEX_STALE"
    assert output.read_bytes() == before


def test_deleted_completed_output_needs_attention(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "gone.md"
    complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    output.unlink()
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["state"] == STATE_NEEDS_ATTENTION
    assert status["ok"] is True


def test_matching_bytes_without_intent_still_conflict(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "same-bytes.md"
    rendered = backend.render_document(workspace, prepared["context"], _document(), output=output)
    output.write_text(rendered["markdown"], encoding="utf-8")
    before = output.read_bytes()
    result = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert result["ok"] is False
    assert result["status"] == LIGHT_OUTPUT_CONFLICT
    assert output.read_bytes() == before


def test_concurrent_complete_returns_busy_and_no_false_receipt(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    session_id = prepared["session_id"]
    lock_path = workspace / ".light-workflow" / "locks" / f"{session_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, os, sys, time\n"
                f"fd = os.open({str(lock_path)!r}, os.O_RDWR | os.O_CREAT, 0o644)\n"
                "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                "sys.stdout.write('held\\n')\n"
                "sys.stdout.flush()\n"
                "time.sleep(30)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        cwd=str(tmp_path),
    )
    try:
        assert holder.stdout is not None
        line = holder.stdout.readline()
        assert line.strip() == b"held"
        result = complete_workflow(
            workspace,
            session_id,
            _document(),
            output=tmp_path / "busy.md",
            _backend=backend,
        )
        assert result["ok"] is False
        assert result["status"] == LIGHT_WORKSPACE_BUSY
        session = Path(prepared["request_path"]).parent
        assert not (session / RECEIPT_NAME).exists()
        assert not (tmp_path / "busy.md").exists()
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_prepare_after_complete_reuses_completed_session(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    output = tmp_path / "done.md"
    complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    again = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
    assert again["ok"] is True
    assert again["session_id"] == prepared["session_id"]
    assert again["reused"] is True
    assert again["state"] == STATE_COMPLETE


def _live_document(prepared: dict) -> dict:
    chunk = prepared["context"]["evidence"][0]["chunk_id"]
    return {
        "text": f"The paper uses hybrid linear attention. [@{chunk}]",
        "citations": [{"chunk_id": chunk}],
    }


def test_live_t2_source_edit_is_stale_and_keeps_completed_output(tmp_path: Path) -> None:
    workspace = tmp_path / "stale-ws"
    pdf = _live_pdf(tmp_path / "stale.pdf", ["Hybrid linear attention with attention residuals."])
    prepared = prepare_workflow(workspace, kind="qa", query="hybrid linear attention", pdf_paths=[pdf])
    output = tmp_path / "stale-out.md"
    completed = complete_workflow(workspace, prepared["session_id"], _live_document(prepared), output=output)
    assert completed["ok"] is True
    before = output.read_bytes()
    markdown = Path(prepared["context"]["evidence"][0]["markdown_path"])
    source = workspace / markdown
    source.write_text(source.read_text(encoding="utf-8") + "\nEdited by the user after complete.\n", encoding="utf-8")
    status = workflow_status(workspace, session_id=prepared["session_id"])
    assert status["ok"] is True
    assert status["state"] == STATE_STALE
    assert output.read_bytes() == before
    refused = complete_workflow(workspace, prepared["session_id"], _live_document(prepared), output=output)
    assert refused["ok"] is False
    assert refused["status"] == "INDEX_STALE"
    assert output.read_bytes() == before
    fresh = prepare_workflow(workspace, kind="qa", query="hybrid linear attention")
    assert fresh["ok"] is True
    assert fresh["session_id"] != prepared["session_id"]
    old = workspace / ".light-workflow" / "sessions" / prepared["session_id"]
    assert old.is_dir()


def test_session_publish_interrupt_recovers_owned_staging_and_keeps_unknown(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    unknown = workspace / WORKFLOW_DIRNAME / "staging" / "user-keep.bin"
    planted = b"unknown-bytes-must-stay\n"

    def hook(name: str) -> None:
        if name == HOOK_BEFORE_SESSION_PUBLISH:
            unknown.parent.mkdir(parents=True, exist_ok=True)
            unknown.write_bytes(planted)
            raise InjectedStop("stop before session rename")

    try:
        prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend, _hook=hook)
    except InjectedStop:
        pass
    sessions = workspace / WORKFLOW_DIRNAME / "sessions"
    assert not sessions.exists() or list(sessions.iterdir()) == []
    assert unknown.exists()
    assert unknown.read_bytes() == planted
    retried = prepare_workflow(workspace, kind="qa", query="What method is used?", _backend=backend)
    assert retried["ok"] is True
    assert retried["state"] == STATE_AWAITING
    assert unknown.exists()
    assert unknown.read_bytes() == planted


def test_intent_and_receipt_staged_interrupt_preserves_unknown_bytes(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    staging = workspace / WORKFLOW_DIRNAME / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    unknown = staging / "user-keep.bin"
    planted = b"do-not-touch\n"
    unknown.write_bytes(planted)
    leftover = staging / f".{prepared['session_id']}.completion-intent.json.tmp"
    leftover.write_bytes(b"fixed-name-unknown\n")
    leftover_bytes = leftover.read_bytes()
    output = tmp_path / "staged-intent.md"

    def stop_intent(name: str) -> None:
        if name == HOOK_AFTER_INTENT_STAGED:
            raise InjectedStop("stop after intent staged")

    try:
        complete_workflow(
            workspace,
            prepared["session_id"],
            _document(),
            output=output,
            _backend=backend,
            _hook=stop_intent,
        )
    except InjectedStop:
        pass
    session = Path(prepared["request_path"]).parent
    assert not (session / INTENT_NAME).exists()
    assert not output.exists()
    assert unknown.read_bytes() == planted
    assert leftover.read_bytes() == leftover_bytes
    status = workflow_status(workspace, session_id=prepared["session_id"], _backend=backend)
    assert status["state"] == STATE_AWAITING

    def stop_receipt(name: str) -> None:
        if name == HOOK_AFTER_RECEIPT_STAGED:
            raise InjectedStop("stop after receipt staged")

    try:
        complete_workflow(
            workspace,
            prepared["session_id"],
            _document(),
            output=output,
            _backend=backend,
            _hook=stop_receipt,
        )
    except InjectedStop:
        pass
    assert (session / INTENT_NAME).is_file()
    assert output.is_file()
    assert not (session / RECEIPT_NAME).exists()
    assert unknown.read_bytes() == planted
    assert leftover.read_bytes() == leftover_bytes
    retried = complete_workflow(workspace, prepared["session_id"], _document(), output=output, _backend=backend)
    assert retried["ok"] is True
    assert retried["state"] == STATE_COMPLETE
    assert unknown.read_bytes() == planted
    assert leftover.read_bytes() == leftover_bytes


def test_live_source_change_after_staging_before_publication(tmp_path: Path) -> None:
    from video_paper_wiki_research import light_workflow as lw

    workspace = tmp_path / "pub-ws"
    pdf = _live_pdf(tmp_path / "pub.pdf", ["quasar evidence on a native synthetic page"])
    original = lw._write_persisted
    injected = False

    def write_and_edit(path, value):
        nonlocal injected
        data = original(path, value)
        if path.name == "manifest.json" and not injected:
            injected = True
            for source in workspace.glob("papers/*/source.md"):
                text = source.read_text(encoding="utf-8")
                source.write_text(text.replace("quasar", "changed-source"), encoding="utf-8")
        return data

    lw._write_persisted = write_and_edit
    try:
        result = prepare_workflow(workspace, kind="qa", query="quasar", pdf_paths=[pdf])
    finally:
        lw._write_persisted = original
    assert injected is True
    assert result["ok"] is False
    assert result["status"] == "INDEX_STALE"
    assert result["session_id"] is None
    sessions = workspace / WORKFLOW_DIRNAME / "sessions"
    assert not sessions.exists() or list(sessions.iterdir()) == []


def test_live_t2_user_edit_and_intent_interrupt(tmp_path: Path) -> None:
    workspace = tmp_path / "rec-ws"
    pdf = _live_pdf(tmp_path / "rec.pdf", ["Hybrid linear attention with attention residuals."])
    prepared = prepare_workflow(workspace, kind="qa", query="hybrid linear attention", pdf_paths=[pdf])
    output = tmp_path / "rec-out.md"

    def stop_after_intent(name: str) -> None:
        if name == HOOK_AFTER_INTENT:
            raise InjectedStop("live intent stop")

    try:
        complete_workflow(
            workspace,
            prepared["session_id"],
            _live_document(prepared),
            output=output,
            _hook=stop_after_intent,
        )
    except InjectedStop:
        pass
    status = workflow_status(workspace, session_id=prepared["session_id"])
    assert status["state"] == STATE_AWAITING
    assert not output.exists()
    complete_workflow(workspace, prepared["session_id"], _live_document(prepared), output=output)
    edited = output.read_bytes()
    output.write_text(output.read_text(encoding="utf-8") + "\nuser rewrite\n", encoding="utf-8")
    changed = workflow_status(workspace, session_id=prepared["session_id"])
    assert changed["state"] == STATE_NEEDS_ATTENTION
    refused = complete_workflow(workspace, prepared["session_id"], _live_document(prepared), output=output)
    assert refused["ok"] is False
    assert refused["status"] in {LIGHT_SESSION_CONFLICT, LIGHT_OUTPUT_CONFLICT}
    assert output.read_bytes() != edited
    assert b"user rewrite" in output.read_bytes()
