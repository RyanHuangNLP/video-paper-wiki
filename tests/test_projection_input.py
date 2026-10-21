from __future__ import annotations

import copy, json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.projection_input import validate_projection_bytes, validate_projection_inventory

FIXTURE = Path(__file__).parent / "fixtures/projection-input/minimal.json"


def inventory() -> dict:
    return json.loads(FIXTURE.read_text())


def test_minimal_inventory_and_complete_bytes() -> None:
    value = inventory()
    assert validate_projection_inventory(value) is None
    assert validate_projection_bytes(value, bytes_map={x["path"]: b"" for x in value["entries"]}) is None


def test_all_thirteen_inventory_branches() -> None:
    h="a"*64
    extra=[
      ("wiki/meta/records/papers/p.json","paper-record","0"*64),("wiki/meta/records/repos/r.json","repo-record","1"*64),
      ("wiki/meta/reviews/clm-"+"a"*20+"/ase-"+"b"*20+".json","assessment-event","2"*64),
      (f".raw/captured/{h}.pdf","captured-artifact",h),(f".raw/derived/{h}/docling/{h}/document.json","docling-document","3"*64),
      (f".raw/derived/{h}/docling/{h}/parser-config.json","parser-config","4"*64),(f".raw/derived/{h}/docling/{h}/model-manifest.json","model-manifest","5"*64),
      (f".raw/derived/{h}/runs/run-1.json","run-manifest","6"*64),(f".raw/derived/code-manifests/{h}.json","code-evidence-manifest",h),
      (f".raw/derived/alignment-manifests/{h}.json","alignment-manifest",h)]
    value=inventory(); value["entries"] += [{"path":p,"kind":k,"sha256":d,"size_bytes":0} for p,k,d in extra]
    value["entries"].sort(key=lambda x:x["path"].encode())
    validate_projection_inventory(value)
    assert {x["kind"] for x in value["entries"]} == {"source-ledger","claim-ledger","taxonomy","paper-record","repo-record","assessment-event","captured-artifact","docling-document","parser-config","model-manifest","run-manifest","code-evidence-manifest","alignment-manifest"}


def test_portable_alias_collision_is_rejected() -> None:
    value=inventory(); value["entries"] += [
      {"path":"wiki/meta/records/papers/A.json","kind":"paper-record","sha256":"0"*64,"size_bytes":0},
      {"path":"wiki/meta/records/papers/a.json","kind":"paper-record","sha256":"1"*64,"size_bytes":0}]
    value["entries"].sort(key=lambda x:x["path"].encode())
    with pytest.raises(ContractError) as exc:validate_projection_inventory(value)
    assert exc.value.code=="PROJECTION_INPUT_INVALID"


@pytest.mark.parametrize("change", ["order", "bool", "lf", "missing", "extra"])
def test_inventory_refuses_shape_and_order_edges(change: str) -> None:
    value = inventory()
    if change == "order": value["entries"].reverse()
    elif change == "bool": value["entries"][0]["size_bytes"] = False
    elif change == "lf": value["entries"][0]["sha256"] += "\n"
    elif change == "missing": value["entries"] = value["entries"][1:]
    else: value["extra"] = True
    with pytest.raises(ContractError) as exc: validate_projection_inventory(value)
    assert exc.value.code in {"SCHEMA_INVALID", "PROJECTION_INPUT_INVALID"}


def test_byte_map_scan_precedes_hash_and_isolation() -> None:
    value = inventory(); byte_map = {x["path"]: b"" for x in value["entries"]}
    wrong = dict(byte_map); wrong["extra"] = object()
    with pytest.raises(ContractError) as exc: validate_projection_bytes(value, bytes_map=wrong)
    assert exc.value.code == "PROJECTION_INPUT_MISMATCH"
    validate_projection_bytes(value, bytes_map=byte_map)
    value["entries"].clear(); byte_map.clear()


def test_non_string_root_key_and_cycle_are_typed() -> None:
    value = inventory(); value[1] = True
    with pytest.raises(ContractError) as exc: validate_projection_inventory(value)
    assert exc.value.code == "SCHEMA_INVALID"
    cyclic = {}; cyclic["schema"] = "video-paper-wiki.projection-input.v1"; cyclic["entries"] = cyclic
    with pytest.raises(ContractError) as exc: validate_projection_inventory(cyclic)
    assert exc.value.code == "SCHEMA_INVALID"
