from __future__ import annotations

import copy, hashlib, json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
import video_paper_wiki.projection_catalog as catalog_module
from video_paper_wiki.projection_catalog import SEMANTIC_CHECK_IDS, canonical_catalog_rows, catalog_rows_sha256
from tests.test_projection_generation import material

ROOT=Path(__file__).resolve().parents[1]


def complete_catalog() -> tuple[dict, list[dict]]:
    document=json.loads((ROOT/"tests/fixtures/projection-catalog/complete-baseline.json").read_text())
    return document["generation_material"],document["tables"]


def table(tables: list[dict], name: str) -> dict:
    return next(item for item in tables if item["name"]==name)


def minimal_tables() -> list[dict]:
    manifest=json.loads((ROOT/"catalog/base-catalog-v1.columns.json").read_text())
    tables={t["name"]:{"name":t["name"],"columns":[c["name"] for c in t["columns"]],"rows":[]} for t in manifest["tables"]}
    def add(name,**row): tables[name]["rows"].append([row[x] for x in tables[name]["columns"]])
    generation=material(); inputs=generation["inventory"]["entries"]
    for x in inputs:add("canonical_inputs",path=x["path"],kind=x["kind"],file_sha256=x["sha256"],size_bytes=x["size_bytes"])
    add("ledger_meta",ledger_kind="source",input_path="wiki/meta/ledgers/source-ledger.json",schema="claude-obsidian.source-ledger.v1",generated_at="2026-01-01T00:00:00Z")
    add("ledger_meta",ledger_kind="claim",input_path="wiki/meta/ledgers/claim-ledger.json",schema="claude-obsidian.claim-ledger.v1",generated_at="2026-01-01T00:00:00Z")
    taxonomy=json.loads((ROOT/"taxonomy/v1.json").read_text()); policy=taxonomy["policy"]
    add("taxonomy_meta",input_path="taxonomy/v1.json",version=taxonomy["version"],unknown_terms=policy["unknown_terms"],silent_create=int(policy["silent_create"]),statement_en=policy["statement_en"],statement_zh=policy["statement_zh"])
    for ai,axis in enumerate(taxonomy["axes"]):
        add("taxonomy_axes",axis=axis["slug"],taxonomy_path="taxonomy/v1.json",ordinal=ai,label_zh=axis["label_zh"],label_en=axis["label_en"])
        for i,value in enumerate(axis["aliases"]):add("taxonomy_axis_aliases",axis=axis["slug"],ordinal=i,alias=value)
        for ti,term in enumerate(axis["terms"]):
            add("taxonomy_terms",axis=axis["slug"],slug=term["slug"],ordinal=ti,label_zh=term["label_zh"],status=term["status"])
            for i,value in enumerate(term["aliases"]):add("taxonomy_term_aliases",axis=axis["slug"],slug=term["slug"],ordinal=i,alias=value)
    return list(reversed(list(tables.values())))


def test_minimal_catalog_is_canonical_and_order_independent() -> None:
    generation=material(); tables=minimal_tables(); raw=canonical_catalog_rows(generation_material=generation,tables=tables)
    parsed=json.loads(raw); assert parsed["schema"]=="video-paper-wiki.catalog-rows.v1"
    assert [x["name"] for x in parsed["tables"]]==sorted(x["name"] for x in tables)
    assert hashlib.sha256(raw).hexdigest()==catalog_rows_sha256(generation_material=generation,tables=list(reversed(tables)))
    assert hashlib.sha256(raw).hexdigest()==(ROOT/"tests/fixtures/projection-catalog/minimal.sha256").read_text().strip()
    assert not raw.endswith(b"\n")


def test_all_twenty_five_semantic_ids_are_bound_in_frozen_order() -> None:
    manifest=json.loads((ROOT/"catalog/base-catalog-v1.columns.json").read_text())
    assert tuple(x["id"] for x in manifest["semantic_checks"])==SEMANTIC_CHECK_IDS
    assert len(SEMANTIC_CHECK_IDS)==25==len(set(SEMANTIC_CHECK_IDS))


@pytest.mark.parametrize("table,column,value", [
    ("ledger_meta","generated_at","2026-01-01T00:00:00.1Z"),
    ("taxonomy_axes","label_zh",""),
    ("taxonomy_terms","status","draft"),
])
def test_semantic_profile_refusals(table: str,column: str,value: object) -> None:
    generation=material(); tables=minimal_tables(); item=next(x for x in tables if x["name"]==table)
    item["rows"][0][item["columns"].index(column)]=value
    with pytest.raises(ContractError) as exc:canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


@pytest.mark.parametrize("mutation", ["missing-table","bad-columns","bool","duplicate-pk","bad-fk"])
def test_catalog_structural_refusals(mutation: str) -> None:
    generation=material(); tables=minimal_tables()
    by={x["name"]:x for x in tables}
    if mutation=="missing-table": tables.pop()
    elif mutation=="bad-columns": by["ledger_meta"]["columns"].reverse()
    elif mutation=="bool": by["canonical_inputs"]["rows"][0][3]=False
    elif mutation=="duplicate-pk": by["ledger_meta"]["rows"].append(copy.deepcopy(by["ledger_meta"]["rows"][0]))
    else: by["ledger_meta"]["rows"][0][1]="missing"
    with pytest.raises(ContractError) as exc: canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


def test_honest_inventory_can_pair_with_forged_rows_only_if_structurally_consistent() -> None:
    generation=material(); tables=minimal_tables(); by={x["name"]:x for x in tables}
    # The pure layer detects declared inventory disagreement, while it intentionally
    # has no byte map from which to prove the remaining row values were derived.
    by["canonical_inputs"]["rows"][0][2]="f"*64
    with pytest.raises(ContractError) as exc: canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


def test_caller_mutation_after_return_cannot_change_prior_bytes() -> None:
    generation=material(); tables=minimal_tables(); before=canonical_catalog_rows(generation_material=generation,tables=tables)
    tables.clear(); generation.clear(); assert json.loads(before)["schema"]=="video-paper-wiki.catalog-rows.v1"


def test_catalog_api_has_no_sqlite_dependency() -> None:
    source=(ROOT/"src/video_paper_wiki/projection_catalog.py").read_text()
    assert "import sqlite3" not in source and "from sqlite3" not in source


def test_complete_catalog_separates_file_and_self_excluding_manifest_hashes() -> None:
    generation,tables=complete_catalog(); code=table(tables,"code_manifests")
    row=dict(zip(code["columns"],code["rows"][0]))
    inventory=next(item for item in generation["inventory"]["entries"] if item["path"]==row["input_path"])
    assert inventory["sha256"]!=row["manifest_sha256"]
    raw=canonical_catalog_rows(generation_material=generation,tables=tables)
    assert hashlib.sha256(raw).hexdigest()=="bf9194056f58ff6b9160f752138c3071c8eef8a1de36b2e26492f1a282b43d02"
    code["rows"][0][code["columns"].index("manifest_sha256")]="a"*64
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


class _DictSubclass(dict):
    pass


@pytest.mark.parametrize("bad",["cycle","surrogate","subclass"])
def test_catalog_wrapper_classifies_generation_preflight_by_subtree(bad: str) -> None:
    generation=material(); tables=minimal_tables()
    if bad=="cycle":
        cycle={}; cycle["again"]=cycle; generation["profile"]=cycle
    elif bad=="surrogate": generation["profile"]="\ud800"
    else: generation=_DictSubclass(generation)
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="PROJECTION_GENERATION_INVALID"


@pytest.mark.parametrize("bad",["cycle","surrogate","subclass"])
def test_catalog_wrapper_classifies_table_preflight_by_subtree(bad: str) -> None:
    generation=material(); tables=minimal_tables()
    if bad=="cycle":
        cycle={}; cycle["again"]=cycle; tables.append(cycle)
    elif bad=="surrogate": tables[0]["name"]="\ud800"
    else: tables=_ListSubclass(tables)
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


class _ListSubclass(list):
    pass


def test_public_phase_limits_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    def limited(_value):
        raise ContractError("PROJECTION_LIMIT_EXCEEDED","limited",{"instance_pointer":"/generation_material"})
    monkeypatch.setattr(catalog_module,"_preflight",limited)
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material={},tables=[])
    assert exc.value.code=="PROJECTION_LIMIT_EXCEEDED"


def test_generation_phase_limit_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    def limited(_value):
        raise ContractError("PROJECTION_LIMIT_EXCEEDED","limited",{"instance_pointer":""})
    monkeypatch.setattr(catalog_module,"projection_generation_sha256",limited)
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=material(),tables=minimal_tables())
    assert exc.value.code=="PROJECTION_LIMIT_EXCEEDED"


def test_semantic_locator_local_limit_is_catalog_rows_invalid() -> None:
    generation,tables=complete_catalog(); evidence=table(tables,"claim_evidence")
    evidence["rows"][0][evidence["columns"].index("locator_wire")]="x"*65537
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.code=="CATALOG_ROWS_INVALID"


def test_collection_phase_wins_over_cell_phase() -> None:
    generation=material(); tables=minimal_tables(); tables.remove(table(tables,"taxonomy_terms"))
    item=table(tables,"canonical_inputs"); item["rows"][0][item["columns"].index("size_bytes")]=False
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.message=="complete table set is required"


def test_cell_winner_uses_manifest_order_under_caller_reversal() -> None:
    def failure(reverse: bool) -> tuple[str,str,str]:
        generation=material(); tables=minimal_tables()
        for name in ("canonical_inputs","ledger_meta"):
            item=table(tables,name); item["rows"][0][0]=False
        if reverse: tables.reverse()
        with pytest.raises(ContractError) as exc:
            canonical_catalog_rows(generation_material=generation,tables=tables)
        pointer=exc.value.details["instance_pointer"]
        winning=tables[int(pointer.split("/")[2])]["name"]
        return exc.value.code,exc.value.message,winning
    assert failure(False)==failure(True)==("CATALOG_ROWS_INVALID","TEXT cell is not exact string","canonical_inputs")


def test_presence_phase_wins_over_duplicate_primary_key() -> None:
    generation,tables=complete_catalog(); claims=table(tables,"claims")
    row=claims["rows"][0]; row[claims["columns"].index("location_anchor") ]="anchor"
    claims["rows"].append(copy.deepcopy(row))
    with pytest.raises(ContractError) as exc:
        canonical_catalog_rows(generation_material=generation,tables=tables)
    assert exc.value.message=="presence pair is inconsistent"


def test_valid_row_permutations_remain_byte_identical() -> None:
    generation,tables=complete_catalog(); expected=canonical_catalog_rows(generation_material=generation,tables=tables)
    tables.reverse()
    for item in tables: item["rows"].reverse()
    assert canonical_catalog_rows(generation_material=generation,tables=tables)==expected
