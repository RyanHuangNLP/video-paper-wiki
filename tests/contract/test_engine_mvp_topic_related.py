from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELATED = ROOT / "docs" / "seed" / "engine-mvp-topic-related.json"
TOPICS = ROOT / "docs" / "seed" / "engine-mvp-topics.json"
SEED = ROOT / "docs" / "seed" / "engine-mvp.json"

EXPECTED = {
    "video-diffusion": ["tokenization", "evaluation", "motion-control", "language-model"],
    "tokenization": ["video-diffusion", "language-model"],
    "evaluation": ["video-diffusion", "data"],
    "data": ["evaluation"],
    "motion-control": ["video-diffusion"],
    "language-model": ["video-diffusion", "tokenization"],
}
FROZEN_SHA256 = "03454c4833c436af191eaa1eb775070609d13371d4d724893112decb95c8f621"
FROZEN_TOPICS_SHA256 = (
    "6e2935762a09ff275fd0b0c3cf06eb741ebffb905d8339fde7441abc085689c5"
)


def test_engine_mvp_topic_related_file_frozen() -> None:
    assert RELATED.is_file()
    raw = RELATED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert list(payload) == ["related"]
    assert payload["related"] == EXPECTED
    topic_ids = {
        topic["id"]
        for topic in json.loads(TOPICS.read_text(encoding="utf-8"))["topics"]
    }
    for topic_id, related_ids in payload["related"].items():
        assert topic_id in topic_ids
        for related_id in related_ids:
            assert related_id in topic_ids
            assert related_id != topic_id
    assert SEED.is_file()
    assert hashlib.sha256(TOPICS.read_bytes()).hexdigest() == FROZEN_TOPICS_SHA256
