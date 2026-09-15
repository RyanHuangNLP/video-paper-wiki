"""Article revision store: Vault load, staged scan, identity, heads, and digest."""

from __future__ import annotations

import os
import re
import stat

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_store import (
    DomainStoreError,
    _list_names,
    _open_named_dir,
    _read_record,
    _register_dir,
    _require_regular,
    _stat_child,
    _with_store,
)
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.secure_io import JSON_MAX_BYTES, close_fd, dir_open_flags
from video_paper_wiki.source_semantics_contracts import calendar, sha
from video_paper_wiki.staging import StagingError, resolve_checkout_root

RECORD_SCHEMA = "video-paper-wiki.article-revision-record.v1"
HEADS_SCHEMA = "video-paper-wiki.article-heads.v1"
CONTEXT_SCHEMA = "video-paper-wiki.article-context.v1"
CHECK_SCHEMA = "video-paper-wiki.article-check.v1"
ARTICLE_ROOT = "wiki/meta/articles"
ARTICLE_RE = re.compile(r"^art-[0-9a-f]{20}$")
REVISION_RE = re.compile(r"^arv-[0-9a-f]{20}$")
EVIDENCE_RE = re.compile(r"^aev-[0-9a-f]{20}$")
SECTION_RE = re.compile(r"^s[1-9][0-9]?$")
CITE_MARK = re.compile(r"\[@(aev-[0-9a-f]{20})\]")
CITE_ANY = re.compile(r"\[@([^\]\s]+)\]")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_ARTICLES = 4096
MAX_REVISIONS_PER_ARTICLE = 128
MAX_RECORD_BYTES = JSON_MAX_BYTES
MAX_PAPERS = 8
MAX_QUESTION_CHARS = 512
MAX_QUESTION_BYTES = 4096
MAX_SECTIONS = 16
MAX_TITLE = 300
MAX_GOAL = 2000
MAX_INSTRUCTIONS = 4000
MAX_SECTION_MARKDOWN = 16000
MAX_CITATIONS = 32
MAX_EVIDENCE = 1024
MAX_BIBLIOGRAPHY = 1024
MAX_TABLE_ROWS = 64
EXCERPT_BYTES_BUDGET = 65536
EXCERPT_ITEM_MAX_BYTES = 2048
RELEVANCE_LIMIT = 48
MAX_LABEL = 512
MAX_TOKENS = 1000
PAPER_ID_LIMIT = 256
UNKNOWN_TEXT = "证据不足"
UNWRITTEN_TEXT = "尚未撰写"
PROVISIONAL_LABEL = "模型建议草稿，非正式科学评审。"
ROLES = (
    "question",
    "background",
    "consensus",
    "differences",
    "controversies",
    "comparison",
    "limits",
    "unknowns",
)
REQUIRED_ROLES = (
    "question",
    "consensus",
    "differences",
    "controversies",
    "limits",
    "unknowns",
)
EVIDENCE_KINDS = (
    "claim",
    "claim_span",
    "condition",
    "condition_value",
    "metric_value",
    "code_lineage",
    "comparability",
    "source_version",
)
MESSAGES = {
    "ARTICLE_STORE_INVALID": "article store is invalid",
    "ARTICLE_STORE_LIMIT": "article store exceeds a closed bound",
    "ARTICLE_STORE_HEADS_MISSING": "article store heads.json is missing",
    "ARTICLE_STORE_HEADS_MISMATCH": "article store heads.json does not match derived heads",
    "ARTICLE_STORE_CHAIN_INVALID": "article store chain is invalid",
    "ARTICLE_STORE_CHANGED": "article store changed during read",
    "ARTICLE_CONTEXT_INVALID": "article context input is invalid",
    "ARTICLE_CONTEXT_LIMIT": "article context exceeds a closed bound",
    "ARTICLE_CONTEXT_PAPER_UNKNOWN": "article context paper_id is unknown",
    "ARTICLE_CONTEXT_STALE": "article context is stale relative to the current store",
    "ARTICLE_REVISION_INVALID": "article revision input is invalid",
    "ARTICLE_REVISION_INPUT_MISSING": "required article revision input is missing",
    "ARTICLE_REVISION_PREVIOUS_MISMATCH": "article revision previous revision does not match the chain head",
    "ARTICLE_REVISION_UNCHANGED": "article revision content is unchanged from the chain head",
    "ARTICLE_UNKNOWN": "article_id is unknown",
    "ARTICLE_REVISION_UNKNOWN": "revision_id is unknown",
    "ARTICLE_CHECK_INVALID": "article check input is invalid",
    "ARTICLE_RENDER_INVALID": "article render input is invalid",
}


class ArticleStoreError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


class ArticleStore:
    def __init__(self):
        self.records = {}
        self.record_raw = {}
        self.chains = {}
        self.heads_raw = None
        self.empty = True
        self.locations = {}


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise ArticleStoreError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _file_pointer(article_id, revision_id, *rest):
    pointer = _pointer("wiki", "meta", "articles", "records", article_id, revision_id + ".json")
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
        pointer = "/wiki/meta/articles" + pointer[len("/wiki/meta/domain") :]
        details["instance_pointer"] = pointer
    path = details.get("path")
    if isinstance(path, str) and path.startswith("wiki/meta/domain"):
        details["path"] = "wiki/meta/articles" + path[len("wiki/meta/domain") :]
    prefix = "DOMAIN" + "_STORE_"
    if code.startswith(prefix):
        code = "ARTICLE_STORE_" + code[len(prefix) :]
    if "instance_pointer" not in details:
        details["instance_pointer"] = pointer or "/wiki/meta/articles"
    if "next_action" not in details:
        details["next_action"] = "repair_store"
    raise ArticleStoreError(
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
        _fail("ARTICLE_STORE_CHANGED", "/wiki/meta/articles", "repeat_read", exit_code=75)


def _byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


def _paper_ids(values):
    return _byte_sort(list(dict.fromkeys(values)))


def article_id_from_question(question, paper_ids):
    material = {
        "schema": "video-paper-wiki.article-identity.v1",
        "question": question,
        "paper_ids": _paper_ids(paper_ids),
    }
    try:
        return "art-" + sha(canonicalize(material))[:20]
    except CanonicalJsonError:
        _fail("ARTICLE_STORE_INVALID", "/article_id", "repair_store", {"reason": "canonical_bytes"})


def revision_id_from_record(record):
    payload = {key: value for key, value in record.items() if key != "revision_id"}
    try:
        return "arv-" + sha(canonicalize(payload))[:20]
    except CanonicalJsonError:
        _fail("ARTICLE_STORE_INVALID", "/revision_id", "repair_store", {"reason": "canonical_bytes"})


def content_sha256_from_record(record):
    material = {
        "question": record["question"],
        "paper_ids": record["paper_ids"],
        "title": record["title"],
        "sections": record["sections"],
        "bibliography": record["bibliography"],
        "comparison_table": record["comparison_table"],
    }
    try:
        return sha(canonicalize(material))
    except CanonicalJsonError:
        _fail("ARTICLE_STORE_INVALID", "/content_sha256", "repair_store", {"reason": "canonical_bytes"})


def evidence_id_for(kind, identity):
    material = {"kind": kind}
    material.update(identity)
    try:
        return "aev-" + sha(canonicalize(material))[:20]
    except CanonicalJsonError:
        _fail("ARTICLE_STORE_INVALID", "/evidence_id", "repair_store", {"reason": "canonical_bytes"})


def derive_article_heads(store):
    heads = {}
    for art in sorted(store.chains):
        chain = store.chains[art]
        rid = chain["record_order"][-1]
        heads[art] = {
            "revision_id": rid,
            "record_sha256": sha(store.record_raw[rid]),
        }
    return {"schema": HEADS_SCHEMA, "heads": heads}


def article_inventory_digest(store):
    rows = []
    for doc in store.records.values():
        path = ARTICLE_ROOT + "/records/" + doc["article_id"] + "/" + doc["revision_id"] + ".json"
        raw = store.record_raw[doc["revision_id"]]
        rows.append([path, sha(raw), len(raw)])
    if store.heads_raw is not None:
        rows.append([ARTICLE_ROOT + "/heads.json", sha(store.heads_raw), len(store.heads_raw)])
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return sha(canonicalize(rows))


def _copy_article_store(store):
    out = ArticleStore()
    out.records = dict(store.records)
    out.record_raw = dict(store.record_raw)
    out.chains = {
        art: {"record_order": list(chain["record_order"])} for art, chain in store.chains.items()
    }
    out.heads_raw = store.heads_raw
    out.empty = store.empty
    out.locations = dict(store.locations)
    return out


def _linear_record_chain(rows, article_id, known):
    by_id = {}
    for row in rows:
        key = row["revision_id"]
        if key in by_id:
            _fail(
                "ARTICLE_STORE_CHAIN_INVALID",
                _file_pointer(row["article_id"], key),
                "repair_store",
                {"reason": "duplicate"},
            )
        by_id[key] = row
    roots = []
    children = {}
    for row in rows:
        previous = row["previous_revision_id"]
        pointer = _file_pointer(row["article_id"], row["revision_id"], "previous_revision_id")
        if previous is None:
            roots.append(row["revision_id"])
            continue
        parent = by_id.get(previous)
        if parent is None:
            _fail(
                "ARTICLE_STORE_CHAIN_INVALID",
                pointer,
                "repair_store",
                {"reason": "previous"},
            )
        if parent["article_id"] != row["article_id"] or row["article_id"] != article_id:
            _fail("ARTICLE_STORE_CHAIN_INVALID", pointer, "repair_store", {"reason": "previous"})
        if previous in children:
            _fail("ARTICLE_STORE_CHAIN_INVALID", pointer, "repair_store", {"reason": "fork"})
        children[previous] = row["revision_id"]
        if calendar(parent["recorded_at"]) > calendar(row["recorded_at"]):
            _fail(
                "ARTICLE_STORE_CHAIN_INVALID",
                _file_pointer(row["article_id"], row["revision_id"], "recorded_at"),
                "repair_store",
                {"reason": "timestamp_order"},
            )
    chain_pointer = _pointer("wiki", "meta", "articles", "records", article_id)
    if rows and len(roots) != 1:
        _fail("ARTICLE_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "genesis"})
    if not rows:
        return []
    seen = []
    cursor = roots[0]
    visiting = set()
    while cursor is not None:
        if cursor in visiting:
            _fail("ARTICLE_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "cycle"})
        visiting.add(cursor)
        seen.append(cursor)
        cursor = children.get(cursor)
    if len(seen) != len(rows):
        _fail("ARTICLE_STORE_CHAIN_INVALID", chain_pointer, "repair_store", {"reason": "orphan"})
    return seen


def _validate_record_identity(doc, pointer):
    expected_art = article_id_from_question(doc["question"], doc["paper_ids"])
    if doc["article_id"] != expected_art:
        _fail("ARTICLE_STORE_INVALID", pointer + "/article_id", "repair_store", {"reason": "identity"})
    if doc["revision_id"] != revision_id_from_record(doc):
        _fail("ARTICLE_STORE_INVALID", pointer + "/revision_id", "repair_store", {"reason": "identity"})
    if doc["content_sha256"] != content_sha256_from_record(doc):
        _fail("ARTICLE_STORE_INVALID", pointer + "/content_sha256", "repair_store", {"reason": "identity"})


def _validate_chains(store):
    groups = {}
    for doc in store.records.values():
        pointer = _file_pointer(doc["article_id"], doc["revision_id"])
        _validate_record_identity(doc, pointer)
        groups.setdefault(doc["article_id"], []).append(doc)
    for art in sorted(groups):
        order = _linear_record_chain(groups[art], art, store.records)
        previous_sha = None
        for rid in order:
            current = store.records[rid]["content_sha256"]
            if previous_sha is not None and current == previous_sha:
                _fail(
                    "ARTICLE_REVISION_UNCHANGED",
                    _file_pointer(art, rid, "content_sha256"),
                    "revise_document",
                )
            previous_sha = current
        if len(order) > MAX_REVISIONS_PER_ARTICLE:
            _fail(
                "ARTICLE_STORE_LIMIT",
                _pointer("wiki", "meta", "articles", "records", art),
                "reduce_store",
            )
        store.chains[art] = {"record_order": order}
    if len(store.chains) > MAX_ARTICLES:
        _fail("ARTICLE_STORE_LIMIT", "/wiki/meta/articles", "reduce_store", {"reason": "articles"})


def _scan_records(snapshot, root_fd, store, *, relative_kind, pointer_kind, location):
    st = _call_store(lambda: _stat_child(root_fd, "records"))
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        _fail("ARTICLE_STORE_INVALID", pointer_kind, "repair_store", {"reason": "symlink", "path": relative_kind})
    if not stat.S_ISDIR(st.st_mode):
        _fail("ARTICLE_STORE_INVALID", pointer_kind, "repair_store", {"reason": "entry_kind", "path": relative_kind})
    try:
        kind_fd = os.open("records", dir_open_flags(), dir_fd=root_fd)
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", pointer_kind, "repeat_read", exit_code=75)
    try:
        _call_store(lambda: _register_dir(snapshot, relative_kind, kind_fd))
        articles = _call_store(lambda: _list_names(kind_fd))
        if not articles:
            return
        for article_name in articles:
            lineage_rel = relative_kind + "/" + article_name
            lineage_ptr = pointer_kind + "/" + article_name
            lst = _call_store(lambda name=article_name: _stat_child(kind_fd, name))
            if lst is None:
                _fail("ARTICLE_STORE_CHANGED", lineage_ptr, "repeat_read", exit_code=75)
            if stat.S_ISLNK(lst.st_mode):
                _fail("ARTICLE_STORE_INVALID", lineage_ptr, "repair_store", {"reason": "symlink", "path": lineage_rel})
            if not stat.S_ISDIR(lst.st_mode):
                _fail(
                    "ARTICLE_STORE_INVALID",
                    lineage_ptr,
                    "repair_store",
                    {"reason": "entry_kind", "path": lineage_rel},
                )
            if ARTICLE_RE.fullmatch(article_name) is None:
                _fail(
                    "ARTICLE_STORE_INVALID",
                    lineage_ptr,
                    "repair_store",
                    {"reason": "unknown_entry", "path": lineage_rel},
                )
            try:
                child_fd = os.open(article_name, dir_open_flags(), dir_fd=kind_fd)
            except OSError:
                _fail("ARTICLE_STORE_CHANGED", lineage_ptr, "repeat_read", exit_code=75)
            try:
                _call_store(lambda rel=lineage_rel, fd=child_fd: _register_dir(snapshot, rel, fd))
                files = _call_store(lambda: _list_names(child_fd))
                if not files:
                    _fail(
                        "ARTICLE_STORE_INVALID",
                        lineage_ptr,
                        "repair_store",
                        {"reason": "empty_lineage", "path": lineage_rel},
                    )
                if len(files) > MAX_REVISIONS_PER_ARTICLE:
                    _fail("ARTICLE_STORE_LIMIT", lineage_ptr, "reduce_store", {"path": lineage_rel})
                for filename in files:
                    file_rel = lineage_rel + "/" + filename
                    file_ptr = lineage_ptr + "/" + filename
                    fst = _call_store(lambda name=filename: _stat_child(child_fd, name))
                    _call_store(lambda st=fst, rel=file_rel: _require_regular(st, rel))
                    stem, sep, ext = filename.partition(".")
                    if sep != "." or ext != "json" or REVISION_RE.fullmatch(stem) is None:
                        _fail(
                            "ARTICLE_STORE_INVALID",
                            file_ptr,
                            "repair_store",
                            {"reason": "unknown_entry", "path": file_rel},
                        )
                    doc, raw = _call_store(
                        lambda rel=file_rel, ptr=file_ptr: _read_record(snapshot, rel, RECORD_SCHEMA, ptr)
                    )
                    if doc["revision_id"] != stem:
                        _fail(
                            "ARTICLE_STORE_INVALID",
                            file_ptr,
                            "repair_store",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    if doc["article_id"] != article_name:
                        _fail(
                            "ARTICLE_STORE_INVALID",
                            file_ptr,
                            "repair_store",
                            {"reason": "path_identity", "path": file_rel},
                        )
                    if doc["revision_id"] in store.records:
                        _fail(
                            "ARTICLE_STORE_INVALID",
                            file_ptr,
                            "repair_store",
                            {"reason": "duplicate_id", "path": file_rel},
                        )
                    store.records[doc["revision_id"]] = doc
                    store.record_raw[doc["revision_id"]] = raw
                    store.locations[doc["revision_id"]] = location
            finally:
                close_fd(child_fd)
    finally:
        close_fd(kind_fd)


def _read_optional(snapshot, relative, pointer):
    try:
        return snapshot.read_optional(relative, max_bytes=MAX_RECORD_BYTES)
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", pointer, "repeat_read", {"path": relative}, exit_code=75)


def _load_article_store(snapshot):
    store = ArticleStore()
    art_fd, fds = _call_store(lambda: _open_named_dir(snapshot, ("wiki", "meta", "articles")))
    try:
        if art_fd is None:
            return store
        names = _call_store(lambda: _list_names(art_fd))
        allowed = {"records", "heads.json"}
        extra = [name for name in names if name not in allowed]
        if extra:
            _fail(
                "ARTICLE_STORE_INVALID",
                _pointer("wiki", "meta", "articles", extra[0]),
                "repair_store",
                {"reason": "unknown_entry", "name": extra[0]},
            )
        if "records" in names:
            _scan_records(
                snapshot,
                art_fd,
                store,
                relative_kind=ARTICLE_ROOT + "/records",
                pointer_kind="/wiki/meta/articles/records",
                location="vault_store",
            )
        heads_raw = None
        if "heads.json" in names:
            st = _call_store(lambda: _stat_child(art_fd, "heads.json"))
            _call_store(lambda: _require_regular(st, ARTICLE_ROOT + "/heads.json"))
            heads_doc, heads_raw = _call_store(
                lambda: _read_record(
                    snapshot,
                    ARTICLE_ROOT + "/heads.json",
                    HEADS_SCHEMA,
                    "/wiki/meta/articles/heads.json",
                )
            )
            store.heads_raw = heads_raw
        store.empty = not store.records and heads_raw is None
        if store.records:
            if heads_raw is None:
                _fail("ARTICLE_STORE_HEADS_MISSING", "/wiki/meta/articles/heads.json", "restore_heads")
        _validate_chains(store)
        derived = derive_article_heads(store)
        derived_raw = canonicalize(derived)
        if heads_raw is None:
            if derived["heads"]:
                _fail("ARTICLE_STORE_HEADS_MISSING", "/wiki/meta/articles/heads.json", "restore_heads")
        elif heads_raw != derived_raw:
            _fail("ARTICLE_STORE_HEADS_MISMATCH", "/wiki/meta/articles/heads.json", "restore_heads")
        return store
    finally:
        for fd in reversed(fds):
            close_fd(fd)


def _map_staged_snapshot(exc, pointer):
    code = getattr(exc, "code", "ARTICLE_STORE_INVALID")
    details = dict(getattr(exc, "details", {}) or {})
    if code in {"AUDIT_RACE", "SOURCE_CHANGED"} or getattr(exc, "exit_code", 2) == 75:
        _fail("ARTICLE_STORE_CHANGED", pointer, "repeat_read", dict(details), exit_code=75)
    if code == "WORK_PATH_UNSAFE":
        raise ArticleStoreError(
            code,
            getattr(exc, "message", code),
            {"instance_pointer": pointer, "next_action": "repair_input", **details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    _fail(
        "ARTICLE_STORE_INVALID",
        pointer,
        "repair_store",
        {"prior_code": code, **details},
        exit_code=getattr(exc, "exit_code", 2),
    )


def _load_staged_articles(batch):
    store = ArticleStore()
    if batch is None:
        return store
    path = resolve_checkout_root() / ".work" / batch / "articles"
    try:
        st = path.lstat()
    except FileNotFoundError:
        return store
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", "/articles", "repeat_read", exit_code=75)
    if stat.S_ISLNK(st.st_mode):
        _fail("ARTICLE_STORE_INVALID", "/articles", "repair_store", {"reason": "symlink", "path": "articles"})
    if not stat.S_ISDIR(st.st_mode):
        _fail("ARTICLE_STORE_INVALID", "/articles", "repair_store", {"reason": "entry_kind", "path": "articles"})
    try:
        snapshot = _Snapshot(path)
    except ContractError as exc:
        _map_staged_snapshot(exc, "/articles")
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", "/articles", "repeat_read", exit_code=75)
    try:
        names = _call_store(lambda: _list_names(snapshot.root_fd))
        allowed = {"records", "render"}
        extra = [name for name in names if name not in allowed]
        if extra:
            _fail(
                "ARTICLE_STORE_INVALID",
                _pointer("articles", extra[0]),
                "repair_store",
                {"reason": "unknown_entry", "name": extra[0]},
            )
        if "records" in names:
            _scan_records(
                snapshot,
                snapshot.root_fd,
                store,
                relative_kind="records",
                pointer_kind="/articles/records",
                location="staged",
            )
        for rid, doc in store.records.items():
            pointer = _pointer("articles", "records", doc["article_id"], rid + ".json")
            _validate_record_identity(doc, pointer)
        store.empty = not store.records
        return store
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", "/articles", "repeat_read", exit_code=75)


def _merge(vault_store, staged):
    out = _copy_article_store(vault_store)
    items = list(staged.records.values())
    items.sort(
        key=lambda doc: (
            doc["recorded_at"].encode("utf-8"),
            doc["article_id"].encode("utf-8"),
            doc["revision_id"].encode("utf-8"),
        )
    )
    for doc in items:
        art = doc["article_id"]
        rid = doc["revision_id"]
        pointer = _pointer("articles", "records", art, rid + ".json")
        prev = doc["previous_revision_id"]
        chain = out.chains.get(art)
        if chain is None:
            if prev is not None:
                _fail(
                    "ARTICLE_STORE_CHAIN_INVALID",
                    pointer,
                    "repair_store",
                    {"reason": "staged_previous"},
                )
            out.chains[art] = {"record_order": [rid]}
        else:
            head = chain["record_order"][-1]
            if prev != head:
                _fail(
                    "ARTICLE_STORE_CHAIN_INVALID",
                    pointer,
                    "repair_store",
                    {"reason": "staged_previous"},
                )
            parent = out.records[head]
            if calendar(parent["recorded_at"]) > calendar(doc["recorded_at"]):
                _fail(
                    "ARTICLE_STORE_CHAIN_INVALID",
                    pointer + "/recorded_at",
                    "repair_store",
                    {"reason": "timestamp_order"},
                )
            chain["record_order"].append(rid)
            if len(chain["record_order"]) > MAX_REVISIONS_PER_ARTICLE:
                _fail("ARTICLE_STORE_LIMIT", _pointer("articles", "records", art), "reduce_store")
        if rid in out.records:
            _fail("ARTICLE_STORE_INVALID", pointer, "repair_store", {"reason": "duplicate_id"})
        out.records[rid] = doc
        out.record_raw[rid] = staged.record_raw[rid]
        out.locations[rid] = staged.locations.get(rid, "staged")
    if len(out.chains) > MAX_ARTICLES:
        _fail("ARTICLE_STORE_LIMIT", "/heads", "reduce_store")
    out.empty = not out.records and out.heads_raw is None
    return out


def _run_with_store(vault_root, function, *, authority_required=True):
    try:
        return _with_store(vault_root, function, authority_required=authority_required)
    except ArticleStoreError:
        raise
    except DomainStoreError:
        raise
    except StagingError:
        raise
    except OSError:
        _fail("ARTICLE_STORE_CHANGED", "/wiki/meta/articles", "repeat_read", exit_code=75)


def _lookup_revision(merged, article_id, revision_id, *, unknown_article="ARTICLE_UNKNOWN"):
    if type(article_id) is not str or ARTICLE_RE.fullmatch(article_id) is None:
        _fail("ARTICLE_CHECK_INVALID", "/article_id", "repair_input")
    if type(revision_id) is not str or REVISION_RE.fullmatch(revision_id) is None:
        _fail("ARTICLE_CHECK_INVALID", "/revision_id", "repair_input")
    chain = merged.chains.get(article_id)
    if chain is None:
        _fail(unknown_article, "/article_id", "check_article_id")
    if revision_id not in merged.records or merged.records[revision_id]["article_id"] != article_id:
        head = chain["record_order"][-1]
        raise ArticleStoreError(
            "ARTICLE_REVISION_UNKNOWN",
            MESSAGES["ARTICLE_REVISION_UNKNOWN"],
            {
                "instance_pointer": "/revision_id",
                "next_action": "check_revision_id",
                "head_revision_id": head,
            },
        )
    record = merged.records[revision_id]
    location = merged.locations.get(revision_id, "vault_store")
    return record, location, chain
