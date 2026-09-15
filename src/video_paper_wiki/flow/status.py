"""Read-only flow status from D1 / D2 / S1 public faces."""

from __future__ import annotations

import json

from video_paper_wiki.article_revision import check_article_revision, status_article_store
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import status_domain_store
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix
from video_paper_wiki.experiment_store import status_experiment_store
from video_paper_wiki.flow.actions import (
    AGENT_APPLY_KEY,
    DOMAIN_BASIS_KEYS,
    MAX_PAPERS,
    MAX_PER_PAPER,
    MAX_SELECTION_BYTES,
    OUTPUT_BASIS_KEYS,
    SELECTION_SCHEMA,
    STATUS_SCHEMA,
    assemble_next_actions,
    byte_sort,
    fail,
    invariants,
    missing_item,
    unique_sorted,
)
from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.secure_io import SecureIOError, read_regular_file
from video_paper_wiki.staging import resolve_checkout_root, validate_batch_id

LINEAGE_KEYS = (
    "lineage_id",
    "head_annotation_id",
    "current_review_id",
    "review_decision",
    "reviewed_officiality",
    "typed_fact_status",
    "source_association_id",
    "association_status",
    "version_status",
    "source_id",
    "version",
    "repository",
    "commit",
)
CONDITION_ROW_KEYS = (
    "condition_id",
    "setting_key",
    "head_record_id",
    "record_status",
    "condition_status",
    "critical_unknown",
)
def _require(document, keys, pointer):
    if type(document) is not dict:
        fail("FLOW_INVALID", pointer, "repair_input", {"reason": "upstream_shape"})
    for key in keys:
        if key not in document:
            fail("FLOW_INVALID", pointer, "repair_input", {"reason": "upstream_shape"})
    return document


def _check_bases(pairs):
    ref = None
    for name, basis in pairs:
        _require(basis, DOMAIN_BASIS_KEYS, name)
        if type(basis) is not dict:
            fail("FLOW_INVALID", name, "repair_input", {"reason": "upstream_shape"})
        if ref is None:
            ref = dict(basis)
            continue
        for key in basis:
            if key in ref and basis[key] != ref[key]:
                fail(
                    "FLOW_BASIS_CHANGED",
                    "/basis/" + key,
                    "repeat_read",
                    {"first": ref[key], "observed": basis[key]},
                    exit_code=75,
                )
        for key, value in basis.items():
            if key not in ref:
                ref[key] = value
    return ref


def _read_selection(batch_id):
    if batch_id is None:
        return None
    path = resolve_checkout_root() / ".work" / batch_id / "flow" / "selection.json"
    try:
        raw = read_regular_file(
            path,
            missing_code="FLOW_SELECTION_MISSING",
            unsafe_code="WORK_PATH_UNSAFE",
            max_bytes=MAX_SELECTION_BYTES,
        )
    except SecureIOError as exc:
        if exc.code == "FLOW_SELECTION_MISSING":
            return None
        raise
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        fail("FLOW_INVALID", "/selection", "repair_input", {"reason": "selection_shape"})
    try:
        validate_document(doc, SELECTION_SCHEMA)
    except ContractError:
        fail("FLOW_INVALID", "/selection", "repair_input", {"reason": "selection_shape"})
    if doc.get("batch_id") != batch_id:
        fail("FLOW_INVALID", "/selection", "repair_input", {"reason": "selection_shape"})
    return doc


def _next_unwritten(sections):
    ids = []
    for item in sections:
        if item.get("status") == "unwritten" and type(item.get("section_id")) is str:
            ids.append(item["section_id"])
    if not ids:
        return None
    return byte_sort(ids)[0]


def _lineage_row(d1_row, typed_status):
    out = {}
    for key in LINEAGE_KEYS:
        if key == "typed_fact_status":
            out[key] = typed_status
        else:
            if key not in d1_row:
                fail(
                    "FLOW_INVALID",
                    "/build_domain_source_version_view",
                    "repair_input",
                    {"reason": "upstream_shape"},
                )
            out[key] = d1_row[key]
    return out


def _condition_row(row):
    out = {}
    for key in CONDITION_ROW_KEYS:
        if key not in row:
            fail(
                "FLOW_INVALID",
                "/status_experiment_store",
                "repair_input",
                {"reason": "upstream_shape"},
            )
        out[key] = row[key]
    return out


def _article_row(row, next_section_id):
    progress = row.get("progress")
    _require(progress, ("provisional", "unknown", "unwritten"), "/status_article_store")
    return {
        "article_id": row["article_id"],
        "head_revision_id": row["head_revision_id"],
        "head_location": row["head_location"],
        "progress": {
            "provisional": progress["provisional"],
            "unknown": progress["unknown"],
            "unwritten": progress["unwritten"],
        },
        "complete": row["complete"],
        "next_section_id": next_section_id,
    }


def _count_map(values):
    counts = {}
    for item in values:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _selection_view(selection, current_basis):
    if selection is None:
        return None
    recorded = selection.get("basis") or {}
    changed = False
    for key in OUTPUT_BASIS_KEYS:
        if key in recorded and key in current_basis and recorded[key] != current_basis[key]:
            changed = True
    return {
        "paper_ids": list(selection["paper_ids"]),
        "association_id": selection.get("association_id"),
        "question": selection.get("question"),
        "basis_state": "changed" if changed else "current",
    }


def _missing_inputs(selection, universe_ids, papers, batch_id, claims_by_paper):
    items = []
    if selection is None:
        items.append(
            missing_item(
                "select-paper",
                "session",
                "paper_ids",
                "select papers to continue the session",
                universe_ids,
            )
        )
    items.append(
        missing_item(
            "recorded-by",
            "session",
            "recorded_by",
            "recorder name is supplied by the executor",
            [],
        )
    )
    items.append(
        missing_item(
            "recorded-at",
            "session",
            "recorded_at",
            "recorded_at is an RFC 3339 UTC timestamp supplied by the executor",
            [],
        )
    )
    if selection is not None and selection.get("question") is None:
        items.append(
            missing_item(
                "article-question",
                "survey",
                "question",
                "a survey question is required to prepare an article",
                [],
            )
        )
    if selection is not None and not selection.get("association_id"):
        first = next((row for row in papers if row["paper_id"] == selection["paper_ids"][0]), None)
        if first is not None:
            assoc = unique_sorted({item["source_association_id"] for item in first["lineages"]})
            if len(assoc) > 1:
                items.append(
                    missing_item(
                        "select-association",
                        "session",
                        "association_id",
                        "first paper has more than one source association",
                        assoc,
                    )
                )
    selected = set(selection["paper_ids"]) if selection else set()
    for row in papers:
        if selection is not None and row["paper_id"] not in selected:
            continue
        claim_ids = claims_by_paper.get(row["paper_id"], [])
        if claim_ids:
            items.append(
                missing_item(
                    "claim-refs-" + row["paper_id"],
                    "compare",
                    "claim_refs",
                    "empirical_result claim_id candidates are not prefilled",
                    claim_ids,
                )
            )
    return items[:256]


def build_flow_status(*, vault_root, batch_id=None, paper_id=None):
    if batch_id is not None:
        validate_batch_id(batch_id)
    if paper_id is not None and not is_canonical_paper_id(paper_id):
        fail("FLOW_INVALID", "/paper_id", "repair_input")
    versions = build_domain_source_version_view(vault_root=vault_root)
    domain = status_domain_store(vault_root=vault_root)
    experiments = status_experiment_store(vault_root=vault_root)
    matrix = build_experiment_comparison_matrix(vault_root=vault_root)
    articles_status = status_article_store(vault_root=vault_root, batch_id=batch_id)
    _require(versions, ("papers", "lineages", "basis"), "/build_domain_source_version_view")
    _require(domain, ("lineages",), "/status_domain_store")
    _require(experiments, ("basis", "conditions", "next_action"), "/status_experiment_store")
    _require(matrix, ("basis", "pairwise"), "/build_experiment_comparison_matrix")
    _require(articles_status, ("basis", "articles"), "/status_article_store")
    ref = _check_bases(
        (
            ("/build_domain_source_version_view", versions["basis"]),
            ("/status_experiment_store", experiments["basis"]),
            ("/build_experiment_comparison_matrix", matrix["basis"]),
            ("/status_article_store", articles_status["basis"]),
        )
    )
    selection = _read_selection(batch_id)
    article_rows = list(articles_status["articles"])
    if paper_id is not None:
        article_rows = [row for row in article_rows if paper_id in row.get("paper_ids", [])]
    next_sections = {}
    for row in article_rows:
        _require(row, ("article_id", "head_revision_id", "head_location", "progress", "complete", "paper_ids"), "/status_article_store")
        check_batch = batch_id if row["head_location"] == "staged" else None
        checked = check_article_revision(
            vault_root=vault_root,
            article_id=row["article_id"],
            revision_id=row["head_revision_id"],
            batch_id=check_batch,
        )
        _require(checked, ("sections",), "/check_article_revision")
        if "basis_current" in checked:
            _check_bases((("/status_article_store", ref), ("/check_article_revision", checked["basis_current"])))
        elif "basis" in checked:
            _check_bases((("/status_article_store", ref), ("/check_article_revision", checked["basis"])))
        next_sections[row["article_id"]] = _next_unwritten(checked["sections"])
    typed = {}
    claims_by_paper = {}
    for row in domain["lineages"]:
        _require(row, ("lineage_id", "paper_id", "typed_fact_status", "claims"), "/status_domain_store")
        typed[row["lineage_id"]] = row["typed_fact_status"]
        bucket = claims_by_paper.setdefault(row["paper_id"], [])
        for claim in row["claims"]:
            if claim.get("claim_kind") == "empirical_result" and type(claim.get("claim_id")) is str:
                bucket.append(claim["claim_id"])
    for key in claims_by_paper:
        claims_by_paper[key] = unique_sorted(claims_by_paper[key])
    universe = set()
    for row in versions["papers"]:
        _require(row, ("paper_id",), "/build_domain_source_version_view")
        universe.add(row["paper_id"])
    for row in versions["lineages"]:
        _require(row, ("paper_id", "lineage_id"), "/build_domain_source_version_view")
        universe.add(row["paper_id"])
    for row in experiments["conditions"]:
        _require(row, ("paper_id",), "/status_experiment_store")
        universe.add(row["paper_id"])
    for row in articles_status["articles"]:
        for item in row.get("paper_ids", []):
            universe.add(item)
    ordered = unique_sorted(universe)
    if len(ordered) > MAX_PAPERS:
        fail("FLOW_LIMIT", "/papers", "reduce_scope", {"limit": MAX_PAPERS, "observed": len(ordered)})
    if paper_id is not None and paper_id not in universe:
        fail(
            "FLOW_INVALID",
            "/paper_id",
            "repair_input",
            {"reason": "unknown_paper", "known_paper_count": len(ordered)},
        )
    d1_by_paper = {}
    for row in versions["lineages"]:
        d1_by_paper.setdefault(row["paper_id"], []).append(row)
    exp_by_paper = {}
    for row in experiments["conditions"]:
        exp_by_paper.setdefault(row["paper_id"], []).append(row)
    art_by_paper = {}
    for row in articles_status["articles"]:
        for item in row.get("paper_ids", []):
            art_by_paper.setdefault(item, []).append(row)
    selected_ids = set(selection["paper_ids"]) if selection else set()
    papers = []
    for pid in ordered:
        lineages = []
        for d1_row in d1_by_paper.get(pid, []):
            status = typed.get(d1_row["lineage_id"])
            if status is None:
                fail(
                    "FLOW_INVALID",
                    "/status_domain_store",
                    "repair_input",
                    {"reason": "upstream_shape"},
                )
            lineages.append(_lineage_row(d1_row, status))
        lineages = sorted(lineages, key=lambda item: item["lineage_id"].encode("utf-8"))
        conditions = [_condition_row(row) for row in exp_by_paper.get(pid, [])]
        conditions = sorted(conditions, key=lambda item: item["condition_id"].encode("utf-8"))
        art_rows = []
        seen_art = set()
        for row in art_by_paper.get(pid, []):
            if row["article_id"] in seen_art:
                continue
            seen_art.add(row["article_id"])
            art_rows.append(_article_row(row, next_sections.get(row["article_id"])))
        art_rows = sorted(art_rows, key=lambda item: item["article_id"].encode("utf-8"))
        if len(lineages) > MAX_PER_PAPER or len(conditions) > MAX_PER_PAPER or len(art_rows) > MAX_PER_PAPER:
            observed = max(len(lineages), len(conditions), len(art_rows))
            fail("FLOW_LIMIT", "/papers", "reduce_scope", {"limit": MAX_PER_PAPER, "observed": observed})
        papers.append(
            {
                "paper_id": pid,
                "selected": pid in selected_ids,
                "lineages": lineages,
                "conditions": conditions,
                "articles": art_rows,
            }
        )
    all_articles = []
    seen = set()
    for row in articles_status["articles"]:
        if row["article_id"] in seen:
            continue
        seen.add(row["article_id"])
        all_articles.append(_article_row(row, next_sections.get(row["article_id"])))
    all_articles = sorted(all_articles, key=lambda item: item["article_id"].encode("utf-8"))
    typed_counts = _count_map([row["typed_fact_status"] for row in domain["lineages"]])
    known_verdicts = {
        "comparable",
        "comparable_with_caveats",
        "incomparable",
        "insufficient_conditions",
    }
    verdicts = []
    for item in matrix["pairwise"]:
        if type(item) is dict and item.get("verdict") in known_verdicts:
            verdicts.append(item["verdict"])
    verdict_counts = _count_map(verdicts)
    staged_count = sum(1 for row in articles_status["articles"] if row.get("head_location") == "staged")
    complete_count = sum(1 for row in articles_status["articles"] if row.get("complete"))
    in_progress = len(articles_status["articles"]) - complete_count
    output_basis = {}
    for key in OUTPUT_BASIS_KEYS:
        if key not in ref:
            fail("FLOW_INVALID", "/basis/" + key, "repair_input", {"reason": "upstream_shape"})
        output_basis[key] = ref[key]
    article_sha = articles_status["basis"].get("article_store_inventory_sha256")
    if type(article_sha) is not str:
        fail("FLOW_INVALID", "/status_article_store", "repair_input", {"reason": "upstream_shape"})
    visible = papers if paper_id is None else [row for row in papers if row["paper_id"] == paper_id]
    selection_view = _selection_view(selection, output_basis)
    missing = _missing_inputs(selection, ordered, papers, batch_id, claims_by_paper)
    actions = assemble_next_actions(
        vault_root=vault_root,
        batch_id=batch_id,
        selection=selection,
        papers=papers,
        universe_ids=ordered,
        condition_count=len(experiments["conditions"]),
        experiment_next=experiments["next_action"],
        articles=all_articles,
    )
    document = {
        "schema": STATUS_SCHEMA,
        "state": "flow_status",
        "batch_id": batch_id,
        "paper_filter": paper_id,
        "basis": output_basis,
        "article_store_inventory_sha256": article_sha,
        "selection": selection_view,
        "counts": {
            "papers": len(ordered),
            "lineages": len(versions["lineages"]),
            "conditions": len(experiments["conditions"]),
            "pairwise": len(matrix["pairwise"]),
            "articles": len(articles_status["articles"]),
            "staged_articles": staged_count,
        },
        "stages": {
            "discover": {
                "state": "empty" if not ordered else "papers_known",
                "paper_count": len(ordered),
            },
            "annotate": {
                "lineage_count": len(domain["lineages"]),
                "by_typed_fact_status": typed_counts,
            },
            "compare": {
                "condition_count": len(experiments["conditions"]),
                "pairwise_count": len(matrix["pairwise"]),
                "by_verdict": verdict_counts,
            },
            "survey": {
                "article_count": len(articles_status["articles"]),
                "complete_count": complete_count,
                "in_progress_count": in_progress,
            },
            "publish": {"state": "unpublished", AGENT_APPLY_KEY: "not_available"},
        },
        "papers": visible,
        "missing_inputs": missing,
        "next_actions": actions,
    }
    document.update(invariants("read_only"))
    validate_document(document, STATUS_SCHEMA)
    return document
