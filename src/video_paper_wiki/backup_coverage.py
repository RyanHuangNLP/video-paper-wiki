"""Bounded p3-r1 research coverage. Whitelist layouts only; never pack ``.work/**``."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any

from video_paper_wiki.contracts import SCHEMA_INVALID, ContractError
from video_paper_wiki.secure_io import close_fd, dir_open_flags, file_open_flags, open_dir_nofollow, stamp

SCHEMA_V1 = "video-paper-wiki.backup-manifest.v1"
SCHEMA_V2 = "video-paper-wiki.backup-manifest.v2"
PROFILE_V1 = "vault-v1"
PROFILE_V2 = "research-r1"
POLICY_V2 = "vpwiki-private-research-complete-set-r1"
COVERAGE_VERSION = "p3-r1"
PROFILE_SCHEMA = {PROFILE_V1: SCHEMA_V1, PROFILE_V2: SCHEMA_V2}
RESEARCH_ROOTS = [".raw", "wiki", ".work"]
RULES = (
    "code-evidence",
    "flow",
    "domain",
    "experiments",
    "articles",
    "draft",
    "review",
    "plan",
)
RULE_DIR = {
    "code-evidence": "code-evidence-v1",
    "flow": "flow",
    "domain": "domain",
    "experiments": "experiments",
    "articles": "articles",
    "draft": "draft",
    "review": "review",
    "plan": "plan",
}
REBUILDABLE_BATCH_DIRS = {
    "source-catalog": ".work/*/source-catalog/**",
    "reading": ".work/*/reading/**",
    "domain-publication": ".work/*/domain-publication/**",
    "experiment-publication": ".work/*/experiment-publication/**",
    "article-publication": ".work/*/article-publication/**",
    "reading-publication": ".work/*/reading-publication/**",
}
MAX_BATCHES = 128
MAX_CANDIDATES = 4096
RESERVED_WORK_DIRS = {"blobs", "pdf-migration", "research"}
_SETTING_KEY_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_FIXED_EXCLUDED = (
    {"root": "checkout", "path": ".light-knowledge/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".light-library/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".light-workflow/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".work/*/article-publication/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/*/domain-publication/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/*/experiment-publication/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/*/reading-publication/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/*/reading/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/*/source-catalog/**", "reason": "rebuildable"},
    {"root": "checkout", "path": ".work/blobs/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".work/pdf-migration/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".work/research/*/discovery-v1/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".work/research/*/manual-pdf/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": ".work/research/*/preview-v1/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": "<custom-files-outside-p3-r1-whitelist>", "reason": "out_of_scope"},
    {"root": "checkout", "path": "<external-pdf>", "reason": "out_of_scope"},
    {"root": "checkout", "path": "<lightweight-writing-and-external-outputs>", "reason": "out_of_scope"},
    {"root": "checkout", "path": "<other-capture-conversion-publication-inputs>", "reason": "out_of_scope"},
    {"root": "checkout", "path": "<temporary-worktrees>", "reason": "out_of_scope"},
    {"root": "checkout", "path": "VPWIKI_BLOB_ROOT/**", "reason": "out_of_scope"},
    {"root": "checkout", "path": "papers/**", "reason": "out_of_scope"},
    {"root": "vault", "path": ".vault-meta/**", "reason": "rebuildable"},
)

def fixed_excluded() -> list[dict[str, str]]:
    """Explanatory exclusions. Patterns are not permission to read arbitrary files."""
    rows = [dict(row) for row in _FIXED_EXCLUDED]
    rows.sort(key=lambda row: (row["root"].encode(), row["path"].encode(), row["reason"].encode()))
    return rows


def _fail(message: str, path: str | None = None) -> None:
    details: dict[str, Any] = {} if path is None else {"path": path}
    raise ContractError("BACKUP_COVERAGE_INVALID", message, details)


def _schema_fail(message: str, pointer: str) -> None:
    raise ContractError(SCHEMA_INVALID, message, {"schema": SCHEMA_V2, "instance_pointer": pointer, "keyword": "const"})


def _limits() -> tuple[int, int, int]:
    from video_paper_wiki.backup_manifest import MAX_ENTRIES, MAX_FILE_BYTES, MAX_TOTAL_BYTES
    return MAX_ENTRIES, MAX_FILE_BYTES, MAX_TOTAL_BYTES


def _portable(path: str) -> None:
    if (not path or path.startswith("/") or "\\" in path or "\x00" in path
            or unicodedata.normalize("NFC", path) != path
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        _fail("coverage path is not portable", path)


def _producer_names() -> dict[str, Any]:
    from video_paper_wiki.article_store import ARTICLE_RE, REVISION_RE
    from video_paper_wiki.code_proof_io import _FAMILY_NAMES, _HEX64_JSON_RE, _OBJECT_BODY_RE, _SLOT_NAMES
    from video_paper_wiki.commands.draft import DRAFT_FILENAME
    from video_paper_wiki.commands.plan import PLAN_FILENAME
    from video_paper_wiki.domain_store import ANNOTATION_RE, LINEAGE_RE, REVIEW_RE
    from video_paper_wiki.experiment_store import CONDITION_RE, RECORD_RE
    return {
        "slots": _SLOT_NAMES,
        "families": _FAMILY_NAMES,
        "object_re": _OBJECT_BODY_RE,
        "hex_json_re": _HEX64_JSON_RE,
        "draft": DRAFT_FILENAME,
        "plan": PLAN_FILENAME,
        "review": "paper.md",
        "lineage_re": LINEAGE_RE,
        "annotation_re": ANNOTATION_RE,
        "review_re": REVIEW_RE,
        "condition_re": CONDITION_RE,
        "record_re": RECORD_RE,
        "article_re": ARTICLE_RE,
        "revision_re": REVISION_RE,
    }


class CoverageSnapshot:
    """Retained checkout identity for one research coverage scan."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root_fd: int | None = None
        self.directories: dict[str, os.stat_result] = {}
        self.files: dict[str, tuple[os.stat_result, bytes]] = {}
        self.absent: set[str] = set()
        self.children: dict[str, tuple[str, ...]] = {}
        self.report: dict[str, Any] | None = None
        self.sealed = False
        self.entry_base = 0
        self.byte_base = 0
        try:
            self.root_stat = self.root.lstat()
        except OSError:
            _fail("checkout root is unavailable")
        if not stat.S_ISDIR(self.root_stat.st_mode) or stat.S_ISLNK(self.root_stat.st_mode):
            _fail("checkout root is unsafe")
        self.root_fd = open_dir_nofollow(self.root, missing_code="BACKUP_COVERAGE_INVALID", unsafe_code="BACKUP_COVERAGE_INVALID")
        if stamp(os.fstat(self.root_fd)) != stamp(self.root_stat):
            close_fd(self.root_fd)
            self.root_fd = None
            _fail("checkout root changed")

    def read(self, relative: str) -> bytes:
        prior = self.files.get(relative)
        if prior is None or self.root_fd is None:
            _fail("coverage file is not retained", relative)
        fd, opened = _walk_open(self.root_fd, relative, directory=False)
        try:
            if stamp(opened) != stamp(prior[0]):
                _fail("coverage file changed", relative)
            raw = _read_fd(fd, max_bytes=len(prior[1]))
        finally:
            close_fd(fd)
        if raw != prior[1] or hashlib.sha256(raw).hexdigest() != hashlib.sha256(prior[1]).hexdigest():
            _fail("coverage file changed", relative)
        return raw

    def verify(self) -> None:
        if self.root_fd is None:
            _fail("checkout root changed")
        try:
            if stamp(self.root.lstat()) != stamp(self.root_stat) or stamp(os.fstat(self.root_fd)) != stamp(self.root_stat):
                raise OSError
            for relative, first in self.directories.items():
                fd, opened = _walk_open(self.root_fd, relative, directory=True)
                close_fd(fd)
                if stamp(opened) != stamp(first):
                    raise OSError
            for relative, (first, raw) in self.files.items():
                fd, opened = _walk_open(self.root_fd, relative, directory=False)
                try:
                    if stamp(opened) != stamp(first) or _read_fd(fd, max_bytes=len(raw)) != raw:
                        raise OSError
                finally:
                    close_fd(fd)
            for relative in self.absent:
                if _exists(self.root_fd, relative):
                    raise OSError
            for relative, names in self.children.items():
                fd, _opened = _walk_open(self.root_fd, relative, directory=True)
                try:
                    found = _names_within_limit(fd, relative, len(names))
                finally:
                    close_fd(fd)
                if _sort_names(found) != names:
                    raise OSError
        except ContractError:
            raise
        except OSError:
            _fail("coverage tree changed")

    def close(self) -> None:
        close_fd(self.root_fd)
        self.root_fd = None


def _sort_names(names: list[str]) -> tuple[str, ...]:
    """Sort only after the caller has already applied the enumeration budget."""
    names.sort(key=lambda item: item.encode())
    return tuple(names)


def _names_within_limit(fd: int, relative: str, limit: int) -> list[str]:
    """Collect at most ``limit`` names. One extra name fails before the list is sorted."""
    names: list[str] = []
    try:
        for entry in os.scandir(fd):
            if len(names) >= limit:
                _fail("coverage tree changed", relative)
            if unicodedata.normalize("NFC", entry.name) != entry.name or "/" in entry.name or "\\" in entry.name or entry.name in {"", ".", ".."}:
                _fail("coverage path is not portable", relative + "/" + entry.name)
            names.append(entry.name)
    except OSError:
        _fail("coverage directory is unsafe", relative)
    return names


def _read_fd(fd: int, *, max_bytes: int | None = None) -> bytes:
    """Read at most ``max_bytes``. One extra byte detects overflow without consuming the rest."""
    chunks: list[bytes] = []
    size = 0
    while True:
        if max_bytes is not None and size >= max_bytes:
            if os.read(fd, 1):
                _fail("manifest resource limit exceeded")
            break
        room = 1024 * 1024 if max_bytes is None else min(1024 * 1024, max_bytes - size)
        chunk = os.read(fd, room)
        if not chunk:
            break
        size += len(chunk)
        if max_bytes is not None and size > max_bytes:
            _fail("manifest resource limit exceeded")
        chunks.append(chunk)
    return b"".join(chunks)


def _walk_open(root_fd: int, relative: str, *, directory: bool) -> tuple[int, os.stat_result]:
    parts = relative.split("/")
    fd = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            flags = dir_open_flags() if (not last or directory) else file_open_flags()
            try:
                nxt = os.open(part, flags, dir_fd=fd)
            except OSError:
                _fail("coverage path is unsafe", relative)
            close_fd(fd)
            fd = nxt
        return fd, os.fstat(fd)
    except ContractError:
        close_fd(fd)
        raise
    except Exception:
        close_fd(fd)
        raise


def _exists(root_fd: int, relative: str) -> bool:
    parts = relative.split("/")
    fd = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            try:
                st = os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            except OSError:
                _fail("coverage path is unsafe", relative)
            if last:
                return True
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                _fail("coverage path is unsafe", relative)
            nxt = os.open(part, dir_open_flags(), dir_fd=fd)
            close_fd(fd)
            fd = nxt
        return False
    finally:
        close_fd(fd)


def absolute_directory(path: Path | str) -> str:
    text = os.path.abspath(os.fspath(path))
    if not text.startswith("/") or "\x00" in text or len(text) > 4096:
        _fail("source root is not a safe absolute path")
    return text


def assert_distinct_or_same(vault: Path | str, checkout: Path | str) -> tuple[str, str]:
    """Allow V=C. Reject nested distinct directories so one tree is not archived twice."""
    vault_abs = absolute_directory(vault)
    checkout_abs = absolute_directory(checkout)
    try:
        vault_stat = os.lstat(vault_abs)
        checkout_stat = os.lstat(checkout_abs)
    except OSError:
        _fail("source root is unavailable")
    for label, found in (("vault", vault_stat), ("checkout", checkout_stat)):
        if stat.S_ISLNK(found.st_mode) or not stat.S_ISDIR(found.st_mode):
            _fail(label + " root is unsafe")
    same = (vault_stat.st_dev, vault_stat.st_ino) == (checkout_stat.st_dev, checkout_stat.st_ino)
    vault_parts = Path(vault_abs).parts
    checkout_parts = Path(checkout_abs).parts
    nested = vault_parts != checkout_parts and (
        vault_parts[:len(checkout_parts)] == checkout_parts or checkout_parts[:len(vault_parts)] == vault_parts
    )
    if nested and not same:
        _fail("vault and checkout roots overlap")
    return vault_abs, checkout_abs


def _sort_excluded(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        unique[(row["root"], row["path"], row["reason"])] = dict(row)
    return [unique[key] for key in sorted(unique, key=lambda item: (item[0].encode(), item[1].encode(), item[2].encode()))]


class _Scan:
    def __init__(self, snap: CoverageSnapshot, compare: bool) -> None:
        self.snap = snap
        self.compare = compare
        self.keys: dict[str, str] = {}
        self.directories: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.discovered: list[dict[str, str]] = []
        self.candidates = 0
        self.total_bytes = 0
        self.entry_base = 0
        self.byte_base = 0
        self.names = _producer_names()
        self.max_entries, self.max_file_bytes, self.max_total_bytes = _limits()

    def candidate(self) -> None:
        self.candidates += 1
        if self.candidates > MAX_CANDIDATES:
            _fail("coverage candidate limit exceeded")

    def remember_dir(self, relative: str, found: os.stat_result) -> None:
        _portable(relative)
        key = unicodedata.normalize("NFC", relative).casefold()
        if key in self.keys and self.keys[key] != relative:
            _fail("coverage path collision", relative)
        self.keys[key] = relative
        if self.compare:
            prior = self.snap.directories.get(relative)
            if prior is None or stamp(prior) != stamp(found):
                _fail("coverage tree changed", relative)
        else:
            self.snap.directories[relative] = found
        self.directories.append({"path": relative, "mode": stat.S_IMODE(found.st_mode)})
        if self.entry_base + len(self.directories) + len(self.files) > self.max_entries:
            _fail("manifest entry limit exceeded")

    def remember_file(self, relative: str, found: os.stat_result, raw: bytes) -> None:
        _portable(relative)
        key = unicodedata.normalize("NFC", relative).casefold()
        if key in self.keys and self.keys[key] != relative:
            _fail("coverage path collision", relative)
        self.keys[key] = relative
        if self.compare:
            prior = self.snap.files.get(relative)
            if prior is None or stamp(prior[0]) != stamp(found) or prior[1] != raw:
                _fail("coverage tree changed", relative)
        else:
            self.snap.files[relative] = (found, raw)
        self.files.append({
            "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "mode": stat.S_IMODE(found.st_mode),
        })
        if self.entry_base + len(self.directories) + len(self.files) > self.max_entries:
            _fail("manifest entry limit exceeded")

    def remember_children(self, relative: str, names: tuple[str, ...]) -> None:
        if self.compare:
            if self.snap.children.get(relative) != names:
                _fail("coverage tree changed", relative)
        else:
            self.snap.children[relative] = names

    def mark_absent(self, relative: str) -> None:
        if self.compare:
            if relative not in self.snap.absent:
                _fail("coverage tree changed", relative)
        else:
            self.snap.absent.add(relative)

    def _require_entry_room(self, pending: int) -> None:
        """Refuse another inner name before it is collected or sorted."""
        used = self.entry_base + len(self.directories) + len(self.files) + pending
        if used > self.max_entries:
            _fail("manifest entry limit exceeded")

    def list_names(self, fd: int, relative: str, *, count_candidates: bool) -> tuple[str, ...]:
        names: list[str] = []
        try:
            for entry in os.scandir(fd):
                if count_candidates:
                    self.candidate()
                else:
                    self._require_entry_room(len(names) + 1)
                if unicodedata.normalize("NFC", entry.name) != entry.name or "/" in entry.name or "\\" in entry.name or entry.name in {"", ".", ".."}:
                    _fail("coverage path is not portable", relative + "/" + entry.name)
                names.append(entry.name)
        except OSError:
            _fail("coverage directory is unsafe", relative)
        observed = _sort_names(names)
        self.remember_children(relative, observed)
        return observed

    def open_dir(self, parent_fd: int, name: str, relative: str) -> int:
        try:
            found = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            _fail("coverage directory is unsafe", relative)
        if stat.S_ISLNK(found.st_mode) or not stat.S_ISDIR(found.st_mode):
            _fail("coverage entry is unsafe", relative)
        try:
            fd = os.open(name, dir_open_flags(), dir_fd=parent_fd)
        except OSError:
            _fail("coverage directory is unsafe", relative)
        try:
            opened = os.fstat(fd)
            if stamp(opened) != stamp(found):
                _fail("coverage directory changed", relative)
            self.remember_dir(relative, opened)
            return fd
        except BaseException:
            close_fd(fd)
            raise

    def read_file(self, parent_fd: int, name: str, relative: str) -> None:
        try:
            found = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            _fail("coverage file is unsafe", relative)
        if stat.S_ISLNK(found.st_mode) or not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            _fail("coverage file is unsafe", relative)
        try:
            fd = os.open(name, file_open_flags(), dir_fd=parent_fd)
        except OSError:
            _fail("coverage file is unsafe", relative)
        try:
            opened = os.fstat(fd)
            if stamp(opened) != stamp(found) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                _fail("coverage file changed", relative)
            remaining = self.max_total_bytes - self.byte_base - self.total_bytes
            if remaining < 0:
                _fail("manifest resource limit exceeded", relative)
            raw = _read_fd(fd, max_bytes=min(self.max_file_bytes, remaining))
            self.total_bytes += len(raw)
            if len(raw) > self.max_file_bytes or self.total_bytes > self.max_total_bytes:
                _fail("manifest resource limit exceeded", relative)
            if stamp(os.fstat(fd)) != stamp(opened):
                _fail("coverage file changed", relative)
            self.remember_file(relative, opened, raw)
        finally:
            close_fd(fd)

    def child_kind(self, parent_fd: int, name: str, relative: str) -> str:
        try:
            found = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            _fail("coverage entry is unsafe", relative)
        if stat.S_ISLNK(found.st_mode):
            _fail("coverage entry is unsafe", relative)
        if stat.S_ISDIR(found.st_mode):
            return "dir"
        if stat.S_ISREG(found.st_mode):
            return "file"
        _fail("coverage entry is unsafe", relative)
        return "unsafe"

    def note_excluded(self, relative: str, reason: str) -> None:
        if len(relative) > 1024:
            _fail("coverage exclusion path exceeds limit", relative)
        self.discovered.append({"root": "checkout", "path": relative, "reason": reason})


def _finish_dir(parent_fd: int, name: str, relative: str, first: os.stat_result) -> None:
    try:
        if stamp(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) != stamp(first):
            _fail("coverage directory changed", relative)
    except OSError:
        _fail("coverage directory changed", relative)


def _scan_single_file_dir(scan: _Scan, parent_fd: int, relative: str, filename: str, *, required: bool) -> None:
    fd = scan.open_dir(parent_fd, relative.rsplit("/", 1)[-1], relative)
    try:
        first = os.fstat(fd)
        names = scan.list_names(fd, relative, count_candidates=False)
        if required and filename not in names:
            _fail("coverage layout is not allowed", relative)
        for name in names:
            child = relative + "/" + name
            if name != filename or scan.child_kind(fd, name, child) != "file":
                _fail("coverage layout is not allowed", child)
            scan.read_file(fd, name, child)
        _finish_dir(parent_fd, relative.rsplit("/", 1)[-1], relative, first)
    finally:
        close_fd(fd)


def _scan_id_tree(scan: _Scan, parent_fd: int, relative: str, dir_re: re.Pattern[str], file_re: re.Pattern[str], suffix: str) -> None:
    fd = scan.open_dir(parent_fd, relative.rsplit("/", 1)[-1], relative)
    try:
        first = os.fstat(fd)
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            if dir_re.fullmatch(name) is None or scan.child_kind(fd, name, child) != "dir":
                _fail("coverage layout is not allowed", child)
            nested = scan.open_dir(fd, name, child)
            try:
                nested_first = os.fstat(nested)
                leaves = scan.list_names(nested, child, count_candidates=False)
                if not leaves:
                    _fail("coverage layout is not allowed", child)
                for leaf in leaves:
                    leaf_rel = child + "/" + leaf
                    stem = leaf[: -len(suffix)] if leaf.endswith(suffix) else leaf
                    if not leaf.endswith(suffix) or file_re.fullmatch(stem) is None or scan.child_kind(nested, leaf, leaf_rel) != "file":
                        _fail("coverage layout is not allowed", leaf_rel)
                    scan.read_file(nested, leaf, leaf_rel)
                _finish_dir(fd, name, child, nested_first)
            finally:
                close_fd(nested)
        _finish_dir(parent_fd, relative.rsplit("/", 1)[-1], relative, first)
    finally:
        close_fd(fd)


def _scan_code(scan: _Scan, parent_fd: int, relative: str) -> None:
    nameset = scan.names
    fd = scan.open_dir(parent_fd, "code-evidence-v1", relative)
    try:
        first = os.fstat(fd)
        allowed = set(nameset["slots"]) | set(nameset["families"])
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            if name not in allowed:
                _fail("coverage layout is not allowed", child)
            kind = scan.child_kind(fd, name, child)
            if name in nameset["slots"]:
                if kind != "file":
                    _fail("coverage entry is unsafe", child)
                scan.read_file(fd, name, child)
                continue
            if kind != "dir":
                _fail("coverage entry is unsafe", child)
            family = scan.open_dir(fd, name, child)
            try:
                family_first = os.fstat(family)
                pattern = nameset["object_re"] if name == "objects" else nameset["hex_json_re"]
                for leaf in scan.list_names(family, child, count_candidates=False):
                    leaf_rel = child + "/" + leaf
                    if pattern.fullmatch(leaf) is None or scan.child_kind(family, leaf, leaf_rel) != "file":
                        _fail("coverage layout is not allowed", leaf_rel)
                    scan.read_file(family, leaf, leaf_rel)
                _finish_dir(fd, name, child, family_first)
            finally:
                close_fd(family)
        _finish_dir(parent_fd, "code-evidence-v1", relative, first)
    finally:
        close_fd(fd)


def _scan_flow(scan: _Scan, parent_fd: int, relative: str) -> None:
    fd = scan.open_dir(parent_fd, "flow", relative)
    try:
        first = os.fstat(fd)
        allowed = {"selection.json", "experiments", "articles"}
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            if name not in allowed:
                _fail("coverage layout is not allowed", child)
            kind = scan.child_kind(fd, name, child)
            if name == "selection.json":
                if kind != "file":
                    _fail("coverage entry is unsafe", child)
                scan.read_file(fd, name, child)
                continue
            if kind != "dir":
                _fail("coverage entry is unsafe", child)
            group = scan.open_dir(fd, name, child)
            try:
                group_first = os.fstat(group)
                for item in scan.list_names(group, child, count_candidates=False):
                    item_rel = child + "/" + item
                    if name == "experiments":
                        if _SETTING_KEY_RE.fullmatch(item) is None or len(item) > 128 or scan.child_kind(group, item, item_rel) != "dir":
                            _fail("coverage layout is not allowed", item_rel)
                        _scan_single_file_dir(scan, group, item_rel, "input.json", required=True)
                    else:
                        if scan.names["article_re"].fullmatch(item) is None or scan.child_kind(group, item, item_rel) != "dir":
                            _fail("coverage layout is not allowed", item_rel)
                        article = scan.open_dir(group, item, item_rel)
                        try:
                            article_first = os.fstat(article)
                            leaves = scan.list_names(article, item_rel, count_candidates=False)
                            if not leaves:
                                _fail("coverage layout is not allowed", item_rel)
                            for leaf in leaves:
                                leaf_rel = item_rel + "/" + leaf
                                if leaf not in {"context.json", "document.json"} or scan.child_kind(article, leaf, leaf_rel) != "file":
                                    _fail("coverage layout is not allowed", leaf_rel)
                                scan.read_file(article, leaf, leaf_rel)
                            _finish_dir(group, item, item_rel, article_first)
                        finally:
                            close_fd(article)
                _finish_dir(fd, name, child, group_first)
            finally:
                close_fd(group)
        _finish_dir(parent_fd, "flow", relative, first)
    finally:
        close_fd(fd)


def _scan_domain(scan: _Scan, parent_fd: int, relative: str) -> None:
    fd = scan.open_dir(parent_fd, "domain", relative)
    try:
        first = os.fstat(fd)
        allowed = {"heads.json", "annotations", "reviews"}
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            if name not in allowed:
                _fail("coverage layout is not allowed", child)
            kind = scan.child_kind(fd, name, child)
            if name == "heads.json":
                if kind != "file":
                    _fail("coverage entry is unsafe", child)
                scan.read_file(fd, name, child)
                continue
            if kind != "dir":
                _fail("coverage entry is unsafe", child)
            pattern = scan.names["annotation_re"] if name == "annotations" else scan.names["review_re"]
            _scan_id_tree(scan, fd, child, scan.names["lineage_re"], pattern, ".json")
        _finish_dir(parent_fd, "domain", relative, first)
    finally:
        close_fd(fd)


def _scan_experiments(scan: _Scan, parent_fd: int, relative: str) -> None:
    fd = scan.open_dir(parent_fd, "experiments", relative)
    try:
        first = os.fstat(fd)
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            kind = scan.child_kind(fd, name, child)
            if name == "heads.json" and kind == "file":
                scan.read_file(fd, name, child)
                continue
            if name == "records" and kind == "dir":
                _scan_id_tree(scan, fd, child, scan.names["condition_re"], scan.names["record_re"], ".json")
                continue
            _fail("coverage layout is not allowed", child)
        _finish_dir(parent_fd, "experiments", relative, first)
    finally:
        close_fd(fd)


def _scan_articles(scan: _Scan, parent_fd: int, relative: str) -> None:
    fd = scan.open_dir(parent_fd, "articles", relative)
    try:
        first = os.fstat(fd)
        allowed = {"records", "render"}
        for name in scan.list_names(fd, relative, count_candidates=False):
            child = relative + "/" + name
            if name not in allowed or scan.child_kind(fd, name, child) != "dir":
                _fail("coverage layout is not allowed", child)
            suffix = ".json" if name == "records" else ".md"
            _scan_id_tree(scan, fd, child, scan.names["article_re"], scan.names["revision_re"], suffix)
        _finish_dir(parent_fd, "articles", relative, first)
    finally:
        close_fd(fd)


_RULE_SCANNERS = {
    "code-evidence": _scan_code,
    "flow": _scan_flow,
    "domain": _scan_domain,
    "experiments": _scan_experiments,
    "articles": _scan_articles,
}


def _rule_counts(scan: _Scan, prefix: str) -> tuple[int, int]:
    rows = [row for row in scan.files if row["path"] == prefix or row["path"].startswith(prefix + "/")]
    return len(rows), sum(row["size_bytes"] for row in rows)


def _scan_batch(scan: _Scan, work_fd: int, batch: str) -> None:
    from video_paper_wiki.staging import StagingError, validate_batch_id
    try:
        validate_batch_id(batch)
    except StagingError:
        _fail("coverage batch id is invalid", ".work/" + batch)
    relative = ".work/" + batch
    fd = scan.open_dir(work_fd, batch, relative)
    try:
        first = os.fstat(fd)
        present: dict[str, str] = {}
        for name in scan.list_names(fd, relative, count_candidates=True):
            child = relative + "/" + name
            rule = next((rule_id for rule_id, dirname in RULE_DIR.items() if dirname == name), None)
            if rule is not None:
                if scan.child_kind(fd, name, child) != "dir":
                    _fail("coverage entry is unsafe", child)
                present[rule] = name
                continue
            if name in REBUILDABLE_BATCH_DIRS:
                scan.child_kind(fd, name, child)
                scan.note_excluded(child, "rebuildable")
                continue
            scan.child_kind(fd, name, child)
            scan.note_excluded(child, "out_of_scope")
        for rule in RULES:
            prefix = relative + "/" + RULE_DIR[rule]
            if rule not in present:
                scan.mark_absent(prefix)
                scan.coverage.append({"batch_id": batch, "rule_id": rule, "state": "absent", "file_count": 0, "total_bytes": 0})
                continue
            before = len(scan.files)
            if rule in {"draft", "review", "plan"}:
                filename = {"draft": scan.names["draft"], "review": scan.names["review"], "plan": scan.names["plan"]}[rule]
                _scan_single_file_dir(scan, fd, prefix, filename, required=False)
            else:
                _RULE_SCANNERS[rule](scan, fd, prefix)
            count, size = _rule_counts(scan, prefix)
            if count != len(scan.files) - before:
                _fail("coverage accounting differs", prefix)
            scan.coverage.append({"batch_id": batch, "rule_id": rule, "state": "included", "file_count": count, "total_bytes": size})
        _finish_dir(work_fd, batch, relative, first)
    finally:
        close_fd(fd)


def scan_research_coverage(
    root: Path | str,
    *,
    snapshot: CoverageSnapshot | None = None,
    entry_base: int = 0,
    byte_base: int = 0,
) -> CoverageSnapshot:
    """Enumerate compliant batches and the eight whitelist rules under ``checkout/.work``.

    ``entry_base`` and ``byte_base`` are bytes and manifest entries already consumed by the
    paired Vault root. Both roots share one remaining budget.
    """
    owns = snapshot is None
    snap = snapshot or CoverageSnapshot(root)
    if snap.root_fd is None:
        _fail("checkout root is unavailable")
    compare = snap.sealed
    if compare:
        entry_base = int(getattr(snap, "entry_base", 0))
        byte_base = int(getattr(snap, "byte_base", 0))
    else:
        snap.entry_base = entry_base
        snap.byte_base = byte_base
    scan = _Scan(snap, compare)
    scan.entry_base = entry_base
    scan.byte_base = byte_base
    try:
        if stamp(os.fstat(snap.root_fd)) != stamp(snap.root_stat) or stamp(snap.root.lstat()) != stamp(snap.root_stat):
            _fail("checkout root changed")
        try:
            found = os.stat(".work", dir_fd=snap.root_fd, follow_symlinks=False)
        except FileNotFoundError:
            scan.mark_absent(".work")
            report = _report(scan, [])
            _seal(snap, report, compare)
            return snap
        if stat.S_ISLNK(found.st_mode) or not stat.S_ISDIR(found.st_mode):
            _fail("coverage entry is unsafe", ".work")
        work_fd = scan.open_dir(snap.root_fd, ".work", ".work")
        try:
            first = os.fstat(work_fd)
            batches: list[str] = []
            from video_paper_wiki.staging import StagingError, validate_batch_id
            for name in scan.list_names(work_fd, ".work", count_candidates=True):
                child = ".work/" + name
                kind = scan.child_kind(work_fd, name, child)
                if name in RESERVED_WORK_DIRS:
                    scan.note_excluded(child, "out_of_scope")
                    continue
                try:
                    validate_batch_id(name)
                    is_batch = True
                except StagingError:
                    is_batch = False
                if is_batch:
                    if kind != "dir":
                        _fail("coverage entry is unsafe", child)
                    batches.append(name)
                    continue
                scan.note_excluded(child, "out_of_scope")
            if len(batches) > MAX_BATCHES:
                _fail("coverage batch limit exceeded")
            batches = sorted(batches, key=lambda item: item.encode())
            for batch in batches:
                _scan_batch(scan, work_fd, batch)
            _finish_dir(snap.root_fd, ".work", ".work", first)
        finally:
            close_fd(work_fd)
        report = _report(scan, batches)
        _seal(snap, report, compare)
        return snap
    except BaseException:
        if owns:
            snap.close()
        raise


def _report(scan: _Scan, batches: list[str]) -> dict[str, Any]:
    return {
        "batches": list(batches),
        "coverage": list(scan.coverage),
        "directories": sorted(scan.directories, key=lambda row: row["path"].encode()),
        "files": sorted(scan.files, key=lambda row: row["path"].encode()),
        "excluded": _sort_excluded(fixed_excluded() + scan.discovered),
    }


def _seal(snap: CoverageSnapshot, report: dict[str, Any], compare: bool) -> None:
    if compare:
        if snap.report != report:
            _fail("coverage tree changed")
        return
    snap.report = report
    snap.sealed = True


def rule_prefix(batch_id: str, rule_id: str) -> str:
    return ".work/" + batch_id + "/" + RULE_DIR[rule_id]


def check_research_manifest_document(document: dict[str, Any]) -> None:
    """Cross-field checks for one closed research manifest. Self-hash stays outside schema validation."""
    scope = document["scope"]
    batches = list(scope["batch_ids"])
    if batches != sorted(set(batches), key=lambda item: item.encode()):
        _schema_fail("research batch ids are not ordered", "/scope/batch_ids")
    expected = [
        {"batch_id": batch, "rule_id": rule}
        for batch in batches
        for rule in RULES
    ]
    coverage = document["coverage"]
    if len(coverage) != len(expected):
        _schema_fail("research coverage does not cover every batch rule", "/coverage")
    for index, (row, want) in enumerate(zip(coverage, expected)):
        pointer = "/coverage/" + str(index)
        if row["batch_id"] != want["batch_id"] or row["rule_id"] != want["rule_id"]:
            _schema_fail("research coverage order differs", pointer)
        prefix = rule_prefix(row["batch_id"], row["rule_id"])
        matched = [item for item in document["files"] if item["path"] == prefix or item["path"].startswith(prefix + "/")]
        dirs = [item["path"] for item in document["directories"]]
        if row["state"] == "absent":
            if row["file_count"] != 0 or row["total_bytes"] != 0 or matched or any(path == prefix or path.startswith(prefix + "/") for path in dirs):
                _schema_fail("absent research coverage still records bytes", pointer)
        else:
            if row["file_count"] != len(matched) or row["total_bytes"] != sum(item["size_bytes"] for item in matched):
                _schema_fail("included research coverage does not match file rows", pointer)
            if prefix not in dirs:
                _schema_fail("included research rule directory is missing", pointer)
    directory_paths = [item["path"] for item in document["directories"]]
    file_paths = [item["path"] for item in document["files"]]
    if directory_paths != sorted(directory_paths, key=lambda item: item.encode()) or file_paths != sorted(file_paths, key=lambda item: item.encode()):
        _schema_fail("research manifest paths are not ordered", "/files")
    if len(directory_paths) + len(file_paths) > _limits()[0]:
        _schema_fail("research manifest entry limit exceeded", "/files")
    keys: dict[str, str] = {}
    for path in directory_paths + file_paths:
        if not path or path.startswith("/") or "\\" in path or "\x00" in path or unicodedata.normalize("NFC", path) != path or any(part in {"", ".", ".."} for part in path.split("/")):
            _schema_fail("research manifest path is not portable", "/files")
        folded = unicodedata.normalize("NFC", path).casefold()
        if folded in keys and keys[folded] != path:
            _schema_fail("research manifest path collision", "/files")
        keys[folded] = path
        if path == ".work":
            if path in file_paths:
                _schema_fail("research work root cannot be a file", "/files")
        elif path.startswith(".work/"):
            parts = path.split("/")
            if len(parts) < 2 or parts[1] not in set(batches):
                _schema_fail("research work path is outside the enumerated batches", "/files")
            if len(parts) == 2:
                if path in file_paths:
                    _schema_fail("research batch path cannot be a file", "/files")
            else:
                rule = next((rule_id for rule_id, dirname in RULE_DIR.items() if dirname == parts[2]), None)
                included = rule is not None and any(
                    row["batch_id"] == parts[1] and row["rule_id"] == rule and row["state"] == "included" for row in coverage
                )
                if not included:
                    _schema_fail("research work path is outside an included rule", "/files")
        elif not (path == ".raw" or path.startswith(".raw/") or path == "wiki" or path.startswith("wiki/")):
            _schema_fail("research manifest path is outside the profile roots", "/files")
    for path in file_paths:
        parent = path.rsplit("/", 1)[0]
        needed = []
        parts = parent.split("/")
        for index in range(1, len(parts) + 1):
            needed.append("/".join(parts[:index]))
        if any(item not in directory_paths for item in needed):
            _schema_fail("research file is missing a parent directory", "/files")
    excluded = document["excluded"]
    identity = [(row["root"], row["path"], row["reason"]) for row in excluded]
    if identity != sorted(identity, key=lambda item: (item[0].encode(), item[1].encode(), item[2].encode())) or len(identity) != len(set(identity)):
        _schema_fail("research exclusions are not a stable set", "/excluded")
    have = set(identity)
    for row in fixed_excluded():
        if (row["root"], row["path"], row["reason"]) not in have:
            _schema_fail("research manifest is missing a fixed exclusion", "/excluded")
    for label in ("vault", "checkout"):
        root = document["source_roots"][label]
        if type(root) is not str or not root.startswith("/") or root != os.path.abspath(root):
            _schema_fail("research source root is not absolute", "/source_roots/" + label)


__all__ = [
    "COVERAGE_VERSION",
    "CoverageSnapshot",
    "MAX_BATCHES",
    "MAX_CANDIDATES",
    "POLICY_V2",
    "PROFILE_SCHEMA",
    "PROFILE_V1",
    "PROFILE_V2",
    "RESEARCH_ROOTS",
    "RULES",
    "SCHEMA_V1",
    "SCHEMA_V2",
    "absolute_directory",
    "assert_distinct_or_same",
    "check_research_manifest_document",
    "fixed_excluded",
    "scan_research_coverage",
]
