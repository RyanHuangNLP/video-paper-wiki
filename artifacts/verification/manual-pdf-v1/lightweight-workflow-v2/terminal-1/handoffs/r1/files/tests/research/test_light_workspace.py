from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.light_index import INDEX_DIRNAME, INDEX_FILENAME, build_index
from video_paper_wiki_research.light_pdf import TRANSACTIONS_DIR, extract_pdf, set_inject_hook
from video_paper_wiki_research.light_workspace import inspect_workspace


def _tree_snapshot(root: Path) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    if not root.exists():
        return rows
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        base = Path(dirpath)
        for name in dirnames + filenames:
            path = base / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                rows.append((rel, "symlink:" + os.readlink(path), 0))
            elif path.is_file():
                data = path.read_bytes()
                rows.append((rel, hashlib.sha256(data).hexdigest(), len(data)))
            elif path.is_dir():
                rows.append((rel, "dir", 0))
    rows.sort()
    return rows


def _inspect_unchanged(root: Path) -> dict:
    existed = root.exists()
    before = _tree_snapshot(root)
    result = inspect_workspace(root)
    assert root.exists() is existed
    assert _tree_snapshot(root) == before
    assert result["ok"] is True
    assert result["schema"] == "video-paper-wiki.light-workspace.v1"
    assert result["workspace_root"] == str(root.resolve())
    return result


def test_missing_and_empty_workspace_are_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing-ws"
    result = _inspect_unchanged(missing)
    assert result["state"] == "empty"
    assert result["index_state"] == "missing"
    assert result["index_id"] is None
    assert result["papers"] == []
    assert result["diagnostics"] == []
    empty = tmp_path / "empty-ws"
    empty.mkdir()
    result = _inspect_unchanged(empty)
    assert result["state"] == "empty"
    assert result["index_state"] == "missing"
    assert result["papers"] == []


def test_valid_papers_need_index_then_ready(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "ready.pdf", _pdf_with_page_texts(["Inspectable body token."]))
    workspace = tmp_path / "ws"
    added = extract_pdf(pdf, workspace, title="Inspectable")
    digest = added["paper_id"].split(":", 1)[1]
    result = _inspect_unchanged(workspace)
    assert result["state"] == "needs_index"
    assert result["index_state"] == "missing"
    assert [item["paper_id"] for item in result["papers"]] == [added["paper_id"]]
    row = result["papers"][0]
    markdown = Path(added["markdown_path"]).read_bytes()
    assert row["title"] == "Inspectable"
    assert row["page_count"] == 1
    assert row["markdown_path"] == f"papers/{digest}/source.md"
    assert row["markdown_sha256"] == hashlib.sha256(markdown).hexdigest()
    assert row["metadata_stale"] is False
    built = build_index(workspace)
    ready = _inspect_unchanged(workspace)
    assert ready["state"] == "ready"
    assert ready["index_state"] == "current"
    assert ready["index_id"] == built["index_id"]


def test_stale_and_invalid_index_are_reported(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "stale.pdf", _pdf_with_page_texts(["Stale inspect body."]))
    workspace = tmp_path / "ws"
    added = extract_pdf(pdf, workspace, title="Stale")
    build_index(workspace)
    markdown_path = Path(added["markdown_path"])
    markdown_path.write_text(markdown_path.read_text(encoding="utf-8") + "\n笔记。\n", encoding="utf-8")
    stale = _inspect_unchanged(workspace)
    assert stale["state"] == "needs_index"
    assert stale["index_state"] == "stale"
    assert stale["papers"][0]["metadata_stale"] is True
    index_path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    index_path.write_text("{not json", encoding="utf-8")
    invalid = _inspect_unchanged(workspace)
    assert invalid["state"] == "needs_attention"
    assert invalid["index_state"] == "invalid"
    assert any(item["code"] == "INDEX_INVALID" for item in invalid["diagnostics"])


def test_damaged_papers_unexpected_paths_and_transactions(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "damage.pdf", _pdf_with_page_texts(["Damage inspect body."]))
    workspace = tmp_path / "ws"
    added = extract_pdf(pdf, workspace, title="Damage")
    digest = added["paper_id"].split(":", 1)[1]
    paper_dir = Path(added["markdown_path"]).parent
    (paper_dir / "source.json").unlink()
    unexpected = workspace / "papers" / "not-a-digest"
    unexpected.mkdir()
    stray = workspace / "papers" / "readme.txt"
    stray.write_text("no\n", encoding="utf-8")
    (workspace / TRANSACTIONS_DIR / "foreign.bin").write_bytes(b"xx")
    broken_anchor = workspace / "papers" / ("b" * 64)
    broken_anchor.mkdir()
    md = '<a id="page-1"></a>\n\n## PDF 第 1 页\n\nbody\n'
    (broken_anchor / "source.md").write_text(md, encoding="utf-8")
    (broken_anchor / "source.json").write_text(
        json.dumps(
            {
                "schema": "video-paper-wiki.light-paper.v1",
                "paper_id": "sha256:" + ("b" * 64),
                "title": "Broken",
                "source": {"path": "/tmp/x.pdf", "sha256": "b" * 64, "size_bytes": 1},
                "parser": {"engine": "pypdf-native-text", "version": "0"},
                "page_count": 2,
                "document": {"path": f"papers/{'b' * 64}/source.md", "sha256": hashlib.sha256(md.encode()).hexdigest()},
                "pages": [],
                "warnings": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _inspect_unchanged(workspace)
    assert result["state"] == "needs_attention"
    codes = {item["code"] for item in result["diagnostics"]}
    paths = {item["relative_path"] for item in result["diagnostics"]}
    assert "PAPER_PAIR_MISSING" in codes
    assert "PAPER_UNEXPECTED_PATH" in codes
    assert "TRANSACTION_UNKNOWN" in codes
    assert f"papers/{digest}" in paths
    assert "papers/not-a-digest" in paths
    assert "papers/readme.txt" in paths
    assert any(item["code"] in {"SOURCE_INVALID", "PAPER_UNEXPECTED_PATH"} and item["relative_path"].endswith("b" * 64) for item in result["diagnostics"])
    assert result["papers"] == []


def test_identity_mismatch_and_symlink_are_attention(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "id.pdf", _pdf_with_page_texts(["Identity inspect body."]))
    workspace = tmp_path / "ws"
    added = extract_pdf(pdf, workspace, title="Ident")
    meta_path = Path(added["metadata_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["source"]["sha256"] = "c" * 64
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    link = workspace / "papers" / "alias"
    link.symlink_to(Path(added["markdown_path"]).parent)
    result = _inspect_unchanged(workspace)
    assert result["state"] == "needs_attention"
    assert any(item["code"] == "SOURCE_INVALID" for item in result["diagnostics"])
    assert any(item["code"] == "PAPER_SYMLINK" for item in result["diagnostics"])
    assert result["papers"] == []


def test_abandoned_owned_transaction_is_reported_and_left_intact(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path / "abandon.pdf", _pdf_with_page_texts(["Abandoned staging body."]))
    workspace = tmp_path / "ws"

    def _boom(_name: str) -> None:
        raise RuntimeError("stop before publish")

    set_inject_hook("before_publish", _boom)
    with pytest.raises(RuntimeError, match="stop before publish"):
        extract_pdf(pdf, workspace, title="Abandoned")
    set_inject_hook(None)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert not (workspace / "papers" / digest).exists()
    result = _inspect_unchanged(workspace)
    assert result["state"] == "needs_attention"
    assert any(item["code"] == "TRANSACTION_ABANDONED" for item in result["diagnostics"])
    assert any(item["message"].endswith(digest) for item in result["diagnostics"] if item["code"] == "TRANSACTION_ABANDONED")
