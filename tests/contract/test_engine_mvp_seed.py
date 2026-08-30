from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED_PAPER_IDS = (
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
    "arxiv-2304.08818",
    "arxiv-2307.04725",
    "arxiv-2311.04145",
    "arxiv-2212.11565",
    "arxiv-2303.13439",
    "arxiv-2401.10147",
    "arxiv-2205.15868",
    "arxiv-2210.02303",
    "arxiv-2309.15807",
    "arxiv-2309.15103",
    "arxiv-2311.16933",
    "arxiv-2312.12456",
    "arxiv-2310.15127",
    "arxiv-2312.03541",
    "arxiv-2312.13253",
    "arxiv-2403.14773",
    "arxiv-2404.02101",
    "arxiv-2407.02371",
    "arxiv-2402.03162",
    "arxiv-2402.04324",
    "arxiv-2311.06908",
    "arxiv-2310.08465",
    "arxiv-2405.18911",
    "arxiv-2403.04916",
    "arxiv-2402.14709",
    "arxiv-2406.08119",
    "arxiv-2410.13720",
)
EXPECTED_ABS_URLS = (
    "https://arxiv.org/abs/2204.03458",
    "https://arxiv.org/abs/2311.15127",
    "https://arxiv.org/abs/2311.17982",
    "https://arxiv.org/abs/2209.14792",
    "https://arxiv.org/abs/2310.12190",
    "https://arxiv.org/abs/2401.03048",
    "https://arxiv.org/abs/2210.02399",
    "https://arxiv.org/abs/2212.05199",
    "https://arxiv.org/abs/2312.14125",
    "https://arxiv.org/abs/2401.12945",
    "https://arxiv.org/abs/2408.06072",
    "https://arxiv.org/abs/2412.03603",
    "https://arxiv.org/abs/2410.05954",
    "https://arxiv.org/abs/2307.06942",
    "https://arxiv.org/abs/2402.19479",
    "https://arxiv.org/abs/2405.18750",
    "https://arxiv.org/abs/2306.02018",
    "https://arxiv.org/abs/2312.03641",
    "https://arxiv.org/abs/1812.01717",
    "https://arxiv.org/abs/2304.08818",
    "https://arxiv.org/abs/2307.04725",
    "https://arxiv.org/abs/2311.04145",
    "https://arxiv.org/abs/2212.11565",
    "https://arxiv.org/abs/2303.13439",
    "https://arxiv.org/abs/2401.10147",
    "https://arxiv.org/abs/2205.15868",
    "https://arxiv.org/abs/2210.02303",
    "https://arxiv.org/abs/2309.15807",
    "https://arxiv.org/abs/2309.15103",
    "https://arxiv.org/abs/2311.16933",
    "https://arxiv.org/abs/2312.12456",
    "https://arxiv.org/abs/2310.15127",
    "https://arxiv.org/abs/2312.03541",
    "https://arxiv.org/abs/2312.13253",
    "https://arxiv.org/abs/2403.14773",
    "https://arxiv.org/abs/2404.02101",
    "https://arxiv.org/abs/2407.02371",
    "https://arxiv.org/abs/2402.03162",
    "https://arxiv.org/abs/2402.04324",
    "https://arxiv.org/abs/2311.06908",
    "https://arxiv.org/abs/2310.08465",
    "https://arxiv.org/abs/2405.18911",
    "https://arxiv.org/abs/2403.04916",
    "https://arxiv.org/abs/2402.14709",
    "https://arxiv.org/abs/2406.08119",
    "https://arxiv.org/abs/2410.13720",
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
    assert len(papers) == 46
    assert [paper["paper_id"] for paper in papers] == list(EXPECTED_PAPER_IDS)
    assert [paper["abs_url"] for paper in papers] == list(EXPECTED_ABS_URLS)
    _assert_no_pdf_or_fetch_keys(payload)
    for paper in papers:
        blob = " ".join(
            str(paper.get(key, "")) for key in ("title", "paper_id", "arxiv_id", "arxiv")
        )
        assert "modelscope" not in blob.lower()
