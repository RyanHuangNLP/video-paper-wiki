"""Compile and inspect unpublished article publication payloads. Vault writes are forbidden."""

from __future__ import annotations

import json
import os
import stat

from video_paper_wiki.article_context import ArticleContextError
from video_paper_wiki.article_revision import ArticleRevisionError, check_revision_view
from video_paper_wiki.article_store import (
    ARTICLE_ROOT,
    ArticleStore,
    ArticleStoreError,
    HEADS_SCHEMA,
    MAX_RECORD_BYTES,
    RECORD_SCHEMA,
    _byte_sort,
    _copy_article_store,
    _load_article_store,
    _load_staged_articles,
    _merge,
    _run_with_store,
    _validate_record_identity,
    article_inventory_digest,
    derive_article_heads,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_publication import CONTENT_NAME_RE, MAX_STAGED_BYTES, MAX_STAGED_RECORDS
from video_paper_wiki.domain_store import _batch, derive_domain_heads
from video_paper_wiki.experiment_publication import _experiment_basis
from video_paper_wiki.experiment_store import _load_experiment_store
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.secure_io import SecureIOError, close_fd, dir_open_flags, parse_strict_json
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

REQUEST_SCHEMA = "video-paper-wiki.article-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.article-publication-inspection.v1"
COMPILE_COMMAND = "articles.compile"
INSPECT_COMMAND = "articles.publish-inspect"
ARTICLE_PREFIX = ARTICLE_ROOT + "/"
MESSAGES = {
    "ARTICLE_COMPILE_INVALID": "article compile input is invalid",
    "ARTICLE_COMPILE_LIMIT": "article compile input exceeds a closed bound",
    "ARTICLE_COMPILE_EMPTY": "article compile batch has no record files",
    "ARTICLE_COMPILE_ALREADY_PUBLISHED": "article compile target already exists in the store",
    "ARTICLE_COMPILE_INCOMPLETE": "article compile head still has unwritten sections",
    "ARTICLE_COMPILE_NOT_CURRENT": "article compile head check is not current",
    "ARTICLE_COMPILE_CHANGED": "article compile input changed during read",
    "ARTICLE_PUBLICATION_INVALID": "article publication request is invalid",
    "ARTICLE_PUBLICATION_CONTENT_MISMATCH": "article publication content does not match the request",
    "ARTICLE_PUBLICATION_STALE": "article publication request basis is stale",
    "ARTICLE_PUBLICATION_MISMATCH": "article publication request does not match the recomputed write set",
}


class ArticlePublicationError(Exception):
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
    raise ArticlePublicationError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _map_schema(exc, code, next_action):
    pointer = exc.details.get("instance_pointer") or ""
    if exc.code in {"SOURCE_SEMANTICS_LIMIT", "TRANSACTION_LIMIT_EXCEEDED"}:
        if code.startswith("ARTICLE_COMPILE"):
            code = "ARTICLE_COMPILE_LIMIT"
            next_action = "reduce_batch"
        else:
            code = "ARTICLE_PUBLICATION_INVALID"
    extra = dict(exc.details)
    if code == "ARTICLE_COMPILE_INVALID" and "reason" not in extra:
        extra["reason"] = "schema"
    raise ArticlePublicationError(
        code,
        MESSAGES.get(code, MESSAGES["ARTICLE_COMPILE_INVALID"]),
        {"instance_pointer": pointer, "next_action": next_action, **extra},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _map_work(exc, pointer, *, invalid="ARTICLE_COMPILE_INVALID", changed="ARTICLE_COMPILE_CHANGED"):
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
        limit = "ARTICLE_COMPILE_LIMIT" if invalid.startswith("ARTICLE_COMPILE") else invalid
        _fail(
            limit,
            pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
            "reduce_batch",
            dict(details),
        )
    if code == "WORK_PATH_UNSAFE":
        raise ArticlePublicationError(
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
        limit = "ARTICLE_COMPILE_LIMIT" if invalid.startswith("ARTICLE_COMPILE") else invalid
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
        limit = "ARTICLE_COMPILE_LIMIT" if invalid.startswith("ARTICLE_COMPILE") else invalid
        _fail(limit, pointer, "reduce_batch", {"path": relative, "size_bytes": len(raw)})
    return raw


def _parse_record(raw, schema, pointer, relative, *, invalid):
    try:
        doc = parse_strict_json(raw, invalid_code=invalid)
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "ARTICLE_COMPILE_LIMIT" if invalid.startswith("ARTICLE_COMPILE") and reason == "depth" else invalid
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


def _work_article_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "articles"
    return _open_snapshot(
        path,
        "/articles",
        invalid="ARTICLE_COMPILE_CHANGED",
        changed="ARTICLE_COMPILE_CHANGED",
    )


def _publication_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "article-publication"
    return _open_snapshot(
        path,
        "/article-publication",
        invalid="ARTICLE_PUBLICATION_INVALID",
        changed="ARTICLE_PUBLICATION_INVALID",
    )


def _inventory_rows(store):
    rows = []
    for doc in store.records.values():
        path = ARTICLE_PREFIX + "records/" + doc["article_id"] + "/" + doc["revision_id"] + ".json"
        raw = store.record_raw[doc["revision_id"]]
        rows.append([path, sha(raw), len(raw)])
    if store.heads_raw is not None:
        rows.append([ARTICLE_ROOT + "/heads.json", sha(store.heads_raw), len(store.heads_raw)])
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    return rows


def _article_basis(snapshot, domain_store, authority, exp, vault):
    basis = dict(_experiment_basis(snapshot, domain_store, authority, exp))
    basis["article_store_inventory_sha256"] = article_inventory_digest(vault)
    return basis


def _payload(path, mode, before, raw):
    digest = sha(raw)
    return {
        "path": path,
        "mode": mode,
        "before_sha256": before,
        "after_sha256": digest,
        "size_bytes": len(raw),
        "content_file": "article-publication/content/" + digest,
    }


def _reread_staged(work, staged):
    for rid, doc in staged.records.items():
        relative = "records/" + doc["article_id"] + "/" + rid + ".json"
        pointer = "/articles/" + relative
        raw = _read_bytes(
            work,
            relative,
            pointer,
            invalid="ARTICLE_COMPILE_CHANGED",
            changed="ARTICLE_COMPILE_CHANGED",
        )
        if raw != staged.record_raw[rid]:
            _fail("ARTICLE_COMPILE_CHANGED", pointer, "repeat_read", {"path": relative}, exit_code=75)


def _build_request(snapshot, domain_store, authority, exp, heads, vault, staged, batch):
    for rid, doc in staged.records.items():
        dest = ARTICLE_PREFIX + "records/" + doc["article_id"] + "/" + rid + ".json"
        if rid in vault.records:
            extra = {"article_id": doc["article_id"], "revision_id": rid, "path": dest}
            _fail(
                "ARTICLE_COMPILE_ALREADY_PUBLISHED",
                _pointer(*(dest.split("/"))),
                "discard_batch",
                extra,
            )
    merged = _merge(vault, staged)
    touched = _byte_sort({doc["article_id"] for doc in staged.records.values()})
    compiled_heads = []
    for art in touched:
        head_rid = merged.chains[art]["record_order"][-1]
        if merged.locations.get(head_rid) != "staged":
            _fail(
                "ARTICLE_COMPILE_INVALID",
                "/articles/records/" + art,
                "repair_input",
                {"reason": "head_not_staged", "article_id": art, "revision_id": head_rid},
            )
        record = merged.records[head_rid]
        unwritten = record["progress"]["unwritten"]
        if unwritten > 0:
            _fail(
                "ARTICLE_COMPILE_INCOMPLETE",
                "/articles/records/" + art + "/" + head_rid + ".json/progress/unwritten",
                "write_unwritten_sections",
                {"article_id": art, "revision_id": head_rid, "unwritten": unwritten},
            )
        try:
            view = check_revision_view(snapshot, domain_store, authority, exp, heads, record, "staged")
        except (ArticleRevisionError, ArticleContextError) as exc:
            exc.details["article_id"] = art
            exc.details["revision_id"] = head_rid
            raise
        if view["check_status"] != "current":
            _fail(
                "ARTICLE_COMPILE_NOT_CURRENT",
                "/articles/records/" + art + "/" + head_rid + ".json",
                view["next_action"],
                {
                    "article_id": art,
                    "revision_id": head_rid,
                    "check_status": view["check_status"],
                    "basis_match": view["basis_match"],
                    "counts": view["counts"],
                    "affected_sections": view["affected_sections"],
                    "table_affected": view["table_affected"],
                    "citation_consistency": view["citation_consistency"],
                },
            )
        previous_vault = None
        if art in vault.chains:
            previous_vault = vault.chains[art]["record_order"][-1]
        staged_count = 0
        for doc in staged.records.values():
            if doc["article_id"] == art:
                staged_count += 1
        compiled_heads.append(
            {
                "article_id": art,
                "revision_id": head_rid,
                "record_sha256": sha(merged.record_raw[head_rid]),
                "previous_vault_revision_id": previous_vault,
                "staged_revision_count": staged_count,
                "progress": record["progress"],
                "check_status": "current",
            }
        )
    payloads = []
    content = {}
    for rid, doc in staged.records.items():
        dest = ARTICLE_PREFIX + "records/" + doc["article_id"] + "/" + rid + ".json"
        item = _payload(dest, "create", None, staged.record_raw[rid])
        payloads.append(item)
        content[item["after_sha256"]] = staged.record_raw[rid]
    prospective = _copy_article_store(merged)
    heads_raw = canonicalize(derive_article_heads(prospective))
    prospective.heads_raw = heads_raw
    if vault.heads_raw is None:
        heads_mode = "create"
        heads_before = None
    else:
        heads_mode = "replace"
        heads_before = sha(vault.heads_raw)
    heads_item = _payload(ARTICLE_ROOT + "/heads.json", heads_mode, heads_before, heads_raw)
    payloads.append(heads_item)
    content[heads_item["after_sha256"]] = heads_raw
    payloads.sort(key=lambda item: item["path"].encode("utf-8"))
    basis = _article_basis(snapshot, domain_store, authority, exp, vault)
    prospective_inventory = article_inventory_digest(prospective)
    request = {
        "schema": REQUEST_SCHEMA,
        "batch_id": batch,
        "kind": "articles",
        "basis": basis,
        "prospective_inventory_sha256": prospective_inventory,
        "touched_articles": touched,
        "compiled_heads": compiled_heads,
        "payloads": payloads,
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
        "next_action": "inspect_article_publication",
    }
    try:
        request_raw = canonicalize(request)
        sealed = json.loads(request_raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("ARTICLE_COMPILE_INVALID", "", "repair_input", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, REQUEST_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "ARTICLE_COMPILE_INVALID", "repair_input")
    if len(request_raw) > MAX_RECORD_BYTES:
        _fail("ARTICLE_COMPILE_LIMIT", "/request", "reduce_batch", {"size_bytes": len(request_raw)})
    changed_paths = [item["path"] for item in sealed["payloads"]]
    data = {
        "state": "article_publication_prepared",
        "batch_id": batch,
        "basis": sealed["basis"],
        "prospective_inventory_sha256": sealed["prospective_inventory_sha256"],
        "request_path": ".work/" + batch + "/article-publication/request.json",
        "request_sha256": sha(request_raw),
        "touched_articles": list(sealed["touched_articles"]),
        "compiled_heads": list(sealed["compiled_heads"]),
        "changed_paths": changed_paths,
        "payload_count": len(sealed["payloads"]),
        "publication": "unpublished",
        "applied": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "backup_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_article_publication",
    }
    return {"request": sealed, "request_raw": request_raw, "content": content, "data": data}


def _stage_publication(batch, built):
    target = resolve_checkout_root() / ".work" / batch / "article-publication" / "request.json"
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
    stage_bytes(batch_id=batch, relative=("article-publication", "request.json"), data=built["request_raw"])
    written = set()
    for item in built["request"]["payloads"]:
        digest = item["after_sha256"]
        if digest in written:
            continue
        written.add(digest)
        stage_bytes(
            batch_id=batch,
            relative=("article-publication", "content", digest),
            data=built["content"][digest],
        )


def _verify_work(snapshot, *, changed):
    try:
        snapshot.verify()
    except ContractError as exc:
        _map_work(exc, "/articles", invalid=changed, changed=changed)
    except OSError:
        _fail(changed, "/articles", "repeat_read", exit_code=75)


def compile_article_publication(*, vault_root, batch_id):
    batch = _batch(batch_id, "/batch_id")

    def apply(snapshot, domain_store, authority):
        try:
            vault = _load_article_store(snapshot)
            exp = _load_experiment_store(snapshot)
            heads = derive_domain_heads(domain_store)
            staged = _load_staged_articles(batch)
            if not staged.records:
                _fail("ARTICLE_COMPILE_EMPTY", "/articles", "import_revision")
            if len(staged.records) > MAX_STAGED_RECORDS:
                _fail(
                    "ARTICLE_COMPILE_LIMIT",
                    "/articles/records",
                    "reduce_batch",
                    {"count": len(staged.records), "limit": MAX_STAGED_RECORDS},
                )
            total = 0
            for raw in staged.record_raw.values():
                total += len(raw)
            if total > MAX_STAGED_BYTES:
                _fail("ARTICLE_COMPILE_LIMIT", "/articles/records", "reduce_batch")
            work = _work_article_snapshot(batch)
            try:
                _reread_staged(work, staged)
                built = _build_request(snapshot, domain_store, authority, exp, heads, vault, staged, batch)
                _verify_work(work, changed="ARTICLE_COMPILE_CHANGED")
                _stage_publication(batch, built)
                _verify_work(work, changed="ARTICLE_COMPILE_CHANGED")
                return built["data"]
            finally:
                work.close()
        except OSError:
            _fail("ARTICLE_COMPILE_CHANGED", "/articles", "repeat_read", exit_code=75)

    return _run_with_store(vault_root, apply, authority_required=True)


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
        if parts != (batch, "article-publication", "request.json"):
            raise ValueError
        return path, batch
    except (ValueError, StagingError) as exc:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "prepared input must use the fixed article publication slot",
            {"path": os.fspath(value)},
        ) from exc


def _article_suffix(path):
    if type(path) is not str or not path.startswith(ARTICLE_PREFIX):
        _fail("ARTICLE_PUBLICATION_INVALID", "/payloads", "repair_input", {"path": path})
    return path[len(ARTICLE_PREFIX) :]


def _staged_from_content(request, content):
    staged = ArticleStore()
    for index, item in enumerate(request["payloads"]):
        pointer = "/payloads/" + str(index)
        digest = item["after_sha256"]
        raw = content.get(digest)
        if raw is None:
            _fail("ARTICLE_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        if sha(raw) != digest or len(raw) != item["size_bytes"]:
            _fail("ARTICLE_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": item["path"]})
        suffix = _article_suffix(item["path"])
        if suffix == "heads.json":
            _parse_record(raw, HEADS_SCHEMA, pointer, item["path"], invalid="ARTICLE_PUBLICATION_INVALID")
            if staged.heads_raw is not None:
                _fail("ARTICLE_PUBLICATION_INVALID", pointer, "repair_input", {"reason": "duplicate_heads"})
            staged.heads_raw = raw
            continue
        if suffix.startswith("records/"):
            doc = _parse_record(
                raw, RECORD_SCHEMA, pointer, item["path"], invalid="ARTICLE_PUBLICATION_INVALID"
            )
            expected = "records/" + doc["article_id"] + "/" + doc["revision_id"] + ".json"
            try:
                _validate_record_identity(doc, pointer)
            except ArticleStoreError:
                _fail("ARTICLE_PUBLICATION_MISMATCH", pointer, "recompile", {"path": item["path"]})
            if suffix != expected:
                _fail("ARTICLE_PUBLICATION_MISMATCH", pointer, "recompile", {"path": item["path"]})
            staged.records[doc["revision_id"]] = doc
            staged.record_raw[doc["revision_id"]] = raw
            staged.locations[doc["revision_id"]] = "staged"
            continue
        _fail("ARTICLE_PUBLICATION_INVALID", pointer, "repair_input", {"path": item["path"]})
    if staged.heads_raw is None or not staged.records:
        _fail("ARTICLE_PUBLICATION_INVALID", "/payloads", "repair_input", {"reason": "incomplete"})
    staged.empty = not staged.records
    return staged


def _load_publication(snapshot, batch):
    names = _list_names(snapshot.root_fd, "/article-publication", changed="ARTICLE_PUBLICATION_INVALID")
    extra = [name for name in names if name not in {"request.json", "content"}]
    if extra:
        _fail(
            "ARTICLE_PUBLICATION_INVALID",
            _pointer("article-publication", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "article-publication/" + extra[0]},
        )
    if "request.json" not in names:
        _fail(
            "ARTICLE_PUBLICATION_INVALID",
            "/article-publication/request.json",
            "repair_input",
            {"reason": "missing", "path": "article-publication/request.json"},
        )
    st = _stat_child(snapshot.root_fd, "request.json")
    _require_regular(
        st,
        "article-publication/request.json",
        invalid="ARTICLE_PUBLICATION_INVALID",
        changed="ARTICLE_PUBLICATION_INVALID",
    )
    request_raw = _read_bytes(
        snapshot,
        "request.json",
        "/article-publication/request.json",
        invalid="ARTICLE_PUBLICATION_INVALID",
        changed="ARTICLE_PUBLICATION_INVALID",
    )
    request = _parse_record(
        request_raw,
        REQUEST_SCHEMA,
        "/article-publication/request.json",
        "article-publication/request.json",
        invalid="ARTICLE_PUBLICATION_INVALID",
    )
    if request["batch_id"] != batch:
        _fail(
            "ARTICLE_PUBLICATION_INVALID",
            "/batch_id",
            "repair_input",
            {"reason": "batch_id", "path": "article-publication/request.json"},
        )
    if "content" not in names:
        _fail(
            "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
            "/article-publication/content",
            "recompile",
            {"path": "article-publication/content"},
        )
    cst = _stat_child(snapshot.root_fd, "content")
    if cst is None:
        _fail(
            "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
            "/article-publication/content",
            "recompile",
            {"path": "article-publication/content"},
        )
    if stat.S_ISLNK(cst.st_mode) or not stat.S_ISDIR(cst.st_mode):
        _fail(
            "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
            "/article-publication/content",
            "recompile",
            {"reason": "entry_kind", "path": "article-publication/content"},
        )
    content_fd = os.open("content", dir_open_flags(), dir_fd=snapshot.root_fd)
    try:
        snapshot.directories.setdefault("content", os.fstat(content_fd))
        content_names = _list_names(
            content_fd, "/article-publication/content", changed="ARTICLE_PUBLICATION_INVALID"
        )
        expected = {item["after_sha256"] for item in request["payloads"]}
        if set(content_names) != expected:
            _fail(
                "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
                "/article-publication/content",
                "recompile",
                {"path": "article-publication/content"},
            )
        content = {}
        for name in content_names:
            relative = "content/" + name
            pointer = "/article-publication/" + relative
            if CONTENT_NAME_RE.fullmatch(name) is None:
                _fail("ARTICLE_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            fst = _stat_child(content_fd, name)
            _require_regular(
                fst,
                "article-publication/" + relative,
                invalid="ARTICLE_PUBLICATION_CONTENT_MISMATCH",
                changed="ARTICLE_PUBLICATION_INVALID",
            )
            raw = _read_bytes(
                snapshot,
                relative,
                pointer,
                invalid="ARTICLE_PUBLICATION_CONTENT_MISMATCH",
                changed="ARTICLE_PUBLICATION_INVALID",
            )
            if sha(raw) != name:
                _fail("ARTICLE_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile", {"path": relative})
            content[name] = raw
        for index, item in enumerate(request["payloads"]):
            raw = content[item["after_sha256"]]
            if sha(raw) != item["after_sha256"] or len(raw) != item["size_bytes"]:
                _fail(
                    "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index),
                    "recompile",
                    {"path": item["content_file"]},
                )
            expected_file = "article-publication/content/" + item["after_sha256"]
            if item["content_file"] != expected_file:
                _fail(
                    "ARTICLE_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index) + "/content_file",
                    "recompile",
                    {"path": item["content_file"]},
                )
        return request, request_raw, content
    finally:
        close_fd(content_fd)


def inspect_article_publication(*, prepared, vault_root):
    _path, batch = _prepared_slot(prepared)

    def apply(snapshot, domain_store, authority):
        try:
            vault = _load_article_store(snapshot)
            exp = _load_experiment_store(snapshot)
            heads = derive_domain_heads(domain_store)
            pub = _publication_snapshot(batch)
            try:
                request, request_raw, content = _load_publication(pub, batch)
                current_basis = _article_basis(snapshot, domain_store, authority, exp, vault)
                if current_basis != request["basis"]:
                    _fail("ARTICLE_PUBLICATION_STALE", "/basis", "recompile", exit_code=75)
                staged = _staged_from_content(request, content)
                rebuilt = _build_request(snapshot, domain_store, authority, exp, heads, vault, staged, batch)
                if (
                    rebuilt["request"]["payloads"] != request["payloads"]
                    or rebuilt["request"]["touched_articles"] != request["touched_articles"]
                    or rebuilt["request"]["compiled_heads"] != request["compiled_heads"]
                    or rebuilt["request"]["prospective_inventory_sha256"] != request["prospective_inventory_sha256"]
                ):
                    _fail("ARTICLE_PUBLICATION_MISMATCH", "/payloads", "recompile")
                inspection = {
                    "schema": INSPECTION_SCHEMA,
                    "batch_id": batch,
                    "request_sha256": sha(request_raw),
                    "request": request,
                    "basis_verified": True,
                    "content_verified": True,
                    "chains_verified": True,
                    "gates_verified": True,
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
                    _map_schema(exc, "ARTICLE_PUBLICATION_INVALID", "repair_input")
                try:
                    pub.verify()
                except ContractError as exc:
                    _map_work(
                        exc,
                        "/article-publication",
                        invalid="ARTICLE_PUBLICATION_INVALID",
                        changed="ARTICLE_PUBLICATION_INVALID",
                    )
                return inspection
            finally:
                pub.close()
        except OSError:
            _fail("ARTICLE_PUBLICATION_INVALID", "/article-publication", "repair_input")

    return _run_with_store(vault_root, apply, authority_required=True)
