from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.light_index import build_index, search
from video_paper_wiki_research.light_pdf import (
    INJECT_POINTS,
    TRANSACTIONS_DIR,
    _marker_path,
    _marker_payload,
    _staging_dir,
    _write_marker,
    extract_pdf,
    lock_is_held,
    lock_path_for,
    set_inject_hook,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def child_extract() -> None:
    pdf = Path(os.environ["VPWIKI_LIGHT_PDF_PDF"])
    workspace = Path(os.environ["VPWIKI_LIGHT_PDF_WORKSPACE"])
    title = os.environ.get("VPWIKI_LIGHT_PDF_TITLE")
    result = extract_pdf(pdf, workspace, title=title or None)
    out = os.environ.get("VPWIKI_LIGHT_PDF_RESULT")
    if out:
        Path(out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _paper_regular_names(paper_dir: Path) -> set[str]:
    names: set[str] = set()
    if not paper_dir.exists():
        return names
    for item in paper_dir.iterdir():
        if item.is_symlink():
            continue
        if item.is_file():
            names.add(item.name)
    return names


def _start_child(
    *,
    pdf: Path,
    workspace: Path,
    ready: Path,
    wait: Path,
    result_path: Path,
    inject: str,
    action: str,
    title: str = "Recovery",
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SOURCE_ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "VPWIKI_LIGHT_PDF_PDF": str(pdf),
            "VPWIKI_LIGHT_PDF_WORKSPACE": str(workspace),
            "VPWIKI_LIGHT_PDF_TITLE": title,
            "VPWIKI_LIGHT_PDF_INJECT": inject,
            "VPWIKI_LIGHT_PDF_INJECT_READY": str(ready),
            "VPWIKI_LIGHT_PDF_INJECT_WAIT": str(wait),
            "VPWIKI_LIGHT_PDF_INJECT_ACTION": action,
            "VPWIKI_LIGHT_PDF_RESULT": str(result_path),
        }
    )
    return subprocess.Popen(
        [str(PYTHON), "-c", "from tests.research.test_light_pdf_recovery import child_extract; child_extract()"],
        cwd=str(SOURCE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _fifo_pair(tmp_path: Path, name: str) -> tuple[Path, Path, int]:
    ready = tmp_path / f"{name}-ready.fifo"
    wait = tmp_path / f"{name}-wait.fifo"
    os.mkfifo(ready)
    os.mkfifo(wait)
    ready_fd = os.open(ready, os.O_RDWR)
    return ready, wait, ready_fd


def _read_ready(ready_fd: int, point: str) -> None:
    chunk = os.read(ready_fd, 128)
    assert point.encode("utf-8") in chunk


def _continue(wait: Path) -> None:
    with open(wait, "w", encoding="utf-8") as handle:
        handle.write("go\n")


@pytest.fixture(autouse=True)
def _clear_hooks() -> None:
    set_inject_hook(None)
    yield
    set_inject_hook(None)


@pytest.mark.parametrize("point", INJECT_POINTS)
def test_inprocess_exception_then_retry_leaves_complete_pair(tmp_path: Path, point: str) -> None:
    pdf = _write_pdf(tmp_path / "paper.pdf", _pdf_with_page_texts(["Recoverable native text."]))
    workspace = tmp_path / "ws"

    def _boom(_name: str) -> None:
        raise RuntimeError(f"injected {_name}")

    set_inject_hook(point, _boom)
    with pytest.raises(RuntimeError, match="injected"):
        extract_pdf(pdf, workspace, title="Recovery")
    set_inject_hook(None)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    paper_dir = workspace / "papers" / digest
    if point == "after_publish":
        assert _paper_regular_names(paper_dir) == {"source.md", "source.json"}
    else:
        assert not paper_dir.exists() or _paper_regular_names(paper_dir) == set()
    retry = extract_pdf(pdf, workspace, title="Recovery")
    assert retry["ok"] is True
    assert retry["disposition"] in {"created", "recovered", "reused"}
    assert _paper_regular_names(Path(retry["markdown_path"]).parent) == {"source.md", "source.json"}
    built = build_index(workspace)
    assert built["ok"] is True
    found = search(workspace, "Recoverable native")
    assert found["ok"] is True


@pytest.mark.parametrize("point", INJECT_POINTS)
def test_child_killed_at_inject_then_parent_recovers(tmp_path: Path, point: str) -> None:
    pdf = _write_pdf(tmp_path / "kill.pdf", _pdf_with_page_texts(["Process stop body."]))
    workspace = tmp_path / "ws"
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    paper_dir = workspace / "papers" / digest
    ready, wait, ready_fd = _fifo_pair(tmp_path, point)
    result_path = tmp_path / f"{point}.json"
    child = _start_child(
        pdf=pdf,
        workspace=workspace,
        ready=ready,
        wait=wait,
        result_path=result_path,
        inject=point,
        action="continue",
    )
    try:
        _read_ready(ready_fd, point)
        if point == "after_publish":
            assert _paper_regular_names(paper_dir) == {"source.md", "source.json"}
        else:
            assert not os.path.lexists(paper_dir)
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        assert not lock_is_held(lock_path_for(workspace, digest))
        retry = extract_pdf(pdf, workspace, title="Recovery")
        assert retry["ok"] is True
        assert _paper_regular_names(Path(retry["markdown_path"]).parent) == {"source.md", "source.json"}
        if point in {"after_json_write", "before_publish"}:
            assert retry["disposition"] == "recovered"
        elif point == "after_publish":
            assert retry["disposition"] == "reused"
        else:
            assert retry["disposition"] in {"created", "recovered"}
    finally:
        os.close(ready_fd)
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_concurrent_add_busy_then_reuse_preserves_notes(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "conc.pdf", _pdf_with_page_texts(["Concurrent body token."]))
    workspace = tmp_path / "ws"
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    paper_dir = workspace / "papers" / digest
    ready, wait, ready_fd = _fifo_pair(tmp_path, "conc")
    result_path = tmp_path / "child.json"
    child = _start_child(
        pdf=pdf,
        workspace=workspace,
        ready=ready,
        wait=wait,
        result_path=result_path,
        inject="before_publish",
        action="continue",
    )
    try:
        _read_ready(ready_fd, "before_publish")
        assert not os.path.lexists(paper_dir)
        busy = extract_pdf(pdf, workspace, title="Recovery")
        assert busy["ok"] is False
        assert busy["status"] == "LIGHT_WORKSPACE_BUSY"
        assert not os.path.lexists(paper_dir)
        _continue(wait)
        assert child.wait(timeout=10) == 0
        first = json.loads(result_path.read_text(encoding="utf-8"))
        assert first["ok"] is True
        assert first["disposition"] == "created"
        assert _paper_regular_names(paper_dir) == {"source.md", "source.json"}
        note = paper_dir / "user-note.md"
        note.write_text("keep-me\n", encoding="utf-8")
        note_sha = hashlib.sha256(note.read_bytes()).hexdigest()
        md_sha = hashlib.sha256((paper_dir / "source.md").read_bytes()).hexdigest()
        ready2, wait2, ready_fd2 = _fifo_pair(tmp_path, "hold")
        holder = _start_child(
            pdf=pdf,
            workspace=workspace,
            ready=ready2,
            wait=wait2,
            result_path=tmp_path / "holder.json",
            inject="after_lock",
            action="continue",
            title="Recovery",
        )
        _read_ready(ready_fd2, "after_lock")
        second_busy = extract_pdf(pdf, workspace)
        assert second_busy["ok"] is False
        assert second_busy["status"] == "LIGHT_WORKSPACE_BUSY"
        _continue(wait2)
        assert holder.wait(timeout=10) == 0
        os.close(ready_fd2)
        reused = extract_pdf(pdf, workspace)
        assert reused["ok"] is True
        assert reused["disposition"] == "reused"
        assert hashlib.sha256(note.read_bytes()).hexdigest() == note_sha
        assert hashlib.sha256((paper_dir / "source.md").read_bytes()).hexdigest() == md_sha
        assert _paper_regular_names(paper_dir) == {"source.json", "source.md", "user-note.md"}
        built = build_index(workspace)
        assert built["ok"] is True
        found = search(workspace, "Concurrent body")
        assert found["ok"] is True
    finally:
        os.close(ready_fd)
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_unknown_transaction_and_partial_final_dir_are_preserved(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "unk.pdf", _pdf_with_page_texts(["Unknown leftover body."]))
    workspace = tmp_path / "ws"
    first = extract_pdf(pdf, workspace, title="Keep")
    digest = first["paper_id"].split(":", 1)[1]
    paper_dir = Path(first["markdown_path"]).parent
    (paper_dir / "source.json").unlink()
    leftover = workspace / TRANSACTIONS_DIR / "not-a-marker.txt"
    leftover.write_text("foreign\n", encoding="utf-8")
    staging_unknown = workspace / TRANSACTIONS_DIR / "staging" / "mystery"
    staging_unknown.mkdir(parents=True)
    (staging_unknown / "source.md").write_text("not owned\n", encoding="utf-8")
    extra_link = paper_dir / "extra-link"
    extra_link.symlink_to(paper_dir / "source.md")
    before_md = (paper_dir / "source.md").read_bytes()
    before_foreign = leftover.read_bytes()
    refused = extract_pdf(pdf, workspace, title="Keep")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert (paper_dir / "source.md").read_bytes() == before_md
    assert leftover.read_bytes() == before_foreign
    assert extra_link.is_symlink()
    assert (staging_unknown / "source.md").read_text(encoding="utf-8") == "not owned\n"
    assert not (paper_dir / "source.json").exists()


def _plant_owned_staging(workspace: Path, digest: str, markdown: str | bytes, metadata: dict | bytes) -> Path:
    token = "ownedprobe"
    staging = _staging_dir(workspace, digest, token)
    staging.mkdir(parents=True)
    md_path = staging / "source.md"
    json_path = staging / "source.json"
    if isinstance(markdown, bytes):
        md_path.write_bytes(markdown)
    else:
        md_path.write_text(markdown, encoding="utf-8")
    if isinstance(metadata, bytes):
        json_path.write_bytes(metadata)
    else:
        json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_marker(_marker_path(workspace, digest, token), _marker_payload(digest, token))
    return staging


def test_invalid_owned_staging_is_refused_before_publish(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "stage.pdf", _pdf_with_page_texts(["Owned staging body."]))
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    created = extract_pdf(pdf, tmp_path / "seed", title="Seed")
    good_md = Path(created["markdown_path"]).read_text(encoding="utf-8")
    good_meta = json.loads(Path(created["metadata_path"]).read_text(encoding="utf-8"))

    bad_meta = dict(good_meta)
    bad_meta["schema"] = "wrong"
    workspace = tmp_path / "bad-meta"
    (workspace / "papers").mkdir(parents=True)
    staging = _plant_owned_staging(workspace, digest, good_md, bad_meta)
    staging_md = (staging / "source.md").read_bytes()
    staging_json = (staging / "source.json").read_bytes()
    refused = extract_pdf(pdf, workspace, title="Seed")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    final = workspace / "papers" / digest
    assert not final.exists()
    assert (staging / "source.md").read_bytes() == staging_md
    assert (staging / "source.json").read_bytes() == staging_json

    bad_anchor_meta = dict(good_meta)
    bad_anchor_meta["page_count"] = 9
    workspace = tmp_path / "bad-anchor"
    (workspace / "papers").mkdir(parents=True)
    _plant_owned_staging(workspace, digest, good_md, bad_anchor_meta)
    refused = extract_pdf(pdf, workspace, title="Seed")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert not (workspace / "papers" / digest).exists()

    mismatch = dict(good_meta)
    mismatch["source"] = dict(good_meta["source"])
    mismatch["source"]["sha256"] = "0" * 64
    workspace = tmp_path / "bad-identity"
    (workspace / "papers").mkdir(parents=True)
    _plant_owned_staging(workspace, digest, good_md, mismatch)
    refused = extract_pdf(pdf, workspace, title="Seed")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert not (workspace / "papers" / digest).exists()

    workspace = tmp_path / "bad-utf8"
    (workspace / "papers").mkdir(parents=True)
    _plant_owned_staging(workspace, digest, b"\xff", good_meta)
    refused = extract_pdf(pdf, workspace, title="Seed")
    assert refused["ok"] is False
    assert refused["status"] == "SOURCE_INVALID"
    assert not (workspace / "papers" / digest).exists()
