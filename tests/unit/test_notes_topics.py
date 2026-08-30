from __future__ import annotations

from pathlib import Path

from video_paper_wiki.notes import load_topics, refresh_topic_pages
from video_paper_wiki.notes.topics import _topic_page_text
from video_paper_wiki.notes.topics import refresh_topic_pages as refresh_direct

VIDEO_DIFFUSION_BLURB = "用扩散模型生成视频，覆盖文生视频和图生视频。"
EVALUATION_BLURB = "视频生成质量与时序一致性的评测指标和基准。"


def test_load_topics_keeps_blurb_zh() -> None:
    topics = load_topics()
    assert topics is not None
    by_id = {topic["id"]: topic for topic in topics}
    assert by_id["video-diffusion"]["blurb_zh"] == VIDEO_DIFFUSION_BLURB
    assert by_id["evaluation"]["blurb_zh"] == EVALUATION_BLURB
    for topic in topics:
        assert isinstance(topic["blurb_zh"], str)


def test_refresh_skips_unknown_and_missing_papers(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    papers = root / "papers"
    papers.mkdir()
    (papers / "arxiv-2209.14792.md").write_text("# Make-A-Video\n", encoding="utf-8")
    (papers / "not-in-catalog.md").write_text("# ghost\n", encoding="utf-8")
    (root / "index.md").write_text("# Video Paper Wiki\n", encoding="utf-8")

    refresh_topic_pages(root)

    vd = (root / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert vd.startswith("# 视频扩散\n")
    assert VIDEO_DIFFUSION_BLURB in vd
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)" in vd
    assert vd.index(VIDEO_DIFFUSION_BLURB) < vd.index(
        "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    )
    assert "not-in-catalog" not in vd
    assert "arxiv-2311.15127" not in vd
    assert "Stable Video Diffusion" not in vd
    assert not (root / "wiki" / "index.md").exists()


def test_refresh_never_writes_wiki_index(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    refresh_topic_pages(root)
    assert not (root / "wiki" / "index.md").exists()
    assert (root / "wiki" / "video-diffusion.md").is_file()
    evaluation = (root / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    assert evaluation.startswith("# 评测\n")
    assert EVALUATION_BLURB in evaluation


def test_refresh_never_creates_notes_root(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    refresh_topic_pages(missing)
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []
    assert refresh_direct is refresh_topic_pages
    topics = load_topics()
    assert topics is not None
    assert [topic["id"] for topic in topics][0] == "video-diffusion"


def test_refresh_skips_unknown_paper_id_even_if_note_exists(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    papers = root / "papers"
    papers.mkdir()
    (papers / "ghost.md").write_text("# ghost\n", encoding="utf-8")
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    (root / "index.md").write_text("# Video Paper Wiki\n", encoding="utf-8")

    monkeypatch.setattr(
        "video_paper_wiki.notes.topics.load_topics",
        lambda: [
            {
                "id": "video-diffusion",
                "heading_zh": "视频扩散",
                "paper_ids": ["ghost", "arxiv-2209.14792"],
            }
        ],
    )
    refresh_direct(root)
    text = (root / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)" in text
    assert "ghost" not in text
    assert not (root / "wiki" / "index.md").exists()


def test_topic_page_empty_blurb_keeps_blank_then_links(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    text = _topic_page_text(
        "视频扩散",
        ["arxiv-2209.14792"],
        root,
        "",
    )
    assert text == "# 视频扩散\n\n[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)\n"


def test_load_topics_missing_blurb_is_empty_string(tmp_path: Path, monkeypatch) -> None:
    topics_path = tmp_path / "docs" / "seed" / "engine-mvp-topics.json"
    topics_path.parent.mkdir(parents=True)
    topics_path.write_text(
        '{"topics":[{"id":"video-diffusion","heading_zh":"视频扩散","paper_ids":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "video_paper_wiki.notes.topics._resolve_topics_path",
        lambda: topics_path,
    )
    topics = load_topics()
    assert topics is not None
    assert topics[0]["blurb_zh"] == ""


def test_topic_page_omits_year_when_unparseable(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "x.md").write_text("# undated\n", encoding="utf-8")
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    monkeypatch.setattr(
        "video_paper_wiki.notes.topics.catalog_title_for_paper_id",
        lambda paper_id: {
            "x": "Undated Paper",
            "arxiv-2209.14792": "Make-A-Video",
        }.get(paper_id),
    )
    text = _topic_page_text(
        "评测",
        ["x", "arxiv-2209.14792"],
        root,
        EVALUATION_BLURB,
    )
    undated = "[Undated Paper](../papers/x.md)"
    dated = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    assert text == f"# 评测\n\n{EVALUATION_BLURB}\n\n{dated}\n{undated}\n"
    assert undated in text
    assert f"{undated} (" not in text
    assert " (20" not in text.splitlines()[5]
    assert text.splitlines()[5].endswith(".md)")
    assert text.index(dated) < text.index(undated)


def test_topic_page_sorts_renderable_ids_by_year_not_input_order(
    tmp_path: Path,
) -> None:
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "arxiv-2408.06072.md").write_text("# cog\n", encoding="utf-8")
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    text = _topic_page_text(
        "视频扩散",
        ["arxiv-2408.06072", "arxiv-2209.14792"],
        root,
    )
    mav = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    cog = "[CogVideoX](../papers/arxiv-2408.06072.md) (2024)"
    assert text == f"# 视频扩散\n\n{mav}\n{cog}\n"
    assert text.index(mav) < text.index(cog)


def test_topic_page_reuses_paper_index_year(tmp_path: Path, monkeypatch) -> None:
    seen: list[str] = []

    def fake_year(paper_id: str):
        seen.append(paper_id)
        return 2099

    monkeypatch.setattr(
        "video_paper_wiki.notes.index.paper_index_year",
        fake_year,
    )
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    text = _topic_page_text("视频扩散", ["arxiv-2209.14792"], root, "")
    assert text == "# 视频扩散\n\n[Make-A-Video](../papers/arxiv-2209.14792.md) (2099)\n"
    assert seen == ["arxiv-2209.14792", "arxiv-2209.14792"]


def test_topics_seed_bytes_and_video_diffusion_paper_ids_unchanged() -> None:
    import hashlib
    import json

    path = Path(__file__).resolve().parents[2] / "docs" / "seed" / "engine-mvp-topics.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "65b4f48decbf840b945723faff757642f515952ac85f03b0f8c430450574b45e"
    )
    payload = json.loads(raw.decode("utf-8"))
    video = next(topic for topic in payload["topics"] if topic["id"] == "video-diffusion")
    assert video["paper_ids"][:2] == ["arxiv-2204.03458", "arxiv-2209.14792"]


def test_command_modules_still_have_no_lowercase_vault() -> None:
    commands = Path(__file__).resolve().parents[2] / "src" / "video_paper_wiki" / "commands"
    for path in commands.glob("*.py"):
        assert "vault" not in path.read_text(encoding="utf-8"), path.name


def test_refresh_appends_related_topics_sorted_by_id(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    root.mkdir()
    papers = root / "papers"
    papers.mkdir()
    (papers / "arxiv-2209.14792.md").write_text("# Make-A-Video\n", encoding="utf-8")
    (root / "index.md").write_text("# Video Paper Wiki\n", encoding="utf-8")
    refresh_topic_pages(root)
    vd = (root / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    paper = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    assert "## 相关主题" in vd
    assert vd.index(paper) < vd.index("## 相关主题")
    assert "[评测](./evaluation.md)" in vd
    assert "[语言模型路线](./language-model.md)" in vd
    assert "[运动控制](./motion-control.md)" in vd
    assert "[视频 tokenizer](./tokenization.md)" in vd
    assert vd.index("[评测](./evaluation.md)") < vd.index(
        "[语言模型路线](./language-model.md)"
    )
    assert vd.index("[语言模型路线](./language-model.md)") < vd.index(
        "[运动控制](./motion-control.md)"
    )
    assert vd.index("[运动控制](./motion-control.md)") < vd.index(
        "[视频 tokenizer](./tokenization.md)"
    )
    assert " (20" not in vd.split("## 相关主题", 1)[1]
    data = (root / "wiki" / "data.md").read_text(encoding="utf-8")
    assert data.endswith("## 相关主题\n[评测](./evaluation.md)\n")
    assert not (root / "wiki" / "index.md").exists()
    paper_note = (papers / "arxiv-2209.14792.md").read_text(encoding="utf-8")
    assert paper_note == "# Make-A-Video\n"


def test_topic_page_omits_related_heading_without_topic_id(tmp_path: Path) -> None:
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    text = _topic_page_text("视频扩散", ["arxiv-2209.14792"], root, "")
    assert text == "# 视频扩散\n\n[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)\n"
    assert "## 相关主题" not in text


def test_topic_page_omits_related_heading_when_graph_missing(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "notes-root"
    papers = root / "papers"
    papers.mkdir(parents=True)
    (papers / "arxiv-2209.14792.md").write_text("# mav\n", encoding="utf-8")
    monkeypatch.setattr(
        "video_paper_wiki.notes.topics.load_topic_related",
        lambda: None,
    )
    text = _topic_page_text(
        "视频扩散",
        ["arxiv-2209.14792"],
        root,
        "",
        "video-diffusion",
    )
    assert "## 相关主题" not in text
    assert text == "# 视频扩散\n\n[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)\n"
