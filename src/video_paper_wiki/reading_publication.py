"""Compile and inspect unpublished reading publication payloads. Vault writes are forbidden."""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata

from video_paper_wiki.article_publication import _article_basis
from video_paper_wiki.article_store import ArticleStoreError, _load_article_store, _run_with_store
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_store import DomainStoreError
from video_paper_wiki.experiment_apply import (
    READ_FLAGS,
    _close_all,
    _read_child,
    _stat_child,
    _stat_via_root,
)
from video_paper_wiki.experiment_store import ExperimentStoreError, _load_experiment_store
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.reading.view import MANIFEST_SCHEMA, MAX_PAGE_BYTES, MAX_PAGES, MAX_TOTAL_BYTES
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

REQUEST_SCHEMA = "video-paper-wiki.reading-publication-request.v1"
INSPECTION_SCHEMA = "video-paper-wiki.reading-publication-inspection.v1"
COMPILE_COMMAND = "reading.compile"
INSPECT_COMMAND = "reading.publish-inspect"
INSTALL_ROOT = "wiki/reading"
NOTES_ROOT = "wiki/reading-notes"
MARKER_PREFIX = b"---\ngenerated_by: video-paper-wiki.reading.v1\n"
PAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*\.md")
MAX_VAULT_ENTRIES = 16384
MAX_DEPTH = 16
MAX_FOREIGN = 8192
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 1_048_576
INSTALL_PREFIX = INSTALL_ROOT + "/"
MESSAGES = {
    "READING_COMPILE_INVALID": "reading compile input is invalid",
    "READING_COMPILE_EMPTY": "reading compile batch has no staged pages",
    "READING_COMPILE_LIMIT": "reading compile input exceeds a closed bound",
    "READING_COMPILE_STALE": "reading compile basis is stale",
    "READING_COMPILE_UNMARKED_TARGET": "reading compile target is an unmarked user file",
    "READING_COMPILE_TARGET_INVALID": "reading compile vault target is invalid",
    "READING_COMPILE_ALREADY_APPLIED": "reading compile targets are already applied",
    "READING_COMPILE_CHANGED": "reading compile input changed during read",
    "READING_PUBLICATION_INVALID": "reading publication request is invalid",
    "READING_PUBLICATION_CONTENT_MISMATCH": "reading publication content does not match the request",
    "READING_PUBLICATION_STALE": "reading publication request basis is stale",
    "READING_PUBLICATION_MISMATCH": "reading publication request does not match the recomputed write set",
}


class ReadingPublicationError(Exception):
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
    raise ReadingPublicationError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _map_schema(exc, code, next_action):
    pointer = exc.details.get("instance_pointer") or ""
    extra = dict(exc.details)
    if code == "READING_COMPILE_INVALID" and "reason" not in extra:
        extra["reason"] = "schema"
    if code == "READING_PUBLICATION_INVALID" and "reason" not in extra:
        extra["reason"] = "schema"
    raise ReadingPublicationError(
        code,
        MESSAGES.get(code, code),
        {"instance_pointer": pointer, "next_action": next_action, **extra},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _map_work(exc, pointer, *, invalid="READING_COMPILE_INVALID", changed="READING_COMPILE_CHANGED"):
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
        _fail(
            "READING_COMPILE_LIMIT" if invalid.startswith("READING_COMPILE") else invalid,
            pointer if str(pointer).startswith("/") else "/" + str(pointer).lstrip("/"),
            "reduce_scope",
            dict(details),
        )
    if code == "WORK_PATH_UNSAFE":
        raise ReadingPublicationError(
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


def _list_names(fd, pointer, *, changed):
    try:
        return sorted(os.listdir(fd))
    except OSError:
        _fail(changed, pointer, "repeat_read", exit_code=75)


def _read_bytes(snapshot, relative, pointer, *, invalid, changed, max_bytes):
    try:
        raw = snapshot.read(relative, max_bytes=max_bytes)
    except ContractError as exc:
        _map_work(exc, pointer, invalid=invalid, changed=changed)
    except SecureIOError as exc:
        _map_work(exc, pointer, invalid=invalid, changed=changed)
    except OSError:
        _fail(changed, pointer, "repeat_read", {"path": relative}, exit_code=75)
    if len(raw) > max_bytes:
        _fail(
            "READING_COMPILE_LIMIT" if invalid.startswith("READING_COMPILE") else invalid,
            pointer,
            "reduce_scope",
            {"path": relative, "size_bytes": len(raw)},
        )
    return raw


def _parse_json_doc(raw, schema, pointer, relative, *, invalid):
    try:
        doc = parse_strict_json(raw, invalid_code=invalid)
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "READING_COMPILE_LIMIT" if invalid.startswith("READING_COMPILE") and reason == "depth" else invalid
        next_action = "reduce_scope" if str(code).endswith("LIMIT") else "repair_input"
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


def _open_snapshot(path, pointer, *, invalid, changed, missing_code=None, missing_action="repair_input"):
    try:
        st = path.lstat()
    except FileNotFoundError:
        code = missing_code or invalid
        _fail(code, pointer, missing_action, {"reason": "missing", "path": str(path.name)})
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


def _work_reading_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "reading"
    return _open_snapshot(
        path,
        "/reading",
        invalid="READING_COMPILE_INVALID",
        changed="READING_COMPILE_CHANGED",
        missing_code="READING_COMPILE_EMPTY",
        missing_action="build_reading",
    )


def _publication_snapshot(batch):
    path = resolve_checkout_root() / ".work" / batch / "reading-publication"
    return _open_snapshot(
        path,
        "/reading-publication",
        invalid="READING_PUBLICATION_INVALID",
        changed="READING_PUBLICATION_INVALID",
    )


def _verify_work(snapshot, pointer, *, changed):
    try:
        snapshot.verify()
    except ContractError as exc:
        _map_work(exc, pointer, invalid=changed, changed=changed)
    except OSError:
        _fail(changed, pointer, "repeat_read", exit_code=75)


def _fold(value):
    return unicodedata.normalize("NFC", value).casefold()


def _portable_name(name):
    if type(name) is not str or name in {".", ".."} or "\x00" in name or "\\" in name:
        return False
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return unicodedata.normalize("NFC", name) == name


def _target_invalid(reason, path, extra=None):
    extra = {} if extra is None else dict(extra)
    extra["reason"] = reason
    extra["path"] = path
    _fail("READING_COMPILE_TARGET_INVALID", _pointer(*path.split("/")), "repair_input", extra)


def _compile_limit(pointer, extra=None):
    extra = {} if extra is None else dict(extra)
    _fail("READING_COMPILE_LIMIT", pointer, "reduce_scope", extra)


def _is_marked_manifest(raw):
    try:
        doc = parse_strict_json(raw, invalid_code="READING_COMPILE_INVALID")
        if type(doc) is not dict:
            return False
        validate_document(doc, MANIFEST_SCHEMA)
    except (SecureIOError, ContractError):
        return False
    return True


def _peek_prefix(parent_fd, name, size):
    fd = os.open(name, READ_FLAGS, dir_fd=parent_fd)
    try:
        return os.read(fd, size)
    finally:
        os.close(fd)


def _classify_existing(rel, st, parent_fd, name, pages_meta):
    page_index, page_sha, page_size, page_set = pages_meta
    vault_path = INSTALL_PREFIX + rel
    if rel in page_set:
        if st.st_nlink > 1:
            try:
                head = _peek_prefix(parent_fd, name, len(MARKER_PREFIX))
            except OSError:
                _fail(
                    "READING_COMPILE_UNMARKED_TARGET",
                    "/pages/" + str(page_index[rel]),
                    "move_user_file",
                    {"path": vault_path, "reason": "hardlink"},
                )
            if head.startswith(MARKER_PREFIX):
                _target_invalid("hardlink", vault_path)
            _fail(
                "READING_COMPILE_UNMARKED_TARGET",
                "/pages/" + str(page_index[rel]),
                "move_user_file",
                {"path": vault_path, "reason": "hardlink"},
            )
        if not PAGE_RE.fullmatch(rel):
            _fail(
                "READING_COMPILE_UNMARKED_TARGET",
                "/pages/" + str(page_index[rel]),
                "move_user_file",
                {"path": vault_path, "reason": "entry_kind"},
            )
        if st.st_size > MAX_PAGE_BYTES:
            _fail(
                "READING_COMPILE_UNMARKED_TARGET",
                "/pages/" + str(page_index[rel]),
                "move_user_file",
                {"path": vault_path, "reason": "oversize"},
            )
        raw = _read_child(parent_fd, name, max_bytes=MAX_PAGE_BYTES)
        if not raw.startswith(MARKER_PREFIX):
            _fail(
                "READING_COMPILE_UNMARKED_TARGET",
                "/pages/" + str(page_index[rel]),
                "move_user_file",
                {"path": vault_path, "reason": "no_marker"},
            )
        digest = sha(raw)
        mode = "keep" if digest == page_sha[rel] and len(raw) == page_size[rel] else "replace"
        return {
            "kind": "row",
            "row": {
                "rel": rel,
                "mode": mode,
                "before": digest,
                "after": page_sha[rel],
                "size": page_size[rel],
            },
        }
    marked = False
    digest = None
    if PAGE_RE.fullmatch(rel) and st.st_size <= MAX_PAGE_BYTES and st.st_nlink == 1:
        raw = _read_child(parent_fd, name, max_bytes=MAX_PAGE_BYTES)
        marked = raw.startswith(MARKER_PREFIX)
        digest = sha(raw)
    elif rel == "manifest.json" and st.st_size <= MAX_MANIFEST_BYTES and st.st_nlink == 1:
        raw = _read_child(parent_fd, name, max_bytes=MAX_MANIFEST_BYTES)
        marked = _is_marked_manifest(raw)
        digest = sha(raw)
    if marked:
        return {
            "kind": "row",
            "row": {"rel": rel, "mode": "delete", "before": digest, "after": None, "size": None},
        }
    return {"kind": "foreign", "path": vault_path}


def _plan_targets(root_fd, pages):
    wiki_st = _stat_child(root_fd, "wiki")
    if wiki_st is None:
        _target_invalid("missing_parent", "wiki")
    if stat.S_ISLNK(wiki_st.st_mode):
        _target_invalid("symlink", "wiki")
    if not stat.S_ISDIR(wiki_st.st_mode):
        _target_invalid("entry_kind", "wiki")
    wiki_fd = os.open("wiki", dir_open_flags(), dir_fd=root_fd)
    try:
        reading_st = _stat_child(wiki_fd, "reading")
        page_index = {item["path"]: index for index, item in enumerate(pages)}
        page_sha = {item["path"]: item["sha256"] for item in pages}
        page_size = {item["path"]: item["size_bytes"] for item in pages}
        page_set = set(page_sha)
        pages_meta = (page_index, page_sha, page_size, page_set)
        folded_targets = {}
        for item in pages:
            parts = item["path"].split("/")
            acc = []
            for part in parts:
                acc.append(part)
                rel = "/".join(acc)
                key = _fold(rel)
                prior = folded_targets.get(key)
                if prior is not None and prior != rel:
                    _target_invalid("portable_collision", INSTALL_PREFIX + rel)
                folded_targets[key] = rel
        rows = []
        foreign = []
        seen = set()
        if reading_st is None:
            for item in pages:
                rows.append(
                    {
                        "rel": item["path"],
                        "mode": "create",
                        "before": None,
                        "after": item["sha256"],
                        "size": item["size_bytes"],
                    }
                )
        else:
            if stat.S_ISLNK(reading_st.st_mode):
                _target_invalid("symlink", INSTALL_ROOT)
            if not stat.S_ISDIR(reading_st.st_mode):
                _target_invalid("entry_kind", INSTALL_ROOT)
            reading_fd = os.open("reading", dir_open_flags(), dir_fd=wiki_fd)
            entry_count = 0

            def walk(parent_fd, prefix, depth):
                nonlocal entry_count
                if depth > MAX_DEPTH:
                    _compile_limit("/wiki/reading", {"path": INSTALL_ROOT, "reason": "depth"})
                try:
                    names = list(os.listdir(parent_fd))
                except OSError:
                    _fail("READING_COMPILE_CHANGED", "/wiki/reading", "repeat_read", exit_code=75)
                seen_fold = {}
                for name in names:
                    if not _portable_name(name):
                        rel = name if not prefix else prefix + "/" + name
                        _target_invalid("portable_name", INSTALL_PREFIX + rel)
                    key = _fold(name)
                    if key in seen_fold and seen_fold[key] != name:
                        rel = name if not prefix else prefix + "/" + name
                        _target_invalid("portable_collision", INSTALL_PREFIX + rel)
                    seen_fold[key] = name
                for name in names:
                    entry_count += 1
                    if entry_count > MAX_VAULT_ENTRIES:
                        _compile_limit("/wiki/reading", {"path": INSTALL_ROOT})
                    rel = name if not prefix else prefix + "/" + name
                    folded = _fold(rel)
                    if folded in folded_targets and folded_targets[folded] != rel:
                        _target_invalid("portable_collision", INSTALL_PREFIX + rel)
                    st = _stat_child(parent_fd, name)
                    if st is None:
                        _fail(
                            "READING_COMPILE_CHANGED",
                            _pointer("wiki", "reading", *rel.split("/")),
                            "repeat_read",
                            exit_code=75,
                        )
                    if stat.S_ISLNK(st.st_mode):
                        _target_invalid("symlink", INSTALL_PREFIX + rel)
                    if stat.S_ISDIR(st.st_mode):
                        if rel in page_set:
                            _target_invalid("entry_kind", INSTALL_PREFIX + rel)
                        child = os.open(name, dir_open_flags(), dir_fd=parent_fd)
                        try:
                            walk(child, rel, depth + 1)
                        finally:
                            close_fd(child)
                        continue
                    if not stat.S_ISREG(st.st_mode):
                        _target_invalid("entry_kind", INSTALL_PREFIX + rel)
                    seen.add(rel)
                    classified = _classify_existing(rel, st, parent_fd, name, pages_meta)
                    if classified["kind"] == "row":
                        rows.append(classified["row"])
                    else:
                        foreign.append(classified["path"])
                        if len(foreign) > MAX_FOREIGN:
                            _compile_limit("/wiki/reading", {"path": classified["path"]})

            try:
                walk(reading_fd, "", 1)
                for item in pages:
                    if item["path"] in seen:
                        continue
                    rows.append(
                        {
                            "rel": item["path"],
                            "mode": "create",
                            "before": None,
                            "after": item["sha256"],
                            "size": item["size_bytes"],
                        }
                    )
            finally:
                close_fd(reading_fd)
        rows.sort(key=lambda row: (INSTALL_PREFIX + row["rel"]).encode("utf-8"))
        foreign = sorted(set(foreign), key=lambda item: item.encode("utf-8"))
        counts = {"create": 0, "replace": 0, "keep": 0, "delete": 0, "foreign": len(foreign)}
        for row in rows:
            counts[row["mode"]] += 1
        return {"rows": rows, "foreign": foreign, "counts": counts, "files": seen}
    finally:
        close_fd(wiki_fd)


def _payloads_from_plan(plan):
    payloads = []
    for row in plan["rows"]:
        path = INSTALL_PREFIX + row["rel"]
        if row["mode"] == "delete":
            payloads.append(
                {
                    "path": path,
                    "mode": "delete",
                    "before_sha256": row["before"],
                    "after_sha256": None,
                    "size_bytes": None,
                    "staged_path": None,
                }
            )
            continue
        payloads.append(
            {
                "path": path,
                "mode": row["mode"],
                "before_sha256": row["before"],
                "after_sha256": row["after"],
                "size_bytes": row["size"],
                "staged_path": "reading/" + row["rel"],
            }
        )
    payloads.sort(key=lambda item: item["path"].encode("utf-8"))
    return payloads


def _check_request(request, *, compile_mode=False, manifest_pages=None):
    invalid = "READING_COMPILE_INVALID" if compile_mode else "READING_PUBLICATION_INVALID"
    payloads = request["payloads"]
    paths = [item["path"] for item in payloads]
    encoded = [path.encode("utf-8") for path in paths]
    if encoded != sorted(encoded) or len(paths) != len(set(paths)):
        _fail(invalid, "/payloads", "repair_input", {"reason": "schema_rule"})
    create = replace = keep = delete = 0
    staged = []
    for index, item in enumerate(payloads):
        pointer = "/payloads/" + str(index)
        path = item["path"]
        if ".." in path.split("/"):
            _fail(invalid, pointer, "repair_input", {"reason": "schema_rule", "path": path})
        mode = item["mode"]
        if path == INSTALL_PREFIX + "manifest.json" and mode != "delete":
            _fail(invalid, pointer, "repair_input", {"reason": "schema_rule", "path": path})
        expected_staged = "reading/" + path[len(INSTALL_PREFIX) :]
        if mode == "create":
            if (
                item["before_sha256"] is not None
                or item["after_sha256"] is None
                or type(item["size_bytes"]) is not int
                or item["size_bytes"] < 1
                or item["staged_path"] != expected_staged
            ):
                _fail(invalid, pointer, "repair_input", {"reason": "schema_rule"})
            create += 1
            staged.append(item["staged_path"])
        elif mode == "replace":
            if (
                item["before_sha256"] is None
                or item["after_sha256"] is None
                or item["before_sha256"] == item["after_sha256"]
                or item["staged_path"] != expected_staged
            ):
                _fail(invalid, pointer, "repair_input", {"reason": "schema_rule"})
            replace += 1
            staged.append(item["staged_path"])
        elif mode == "keep":
            if (
                item["before_sha256"] is None
                or item["before_sha256"] != item["after_sha256"]
                or item["staged_path"] != expected_staged
            ):
                _fail(invalid, pointer, "repair_input", {"reason": "schema_rule"})
            keep += 1
            staged.append(item["staged_path"])
        elif mode == "delete":
            if (
                item["before_sha256"] is None
                or item["after_sha256"] is not None
                or item["size_bytes"] is not None
                or item["staged_path"] is not None
            ):
                _fail(invalid, pointer, "repair_input", {"reason": "schema_rule"})
            delete += 1
        else:
            _fail(invalid, pointer, "repair_input", {"reason": "schema_rule"})
    if create + replace + keep != request["counts"]["pages"]:
        _fail(invalid, "/counts/pages", "repair_input", {"reason": "schema_rule"})
    if manifest_pages is not None:
        if create + replace + keep != len(manifest_pages):
            _fail(invalid, "/payloads", "repair_input", {"reason": "schema_rule"})
        expected = {"reading/" + item["path"] for item in manifest_pages}
        if set(staged) != expected:
            _fail(invalid, "/payloads", "repair_input", {"reason": "schema_rule"})
    foreign = request["foreign_paths"]
    foreign_encoded = [item.encode("utf-8") for item in foreign]
    if foreign_encoded != sorted(foreign_encoded) or len(foreign) != len(set(foreign)):
        _fail(invalid, "/foreign_paths", "repair_input", {"reason": "schema_rule"})
    payload_set = set(paths)
    for item in foreign:
        if item in payload_set or ".." in item.split("/"):
            _fail(invalid, "/foreign_paths", "repair_input", {"reason": "schema_rule", "path": item})
    expected_counts = {
        "create": create,
        "replace": replace,
        "keep": keep,
        "delete": delete,
        "foreign": len(foreign),
    }
    if request["write_plan_counts"] != expected_counts:
        _fail(invalid, "/write_plan_counts", "repair_input", {"reason": "schema_rule"})
    if create + replace + delete == 0 and compile_mode:
        _fail("READING_COMPILE_ALREADY_APPLIED", "/payloads", "discard_batch")


def _enum_staged_files(fd, prefix, depth, files, *, invalid, changed):
    if depth > MAX_DEPTH:
        _compile_limit("/reading", {"reason": "depth"})
    names = _list_names(fd, "/reading" if not prefix else "/reading/" + prefix, changed=changed)
    for name in names:
        if not _portable_name(name):
            rel = name if not prefix else prefix + "/" + name
            _fail(invalid, "/reading/" + rel, "repair_input", {"reason": "entry_kind", "path": rel})
        rel = name if not prefix else prefix + "/" + name
        st = _stat_child(fd, name)
        if st is None:
            _fail(changed, "/reading/" + rel, "repeat_read", {"path": rel}, exit_code=75)
        if stat.S_ISLNK(st.st_mode):
            _fail(invalid, "/reading/" + rel, "repair_input", {"reason": "symlink", "path": rel})
        if stat.S_ISDIR(st.st_mode):
            child = os.open(name, dir_open_flags(), dir_fd=fd)
            try:
                _enum_staged_files(child, rel, depth + 1, files, invalid=invalid, changed=changed)
            finally:
                close_fd(child)
            continue
        if not stat.S_ISREG(st.st_mode):
            _fail(invalid, "/reading/" + rel, "repair_input", {"reason": "entry_kind", "path": rel})
        files.append(rel)
        if len(files) > MAX_PAGES + 1:
            _compile_limit("/reading", {"path": rel})


def _load_staged_reading(
    batch,
    *,
    invalid="READING_COMPILE_INVALID",
    changed="READING_COMPILE_CHANGED",
    expected_manifest_sha=None,
):
    staged = _work_reading_snapshot(batch)
    try:
        files = []
        _enum_staged_files(staged.root_fd, "", 1, files, invalid=invalid, changed=changed)
        file_set = set(files)
        if "manifest.json" not in file_set:
            _fail(invalid, "/reading/manifest.json", "repair_input", {"reason": "manifest_missing", "path": "reading/manifest.json"})
        manifest_raw = _read_bytes(
            staged,
            "manifest.json",
            "/reading/manifest.json",
            invalid=invalid,
            changed=changed,
            max_bytes=MAX_MANIFEST_BYTES,
        )
        if expected_manifest_sha is not None and sha(manifest_raw) != expected_manifest_sha:
            _fail(
                "READING_PUBLICATION_CONTENT_MISMATCH",
                "/manifest_sha256",
                "recompile",
                {"path": "reading/manifest.json"},
            )
        manifest = _parse_json_doc(
            manifest_raw,
            MANIFEST_SCHEMA,
            "/reading/manifest.json",
            "reading/manifest.json",
            invalid=invalid,
        )
        if manifest["batch_id"] != batch:
            _fail(invalid, "/reading/manifest.json", "repair_input", {"reason": "batch_id"})
        if manifest["paper_filter"] is not None:
            _fail(
                "READING_COMPILE_INVALID",
                "/paper_filter",
                "rebuild_unfiltered",
                {"reason": "paper_filter"},
            )
        expected = {"manifest.json"} | {item["path"] for item in manifest["pages"]}
        extra = sorted(file_set - expected)
        if extra:
            _fail(invalid, "/reading/" + extra[0], "repair_input", {"reason": "unknown_entry", "path": extra[0]})
        missing = sorted(expected - file_set)
        if missing:
            _fail(invalid, "/reading/" + missing[0], "repair_input", {"reason": "page_missing", "path": missing[0]})
        page_bytes = {}
        total = 0
        for index, item in enumerate(manifest["pages"]):
            rel = item["path"]
            pointer = "/pages/" + str(index)
            raw = _read_bytes(
                staged,
                rel,
                pointer,
                invalid=invalid,
                changed=changed,
                max_bytes=MAX_PAGE_BYTES,
            )
            if sha(raw) != item["sha256"] or len(raw) != item["size_bytes"]:
                digest_code = "READING_PUBLICATION_CONTENT_MISMATCH" if invalid == "READING_PUBLICATION_INVALID" else invalid
                digest_action = "recompile" if digest_code == "READING_PUBLICATION_CONTENT_MISMATCH" else "repair_input"
                _fail(digest_code, pointer, digest_action, {"reason": "page_digest", "path": rel})
            if not raw.startswith(MARKER_PREFIX):
                _fail(invalid, pointer, "repair_input", {"reason": "unmarked_page", "path": rel})
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                _compile_limit("/reading", {"path": rel})
            page_bytes[rel] = raw
        return {
            "snapshot": staged,
            "manifest": manifest,
            "manifest_raw": manifest_raw,
            "pages": page_bytes,
        }
    except Exception:
        staged.close()
        raise


def _reread_staged(loaded, *, changed="READING_COMPILE_CHANGED"):
    snapshot = loaded["snapshot"]
    raw = _read_bytes(
        snapshot,
        "manifest.json",
        "/reading/manifest.json",
        invalid=changed,
        changed=changed,
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if raw != loaded["manifest_raw"]:
        _fail(changed, "/reading/manifest.json", "repeat_read", {"path": "reading/manifest.json"}, exit_code=75)
    for index, item in enumerate(loaded["manifest"]["pages"]):
        rel = item["path"]
        pointer = "/pages/" + str(index)
        again = _read_bytes(
            snapshot,
            rel,
            pointer,
            invalid=changed,
            changed=changed,
            max_bytes=MAX_PAGE_BYTES,
        )
        if again != loaded["pages"][rel]:
            _fail(changed, pointer, "repeat_read", {"path": rel}, exit_code=75)


def _manifest_basis(manifest):
    return {
        **manifest["basis"],
        "article_store_inventory_sha256": manifest["article_store_inventory_sha256"],
    }


def _check_request_derived(request, manifest):
    expected = {
        "basis": _manifest_basis(manifest),
        "graph_sha256": manifest["graph_sha256"],
        "matrix_sha256": manifest["matrix_sha256"],
        "articles_batch": manifest["articles_batch"],
        "counts": dict(manifest["counts"]),
    }
    observed = {
        "basis": request["basis"],
        "graph_sha256": request["graph_sha256"],
        "matrix_sha256": request["matrix_sha256"],
        "articles_batch": request["articles_batch"],
        "counts": request["counts"],
    }
    if expected == observed:
        return
    pointer = "/basis"
    for key in ("basis", "graph_sha256", "matrix_sha256", "articles_batch", "counts"):
        if expected[key] != observed[key]:
            pointer = "/" + key
            break
    _fail("READING_PUBLICATION_CONTENT_MISMATCH", pointer, "recompile")


def _register_plan(snapshot, plan):
    for row in plan["rows"]:
        path = INSTALL_PREFIX + row["rel"]
        if row["mode"] == "create":
            snapshot.absent.add(path)
            continue
        limit = MAX_MANIFEST_BYTES if row["rel"] == "manifest.json" else MAX_PAGE_BYTES
        try:
            snapshot.read(path, max_bytes=limit)
        except ContractError as exc:
            _map_work(exc, _pointer(*path.split("/")), invalid="READING_COMPILE_CHANGED", changed="READING_COMPILE_CHANGED")


def _build_request(snapshot, domain_store, authority, exp, art, loaded, batch, current_basis):
    manifest = loaded["manifest"]
    first = _manifest_basis(manifest)
    if first != current_basis:
        _fail(
            "READING_COMPILE_STALE",
            "/basis",
            "rebuild_reading",
            {"first": first, "observed": current_basis},
            exit_code=75,
        )
    plan = _plan_targets(snapshot.root_fd, manifest["pages"])
    if plan["counts"]["create"] + plan["counts"]["replace"] + plan["counts"]["delete"] == 0:
        _fail("READING_COMPILE_ALREADY_APPLIED", "/payloads", "discard_batch")
    _register_plan(snapshot, plan)
    payloads = _payloads_from_plan(plan)
    request = {
        "schema": REQUEST_SCHEMA,
        "batch_id": batch,
        "kind": "reading",
        "install_path": INSTALL_ROOT,
        "reading_notes_root": NOTES_ROOT,
        "manifest_sha256": sha(loaded["manifest_raw"]),
        "basis": current_basis,
        "graph_sha256": manifest["graph_sha256"],
        "matrix_sha256": manifest["matrix_sha256"],
        "articles_batch": manifest["articles_batch"],
        "paper_filter": None,
        "counts": dict(manifest["counts"]),
        "payloads": payloads,
        "foreign_paths": list(plan["foreign"]),
        "write_plan_counts": dict(plan["counts"]),
        "publication": "unpublished",
        "applied": False,
        "vault_written": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "backup_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "typed_fact_promotion": "none",
        "ranking": "not_ranked",
        "next_action": "inspect_reading_publication",
    }
    _check_request(request, compile_mode=True, manifest_pages=manifest["pages"])
    try:
        request_raw = canonicalize(request)
        sealed = json.loads(request_raw.decode("utf-8"))
    except (CanonicalJsonError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("READING_COMPILE_INVALID", "", "repair_input", {"reason": "canonical_bytes"})
    try:
        validate_document(sealed, REQUEST_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "READING_COMPILE_INVALID", "repair_input")
    if len(request_raw) > MAX_REQUEST_BYTES:
        _fail("READING_COMPILE_LIMIT", "/request", "reduce_scope", {"size_bytes": len(request_raw)})
    changed_paths = [
        item["path"]
        for item in sealed["payloads"]
        if item["mode"] in {"create", "replace", "delete"}
    ]
    changed_paths.sort(key=lambda item: item.encode("utf-8"))
    data = {
        "state": "reading_publication_prepared",
        "batch_id": batch,
        "request_path": ".work/" + batch + "/reading-publication/request.json",
        "request_sha256": sha(request_raw),
        "manifest_sha256": sealed["manifest_sha256"],
        "basis": sealed["basis"],
        "install_path": INSTALL_ROOT,
        "write_plan_counts": sealed["write_plan_counts"],
        "changed_paths": changed_paths,
        "payload_count": len(sealed["payloads"]),
        "foreign_count": len(sealed["foreign_paths"]),
        "publication": "unpublished",
        "applied": False,
        "vault_written": False,
        "receipt_backed": False,
        "audit_coverage": "not_wired",
        "backup_coverage": "not_wired",
        "transaction_authority": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "inspect_reading_publication",
    }
    return {"request": sealed, "request_raw": request_raw, "data": data, "plan": plan}


def _stage_publication(batch, built):
    target = resolve_checkout_root() / ".work" / batch / "reading-publication" / "request.json"
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
    stage_bytes(batch_id=batch, relative=("reading-publication", "request.json"), data=built["request_raw"])


def compile_reading_publication(*, vault_root, batch_id):
    batch = validate_batch_id(batch_id)

    def apply(snapshot, domain_store, authority):
        try:
            art = _load_article_store(snapshot)
            exp = _load_experiment_store(snapshot)
            current_basis = _article_basis(snapshot, domain_store, authority, exp, art)
            loaded = _load_staged_reading(batch)
            try:
                _reread_staged(loaded)
                built = _build_request(
                    snapshot, domain_store, authority, exp, art, loaded, batch, current_basis
                )
                _verify_work(loaded["snapshot"], "/reading", changed="READING_COMPILE_CHANGED")
                _stage_publication(batch, built)
                _verify_work(loaded["snapshot"], "/reading", changed="READING_COMPILE_CHANGED")
                return built["data"]
            finally:
                loaded["snapshot"].close()
        except OSError:
            _fail("READING_COMPILE_CHANGED", "/reading", "repeat_read", exit_code=75)

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
        if parts != (batch, "reading-publication", "request.json"):
            raise ValueError
        return path, batch
    except (ValueError, StagingError) as exc:
        raise StagingError(
            CODE_WORK_PATH_UNSAFE,
            "prepared input must use the fixed reading publication slot",
            {"path": os.fspath(value)},
        ) from exc


def _load_request(pub, batch):
    names = _list_names(pub.root_fd, "/reading-publication", changed="READING_PUBLICATION_INVALID")
    extra = [name for name in names if name != "request.json"]
    if extra:
        _fail(
            "READING_PUBLICATION_INVALID",
            _pointer("reading-publication", extra[0]),
            "repair_input",
            {"reason": "unknown_entry", "name": extra[0], "path": "reading-publication/" + extra[0]},
        )
    if "request.json" not in names:
        _fail(
            "READING_PUBLICATION_INVALID",
            "/reading-publication/request.json",
            "repair_input",
            {"reason": "missing", "path": "reading-publication/request.json"},
        )
    st = _stat_child(pub.root_fd, "request.json")
    if st is None:
        _fail(
            "READING_PUBLICATION_INVALID",
            "/reading-publication/request.json",
            "repair_input",
            {"reason": "missing", "path": "reading-publication/request.json"},
        )
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        _fail(
            "READING_PUBLICATION_INVALID",
            "/reading-publication/request.json",
            "repair_input",
            {"reason": "entry_kind", "path": "reading-publication/request.json"},
        )
    if st.st_nlink != 1:
        _fail(
            "READING_PUBLICATION_INVALID",
            "/reading-publication/request.json",
            "repair_input",
            {"reason": "hardlink", "path": "reading-publication/request.json"},
        )
    if st.st_size > MAX_REQUEST_BYTES:
        _fail(
            "READING_PUBLICATION_INVALID",
            "/reading-publication/request.json",
            "repair_input",
            {"reason": "oversize", "path": "reading-publication/request.json"},
        )
    request_raw = _read_bytes(
        pub,
        "request.json",
        "/reading-publication/request.json",
        invalid="READING_PUBLICATION_INVALID",
        changed="READING_PUBLICATION_INVALID",
        max_bytes=MAX_REQUEST_BYTES,
    )
    request = _parse_json_doc(
        request_raw,
        REQUEST_SCHEMA,
        "/reading-publication/request.json",
        "reading-publication/request.json",
        invalid="READING_PUBLICATION_INVALID",
    )
    _check_request(request, compile_mode=False)
    if request["batch_id"] != batch:
        _fail(
            "READING_PUBLICATION_INVALID",
            "/batch_id",
            "repair_input",
            {"reason": "batch_id", "path": "reading-publication/request.json"},
        )
    return request, request_raw


def _restage_against_request(batch, request):
    loaded = _load_staged_reading(
        batch,
        invalid="READING_PUBLICATION_INVALID",
        changed="READING_PUBLICATION_INVALID",
        expected_manifest_sha=request["manifest_sha256"],
    )
    try:
        _check_request_derived(request, loaded["manifest"])
        _check_request(request, compile_mode=False, manifest_pages=loaded["manifest"]["pages"])
        by_path = {item["path"]: item for item in request["payloads"] if item["mode"] != "delete"}
        expected = {INSTALL_PREFIX + rel for rel in loaded["pages"]}
        if set(by_path) != expected:
            _fail("READING_PUBLICATION_CONTENT_MISMATCH", "/payloads", "recompile")
        for index, item in enumerate(request["payloads"]):
            if item["mode"] == "delete":
                continue
            rel = item["path"][len(INSTALL_PREFIX) :]
            raw = loaded["pages"][rel]
            if sha(raw) != item["after_sha256"] or len(raw) != item["size_bytes"]:
                _fail(
                    "READING_PUBLICATION_CONTENT_MISMATCH",
                    "/payloads/" + str(index),
                    "recompile",
                    {"path": item["path"]},
                )
        return loaded
    except Exception:
        loaded["snapshot"].close()
        raise


def _plans_match(plan, request):
    payloads = _payloads_from_plan(plan)
    return (
        payloads == request["payloads"]
        and plan["foreign"] == request["foreign_paths"]
        and plan["counts"] == request["write_plan_counts"]
    )


def inspect_reading_publication(*, prepared, vault_root):
    _path, batch = _prepared_slot(prepared)

    def apply(snapshot, domain_store, authority):
        try:
            art = _load_article_store(snapshot)
            exp = _load_experiment_store(snapshot)
            current_basis = _article_basis(snapshot, domain_store, authority, exp, art)
            pub = _publication_snapshot(batch)
            try:
                request, request_raw = _load_request(pub, batch)
                loaded = _restage_against_request(batch, request)
                try:
                    if current_basis != request["basis"]:
                        _fail("READING_PUBLICATION_STALE", "/basis", "recompile", exit_code=75)
                    plan = _plan_targets(snapshot.root_fd, loaded["manifest"]["pages"])
                    _register_plan(snapshot, plan)
                    if not _plans_match(plan, request):
                        _fail("READING_PUBLICATION_MISMATCH", "/payloads", "recompile")
                    inspection = {
                        "schema": INSPECTION_SCHEMA,
                        "batch_id": batch,
                        "request_sha256": sha(request_raw),
                        "request": request,
                        "staged_verified": True,
                        "targets_verified": True,
                        "basis_verified": True,
                        "publication": "unpublished",
                        "applied": False,
                        "vault_written": False,
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
                        _map_schema(exc, "READING_PUBLICATION_INVALID", "repair_input")
                    _verify_work(pub, "/reading-publication", changed="READING_PUBLICATION_INVALID")
                    _verify_work(loaded["snapshot"], "/reading", changed="READING_PUBLICATION_INVALID")
                    return inspection
                finally:
                    loaded["snapshot"].close()
            finally:
                pub.close()
        except OSError:
            _fail("READING_PUBLICATION_INVALID", "/reading-publication", "repair_input")

    return _run_with_store(vault_root, apply, authority_required=True)
