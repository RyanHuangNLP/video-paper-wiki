"""Build a disposable search catalog from receipt-backed publication records.

Canonical paper/concept pages still require accepted core claims. This adapter
indexes published records, claims, and locators for QA/writing without planting
the projection-catalog baseline or forging a human assessment.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.catalog_collector import (
    _add,
    _alignment,
    _code,
    _document,
    _event,
    _generation,
    _kind,
    _ledgers,
    _paper,
    _repo,
    _row_tables,
    _run,
    _sha,
    _taxonomy,
)
from video_paper_wiki.catalog_store import DB_RELATIVE, build_catalog_database
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.evidence_join import join_evidence, validate_evidence_inventory
from video_paper_wiki.identity import locator_fingerprint, paper_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence
from video_paper_wiki.projection_input import validate_projection_bytes
from video_paper_wiki.projection_runtime import parse_projection_json, validate_runtime_record
from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory, audit_integrity
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.retrieval import validate_retrieval_config
from video_paper_wiki.secure_io import parse_strict_json

from video_paper_wiki_research.contracts import ResearchError

INDEX_UNAVAILABLE = "INDEX_UNAVAILABLE"
STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have he her him his i if in is it its
    of on or that the their them they this to was were will with you your
    """.split()
)
_TOKEN = re.compile(r"\w[\w'\-]*", re.UNICODE)


def _fail(message: str, *, code: str = "CATALOG_INPUT_INVALID") -> None:
    raise ContractError(code, message)


def _terms(text: str) -> list[str]:
    terms: list[str] = []
    normalized = unicodedata.normalize("NFKC", text)
    for match in _TOKEN.finditer(normalized):
        token = match.group(0).lower().strip("'_-")
        if len(token) > 1 and token not in STOPWORDS:
            terms.append(token)
    return terms


def _preview_page(*, record: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> bytes:
    title = str(record.get("title_zh") or record["title"])
    lines = [
        f"# {title}",
        "",
        f"paper_id: {record['paper_id']}",
        "",
        "## Claims",
        "",
    ]
    for claim in claims:
        lines.append(f"- {claim['canonical_claim_text']}  ^{claim['claim_id']}")
    lines.append("")
    return unicodedata.normalize("NFC", "\n".join(lines)).encode("utf-8")


def _inventory(compile_papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in compile_papers:
        record = item["record"]
        refs = {row["claim_id"]: row for row in record["section_claim_refs"]}
        heads = derive_assessment_heads(claims=item["claims"], events=item["events"])
        events = {row["event_id"]: row for row in item["events"]}
        for claim in item["claims"]:
            cid = claim["claim_id"]
            ref = refs[cid]
            event = events[heads[cid]]
            for locator in claim["evidence"]:
                fingerprint = locator_fingerprint(locator)
                unit_id = "evu-" + hashlib.sha256(
                    canonicalize(
                        {
                            "paper_id": record["paper_id"],
                            "claim_id": cid,
                            "locator_fingerprint": fingerprint,
                        }
                    )
                ).hexdigest()[:20]
                if unit_id in seen:
                    _fail("duplicate evidence unit")
                seen.add(unit_id)
                units.append(
                    {
                        "evidence_unit_id": unit_id,
                        "paper_id": record["paper_id"],
                        "claim_id": cid,
                        "locator_fingerprint": fingerprint,
                        "locator": locator,
                        "core": bool(ref["core"]),
                        "lifecycle": ref["lifecycle"],
                        "assessment": event["to_assessment"],
                        "default_eligible": ref["lifecycle"] == "active"
                        and event["to_assessment"] != "deprecated",
                        "gold_eligible": ref["lifecycle"] == "active"
                        and bool(ref["core"])
                        and event["to_assessment"] in {"accepted", "contested"},
                    }
                )
    return validate_evidence_inventory(
        {
            "schema": "video-paper-wiki.evidence-inventory.v1",
            "units": sorted(units, key=lambda item: item["evidence_unit_id"]),
        }
    )


def _builder_files() -> list[dict[str, str]]:
    src = Path(__file__).resolve().parent.parent / "video_paper_wiki"
    names = (
        "video_paper_wiki/catalog_collector.py",
        "video_paper_wiki/catalog_reporting.py",
        "video_paper_wiki/catalog_store.py",
    )
    files = [
        {"path": name, "sha256": _sha((src / name.removeprefix("video_paper_wiki/")).read_bytes())}
        for name in names
    ]
    files.sort(key=lambda item: item["path"].encode())
    return files


def _load_canonical(vault: Path, upstream: Path) -> dict[str, Any]:
    snap = _Snapshot(vault)
    try:
        audit_integrity(vault, _snapshot=snap)
        actual = _walk_inventory(snap, read_bytes=True)
        tax = read_projection_resource_bytes("taxonomy", "v1.json")
        if tax is None:
            _fail("taxonomy resource is unavailable")
        byte_map = {path: snap.files[path][1] for path in sorted(actual) if _kind(path) is not None}
        byte_map["taxonomy/v1.json"] = tax
        entries = [
            {"path": path, "kind": _kind(path) or "taxonomy", "sha256": _sha(raw), "size_bytes": len(raw)}
            for path, raw in sorted(byte_map.items())
        ]
        inventory = {"schema": "video-paper-wiki.projection-input.v1", "entries": entries}
        validate_projection_bytes(inventory, bytes_map=byte_map)
        rows = _row_tables()
        _taxonomy(rows, tax)
        source = parse_strict_json(byte_map["wiki/meta/ledgers/source-ledger.json"], invalid_code="CATALOG_INPUT_INVALID")
        claim = parse_strict_json(byte_map["wiki/meta/ledgers/claim-ledger.json"], invalid_code="CATALOG_INPUT_INVALID")
        _ledgers(rows, source, claim)
        papers: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        codes: list[dict[str, Any]] = []
        repos: dict[str, dict[str, Any]] = {}
        alignments: list[dict[str, Any]] = []
        for entry in entries:
            path, kind = entry["path"], entry["kind"]
            if kind in {
                "paper-record",
                "repo-record",
                "assessment-event",
                "run-manifest",
                "code-evidence-manifest",
                "alignment-manifest",
            }:
                title = {
                    "paper-record": "video-paper-wiki.paper-record.v1",
                    "repo-record": "video-paper-wiki.repo-record.v1",
                    "assessment-event": "video-paper-wiki.assessment-event.v1",
                    "run-manifest": "video-paper-wiki.run-manifest.v1",
                    "code-evidence-manifest": "video-paper-wiki.code-evidence-manifest.v1",
                    "alignment-manifest": "video-paper-wiki.paper-code-alignment.v1",
                }[kind]
                doc = _document(byte_map[path], title)
                if kind == "paper-record":
                    _paper(rows, path, doc)
                    papers.append(doc)
                elif kind == "repo-record":
                    _repo(rows, path, doc)
                    repos[doc["repo_id"]] = doc
                elif kind == "assessment-event":
                    _event(rows, path, doc)
                    events.append(doc)
                elif kind == "code-evidence-manifest":
                    _code(rows, path, doc)
                    codes.append(doc)
                elif kind == "alignment-manifest":
                    _alignment(rows, path, doc)
                    alignments.append(doc)
                else:
                    _run(rows, path, doc)
            if kind in {"captured-artifact", "docling-document", "parser-config", "model-manifest"}:
                _add(
                    rows,
                    "artifacts",
                    artifact_path=path,
                    artifact_kind=kind,
                    file_sha256=entry["sha256"],
                    size_bytes=entry["size_bytes"],
                )
        for entry in entries:
            _add(
                rows,
                "canonical_inputs",
                path=entry["path"],
                kind=entry["kind"],
                file_sha256=entry["sha256"],
                size_bytes=entry["size_bytes"],
            )
        paper_pages = {
            "paper:" + paper["paper_id"]: "wiki/papers/" + paper_page_slug(paper["paper_id"]) + ".md"
            for paper in papers
        }
        refs = {row["claim_id"]: row for row in rows["claim_refs"]}
        for row in rows["claims"]:
            owner = refs.get(row["claim_id"])
            if owner is not None and owner["subject_id"] in paper_pages:
                row["location_path"] = paper_pages[owner["subject_id"]]
        claims: list[dict[str, Any]] = []
        for cid, item in sorted(claim["claims"].items()):
            if cid not in refs:
                continue
            claims.append(
                {
                    "claim_id": cid,
                    "stable_subject_id": refs[cid]["subject_id"],
                    "canonical_claim_text": item["text"],
                    "evidence": [decode_ledger_evidence(row) for row in item["evidence"]],
                    "assessment": item["assessment"],
                    "reviewed_at": item.get("reviewed_at"),
                }
            )
        heads = derive_assessment_heads(claims=claims, events=events)
        for cid, eid in sorted(heads.items()):
            _add(rows, "assessment_heads", claim_id=cid, head_event_id=eid)
        compile_papers = []
        for paper in papers:
            owned = [row for row in claims if row["stable_subject_id"] == "paper:" + paper["paper_id"]]
            compile_papers.append(
                {
                    "record": paper,
                    "claims": owned,
                    "events": [event for event in events if event["claim_id"] in {row["claim_id"] for row in owned}],
                }
            )
        generation = _generation(inventory, upstream)
        snap.verify()
        return {
            "rows": rows,
            "papers": papers,
            "compile_papers": compile_papers,
            "generation": generation,
        }
    finally:
        snap.close()


def _config_from_mapping(mapping: Mapping[str, Any], supplied: object | None) -> dict[str, Any]:
    base = {
        "schema": "video-paper-wiki.retrieval-config.v1",
        "corpus_version": "published-research-v1",
        "query_version": "published-research-v1",
        "top_chunks": 10,
        "top_papers": 10,
        "evidence_limit": 8,
        "per_paper_evidence_limit": 2,
        "generation_sha256": mapping["generation_sha256"],
        "mapping_sha256": mapping["mapping_sha256"],
        "eligibility": "active-not-deprecated",
        "paper_tie_break": "score-desc-paper-id-asc",
        "chunk_tie_break": "score-desc-paper-id-asc-chunk-id-asc",
    }
    if supplied is None:
        return validate_retrieval_config(base)
    if isinstance(supplied, (str, Path)):
        raw = parse_strict_json(Path(supplied).read_bytes(), invalid_code="CATALOG_STALE")
        value = validate_retrieval_config(raw)
    else:
        value = validate_retrieval_config(dict(supplied))
    if value["generation_sha256"] != mapping["generation_sha256"] or value["mapping_sha256"] != mapping["mapping_sha256"]:
        _fail("retrieval config does not bind the published mapping", code="RETRIEVAL_GENERATION_MISMATCH")
    return value


def _material_from_records(
    *,
    vault: Path,
    upstream: Path,
    retrieval_config: object,
    chunks: list[dict[str, Any]],
    bm25: dict[str, Any],
) -> dict[str, Any]:
    canonical = _load_canonical(vault, upstream)
    if not canonical["compile_papers"]:
        _fail("published paper records are missing")
    inventory = _inventory(canonical["compile_papers"])
    pages: list[dict[str, Any]] = []
    compiled: list[dict[str, Any]] = []
    page_bytes: dict[str, bytes] = {}
    chunk_records: dict[str, dict[str, Any]] = {}
    for item in canonical["compile_papers"]:
        record = item["record"]
        path = "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md"
        raw = _preview_page(record=record, claims=item["claims"])
        address = "syn-" + hashlib.sha256(path.encode("utf-8")).hexdigest()
        pages.append(
            {
                "path": path,
                "role": "paper",
                "bytes": raw,
                "paper_id": record["paper_id"],
                "page_address": address,
            }
        )
        compiled.append({"path": path, "compiler_role": "paper", "bytes": raw})
        page_bytes[path] = raw
    pages.sort(key=lambda item: item["path"].encode())
    compiled.sort(key=lambda item: item["path"].encode())
    for item in chunks:
        record = validate_runtime_record("chunk", item["record"])
        chunk_records[f"{record['page_address']}:{record['chunk_index']}"] = record
    mapping = join_evidence(
        inventory=inventory,
        pages=page_bytes,
        chunks=chunk_records,
        bm25=bm25["record"],
    )
    cfg = _config_from_mapping(mapping, retrieval_config)
    tables = []
    manifest = json.loads(read_projection_resource_bytes("catalog", "base-catalog-v1.columns.json"))
    rows = canonical["rows"]
    for definition in manifest["tables"]:
        cols = [col["name"] for col in definition["columns"]]
        tables.append(
            {
                "name": definition["name"],
                "columns": cols,
                "rows": [[row.get(col) for col in cols] for row in rows[definition["name"]]],
            }
        )
    return {
        "base_generation_material": canonical["generation"],
        "base_tables": tables,
        "mapping": mapping,
        "config": cfg,
        "indexed_pages": pages,
        "compiled_pages": compiled,
        "chunks": sorted(chunks, key=lambda item: item["path"].encode()),
        "bm25": bm25,
        "builder_files": _builder_files(),
    }


def _chunk_and_index(compile_papers: Sequence[Mapping[str, Any]], *, created_at: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    docs: dict[str, dict[str, Any]] = {}
    df: Counter[str] = Counter()
    postings: dict[str, list[list[object]]] = defaultdict(list)
    for item in compile_papers:
        record = item["record"]
        path = "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md"
        raw = _preview_page(record=record, claims=item["claims"])
        text = raw.decode("utf-8")
        if len(text) > 4000:
            _fail("published preview page exceeds the chunk text budget")
        address = "syn-" + hashlib.sha256(path.encode("utf-8")).hexdigest()
        body = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        page_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
        chunk_record = {
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
            "page_body_hash": page_hash,
            "created_at": created_at,
        }
        chunk_record = validate_runtime_record("chunk", chunk_record)
        chunk_path = f".vault-meta/chunks/{address}/chunk-000.json"
        chunk_bytes = canonicalize(chunk_record)
        chunks.append({"path": chunk_path, "bytes": chunk_bytes, "record": chunk_record})
        cid = address + ":0"
        terms = _terms(text)
        docs[cid] = {"path": chunk_path, "dl": len(terms), "body_hash": body, "page_body_hash": page_hash}
        tf = Counter(terms)
        for term, count in tf.items():
            df[term] += 1
            postings[term].append([cid, count])
    chunks.sort(key=lambda item: item["path"].encode())
    avg_dl = (sum(item["dl"] for item in docs.values()) / len(docs)) if docs else 0.0
    vocab = {term: {"df": df[term], "postings": postings[term]} for term in sorted(df)}
    bm25_record = {
        "schema_version": 2,
        "params": {"k1": 1.5, "b": 0.75},
        "doc_count": len(docs),
        "avg_dl": avg_dl,
        "updated_at": created_at,
        "vocab": vocab,
        "docs": docs,
    }
    bm25_record = validate_runtime_record("bm25", bm25_record)
    bm25_raw = json.dumps(bm25_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return chunks, {"path": ".vault-meta/bm25/index.json", "bytes": bm25_raw + b"\n", "record": bm25_record}


def _write_runtime(vault: Path, chunks: Sequence[Mapping[str, Any]], bm25: Mapping[str, Any]) -> None:
    for item in chunks:
        path = vault / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item["bytes"])
    index = vault / bm25["path"]
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(bm25["bytes"])


def _read_runtime(vault: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = vault / ".vault-meta" / "chunks"
    index = vault / ".vault-meta" / "bm25" / "index.json"
    if not root.is_dir() or not index.is_file():
        _fail("published catalog runtime files are missing", code="CATALOG_STALE")
    chunks: list[dict[str, Any]] = []
    for path in sorted(root.rglob("chunk-*.json")):
        raw = path.read_bytes()
        record = validate_runtime_record("chunk", parse_projection_json(raw))
        relative = path.resolve().relative_to(vault.resolve()).as_posix()
        chunks.append({"path": relative, "bytes": raw, "record": record})
    chunks.sort(key=lambda item: item["path"].encode())
    raw = index.read_bytes()
    record = validate_runtime_record("bm25", parse_projection_json(raw))
    return chunks, {"path": ".vault-meta/bm25/index.json", "bytes": raw, "record": record}


def collect_published_catalog_material(
    *,
    vault_root: Path | str,
    upstream_root: Path | str,
    retrieval_config: object,
    _retain: bool = False,
) -> dict[str, Any]:
    """Read published Vault records plus installed catalog runtime files."""
    del _retain
    vault = Path(vault_root)
    upstream = Path(upstream_root)
    chunks, bm25 = _read_runtime(vault)
    return _material_from_records(
        vault=vault,
        upstream=upstream,
        retrieval_config=retrieval_config,
        chunks=chunks,
        bm25=bm25,
    )


def build_published_catalog(
    *,
    vault_root: Path | str,
    upstream_root: Path | str,
    created_at: str = "2026-09-01T00:00:00Z",
) -> dict[str, Any]:
    """Install catalog sqlite, chunks, and BM25 from published paper records."""
    vault = Path(vault_root)
    upstream = Path(upstream_root)
    canonical = _load_canonical(vault, upstream)
    if not canonical["compile_papers"]:
        raise ResearchError(INDEX_UNAVAILABLE, "no published paper records are available to index")
    chunks, bm25 = _chunk_and_index(canonical["compile_papers"], created_at=created_at)
    _write_runtime(vault, chunks, bm25)
    material = _material_from_records(
        vault=vault,
        upstream=upstream,
        retrieval_config=None,
        chunks=chunks,
        bm25=bm25,
    )
    db = vault / DB_RELATIVE
    db.parent.mkdir(parents=True, exist_ok=True)
    built = build_catalog_database(db, material)
    config_path = vault / ".vault-meta" / "retrieval-config.json"
    config_bytes = canonicalize(material["config"])
    config_path.write_bytes(config_bytes)
    return {
        "database": str(db),
        "config": material["config"],
        "config_path": str(config_path),
        "mapping_sha256": material["mapping"]["mapping_sha256"],
        "catalog_generation_sha256": built["catalog_generation_sha256"],
        "papers": [item["record"]["paper_id"] for item in canonical["compile_papers"]],
    }


def live_catalog_collector(**kwargs: Any) -> dict[str, Any]:
    """Prefer the canonical collector; fall back to published-record indexing."""
    from video_paper_wiki.catalog_collector import collect_current_catalog_material

    try:
        return collect_current_catalog_material(**kwargs)
    except ContractError as exc:
        if getattr(exc, "code", "") not in {"COMPILE_INPUT_INVALID", "CATALOG_INPUT_INVALID", "CATALOG_STALE"}:
            raise
        return collect_published_catalog_material(**kwargs)
