from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.cli import main

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"

TOPIC_INDEX_LINKS = (
    "[视频扩散](wiki/video-diffusion.md)",
    "[视频 tokenizer](wiki/tokenization.md)",
    "[评测](wiki/evaluation.md)",
    "[数据](wiki/data.md)",
    "[运动控制](wiki/motion-control.md)",
    "[语言模型路线](wiki/language-model.md)",
)

BLURB_ZH = {
    "video-diffusion": "用扩散模型生成视频，覆盖文生视频和图生视频。",
    "tokenization": "把视频压成离散或连续 token，供扩散或语言模型使用。",
    "evaluation": "视频生成质量与时序一致性的评测指标和基准。",
    "data": "大规模视频-文本数据，用来训练表征或生成模型。",
    "motion-control": "用轨迹、条件或组合模块控制生成视频里的运动。",
    "language-model": "用自回归语言模型作为视频生成主干。",
}

HEADING_ZH = {
    "video-diffusion": "视频扩散",
    "tokenization": "视频 tokenizer",
    "evaluation": "评测",
    "data": "数据",
    "motion-control": "运动控制",
    "language-model": "语言模型路线",
}


RELATED_IDS = {
    "video-diffusion": [
        "evaluation",
        "language-model",
        "motion-control",
        "tokenization",
    ],
    "tokenization": ["language-model", "video-diffusion"],
    "evaluation": ["data", "video-diffusion"],
    "data": ["evaluation"],
    "motion-control": ["video-diffusion"],
    "language-model": ["tokenization", "video-diffusion"],
}


def _related_block(topic_id: str) -> str:
    links = "\n".join(
        f"[{HEADING_ZH[related_id]}](./{related_id}.md)"
        for related_id in RELATED_IDS[topic_id]
    )
    return f"## 相关主题\n{links}\n"


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _prepare(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))


def _ingest(path, paper_id, dest):
    return main(
        [
            "ingest",
            "run",
            "--path",
            str(path),
            "--paper-id",
            paper_id,
            "--vault",
            str(dest),
        ]
    )


def test_ingest_one_paper_writes_topic_wiki_pages(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = _ingest(TINY_PDF, "arxiv-2209.14792", dest)
    assert code == 0
    _stdout_json(capsys)

    wiki = dest / "wiki"
    vd = (wiki / "video-diffusion.md").read_text(encoding="utf-8")
    blurb = BLURB_ZH["video-diffusion"]
    link = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    assert vd.startswith("# 视频扩散\n")
    assert blurb in vd
    assert link in vd
    assert vd.index("# 视频扩散") < vd.index(blurb) < vd.index(link)
    assert vd == f"# 视频扩散\n\n{blurb}\n\n{link}\n\n{_related_block('video-diffusion')}"
    assert not (wiki / "index.md").exists()

    for topic_id, heading in HEADING_ZH.items():
        page = (wiki / f"{topic_id}.md").read_text(encoding="utf-8")
        assert page.startswith(f"# {heading}\n")
        assert BLURB_ZH[topic_id] in page
        if topic_id != "video-diffusion":
            assert "../papers/" not in page
            assert page == f"# {heading}\n\n{BLURB_ZH[topic_id]}\n\n{_related_block(topic_id)}"

    evaluation = (wiki / "evaluation.md").read_text(encoding="utf-8")
    assert evaluation.startswith("# 评测\n")
    assert "VBench" not in evaluation
    assert "../papers/" not in evaluation

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert index_text.startswith("# Video Paper Wiki\n")
    assert "[Make-A-Video](papers/arxiv-2209.14792.md) (2022)" in index_text
    assert "## 主题" in index_text
    assert "[视频扩散](wiki/video-diffusion.md)" in index_text
    for blurb_text in BLURB_ZH.values():
        assert blurb_text not in index_text
    paper_at = index_text.splitlines().index("[Make-A-Video](papers/arxiv-2209.14792.md) (2022)")
    topics_at = index_text.splitlines().index("## 主题")
    assert paper_at < topics_at
    for link in TOPIC_INDEX_LINKS:
        assert link in index_text
    assert index_text.count("## 主题") == 1
    assert network_attempts == []


def test_ingest_second_paper_keeps_papers_above_topics(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, "arxiv-2209.14792", dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "arxiv-2311.17982", dest) == 0
    _stdout_json(capsys)

    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)" in vd
    assert BLURB_ZH["video-diffusion"] in vd
    assert vd.index(BLURB_ZH["video-diffusion"]) < vd.index(
        "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    )
    assert "VBench" not in vd

    evaluation = (dest / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    assert evaluation.startswith("# 评测\n")
    assert BLURB_ZH["evaluation"] in evaluation
    assert "[VBench](../papers/arxiv-2311.17982.md) (2023)" in evaluation
    assert evaluation.index(BLURB_ZH["evaluation"]) < evaluation.index(
        "[VBench](../papers/arxiv-2311.17982.md) (2023)"
    )

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    lines = index_text.splitlines()
    assert index_text.startswith("# Video Paper Wiki\n")
    assert "[Make-A-Video](papers/arxiv-2209.14792.md) (2022)" in lines
    assert "[VBench](papers/arxiv-2311.17982.md) (2023)" in lines
    topics_at = lines.index("## 主题")
    assert lines.index("[Make-A-Video](papers/arxiv-2209.14792.md) (2022)") < topics_at
    assert lines.index("[VBench](papers/arxiv-2311.17982.md) (2023)") < topics_at
    vbench_line = lines.index("[VBench](papers/arxiv-2311.17982.md) (2023)")
    assert vbench_line < topics_at
    assert "[评测](wiki/evaluation.md)" in lines
    for blurb_text in BLURB_ZH.values():
        assert blurb_text not in index_text
    assert index_text.count("## 主题") == 1
    assert not (dest / "wiki" / "index.md").exists()
    assert network_attempts == []


def test_ingest_2311_then_2209_sorts_video_diffusion_by_year(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, "arxiv-2311.15127", dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "arxiv-2209.14792", dest) == 0
    _stdout_json(capsys)

    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    blurb = BLURB_ZH["video-diffusion"]
    mav = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    svd = "[Stable Video Diffusion](../papers/arxiv-2311.15127.md) (2023)"
    assert vd.startswith("# 视频扩散\n")
    assert blurb in vd
    assert mav in vd
    assert svd in vd
    assert vd.index("# 视频扩散") < vd.index(blurb) < vd.index(mav) < vd.index(svd)
    assert not (dest / "wiki" / "index.md").exists()

    index_lines = (dest / "index.md").read_text(encoding="utf-8").splitlines()
    mav_index = "[Make-A-Video](papers/arxiv-2209.14792.md) (2022)"
    svd_index = "[Stable Video Diffusion](papers/arxiv-2311.15127.md) (2023)"
    assert index_lines.index(mav_index) < index_lines.index(svd_index)
    assert index_lines.index(svd_index) < index_lines.index("## 主题")

    topics_path = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
    payload = json.loads(topics_path.read_text(encoding="utf-8"))
    video_ids = next(
        topic["paper_ids"] for topic in payload["topics"] if topic["id"] == "video-diffusion"
    )
    assert video_ids[:2] == ["arxiv-2204.03458", "arxiv-2209.14792"]
    assert network_attempts == []


def test_ingest_pdf_dir_fills_tokenization_page(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    for paper_id in ("arxiv-2210.02399", "arxiv-2212.05199", "arxiv-2408.06072"):
        (pdf_dir / f"{paper_id}.pdf").write_bytes(TINY_PDF.read_bytes())
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    code = main(
        ["ingest", "run", "--pdf-dir", str(pdf_dir), "--vault", str(dest)]
    )
    assert code == 0
    _stdout_json(capsys)

    tok = (dest / "wiki" / "tokenization.md").read_text(encoding="utf-8")
    assert tok.startswith("# 视频 tokenizer\n")
    assert BLURB_ZH["tokenization"] in tok
    assert "[Phenaki](../papers/arxiv-2210.02399.md) (2022)" in tok
    assert "[MAGVIT](../papers/arxiv-2212.05199.md) (2022)" in tok
    assert "[CogVideoX](../papers/arxiv-2408.06072.md) (2024)" in tok
    phenaki = "[Phenaki](../papers/arxiv-2210.02399.md) (2022)"
    magvit = "[MAGVIT](../papers/arxiv-2212.05199.md) (2022)"
    cog = "[CogVideoX](../papers/arxiv-2408.06072.md) (2024)"
    assert tok.index(BLURB_ZH["tokenization"]) < tok.index(phenaki) < tok.index(magvit) < tok.index(cog)

    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[CogVideoX](../papers/arxiv-2408.06072.md) (2024)" in vd
    assert BLURB_ZH["video-diffusion"] in vd
    assert "Phenaki" not in vd

    lm = (dest / "wiki" / "language-model.md").read_text(encoding="utf-8")
    assert "[Phenaki](../papers/arxiv-2210.02399.md) (2022)" in lm
    assert BLURB_ZH["language-model"] in lm

    assert not (dest / "wiki" / "index.md").exists()
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    for blurb_text in BLURB_ZH.values():
        assert blurb_text not in index_text
    lines = index_text.splitlines()
    topics_at = lines.index("## 主题")
    phenaki_i = next(i for i, row in enumerate(lines) if "](papers/arxiv-2210.02399.md)" in row)
    magvit_i = next(i for i, row in enumerate(lines) if "](papers/arxiv-2212.05199.md)" in row)
    cog_i = next(i for i, row in enumerate(lines) if "](papers/arxiv-2408.06072.md)" in row)
    assert phenaki_i < magvit_i < cog_i < topics_at
    assert lines[phenaki_i].endswith("(2022)")
    assert lines[magvit_i].endswith("(2022)")
    assert lines[cog_i].endswith("(2024)")
    assert network_attempts == []


def test_ingest_without_notes_root_writes_no_wiki(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    code = main(
        ["ingest", "run", "--path", str(TINY_PDF), "--paper-id", "arxiv-2209.14792"]
    )
    assert code == 0
    capsys.readouterr()
    assert not (tmp_path / "wiki").exists()
    assert not (tmp_path / "index.md").exists()
    assert list(tmp_path.rglob("wiki")) == []
    assert list(tmp_path.rglob("index.md")) == []
    assert network_attempts == []


def test_ingest_1812_evaluation_year_and_heading_format(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, "arxiv-1812.01717", dest) == 0
    _stdout_json(capsys)

    evaluation = (dest / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    blurb = BLURB_ZH["evaluation"]
    link = (
        "[Towards Accurate Generative Models of Video]"
        "(../papers/arxiv-1812.01717.md) (2018)"
    )
    assert evaluation.startswith("# 评测\n")
    assert blurb in evaluation
    assert link in evaluation
    assert evaluation.index("# 评测") < evaluation.index(blurb) < evaluation.index(link)
    assert evaluation == f"# 评测\n\n{blurb}\n\n{link}\n\n{_related_block('evaluation')}"
    assert not (dest / "wiki" / "index.md").exists()

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert (
        "[Towards Accurate Generative Models of Video]"
        "(papers/arxiv-1812.01717.md) (2018)"
    ) in index_text
    assert network_attempts == []


def test_ingest_2408_and_1812_keep_seed_order_index_year_sorted(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, "arxiv-2408.06072", dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "arxiv-1812.01717", dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "arxiv-2209.14792", dest) == 0
    _stdout_json(capsys)

    evaluation = (dest / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    towards = (
        "[Towards Accurate Generative Models of Video]"
        "(../papers/arxiv-1812.01717.md) (2018)"
    )
    assert evaluation.startswith("# 评测\n")
    assert BLURB_ZH["evaluation"] in evaluation
    assert towards in evaluation
    assert evaluation.index(BLURB_ZH["evaluation"]) < evaluation.index(towards)
    assert "VBench" not in evaluation

    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    mav = "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)"
    cog = "[CogVideoX](../papers/arxiv-2408.06072.md) (2024)"
    assert vd.startswith("# 视频扩散\n")
    assert BLURB_ZH["video-diffusion"] in vd
    assert mav in vd
    assert cog in vd
    assert vd.index(BLURB_ZH["video-diffusion"]) < vd.index(mav) < vd.index(cog)

    tok = (dest / "wiki" / "tokenization.md").read_text(encoding="utf-8")
    assert tok.startswith("# 视频 tokenizer\n")
    assert BLURB_ZH["tokenization"] in tok
    assert cog in tok
    assert tok.index(BLURB_ZH["tokenization"]) < tok.index(cog)

    assert not (dest / "wiki" / "index.md").exists()
    index_lines = (dest / "index.md").read_text(encoding="utf-8").splitlines()
    towards_index = (
        "[Towards Accurate Generative Models of Video]"
        "(papers/arxiv-1812.01717.md) (2018)"
    )
    mav_index = "[Make-A-Video](papers/arxiv-2209.14792.md) (2022)"
    cog_index = "[CogVideoX](papers/arxiv-2408.06072.md) (2024)"
    assert index_lines[0] == "# Video Paper Wiki"
    assert index_lines.index(towards_index) < index_lines.index(mav_index)
    assert index_lines.index(mav_index) < index_lines.index(cog_index)
    assert index_lines.index(cog_index) < index_lines.index("## 主题")
    assert network_attempts == []


def test_ingest_non_catalog_paper_id_x_is_not_a_wiki_link(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    assert _ingest(TINY_PDF, "x", dest) == 0
    capsys.readouterr()
    assert _ingest(TINY_PDF, "arxiv-2209.14792", dest) == 0
    _stdout_json(capsys)

    wiki = dest / "wiki"
    for page in wiki.glob("*.md"):
        body = page.read_text(encoding="utf-8")
        assert "](../papers/x.md)" not in body
        assert "papers/x.md" not in body
    vd = (wiki / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)" in vd
    assert not (wiki / "index.md").exists()

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert "](papers/x.md)" in index_text
    x_line = next(line for line in index_text.splitlines() if "](papers/x.md)" in line)
    assert x_line.endswith(".md)")
    assert " (20" not in x_line
    assert f"{x_line} (" not in index_text
    assert network_attempts == []


def test_ingest_writes_related_topics_and_leaves_notes(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    _prepare(tmp_path, monkeypatch)
    dest = tmp_path / "obsidian-root"
    dest.mkdir()
    paper_before = None
    assert _ingest(TINY_PDF, "arxiv-2209.14792", dest) == 0
    _stdout_json(capsys)
    note = dest / "papers" / "arxiv-2209.14792.md"
    paper_before = note.read_text(encoding="utf-8")
    index_before = (dest / "index.md").read_text(encoding="utf-8")
    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert vd.endswith(_related_block("video-diffusion"))
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)" in vd
    assert vd.index("[Make-A-Video](../papers/arxiv-2209.14792.md) (2022)") < vd.index(
        "## 相关主题"
    )
    assert " (20" not in vd.split("## 相关主题", 1)[1]
    assert not (dest / "wiki" / "index.md").exists()
    assert note.read_text(encoding="utf-8") == paper_before
    assert (dest / "index.md").read_text(encoding="utf-8") == index_before
    assert "## 相关主题" not in index_before
    assert network_attempts == []
