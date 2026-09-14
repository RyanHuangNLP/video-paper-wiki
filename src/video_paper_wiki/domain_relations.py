"""Read-only typed paper-repository relation view. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import MAX_BYTES, ContractError, validate_document
from video_paper_wiki.domain_publication import _basis
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MESSAGES as STORE_MESSAGES,
    _claim_freshness,
    _with_store,
    derive_domain_heads,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki.source_catalog_projection import _pointer
from video_paper_wiki.source_semantics_contracts import sha

VIEW_SCHEMA = "video-paper-wiki.domain-relation-view.v1"
RELATIONS_COMMAND = "domain.relations"
PAPER_ID_LIMIT = 256
B_STALE = frozenset({"artifact_missing", "artifact_changed", "fragment_changed"})
MESSAGES = {
    "DOMAIN_RELATION_INVALID": "domain relation input is invalid",
    "DOMAIN_RELATION_PAPER_UNKNOWN": "domain relation paper_id is unknown",
    "DOMAIN_RELATION_VIEW_INVALID": "domain relation view is invalid",
}
DETAIL_MULTI = "multiple repositories carry reviewed official implementations of this paper"
DETAIL_DIVERGENCE = "one repository has diverging relation kinds across lineages of this paper"
DETAIL_STALE_OFFICIAL = "reviewed official lineage is stale against current Vault bytes or claims"


class DomainRelationError(Exception):
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
    raise DomainRelationError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


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
        _fail("DOMAIN_RELATION_INVALID", "/paper_id", "repair_input")


def _present(classes, key):
    return bool(classes.get(key))


def _recheck_a_locator(snapshot, locator):
    path = locator["artifact_path"]
    try:
        raw = snapshot.read_optional(path, max_bytes=MAX_BYTES)
    except OSError:
        _changed()
    if raw is None:
        return "artifact_missing"
    if sha(raw) != locator["artifact_sha256"]:
        return "artifact_changed"
    try:
        document = parse_strict_json(raw, invalid_code="DOMAIN_RELATION_VIEW_INVALID")
        node = _pointer(document, locator["ref"])
    except (SecureIOError, ValueError, KeyError, IndexError, TypeError, UnicodeError):
        return "ref_unresolvable"
    if type(node) is not dict or type(node.get("text")) is not str:
        return "ref_unresolvable"
    if sha(node["text"].encode("utf-8")) != locator["text_sha256"]:
        return "text_mismatch"
    prov = node.get("prov")
    page = locator["page"]
    if type(prov) is not list or not any(
        type(item) is dict and item.get("page_no") == page for item in prov
    ):
        return "page_mismatch"
    return "bound"


def _evidence_a(snapshot, present, locators):
    if not present:
        return {"present": False, "status": "absent", "locators": []}
    rows = []
    for locator in locators:
        rows.append({"artifact_path": locator["artifact_path"], "status": _recheck_a_locator(snapshot, locator)})
    status = "bound" if rows and all(row["status"] == "bound" for row in rows) else "stale"
    if not rows:
        status = "stale"
    return {"present": True, "status": status, "locators": rows}


def _evidence_b(snapshot, present, page):
    if not present:
        return {"present": False, "status": "absent"}
    if type(page) is not dict:
        return {"present": True, "status": "artifact_missing"}
    digest = page["local_digest"]
    try:
        raw = snapshot.read_optional(digest["path"], max_bytes=MAX_BYTES)
    except OSError:
        _changed()
    if raw is None:
        return {"present": True, "status": "artifact_missing"}
    if sha(raw) != digest["sha256"] or len(raw) != digest["size_bytes"]:
        return {"present": True, "status": "artifact_changed"}
    fragment = page["fragment"]
    start = fragment["start"]
    end = fragment["end"]
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
        return {"present": True, "status": "fragment_changed"}
    if sha(raw[start:end]) != fragment["text_sha256"]:
        return {"present": True, "status": "fragment_changed"}
    return {"present": True, "status": "bound"}


def _evidence_c(present):
    return {"present": bool(present), "status": "not_checked" if present else "absent"}


def _evidence_d(present):
    return {"present": bool(present), "status": "declared_only" if present else "absent"}


def _evidence_freshness(a_status, b_status):
    if a_status == "absent" and b_status == "absent":
        return "unchecked"
    if a_status == "stale" or b_status in B_STALE:
        return "stale"
    return "bound"


def _relation_status(claim_stale, evidence_freshness, head):
    if claim_stale or evidence_freshness == "stale":
        return "stale"
    if head["review_id"] is None:
        return "proposal_only"
    return "reviewed_" + head["review_decision"]


def _history_row(annotation):
    report = annotation["report"]
    relation = report["relation"]
    classes = relation["evidence_classes"]
    return {
        "annotation_id": annotation["annotation_id"],
        "previous_annotation_id": annotation["previous_annotation_id"],
        "recorded_at": annotation["recorded_at"],
        "commit": report["commit"],
        "relation_kind": relation["kind"],
        "officiality_candidate": relation["officiality_candidate"],
        "evidence_classes": {
            "A": bool(classes["A"]),
            "B": bool(classes["B"]),
            "C": bool(classes["C"]),
            "D": bool(classes["D"]),
        },
        "gaps": list(relation["gaps"]),
        "refused_shortcuts": list(relation["refused_shortcuts"]),
        "report_sha256": annotation["report_sha256"],
    }


def _review_row(review, current_id):
    relation_review = review.get("relation_review")
    officiality = None if relation_review is None else relation_review["reviewed_officiality"]
    return {
        "review_id": review["review_id"],
        "annotation_id": review["annotation_id"],
        "decided_at": review["decided_at"],
        "decision": review["decision"],
        "reviewed_officiality": officiality,
        "current": review["review_id"] == current_id,
    }


def _lineage_view(snapshot, store, authority, heads, lid):
    chain = store.chains[lid]
    head_ann = store.annotations[chain["annotation_order"][-1]]
    report = head_ann["report"]
    relation = report["relation"]
    classes = relation["evidence_classes"]
    locators = relation["locators"]
    head = heads["heads"][lid]
    bound = 0
    stale = 0
    for item in report["claim_annotations"]:
        freshness, _reason = _claim_freshness(item, authority)
        if freshness == "stale":
            stale += 1
        else:
            bound += 1
    evidence_a = _evidence_a(snapshot, _present(classes, "A"), locators["A"])
    evidence_b = _evidence_b(snapshot, _present(classes, "B"), locators["B"])
    evidence_c = _evidence_c(_present(classes, "C"))
    evidence_d = _evidence_d(_present(classes, "D"))
    freshness = _evidence_freshness(evidence_a["status"], evidence_b["status"])
    status = _relation_status(stale > 0, freshness, head)
    return {
        "lineage_id": lid,
        "paper_id": report["paper_id"],
        "source_association_id": report["source_association"]["association_id"],
        "repository": report["repository"],
        "commit": report["commit"],
        "head_annotation_id": head_ann["annotation_id"],
        "head_report_sha256": head_ann["report_sha256"],
        "current_review_id": head["review_id"],
        "review_decision": head["review_decision"],
        "reviewed_officiality": head["reviewed_officiality"],
        "relation_kind": relation["kind"],
        "officiality_candidate": relation["officiality_candidate"],
        "role_basis": "reviewed" if status == "reviewed_accepted" else "proposal",
        "relation_status": status,
        "claim_freshness": {"head_bound": bound, "stale": stale},
        "evidence": {"A": evidence_a, "B": evidence_b, "C": evidence_c, "D": evidence_d},
        "evidence_freshness": freshness,
        "gaps": list(relation["gaps"]),
        "refused_shortcuts": list(relation["refused_shortcuts"]),
        "history": [_history_row(store.annotations[aid]) for aid in chain["annotation_order"]],
        "reviews": [_review_row(store.reviews[rid], head["review_id"]) for rid in chain["review_order"]],
    }


def _paper_ref(row):
    return {
        "lineage_id": row["lineage_id"],
        "source_association_id": row["source_association_id"],
        "commit": row["commit"],
        "relation_kind": row["relation_kind"],
        "officiality_candidate": row["officiality_candidate"],
        "relation_status": row["relation_status"],
        "reviewed_officiality": row["reviewed_officiality"],
    }


def _papers_and_conflicts(lineages):
    by_paper = {}
    for row in lineages:
        paper = by_paper.setdefault(row["paper_id"], {"ids": set(), "repos": {}, "rows": []})
        paper["ids"].add(row["source_association_id"])
        paper["repos"].setdefault(row["repository"], []).append(row)
        paper["rows"].append(row)
    papers = []
    conflicts = []
    for paper_id in _byte_sort(by_paper):
        group = by_paper[paper_id]
        repositories = []
        for repo in _byte_sort(group["repos"]):
            items = sorted(group["repos"][repo], key=lambda row: row["lineage_id"].encode("utf-8"))
            repositories.append({"repository": repo, "lineages": [_paper_ref(item) for item in items]})
            if len(items) >= 2 and len({item["relation_kind"] for item in items}) >= 2:
                conflicts.append(
                    {
                        "kind": "repository_role_divergence",
                        "paper_id": paper_id,
                        "repositories": [repo],
                        "lineage_ids": _byte_sort(item["lineage_id"] for item in items),
                        "detail": DETAIL_DIVERGENCE,
                    }
                )
        official = [item for item in group["rows"] if item["reviewed_officiality"] == "official"]
        official_repos = _byte_sort({item["repository"] for item in official})
        if len(official_repos) >= 2:
            conflicts.append(
                {
                    "kind": "multiple_official_implementations",
                    "paper_id": paper_id,
                    "repositories": official_repos,
                    "lineage_ids": _byte_sort(item["lineage_id"] for item in official),
                    "detail": DETAIL_MULTI,
                }
            )
        for item in sorted(group["rows"], key=lambda row: row["lineage_id"].encode("utf-8")):
            if item["reviewed_officiality"] == "official" and item["relation_status"] == "stale":
                conflicts.append(
                    {
                        "kind": "official_with_stale_evidence",
                        "paper_id": paper_id,
                        "repositories": [item["repository"]],
                        "lineage_ids": [item["lineage_id"]],
                        "detail": DETAIL_STALE_OFFICIAL,
                    }
                )
        papers.append(
            {
                "paper_id": paper_id,
                "source_association_ids": _byte_sort(group["ids"]),
                "repositories": repositories,
                "conflict_count": 0,
            }
        )
    conflicts.sort(
        key=lambda row: (
            row["kind"].encode("utf-8"),
            row["paper_id"].encode("utf-8"),
            [lid.encode("utf-8") for lid in row["lineage_ids"]],
        )
    )
    counts = {}
    for row in conflicts:
        counts[row["paper_id"]] = counts.get(row["paper_id"], 0) + 1
    for paper in papers:
        paper["conflict_count"] = counts.get(paper["paper_id"], 0)
    return papers, conflicts


def _next_action(lineages, conflicts):
    if conflicts:
        return "resolve_conflicts"
    if any(row["relation_status"] == "stale" for row in lineages):
        return "re_record_annotation"
    return "none"


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_RELATION_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, VIEW_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise DomainRelationError(
            "DOMAIN_RELATION_VIEW_INVALID",
            MESSAGES["DOMAIN_RELATION_VIEW_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_store",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed


def _build(snapshot, store, authority, paper_id):
    basis = _basis(snapshot, store, authority)
    heads = derive_domain_heads(store)
    lineages = []
    for lid in sorted(store.chains, key=lambda item: item.encode("utf-8")):
        lineages.append(_lineage_view(snapshot, store, authority, heads, lid))
    if paper_id is not None:
        known = {row["paper_id"] for row in lineages}
        if paper_id not in known:
            _fail(
                "DOMAIN_RELATION_PAPER_UNKNOWN",
                "/paper_id",
                "check_paper_id",
                {"known_paper_count": len(known)},
            )
        lineages = [row for row in lineages if row["paper_id"] == paper_id]
    papers, conflicts = _papers_and_conflicts(lineages)
    view = {
        "schema": VIEW_SCHEMA,
        "basis": basis,
        "paper_filter": paper_id,
        "lineage_count": len(lineages),
        "lineages": lineages,
        "papers": papers,
        "conflicts": conflicts,
        "publication": "unpublished",
        "write_kind": "read_only",
        "audit_coverage": "not_wired",
        "code_freshness": "not_checked",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": _next_action(lineages, conflicts),
    }
    return _seal(view)


def build_domain_relation_view(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, store, authority):
        try:
            return _build(snapshot, store, authority, paper_id)
        except DomainRelationError:
            raise
        except DomainStoreError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
    except DomainRelationError:
        raise
    except DomainStoreError:
        raise
    except OSError:
        _changed()
