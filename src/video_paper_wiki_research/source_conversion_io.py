"""Bounded retained lightweight inputs and private, verified validator mirrors."""
from __future__ import annotations

import os
import secrets
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.markdown_source_io import RetainedDirectory, RetainedFile, checked_path
from video_paper_wiki.secure_io import dir_open_flags, file_open_flags, stamp
from video_paper_wiki.source_semantics_contracts import fail
from video_paper_wiki.staging import StagingError, _atomic_install, _ensure_dir_at, _open_batch_session

MAX_ENTRIES = 8192
MAX_DEPTH = 16
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def safe_path(value):
    try:
        raw = os.fspath(value)
    except TypeError:
        fail("WORK_PATH_UNSAFE", "input path must be filesystem text")
    if (type(raw) is not str or any(p in {".", ".."} for p in raw.split("/"))
            or "//" in raw or any(ord(c) == 127 for c in raw)
            or unicodedata.normalize("NFC", raw) != raw):
        fail("WORK_PATH_UNSAFE", "input path spelling is not canonical")
    return checked_path(raw)


def _identity(value):
    return value.st_dev, value.st_ino, value.st_mode


def _name(name):
    if (not name or name in {".", ".."} or "/" in name or "\\" in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or unicodedata.normalize("NFC", name) != name):
        fail("WORK_PATH_UNSAFE", "managed input contains an unsafe path spelling")
    try:
        name.encode("utf-8")
    except UnicodeError:
        fail("WORK_PATH_UNSAFE", "managed input path is not UTF-8")


def _read(fd, maximum):
    os.lseek(fd, 0, os.SEEK_SET)
    parts, size = [], 0
    while True:
        part = os.read(fd, min(65536, maximum + 1 - size))
        if not part:
            return b"".join(parts)
        parts.append(part)
        size += len(part)
        if size > maximum:
            fail("WORK_PATH_UNSAFE", "retained input grew beyond its bound")


class RetainedTree:
    """One ancestor chain plus descendant stamps, complete sets and exact bytes.

    Acquisition is separate so partial acquisition is verified by the caller's
    finally block. Generated mirrors record each owned install, never adopt an
    arbitrary tree after writing it.
    """

    def __init__(self, path, *, empty=False, expected_identity=None):
        self.path = safe_path(path)
        self.held = RetainedDirectory(self.path)
        self.fd = self.held.fds[-1]
        self.directories, self.names, self.files = {}, {}, {}
        self.count = self.total = 0
        try:
            first = os.fstat(self.fd)
            self.directories[""] = first
            if expected_identity is not None and _identity(first) != _identity(expected_identity):
                fail("WORK_PATH_UNSAFE", "created mirror directory identity changed")
            if empty:
                self.names[""] = set()
                self.verify()
        except BaseException:
            try:
                self.held.verify()
            finally:
                self.close()
            raise

    def _directory(self, relative):
        fd = os.dup(self.fd)
        try:
            prefix = ""
            for name in relative.split("/") if relative else ():
                prefix = name if not prefix else prefix + "/" + name
                child = os.open(name, dir_open_flags(), dir_fd=fd)
                os.close(fd)
                fd = child
                if stamp(os.fstat(fd)) != stamp(self.directories[prefix]):
                    raise OSError("retained directory changed")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def capture(self):
        def walk(fd, relative, depth):
            entries = set(os.listdir(fd))
            self.names[relative] = entries
            if self.count + len(entries) > MAX_ENTRIES or (entries and depth + 1 > MAX_DEPTH):
                fail("SOURCE_CONVERSION_INVALID", "lightweight tree exceeds entry/depth limits", "/workspace_root")
            portable = set()
            for name in sorted(entries):
                _name(name)
                key = name.casefold()
                if key in portable:
                    fail("WORK_PATH_UNSAFE", "managed input names collide portably")
                portable.add(key)
            siblings = {}
            for name in sorted(entries):
                path = name if not relative else relative + "/" + name
                first = os.stat(name, dir_fd=fd, follow_symlinks=False)
                siblings[name] = first
                self.count += 1
                if stat.S_ISDIR(first.st_mode):
                    self.directories[path] = first
                elif stat.S_ISREG(first.st_mode) and first.st_nlink == 1:
                    self.files[path] = (first, None)
                else:
                    fail("WORK_PATH_UNSAFE", "managed input contains a link or special file")
            # Record sibling identities before reading any payload. Early exits
            # retain all reached names/stamps, without claiming unread bytes.
            for name, first in siblings.items():
                path = name if not relative else relative + "/" + name
                if stat.S_ISDIR(first.st_mode):
                    child = os.open(name, dir_open_flags(), dir_fd=fd)
                    try:
                        if stamp(os.fstat(child)) != stamp(first):
                            raise OSError("input directory changed")
                        walk(child, path, depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(first.st_mode) and first.st_nlink == 1:
                    self.total += first.st_size
                    if first.st_size > MAX_FILE or self.total > MAX_TOTAL:
                        fail("SOURCE_CONVERSION_INVALID", "lightweight input exceeds byte limits", "/workspace_root")
                    child = os.open(name, file_open_flags(), dir_fd=fd)
                    try:
                        if stamp(os.fstat(child)) != stamp(first):
                            raise OSError("input file changed")
                        raw = _read(child, MAX_FILE)
                        if stamp(os.fstat(child)) != stamp(first):
                            raise OSError("input file changed")
                        self.files[path] = (first, raw)
                    finally:
                        os.close(child)
        try:
            walk(self.fd, "", 0)
            self.verify()
        except OSError:
            fail("WORK_PATH_UNSAFE", "managed input changed during acquisition")

    def verify(self):
        self.held.verify()
        try:
            if stamp(os.fstat(self.fd)) != stamp(self.directories[""]):
                raise OSError("input root changed")
            for relative in self.directories:
                fd = self._directory(relative)
                try:
                    if relative in self.names and set(os.listdir(fd)) != self.names[relative]:
                        raise OSError("input complete set changed")
                finally:
                    os.close(fd)
            for relative, (first, data) in self.files.items():
                parent, _, name = relative.rpartition("/")
                fd = self._directory(parent)
                child = None
                try:
                    named = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stamp(named) != stamp(first) or named.st_nlink != 1 or not stat.S_ISREG(named.st_mode):
                        raise OSError("input identity changed")
                    child = os.open(name, file_open_flags(), dir_fd=fd)
                    if stamp(os.fstat(child)) != stamp(first):
                        raise OSError("input file changed")
                    if data is not None and _read(child, MAX_FILE) != data:
                        raise OSError("input bytes changed")
                    if stamp(os.fstat(child)) != stamp(first):
                        raise OSError("input changed during reread")
                finally:
                    if child is not None:
                        os.close(child)
                    os.close(fd)
        except OSError:
            fail("WORK_PATH_UNSAFE", "retained tree bytes, identity or complete set changed")
        finally:
            self.held.verify()

    def mkdir(self, relative):
        self.held.verify()
        parent, _, name = relative.rpartition("/")
        fd = self._directory(parent)
        try:
            if set(os.listdir(fd)) != self.names[parent]:
                raise OSError("mirror parent complete set changed")
            os.mkdir(name, mode=0o700, dir_fd=fd)
            self.names[parent].add(name)
            self.directories[parent] = os.fstat(fd)
            self.directories[relative] = os.stat(name, dir_fd=fd, follow_symlinks=False)
            self.names[relative] = set()
            if not stat.S_ISDIR(self.directories[relative].st_mode):
                raise OSError("created directory changed")
        except OSError:
            fail("WORK_PATH_UNSAFE", "private mirror directory creation conflicted or changed")
        finally:
            os.close(fd)

    def install(self, relative, raw, session):
        self.held.verify()
        parent, _, name = relative.rpartition("/")
        fd = self._directory(parent)
        try:
            if set(os.listdir(fd)) != self.names[parent]:
                raise OSError("mirror parent complete set changed")
            reused, first = _atomic_install(session.work_fd, fd, name, raw,
                target=self.path / relative, checkout_fd=session.checkout_fd, return_identity=True)
            if reused:
                fail("WORK_PATH_UNSAFE", "private mirror slot was occupied by another writer")
            self.names[parent].add(name)
            self.directories[parent] = os.fstat(fd)
            named = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if _identity(named) != _identity(first) or named.st_nlink != 1:
                fail("WORK_PATH_UNSAFE", "installed mirror file identity changed")
            self.files[relative] = (named, raw)
        except (OSError, StagingError):
            fail("WORK_PATH_UNSAFE", "private mirror install conflicted or changed")
        finally:
            os.close(fd)

    def close(self):
        self.held.close()


def _verify_all(held):
    error = None
    for item in held:
        try:
            item.verify()
        except (ContractError, OSError, StagingError) as exc:
            if error is None:
                error = exc
    if error is not None:
        if isinstance(error, ContractError):
            raise error
        if isinstance(error, StagingError):
            raise ContractError(error.code, error.message, {"instance_pointer": "", **error.details},
                                exit_code=getattr(error, "exit_code", 2)) from error
        fail("WORK_PATH_UNSAFE", "retained input verification failed")


@contextmanager
def retained_inputs(*, workspace, markdown_path, source_path, authority_path, metadata_path):
    held = []
    try:
        specs = [(markdown_path, 8388608), (source_path, 1048576), (authority_path, 8388608)]
        if metadata_path is not None:
            specs.append((metadata_path, 1048576))
        for path, maximum in specs:
            held.append(RetainedFile(safe_path(path), maximum=maximum))
        tree = RetainedTree(workspace / ".light-knowledge")
        held.append(tree)
        tree.capture()
        if tree.total + sum(len(item.data) for item in held[:-1]) > MAX_TOTAL:
            fail("SOURCE_CONVERSION_INVALID", "complete conversion inputs exceed byte limit", "/workspace_root")
        yield held[:-1], tree
    finally:
        try:
            _verify_all(held)
        finally:
            for item in reversed(held):
                item.close()


@contextmanager
def validator_mirror(*, batch, light_paper_id, tree, markdown, metadata):
    with _open_batch_session(batch, create=True) as session:
        parent_path = session.batch_path / "source-conversion"
        parent_fd = _ensure_dir_at(session.batch_fd, "source-conversion", parent_path,
                                   work_fd=session.work_fd)
        parent = None
        mirror = None
        try:
            first = os.fstat(parent_fd)
            parent = RetainedDirectory(parent_path)
            if _identity(os.fstat(parent.fds[-1])) != _identity(first):
                fail("WORK_PATH_UNSAFE", "mirror parent identity changed")
            name = "inputs-" + secrets.token_hex(16)
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            mirror = RetainedTree(parent_path / name, empty=True, expected_identity=created)
            digest = light_paper_id.split(":", 1)[1]
            directories = {".light-knowledge", "papers", "papers/" + digest}
            directories.update(".light-knowledge/" + p for p in tree.directories if p)
            for relative in sorted(directories, key=lambda p: (p.count("/"), p)):
                mirror.mkdir(relative)
            files = {".light-knowledge/" + p: raw for p, (_, raw) in tree.files.items()}
            files.update({"papers/" + digest + "/source.md": markdown,
                          "papers/" + digest + "/source.json": metadata})
            for relative, raw in sorted(files.items()):
                mirror.install(relative, raw, session)
            mirror.verify()
            tree.verify()
            yield mirror.path
        except OSError:
            fail("WORK_PATH_UNSAFE", "private validator mirror creation or lineage changed")
        finally:
            try:
                _verify_all([x for x in (mirror, parent, session) if x is not None])
            finally:
                if mirror is not None:
                    mirror.close()
                if parent is not None:
                    parent.close()
                os.close(parent_fd)
