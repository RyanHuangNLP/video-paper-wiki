import json
from pathlib import Path

import pytest

from tests.preview_fixture import page
from video_paper_wiki_research.arxiv_preview import normalize_arxiv, parse_normalized_page
from video_paper_wiki_research.contracts import ResearchError


@pytest.mark.parametrize("raw,expected", [
    ("  arXiv:2408.06072v2  ", ("2408.06072", 2)), ("https://arxiv.org/abs/2408.06072", ("2408.06072", None)),
    ("hep-th/9901001v12", ("hep-th/9901001", 12)), ("0704.0001", ("0704.0001", None)),
])
def test_normalize(raw, expected):
    assert normalize_arxiv(raw) == expected


@pytest.mark.parametrize("raw", [
    "2400.06072", "2413.06072", "2408.06072v0", "2408.06072v10000", "2408.06072V2",
    "https://arxiv.org:443/abs/2408.06072", "https://user@arxiv.org/abs/2408.06072",
    "https://arxiv.org.evil/abs/2408.06072", "http://arxiv.org/abs/2408.06072",
    "https://arxiv.org/abs/2408.06072?x=1", "https://arxiv.org/abs/2408.06072#x",
    "https://arxiv.org/abs/2408.06072/", "https://arxiv.org/abs/%32%34%30%38.06072",
    "2408. 06072", "24０8.06072", "hep-th/9913001", "title only", [], {}, None,
])
def test_refuse_identity(raw):
    with pytest.raises(ResearchError) as caught:
        normalize_arxiv(raw)
    assert caught.value.code == "ARXIV_ID_INVALID"


def parse(text, requested=2):
    return parse_normalized_page(text, entity_id="2408.06072", requested_version=requested)


def test_complete_and_tool_numbered_stream():
    expected = parse(page())
    numbered = "tool header\n" + " ".join(f"L{i}: {line}" for i, line in enumerate(page().splitlines()))
    assert parse(numbered) == expected
    assert expected["authors"] == ["Alice Example", "Bob Example"]
    assert "second synthetic paragraph" in expected["abstract"]
    assert "Comments" not in expected["abstract"] and "View PDF" not in expected["authors"]
    assert expected["latest_at_observation"] is True and expected["other_versions_exist"] == "yes"
    assert expected["updated_at"] == "2024-10-08T06:28:19Z"


def test_incomplete_history_only_proves_yes():
    value = parse(page(complete=False))
    assert value["latest_at_observation"] is None and value["other_versions_exist"] == "yes"
    single = parse(page(version=1, complete=False), requested=1)
    assert single["latest_at_observation"] is None and single["other_versions_exist"] == "unknown"
    single = parse(page(version=1), requested=1)
    assert single["latest_at_observation"] is True and single["other_versions_exist"] == "no"


@pytest.mark.parametrize("text,code", [
    (page().replace("2408.06072", "2408.06073"), "ARXIV_ID_MISMATCH"),
    (page(version=1), "ARXIV_VERSION_MISMATCH"),
    (page().replace("v2】", "】"), "ARXIV_VERSION_UNCONFIRMED"),
    (page().replace("(or", "arXiv:2408.06072v1 (or"), "ARXIV_VERSION_MISMATCH"),
    (page().replace("Authors:", "Missing:"), "ARXIV_METADATA_INCOMPLETE"),
    (page().replace("Subjects:", "Title: duplicate\nSubjects:"), "ARXIV_METADATA_INCOMPLETE"),
    (page().replace("A synthetic method", "[abstract omitted] A synthetic method"), "ARXIV_METADATA_INCOMPLETE"),
    (page().replace("[v2]", "unrecognized history text\n[v2]"), "ARXIV_METADATA_INCOMPLETE"),
    (page().replace("[v1]", "[v3]"), "ARXIV_METADATA_INCOMPLETE"),
])
def test_named_sections_refuse(text, code):
    with pytest.raises(ResearchError) as caught:
        parse(text)
    assert caught.value.code == code


def test_footer_does_not_supply_identity():
    text = page().replace("Cite as:", "untrusted:") + "\narXiv:2408.06072v2\n"
    with pytest.raises(ResearchError) as caught:
        parse(text)
    assert caught.value.code == "ARXIV_VERSION_UNCONFIRMED"


def test_preserved_cap_excerpts_are_incomplete():
    fixture = Path(__file__).parents[1] / "fixtures/research-preview/cap-web-obs-001-excerpts.json"
    for sample in json.loads(fixture.read_bytes())["samples"]:
        with pytest.raises(ResearchError) as caught:
            parse(sample["normalized_excerpt"])
        assert caught.value.code == "ARXIV_METADATA_INCOMPLETE"
