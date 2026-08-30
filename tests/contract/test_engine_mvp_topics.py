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
FORBIDDEN_KEY_FRAGMENTS = ("pdf", "fetch")
ALLOWED_TOPIC_KEYS = {"id", "heading_zh", "paper_ids"}
FROZEN_TOPICS_SHA256 = (
    "3df830cb7dbd7a467aec5a92fbaae06554423b03984b35028d9457e9f9446f52"
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
