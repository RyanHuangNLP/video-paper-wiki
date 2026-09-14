"""Experiment-condition store: read-only load, record staging, and status."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from video_paper_wiki.contracts import MAX_BYTES, ContractError, validate_document
from video_paper_wiki.domain_proposal import _ASSOCIATION_DIR, DomainProposalError
from video_paper_wiki.domain_publication import _basis
from video_paper_wiki.domain_store import (
    DomainStoreError,
    MAX_LINEAGES,
    MAX_PER_LINEAGE,
    MAX_RECORD_BYTES,
    _batch,
    _claim_freshness,
    _list_names,
    _map_snapshot,
    _open_named_dir,
    _read_record,
    _register_dir,
    _require_regular,
    _stage_items,
    _stat_child,
    _with_store,
)
from video_paper_wiki.domain_versions import DomainVersionsError, _association_state
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.secure_io import SecureIOError, close_fd, dir_open_flags, load_strict_json, parse_strict_json
from video_paper_wiki.source_semantics_contracts import calendar, sha
from video_paper_wiki.staging import StagingError

RECORD_SCHEMA = "video-paper-wiki.experiment-condition-record.v1"
HEADS_SCHEMA = "video-paper-wiki.experiment-heads.v1"
RECORD_COMMAND = "experiments.record"
STATUS_COMMAND = "experiments.status"
EXPERIMENT_ROOT = "wiki/meta/experiments"
CONDITION_RE = re.compile(r"^exc-[0-9a-f]{20}$")
RECORD_RE = re.compile(r"^exr-[0-9a-f]{20}$")
INPUT_KEYS = frozenset(
    {
        "paper_id",
        "source_association",
        "source_digest",
        "code_binding",
        "setting_key",
        "conditions",
        "claim_refs",
    }
)
CONDITION_KEYS = (
    "model_checkpoint",
    "parameter_count",
    "dataset_split",
    "metrics",
    "resolution",
    "frames",
    "inference_steps",
    "sampling_guidance",
    "evaluation_setup",
)
CRITICAL_CONDITIONS = (
    "dataset_split",
    "metrics",
    "resolution",
    "frames",
    "evaluation_setup",
)
KNOWN_STATUSES = frozenset({"reported", "derived"})
STALE_BINDINGS = frozenset({"lineage_missing", "annotation_missing", "report_mismatch"})
PAPER_ID_LIMIT = 256
MESSAGES = {
    "EXPERIMENT_STORE_INVALID": "experiment store is invalid",
    "EXPERIMENT_STORE_LIMIT": "experiment store exceeds a closed bound",
    "EXPERIMENT_STORE_CHAIN_INVALID": "experiment store chain is invalid",
    "EXPERIMENT_STORE_HEADS_MISSING": "experiment store heads.json is missing",
    "EXPERIMENT_STORE_HEADS_MISMATCH": "experiment store heads.json does not match derived heads",
    "EXPERIMENT_STORE_CHANGED": "experiment store changed during read",
    "EXPERIMENT_RECORD_INVALID": "experiment record is invalid",
    "EXPERIMENT_RECORD_INPUT_MISSING": "required experiment record input is missing",
    "EXPERIMENT_RECORD_BINDING_MISMATCH": "experiment record binding mismatch",
    "EXPERIMENT_RECORD_PREVIOUS_MISMATCH": "experiment record previous record does not match the chain head",
    "EXPERIMENT_RECORD_UNCHANGED": "experiment record content is unchanged from the chain head",
    "EXPERIMENT_HEAD_STALE": "experiment record claim bindings are stale",
    "EXPERIMENT_STATUS_INVALID": "experiment status input is invalid",
    "EXPERIMENT_STATUS_PAPER_UNKNOWN": "experiment status paper_id is unknown",
}


class ExperimentStoreError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


class ExperimentStore:
    def __init__(self):
        self.records = {}
        self.record_raw = {}
        self.chains = {}
        self.heads_raw = None
        self.empty = True


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise ExperimentStoreError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _file_pointer(condition_id, record_id, *rest):
    pointer = _pointer("wiki", "meta", "experiments", "records", condition_id, record_id + ".json")
    if rest:
        pointer += _pointer(*rest)
    return pointer


def _remap_domain_store_error(exc):
    code = exc.code
    if code == "WORK_PATH_UNSAFE":
        raise exc
    details = dict(exc.details or {})
    pointer = details.get("instance_pointer") or ""
    if pointer.startswith("/wiki/meta/domain"):
        pointer = "/wiki/meta/experiments" + pointer[len("/wiki/meta/domain") :]
        details["instance_pointer"] = pointer
    path = details.get("path")
    if isinstance(path, str) and path.startswith("wiki/meta/domain"):
        details["path"] = "wiki/meta/experiments" + path[len("wiki/meta/domain") :]
    if code.startswith("DOMAIN_STORE_"):
        code = "EXPERIMENT_STORE_" + code[len("DOMAIN_STORE_") :]
    if "instance_pointer" not in details:
        details["instance_pointer"] = pointer or "/wiki/meta/experiments"
    if "next_action" not in details:
        details["next_action"] = "repair_store"
    raise ExperimentStoreError(
        code,
        MESSAGES.get(code, exc.message),
        details,
        exit_code=exc.exit_code,
    ) from exc


def _call_store(function):
    try:
        return function()
    except DomainStoreError as exc:
        _remap_domain_store_error(exc)
    except OSError:
        _fail("EXPERIMENT_STORE_CHANGED", "/wiki/meta/experiments", "repeat_read", exit_code=75)


def condition_id_from_record(record):
    material = {
        "paper_id": record["paper_id"],
        "source_association_id": record["source_association"]["association_id"],
        "setting_key": record["setting_key"],
    }
    try:
        return "exc-" + sha(canonicalize(material))[:20]
    except CanonicalJsonError:
        _fail("EXPERIMENT_STORE_INVALID", "/condition_id", "repair_store", {"reason": "canonical_bytes"})


def record_id_from_record(record):
    payload = {key: value for key, value in record.items() if key != "record_id"}
    try:
        return "exr-" + sha(canonicalize(payload))[:20]
    except CanonicalJsonError:
        _fail("EXPERIMENT_STORE_INVALID", "/record_id", "repair_store", {"reason": "canonical_bytes"})


def content_sha256_from_record(record):
    material = {
        "source_association": record["source_association"],
        "source_digest": record["source_digest"],
        "code_binding": record["code_binding"],
        "setting_key": record["setting_key"],
        "conditions": record["conditions"],
        "claim_refs": record["claim_refs"],
    }
    try:
        return sha(canonicalize(material))
    except CanonicalJsonError:
        _fail("EXPERIMENT_STORE_INVALID", "/content_sha256", "repair_store", {"reason": "canonical_bytes"})


def derive_experiment_heads(store):
    heads = {}
    for cid in sorted(store.chains):
        chain = store.chains[cid]
        rid = chain["record_order"][-1]
        heads[cid] = {
            "record_id": rid,
            "record_sha256": sha(store.record_raw[rid]),
        }
    return {"schema": HEADS_SCHEMA, "heads": heads}


def experiment_inventory_digest(store):
    rows = []
    for doc in store.records.values():
        path = EXPERIMENT_ROOT + "/records/" + doc["condition_id"] + "/" + doc["record_id"] + ".json"
        raw = store.record_raw[doc["record_id"]]
        rows.append([path, sha(raw), len(raw)])
    if store.heads_raw is not None:
        rows.append([EXPERIMENT_ROOT + "/heads.json", sha(store.heads_raw), len(store.heads_raw)])
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return sha(canonicalize(rows))


def _copy_experiment_store(store):
    out = ExperimentStore()
    out.records = dict(store.records)
    out.record_raw = dict(store.record_raw)
    out.chains = {cid: {"record_order": list(chain["record_order"])} for cid, chain in store.chains.items()}
    out.heads_raw = store.heads_raw
    out.empty = store.empty
    return out


def _iter_sources(record):
    conditions = record["conditions"]
    for key in CONDITION_KEYS:
        cond = conditions[key]
        for index, source in enumerate(cond.get("sources") or []):
            yield key, _pointer("conditions", key, "sources", index), source
        if key == "metrics" and cond.get("status") in KNOWN_STATUSES:
            for index, metric in enumerate(cond["value"]):
                source = metric.get("definition_source")
                if source is not None:
                    yield key, _pointer("conditions", "metrics", "value", index, "definition_source"), source


def _check_record_shape(record, *, base=""):
    conditions = record["conditions"]
    binding = record["code_binding"]
    for key in CONDITION_KEYS:
        cond = conditions[key]
        status = cond["status"]
        pointer = base + _pointer("conditions", key)
        if status == "derived" and cond["basis_note"] is None:
            _fail(
                "EXPERIMENT_RECORD_INVALID",
                pointer + "/basis_note",
                "repair_input",
                {"reason": "derived_basis"},
            )
        if status in KNOWN_STATUSES and key == "metrics":
            names = [item["name"] for item in cond["value"]]
            if len(names) != len(set(names)):
                _fail(
                    "EXPERIMENT_RECORD_INVALID",
                    pointer,
                    "repair_input",
                    {"reason": "duplicate_metric"},
                )
        if status in KNOWN_STATUSES and key == "sampling_guidance":
            value = cond["value"]
            if value["guidance_scale"] is None and value["sampler"] is None and value["seed"] is None:
                _fail(
                    "EXPERIMENT_RECORD_INVALID",
                    pointer + "/value",
                    "repair_input",
                    {"reason": "empty_value"},
                )
    for key, pointer, source in _iter_sources(record):
        if source["kind"] != "repository_text":
            continue
        commit = source["locator"]["commit"]
        if binding is None or binding["commit"] != commit:
            _fail(
                "EXPERIMENT_RECORD_INVALID",
                base + pointer,
                "repair_input",
                {"reason": "repository_text_requires_code_binding"},
            )


def _linear_record_chain(rows, condition_id, known):
    by_id = {}
    for row in rows:
        key = row["record_id"]
        if key in by_id:
            _fail(
                "EXPERIMENT_STORE_CHAIN_INVALID",
                _file_pointer(row["condition_id"], key),
                "repair_store",
                {"reason": "duplicate"},
            )
        by_id[key] = row
    roots = []
    children = {}
    for row in rows:
        previous = row["previous_record_id"]
        pointer = _file_pointer(row["condition_id"], row["record_id"], "previous_record_id")
        if previous is None:
            roots.append(row["record_id"])
            continue
        parent = by_id.get(previous)
        if parent is None:
            foreign = known.get(previous)
            _fail(
                "EXPERIMENT_STORE_CHAIN_INVALID",
                pointer,
                "repair_store",
                {"reason": "cross_lineage" if foreign is not None else "missing_predecessor"},
            )
        if parent["condition_id"] != row["condition_id"] or row["condition_id"] != condition_id:
            _fail("EXPERIMENT_STORE_CHAIN_INVALID", pointer, "repair_store", {"reason": "cross_lineage"})
        if previous in children:
            _fail("EXPERIMENT_STORE_CHAIN_INVALID", pointer, "repair_store", {"reason": "fork"})
        children[previous] = row["record_id"]
        if calendar(parent["recorded_at"]) > calendar(row["recorded_at"]):
            _fail(
                "EXPERIMENT_STORE_CHAIN_INVALID",
                _file_pointer(row["condition_id"], row["record_id"], "recorded_at"),
                "repair_store",
                {"reason": "timestamp_order"},
            )
    chain_pointer = _pointer("wiki", "meta", "experiments", "records", condition_id)
    if rows and len(roots) != 1:
        _fail("EXPERIMENT_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "genesis"})
    if not rows:
        return []
    seen = []
    cursor = roots[0]
    visiting = set()
    while cursor is not None:
        if cursor in visiting:
            _fail("EXPERIMENT_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "cycle"})
        visiting.add(cursor)
        seen.append(cursor)
        cursor = children.get(cursor)
    if len(seen) != len(rows):
        _fail("EXPERIMENT_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "orphan"})
    return seen


def _validate_chains(store):
    groups = {}
    for doc in store.records.values():
        expected_cid = condition_id_from_record(doc)
        pointer = _file_pointer(doc["condition_id"], doc["record_id"])
        if doc["condition_id"] != expected_cid:
            _fail("EXPERIMENT_STORE_INVALID", pointer + "/condition_id", "repair_store", {"reason": "identity"})
        if doc["record_id"] != record_id_from_record(doc):
            _fail("EXPERIMENT_STORE_INVALID", pointer + "/record_id", "repair_store", {"reason": "identity"})
        if doc["content_sha256"] != content_sha256_from_record(doc):
            _fail(
                "EXPERIMENT_STORE_INVALID",
                pointer + "/content_sha256",
                "repair_store",
                {"reason": "content_sha256"},
            )
        _check_record_shape(doc, base=pointer)
        groups.setdefault(doc["condition_id"], []).append(doc)
    for cid in sorted(groups):
        order = _linear_record_chain(groups[cid], cid, store.records)
        previous_sha = None
        for rid in order:
            current = store.records[rid]["content_sha256"]
            if previous_sha is not None and current == previous_sha:
                _fail(
                    "EXPERIMENT_RECORD_UNCHANGED",
                    _file_pointer(cid, rid, "content_sha256"),
                    "revise_record",
                )
            previous_sha = current
        if len(order) > MAX_PER_LINEAGE:
            _fail(
                "EXPERIMENT_STORE_LIMIT",
                _pointer("wiki", "meta", "experiments", "records", cid),
                "reduce_store",
            )
        store.chains[cid] = {"record_order": order}
    if len(store.chains) > MAX_LINEAGES:
        _fail("EXPERIMENT_STORE_LIMIT", "/wiki/meta/experiments", "reduce_store", {"reason": "lineages"})


def _scan_records(snapshot, exp_fd, store):
    relative_kind = EXPERIMENT_ROOT + "/records"
    st = _call_store(lambda: _stat_child(exp_fd, "records"))
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        _fail("EXPERIMENT_STORE_INVALID", "/" + relative_kind, "repair_store", {"reason": "symlink", "path": relative_kind})
    if not stat.S_ISDIR(st.st_mode):
        _fail("EXPERIMENT_STORE_INVALID", "/" + relative_kind, "repair_store", {"reason": "entry_kind", "path": relative_kind})
    try:
        kind_fd = os.open("records", dir_open_flags(), dir_fd=exp_fd)
    except OSError:
        _fail("EXPERIMENT_STORE_CHANGED", "/" + relative_kind, "repeat_read", exit_code=75)
    try:
        _call_store(lambda: _register_dir(snapshot, relative_kind, kind_fd))
        conditions = _call_store(lambda: _list_names(kind_fd))
        if not conditions:
            return
        for condition_name in conditions:
            lineage_rel = relative_kind + "/" + condition_name
            lst = _call_store(lambda name=condition_name: _stat_child(kind_fd, name))
            if lst is None:
                _fail("EXPERIMENT_STORE_CHANGED", "/" + lineage_rel, "repeat_read", exit_code=75)
            if stat.S_ISLNK(lst.st_mode):
                _fail("EXPERIMENT_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "symlink", "path": lineage_rel})
            if not stat.S_ISDIR(lst.st_mode):
                _fail("EXPERIMENT_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "entry_kind", "path": lineage_rel})
            if CONDITION_RE.fullmatch(condition_name) is None:
                _fail("EXPERIMENT_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "unknown_entry", "path": lineage_rel})
            try:
                child_fd = os.open(condition_name, dir_open_flags(), dir_fd=kind_fd)
            except OSError:
                _fail("EXPERIMENT_STORE_CHANGED", "/" + lineage_rel, "repeat_read", exit_code=75)
            try:
                _call_store(lambda rel=lineage_rel, fd=child_fd: _register_dir(snapshot, rel, fd))
                files = _call_store(lambda: _list_names(child_fd))
                if not files:
                    _fail("EXPERIMENT_STORE_INVALID", "/" + lineage_rel, "repair_store", {"reason": "empty_lineage", "path": lineage_rel})
                if len(files) > MAX_PER_LINEAGE:
                    _fail("EXPERIMENT_STORE_LIMIT", "/" + lineage_rel, "reduce_store", {"path": lineage_rel})
                for filename in files:
                    file_rel = lineage_rel + "/" + filename
                    fst = _call_store(lambda name=filename: _stat_child(child_fd, name))
                    _call_store(lambda st=fst, rel=file_rel: _require_regular(st, rel))
                    stem, sep, ext = filename.partition(".")
                    if sep != "." or ext != "json" or RECORD_RE.fullmatch(stem) is None:
                        _fail("EXPERIMENT_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "unknown_entry", "path": file_rel})
                    doc, raw = _call_store(lambda rel=file_rel: _read_record(snapshot, rel, RECORD_SCHEMA, "/" + rel))
                    if doc["record_id"] != stem:
                        _fail("EXPERIMENT_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "path_identity", "path": file_rel})
                    if doc["condition_id"] != condition_name:
                        _fail("EXPERIMENT_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "path_identity", "path": file_rel})
                    if doc["record_id"] in store.records:
                        _fail("EXPERIMENT_STORE_INVALID", "/" + file_rel, "repair_store", {"reason": "duplicate_id", "path": file_rel})
                    store.records[doc["record_id"]] = doc
                    store.record_raw[doc["record_id"]] = raw
            finally:
                close_fd(child_fd)
    finally:
        close_fd(kind_fd)


def _load_experiment_store(snapshot):
    store = ExperimentStore()
    exp_fd, fds = _call_store(lambda: _open_named_dir(snapshot, ("wiki", "meta", "experiments")))
    try:
        if exp_fd is None:
            return store
        names = _call_store(lambda: _list_names(exp_fd))
        allowed = {"records", "heads.json"}
        extra = [name for name in names if name not in allowed]
        if extra:
            _fail(
                "EXPERIMENT_STORE_INVALID",
                _pointer("wiki", "meta", "experiments", extra[0]),
                "repair_store",
                {"reason": "unknown_entry", "name": extra[0]},
            )
        if "records" in names:
            _scan_records(snapshot, exp_fd, store)
        heads_raw = None
        if "heads.json" in names:
            st = _call_store(lambda: _stat_child(exp_fd, "heads.json"))
            _call_store(lambda: _require_regular(st, EXPERIMENT_ROOT + "/heads.json"))
            heads_doc, heads_raw = _call_store(
                lambda: _read_record(
                    snapshot,
                    EXPERIMENT_ROOT + "/heads.json",
                    HEADS_SCHEMA,
                    "/wiki/meta/experiments/heads.json",
                )
            )
            store.heads_raw = heads_raw
        store.empty = not store.records and heads_raw is None
        if store.records:
            if heads_raw is None:
                _fail("EXPERIMENT_STORE_HEADS_MISSING", "/wiki/meta/experiments/heads.json", "restore_heads")
        _validate_chains(store)
        derived = derive_experiment_heads(store)
        derived_raw = canonicalize(derived)
        if heads_raw is None:
            if derived["heads"]:
                _fail("EXPERIMENT_STORE_HEADS_MISSING", "/wiki/meta/experiments/heads.json", "restore_heads")
        elif heads_raw != derived_raw:
            _fail("EXPERIMENT_STORE_HEADS_MISMATCH", "/wiki/meta/experiments/heads.json", "restore_heads")
        return store
    finally:
        for fd in reversed(fds):
            close_fd(fd)


def _run_with_store(vault_root, function, *, authority_required=True):
    try:
        return _with_store(vault_root, function, authority_required=authority_required)
    except ExperimentStoreError:
        raise
    except DomainStoreError:
        raise
    except DomainProposalError:
        raise
    except StagingError:
        raise
    except OSError:
        _fail("EXPERIMENT_STORE_CHANGED", "/wiki/meta/experiments", "repeat_read", exit_code=75)


def load_experiment_store(vault_root):
    def apply(snapshot, store, authority):
        exp = _load_experiment_store(snapshot)
        return exp, derive_experiment_heads(exp), authority

    return _run_with_store(vault_root, apply, authority_required=True)


def _recorded_by(value):
    if type(value) is not str or not value or len(value) > 256:
        _fail("EXPERIMENT_RECORD_INVALID", "/recorded_by", "repair_input", {"reason": "string"})
    return value


def _recorded_at(value):
    try:
        calendar(value, "/recorded_at")
    except ContractError as exc:
        _fail("EXPERIMENT_RECORD_INVALID", "/recorded_at", "repair_input", dict(exc.details))
    return value


def _load_input(path):
    try:
        parsed = load_strict_json(
            Path(path),
            missing_code="EXPERIMENT_RECORD_INPUT_MISSING",
            unsafe_code="WORK_PATH_UNSAFE",
            invalid_code="EXPERIMENT_RECORD_INVALID",
            changed_code="EXPERIMENT_STORE_CHANGED",
            max_bytes=MAX_RECORD_BYTES,
        )
    except SecureIOError as exc:
        code = exc.code
        next_action = "repeat_read" if code == "EXPERIMENT_STORE_CHANGED" else "repair_input"
        raise ExperimentStoreError(
            code,
            MESSAGES.get(code, exc.message),
            {"instance_pointer": "/input", "next_action": next_action, **exc.details},
            exit_code=75 if code == "EXPERIMENT_STORE_CHANGED" else getattr(exc, "exit_code", 2),
        ) from exc
    if type(parsed) is not dict:
        _fail("EXPERIMENT_RECORD_INVALID", "/input", "repair_input", {"reason": "type"})
    if set(parsed) != INPUT_KEYS:
        _fail("EXPERIMENT_RECORD_INVALID", "/input", "repair_input", {"reason": "input_keys"})
    return parsed


def _seal_record(document):
    try:
        raw = canonicalize(document)
        sealed = json.loads(raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("EXPERIMENT_RECORD_INVALID", "/input", "repair_input", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, RECORD_SCHEMA)
    except ContractError as exc:
        pointer = exc.details.get("instance_pointer") or ""
        raise ExperimentStoreError(
            "EXPERIMENT_RECORD_INVALID",
            MESSAGES["EXPERIMENT_RECORD_INVALID"],
            {"instance_pointer": pointer, "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    return sealed, raw


def _read_optional(snapshot, relative, pointer):
    try:
        return snapshot.read_optional(relative, max_bytes=MAX_BYTES)
    except OSError:
        _fail("EXPERIMENT_STORE_CHANGED", pointer, "repeat_read", {"path": relative}, exit_code=75)
    except ContractError as exc:
        _map_snapshot(exc)
    except SecureIOError as exc:
        _map_snapshot(exc)


def _association_lookup(snapshot, record):
    association_id = record["source_association"]["association_id"]
    relative = _ASSOCIATION_DIR + association_id + ".json"
    raw = _read_optional(snapshot, relative, "/source_association")
    try:
        state, doc, _sha = _association_state(raw, record, association_id)
    except DomainVersionsError as exc:
        reason = (exc.details or {}).get("reason") or "association_shape"
        if reason == "association_binding" and raw is not None:
            try:
                parsed = parse_strict_json(raw, invalid_code="EXPERIMENT_STORE_INVALID")
            except SecureIOError:
                return "invalid", "association_shape", None
            digest = record["source_digest"]
            if parsed.get("paper_id") == record["paper_id"] and (
                parsed.get("raw", {}).get("path") != digest["path"]
                or parsed.get("raw", {}).get("sha256") != digest["sha256"]
                or parsed.get("raw", {}).get("size_bytes") != digest["size_bytes"]
            ):
                return "digest", "sha256", None
        return "invalid", reason, None
    return state, None, doc


def _require_association(snapshot, record):
    state, reason, doc = _association_lookup(snapshot, record)
    if state == "digest":
        _fail(
            "EXPERIMENT_RECORD_BINDING_MISMATCH",
            "/source_digest",
            "repair_bindings",
            {"field": "source_digest", "reason": reason},
        )
    if state == "invalid":
        _fail(
            "EXPERIMENT_RECORD_BINDING_MISMATCH",
            "/source_association",
            "repair_bindings",
            {"field": "source_association", "reason": reason},
        )
    mapped = {"missing": "missing", "changed": "sha256", "identity_mismatch": "association_identity", "bound": None}
    if state != "bound":
        _fail(
            "EXPERIMENT_RECORD_BINDING_MISMATCH",
            "/source_association",
            "repair_bindings",
            {"field": "source_association", "reason": mapped[state]},
        )
    return doc


def _check_source_digest(snapshot, digest, *, error=True):
    pointer = "/source_digest"
    raw = _read_optional(snapshot, digest["path"], pointer)
    if raw is None:
        if error:
            _fail(
                "EXPERIMENT_RECORD_BINDING_MISMATCH",
                pointer,
                "repair_bindings",
                {"field": "source_digest", "reason": "missing"},
            )
        return "missing"
    if sha(raw) != digest["sha256"] or len(raw) != digest["size_bytes"]:
        if error:
            _fail(
                "EXPERIMENT_RECORD_BINDING_MISMATCH",
                pointer,
                "repair_bindings",
                {"field": "source_digest", "reason": "sha256"},
            )
        return "changed"
    return "bound"


def _check_fragment(fragment, raw):
    start = fragment["start"]
    end = fragment["end"]
    if not 0 <= start < end <= len(raw):
        return False
    return sha(raw[start:end]) == fragment["text_sha256"]


def _bind_sources(snapshot, record, association):
    source_id = association["source_id"]
    for _key, pointer, source in _iter_sources(record):
        kind = source["kind"]
        locator = source["locator"]
        if kind == "paper_direct":
            if locator["source_id"] != source_id:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer + "/locator/source_id",
                    "repair_bindings",
                    {"field": "paper_direct", "reason": "source_id"},
                )
            raw = _read_optional(snapshot, locator["artifact_path"], pointer)
            if raw is None:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer,
                    "repair_bindings",
                    {"field": "paper_direct", "reason": "missing"},
                )
            if sha(raw) != locator["artifact_sha256"]:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer,
                    "repair_bindings",
                    {"field": "paper_direct", "reason": "sha256"},
                )
        elif kind == "project_page":
            digest = locator["local_digest"]
            raw = _read_optional(snapshot, digest["path"], pointer)
            if raw is None:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer,
                    "repair_bindings",
                    {"field": "project_page", "reason": "missing"},
                )
            if len(raw) != digest["size_bytes"]:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer,
                    "repair_bindings",
                    {"field": "project_page", "reason": "size_bytes"},
                )
            if sha(raw) != digest["sha256"]:
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer,
                    "repair_bindings",
                    {"field": "project_page", "reason": "sha256"},
                )
            if not _check_fragment(locator["fragment"], raw):
                _fail(
                    "EXPERIMENT_RECORD_BINDING_MISMATCH",
                    pointer + "/locator/fragment",
                    "repair_bindings",
                    {"field": "project_page", "reason": "fragment"},
                )


def _code_binding_status(domain_store, record):
    binding = record["code_binding"]
    if binding is None:
        return None
    lid = binding["lineage_id"]
    chain = domain_store.chains.get(lid)
    if chain is None:
        return "lineage_missing"
    if binding["annotation_id"] not in chain["annotation_order"]:
        return "annotation_missing"
    annotation = domain_store.annotations[binding["annotation_id"]]
    report = annotation["report"]
    if (
        report["repository"] != binding["repository"]
        or report["commit"] != binding["commit"]
        or report["paper_id"] != record["paper_id"]
        or report["source_association"]["association_id"] != record["source_association"]["association_id"]
    ):
        return "report_mismatch"
    if chain["annotation_order"][-1] == binding["annotation_id"]:
        return "head"
    return "superseded"


def _require_code_binding(domain_store, record):
    status = _code_binding_status(domain_store, record)
    if status in STALE_BINDINGS:
        _fail(
            "EXPERIMENT_RECORD_BINDING_MISMATCH",
            "/code_binding",
            "repair_bindings",
            {"field": "code_binding", "reason": status},
        )


def _require_claims(record, authority):
    for index, item in enumerate(record["claim_refs"]):
        freshness, reason = _claim_freshness(item, authority)
        if freshness != "head_bound":
            _fail(
                "EXPERIMENT_HEAD_STALE",
                _pointer("claim_refs", index),
                "re_record_condition",
                {"stale_reason": reason, "claim_id": item["claim_id"]},
            )


def _build_record(*, payload, previous, recorded_by, recorded_at):
    condition_id = condition_id_from_record(payload)
    content_sha256 = content_sha256_from_record(payload)
    body = {
        "schema": RECORD_SCHEMA,
        "condition_id": condition_id,
        "previous_record_id": previous,
        "recorded_by": recorded_by,
        "recorded_at": recorded_at,
        "paper_id": payload["paper_id"],
        "source_association": payload["source_association"],
        "source_digest": payload["source_digest"],
        "code_binding": payload["code_binding"],
        "setting_key": payload["setting_key"],
        "conditions": payload["conditions"],
        "claim_refs": payload["claim_refs"],
        "content_sha256": content_sha256,
        "publication": "unpublished",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
    }
    record_id = record_id_from_record(body)
    return _seal_record({"record_id": record_id, **body})


def record_experiment_condition(
    *,
    input_path,
    vault_root,
    batch_id,
    recorded_by,
    recorded_at,
    previous_record_id=None,
):
    batch = _batch(batch_id, "/batch_id")
    recorded_by = _recorded_by(recorded_by)
    recorded_at = _recorded_at(recorded_at)
    previous = previous_record_id
    if previous is not None:
        if type(previous) is not str or RECORD_RE.fullmatch(previous) is None:
            _fail("EXPERIMENT_RECORD_INVALID", "/previous_record_id", "repair_input", {"reason": "identity"})
    payload = _load_input(input_path)

    def apply(snapshot, domain_store, authority):
        exp = _load_experiment_store(snapshot)
        record, raw = _build_record(
            payload=payload,
            previous=previous,
            recorded_by=recorded_by,
            recorded_at=recorded_at,
        )
        _check_record_shape(record)
        association = _require_association(snapshot, record)
        _check_source_digest(snapshot, record["source_digest"], error=True)
        _bind_sources(snapshot, record, association)
        _require_code_binding(domain_store, record)
        _require_claims(record, authority)
        cid = record["condition_id"]
        chain = exp.chains.get(cid)
        if chain:
            head_id = chain["record_order"][-1]
            if previous != head_id:
                _fail(
                    "EXPERIMENT_RECORD_PREVIOUS_MISMATCH",
                    "/previous_record_id",
                    "supply_previous",
                    {"expected": head_id},
                )
            head = exp.records[head_id]
            if record["content_sha256"] == head["content_sha256"]:
                _fail("EXPERIMENT_RECORD_UNCHANGED", "/conditions", "revise_record")
            if calendar(recorded_at) < calendar(head["recorded_at"]):
                _fail("EXPERIMENT_STORE_CHAIN_INVALID", "/recorded_at", "repair_input", {"reason": "timestamp_order"})
            if len(chain["record_order"]) >= MAX_PER_LINEAGE:
                _fail("EXPERIMENT_STORE_LIMIT", "/records", "reduce_store")
        else:
            if previous is not None:
                _fail("EXPERIMENT_RECORD_PREVIOUS_MISMATCH", "/previous_record_id", "omit_previous")
            if len(exp.chains) >= MAX_LINEAGES:
                _fail("EXPERIMENT_STORE_LIMIT", "/heads", "reduce_store")
        updated = _copy_experiment_store(exp)
        updated.records[record["record_id"]] = record
        updated.record_raw[record["record_id"]] = raw
        if chain:
            updated.chains[cid]["record_order"].append(record["record_id"])
        else:
            updated.chains[cid] = {"record_order": [record["record_id"]]}
        updated.empty = False
        heads = derive_experiment_heads(updated)
        heads_raw = canonicalize(heads)
        destination = EXPERIMENT_ROOT + "/records/" + cid + "/" + record["record_id"] + ".json"
        staged = _stage_items(
            batch,
            [
                (
                    ("experiments", "records", cid, record["record_id"] + ".json"),
                    destination,
                    raw,
                ),
                (("experiments", "heads.json"), EXPERIMENT_ROOT + "/heads.json", heads_raw),
            ],
        )
        return {
            "record": record,
            "heads": heads,
            "staged": staged,
            "publication": "unpublished",
            "audit_coverage": "not_wired",
            "code_freshness": "not_checked",
            "code_source_verification": "not_checked",
            "ranking": "not_ranked",
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "publication_requires_later_slice",
        }

    return _run_with_store(vault_root, apply, authority_required=True)


def _byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


def _check_paper_id(paper_id):
    if paper_id is None:
        return
    if type(paper_id) is not str or not paper_id or len(paper_id.encode("utf-8")) > PAPER_ID_LIMIT:
        _fail("EXPERIMENT_STATUS_INVALID", "/paper_id", "repair_input")


def _association_status(snapshot, record):
    state, reason, _doc = _association_lookup(snapshot, record)
    if state == "invalid":
        _fail(
            "EXPERIMENT_STORE_INVALID",
            "/source_association",
            "repair_store",
            {"reason": reason},
        )
    return state


def _condition_row(snapshot, domain_store, authority, exp, cid):
    chain = exp.chains[cid]
    head_id = chain["record_order"][-1]
    record = exp.records[head_id]
    association_status = _association_status(snapshot, record)
    source_status = _check_source_digest(snapshot, record["source_digest"], error=False)
    binding_status = _code_binding_status(domain_store, record)
    code_binding = None
    if record["code_binding"] is not None:
        code_binding = {
            "lineage_id": record["code_binding"]["lineage_id"],
            "annotation_id": record["code_binding"]["annotation_id"],
            "repository": record["code_binding"]["repository"],
            "commit": record["code_binding"]["commit"],
            "binding_status": binding_status,
        }
    claims = []
    stale_claims = 0
    bound_claims = 0
    for item in record["claim_refs"]:
        freshness, reason = _claim_freshness(item, authority)
        if freshness == "stale":
            stale_claims += 1
        else:
            bound_claims += 1
        claims.append(
            {
                "claim_id": item["claim_id"],
                "freshness": freshness,
                "stale_reason": reason,
            }
        )
    condition_status = {key: record["conditions"][key]["status"] for key in CONDITION_KEYS}
    unknown_conditions = _byte_sort([key for key, status in condition_status.items() if status == "unknown"])
    critical_unknown = [key for key in unknown_conditions if key in CRITICAL_CONDITIONS]
    stale = (
        association_status != "bound"
        or source_status != "bound"
        or stale_claims > 0
        or (binding_status in STALE_BINDINGS)
    )
    return {
        "condition_id": cid,
        "paper_id": record["paper_id"],
        "source_association_id": record["source_association"]["association_id"],
        "setting_key": record["setting_key"],
        "record_count": len(chain["record_order"]),
        "head_record_id": head_id,
        "head_record_sha256": sha(exp.record_raw[head_id]),
        "content_sha256": record["content_sha256"],
        "recorded_at": record["recorded_at"],
        "association_status": association_status,
        "source_status": source_status,
        "code_binding": code_binding,
        "claims": claims,
        "claim_freshness": {"head_bound": bound_claims, "stale": stale_claims},
        "condition_status": condition_status,
        "unknown_conditions": unknown_conditions,
        "critical_unknown": critical_unknown,
        "record_status": "stale" if stale else "current",
    }


def status_experiment_store(*, vault_root, paper_id=None):
    _check_paper_id(paper_id)

    def apply(snapshot, domain_store, authority):
        exp = _load_experiment_store(snapshot)
        heads = derive_experiment_heads(exp)
        basis = dict(_basis(snapshot, domain_store, authority))
        basis["experiment_store_inventory_sha256"] = experiment_inventory_digest(exp)
        rows = [_condition_row(snapshot, domain_store, authority, exp, cid) for cid in _byte_sort(list(exp.chains))]
        if paper_id is not None:
            known = {row["paper_id"] for row in rows}
            if paper_id not in known:
                _fail(
                    "EXPERIMENT_STATUS_PAPER_UNKNOWN",
                    "/paper_id",
                    "check_paper_id",
                    {"known_paper_count": len(known)},
                )
            rows = [row for row in rows if row["paper_id"] == paper_id]
        next_action = "none"
        if any(row["record_status"] == "stale" for row in rows):
            next_action = "re_record_condition"
        elif any(row["critical_unknown"] for row in rows):
            next_action = "supply_missing_conditions"
        return {
            "basis": basis,
            "heads": heads,
            "paper_filter": paper_id,
            "condition_count": len(rows),
            "conditions": rows,
            "publication": "unpublished",
            "write_kind": "read_only",
            "audit_coverage": "not_wired",
            "code_freshness": "not_checked",
            "code_source_verification": "not_checked",
            "ranking": "not_ranked",
            "scientific_conclusion_contradiction": False,
            "typed_fact_promotion": "none",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": next_action,
        }

    return _run_with_store(vault_root, apply, authority_required=True)
