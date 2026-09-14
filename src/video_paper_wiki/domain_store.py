"""Compatible domain annotation, review, and head storage under .work staging."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_proposal import DomainProposalError, inspect_domain_proposal
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.markdown_locator import decode_evidence, evidence_fingerprint_versioned
from video_paper_wiki.secure_io import (
    JSON_MAX_BYTES,
    SecureIOError,
    close_fd,
    dir_open_flags,
    load_strict_json,
    parse_strict_json,
    stamp,
)
from video_paper_wiki.source_publication import _vault
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import calendar, sha
from video_paper_wiki.source_state import _claim_ledger
from video_paper_wiki.staging import StagingError, stage_bytes, validate_batch_id

ANNOTATION_SCHEMA = "video-paper-wiki.domain-annotation-record.v1"
REVIEW_SCHEMA = "video-paper-wiki.domain-review-record.v1"
DECISION_SCHEMA = "video-paper-wiki.domain-review-decision.v1"
HEADS_SCHEMA = "video-paper-wiki.domain-heads.v1"
RECORD_COMMAND = "domain.record"
REVIEW_COMMAND = "domain.review"
STATUS_COMMAND = "domain.status"
DOMAIN_ROOT = "wiki/meta/domain"
EVENT_DIR = "wiki/meta/reviews/"
MAX_LINEAGES = 4096
MAX_PER_LINEAGE = 256
MAX_RECORD_BYTES = JSON_MAX_BYTES
LINEAGE_RE = re.compile(r"^dln-[0-9a-f]{20}$")
ANNOTATION_RE = re.compile(r"^dan-[0-9a-f]{20}$")
REVIEW_RE = re.compile(r"^drv-[0-9a-f]{20}$")
MESSAGES = {
    "DOMAIN_STORE_INVALID": "domain store is invalid",
    "DOMAIN_STORE_LIMIT": "domain store exceeds a closed bound",
    "DOMAIN_STORE_CHAIN_INVALID": "domain store chain is invalid",
    "DOMAIN_STORE_HEADS_MISSING": "domain store heads.json is missing",
    "DOMAIN_STORE_HEADS_MISMATCH": "domain store heads.json does not match derived heads",
    "DOMAIN_STORE_CHANGED": "domain store changed during read",
    "DOMAIN_RECORD_PREVIOUS_MISMATCH": "domain record previous annotation does not match the lineage head",
    "DOMAIN_RECORD_UNCHANGED": "domain record report is unchanged from the lineage head",
    "DOMAIN_REVIEW_TARGET_NOT_HEAD": "domain review target is not the lineage annotation head",
    "DOMAIN_REVIEW_BINDING_MISMATCH": "domain review annotation binding does not match stored bytes",
    "DOMAIN_REVIEW_STALE": "domain review expected previous review is stale",
    "DOMAIN_REVIEW_INVALID": "domain review is invalid",
    "DOMAIN_HEAD_STALE": "domain head claim bindings are stale",
}


class DomainStoreError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


class DomainStore:
    def __init__(self):
        self.annotations = {}
        self.annotation_raw = {}
        self.reviews = {}
        self.review_raw = {}
        self.chains = {}
        self.heads_raw = None
        self.empty = True


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise DomainStoreError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _id_digest(prefix, document, excluded):
    payload = {key: value for key, value in document.items() if key != excluded}
    try:
        return prefix + sha(canonicalize(payload))[:20]
    except CanonicalJsonError:
        _fail("DOMAIN_STORE_INVALID", "", "repair_store", {"reason": "canonical_bytes"})


def lineage_id_from_report(report):
    material = {
        "paper_id": report["paper_id"],
        "repository": report["repository"],
        "source_association_id": report["source_association"]["association_id"],
    }
    try:
        return "dln-" + sha(canonicalize(material))[:20]
    except CanonicalJsonError:
        _fail("DOMAIN_STORE_INVALID", "/report", "repair_store", {"reason": "canonical_bytes"})


def annotation_id_from_record(record):
    return _id_digest("dan-", record, "annotation_id")


def review_id_from_record(record):
    return _id_digest("drv-", record, "review_id")


def derive_domain_heads(store):
    heads = {}
    for lid in sorted(store.chains):
        chain = store.chains[lid]
        ann_id = chain["annotation_order"][-1]
        entry = {
            "annotation_id": ann_id,
            "annotation_sha256": sha(store.annotation_raw[ann_id]),
            "review_id": None,
            "review_sha256": None,
            "review_decision": None,
            "reviewed_officiality": None,
        }
        if chain["review_order"]:
            review_id = chain["review_order"][-1]
            review = store.reviews[review_id]
            if review["annotation_id"] == ann_id:
                relation = review.get("relation_review")
                entry["review_id"] = review_id
                entry["review_sha256"] = sha(store.review_raw[review_id])
                entry["review_decision"] = review["decision"]
                entry["reviewed_officiality"] = (
                    None if relation is None else relation["reviewed_officiality"]
                )
        heads[lid] = entry
    return {"schema": HEADS_SCHEMA, "heads": heads}


def _batch(value, pointer):
    try:
        return validate_batch_id(value)
    except StagingError as exc:
        raise DomainStoreError(
            exc.code,
            exc.message,
            {"instance_pointer": pointer, "next_action": "repair_input", **exc.details},
        ) from exc


def _vault_root(value):
    try:
        return checked_path(value)
    except ContractError as exc:
        raise DomainStoreError(
            exc.code,
            exc.message,
            {"instance_pointer": "/vault_root", "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc


def _timestamp(value, pointer):
    try:
        calendar(value, pointer)
    except ContractError as exc:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_input", {"reason": "timestamp", **exc.details})
    return value


def _nonempty(value, pointer, *, limit=256):
    if type(value) is not str or not value or len(value) > limit:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_input", {"reason": "string"})
    return value


def _match_id(value, pattern, pointer):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_input", {"reason": "identity"})
    return value


def _seal(document, schema):
    try:
        raw = canonicalize(document)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_STORE_INVALID", "", "repair_store", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, schema)
    except ContractError as exc:
        _map_schema(exc, "repair_store")
    return sealed, raw


def _map_schema(exc, next_action, *, code="DOMAIN_STORE_INVALID"):
    pointer = exc.details.get("instance_pointer") or ""
    if exc.code in {"SOURCE_SEMANTICS_LIMIT", "TRANSACTION_LIMIT_EXCEEDED"}:
        code = "DOMAIN_STORE_LIMIT"
    raise DomainStoreError(
        code,
        MESSAGES.get(code, MESSAGES["DOMAIN_STORE_INVALID"]),
        {"instance_pointer": pointer, "next_action": next_action, **exc.details},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _map_snapshot(exc):
    code = getattr(exc, "code", "DOMAIN_STORE_INVALID")
    details = dict(getattr(exc, "details", {}) or {})
    pointer = details.get("path") or details.get("instance_pointer") or "/wiki/meta/domain"
    if code in {"AUDIT_RACE"} or getattr(exc, "exit_code", 2) == 75 and code in {"SOURCE_CHANGED"}:
        _fail(
            "DOMAIN_STORE_CHANGED",
            pointer if str(pointer).startswith("/") else "/" + str(pointer),
            "repeat_read",
            dict(details),
            exit_code=75,
        )
    if code in {"RECEIPT_CHAIN_INVALID", "BLOB_LIMIT_EXCEEDED"}:
        _fail("DOMAIN_STORE_LIMIT", pointer if str(pointer).startswith("/") else "/" + str(pointer), "reduce_store", dict(details))
    if code == "WORK_PATH_UNSAFE":
        raise DomainStoreError(
            code,
            getattr(exc, "message", code),
            {"instance_pointer": "/vault_root", "next_action": "repair_input", **details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    _fail(
        "DOMAIN_STORE_INVALID",
        pointer if str(pointer).startswith("/") else "/" + str(pointer),
        "repair_store",
        {"prior_code": code, **details},
        exit_code=getattr(exc, "exit_code", 2),
    )


def _stat_child(parent_fd, name):
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _register_dir(snapshot, relative, fd):
    current = os.fstat(fd)
    prior = snapshot.directories.get(relative)
    if prior is not None and stamp(prior) != stamp(current):
        _fail("DOMAIN_STORE_CHANGED", "/" + relative, "repeat_read", {"path": relative}, exit_code=75)
    snapshot.directories.setdefault(relative, current)


def _open_named_dir(snapshot, parts):
    fds = []
    parent = snapshot.root_fd
    relative = ""
    try:
        for name in parts:
            st = _stat_child(parent, name)
            if st is None:
                for fd in reversed(fds):
                    close_fd(fd)
                return None, []
            relative = name if not relative else relative + "/" + name
            if stat.S_ISLNK(st.st_mode):
                _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "symlink", "path": relative})
            if not stat.S_ISDIR(st.st_mode):
                _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "entry_kind", "path": relative})
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            _register_dir(snapshot, relative, fd)
            parent = fd
        return parent, fds
    except BaseException:
        for fd in reversed(fds):
            close_fd(fd)
        raise


def _list_names(fd):
    try:
        return sorted(os.listdir(fd))
    except OSError:
        _fail("DOMAIN_STORE_CHANGED", "/wiki/meta/domain", "repeat_read", exit_code=75)


def _read_record(snapshot, relative, schema, pointer):
    try:
        raw = snapshot.read(relative, max_bytes=MAX_RECORD_BYTES)
    except ContractError as exc:
        _map_snapshot(exc)
    except SecureIOError as exc:
        _map_snapshot(exc)
    except OSError:
        _fail("DOMAIN_STORE_CHANGED", pointer, "repeat_read", {"path": relative}, exit_code=75)
    if len(raw) > MAX_RECORD_BYTES:
        _fail("DOMAIN_STORE_LIMIT", pointer, "reduce_store", {"path": relative, "size_bytes": len(raw)})
    try:
        doc = parse_strict_json(raw, invalid_code="DOMAIN_STORE_INVALID")
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "DOMAIN_STORE_LIMIT" if reason == "depth" else "DOMAIN_STORE_INVALID"
        _fail(code, pointer, "repair_store", {"path": relative, **exc.details})
    if type(doc) is not dict:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_store", {"reason": "type", "path": relative})
    try:
        validate_document(doc, schema)
    except ContractError as exc:
        _map_schema(exc, "repair_store")
    try:
        expected = canonicalize(doc)
    except CanonicalJsonError:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_store", {"reason": "canonical_bytes", "path": relative})
    if raw != expected:
        _fail("DOMAIN_STORE_INVALID", pointer, "repair_store", {"reason": "canonical_bytes", "path": relative})
    return doc, raw


def _load_store(snapshot):
    store = DomainStore()
    domain_fd, fds = _open_named_dir(snapshot, ("wiki", "meta", "domain"))
    try:
        if domain_fd is None:
            return store
        names = _list_names(domain_fd)
        allowed = {"annotations", "reviews", "heads.json"}
        extra = [name for name in names if name not in allowed]
        if extra:
            _fail(
                "DOMAIN_STORE_INVALID",
                _pointer("wiki", "meta", "domain", extra[0]),
                "repair_store",
                {"reason": "unknown_entry", "name": extra[0]},
            )
        annotations = {}
        annotation_raw = {}
        reviews = {}
        review_raw = {}
        if "annotations" in names:
            _scan_identity_tree(
                snapshot,
                domain_fd,
                "annotations",
                LINEAGE_RE,
                ANNOTATION_RE,
                ANNOTATION_SCHEMA,
                "annotation_id",
                annotations,
                annotation_raw,
            )
        if "reviews" in names:
            _scan_identity_tree(
                snapshot,
                domain_fd,
                "reviews",
                LINEAGE_RE,
                REVIEW_RE,
                REVIEW_SCHEMA,
                "review_id",
                reviews,
                review_raw,
            )
        heads_raw = None
        if "heads.json" in names:
            st = _stat_child(domain_fd, "heads.json")
            _require_regular(st, DOMAIN_ROOT + "/heads.json")
            heads_doc, heads_raw = _read_record(
                snapshot, DOMAIN_ROOT + "/heads.json", HEADS_SCHEMA, "/wiki/meta/domain/heads.json"
            )
            store.heads_raw = heads_raw
        store.annotations = annotations
        store.annotation_raw = annotation_raw
        store.reviews = reviews
        store.review_raw = review_raw
        store.empty = not annotations and not reviews and heads_raw is None
        if annotations or reviews:
            if heads_raw is None:
                _fail("DOMAIN_STORE_HEADS_MISSING", "/wiki/meta/domain/heads.json", "restore_heads")
        _validate_chains(store)
        derived = derive_domain_heads(store)
        derived_raw = canonicalize(derived)
        if heads_raw is None:
            if derived["heads"]:
                _fail("DOMAIN_STORE_HEADS_MISSING", "/wiki/meta/domain/heads.json", "restore_heads")
        elif heads_raw != derived_raw:
            _fail("DOMAIN_STORE_HEADS_MISMATCH", "/wiki/meta/domain/heads.json", "restore_heads")
        if len(store.chains) > MAX_LINEAGES:
            _fail("DOMAIN_STORE_LIMIT", "/wiki/meta/domain", "reduce_store", {"reason": "lineages"})
        return store
    finally:
        for fd in reversed(fds):
            close_fd(fd)


def _require_regular(st, relative):
    if st is None:
        _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "missing", "path": relative})
    if stat.S_ISLNK(st.st_mode):
        _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "symlink", "path": relative})
    if not stat.S_ISREG(st.st_mode):
        _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "entry_kind", "path": relative})
    if st.st_nlink > 1:
        _fail("DOMAIN_STORE_INVALID", "/" + relative, "repair_store", {"reason": "hardlink", "path": relative})
    if st.st_size > MAX_RECORD_BYTES:
        _fail("DOMAIN_STORE_LIMIT", "/" + relative, "reduce_store", {"path": relative, "size_bytes": st.st_size})


def _scan_identity_tree(snapshot, domain_fd, kind, lineage_re, file_re, schema, id_field, docs, raws):
    relative_kind = DOMAIN_ROOT + "/" + kind
    st = _stat_child(domain_fd, kind)
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        _fail("DOMAIN_STORE_INVALID", "/" + relative_kind, "repair_store", {"reason": "symlink", "path": relative_kind})
    if not stat.S_ISDIR(st.st_mode):
        _fail("DOMAIN_STORE_INVALID", "/" + relative_kind, "repair_store", {"reason": "entry_kind", "path": relative_kind})
    kind_fd = os.open(kind, dir_open_flags(), dir_fd=domain_fd)
    try:
        _register_dir(snapshot, relative_kind, kind_fd)
        lineages = _list_names(kind_fd)
        if not lineages:
            return
        for lineage_name in lineages:
            lineage_rel = relative_kind + "/" + lineage_name
            lst = _stat_child(kind_fd, lineage_name)
            if lst is None:
                _fail("DOMAIN_STORE_CHANGED", "/" + lineage_rel, "repeat_read", exit_code=75)
            if stat.S_ISLNK(lst.st_mode):
                _fail("DOMAIN_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "symlink", "path": lineage_rel})
            if not stat.S_ISDIR(lst.st_mode):
                _fail("DOMAIN_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "entry_kind", "path": lineage_rel})
            if lineage_re.fullmatch(lineage_name) is None:
                _fail("DOMAIN_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "unknown_entry", "path": lineage_rel})
            child_fd = os.open(lineage_name, dir_open_flags(), dir_fd=kind_fd)
            try:
                _register_dir(snapshot, lineage_rel, child_fd)
                files = _list_names(child_fd)
                if not files:
                    _fail("DOMAIN_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "empty_lineage", "path": lineage_rel})
                if len(files) > MAX_PER_LINEAGE:
                    _fail("DOMAIN_STORE_LIMIT", "/" + lineage_rel, "reduce_store", {"path": lineage_rel})
                for filename in files:
                    file_rel = lineage_rel + "/" + filename
                    fst = _stat_child(child_fd, filename)
                    _require_regular(fst, file_rel)
                    stem, sep, ext = filename.partition(".")
                    if sep != "." or ext != "json" or file_re.fullmatch(stem) is None:
                        _fail("DOMAIN_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "unknown_entry", "path": file_rel})
                    doc, raw = _read_record(snapshot, file_rel, schema, "/" + file_rel)
                    identity = doc[id_field]
                    if identity != stem:
                        _fail("DOMAIN_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "path_identity", "path": file_rel})
                    if doc["lineage_id"] != lineage_name:
                        _fail("DOMAIN_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "path_identity", "path": file_rel})
                    expected_id = (
                        annotation_id_from_record(doc) if id_field == "annotation_id" else review_id_from_record(doc)
                    )
                    if identity != expected_id:
                        _fail(
                            "DOMAIN_STORE_INVALID",
                            _pointer(*(file_rel.split("/"))) + "/" + id_field,
                            "repair_store",
                            {"reason": "identity", "path": file_rel},
                        )
                    if identity in docs:
                        _fail("DOMAIN_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "duplicate_id", "path": file_rel})
                    docs[identity] = doc
                    raws[identity] = raw
            finally:
                close_fd(child_fd)
    finally:
        close_fd(kind_fd)


def _validate_chains(store):
    annotation_groups = {}
    for doc in store.annotations.values():
        derived = lineage_id_from_report(doc["report"])
        if doc["lineage_id"] != derived:
            _fail(
                "DOMAIN_STORE_INVALID",
                "/annotation_id/" + doc["annotation_id"] + "/lineage_id",
                "repair_store",
                {"reason": "lineage_mismatch"},
            )
        expected_sha = sha(canonicalize(doc["report"]))
        if doc["report_sha256"] != expected_sha:
            _fail(
                "DOMAIN_STORE_INVALID",
                "/annotation_id/" + doc["annotation_id"] + "/report_sha256",
                "repair_store",
                {"reason": "report_sha256"},
            )
        annotation_groups.setdefault(doc["lineage_id"], []).append(doc)
    review_groups = {}
    for doc in store.reviews.values():
        if doc["annotation_id"] not in store.annotations:
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/review_id/" + doc["review_id"] + "/annotation_id",
                "repair_store",
                {"reason": "missing_annotation"},
            )
        parent = store.annotations[doc["annotation_id"]]
        if parent["lineage_id"] != doc["lineage_id"]:
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/review_id/" + doc["review_id"] + "/lineage_id",
                "repair_store",
                {"reason": "cross_lineage"},
            )
        if sha(store.annotation_raw[doc["annotation_id"]]) != doc["annotation_sha256"]:
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/review_id/" + doc["review_id"] + "/annotation_sha256",
                "repair_store",
                {"reason": "annotation_sha256"},
            )
        if doc.get("actor_kind") != "human":
            _fail("DOMAIN_STORE_INVALID", "/review_id/" + doc["review_id"] + "/actor_kind", "repair_store")
        _check_relation_review_shape(doc, "/review_id/" + doc["review_id"])
        review_groups.setdefault(doc["lineage_id"], []).append(doc)
    lineages = set(annotation_groups) | set(review_groups)
    if review_groups.keys() - annotation_groups.keys():
        orphan = sorted(review_groups.keys() - annotation_groups.keys())[0]
        _fail("DOMAIN_STORE_CHAIN_INVALID", "/lineage_id/" + orphan, "repair_store", {"reason": "orphan_review"})
    for lid in sorted(lineages):
        ann_order = _linear_chain(
            annotation_groups.get(lid, []),
            "annotation_id",
            "previous_annotation_id",
            "recorded_at",
            lid,
            known=store.annotations,
        )
        _check_report_progression(store, ann_order)
        review_order = _linear_chain(
            review_groups.get(lid, []),
            "review_id",
            "previous_review_id",
            "decided_at",
            lid,
            known=store.reviews,
        )
        store.chains[lid] = {"annotation_order": ann_order, "review_order": review_order}
        if len(ann_order) > MAX_PER_LINEAGE or len(review_order) > MAX_PER_LINEAGE:
            _fail("DOMAIN_STORE_LIMIT", "/lineage_id/" + lid, "reduce_store")


def _linear_chain(rows, id_field, prev_field, time_field, lineage_id, *, known=None):
    by_id = {}
    for row in rows:
        key = row[id_field]
        if key in by_id:
            _fail("DOMAIN_STORE_CHAIN_INVALID", "/" + id_field + "/" + key, "repair_store", {"reason": "duplicate"})
        by_id[key] = row
    roots = []
    children = {}
    for row in rows:
        previous = row[prev_field]
        if previous is None:
            roots.append(row[id_field])
            continue
        parent = by_id.get(previous)
        if parent is None:
            foreign = None if known is None else known.get(previous)
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/" + id_field + "/" + row[id_field] + "/" + prev_field,
                "repair_store",
                {"reason": "cross_lineage" if foreign is not None else "missing_predecessor"},
            )
        if parent["lineage_id"] != row["lineage_id"] or row["lineage_id"] != lineage_id:
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/" + id_field + "/" + row[id_field] + "/" + prev_field,
                "repair_store",
                {"reason": "cross_lineage"},
            )
        if previous in children:
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/" + id_field + "/" + row[id_field] + "/" + prev_field,
                "repair_store",
                {"reason": "fork"},
            )
        children[previous] = row[id_field]
        if calendar(parent[time_field]) > calendar(row[time_field]):
            _fail(
                "DOMAIN_STORE_CHAIN_INVALID",
                "/" + id_field + "/" + row[id_field] + "/" + time_field,
                "repair_store",
                {"reason": "timestamp_order"},
            )
    if rows and len(roots) != 1:
        _fail(
            "DOMAIN_STORE_CHAIN_INVALID",
            "/lineage_id/" + lineage_id,
            "repair_store",
            {"reason": "genesis"},
        )
    if not rows:
        return []
    seen = []
    cursor = roots[0]
    visiting = set()
    while cursor is not None:
        if cursor in visiting:
            _fail("DOMAIN_STORE_CHAIN_INVALID", "/lineage_id/" + lineage_id, "repair_store", {"reason": "cycle"})
        visiting.add(cursor)
        seen.append(cursor)
        cursor = children.get(cursor)
    if len(seen) != len(rows):
        _fail("DOMAIN_STORE_CHAIN_INVALID", "/lineage_id/" + lineage_id, "repair_store", {"reason": "orphan"})
    return seen


def _check_report_progression(store, order):
    previous_sha = None
    for annotation_id in order:
        current = store.annotations[annotation_id]["report_sha256"]
        if previous_sha is not None and current == previous_sha:
            _fail(
                "DOMAIN_RECORD_UNCHANGED",
                "/annotation_id/" + annotation_id + "/report_sha256",
                "revise_annotation",
            )
        previous_sha = current


def _check_relation_review_shape(doc, pointer):
    decision = doc["decision"]
    present = "relation_review" in doc and doc["relation_review"] is not None
    if decision == "accepted":
        if not present:
            _fail("DOMAIN_STORE_INVALID", pointer + "/relation_review", "repair_store", {"reason": "relation_review"})
    elif present:
        _fail("DOMAIN_STORE_INVALID", pointer + "/relation_review", "repair_store", {"reason": "relation_review"})


def _load_authority(snapshot, *, required):
    ledger = None
    heads = None
    events = {}
    try:
        ledger_raw = snapshot.read_optional(CLAIM_LEDGER, max_bytes=MAX_RECORD_BYTES * 8)
        heads_raw = snapshot.read_optional(ASSESSMENT_HEADS, max_bytes=MAX_RECORD_BYTES)
    except ContractError as exc:
        _map_snapshot(exc)
    except SecureIOError as exc:
        _map_snapshot(exc)
    if ledger_raw is None or heads_raw is None:
        if required:
            _fail("DOMAIN_STORE_INVALID", "/wiki/meta/ledgers/claim-ledger.json", "repair_store", {"reason": "authority"})
        return {"ledger": None, "heads": None, "events": events}
    try:
        ledger = _claim_ledger(ledger_raw, structural=False)
    except ContractError as exc:
        _fail("DOMAIN_STORE_INVALID", "/" + CLAIM_LEDGER, "repair_store", {"prior_code": exc.code, **exc.details})
    try:
        heads_doc = parse_strict_json(heads_raw, invalid_code="DOMAIN_STORE_INVALID")
        validate_document(heads_doc, "video-paper-wiki.assessment-heads.v2")
    except SecureIOError as exc:
        _fail("DOMAIN_STORE_INVALID", "/" + ASSESSMENT_HEADS, "repair_store", dict(exc.details))
    except ContractError as exc:
        _fail("DOMAIN_STORE_INVALID", "/" + ASSESSMENT_HEADS, "repair_store", {"prior_code": exc.code, **exc.details})
    return {"ledger": ledger, "heads": heads_doc, "heads_raw": heads_raw, "events": events, "snapshot": snapshot}


def _event_bytes(authority, claim_id, event_id):
    snapshot = authority["snapshot"]
    relative = EVENT_DIR + claim_id + "/" + event_id + ".json"
    if relative in authority["events"]:
        return authority["events"][relative]
    try:
        raw = snapshot.read_optional(relative, max_bytes=MAX_RECORD_BYTES)
    except ContractError as exc:
        _map_snapshot(exc)
    except SecureIOError as exc:
        _map_snapshot(exc)
    authority["events"][relative] = raw
    return raw


def _claim_freshness(item, authority):
    ledger = authority.get("ledger")
    heads = authority.get("heads")
    if ledger is None or heads is None:
        return "stale", "claim_missing"
    cid = item["claim_id"]
    row = ledger["claims"].get(cid)
    if row is None:
        return "stale", "claim_missing"
    if sha(row["text"].encode("utf-8")) != sha(item["claim_text"].encode("utf-8")):
        return "stale", "claim_text_changed"
    try:
        fingerprint = evidence_fingerprint_versioned([decode_evidence(entry) for entry in row["evidence"]])
    except ContractError:
        return "stale", "evidence_changed"
    if fingerprint != item["evidence_fingerprint"]:
        return "stale", "evidence_changed"
    stated = item["assessment_head"]
    head = heads["heads"].get(cid)
    event_raw = _event_bytes(authority, cid, stated["event_id"])
    if (
        head is None
        or head.get("event_id") != stated["event_id"]
        or head.get("event_sha256") != stated["event_sha256"]
        or head.get("evidence_profile") != stated["evidence_profile"]
        or event_raw is None
        or sha(event_raw) != stated["event_sha256"]
    ):
        return "stale", "assessment_head_changed"
    return "head_bound", None


def _require_head_bound(report, authority, pointer="/claim_annotations"):
    for index, item in enumerate(report["claim_annotations"]):
        freshness, reason = _claim_freshness(item, authority)
        if freshness != "head_bound":
            _fail(
                "DOMAIN_HEAD_STALE",
                pointer + "/" + str(index),
                "re_record_annotation",
                {"stale_reason": reason, "claim_id": item["claim_id"]},
            )


def _officiality_ok(report, relation_review):
    candidate = relation_review["reviewed_officiality"]
    if candidate == "unverified_candidate":
        return True
    relation = report["relation"]
    if candidate == "unofficial":
        return relation.get("officiality_candidate") == "third_party"
    if candidate != "official":
        return False
    if relation.get("kind") != "this_paper_implementation":
        return False
    if relation.get("officiality_candidate") != "pending_review":
        return False
    relied = list(relation_review["evidence_classes_relied_on"])
    if not relied:
        return False
    classes = relation["evidence_classes"]
    for item in relied:
        if not classes.get(item):
            return False
    if not any(item in relied for item in ("A", "B", "D")):
        return False
    if sorted(relation_review["missing_evidence"]) != sorted(relation.get("gaps") or []):
        return False
    if type(relation_review.get("reason")) is not str or not relation_review["reason"]:
        return False
    return True


def _copy_store(store):
    out = DomainStore()
    out.annotations = dict(store.annotations)
    out.annotation_raw = dict(store.annotation_raw)
    out.reviews = dict(store.reviews)
    out.review_raw = dict(store.review_raw)
    out.chains = {
        lid: {
            "annotation_order": list(chain["annotation_order"]),
            "review_order": list(chain["review_order"]),
        }
        for lid, chain in store.chains.items()
    }
    out.heads_raw = store.heads_raw
    out.empty = store.empty
    return out


def _stage_items(batch_id, items):
    staged = []
    for relative, destination, data in items:
        stage_bytes(batch_id=batch_id, relative=relative, data=data)
        staged.append(
            {
                "relative": "/".join(relative),
                "destination": destination,
                "sha256": sha(data),
                "size_bytes": len(data),
            }
        )
    return staged


def _with_store(vault_root, function, *, authority_required=False):
    vault = _vault_root(vault_root)
    try:
        with _vault(vault, None) as (_root, snapshot, _captured):
            try:
                store = _load_store(snapshot)
                required = authority_required or bool(store.annotations)
                authority = _load_authority(snapshot, required=required)
                result = function(snapshot, store, authority)
                snapshot.verify()
                return result
            except DomainStoreError:
                try:
                    snapshot.verify()
                except ContractError as exc:
                    _map_snapshot(exc)
                raise
            except ContractError as exc:
                _map_snapshot(exc)
            except SecureIOError as exc:
                _map_snapshot(exc)
            except StagingError:
                raise
    except DomainStoreError:
        raise
    except DomainProposalError:
        raise
    except StagingError:
        raise
    except ContractError as exc:
        _map_snapshot(exc)


def _build_annotation(*, lineage_id, previous, recorded_by, recorded_at, report):
    report_raw = canonicalize(report)
    sealed_report = json.loads(report_raw.decode("utf-8"))
    body = {
        "schema": ANNOTATION_SCHEMA,
        "lineage_id": lineage_id,
        "previous_annotation_id": previous,
        "recorded_by": recorded_by,
        "recorded_at": recorded_at,
        "report": sealed_report,
        "report_sha256": sha(report_raw),
    }
    annotation_id = annotation_id_from_record(body)
    record = {"annotation_id": annotation_id, **body}
    return _seal(record, ANNOTATION_SCHEMA)


def _build_review(*, lineage_id, annotation_id, annotation_sha256, previous, decision):
    body = {
        "schema": REVIEW_SCHEMA,
        "lineage_id": lineage_id,
        "annotation_id": annotation_id,
        "annotation_sha256": annotation_sha256,
        "previous_review_id": previous,
        "actor_kind": "human",
        "decision": decision["decision"],
        "decided_by": decision["decided_by"],
        "decided_at": decision["decided_at"],
        "reason": decision["reason"],
    }
    if decision["decision"] == "accepted":
        body["relation_review"] = dict(decision["relation_review"])
    review_id = review_id_from_record(body)
    record = {"review_id": review_id, **body}
    return _seal(record, REVIEW_SCHEMA)


def record_domain_annotation(
    *,
    input_path,
    vault_root,
    code_batch_id,
    batch_id,
    recorded_by,
    recorded_at,
    previous_annotation_id=None,
):
    batch = _batch(batch_id, "/batch_id")
    _batch(code_batch_id, "/code_batch_id")
    recorded_by = _nonempty(recorded_by, "/recorded_by")
    recorded_at = _timestamp(recorded_at, "/recorded_at")
    previous = previous_annotation_id
    if previous is not None:
        previous = _match_id(previous, ANNOTATION_RE, "/previous_annotation_id")
    report = inspect_domain_proposal(
        input_path=input_path,
        vault_root=vault_root,
        code_batch_id=code_batch_id,
    )

    def apply(snapshot, store, authority):
        _require_head_bound(report, authority)
        lineage_id = lineage_id_from_report(report)
        chain = store.chains.get(lineage_id)
        if chain:
            head_id = chain["annotation_order"][-1]
            if previous != head_id:
                _fail(
                    "DOMAIN_RECORD_PREVIOUS_MISMATCH",
                    "/previous_annotation_id",
                    "supply_previous",
                    {"expected": head_id},
                )
            head = store.annotations[head_id]
            if sha(canonicalize(report)) == head["report_sha256"]:
                _fail("DOMAIN_RECORD_UNCHANGED", "/report", "revise_annotation")
            if calendar(recorded_at) < calendar(head["recorded_at"]):
                _fail("DOMAIN_STORE_CHAIN_INVALID", "/recorded_at", "repair_input", {"reason": "timestamp_order"})
            if len(chain["annotation_order"]) >= MAX_PER_LINEAGE:
                _fail("DOMAIN_STORE_LIMIT", "/annotations", "reduce_store")
        else:
            if previous is not None:
                _fail("DOMAIN_RECORD_PREVIOUS_MISMATCH", "/previous_annotation_id", "omit_previous")
            if len(store.chains) >= MAX_LINEAGES:
                _fail("DOMAIN_STORE_LIMIT", "/heads", "reduce_store")
        record, raw = _build_annotation(
            lineage_id=lineage_id,
            previous=previous,
            recorded_by=recorded_by,
            recorded_at=recorded_at,
            report=report,
        )
        updated = _copy_store(store)
        updated.annotations[record["annotation_id"]] = record
        updated.annotation_raw[record["annotation_id"]] = raw
        if chain:
            updated.chains[lineage_id]["annotation_order"].append(record["annotation_id"])
        else:
            updated.chains[lineage_id] = {
                "annotation_order": [record["annotation_id"]],
                "review_order": [],
            }
        heads = derive_domain_heads(updated)
        heads_raw = canonicalize(heads)
        destination = DOMAIN_ROOT + "/annotations/" + lineage_id + "/" + record["annotation_id"] + ".json"
        staged = _stage_items(
            batch,
            [
                (
                    ("domain", "annotations", lineage_id, record["annotation_id"] + ".json"),
                    destination,
                    raw,
                ),
                (("domain", "heads.json"), DOMAIN_ROOT + "/heads.json", heads_raw),
            ],
        )
        return {
            "record": record,
            "heads": heads,
            "staged": staged,
            "publication": "unpublished",
            "next_action": "semantic_review_required",
        }

    return _with_store(vault_root, apply, authority_required=True)


def _load_decision(path):
    try:
        parsed = load_strict_json(
            Path(path),
            missing_code="DOMAIN_REVIEW_INVALID",
            unsafe_code="WORK_PATH_UNSAFE",
            invalid_code="DOMAIN_REVIEW_INVALID",
            changed_code="DOMAIN_STORE_CHANGED",
            max_bytes=MAX_RECORD_BYTES,
        )
    except SecureIOError as exc:
        code = exc.code
        if exc.details.get("reason") == "depth":
            code = "DOMAIN_STORE_LIMIT"
        next_action = "repeat_read" if code == "DOMAIN_STORE_CHANGED" else "repair_input"
        raise DomainStoreError(
            code,
            MESSAGES.get(code, exc.message),
            {"instance_pointer": "/decision", "next_action": next_action, **exc.details},
            exit_code=75 if code == "DOMAIN_STORE_CHANGED" else getattr(exc, "exit_code", 2),
        ) from exc
    if type(parsed) is not dict:
        _fail("DOMAIN_REVIEW_INVALID", "/decision", "repair_input", {"reason": "type"})
    try:
        decision = validate_document(parsed, DECISION_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "repair_input", code="DOMAIN_REVIEW_INVALID")
    _timestamp(decision["decided_at"], "/decided_at")
    _nonempty(decision["decided_by"], "/decided_by")
    _nonempty(decision["reason"], "/reason", limit=4096)
    return decision


def review_domain_annotation(*, decision_path, vault_root, batch_id):
    batch = _batch(batch_id, "/batch_id")
    decision = _load_decision(decision_path)

    def apply(snapshot, store, authority):
        lineage_id = decision["lineage_id"]
        chain = store.chains.get(lineage_id)
        if chain is None:
            _fail("DOMAIN_REVIEW_INVALID", "/lineage_id", "repair_review", {"reason": "unknown_lineage"})
        head_id = chain["annotation_order"][-1]
        if decision["annotation_id"] != head_id:
            _fail("DOMAIN_REVIEW_TARGET_NOT_HEAD", "/annotation_id", "review_head", {"expected": head_id})
        actual_sha = sha(store.annotation_raw[head_id])
        if decision["annotation_sha256"] != actual_sha:
            _fail("DOMAIN_REVIEW_BINDING_MISMATCH", "/annotation_sha256", "refresh_binding")
        tail = chain["review_order"][-1] if chain["review_order"] else None
        if decision["expected_previous_review_id"] != tail:
            _fail(
                "DOMAIN_REVIEW_STALE",
                "/expected_previous_review_id",
                "refresh_expectation",
                {"expected": tail},
            )
        annotation = store.annotations[head_id]
        _require_head_bound(annotation["report"], authority)
        if calendar(decision["decided_at"]) < calendar(annotation["recorded_at"]):
            _fail("DOMAIN_REVIEW_INVALID", "/decided_at", "repair_review", {"reason": "timestamp_order"})
        if tail is not None and calendar(decision["decided_at"]) < calendar(store.reviews[tail]["decided_at"]):
            _fail("DOMAIN_REVIEW_INVALID", "/decided_at", "repair_review", {"reason": "timestamp_order"})
        has_relation = "relation_review" in decision and decision["relation_review"] is not None
        if decision["decision"] == "accepted":
            if not has_relation:
                _fail("DOMAIN_REVIEW_INVALID", "/relation_review", "repair_review", {"reason": "required"})
            if not _officiality_ok(annotation["report"], decision["relation_review"]):
                _fail("DOMAIN_REVIEW_INVALID", "/relation_review", "repair_review", {"reason": "officiality"})
        elif has_relation:
            _fail("DOMAIN_REVIEW_INVALID", "/relation_review", "repair_review", {"reason": "forbidden"})
        if len(chain["review_order"]) >= MAX_PER_LINEAGE:
            _fail("DOMAIN_STORE_LIMIT", "/reviews", "reduce_store")
        record, raw = _build_review(
            lineage_id=lineage_id,
            annotation_id=head_id,
            annotation_sha256=actual_sha,
            previous=tail,
            decision=decision,
        )
        updated = _copy_store(store)
        updated.reviews[record["review_id"]] = record
        updated.review_raw[record["review_id"]] = raw
        updated.chains[lineage_id]["review_order"].append(record["review_id"])
        heads = derive_domain_heads(updated)
        heads_raw = canonicalize(heads)
        destination = DOMAIN_ROOT + "/reviews/" + lineage_id + "/" + record["review_id"] + ".json"
        staged = _stage_items(
            batch,
            [
                (
                    ("domain", "reviews", lineage_id, record["review_id"] + ".json"),
                    destination,
                    raw,
                ),
                (("domain", "heads.json"), DOMAIN_ROOT + "/heads.json", heads_raw),
            ],
        )
        next_action = (
            "publication_pending_later_slice" if decision["decision"] == "accepted" else "revise_annotation"
        )
        return {
            "record": record,
            "heads": heads,
            "staged": staged,
            "publication": "unpublished",
            "next_action": next_action,
            "canonical_official": False,
            "current_supported_typed_fact": False,
        }

    return _with_store(vault_root, apply, authority_required=True)


def status_domain_store(*, vault_root):
    def apply(snapshot, store, authority):
        heads = derive_domain_heads(store)
        lineages = []
        for lid in sorted(store.chains):
            chain = store.chains[lid]
            head = store.annotations[chain["annotation_order"][-1]]
            report = head["report"]
            claims = []
            stale_any = False
            for item in report["claim_annotations"]:
                freshness, reason = _claim_freshness(item, authority)
                if freshness == "stale":
                    stale_any = True
                claims.append(
                    {
                        "claim_id": item["claim_id"],
                        "claim_kind": item["claim_kind"],
                        "assessment": item["assessment"],
                        "freshness": freshness,
                        "stale_reason": reason,
                        "typed_fact_candidate": "not_supported",
                    }
                )
            current = heads["heads"][lid]
            if stale_any:
                typed_status = "stale"
            elif current["review_id"] is None:
                typed_status = "proposal_only"
            else:
                typed_status = "reviewed_" + current["review_decision"]
            for row in claims:
                if (
                    typed_status == "reviewed_accepted"
                    and row["assessment"] == "accepted"
                    and row["freshness"] == "head_bound"
                ):
                    row["typed_fact_candidate"] = "supported_candidate"
            lineages.append(
                {
                    "lineage_id": lid,
                    "paper_id": report["paper_id"],
                    "source_association_id": report["source_association"]["association_id"],
                    "repository": report["repository"],
                    "commit": report["commit"],
                    "annotation_count": len(chain["annotation_order"]),
                    "review_count": len(chain["review_order"]),
                    "typed_fact_status": typed_status,
                    "reviewed_officiality": current["reviewed_officiality"],
                    "claims": claims,
                }
            )
        return {
            "heads": heads,
            "lineages": lineages,
            "publication": "unpublished",
            "audit_coverage": "not_wired",
            "code_freshness": "not_checked",
            "canonical_official": False,
            "current_supported_typed_fact": False,
        }

    return _with_store(vault_root, apply)


def load_domain_store(vault_root):
    def apply(snapshot, store, authority):
        return store, derive_domain_heads(store), authority

    return _with_store(vault_root, apply)
