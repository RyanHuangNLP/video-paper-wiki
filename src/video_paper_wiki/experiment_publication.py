"""Compile and inspect unpublished experiment publication payloads. Vault writes are forbidden."""

from __future__ import annotations

import json
import os
import stat

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_publication import (
    CONTENT_NAME_RE,
    MAX_STAGED_BYTES,
    MAX_STAGED_RECORDS,
    _basis,
)
from video_paper_wiki.domain_store import _batch, _with_store
from video_paper_wiki.experiment_store import (
    CONDITION_RE,
    EXPERIMENT_ROOT,
    HEADS_SCHEMA,
    RECORD_RE,
    RECORD_SCHEMA,
    ExperimentStoreError,
    _bind_sources,
    _byte_sort,
    _check_record_shape,
    _check_source_digest,
    _copy_experiment_store,
    _load_experiment_store,
    _require_association,
    _require_claims,
    _require_code_binding,
    _validate_chains,
    condition_id_from_record,
    content_sha256_from_record,
    derive_experiment_heads,
    experiment_inventory_digest,
    record_id_from_record,
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
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import (
    CODE_STAGING_CONFLICT,
    CODE_WORK_PATH_UNSAFE,
    StagingError,
    resolve_checkout_root,
    stage_bytes,
    validate_batch_id,
)

REQUEST_SCHEMA = "video-paper-wiki.experiment-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.experiment-publication-inspection.v1"
COMPILE_COMMAND = "experiments.compile"
INSPECT_COMMAND = "experiments.publish-inspect"
EXPERIMENT_PREFIX = EXPERIMENT_ROOT + "/"
MAX_RECORD_BYTES = JSON_MAX_BYTES
MESSAGES = {
    "EXPERIMENT_COMPILE_INVALID": "experiment compile input is invalid",
    "EXPERIMENT_COMPILE_LIMIT": "experiment compile input exceeds a closed bound",
    "EXPERIMENT_COMPILE_EMPTY": "experiment compile batch has no record files",
    "EXPERIMENT_COMPILE_ALREADY_PUBLISHED": "experiment compile target already exists in the store",
    "EXPERIMENT_COMPILE_STALE": "experiment compile staged heads do not match the current store",
    "EXPERIMENT_COMPILE_CHANGED": "experiment compile input changed during read",
    "EXPERIMENT_PUBLICATION_INVALID": "experiment publication request is invalid",
    "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH": "experiment publication content does not match the request",
    "EXPERIMENT_PUBLICATION_STALE": "experiment publication request basis is stale",
    "EXPERIMENT_PUBLICATION_MISMATCH": "experiment publication request does not match the recomputed write set",
}


class ExperimentPublicationError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


class _StagedExperiments:
    def __init__(self):
        self.records = {}
        self.heads_doc = None
        self.heads_raw = None


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise ExperimentPublicationError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _map_schema(exc, code, next_action):
    pointer = exc.details.get("instance_pointer") or ""
    if exc.code in {"SOURCE_SEMANTICS_LIMIT", "TRANSACTION_LIMIT_EXCEEDED"}:
        if code.startswith("EXPERIMENT_COMPILE"):
            code = "EXPERIMENT_COMPILE_LIMIT"
            next_action = "reduce_batch"
        else:
            code = "EXPERIMENT_PUBLICATION_INVALID"
    raise ExperimentPublicationError(
        code,
        MESSAGES.get(code, MESSAGES["EXPERIMENT_COMPILE_INVALID"]),
        {"instance_pointer": pointer, "next_action": next_action, **exc.details},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _map_work(exc, pointer, *, invalid="EXPERIMENT_COMPILE_INVALID", changed="EXPERIMENT_COMPILE_CHANGED"):
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
        limit = "EXPERIMENT_COMPILE_LIMIT" if invalid.startswith("EXPERIMENT_COMPILE") else invalid
        _fail(
            limit,
            pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
            "reduce_batch",
            dict(details),
        )
    if code == "WORK_PATH_UNSAFE":
        raise ExperimentPublicationError(
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
        limit = "EXPERIMENT_COMPILE_LIMIT" if invalid.startswith("EXPERIMENT_COMPILE") else invalid
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
        limit = "EXPERIMENT_COMPILE_LIMIT" if invalid.startswith("EXPERIMENT_COMPILE") else invalid
        _fail(limit, pointer, "reduce_batch", {"path": relative, "size_bytes": len(raw)})
    return raw


def _parse_record(raw, schema, pointer, relative, *, invalid):
    try:
        doc = parse_strict_json(raw, invalid_code=invalid)
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "EXPERIMENT_COMPILE_LIMIT" if invalid.startswith("EXPERIMENT_COMPILE") and reason == "depth" else invalid
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


def _work_experiment_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "experiments"
    return _open_snapshot(
        path,
        "/experiments",
        invalid="EXPERIMENT_COMPILE_INVALID",
        changed="EXPERIMENT_COMPILE_CHANGED",
    )


def _publication_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "experiment-publication"
    return _open_snapshot(
        path,
        "/experiment-publication",
        invalid="EXPERIMENT_PUBLICATION_INVALID",
        changed="EXPERIMENT_PUBLICATION_INVALID",
    )


def _scan_records(snapshot, exp_fd, staged, counters):
    relative_kind = "records"
    pointer_kind = "/records"
    st = _stat_child(exp_fd, "records")
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        _fail("EXPERIMENT_COMPILE_INVALID", pointer_kind, "repair_input", {"reason": "symlink", "path": relative_kind})
    if not stat.S_ISDIR(st.st_mode):
        _fail("EXPERIMENT_COMPILE_INVALID", pointer_kind, "repair_input", {"reason": "entry_kind", "path": relative_kind})
    kind_fd = os.open("records", dir_open_flags(), dir_fd=exp_fd)
    try:
        snapshot.directories.setdefault(relative_kind, os.fstat(kind_fd))
        conditions = _list_names(kind_fd, pointer_kind, changed="EXPERIMENT_COMPILE_CHANGED")
        if not conditions:
            return
        for condition_name in conditions:
            lineage_rel = relative_kind + "/" + condition_name
            lst = _stat_child(kind_fd, condition_name)
            if lst is None:
                _fail("EXPERIMENT_COMPILE_CHANGED", "/" + lineage_rel, "repeat_read", exit_code=75)
            if stat.S_ISLNK(lst.st_mode):
                _fail(
                    "EXPERIMENT_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "symlink", "path": lineage_rel},
                )
            if not stat.S_ISDIR(lst.st_mode):
                _fail(
                    "EXPERIMENT_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "entry_kind", "path": lineage_rel},
                )
            if CONDITION_RE.fullmatch(condition_name) is None:
                _fail(
                    "EXPERIMENT_COMPILE_INVALID",
                    "/" + lineage_rel,
                    "repair_input",
                    {"reason": "unknown_entry", "path": lineage_rel},
                )
            child_fd = os.open(condition_name, dir_open_flags(), dir_fd=kind_fd)
            try:
                snapshot.directories.setdefault(lineage_rel, os.fstat(child_fd))
                files = _list_names(child_fd, "/" + lineage_rel, changed="EXPERIMENT_COMPILE_CHANGED")
                if not files:
                    _fail(
                        "EXPERIMENT_COMPILE_INVALID",
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
                        invalid="EXPERIMENT_COMPILE_INVALID",
                        changed="EXPERIMENT_COMPILE_CHANGED",
                    )
                    counters["files"] += 1
                    counters["bytes"] += fst.st_size
                    if counters["files"] > MAX_STAGED_RECORDS or counters["bytes"] > MAX_STAGED_BYTES:
                        _fail(
                            "EXPERIMENT_COMPILE_LIMIT",
                            "/" + file_rel,
                            "reduce_batch",
                            {"path": file_rel},
                        )
                    stem, sep, ext = filename.partition(".")
                    if sep != "." or ext != "json" or RECORD_RE.fullmatch(stem) is None:
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "unknown_entry", "path": file_rel},
                        )
                    raw = _read_bytes(
                        snapshot,
                        file_rel,
                        "/" + file_rel,
                        invalid="EXPERIMENT_COMPILE_INVALID",
                        changed="EXPERIMENT_COMPILE_CHANGED",
                    )
                    doc = _parse_record(
                        raw,
                        RECORD_SCHEMA,
                        "/" + file_rel,
                        file_rel,
                        invalid="EXPERIMENT_COMPILE_INVALID",
                    )
                    if doc["record_id"] != stem:
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    if doc["condition_id"] != condition_name:
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    if doc["record_id"] != record_id_from_record(doc):
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            _pointer(*(file_rel.split("/"))) + "/record_id",
                            "repair_input",
                            {"reason": "identity", "path": file_rel},
                        )
                    if doc["condition_id"] != condition_id_from_record(doc):
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            _pointer(*(file_rel.split("/"))) + "/condition_id",
                            "repair_input",
                            {"reason": "identity", "path": file_rel},
                        )
                    if doc["content_sha256"] != content_sha256_from_record(doc):
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            _pointer(*(file_rel.split("/"))) + "/content_sha256",
                            "repair_input",
                            {"reason": "content_sha256", "path": file_rel},
                        )
                    _check_record_shape(doc)
                    if doc["record_id"] in staged.records:
                        _fail(
                            "EXPERIMENT_COMPILE_INVALID",
                            "/" + file_rel,
                            "repair_input",
                            {"reason": "duplicate_id", "path": file_rel},
                        )
                    staged.records[doc["record_id"]] = (doc, raw, file_rel)
            finally:
                close_fd(child_fd)
    finally:
        close_fd(kind_fd)


def _load_staged_experiments(snapshot):
    staged = _StagedExperiments()
    names = _list_names(snapshot.root_fd, "/experiments", changed="EXPERIMENT_COMPILE_CHANGED")
    allowed = {"records", "heads.json"}
    extra = [name for name in names if name not in allowed]
    if extra:
        _fail(
            "EXPERIMENT_COMPILE_INVALID",
            _pointer("experiments", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "experiments/" + extra[0]},
        )
    if "heads.json" not in names:
        _fail(
            "EXPERIMENT_COMPILE_INVALID",
            "/experiments/heads.json",
            "repair_input",
            {"reason": "missing", "path": "experiments/heads.json"},
        )
    counters = {"files": 0, "bytes": 0}
    if "records" in names:
        _scan_records(snapshot, snapshot.root_fd, staged, counters)
    st = _stat_child(snapshot.root_fd, "heads.json")
    _require_regular(st, "heads.json", invalid="EXPERIMENT_COMPILE_INVALID", changed="EXPERIMENT_COMPILE_CHANGED")
    counters["bytes"] += st.st_size
    if counters["bytes"] > MAX_STAGED_BYTES:
        _fail("EXPERIMENT_COMPILE_LIMIT", "/experiments/heads.json", "reduce_batch", {"path": "experiments/heads.json"})
    heads_raw = _read_bytes(
        snapshot,
        "heads.json",
        "/experiments/heads.json",
        invalid="EXPERIMENT_COMPILE_INVALID",
        changed="EXPERIMENT_COMPILE_CHANGED",
    )
    heads_doc = _parse_record(
        heads_raw,
        HEADS_SCHEMA,
        "/experiments/heads.json",
        "experiments/heads.json",
        invalid="EXPERIMENT_COMPILE_INVALID",
    )
    staged.heads_doc = heads_doc
    staged.heads_raw = heads_raw
    if not staged.records:
        _fail("EXPERIMENT_COMPILE_EMPTY", "/experiments", "record_condition", {"path": "experiments"})
    return staged


def _inventory_rows(store):
    rows = []
    for doc in store.records.values():
        path = EXPERIMENT_PREFIX + "records/" + doc["condition_id"] + "/" + doc["record_id"] + ".json"
        raw = store.record_raw[doc["record_id"]]
        rows.append([path, sha(raw), len(raw)])
    if store.heads_raw is not None:
        rows.append([EXPERIMENT_ROOT + "/heads.json", sha(store.heads_raw), len(store.heads_raw)])
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return rows


def _experiment_basis(snapshot, domain_store, authority, exp):
    basis = dict(_basis(snapshot, domain_store, authority))
    basis["experiment_store_inventory_sha256"] = experiment_inventory_digest(exp)
    return basis


def _payload(path, mode, before, raw):
    digest = sha(raw)
    return {
        "path": path,
        "mode": mode,
        "before_sha256": before,
        "after_sha256": digest,
        "size_bytes": len(raw),
        "content_file": "experiment-publication/content/" + digest,
    }


def _destination(rel):
    return EXPERIMENT_PREFIX + rel


def _rebind_staged(snapshot, domain_store, authority, staged):
    for rid, (doc, _raw, rel) in staged.records.items():
        try:
            association = _require_association(snapshot, doc)
            _check_source_digest(snapshot, doc["source_digest"], error=True)
            _bind_sources(snapshot, doc, association)
            _require_code_binding(domain_store, doc)
            _require_claims(doc, authority)
        except ExperimentStoreError as exc:
            exc.details["record_id"] = rid
            exc.details["path"] = "experiments/" + rel
            raise


def _build_request(snapshot, domain_store, authority, exp, batch, staged):
    for rid, (doc, _raw, rel) in staged.records.items():
        dest = _destination(rel)
        if rid in exp.records:
            _fail(
                "EXPERIMENT_COMPILE_ALREADY_PUBLISHED",
                _pointer(*(dest.split("/"))),
                "discard_batch",
                {"path": dest},
            )
    prospective = _copy_experiment_store(exp)
    for rid, (doc, raw, _rel) in staged.records.items():
        prospective.records[rid] = doc
        prospective.record_raw[rid] = raw
    prospective.chains = {}
    prospective.heads_raw = staged.heads_raw
    prospective.empty = False
    _validate_chains(prospective)
    derived = derive_experiment_heads(prospective)
    derived_raw = canonicalize(derived)
    if staged.heads_raw != derived_raw:
        _fail(
            "EXPERIMENT_COMPILE_STALE",
            "/experiments/heads.json",
            "re_record_condition",
            {"path": "experiments/heads.json"},
            exit_code=75,
        )
    _rebind_staged(snapshot, domain_store, authority, staged)
    touched = _byte_sort({doc["condition_id"] for doc, _raw, _rel in staged.records.values()})
    payloads = []
    content = {}
    for _rid, (_doc, raw, rel) in staged.records.items():
        item = _payload(_destination(rel), "create", None, raw)
        payloads.append(item)
        content[item["after_sha256"]] = raw
    if exp.heads_raw is None:
        heads_mode = "create"
        heads_before = None
    else:
        heads_mode = "replace"
        heads_before = sha(exp.heads_raw)
    heads_item = _payload(EXPERIMENT_ROOT + "/heads.json", heads_mode, heads_before, staged.heads_raw)
    payloads.append(heads_item)
    content[heads_item["after_sha256"]] = staged.heads_raw
    payloads.sort(key=lambda item: item["path"].encode("utf-8"))
    basis = _experiment_basis(snapshot, domain_store, authority, exp)
    prospective_inventory = experiment_inventory_digest(prospective)
    request = {
        "schema": REQUEST_SCHEMA,
        "batch_id": batch,
        "kind": "experiments",
        "basis": basis,
        "prospective_inventory_sha256": prospective_inventory,
        "touched_conditions": touched,
        "payloads": payloads,
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "typed_fact_promotion": "none",
        "ranking": "not_ranked",
        "next_action": "inspect_experiment_publication",
    }
    try:
        request_raw = canonicalize(request)
        sealed = json.loads(request_raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("EXPERIMENT_COMPILE_INVALID", "", "repair_input", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, REQUEST_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "EXPERIMENT_COMPILE_INVALID", "repair_input")
    if len(request_raw) > MAX_RECORD_BYTES:
        _fail("EXPERIMENT_COMPILE_LIMIT", "/request", "reduce_batch", {"size_bytes": len(request_raw)})
    changed_paths = [item["path"] for item in sealed["payloads"]]
    data = {
        "state": "experiment_publication_prepared",
        "batch_id": batch,
        "basis": sealed["basis"],
        "prospective_inventory_sha256": sealed["prospective_inventory_sha256"],
        "request_path": ".work/" + batch + "/experiment-publication/request.json",
        "request_sha256": sha(request_raw),
        "touched_conditions": list(sealed["touched_conditions"]),
        "changed_paths": changed_paths,
        "payload_count": len(sealed["payloads"]),
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "code_freshness": "not_checked",
        "code_source_verification": "not_checked",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_experiment_publication",
    }
    return {"request": sealed, "request_raw": request_raw, "content": content, "data": data}


def _stage_publication(batch, built):
    target = resolve_checkout_root() / ".work" / batch / "experiment-publication" / "request.json"
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise StagingError(
            CODE_STAGING_CONFLICT,
            "target exists with different bytes",
            {"path": target.as_posix()},
        )
    stage_bytes(batch_id=batch, relative=("experiment-publication", "request.json"), data=built["request_raw"])
    written = set()
    for item in built["request"]["payloads"]:
        digest = item["after_sha256"]
        if digest in written:
            continue
        written.add(digest)
        stage_bytes(
            batch_id=batch,
            relative=("experiment-publication", "content", digest),
            data=built["content"][digest],
        )


def _verify_work(snapshot, *, changed):
    try:
        snapshot.verify()
    except ContractError as exc:
        _map_work(exc, "/experiments", invalid=changed, changed=changed)
    except OSError:
        _fail(changed, "/experiments", "repeat_read", exit_code=75)


def compile_experiment_publication(*, vault_root, batch_id):
    batch = _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        try:
            exp = _load_experiment_store(snapshot)
            work = _work_experiment_snapshot(batch)
            try:
                staged = _load_staged_experiments(work)
                built = _build_request(snapshot, domain_store, authority, exp, batch, staged)
                _verify_work(work, changed="EXPERIMENT_COMPILE_CHANGED")
                _stage_publication(batch, built)
                _verify_work(work, changed="EXPERIMENT_COMPILE_CHANGED")
                return built["data"]
            finally:
                work.close()
        except OSError:
            _fail("EXPERIMENT_COMPILE_CHANGED", "/experiments", "repeat_read", exit_code=75)

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
        if parts != (batch, "experiment-publication", "request.json"):
            raise ValueError
        return path, batch
    except (ValueError, StagingError) as exc:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "prepared input must use the fixed experiment publication slot",
            {"path": os.fspath(value)},
        ) from exc


def _experiment_suffix(path):
    if type(path) is not str or not path.startswith(EXPERIMENT_PREFIX):
        _fail("EXPERIMENT_PUBLICATION_INVALID", "/payloads", "repair_input", {"path": path})
    return path[len(EXPERIMENT_PREFIX) :]


def _staged_from_content(request, content):
    staged = _StagedExperiments()
    for index, item in enumerate(request["payloads"]):
        pointer = "/payloads/" + str(index)
        digest = item["after_sha256"]
        raw = content.get(digest)
        if raw is None:
            _fail("EXPERIMENT_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        if sha(raw) != digest or len(raw) != item["size_bytes"]:
            _fail("EXPERIMENT_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        suffix = _experiment_suffix(item["path"])
        if suffix == "heads.json":
            doc = _parse_record(raw, HEADS_SCHEMA, pointer, item["path"], invalid="EXPERIMENT_PUBLICATION_INVALID")
            if staged.heads_raw is not None:
                _fail("EXPERIMENT_PUBLICATION_INVALID", pointer, "repair_input", {"reason": "duplicate_heads"})
            staged.heads_doc = doc
            staged.heads_raw = raw
            continue
        if suffix.startswith("records/"):
            doc = _parse_record(
                raw, RECORD_SCHEMA, pointer, item["path"], invalid="EXPERIMENT_PUBLICATION_INVALID"
            )
            expected = "records/" + doc["condition_id"] + "/" + doc["record_id"] + ".json"
            if suffix != expected or record_id_from_record(doc) != doc["record_id"]:
                _fail("EXPERIMENT_PUBLICATION_MISMATCH", pointer, "recompile", {"path": item["path"]})
            staged.records[doc["record_id"]] = (doc, raw, suffix)
            continue
        _fail("EXPERIMENT_PUBLICATION_INVALID", pointer, "repair_input", {"path": item["path"]})
    if staged.heads_raw is None or not staged.records:
        _fail("EXPERIMENT_PUBLICATION_INVALID", "/payloads", "repair_input", {"reason": "incomplete"})
    return staged


def _load_publication(snapshot, batch):
    names = _list_names(snapshot.root_fd, "/experiment-publication", changed="EXPERIMENT_PUBLICATION_INVALID")
    extra = [name for name in names if name not in {"request.json", "content"}]
    if extra:
        _fail(
            "EXPERIMENT_PUBLICATION_INVALID",
            _pointer("experiment-publication", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "experiment-publication/" + extra[0]},
        )
    if "request.json" not in names:
        _fail(
            "EXPERIMENT_PUBLICATION_INVALID",
            "/experiment-publication/request.json",
            "repair_input",
            {"reason": "missing", "path": "experiment-publication/request.json"},
        )
    st = _stat_child(snapshot.root_fd, "request.json")
    _require_regular(
        st,
        "experiment-publication/request.json",
        invalid="EXPERIMENT_PUBLICATION_INVALID",
        changed="EXPERIMENT_PUBLICATION_INVALID",
    )
    request_raw = _read_bytes(
        snapshot,
        "request.json",
        "/experiment-publication/request.json",
        invalid="EXPERIMENT_PUBLICATION_INVALID",
        changed="EXPERIMENT_PUBLICATION_INVALID",
    )
    request = _parse_record(
        request_raw,
        REQUEST_SCHEMA,
        "/experiment-publication/request.json",
        "experiment-publication/request.json",
        invalid="EXPERIMENT_PUBLICATION_INVALID",
    )
    if request["batch_id"] != batch:
        _fail(
            "EXPERIMENT_PUBLICATION_INVALID",
            "/batch_id",
            "repair_input",
            {"reason": "batch_id", "path": "experiment-publication/request.json"},
        )
    if "content" not in names:
        _fail(
            "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
            "/experiment-publication/content",
            "recompile",
            {"path": "experiment-publication/content"},
        )
    cst = _stat_child(snapshot.root_fd, "content")
    if cst is None:
        _fail(
            "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
            "/experiment-publication/content",
            "recompile",
            {"path": "experiment-publication/content"},
        )
    if stat.S_ISLNK(cst.st_mode) or not stat.S_ISDIR(cst.st_mode):
        _fail(
            "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
            "/experiment-publication/content",
            "recompile",
            {"reason": "entry_kind", "path": "experiment-publication/content"},
        )
    content_fd = os.open("content", dir_open_flags(), dir_fd=snapshot.root_fd)
    try:
        snapshot.directories.setdefault("content", os.fstat(content_fd))
        content_names = _list_names(
            content_fd, "/experiment-publication/content", changed="EXPERIMENT_PUBLICATION_INVALID"
        )
        expected = {item["after_sha256"] for item in request["payloads"]}
        if set(content_names) != expected:
            _fail(
                "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
                "/experiment-publication/content",
                "recompile",
                {"path": "experiment-publication/content"},
            )
        content = {}
        for name in content_names:
            relative = "content/" + name
            pointer = "/experiment-publication/" + relative
            if CONTENT_NAME_RE.fullmatch(name) is None:
                _fail("EXPERIMENT_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            fst = _stat_child(content_fd, name)
            _require_regular(
                fst,
                "experiment-publication/" + relative,
                invalid="EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
                changed="EXPERIMENT_PUBLICATION_INVALID",
            )
            raw = _read_bytes(
                snapshot,
                relative,
                pointer,
                invalid="EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
                changed="EXPERIMENT_PUBLICATION_INVALID",
            )
            if sha(raw) != name:
                _fail("EXPERIMENT_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            content[name] = raw
        for index, item in enumerate(request["payloads"]):
            raw = content[item["after_sha256"]]
            if sha(raw) != item["after_sha256"] or len(raw) != item["size_bytes"]:
                _fail(
                    "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index),
                    "recompile",
                    {"path": item["content_file"]},
                )
            expected_file = "experiment-publication/content/" + item["after_sha256"]
            if item["content_file"] != expected_file:
                _fail(
                    "EXPERIMENT_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index) + "/content_file",
                    "recompile",
                    {"path": item["content_file"]},
                )
        return request, request_raw, content
    finally:
        close_fd(content_fd)


def inspect_experiment_publication(*, prepared, vault_root):
    _path, batch = _prepared_slot(prepared)

    def apply(snapshot, domain_store, authority):
        try:
            exp = _load_experiment_store(snapshot)
            pub = _publication_snapshot(batch)
            try:
                request, request_raw, content = _load_publication(pub, batch)
                current_basis = _experiment_basis(snapshot, domain_store, authority, exp)
                if current_basis != request["basis"]:
                    _fail("EXPERIMENT_PUBLICATION_STALE", "/basis", "recompile", exit_code=75)
                staged = _staged_from_content(request, content)
                rebuilt = _build_request(snapshot, domain_store, authority, exp, batch, staged)
                if (
                    rebuilt["request"]["payloads"] != request["payloads"]
                    or rebuilt["request"]["touched_conditions"] != request["touched_conditions"]
                    or rebuilt["request"]["prospective_inventory_sha256"] != request["prospective_inventory_sha256"]
                ):
                    _fail("EXPERIMENT_PUBLICATION_MISMATCH", "/payloads", "recompile")
                inspection = {
                    "schema": INSPECTION_SCHEMA,
                    "batch_id": batch,
                    "request_sha256": sha(request_raw),
                    "request": request,
                    "basis_verified": True,
                    "content_verified": True,
                    "bindings_verified": True,
                    "publication": "unpublished",
                    "applied": False,
                    "receipt_backed": False,
                    "audit_coverage": "not_wired",
                    "backup_coverage": "not_wired",
                    "transaction_authority": "not_wired",
                    "canonical_official": False,
                    "current_supported_typed_fact": False,
                    "typed_fact_promotion": "none",
                    "ranking": "not_ranked",
                    "next_action": "apply_via_vpwiki_admin",
                }
                try:
                    validate_document(inspection, INSPECTION_SCHEMA)
                except ContractError as exc:
                    _map_schema(exc, "EXPERIMENT_PUBLICATION_INVALID", "repair_input")
                try:
                    pub.verify()
                except ContractError as exc:
                    _map_work(
                        exc,
                        "/experiment-publication",
                        invalid="EXPERIMENT_PUBLICATION_INVALID",
                        changed="EXPERIMENT_PUBLICATION_INVALID",
                    )
                return inspection
            finally:
                pub.close()
        except OSError:
            _fail("EXPERIMENT_PUBLICATION_INVALID", "/experiment-publication", "repair_input")

    return _with_store(vault_root, apply, authority_required=True)
