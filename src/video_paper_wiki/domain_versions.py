"""Read-only typed source-version view. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import MAX_BYTES, ContractError, validate_document
from video_paper_wiki.domain_proposal import _ASSOCIATION_DIR
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
from video_paper_wiki.source_semantics_contracts import sha

VIEW_SCHEMA = "video-paper-wiki.domain-source-version-view.v1"
ASSOCIATION_SCHEMA = "video-paper-wiki.source-version-association.v1"
VERSIONS_COMMAND = "domain.versions"
PAPER_ID_LIMIT = 256
MESSAGES = {
    "DOMAIN_VERSIONS_INVALID": "domain versions input is invalid",
    "DOMAIN_VERSIONS_PAPER_UNKNOWN": "domain versions paper_id is unknown",
    "DOMAIN_VERSIONS_VIEW_INVALID": "domain versions view is invalid",
}
DETAIL = {
    "association_missing": (
        "the bound source-version association record is absent from the Vault"
    ),
    "association_changed": (
        "the bound source-version association record bytes differ from the recorded digest"
    ),
    "association_identity_mismatch": (
        "the association_id field inside the record does not match the filename identity"
    ),
    "source_missing": "the captured source bytes at the recorded path are absent",
    "source_changed": "the captured source bytes differ from the recorded digest",
    "association_binding_divergence": (
        "the same source-version association is bound to more than one recorded digest"
    ),
    "association_paper_divergence": (
        "the same source-version association is bound to more than one paper_id"
    ),
    "version_label_collision": (
        "two source versions of this paper declare the same version label"
    ),
}
ASSOCIATION_FINDING = {
    "missing": "association_missing",
    "changed": "association_changed",
    "identity_mismatch": "association_identity_mismatch",
}
SOURCE_FINDING = {
    "missing": "source_missing",
    "changed": "source_changed",
}


class DomainVersionsError(Exception):
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
    raise DomainVersionsError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


def _unique_sorted(values):
    seen = set()
    out = []
    for item in _byte_sort(values):
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


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
        _fail("DOMAIN_VERSIONS_INVALID", "/paper_id", "repair_input")


def _record_path(association_id):
    return _ASSOCIATION_DIR + association_id + ".json"


def _association_state(raw, report, association_id):
    if raw is None:
        return ("missing", None, None)
    record_sha = sha(raw)
    recorded_sha = report["source_association"]["sha256"]
    if record_sha != recorded_sha:
        return ("changed", None, record_sha)
    try:
        doc = parse_strict_json(raw, invalid_code="DOMAIN_VERSIONS_VIEW_INVALID")
        validate_document(doc, ASSOCIATION_SCHEMA)
    except (SecureIOError, ContractError):
        _fail(
            "DOMAIN_VERSIONS_VIEW_INVALID",
            "/association",
            "repair_store",
            {"reason": "association_shape"},
        )
    digest = report["source_digest"]
    if (
        doc["paper_id"] != report["paper_id"]
        or doc["raw"]["path"] != digest["path"]
        or doc["raw"]["sha256"] != digest["sha256"]
        or doc["raw"]["size_bytes"] != digest["size_bytes"]
    ):
        _fail(
            "DOMAIN_VERSIONS_VIEW_INVALID",
            "/association",
            "repair_store",
            {"reason": "association_binding"},
        )
    if doc["association_id"] != association_id:
        return ("identity_mismatch", None, record_sha)
    return ("bound", doc, record_sha)


def _source_status(snapshot, digest):
    try:
        src = snapshot.read_optional(digest["path"], max_bytes=MAX_BYTES)
    except OSError:
        _changed()
    if src is None:
        return "missing"
    if sha(src) != digest["sha256"] or len(src) != digest["size_bytes"]:
        return "changed"
    return "bound"


def _version_status(stale_count, association_status, source_status, head):
    if stale_count > 0 or association_status != "bound" or source_status != "bound":
        return "stale"
    if head["review_id"] is None:
        return "proposal_only"
    return "reviewed_" + head["review_decision"]


def _history(store, lid):
    order = store.chains[lid]["annotation_order"]
    history = []
    previous_sha = None
    seen = set()
    for aid in order:
        annotation = store.annotations[aid]
        report = annotation["report"]
        recorded = report["source_association"]["sha256"]
        seen.add(recorded)
        history.append(
            {
                "annotation_id": annotation["annotation_id"],
                "previous_annotation_id": annotation["previous_annotation_id"],
                "recorded_at": annotation["recorded_at"],
                "commit": report["commit"],
                "report_sha256": annotation["report_sha256"],
                "recorded_association_sha256": recorded,
                "source_digest_sha256": report["source_digest"]["sha256"],
                "changes_from_previous": {
                    "association_rebound": False if previous_sha is None else recorded != previous_sha
                },
            }
        )
        previous_sha = recorded
    return history, len(seen)


def _lineage_view(snapshot, store, authority, heads, lid, index):
    chain = store.chains[lid]
    order = chain["annotation_order"]
    head_ann = store.annotations[order[-1]]
    report = head_ann["report"]
    head = heads["heads"][lid]
    association_id = report["source_association"]["association_id"]
    recorded_sha = report["source_association"]["sha256"]
    digest = report["source_digest"]
    record_path = _record_path(association_id)
    try:
        raw = snapshot.read_optional(record_path, max_bytes=MAX_BYTES)
    except OSError:
        _changed()
    try:
        association_status, doc, record_sha = _association_state(raw, report, association_id)
    except DomainVersionsError as exc:
        if exc.code == "DOMAIN_VERSIONS_VIEW_INVALID":
            details = dict(exc.details)
            details["instance_pointer"] = "/lineages/" + str(index) + "/association"
            raise DomainVersionsError(
                exc.code, exc.message, details, exit_code=exc.exit_code
            ) from exc
        raise
    if association_status == "bound":
        source_id = doc["source_id"]
        version = doc["version"]
    else:
        source_id = None
        version = None
    source_status = _source_status(snapshot, digest)
    bound = 0
    stale = 0
    for item in report["claim_annotations"]:
        freshness, _reason = _claim_freshness(item, authority)
        if freshness == "stale":
            stale += 1
        else:
            bound += 1
    history, revisions = _history(store, lid)
    return {
        "lineage_id": lid,
        "paper_id": report["paper_id"],
        "repository": report["repository"],
        "commit": report["commit"],
        "head_annotation_id": head_ann["annotation_id"],
        "head_report_sha256": head_ann["report_sha256"],
        "current_review_id": head["review_id"],
        "review_decision": head["review_decision"],
        "reviewed_officiality": head["reviewed_officiality"],
        "relation_kind": report["relation"]["kind"],
        "source_association_id": association_id,
        "recorded_association_sha256": recorded_sha,
        "association_status": association_status,
        "association_record_sha256": record_sha,
        "source_id": source_id,
        "version": version,
        "source_digest": {
            "path": digest["path"],
            "sha256": digest["sha256"],
            "size_bytes": digest["size_bytes"],
        },
        "source_status": source_status,
        "claim_freshness": {"head_bound": bound, "stale": stale},
        "version_status": _version_status(stale, association_status, source_status, head),
        "binding_revisions": revisions,
        "history": history,
    }


def _empty_assoc_counts():
    return {"bound": 0, "changed": 0, "missing": 0, "identity_mismatch": 0}


def _empty_source_counts():
    return {"bound": 0, "changed": 0, "missing": 0}


def _labels_when_all_bound(counts, n, source_id, version):
    if counts["bound"] == n:
        return source_id, version
    return None, None


def _registry(lineages):
    buckets = {}
    for row in lineages:
        assoc = row["source_association_id"]
        bucket = buckets.setdefault(
            assoc,
            {
                "papers": set(),
                "recorded": set(),
                "status": _empty_assoc_counts(),
                "digests": set(),
                "repos": set(),
                "lids": [],
                "record_status": "missing",
                "association_record_sha256": None,
                "source_id": None,
                "version": None,
            },
        )
        bucket["papers"].add(row["paper_id"])
        bucket["recorded"].add(row["recorded_association_sha256"])
        bucket["status"][row["association_status"]] += 1
        bucket["digests"].add(row["source_digest"]["sha256"])
        bucket["repos"].add(row["repository"])
        bucket["lids"].append(row["lineage_id"])
        if row["association_record_sha256"] is not None:
            bucket["record_status"] = "present"
            bucket["association_record_sha256"] = row["association_record_sha256"]
        if row["association_status"] == "bound":
            bucket["source_id"] = row["source_id"]
            bucket["version"] = row["version"]
    versions = []
    for assoc in _byte_sort(buckets):
        bucket = buckets[assoc]
        lids = _unique_sorted(bucket["lids"])
        source_id, version = _labels_when_all_bound(
            bucket["status"], len(lids), bucket["source_id"], bucket["version"]
        )
        versions.append(
            {
                "source_association_id": assoc,
                "paper_ids": _unique_sorted(bucket["papers"]),
                "record_status": bucket["record_status"],
                "association_record_sha256": bucket["association_record_sha256"],
                "recorded_association_sha256s": _unique_sorted(bucket["recorded"]),
                "status_counts": bucket["status"],
                "source_id": source_id,
                "version": version,
                "source_digest_sha256s": _unique_sorted(bucket["digests"]),
                "repositories": _unique_sorted(bucket["repos"]),
                "lineage_ids": lids,
            }
        )
    return versions


def _finding(kind, subject, paper_ids, lineage_ids):
    return {
        "kind": kind,
        "subject": subject,
        "paper_ids": _unique_sorted(paper_ids),
        "lineage_ids": _unique_sorted(lineage_ids),
        "detail": DETAIL[kind],
    }


def _papers_and_findings(lineages, versions, basis):
    by_paper = {}
    assoc_status = {}
    source_status = {}
    for row in lineages:
        paper = by_paper.setdefault(
            row["paper_id"],
            {
                "versions": {},
                "repos": {},
                "lids": [],
                "head_aids": [],
                "paths": set(),
            },
        )
        paper["lids"].append(row["lineage_id"])
        paper["head_aids"].append(row["head_annotation_id"])
        paper["paths"].add(_record_path(row["source_association_id"]))
        assoc = row["source_association_id"]
        version = paper["versions"].setdefault(
            assoc,
            {
                "assoc": _empty_assoc_counts(),
                "source": _empty_source_counts(),
                "repos": set(),
                "lids": [],
                "source_id": None,
                "version": None,
            },
        )
        version["assoc"][row["association_status"]] += 1
        version["source"][row["source_status"]] += 1
        version["repos"].add(row["repository"])
        version["lids"].append(row["lineage_id"])
        if row["association_status"] == "bound":
            version["source_id"] = row["source_id"]
            version["version"] = row["version"]
        paper["repos"].setdefault(row["repository"], []).append(row)
        key = (assoc, row["association_status"])
        group = assoc_status.setdefault(key, {"papers": set(), "lids": set()})
        group["papers"].add(row["paper_id"])
        group["lids"].add(row["lineage_id"])
        skey = (assoc, row["source_status"])
        sgroup = source_status.setdefault(skey, {"papers": set(), "lids": set()})
        sgroup["papers"].add(row["paper_id"])
        sgroup["lids"].add(row["lineage_id"])
    papers = []
    for paper_id in _byte_sort(by_paper):
        group = by_paper[paper_id]
        paper_versions = []
        unlabeled = []
        declared = 0
        for assoc in _byte_sort(group["versions"]):
            item = group["versions"][assoc]
            lids = _unique_sorted(item["lids"])
            source_id, version = _labels_when_all_bound(
                item["assoc"], len(lids), item["source_id"], item["version"]
            )
            if version is not None and version.get("kind") == "declared":
                declared += 1
            if version is None or version.get("kind") == "unknown":
                unlabeled.append(assoc)
            paper_versions.append(
                {
                    "source_association_id": assoc,
                    "source_id": source_id,
                    "version": version,
                    "association_counts": item["assoc"],
                    "source_counts": item["source"],
                    "repositories": _unique_sorted(item["repos"]),
                    "lineage_ids": lids,
                }
            )
        repositories = []
        for repo in _byte_sort(group["repos"]):
            items = sorted(
                group["repos"][repo], key=lambda item: item["lineage_id"].encode("utf-8")
            )
            repositories.append(
                {
                    "repository": repo,
                    "lineages": [
                        {
                            "lineage_id": item["lineage_id"],
                            "source_association_id": item["source_association_id"],
                            "commit": item["commit"],
                            "relation_kind": item["relation_kind"],
                            "reviewed_officiality": item["reviewed_officiality"],
                            "version_status": item["version_status"],
                            "association_status": item["association_status"],
                            "source_status": item["source_status"],
                        }
                        for item in items
                    ],
                }
            )
        papers.append(
            {
                "paper_id": paper_id,
                "versions": paper_versions,
                "repositories": repositories,
                "declared_version_count": declared,
                "unlabeled_versions": _unique_sorted(unlabeled),
                "search_scope": {
                    "lineage_ids": _unique_sorted(group["lids"]),
                    "head_annotation_ids": _unique_sorted(group["head_aids"]),
                    "association_record_paths": _unique_sorted(group["paths"]),
                    "claim_ledger_sha256": basis["claim_ledger_sha256"],
                    "assessment_heads_sha256": basis["assessment_heads_sha256"],
                },
                "finding_count": 0,
            }
        )
    findings = []
    for assoc, status in assoc_status:
        if status == "bound":
            continue
        group = assoc_status[(assoc, status)]
        findings.append(
            _finding(ASSOCIATION_FINDING[status], assoc, group["papers"], group["lids"])
        )
    for assoc, status in source_status:
        if status == "bound":
            continue
        group = source_status[(assoc, status)]
        findings.append(
            _finding(SOURCE_FINDING[status], assoc, group["papers"], group["lids"])
        )
    for item in versions:
        if len(item["recorded_association_sha256s"]) >= 2:
            findings.append(
                _finding(
                    "association_binding_divergence",
                    item["source_association_id"],
                    item["paper_ids"],
                    item["lineage_ids"],
                )
            )
        if len(item["paper_ids"]) >= 2:
            findings.append(
                _finding(
                    "association_paper_divergence",
                    item["source_association_id"],
                    item["paper_ids"],
                    item["lineage_ids"],
                )
            )
    for paper in papers:
        labels = {}
        for item in paper["versions"]:
            version = item["version"]
            if version is None or version.get("kind") != "declared":
                continue
            label = version["label"]
            entry = labels.setdefault(label, {"assocs": set(), "lids": set()})
            entry["assocs"].add(item["source_association_id"])
            for lid in item["lineage_ids"]:
                entry["lids"].add(lid)
        for label in _byte_sort(labels):
            entry = labels[label]
            if len(entry["assocs"]) < 2:
                continue
            findings.append(
                _finding(
                    "version_label_collision",
                    paper["paper_id"] + "|" + label,
                    [paper["paper_id"]],
                    entry["lids"],
                )
            )
    findings.sort(
        key=lambda row: (
            row["kind"].encode("utf-8"),
            row["subject"].encode("utf-8"),
            [lid.encode("utf-8") for lid in row["lineage_ids"]],
        )
    )
    counts = {}
    for row in findings:
        for paper_id in row["paper_ids"]:
            counts[paper_id] = counts.get(paper_id, 0) + 1
    for paper in papers:
        paper["finding_count"] = counts.get(paper["paper_id"], 0)
    return papers, findings


def _next_action(lineages, findings):
    if findings:
        return "review_findings"
    if any(row["version_status"] == "stale" for row in lineages):
        return "re_record_annotation"
    return "none"


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_VERSIONS_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, VIEW_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise DomainVersionsError(
            "DOMAIN_VERSIONS_VIEW_INVALID",
            MESSAGES["DOMAIN_VERSIONS_VIEW_INVALID"],
            {
                "instance_pointer": details.get("instance_pointer", ""),
                "next_action": "repair_store",
                **details,
            },
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed


def _paper_of(store, lid):
    chain = store.chains[lid]
    head = store.annotations[chain["annotation_order"][-1]]
    return head["report"]["paper_id"]


def _build(snapshot, store, authority, paper_id):
    basis = _basis(snapshot, store, authority)
    heads = derive_domain_heads(store)
    all_lids = sorted(store.chains, key=lambda item: item.encode("utf-8"))
    known = {_paper_of(store, lid) for lid in all_lids}
    if paper_id is not None:
        if paper_id not in known:
            _fail(
                "DOMAIN_VERSIONS_PAPER_UNKNOWN",
                "/paper_id",
                "check_paper_id",
                {"known_paper_count": len(known)},
            )
        lids = [lid for lid in all_lids if _paper_of(store, lid) == paper_id]
    else:
        lids = all_lids
    lineages = []
    for index, lid in enumerate(lids):
        lineages.append(_lineage_view(snapshot, store, authority, heads, lid, index))
    versions = _registry(lineages)
    papers, findings = _papers_and_findings(lineages, versions, basis)
    view = {
        "schema": VIEW_SCHEMA,
        "basis": basis,
        "paper_filter": paper_id,
        "lineage_count": len(lineages),
        "lineages": lineages,
        "versions": versions,
        "papers": papers,
        "findings": findings,
        "publication": "unpublished",
        "write_kind": "read_only",
        "audit_coverage": "not_wired",
        "code_freshness": "not_checked",
        "evidence_recheck": "not_performed",
        "source_recheck": "captured_markdown_digest",
        "source_association_verified": False,
        "typed_fact_promotion": "none",
        "experiment_conditions": "not_modeled",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": _next_action(lineages, findings),
    }
    return _seal(view)


def build_domain_source_version_view(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, store, authority):
        try:
            return _build(snapshot, store, authority, paper_id)
        except DomainVersionsError:
            raise
        except DomainStoreError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
    except DomainVersionsError:
        raise
    except DomainStoreError:
        raise
    except OSError:
        _changed()
