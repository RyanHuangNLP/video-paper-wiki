"""Read-only typed claim-kind coverage view. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_proposal import CLAIM_KINDS
from video_paper_wiki.domain_publication import _basis
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MESSAGES as STORE_MESSAGES,
    _claim_freshness,
    _with_store,
    derive_domain_heads,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.source_semantics_contracts import sha

VIEW_SCHEMA = "video-paper-wiki.domain-claim-coverage-view.v1"
CLAIMS_COMMAND = "domain.claims"
PAPER_ID_LIMIT = 256
ASSESSMENTS = frozenset(
    {"accepted", "provisional", "contested", "unsupported", "deprecated"}
)
PROFILES = frozenset({"legacy-v1", "mixed-v2"})
MESSAGES = {
    "DOMAIN_CLAIMS_INVALID": "domain claims input is invalid",
    "DOMAIN_CLAIMS_PAPER_UNKNOWN": "domain claims paper_id is unknown",
    "DOMAIN_CLAIMS_VIEW_INVALID": "domain claims view is invalid",
}
DETAIL = {
    "claim_kind_divergence": "the same claim_id is used with more than one claim_kind",
    "claim_binding_divergence": (
        "the same claim_id is bound to more than one evidence fingerprint or assessment event"
    ),
    "claim_assessment_drift": (
        "recorded assessment differs from the current claim ledger assessment"
    ),
    "untyped_claim_missing": "an untyped claim is absent from the claim ledger",
}


class DomainClaimsError(Exception):
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
    raise DomainClaimsError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _view_invalid(pointer, reason):
    _fail("DOMAIN_CLAIMS_VIEW_INVALID", pointer, "repair_store", {"reason": reason})


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
        _fail("DOMAIN_CLAIMS_INVALID", "/paper_id", "repair_input")


def _empty_kinds():
    return {kind: {"claim_ids": [], "head_bound": 0, "stale": 0} for kind in CLAIM_KINDS}


def _empty_kind_counts():
    return {kind: 0 for kind in CLAIM_KINDS}


def _empty_changes():
    return {
        "claims_added": [],
        "claims_removed": [],
        "claims_retyped": [],
        "claims_rebound": [],
        "untyped_changed": False,
    }


def _ledger_map(authority):
    if type(authority) is not dict:
        return {}
    document = authority.get("ledger")
    if type(document) is not dict:
        return {}
    claims = document.get("claims")
    if type(claims) is not dict:
        return {}
    return claims


def _claim_binding(item, pointer, *, seen=None):
    try:
        if type(item) is not dict:
            _view_invalid(pointer, "claim_shape")
        cid = item.get("claim_id")
        kind = item.get("claim_kind")
        fingerprint = item.get("evidence_fingerprint")
        head = item.get("assessment_head")
        if type(cid) is not str or not cid:
            _view_invalid(pointer, "claim_shape")
        if kind not in CLAIM_KINDS:
            _view_invalid(pointer, "claim_shape")
        if type(fingerprint) is not str:
            _view_invalid(pointer, "claim_shape")
        if type(head) is not dict:
            _view_invalid(pointer, "claim_shape")
        event_sha = head.get("event_sha256")
        if type(event_sha) is not str:
            _view_invalid(pointer, "claim_shape")
        if seen is not None:
            if cid in seen:
                _view_invalid(pointer, "claim_shape")
            seen.add(cid)
        return cid, kind, fingerprint, event_sha
    except DomainClaimsError:
        raise
    except DomainStoreError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        _view_invalid(pointer, "claim_shape")


def _typed_row(item, authority, pointer, *, seen=None):
    try:
        cid, kind, fingerprint, event_sha = _claim_binding(item, pointer, seen=seen)
        assessment = item.get("assessment")
        text = item.get("claim_text")
        head = item.get("assessment_head")
        if assessment not in ASSESSMENTS:
            _view_invalid(pointer, "claim_shape")
        if type(text) is not str:
            _view_invalid(pointer, "claim_shape")
        event_id = head.get("event_id")
        profile = head.get("evidence_profile")
        if type(event_id) is not str or type(event_sha) is not str:
            _view_invalid(pointer, "claim_shape")
        if profile not in PROFILES:
            _view_invalid(pointer, "claim_shape")
        freshness, stale_reason = _claim_freshness(item, authority)
        ledger = _ledger_map(authority)
        row = ledger.get(cid)
        current = None if row is None else row["assessment"]
        return {
            "claim_id": cid,
            "claim_kind": kind,
            "recorded_assessment": assessment,
            "current_assessment": current,
            "assessment_drift": row is not None and row["assessment"] != assessment,
            "ledger_status": "present" if row is not None else "missing",
            "claim_text_sha256": sha(text.encode("utf-8")),
            "evidence_fingerprint": fingerprint,
            "assessment_head": {
                "event_id": event_id,
                "event_sha256": event_sha,
                "evidence_profile": profile,
            },
            "freshness": freshness,
            "stale_reason": stale_reason,
        }
    except DomainClaimsError:
        raise
    except DomainStoreError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        _view_invalid(pointer, "claim_shape")


def _typed_rows(items, authority, pointer):
    if type(items) is not list:
        _view_invalid(pointer, "claim_shape")
    seen = set()
    rows = []
    for index, item in enumerate(items):
        rows.append(_typed_row(item, authority, pointer + "/" + str(index), seen=seen))
    rows.sort(key=lambda row: row["claim_id"].encode("utf-8"))
    return rows


def _untyped_row(item, authority, pointer, *, typed_ids=None, seen=None):
    try:
        if type(item) is not dict:
            _view_invalid(pointer, "untyped_shape")
        cid = item.get("claim_id")
        text = item.get("claim_text")
        assessment = item.get("assessment")
        if type(cid) is not str or not cid:
            _view_invalid(pointer, "untyped_shape")
        if type(text) is not str:
            _view_invalid(pointer, "untyped_shape")
        if assessment not in ASSESSMENTS:
            _view_invalid(pointer, "untyped_shape")
        if typed_ids is not None and cid in typed_ids:
            _view_invalid(pointer, "untyped_shape")
        if seen is not None:
            if cid in seen:
                _view_invalid(pointer, "untyped_shape")
            seen.add(cid)
        ledger = _ledger_map(authority)
        row = ledger.get(cid)
        return {
            "claim_id": cid,
            "claim_text_sha256": sha(text.encode("utf-8")),
            "recorded_assessment": assessment,
            "ledger_status": "present" if row is not None else "missing",
            "current_assessment": None if row is None else row["assessment"],
        }
    except DomainClaimsError:
        raise
    except DomainStoreError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        _view_invalid(pointer, "untyped_shape")


def _untyped_rows(items, typed_ids, authority, pointer):
    if type(items) is not list:
        _view_invalid(pointer, "untyped_shape")
    seen = set()
    rows = []
    for index, item in enumerate(items):
        rows.append(
            _untyped_row(
                item,
                authority,
                pointer + "/" + str(index),
                typed_ids=typed_ids,
                seen=seen,
            )
        )
    rows.sort(key=lambda row: row["claim_id"].encode("utf-8"))
    return rows


def _coverage_status(stale_count, head):
    if stale_count > 0:
        return "stale"
    if head["review_id"] is None:
        return "proposal_only"
    return "reviewed_" + head["review_decision"]


def _history(store, lid, lineage_pointer):
    order = store.chains[lid]["annotation_order"]
    history = []
    previous = None
    first_ids = {}
    triples = {}
    for index, aid in enumerate(order):
        annotation = store.annotations[aid]
        report = annotation["report"]
        hpointer = lineage_pointer + "/history/" + str(index)
        items = report.get("claim_annotations")
        if type(items) is not list:
            _view_invalid(hpointer + "/claims", "claim_shape")
        seen = set()
        cmap = {}
        kind_counts = _empty_kind_counts()
        for j, item in enumerate(items):
            cid, kind, fingerprint, event_sha = _claim_binding(
                item, hpointer + "/claims/" + str(j), seen=seen
            )
            cmap[cid] = (kind, fingerprint, event_sha)
            kind_counts[kind] += 1
            if cid not in first_ids:
                first_ids[cid] = aid
            triples.setdefault(cid, set()).add((kind, fingerprint, event_sha))
        untyped_items = report.get("unannotated_claims")
        if type(untyped_items) is not list:
            _view_invalid(hpointer + "/untyped", "untyped_shape")
        untyped_ids = []
        untyped_seen = set()
        for j, item in enumerate(untyped_items):
            if type(item) is not dict or type(item.get("claim_id")) is not str:
                _view_invalid(hpointer + "/untyped/" + str(j), "untyped_shape")
            uid = item["claim_id"]
            if uid in seen or uid in untyped_seen:
                _view_invalid(hpointer + "/untyped/" + str(j), "untyped_shape")
            untyped_seen.add(uid)
            untyped_ids.append(uid)
        untyped_sorted = _unique_sorted(untyped_ids)
        if previous is None:
            changes = _empty_changes()
        else:
            prev_map, prev_untyped = previous
            added = _unique_sorted(cid for cid in cmap if cid not in prev_map)
            removed = _unique_sorted(cid for cid in prev_map if cid not in cmap)
            retyped = []
            rebound = []
            for cid in _byte_sort(cid for cid in cmap if cid in prev_map):
                kind, fingerprint, event_sha = cmap[cid]
                pkind, pfp, pevent = prev_map[cid]
                if kind != pkind:
                    retyped.append(cid)
                elif (fingerprint, event_sha) != (pfp, pevent):
                    rebound.append(cid)
            changes = {
                "claims_added": added,
                "claims_removed": removed,
                "claims_retyped": retyped,
                "claims_rebound": rebound,
                "untyped_changed": untyped_sorted != prev_untyped,
            }
        history.append(
            {
                "annotation_id": annotation["annotation_id"],
                "previous_annotation_id": annotation["previous_annotation_id"],
                "recorded_at": annotation["recorded_at"],
                "commit": report["commit"],
                "report_sha256": annotation["report_sha256"],
                "typed_claim_count": len(cmap),
                "untyped_claim_count": len(untyped_ids),
                "kind_counts": kind_counts,
                "changes_from_previous": changes,
            }
        )
        previous = (cmap, untyped_sorted)
    revisions = {cid: len(items) for cid, items in triples.items()}
    return history, first_ids, revisions


def _lineage_view(store, authority, heads, lid, index):
    chain = store.chains[lid]
    order = chain["annotation_order"]
    pointer = "/lineages/" + str(index)
    history, first_ids, revisions = _history(store, lid, pointer)
    head_ann = store.annotations[order[-1]]
    report = head_ann["report"]
    head = heads["heads"][lid]
    typed = _typed_rows(report.get("claim_annotations"), authority, pointer + "/claims")
    typed_ids = {row["claim_id"] for row in typed}
    for row in typed:
        row["first_annotation_id"] = first_ids[row["claim_id"]]
        row["binding_revisions"] = revisions[row["claim_id"]]
    untyped = _untyped_rows(
        report.get("unannotated_claims"), typed_ids, authority, pointer + "/untyped"
    )
    kinds = _empty_kinds()
    bound = 0
    stale = 0
    for row in typed:
        cell = kinds[row["claim_kind"]]
        cell["claim_ids"].append(row["claim_id"])
        if row["freshness"] == "stale":
            stale += 1
            cell["stale"] += 1
        else:
            bound += 1
            cell["head_bound"] += 1
    for kind in CLAIM_KINDS:
        kinds[kind]["claim_ids"] = _unique_sorted(kinds[kind]["claim_ids"])
    return {
        "lineage_id": lid,
        "paper_id": report["paper_id"],
        "source_association_id": report["source_association"]["association_id"],
        "source_digest_sha256": report["source_digest"]["sha256"],
        "repository": report["repository"],
        "commit": report["commit"],
        "head_annotation_id": head_ann["annotation_id"],
        "head_report_sha256": head_ann["report_sha256"],
        "current_review_id": head["review_id"],
        "review_decision": head["review_decision"],
        "reviewed_officiality": head["reviewed_officiality"],
        "relation_kind": report["relation"]["kind"],
        "coverage_status": _coverage_status(stale, head),
        "claim_freshness": {"head_bound": bound, "stale": stale},
        "typed_claim_count": len(typed),
        "untyped_claim_count": len(untyped),
        "claims": typed,
        "kinds": kinds,
        "untyped": untyped,
        "history": history,
    }


def _registry(lineages, authority):
    buckets = {}
    ledger = _ledger_map(authority)
    for row in lineages:
        for claim in row["claims"]:
            cid = claim["claim_id"]
            bucket = buckets.setdefault(
                cid,
                {
                    "claim_id": cid,
                    "kinds": set(),
                    "assessments": set(),
                    "fingerprints": set(),
                    "events": set(),
                    "papers": set(),
                    "lineages": set(),
                    "head_bound": 0,
                    "stale": 0,
                },
            )
            bucket["kinds"].add(claim["claim_kind"])
            bucket["assessments"].add(claim["recorded_assessment"])
            bucket["fingerprints"].add(claim["evidence_fingerprint"])
            bucket["events"].add(claim["assessment_head"]["event_sha256"])
            bucket["papers"].add(row["paper_id"])
            bucket["lineages"].add(row["lineage_id"])
            if claim["freshness"] == "stale":
                bucket["stale"] += 1
            else:
                bucket["head_bound"] += 1
    claims = []
    for cid in _byte_sort(buckets):
        bucket = buckets[cid]
        row = ledger.get(cid)
        claims.append(
            {
                "claim_id": cid,
                "claim_kinds": _unique_sorted(bucket["kinds"]),
                "recorded_assessments": _unique_sorted(bucket["assessments"]),
                "evidence_fingerprints": _unique_sorted(bucket["fingerprints"]),
                "event_sha256s": _unique_sorted(bucket["events"]),
                "ledger_status": "present" if row is not None else "missing",
                "current_assessment": None if row is None else row["assessment"],
                "paper_ids": _unique_sorted(bucket["papers"]),
                "lineage_ids": _unique_sorted(bucket["lineages"]),
                "head_bound": bucket["head_bound"],
                "stale": bucket["stale"],
            }
        )
    return claims


def _finding(kind, subject, paper_ids, lineage_ids):
    return {
        "kind": kind,
        "subject": subject,
        "paper_ids": _unique_sorted(paper_ids),
        "lineage_ids": _unique_sorted(lineage_ids),
        "detail": DETAIL[kind],
    }


def _papers_and_findings(lineages, registry, basis, ledger_claim_count, authority):
    findings = []
    for claim in registry:
        if len(claim["claim_kinds"]) >= 2:
            findings.append(
                _finding(
                    "claim_kind_divergence",
                    claim["claim_id"],
                    claim["paper_ids"],
                    claim["lineage_ids"],
                )
            )
        if len(claim["evidence_fingerprints"]) >= 2 or len(claim["event_sha256s"]) >= 2:
            findings.append(
                _finding(
                    "claim_binding_divergence",
                    claim["claim_id"],
                    claim["paper_ids"],
                    claim["lineage_ids"],
                )
            )
    drift = {}
    for row in lineages:
        for claim in row["claims"]:
            if not claim["assessment_drift"]:
                continue
            entry = drift.setdefault(claim["claim_id"], {"papers": set(), "lineages": set()})
            entry["papers"].add(row["paper_id"])
            entry["lineages"].add(row["lineage_id"])
    for cid in _byte_sort(drift):
        entry = drift[cid]
        findings.append(
            _finding("claim_assessment_drift", cid, entry["papers"], entry["lineages"])
        )
    by_paper = {}
    for row in lineages:
        paper = by_paper.setdefault(
            row["paper_id"],
            {
                "source_versions": {},
                "repos": {},
                "kind_claims": {kind: set() for kind in CLAIM_KINDS},
                "kind_lineages": {kind: set() for kind in CLAIM_KINDS},
                "kind_bound": {kind: 0 for kind in CLAIM_KINDS},
                "kind_stale": {kind: 0 for kind in CLAIM_KINDS},
                "typed_ids": set(),
                "untyped": {},
                "lids": [],
                "head_aids": [],
            },
        )
        paper["lids"].append(row["lineage_id"])
        paper["head_aids"].append(row["head_annotation_id"])
        assoc = row["source_association_id"]
        version = paper["source_versions"].setdefault(
            assoc, {"digests": set(), "repos": set(), "lids": set()}
        )
        version["digests"].add(row["source_digest_sha256"])
        version["repos"].add(row["repository"])
        version["lids"].add(row["lineage_id"])
        paper["repos"].setdefault(row["repository"], []).append(row)
        for kind in CLAIM_KINDS:
            cell = row["kinds"][kind]
            paper["kind_bound"][kind] += cell["head_bound"]
            paper["kind_stale"][kind] += cell["stale"]
            for cid in cell["claim_ids"]:
                paper["kind_claims"][kind].add(cid)
                paper["kind_lineages"][kind].add(row["lineage_id"])
                paper["typed_ids"].add(cid)
        for item in row["untyped"]:
            cid = item["claim_id"]
            untyped = paper["untyped"].setdefault(
                cid,
                {
                    "sha": item["claim_text_sha256"],
                    "assessments": set(),
                    "lids": set(),
                },
            )
            untyped["assessments"].add(item["recorded_assessment"])
            untyped["lids"].add(row["lineage_id"])
    ledger = _ledger_map(authority)
    papers = []
    for paper_id in _byte_sort(by_paper):
        group = by_paper[paper_id]
        source_versions = []
        for assoc in _byte_sort(group["source_versions"]):
            version = group["source_versions"][assoc]
            source_versions.append(
                {
                    "source_association_id": assoc,
                    "source_digest_sha256s": _unique_sorted(version["digests"]),
                    "repositories": _unique_sorted(version["repos"]),
                    "lineage_ids": _unique_sorted(version["lids"]),
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
                            "coverage_status": item["coverage_status"],
                            "typed_claim_count": item["typed_claim_count"],
                            "kind_counts": {
                                kind: len(item["kinds"][kind]["claim_ids"])
                                for kind in CLAIM_KINDS
                            },
                        }
                        for item in items
                    ],
                }
            )
        kind_coverage = {}
        uncovered = []
        for kind in CLAIM_KINDS:
            typed_count = len(group["kind_claims"][kind])
            coverage = "covered" if typed_count > 0 else "uncovered"
            kind_coverage[kind] = {
                "typed_claim_count": typed_count,
                "lineage_count": len(group["kind_lineages"][kind]),
                "head_bound": group["kind_bound"][kind],
                "stale": group["kind_stale"][kind],
                "coverage": coverage,
            }
            if coverage == "uncovered":
                uncovered.append(kind)
        untyped_claims = []
        for cid in _byte_sort(cid for cid in group["untyped"] if cid not in group["typed_ids"]):
            item = group["untyped"][cid]
            row = ledger.get(cid)
            untyped_claims.append(
                {
                    "claim_id": cid,
                    "claim_text_sha256": item["sha"],
                    "recorded_assessments": _unique_sorted(item["assessments"]),
                    "ledger_status": "present" if row is not None else "missing",
                    "current_assessment": None if row is None else row["assessment"],
                    "lineage_ids": _unique_sorted(item["lids"]),
                }
            )
        search_scope = {
            "lineage_ids": _unique_sorted(group["lids"]),
            "head_annotation_ids": _unique_sorted(group["head_aids"]),
            "claim_ledger_sha256": basis["claim_ledger_sha256"],
            "assessment_heads_sha256": basis["assessment_heads_sha256"],
            "ledger_claim_count": ledger_claim_count,
        }
        papers.append(
            {
                "paper_id": paper_id,
                "source_versions": source_versions,
                "repositories": repositories,
                "kind_coverage": kind_coverage,
                "uncovered_kinds": uncovered,
                "untyped_claims": untyped_claims,
                "search_scope": search_scope,
                "finding_count": 0,
            }
        )
        for item in untyped_claims:
            if item["ledger_status"] != "missing":
                continue
            findings.append(
                _finding(
                    "untyped_claim_missing",
                    paper_id + "|" + item["claim_id"],
                    [paper_id],
                    item["lineage_ids"],
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
    if any(row["coverage_status"] == "stale" for row in lineages):
        return "re_record_annotation"
    return "none"


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_CLAIMS_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, VIEW_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise DomainClaimsError(
            "DOMAIN_CLAIMS_VIEW_INVALID",
            MESSAGES["DOMAIN_CLAIMS_VIEW_INVALID"],
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
    ledger = _ledger_map(authority)
    ledger_claim_count = len(ledger)
    all_lids = sorted(store.chains, key=lambda item: item.encode("utf-8"))
    known = {_paper_of(store, lid) for lid in all_lids}
    if paper_id is not None:
        if paper_id not in known:
            _fail(
                "DOMAIN_CLAIMS_PAPER_UNKNOWN",
                "/paper_id",
                "check_paper_id",
                {"known_paper_count": len(known)},
            )
        lids = [lid for lid in all_lids if _paper_of(store, lid) == paper_id]
    else:
        lids = all_lids
    lineages = []
    for index, lid in enumerate(lids):
        lineages.append(_lineage_view(store, authority, heads, lid, index))
    claims = _registry(lineages, authority)
    papers, findings = _papers_and_findings(
        lineages, claims, basis, ledger_claim_count, authority
    )
    view = {
        "schema": VIEW_SCHEMA,
        "basis": basis,
        "paper_filter": paper_id,
        "ledger_claim_count": ledger_claim_count,
        "lineage_count": len(lineages),
        "lineages": lineages,
        "claims": claims,
        "papers": papers,
        "findings": findings,
        "publication": "unpublished",
        "write_kind": "read_only",
        "audit_coverage": "not_wired",
        "code_freshness": "not_checked",
        "evidence_recheck": "not_performed",
        "typed_fact_promotion": "none",
        "experiment_conditions": "not_modeled",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": _next_action(lineages, findings),
    }
    return _seal(view)


def build_domain_claim_coverage_view(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, store, authority):
        try:
            return _build(snapshot, store, authority, paper_id)
        except DomainClaimsError:
            raise
        except DomainStoreError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
    except DomainClaimsError:
        raise
    except DomainStoreError:
        raise
    except OSError:
        _changed()
