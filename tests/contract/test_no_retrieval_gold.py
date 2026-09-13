from pathlib import Path
from video_paper_wiki.contracts import schema_by_title


def test_retrieval_gold_is_closed_and_separate_from_runtime_ranking() -> None:
    paths=sorted(path.name for path in Path("schemas").glob("*retrieval*"))
    assert paths==["video-paper-wiki.retrieval-config.v1.schema.json","video-paper-wiki.retrieval-gold.v1.schema.json","video-paper-wiki.retrieval-policy.v1.schema.json"]
    assert schema_by_title("video-paper-wiki.retrieval-gold.v1")["additionalProperties"] is False
    source=Path("src/video_paper_wiki/retrieval.py").read_text()
    ranking=source[source.index("def rank_hits"):source.index("def _bp")]
    assert "gold" not in ranking.casefold()
