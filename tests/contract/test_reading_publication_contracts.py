from __future__ import annotations

import copy

import pytest

from tests.contract.paths import VALID, load_json
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_reading_view import _build, _reading_root
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.reading import view as reading_view
from video_paper_wiki.reading_publication import (
    INSTALL_ROOT,
    MARKER_PREFIX,
    MAX_PAGE_BYTES,
    MAX_PAGES,
    MAX_TOTAL_BYTES,
    PAGE_RE,
)

TITLES = (
    "video-paper-wiki.reading-publication-request.v1",
    "video-paper-wiki.reading-publication-inspection.v1",
    "video-paper-wiki.reading-publication-apply-result.v1",
)
REQUEST = TITLES[0]
INSPECTION = TITLES[1]
RESULT = TITLES[2]


def _fixture(title: str) -> dict:
    return load_json(VALID / f"{title}.json")


def _first_nested_object(document: dict) -> dict | None:
    for value in document.values():
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return None


def _reject(document: dict, title: str) -> None:
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema=title)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("title", TITLES)
def test_valid_fixtures_and_closed_objects(title: str) -> None:
    document = _fixture(title)
    validate_document(document, expected_schema=title)
    top = copy.deepcopy(document)
    top["unexpected_field"] = True
    _reject(top, title)
    nested_doc = copy.deepcopy(document)
    nested = _first_nested_object(nested_doc)
    assert nested is not None
    nested["unexpected_field"] = True
    _reject(nested_doc, title)


@pytest.mark.parametrize("title", TITLES)
def test_schema_by_title_round_trip(title: str) -> None:
    assert schema_by_title(title)["title"] == title


def test_request_kind_path_and_consts() -> None:
    document = _fixture(REQUEST)
    bad = copy.deepcopy(document)
    bad["kind"] = "articles"
    _reject(bad, REQUEST)
    install = copy.deepcopy(document)
    install["install_path"] = "wiki/reading-notes"
    _reject(install, REQUEST)
    filt = copy.deepcopy(document)
    filt["paper_filter"] = "sha256:" + "a" * 64
    _reject(filt, REQUEST)
    for path in (
        "wiki/reading-notes/x.md",
        "wiki/meta/articles/heads.json",
        "wiki/reading/../x.md",
        "wiki/reading/x.txt",
    ):
        item = copy.deepcopy(document)
        item["payloads"][0]["path"] = path
        _reject(item, REQUEST)
    mode = copy.deepcopy(document)
    mode["payloads"][0]["mode"] = "append"
    _reject(mode, REQUEST)
    staged = copy.deepcopy(document)
    staged["payloads"][0]["staged_path"] = ".work/r1/reading/x.md"
    _reject(staged, REQUEST)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied, REQUEST)
    written = copy.deepcopy(document)
    written["vault_written"] = True
    _reject(written, REQUEST)
    ranked = copy.deepcopy(document)
    ranked["ranking"] = "ranked"
    _reject(ranked, REQUEST)
    published = copy.deepcopy(document)
    published["publication"] = "published"
    _reject(published, REQUEST)
    wired = copy.deepcopy(document)
    wired["audit_coverage"] = "wired"
    _reject(wired, REQUEST)


def test_inspection_verified_and_next_action() -> None:
    document = _fixture(INSPECTION)
    for key in ("staged_verified", "targets_verified", "basis_verified"):
        bad = copy.deepcopy(document)
        bad[key] = False
        _reject(bad, INSPECTION)
    applied = copy.deepcopy(document)
    applied["applied"] = True
    _reject(applied, INSPECTION)
    later = copy.deepcopy(document)
    later["next_action"] = "apply_requires_later_slice"
    _reject(later, INSPECTION)


def test_apply_result_write_kind_and_coverage() -> None:
    document = _fixture(RESULT)
    not_applied = copy.deepcopy(document)
    not_applied["applied"] = False
    _reject(not_applied, RESULT)
    not_written = copy.deepcopy(document)
    not_written["vault_written"] = False
    _reject(not_written, RESULT)
    for kind in ("work_staging", "transaction"):
        bad = copy.deepcopy(document)
        bad["write_kind"] = kind
        _reject(bad, RESULT)
    notes = copy.deepcopy(document)
    notes["reading_notes_written"] = True
    _reject(notes, RESULT)
    receipt = copy.deepcopy(document)
    receipt["receipt_backed"] = True
    _reject(receipt, RESULT)
    removed = copy.deepcopy(document)
    removed["removed_dirs"] = ["wiki/reading"]
    _reject(removed, RESULT)
    created = copy.deepcopy(document)
    created["created_dirs"] = ["wiki/reading-notes"]
    _reject(created, RESULT)
    publish = copy.deepcopy(document)
    publish["next_action"] = "publish"
    _reject(publish, RESULT)
    empty_applied = copy.deepcopy(document)
    empty_applied["applied_paths"] = []
    validate_document(empty_applied, expected_schema=RESULT)


def test_constant_alignment_with_manifest_and_pages(tmp_path, monkeypatch) -> None:
    assert INSTALL_ROOT == "wiki/reading"
    manifest_schema = schema_by_title("video-paper-wiki.reading-manifest.v1")
    assert manifest_schema["properties"]["install_path"]["const"] == INSTALL_ROOT
    assert MARKER_PREFIX == b"---\ngenerated_by: video-paper-wiki.reading.v1\n"
    world = make_world(tmp_path, monkeypatch)
    _three_chain(world)
    _build(world, "r1")
    root = _reading_root(world, "r1")
    for path in root.rglob("*.md"):
        assert path.read_bytes().startswith(MARKER_PREFIX)
    assert MAX_PAGE_BYTES == reading_view.MAX_PAGE_BYTES
    assert MAX_PAGES == reading_view.MAX_PAGES
    assert MAX_TOTAL_BYTES == reading_view.MAX_TOTAL_BYTES
    pattern = schema_by_title("video-paper-wiki.reading-manifest.v1")["properties"]["pages"]["items"]["properties"][
        "path"
    ]["pattern"]
    stripped = pattern
    suffix = "$(?![" + "\\s\\S" + "])"
    if stripped.endswith(suffix):
        stripped = stripped[: -len(suffix)]
    assert PAGE_RE.pattern == stripped
