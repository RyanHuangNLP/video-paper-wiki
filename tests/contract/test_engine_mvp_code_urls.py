from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CODE_URLS = ROOT / "docs" / "seed" / "engine-mvp-code-urls.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"

FROZEN_SHA256 = "9fbb533d3be9cf01bc098c50a8fa325accf5b3ecf1a6486aae9a4872f4119bde"
FROZEN_SEED_SHA256 = (
    "0f8ca52f9d0175837818a8d2fed041280c9ad7691974a75a54b703a4df954717"
)
FROZEN_TOPICS_SHA256 = (
    "3bb9aad76e835b1f77c14bf6f83c7e039997763f78b8b59b22e2682007aedc5b"
)


def test_engine_mvp_code_urls_file_default_empty() -> None:
    assert CODE_URLS.is_file()
    raw = CODE_URLS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["code_urls"]
    assert payload["code_urls"] == {}
    seed_ids = {
        paper["paper_id"]
        for paper in json.loads(SEED.read_text(encoding="utf-8"))["papers"]
    }
    assert len(seed_ids) == 67
    for paper_id, urls in payload["code_urls"].items():
        assert paper_id in seed_ids
        assert isinstance(urls, list)
        for url in urls:
            assert isinstance(url, str)
            parts = urlsplit(url)
            assert parts.scheme in {"http", "https"}
            assert parts.netloc
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == FROZEN_SEED_SHA256
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
