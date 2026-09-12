from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from tests.unit.test_catalog_store import material
from video_paper_wiki.catalog_store import DB_RELATIVE, build_catalog_database
from video_paper_wiki.evidence_join import join_evidence
from video_paper_wiki.identity import locator_fingerprint
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence
from video_paper_wiki_research.qa import (
    INDEX_STALE,
    INSUFFICIENT_EVIDENCE,
    INVALID_CITATION,
    NO_RESULTS,
    export_from_question,
    import_and_check,
)
from video_paper_wiki_research.qa_cli import main as qa_main

ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((ROOT / "tests/fixtures/projection-catalog/complete-baseline.json").read_text(encoding="utf-8"))
CLAIM_ID = "clm-6b2c14bc79f44aaa7714"
PAPER_ID = "arxiv:2311.15127"
RESEARCH = ROOT / "src" / "video_paper_wiki_research"


def _baseline_locator() -> dict:
    table = next(item for item in BASELINE["tables"] if item["name"] == "claim_evidence")
    row = next(item for item in table["rows"] if item[0] == CLAIM_ID)
    return decode_ledger_evidence({"source_id": row[2], "relation": row[3], "locator": row[4]})


def evidence_inventory(*, assessment: str = "accepted") -> dict:
    locator = _baseline_locator()
    fingerprint = locator_fingerprint(locator)
    unit_id = "evu-" + hashlib.sha256(
        canonicalize({"paper_id": PAPER_ID, "claim_id": CLAIM_ID, "locator_fingerprint": fingerprint})
    ).hexdigest()[:20]
    return {
        "schema": "video-paper-wiki.evidence-inventory.v1",
        "units": [
            {
                "evidence_unit_id": unit_id,
                "paper_id": PAPER_ID,
                "claim_id": CLAIM_ID,
                "locator_fingerprint": fingerprint,
                "locator": locator,
                "lifecycle": "active",
                "assessment": assessment,
                "core": True,
                "default_eligible": assessment != "deprecated",
                "gold_eligible": assessment in {"accepted", "contested"},
            }
        ],
    }


def catalog_material(*, with_evidence: bool = True, assessment: str = "accepted") -> dict:
    value = material()
    if not with_evidence:
        return value
    inventory = evidence_inventory(assessment=assessment)
    pages = []
    chunks = []
    docs: dict[str, dict] = {}
    for item in value["indexed_pages"]:
        raw = item["bytes"]
        if item["role"] == "paper":
            raw = f"# paper\n\nbody 0\n\n^{CLAIM_ID}\n".encode()
        body = "sha256:" + hashlib.sha256(raw).hexdigest()
        text = raw.decode()
        address = item["page_address"]
        path = item["path"]
        record = {
            "schema_version": 1,
            "page_path": path,
            "page_address": address,
            "chunk_index": 0,
            "raw_text": text,
            "contextualized_text": text,
            "prefix": "",
            "prefix_source": "synthetic",
            "char_count": len(text),
            "body_hash": body,
            "page_body_hash": body,
            "created_at": "2026-09-02T00:00:00Z",
        }
        chunk_path = f".vault-meta/chunks/{address}/chunk-000.json"
        cid = address + ":0"
        pages.append({"path": path, "role": item["role"], "bytes": raw, "paper_id": item["paper_id"], "page_address": address})
        chunks.append({"path": chunk_path, "bytes": canonicalize(record), "record": record})
        docs[cid] = {"path": chunk_path, "body_hash": body, "page_body_hash": body, "dl": 0}
    pages.sort(key=lambda item: item["path"].encode())
    chunks.sort(key=lambda item: item["path"].encode())
    bm25 = {
        "schema_version": 2,
        "params": {"k1": 1.2, "b": 0.75},
        "doc_count": len(docs),
        "avg_dl": 0.0,
        "updated_at": "2026-09-02T00:00:00Z",
        "vocab": {},
        "docs": docs,
    }
    mapping = join_evidence(
        inventory=inventory,
        pages={item["path"]: item["bytes"] for item in pages},
        chunks={item["record"]["page_address"] + ":0": item["record"] for item in chunks},
        bm25=bm25,
    )
    config = copy.deepcopy(value["config"])
    config["generation_sha256"] = mapping["generation_sha256"]
    config["mapping_sha256"] = mapping["mapping_sha256"]
    bm25_raw = json.dumps(bm25, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {
        "base_generation_material": value["base_generation_material"],
        "base_tables": value["base_tables"],
        "mapping": mapping,
        "config": config,
        "indexed_pages": pages,
        "compiled_pages": [
            {"path": item["path"], "compiler_role": item["role"], "bytes": item["bytes"]}
            for item in pages
            if item["role"] != "other"
        ],
        "chunks": chunks,
        "bm25": {"path": ".vault-meta/bm25/index.json", "bytes": b" " + bm25_raw + b"\n", "record": bm25},
        "builder_files": value["builder_files"],
    }


@dataclass
class PlantedCatalog:
    vault: Path
    upstream: Path
    config: dict
    config_path: Path
    material: dict
    hits: list


def plant_catalog(
    tmp_path: Path,
    monkeypatch,
    *,
    with_evidence: bool = True,
    assessment: str = "accepted",
    hits: str = "paper",
) -> PlantedCatalog:
    value = catalog_material(with_evidence=with_evidence, assessment=assessment)
    vault = tmp_path / "vault"
    path = vault / DB_RELATIVE
    path.parent.mkdir(parents=True)
    build_catalog_database(path, value)
    upstream = tmp_path / "upstream"
    (upstream / "scripts").mkdir(parents=True)
    (upstream / "scripts" / "bm25-index.py").write_bytes(b"# pinned-bm25-child\n")
    config_path = tmp_path / "retrieval-config.json"
    config_path.write_text(json.dumps(value["config"], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    planted_hits = []
    if hits == "paper":
        for chunk in value["mapping"]["chunks"]:
            if chunk.get("paper_id") is None:
                continue
            planted_hits.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "score": 1.0,
                    "path": chunk["path"],
                    "body_hash": chunk["body_hash"],
                    "page_body_hash": chunk["page_body_hash"],
                }
            )
    monkeypatch.setattr("video_paper_wiki.catalog_store.verify_upstream", lambda root: Path(root))
    monkeypatch.setattr(
        "video_paper_wiki.catalog_store.bm25_query",
        lambda **_kwargs: list(planted_hits[: _kwargs.get("top", 20)]),
    )
    monkeypatch.setattr("video_paper_wiki.catalog_collector.collect_current_catalog_material", lambda **_kwargs: value)
    return PlantedCatalog(
        vault=vault,
        upstream=upstream,
        config=value["config"],
        config_path=config_path,
        material=value,
        hits=planted_hits,
    )


def _export(env: PlantedCatalog, question: str = "Video Paper") -> dict:
    return export_from_question(
        question=question,
        vault_root=env.vault,
        upstream_root=env.upstream,
        retrieval_config=env.config,
    )


def _valid_answer(context: dict) -> dict:
    unit = context["evidence"][0]
    return {
        "text": f"The method is described in {unit['paper_id']}.",
        "citations": [
            {
                "paper_id": unit["paper_id"],
                "evidence_unit_id": unit["evidence_unit_id"],
                "locator_fingerprint": unit["locator_fingerprint"],
            }
        ],
    }


def test_question_retrieve_export_import_accepts_structural_subset(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    context = _export(env, "Video Paper")
    assert context["ok"] is True
    assert context["kind"] == "qa-context"
    assert context["question"] == "Video Paper"
    identities = json.dumps(context, ensure_ascii=False)
    assert PAPER_ID in identities
    unit = context["evidence"][0]
    assert unit["paper_id"] == PAPER_ID
    assert unit["evidence_unit_id"].startswith("evu-")
    assert unit["locator_fingerprint"]
    assert unit["claim_id"] == CLAIM_ID
    checked = import_and_check(context=context, answer=_valid_answer(context))
    assert checked["ok"] is True
    assert checked["citation_check"] == {"kind": "structural-subset", "accepted": True}
    blob = json.dumps(checked, ensure_ascii=False)
    assert "事实正确性" not in blob
    assert checked["citations"][0]["paper_id"] == PAPER_ID
    assert checked["citations"][0]["evidence_unit_id"] == unit["evidence_unit_id"]


def test_stale_index_is_distinct_and_does_not_invent_hits(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    stale = copy.deepcopy(env.config)
    stale["query_version"] = "changed"
    result = export_from_question(
        question="Video Paper",
        vault_root=env.vault,
        upstream_root=env.upstream,
        retrieval_config=stale,
    )
    assert result["ok"] is False
    assert result["status"] == INDEX_STALE
    assert result["label"] == "旧索引"
    assert result["papers"] == []
    assert result["evidence"] == []
    blob = json.dumps(result, ensure_ascii=False)
    assert PAPER_ID not in blob
    assert "arxiv:0000.00000" not in blob


def test_empty_results_are_distinct_and_non_fabricated(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch, hits="empty")
    result = _export(env)
    assert result["ok"] is False
    assert result["status"] == NO_RESULTS
    assert result["label"] == "无结果"
    assert result["papers"] == []
    assert result["evidence"] == []
    blob = json.dumps(result, ensure_ascii=False)
    assert PAPER_ID not in blob
    assert "openai" not in blob


def test_insufficient_evidence_keeps_retrieved_papers_without_locators(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch, assessment="deprecated")
    result = _export(env)
    assert result["ok"] is False
    assert result["status"] == INSUFFICIENT_EVIDENCE
    assert result["label"] == "证据不足"
    assert [item["paper_id"] for item in result["papers"]] == [PAPER_ID]
    assert result["evidence"] == []


def test_invalid_citation_is_refused_without_adding_invented_papers(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    context = _export(env)
    invented = "arxiv:0000.00000"
    checked = import_and_check(
        context=context,
        answer={"text": "An invented source.", "citations": [{"paper_id": invented, "evidence_unit_id": "evu-" + "0" * 20}]},
    )
    assert checked["ok"] is False
    assert checked["status"] == INVALID_CITATION
    assert checked["label"] == "无效引用"
    assert invented not in [item["paper_id"] for item in checked["papers"]]
    assert invented not in [item["paper_id"] for item in checked["evidence"]]
    assert any(item.get("paper_id") == invented for item in checked["invalid_citations"])
    assert all(item["paper_id"] == PAPER_ID for item in checked["evidence"])


def test_answer_without_citations_is_invalid(tmp_path, monkeypatch) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    context = _export(env)
    checked = import_and_check(context=context, answer={"text": "A claim with no sources."})
    assert checked["status"] == INVALID_CITATION
    assert checked["ok"] is False


def test_shipped_qa_modules_do_not_embed_model_clients() -> None:
    forbidden = ("api_key", "openai", "anthropic", "httpx", "urllib.request")
    for name in ("qa.py", "qa_cli.py"):
        text = (RESEARCH / name).read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text


def test_qa_cli_export_then_import(tmp_path, monkeypatch, capsys) -> None:
    env = plant_catalog(tmp_path, monkeypatch)
    export_code = qa_main(
        [
            "export",
            "--question",
            "Video Paper",
            "--vault-root",
            str(env.vault),
            "--upstream-root",
            str(env.upstream),
            "--config",
            str(env.config_path),
        ]
    )
    exported = json.loads(capsys.readouterr().out)
    assert export_code == 0
    assert exported["ok"] is True
    assert exported["evidence"][0]["paper_id"] == PAPER_ID
    context_path = tmp_path / "qa-context.json"
    answer_path = tmp_path / "qa-answer.json"
    context_path.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")
    answer_path.write_text(json.dumps(_valid_answer(exported), ensure_ascii=False), encoding="utf-8")
    import_code = qa_main(["import", "--context", str(context_path), "--answer", str(answer_path)])
    imported = json.loads(capsys.readouterr().out)
    assert import_code == 0
    assert imported["ok"] is True
    assert imported["citation_check"]["accepted"] is True
    assert "事实正确性" not in json.dumps(imported, ensure_ascii=False)
