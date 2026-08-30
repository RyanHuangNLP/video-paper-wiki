from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED_TOPIC_IDS = (
    "video-diffusion",
    "tokenization",
    "evaluation",
    "data",
    "motion-control",
    "language-model",
)
EXPECTED_HEADING_ZH = {
    "video-diffusion": "视频扩散",
    "tokenization": "视频 tokenizer",
    "evaluation": "评测",
    "data": "数据",
    "motion-control": "运动控制",
    "language-model": "语言模型路线",
}
EXPECTED_PAPER_IDS = {
    "video-diffusion": [
        "arxiv-2204.03458",
        "arxiv-2209.14792",
        "arxiv-2210.02303",
        "arxiv-2212.11565",
        "arxiv-2303.13439",
        "arxiv-2304.08818",
        "arxiv-2307.04725",
        "arxiv-2309.15103",
        "arxiv-2309.15807",
        "arxiv-2310.15127",
        "arxiv-2311.04145",
        "arxiv-2311.15127",
        "arxiv-2312.13253",
        "arxiv-2401.03048",
        "arxiv-2401.10147",
        "arxiv-2401.12945",
        "arxiv-2402.04324",
        "arxiv-2403.14773",
        "arxiv-2405.18750",
        "arxiv-2405.18911",
        "arxiv-2408.06072",
        "arxiv-2410.05954",
        "arxiv-2412.03603",
    ],
    "tokenization": ["arxiv-2210.02399", "arxiv-2212.05199", "arxiv-2312.03541", "arxiv-2408.06072"],
    "evaluation": ["arxiv-1812.01717", "arxiv-2311.06908", "arxiv-2311.17982", "arxiv-2312.12456"],
    "data": ["arxiv-2307.06942", "arxiv-2402.19479", "arxiv-2403.04916", "arxiv-2407.02371"],
    "motion-control": ["arxiv-2212.11565", "arxiv-2306.02018", "arxiv-2307.04725", "arxiv-2310.08465", "arxiv-2310.12190", "arxiv-2311.16933", "arxiv-2312.03641", "arxiv-2402.03162", "arxiv-2404.02101"],
    "language-model": ["arxiv-2205.15868", "arxiv-2210.02399", "arxiv-2312.03541", "arxiv-2312.14125"],
}
EXPECTED_BLURB_ZH = {
    "video-diffusion": "用扩散模型生成视频，覆盖文生视频和图生视频。",
    "tokenization": "把视频压成离散或连续 token，供扩散或语言模型使用。",
    "evaluation": "视频生成质量与时序一致性的评测指标和基准。",
    "data": "大规模视频-文本数据，用来训练表征或生成模型。",
    "motion-control": "用轨迹、条件或组合模块控制生成视频里的运动。",
    "language-model": "用自回归语言模型作为视频生成主干。",
}
FORBIDDEN_KEY_FRAGMENTS = ("pdf", "fetch")
ALLOWED_TOPIC_KEYS = {"id", "heading_zh", "paper_ids", "blurb_zh"}
FROZEN_TOPICS_SHA256 = (
    "230d312230aed2a24ddbee5f0398ad67ebf2fffbe9d443574c439d084c9a4848"
)


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


def test_engine_mvp_topics_file_ids_catalog_and_overlaps() -> None:
    assert TOPICS.is_file()
    payload = json.loads(TOPICS.read_text(encoding="utf-8"))
    topics = payload["topics"]
    assert [topic["id"] for topic in topics] == list(EXPECTED_TOPIC_IDS)
    catalog = json.loads(SEED.read_text(encoding="utf-8"))
    catalog_ids = {paper["paper_id"] for paper in catalog["papers"]}
    for topic in topics:
        assert set(topic.keys()) == ALLOWED_TOPIC_KEYS
        tid = topic["id"]
        assert topic["heading_zh"] == EXPECTED_HEADING_ZH[tid]
        assert topic["paper_ids"] == EXPECTED_PAPER_IDS[tid]
        assert topic["blurb_zh"] == EXPECTED_BLURB_ZH[tid]
        for paper_id in topic["paper_ids"]:
            assert paper_id in catalog_ids
    _assert_no_pdf_or_fetch_keys(payload)
    raw = TOPICS.read_text(encoding="utf-8")
    assert "modelscope" not in raw.lower()
    assert "ModelScope" not in raw
    by_id = {topic["id"]: topic["paper_ids"] for topic in topics}
    assert "arxiv-2408.06072" in by_id["video-diffusion"]
    assert "arxiv-2408.06072" in by_id["tokenization"]
    assert "arxiv-2210.02399" in by_id["tokenization"]
    assert "arxiv-2210.02399" in by_id["language-model"]


def test_engine_mvp_topics_file_bytes_unchanged() -> None:
    digest = hashlib.sha256(TOPICS.read_bytes()).hexdigest()
    assert digest == FROZEN_TOPICS_SHA256
    assert TOPICS.read_text(encoding="utf-8") == TOPICS.read_bytes().decode("utf-8")
