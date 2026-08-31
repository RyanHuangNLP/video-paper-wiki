from __future__ import annotations

from tests.support import make_checkout, work_review, write_catalog_paper_note

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.notes import backlink_catalog_ids, paper_note_link_suffix, related_catalog_papers
from video_paper_wiki.notes.frozen import FrozenSeedMissing
from video_paper_wiki.notes.links import paper_note_link_suffix as suffix_direct
from video_paper_wiki.parse.draft_document import SECTION_SPECS
from video_paper_wiki.parse.title import catalog_title_for_paper_id

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _prepare(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))


def _ingest(_path, paper_id, dest):
    try:
        write_catalog_paper_note(dest, paper_id)
    except FrozenSeedMissing:
        return 2
    return 0


def _assert_frozen_headings(text: str) -> None:
    for _section_id, heading in SECTION_SPECS:
        assert f"## {heading}" in text
    positions = [text.index(f"## {heading}") for _section_id, heading in SECTION_SPECS]
    assert positions == sorted(positions)


def _trailer_after_related(text: str) -> str:
    marker = "## 关联"
    assert marker in text
    return text.split(marker, 1)[1]


def test_suffix_empty_when_paper_not_in_topics() -> None:
    assert paper_note_link_suffix("fixture-minimal") == ""
    assert paper_note_link_suffix("x") == ""
    assert paper_note_link_suffix("not-a-topic") == ""
    assert related_catalog_papers("fixture-minimal") == []
    assert suffix_direct is paper_note_link_suffix


def test_suffix_topic_paper_deduped_related_stable_order() -> None:
    first = paper_note_link_suffix("arxiv-2209.14792")
    second = paper_note_link_suffix("arxiv-2209.14792")
    assert first == second
    assert first.startswith("\n## 主题\n")
    assert "[视频扩散](../wiki/video-diffusion.md)" in first
    assert "[视频 tokenizer](../wiki/tokenization.md)" not in first
    assert "## 相关论文" in first
    related = related_catalog_papers("arxiv-2209.14792")
    ids = [paper_id for paper_id, _title in related]
    assert ids[0] == "arxiv-2204.03458"
    assert "arxiv-2209.14792" not in ids
    assert len(ids) == len(set(ids))
    assert related == related_catalog_papers("arxiv-2209.14792")
    assert "[Video Diffusion Models](./arxiv-2204.03458.md) (2022)" in first
    assert "](./arxiv-2209.14792.md)" not in first


def test_suffix_cogvideox_unions_topics_and_skips_self() -> None:
    text = paper_note_link_suffix("arxiv-2408.06072")
    topic_vd = "[视频扩散](../wiki/video-diffusion.md)"
    topic_tok = "[视频 tokenizer](../wiki/tokenization.md)"
    assert topic_vd in text
    assert topic_tok in text
    assert text.index(topic_vd) < text.index(topic_tok)
    related = related_catalog_papers("arxiv-2408.06072")
    ids = [paper_id for paper_id, _title in related]
    assert "arxiv-2408.06072" not in ids
    assert len(ids) == len(set(ids))
    assert "arxiv-2204.03458" in ids
    assert "arxiv-2209.14792" in ids
    assert "arxiv-2210.02399" in ids
    assert ids.index("arxiv-2204.03458") < ids.index("arxiv-2209.14792")
    assert ids.index("arxiv-2209.14792") < ids.index("arxiv-2210.02399")
    from video_paper_wiki.notes.index import paper_index_year, sort_paper_ids

    assert ids == sort_paper_ids(ids)
    years = [paper_index_year(pid) for pid in ids]
    dated = [(i, y) for i, y in enumerate(years) if y is not None]
    assert [y for _i, y in dated] == sorted(y for _i, y in dated)
    y2022 = [pid for pid in ids if paper_index_year(pid) == 2022]
    later = [pid for pid in ids if (paper_index_year(pid) or 0) > 2022]
    assert "arxiv-2204.03458" in y2022
    assert "arxiv-2209.14792" in y2022
    assert "arxiv-2210.02399" in y2022
    assert y2022 == sorted(y2022)
    if later:
        assert ids.index(y2022[-1]) < ids.index(later[0])
    assert "[Phenaki](./arxiv-2210.02399.md) (2022)" in text
    assert "[Video Diffusion Models](./arxiv-2204.03458.md) (2022)" in text
    assert "](./arxiv-2408.06072.md)" not in text


def test_related_skips_sibling_without_catalog_title(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.notes.links.load_topics",
        lambda: [
            {
                "id": "video-diffusion",
                "heading_zh": "视频扩散",
                "paper_ids": ["arxiv-2209.14792", "ghost", "arxiv-2204.03458"],
            }
        ],
    )

    def _titles(paper_id: str) -> str | None:
        if paper_id == "ghost":
            return None
        return catalog_title_for_paper_id(paper_id)

    monkeypatch.setattr("video_paper_wiki.notes.links.catalog_title_for_paper_id", _titles)
    related = related_catalog_papers("arxiv-2209.14792")
    assert [paper_id for paper_id, _title in related] == ["arxiv-2204.03458"]
    text = paper_note_link_suffix("arxiv-2209.14792")
    assert "ghost" not in text
    assert "[Video Diffusion Models](./arxiv-2204.03458.md) (2022)" in text


def test_ingest_make_a_video_appends_trailers_only_on_papers_copy(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2209.14792", dest)
    assert code == 0

    copied = dest / "papers" / "arxiv-2209.14792.md"
    copied_text = copied.read_text(encoding="utf-8")
    _assert_frozen_headings(copied_text)
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied_text
    assert "](./arxiv-" in copied_text
    assert "](./arxiv-2209.14792.md)" not in copied_text
    assert "## 相关论文" in copied_text
    from video_paper_wiki.notes.index import paper_index_year, sort_paper_ids

    related = related_catalog_papers("arxiv-2209.14792")
    related_ids = [pid for pid, _title in related]
    assert related_ids == sort_paper_ids(related_ids)
    block = copied_text.split("## 相关论文", 1)[1]
    for pid, title in related:
        year = paper_index_year(pid)
        expected = f"[{title}](./{pid}.md)"
        if year is not None:
            expected = f"{expected} ({year})"
        assert expected in block
        assert expected in copied_text
    assert copied_text.startswith("---\ntitle:")
    assert "title: Make-A-Video" in copied_text
    assert "year: 2022" in copied_text
    assert "topics: [video-diffusion]" in copied_text
    assert f"related: [{', '.join(related_ids)}]" in copied_text
    backlinks = backlink_catalog_ids("arxiv-2209.14792")
    assert backlinks
    assert f"backlinks: [{', '.join(backlinks)}]" in copied_text
    assert network_attempts == []


def test_ingest_cogvideox_unions_both_topics(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2408.06072", dest)
    assert code == 0

    copied = (dest / "papers" / "arxiv-2408.06072.md").read_text(encoding="utf-8")
    _assert_frozen_headings(copied)
    assert "[视频扩散](../wiki/video-diffusion.md)" in copied
    assert "[视频 tokenizer](../wiki/tokenization.md)" in copied
    assert "[Phenaki](./arxiv-2210.02399.md) (2022)" in copied
    assert "[Video Diffusion Models](./arxiv-2204.03458.md) (2022)" in copied
    assert "](./arxiv-2408.06072.md)" not in copied
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_non_topic_paper_omits_trailers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "not-a-topic", dest)
    assert code == 2
    assert not (dest / "papers").exists()
    assert network_attempts == []


def test_export_minimal_fixture_omits_trailers(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(["review", "export", "--draft", str(MINIMAL), "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FROZEN_SEED_MISSING"
    assert payload["error"]["details"]["paper_id"] == "fixture-minimal"
    assert not (dest / "papers").exists()
    assert not work_review(tmp_path, "b1").exists()
    assert network_attempts == []


def test_backlink_catalog_ids_is_reverse_related() -> None:
    from video_paper_wiki.notes.index import sort_paper_ids
    from video_paper_wiki.parse.title import catalog_paper_ids

    for paper_id in catalog_paper_ids():
        expected = []
        for other in catalog_paper_ids():
            if other == paper_id:
                continue
            related = [sibling for sibling, _title in related_catalog_papers(other)]
            if paper_id in related:
                expected.append(other)
        assert backlink_catalog_ids(paper_id) == sort_paper_ids(expected)
    assert backlink_catalog_ids("") == []
    assert backlink_catalog_ids("fixture-minimal") == []
    assert backlink_catalog_ids("x") == []


def test_backlinks_include_untitled_source(monkeypatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki.notes.links.load_topics",
        lambda: [
            {
                "id": "video-diffusion",
                "heading_zh": "视频扩散",
                "paper_ids": ["ghost", "arxiv-2204.03458"],
            }
        ],
    )

    def _titles(paper_id: str) -> str | None:
        if paper_id == "ghost":
            return None
        return catalog_title_for_paper_id(paper_id)

    monkeypatch.setattr("video_paper_wiki.notes.links.catalog_title_for_paper_id", _titles)
    monkeypatch.setattr(
        "video_paper_wiki.parse.title.catalog_paper_ids",
        lambda: ["ghost", "arxiv-2204.03458"],
    )
    assert [paper_id for paper_id, _title in related_catalog_papers("ghost")] == [
        "arxiv-2204.03458"
    ]
    assert related_catalog_papers("arxiv-2204.03458") == []
    assert backlink_catalog_ids("arxiv-2204.03458") == ["ghost"]
    assert backlink_catalog_ids("ghost") == []


def test_frozen_seed_topics_json_unchanged() -> None:
    import hashlib
    import subprocess

    for rel in (
        "docs/seed/engine-mvp.json",
        "docs/seed/engine-mvp-topics.json",
    ):
        path = ROOT / rel
        assert path.is_file()
        git = subprocess.check_output(
            ["git", "hash-object", str(path)],
            cwd=ROOT,
        ).decode().strip()
        head = subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{rel}"],
            cwd=ROOT,
        ).decode().strip()
        assert git == head
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == hashlib.sha256(
            subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
        ).hexdigest()
