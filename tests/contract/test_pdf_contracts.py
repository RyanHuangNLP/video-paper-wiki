from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.contract.paths import VALID, load_json
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document

TITLES = (
    "video-paper-wiki.pdf-locations.v1",
    "video-paper-wiki.pdf-migration-inventory.v1",
    "video-paper-wiki.pdf-upload-manifest.v1",
    "video-paper-wiki.pdf-link-plan.v1",
    "video-paper-wiki.pdf-migration-report.v1",
    "video-paper-wiki.pdf-bind-request.v1",
    "video-paper-wiki.pdf-bind-plan.v1",
    "video-paper-wiki.pdf-binding.v1",
)


@pytest.mark.parametrize("title", TITLES)
def test_pdf_schema_titles_resolve_and_reject_extra_fields(title: str) -> None:
    schema = schema_by_title(title)
    assert schema["title"] == title
    document = load_json(VALID / f"{title}.json")
    validate_document(document, expected_schema=title)
    invalid = copy.deepcopy(document)
    invalid["unexpected_field"] = True
    with pytest.raises(ContractError) as exc:
        validate_document(invalid, expected_schema=title)
    assert exc.value.code == "SCHEMA_INVALID"


def test_package_ships_pdf_schemas() -> None:
    from video_paper_wiki.resources import schema_resource_names

    names = schema_resource_names()
    for title in TITLES:
        assert f"{title}.schema.json" in names


def test_sample_agy_fixtures_validate() -> None:
    root = Path("tests/fixtures/pdf-migration")
    inventory = load_json(root / "sample-inventory.json")
    manifest = load_json(root / "sample-uploaded-manifest.json")
    validate_document(inventory, "video-paper-wiki.pdf-migration-inventory.v1")
    validate_document(manifest, "video-paper-wiki.pdf-upload-manifest.v1")
    assert manifest["inventory_sha256"] == inventory["inventory_sha256"]
