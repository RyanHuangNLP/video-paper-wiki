from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
COMMANDS_DIR = ROOT / "src" / "video_paper_wiki" / "commands"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_grep_hits_papers_and_wiki_case_insensitive(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "a.md", "Hello Video paper\nsecond line\n")
    _write(notes / "wiki" / "t.md", "a video diffusion page\n")
    _write(notes / "wiki" / "index.md", "Video must not appear\n")
    _write(notes / "index.md", "Video at root must not appear\n")
    code = main(["vault", "grep", "--vault", str(notes), "Video"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.grep"
    matches = payload["data"]["matches"]
    assert matches == [
        {"path": "papers/a.md", "line": 1, "text": "Hello Video paper"},
        {"path": "wiki/t.md", "line": 1, "text": "a video diffusion page"},
    ]
    assert network_attempts == []


def test_grep_no_hits_is_ok_empty_matches(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "a.md", "nothing here\n")
    _write(notes / "wiki" / "t.md", "still nothing\n")
    code = main(["vault", "grep", "--vault", str(notes), "Video"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.grep"
    assert payload["data"]["matches"] == []
    assert network_attempts == []


def test_grep_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "grep", "--vault", str(missing), "Video"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.grep"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_grep_wiki_index_only_is_empty(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    _write(notes / "wiki" / "index.md", "Video lives only here\n")
    code = main(["vault", "grep", "--vault", str(notes), "Video"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["data"]["matches"] == []
    assert network_attempts == []


def test_grep_skips_root_index_md(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    _write(notes / "index.md", "Video at the vault root\n")
    _write(notes / "papers" / "other.md", "unrelated\n")
    code = main(["vault", "grep", "--vault", str(notes), "Video"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["data"]["matches"] == []
    assert network_attempts == []


def test_grep_empty_query_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "grep", "--vault", str(notes), ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.grep"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_grep_missing_query_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "grep", "--vault", str(notes)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_grep_after_ingest_finds_make_a_video(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(
        [
            "ingest",
            "run",
            "--path",
            str(TINY_PDF),
            "--paper-id",
            "arxiv-2209.14792",
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    capsys.readouterr()
    code = main(["vault", "grep", "--vault", str(dest), "Make-A-Video"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.grep"
    matches = payload["data"]["matches"]
    paths = {item["path"] for item in matches}
    assert "papers/arxiv-2209.14792.md" in paths
    assert all(item["path"] != "wiki/index.md" for item in matches)
    assert all(item["path"] != "index.md" for item in matches)
    assert all("Make-A-Video" in item["text"] or "make-a-video" in item["text"].casefold() for item in matches)
    assert matches == sorted(matches, key=lambda item: (item["path"], item["line"]))
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_command_modules_have_no_lowercase_vault() -> None:
    for path in COMMANDS_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "vault" not in text, f"{path.name} contains lowercase vault"


def test_no_retrieval_gold_or_bm25_added() -> None:
    tracked_markers = (
        "retrieval-gold",
        "retrieval_gold",
        "bm25",
    )
    src = ROOT / "src" / "video_paper_wiki"
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        assert "retrieval-gold" not in name
        assert "bm25" not in name
        if path.suffix == ".py":
            text = path.read_text(encoding="utf-8").lower()
            for marker in tracked_markers:
                assert marker not in text, f"{path} contains {marker}"
    assert list((ROOT / "schemas").glob("*retrieval*")) == []
