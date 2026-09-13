"""Retained fixed publication trees for external input and generated staging."""
from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path

from video_paper_wiki.markdown_source_io import RetainedDirectory, RetainedFile, _identity
from video_paper_wiki.secure_io import stamp
from video_paper_wiki.source_publication_contracts import HEX, MAX_FILE, MAX_JSON, MAX_PAYLOADS, MAX_TOTAL, invalid
from video_paper_wiki.source_semantics_contracts import fail, sha
from video_paper_wiki.staging import _atomic_install, _ensure_dir_at, _open_batch_session, resolve_checkout_root, validate_batch_id


def checked_path(value):
    try:
        spelling = os.fspath(value)
        if (type(spelling) is not str or not spelling or "\\" in spelling
                or any(ord(c) < 32 or ord(c) == 127 for c in spelling)
                or any(part in {".", ".."} for part in spelling.split("/"))
                or "//" in spelling):
            raise ValueError
        return Path(os.path.abspath(spelling))
    except (TypeError, ValueError, OSError):
        fail("WORK_PATH_UNSAFE", "caller path spelling is unsafe")


def prepared_path(value):
    path = checked_path(value)
    try:
        parts = path.relative_to(resolve_checkout_root() / ".work").parts
        batch = validate_batch_id(parts[0])
        if parts != (batch, "source-publication", "request.json"):
            raise ValueError
        return path, batch
    except (ValueError, IndexError):
        fail("WORK_PATH_UNSAFE", "prepared input must use the fixed source publication slot")


class PublicationTree:
    """One named input tree; every fixed slot is held before request parsing."""

    def __init__(self, path, *, filename="request.json", session=None, create=False):
        self.path = checked_path(path)
        self.filename, self.session = filename, session
        self.directory = self.content_directory = self.request = None
        self.root_fd = self.root_first = None
        self.request_observed = self.content_observed = False
        self.request_first = self.content_first = None
        self.files, self.initial_stats = {}, {}
        self.names = self.content_names = None
        self.private = session is not None
        try:
            if create:
                self.root_fd = _ensure_dir_at(session.batch_fd, "source-publication", self.path, work_fd=session.work_fd)
                self.root_first = os.fstat(self.root_fd)
            self.directory = RetainedDirectory(self.path)
            self.fd = self.directory.fds[-1]
            self.names = set(os.listdir(self.fd))
            if not self.names <= {filename, "content"}:
                fail("WORK_PATH_UNSAFE", "publication directory has unknown entries")
            # Record both fixed slots before reading the request or creating a
            # sibling. Retain content before the request constructor reads bytes.
            try:
                self.request_first = os.stat(filename, dir_fd=self.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            self.request_observed = True
            try:
                self.content_first = os.stat("content", dir_fd=self.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            self.content_observed = True
            self.verify_directories()
            if "content" not in self.names:
                if not create:
                    fail("WORK_PATH_UNSAFE", "publication content directory is missing")
                self.verify_directories()
                try:
                    os.mkdir("content", mode=0o700, dir_fd=self.fd)
                except FileExistsError:
                    fail("WORK_PATH_UNSAFE", "absent content slot was filled by another writer")
                self.names.add("content")
                self.content_first = os.stat("content", dir_fd=self.fd, follow_symlinks=False)
            self.content_directory = RetainedDirectory(self.path / "content")
            self.content_fd = self.content_directory.fds[-1]
            self.verify_directories()
            self.request = RetainedFile(self.path / filename, maximum=MAX_JSON, required=False)
            self.verify_directories()
            self.content_names = set(os.listdir(self.content_fd))
            if len(self.content_names) > MAX_PAYLOADS:
                fail("TRANSACTION_LIMIT_EXCEEDED", "publication content count exceeds its bound")
            total = 0
            for name in sorted(self.content_names):
                if HEX.fullmatch(name) is None:
                    fail("WORK_PATH_UNSAFE", "publication content filename is not a digest")
                first = os.stat(name, dir_fd=self.content_fd, follow_symlinks=False)
                self.initial_stats[name] = first
                if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1
                        or (self.private and stat.S_IMODE(first.st_mode) & 0o077)):
                    fail("WORK_PATH_UNSAFE", "publication content entry is unsafe")
                total += first.st_size
                if first.st_size > MAX_FILE or total > MAX_TOTAL:
                    fail("TRANSACTION_LIMIT_EXCEEDED", "publication content bytes exceed the input bound")
            if self.private and self.request.first is not None and stat.S_IMODE(self.request.first.st_mode) & 0o077:
                fail("WORK_PATH_UNSAFE", "publication request permissions are not private")
            self.verify()
        except BaseException as exc:
            try:
                self.verify()
            finally:
                self.close()
            if isinstance(exc, OSError):
                fail("WORK_PATH_UNSAFE", "publication tree could not be retained")
            raise

    def verify_directories(self):
        if self.session is not None:
            self.session.verify()
        if self.directory is not None:
            self.directory.verify()
            if self.root_fd is not None and (_identity(os.fstat(self.root_fd)) != _identity(self.root_first)
                    or _identity(os.fstat(self.fd)) != _identity(self.root_first)):
                fail("WORK_PATH_UNSAFE", "publication root changed during initial retention")
            if self.names is not None and set(os.listdir(self.fd)) != self.names:
                fail("WORK_PATH_UNSAFE", "publication directory set changed")
            for observed, first, name, is_directory in (
                    (self.request_observed, self.request_first, self.filename, False),
                    (self.content_observed, self.content_first, "content", True)):
                if not observed:
                    continue
                try:
                    current = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
                except FileNotFoundError:
                    current = None
                identity = _identity if is_directory else stamp
                if (current is None) != (first is None) or first is not None and identity(current) != identity(first):
                    fail("WORK_PATH_UNSAFE", "publication fixed slot changed before retention")
        if self.content_directory is not None:
            self.content_directory.verify()
            if self.content_names is not None and set(os.listdir(self.content_fd)) != self.content_names:
                fail("WORK_PATH_UNSAFE", "publication content set changed")

    def verify(self):
        try:
            self.verify_directories()
            if self.request is not None:
                self.request.verify()
            for name, first in self.initial_stats.items():
                current = os.stat(name, dir_fd=self.content_fd, follow_symlinks=False)
                if stamp(current) != stamp(first):
                    fail("WORK_PATH_UNSAFE", "publication content identity changed")
            for held in self.files.values():
                held.verify()
        except OSError:
            fail("WORK_PATH_UNSAFE", "publication retained entry is unavailable")
        finally:
            # Named lineage is checked even when scanning or checking a child failed.
            if self.directory is not None:
                self.directory.verify()
            if self.content_directory is not None:
                self.content_directory.verify()
            if self.session is not None:
                self.session.verify()

    def request_bytes(self):
        self.verify()
        if self.request.data is None:
            invalid("publication request is missing")
        return self.request.data

    def bind(self, expected, *, allow_missing=False):
        self.verify()
        wanted = set(expected)
        if not self.content_names <= wanted or (not allow_missing and self.content_names != wanted):
            fail("WORK_PATH_UNSAFE", "publication content set differs from its request")
        for digest in sorted(wanted):
            if digest not in self.files:
                held = RetainedFile(self.path / "content" / digest, maximum=MAX_FILE, required=not allow_missing)
                self.files[digest] = held
                initial = self.initial_stats.get(digest)
                if (initial is None) != (held.first is None) or (initial is not None and stamp(initial) != stamp(held.first)):
                    fail("WORK_PATH_UNSAFE", "publication content changed before retention")
            held = self.files[digest]
            if held.data is not None:
                if sha(held.data) != digest or (expected[digest] is not None and len(held.data) != expected[digest]):
                    invalid("publication content bytes differ from the descriptor", "/payloads")
        self.verify()
        return {digest: self.files[digest].data for digest in sorted(wanted)}

    def _install(self, held, parent_fd, name, data, *, request=False):
        self.verify_directories()
        held.verify()
        if held.data is not None:
            if held.data != data:
                fail("SOURCE_HISTORY_CONFLICT", "staged publication slot contains different bytes", exit_code=75)
            return
        reused, identity = _atomic_install(self.session.work_fd, parent_fd, name, data,
            target=held.path, checkout_fd=self.session.checkout_fd, return_identity=True)
        if reused:
            fail("WORK_PATH_UNSAFE", "retained missing slot was filled by another writer")
        held.adopt(identity, data)
        if request:
            self.names.add(name)
            self.request_first = held.first
        else:
            self.content_names.add(name)
            self.initial_stats[name] = held.first
        self.verify_directories()

    def install(self, raw_request, contents):
        if self.session is None:
            invalid("external publication input cannot be written")
        if type(raw_request) is not bytes or len(raw_request) > MAX_JSON:
            invalid("staged request must be bounded exact bytes")
        if (type(contents) is not dict or len(contents) > MAX_PAYLOADS
                or any(type(k) is not str or HEX.fullmatch(k) is None or type(v) is not bytes for k, v in contents.items())):
            invalid("staged content must be a bounded digest-to-bytes map")
        if any(len(v) > MAX_FILE for v in contents.values()) or sum(map(len, contents.values())) > MAX_TOTAL:
            fail("TRANSACTION_LIMIT_EXCEEDED", "staged content exceeds byte limits")
        if any(sha(v) != k for k, v in contents.items()):
            invalid("staged content digest differs from exact bytes")
        self.verify()
        if self.request.data is not None and self.request.data != raw_request:
            fail("SOURCE_HISTORY_CONFLICT", "staged request already contains different bytes", exit_code=75)
        self.bind({digest: len(data) for digest, data in contents.items()}, allow_missing=True)
        for digest, data in sorted(contents.items()):
            self._install(self.files[digest], self.content_fd, digest, data)
        self._install(self.request, self.fd, self.filename, raw_request, request=True)
        self.verify()

    def close(self):
        for held in self.files.values():
            held.close()
        if self.request is not None:
            self.request.close()
        for directory in (self.content_directory, self.directory):
            if directory is not None:
                directory.close()
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None


@contextmanager
def staged_tree(batch, *, create):
    with _open_batch_session(validate_batch_id(batch), create=create) as session:
        tree = PublicationTree(session.batch_path / "source-publication", session=session, create=create)
        try:
            yield tree
        finally:
            try:
                tree.verify()
            finally:
                tree.close()


@contextmanager
def proposal_tree(proposal_path):
    path = checked_path(proposal_path)
    if path.name != "proposal.json" or path.parent.name != "source-publication":
        fail("WORK_PATH_UNSAFE", "proposal must use the fixed external publication layout")
    tree = PublicationTree(path.parent, filename="proposal.json")
    try:
        yield tree
    finally:
        try:
            tree.verify()
        finally:
            tree.close()
