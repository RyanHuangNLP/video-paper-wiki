"""Retained named edges and no-clobber staging for Markdown handoffs."""
from __future__ import annotations

import os
import re
import stat
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from video_paper_wiki.markdown_source_contracts import fail, json_preflight
from video_paper_wiki.secure_io import dir_open_flags, file_open_flags, parse_strict_json, stamp
from video_paper_wiki.staging import (
    _atomic_install, _ensure_dir_at, _open_batch_session, _open_dir_at,
    resolve_checkout_root, validate_batch_id,
)


def checked_path(value: Path | str) -> Path:
    """Check the caller spelling before Path/abspath can discard traversal."""
    try:
        raw = os.fspath(value)
        if (type(raw) is not str or not raw or "\0" in raw or "\\" in raw
                or ".." in raw.split("/") or any(ord(c) < 32 for c in raw)):
            raise ValueError
        return Path(os.path.abspath(raw))
    except (TypeError, ValueError, OSError):
        fail("WORK_PATH_UNSAFE", "input path is not safe")


def _identity(value: os.stat_result) -> tuple:
    return value.st_dev, value.st_ino, value.st_mode


class RetainedDirectory:
    """Keep every named edge through the final input directory."""

    def __init__(self, path: Path | str):
        self.path = checked_path(path)
        self.fds, self.edges = [], []
        try:
            fd = os.open("/", dir_open_flags())
            self.fds.append(fd)
            self.root_stat = os.fstat(fd)
            for name in self.path.parts[1:]:
                child = os.open(name, dir_open_flags(), dir_fd=fd)
                self.fds.append(child)
                first = os.fstat(child)
                self.edges.append((fd, name, child, first))
                fd = child
            self.verify()
        except BaseException as exc:
            try:
                if self.fds:
                    self.verify()
            finally:
                self.close()
            if hasattr(exc, "code"):
                raise
            fail("WORK_PATH_UNSAFE", "input directory is missing or unsafe")

    def verify(self) -> None:
        try:
            if _identity(os.fstat(self.fds[0])) != _identity(self.root_stat):
                raise OSError
            for parent, name, child, first in self.edges:
                if (_identity(os.fstat(child)) != _identity(first)
                        or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(first)):
                    raise OSError
        except OSError:
            fail("WORK_PATH_UNSAFE", "input directory named lineage changed")

    def close(self) -> None:
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []


def retain_directory_arguments(*names):
    """Retain caller directory spellings around every exit of keyword-only APIs."""
    def decorate(function):
        @wraps(function)
        def call(**kwargs):
            held = []
            try:
                for name in names:
                    held.append(RetainedDirectory(kwargs.get(name)))
                return function(**kwargs)
            finally:
                try:
                    for item in held:
                        item.verify()
                finally:
                    for item in reversed(held):
                        item.close()
        return call
    return decorate


class RetainedFile:
    """Keep all named ancestors and a regular file (including a missing slot)."""

    def __init__(self, path: Path | str, *, maximum: int, required: bool = True):
        self.path = checked_path(path)
        self.edges = []
        self.fds = []
        self.fd = None
        self.first = None
        self.data = None
        self.maximum = maximum
        try:
            fd = os.open("/", dir_open_flags())
            self.fds.append(fd)
            self.root_stat = os.fstat(fd)
            for part in self.path.parts[1:-1]:
                child = os.open(part, dir_open_flags(), dir_fd=fd)
                self.fds.append(child)
                first = os.fstat(child)
                if _identity(first) != _identity(os.stat(part, dir_fd=fd, follow_symlinks=False)):
                    raise OSError
                self.edges.append((fd, part, child, first))
                fd = child
            self.parent_fd, self.name = fd, self.path.name
            self._open(required=required)
            self.verify()
        except BaseException as exc:
            try:
                # Even acquisition errors must recheck already retained ancestors.
                if hasattr(self, "root_stat"):
                    self.verify_ancestors()
            finally:
                self.close()
            if hasattr(exc, "code"):
                raise
            fail("WORK_PATH_UNSAFE", "input is missing, oversized or unsafe")

    def _open(self, *, required: bool) -> None:
        try:
            self.fd = os.open(self.name, file_open_flags(), dir_fd=self.parent_fd)
        except FileNotFoundError:
            if required:
                raise
            return
        self.first = os.fstat(self.fd)
        if (not stat.S_ISREG(self.first.st_mode) or self.first.st_nlink != 1
                or self.first.st_size > self.maximum):
            raise OSError
        parts, size = [], 0
        while True:
            chunk = os.read(self.fd, min(65536, self.maximum + 1 - size))
            if not chunk:
                break
            parts.append(chunk)
            size += len(chunk)
            if size > self.maximum:
                raise OSError
        self.data = b"".join(parts)

    def verify_ancestors(self) -> None:
        try:
            if _identity(os.fstat(self.fds[0])) != _identity(self.root_stat):
                raise OSError
            for parent, name, fd, first in self.edges:
                if (_identity(os.fstat(fd)) != _identity(first)
                        or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(first)):
                    raise OSError
        except OSError:
            fail("WORK_PATH_UNSAFE", "a retained named input ancestor changed")

    def verify(self) -> None:
        self.verify_ancestors()
        try:
            try:
                named = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if self.fd is None:
                    return
                raise
            if (self.fd is None or named.st_nlink != 1 or stamp(named) != stamp(self.first)
                    or stamp(os.fstat(self.fd)) != stamp(self.first)):
                raise OSError
            os.lseek(self.fd, 0, os.SEEK_SET)
            size, parts = 0, []
            while True:
                chunk = os.read(self.fd, min(65536, self.maximum + 1 - size))
                if not chunk:
                    break
                parts.append(chunk)
                size += len(chunk)
                if size > self.maximum:
                    raise OSError
            if b"".join(parts) != self.data or stamp(os.fstat(self.fd)) != stamp(self.first):
                raise OSError
        except OSError:
            fail("WORK_PATH_UNSAFE", "retained file bytes or identity changed")
        finally:
            self.verify_ancestors()

    def adopt(self, identity: os.stat_result, data: bytes) -> None:
        """Only a successful install through our retained directory fills a slot."""
        if self.fd is not None:
            fail("WORK_PATH_UNSAFE", "cannot replace an already retained slot")
        try:
            self._open(required=True)
            if _identity(self.first) != _identity(identity) or self.data != data:
                raise OSError
            self.verify()
        except OSError:
            fail("WORK_PATH_UNSAFE", "installed file identity changed")

    def close(self) -> None:
        for fd in [self.fd, *reversed(self.fds)]:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.fd = None
        self.fds = []


@contextmanager
def retain_files(specs):
    held = []
    try:
        for path, maximum, required in specs:
            held.append(RetainedFile(path, maximum=maximum, required=required))
        yield held
    finally:
        try:
            for item in held:
                item.verify()
        finally:
            for item in reversed(held):
                item.close()


def json_bytes(raw: bytes, *, code: str) -> object:
    try:
        value = parse_strict_json(raw, invalid_code=code)
        json_preflight(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        if hasattr(exc, "code"):
            raise
        fail(code, "input must be bounded strict UTF-8 JSON")


def fixed_batch(value: Path | str, filename: str) -> tuple[Path, str]:
    path = checked_path(value)
    checkout = resolve_checkout_root()
    try:
        relative = path.relative_to(checkout / ".work")
        batch = validate_batch_id(relative.parts[0])
        if relative.parts != (batch, "markdown-source", filename):
            raise ValueError
    except (ValueError, IndexError):
        fail("WORK_PATH_UNSAFE", "Markdown handoff must use its fixed batch slot")
    return path, batch


class MarkdownSlots:
    """One batch lineage and complete fixed-slot set, across reads and installs."""

    def __init__(self, session, *, create: bool):
        self.session = session
        self.path = session.batch_path / "markdown-source"
        self.files = {}
        self.fd = None
        try:
            if create:
                self.fd = _ensure_dir_at(session.batch_fd, "markdown-source", self.path,
                                         work_fd=session.work_fd)
            else:
                self.fd = _open_dir_at(session.batch_fd, "markdown-source", self.path)
            self.first = os.fstat(self.fd)
            self.names = set(os.listdir(self.fd))
            if any(name not in {"plan.json", "request.json"} and re.fullmatch(r"[0-9a-f]{64}\.md", name) is None
                   for name in self.names) or len(self.names) > 3:
                fail("WORK_PATH_UNSAFE", "Markdown staging contains unexpected entries")
            # Capture both fixed JSON slots before parsing either document.
            for name in sorted(self.names | {"plan.json", "request.json"}):
                self.files[name] = RetainedFile(self.path / name, maximum=8388608 if name.endswith(".md") else 1048576,
                                                 required=name in self.names)
            self.verify()
        except BaseException:
            try:
                self.verify_directory()
            finally:
                self.close()
            raise

    def verify_directory(self) -> None:
        self.session.verify()
        if self.fd is None:
            return
        try:
            if (_identity(os.fstat(self.fd)) != _identity(self.first)
                    or _identity(os.stat("markdown-source", dir_fd=self.session.batch_fd,
                                         follow_symlinks=False)) != _identity(self.first)):
                raise OSError
        except OSError:
            fail("WORK_PATH_UNSAFE", "Markdown staging directory lineage changed")

    def verify(self) -> None:
        self.verify_directory()
        try:
            if set(os.listdir(self.fd)) != self.names:
                fail("WORK_PATH_UNSAFE", "Markdown staging complete set changed")
            for held in self.files.values():
                held.verify()
        finally:
            self.verify_directory()

    def payload_slot(self, digest: str) -> str:
        self.verify()
        name = digest + ".md"
        if not self.names <= {"plan.json", "request.json", name}:
            fail("WORK_PATH_UNSAFE", "Markdown staging contains a different payload")
        if name not in self.files:
            self.files[name] = RetainedFile(self.path / name, maximum=8388608, required=False)
        self.verify()
        return name

    def read(self, name: str) -> bytes:
        self.verify()
        value = self.files[name].data
        if value is None:
            fail("MARKDOWN_REQUEST_MISMATCH", "required Markdown slot is missing")
        return value

    def install(self, name: str, data: bytes) -> bool:
        self.verify()
        held = self.files[name]
        if held.data is not None:
            if held.data != data:
                fail("MARKDOWN_CAPTURE_CONFLICT", "staged file already holds different bytes")
            return True
        reused, identity = _atomic_install(self.session.work_fd, self.fd, name, data,
                                           target=self.path / name, checkout_fd=self.session.checkout_fd,
                                           return_identity=True)
        if reused:
            fail("WORK_PATH_UNSAFE", "previously missing slot was filled by another writer")
        held.adopt(identity, data)
        self.names.add(name)
        self.verify()
        return False

    def close(self) -> None:
        for item in self.files.values():
            item.close()
        if self.fd is not None:
            os.close(self.fd)
        self.fd = None


@contextmanager
def markdown_slots(batch: object, *, create: bool):
    with _open_batch_session(validate_batch_id(batch), create=create) as session:
        slots = MarkdownSlots(session, create=create)
        try:
            yield slots
        finally:
            try:
                slots.verify()
            finally:
                slots.close()
