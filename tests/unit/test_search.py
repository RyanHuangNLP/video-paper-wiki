from __future__ import annotations

from pathlib import Path

from tests.support import make_checkout
from tests.security._projection_scope_policy import assert_projection_source_scope
from video_paper_wiki.cli import main
from video_paper_wiki.notes.doctor import scan_doctor
from video_paper_wiki.notes.grep import scan_matches
from video_paper_wiki.notes.list import scan_list
from video_paper_wiki.notes.section import list_headings, read_paper_text, section_text
from video_paper_wiki.notes.show import load_paper
from video_paper_wiki.notes.stat import scan_stat

ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = ROOT / "src" / "video_paper_wiki" / "commands"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_grep_hits_papers_and_wiki_case_insensitive(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "a.md", "Hello Video paper\nsecond line\n")
    _write(notes / "wiki" / "t.md", "a video diffusion page\n")
    _write(notes / "wiki" / "index.md", "Video must not appear\n")
    _write(notes / "index.md", "Video at root must not appear\n")
    matches = scan_matches(notes, "Video")
    assert matches == [
        {"path": "papers/a.md", "line": 1, "text": "Hello Video paper"},
        {"path": "wiki/t.md", "line": 1, "text": "a video diffusion page"},
    ]
    assert network_attempts == []


def test_grep_no_hits_is_ok_empty_matches(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "a.md", "nothing here\n")
    _write(notes / "wiki" / "t.md", "still nothing\n")
    assert scan_matches(notes, "Video") == []
    assert network_attempts == []


def test_grep_wiki_index_only_is_empty(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    _write(notes / "wiki" / "index.md", "Video lives only here\n")
    assert scan_matches(notes, "Video") == []
    assert network_attempts == []


def test_grep_skips_root_index_md(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    _write(notes / "index.md", "Video at the vault root\n")
    _write(notes / "papers" / "other.md", "unrelated\n")
    assert scan_matches(notes, "Video") == []
    assert network_attempts == []


def test_command_modules_have_no_lowercase_vault() -> None:
    for path in COMMANDS_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "vault" not in text, f"{path.name} contains lowercase vault"


def test_no_retrieval_gold_or_unreleased_bm25_engine_added() -> None:
    src = ROOT / "src" / "video_paper_wiki"
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        assert_projection_source_scope(
            path.relative_to(src).as_posix(),
            path.read_text(encoding="utf-8") if path.suffix == ".py" else None,
        )
    assert list((ROOT / "schemas").glob("*retrieval*")) == []


def test_stat_empty_existing_dir(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    assert scan_stat(notes) == {"papers": 0, "wiki_pages": 0, "years": {}}
    assert list(notes.iterdir()) == []
    assert network_attempts == []


def test_stat_undated_paper_counted_but_omitted_from_years(tmp_path, network_attempts) -> None:
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    papers = dest / "papers"
    papers.mkdir()
    (papers / "x.md").write_text("---\ntitle: Undated\npaper_id: x\n---\n", encoding="utf-8")
    data = scan_stat(dest)
    assert data["papers"] == 1
    assert "2022" not in data["years"]
    assert data["years"] == {}
    assert network_attempts == []


def test_stat_ignores_body_year_and_nested_papers(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "a.md",
        "---\ntitle: Dated\nyear: 2022\n---\n\nBody mentions year: 1999\n",
    )
    _write(notes / "papers" / "nested" / "b.md", "---\nyear: 2018\n---\n")
    _write(notes / "papers" / "c.txt", "year: 2024\n")
    _write(notes / "wiki" / "topic.md", "topic\n")
    _write(notes / "wiki" / "index.md", "index\n")
    _write(notes / "index.md", "root index\n")
    assert scan_stat(notes) == {"papers": 1, "wiki_pages": 1, "years": {"2022": 1}}
    assert network_attempts == []


def test_list_empty_vault_dir(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    assert scan_list(notes)["papers"] == []
    assert network_attempts == []


def test_list_two_handwritten_papers_year_sorted(tmp_path, network_attempts) -> None:
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
    papers = scan_list(notes)["papers"]
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
    assert network_attempts == []


def test_list_same_year_sorted_by_paper_id(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "zeta.md", "---\npaper_id: zeta\ntitle: Z\nyear: 2020\ntopics: []\n---\n")
    _write(notes / "papers" / "alpha.md", "---\npaper_id: alpha\ntitle: A\nyear: 2020\ntopics: []\n---\n")
    papers = scan_list(notes)["papers"]
    assert [item["paper_id"] for item in papers] == ["alpha", "zeta"]
    assert network_attempts == []


def test_list_undated_year_is_null_and_sorts_last(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(notes / "papers" / "undated.md", "---\npaper_id: undated\ntitle: No Year\ntopics: [misc]\n---\n")
    _write(notes / "papers" / "dated.md", "---\npaper_id: dated\ntitle: Has Year\nyear: 2022\ntopics: []\n---\n")
    papers = scan_list(notes)["papers"]
    assert [item["paper_id"] for item in papers] == ["dated", "undated"]
    assert papers[0]["year"] == 2022
    assert papers[1]["year"] is None
    assert network_attempts == []


def test_list_topic_and_year_are_and(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "diffusion.md",
        "---\npaper_id: diffusion-id\ntitle: Diffusion Paper\nyear: 2022\ntopics: [video-diffusion]\n---\n",
    )
    _write(
        notes / "papers" / "eval.md",
        "---\npaper_id: eval-id\ntitle: Evaluation Paper\nyear: 2018\ntopics: [evaluation]\n---\n",
    )
    papers = scan_list(notes, topic="video-diffusion", year=2022)["papers"]
    assert [item["paper_id"] for item in papers] == ["diffusion-id"]
    assert scan_list(notes, topic="video-diffusion", year=2018)["papers"] == []
    assert network_attempts == []


def test_show_handwritten_yaml_and_related_file_order(tmp_path, network_attempts) -> None:
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
    data = load_paper(notes, "arxiv-2408.06072")
    assert data is not None
    assert data["paper_id"] == "arxiv-2408.06072"
    assert data["title"] == "CogVideoX"
    assert data["year"] == 2024
    assert data["topics"] == ["video-diffusion", "tokenization"]
    assert data["related"] == ["arxiv-2209.14792", "arxiv-2501.00001"]
    assert network_attempts == []


def test_show_yaml_related_wins_over_markdown(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\n"
        "title: CogVideoX\n"
        "paper_id: arxiv-2408.06072\n"
        "related: [arxiv-1111.11111, arxiv-2222.22222]\n"
        "---\n\n"
        "## 相关论文\n\n"
        "[Make-A-Video](./arxiv-2209.14792.md) (2022)\n",
    )
    data = load_paper(notes, "arxiv-2408.06072")
    assert data is not None
    assert data["related"] == ["arxiv-1111.11111", "arxiv-2222.22222"]
    assert network_attempts == []


def test_show_missing_file_is_none(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    notes.mkdir()
    before = list(notes.rglob("*"))
    assert load_paper(notes, "arxiv-2408.06072") is None
    assert not (notes / "papers").exists()
    assert list(notes.rglob("*")) == before
    assert network_attempts == []


def test_section_handwritten_extracts_exact_headings(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "---\ntitle: CogVideoX\n---\n\n"
        "## 方法\n\nmethod body\n\n"
        "## 相关论文\n\nrelated body\n\n"
        "## 一句话结论\n\nconclusion body\n\n"
        "## 关联\n\nassoc body\n",
    )
    text = read_paper_text(notes, "arxiv-2408.06072")
    assert text is not None
    assert section_text(text, "方法") == "method body"
    assert section_text(text, "相关论文") == "related body"
    assert section_text(text, "一句话结论") == "conclusion body"
    assert section_text(text, "关联") == "assoc body"
    assert network_attempts == []


def test_headings_handwritten_file_order(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "arxiv-2408.06072.md",
        "## 方法\nbody\n## 局限\nlim\n## 关联\nrel\n",
    )
    text = read_paper_text(notes, "arxiv-2408.06072")
    assert list_headings(text) == ["方法", "局限", "关联"]
    assert network_attempts == []


def test_doctor_complete_yaml_is_empty_missing(tmp_path, network_attempts) -> None:
    notes = tmp_path / "notes-root"
    _write(
        notes / "papers" / "ok.md",
        "---\n"
        "title: Ok\n"
        "paper_id: ok\n"
        "year: 2022\n"
        "topics: []\n"
        "related: []\n"
        "backlinks: []\n"
        "---\n",
    )
    data = scan_doctor(notes)
    assert data["papers"] == 1
    assert data["missing_yaml"] == []
    assert network_attempts == []


def test_deleted_vault_cli_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes-root"
    notes.mkdir()
    for argv in (
        ["vault", "grep", "--vault", str(notes), "Video"],
        ["vault", "stat", "--vault", str(notes)],
        ["vault", "list", "--vault", str(notes)],
        ["vault", "show", "--vault", str(notes), "x"],
        ["vault", "doctor", "--vault", str(notes)],
    ):
        assert main(argv) == 2
    assert network_attempts == []
