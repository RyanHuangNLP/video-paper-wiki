from __future__ import annotations

from pathlib import Path

from .paths import load_json

EXPECTED_AXES = [
    "task/conditioning", "formulation/objective", "representation/tokenizer", "backbone",
    "spatial-temporal-modeling", "data/captioning/filtering", "training/parallelism/optimization",
    "inference/distillation/acceleration", "control", "evaluation/dataset/benchmark",
]


def test_taxonomy_v1_axes_and_unknown_term_policy() -> None:
    taxonomy = load_json(Path("taxonomy/v1.json"))
    assert taxonomy["version"] == "v1"
    assert taxonomy["policy"]["unknown_terms"] == "review_queue"
    assert taxonomy["policy"]["silent_create"] is False
    assert [axis["slug"] for axis in taxonomy["axes"]] == EXPECTED_AXES
    for axis in taxonomy["axes"]:
        assert set(axis) == {"slug", "label_zh", "label_en", "aliases", "terms"}
        assert axis["terms"]
        for term in axis["terms"]:
            assert set(term) == {"slug", "label_zh", "aliases", "status"}
            assert term["status"] == "canonical"


def test_yaml_human_copy_starts_with_comment_and_freezes_bilingual_policy() -> None:
    yaml = Path("taxonomy/v1.yaml").read_text(encoding="utf-8")
    assert yaml.startswith("#")
    assert "Unknown terms MUST enter a review queue and MUST NOT be silently created as canonical terms." in yaml
    assert "未知术语必须进入 review queue，不得静默创建新的 canonical term。" in yaml
    assert "silent_create: false" in yaml
