from __future__ import annotations

import copy, hashlib, json
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.projection_generation import projection_generation_sha256, projection_is_stale

ROOT = Path(__file__).resolve().parents[1]


def material(version: str = "3.13.13") -> dict:
    profile = json.loads((ROOT / "catalog/base-catalog-v1.generation-profile.json").read_text())
    zero = "0" * 64
    taxonomy_sha = hashlib.sha256((ROOT / "taxonomy/v1.json").read_bytes()).hexdigest()
    entries = [
        {"path": "taxonomy/v1.json", "kind": "taxonomy", "sha256": taxonomy_sha, "size_bytes": 0},
        {"path": "wiki/meta/ledgers/claim-ledger.json", "kind": "claim-ledger", "sha256": zero, "size_bytes": 0},
        {"path": "wiki/meta/ledgers/source-ledger.json", "kind": "source-ledger", "sha256": zero, "size_bytes": 0},
    ]
    def files(names):
        result=[]
        for name in names:
            digest=zero
            if name == "video_paper_wiki/taxonomy/v1.json": digest=taxonomy_sha
            elif name.endswith("base-catalog-v1.sql"): digest=hashlib.sha256((ROOT/"catalog/base-catalog-v1.sql").read_bytes()).hexdigest()
            elif name.endswith("base-catalog-v1.columns.json"): digest=hashlib.sha256((ROOT/"catalog/base-catalog-v1.columns.json").read_bytes()).hexdigest()
            elif name.endswith("base-catalog-v1.generation-profile.json"): digest=hashlib.sha256((ROOT/"catalog/base-catalog-v1.generation-profile.json").read_bytes()).hexdigest()
            result.append({"path":name,"sha256":digest})
        return result
    pair=next(x for x in profile["runtime"]["accepted_exact_pairs"] if x["python_version"]==version)
    deps=next(x for x in profile["dependencies"]["accepted_exact_sets"] if x["python_version"]==version)
    return {"schema":"video-paper-wiki.projection-generation.v1","profile":"base-catalog-v1",
            "inventory":{"schema":"video-paper-wiki.projection-input.v1","entries":entries},
            "implementation":{"package_version":"0.1.0","files":files(profile["implementation"]["files"])},
            "resources":{"files":files(profile["resources"]["files"])},
            "dependencies":{"profile":profile["dependencies"]["profile"],"distributions":deps["distributions"]},
            "upstream":{"commit":profile["upstream"]["commit"],"version":profile["upstream"]["version"],"files":files(profile["upstream"]["files"])},
            "runtime":{"python_implementation":"CPython","python_version":version,"unicode_version":pair["unicode_version"],
                       "prefix_mode":"synthetic","chunk_profile":"claude-obsidian.chunk.v1","bm25_profile":"claude-obsidian.bm25.v2"}}


@pytest.mark.parametrize("version,count", [("3.12.14",6),("3.13.13",5),("3.13.15",5)])
def test_all_runtime_dependency_profiles(version: str, count: int) -> None:
    value=material(version); assert len(value["dependencies"]["distributions"])==count
    assert len(projection_generation_sha256(value))==64


def test_generation_hash_stability_and_stale_order() -> None:
    value=material(); clone=copy.deepcopy(value)
    golden=(ROOT/"tests/fixtures/projection-generation/minimal.sha256").read_text().strip()
    assert projection_generation_sha256(value)==projection_generation_sha256(clone)==golden
    assert projection_is_stale(current=value,stored=clone) is False
    assert projection_is_stale(current=value,stored=None) is True
    clone["implementation"]["files"][0]["sha256"]="1"*64
    assert projection_is_stale(current=value,stored=clone) is True


@pytest.mark.parametrize("part", ["runtime","dependencies","resources","implementation","upstream"])
def test_generation_closed_profiles(part: str) -> None:
    value=material()
    if part=="runtime": value[part]["python_version"]="3.13.14"
    elif part=="dependencies": value[part]["distributions"].reverse()
    else: value[part]["files"].reverse()
    with pytest.raises(ContractError) as exc: projection_generation_sha256(value)
    assert exc.value.code=="PROJECTION_GENERATION_INVALID"


def test_current_validation_precedes_stored_none() -> None:
    value=material(); value["runtime"]["python_version"]="bad"
    with pytest.raises(ContractError): projection_is_stale(current=value,stored=None)


def test_nonjson_and_cycle_are_typed() -> None:
    with pytest.raises(ContractError) as exc: projection_generation_sha256({1:True})
    assert exc.value.code=="PROJECTION_GENERATION_INVALID"
    value=material(); value["loop"]=value
    with pytest.raises(ContractError) as exc: projection_generation_sha256(value)
    assert exc.value.code=="PROJECTION_GENERATION_INVALID"


def test_fixed_resource_mismatch_has_dedicated_error(monkeypatch) -> None:
    monkeypatch.setattr("video_paper_wiki.projection_generation.read_projection_resource_bytes",lambda *_:None)
    with pytest.raises(ContractError) as exc:projection_generation_sha256(material())
    assert exc.value.code=="CATALOG_RESOURCE_MISMATCH"
