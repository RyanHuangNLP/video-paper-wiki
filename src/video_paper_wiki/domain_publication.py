"""Compile and inspect unpublished domain publication requests. Vault writes are forbidden."""

from __future__ import annotations

import json
import os
import re
import stat

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import (
    ANNOTATION_RE,
    ANNOTATION_SCHEMA,
    DOMAIN_ROOT,
    DomainStoreError,
    HEADS_SCHEMA,
    LINEAGE_RE,
    MAX_LINEAGES,
    MESSAGES as STORE_MESSAGES,
    REVIEW_RE,
    REVIEW_SCHEMA,
    annotation_id_from_record,
    derive_domain_heads,
    review_id_from_record,
    _batch,
    _copy_store,
    _officiality_ok,
    _require_head_bound,
    _validate_chains,
    _with_store,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.secure_io import (
    JSON_MAX_BYTES,
    SecureIOError,
    close_fd,
    dir_open_flags,
    parse_strict_json,
)
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import (
    CODE_WORK_PATH_UNSAFE,
    StagingError,
    resolve_checkout_root,
    stage_bytes,
    validate_batch_id,
)

REQUEST_SCHEMA = "video-paper-wiki.domain-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.domain-publication-inspection.v1"
COMPILE_COMMAND = "domain.compile"
INSPECT_COMMAND = "domain.publish-inspect"
DOMAIN_PREFIX = DOMAIN_ROOT + "/"
MAX_STAGED_RECORDS = 512
MAX_STAGED_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = JSON_MAX_BYTES
CONTENT_NAME_RE = re.compile(r"^[0-9a-f]{64}$")
MESSAGES = {
    "DOMAIN_COMPILE_INVALID": "domain compile input is invalid",
    "DOMAIN_COMPILE_LIMIT": "domain compile input exceeds a closed bound",
    "DOMAIN_COMPILE_EMPTY": "domain compile batch has no record files",
    "DOMAIN_COMPILE_ALREADY_PUBLISHED": "domain compile target already exists in the store",
    "DOMAIN_COMPILE_STALE": "domain compile staged heads do not match the current store",
    "DOMAIN_COMPILE_CHANGED": "domain compile input changed during read",
    "DOMAIN_PUBLICATION_INVALID": "domain publication request is invalid",
    "DOMAIN_PUBLICATION_CONTENT_MISMATCH": "domain publication content does not match the request",
    "DOMAIN_PUBLICATION_STALE": "domain publication request basis is stale",
    "DOMAIN_PUBLICATION_MISMATCH": "domain publication request does not match the recomputed write set",
}


class DomainPublicationError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


class _StagedDomain:
    def __init__(self):
        self.annotations = {}
        self.reviews = {}
        self.heads_doc = None
        self.heads_raw = None


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise DomainPublicationError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _map_schema(exc, code, next_action):
    pointer = exc.details.get("instance_pointer") or ""
    if exc.code in {"SOURCE_SEMANTICS_LIMIT", "TRANSACTION_LIMIT_EXCEEDED"}:
        if code.startswith("DOMAIN_COMPILE"):
            code = "DOMAIN_COMPILE_LIMIT"
            next_action = "reduce_batch"
        else:
            code = "DOMAIN_PUBLICATION_INVALID"
    raise DomainPublicationError(
        code,
        MESSAGES.get(code, MESSAGES["DOMAIN_COMPILE_INVALID"]),
        {"instance_pointer": pointer, "next_action": next_action, **exc.details},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _map_work(exc, pointer, *, invalid="DOMAIN_COMPILE_INVALID", changed="DOMAIN_COMPILE_CHANGED"):
    code = getattr(exc, "code", invalid)
    details = dict(getattr(exc, "details", {}) or {})
    path = details.get("path") or pointer
    if code in {"AUDIT_RACE", "SOURCE_CHANGED"} or getattr(exc, "exit_code", 2) == 75 and code in {
        "AUDIT_RACE",
        "SOURCE_CHANGED",
    }:
        _fail(
            changed,
            pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
            "repeat_read",
            dict(details),
            exit_code=75,
        )
    if code in {"RECEIPT_CHAIN_INVALID", "BLOB_LIMIT_EXCEEDED"}:
        limit = "DOMAIN_COMPILE_LIMIT" if invalid.startswith("DOMAIN_COMPILE") else invalid
        _fail(
            limit,
            pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
            "reduce_batch",
            dict(details),
        )
    if code == "WORK_PATH_UNSAFE":
        raise DomainPublicationError(
            code,
            getattr(exc, "message", code),
            {"instance_pointer": pointer, "next_action": "repair_input", **details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    _fail(
        invalid,
        pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
        "repair_input",
        {"prior_code": code, "path": path, **details},
        exit_code=getattr(exc, "exit_code", 2),
    )


def _stat_child(parent_fd, name):
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _list_names(fd, pointer, *, changed):
    try:
        return sorted(os.listdir(fd))
    except OSError:
        _fail(changed, pointer, "repeat_read", exit_code=75)


def _require_regular(st, relative, *, invalid, changed):
    pointer = "/" + relative
    if st is None:
        _fail(invalid, pointer, "repair_input", {"reason": "missing", "path": relative})
    if stat.S_ISLNK(st.st_mode):
        _fail(invalid, pointer, "repair_input", {"reason": "symlink", "path": relative})
    if not stat.S_ISREG(st.st_mode):
        _fail(invalid, pointer, "repair_input", {"reason": "entry_kind", "path": relative})
    if st.st_nlink != 1:
        _fail(invalid, pointer, "repair_input", {"reason": "hardlink", "path": relative})
    if st.st_size > MAX_RECORD_BYTES:
        limit = "DOMAIN_COMPILE_LIMIT" if invalid.startswith("DOMAIN_COMPILE") else invalid
        _fail(limit, pointer, "reduce_batch", {"path": relative, "size_bytes": st.st_size})


def _read_bytes(snapshot, relative, pointer, *, invalid, changed):
    try:
        raw = snapshot.read(relative, max_bytes=MAX_RECORD_BYTES)
    except ContractError as exc:
        _map_work(exc, pointer, invalid=invalid, changed=changed)
    except SecureIOError as exc:
        _map_work(exc, pointer, invalid=invalid, changed=changed)
    except OSError:
        _fail(changed, pointer, "repeat_read", {"path": relative}, exit_code=75)
    if len(raw) > MAX_RECORD_BYTES:
        limit = "DOMAIN_COMPILE_LIMIT" if invalid.startswith("DOMAIN_COMPILE") else invalid
        _fail(limit, pointer, "reduce_batch", {"path": relative, "size_bytes": len(raw)})
    return raw


def _parse_record(raw, schema, pointer, relative, *, invalid):
    try:
        doc = parse_strict_json(raw, invalid_code=invalid)
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "DOMAIN_COMPILE_LIMIT" if invalid.startswith("DOMAIN_COMPILE") and reason == "depth" else invalid
        next_action = "reduce_batch" if code.endswith("LIMIT") else "repair_input"
        _fail(code, pointer, next_action, {"path": relative, **exc.details})
    if type(doc) is not dict:
        _fail(invalid, pointer, "repair_input", {"reason": "type", "path": relative})
    try:
        validate_document(doc, schema)
    except ContractError as exc:
        _map_schema(exc, invalid, "repair_input")
    try:
        expected = canonicalize(doc)
    except CanonicalJsonError:
        _fail(invalid, pointer, "repair_input", {"reason": "canonical_bytes", "path": relative})
    if raw != expected:
        _fail(invalid, pointer, "repair_input", {"reason": "canonical_bytes", "path": relative})
    return doc


def _open_snapshot(path, pointer, *, invalid, changed):
    try:
        st = path.lstat()
    except FileNotFoundError:
        _fail(invalid, pointer, "repair_input", {"reason": "missing", "path": str(path.name)})
    except OSError:
        _fail(changed, pointer, "repeat_read", {"path": str(path.name)}, exit_code=75)
    if stat.S_ISLNK(st.st_mode):
        _fail(invalid, pointer, "repair_input", {"reason": "symlink", "path": str(path.name)})
    if not stat.S_ISDIR(st.st_mode):
        _fail(invalid, pointer, "repair_input", {"reason": "entry_kind", "path": str(path.name)})
    try:
        return _Snapshot(path)
    except ContractError as exc:
        _map_work(exc, pointer, invalid=invalid, changed=changed)


def _work_domain_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "domain"
    return _open_snapshot(
        path,
        "/domain",
        invalid="DOMAIN_COMPILE_INVALID",
        changed="DOMAIN_COMPILE_CHANGED",
    )


def _publication_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "domain-publication"
    return _open_snapshot(
        path,
        "/domain-publication",
        invalid="DOMAIN_PUBLICATION_INVALID",
        changed="DOMAIN_PUBLICATION_INVALID",
    )


def _scan_kind(snapshot, domain_fd, kind, lineage_re, file_re, schema, id_field, id_fn, bucket, counters):
    relative_kind = kind
    pointer_kind = "/" + kind
    st = _stat_child(domain_fd, kind)
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        _fail("DOMAIN_COMPILE_INVALID", pointer_kind, "repair_input", {"reason": "symlink", "path": relative_kind})
    if not stat.S_ISDIR(st.st_mode):
        _fail("DOMAIN_COMPILE_INVALID", pointer_kind, "repair_input", {"reason": "entry_kind", "path": relative_kind})
    kind_fd = os.open(kind, dir_open_flags(), dir_fd=domain_fd)
    try:
        snapshot.directories.setdefault(relative_kind, os.fstat(kind_fd))
        lineages = _list_names(kind_fd, pointer_kind, changed="DOMAIN_COMPILE_CHANGED")
        if not lineages:
            return
        for lineage_name in lineages:
            lineage_rel = relative_kind + "/" + lineage_name
            lst = _stat_child(kind_fd, lineage_name)
            if lst is None:
                _fail("DOMAIN_COMPILE_CHANGED", "/" + lineage_rel, "repeat_read", exit_code=75)
            if stat.S_ISLNK(lst.st_mode):
                _fail(
                    "DOMAIN_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "symlink", "path": lineage_rel},
                )
            if not stat.S_ISDIR(lst.st_mode):
                _fail(
                    "DOMAIN_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "entry_kind", "path": lineage_rel},
                )
            if lineage_re.fullmatch(lineage_name) is None:
                _fail(
                    "DOMAIN_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "unknown_entry", "path": lineage_rel},
                )
            child_fd = os.open(lineage_name, dir_open_flags(), dir_fd=kind_fd)
            try:
                snapshot.directories.setdefault(lineage_rel, os.fstat(child_fd))
                files = _list_names(child_fd, "/" + lineage_rel, changed="DOMAIN_COMPILE_CHANGED")
                if not files:
                    _fail(
                        "DOMAIN_COMPILE_INVALID",
                        "/" + lineage_rel,
                        "repair_input",
                        {"reason": "empty_lineage", "path": lineage_rel},
                    )
                for filename in files:
                    file_rel = lineage_rel + "/" + filename
                    fst = _stat_child(child_fd, filename)
                    _require_regular(
                        fst,
                        file_rel,
                        invalid="DOMAIN_COMPILE_INVALID",
                        changed="DOMAIN_COMPILE_CHANGED",
                    )
                    counters["files"] += 1
                    counters["bytes"] += fst.st_size
                    if counters["files"] > MAX_STAGED_RECORDS or counters["bytes"] > MAX_STAGED_BYTES:
                        _fail(
                            "DOMAIN_COMPILE_LIMIT",
                            "/" + file_rel,
                            "reduce_batch",
                            {"path": file_rel},
                        )
                    stem, sep, ext = filename.partition(".")
                    if sep != "." or ext != "json" or file_re.fullmatch(stem) is None:
                        _fail(
                            "DOMAIN_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "unknown_entry", "path": file_rel},
                        )
                    raw = _read_bytes(
                        snapshot,
                        file_rel,
                        "/" + file_rel,
                        invalid="DOMAIN_COMPILE_INVALID",
                        changed="DOMAIN_COMPILE_CHANGED",
                    )
                    doc = _parse_record(
                        raw,
                        schema,
                        "/" + file_rel,
                        file_rel,
                        invalid="DOMAIN_COMPILE_INVALID",
                    )
                    identity = doc[id_field]
                    if identity != stem:
                        _fail(
                            "DOMAIN_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    if doc["lineage_id"] != lineage_name:
                        _fail(
                            "DOMAIN_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    expected_id = id_fn(doc)
                    if identity != expected_id:
                        _fail(
                            "DOMAIN_COMPILE_INVALID",
                            _pointer(*(file_rel.split("/"))) + "/" + id_field,
                            "repair_input",
                            {"reason": "identity", "path": file_rel},
                        )
                    if identity in bucket:
                        _fail(
                            "DOMAIN_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "duplicate_id", "path": file_rel},
                        )
                    bucket[identity] = (doc, raw, file_rel)
            finally:
                close_fd(child_fd)
    finally:
        close_fd(kind_fd)


def _load_staged_domain(snapshot):
    staged = _StagedDomain()
    names = _list_names(snapshot.root_fd, "/domain", changed="DOMAIN_COMPILE_CHANGED")
    allowed = {"annotations", "reviews", "heads.json"}
    extra = [name for name in names if name not in allowed]
    if extra:
        _fail(
            "DOMAIN_COMPILE_INVALID",
            _pointer("domain", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "domain/" + extra[0]},
        )
    if "heads.json" not in names:
        _fail(
            "DOMAIN_COMPILE_INVALID",
            "/domain/heads.json",
            "repair_input",
            {"reason": "missing", "path": "domain/heads.json"},
        )
    counters = {"files": 0, "bytes": 0}
    if "annotations" in names:
        _scan_kind(
            snapshot,
            snapshot.root_fd,
            "annotations",
            LINEAGE_RE,
            ANNOTATION_RE,
            ANNOTATION_SCHEMA,
            "annotation_id",
            annotation_id_from_record,
            staged.annotations,
            counters,
        )
    if "reviews" in names:
        _scan_kind(
            snapshot,
            snapshot.root_fd,
            "reviews",
            LINEAGE_RE,
            REVIEW_RE,
            REVIEW_SCHEMA,
            "review_id",
            review_id_from_record,
            staged.reviews,
            counters,
        )
    st = _stat_child(snapshot.root_fd, "heads.json")
    _require_regular(st, "heads.json", invalid="DOMAIN_COMPILE_INVALID", changed="DOMAIN_COMPILE_CHANGED")
    counters["bytes"] += st.st_size
    if counters["bytes"] > MAX_STAGED_BYTES:
        _fail("DOMAIN_COMPILE_LIMIT", "/domain/heads.json", "reduce_batch", {"path": "domain/heads.json"})
    heads_raw = _read_bytes(
        snapshot,
        "heads.json",
        "/domain/heads.json",
        invalid="DOMAIN_COMPILE_INVALID",
        changed="DOMAIN_COMPILE_CHANGED",
    )
    heads_doc = _parse_record(
        heads_raw,
        HEADS_SCHEMA,
        "/domain/heads.json",
        "domain/heads.json",
        invalid="DOMAIN_COMPILE_INVALID",
    )
    staged.heads_doc = heads_doc
    staged.heads_raw = heads_raw
    if not staged.annotations and not staged.reviews:
        _fail("DOMAIN_COMPILE_EMPTY", "/domain", "record_or_review", {"path": "domain"})
    return staged


def _inventory_rows(store):
    rows = []
    for doc in store.annotations.values():
        path = DOMAIN_PREFIX + "annotations/" + doc["lineage_id"] + "/" + doc["annotation_id"] + ".json"
        raw = store.annotation_raw[doc["annotation_id"]]
        rows.append([path, sha(raw), len(raw)])
    for doc in store.reviews.values():
        path = DOMAIN_PREFIX + "reviews/" + doc["lineage_id"] + "/" + doc["review_id"] + ".json"
        raw = store.review_raw[doc["review_id"]]
        rows.append([path, sha(raw), len(raw)])
    if store.heads_raw is not None:
        rows.append([DOMAIN_ROOT + "/heads.json", sha(store.heads_raw), len(store.heads_raw)])
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return rows


def _inventory_digest(store):
    return sha(canonicalize(_inventory_rows(store)))


def _basis(snapshot, store, authority):
    ledger_raw = snapshot.read(CLAIM_LEDGER, max_bytes=MAX_RECORD_BYTES * 8)
    heads_raw = authority.get("heads_raw")
    if heads_raw is None:
        heads_raw = snapshot.read(ASSESSMENT_HEADS, max_bytes=MAX_RECORD_BYTES)
    return {
        "domain_store_inventory_sha256": _inventory_digest(store),
        "claim_ledger_sha256": sha(ledger_raw),
        "assessment_heads_sha256": sha(heads_raw),
    }


def _payload(path, mode, before, raw):
    digest = sha(raw)
    return {
        "path": path,
        "mode": mode,
        "before_sha256": before,
        "after_sha256": digest,
        "size_bytes": len(raw),
        "content_file": "domain-publication/content/" + digest,
    }


def _destination(rel):
    return DOMAIN_PREFIX + rel


def _build_request(snapshot, store, authority, batch, staged):
    for _aid, (doc, _raw, rel) in staged.annotations.items():
        dest = _destination(rel)
        if doc["annotation_id"] in store.annotations:
            _fail(
                "DOMAIN_COMPILE_ALREADY_PUBLISHED",
                _pointer(*(dest.split("/"))),
                "discard_batch",
                {"path": dest},
            )
    for _rid, (doc, _raw, rel) in staged.reviews.items():
        dest = _destination(rel)
        if doc["review_id"] in store.reviews:
            _fail(
                "DOMAIN_COMPILE_ALREADY_PUBLISHED",
                _pointer(*(dest.split("/"))),
                "discard_batch",
                {"path": dest},
            )
    prospective = _copy_store(store)
    for aid, (doc, raw, _rel) in staged.annotations.items():
        prospective.annotations[aid] = doc
        prospective.annotation_raw[aid] = raw
    for rid, (doc, raw, _rel) in staged.reviews.items():
        prospective.reviews[rid] = doc
        prospective.review_raw[rid] = raw
    prospective.chains = {}
    prospective.heads_raw = staged.heads_raw
    prospective.empty = False
    _validate_chains(prospective)
    if len(prospective.chains) > MAX_LINEAGES:
        raise DomainStoreError(
            "DOMAIN_STORE_LIMIT",
            STORE_MESSAGES["DOMAIN_STORE_LIMIT"],
            {"instance_pointer": "/wiki/meta/domain", "next_action": "reduce_store", "reason": "lineages"},
        )
    derived = derive_domain_heads(prospective)
    derived_raw = canonicalize(derived)
    if staged.heads_raw != derived_raw:
        _fail(
            "DOMAIN_COMPILE_STALE",
            "/domain/heads.json",
            "re_record_or_re_review",
            {"path": "domain/heads.json"},
            exit_code=75,
        )
    touched = sorted(
        {doc["lineage_id"] for doc, _raw, _rel in staged.annotations.values()}
        | {doc["lineage_id"] for doc, _raw, _rel in staged.reviews.values()}
    )
    for lid in touched:
        chain = prospective.chains[lid]
        head = prospective.annotations[chain["annotation_order"][-1]]
        _require_head_bound(head["report"], authority)
    for rid, (doc, _raw, _rel) in staged.reviews.items():
        if doc["decision"] != "accepted":
            continue
        annotation = prospective.annotations[doc["annotation_id"]]
        if not _officiality_ok(annotation["report"], doc["relation_review"]):
            raise DomainStoreError(
                "DOMAIN_REVIEW_INVALID",
                STORE_MESSAGES["DOMAIN_REVIEW_INVALID"],
                {
                    "instance_pointer": "/review_id/" + rid + "/relation_review",
                    "next_action": "repair_review",
                    "reason": "officiality",
                },
            )
    payloads = []
    content = {}
    for _aid, (_doc, raw, rel) in staged.annotations.items():
        item = _payload(_destination(rel), "create", None, raw)
        payloads.append(item)
        content[item["after_sha256"]] = raw
    for _rid, (_doc, raw, rel) in staged.reviews.items():
        item = _payload(_destination(rel), "create", None, raw)
        payloads.append(item)
        content[item["after_sha256"]] = raw
    if store.heads_raw is None:
        heads_mode = "create"
        heads_before = None
    else:
        heads_mode = "replace"
        heads_before = sha(store.heads_raw)
    heads_item = _payload(DOMAIN_ROOT + "/heads.json", heads_mode, heads_before, staged.heads_raw)
    payloads.append(heads_item)
    content[heads_item["after_sha256"]] = staged.heads_raw
    payloads.sort(key=lambda item: item["path"].encode("utf-8"))
    basis = _basis(snapshot, store, authority)
    prospective_inventory = _inventory_digest(prospective)
    request = {
        "schema": REQUEST_SCHEMA,
        "batch_id": batch,
        "kind": "domain",
        "basis": basis,
        "prospective_inventory_sha256": prospective_inventory,
        "touched_lineages": touched,
        "payloads": payloads,
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_domain_publication",
    }
    try:
        request_raw = canonicalize(request)
        sealed = json.loads(request_raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_COMPILE_INVALID", "", "repair_input", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, REQUEST_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "DOMAIN_COMPILE_INVALID", "repair_input")
    if len(request_raw) > MAX_RECORD_BYTES:
        _fail("DOMAIN_COMPILE_LIMIT", "/request", "reduce_batch", {"size_bytes": len(request_raw)})
    changed_paths = [item["path"] for item in sealed["payloads"]]
    data = {
        "state": "domain_publication_prepared",
        "batch_id": batch,
        "basis": sealed["basis"],
        "prospective_inventory_sha256": sealed["prospective_inventory_sha256"],
        "request_path": ".work/" + batch + "/domain-publication/request.json",
        "request_sha256": sha(request_raw),
        "touched_lineages": list(sealed["touched_lineages"]),
        "changed_paths": changed_paths,
        "payload_count": len(sealed["payloads"]),
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_domain_publication",
    }
    return {"request": sealed, "request_raw": request_raw, "content": content, "data": data}


def _stage_publication(batch, built):
    stage_bytes(batch_id=batch, relative=("domain-publication", "request.json"), data=built["request_raw"])
    written = set()
    for item in built["request"]["payloads"]:
        digest = item["after_sha256"]
        if digest in written:
            continue
        written.add(digest)
        stage_bytes(
            batch_id=batch,
            relative=("domain-publication", "content", digest),
            data=built["content"][digest],
        )


def _verify_work(snapshot, *, changed):
    try:
        snapshot.verify()
    except ContractError as exc:
        _map_work(exc, "/domain", invalid=changed, changed=changed)


def compile_domain_publication(*, vault_root, batch_id):
    batch = _batch(batch_id, "/batch_id")

    def apply(snapshot, store, authority):
        work = _work_domain_snapshot(batch)
        try:
            staged = _load_staged_domain(work)
            built = _build_request(snapshot, store, authority, batch, staged)
            _verify_work(work, changed="DOMAIN_COMPILE_CHANGED")
            _stage_publication(batch, built)
            _verify_work(work, changed="DOMAIN_COMPILE_CHANGED")
            return built["data"]
        finally:
            work.close()

    return _with_store(vault_root, apply, authority_required=True)


def _prepared_slot(value):
    try:
        path = checked_path(value)
    except ContractError as exc:
        if getattr(exc, "code", None) == "WORK_PATH_UNSAFE":
            raise StagingError(CODE_WORK_PATH_UNSAFE, exc.message, dict(exc.details)) from exc
        raise
    try:
        rel = path.relative_to(resolve_checkout_root() / ".work")
        parts = rel.parts
        if len(parts) != 3:
            raise ValueError
        batch = validate_batch_id(parts[0])
        if parts != (batch, "domain-publication", "request.json"):
            raise ValueError
        return path, batch
    except (ValueError, StagingError) as exc:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "prepared input must use the fixed domain publication slot",
            {"path": os.fspath(value)},
        ) from exc


def _domain_suffix(path):
    if type(path) is not str or not path.startswith(DOMAIN_PREFIX):
        _fail("DOMAIN_PUBLICATION_INVALID", "/payloads", "repair_input", {"path": path})
    return path[len(DOMAIN_PREFIX) :]


def _staged_from_content(request, content):
    staged = _StagedDomain()
    for index, item in enumerate(request["payloads"]):
        pointer = "/payloads/" + str(index)
        digest = item["after_sha256"]
        raw = content.get(digest)
        if raw is None:
            _fail("DOMAIN_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        if sha(raw) != digest or len(raw) != item["size_bytes"]:
            _fail("DOMAIN_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        suffix = _domain_suffix(item["path"])
        if suffix == "heads.json":
            doc = _parse_record(raw, HEADS_SCHEMA, pointer, item["path"], invalid="DOMAIN_PUBLICATION_INVALID")
            if staged.heads_raw is not None:
                _fail("DOMAIN_PUBLICATION_INVALID", pointer, "repair_input", {"reason": "duplicate_heads"})
            staged.heads_doc = doc
            staged.heads_raw = raw
            continue
        if suffix.startswith("annotations/"):
            doc = _parse_record(
                raw, ANNOTATION_SCHEMA, pointer, item["path"], invalid="DOMAIN_PUBLICATION_INVALID"
            )
            expected = "annotations/" + doc["lineage_id"] + "/" + doc["annotation_id"] + ".json"
            if suffix != expected or annotation_id_from_record(doc) != doc["annotation_id"]:
                _fail("DOMAIN_PUBLICATION_MISMATCH", pointer, "recompile", {"path": item["path"]})
            staged.annotations[doc["annotation_id"]] = (doc, raw, suffix)
            continue
        if suffix.startswith("reviews/"):
            doc = _parse_record(raw, REVIEW_SCHEMA, pointer, item["path"], invalid="DOMAIN_PUBLICATION_INVALID")
            expected = "reviews/" + doc["lineage_id"] + "/" + doc["review_id"] + ".json"
            if suffix != expected or review_id_from_record(doc) != doc["review_id"]:
                _fail("DOMAIN_PUBLICATION_MISMATCH", pointer, "recompile", {"path": item["path"]})
            staged.reviews[doc["review_id"]] = (doc, raw, suffix)
            continue
        _fail("DOMAIN_PUBLICATION_INVALID", pointer, "repair_input", {"path": item["path"]})
    if staged.heads_raw is None or (not staged.annotations and not staged.reviews):
        _fail("DOMAIN_PUBLICATION_INVALID", "/payloads", "repair_input", {"reason": "incomplete"})
    return staged


def _load_publication(snapshot, batch):
    names = _list_names(snapshot.root_fd, "/domain-publication", changed="DOMAIN_PUBLICATION_INVALID")
    extra = [name for name in names if name not in {"request.json", "content"}]
    if extra:
        _fail(
            "DOMAIN_PUBLICATION_INVALID",
            _pointer("domain-publication", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "domain-publication/" + extra[0]},
        )
    if "request.json" not in names:
        _fail(
            "DOMAIN_PUBLICATION_INVALID",
            "/domain-publication/request.json",
            "repair_input",
            {"reason": "missing", "path": "domain-publication/request.json"},
        )
    st = _stat_child(snapshot.root_fd, "request.json")
    _require_regular(
        st,
        "domain-publication/request.json",
        invalid="DOMAIN_PUBLICATION_INVALID",
        changed="DOMAIN_PUBLICATION_INVALID",
    )
    request_raw = _read_bytes(
        snapshot,
        "request.json",
        "/domain-publication/request.json",
        invalid="DOMAIN_PUBLICATION_INVALID",
        changed="DOMAIN_PUBLICATION_INVALID",
    )
    request = _parse_record(
        request_raw,
        REQUEST_SCHEMA,
        "/domain-publication/request.json",
        "domain-publication/request.json",
        invalid="DOMAIN_PUBLICATION_INVALID",
    )
    if request["batch_id"] != batch:
        _fail(
            "DOMAIN_PUBLICATION_INVALID",
            "/batch_id",
            "repair_input",
            {"reason": "batch_id", "path": "domain-publication/request.json"},
        )
    if "content" not in names:
        _fail(
            "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
            "/domain-publication/content",
            "recompile",
            {"path": "domain-publication/content"},
        )
    cst = _stat_child(snapshot.root_fd, "content")
    if cst is None:
        _fail(
            "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
            "/domain-publication/content",
            "recompile",
            {"path": "domain-publication/content"},
        )
    if stat.S_ISLNK(cst.st_mode) or not stat.S_ISDIR(cst.st_mode):
        _fail(
            "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
            "/domain-publication/content",
            "recompile",
            {"reason": "entry_kind", "path": "domain-publication/content"},
        )
    content_fd = os.open("content", dir_open_flags(), dir_fd=snapshot.root_fd)
    try:
        snapshot.directories.setdefault("content", os.fstat(content_fd))
        content_names = _list_names(
            content_fd, "/domain-publication/content", changed="DOMAIN_PUBLICATION_INVALID"
        )
        expected = {item["after_sha256"] for item in request["payloads"]}
        if set(content_names) != expected:
            _fail(
                "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
                "/domain-publication/content",
                "recompile",
                {"path": "domain-publication/content"},
            )
        content = {}
        for name in content_names:
            relative = "content/" + name
            pointer = "/domain-publication/" + relative
            if CONTENT_NAME_RE.fullmatch(name) is None:
                _fail("DOMAIN_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            fst = _stat_child(content_fd, name)
            _require_regular(
                fst,
                "domain-publication/" + relative,
                invalid="DOMAIN_PUBLICATION_CONTENT_MISMATCH",
                changed="DOMAIN_PUBLICATION_INVALID",
            )
            raw = _read_bytes(
                snapshot,
                relative,
                pointer,
                invalid="DOMAIN_PUBLICATION_CONTENT_MISMATCH",
                changed="DOMAIN_PUBLICATION_INVALID",
            )
            if sha(raw) != name:
                _fail("DOMAIN_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            content[name] = raw
        for index, item in enumerate(request["payloads"]):
            raw = content[item["after_sha256"]]
            if sha(raw) != item["after_sha256"] or len(raw) != item["size_bytes"]:
                _fail(
                    "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index),
                    "recompile",
                    {"path": item["content_file"]},
                )
            expected_file = "domain-publication/content/" + item["after_sha256"]
            if item["content_file"] != expected_file:
                _fail(
                    "DOMAIN_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index) + "/content_file",
                    "recompile",
                    {"path": item["content_file"]},
                )
        return request, request_raw, content
    finally:
        close_fd(content_fd)


def inspect_domain_publication(*, prepared, vault_root):
    _path, batch = _prepared_slot(prepared)

    def apply(snapshot, store, authority):
        pub = _publication_snapshot(batch)
        try:
            request, request_raw, content = _load_publication(pub, batch)
            current_basis = _basis(snapshot, store, authority)
            if current_basis != request["basis"]:
                _fail("DOMAIN_PUBLICATION_STALE", "/basis", "recompile", exit_code=75)
            staged = _staged_from_content(request, content)
            rebuilt = _build_request(snapshot, store, authority, batch, staged)
            if (
                rebuilt["request"]["payloads"] != request["payloads"]
                or rebuilt["request"]["touched_lineages"] != request["touched_lineages"]
                or rebuilt["request"]["prospective_inventory_sha256"] != request["prospective_inventory_sha256"]
            ):
                _fail("DOMAIN_PUBLICATION_MISMATCH", "/payloads", "recompile")
            inspection = {
                "schema": INSPECTION_SCHEMA,
                "batch_id": batch,
                "request_sha256": sha(request_raw),
                "request": request,
                "basis_verified": True,
                "content_verified": True,
                "publication": "unpublished",
                "applied": False,
                "receipt_backed": False,
                "audit_coverage": "not_wired",
                "backup_coverage": "not_wired",
                "transaction_authority": "not_wired",
                "canonical_official": False,
                "current_supported_typed_fact": False,
                "next_action": "apply_requires_later_slice",
            }
            try:
                validate_document(inspection, INSPECTION_SCHEMA)
            except ContractError as exc:
                _map_schema(exc, "DOMAIN_PUBLICATION_INVALID", "repair_input")
            try:
                pub.verify()
            except ContractError as exc:
                _map_work(
                    exc,
                    "/domain-publication",
                    invalid="DOMAIN_PUBLICATION_INVALID",
                    changed="DOMAIN_PUBLICATION_INVALID",
                )
            return inspection
        finally:
            pub.close()

    return _with_store(vault_root, apply, authority_required=True)
