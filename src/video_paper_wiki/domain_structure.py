"""Read-only typed concept registry and capability matrix. Vault writes are forbidden."""

from __future__ import annotations

import json

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_proposal import (
    CAPABILITY_NAMES,
    CLAIM_KINDS,
    CONCEPT_KINDS,
    DomainProposalError,
    _taxonomy_pairs,
)
from video_paper_wiki.domain_publication import _basis
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MESSAGES as STORE_MESSAGES,
    _claim_freshness,
    _with_store,
    derive_domain_heads,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.source_semantics_contracts import sha

VIEW_SCHEMA = "video-paper-wiki.domain-structure-view.v1"
STRUCTURE_COMMAND = "domain.structure"
PAPER_ID_LIMIT = 256
PRESENT_STATUSES = frozenset({"present", "partial"})
CODE_OR_CONFIG = frozenset({"code", "config"})
MESSAGES = {
    "DOMAIN_STRUCTURE_INVALID": "domain structure input is invalid",
    "DOMAIN_STRUCTURE_PAPER_UNKNOWN": "domain structure paper_id is unknown",
    "DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE": "domain structure taxonomy is unavailable",
    "DOMAIN_STRUCTURE_VIEW_INVALID": "domain structure view is invalid",
}
DETAIL = {
    "concept_kind_divergence": "the same term_key is used with more than one concept_kind",
    "surface_form_divergence": "the same concept_kind and surface_form map to more than one term_key",
    "taxonomy_term_unknown": "taxonomy_v1 term_key is absent from the packed taxonomy pair set",
    "capability_divergence": "lineages of the same paper and repository disagree on this capability status",
}


class DomainStructureError(Exception):
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
    raise DomainStructureError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _view_invalid(pointer, reason):
    _fail("DOMAIN_STRUCTURE_VIEW_INVALID", pointer, "repair_store", {"reason": reason})


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
        _fail("DOMAIN_STRUCTURE_INVALID", "/paper_id", "repair_input")


def _load_taxonomy():
    try:
        raw = read_projection_resource_bytes("taxonomy", "v1.json")
        pairs = _taxonomy_pairs()
    except DomainProposalError:
        _fail("DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE", "/taxonomy_basis", "repair_install")
    except OSError:
        _fail("DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE", "/taxonomy_basis", "repair_install")
    if raw is None or not pairs:
        _fail("DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE", "/taxonomy_basis", "repair_install")
    return {
        "resource": "taxonomy/v1.json",
        "sha256": sha(raw),
        "pair_count": len(pairs),
    }, pairs


def _concept_row(row, pairs, pointer):
    try:
        if type(row) is not dict:
            _view_invalid(pointer, "concept_shape")
        tax = row.get("taxonomy_ref")
        proposal = row.get("normalization_proposal")
        term_status = row.get("term_status")
        tax_present = tax is not None
        prop_present = proposal is not None
        if tax_present and not prop_present and term_status == "taxonomy_v1":
            if type(tax) is not dict:
                _view_invalid(pointer, "concept_shape")
            axis = tax.get("axis")
            slug = tax.get("slug")
            if type(axis) is not str or type(slug) is not str:
                _view_invalid(pointer, "concept_shape")
            term_key = "tax:" + axis + ":" + slug
            taxonomy_check = "known" if (axis, slug) in pairs else "unknown"
            proposed_slug = None
            taxonomy_ref = {"axis": axis, "slug": slug}
        elif prop_present and not tax_present and term_status == "normalization_proposal":
            if type(proposal) is not dict:
                _view_invalid(pointer, "concept_shape")
            proposed_slug = proposal.get("proposed_slug")
            if type(proposed_slug) is not str or not proposed_slug:
                _view_invalid(pointer, "concept_shape")
            term_key = "prop:" + proposed_slug
            taxonomy_check = "not_applicable"
            taxonomy_ref = None
        else:
            _view_invalid(pointer, "concept_shape")
        kind = row.get("concept_kind")
        surface = row.get("surface_form")
        if type(kind) is not str or type(surface) is not str:
            _view_invalid(pointer, "concept_shape")
        return {
            "concept_kind": kind,
            "surface_form": surface,
            "term_status": term_status,
            "term_key": term_key,
            "taxonomy_ref": taxonomy_ref,
            "proposed_slug": proposed_slug,
            "taxonomy_check": taxonomy_check,
        }
    except DomainStructureError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        _view_invalid(pointer, "concept_shape")


def _search_scope(absence, pointer):
    if type(absence) is not dict:
        _view_invalid(pointer, "capability_shape")
    commit = absence.get("commit")
    tree_prefix = absence.get("tree_prefix")
    patterns = absence.get("search_patterns")
    observed = absence.get("observed_files")
    if type(commit) is not str or type(tree_prefix) is not str:
        _view_invalid(pointer, "capability_shape")
    if type(patterns) is not list or type(observed) is not list:
        _view_invalid(pointer, "capability_shape")
    return {
        "commit": commit,
        "tree_prefix": tree_prefix,
        "search_patterns": list(patterns),
        "observed_file_count": len(observed),
    }


def _capability_row(row, pointer):
    try:
        if type(row) is not dict:
            _view_invalid(pointer, "capability_shape")
        status = row.get("status")
        kind = row.get("declaration_kind")
        locators = row.get("locators")
        absence = row.get("absence_scope")
        if type(locators) is not list:
            _view_invalid(pointer, "capability_shape")
        paths = []
        for locator in locators:
            if type(locator) is not dict or type(locator.get("path")) is not str:
                _view_invalid(pointer, "capability_shape")
            paths.append(locator["path"])
        if status in PRESENT_STATUSES:
            if kind not in CODE_OR_CONFIG or not locators or absence is not None:
                _view_invalid(pointer, "capability_shape")
            evidence_basis = "code_located"
            search_scope = None
        elif status == "absent":
            if locators or absence is None:
                _view_invalid(pointer, "capability_shape")
            evidence_basis = "absent_with_scope"
            search_scope = _search_scope(absence, pointer)
        elif status == "unverified":
            if absence is not None:
                _view_invalid(pointer, "capability_shape")
            evidence_basis = "declared_only" if kind == "readme_only" else "unverified"
            search_scope = None
        else:
            _view_invalid(pointer, "capability_shape")
        return {
            "status": status,
            "declaration_kind": kind,
            "evidence_basis": evidence_basis,
            "locator_count": len(locators),
            "locator_paths": paths,
            "search_scope": search_scope,
            "code_recheck": "not_checked",
        }
    except DomainStructureError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        _view_invalid(pointer, "capability_shape")


def _capabilities_map(rows, pointer):
    if type(rows) is not list:
        _view_invalid(pointer, "capability_shape")
    names = []
    for row in rows:
        if type(row) is not dict:
            _view_invalid(pointer, "capability_shape")
        names.append(row.get("name"))
    try:
        if sorted(names) != sorted(CAPABILITY_NAMES) or len(set(names)) != 5:
            _view_invalid(pointer, "capability_shape")
    except TypeError:
        _view_invalid(pointer, "capability_shape")
    out = {}
    originals = {}
    for row in rows:
        name = row["name"]
        if name not in CAPABILITY_NAMES:
            _view_invalid(pointer, "capability_shape")
        out[name] = _capability_row(row, pointer + "/" + name)
        originals[name] = row
    return out, originals


def _claim_set(items, pointer):
    out = set()
    if type(items) is not list:
        _view_invalid(pointer, "concept_shape")
    for index, item in enumerate(items):
        if type(item) is not dict:
            _view_invalid(pointer + "/" + str(index), "concept_shape")
        try:
            head = item["assessment_head"]
            out.add(
                (
                    item["claim_id"],
                    item["claim_kind"],
                    item["evidence_fingerprint"],
                    head["event_sha256"],
                )
            )
        except (TypeError, KeyError):
            _view_invalid(pointer + "/" + str(index), "concept_shape")
    return out


def _freshness_counts():
    return {kind: {"head_bound": 0, "stale": 0} for kind in CLAIM_KINDS}


def _structure_status(stale_count, head):
    if stale_count > 0:
        return "stale"
    if head["review_id"] is None:
        return "proposal_only"
    return "reviewed_" + head["review_decision"]


def _capability_status(capabilities):
    return {name: capabilities[name]["status"] for name in CAPABILITY_NAMES}


def _history(store, lid, pairs, lineage_pointer):
    chain = store.chains[lid]
    order = chain["annotation_order"]
    history = []
    previous = None
    head_concepts = None
    head_capabilities = None
    for index, aid in enumerate(order):
        annotation = store.annotations[aid]
        report = annotation["report"]
        is_head = index == len(order) - 1
        concept_pointer = lineage_pointer + "/concepts" if is_head else lineage_pointer + "/history/" + str(index) + "/concepts"
        capability_pointer = lineage_pointer + "/capabilities" if is_head else lineage_pointer + "/history/" + str(index) + "/capabilities"
        if type(report.get("concepts")) is not list:
            _view_invalid(concept_pointer, "concept_shape")
        concepts = [
            _concept_row(row, pairs, concept_pointer + "/" + str(j))
            for j, row in enumerate(report["concepts"])
        ]
        capabilities, originals = _capabilities_map(report["capabilities"], capability_pointer)
        term_keys = _byte_sort(item["term_key"] for item in concepts)
        triples = sorted(
            ([item["concept_kind"], item["term_key"], item["surface_form"]] for item in concepts),
            key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8"), item[2].encode("utf-8")),
        )
        try:
            triple_bytes = canonicalize(triples)
            cap_bytes = {name: canonicalize(originals[name]) for name in CAPABILITY_NAMES}
        except CanonicalJsonError:
            _view_invalid(lineage_pointer, "canonical_bytes")
        claims = _claim_set(report.get("claim_annotations"), lineage_pointer + "/claim_annotations")
        if previous is None:
            changes = {
                "commit_changed": False,
                "concepts_changed": False,
                "claims_changed": False,
                "capabilities_changed": [],
            }
        else:
            changes = {
                "commit_changed": report["commit"] != previous["commit"],
                "concepts_changed": triple_bytes != previous["triples"],
                "claims_changed": claims != previous["claims"],
                "capabilities_changed": [
                    name for name in CAPABILITY_NAMES if cap_bytes[name] != previous["cap_bytes"][name]
                ],
            }
        history.append(
            {
                "annotation_id": annotation["annotation_id"],
                "previous_annotation_id": annotation["previous_annotation_id"],
                "recorded_at": annotation["recorded_at"],
                "commit": report["commit"],
                "report_sha256": annotation["report_sha256"],
                "concept_count": len(concepts),
                "concept_term_keys": term_keys,
                "capability_status": _capability_status(capabilities),
                "changes_from_previous": changes,
            }
        )
        previous = {
            "commit": report["commit"],
            "triples": triple_bytes,
            "claims": claims,
            "cap_bytes": cap_bytes,
        }
        if is_head:
            head_concepts = concepts
            head_capabilities = capabilities
    return history, head_concepts, head_capabilities


def _lineage_view(store, authority, heads, lid, pairs, index):
    chain = store.chains[lid]
    head_ann = store.annotations[chain["annotation_order"][-1]]
    report = head_ann["report"]
    head = heads["heads"][lid]
    pointer = "/lineages/" + str(index)
    bound = 0
    stale = 0
    by_kind = _freshness_counts()
    for item in report["claim_annotations"]:
        freshness, _reason = _claim_freshness(item, authority)
        bucket = "stale" if freshness == "stale" else "head_bound"
        if freshness == "stale":
            stale += 1
        else:
            bound += 1
        kind = item.get("claim_kind")
        if kind not in by_kind:
            _view_invalid(pointer + "/claims_by_kind", "concept_shape")
        by_kind[kind][bucket] += 1
    history, concepts, capabilities = _history(store, lid, pairs, pointer)
    status = _structure_status(stale, head)
    unannotated = report.get("unannotated_claims")
    if type(unannotated) is not list:
        _view_invalid(pointer + "/unannotated_count", "concept_shape")
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
        "relation_kind": report["relation"]["kind"],
        "structure_status": status,
        "claim_freshness": {"head_bound": bound, "stale": stale},
        "claims_by_kind": by_kind,
        "unannotated_count": len(unannotated),
        "concepts": concepts,
        "capabilities": capabilities,
        "history": history,
    }


def _registry(lineages):
    buckets = {}
    for row in lineages:
        for concept in row["concepts"]:
            key = concept["term_key"]
            bucket = buckets.setdefault(
                key,
                {
                    "term_key": key,
                    "term_status": concept["term_status"],
                    "kinds": set(),
                    "taxonomy_ref": concept["taxonomy_ref"],
                    "proposed_slug": concept["proposed_slug"],
                    "taxonomy_check": concept["taxonomy_check"],
                    "surfaces": set(),
                    "papers": set(),
                    "lineages": set(),
                    "mention_count": 0,
                },
            )
            bucket["kinds"].add(concept["concept_kind"])
            bucket["surfaces"].add(concept["surface_form"])
            bucket["papers"].add(row["paper_id"])
            bucket["lineages"].add(row["lineage_id"])
            bucket["mention_count"] += 1
    concepts = []
    for key in _byte_sort(buckets):
        bucket = buckets[key]
        concepts.append(
            {
                "term_key": key,
                "term_status": bucket["term_status"],
                "concept_kinds": _unique_sorted(bucket["kinds"]),
                "taxonomy_ref": bucket["taxonomy_ref"],
                "proposed_slug": bucket["proposed_slug"],
                "taxonomy_check": bucket["taxonomy_check"],
                "surface_forms": _unique_sorted(bucket["surfaces"]),
                "paper_ids": _unique_sorted(bucket["papers"]),
                "lineage_ids": _unique_sorted(bucket["lineages"]),
                "mention_count": bucket["mention_count"],
            }
        )
    return concepts


def _empty_coverage():
    return {name: {"present": 0, "partial": 0, "absent": 0, "unverified": 0} for name in CAPABILITY_NAMES}


def _papers_and_findings(lineages, concepts):
    findings = []
    for concept in concepts:
        if len(concept["concept_kinds"]) >= 2:
            findings.append(
                {
                    "kind": "concept_kind_divergence",
                    "subject": concept["term_key"],
                    "paper_ids": list(concept["paper_ids"]),
                    "lineage_ids": list(concept["lineage_ids"]),
                    "detail": DETAIL["concept_kind_divergence"],
                }
            )
        if concept["taxonomy_check"] == "unknown":
            findings.append(
                {
                    "kind": "taxonomy_term_unknown",
                    "subject": concept["term_key"],
                    "paper_ids": list(concept["paper_ids"]),
                    "lineage_ids": list(concept["lineage_ids"]),
                    "detail": DETAIL["taxonomy_term_unknown"],
                }
            )
    surfaces = {}
    for row in lineages:
        for concept in row["concepts"]:
            key = (concept["concept_kind"], concept["surface_form"])
            entry = surfaces.setdefault(key, {"keys": set(), "papers": set(), "lineages": set()})
            entry["keys"].add(concept["term_key"])
            entry["papers"].add(row["paper_id"])
            entry["lineages"].add(row["lineage_id"])
    for (kind, surface), entry in surfaces.items():
        if len(entry["keys"]) >= 2:
            findings.append(
                {
                    "kind": "surface_form_divergence",
                    "subject": kind + ":" + surface,
                    "paper_ids": _unique_sorted(entry["papers"]),
                    "lineage_ids": _unique_sorted(entry["lineages"]),
                    "detail": DETAIL["surface_form_divergence"],
                }
            )
    groups = {}
    for row in lineages:
        groups.setdefault((row["paper_id"], row["repository"]), []).append(row)
    for (paper_id, repository), items in groups.items():
        if len(items) < 2:
            continue
        for name in CAPABILITY_NAMES:
            statuses = {item["capabilities"][name]["status"] for item in items}
            if len(statuses) >= 2:
                findings.append(
                    {
                        "kind": "capability_divergence",
                        "subject": paper_id + "|" + repository + "|" + name,
                        "paper_ids": [paper_id],
                        "lineage_ids": _unique_sorted(item["lineage_id"] for item in items),
                        "detail": DETAIL["capability_divergence"],
                    }
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
    by_paper = {}
    for row in lineages:
        paper = by_paper.setdefault(
            row["paper_id"],
            {
                "ids": set(),
                "repos": {},
                "kind_terms": {kind: set() for kind in CONCEPT_KINDS},
                "coverage": _empty_coverage(),
            },
        )
        paper["ids"].add(row["source_association_id"])
        paper["repos"].setdefault(row["repository"], []).append(row)
        for concept in row["concepts"]:
            paper["kind_terms"][concept["concept_kind"]].add(concept["term_key"])
        for name in CAPABILITY_NAMES:
            paper["coverage"][name][row["capabilities"][name]["status"]] += 1
    papers = []
    for paper_id in _byte_sort(by_paper):
        group = by_paper[paper_id]
        repositories = []
        for repo in _byte_sort(group["repos"]):
            items = sorted(group["repos"][repo], key=lambda item: item["lineage_id"].encode("utf-8"))
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
                            "structure_status": item["structure_status"],
                            "capability_status": _capability_status(item["capabilities"]),
                        }
                        for item in items
                    ],
                }
            )
        papers.append(
            {
                "paper_id": paper_id,
                "source_association_ids": _unique_sorted(group["ids"]),
                "repositories": repositories,
                "concept_kind_counts": {
                    kind: len(group["kind_terms"][kind]) for kind in CONCEPT_KINDS
                },
                "capability_coverage": group["coverage"],
                "finding_count": counts.get(paper_id, 0),
            }
        )
    return papers, findings


def _next_action(lineages, findings):
    if findings:
        return "review_findings"
    if any(row["structure_status"] == "stale" for row in lineages):
        return "re_record_annotation"
    return "none"


def _seal(view):
    try:
        raw = canonicalize(view)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_STRUCTURE_VIEW_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, VIEW_SCHEMA)
    except ContractError as exc:
        details = dict(exc.details or {})
        raise DomainStructureError(
            "DOMAIN_STRUCTURE_VIEW_INVALID",
            MESSAGES["DOMAIN_STRUCTURE_VIEW_INVALID"],
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


def _build(snapshot, store, authority, paper_id, taxonomy_basis, pairs):
    basis = _basis(snapshot, store, authority)
    heads = derive_domain_heads(store)
    all_lids = sorted(store.chains, key=lambda item: item.encode("utf-8"))
    known = {_paper_of(store, lid) for lid in all_lids}
    if paper_id is not None:
        if paper_id not in known:
            _fail(
                "DOMAIN_STRUCTURE_PAPER_UNKNOWN",
                "/paper_id",
                "check_paper_id",
                {"known_paper_count": len(known)},
            )
        lids = [lid for lid in all_lids if _paper_of(store, lid) == paper_id]
    else:
        lids = all_lids
    lineages = []
    for index, lid in enumerate(lids):
        lineages.append(_lineage_view(store, authority, heads, lid, pairs, index))
    concepts = _registry(lineages)
    papers, findings = _papers_and_findings(lineages, concepts)
    view = {
        "schema": VIEW_SCHEMA,
        "basis": basis,
        "taxonomy_basis": taxonomy_basis,
        "paper_filter": paper_id,
        "lineage_count": len(lineages),
        "lineages": lineages,
        "concepts": concepts,
        "papers": papers,
        "findings": findings,
        "publication": "unpublished",
        "write_kind": "read_only",
        "audit_coverage": "not_wired",
        "code_freshness": "not_checked",
        "evidence_recheck": "not_performed",
        "taxonomy_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": _next_action(lineages, findings),
    }
    return _seal(view)


def build_domain_structure_view(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)
    taxonomy_basis, pairs = _load_taxonomy()

    def apply(snapshot, store, authority):
        try:
            return _build(snapshot, store, authority, paper_id, taxonomy_basis, pairs)
        except DomainStructureError:
            raise
        except DomainStoreError:
            raise
        except OSError:
            _changed()

    try:
        return _with_store(vault_root, apply, authority_required=True)
    except DomainStructureError:
        raise
    except DomainStoreError:
        raise
    except DomainProposalError:
        _fail("DOMAIN_STRUCTURE_TAXONOMY_UNAVAILABLE", "/taxonomy_basis", "repair_install")
    except OSError:
        _changed()
