"""Direct fail-closed apply of a compiled reading publication request.

Writes only under wiki/reading/** via vpwiki-admin. No receipt, audit,
backup, transaction authority, or canonical official fact is produced.
"""

from __future__ import annotations

import os
import secrets
import stat

from video_paper_wiki.article_publication import _article_basis
from video_paper_wiki.article_store import ArticleStoreError, _load_article_store
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import DomainPublicationError
from video_paper_wiki.domain_store import (
    DomainStoreError,
    _load_authority,
    _load_store,
    _map_snapshot,
)
from video_paper_wiki.experiment_apply import (
    READ_FLAGS,
    WRITE_FLAGS,
    _close_all,
    _dir_id,
    _read_child,
    _rmdir_relative,
    _stat_child,
    _stat_via_root,
    _unlink_relative,
)
from video_paper_wiki.experiment_store import ExperimentStoreError, _load_experiment_store
from video_paper_wiki.reading_publication import (
    INSTALL_PREFIX,
    INSTALL_ROOT,
    MARKER_PREFIX,
    MAX_MANIFEST_BYTES,
    MAX_PAGE_BYTES,
    NOTES_ROOT,
    ReadingPublicationError,
    _load_request,
    _plan_targets,
    _plans_match,
    _prepared_slot,
    _publication_snapshot,
    _register_plan,
    _restage_against_request,
)
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.secure_io import SecureIOError, close_fd, dir_open_flags, stamp
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

RESULT_SCHEMA = "video-paper-wiki.reading-publication-apply-result.v1"
MESSAGES = {
    "READING_APPLY_ALREADY_APPLIED": "reading publication is already applied",
    "READING_APPLY_VAULT_INVALID": "reading apply vault shape is invalid",
    "READING_APPLY_WRITE_FAILED": "reading apply write failed",
    "READING_APPLY_CHANGED": "reading apply inputs changed after confirmation",
    "READING_APPLY_VERIFY_FAILED": "reading apply post-write verification failed",
    "HUMAN_APPROVAL_REQUIRED": "interactive confirmation is required",
}


class ReadingApplyError(Exception):
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
    raise ReadingApplyError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _write_excl(parent_fd, name, data, created_files=None, created_path=None):
    fd = os.open(name, WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    try:
        if created_files is not None and created_path is not None:
            created_files.append(created_path)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(parent_fd)
    st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            "/" + name,
            "repair_store",
            {"reason": "entry_kind", "path": name},
        )
    if st.st_nlink != 1:
        _fail(
            "READING_APPLY_VAULT_INVALID",
            "/" + name,
            "repair_store",
            {"reason": "hardlink", "path": name},
        )
    if st.st_size != len(data):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            "/" + name,
            "repair_store",
            {"reason": "entry_kind", "path": name},
        )
    return st


def _open_existing_dir(parent_fd, name, relative, *, required):
    st = _stat_child(parent_fd, name)
    if st is None:
        if required:
            _fail(
                "READING_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "missing_parent", "path": relative},
            )
        return None
    if stat.S_ISLNK(st.st_mode):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*relative.split("/")),
            "repair_store",
            {"reason": "symlink", "path": relative},
        )
    if not stat.S_ISDIR(st.st_mode):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*relative.split("/")),
            "repair_store",
            {"reason": "entry_kind", "path": relative},
        )
    return os.open(name, dir_open_flags(), dir_fd=parent_fd)


def _ensure_dir(parent_fd, name, relative, created_dirs):
    st = _stat_child(parent_fd, name)
    if st is None:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created_dirs.append(relative)
    else:
        if stat.S_ISLNK(st.st_mode):
            _fail(
                "READING_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "symlink", "path": relative, "phase": "write"},
            )
        if not stat.S_ISDIR(st.st_mode):
            _fail(
                "READING_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "entry_kind", "path": relative, "phase": "write"},
            )
    return os.open(name, dir_open_flags(), dir_fd=parent_fd)


def _rollback(root_fd, created_files, created_dirs):
    rolled = []
    complete = True
    for relative in reversed(created_files):
        try:
            _unlink_relative(root_fd, relative)
            rolled.append(relative)
        except OSError:
            if _stat_via_root(root_fd, relative) is not None:
                complete = False
    for relative in reversed(created_dirs):
        try:
            _rmdir_relative(root_fd, relative)
            rolled.append(relative)
        except OSError:
            if _stat_via_root(root_fd, relative) is not None:
                complete = False
    return rolled, complete


def _write_failed(exc, phase, rolled, complete):
    extra = {
        "phase": phase,
        "rolled_back": list(rolled),
        "rollback_complete": bool(complete),
    }
    if isinstance(exc, OSError):
        extra["errno"] = exc.errno
    _fail("READING_APPLY_WRITE_FAILED", "/wiki/reading", "retry_apply", extra)


def _verify_failed(extra):
    details = dict(extra)
    details.setdefault("phase", extra.get("phase", "after-commit"))
    details.setdefault("instance_pointer", extra.get("instance_pointer", "/wiki/reading"))
    details.setdefault("committed_paths", [])
    details["next_action"] = "repair_store"
    raise ReadingApplyError(
        "READING_APPLY_VERIFY_FAILED",
        MESSAGES["READING_APPLY_VERIFY_FAILED"],
        details,
        exit_code=2,
    )


def _notes_stamp(root_fd):
    wiki_fd = os.open("wiki", dir_open_flags(), dir_fd=root_fd)
    try:
        st = _stat_child(wiki_fd, "reading-notes")
        if st is None:
            return None
        return stamp(st)
    finally:
        close_fd(wiki_fd)


def _read_relative(root_fd, relative, max_bytes):
    parts = relative.split("/")
    fds = []
    parent = root_fd
    try:
        for name in parts[:-1]:
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
        return _read_child(parent, parts[-1], max_bytes=max_bytes)
    finally:
        _close_all(fds)


def _check_create_absent(root_fd, path):
    parts = path.split("/")
    fds = []
    parent = root_fd
    try:
        for index, name in enumerate(parts):
            st = _stat_child(parent, name)
            last = index == len(parts) - 1
            relative = "/".join(parts[: index + 1])
            if st is None:
                if index < 1:
                    _fail(
                        "READING_APPLY_VAULT_INVALID",
                        _pointer(*relative.split("/")),
                        "repair_store",
                        {"reason": "missing_parent", "path": relative},
                    )
                return
            if last:
                if stat.S_ISLNK(st.st_mode):
                    _fail(
                        "READING_APPLY_VAULT_INVALID",
                        _pointer(*relative.split("/")),
                        "repair_store",
                        {"reason": "symlink", "path": relative},
                    )
                _fail(
                    "READING_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "target_exists", "path": relative},
                )
            if stat.S_ISLNK(st.st_mode):
                _fail(
                    "READING_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "symlink", "path": relative},
                )
            if not stat.S_ISDIR(st.st_mode):
                _fail(
                    "READING_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "entry_kind", "path": relative},
                )
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
    finally:
        _close_all(fds)


def _check_before(root_fd, path, expected):
    st = _stat_via_root(root_fd, path)
    if st is None:
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*path.split("/")),
            "repair_store",
            {"reason": "before", "path": path},
        )
    if stat.S_ISLNK(st.st_mode):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*path.split("/")),
            "repair_store",
            {"reason": "symlink", "path": path},
        )
    if not stat.S_ISREG(st.st_mode):
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*path.split("/")),
            "repair_store",
            {"reason": "entry_kind", "path": path},
        )
    if st.st_nlink != 1:
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*path.split("/")),
            "repair_store",
            {"reason": "hardlink", "path": path},
        )
    limit = MAX_MANIFEST_BYTES if path.endswith("/manifest.json") else MAX_PAGE_BYTES
    raw = _read_relative(root_fd, path, limit)
    if sha(raw) != expected:
        _fail(
            "READING_APPLY_VAULT_INVALID",
            _pointer(*path.split("/")),
            "repair_store",
            {"reason": "before", "path": path},
        )


def _parent_dir_rel(path):
    parts = path.split("/")
    return "/".join(parts[:-1])


def _open_dir_rel(root_fd, relative):
    parts = relative.split("/")
    fds = []
    parent = root_fd
    try:
        for name in parts:
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
        return parent, fds
    except Exception:
        _close_all(fds)
        raise


def _already_applied(root_fd, plan, request):
    if plan["counts"]["delete"] != 0:
        return False
    keep = {INSTALL_PREFIX + row["rel"] for row in plan["rows"] if row["mode"] == "keep"}
    targets = {item["path"] for item in request["payloads"] if item["mode"] != "delete"}
    if keep != targets:
        return False
    for item in request["payloads"]:
        if item["mode"] != "delete":
            continue
        if _stat_via_root(root_fd, item["path"]) is not None:
            return False
    return True


def _foreign_stamps(root_fd, foreign_paths):
    out = {}
    for path in foreign_paths:
        st = _stat_via_root(root_fd, path)
        if st is None:
            _fail(
                "READING_APPLY_VAULT_INVALID",
                _pointer(*path.split("/")),
                "repair_store",
                {"reason": "foreign", "path": path},
            )
        out[path] = stamp(st)
    return out


def _preflight(root_fd, request):
    wiki_fd = _open_existing_dir(root_fd, "wiki", "wiki", required=True)
    try:
        reading_st = _stat_child(wiki_fd, "reading")
        if reading_st is None:
            will_create_root = True
        else:
            will_create_root = False
            if stat.S_ISLNK(reading_st.st_mode):
                _fail(
                    "READING_APPLY_VAULT_INVALID",
                    "/wiki/reading",
                    "repair_store",
                    {"reason": "symlink", "path": INSTALL_ROOT},
                )
            if not stat.S_ISDIR(reading_st.st_mode):
                _fail(
                    "READING_APPLY_VAULT_INVALID",
                    "/wiki/reading",
                    "repair_store",
                    {"reason": "entry_kind", "path": INSTALL_ROOT},
                )
    finally:
        close_fd(wiki_fd)
    for item in request["payloads"]:
        parent = _parent_dir_rel(item["path"])
        if parent and _stat_via_root(root_fd, parent) is not None:
            pst = _stat_via_root(root_fd, parent)
            if pst is not None:
                if stat.S_ISLNK(pst.st_mode):
                    _fail(
                        "READING_APPLY_VAULT_INVALID",
                        _pointer(*parent.split("/")),
                        "repair_store",
                        {"reason": "symlink", "path": parent},
                    )
                if not stat.S_ISDIR(pst.st_mode):
                    _fail(
                        "READING_APPLY_VAULT_INVALID",
                        _pointer(*parent.split("/")),
                        "repair_store",
                        {"reason": "entry_kind", "path": parent},
                    )
        if item["mode"] == "create":
            _check_create_absent(root_fd, item["path"])
        else:
            _check_before(root_fd, item["path"], item["before_sha256"])
    notes = _notes_stamp(root_fd)
    foreign = _foreign_stamps(root_fd, request["foreign_paths"])
    return {"will_create_root": will_create_root, "notes": notes, "foreign": foreign}


def _ensure_parent(root_fd, path, created_dirs):
    parts = path.split("/")
    fds = []
    parent = root_fd
    acc = []
    try:
        for name in parts[:-1]:
            acc.append(name)
            relative = "/".join(acc)
            fd = _ensure_dir(parent, name, relative, created_dirs)
            fds.append(fd)
            parent = fd
        return parent, fds, parts[-1]
    except Exception:
        _close_all(fds)
        raise


def _empty_after_delete(root_fd, delete_paths):
    parents = set()
    for path in delete_paths:
        parts = path.split("/")
        for index in range(len(parts) - 1, 2, -1):
            parents.add("/".join(parts[:index]))
    removed = []
    for relative in sorted(parents, key=lambda item: (-item.count("/"), item.encode("utf-8"))):
        dir_fd, fds = _open_dir_rel(root_fd, relative)
        try:
            try:
                names = os.listdir(dir_fd)
            except OSError:
                continue
        finally:
            _close_all(fds)
        if names:
            continue
        try:
            _rmdir_relative(root_fd, relative)
            removed.append(relative)
        except OSError:
            continue
    return removed


def _post_verify(
    vault,
    request,
    snapshot,
    pages,
    write_set,
    created_dirs,
    removed_dirs,
    notes_stamp,
    foreign_stamps,
    staged,
    pub,
):
    try:
        post = _Snapshot(vault)
    except ContractError as exc:
        _verify_failed({"prior_code": exc.code, **dict(exc.details)})
    except OSError as exc:
        _verify_failed({"reason": "snapshot", "errno": exc.errno})
    try:
        try:
            plan = _plan_targets(post.root_fd, pages)
        except ReadingPublicationError as exc:
            _verify_failed({"prior_code": exc.code, **dict(exc.details)})
        expected_files = {item["path"] for item in pages} | {
            path[len(INSTALL_PREFIX) :] for path in request["foreign_paths"]
        }
        if plan["files"] != expected_files:
            _verify_failed({"reason": "inventory", "path": INSTALL_ROOT})
        by_rel = {row["rel"]: row for row in plan["rows"]}
        for item in request["payloads"]:
            if item["mode"] == "delete":
                if _stat_via_root(post.root_fd, item["path"]) is not None:
                    _verify_failed({"reason": "delete_remains", "path": item["path"]})
                continue
            rel = item["path"][len(INSTALL_PREFIX) :]
            row = by_rel.get(rel)
            if row is None or row["mode"] != "keep" or row["before"] != item["after_sha256"]:
                _verify_failed({"reason": "page_bytes", "path": item["path"]})
            st = _stat_via_root(post.root_fd, item["path"])
            if st is None or not raw_marked(post.root_fd, item["path"]):
                _verify_failed({"reason": "page_bytes", "path": item["path"]})
            if item["mode"] in {"create", "replace"}:
                if st is None or stat.S_IMODE(st.st_mode) != 0o600:
                    _verify_failed({"reason": "mode", "path": item["path"]})
        for path, first in foreign_stamps.items():
            st = _stat_via_root(post.root_fd, path)
            if st is None or stamp(st) != first:
                _verify_failed({"reason": "foreign", "path": path})
        after_notes = _notes_stamp(post.root_fd)
        if after_notes != notes_stamp:
            _verify_failed({"reason": "reading_notes", "path": "wiki/reading-notes"})
        try:
            post_store = _load_store(post)
            post_auth = _load_authority(post, required=True)
            post_exp = _load_experiment_store(post)
            post_art = _load_article_store(post)
        except (DomainStoreError, ExperimentStoreError, ArticleStoreError) as exc:
            _verify_failed({"prior_code": exc.code, "reason": "basis", **dict(exc.details)})
        post_basis = _article_basis(post, post_store, post_auth, post_exp, post_art)
        if post_basis != request["basis"]:
            _verify_failed({"reason": "basis", "path": "/basis"})
        for relative, (first, _raw) in snapshot.files.items():
            if relative in write_set:
                continue
            try:
                current = post._current_stat(relative)
            except ContractError as exc:
                _verify_failed({"prior_code": exc.code, "path": relative, **dict(exc.details)})
            if stamp(current) != stamp(first):
                _verify_failed({"reason": "file_stamp", "path": relative})
        skip_dirs = set(removed_dirs)
        for relative, first in snapshot.directories.items():
            if not relative:
                continue
            if relative in skip_dirs or any(relative == item or relative.startswith(item + "/") for item in skip_dirs):
                continue
            try:
                current = post.directories.get(relative)
                if current is None:
                    fd, _parts = post._parent_fd(relative + "/probe", allow_missing=False)
                    try:
                        current = os.fstat(fd)
                    finally:
                        close_fd(fd)
            except ContractError as exc:
                _verify_failed({"prior_code": exc.code, "path": relative, **dict(exc.details)})
            except OSError as exc:
                _verify_failed({"reason": "directory", "path": relative, "errno": exc.errno})
            if _dir_id(current) != _dir_id(first):
                _verify_failed({"reason": "directory", "path": relative})
        for relative in created_dirs:
            st = _stat_via_root(post.root_fd, relative)
            if st is None or not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o700:
                _verify_failed({"reason": "mode", "path": relative})
        for relative in removed_dirs:
            if _stat_via_root(post.root_fd, relative) is not None:
                _verify_failed({"reason": "delete_remains", "path": relative})
        try:
            post.verify()
        except ContractError as exc:
            _verify_failed({"prior_code": exc.code, **dict(exc.details)})
        try:
            pub.verify()
            staged.verify()
        except ContractError as exc:
            _verify_failed({"prior_code": exc.code, **dict(exc.details)})
        return post
    except Exception:
        post.close()
        raise


def raw_marked(root_fd, path):
    limit = MAX_MANIFEST_BYTES if path.endswith("/manifest.json") else MAX_PAGE_BYTES
    raw = _read_relative(root_fd, path, limit)
    if path.endswith("/manifest.json"):
        return True
    return raw.startswith(MARKER_PREFIX)


def apply_reading_publication(*, prepared, vault_root, confirm, _fault=None):
    try:
        _path, batch = _prepared_slot(prepared)
    except StagingError as exc:
        if "next_action" not in exc.details:
            exc.details["next_action"] = "repair_input"
        if "instance_pointer" not in exc.details:
            exc.details["instance_pointer"] = "/prepared"
        raise
    pub = None
    snapshot = None
    staged = None
    post = None
    committed = False
    committed_paths = []
    try:
        pub = _publication_snapshot(batch)
        request, request_raw = _load_request(pub, batch)
        try:
            vault = checked_path(vault_root)
        except ContractError:
            raise
        try:
            snapshot = _Snapshot(vault)
        except ContractError as exc:
            _map_snapshot(exc)
        except OSError as exc:
            _map_snapshot(ContractError("AUDIT_RACE", "Vault root is unavailable", {"errno": exc.errno}))
        domain_store = _load_store(snapshot)
        authority = _load_authority(snapshot, required=True)
        exp = _load_experiment_store(snapshot)
        art = _load_article_store(snapshot)
        current_basis = _article_basis(snapshot, domain_store, authority, exp, art)
        loaded = _restage_against_request(batch, request)
        staged = loaded["snapshot"]
        pages = loaded["manifest"]["pages"]
        plan = _plan_targets(snapshot.root_fd, pages)
        if _already_applied(snapshot.root_fd, plan, request):
            _fail("READING_APPLY_ALREADY_APPLIED", "/payloads", "discard_batch")
        if current_basis != request["basis"]:
            raise ReadingPublicationError(
                "READING_PUBLICATION_STALE",
                "reading publication request basis is stale",
                {"instance_pointer": "/basis", "next_action": "recompile"},
                exit_code=75,
            )
        if not _plans_match(plan, request):
            raise ReadingPublicationError(
                "READING_PUBLICATION_MISMATCH",
                "reading publication request does not match the recomputed write set",
                {"instance_pointer": "/payloads", "next_action": "recompile"},
            )
        _register_plan(snapshot, plan)
        pre = _preflight(snapshot.root_fd, request)
        create_paths = [item["path"] for item in request["payloads"] if item["mode"] == "create"]
        replace_paths = [item["path"] for item in request["payloads"] if item["mode"] == "replace"]
        delete_paths = [item["path"] for item in request["payloads"] if item["mode"] == "delete"]
        create_paths.sort(key=lambda item: item.encode("utf-8"))
        replace_paths.sort(key=lambda item: item.encode("utf-8"))
        delete_paths.sort(key=lambda item: item.encode("utf-8"))
        summary = {
            "batch_id": batch,
            "request_sha256": sha(request_raw),
            "manifest_sha256": request["manifest_sha256"],
            "basis": dict(request["basis"]),
            "install_path": INSTALL_ROOT,
            "write_plan_counts": dict(request["write_plan_counts"]),
            "create_paths": create_paths,
            "replace_paths": replace_paths,
            "delete_paths": delete_paths,
            "kept_count": request["write_plan_counts"]["keep"],
            "foreign_count": request["write_plan_counts"]["foreign"],
        }
        if not confirm(summary):
            _fail("HUMAN_APPROVAL_REQUIRED", "/confirm", "confirm_interactively")
        try:
            pub.verify()
            staged.verify()
            snapshot.verify()
        except ContractError:
            _fail("READING_APPLY_CHANGED", "/confirm", "repeat_apply", exit_code=75)
        except OSError:
            _fail("READING_APPLY_CHANGED", "/confirm", "repeat_apply", exit_code=75)
        write_set = {item["path"] for item in request["payloads"] if item["mode"] in {"create", "replace", "delete"}}
        created_dirs = []
        created_files = []
        pending_renames = []
        removed_dirs = []
        page_bytes = loaded["pages"]
        phase = "before-create"
        try:
            if _fault is not None:
                _fault("before-create")
            wiki_fd = _open_existing_dir(snapshot.root_fd, "wiki", "wiki", required=True)
            try:
                reading_fd = _ensure_dir(wiki_fd, "reading", INSTALL_ROOT, created_dirs)
                try:
                    phase = "write"
                    ordered = sorted(request["payloads"], key=lambda item: item["path"].encode("utf-8"))
                    for item in ordered:
                        if item["mode"] == "keep" or item["mode"] == "delete":
                            continue
                        rel = item["path"][len(INSTALL_PREFIX) :]
                        data = page_bytes[rel]
                        parent_fd, fds, name = _ensure_parent(snapshot.root_fd, item["path"], created_dirs)
                        try:
                            if item["mode"] == "create":
                                _write_excl(parent_fd, name, data, created_files, item["path"])
                            else:
                                tmp = "." + name + "." + secrets.token_hex(12) + ".tmp"
                                tmp_path = _parent_dir_rel(item["path"]) + "/" + tmp
                                _write_excl(parent_fd, tmp, data, created_files, tmp_path)
                                pending_renames.append(
                                    {
                                        "dir_rel": _parent_dir_rel(item["path"]),
                                        "tmp": tmp,
                                        "name": name,
                                        "path": item["path"],
                                    }
                                )
                        finally:
                            _close_all(fds)
                    phase = "before-commit"
                    if _fault is not None:
                        _fault("before-commit")
                    for item in ordered:
                        if item["mode"] in {"replace", "delete"}:
                            _check_before(snapshot.root_fd, item["path"], item["before_sha256"])
                    committed = True
                    phase = "commit"
                    pending_renames.sort(key=lambda row: row["path"].encode("utf-8"))
                    for row in pending_renames:
                        dir_fd, fds = _open_dir_rel(snapshot.root_fd, row["dir_rel"])
                        try:
                            os.rename(row["tmp"], row["name"], src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                            committed_paths.append(row["path"])
                        finally:
                            _close_all(fds)
                    for path in delete_paths:
                        _unlink_relative(snapshot.root_fd, path)
                        committed_paths.append(path)
                    removed_dirs = _empty_after_delete(snapshot.root_fd, delete_paths)
                    touched_dirs = {INSTALL_ROOT}
                    for path in create_paths + replace_paths + delete_paths + created_dirs:
                        touched_dirs.add(_parent_dir_rel(path) if path != INSTALL_ROOT else INSTALL_ROOT)
                    for relative in sorted(touched_dirs, key=lambda item: item.encode("utf-8")):
                        if _stat_via_root(snapshot.root_fd, relative) is None:
                            continue
                        dir_fd, fds = _open_dir_rel(snapshot.root_fd, relative)
                        try:
                            os.fsync(dir_fd)
                        finally:
                            _close_all(fds)
                    phase = "after-commit"
                    if _fault is not None:
                        _fault("after-commit")
                finally:
                    close_fd(reading_fd)
            finally:
                close_fd(wiki_fd)
        except ReadingApplyError as exc:
            if not committed:
                rolled, complete = _rollback(snapshot.root_fd, created_files, created_dirs)
                exc.details.setdefault("phase", phase)
                exc.details.setdefault("rolled_back", rolled)
                exc.details.setdefault("rollback_complete", complete)
                raise
            _verify_failed(
                {
                    "phase": phase,
                    "prior_code": exc.code,
                    "reason": exc.details.get("reason"),
                    "committed_paths": list(committed_paths),
                    **dict(exc.details),
                }
            )
        except ReadingPublicationError as exc:
            if not committed:
                rolled, complete = _rollback(snapshot.root_fd, created_files, created_dirs)
                extra = {
                    "phase": phase,
                    "rolled_back": rolled,
                    "rollback_complete": complete,
                }
                _fail("READING_APPLY_WRITE_FAILED", "/wiki/reading", "retry_apply", extra)
            _verify_failed(
                {
                    "phase": phase,
                    "prior_code": exc.code,
                    "reason": exc.details.get("reason"),
                    "committed_paths": list(committed_paths),
                    **dict(exc.details),
                }
            )
        except OSError as exc:
            if not committed:
                rolled, complete = _rollback(snapshot.root_fd, created_files, created_dirs)
                _write_failed(exc, phase, rolled, complete)
            _verify_failed(
                {
                    "reason": "oserror",
                    "errno": exc.errno,
                    "phase": phase,
                    "committed_paths": list(committed_paths),
                }
            )
        except Exception as exc:
            if not committed:
                rolled, complete = _rollback(snapshot.root_fd, created_files, created_dirs)
                extra = {
                    "phase": phase,
                    "rolled_back": rolled,
                    "rollback_complete": complete,
                    "prior_type": type(exc).__name__,
                }
                _fail("READING_APPLY_WRITE_FAILED", "/wiki/reading", "retry_apply", extra)
            _verify_failed(
                {
                    "reason": "after-commit",
                    "prior_type": type(exc).__name__,
                    "committed_paths": list(committed_paths),
                    "phase": phase,
                }
            )
        try:
            post = _post_verify(
                vault,
                request,
                snapshot,
                pages,
                write_set,
                created_dirs,
                removed_dirs,
                pre["notes"],
                pre["foreign"],
                staged,
                pub,
            )
        except ReadingApplyError as exc:
            if committed and exc.code == "READING_APPLY_VERIFY_FAILED":
                exc.details["committed_paths"] = list(committed_paths)
                exc.details["next_action"] = "repair_store"
            raise
        except ReadingPublicationError as exc:
            _verify_failed(
                {
                    "phase": "after-commit",
                    "prior_code": exc.code,
                    "reason": exc.details.get("reason"),
                    "committed_paths": list(committed_paths),
                    **dict(exc.details),
                }
            )
        applied_paths = [item["path"] for item in request["payloads"] if item["mode"] in {"create", "replace"}]
        applied_paths.sort(key=lambda item: item.encode("utf-8"))
        kept_paths = [item["path"] for item in request["payloads"] if item["mode"] == "keep"]
        kept_paths.sort(key=lambda item: item.encode("utf-8"))
        result = {
            "schema": RESULT_SCHEMA,
            "batch_id": batch,
            "request_sha256": sha(request_raw),
            "manifest_sha256": request["manifest_sha256"],
            "basis": request["basis"],
            "graph_sha256": request["graph_sha256"],
            "matrix_sha256": request["matrix_sha256"],
            "articles_batch": request["articles_batch"],
            "counts": request["counts"],
            "install_path": INSTALL_ROOT,
            "reading_notes_root": NOTES_ROOT,
            "applied_paths": applied_paths,
            "kept_paths": kept_paths,
            "deleted_paths": delete_paths,
            "foreign_paths": list(request["foreign_paths"]),
            "created_dirs": list(dict.fromkeys(created_dirs)),
            "removed_dirs": list(dict.fromkeys(removed_dirs)),
            "write_plan_counts": request["write_plan_counts"],
            "payload_count": len(request["payloads"]),
            "write_kind": "direct_vault_write",
            "applied": True,
            "vault_written": True,
            "publication": "unpublished",
            "receipt_backed": False,
            "audit_coverage": "not_wired",
            "backup_coverage": "not_wired",
            "transaction_authority": "not_wired",
            "reading_notes_written": False,
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "typed_fact_promotion": "none",
            "ranking": "not_ranked",
            "next_action": "open_in_obsidian",
        }
        try:
            validate_document(result, RESULT_SCHEMA)
        except ContractError:
            raise
        return result
    except (
        ReadingApplyError,
        ReadingPublicationError,
        ArticleStoreError,
        ExperimentStoreError,
        DomainStoreError,
        DomainPublicationError,
        DomainProposalError,
        StagingError,
        ContractError,
        SecureIOError,
    ):
        raise
    except OSError as exc:
        if committed:
            _verify_failed({"reason": "oserror", "errno": exc.errno, "committed_paths": list(committed_paths)})
        extra = {"phase": "write", "rolled_back": [], "rollback_complete": True, "errno": exc.errno}
        _fail("READING_APPLY_WRITE_FAILED", "/wiki/reading", "retry_apply", extra)
    finally:
        if post is not None:
            post.close()
        if snapshot is not None:
            snapshot.close()
        if staged is not None:
            staged.close()
        if pub is not None:
            pub.close()
