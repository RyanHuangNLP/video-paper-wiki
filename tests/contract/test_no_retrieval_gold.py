from pathlib import Path


def test_retrieval_gold_contract_is_explicitly_absent() -> None:
    excluded = Path("schemas/video-paper-wiki.retrieval-gold.v1.schema.json")
    assert not excluded.exists()
    assert list(Path("schemas").glob("*retrieval*")) == []
