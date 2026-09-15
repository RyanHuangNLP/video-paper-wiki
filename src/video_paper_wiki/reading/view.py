"""Collect D1/D2/D3/S1-R1 read faces and stage Obsidian reading pages."""

from __future__ import annotations

import hashlib

from video_paper_wiki.article_revision import (
    article_history,
    check_article_revision,
    render_article_revision,
    status_article_store,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_claims import build_domain_claim_coverage_view
from video_paper_wiki.domain_relations import build_domain_relation_view
from video_paper_wiki.domain_structure import build_domain_structure_view
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.graph_projection import build_domain_graph_projection
from video_paper_wiki.identity import is_canonical_paper_id, paper_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.reading.pages import render_all
from video_paper_wiki.secure_io import read_regular_file
from video_paper_wiki.staging import resolve_checkout_root, stage_bytes, validate_batch_id

MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 8192
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ARTICLE_BODY = 8 * 1024 * 1024
BASIS_KEYS = (
    "domain_store_inventory_sha256",
    "claim_ledger_sha256",
    "assessment_heads_sha256",
    "experiment_store_inventory_sha256",
)
DOMAIN_BASIS_KEYS = BASIS_KEYS[:3]
MANIFEST_KEYS = (
    "view_kind",
    "state",
    "batch_id",
    "articles_batch",
    "paper_filter",
    "install_path",
    "basis",
    "article_store_inventory_sha256",
    "graph_sha256",
    "matrix_sha256",
    "counts",
    "stale_counts",
    "articles",
    "pages",
    "publication",
    "applied",
    "vault_written",
    "write_kind",
    "audit_coverage",
    "backup_coverage",
    "ranking",
    "typed_fact_promotion",
    "canonical_official",
    "current_supported_typed_fact",
    "next_action",
)
MANIFEST_SCHEMA = "video-paper-wiki.reading-manifest.v1"
MESSAGES = {
    "READING_INVALID": "reading input is invalid",
    "READING_BASIS_CHANGED": "reading basis changed across read faces",
    "READING_RENDER_MISSING": "reading render bytes are missing",
    "READING_RENDER_MISMATCH": "reading render bytes do not match the sealed digest",
    "READING_LIMIT": "reading pages exceed a closed bound",
}


class ReadingViewError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise ReadingViewError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _digest(value):
    return hashlib.sha256(canonicalize(value)).hexdigest()


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _require(document, keys, pointer):
    if type(document) is not dict:
        _fail("READING_INVALID", pointer, "repair_store", {"reason": "upstream_shape"})
    for key in keys:
        if key not in document:
            _fail("READING_INVALID", pointer, "repair_store", {"reason": "upstream_shape"})
    return document


def _basis4(document, pointer):
    _require(document, ("basis",), pointer)
    basis = document["basis"]
    if type(basis) is not dict:
        _fail("READING_INVALID", pointer, "repair_store", {"reason": "upstream_shape"})
    for key in DOMAIN_BASIS_KEYS:
        if key not in basis:
            _fail("READING_INVALID", pointer, "repair_store", {"reason": "upstream_shape"})
    out = {key: basis[key] for key in DOMAIN_BASIS_KEYS}
    extra = "experiment_store_inventory_sha256"
    if extra in basis:
        out[extra] = basis[extra]
    return out


def _check_basis(first, observed, pointer):
    for key in observed:
        if key in first and observed[key] != first[key]:
            _fail(
                "READING_BASIS_CHANGED",
                "/basis/" + key,
                "repeat_read",
                {"first": dict(first), "observed": dict(observed), "call": pointer},
                exit_code=75,
            )


def _title_from_render(body, fallback):
    text = body.decode("utf-8")
    if text.startswith("# "):
        line = text.split("\n", 1)[0][2:].strip()
        if line:
            return line
    return fallback


def _paper_index(items, key="paper_id"):
    out = {}
    if type(items) is not list:
        return out
    for item in items:
        if type(item) is dict and key in item:
            out[item[key]] = item
    return out


def _annotation_maps(versions, structure, relations):
    annotation = {}
    review = {}
    for view in (versions, structure, relations):
        lineages = view.get("lineages") if type(view) is dict else None
        if type(lineages) is not list:
            continue
        for row in lineages:
            if type(row) is not dict:
                continue
            lid = row.get("lineage_id")
            if type(lid) is not str:
                continue
            head = row.get("head_annotation_id")
            if type(head) is str:
                annotation[head] = lid
            history = row.get("history")
            if type(history) is list:
                for item in history:
                    if type(item) is dict and type(item.get("annotation_id")) is str:
                        annotation[item["annotation_id"]] = lid
            reviews = row.get("reviews")
            if type(reviews) is list:
                for item in reviews:
                    if type(item) is dict and type(item.get("review_id")) is str:
                        review[item["review_id"]] = lid
    return annotation, review


def _record_conditions(graph, matrix):
    mapping = {}
    for row in matrix.get("rows") or []:
        if type(row) is dict and type(row.get("record_id")) is str and type(row.get("condition_id")) is str:
            mapping[row["record_id"]] = row["condition_id"]
    for node in graph.get("nodes") or []:
        if type(node) is not dict or node.get("kind") != "experiment_condition":
            continue
        cid = node.get("node_id")
        if type(cid) is not str:
            continue
        for source in node.get("sources") or []:
            if type(source) is dict and source.get("record_kind") == "experiment_record":
                rid = source.get("record_id")
                if type(rid) is str:
                    mapping[rid] = cid
    return mapping


def _paper_sources(graph, paper_id):
    nodes = [node for node in graph.get("nodes") or [] if type(node) is dict]
    by_id = {node.get("node_id"): node for node in nodes if type(node.get("node_id")) is str}
    chosen = []
    seen = set()

    def add(node):
        nid = node.get("node_id")
        if nid in seen:
            return
        seen.add(nid)
        chosen.append(node)

    for node in nodes:
        if node.get("kind") == "paper" and node.get("node_id") == paper_id:
            add(node)
        elif node.get("paper_id") == paper_id:
            add(node)
    for edge in graph.get("edges") or []:
        if type(edge) is not dict:
            continue
        if edge.get("from_node") == paper_id or edge.get("to_node") == paper_id:
            for key in ("from_node", "to_node"):
                node = by_id.get(edge.get(key))
                if node is not None:
                    add(node)
    sources = []
    seen_src = set()
    for node in chosen:
        for source in node.get("sources") or []:
            if type(source) is not dict:
                continue
            kind = source.get("record_kind")
            rid = source.get("record_id")
            pair = (kind, rid)
            if type(kind) is not str or type(rid) is not str or pair in seen_src:
                continue
            seen_src.add(pair)
            sources.append({"record_kind": kind, "record_id": rid})
    sources.sort(key=lambda item: (item["record_kind"].encode("utf-8"), item["record_id"].encode("utf-8")))
    return sources


def _current_labels(versions, paper_id):
    labels = []
    for item in versions.get("versions") or []:
        if type(item) is not dict:
            continue
        papers = item.get("paper_ids") or []
        if paper_id not in papers or item.get("record_status") != "current":
            continue
        version = item.get("version")
        if type(version) is dict:
            label = version.get("label")
            if type(label) is str and label:
                labels.append(label)
            elif type(version.get("kind")) is str and version.get("kind"):
                labels.append(version["kind"])
    return labels


def _typed_untyped(claim_paper):
    if claim_paper is None:
        return 0, 0
    coverage = claim_paper.get("kind_coverage") or {}
    typed = 0
    if type(coverage) is dict:
        for cell in coverage.values():
            if type(cell) is dict and type(cell.get("typed_claim_count")) is int:
                typed += cell["typed_claim_count"]
    untyped = claim_paper.get("untyped_claims") or []
    return typed, len(untyped) if type(untyped) is list else 0


def _assemble_paper(paper_id, graph, versions, structure, claims, relations, matrix, articles):
    nodes = [node for node in graph.get("nodes") or [] if type(node) is dict]
    paper_node = next((node for node in nodes if node.get("kind") == "paper" and node.get("node_id") == paper_id), {})
    version_paper = _paper_index(versions.get("papers") or []).get(paper_id)
    structure_paper = _paper_index(structure.get("papers") or []).get(paper_id)
    claim_paper = _paper_index(claims.get("papers") or []).get(paper_id)
    relation_paper = _paper_index(relations.get("papers") or []).get(paper_id)
    version_rows = []
    for item in versions.get("versions") or []:
        if type(item) is dict and paper_id in (item.get("paper_ids") or []):
            version_rows.append(item)
    if not version_rows and version_paper is not None:
        version_rows = list(version_paper.get("versions") or [])
    concept_rows = [
        item
        for item in (structure.get("concepts") or [])
        if type(item) is dict and paper_id in (item.get("paper_ids") or [])
    ]
    claim_rows = [
        item
        for item in (claims.get("claims") or [])
        if type(item) is dict and paper_id in (item.get("paper_ids") or [])
    ]
    lineages = [
        item
        for item in (relations.get("lineages") or [])
        if type(item) is dict and item.get("paper_id") == paper_id
    ]
    conflicts = [
        item
        for item in (relations.get("conflicts") or [])
        if type(item) is dict and item.get("paper_id") == paper_id
    ]
    matrix_rows = [
        item
        for item in (matrix.get("rows") or [])
        if type(item) is dict and item.get("paper_id") == paper_id
    ]
    related = [item for item in articles if paper_id in (item.get("paper_ids") or [])]
    typed, untyped = _typed_untyped(claim_paper)
    counts = (structure_paper or {}).get("concept_kind_counts") or {}
    concept_total = 0
    if type(counts) is dict:
        for value in counts.values():
            if type(value) is int:
                concept_total += value
    unlabeled = list((version_paper or {}).get("unlabeled_versions") or [])
    return {
        "paper_id": paper_id,
        "slug": paper_page_slug(paper_id),
        "status": paper_node.get("status") or "",
        "stale_reasons": list(paper_node.get("stale_reasons") or []),
        "declared_version_count": int((version_paper or {}).get("declared_version_count") or 0),
        "unlabeled_count": len(unlabeled),
        "current_labels": _current_labels(versions, paper_id),
        "concept_kind_counts": counts if type(counts) is dict else {},
        "concept_total": concept_total,
        "capability_coverage": (structure_paper or {}).get("capability_coverage") or {},
        "concepts": concept_rows,
        "typed_claim_count": typed,
        "untyped_claim_count": untyped,
        "kind_coverage": (claim_paper or {}).get("kind_coverage") or {},
        "uncovered_kinds": list((claim_paper or {}).get("uncovered_kinds") or []),
        "untyped_claims": list((claim_paper or {}).get("untyped_claims") or []),
        "claims": claim_rows,
        "lineages": lineages,
        "version_rows": version_rows,
        "conflicts": conflicts,
        "matrix_rows": matrix_rows,
        "related_articles": related,
        "sources": _paper_sources(graph, paper_id),
        "relation_paper": relation_paper,
    }


def _load_articles(vault_root, batch_id, articles_batch, first_basis, paper_id):
    status = status_article_store(vault_root=vault_root, batch_id=articles_batch)
    _require(status, ("basis", "articles"), "/articles")
    _check_basis(first_basis, _basis4(status, "/articles"), "/articles")
    article_sha = status["basis"].get("article_store_inventory_sha256")
    if type(article_sha) is not str:
        _fail("READING_INVALID", "/articles", "repair_store", {"reason": "upstream_shape"})
    rows = []
    for item in status.get("articles") or []:
        if type(item) is not dict:
            _fail("READING_INVALID", "/articles", "repair_store", {"reason": "upstream_shape"})
        _require(
            item,
            (
                "article_id",
                "question",
                "paper_ids",
                "head_revision_id",
                "head_location",
                "revision_count",
                "staged_revision_count",
                "vault_revision_count",
                "kind",
                "progress",
                "complete",
            ),
            "/articles",
        )
        if paper_id is not None and paper_id not in item["paper_ids"]:
            continue
        art = item["article_id"]
        head = item["head_revision_id"]
        history = article_history(vault_root=vault_root, article_id=art, batch_id=articles_batch)
        _require(history, ("revisions",), "/history")
        checked = check_article_revision(
            vault_root=vault_root,
            article_id=art,
            revision_id=head,
            batch_id=articles_batch,
        )
        _require(checked, ("check_status", "sections"), "/check")
        if "basis_current" in checked:
            _check_basis(first_basis, _basis4({"basis": checked["basis_current"]}, "/check"), "/check")
        elif "basis" in checked:
            _check_basis(first_basis, _basis4(checked, "/check"), "/check")
        render_batch = articles_batch if item["head_location"] == "staged" else batch_id
        rendered = render_article_revision(
            vault_root=vault_root,
            batch_id=render_batch,
            article_id=art,
            revision_id=head,
        )
        _require(rendered, ("markdown_path", "markdown_sha256", "size_bytes", "complete"), "/render")
        path = resolve_checkout_root() / rendered["markdown_path"]
        body = read_regular_file(
            path,
            missing_code="READING_RENDER_MISSING",
            unsafe_code="WORK_PATH_UNSAFE",
            max_bytes=MAX_ARTICLE_BODY,
        )
        if _sha_bytes(body) != rendered["markdown_sha256"] or len(body) != rendered["size_bytes"]:
            _fail("READING_RENDER_MISMATCH", "/render", "repair_store")
        affected = []
        for section in checked.get("sections") or []:
            if type(section) is dict and section.get("affected") is True and type(section.get("section_id")) is str:
                affected.append(section["section_id"])
        title = _title_from_render(body, item["question"] or art)
        rows.append(
            {
                "article_id": art,
                "title": title,
                "question": item["question"],
                "paper_ids": list(item["paper_ids"]),
                "head_revision_id": head,
                "head_location": item["head_location"],
                "revision_count": item["revision_count"],
                "staged_revision_count": item["staged_revision_count"],
                "vault_revision_count": item["vault_revision_count"],
                "kind": item["kind"],
                "progress": item["progress"],
                "complete": item["complete"],
                "check_status": checked["check_status"],
                "affected_sections": affected,
                "render_path": rendered["markdown_path"],
                "render_sha256": rendered["markdown_sha256"],
                "render_bytes": body,
                "revisions": list(history["revisions"]),
            }
        )
    return rows, article_sha


def _stage_pages(batch_id, page_map, manifest):
    items = sorted(page_map.items(), key=lambda item: item[0].encode("utf-8"))
    if len(items) > MAX_PAGES:
        _fail(
            "READING_LIMIT",
            "/pages",
            "reduce_scope",
            {"limit": MAX_PAGES, "observed": len(items)},
        )
    total = 0
    for path, data in items:
        if len(data) > MAX_PAGE_BYTES:
            _fail(
                "READING_LIMIT",
                "/pages/" + path,
                "reduce_scope",
                {"limit": MAX_PAGE_BYTES, "observed": len(data)},
            )
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        _fail(
            "READING_LIMIT",
            "/pages",
            "reduce_scope",
            {"limit": MAX_TOTAL_BYTES, "observed": total},
        )
    pages = [{"path": path, "sha256": _sha_bytes(data), "size_bytes": len(data)} for path, data in items]
    manifest["pages"] = pages
    validate_document(manifest, MANIFEST_SCHEMA)
    new = 0
    already = 0
    for path, data in items:
        relative = tuple(path.split("/"))
        result = stage_bytes(batch_id=batch_id, relative=("reading",) + relative, data=data)
        if result.already_staged:
            already += 1
        else:
            new += 1
    raw = canonicalize(manifest)
    result = stage_bytes(batch_id=batch_id, relative=("reading", "manifest.json"), data=raw)
    if result.already_staged:
        already += 1
    else:
        new += 1
    return new, already, pages


def build_reading_views(*, vault_root, batch_id, paper_id=None, articles_batch=None):
    batch = validate_batch_id(batch_id)
    if articles_batch is not None:
        other = validate_batch_id(articles_batch)
        if other == batch:
            _fail("READING_INVALID", "/articles_batch", "repair_input", {"reason": "same_batch"})
        articles_batch = other
    if paper_id is not None and not is_canonical_paper_id(paper_id):
        _fail("READING_INVALID", "/paper_id", "repair_input")
    graph = build_domain_graph_projection(vault_root=vault_root, paper_id=paper_id)
    first = _basis4(graph, "/graph")
    if "experiment_store_inventory_sha256" not in first:
        _fail("READING_INVALID", "/graph", "repair_store", {"reason": "upstream_shape"})
    _require(graph, ("graph_sha256", "known_paper_count", "nodes", "stale_counts"), "/graph")
    versions = build_domain_source_version_view(vault_root=vault_root, paper_id=paper_id)
    _check_basis(first, _basis4(versions, "/versions"), "/versions")
    _require(versions, ("papers", "versions", "lineages"), "/versions")
    structure = build_domain_structure_view(vault_root=vault_root, paper_id=paper_id)
    _check_basis(first, _basis4(structure, "/structure"), "/structure")
    _require(structure, ("concepts", "papers"), "/structure")
    claims = build_domain_claim_coverage_view(vault_root=vault_root, paper_id=paper_id)
    _check_basis(first, _basis4(claims, "/claims"), "/claims")
    _require(claims, ("claims", "papers"), "/claims")
    relations = build_domain_relation_view(vault_root=vault_root, paper_id=paper_id)
    _check_basis(first, _basis4(relations, "/relations"), "/relations")
    _require(relations, ("lineages", "conflicts"), "/relations")
    matrix = build_experiment_comparison_matrix(vault_root=vault_root, paper_id=paper_id)
    _check_basis(first, _basis4(matrix, "/matrix"), "/matrix")
    _require(matrix, ("rows", "columns", "cells", "metric_columns", "metric_cells", "pairwise", "row_count"), "/matrix")
    articles, article_sha = _load_articles(vault_root, batch, articles_batch, first, paper_id)
    annotation_lineage, review_lineage = _annotation_maps(versions, structure, relations)
    record_condition = _record_conditions(graph, matrix)
    paper_ids = [
        node["node_id"]
        for node in graph.get("nodes") or []
        if type(node) is dict and node.get("kind") == "paper" and type(node.get("node_id")) is str
    ]
    paper_ids.sort(key=lambda item: item.encode("utf-8"))
    papers = [
        _assemble_paper(pid, graph, versions, structure, claims, relations, matrix, articles)
        for pid in paper_ids
    ]
    lineages_n = len([node for node in graph.get("nodes") or [] if type(node) is dict and node.get("kind") == "code_lineage"])
    stale = graph.get("stale_counts") or {}
    if type(stale) is not dict or "nodes" not in stale or "edges" not in stale:
        _fail("READING_INVALID", "/graph", "repair_store", {"reason": "upstream_shape"})
    model = {
        "batch_id": batch,
        "articles_batch": articles_batch,
        "paper_filter": paper_id,
        "basis": first,
        "basis_sha256": _digest(first),
        "graph_sha256": graph["graph_sha256"],
        "known_paper_count": graph["known_paper_count"],
        "stale_counts": {"nodes": stale["nodes"], "edges": stale["edges"]},
        "papers": papers,
        "concepts": list(structure.get("concepts") or []),
        "articles": articles,
        "matrix": matrix,
        "annotation_lineage": annotation_lineage,
        "review_lineage": review_lineage,
        "record_condition": record_condition,
    }
    page_map = render_all(model)
    manifest = {
        "view_kind": "obsidian-reading.v1",
        "state": "reading_staged",
        "batch_id": batch,
        "articles_batch": articles_batch,
        "paper_filter": paper_id,
        "install_path": "wiki/reading",
        "basis": first,
        "article_store_inventory_sha256": article_sha,
        "graph_sha256": graph["graph_sha256"],
        "matrix_sha256": _digest(matrix),
        "counts": {
            "papers": graph["known_paper_count"],
            "versions": len(versions.get("versions") or []),
            "concepts": len(structure.get("concepts") or []),
            "claims": len(claims.get("claims") or []),
            "lineages": lineages_n,
            "conditions": matrix["row_count"],
            "pairwise": len(matrix.get("pairwise") or []),
            "articles": len(articles),
            "pages": len(page_map),
        },
        "stale_counts": {"nodes": stale["nodes"], "edges": stale["edges"]},
        "articles": [
            {
                "article_id": item["article_id"],
                "head_revision_id": item["head_revision_id"],
                "head_location": item["head_location"],
                "check_status": item["check_status"],
                "complete": item["complete"],
                "render_path": item["render_path"],
                "render_sha256": item["render_sha256"],
            }
            for item in articles
        ],
        "pages": [],
        "publication": "unpublished",
        "applied": False,
        "vault_written": False,
        "write_kind": "work_staging",
        "audit_coverage": "not_wired",
        "backup_coverage": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "open_in_obsidian",
    }
    extra = set(manifest) - set(MANIFEST_KEYS)
    missing = set(MANIFEST_KEYS) - set(manifest)
    if extra or missing:
        _fail("READING_INVALID", "/manifest", "repair_store", {"reason": "upstream_shape"})
    new, already, pages = _stage_pages(batch, page_map, manifest)
    data = dict(manifest)
    data["pages"] = pages
    data["staging"] = {
        "new": new,
        "already_staged": already,
        "manifest_path": ".work/" + batch + "/reading/manifest.json",
    }
    return data
