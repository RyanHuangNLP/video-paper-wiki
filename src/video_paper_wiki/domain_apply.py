"""Direct fail-closed apply of a compiled domain publication request.

Writes only under wiki/meta/domain/** via vpwiki-admin. No receipt, audit,
backup, transaction authority, or canonical official fact is produced.
"""

from __future__ import annotations

import os
import secrets
import stat

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain_proposal import DomainProposalError
from video_paper_wiki.domain_publication import (
    DomainPublicationError,
    _basis,
    _build_request,
    _inventory_digest,
    _inventory_rows,
    _load_publication,
    _prepared_slot,
    _publication_snapshot,
    _staged_from_content,
)
from video_paper_wiki.domain_store import (
    DOMAIN_ROOT,
    DomainStoreError,
    _load_authority,
    _load_store,
    _map_snapshot,
)
from video_paper_wiki.receipt_audit import _Snapshot
from video_paper_wiki.secure_io import SecureIOError, close_fd, dir_open_flags, stamp
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import StagingError

RESULT_SCHEMA = "video-paper-wiki.domain-publication-apply-result.v1"
HEADS_PATH = DOMAIN_ROOT + "/heads.json"
MAX_RECORD_BYTES = 1_048_576
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    WRITE_FLAGS |= os.O_NOFOLLOW
if hasattr(os, "O_CLOEXEC"):
    WRITE_FLAGS |= os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY
if hasattr(os, "O_NOFOLLOW"):
    READ_FLAGS |= os.O_NOFOLLOW
if hasattr(os, "O_CLOEXEC"):
    READ_FLAGS |= os.O_CLOEXEC
MESSAGES = {
    "DOMAIN_APPLY_ALREADY_APPLIED": "domain publication is already applied",
    "DOMAIN_APPLY_VAULT_INVALID": "domain apply vault shape is invalid",
    "DOMAIN_APPLY_WRITE_FAILED": "domain apply write failed",
    "DOMAIN_APPLY_CHANGED": "domain apply inputs changed after confirmation",
    "DOMAIN_APPLY_VERIFY_FAILED": "domain apply post-write verification failed",
    "HUMAN_APPROVAL_REQUIRED": "interactive confirmation is required",
}


class DomainApplyError(Exception):
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
    raise DomainApplyError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def _close_all(fds):
    for fd in reversed(fds):
        close_fd(fd)


def _stat_child(parent_fd, name):
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _dir_id(st):
    return (st.st_dev, st.st_ino, stat.S_IMODE(st.st_mode))


def _heads_item(request):
    for item in request["payloads"]:
        if item["path"] == HEADS_PATH:
            return item
    _fail(
        "DOMAIN_APPLY_VAULT_INVALID",
        "/payloads",
        "repair_store",
        {"reason": "missing_parent", "path": HEADS_PATH},
    )


def _read_child(parent_fd, name, *, max_bytes=MAX_RECORD_BYTES):
    fd = os.open(name, READ_FLAGS, dir_fd=parent_fd)
    try:
        chunks = []
        total = 0
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            total += len(part)
            if total > max_bytes:
                raise OSError("too large")
            chunks.append(part)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_excl(parent_fd, name, data):
    fd = os.open(name, WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    try:
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
            "DOMAIN_APPLY_VAULT_INVALID",
            "/" + name,
            "repair_store",
            {"reason": "entry_kind", "path": name},
        )
    if st.st_nlink != 1:
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/" + name,
            "repair_store",
            {"reason": "hardlink", "path": name},
        )
    if st.st_size != len(data):
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
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
                "DOMAIN_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "missing_parent", "path": relative},
            )
        return None
    if stat.S_ISLNK(st.st_mode):
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            _pointer(*relative.split("/")),
            "repair_store",
            {"reason": "symlink", "path": relative},
        )
    if not stat.S_ISDIR(st.st_mode):
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
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
                "DOMAIN_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "symlink", "path": relative, "phase": "write"},
            )
        if not stat.S_ISDIR(st.st_mode):
            _fail(
                "DOMAIN_APPLY_VAULT_INVALID",
                _pointer(*relative.split("/")),
                "repair_store",
                {"reason": "entry_kind", "path": relative, "phase": "write"},
            )
    return os.open(name, dir_open_flags(), dir_fd=parent_fd)


def _unlink_relative(root_fd, relative):
    parts = relative.split("/")
    fds = []
    parent = root_fd
    try:
        for name in parts[:-1]:
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
        os.unlink(parts[-1], dir_fd=parent)
    finally:
        _close_all(fds)


def _rmdir_relative(root_fd, relative):
    parts = relative.split("/")
    fds = []
    parent = root_fd
    try:
        for name in parts[:-1]:
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
        os.rmdir(parts[-1], dir_fd=parent)
    finally:
        _close_all(fds)


def _rollback(root_fd, tmp_name, created_files, created_dirs, *, heads_mode, heads_existed):
    rolled = []
    complete = True

    def note(relative):
        rolled.append(relative)

    if tmp_name:
        try:
            _unlink_relative(root_fd, DOMAIN_ROOT + "/" + tmp_name)
            note(DOMAIN_ROOT + "/" + tmp_name)
        except OSError:
            if _stat_via_root(root_fd, DOMAIN_ROOT + "/" + tmp_name) is not None:
                complete = False
    for relative in reversed(created_files):
        try:
            _unlink_relative(root_fd, relative)
            note(relative)
        except OSError:
            if _stat_via_root(root_fd, relative) is not None:
                complete = False
    if heads_mode == "create" and not heads_existed:
        try:
            if _stat_via_root(root_fd, HEADS_PATH) is not None:
                _unlink_relative(root_fd, HEADS_PATH)
                note(HEADS_PATH)
        except OSError:
            if _stat_via_root(root_fd, HEADS_PATH) is not None:
                complete = False
    for relative in reversed(created_dirs):
        try:
            _rmdir_relative(root_fd, relative)
            note(relative)
        except OSError:
            if _stat_via_root(root_fd, relative) is not None:
                complete = False
    return rolled, complete


def _stat_via_root(root_fd, relative):
    parts = relative.split("/")
    fds = []
    parent = root_fd
    try:
        for name in parts[:-1]:
            st = _stat_child(parent, name)
            if st is None:
                return None
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
        return _stat_child(parent, parts[-1])
    except OSError:
        return None
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
                if index < 2:
                    _fail(
                        "DOMAIN_APPLY_VAULT_INVALID",
                        _pointer(*relative.split("/")),
                        "repair_store",
                        {"reason": "missing_parent", "path": relative},
                    )
                return
            if last:
                if stat.S_ISLNK(st.st_mode):
                    _fail(
                        "DOMAIN_APPLY_VAULT_INVALID",
                        _pointer(*relative.split("/")),
                        "repair_store",
                        {"reason": "symlink", "path": relative},
                    )
                _fail(
                    "DOMAIN_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "target_exists", "path": relative},
                )
            if stat.S_ISLNK(st.st_mode):
                _fail(
                    "DOMAIN_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "symlink", "path": relative},
                )
            if not stat.S_ISDIR(st.st_mode):
                _fail(
                    "DOMAIN_APPLY_VAULT_INVALID",
                    _pointer(*relative.split("/")),
                    "repair_store",
                    {"reason": "entry_kind", "path": relative},
                )
            fd = os.open(name, dir_open_flags(), dir_fd=parent)
            fds.append(fd)
            parent = fd
    finally:
        _close_all(fds)


def _check_heads(domain_fd, item):
    st = _stat_child(domain_fd, "heads.json")
    if item["mode"] == "create":
        if st is None:
            return
        if stat.S_ISLNK(st.st_mode):
            _fail(
                "DOMAIN_APPLY_VAULT_INVALID",
                "/wiki/meta/domain/heads.json",
                "repair_store",
                {"reason": "symlink", "path": HEADS_PATH},
            )
        if not stat.S_ISREG(st.st_mode):
            _fail(
                "DOMAIN_APPLY_VAULT_INVALID",
                "/wiki/meta/domain/heads.json",
                "repair_store",
                {"reason": "entry_kind", "path": HEADS_PATH},
            )
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "heads_before", "path": HEADS_PATH},
        )
    if st is None:
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "heads_before", "path": HEADS_PATH},
        )
    if stat.S_ISLNK(st.st_mode):
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "symlink", "path": HEADS_PATH},
        )
    if not stat.S_ISREG(st.st_mode):
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "entry_kind", "path": HEADS_PATH},
        )
    if st.st_nlink != 1:
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "hardlink", "path": HEADS_PATH},
        )
    raw = _read_child(domain_fd, "heads.json")
    if sha(raw) != item["before_sha256"]:
        _fail(
            "DOMAIN_APPLY_VAULT_INVALID",
            "/wiki/meta/domain/heads.json",
            "repair_store",
            {"reason": "heads_before", "path": HEADS_PATH},
        )


def _preflight(root_fd, request):
    wiki_fd = _open_existing_dir(root_fd, "wiki", "wiki", required=True)
    try:
        meta_fd = _open_existing_dir(wiki_fd, "meta", "wiki/meta", required=True)
        try:
            domain_fd = _open_existing_dir(meta_fd, "domain", DOMAIN_ROOT, required=False)
            try:
                if domain_fd is not None:
                    for kind in ("annotations", "reviews"):
                        kind_fd = _open_existing_dir(
                            domain_fd, kind, DOMAIN_ROOT + "/" + kind, required=False
                        )
                        if kind_fd is None:
                            continue
                        try:
                            try:
                                names = sorted(os.listdir(kind_fd))
                            except OSError as exc:
                                raise OSError(exc.errno, exc.strerror) from exc
                            for lineage in names:
                                lineage_rel = DOMAIN_ROOT + "/" + kind + "/" + lineage
                                child = _open_existing_dir(
                                    kind_fd, lineage, lineage_rel, required=False
                                )
                                if child is not None:
                                    close_fd(child)
                        finally:
                            close_fd(kind_fd)
                    _check_heads(domain_fd, _heads_item(request))
                else:
                    heads = _heads_item(request)
                    if heads["mode"] != "create":
                        _fail(
                            "DOMAIN_APPLY_VAULT_INVALID",
                            "/wiki/meta/domain/heads.json",
                            "repair_store",
                            {"reason": "heads_before", "path": HEADS_PATH},
                        )
            finally:
                if domain_fd is not None:
                    close_fd(domain_fd)
        finally:
            close_fd(meta_fd)
    finally:
        close_fd(wiki_fd)
    for item in request["payloads"]:
        if item["path"] == HEADS_PATH:
            continue
        if item["mode"] == "create":
            _check_create_absent(root_fd, item["path"])
        else:
            _fail(
                "DOMAIN_APPLY_VAULT_INVALID",
                _pointer(*item["path"].split("/")),
                "repair_store",
                {"reason": "entry_kind", "path": item["path"]},
            )


def _open_domain_stack(root_fd, created_dirs):
    wiki_fd = _open_existing_dir(root_fd, "wiki", "wiki", required=True)
    try:
        meta_fd = _open_existing_dir(wiki_fd, "meta", "wiki/meta", required=True)
    except BaseException:
        close_fd(wiki_fd)
        raise
    try:
        domain_fd = _ensure_dir(meta_fd, "domain", DOMAIN_ROOT, created_dirs)
    except BaseException:
        close_fd(meta_fd)
        close_fd(wiki_fd)
        raise
    return wiki_fd, meta_fd, domain_fd


def _write_create_payloads(domain_fd, request, content, created_dirs, created_files):
    kind_fds = {}
    lineage_fds = {}
    try:
        for item in sorted(request["payloads"], key=lambda row: row["path"].encode("utf-8")):
            if item["path"] == HEADS_PATH:
                continue
            suffix = item["path"][len(DOMAIN_ROOT) + 1 :]
            parts = suffix.split("/")
            kind, lineage, filename = parts[0], parts[1], parts[2]
            kind_rel = DOMAIN_ROOT + "/" + kind
            lineage_rel = kind_rel + "/" + lineage
            if kind not in kind_fds:
                kind_fds[kind] = _ensure_dir(domain_fd, kind, kind_rel, created_dirs)
            if lineage_rel not in lineage_fds:
                lineage_fds[lineage_rel] = _ensure_dir(
                    kind_fds[kind], lineage, lineage_rel, created_dirs
                )
            parent_fd = lineage_fds[lineage_rel]
            _write_excl(parent_fd, filename, content[item["after_sha256"]])
            created_files.append(item["path"])
    finally:
        for fd in lineage_fds.values():
            close_fd(fd)
        for fd in kind_fds.values():
            close_fd(fd)


def _write_failed(exc, phase, rolled, complete):
    extra = {
        "phase": phase,
        "rolled_back": list(rolled),
        "rollback_complete": bool(complete),
    }
    if isinstance(exc, OSError):
        extra["errno"] = exc.errno
    _fail("DOMAIN_APPLY_WRITE_FAILED", "/wiki/meta/domain", "retry_apply", extra)


def _verify_failed(extra):
    details = {"phase": "after-commit", "next_action": "repair_store"}
    details.update(extra)
    if "instance_pointer" not in details:
        details["instance_pointer"] = "/wiki/meta/domain"
    raise DomainApplyError(
        "DOMAIN_APPLY_VERIFY_FAILED",
        MESSAGES["DOMAIN_APPLY_VERIFY_FAILED"],
        details,
        exit_code=2,
    )


def _post_verify(
    vault,
    request,
    store,
    snapshot,
    write_set,
    created_dirs,
    applied_inventory,
):
    try:
        post = _Snapshot(vault)
    except ContractError as exc:
        _verify_failed({"prior_code": exc.code, **dict(exc.details)})
    except OSError as exc:
        _verify_failed({"reason": "snapshot", "errno": exc.errno})
    try:
        try:
            post_store = _load_store(post)
        except DomainStoreError as exc:
            _verify_failed(
                {
                    "prior_code": exc.code,
                    "instance_pointer": exc.details.get("instance_pointer", "/wiki/meta/domain"),
                    **dict(exc.details),
                }
            )
        except ContractError as exc:
            _map_snapshot(exc)
        digest = _inventory_digest(post_store)
        if digest != request["prospective_inventory_sha256"] or digest != applied_inventory:
            _verify_failed({"reason": "inventory_digest", "path": DOMAIN_ROOT})
        pre_rows = {tuple(row) for row in _inventory_rows(store)}
        expected = {row for row in pre_rows if row[0] != HEADS_PATH}
        for item in request["payloads"]:
            expected.add((item["path"], item["after_sha256"], item["size_bytes"]))
        post_rows = {tuple(row) for row in _inventory_rows(post_store)}
        if post_rows != expected:
            _verify_failed({"reason": "inventory_rows", "path": DOMAIN_ROOT})
        try:
            post_auth = _load_authority(post, required=True)
        except DomainStoreError as exc:
            _verify_failed({"prior_code": exc.code, **dict(exc.details)})
        post_basis = _basis(post, post_store, post_auth)
        if (
            post_basis["claim_ledger_sha256"] != request["basis"]["claim_ledger_sha256"]
            or post_basis["assessment_heads_sha256"] != request["basis"]["assessment_heads_sha256"]
        ):
            _verify_failed({"reason": "authority", "path": "/basis"})
        for relative, (first, _raw) in snapshot.files.items():
            if relative in write_set:
                continue
            try:
                current = post._current_stat(relative)
            except ContractError as exc:
                _verify_failed({"prior_code": exc.code, "path": relative, **dict(exc.details)})
            if stamp(current) != stamp(first):
                _verify_failed({"reason": "file_stamp", "path": relative})
        for relative, first in snapshot.directories.items():
            if not relative:
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
        for path in write_set:
            try:
                current = post._current_stat(path)
            except ContractError as exc:
                _verify_failed({"prior_code": exc.code, "path": path, **dict(exc.details)})
            if stat.S_IMODE(current.st_mode) != 0o600 or not stat.S_ISREG(current.st_mode):
                _verify_failed({"reason": "mode", "path": path})
        for relative in created_dirs:
            try:
                fd, _parts = post._parent_fd(relative + "/probe", allow_missing=False)
                try:
                    current = os.fstat(fd)
                finally:
                    close_fd(fd)
            except ContractError as exc:
                _verify_failed({"prior_code": exc.code, "path": relative, **dict(exc.details)})
            except OSError as exc:
                _verify_failed({"reason": "created_dir", "path": relative, "errno": exc.errno})
            if stat.S_IMODE(current.st_mode) != 0o700 or not stat.S_ISDIR(current.st_mode):
                _verify_failed({"reason": "mode", "path": relative})
        try:
            post.verify()
        except ContractError as exc:
            _verify_failed({"prior_code": exc.code, **dict(exc.details)})
        return post, post_store, digest
    except Exception:
        post.close()
        raise


def apply_domain_publication(*, prepared, vault_root, confirm, _fault=None):
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
    post = None
    committed = False
    try:
        pub = _publication_snapshot(batch)
        request, request_raw, content = _load_publication(pub, batch)
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
        try:
            store = _load_store(snapshot)
        except ContractError as exc:
            _map_snapshot(exc)
        authority = _load_authority(snapshot, required=True)
        current_basis = _basis(snapshot, store, authority)
        request_basis = request["basis"]
        if (
            current_basis["domain_store_inventory_sha256"] == request["prospective_inventory_sha256"]
            and current_basis["claim_ledger_sha256"] == request_basis["claim_ledger_sha256"]
            and current_basis["assessment_heads_sha256"] == request_basis["assessment_heads_sha256"]
        ):
            _fail(
                "DOMAIN_APPLY_ALREADY_APPLIED",
                "/prospective_inventory_sha256",
                "discard_batch",
            )
        if current_basis != request_basis:
            raise DomainPublicationError(
                "DOMAIN_PUBLICATION_STALE",
                "domain publication request basis is stale",
                {"instance_pointer": "/basis", "next_action": "recompile"},
                exit_code=75,
            )
        staged = _staged_from_content(request, content)
        rebuilt = _build_request(snapshot, store, authority, batch, staged)
        if (
            rebuilt["request"]["payloads"] != request["payloads"]
            or rebuilt["request"]["touched_lineages"] != request["touched_lineages"]
            or rebuilt["request"]["prospective_inventory_sha256"] != request["prospective_inventory_sha256"]
        ):
            raise DomainPublicationError(
                "DOMAIN_PUBLICATION_MISMATCH",
                "domain publication request does not match the recomputed write set",
                {"instance_pointer": "/payloads", "next_action": "recompile"},
            )
        _preflight(snapshot.root_fd, request)
        heads = _heads_item(request)
        summary = {
            "batch_id": batch,
            "request_sha256": sha(request_raw),
            "basis": dict(request["basis"]),
            "heads_mode": heads["mode"],
            "heads_before_sha256": heads["before_sha256"],
            "changed_paths": [item["path"] for item in request["payloads"]],
            "payload_count": len(request["payloads"]),
        }
        if not confirm(summary):
            _fail("HUMAN_APPROVAL_REQUIRED", "/confirm", "confirm_interactively")
        try:
            pub.verify()
            snapshot.verify()
        except ContractError:
            _fail("DOMAIN_APPLY_CHANGED", "/confirm", "repeat_apply", exit_code=75)
        except OSError:
            _fail("DOMAIN_APPLY_CHANGED", "/confirm", "repeat_apply", exit_code=75)
        write_set = {item["path"] for item in request["payloads"]}
        created_dirs = []
        created_files = []
        tmp_name = None
        wiki_fd = meta_fd = domain_fd = None
        heads_existed = _stat_via_root(snapshot.root_fd, HEADS_PATH) is not None
        phase = "before-create"
        try:
            if _fault is not None:
                _fault("before-create")
            wiki_fd, meta_fd, domain_fd = _open_domain_stack(snapshot.root_fd, created_dirs)
            phase = "write"
            _write_create_payloads(domain_fd, request, content, created_dirs, created_files)
            tmp_name = ".heads.json." + secrets.token_hex(12) + ".tmp"
            phase = "before-commit"
            _write_excl(domain_fd, tmp_name, content[heads["after_sha256"]])
            if _fault is not None:
                _fault("before-commit")
            _check_heads(domain_fd, heads)
            os.rename(tmp_name, "heads.json", src_dir_fd=domain_fd, dst_dir_fd=domain_fd)
            committed = True
            tmp_name = None
            os.fsync(domain_fd)
            phase = "after-commit"
            if _fault is not None:
                _fault("after-commit")
        except DomainApplyError as exc:
            if not committed:
                rolled, complete = _rollback(
                    snapshot.root_fd,
                    tmp_name,
                    created_files,
                    created_dirs,
                    heads_mode=heads["mode"],
                    heads_existed=heads_existed,
                )
                exc.details.setdefault("phase", phase)
                exc.details.setdefault("rolled_back", rolled)
                exc.details.setdefault("rollback_complete", complete)
            raise
        except OSError as exc:
            if not committed:
                rolled, complete = _rollback(
                    snapshot.root_fd,
                    tmp_name,
                    created_files,
                    created_dirs,
                    heads_mode=heads["mode"],
                    heads_existed=heads_existed,
                )
                _write_failed(exc, phase, rolled, complete)
            _verify_failed({"reason": "oserror", "errno": exc.errno, "phase": phase})
        except Exception as exc:
            if not committed:
                rolled, complete = _rollback(
                    snapshot.root_fd,
                    tmp_name,
                    created_files,
                    created_dirs,
                    heads_mode=heads["mode"],
                    heads_existed=heads_existed,
                )
                extra = {
                    "phase": phase,
                    "rolled_back": rolled,
                    "rollback_complete": complete,
                    "prior_type": type(exc).__name__,
                }
                _fail("DOMAIN_APPLY_WRITE_FAILED", "/wiki/meta/domain", "retry_apply", extra)
            _verify_failed({"reason": "after-commit", "prior_type": type(exc).__name__})
        finally:
            if domain_fd is not None:
                close_fd(domain_fd)
            if meta_fd is not None:
                close_fd(meta_fd)
            if wiki_fd is not None:
                close_fd(wiki_fd)
        post, _post_store, applied_inventory = _post_verify(
            vault,
            request,
            store,
            snapshot,
            write_set,
            created_dirs,
            request["prospective_inventory_sha256"],
        )
        applied_paths = [item["path"] for item in request["payloads"]]
        result = {
            "schema": RESULT_SCHEMA,
            "batch_id": batch,
            "request_sha256": sha(request_raw),
            "basis": request["basis"],
            "prospective_inventory_sha256": request["prospective_inventory_sha256"],
            "applied_inventory_sha256": applied_inventory,
            "touched_lineages": list(request["touched_lineages"]),
            "applied_paths": list(applied_paths),
            "payload_count": len(request["payloads"]),
            "heads_mode": heads["mode"],
            "heads_before_sha256": heads["before_sha256"],
            "write_kind": "direct_store_write",
            "applied": True,
            "publication": "unpublished",
            "receipt_backed": False,
            "audit_coverage": "not_wired",
            "backup_coverage": "not_wired",
            "transaction_authority": "not_wired",
            "canonical_official": False,
            "current_supported_typed_fact": False,
            "next_action": "domain_status",
        }
        try:
            validate_document(result, RESULT_SCHEMA)
        except ContractError:
            raise
        try:
            pub.verify()
        except ContractError as exc:
            _verify_failed({"prior_code": exc.code, "path": "domain-publication", **dict(exc.details)})
        return result
    except (DomainApplyError, DomainStoreError, DomainPublicationError, DomainProposalError, StagingError, ContractError, SecureIOError):
        raise
    except OSError as exc:
        if committed:
            _verify_failed({"reason": "oserror", "errno": exc.errno})
        extra = {"phase": "write", "rolled_back": [], "rollback_complete": True, "errno": exc.errno}
        _fail("DOMAIN_APPLY_WRITE_FAILED", "/wiki/meta/domain", "retry_apply", extra)
    finally:
        if post is not None:
            post.close()
        if snapshot is not None:
            snapshot.close()
        if pub is not None:
            pub.close()
