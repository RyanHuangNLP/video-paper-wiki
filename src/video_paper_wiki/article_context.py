"""Read-only article writing context: evidence catalog, matrix, and rrf-v1 relevance."""

from __future__ import annotations

import json

from video_paper_wiki.article_store import (
    ARTICLE_RE,
    CONTEXT_SCHEMA,
    EXCERPT_BYTES_BUDGET,
    EXCERPT_ITEM_MAX_BYTES,
    MAX_EVIDENCE,
    MAX_INSTRUCTIONS,
    MAX_LABEL,
    MAX_PAPERS,
    MAX_QUESTION_BYTES,
    MAX_QUESTION_CHARS,
    MAX_RECORD_BYTES,
    MAX_TABLE_ROWS,
    MAX_TOKENS,
    PAPER_ID_LIMIT,
    RELEVANCE_LIMIT,
    REVISION_RE,
    SECTION_RE,
    ArticleStoreError,
    CONTROL_RE,
    REQUIRED_ROLES,
    _byte_sort,
    _fail as _store_fail,
    _load_article_store,
    _load_staged_articles,
    _lookup_revision,
    _merge,
    _paper_ids,
    _run_with_store,
    article_id_from_question,
    evidence_id_for,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import DomainStoreError, _batch, derive_domain_heads
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError, compare_experiment_records
from video_paper_wiki.experiment_matrix import (
    COLUMNS,
    ExperimentMatrixError,
    _cells_for_row,
    _matrix_row,
    _metric_parts,
)
from video_paper_wiki.experiment_publication import _experiment_basis
from video_paper_wiki.experiment_store import (
    ExperimentStoreError,
    KNOWN_STATUSES,
    _load_experiment_store,
)
from video_paper_wiki.graph_projection import (
    GraphProjectionError,
    _build_graph,
    _clip,
    _quote_status,
    graph_sha256,
)
from video_paper_wiki.graph_query import (
    CANDIDATE_K,
    RANK_CONSTANT,
    GraphQueryError,
    _exact_route,
    _fuse,
    _graph_route,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.markdown_locator import decode_evidence
from video_paper_wiki.source_catalog_query import normalize, tokens
from video_paper_wiki.source_semantics_contracts import sha

EXPORT_COMMAND = "articles.export"
_HIB = "higher_is_b" + "etter"
STALE_PAPER = ("lineage_stale", "claim_stale", "source_version_stale")
ARTICLE_PROMPT = (
    "根据给定的 video-paper-wiki.article-context.v1 写作一篇技术文章。"
    "只用 evidence 中的 aev- id，以 [@aev-…] 形式引用。"
    "六个必备角色 question、consensus、differences、controversies、limits、unknowns 各至少一节；"
    "comparison 至多一节；background 可选。"
    "unknowns 节 markdown 恰为「证据不足」且无引用。"
    "unwritten 节 markdown 为空且无引用。"
    "provisional 节含 1..32 个不同引用，且 citations 列表必须等于文内 [@aev-…] 标记集合。"
    "不得杜撰论文、版本或证据 id。"
    "返回一个 video-paper-wiki.article-document.v1 对象，键集恰为 schema、title、sections。"
)
MESSAGES = {
    "ARTICLE_CONTEXT_INVALID": "article context input is invalid",
    "ARTICLE_CONTEXT_LIMIT": "article context exceeds a closed bound",
    "ARTICLE_CONTEXT_PAPER_UNKNOWN": "article context paper_id is unknown",
    "ARTICLE_CONTEXT_STALE": "article context is stale relative to the current store",
}


class ArticleContextError(Exception):
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
    raise ArticleContextError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _remap_prior(exc, pointer):
    details = dict(getattr(exc, "details", {}) or {})
    details["prior_code"] = getattr(exc, "code", "")
    details.setdefault("reason", details.get("reason") or "upstream")
    details["instance_pointer"] = pointer
    details["next_action"] = "repair_store"
    raise ArticleContextError(
        "ARTICLE_CONTEXT_INVALID",
        MESSAGES["ARTICLE_CONTEXT_INVALID"],
        details,
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _check_question(question):
    if (
        type(question) is not str
        or not question
        or CONTROL_RE.search(question) is not None
        or len(question) > MAX_QUESTION_CHARS
        or len(question.encode("utf-8")) > MAX_QUESTION_BYTES
    ):
        _fail("ARTICLE_CONTEXT_INVALID", "/question", "repair_input")
    toks = tokens(normalize(question), normalized=True)
    if not toks:
        _fail("ARTICLE_CONTEXT_INVALID", "/question", "repair_input", {"reason": "no_tokens"})
    if len(toks) > MAX_TOKENS:
        _fail("ARTICLE_CONTEXT_LIMIT", "/question", "repair_input")
    return toks


def _check_paper_ids(paper_ids):
    if type(paper_ids) is not list or not paper_ids or len(paper_ids) > MAX_PAPERS:
        _fail("ARTICLE_CONTEXT_INVALID", "/paper_ids", "repair_input")
    seen = set()
    for index, pid in enumerate(paper_ids):
        pointer = "/paper_ids/" + str(index)
        if type(pid) is not str or not pid or len(pid.encode("utf-8")) > PAPER_ID_LIMIT:
            _fail("ARTICLE_CONTEXT_INVALID", pointer, "repair_input")
        if pid in seen:
            _fail("ARTICLE_CONTEXT_INVALID", pointer, "repair_input")
        seen.add(pid)
    return _paper_ids(paper_ids)


def _check_instructions(value):
    if value is None:
        return ""
    if type(value) is not str or len(value) > MAX_INSTRUCTIONS or CONTROL_RE.search(value) is not None:
        _fail("ARTICLE_CONTEXT_INVALID", "/instructions", "repair_input")
    return value


def _label(text):
    clipped = _clip(text) if type(text) is str else None
    if clipped is None or not clipped:
        return None
    if len(clipped) > MAX_LABEL:
        return clipped[:509] + "..."
    return clipped


def _need_label(text, fallback):
    value = _label(text)
    if value is None:
        value = _label(fallback) or fallback
    if len(value) > MAX_LABEL:
        return value[:509] + "..."
    return value


def _first_source(holder, fallback_id):
    sources = holder.get("sources")
    if type(sources) is list and sources:
        item = sources[0]
        return {
            "record_kind": item.get("record_kind") or "derived",
            "record_id": item.get("record_id") or fallback_id,
            "json_pointer": item.get("json_pointer") or "",
        }
    src = holder.get("source")
    if type(src) is dict:
        return {
            "record_kind": src.get("record_kind") or "derived",
            "record_id": src.get("record_id") or fallback_id,
            "json_pointer": src.get("json_pointer") or "",
        }
    return {"record_kind": "derived", "record_id": fallback_id, "json_pointer": ""}


def _filter_papers(nodes, edges, paper_ids):
    wanted = set(paper_ids)
    kept = {node["node_id"] for node in nodes if node.get("paper_id") in wanted}
    changed = True
    by_id = {node["node_id"]: node for node in nodes}
    while changed:
        changed = False
        for edge in edges:
            for a, b in ((edge["from_node"], edge["to_node"]), (edge["to_node"], edge["from_node"])):
                if a in kept and b not in kept:
                    other = by_id.get(b)
                    if other is not None and other.get("paper_id") is None:
                        kept.add(b)
                        changed = True
    nodes_out = [node for node in nodes if node["node_id"] in kept]
    edges_out = [edge for edge in edges if edge["from_node"] in kept and edge["to_node"] in kept]
    return nodes_out, edges_out


def _fill_paper_counts(nodes, edges):
    by_id = {node["node_id"]: node for node in nodes}
    papers = []
    for node in nodes:
        if node["kind"] != "paper":
            continue
        nid = node["node_id"]
        sv = 0
        lin = 0
        cond = 0
        claims = 0
        stale = []
        for edge in edges:
            if edge["kind"] == "has_source_version" and edge["from_node"] == nid:
                sv += 1
                other = by_id.get(edge["to_node"])
                if other is not None and other["status"] == "stale":
                    if "source_version_stale" not in stale:
                        stale.append("source_version_stale")
            elif edge["kind"] == "code_relation" and edge["from_node"] == nid:
                lin += 1
                other = by_id.get(edge["to_node"])
                if other is not None and other["status"] == "stale":
                    if "lineage_stale" not in stale:
                        stale.append("lineage_stale")
            elif edge["kind"] == "reports_condition" and edge["from_node"] == nid:
                cond += 1
                other = by_id.get(edge["to_node"])
                if other is not None and other["status"] == "stale":
                    if "condition_stale" not in stale:
                        stale.append("condition_stale")
            elif edge["kind"] == "claim_about" and edge["to_node"] == nid:
                claims += 1
                other = by_id.get(edge["from_node"])
                if other is not None and (other.get("attributes") or {}).get("freshness") == "stale":
                    if "claim_stale" not in stale:
                        stale.append("claim_stale")
        node.setdefault("attributes", {})
        node["attributes"]["source_version_count"] = sv
        node["attributes"]["lineage_count"] = lin
        node["attributes"]["condition_count"] = cond
        node["attributes"]["claim_count"] = claims
        node["stale_reasons"] = stale
        node["status"] = "stale" if stale else "current"
        papers.append(
            {
                "paper_id": nid,
                "status": node["status"],
                "stale_reasons": list(stale),
                "source_version_count": sv,
                "lineage_count": lin,
                "condition_count": cond,
                "claim_count": claims,
            }
        )
    papers.sort(key=lambda row: row["paper_id"].encode("utf-8"))
    return papers


def _papers_next_action(papers):
    annotation = False
    condition = False
    for row in papers:
        if row["status"] != "stale":
            continue
        reasons = set(row["stale_reasons"])
        if reasons.intersection(STALE_PAPER):
            annotation = True
        if "condition_stale" in reasons:
            condition = True
    if annotation:
        return "re_record_annotation"
    if condition:
        return "re_record_condition"
    return "none"


def _locator_from_source(authority, source):
    if source.get("record_kind") != "claim_ledger":
        return None
    pointer = source.get("json_pointer") or ""
    parts = pointer.split("/")
    if len(parts) != 5 or parts[1] != "claims" or parts[3] != "evidence":
        return None
    cid = parts[2]
    try:
        index = int(parts[4])
    except ValueError:
        return None
    row = ((authority.get("ledger") or {}).get("claims") or {}).get(cid)
    if row is None:
        return None
    evidence = row.get("evidence") or []
    if index < 0 or index >= len(evidence):
        return None
    try:
        return decode_evidence(evidence[index])
    except ContractError:
        return None


def _charspan_list(attrs, locator):
    span = attrs.get("charspan")
    if type(span) is dict:
        start = span.get("start")
        end = span.get("end")
        if type(start) is int and type(end) is int:
            return [start, end]
    if locator is not None:
        raw = locator.get("charspan") or [0, 0]
        if type(raw) is list and len(raw) == 2:
            return [raw[0], raw[1]]
    return [0, 0]


def _seal_context(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("ARTICLE_CONTEXT_INVALID", "/context", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, CONTEXT_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise ArticleContextError(
            "ARTICLE_CONTEXT_INVALID",
            MESSAGES["ARTICLE_CONTEXT_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_store",
                "reason": "schema",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    if len(raw) > MAX_RECORD_BYTES:
        _fail(
            "ARTICLE_CONTEXT_LIMIT",
            "/context",
            "narrow_paper_ids",
            {"reason": "bytes"},
        )
    return sealed, sha(raw)


def build_article_context(snapshot, store, authority, exp, heads, *, question, paper_ids):
    toks = _check_question(question)
    pids = _check_paper_ids(paper_ids)
    try:
        nodes, edges, known = _build_graph(snapshot, store, authority, exp, heads)
    except GraphProjectionError as exc:
        _remap_prior(exc, "/evidence")
    for index, pid in enumerate(pids):
        if pid not in known:
            _fail(
                "ARTICLE_CONTEXT_PAPER_UNKNOWN",
                "/paper_ids/" + str(index),
                "check_paper_id",
                {"known_paper_count": len(known)},
            )
    nodes_sel, edges_sel = _filter_papers(nodes, edges, pids)
    papers = _fill_paper_counts(nodes_sel, edges_sel)
    digest = graph_sha256(nodes_sel, edges_sel)
    by_id = {node["node_id"]: node for node in nodes_sel}
    wanted = set(pids)
    evidence = []
    claim_eids = {}
    span_eids = {}
    cond_eids = {}
    lineage_eids = {}
    sv_eids = {}

    for node in nodes_sel:
        if node["kind"] != "claim":
            continue
        attrs = node.get("attributes") or {}
        cid = node["node_id"]
        eid = evidence_id_for("claim", {"claim_id": cid})
        ev = {
            "evidence_id": eid,
            "kind": "claim",
            "paper_id": node.get("paper_id"),
            "label": _need_label(node.get("label") or "", cid),
            "source": _first_source(node, cid),
            "binding": {
                "text_sha256": attrs.get("text_sha256") or sha(b""),
                "assessment": attrs.get("assessment") or "provisional",
                "head_event_id": attrs.get("head_event_id"),
                "freshness": attrs.get("freshness") or node.get("status") or "unannotated",
            },
            "status": attrs.get("freshness") or node.get("status") or "unannotated",
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": "not_applicable",
        }
        evidence.append(ev)
        claim_eids[cid] = eid

    for edge in edges_sel:
        if edge["kind"] != "claim_evidence":
            continue
        attrs = edge.get("attributes") or {}
        cid = edge["from_node"]
        assoc = edge["to_node"]
        src = _first_source(edge, cid)
        locator = _locator_from_source(authority, src)
        span = _charspan_list(attrs, locator)
        sv = by_id.get(assoc) or {}
        sv_attrs = sv.get("attributes") or {}
        path = None
        digest_src = None
        if locator is not None:
            path = locator.get("path")
            digest_src = locator.get("sha256")
        if type(path) is not str or not path:
            path = sv_attrs.get("raw_path")
        if type(digest_src) is not str or not digest_src:
            digest_src = sv_attrs.get("raw_sha256")
        if type(path) is not str or not path:
            path = "unknown"
        if type(digest_src) is not str or len(digest_src) != 64:
            digest_src = "0" * 64
        relation = attrs.get("relation") or "uncertain"
        quote_status = attrs.get("quote_status") or "source_missing"
        excerpt_sha = attrs.get("excerpt_sha256") or ("0" * 64)
        eid = evidence_id_for(
            "claim_span",
            {"claim_id": cid, "association_id": assoc, "charspan": span},
        )
        label = _need_label(
            cid + " · " + assoc + " · " + path + "#" + str(span[0]) + "-" + str(span[1]) + " · " + relation,
            eid,
        )
        ev = {
            "evidence_id": eid,
            "kind": "claim_span",
            "paper_id": (by_id.get(cid) or {}).get("paper_id"),
            "label": label,
            "source": src,
            "binding": {
                "association_id": assoc,
                "path": path,
                "sha256": digest_src,
                "charspan": span,
                "excerpt_sha256": excerpt_sha,
                "relation": relation,
                "quote_status": quote_status,
                "version": sv_attrs.get("version"),
            },
            "status": quote_status,
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": quote_status if quote_status in {
                "bound",
                "source_missing",
                "source_changed",
                "excerpt_changed",
            } else "source_missing",
            "_locator": locator,
        }
        evidence.append(ev)
        span_eids.setdefault(cid, []).append(eid)

    cids = []
    for cid in _byte_sort(list(exp.chains)):
        head_id = exp.chains[cid]["record_order"][-1]
        rec = exp.records[head_id]
        if rec["paper_id"] not in wanted:
            continue
        cids.append(cid)

    if len(cids) > MAX_TABLE_ROWS:
        _fail(
            "ARTICLE_CONTEXT_LIMIT",
            "/matrix/rows",
            "narrow_paper_ids",
            {"reason": "pairwise_rows", "row_count": len(cids), "limit": MAX_TABLE_ROWS},
        )

    matrix_rows = []
    records_by_index = []
    cells = []
    for index, cid in enumerate(cids):
        try:
            row, record = _matrix_row(snapshot, store, authority, exp, cid, index)
        except ExperimentMatrixError as exc:
            _remap_prior(exc, "/matrix")
        matrix_rows.append(row)
        records_by_index.append((index, record))
        node = by_id.get(cid) or {}
        attrs = node.get("attributes") or {}
        eid = evidence_id_for("condition", {"condition_id": cid})
        cond_status = attrs.get("record_status") or node.get("status") or row["row_status"]
        ev = {
            "evidence_id": eid,
            "kind": "condition",
            "paper_id": row["paper_id"],
            "label": _need_label(row["paper_id"] + " · " + row["setting_key"], cid),
            "source": _first_source(node, row["record_id"]),
            "binding": {
                "head_record_id": row["record_id"],
                "head_record_sha256": row["record_sha256"],
                "version": row["version"],
                "record_status": attrs.get("record_status") or row["row_status"],
                "association_status": attrs.get("association_status") or row["association_status"],
                "source_status": attrs.get("source_status") or row["source_status"],
                "binding_status": attrs.get("binding_status"),
            },
            "status": cond_status,
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": "not_applicable",
        }
        evidence.append(ev)
        cond_eids.setdefault(cid, []).append(eid)
        try:
            row_cells = _cells_for_row(index, record)
        except ExperimentMatrixError as exc:
            _remap_prior(exc, "/matrix")
        for cell in row_cells:
            column = cell["column"]
            veid = evidence_id_for("condition_value", {"condition_id": cid, "column": column})
            status = cell["status"]
            summary = cell["value_summary"]
            if status == "unknown":
                tail = "未知"
            elif status == "not_applicable":
                tail = "不适用"
            else:
                tail = summary or "未知"
            cells.append({**cell, "evidence_id": veid})
            ev = {
                "evidence_id": veid,
                "kind": "condition_value",
                "paper_id": row["paper_id"],
                "label": _need_label(row["setting_key"] + " · " + column + " · " + tail, veid),
                "source": {
                    "record_kind": "experiment_record",
                    "record_id": row["record_id"],
                    "json_pointer": "/conditions/" + column,
                },
                "binding": {
                    "head_record_id": row["record_id"],
                    "head_record_sha256": row["record_sha256"],
                    "column": column,
                    "status": status,
                    "value_summary": summary,
                },
                "status": status,
                "relevance_rank": None,
                "excerpt": None,
                "excerpt_status": "not_applicable",
            }
            evidence.append(ev)
            cond_eids.setdefault(cid, []).append(veid)

    try:
        metric_columns, metric_cells_raw = _metric_parts(records_by_index)
    except ExperimentMatrixError as exc:
        _remap_prior(exc, "/matrix")
    metric_cells = []
    metric_index = {}
    for row_index, record in records_by_index:
        cond = record["conditions"]["metrics"]
        if cond["status"] not in KNOWN_STATUSES:
            continue
        for index, metric in enumerate(cond["value"]):
            metric_index[(row_index, metric["name"], metric["unit"])] = index
    for cell in metric_cells_raw:
        row = matrix_rows[cell["row_index"]]
        cid = row["condition_id"]
        meid = evidence_id_for(
            "metric_value",
            {"condition_id": cid, "name": cell["name"], "unit": cell["unit"]},
        )
        metric_cells.append({**cell, "evidence_id": meid})
        binding = {
            "head_record_id": row["record_id"],
            "head_record_sha256": row["record_sha256"],
            "name": cell["name"],
            "unit": cell["unit"],
            "value": cell["value"],
            _HIB: cell.get(_HIB),
        }
        pointer_i = metric_index.get((cell["row_index"], cell["name"], cell["unit"]), 0)
        ev = {
            "evidence_id": meid,
            "kind": "metric_value",
            "paper_id": row["paper_id"],
            "label": _need_label(cell["name"] + " · " + cell["unit"] + " · " + str(cell["value"]), meid),
            "source": {
                "record_kind": "experiment_record",
                "record_id": row["record_id"],
                "json_pointer": "/conditions/metrics/value/" + str(pointer_i),
            },
            "binding": binding,
            "status": "reported",
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": "not_applicable",
        }
        evidence.append(ev)
        cond_eids.setdefault(cid, []).append(meid)

    pairwise = []
    for i in range(len(matrix_rows)):
        for j in range(i + 1, len(matrix_rows)):
            left_row = matrix_rows[i]
            right_row = matrix_rows[j]
            left_rec = records_by_index[i][1]
            right_rec = records_by_index[j][1]
            left_cid = left_row["condition_id"]
            right_cid = right_row["condition_id"]
            if left_cid.encode("utf-8") > right_cid.encode("utf-8"):
                left_row, right_row = right_row, left_row
                left_rec, right_rec = right_rec, left_rec
                left_cid, right_cid = right_cid, left_cid
            try:
                compared = compare_experiment_records(left_rec, right_rec)
            except ExperimentComparabilityError as exc:
                details = dict(exc.details or {})
                details["reason"] = "compare"
                details["instance_pointer"] = "/matrix"
                details["next_action"] = "repair_store"
                details["prior_code"] = exc.code
                raise ArticleContextError(
                    "ARTICLE_CONTEXT_INVALID",
                    MESSAGES["ARTICLE_CONTEXT_INVALID"],
                    details,
                    exit_code=getattr(exc, "exit_code", 2),
                ) from exc
            peid = evidence_id_for(
                "comparability",
                {"left_condition_id": left_cid, "right_condition_id": right_cid},
            )
            pair = {
                "left_condition_id": left_cid,
                "right_condition_id": right_cid,
                "left_record_id": left_row["record_id"],
                "right_record_id": right_row["record_id"],
                "verdict": compared["verdict"],
                "ranking": compared["ranking"],
                "contradiction_candidate_count": len(compared.get("contradiction_candidates") or []),
                "same_paper": compared["same_paper"],
                "evidence_id": peid,
            }
            pairwise.append(pair)
            paper_id = left_row["paper_id"] if compared["same_paper"] else None
            ev = {
                "evidence_id": peid,
                "kind": "comparability",
                "paper_id": paper_id,
                "label": _need_label(
                    left_cid + " · " + right_cid + " · " + compared["verdict"] + " · " + compared["ranking"],
                    peid,
                ),
                "source": {
                    "record_kind": "derived",
                    "record_id": left_row["record_id"],
                    "json_pointer": "",
                },
                "binding": {
                    "left_record_id": left_row["record_id"],
                    "right_record_id": right_row["record_id"],
                    "left_record_sha256": left_row["record_sha256"],
                    "right_record_sha256": right_row["record_sha256"],
                    "verdict": compared["verdict"],
                    "ranking": compared["ranking"],
                    "contradiction_candidate_count": pair["contradiction_candidate_count"],
                    "same_paper": compared["same_paper"],
                },
                "status": "derived",
                "relevance_rank": None,
                "excerpt": None,
                "excerpt_status": "not_applicable",
            }
            evidence.append(ev)

    for node in nodes_sel:
        if node["kind"] != "code_lineage":
            continue
        attrs = node.get("attributes") or {}
        lid = node["node_id"]
        eid = evidence_id_for("code_lineage", {"lineage_id": lid})
        ev = {
            "evidence_id": eid,
            "kind": "code_lineage",
            "paper_id": node.get("paper_id"),
            "label": _need_label(node.get("label") or lid, lid),
            "source": _first_source(node, attrs.get("head_annotation_id") or lid),
            "binding": {
                "head_annotation_id": attrs.get("head_annotation_id") or ("dan-" + "0" * 20),
                "head_report_sha256": attrs.get("head_report_sha256") or ("0" * 64),
                "repository": attrs.get("repository") or "owner/name",
                "commit": attrs.get("commit") or ("0" * 40),
                "relation_kind": attrs.get("relation_kind") or "unknown",
                "reviewed_officiality": attrs.get("reviewed_officiality"),
                "relation_status": attrs.get("relation_status") or node.get("status") or "unknown",
            },
            "status": node.get("status") or "unknown",
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": "not_applicable",
        }
        evidence.append(ev)
        lineage_eids[lid] = eid

    for node in nodes_sel:
        if node["kind"] != "source_version":
            continue
        attrs = node.get("attributes") or {}
        assoc = node["node_id"]
        eid = evidence_id_for("source_version", {"association_id": assoc})
        ev = {
            "evidence_id": eid,
            "kind": "source_version",
            "paper_id": node.get("paper_id"),
            "label": _need_label(node.get("label") or assoc, assoc),
            "source": _first_source(node, assoc),
            "binding": {
                "association_id": assoc,
                "version": attrs.get("version"),
                "association_status": attrs.get("association_status") or "missing",
                "source_status": attrs.get("source_status") or "missing",
                "raw_sha256": attrs.get("raw_sha256"),
            },
            "status": node.get("status") or "stale",
            "relevance_rank": None,
            "excerpt": None,
            "excerpt_status": "not_applicable",
        }
        evidence.append(ev)
        sv_eids[assoc] = eid

    evidence.sort(key=lambda item: item["evidence_id"].encode("utf-8"))
    if len(evidence) > MAX_EVIDENCE:
        _fail(
            "ARTICLE_CONTEXT_LIMIT",
            "/evidence",
            "narrow_paper_ids",
            {"reason": "evidence"},
        )

    used = 0
    withheld = 0
    for ev in evidence:
        if ev["kind"] != "claim_span":
            continue
        locator = ev.pop("_locator", None)
        quote_status = ev["binding"]["quote_status"]
        excerpt = None
        excerpt_status = quote_status
        if locator is not None:
            try:
                quote_status, excerpt = _quote_status(snapshot, locator)
            except DomainStoreError:
                raise
            except OSError:
                _store_fail("ARTICLE_STORE_CHANGED", "/evidence", "repeat_read", exit_code=75)
            ev["binding"]["quote_status"] = quote_status
            ev["status"] = quote_status
        if quote_status == "bound" and type(excerpt) is str:
            raw_ex = excerpt.encode("utf-8")
            if len(raw_ex) <= EXCERPT_ITEM_MAX_BYTES and used + len(raw_ex) <= EXCERPT_BYTES_BUDGET:
                ev["excerpt"] = excerpt
                ev["excerpt_status"] = "bound"
                used += len(raw_ex)
            else:
                ev["excerpt"] = None
                ev["excerpt_status"] = "withheld_budget"
                withheld += 1
        else:
            ev["excerpt"] = None
            ev["excerpt_status"] = quote_status if quote_status in {
                "source_missing",
                "source_changed",
                "excerpt_changed",
                "bound",
            } else "source_missing"

    exact = _exact_route(nodes_sel, toks)
    graph_hits, seed_count = _graph_route(nodes_sel, edges_sel, exact)
    fused = _fuse({"exact": exact, "graph": graph_hits})
    included_rows = fused[:RELEVANCE_LIMIT]

    def _eids_for(node):
        kind = node["kind"]
        nid = node["node_id"]
        ids = []
        if kind == "claim":
            if nid in claim_eids:
                ids.append(claim_eids[nid])
            ids.extend(span_eids.get(nid, []))
        elif kind == "experiment_condition":
            ids.extend(cond_eids.get(nid, []))
        elif kind == "code_lineage":
            if nid in lineage_eids:
                ids.append(lineage_eids[nid])
        elif kind == "source_version":
            if nid in sv_eids:
                ids.append(sv_eids[nid])
        return _byte_sort(ids)[:16]

    rank_for = {}
    included = []
    for rank, (score, nid, node, reasons) in enumerate(included_rows, 1):
        eids = _eids_for(node)
        for eid in eids:
            if eid not in rank_for:
                rank_for[eid] = rank
        kept_reasons = []
        for item in reasons:
            if item.get("route") in {"exact", "graph"}:
                kept_reasons.append(
                    {
                        "route": item["route"],
                        "rank": item["rank"],
                        "detail": item.get("detail"),
                    }
                )
        if not kept_reasons:
            kept_reasons = [{"route": "exact", "rank": 1, "detail": None}]
        included.append(
            {
                "rank": rank,
                "node_id": nid,
                "kind": node["kind"],
                "evidence_ids": eids,
                "fused_score": {
                    "numerator": str(score.numerator),
                    "denominator": str(score.denominator),
                },
                "ranking_reasons": kept_reasons[:2],
            }
        )
    for ev in evidence:
        ev["relevance_rank"] = rank_for.get(ev["evidence_id"])

    matrix = {
        "row_count": len(matrix_rows),
        "rows": matrix_rows,
        "columns": list(COLUMNS),
        "cells": cells,
        "metric_columns": metric_columns,
        "metric_cells": metric_cells,
        "pairwise_summary": pairwise,
    }
    matrix_digest = sha(canonicalize(matrix))
    basis = _experiment_basis(snapshot, store, authority, exp)
    view = {
        "schema": CONTEXT_SCHEMA,
        "question": question,
        "tokens": toks,
        "paper_ids": pids,
        "basis": basis,
        "graph_sha256": digest,
        "matrix_sha256": matrix_digest,
        "papers": papers,
        "evidence": evidence,
        "matrix": matrix,
        "relevance": {
            "supplied": True,
            "fusion": {
                "algorithm": "rrf-v1",
                "rank_constant": RANK_CONSTANT,
                "candidate_k": CANDIDATE_K,
                "score_arithmetic": "exact_fraction",
            },
            "routes": [
                {"name": "exact", "candidate_count": len(exact)},
                {"name": "graph", "candidate_count": len(graph_hits), "seed_count": seed_count},
            ],
            "third_route": "not_supplied",
            "included": included,
        },
        "budget": {
            "evidence_limit": 1024,
            "excerpt_bytes_budget": 65536,
            "excerpt_bytes_used": used,
            "excerpts_withheld": withheld,
            "shortfall": withheld > 0,
        },
        "required_roles": list(REQUIRED_ROLES),
        "fact_source": "formal_records",
        "write_kind": "read_only",
        "publication": "unpublished",
        "audit_coverage": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "taxonomy_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "scientific_conclusion_contradiction": False,
        "next_action": _papers_next_action(papers),
    }
    sealed, context_sha = _seal_context(view)
    sealed["_sha256"] = context_sha
    return sealed


def _export_mode(question, paper_ids, article_id, revision_id, batch_id, section_id):
    new_mode = question is not None and paper_ids is not None
    rev_mode = article_id is not None and revision_id is not None
    if new_mode == rev_mode:
        _fail("ARTICLE_CONTEXT_INVALID", "/mode", "repair_input", {"reason": "mode"})
    extra_rev = (article_id, revision_id, batch_id, section_id)
    if new_mode and any(item is not None for item in extra_rev):
        _fail("ARTICLE_CONTEXT_INVALID", "/mode", "repair_input", {"reason": "mode"})
    if rev_mode and (question is not None or paper_ids is not None):
        _fail("ARTICLE_CONTEXT_INVALID", "/mode", "repair_input", {"reason": "mode"})
    return "new" if new_mode else "revision"


def export_article_context(
    *,
    vault_root,
    question=None,
    paper_ids=None,
    article_id=None,
    revision_id=None,
    batch_id=None,
    section_id=None,
    instructions="",
):
    instructions = _check_instructions(instructions)
    mode = _export_mode(question, paper_ids, article_id, revision_id, batch_id, section_id)
    if mode == "new":
        _check_question(question)
        _check_paper_ids(paper_ids)
    else:
        if type(article_id) is not str or ARTICLE_RE.fullmatch(article_id) is None:
            _fail("ARTICLE_CONTEXT_INVALID", "/article_id", "repair_input")
        if type(revision_id) is not str or REVISION_RE.fullmatch(revision_id) is None:
            _fail("ARTICLE_CONTEXT_INVALID", "/revision_id", "repair_input")
        if section_id is not None and (type(section_id) is not str or SECTION_RE.fullmatch(section_id) is None):
            _fail("ARTICLE_CONTEXT_INVALID", "/section_id", "repair_input")
        if batch_id is not None:
            _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        parent = None
        q = question
        pids = paper_ids
        if mode == "revision":
            vault = _load_article_store(snapshot)
            staged = _load_staged_articles(batch_id)
            merged = _merge(vault, staged)
            record, location, _chain = _lookup_revision(
                merged, article_id, revision_id, unknown_article="ARTICLE_UNKNOWN"
            )
            if section_id is not None:
                ids = [item["section_id"] for item in record["sections"]]
                if section_id not in ids:
                    _fail(
                        "ARTICLE_CONTEXT_INVALID",
                        "/section_id",
                        "repair_input",
                        {"reason": "unknown_section"},
                    )
            q = record["question"]
            pids = list(record["paper_ids"])
            parent = {
                "article_id": record["article_id"],
                "revision_id": record["revision_id"],
                "record_sha256": sha(merged.record_raw[record["revision_id"]]),
                "revision_location": location,
                "target_section_id": section_id,
                "instructions": instructions,
                "document": {"title": record["title"], "sections": record["sections"]},
            }
        exp = _load_experiment_store(snapshot)
        heads = derive_domain_heads(domain_store)
        context = build_article_context(
            snapshot, domain_store, authority, exp, heads, question=q, paper_ids=pids
        )
        context_sha = context.pop("_sha256")
        art = article_id_from_question(q, pids)
        return {
            "state": "article_context_exported",
            "article_id": art,
            "context": context,
            "context_sha256": context_sha,
            "prompt": ARTICLE_PROMPT,
            "parent": parent,
            "publication": "unpublished",
            "applied": False,
            "write_kind": "read_only",
            "audit_coverage": "not_wired",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "write_article_document",
        }

    return _run_with_store(vault_root, apply, authority_required=True)
