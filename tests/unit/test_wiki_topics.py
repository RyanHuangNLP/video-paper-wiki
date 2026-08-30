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
    assert vd.startswith("# 视频扩散\n")
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md)" in vd
    assert not (wiki / "index.md").exists()

    evaluation = (wiki / "evaluation.md").read_text(encoding="utf-8")
    assert evaluation.startswith("# 评测\n")
    assert "VBench" not in evaluation
    assert "../papers/" not in evaluation

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert index_text.startswith("# Video Paper Wiki\n")
    assert "[Make-A-Video](papers/arxiv-2209.14792.md)" in index_text
    assert "## 主题" in index_text
    assert "[视频扩散](wiki/video-diffusion.md)" in index_text
    paper_at = index_text.splitlines().index("[Make-A-Video](papers/arxiv-2209.14792.md)")
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
    assert "[Make-A-Video](../papers/arxiv-2209.14792.md)" in vd
    assert "VBench" not in vd

    evaluation = (dest / "wiki" / "evaluation.md").read_text(encoding="utf-8")
    assert evaluation.startswith("# 评测\n")
    assert "[VBench](../papers/arxiv-2311.17982.md)" in evaluation

    index_text = (dest / "index.md").read_text(encoding="utf-8")
    lines = index_text.splitlines()
    assert index_text.startswith("# Video Paper Wiki\n")
    assert "[Make-A-Video](papers/arxiv-2209.14792.md)" in lines
    assert "[VBench](papers/arxiv-2311.17982.md)" in lines
    topics_at = lines.index("## 主题")
    assert lines.index("[Make-A-Video](papers/arxiv-2209.14792.md)") < topics_at
    assert lines.index("[VBench](papers/arxiv-2311.17982.md)") < topics_at
    vbench_line = lines.index("[VBench](papers/arxiv-2311.17982.md)")
    assert vbench_line < topics_at
    assert "[评测](wiki/evaluation.md)" in lines
    assert index_text.count("## 主题") == 1
    assert not (dest / "wiki" / "index.md").exists()
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
    assert "[Phenaki](../papers/arxiv-2210.02399.md)" in tok
    assert "[MAGVIT](../papers/arxiv-2212.05199.md)" in tok
    assert "[CogVideoX](../papers/arxiv-2408.06072.md)" in tok

    vd = (dest / "wiki" / "video-diffusion.md").read_text(encoding="utf-8")
    assert "[CogVideoX](../papers/arxiv-2408.06072.md)" in vd
    assert "Phenaki" not in vd

    lm = (dest / "wiki" / "language-model.md").read_text(encoding="utf-8")
    assert "[Phenaki](../papers/arxiv-2210.02399.md)" in lm

    assert not (dest / "wiki" / "index.md").exists()
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    topics_at = index_text.splitlines().index("## 主题")
    for paper_id in ("arxiv-2210.02399", "arxiv-2212.05199", "arxiv-2408.06072"):
        line = next(
            i
            for i, row in enumerate(index_text.splitlines())
            if f"](papers/{paper_id}.md)" in row
        )
        assert line < topics_at
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
