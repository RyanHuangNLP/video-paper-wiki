from __future__ import annotations

import copy
import json
import re

import pytest

from tests.contract.paths import VALID, load_json
from tests.unit.test_article_revision import _import_outline
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading.view import build_reading_views

TITLE = "video-paper-wiki.reading-manifest.v1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _fixture() -> dict:
    return load_json(VALID / f"{TITLE}.json")


def _reject(document: dict) -> None:
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema=TITLE)
    assert exc.value.code == "SCHEMA_INVALID"


def test_reading_manifest_fixture_and_refusals() -> None:
    document = _fixture()
    validate_document(document, expected_schema=TITLE)
    top = copy.deepcopy(document)
    top["unexpected_field"] = True
    _reject(top)
    nested = copy.deepcopy(document)
    nested["basis"]["unexpected_field"] = True
    _reject(nested)
    staged = copy.deepcopy(document)
    staged["staging"] = {"new": 1, "already_staged": 0, "manifest_path": ".work/r1/reading/manifest.json"}
    _reject(staged)
    with_schema = copy.deepcopy(document)
    with_schema["schema"] = TITLE
    _reject(with_schema)
    kind = copy.deepcopy(document)
    kind["view_kind"] = "obsidian-reading.v0"
    _reject(kind)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied)
    published = copy.deepcopy(document)
    published["publication"] = "published"
    _reject(published)
    ranked = copy.deepcopy(document)
    ranked["ranking"] = "ranked"
    _reject(ranked)
    wiki_path = copy.deepcopy(document)
    wiki_path["articles"][0]["render_path"] = "wiki/x.md"
    _reject(wiki_path)
    traversal = copy.deepcopy(document)
    traversal["articles"][0]["render_path"] = ".work/w1/../x.md"
    _reject(traversal)
    manifest_page = copy.deepcopy(document)
    manifest_page["pages"][0]["path"] = "manifest.json"
    _reject(manifest_page)
    parent_page = copy.deepcopy(document)
    parent_page["pages"][0]["path"] = "../x.md"
    _reject(parent_page)
    location = copy.deepcopy(document)
    location["articles"][0]["head_location"] = "vault"
    _reject(location)
    status = copy.deepcopy(document)
    status["articles"][0]["check_status"] = "ok"
    _reject(status)
    negative = copy.deepcopy(document)
    negative["counts"]["pages"] = -1
    _reject(negative)
    schema = schema_by_title(TITLE)
    assert schema["title"] == TITLE


def test_reading_manifest_matches_built_world(world) -> None:
    _three_chain(world)
    data = build_reading_views(vault_root=str(world["vault"]), batch_id="r1")
    manifest = {key: value for key, value in data.items() if key != "staging"}
    validate_document(manifest, expected_schema=TITLE)
    raw = (world["checkout"] / ".work" / "r1" / "reading" / "manifest.json").read_bytes()
    loaded = json.loads(raw.decode("utf-8"))
    validate_document(loaded, expected_schema=TITLE)
    assert canonicalize(loaded) == raw
    assert canonicalize(manifest) == raw
    assert loaded == manifest


def test_reading_manifest_render_path_matches_pattern(world) -> None:
    _three_chain(world)
    _import_outline(world, batch="w1")
    data = build_reading_views(
        vault_root=str(world["vault"]),
        batch_id="r1",
        articles_batch="w1",
    )
    manifest = {key: value for key, value in data.items() if key != "staging"}
    validate_document(manifest, expected_schema=TITLE)
    pattern = schema_by_title(TITLE)["properties"]["articles"]["items"]["properties"]["render_path"]["pattern"]
    assert re.search(pattern, data["articles"][0]["render_path"])
