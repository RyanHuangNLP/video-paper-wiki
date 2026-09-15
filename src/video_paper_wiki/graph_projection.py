"""Read-only typed relation graph from D1 and D2 formal records. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import MAX_BYTES, ContractError, validate_document
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_relations import DomainRelationError, _lineage_view as _relation_lineage
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MESSAGES as STORE_MESSAGES,
    _claim_freshness,
    _with_store,
    derive_domain_heads,
)
from video_paper_wiki.domain_versions import (
    DomainVersionsError,
    _lineage_view as _version_lineage,
    _record_path,
    _source_status,
)
from video_paper_wiki.experiment_comparability import ExperimentComparabilityError, _summary, compare_experiment_records
from video_paper_wiki.experiment_publication import ExperimentPublicationError, _experiment_basis
from video_paper_wiki.experiment_store import (
    CONDITION_KEYS,
    KNOWN_STATUSES,
    ExperimentStoreError,
    _byte_sort,
    _condition_row,
    _load_experiment_store,
    _pointer as _store_pointer,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.markdown_locator import decode_evidence
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_catalog_projection import _pointer as _resolve_pointer
from video_paper_wiki.source_catalog_query import normalize
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

PROJECTION_SCHEMA = "video-paper-wiki.domain-graph-projection.v1"
PROJECT_COMMAND = "graph.project"
PAPER_ID_LIMIT = 256
MAX_NODES = 65536
MAX_EDGES = 262144
MAX_PAIRWISE_ROWS = 64
MAX_SEARCH_ITEM = 1024
NODE_KINDS = (
    "paper",
    "source_version",
    "claim",
    "concept",
    "code_lineage",
    "capability",
    "code_ref",
    "experiment_condition",
)
EDGE_KINDS = (
    "has_source_version",
    "claim_about",
    "claim_evidence",
    "mentions_concept",
    "code_relation",
    "declares_capability",
    "handoff_ref",
    "reports_condition",
    "condition_code_binding",
    "condition_claim",
    "comparability",
)
ENDPOINT_TYPES = {
    "has_source_version": ("paper", "source_version"),
    "claim_about": ("claim", "paper"),
    "claim_evidence": ("claim", "source_version"),
    "mentions_concept": ("paper", "concept"),
    "code_relation": ("paper", "code_lineage"),
    "declares_capability": ("code_lineage", "capability"),
    "handoff_ref": ("code_lineage", "code_ref"),
    "reports_condition": ("paper", "experiment_condition"),
    "condition_code_binding": ("experiment_condition", "code_lineage"),
    "condition_claim": ("experiment_condition", "claim"),
    "comparability": ("experiment_condition", "experiment_condition"),
}
MESSAGES = {
    "GRAPH_PROJECTION_INVALID": "domain graph projection input is invalid",
    "GRAPH_PROJECTION_LIMIT": "domain graph projection exceeds a closed bound",
    "GRAPH_PROJECTION_PAPER_UNKNOWN": "domain graph projection paper_id is unknown",
    "GRAPH_PROJECTION_VIEW_INVALID": "domain graph projection view is invalid",
}


class GraphProjectionError(Exception):
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
    raise GraphProjectionError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _changed():
    raise DomainStoreError(
        "DOMAIN_STORE_CHANGED",
        STORE_MESSAGES["DOMAIN_STORE_CHANGED"],
        {"instance_pointer": "/wiki/meta/domain", "next_action": "repeat_read"},
        exit_code=75,
    )


def _check_paper_id(paper_id):
    if paper_id is None:
        return
    if type(paper_id) is not str or not paper_id or len(paper_id.encode("utf-8")) > PAPER_ID_LIMIT:
        _fail("GRAPH_PROJECTION_INVALID", "/paper_id", "repair_input")


def _clip(text):
    if type(text) is not str:
        return None
    if not text:
        return None
    if len(text) > MAX_SEARCH_ITEM:
        return text[:1021] + "..."
    return text


def _clip_list(items):
    out = []
    seen = set()
    for item in items:
        clipped = _clip(item)
        if clipped is None or clipped in seen:
            continue
        seen.add(clipped)
        out.append(clipped)
        if len(out) >= 64:
            break
    return out


def _string_leaves(value):
    if type(value) is str:
        yield value
        return
    if type(value) is dict:
        for child in value.values():
            yield from _string_leaves(child)
        return
    if type(value) is list:
        for child in value:
            yield from _string_leaves(child)


def _unique_add(seq, item):
    if item is None:
        return
    if item not in seq:
        seq.append(item)


def _id_hash(prefix, payload):
    return prefix + sha(canonicalize(payload))[:20]


def _source(record_kind, record_id, json_pointer):
    return {
        "record_kind": record_kind,
        "record_id": record_id,
        "json_pointer": json_pointer,
    }


def _concept_parts(item):
    tax = item.get("taxonomy_ref")
    status = item.get("term_status")
    if status is None:
        status = "taxonomy_v1" if tax is not None else "normalization_proposal"
    if status == "taxonomy_v1" and tax is not None:
        if type(tax) is dict:
            key = tax["axis"] + "/" + tax["slug"]
        else:
            key = tax
        return status, key, key
    surface = item.get("surface_form") or ""
    return "normalization_proposal", "proposal:" + normalize(surface), None


def _read_optional(snapshot, relative):
    try:
        return snapshot.read_optional(relative, max_bytes=MAX_BYTES)
    except OSError:
        _changed()


def _remap_view(exc, lid):
    code = getattr(exc, "code", "")
    if isinstance(exc, (DomainRelationError, DomainVersionsError)) and str(code).endswith("_VIEW_INVALID"):
        details = dict(exc.details or {})
        details["prior_code"] = code
        details.setdefault("reason", details.get("reason") or "view")
        details["instance_pointer"] = "/lineages/" + lid
        details["next_action"] = "repair_store"
        raise GraphProjectionError(
            "GRAPH_PROJECTION_INVALID",
            MESSAGES["GRAPH_PROJECTION_INVALID"],
            details,
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    raise


class _Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.edge_ids = set()
        self.claim_owner = {}
        self.claim_kind = {}
        self.claim_fresh = {}
        self.concept_papers = {}
        self.lineage_ids = set()

    def ensure(self, node_id, kind, label, paper_id, status, attributes, source=None):
        node = self.nodes.get(node_id)
        if node is None:
            clipped = _clip(label) or node_id
            node = {
                "node_id": node_id,
                "kind": kind,
                "label": clipped,
                "paper_id": paper_id,
                "status": status,
                "stale_reasons": [],
                "sources": [],
                "search_text": [clipped[:MAX_SEARCH_ITEM] if clipped else node_id],
                "attributes": attributes,
            }
            self.nodes[node_id] = node
            if kind == "concept":
                self.concept_papers[node_id] = set()
        else:
            if paper_id is not None and node["paper_id"] is None:
                node["paper_id"] = paper_id
        if source is not None:
            if source not in node["sources"] and len(node["sources"]) < 64:
                node["sources"].append(source)
        return node

    def edge(self, kind, from_node, to_node, freshness, source, attributes):
        payload = {
            "kind": kind,
            "from_node": from_node,
            "to_node": to_node,
            "json_pointer": source["json_pointer"],
            "record_id": source["record_id"],
        }
        edge_id = _id_hash("edg-", payload)
        if edge_id in self.edge_ids:
            return
        self.edge_ids.add(edge_id)
        self.edges.append(
            {
                "edge_id": edge_id,
                "kind": kind,
                "from_node": from_node,
                "to_node": to_node,
                "freshness": freshness,
                "source": source,
                "attributes": attributes,
            }
        )

    def set_claim_owner(self, cid, paper_id):
        if paper_id is None:
            return
        current = self.claim_owner.get(cid)
        if current is None:
            self.claim_owner[cid] = paper_id
            return
        if current != paper_id:
            _fail(
                "GRAPH_PROJECTION_INVALID",
                "/nodes/claim/" + cid,
                "repair_store",
                {"reason": "claim_owner_conflict", "claim_id": cid},
            )

    def note_claim(self, cid, paper_id, kind, freshness, reason, source):
        self.set_claim_owner(cid, paper_id)
        if kind is not None and cid not in self.claim_kind:
            self.claim_kind[cid] = kind
        bucket = self.claim_fresh.setdefault(cid, [])
        bucket.append((freshness, reason, source))


def _paper_node(graph, paper_id, source):
    graph.ensure(
        paper_id,
        "paper",
        paper_id,
        paper_id,
        "current",
        {
            "source_version_count": 0,
            "lineage_count": 0,
            "condition_count": 0,
            "claim_count": 0,
        },
        source,
    )


def _sv_status(association_status, source_status):
    if association_status == "bound" and source_status == "bound":
        return "bound"
    return "stale"


def _quote_status(snapshot, locator):
    path = locator.get("path")
    try:
        raw = snapshot.read_optional(path, max_bytes=MAX_BYTES)
    except OSError:
        _changed()
    if raw is None:
        return "source_missing", None
    if sha(raw) != locator.get("sha256"):
        return "source_changed", None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "source_changed", None
    span = locator.get("charspan") or [0, 0]
    start, end = span[0], span[1]
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        return "excerpt_changed", None
    excerpt = text[start:end]
    if sha(excerpt.encode("utf-8")) != locator.get("excerpt_sha256"):
        return "excerpt_changed", None
    return "bound", excerpt


def _association_node(graph, snapshot, association_id, recorded_sha, source, paper_id=None):
    path = _record_path(association_id)
    raw = _read_optional(snapshot, path)
    version = None
    source_id = None
    raw_path = None
    raw_sha = None
    if raw is None:
        association_status = "missing"
        source_status = "missing"
    else:
        if recorded_sha is not None and sha(raw) != recorded_sha:
            association_status = "changed"
        else:
            association_status = "bound"
            try:
                doc = parse_strict_json(raw, invalid_code="GRAPH_PROJECTION_INVALID")
                source_id = doc.get("source_id")
                version = doc.get("version")
                digest = doc.get("raw") or {}
                raw_path = digest.get("path")
                raw_sha = digest.get("sha256")
                if paper_id is None:
                    paper_id = doc.get("paper_id")
            except (SecureIOError, TypeError, AttributeError):
                source_id = None
                version = None
        if raw_path is None:
            source_status = "missing"
        else:
            source_status = _source_status(
                snapshot, {"path": raw_path, "sha256": raw_sha, "size_bytes": 0 if raw_sha is None else 1}
            )
            if raw_sha is not None:
                src = _read_optional(snapshot, raw_path)
                if src is None:
                    source_status = "missing"
                elif sha(src) != raw_sha:
                    source_status = "changed"
                else:
                    source_status = "bound"
                    raw_path = raw_path
    node = graph.ensure(
        association_id,
        "source_version",
        association_id,
        paper_id,
        _sv_status(association_status, source_status),
        {
            "source_id": source_id,
            "version": version,
            "association_status": association_status,
            "source_status": source_status,
            "raw_path": raw_path,
            "raw_sha256": raw_sha,
        },
        source,
    )
    attrs = node["attributes"]
    if association_status == "bound" and attrs["association_status"] != "bound":
        pass
    if node["status"] == "bound" and _sv_status(association_status, source_status) == "stale":
        node["status"] = "stale"
        node["attributes"]["association_status"] = association_status
        node["attributes"]["source_status"] = source_status
    return node


def _fill_d1(graph, snapshot, store, authority, heads):
    for index, lid in enumerate(_byte_sort(list(store.chains))):
        try:
            rel = _relation_lineage(snapshot, store, authority, heads, lid)
        except DomainRelationError as exc:
            _remap_view(exc, lid)
        try:
            ver = _version_lineage(snapshot, store, authority, heads, lid, index)
        except DomainVersionsError as exc:
            _remap_view(exc, lid)
        chain = store.chains[lid]
        head_ann = store.annotations[chain["annotation_order"][-1]]
        report = head_ann["report"]
        aid = head_ann["annotation_id"]
        paper_id = report["paper_id"]
        graph.lineage_ids.add(lid)
        _paper_node(graph, paper_id, _source("annotation", aid, "/paper_id"))
        assoc_id = report["source_association"]["association_id"]
        _association_node(
            graph,
            snapshot,
            assoc_id,
            report["source_association"].get("sha256"),
            _source("annotation", aid, "/source_association"),
            paper_id,
        )
        sv = graph.nodes[assoc_id]
        sv["attributes"]["association_status"] = ver["association_status"]
        sv["attributes"]["source_status"] = ver["source_status"]
        sv["attributes"]["source_id"] = ver["source_id"]
        sv["attributes"]["version"] = ver["version"]
        digest = ver.get("source_digest") or {}
        sv["attributes"]["raw_path"] = digest.get("path")
        sv["attributes"]["raw_sha256"] = digest.get("sha256")
        sv["status"] = _sv_status(ver["association_status"], ver["source_status"])
        sv["paper_id"] = paper_id
        graph.edge(
            "has_source_version",
            paper_id,
            assoc_id,
            "bound" if sv["status"] == "bound" else "stale",
            _source("annotation", aid, "/source_association"),
            {},
        )
        lineage_status = rel["relation_status"]
        if sv["status"] == "stale":
            lineage_status = "stale"
        lineage = graph.ensure(
            lid,
            "code_lineage",
            rel["repository"] + "@" + rel["commit"],
            paper_id,
            lineage_status,
            {
                "repository": rel["repository"],
                "commit": rel["commit"],
                "relation_kind": rel["relation_kind"],
                "officiality_candidate": rel["officiality_candidate"],
                "reviewed_officiality": rel["reviewed_officiality"],
                "review_decision": rel["review_decision"],
                "relation_status": rel["relation_status"],
                "evidence_freshness": rel["evidence_freshness"],
                "role_basis": rel["role_basis"],
                "head_annotation_id": rel["head_annotation_id"],
                "head_report_sha256": rel["head_report_sha256"],
                "gaps": list(rel["gaps"]),
                "refused_shortcuts": list(rel["refused_shortcuts"]),
            },
            _source("annotation", aid, "/relation"),
        )
        graph.edge(
            "code_relation",
            paper_id,
            lid,
            rel["evidence_freshness"] if rel["evidence_freshness"] in {"bound", "stale", "unchecked"} else "unchecked",
            _source("annotation", aid, "/relation"),
            {
                "relation_kind": rel["relation_kind"],
                "officiality_candidate": rel["officiality_candidate"],
                "reviewed_officiality": rel["reviewed_officiality"],
                "relation_status": rel["relation_status"],
            },
        )
        for index_c, item in enumerate(report.get("concepts") or []):
            status, key, tax_str = _concept_parts(item)
            cid = _id_hash("cpt-", {"concept_kind": item["concept_kind"], "key": key})
            node_status = "taxonomy_v1" if status == "taxonomy_v1" else "proposal_only"
            proposal = item.get("normalization_proposal") or {}
            slug = proposal.get("proposed_slug")
            node = graph.ensure(
                cid,
                "concept",
                item.get("surface_form") or key,
                None,
                node_status,
                {
                    "concept_kind": item["concept_kind"],
                    "taxonomy_ref": tax_str,
                    "surface_forms": [],
                    "proposed_slugs": [],
                    "term_status": status,
                    "paper_count": 1,
                },
                _source("annotation", aid, _store_pointer("concepts", index_c)),
            )
            _unique_add(node["attributes"]["surface_forms"], item.get("surface_form"))
            if slug:
                _unique_add(node["attributes"]["proposed_slugs"], slug)
            graph.concept_papers.setdefault(cid, set()).add(paper_id)
            node["attributes"]["paper_count"] = len(graph.concept_papers[cid])
            graph.edge(
                "mentions_concept",
                paper_id,
                cid,
                "bound",
                _source("annotation", aid, _store_pointer("concepts", index_c)),
                {
                    "surface_form": item.get("surface_form") or key,
                    "term_status": status,
                },
            )
        for index_cap, cap in enumerate(report.get("capabilities") or []):
            name = cap["name"]
            cap_id = _id_hash("cap-", {"lineage_id": lid, "name": name})
            locators = cap.get("locators") or []
            paths = []
            for loc in locators:
                path = loc.get("path")
                if type(path) is str:
                    paths.append(path)
                if len(paths) >= 8:
                    break
            graph.ensure(
                cap_id,
                "capability",
                name,
                paper_id,
                cap.get("status") or "unverified",
                {
                    "name": name,
                    "status": cap.get("status") or "unverified",
                    "declaration_kind": cap.get("declaration_kind"),
                    "locator_count": min(len(locators), 8),
                    "locator_paths": paths[:8],
                    "absence_scope_present": cap.get("absence_scope") is not None,
                },
                _source("annotation", aid, _store_pointer("capabilities", index_cap)),
            )
            graph.edge(
                "declares_capability",
                lid,
                cap_id,
                "bound",
                _source("annotation", aid, _store_pointer("capabilities", index_cap)),
                {
                    "status": cap.get("status") or "unverified",
                    "declaration_kind": cap.get("declaration_kind"),
                },
            )
        handoffs = ((report.get("code_refs") or {}).get("handoffs")) or []
        for index_h, row in enumerate(handoffs):
            path = row["path"]
            ref_id = row["id"]
            digest = row["sha256"]
            cref = _id_hash(
                "cref-",
                {"lineage_id": lid, "path": path, "id": ref_id, "sha256": digest},
            )
            graph.ensure(
                cref,
                "code_ref",
                path,
                paper_id,
                "recorded_only",
                {
                    "path": path,
                    "ref_id": ref_id,
                    "sha256": digest,
                    "verification": "recorded_only",
                },
                _source("annotation", aid, "/code_refs/handoffs/" + str(index_h)),
            )
            graph.edge(
                "handoff_ref",
                lid,
                cref,
                "recorded_only",
                _source("annotation", aid, "/code_refs/handoffs/" + str(index_h)),
                {"verification": "recorded_only"},
            )
        for index_cl, item in enumerate(report.get("claim_annotations") or []):
            cid = item["claim_id"]
            freshness, reason = _claim_freshness(item, authority)
            src = _source("annotation", aid, _store_pointer("claim_annotations", index_cl))
            graph.note_claim(cid, paper_id, item.get("claim_kind"), freshness, reason, src)
            graph.edge(
                "claim_about",
                cid,
                paper_id,
                "stale" if freshness == "stale" else "bound",
                src,
                {},
            )
        _ = lineage


def _fill_d2(graph, snapshot, store, authority, exp):
    by_paper = {}
    for cid in _byte_sort(list(exp.chains)):
        try:
            row = _condition_row(snapshot, store, authority, exp, cid)
        except ExperimentStoreError as exc:
            if exc.code == "EXPERIMENT_STORE_INVALID":
                details = dict(exc.details or {})
                details["prior_code"] = exc.code
                details.setdefault("reason", details.get("reason") or "store")
                details["instance_pointer"] = "/nodes/experiment_condition/" + cid
                details["next_action"] = "repair_store"
                raise GraphProjectionError(
                    "GRAPH_PROJECTION_INVALID",
                    MESSAGES["GRAPH_PROJECTION_INVALID"],
                    details,
                    exit_code=getattr(exc, "exit_code", 2),
                ) from exc
            raise
        chain = exp.chains[cid]
        head_id = chain["record_order"][-1]
        record = exp.records[head_id]
        paper_id = row["paper_id"]
        src = _source("experiment_record", head_id, "/paper_id")
        _paper_node(graph, paper_id, src)
        assoc_id = row["source_association_id"]
        lookup_doc = None
        if row["association_status"] == "bound":
            from video_paper_wiki.experiment_store import _association_lookup

            _state, _reason, lookup_doc = _association_lookup(snapshot, record)
        version = None if lookup_doc is None else lookup_doc.get("version")
        source_id = None if lookup_doc is None else lookup_doc.get("source_id")
        if assoc_id not in graph.nodes:
            graph.ensure(
                assoc_id,
                "source_version",
                assoc_id,
                paper_id,
                _sv_status(row["association_status"], row["source_status"]),
                {
                    "source_id": source_id,
                    "version": version,
                    "association_status": row["association_status"],
                    "source_status": row["source_status"],
                    "raw_path": (record.get("source_digest") or {}).get("path"),
                    "raw_sha256": (record.get("source_digest") or {}).get("sha256"),
                },
                _source("experiment_record", head_id, "/source_association"),
            )
        else:
            graph.ensure(
                assoc_id,
                "source_version",
                assoc_id,
                paper_id,
                graph.nodes[assoc_id]["status"],
                graph.nodes[assoc_id]["attributes"],
                _source("experiment_record", head_id, "/source_association"),
            )
        graph.edge(
            "has_source_version",
            paper_id,
            assoc_id,
            "bound" if graph.nodes[assoc_id]["status"] == "bound" else "stale",
            _source("experiment_record", head_id, "/source_association"),
            {},
        )
        binding = row.get("code_binding")
        binding_status = None if binding is None else binding.get("binding_status")
        cond_status = "stale" if row["record_status"] == "stale" else "current"
        graph.ensure(
            cid,
            "experiment_condition",
            row["setting_key"],
            paper_id,
            cond_status,
            {
                "setting_key": row["setting_key"],
                "head_record_id": row["head_record_id"],
                "head_record_sha256": row["head_record_sha256"],
                "record_count": row["record_count"],
                "record_status": row["record_status"],
                "association_status": row["association_status"],
                "source_status": row["source_status"],
                "binding_status": binding_status,
                "condition_status": dict(row["condition_status"]),
                "unknown_conditions": list(row["unknown_conditions"]),
                "critical_unknown": list(row["critical_unknown"]),
                "claim_freshness": dict(row["claim_freshness"]),
            },
            _source("experiment_record", head_id, ""),
        )
        graph.edge(
            "reports_condition",
            paper_id,
            cid,
            "bound" if cond_status == "current" else "stale",
            src,
            {"record_status": row["record_status"]},
        )
        if binding is not None:
            lid = binding["lineage_id"]
            if lid in graph.nodes and graph.nodes[lid]["kind"] == "code_lineage":
                graph.edge(
                    "condition_code_binding",
                    cid,
                    lid,
                    "bound" if binding_status in {"head", "superseded"} else "stale",
                    _source("experiment_record", head_id, "/code_binding"),
                    {"binding_status": binding_status},
                )
        for index, item in enumerate(record.get("claim_refs") or []):
            claim_id = item["claim_id"]
            freshness, reason = _claim_freshness(item, authority)
            src_c = _source("experiment_record", head_id, _store_pointer("claim_refs", index))
            graph.note_claim(claim_id, paper_id, item.get("claim_kind"), freshness, reason, src_c)
            graph.edge(
                "condition_claim",
                cid,
                claim_id,
                "stale" if freshness == "stale" else "bound",
                src_c,
                {"freshness": freshness, "stale_reason": reason},
            )
        by_paper.setdefault(paper_id, []).append((cid, record, head_id))
    for paper_id in _byte_sort(list(by_paper)):
        rows = sorted(by_paper[paper_id], key=lambda item: item[0].encode("utf-8"))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                left_cid, left_rec, left_head = rows[i]
                right_cid, right_rec, right_head = rows[j]
                try:
                    compared = compare_experiment_records(left_rec, right_rec)
                except ExperimentComparabilityError as exc:
                    details = dict(exc.details or {})
                    details["reason"] = "compare"
                    details["instance_pointer"] = "/nodes/experiment_condition/" + left_cid
                    details["next_action"] = "repair_store"
                    raise GraphProjectionError(
                        "GRAPH_PROJECTION_INVALID",
                        MESSAGES["GRAPH_PROJECTION_INVALID"],
                        details,
                        exit_code=getattr(exc, "exit_code", 2),
                    ) from exc
                graph.edge(
                    "comparability",
                    left_cid,
                    right_cid,
                    "derived",
                    _source("experiment_record", left_head, ""),
                    {
                        "verdict": compared["verdict"],
                        "ranking": compared["ranking"],
                        "contradiction_candidate_count": len(compared.get("contradiction_candidates") or []),
                        "same_paper": True,
                    },
                )


def _fill_claims(graph, snapshot, authority):
    ledger = authority.get("ledger") or {}
    claims = ledger.get("claims") or {}
    heads = (authority.get("heads") or {}).get("heads") or {}
    for cid in _byte_sort(list(claims)):
        row = claims[cid]
        text = row["text"]
        evidence = row.get("evidence") or []
        owner = graph.claim_owner.get(cid)
        notes = graph.claim_fresh.get(cid) or []
        freshness = "unannotated"
        stale_reason = None
        if notes:
            if any(item[0] == "stale" for item in notes):
                freshness = "stale"
                for item in notes:
                    if item[0] == "stale":
                        stale_reason = item[1]
                        break
            else:
                freshness = "head_bound"
        elif owner is None:
            freshness = "unannotated"
        supports = 0
        contradicts = 0
        uncertain = 0
        legacy = 0
        src = _source("claim_ledger", cid, "/claims/" + cid)
        for index, entry in enumerate(evidence):
            try:
                locator = decode_evidence(entry)
            except ContractError:
                legacy += 1
                continue
            kind = locator.get("kind")
            relation = locator.get("relation")
            if kind != "markdown":
                legacy += 1
                continue
            assoc = locator.get("association") or {}
            assoc_id = assoc.get("association_id")
            if type(assoc_id) is not str:
                legacy += 1
                continue
            ev_src = _source("claim_ledger", cid, "/claims/" + cid + "/evidence/" + str(index))
            if assoc_id not in graph.nodes:
                recorded = assoc.get("sha256")
                path = _record_path(assoc_id)
                raw = _read_optional(snapshot, path)
                association_status = "missing"
                version = None
                source_id = None
                raw_path = locator.get("path")
                raw_sha = locator.get("sha256")
                if raw is None:
                    association_status = "missing"
                elif recorded is not None and sha(raw) != recorded:
                    association_status = "changed"
                else:
                    association_status = "bound"
                    try:
                        doc = parse_strict_json(raw, invalid_code="GRAPH_PROJECTION_INVALID")
                        version = doc.get("version")
                        source_id = doc.get("source_id")
                    except (SecureIOError, TypeError, AttributeError):
                        version = None
                        source_id = None
                src_bytes = _read_optional(snapshot, locator.get("path"))
                if src_bytes is None:
                    source_status = "missing"
                elif sha(src_bytes) != locator.get("sha256"):
                    source_status = "changed"
                else:
                    source_status = "bound"
                graph.ensure(
                    assoc_id,
                    "source_version",
                    assoc_id,
                    owner,
                    _sv_status(association_status, source_status),
                    {
                        "source_id": source_id,
                        "version": version,
                        "association_status": association_status,
                        "source_status": source_status,
                        "raw_path": raw_path,
                        "raw_sha256": raw_sha,
                    },
                    ev_src,
                )
            quote_status, _excerpt = _quote_status(snapshot, locator)
            span = locator.get("charspan") or [0, 0]
            graph.edge(
                "claim_evidence",
                cid,
                assoc_id,
                "bound" if quote_status == "bound" else "stale",
                ev_src,
                {
                    "relation": relation,
                    "charspan": {"start": span[0], "end": span[1]},
                    "excerpt_sha256": locator.get("excerpt_sha256") or ("0" * 64),
                    "quote_status": quote_status,
                },
            )
            if relation == "supports":
                supports += 1
            elif relation == "contradicts":
                contradicts += 1
            elif relation == "uncertain":
                uncertain += 1
        head = heads.get(cid)
        graph.ensure(
            cid,
            "claim",
            text,
            owner,
            freshness,
            {
                "claim_kind": graph.claim_kind.get(cid),
                "assessment": row.get("assessment") or "provisional",
                "text_sha256": sha(text.encode("utf-8")),
                "freshness": freshness,
                "stale_reason": stale_reason,
                "head_event_id": None if head is None else head.get("event_id"),
                "evidence_count": len(evidence),
                "supports": supports,
                "contradicts": contradicts,
                "uncertain": uncertain,
                "legacy_locators": legacy,
            },
            src,
        )
        node = graph.nodes[cid]
        node["status"] = freshness
        if stale_reason:
            _unique_add(node["stale_reasons"], stale_reason)
        for _freshness, _reason, extra_src in notes:
            if extra_src not in node["sources"] and len(node["sources"]) < 64:
                node["sources"].append(extra_src)


def _fill_search_text(node):
    kind = node["kind"]
    attrs = node["attributes"]
    items = []
    if kind == "paper":
        items.append(node["node_id"])
    elif kind == "source_version":
        items.append(node["node_id"])
        if attrs.get("source_id"):
            items.append(attrs["source_id"])
        items.extend(_string_leaves(attrs.get("version")))
    elif kind == "claim":
        items.append(node["label"])
    elif kind == "concept":
        items.extend(attrs.get("surface_forms") or [])
        if attrs.get("taxonomy_ref"):
            items.append(attrs["taxonomy_ref"])
        items.extend(attrs.get("proposed_slugs") or [])
    elif kind == "code_lineage":
        items.extend([attrs.get("repository"), attrs.get("commit"), attrs.get("relation_kind")])
        if attrs.get("reviewed_officiality"):
            items.append(attrs["reviewed_officiality"])
    elif kind == "capability":
        items.append(attrs.get("name"))
        if attrs.get("declaration_kind"):
            items.append(attrs["declaration_kind"])
        items.extend(attrs.get("locator_paths") or [])
    elif kind == "code_ref":
        items.extend([attrs.get("path"), attrs.get("ref_id")])
    elif kind == "experiment_condition":
        items.append(attrs.get("setting_key"))
        # filled later with summaries by caller if record is available
    node["search_text"] = _clip_list(items)
    if not node["search_text"]:
        node["search_text"] = [_clip(node["label"]) or node["node_id"]]


def _condition_search(node, record):
    items = [node["attributes"].get("setting_key")]
    conditions = record.get("conditions") or {}
    for key in CONDITION_KEYS:
        cond = conditions.get(key) or {}
        status = cond.get("status")
        if status in KNOWN_STATUSES:
            summary = _summary(cond.get("value"))
            if summary:
                items.append(summary)
        if key == "metrics" and status in KNOWN_STATUSES:
            for metric in cond.get("value") or []:
                if metric.get("name"):
                    items.append(metric["name"])
                if metric.get("unit"):
                    items.append(metric["unit"])
    node["search_text"] = _clip_list(items)
    if not node["search_text"]:
        node["search_text"] = [_clip(node["label"]) or node["node_id"]]


def _sort_surface(node):
    if node["kind"] != "concept":
        return
    attrs = node["attributes"]
    attrs["surface_forms"] = _byte_sort(list(attrs["surface_forms"]))
    attrs["proposed_slugs"] = _byte_sort(list(attrs["proposed_slugs"]))
    if attrs["surface_forms"]:
        node["label"] = _clip(attrs["surface_forms"][0]) or node["node_id"]


def _paper_counts_and_status(graph, nodes, edges):
    by_id = {node["node_id"]: node for node in nodes}
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
                    _unique_add(stale, "source_version_stale")
            elif edge["kind"] == "code_relation" and edge["from_node"] == nid:
                lin += 1
                other = by_id.get(edge["to_node"])
                if other is not None and other["status"] == "stale":
                    _unique_add(stale, "lineage_stale")
            elif edge["kind"] == "reports_condition" and edge["from_node"] == nid:
                cond += 1
                other = by_id.get(edge["to_node"])
                if other is not None and other["status"] == "stale":
                    _unique_add(stale, "condition_stale")
            elif edge["kind"] == "claim_about" and edge["to_node"] == nid:
                claims += 1
                other = by_id.get(edge["from_node"])
                if other is not None and other.get("attributes", {}).get("freshness") == "stale":
                    _unique_add(stale, "claim_stale")
        node["attributes"]["source_version_count"] = sv
        node["attributes"]["lineage_count"] = lin
        node["attributes"]["condition_count"] = cond
        node["attributes"]["claim_count"] = claims
        node["stale_reasons"] = stale
        node["status"] = "stale" if stale else "current"


def _validate_endpoints(nodes, edges):
    kinds = {node["node_id"]: node["kind"] for node in nodes}
    for index, edge in enumerate(edges):
        expected = ENDPOINT_TYPES[edge["kind"]]
        frm = edge["from_node"]
        to = edge["to_node"]
        if frm not in kinds or to not in kinds:
            _fail(
                "GRAPH_PROJECTION_INVALID",
                "/edges/" + str(index),
                "repair_store",
                {"reason": "endpoint_missing"},
            )
        if kinds[frm] != expected[0] or kinds[to] != expected[1]:
            _fail(
                "GRAPH_PROJECTION_INVALID",
                "/edges/" + str(index),
                "repair_store",
                {"reason": "endpoint_type"},
            )


def _try_pointer(document, pointer):
    try:
        _resolve_pointer(document, pointer)
        return True
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
        return False


def _validate_sources(nodes, edges, snapshot, store, authority, exp):
    ledger = authority.get("ledger") or {}
    heads = authority.get("heads") or {}

    def exists(source):
        kind = source["record_kind"]
        rid = source["record_id"]
        pointer = source["json_pointer"]
        docs = []
        if kind == "annotation":
            rec = store.annotations.get(rid)
            if rec is None:
                return False
            docs = [rec, rec.get("report")]
        elif kind == "review":
            rec = store.reviews.get(rid)
            if rec is None:
                return False
            docs = [rec]
        elif kind == "experiment_record":
            rec = exp.records.get(rid)
            if rec is None:
                return False
            docs = [rec]
        elif kind == "claim_ledger":
            claims = ledger.get("claims") or {}
            if rid not in claims:
                return False
            docs = [ledger, claims[rid]]
        elif kind == "assessment_heads":
            if heads.get("heads", {}).get(rid) is None and rid not in (ledger.get("claims") or {}):
                return False
            docs = [heads]
        elif kind == "association_record":
            raw = _read_optional(snapshot, _record_path(rid))
            if raw is None:
                return False
            try:
                docs = [parse_strict_json(raw, invalid_code="GRAPH_PROJECTION_INVALID")]
            except SecureIOError:
                return False
        else:
            return False
        if pointer == "":
            return True
        return any(doc is not None and _try_pointer(doc, pointer) for doc in docs)

    for index, node in enumerate(nodes):
        for source in node["sources"]:
            if not exists(source):
                _fail(
                    "GRAPH_PROJECTION_INVALID",
                    "/nodes/" + str(index) + "/sources/0",
                    "repair_store",
                    {"reason": "source_unresolvable"},
                )
    for index, edge in enumerate(edges):
        if not exists(edge["source"]):
            _fail(
                "GRAPH_PROJECTION_INVALID",
                "/edges/" + str(index) + "/source",
                "repair_store",
                {"reason": "source_unresolvable"},
            )


def _sorted_graph(nodes_map, edges):
    nodes = list(nodes_map.values())
    nodes.sort(key=lambda item: (item["kind"].encode("utf-8"), item["node_id"].encode("utf-8")))
    edges = list(edges)
    edges.sort(
        key=lambda item: (
            item["kind"].encode("utf-8"),
            item["from_node"].encode("utf-8"),
            item["to_node"].encode("utf-8"),
            item["source"]["record_id"].encode("utf-8"),
            item["source"]["json_pointer"].encode("utf-8"),
        )
    )
    return nodes, edges


def _filter_graph(nodes, edges, paper_id):
    if paper_id is None:
        return nodes, edges
    kept = {node["node_id"] for node in nodes if node.get("paper_id") == paper_id}
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
    nodes = [node for node in nodes if node["node_id"] in kept]
    edges = [edge for edge in edges if edge["from_node"] in kept and edge["to_node"] in kept]
    return nodes, edges


def _check_pairwise_limit(nodes, paper_id):
    groups = {}
    for node in nodes:
        if node["kind"] != "experiment_condition":
            continue
        pid = node.get("paper_id")
        if pid is None:
            continue
        groups.setdefault(pid, 0)
        groups[pid] += 1
    papers = [paper_id] if paper_id is not None else _byte_sort(list(groups))
    for pid in papers:
        count = groups.get(pid, 0)
        if count > MAX_PAIRWISE_ROWS:
            _fail(
                "GRAPH_PROJECTION_LIMIT",
                "/nodes",
                "filter_paper_id",
                {
                    "reason": "pairwise_rows",
                    "paper_id": pid,
                    "row_count": count,
                    "limit": MAX_PAIRWISE_ROWS,
                },
            )


def _next_action(nodes):
    for node in nodes:
        if node["kind"] == "code_lineage" and (
            node["status"] == "stale" or node["attributes"].get("relation_status") == "stale"
        ):
            return "re_record_annotation"
        if node["kind"] == "claim" and node["attributes"].get("freshness") == "stale":
            return "re_record_annotation"
        if node["kind"] == "source_version" and node["status"] == "stale":
            return "re_record_annotation"
    for node in nodes:
        if node["kind"] == "experiment_condition" and node["status"] == "stale":
            return "re_record_condition"
    by_paper = {}
    for node in nodes:
        if node["kind"] != "code_lineage":
            continue
        if node["attributes"].get("reviewed_officiality") != "official":
            continue
        pid = node.get("paper_id")
        if pid is None:
            continue
        by_paper.setdefault(pid, set()).add(node["attributes"]["repository"])
    for repos in by_paper.values():
        if len(repos) >= 2:
            return "resolve_conflicts"
    return "none"


def _counts(nodes, edges):
    node_counts = {kind: 0 for kind in NODE_KINDS}
    edge_counts = {kind: 0 for kind in EDGE_KINDS}
    stale_nodes = 0
    stale_edges = 0
    for node in nodes:
        node_counts[node["kind"]] += 1
        if node["status"] == "stale" or node.get("attributes", {}).get("freshness") == "stale":
            stale_nodes += 1
        elif node["kind"] == "code_lineage" and node["status"] == "stale":
            stale_nodes += 1
    for edge in edges:
        edge_counts[edge["kind"]] += 1
        if edge["freshness"] == "stale":
            stale_edges += 1
    return node_counts, edge_counts, {"nodes": stale_nodes, "edges": stale_edges}


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("GRAPH_PROJECTION_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, PROJECTION_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise GraphProjectionError(
            "GRAPH_PROJECTION_VIEW_INVALID",
            MESSAGES["GRAPH_PROJECTION_VIEW_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_store",
                "reason": "schema",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed


def _assemble_graph(snapshot, store, authority, exp, heads):
    graph = _Graph()
    _fill_d1(graph, snapshot, store, authority, heads)
    _fill_d2(graph, snapshot, store, authority, exp)
    _fill_claims(graph, snapshot, authority)
    for node in graph.nodes.values():
        _sort_surface(node)
        if node["kind"] == "experiment_condition":
            rec = exp.records.get(node["attributes"]["head_record_id"])
            if rec is not None:
                _condition_search(node, rec)
            else:
                _fill_search_text(node)
        else:
            _fill_search_text(node)
    return graph


def _build_graph(snapshot, store, authority, exp, heads):
    graph = _assemble_graph(snapshot, store, authority, exp, heads)
    nodes, edges = _sorted_graph(graph.nodes, graph.edges)
    known = {node["node_id"] for node in nodes if node["kind"] == "paper"}
    return nodes, edges, known


def graph_sha256(nodes, edges):
    return sha(canonicalize({"nodes": nodes, "edges": edges}))


def _project(snapshot, store, authority, paper_id):
    exp = _load_experiment_store(snapshot)
    heads = derive_domain_heads(store)
    basis = _experiment_basis(snapshot, store, authority, exp)
    nodes, edges, known = _build_graph(snapshot, store, authority, exp, heads)
    if paper_id is not None and paper_id not in known:
        _fail(
            "GRAPH_PROJECTION_PAPER_UNKNOWN",
            "/paper_id",
            "check_paper_id",
            {"known_paper_count": len(known)},
        )
    _check_pairwise_limit(nodes, paper_id)
    nodes, edges = _filter_graph(nodes, edges, paper_id)
    _paper_counts_and_status(_Graph(), nodes, edges)
    if len(nodes) > MAX_NODES:
        _fail(
            "GRAPH_PROJECTION_LIMIT",
            "/nodes",
            "filter_paper_id",
            {"reason": "nodes", "count": len(nodes), "limit": MAX_NODES},
        )
    if len(edges) > MAX_EDGES:
        _fail(
            "GRAPH_PROJECTION_LIMIT",
            "/edges",
            "filter_paper_id",
            {"reason": "edges", "count": len(edges), "limit": MAX_EDGES},
        )
    _validate_endpoints(nodes, edges)
    _validate_sources(nodes, edges, snapshot, store, authority, exp)
    node_counts, edge_counts, stale_counts = _counts(nodes, edges)
    digest = graph_sha256(nodes, edges)
    known_count = len({node["node_id"] for node in nodes if node["kind"] == "paper"})
    view = {
        "schema": PROJECTION_SCHEMA,
        "basis": basis,
        "graph_sha256": digest,
        "paper_filter": paper_id,
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "stale_counts": stale_counts,
        "known_paper_count": known_count,
        "nodes": nodes,
        "edges": edges,
        "fact_source": "formal_records",
        "write_kind": "read_only",
        "publication": "unpublished",
        "audit_coverage": "not_wired",
        "code_freshness": "not_checked",
        "code_source_verification": "not_checked",
        "taxonomy_promotion": "none",
        "typed_fact_promotion": "none",
        "ranking": "not_ranked",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": _next_action(nodes),
    }
    return _seal(view)


def build_domain_graph_projection(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, store, authority):
        try:
            return _project(snapshot, store, authority, paper_id)
        except GraphProjectionError:
            raise
        except DomainStoreError:
            raise
        except ExperimentStoreError:
            raise
        except DomainProposalError:
            raise
        except DomainPublicationError:
            raise
        except ExperimentPublicationError:
            raise
        except StagingError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
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
