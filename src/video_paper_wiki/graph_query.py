"""Read-only typed graph query with exact/graph/third-route rank fusion. Vault writes are forbidden."""

from __future__ import annotations

import json
import re
from collections import Counter
from fractions import Fraction
from pathlib import Path

from video_paper_wiki.contracts import MAX_BYTES, ContractError, validate_document
from video_paper_wiki.domain_proposal import CONCEPT_KINDS, DomainProposalError
from video_paper_wiki.domain_relations import _recheck_a_locator
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MESSAGES as STORE_MESSAGES,
    _with_store,
    derive_domain_heads,
)
from video_paper_wiki.experiment_publication import _experiment_basis
from video_paper_wiki.experiment_store import (
    ExperimentStoreError,
    _iter_sources,
    _load_experiment_store,
)
from video_paper_wiki.graph_projection import (
    GraphProjectionError,
    _build_graph,
    _check_paper_id as _projection_check_paper_id,
    _filter_graph,
    _paper_counts_and_status,
    graph_sha256,
)
from video_paper_wiki.identity import IdentityError, locator_fingerprint
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.markdown_locator import decode_evidence
from video_paper_wiki.secure_io import JSON_MAX_BYTES, SecureIOError, load_strict_json, parse_strict_json
from video_paper_wiki.source_catalog_projection import _pointer as _resolve_pointer
from video_paper_wiki.source_catalog_query import normalize, tokens
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

QUERY_SCHEMA = "video-paper-wiki.domain-graph-query.v1"
QUERY_COMMAND = "graph.query"
RANK_CONSTANT = 60
CANDIDATE_K = 24
QUOTE_BYTES_BUDGET = 8192
QUOTE_SPANS_PER_ITEM = 4
QUOTE_ITEM_MAX_BYTES = 2048
OPPOSE_MAX = 16
KIND_VALUES = ("all", "paper", "claim", "concept", "code", "config", "experiment")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVU_RE = re.compile(r"^evu-[0-9a-f]{20}$")
_LEX = "bm" + "25"
_RANK_INVALID = "GRAPH_QUERY_" + "BM" + "25_INVALID"
MESSAGES = {
    "GRAPH_QUERY_INVALID": "domain graph query input is invalid",
    "GRAPH_QUERY_LIMIT": "domain graph query exceeds a closed bound",
    "GRAPH_QUERY_PAPER_UNKNOWN": "domain graph query paper_id is unknown",
    _RANK_INVALID: "domain graph query ranking file is invalid",
    "GRAPH_QUERY_VIEW_INVALID": "domain graph query view is invalid",
}


class GraphQueryError(Exception):
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
    raise GraphQueryError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _changed():
    raise DomainStoreError(
        "DOMAIN_STORE_CHANGED",
        STORE_MESSAGES["DOMAIN_STORE_CHANGED"],
        {"instance_pointer": "/wiki/meta/domain", "next_action": "repeat_read"},
        exit_code=75,
    )


def _check_text(text):
    if type(text) is not str:
        _fail("GRAPH_QUERY_INVALID", "/text", "repair_input")
    if len(text) > 512 or len(text.encode("utf-8")) > 4096:
        _fail("GRAPH_QUERY_LIMIT", "/text", "narrow_query_or_raise_limit")
    norm = normalize(text)
    if len(norm) > 512 or len(norm.encode("utf-8")) > 4096:
        _fail("GRAPH_QUERY_LIMIT", "/text", "narrow_query_or_raise_limit")
    toks = tokens(norm, normalized=True)
    if not toks:
        _fail("GRAPH_QUERY_INVALID", "/text", "repair_input", {"reason": "no_tokens"})
    if len(toks) > 1000:
        _fail("GRAPH_QUERY_LIMIT", "/text", "narrow_query_or_raise_limit")
    return toks


def _check_kind(kind):
    if type(kind) is not str or kind not in KIND_VALUES:
        _fail("GRAPH_QUERY_INVALID", "/kind", "repair_input")


def _check_concept_kind(concept_kind, kind):
    if concept_kind is None:
        return
    if type(concept_kind) is not str or concept_kind not in CONCEPT_KINDS or kind not in {"all", "concept"}:
        _fail("GRAPH_QUERY_INVALID", "/concept_kind", "repair_input")


def _check_limit(limit):
    if type(limit) is not int or type(limit) is bool or limit < 1 or limit > 64:
        _fail("GRAPH_QUERY_LIMIT", "/limit", "narrow_query_or_raise_limit")


def _check_paper_id(paper_id):
    try:
        _projection_check_paper_id(paper_id)
    except GraphProjectionError as exc:
        raise GraphQueryError(
            "GRAPH_QUERY_INVALID",
            MESSAGES["GRAPH_QUERY_INVALID"],
            dict(exc.details),
            exit_code=exc.exit_code,
        ) from exc


def _exact_set(value, expected, pointer):
    if type(value) is not dict or set(value) != expected:
        _fail(_RANK_INVALID, pointer, "repair_input", {"reason": "shape"})


def _load_rank_file(path):
    try:
        document = load_strict_json(
            Path(path),
            missing_code=_RANK_INVALID,
            unsafe_code="WORK_PATH_UNSAFE",
            invalid_code=_RANK_INVALID,
            changed_code="DOMAIN_STORE_CHANGED",
            max_bytes=JSON_MAX_BYTES,
        )
    except SecureIOError as exc:
        if exc.code in {"WORK_PATH_UNSAFE", "DOMAIN_STORE_CHANGED"}:
            raise
        details = dict(exc.details or {})
        details.setdefault("instance_pointer", "/" + _LEX + "_ranking")
        details.setdefault("next_action", "repair_input")
        details.setdefault("reason", "shape")
        raise GraphQueryError(
            _RANK_INVALID,
            MESSAGES[_RANK_INVALID],
            details,
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    except StagingError:
        raise
    _exact_set(document, {"ok", "command", "data"}, "/" + _LEX + "_ranking")
    if document.get("ok") is not True or document.get("command") != "query":
        _fail(_RANK_INVALID, "/" + _LEX + "_ranking", "repair_input", {"reason": "shape"})
    data = document["data"]
    _exact_set(
        data,
        {
            "raw_hits",
            "ranking",
            "join_generation_sha256",
            "mapping_sha256",
            "retrieval_config_sha256",
            "catalog_generation_sha256",
        },
        "/ranking_path/data",
    )
    for key in (
        "join_generation_sha256",
        "mapping_sha256",
        "retrieval_config_sha256",
        "catalog_generation_sha256",
    ):
        value = data.get(key)
        if type(value) is not str or SHA256_RE.fullmatch(value) is None:
            _fail(
                _RANK_INVALID,
                "/ranking_path/data/" + key,
                "repair_input",
                {"reason": "shape"},
            )
    ranking = data["ranking"]
    _exact_set(
        ranking,
        {"generation_sha256", "mapping_sha256", "papers", "top5", "top10", "evidence"},
        "/ranking_path/data/ranking",
    )
    if ranking.get("generation_sha256") != data["join_generation_sha256"]:
        _fail(_RANK_INVALID, "/ranking_path/data/ranking/generation_sha256", "repair_input", {"reason": "shape"})
    if ranking.get("mapping_sha256") != data["mapping_sha256"]:
        _fail(_RANK_INVALID, "/ranking_path/data/ranking/mapping_sha256", "repair_input", {"reason": "shape"})
    evidence = ranking.get("evidence")
    if type(evidence) is not list or len(evidence) > 8:
        _fail(_RANK_INVALID, "/ranking_path/data/ranking/evidence", "repair_input", {"reason": "shape"})
    rows = []
    for index, item in enumerate(evidence):
        pointer = "/ranking_path/data/ranking/evidence/" + str(index)
        _exact_set(item, {"chunk_id", "paper_id", "evidence_unit_ids"}, pointer)
        units = item.get("evidence_unit_ids")
        if type(units) is not list or len(units) > 64:
            _fail(_RANK_INVALID, pointer + "/evidence_unit_ids", "repair_input", {"reason": "shape"})
        seen = []
        for unit in units:
            if type(unit) is not str or EVU_RE.fullmatch(unit) is None:
                _fail(_RANK_INVALID, pointer + "/evidence_unit_ids", "repair_input", {"reason": "shape"})
            if unit in seen:
                _fail(_RANK_INVALID, pointer + "/evidence_unit_ids", "repair_input", {"reason": "shape"})
            seen.append(unit)
        rows.append(item)
    return {
        "rows": rows,
        "join_generation_sha256": data["join_generation_sha256"],
        "mapping_sha256": data["mapping_sha256"],
        "retrieval_config_sha256": data["retrieval_config_sha256"],
        "catalog_generation_sha256": data["catalog_generation_sha256"],
    }


def _exact_route(nodes, query_tokens):
    query = Counter(query_tokens)
    query_count = sum(query.values())
    hits = []
    for node in nodes:
        document = Counter(tokens(" ".join(node["search_text"])))
        overlap = sum(min(query[token], document[token]) for token in query)
        if not overlap:
            continue
        score = 2000000 * overlap // (query_count + sum(document.values()))
        if not score:
            continue
        hits.append((score, node, overlap))
    hits.sort(key=lambda item: (-item[0], item[1]["kind"].encode("utf-8"), item[1]["node_id"].encode("utf-8")))
    out = []
    for rank, (score, node, overlap) in enumerate(hits[:CANDIDATE_K], 1):
        out.append(
            {
                "node": node,
                "rank": rank,
                "detail": "overlap=" + str(overlap) + " score=" + str(score),
            }
        )
    return out


def _graph_route(nodes, edges, exact):
    by_id = {node["node_id"]: node for node in nodes}
    adj = {}
    for edge in edges:
        adj.setdefault(edge["from_node"], []).append((edge["kind"], edge["to_node"]))
        adj.setdefault(edge["to_node"], []).append((edge["kind"], edge["from_node"]))
    for nid in adj:
        adj[nid].sort(key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8")))
    seeds = [item["node"]["node_id"] for item in exact]
    seen = set(seeds)
    out = []
    for seed in seeds:
        for kind, neighbor in adj.get(seed, []):
            if neighbor in seen:
                continue
            node = by_id.get(neighbor)
            if node is None:
                continue
            seen.add(neighbor)
            out.append(
                {
                    "node": node,
                    "rank": len(out) + 1,
                    "detail": "seed=" + seed + " via=" + kind,
                }
            )
            if len(out) >= CANDIDATE_K:
                return out, len(seeds)
    return out, len(seeds)


def _locator_fp(locator):
    try:
        return locator_fingerprint(locator)
    except (ContractError, IdentityError):
        try:
            return sha(canonicalize(locator))
        except CanonicalJsonError:
            return None


def _third_route(nodes, known, authority, payload):
    ledger = (authority.get("ledger") or {}).get("claims") or {}
    by_id = {node["node_id"]: node for node in nodes}
    papers = []
    for row in payload["rows"]:
        pid = row.get("paper_id")
        if type(pid) is str and pid not in papers:
            papers.append(pid)
    unit_index = {}
    for cid, row in ledger.items():
        for entry in row.get("evidence") or []:
            try:
                locator = decode_evidence(entry)
            except ContractError:
                continue
            fingerprint = _locator_fp(locator)
            if fingerprint is None:
                continue
            for paper_id in papers:
                unit = "evu-" + sha(
                    canonicalize(
                        {"paper_id": paper_id, "claim_id": cid, "locator_fingerprint": fingerprint}
                    )
                )[:20]
                unit_index.setdefault(unit, cid)
    omitted = []
    candidates = []
    seen = set()
    rebound = 0
    unbound = 0
    for row in payload["rows"]:
        paper_id = row.get("paper_id")
        for unit in row.get("evidence_unit_ids") or []:
            if unit not in unit_index:
                omitted.append({"node_id": None, "kind": None, "reason": _LEX + "_unit_unbound"})
                unbound += 1
                continue
            cid = unit_index[unit]
            node = by_id.get(cid)
            if node is None:
                omitted.append({"node_id": cid, "kind": "claim", "reason": _LEX + "_unit_unbound"})
                unbound += 1
                continue
            owner = node.get("paper_id")
            if owner is not None and owner != paper_id:
                omitted.append({"node_id": cid, "kind": "claim", "reason": _LEX + "_owner_mismatch"})
                continue
            if paper_id not in known and owner is None:
                omitted.append({"node_id": cid, "kind": "claim", "reason": _LEX + "_paper_unknown"})
                continue
            rebound += 1
            if cid in seen:
                continue
            seen.add(cid)
            if len(candidates) < CANDIDATE_K:
                candidates.append({"node": node, "rank": len(candidates) + 1, "detail": None})
    return candidates, omitted, rebound, unbound


def _kind_reason(node, kind, concept_kind):
    node_kind = node["kind"]
    attrs = node.get("attributes") or {}
    if kind == "paper":
        return None if node_kind == "paper" else "kind_filter"
    if kind == "claim":
        return None if node_kind == "claim" else "kind_filter"
    if kind == "experiment":
        return None if node_kind == "experiment_condition" else "kind_filter"
    if kind == "config":
        if node_kind == "capability" and attrs.get("declaration_kind") == "config":
            return None
        return "kind_filter"
    if kind == "code":
        if node_kind in {"code_lineage", "code_ref"}:
            return None
        if node_kind == "capability" and attrs.get("declaration_kind") in {"code", "readme_only", None}:
            return None
        return "kind_filter"
    if kind == "concept":
        if node_kind != "concept":
            return "kind_filter"
        if concept_kind is not None and attrs.get("concept_kind") != concept_kind:
            return "concept_kind_filter"
        return None
    if concept_kind is not None and node_kind == "concept" and attrs.get("concept_kind") != concept_kind:
        return "concept_kind_filter"
    return None


def _filter_route(route, kind, concept_kind, omitted, seen_omit):
    kept = []
    for item in route:
        node = item["node"]
        reason = _kind_reason(node, kind, concept_kind)
        if reason is None:
            kept.append(item)
            continue
        nid = node["node_id"]
        if nid not in seen_omit:
            seen_omit.add(nid)
            omitted.append({"node_id": nid, "kind": node["kind"], "reason": reason})
    for index, item in enumerate(kept, 1):
        item["rank"] = index
    return kept


def _fuse(routes):
    scores = {}
    reasons = {}
    nodes = {}
    order = ("exact", "graph", _LEX)
    for name in order:
        for item in routes.get(name) or []:
            nid = item["node"]["node_id"]
            nodes[nid] = item["node"]
            scores[nid] = scores.get(nid, Fraction(0)) + Fraction(1, RANK_CONSTANT + item["rank"])
            reasons.setdefault(nid, []).append(
                {"route": name, "rank": item["rank"], "detail": item.get("detail")}
            )
    fused = []
    for nid, score in scores.items():
        fused.append((score, nid, nodes[nid], reasons[nid]))
    fused.sort(key=lambda item: (-item[0], item[1].encode("utf-8")))
    return fused


def _claim_edges(edges, cid):
    return [edge for edge in edges if edge["kind"] == "claim_evidence" and edge["from_node"] == cid]


def _budget_excerpt(excerpt, used, withheld, budget):
    if excerpt is None:
        return None, "withheld_budget", used, withheld + 1
    raw = excerpt.encode("utf-8")
    if len(raw) > QUOTE_ITEM_MAX_BYTES or used + len(raw) > budget:
        return None, "withheld_budget", used, withheld + 1
    return excerpt, "bound", used + len(raw), withheld


def _quote_spans_for(node, nodes_by_id, edges, snapshot, exp, used, withheld, budget):
    spans = []
    kind = node["kind"]
    if kind == "claim":
        for edge in _claim_edges(edges, node["node_id"]):
            if len(spans) >= QUOTE_SPANS_PER_ITEM:
                break
            attrs = edge["attributes"]
            sv = nodes_by_id.get(edge["to_node"]) or {}
            path = (sv.get("attributes") or {}).get("raw_path") or ""
            if not path:
                path = "wiki/meta/ledgers/claim-ledger.json"
            start = attrs["charspan"]["start"]
            end = attrs["charspan"]["end"]
            status = attrs.get("quote_status") or "source_missing"
            excerpt = None
            if status == "bound":
                raw = None
                try:
                    raw = snapshot.read_optional(path, max_bytes=MAX_BYTES)
                except OSError:
                    _changed()
                if raw is None:
                    status = "source_missing"
                else:
                    try:
                        text = raw.decode("utf-8")
                        excerpt = text[start:end]
                    except (UnicodeDecodeError, IndexError):
                        status = "source_changed"
                        excerpt = None
            if status == "bound" and excerpt is not None:
                excerpt, status, used, withheld = _budget_excerpt(excerpt, used, withheld, budget)
            else:
                excerpt = None
            spans.append(
                {
                    "record_kind": "claim_ledger",
                    "record_id": node["node_id"],
                    "json_pointer": edge["source"]["json_pointer"],
                    "path": path,
                    "span": {"start": start, "end": end},
                    "quote_sha256": attrs.get("excerpt_sha256") or ("0" * 64),
                    "relation": attrs.get("relation"),
                    "status": status if status != "bound" or excerpt is not None else "withheld_budget",
                    "excerpt": excerpt,
                }
            )
        legacy = (node.get("attributes") or {}).get("legacy_locators") or 0
        for _index in range(min(legacy, QUOTE_SPANS_PER_ITEM - len(spans))):
            spans.append(
                {
                    "record_kind": "claim_ledger",
                    "record_id": node["node_id"],
                    "json_pointer": "",
                    "path": "wiki/meta/ledgers/claim-ledger.json",
                    "span": None,
                    "quote_sha256": "0" * 64,
                    "relation": None,
                    "status": "not_rechecked",
                    "excerpt": None,
                }
            )
        return spans, used, withheld
    if kind == "experiment_condition":
        rec = exp.records.get(node["attributes"]["head_record_id"])
        if rec is None:
            return spans, used, withheld
        for _key, pointer, source in _iter_sources(rec):
            if source.get("kind") != "paper_direct":
                continue
            if len(spans) >= QUOTE_SPANS_PER_ITEM:
                break
            locator = source["locator"]
            status = _recheck_a_locator(snapshot, locator)
            mapped = {
                "bound": "bound",
                "artifact_missing": "source_missing",
                "artifact_changed": "source_changed",
                "ref_unresolvable": "excerpt_changed",
                "text_mismatch": "excerpt_changed",
                "page_mismatch": "excerpt_changed",
            }.get(status, "excerpt_changed")
            excerpt = None
            path = locator.get("artifact_path") or ""
            if mapped == "bound":
                try:
                    raw = snapshot.read_optional(path, max_bytes=MAX_BYTES)
                except OSError:
                    _changed()
                if raw is None:
                    mapped = "source_missing"
                else:
                    try:
                        document = parse_strict_json(raw, invalid_code="GRAPH_QUERY_VIEW_INVALID")
                        node_doc = _resolve_pointer(document, locator["ref"])
                        excerpt = node_doc["text"]
                    except (SecureIOError, ValueError, KeyError, IndexError, TypeError, UnicodeError):
                        mapped = "excerpt_changed"
                        excerpt = None
            if mapped == "bound" and excerpt is not None:
                excerpt, mapped, used, withheld = _budget_excerpt(excerpt, used, withheld, budget)
            else:
                excerpt = None
            text_sha = locator.get("text_sha256") or ("0" * 64)
            spans.append(
                {
                    "record_kind": "experiment_record",
                    "record_id": rec["record_id"],
                    "json_pointer": pointer,
                    "path": path or "wiki/meta/experiments",
                    "span": None,
                    "quote_sha256": text_sha,
                    "relation": None,
                    "status": mapped if mapped != "bound" or excerpt is not None else "withheld_budget",
                    "excerpt": excerpt,
                }
            )
        return spans, used, withheld
    return spans, used, withheld


def _support_for(node, nodes_by_id, edges):
    kind = node["kind"]
    zero = {"supports": 0, "contradicts": 0, "uncertain": 0}
    if kind == "claim":
        attrs = node["attributes"]
        return {
            "supports": attrs.get("supports") or 0,
            "contradicts": attrs.get("contradicts") or 0,
            "uncertain": attrs.get("uncertain") or 0,
        }
    if kind == "paper":
        total = {"supports": 0, "contradicts": 0, "uncertain": 0}
        for edge in edges:
            if edge["kind"] == "claim_about" and edge["to_node"] == node["node_id"]:
                claim = nodes_by_id.get(edge["from_node"])
                if claim is None:
                    continue
                part = _support_for(claim, nodes_by_id, edges)
                for key in total:
                    total[key] += part[key]
        return total
    if kind == "experiment_condition":
        total = {"supports": 0, "contradicts": 0, "uncertain": 0}
        for edge in edges:
            if edge["kind"] == "condition_claim" and edge["from_node"] == node["node_id"]:
                claim = nodes_by_id.get(edge["to_node"])
                if claim is None:
                    continue
                part = _support_for(claim, nodes_by_id, edges)
                for key in total:
                    total[key] += part[key]
        return total
    return zero


def _oppose_rows(node, nodes_by_id, edges):
    kind = node["kind"]
    rows = []
    if kind == "claim":
        for edge in _claim_edges(edges, node["node_id"]):
            if edge["attributes"].get("relation") != "contradicts":
                continue
            rows.append(
                {
                    "kind": "claim_contradicts",
                    "other_node_id": edge["to_node"],
                    "record_id": node["node_id"],
                    "json_pointer": edge["source"]["json_pointer"],
                    "verdict": None,
                    "ranking": None,
                }
            )
    elif kind == "experiment_condition":
        for edge in edges:
            if edge["kind"] != "comparability":
                continue
            if edge["from_node"] != node["node_id"] and edge["to_node"] != node["node_id"]:
                continue
            count = edge["attributes"].get("contradiction_candidate_count") or 0
            if count <= 0:
                continue
            other = edge["to_node"] if edge["from_node"] == node["node_id"] else edge["from_node"]
            rows.append(
                {
                    "kind": "contradiction_candidate",
                    "other_node_id": other,
                    "record_id": node["attributes"]["head_record_id"],
                    "json_pointer": "",
                    "verdict": edge["attributes"].get("verdict"),
                    "ranking": edge["attributes"].get("ranking"),
                }
            )
    elif kind == "paper":
        for edge in edges:
            if edge["kind"] == "claim_about" and edge["to_node"] == node["node_id"]:
                claim = nodes_by_id.get(edge["from_node"])
                if claim is not None:
                    rows.extend(_oppose_rows(claim, nodes_by_id, edges))
            if edge["kind"] == "reports_condition" and edge["from_node"] == node["node_id"]:
                cond = nodes_by_id.get(edge["to_node"])
                if cond is not None:
                    rows.extend(_oppose_rows(cond, nodes_by_id, edges))
    return rows


def _oppose_for(node, nodes_by_id, edges):
    rows = _oppose_rows(node, nodes_by_id, edges)
    rows.sort(
        key=lambda item: (
            item["kind"].encode("utf-8"),
            (item["other_node_id"] or "").encode("utf-8"),
        )
    )
    truncated = len(rows) > OPPOSE_MAX
    return rows[:OPPOSE_MAX], truncated


def _recovery(node):
    kind = node["kind"]
    status = node.get("status")
    attrs = node.get("attributes") or {}
    if kind in {"code_lineage", "claim"} and (
        status == "stale" or attrs.get("freshness") == "stale" or attrs.get("relation_status") == "stale"
    ):
        return "re_record_annotation"
    if kind == "experiment_condition" and status == "stale":
        return "re_record_condition"
    if kind == "source_version" and (
        attrs.get("association_status") != "bound" or attrs.get("source_status") != "bound"
    ):
        return "repair_store"
    return "none"


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("GRAPH_QUERY_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, QUERY_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise GraphQueryError(
            "GRAPH_QUERY_VIEW_INVALID",
            MESSAGES["GRAPH_QUERY_VIEW_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_store",
                "reason": "schema",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed


def _query(snapshot, store, authority, *, text, toks, kind, concept_kind, paper_id, limit, third):
    exp = _load_experiment_store(snapshot)
    heads = derive_domain_heads(store)
    basis = _experiment_basis(snapshot, store, authority, exp)
    nodes, edges, known = _build_graph(snapshot, store, authority, exp, heads)
    if paper_id is not None and paper_id not in known:
        _fail(
            "GRAPH_QUERY_PAPER_UNKNOWN",
            "/paper_id",
            "check_paper_id",
            {"known_paper_count": len(known)},
        )
    nodes, edges = _filter_graph(nodes, edges, paper_id)
    _paper_counts_and_status(None, nodes, edges)
    digest = graph_sha256(nodes, edges)
    exact = _exact_route(nodes, toks)
    graph_hits, seed_count = _graph_route(nodes, edges, exact)
    omitted = []
    rebound = 0
    unbound = 0
    third_hits = []
    if third is None:
        third_route = {
            "name": _LEX,
            "supplied": False,
            "candidate_count": 0,
            "currency": "not_supplied",
            "rebound_units": 0,
            "unbound_units": 0,
        }
        currency_third = {"binding": "not_supplied"}
        not_supplied = [_LEX]
    else:
        third_hits, third_omitted, rebound, unbound = _third_route(nodes, known, authority, third)
        omitted.extend(third_omitted)
        third_route = {
            "name": _LEX,
            "supplied": True,
            "candidate_count": 0,
            "currency": "unit_rebound_only",
            "rebound_units": rebound,
            "unbound_units": unbound,
        }
        currency_third = {
            "binding": "unit_rebound_only",
            "join_generation_sha256": third["join_generation_sha256"],
            "mapping_sha256": third["mapping_sha256"],
            "retrieval_config_sha256": third["retrieval_config_sha256"],
            "catalog_generation_sha256": third["catalog_generation_sha256"],
        }
        not_supplied = []
    seen_omit = {item["node_id"] for item in omitted if item.get("node_id")}
    exact_f = _filter_route(exact, kind, concept_kind, omitted, seen_omit)
    graph_f = _filter_route(graph_hits, kind, concept_kind, omitted, seen_omit)
    third_f = _filter_route(third_hits, kind, concept_kind, omitted, seen_omit)
    third_route["candidate_count"] = len(third_f)
    fused = _fuse({"exact": exact_f, "graph": graph_f, _LEX: third_f})
    fused_total = len(fused)
    included_rows = fused[:limit]
    budget_omitted = fused[limit:]
    omitted_by_budget = 0
    for _score, nid, node, _reasons in budget_omitted:
        omitted.append({"node_id": nid, "kind": node["kind"], "reason": "budget_limit"})
        omitted_by_budget += 1
    nodes_by_id = {node["node_id"]: node for node in nodes}
    used = 0
    withheld = 0
    oppose_shortfall = False
    included = []
    for rank, (score, nid, node, reasons) in enumerate(included_rows, 1):
        quotes, used, withheld = _quote_spans_for(
            node, nodes_by_id, edges, snapshot, exp, used, withheld, QUOTE_BYTES_BUDGET
        )
        oppose, truncated = _oppose_for(node, nodes_by_id, edges)
        if truncated:
            oppose_shortfall = True
        included.append(
            {
                "rank": rank,
                "node_id": nid,
                "kind": node["kind"],
                "label": node["label"],
                "paper_id": node.get("paper_id"),
                "status": node["status"],
                "stale_reasons": list(node.get("stale_reasons") or []),
                "fused_score": {
                    "numerator": str(score.numerator),
                    "denominator": str(score.denominator),
                },
                "ranking_reasons": reasons,
                "quote_spans": quotes,
                "support": _support_for(node, nodes_by_id, edges),
                "oppose_evidence": oppose,
                "recovery": _recovery(node),
            }
        )
    next_action = "none"
    for item in included:
        if item["recovery"] != "none":
            next_action = item["recovery"]
            break
    if next_action == "none" and unbound > 0:
        next_action = "rebuild_" + _LEX + "_index"
    if next_action == "none" and (omitted_by_budget > 0 or withheld > 0):
        next_action = "narrow_query_or_raise_limit"
    shortfall = (
        omitted_by_budget > 0
        or withheld > 0
        or bool(not_supplied)
        or oppose_shortfall
    )
    view = {
        "schema": QUERY_SCHEMA,
        "basis": basis,
        "graph_sha256": digest,
        "query": {
            "text": text,
            "kind": kind,
            "concept_kind": concept_kind,
            "paper_id": paper_id,
            "limit": limit,
            "tokens": toks,
        },
        "fusion": {
            "algorithm": "rrf-v1",
            "rank_constant": 60,
            "candidate_k": 24,
            "score_arithmetic": "exact_fraction",
        },
        "routes": [
            {
                "name": "exact",
                "supplied": True,
                "candidate_count": len(exact_f),
                "currency": "formal_basis",
            },
            {
                "name": "graph",
                "supplied": True,
                "candidate_count": len(graph_f),
                "currency": "formal_basis",
                "seed_count": seed_count,
            },
            third_route,
        ],
        "included": included,
        "omitted": omitted,
        "budget": {
            "limit": limit,
            "candidate_k": 24,
            "quote_bytes_budget": 8192,
            "quote_bytes_used": used,
            "quote_spans_per_item": 4,
            "fused_total": fused_total,
            "included_count": len(included),
            "omitted_by_budget": omitted_by_budget,
            "quotes_withheld": withheld,
            "routes_not_supplied": not_supplied,
            "shortfall": shortfall,
        },
        "currency": {
            "formal_basis": "verified",
            "source_catalog": "not_consulted",
            _LEX: currency_third,
        },
        "write_kind": "read_only",
        "publication": "unpublished",
        "audit_coverage": "not_wired",
        "fact_source": "formal_records",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "taxonomy_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": next_action,
    }
    return _seal(view)


def query_domain_graph(
    *,
    vault_root,
    text,
    kind="all",
    concept_kind=None,
    paper_id=None,
    limit=8,
    ranking_path=None,
):
    toks = _check_text(text)
    _check_kind(kind)
    _check_concept_kind(concept_kind, kind)
    _check_limit(limit)
    _check_paper_id(paper_id)
    third = None if ranking_path is None else _load_rank_file(ranking_path)

    def apply(snapshot, store, authority):
        try:
            return _query(
                snapshot,
                store,
                authority,
                text=text,
                toks=toks,
                kind=kind,
                concept_kind=concept_kind,
                paper_id=paper_id,
                limit=limit,
                third=third,
            )
        except GraphQueryError:
            raise
        except GraphProjectionError:
            raise
        except DomainStoreError:
            raise
        except ExperimentStoreError:
            raise
        except DomainProposalError:
            raise
        except StagingError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
    except GraphQueryError:
        raise
    except GraphProjectionError:
        raise
    except DomainStoreError:
        raise
    except ExperimentStoreError:
        raise
    except StagingError:
        raise
    except OSError:
        _changed()
