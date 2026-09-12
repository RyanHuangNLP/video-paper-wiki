from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.source_publication_fixture import render_proposal
from tests.source_semantics_fixture import fixture, selection
from tests.support import make_checkout
from tests.upstream.test_source_catalog import published, read_catalog
from tests.upstream.test_source_publication import publish
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.source_catalog import build_source_catalog, source_catalog_status
from video_paper_wiki.source_catalog_contracts import KEYS, digest, encode, parse_cache
from video_paper_wiki.source_catalog_projection import assert_projection, project_rows
from video_paper_wiki.source_publication import _vault
from video_paper_wiki.source_semantics_contracts import decision_reference, sha
from video_paper_wiki.source_state import collect_source_state


@pytest.fixture(scope="module")
def catalog_material(tmp_path_factory):
    checkout = tmp_path_factory.mktemp("catalog-contract")
    make_checkout(checkout)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(checkout)
        vault, _, material, arguments = published(checkout)
        group = material["papers"][0]
        association = group["associations"][0]
        chosen = selection(association)
        group["display_decisions"] = [chosen]
        group["record"].update(display_head=decision_reference(chosen),
            active_extraction_path=association["extraction"]["path"],
            active_extraction_sha256=association["extraction"]["sha256"])
        publish(checkout, vault, render_proposal(material, arguments), "select")
        built = build_source_catalog(vault_root=vault, batch_id="catalog")
        with _vault(vault, None) as (root, retained, _):
            state = collect_source_state(retained, audit_integrity(root, _snapshot=retained), require_rendered=True)
        yield checkout, vault, built, read_catalog(built), state


def rehash(doc):
    doc["generation"]["rows_sha256"] = sha(canonicalize(doc["rows"]))
    doc["catalog_sha256"] = digest(doc)
    return canonicalize(doc)


def test_closed_root_nested_objects_and_all_row_shapes(catalog_material):
    original = catalog_material[3]
    assert parse_cache(encode(original)) == original
    mutations = [([], "extra"), (["basis"], "extra"), (["generation"], "extra"),
                 (["generation", "runtime"], "extra"), (["rows"], "extra")]
    mutations += [(["rows", group, 0], "extra") for group, rows in original["rows"].items() if rows]
    for route, field in mutations:
        doc = copy.deepcopy(original)
        target = doc
        for part in route:
            target = target[part]
        target[field] = "unrecognized"
        with pytest.raises(ContractError) as err:
            parse_cache(rehash(doc))
        assert err.value.code == "SOURCE_CATALOG_INVALID"
    for group in KEYS:
        doc = copy.deepcopy(original)
        del doc["rows"][group]
        with pytest.raises(ContractError) as err:
            parse_cache(rehash(doc))
        assert err.value.code == "SOURCE_CATALOG_INVALID"


def test_every_cache_identity_group_rejects_duplicates_without_repair(catalog_material):
    original = copy.deepcopy(catalog_material[3])
    repo = fixture("video-paper-wiki.repo-record.v1")
    original["rows"]["repositories"] = [{**{k: repo[k] for k in
        ("repo_id", "canonical_repository", "canonical_commit", "paper_ids", "officiality", "license")},
        "record_path": "wiki/meta/records/code/synthetic.json", "archived": repo.get("archived")}]
    parse_cache(rehash(original))  # Shape only; this forged repository is never current authority.
    routes = [("rows", group) for group in KEYS]
    routes += [("basis", "inventory"), ("generation", "implementation"), ("generation", "resources")]
    for parent, group in routes:
        assert original[parent][group]
        for mutation in ("duplicate", "reverse"):
            doc = copy.deepcopy(original)
            rows = doc[parent][group]
            if mutation == "reverse" and len(rows) < 2:
                continue
            if mutation == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            else:
                rows.reverse()
            raw = rehash(doc)
            with pytest.raises(ContractError) as err:
                parse_cache(raw)
            assert err.value.code == "SOURCE_CATALOG_INVALID"
            assert raw == canonicalize(doc), "parsing must not sort or repair foreign input"


def test_status_distinguishes_malformed_arrays_from_well_shaped_forgery(catalog_material):
    checkout, vault, built, original, _ = catalog_material
    path = Path(built["cache_path"])
    before = path.read_bytes()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.chdir(checkout)
            for parent, group in (("rows", "documents"), ("basis", "inventory"),
                                  ("generation", "implementation"), ("generation", "resources")):
                for mutation in ("duplicate", "reverse"):
                    doc = copy.deepcopy(original)
                    rows = doc[parent][group]
                    rows.append(copy.deepcopy(rows[0])) if mutation == "duplicate" else rows.reverse()
                    path.write_bytes(rehash(doc))
                    with pytest.raises(ContractError) as err:
                        source_catalog_status(vault_root=vault, batch_id="catalog")
                    assert err.value.code == "SOURCE_CATALOG_INVALID"
            doc = copy.deepcopy(original)
            doc["rows"]["claims"][0]["text"] = "Plausible but forged."
            path.write_bytes(rehash(doc))
            assert source_catalog_status(vault_root=vault, batch_id="catalog")["state"] == "stale"
    finally:
        path.write_bytes(before)


def test_complete_projection_rejects_dropped_rows_and_changed_provenance(catalog_material):
    state = catalog_material[4]
    original = project_rows(state)
    assert_projection(original, state)
    for group, values in original.items():
        if values:
            for mutation in ("drop", "duplicate"):
                rows = copy.deepcopy(original)
                rows[group].pop() if mutation == "drop" else rows[group].append(copy.deepcopy(values[0]))
                with pytest.raises(ContractError) as err:
                    assert_projection(rows, state)
                assert err.value.code == "SOURCE_CATALOG_INVALID"
    for group, field, value in (
        ("claims", "assessment", "accepted"), ("claims", "owner_id", "arxiv:2609.99999"),
        ("claims", "head_event_sha256", "f" * 64), ("evidence", "ordinal", 3),
        ("evidence", "source_id", "src-foreign"), ("evidence", "association_id", None),
        ("papers", "association_ids", []), ("compiled_pages", "text", "Forged page."),
        ("artifacts", "source_ids", ["src-foreign"]), ("documents", "json_text", "{}"),
        ("coverage", "paper_ids", ["arxiv:2609.99999"]),
    ):
        rows = copy.deepcopy(original)
        rows[group][0][field] = value
        with pytest.raises(ContractError) as err:
            assert_projection(rows, state)
        assert err.value.code == "SOURCE_CATALOG_INVALID"


@pytest.mark.parametrize("bound", ["MAX_CACHE", "MAX_DOCUMENT", "MAX_EXCERPT", "MAX_INVENTORY", "MAX_ROWS"])
def test_catalog_limits_refuse_without_truncation(catalog_material, monkeypatch, bound):
    import video_paper_wiki.source_catalog_contracts as contract
    original = copy.deepcopy(catalog_material[3])
    before = canonicalize(original)
    monkeypatch.setattr(contract, bound, 1)
    with pytest.raises(ContractError) as err:
        encode(original)
    assert err.value.code == "SOURCE_CATALOG_LIMIT" and err.value.exit_code == 75
    assert canonicalize(original) == before
