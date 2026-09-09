"""Retained, create-only storage for the five preview artifact families."""
from __future__ import annotations

import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from video_paper_wiki import staging
from video_paper_wiki.secure_io import close_fd, file_open_flags, lexical_abs, open_dir_nofollow, stamp
from video_paper_wiki_research.preview_contracts import (
    MAX_BYTES, fail, parse_json, preflight, reference, saved_bytes, validate, validate_graph,
)

FAMILIES = {"request": "requests", "observation": "observations", "metadata": "metadata",
            "preview": "proposals", "decision": "decisions"}
LIMIT = 256


def _unsafe(path: Path, reason: str):
    staging._raise_unsafe(path, reason)


def _input_path(path):
    try:
        raw = os.fspath(path)
    except TypeError:
        fail("ARTIFACT_INVALID", "input path must be a string or path")
    if type(raw) is not str or len(raw) > 4096:
        fail("ARTIFACT_INVALID", "input path must be bounded text")
    preflight(raw)
    if ".." in Path(raw).parts:
        fail("WORK_PATH_UNSAFE", "input path cannot contain traversal")
    return lexical_abs(raw)


@contextmanager
def read_input(path: Path | str):
    """Hold the input's parent and live inode until parsing/command completion."""
    target = _input_path(path)
    root_fd = open_dir_nofollow(Path("/"), missing_code="ARTIFACT_INVALID", unsafe_code="WORK_PATH_UNSAFE")
    parent_fd = root_fd
    edges = []
    fd = None
    original = None
    raw = None

    def verify():
        try:
            for parent, name, child, identity, directory in edges:
                staging._require_same_directory(child, identity, directory)
                check = staging._open_dir_at(parent, name, directory)
                try:
                    staging._require_same_directory(check, identity, directory)
                finally:
                    close_fd(check)
            if original is not None:
                named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                if stamp(named) != stamp(original) or named.st_nlink != 1:
                    _unsafe(target, "preview input's named identity changed")
                if raw is not None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    chunks, total = [], 0
                    while total <= MAX_BYTES:
                        chunk = os.read(fd, min(65536, MAX_BYTES + 1 - total))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    if b"".join(chunks) != raw or stamp(os.fstat(fd)) != stamp(original):
                        _unsafe(target, "preview input bytes changed")
        except OSError as exc:
            staging._map_oserror(target, exc)

    try:
        try:
            directory = Path("/")
            for name in target.parent.parts[1:]:
                directory = directory / name
                child = staging._open_dir_at(parent_fd, name, directory)
                edges.append((parent_fd, name, child, os.fstat(child), directory))
                parent_fd = child
            fd = os.open(target.name, file_open_flags(), dir_fd=parent_fd)
            original = os.fstat(fd)
            if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
                _unsafe(target, "preview input must be a single-link regular file")
            if original.st_size > MAX_BYTES:
                fail("RESPONSE_TOO_LARGE", "preview input exceeds one MiB")
            chunks, total = [], 0
            while total <= MAX_BYTES:
                chunk = os.read(fd, min(65536, MAX_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
            if len(raw) > MAX_BYTES:
                fail("RESPONSE_TOO_LARGE", "preview input exceeds one MiB")
            verify()
            yield raw
        except OSError as exc:
            staging._map_oserror(target, exc)
        finally:
            verify()
    finally:
        close_fd(fd)
        for _, _, child, _, _ in reversed(edges):
            close_fd(child)
        close_fd(root_fd)


class PreviewStore:
    def __init__(self, batch, session: str):
        self.batch, self.session = batch, session
        self.root = batch.batch_path / session / "preview-v1"
        self.edges = []
        self.family_fds = {}
        self.snapshots = {}
        self.documents = {}
        self.ready = False

    def _directory(self, parent, name, path, create):
        fd = (staging._ensure_dir_at(parent, name, path, work_fd=self.batch.work_fd) if create
              else staging._open_dir_at(parent, name, path))
        self.edges.append((parent, name, fd, os.fstat(fd), path))
        return fd

    def initialize(self, create):
        session_fd = self._directory(self.batch.batch_fd, self.session, self.root.parent, create)
        root_fd = self._directory(session_fd, "preview-v1", self.root, create)
        self.root_fd = root_fd
        for kind, family in FAMILIES.items():
            fd = self._directory(root_fd, family, self.root / family, create)
            self.family_fds[kind] = fd
        self.verify_edges()
        for kind in FAMILIES:
            self.snapshots[kind] = self._scan(kind)
        self.ready = True
        self.verify()
        for kind, snapshot in self.snapshots.items():
            for name, (raw, _) in snapshot.items():
                document = validate(parse_json(raw), kind)
                if raw != saved_bytes(document) or name != self.filename(document):
                    fail("ARTIFACT_BINDING_MISMATCH", "stored artifact filename or canonical bytes differ")
                self.documents[document["id"]] = document
        self.validate_all()

    def verify_edges(self):
        self.batch.verify()
        for parent, name, fd, identity, path in self.edges:
            staging._require_same_directory(fd, identity, path)
            named_fd = staging._open_dir_at(parent, name, path)
            try:
                staging._require_same_directory(named_fd, identity, path)
            finally:
                close_fd(named_fd)

    def _scan(self, kind):
        fd, result = self.family_fds[kind], {}
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    name = entry.name
                    if len(result) >= LIMIT:
                        fail("SESSION_LIMIT_EXCEEDED", "preview family exceeds 256 files")
                    pattern = r"[0-9]{6}\.json" if kind == "decision" else r"[0-9a-f]{64}\.json"
                    target = self.root / FAMILIES[kind] / name
                    if re.fullmatch(pattern, name) is None:
                        _unsafe(target, "unexpected preview family entry")
                    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                        _unsafe(target, "preview artifact must be a single-link regular file")
                    if before.st_size > MAX_BYTES:
                        fail("RESPONSE_TOO_LARGE", "stored preview artifact exceeds one MiB")
                    raw, after = staging._read_regular_file_at_bounded_identity(fd, name, target, max_bytes=MAX_BYTES)
                    if stamp(before) != stamp(after) or after.st_nlink != 1:
                        _unsafe(target, "preview artifact changed during inventory")
                    result[name] = (raw, stamp(after))
        except OSError as exc:
            staging._map_oserror(self.root / FAMILIES[kind], exc)
        finally:
            self.verify_edges()
        return result

    def verify(self):
        self.verify_edges()
        try:
            if hasattr(self, "root_fd") and set(os.listdir(self.root_fd)) != set(FAMILIES.values()):
                # During incremental opening the expected families may not all exist yet.
                if self.ready or len(self.family_fds) == len(FAMILIES):
                    _unsafe(self.root, "unexpected preview root entries")
            for kind, original in self.snapshots.items():
                current = self._scan(kind)
                if current != original:
                    if len(current) > len(original) and all(current.get(name) == value for name, value in original.items()):
                        fail("STAGING_CONFLICT", "session has additional entries; re-read before retrying")
                    _unsafe(self.root / FAMILIES[kind], "preview artifact set or bytes changed")
        finally:
            self.verify_edges()

    @staticmethod
    def filename(document):
        return (f'{document["data"]["sequence"]:06d}.json' if document["kind"] == "decision"
                else document["content_sha256"] + ".json")

    def path(self, document):
        return self.root / FAMILIES[document["kind"]] / self.filename(document)

    def resolve(self, ref, kind):
        document = self.documents.get(ref["id"])
        if document is None or document["kind"] != kind or reference(document) != ref:
            fail("ARTIFACT_BINDING_MISMATCH", "referenced artifact is absent or has different bytes")
        return document

    def load_path(self, path, kind):
        target = _input_path(path)
        if target.parent != self.root / FAMILIES[kind]:
            fail("ARTIFACT_BINDING_MISMATCH", "generated reference belongs to another kind or session")
        snapshot = self.snapshots[kind].get(target.name)
        if snapshot is None:
            fail("ARTIFACT_BINDING_MISMATCH", "generated reference is absent")
        return validate(parse_json(snapshot[0]), kind)

    def all(self, kind):
        return sorted((doc for doc in self.documents.values() if doc["kind"] == kind),
                      key=lambda doc: self.filename(doc))

    def validate_all(self):
        memo = {}
        for kind in FAMILIES:
            for document in self.all(kind):
                validate_graph(document, self.resolve, memo=memo)
        previous, event_ids = None, set()
        for sequence, decision in enumerate(self.all("decision"), 1):
            data = decision["data"]
            if data["sequence"] != sequence or data["previous"] != previous:
                fail("DECISION_INVALID", "session decision chain is not contiguous")
            event_id = data["user_record"]["event_id"]
            if event_id in event_ids:
                fail("DECISION_CONFLICT", "decision event ID is repeated")
            event_ids.add(event_id)
            previous = reference(decision)
        self.graph_memo = memo

    def write(self, document):
        value = validate(document)
        validate_graph(value, self.resolve, memo=dict(self.graph_memo))
        kind, name = value["kind"], self.filename(value)
        raw, target = saved_bytes(value), self.path(value)
        self.verify()
        previous = self.snapshots[kind].get(name)
        if previous is not None:
            if previous[0] != raw:
                fail("DECISION_CONFLICT" if kind == "decision" else "STAGING_CONFLICT", "immutable artifact already has other bytes")
            return target
        if len(self.snapshots[kind]) >= LIMIT:
            fail("SESSION_LIMIT_EXCEEDED", "preview family is full")
        try:
            staging._atomic_install(self.batch.work_fd, self.family_fds[kind], name, raw,
                                    target=target, checkout_fd=self.batch.checkout_fd)
        finally:
            self.verify_edges()
        current, identity = staging._read_regular_file_at_bounded_identity(
            self.family_fds[kind], name, target, max_bytes=MAX_BYTES)
        if current != raw or identity.st_nlink != 1:
            _unsafe(target, "installed artifact differs from requested bytes")
        self.snapshots[kind][name] = (current, stamp(identity))
        self.documents[value["id"]] = value
        self.validate_all()
        self.verify()
        return target


@contextmanager
def open_preview_session(session: str, *, create=False):
    if type(session) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", session) is None:
        fail("USAGE_ERROR", "session must be a 1–64 character safe slug")
    with staging._open_batch_session("research", create=create) as batch:
        store = PreviewStore(batch, session)
        try:
            store.initialize(create)
            yield store
        finally:
            try:
                store.verify()
            finally:
                for _, _, fd, _, _ in reversed(store.edges):
                    close_fd(fd)
