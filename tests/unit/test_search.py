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



def test_stat_empty_existing_dir(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "stat", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.stat"
    assert payload["data"] == {"papers": 0, "wiki_pages": 0, "years": {}}
    assert list(notes.iterdir()) == []
    assert network_attempts == []


def test_stat_after_ingest_make_a_video(
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
    code = main(["vault", "stat", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.stat"
    data = payload["data"]
    assert data["papers"] >= 1
    assert data["wiki_pages"] == 6
    assert data["years"]["2022"] >= 1
    assert list(data["years"]) == sorted(data["years"], key=int)
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_stat_two_catalog_years_and_planted_wiki_index(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    for paper_id in ("arxiv-1812.01717", "arxiv-2408.06072"):
        code = main(
            [
                "ingest",
                "run",
                "--path",
                str(TINY_PDF),
                "--paper-id",
                paper_id,
                "--vault",
                str(dest),
            ]
        )
        assert code == 0
        capsys.readouterr()
    planted = dest / "wiki" / "index.md"
    planted.write_text("junk year: 1999\n", encoding="utf-8")
    code = main(["vault", "stat", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["papers"] == 2
    assert data["wiki_pages"] == 6
    assert data["years"]["2018"] >= 1
    assert data["years"]["2024"] >= 1
    assert list(data["years"]) == ["2018", "2024"]
    assert planted.is_file()
    assert network_attempts == []


def test_stat_undated_paper_counted_but_omitted_from_years(
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
            "x",
            "--vault",
            str(dest),
        ]
    )
    assert code == 0
    capsys.readouterr()
    code = main(["vault", "stat", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["papers"] == 1
    assert "2022" not in data["years"]
    assert data["years"] == {}
    assert network_attempts == []


def test_stat_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "stat", "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.stat"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_stat_ignores_body_year_and_nested_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "a.md",
        "---\ntitle: Dated\nyear: 2022\n---\n\nBody mentions year: 1999\n",
    )
    _write(
        notes / "papers" / "nested" / "b.md",
        "---\nyear: 2018\n---\n",
    )
    _write(notes / "papers" / "c.txt", "year: 2024\n")
    _write(notes / "wiki" / "topic.md", "topic\n")
    _write(notes / "wiki" / "index.md", "index\n")
    _write(notes / "index.md", "root index\n")
    code = main(["vault", "stat", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["data"] == {
        "papers": 1,
        "wiki_pages": 1,
        "years": {"2022": 1},
    }
    assert network_attempts == []


def test_list_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "list", "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.list"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_list_empty_vault_dir(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    assert payload["data"]["papers"] == []
    assert network_attempts == []


def test_list_empty_papers_dir(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    (notes / "papers").mkdir(parents=True)
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["data"]["papers"] == []
    assert network_attempts == []


def test_list_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["vault", "list"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_list_two_handwritten_papers_year_sorted(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "newer.md",
        "---\n"
        "paper_id: newer-id\n"
        "title: Newer Paper\n"
        "year: 2024\n"
        "topics: [gamma]\n"
        "---\n\n"
        "Body mentions year: 1999 and topics: [ignore]\n",
    )
    _write(
        notes / "papers" / "older.md",
        "---\n"
        "paper_id: older-id\n"
        "title: Older Paper\n"
        "year: 2018\n"
        "topics: [alpha, beta]\n"
        "---\n\n"
        "Body year: 2024\n",
    )
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    papers = payload["data"]["papers"]
    assert papers == [
        {
            "paper_id": "older-id",
            "title": "Older Paper",
            "year": 2018,
            "topics": ["alpha", "beta"],
        },
        {
            "paper_id": "newer-id",
            "title": "Newer Paper",
            "year": 2024,
            "topics": ["gamma"],
        },
    ]
    assert isinstance(papers[0]["year"], int)
    assert isinstance(papers[1]["year"], int)
    assert not isinstance(papers[0]["year"], str)
    assert isinstance(papers[0]["topics"], list)
    assert network_attempts == []


def test_list_same_year_sorted_by_paper_id(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "zeta.md",
        "---\npaper_id: zeta\ntitle: Z\nyear: 2020\ntopics: []\n---\n",
    )
    _write(
        notes / "papers" / "alpha.md",
        "---\npaper_id: alpha\ntitle: A\nyear: 2020\ntopics: []\n---\n",
    )
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["alpha", "zeta"]
    assert papers[0]["year"] == papers[1]["year"] == 2020
    assert isinstance(papers[0]["year"], int)
    assert network_attempts == []


def test_list_undated_year_is_null_and_sorts_last(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "undated.md",
        "---\npaper_id: undated\ntitle: No Year\ntopics: [misc]\n---\n",
    )
    _write(
        notes / "papers" / "dated.md",
        "---\npaper_id: dated\ntitle: Has Year\nyear: 2022\ntopics: []\n---\n",
    )
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["dated", "undated"]
    assert papers[0]["year"] == 2022
    assert isinstance(papers[0]["year"], int)
    assert papers[1]["year"] is None
    assert network_attempts == []


def test_list_after_ingest_make_a_video_then_cogvideox(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    for paper_id in ("arxiv-2209.14792", "arxiv-2408.06072"):
        code = main(
            [
                "ingest",
                "run",
                "--path",
                str(TINY_PDF),
                "--paper-id",
                paper_id,
                "--vault",
                str(dest),
            ]
        )
        assert code == 0
        capsys.readouterr()
    code = main(["vault", "list", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    papers = payload["data"]["papers"]
    assert [item["paper_id"] for item in papers] == [
        "arxiv-2209.14792",
        "arxiv-2408.06072",
    ]
    assert papers[0]["title"] == "Make-A-Video"
    assert papers[1]["title"] == "CogVideoX"
    assert papers[0]["year"] == 2022
    assert papers[1]["year"] == 2024
    assert isinstance(papers[0]["year"], int)
    assert isinstance(papers[1]["year"], int)
    assert not isinstance(papers[0]["year"], str)
    assert "video-diffusion" in papers[0]["topics"]
    assert "video-diffusion" in papers[1]["topics"]
    assert isinstance(papers[0]["topics"], list)
    assert network_attempts == []


def test_list_ignores_nested_papers_and_wiki(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "keep.md",
        "---\npaper_id: keep\ntitle: Keep\nyear: 2021\ntopics: [ok]\n---\n",
    )
    _write(
        notes / "papers" / "nested" / "x.md",
        "---\npaper_id: nested\ntitle: Nested\nyear: 2018\ntopics: [no]\n---\n",
    )
    _write(
        notes / "wiki" / "topic.md",
        "---\npaper_id: wiki\ntitle: Wiki\nyear: 2019\ntopics: [no]\n---\n",
    )
    _write(notes / "wiki" / "index.md", "wiki index\n")
    _write(notes / "index.md", "root index\n")
    code = main(["vault", "list", "--vault", str(notes)])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert papers == [
        {
            "paper_id": "keep",
            "title": "Keep",
            "year": 2021,
            "topics": ["ok"],
        }
    ]
    assert network_attempts == []


def test_list_topic_filters_handwritten_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\n"
        "paper_id: diffusion-id\n"
        "title: Diffusion Paper\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "---\n",
    )
    _write(
        notes / "papers" / "eval.md",
        "---\n"
        "paper_id: eval-id\n"
        "title: Evaluation Paper\n"
        "year: 2018\n"
        "topics: [evaluation]\n"
        "---\n",
    )
    code = main(["vault", "list", "--vault", str(notes), "--topic", "video-diffusion"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    papers = payload["data"]["papers"]
    assert papers == [
        {
            "paper_id": "diffusion-id",
            "title": "Diffusion Paper",
            "year": 2022,
            "topics": ["video-diffusion"],
        }
    ]
    assert isinstance(papers[0]["year"], int)
    code = main(["vault", "list", "--vault", str(notes), "--topic", "evaluation"])
    assert code == 0
    payload = _stdout_json(capsys)
    papers = payload["data"]["papers"]
    assert papers == [
        {
            "paper_id": "eval-id",
            "title": "Evaluation Paper",
            "year": 2018,
            "topics": ["evaluation"],
        }
    ]
    assert isinstance(papers[0]["year"], int)
    assert network_attempts == []


def test_list_topic_missing_is_empty_ok(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\n"
        "paper_id: diffusion-id\n"
        "title: Diffusion Paper\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "---\n",
    )
    code = main(["vault", "list", "--vault", str(notes), "--topic", "missing-topic"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    assert payload["data"]["papers"] == []
    assert network_attempts == []


def test_list_empty_topic_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "list", "--vault", str(notes), "--topic", ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.list"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_list_after_ingest_filter_by_topic(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    for paper_id in ("arxiv-2209.14792", "arxiv-1812.01717"):
        code = main(
            [
                "ingest",
                "run",
                "--path",
                str(TINY_PDF),
                "--paper-id",
                paper_id,
                "--vault",
                str(dest),
            ]
        )
        assert code == 0
        capsys.readouterr()
    code = main(["vault", "list", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    papers = payload["data"]["papers"]
    assert [item["paper_id"] for item in papers] == [
        "arxiv-1812.01717",
        "arxiv-2209.14792",
    ]
    assert papers[0]["title"] == "Towards Accurate Generative Models of Video"
    assert papers[1]["title"] == "Make-A-Video"
    assert papers[0]["year"] == 2018
    assert papers[1]["year"] == 2022
    assert isinstance(papers[0]["year"], int)
    assert isinstance(papers[1]["year"], int)
    assert not isinstance(papers[0]["year"], str)
    assert "evaluation" in papers[0]["topics"]
    assert "video-diffusion" in papers[1]["topics"]
    code = main(["vault", "list", "--vault", str(dest), "--topic", "video-diffusion"])
    assert code == 0
    filtered = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in filtered] == ["arxiv-2209.14792"]
    assert filtered[0]["title"] == "Make-A-Video"
    assert filtered[0]["year"] == 2022
    assert isinstance(filtered[0]["year"], int)
    assert "video-diffusion" in filtered[0]["topics"]
    assert all(item["paper_id"] != "arxiv-1812.01717" for item in filtered)
    code = main(["vault", "list", "--vault", str(dest), "--topic", "evaluation"])
    assert code == 0
    filtered = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in filtered] == ["arxiv-1812.01717"]
    assert filtered[0]["title"] == "Towards Accurate Generative Models of Video"
    assert filtered[0]["year"] == 2018
    assert isinstance(filtered[0]["year"], int)
    assert "evaluation" in filtered[0]["topics"]
    assert all(item["paper_id"] != "arxiv-2209.14792" for item in filtered)
    assert network_attempts == []


def test_list_year_filters_handwritten_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\n"
        "paper_id: diffusion-id\n"
        "title: Diffusion Paper\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "---\n",
    )
    _write(
        notes / "papers" / "eval.md",
        "---\n"
        "paper_id: eval-id\n"
        "title: Evaluation Paper\n"
        "year: 2018\n"
        "topics: [evaluation]\n"
        "---\n",
    )
    code = main(["vault", "list", "--vault", str(notes), "--year", "2022"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    papers = payload["data"]["papers"]
    assert papers == [
        {
            "paper_id": "diffusion-id",
            "title": "Diffusion Paper",
            "year": 2022,
            "topics": ["video-diffusion"],
        }
    ]
    assert isinstance(papers[0]["year"], int)
    code = main(["vault", "list", "--vault", str(notes), "--year", "2018"])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert papers == [
        {
            "paper_id": "eval-id",
            "title": "Evaluation Paper",
            "year": 2018,
            "topics": ["evaluation"],
        }
    ]
    assert isinstance(papers[0]["year"], int)
    assert network_attempts == []


def test_list_year_missing_is_empty_ok(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\n"
        "paper_id: diffusion-id\n"
        "title: Diffusion Paper\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "---\n",
    )
    code = main(["vault", "list", "--vault", str(notes), "--year", "2024"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.list"
    assert payload["data"]["papers"] == []
    assert network_attempts == []


def test_list_invalid_year_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    for value in ("", "abc", "2024.0", "0", "-1"):
        code = main(["vault", "list", "--vault", str(notes), "--year", value])
        assert code == 2
        payload = _stdout_json(capsys)
        assert payload["ok"] is False
        assert payload["command"] == "vault.list"
        assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_list_topic_and_year_are_and(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\n"
        "paper_id: diffusion-id\n"
        "title: Diffusion Paper\n"
        "year: 2022\n"
        "topics: [video-diffusion]\n"
        "---\n",
    )
    _write(
        notes / "papers" / "eval.md",
        "---\n"
        "paper_id: eval-id\n"
        "title: Evaluation Paper\n"
        "year: 2018\n"
        "topics: [evaluation]\n"
        "---\n",
    )
    code = main(
        [
            "vault",
            "list",
            "--vault",
            str(notes),
            "--topic",
            "video-diffusion",
            "--year",
            "2022",
        ]
    )
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["diffusion-id"]
    code = main(
        [
            "vault",
            "list",
            "--vault",
            str(notes),
            "--topic",
            "video-diffusion",
            "--year",
            "2018",
        ]
    )
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert papers == []
    assert network_attempts == []


def test_list_after_ingest_filter_by_year(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    for paper_id in ("arxiv-2209.14792", "arxiv-1812.01717"):
        code = main(
            [
                "ingest",
                "run",
                "--path",
                str(TINY_PDF),
                "--paper-id",
                paper_id,
                "--vault",
                str(dest),
            ]
        )
        assert code == 0
        capsys.readouterr()
    code = main(["vault", "list", "--vault", str(dest), "--year", "2022"])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["arxiv-2209.14792"]
    assert papers[0]["year"] == 2022
    assert isinstance(papers[0]["year"], int)
    code = main(["vault", "list", "--vault", str(dest), "--year", "2018"])
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["arxiv-1812.01717"]
    assert papers[0]["year"] == 2018
    assert isinstance(papers[0]["year"], int)
    code = main(
        [
            "vault",
            "list",
            "--vault",
            str(dest),
            "--topic",
            "video-diffusion",
            "--year",
            "2022",
        ]
    )
    assert code == 0
    papers = _stdout_json(capsys)["data"]["papers"]
    assert [item["paper_id"] for item in papers] == ["arxiv-2209.14792"]
    assert network_attempts == []


def test_show_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "show", "--vault", str(missing), "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.show"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_show_empty_paper_id_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "show", "--vault", str(notes), ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.show"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_show_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["vault", "show", "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_show_missing_file_does_not_create_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.show"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert not (notes / "papers").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_show_handwritten_yaml_and_related_file_order(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "arxiv_id: 2408.06072\n"
        "year: 2024\n"
        "topics: [video-diffusion, tokenization]\n"
        "---\n\n"
        "Body mentions year: 1999\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n"
        "[Later Paper](./arxiv-2501.00001.md) (2025)\n"
        "\n## 其他\n\n"
        "[Ignored](./arxiv-ignored.md)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.show"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2408.06072"
    assert data["title"] == "CogVideoX"
    assert data["arxiv_id"] == "2408.06072"
    assert data["year"] == 2024
    assert isinstance(data["year"], int)
    assert not isinstance(data["year"], str)
    assert data["topics"] == ["video-diffusion", "tokenization"]
    assert data["related"] == ["arxiv-2209.14792", "arxiv-2501.00001"]
    assert data["backlinks"] == []
    assert "arxiv_id" in data
    assert "related" in data
    assert "backlinks" in data
    assert network_attempts == []


def test_show_yaml_related_wins_over_markdown(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "arxiv_id: 2408.06072\n"
        "year: 2024\n"
        "topics: [video-diffusion]\n"
        "related: [arxiv-1111.11111, arxiv-2222.22222]\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["related"] == ["arxiv-1111.11111", "arxiv-2222.22222"]
    assert data["backlinks"] == []
    assert network_attempts == []


def test_show_yaml_empty_related_skips_markdown(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "year: 2024\n"
        "topics: []\n"
        "related: []\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["related"] == []
    assert network_attempts == []


def test_show_no_related_section_is_empty_list(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "lonely.md",
        "---\n"
        "title: Lonely\n"
        "paper_id: lonely\n"
        "year: 2021\n"
        "topics: []\n"
        "---\n\n"
        "No related heading here.\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "lonely"])
    assert code == 0
    payload = _stdout_json(capsys)
    data = payload["data"]
    assert data["related"] == []
    assert data["backlinks"] == []
    assert data["arxiv_id"] == ""
    assert data["year"] == 2021
    assert isinstance(data["year"], int)
    assert network_attempts == []


def test_show_after_ingest_make_a_video(
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
    note = dest / "papers" / "arxiv-2209.14792.md"
    original = note.read_text(encoding="utf-8")
    code = main(["vault", "show", "--vault", str(dest), "arxiv-2209.14792"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.show"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2209.14792"
    assert data["title"] == "Make-A-Video"
    assert data["year"] == 2022
    assert isinstance(data["year"], int)
    assert data["arxiv_id"] == "2209.14792"
    assert "video-diffusion" in data["topics"]
    assert isinstance(data["related"], list)
    assert "arxiv-2209.14792" not in data["related"]
    from video_paper_wiki.notes.links import backlink_catalog_ids
    assert data["backlinks"] == backlink_catalog_ids("arxiv-2209.14792")
    assert note.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_show_ignores_nested_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "nested" / "x.md",
        "---\n"
        "paper_id: nested\n"
        "title: Nested\n"
        "year: 2018\n"
        "topics: [no]\n"
        "---\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "x"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.show"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert (notes / "papers" / "nested" / "x.md").is_file()
    assert not (notes / "papers" / "x.md").exists()
    assert network_attempts == []


def test_section_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "section", "--vault", str(missing), "arxiv-2408.06072", "方法"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_section_empty_paper_id_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "section", "--vault", str(notes), "", "方法"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_section_empty_heading_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_section_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["vault", "section", "arxiv-2408.06072", "方法"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_section_missing_file_does_not_create_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "方法"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert not (notes / "papers").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_section_unsafe_ids_are_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    for paper_id in ("../x", "foo/bar", "foo\\bar", ".", ".."):
        code = main(["vault", "section", "--vault", str(notes), paper_id, "方法"])
        assert code == 2
        payload = _stdout_json(capsys)
        assert payload["ok"] is False
        assert payload["command"] == "vault.section"
        assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert list(notes.rglob("*")) == before
    assert not (tmp_path / "x.md").exists()
    assert not (notes / "papers").exists()
    assert network_attempts == []


def test_section_handwritten_extracts_exact_headings(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "---\n\n"
        "## 一句话结论\n"
        "A one liner.\n"
        "## 方法\n"
        "The method body.\n"
        "still method.\n"
        "## 关联\n"
        "Frozen related section.\n"
        "## 相关论文\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    original = (notes / "papers" / "arxiv-2408.06072.md").read_text(encoding="utf-8")
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "方法"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.section"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2408.06072"
    assert data["section"] == "方法"
    assert data["text"] == "The method body.\nstill method."
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "相关论文"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["section"] == "相关论文"
    assert data["text"] == "[Make-A-Video](./arxiv-2209.14792.md) (2022)"
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "一句话结论"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["text"] == "A one liner."
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "关联"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["text"] == "Frozen related section."
    assert data["text"] != "[Make-A-Video](./arxiv-2209.14792.md) (2022)"
    assert (notes / "papers" / "arxiv-2408.06072.md").read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_section_missing_heading_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    path = notes / "papers" / "arxiv-2408.06072.md"
    _write(path, "## 方法\nThe method body.\n")
    original = path.read_text(encoding="utf-8")
    code = main(["vault", "section", "--vault", str(notes), "arxiv-2408.06072", "局限"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "SECTION_NOT_FOUND"
    assert payload["error"]["details"]["paper_id"] == "arxiv-2408.06072"
    assert payload["error"]["details"]["section"] == "局限"
    assert path.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_section_after_ingest_make_a_video(
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
    note = dest / "papers" / "arxiv-2209.14792.md"
    original = note.read_text(encoding="utf-8")
    code = main(
        ["vault", "section", "--vault", str(dest), "arxiv-2209.14792", "证据状态"]
    )
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.section"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2209.14792"
    assert data["section"] == "证据状态"
    assert isinstance(data["text"], str)
    assert data["text"]
    code = main(
        ["vault", "section", "--vault", str(dest), "arxiv-2209.14792", "相关论文"]
    )
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["section"] == "相关论文"
    assert isinstance(data["text"], str)
    assert note.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_section_ignores_nested_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "nested" / "x.md",
        "## 方法\nNested method.\n",
    )
    code = main(["vault", "section", "--vault", str(notes), "x", "方法"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.section"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert (notes / "papers" / "nested" / "x.md").is_file()
    assert not (notes / "papers" / "x.md").exists()
    assert network_attempts == []


def test_headings_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "headings", "--vault", str(missing), "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.headings"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_headings_empty_paper_id_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "headings", "--vault", str(notes), ""])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.headings"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_headings_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["vault", "headings", "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_headings_missing_file_does_not_create_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    code = main(["vault", "headings", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.headings"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert not (notes / "papers").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_headings_unsafe_ids_are_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    for paper_id in ("../x", "foo/bar", "foo\\bar", ".", ".."):
        code = main(["vault", "headings", "--vault", str(notes), paper_id])
        assert code == 2
        payload = _stdout_json(capsys)
        assert payload["ok"] is False
        assert payload["command"] == "vault.headings"
        assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert list(notes.rglob("*")) == before
    assert not (tmp_path / "x.md").exists()
    assert not (notes / "papers").exists()
    assert network_attempts == []


def test_headings_handwritten_file_order(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    path = notes / "papers" / "arxiv-2408.06072.md"
    _write(
        path,
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "---\n\n"
        "## 一句话结论\n"
        "A one liner.\n"
        "## 方法\n"
        "The method body.\n"
        "still method.\n"
        "## 关联\n"
        "Frozen related section.\n"
        "## 相关论文\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    original = path.read_text(encoding="utf-8")
    code = main(["vault", "headings", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.headings"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2408.06072"
    assert data["headings"] == ["一句话结论", "方法", "关联", "相关论文"]
    assert "text" not in data
    assert path.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_headings_none_is_empty_ok(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    path = notes / "papers" / "arxiv-2408.06072.md"
    _write(path, "just a title and no headings\n")
    original = path.read_text(encoding="utf-8")
    code = main(["vault", "headings", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.headings"
    assert payload["data"]["paper_id"] == "arxiv-2408.06072"
    assert payload["data"]["headings"] == []
    assert "text" not in payload["data"]
    assert path.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_headings_after_ingest_make_a_video(
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
    note = dest / "papers" / "arxiv-2209.14792.md"
    original = note.read_text(encoding="utf-8")
    code = main(["vault", "headings", "--vault", str(dest), "arxiv-2209.14792"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.headings"
    data = payload["data"]
    assert data["paper_id"] == "arxiv-2209.14792"
    headings = data["headings"]
    assert "证据状态" in headings
    assert "相关论文" in headings
    assert "关联" in headings
    assert headings.index("关联") < headings.index("相关论文")
    assert "text" not in data
    assert note.read_text(encoding="utf-8") == original
    assert network_attempts == []


def test_headings_ignores_nested_papers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "nested" / "x.md",
        "## 方法\nNested method.\n",
    )
    code = main(["vault", "headings", "--vault", str(notes), "x"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.headings"
    assert payload["error"]["code"] == "PAPER_NOT_FOUND"
    assert (notes / "papers" / "nested" / "x.md").is_file()
    assert not (notes / "papers" / "x.md").exists()
    assert network_attempts == []


def test_show_yaml_backlinks_used_as_is(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "arxiv_id: 2408.06072\n"
        "year: 2024\n"
        "topics: [video-diffusion]\n"
        "related: [arxiv-1111.11111]\n"
        "backlinks: [arxiv-3333.33333, arxiv-4444.44444]\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["command"] == "vault.show"
    data = payload["data"]
    assert data["related"] == ["arxiv-1111.11111"]
    assert data["backlinks"] == ["arxiv-3333.33333", "arxiv-4444.44444"]
    assert list(data) == [
        "paper_id",
        "title",
        "arxiv_id",
        "year",
        "topics",
        "related",
        "backlinks",
    ]
    assert network_attempts == []


def test_show_yaml_empty_backlinks_skips_markdown(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "year: 2024\n"
        "topics: []\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "arxiv-2408.06072"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["related"] == []
    assert data["backlinks"] == []
    assert network_attempts == []


def test_show_missing_backlinks_key_is_empty_list(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "lonely.md",
        "---\n"
        "title: Lonely\n"
        "paper_id: lonely\n"
        "year: 2021\n"
        "topics: []\n"
        "related: [arxiv-2209.14792]\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    code = main(["vault", "show", "--vault", str(notes), "lonely"])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["related"] == ["arxiv-2209.14792"]
    assert data["backlinks"] == []
    assert network_attempts == []


def test_doctor_missing_dir_refuses_and_does_not_create(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-root"
    code = main(["vault", "doctor", "--vault", str(missing)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.doctor"
    assert payload["error"]["code"] == "VAULT_NOT_FOUND"
    assert not missing.exists()
    assert network_attempts == []


def test_doctor_missing_vault_flag_is_usage(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["vault", "doctor"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "vault.doctor"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_doctor_empty_vault_dir(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    code = main(["vault", "doctor", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.doctor"
    assert payload["data"] == {"papers": 0, "wiki_pages": 0, "missing_yaml": []}
    assert list(notes.iterdir()) == []
    assert network_attempts == []


def test_doctor_complete_yaml_is_empty_missing(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "year: 2024\n"
        "topics: [video-diffusion]\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n\n"
        "body\n",
    )
    _write(notes / "wiki" / "video-diffusion.md", "topic\n")
    _write(notes / "wiki" / "index.md", "index\n")
    _write(notes / "papers" / "nested" / "x.md", "no yaml\n")
    code = main(["vault", "doctor", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["command"] == "vault.doctor"
    assert payload["data"] == {
        "papers": 1,
        "wiki_pages": 1,
        "missing_yaml": [],
    }
    assert network_attempts == []


def test_doctor_empty_values_are_not_missing(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "empty.md",
        "---\n"
        'title: ""\n'
        "paper_id:\n"
        "year: null\n"
        "topics: []\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n",
    )
    code = main(["vault", "doctor", "--vault", str(notes)])
    assert code == 0
    data = _stdout_json(capsys)["data"]
    assert data["papers"] == 1
    assert data["missing_yaml"] == []
    assert network_attempts == []


def test_doctor_reports_missing_keys_and_stays_ok(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    original_a = (
        "---\n"
        "title: Dated\n"
        "paper_id: a\n"
        "year: 2022\n"
        "topics: []\n"
        "---\n\n"
        "body\n"
    )
    original_z = "no frontmatter here\n"
    _write(notes / "papers" / "z.md", original_z)
    _write(notes / "papers" / "a.md", original_a)
    _write(
        notes / "papers" / "complete.md",
        "---\n"
        "title: Done\n"
        "paper_id: complete\n"
        "year: 2020\n"
        "topics: []\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n",
    )
    _write(notes / "wiki" / "topic.md", "topic\n")
    before = (notes / "papers" / "a.md").read_text(encoding="utf-8")
    code = main(["vault", "doctor", "--vault", str(notes)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.doctor"
    data = payload["data"]
    assert data["papers"] == 3
    assert data["wiki_pages"] == 1
    assert data["missing_yaml"] == [
        {"paper_id": "a", "fields": ["related", "backlinks"]},
        {
            "paper_id": "z",
            "fields": [
                "title",
                "paper_id",
                "year",
                "topics",
                "related",
                "backlinks",
            ],
        },
    ]
    assert (notes / "papers" / "a.md").read_text(encoding="utf-8") == before
    assert (notes / "papers" / "z.md").read_text(encoding="utf-8") == original_z
    assert network_attempts == []


def test_doctor_after_ingest_make_a_video(
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
    note = dest / "papers" / "arxiv-2209.14792.md"
    original = note.read_text(encoding="utf-8")
    code = main(["vault", "doctor", "--vault", str(dest)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "vault.doctor"
    data = payload["data"]
    assert data["papers"] >= 1
    assert data["wiki_pages"] == 6
    assert data["missing_yaml"] == []
    assert note.read_text(encoding="utf-8") == original
    assert network_attempts == []
