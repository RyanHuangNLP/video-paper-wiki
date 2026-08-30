from __future__ import annotations

from tests.support import make_checkout, plant_blob, work_review

import json
from pathlib import Path

from video_paper_wiki.cli import main
from video_paper_wiki.parse.title import collapse_letter_spacing, resolve_draft_title

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

LETTER_SPACED = "MAKE -A-V IDEO : T EXT-TO-V IDEO GENERATION"
JOURNAL_HEADER = "Published in Transactions on Machine Learning Research (03/2025)"
CATALOG = (
    ("arxiv-2204.03458", "Video Diffusion Models"),
    ("arxiv-2311.15127", "Stable Video Diffusion"),
    ("arxiv-2311.17982", "VBench"),
    ("arxiv-2209.14792", "Make-A-Video"),
    ("arxiv-2310.12190", "DynamiCrafter"),
    ("arxiv-2401.03048", "Latte"),
    ("arxiv-2210.02399", "Phenaki"),
    ("arxiv-2212.05199", "MAGVIT"),
    ("arxiv-2312.14125", "VideoPoet"),
    ("arxiv-2401.12945", "Lumiere"),
    ("arxiv-2408.06072", "CogVideoX"),
    ("arxiv-2412.03603", "HunyuanVideo"),
    ("arxiv-2410.05954", "Pyramidal Flow Matching"),
    ("arxiv-2307.06942", "InternVid"),
    ("arxiv-2402.19479", "Panda-70M"),
    ("arxiv-2405.18750", "T2V-Turbo"),
    ("arxiv-2306.02018", "VideoComposer"),
    ("arxiv-2312.03641", "MotionCtrl"),
    ("arxiv-1812.01717", "Towards Accurate Generative Models of Video"),
    ("arxiv-2304.08818", "Align Your Latents"),
    ("arxiv-2307.04725", "AnimateDiff"),
    ("arxiv-2311.04145", "I2VGen-XL"),
    ("arxiv-2212.11565", "Tune-A-Video"),
    ("arxiv-2303.13439", "Text2Video-Zero"),
    ("arxiv-2401.09047", "VideoCrafter2"),
    ("arxiv-2205.15868", "CogVideo"),
    ("arxiv-2210.02303", "Imagen Video"),
    ("arxiv-2309.15818", "Show-1"),
    ("arxiv-2309.15103", "LaVie"),
    ("arxiv-2311.16933", "SparseCtrl"),
    ("arxiv-2310.11440", "EvalCrafter"),
    ("arxiv-2310.19512", "VideoCrafter1"),
    ("arxiv-2310.05737", "MAGVIT-v2"),
    ("arxiv-2311.10709", "Emu Video"),
    ("arxiv-2403.14773", "StreamingT2V"),
    ("arxiv-2404.02101", "CameraCtrl"),
    ("arxiv-2407.02371", "OpenVid-1M"),
    ("arxiv-2402.03162", "Direct-a-Video"),
    ("arxiv-2402.04324", "ConsistI2V"),
    ("arxiv-2311.01813", "FETV"),
    ("arxiv-2310.08465", "MotionDirector"),
    ("arxiv-2405.18991", "EasyAnimate"),
    ("arxiv-2403.06098", "VidProM"),
    ("arxiv-2402.14797", "Snap Video"),
    ("arxiv-2406.09399", "OmniTokenizer"),
    ("arxiv-2410.13720", "Movie Gen"),
    ("arxiv-2302.03011", "Gen-1"),
    ("arxiv-2403.12706", "AnimateDiff-Lightning"),
    ("arxiv-2406.15252", "VideoScore"),
    ("arxiv-2303.12346", "NUWA-XL"),
    ("arxiv-2310.20700", "SEINE"),
    ("arxiv-2410.02757", "Loong"),
    ("arxiv-2308.08089", "DragNUWA"),
    ("arxiv-2407.07667", "VEnhancer"),
    ("arxiv-2410.08260", "Koala-36M"),
    ("arxiv-2211.11018", "MagicVideo"),
    ("arxiv-2310.07702", "ScaleCrafter"),
    ("arxiv-2402.03161", "Video-LaVIT"),
    ("arxiv-2310.15169", "FreeNoise"),
    ("arxiv-2305.13077", "ControlVideo"),
    ("arxiv-2402.01566", "Boximator"),
    ("arxiv-2304.01186", "Follow-Your-Pose"),
    ("arxiv-2306.00943", "Make-Your-Video"),
    ("arxiv-2311.18829", "MicroCinema"),
    ("arxiv-2302.01329", "Dreamix"),
    ("arxiv-2305.10874", "VideoFactory"),
    ("arxiv-2406.18522", "ChronoMagic-Bench"),
)


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_catalog_override_ignores_pdf_junk() -> None:
    assert (
        resolve_draft_title("arxiv-2209.14792", LETTER_SPACED, LETTER_SPACED)
        == "Make-A-Video"
    )
    assert resolve_draft_title("arxiv-2401.03048", JOURNAL_HEADER, JOURNAL_HEADER) == "Latte"
    assert resolve_draft_title("arxiv-2310.12190", "some junk masthead", "some junk") == (
        "DynamiCrafter"
    )
    for paper_id, title in CATALOG:
        assert resolve_draft_title(paper_id, LETTER_SPACED, JOURNAL_HEADER) == title


def test_journal_header_first_line_skipped_without_catalog() -> None:
    page1 = f"{JOURNAL_HEADER}\nA Real Paper Title\nAbstract\nWe present a method.\n"
    title = resolve_draft_title("not-in-catalog", JOURNAL_HEADER, page1)
    assert title == "A Real Paper Title"
    assert "Published in" not in title


def test_letter_spaced_title_collapsed_without_catalog() -> None:
    title = resolve_draft_title("not-in-catalog", LETTER_SPACED, LETTER_SPACED)
    assert "T EXT" not in title
    assert "V IDEO" not in title
    assert "MAKE -A" not in title
    assert "TEXT-TO-VIDEO GENERATION" in title
    assert "MAKE-A-VIDEO" in title
    assert "VIDEOGENERATION" not in title
    assert title != "Make-A-Video"


def test_normal_titles_unchanged() -> None:
    assert resolve_draft_title("not-in-catalog", "Video Diffusion Models", "") == (
        "Video Diffusion Models"
    )
    assert resolve_draft_title("not-in-catalog", "Many Pages", "") == "Many Pages"
    assert collapse_letter_spacing("Video Diffusion Models") == "Video Diffusion Models"
    assert collapse_letter_spacing("Many Pages") == "Many Pages"


def test_missing_catalog_falls_through_to_cleanup(monkeypatch) -> None:
    monkeypatch.setattr("video_paper_wiki.parse.title._catalog_payload", lambda: None)
    title = resolve_draft_title("arxiv-2209.14792", LETTER_SPACED, "")
    assert title != "Make-A-Video"
    assert "T EXT" not in title
    assert "MAKE-A-VIDEO" in title


def test_ingest_catalog_titles_appear_in_index(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    dest = tmp_path / "notes-root"
    dest.mkdir()
    from tests.support import write_catalog_paper_note
    from video_paper_wiki.notes import upsert_index_entry

    for paper_id, title in CATALOG:
        write_catalog_paper_note(dest, paper_id, title)
        upsert_index_entry(dest, paper_id, title)
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    for paper_id, title in CATALOG:
        assert title in index_text
        assert f"papers/{paper_id}.md" in index_text
        assert (dest / "papers" / f"{paper_id}.md").is_file()
    assert JOURNAL_HEADER not in index_text
    assert "MAKE -A-V" not in index_text
    assert "T EXT-TO-V" not in index_text
    assert network_attempts == []


def test_seed_catalog_has_expected_titles() -> None:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    by_id = {paper["paper_id"]: paper["title"] for paper in payload["papers"]}
    assert by_id == dict(CATALOG)
