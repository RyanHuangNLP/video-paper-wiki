from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_ingest_run_without_copy_writes_work_drafts_and_notes(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    sha256 = data["sha256"]
    paper_id = data["paper_id"]
    draft_path = Path(data["draft_path"])
    note_path = Path(data["note_path"])
    assert paper_id == sha256[:12]
    assert draft_path == tmp_path / ".work" / "drafts" / paper_id / "paper-analysis-draft.v1.json"
    assert note_path == tmp_path / ".work" / "notes" / f"{paper_id}.md"
    assert draft_path.is_file()
    assert note_path.is_file()
    assert "vault_path" not in data
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []


def test_ingest_run_existing_dir_copies_papers_and_reports_copy(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--vault", str(existing)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    paper_id = data["paper_id"]
    copied = existing / "papers" / f"{paper_id}.md"
    assert Path(data["draft_path"]).is_file()
    assert Path(data["note_path"]).is_file()
    assert data["vault_path"] == copied.as_posix()
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == Path(data["note_path"]).read_text(encoding="utf-8")
    index_md = existing / "index.md"
    assert index_md.is_file()
    index_text = index_md.read_text(encoding="utf-8")
    assert index_text.startswith("# Video Paper Wiki\n")
    assert paper_id in index_text
    assert f"papers/{paper_id}.md" in index_text
    assert not (existing / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_run_missing_pdf_blob_source_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = tmp_path / "missing.pdf"
    code = main(["ingest", "run", "--path", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.put"
    assert payload["error"]["code"] == "BLOB_SOURCE_NOT_FOUND"
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


def test_ingest_run_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    missing = tmp_path / "missing-root"
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []



def test_ingest_run_paper_id_writes_stable_draft_and_note(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    paper_id = "arxiv-2311.15127"
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--paper-id", paper_id])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    assert data["paper_id"] == paper_id
    draft_path = Path(data["draft_path"])
    note_path = Path(data["note_path"])
    assert draft_path == tmp_path / ".work" / "drafts" / paper_id / "paper-analysis-draft.v1.json"
    assert note_path == tmp_path / ".work" / "notes" / f"{paper_id}.md"
    assert draft_path.is_file()
    assert note_path.is_file()
    document = json.loads(draft_path.read_text(encoding="utf-8"))
    assert document["paper_id"] == paper_id
    assert network_attempts == []


def test_ingest_run_paper_id_copies_under_stable_id(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    paper_id = "arxiv-2311.15127"
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            paper_id,
            "--vault",
            str(existing),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    copied = existing / "papers" / f"{paper_id}.md"
    assert data["paper_id"] == paper_id
    assert data["vault_path"] == copied.as_posix()
    assert copied.is_file()
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["", "/", "..", "a/b", "a\\b", "foo/../bar"])
def test_ingest_run_illegal_paper_id(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--paper-id", paper_id])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.run"
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not blob_root.exists()
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


SEED_PAPER_IDS = (
    "arxiv-2204.03458",
    "arxiv-2311.15127",
    "arxiv-2311.17982",
    "arxiv-2209.14792",
    "arxiv-2310.12190",
    "arxiv-2401.03048",
    "arxiv-2210.02399",
    "arxiv-2212.05199",
    "arxiv-2312.14125",
    "arxiv-2401.12945",
    "arxiv-2408.06072",
    "arxiv-2412.03603",
    "arxiv-2410.05954",
    "arxiv-2307.06942",
    "arxiv-2402.19479",
    "arxiv-2405.18750",
    "arxiv-2306.02018",
    "arxiv-2312.03641",
    "arxiv-1812.01717",
)
SEED_ARXIV_IDS = (
    "2204.03458",
    "2311.15127",
    "2311.17982",
    "2209.14792",
    "2310.12190",
    "2401.03048",
    "2210.02399",
    "2212.05199",
    "2312.14125",
    "2401.12945",
    "2408.06072",
    "2412.03603",
    "2410.05954",
    "2307.06942",
    "2402.19479",
    "2405.18750",
    "2306.02018",
    "2312.03641",
    "1812.01717",
)


def _copy_tiny(dest: Path) -> None:
    dest.write_bytes(TINY_PDF.read_bytes())


def _prepare_run_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))


def test_ingest_run_pdf_dir_nineteen_paper_id_files(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    for paper_id in SEED_PAPER_IDS:
        _copy_tiny(pdf_dir / f"{paper_id}.pdf")
    code = main(["ingest", "run", "--pdf-dir", str(pdf_dir)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.run"
    data = payload["data"]
    assert [paper["paper_id"] for paper in data["papers"]] == list(SEED_PAPER_IDS)
    assert data["skipped"] == []
    for paper_id in SEED_PAPER_IDS:
        assert (tmp_path / ".work" / "notes" / f"{paper_id}.md").is_file()
        paper = next(item for item in data["papers"] if item["paper_id"] == paper_id)
        assert Path(paper["draft_path"]).is_file()
        assert Path(paper["note_path"]).is_file()
        assert "sha256" in paper
    assert network_attempts == []


def test_ingest_run_pdf_dir_matches_arxiv_id_filename(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    _copy_tiny(pdf_dir / "2311.15127.pdf")
    code = main(["ingest", "run", "--pdf-dir", str(pdf_dir)])
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    assert [paper["paper_id"] for paper in data["papers"]] == ["arxiv-2311.15127"]
    skipped_ids = [row["paper_id"] for row in data["skipped"]]
    assert skipped_ids == [
        paper_id for paper_id in SEED_PAPER_IDS if paper_id != "arxiv-2311.15127"
    ]
    assert (tmp_path / ".work" / "notes" / "arxiv-2311.15127.md").is_file()
    assert network_attempts == []


def test_ingest_run_pdf_dir_empty_dir_blob_source_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    code = main(["ingest", "run", "--pdf-dir", str(pdf_dir)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.run"
    assert payload["error"]["code"] == "BLOB_SOURCE_NOT_FOUND"
    skipped = payload["error"]["details"]["skipped"]
    assert len(skipped) == 19
    assert [row["paper_id"] for row in skipped] == list(SEED_PAPER_IDS)
    assert [row["arxiv_id"] for row in skipped] == list(SEED_ARXIV_IDS)
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


def test_ingest_run_pdf_dir_missing_dir_exit_2_no_network(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    missing = tmp_path / "missing-pdfs"
    code = main(["ingest", "run", "--pdf-dir", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BLOB_SOURCE_NOT_FOUND"
    assert not missing.exists()
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


def test_ingest_run_neither_path_nor_pdf_dir_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    code = main(["ingest", "run"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.run"
    assert payload["error"]["code"] == "USAGE"
    assert "ingest.run requires --path or --pdf-dir" in payload["error"]["message"]
    assert network_attempts == []


def test_ingest_run_path_and_pdf_dir_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    code = main(
        ["ingest", "run", "--path", str(TINY_PDF), "--pdf-dir", str(pdf_dir)]
    )
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "ingest.run"
    assert payload["error"]["code"] == "USAGE"
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


def test_ingest_run_pdf_dir_partial_one_of_nineteen(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    _copy_tiny(pdf_dir / "arxiv-2311.15127.pdf")
    code = main(["ingest", "run", "--pdf-dir", str(pdf_dir)])
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    assert [paper["paper_id"] for paper in data["papers"]] == ["arxiv-2311.15127"]
    assert len(data["skipped"]) == 18
    assert {row["paper_id"] for row in data["skipped"]} == {
        paper_id for paper_id in SEED_PAPER_IDS if paper_id != "arxiv-2311.15127"
    }
    assert (tmp_path / ".work" / "notes" / "arxiv-2311.15127.md").is_file()
    for paper_id in SEED_PAPER_IDS:
        if paper_id == "arxiv-2311.15127":
            continue
        assert not (tmp_path / ".work" / "notes" / f"{paper_id}.md").exists()
    assert network_attempts == []


def test_ingest_run_pdf_dir_existing_dir_copies_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare_run_env(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    for paper_id in SEED_PAPER_IDS:
        _copy_tiny(pdf_dir / f"{paper_id}.pdf")
    existing = tmp_path / "obsidian-root"
    existing.mkdir()
    code = main(
        ["ingest", "run", "--pdf-dir", str(pdf_dir), "--vault", str(existing)]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    assert data["skipped"] == []
    assert [paper["paper_id"] for paper in data["papers"]] == list(SEED_PAPER_IDS)
    for paper in data["papers"]:
        paper_id = paper["paper_id"]
        copied = existing / "papers" / f"{paper_id}.md"
        assert paper["vault_path"] == copied.as_posix()
        assert copied.is_file()
        assert copied.read_text(encoding="utf-8") == Path(paper["note_path"]).read_text(
            encoding="utf-8"
        )
        assert f"papers/{paper_id}.md" in (existing / "index.md").read_text(encoding="utf-8")
        assert paper_id in (existing / "index.md").read_text(encoding="utf-8")
    assert (existing / "index.md").is_file()
    assert (existing / "index.md").read_text(encoding="utf-8").startswith("# Video Paper Wiki\n")
    assert not (existing / "wiki" / "index.md").exists()
    assert network_attempts == []



def test_ingest_run_two_papers_keeps_both_index_lines(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            "x",
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    capsys.readouterr()
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            "y",
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert "x" in index_text
    assert "papers/x.md" in index_text
    assert "y" in index_text
    assert "papers/y.md" in index_text
    assert index_text.count("](papers/") >= 2
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_run_without_notes_root_does_not_write_index(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    code = main(["ingest", "run", "--path", str(TINY_PDF), "--paper-id", "x"])
    assert code == 0
    capsys.readouterr()
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []
