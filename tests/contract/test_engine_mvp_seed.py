from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED_PAPER_IDS = (
    "arxiv-2204.03458",
    "arxiv-2311.15127",
    "arxiv-2311.17982",
)
EXPECTED_ABS_URLS = (
    "https://arxiv.org/abs/2204.03458",
    "https://arxiv.org/abs/2311.15127",
    "https://arxiv.org/abs/2311.17982",
)
FORBIDDEN_KEY_FRAGMENTS = ("pdf", "fetch")


def _assert_no_pdf_or_fetch_keys(obj: object) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            for fragment in FORBIDDEN_KEY_FRAGMENTS:
                assert fragment not in lowered, f"forbidden key {key!r}"
            _assert_no_pdf_or_fetch_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_pdf_or_fetch_keys(item)


def test_engine_mvp_seed_catalog_exact_ids_and_urls() -> None:
    assert SEED.is_file()
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    papers = payload["papers"]
    assert len(papers) == 3
    assert [paper["paper_id"] for paper in papers] == list(EXPECTED_PAPER_IDS)
    assert [paper["abs_url"] for paper in papers] == list(EXPECTED_ABS_URLS)
    _assert_no_pdf_or_fetch_keys(payload)
