"""Retained, read-only snapshot of the staged capture destination."""
from __future__ import annotations

import hashlib
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, NoReturn

from video_paper_wiki.contracts import ContractError

MAX_CAPTURE_ENTRIES = 1024
MAX_CAPTURE_BYTES = 67108864
_NAME = re.compile(r"([0-9a-f]{64})\.([A-Za-z0-9][A-Za-z0-9._-]*)")


def _fail(message: str, *, limit: bool = False) -> NoReturn:
    raise ContractError(
        "UPSTREAM_LIMIT_EXCEEDED" if limit else "CAPTURE_SNAPSHOT_INVALID",
        message,
        {"instance_pointer": "/vault_root/.raw/captured"},
    )


def _dir_flags() -> int:
    value = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    return value | getattr(os, "O_NOFOLLOW", 0)


def _file_flags() -> int:
    return (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))


def _same(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino, stat.S_IFMT(a.st_mode), stat.S_IMODE(a.st_mode), a.st_size, a.st_mtime_ns) == (
        b.st_dev, b.st_ino, stat.S_IFMT(b.st_mode), stat.S_IMODE(b.st_mode), b.st_size, b.st_mtime_ns,
    )


@dataclass
class CapturedSnapshot:
    vault: Path
    digest: str
    vault_fd: int
    raw_fd: int | None
    captured_fd: int | None
    identities: tuple[os.stat_result | None, os.stat_result | None, os.stat_result | None]
    inventory: tuple[tuple[str, int, int, int, int, int, int], ...]
    stored_path: str
    sibling: dict[str, object] | None
    payload: bytes

    def verify(self) -> None:
        _verify_directory_lineage(
            self.vault, (self.vault_fd, self.raw_fd, self.captured_fd), self.identities,
        )
        try:
            inventory, sibling, payload = _scan(self.captured_fd, self.digest)
            if inventory != self.inventory or sibling != self.sibling or payload != self.payload:
                _fail("captured directory contents changed")
        except BaseException:
            _verify_directory_lineage(
                self.vault, (self.vault_fd, self.raw_fd, self.captured_fd), self.identities,
            )
            raise
        else:
            _verify_directory_lineage(
                self.vault, (self.vault_fd, self.raw_fd, self.captured_fd), self.identities,
            )


def _verify_directory_lineage(
    vault: Path,
    fds: tuple[int | None, int | None, int | None],
    identities: tuple[os.stat_result | None, os.stat_result | None, os.stat_result | None],
) -> None:
    """Re-prove retained and named vault/raw/captured directory identities."""
    for fd, expected in zip(fds, identities, strict=True):
        if fd is None or expected is None:
            if fd is not None or expected is not None:
                _fail("captured directory state changed")
            continue
        try:
            current = os.fstat(fd)
        except OSError:
            _fail("captured directory state changed")
        if not _same(current, expected):
            _fail("captured directory identity changed")
    opened: list[int] = []
    try:
        vault_fd = os.open(vault, _dir_flags())
        opened.append(vault_fd)
        if not _same(os.fstat(vault_fd), identities[0]):
            _fail("vault root identity changed")
        raw_expected = identities[1]
        try:
            raw_fd = os.open(".raw", _dir_flags(), dir_fd=vault_fd)
        except FileNotFoundError:
            raw_fd = None
        except OSError:
            _fail("raw directory became unsafe")
        if raw_fd is not None:
            opened.append(raw_fd)
        if ((raw_fd is None) != (raw_expected is None)
                or raw_fd is not None and not _same(os.fstat(raw_fd), raw_expected)):
            _fail("raw directory identity changed")
        captured_expected = identities[2]
        captured_fd = None
        if raw_fd is not None:
            try:
                captured_fd = os.open("captured", _dir_flags(), dir_fd=raw_fd)
            except FileNotFoundError:
                pass
            except OSError:
                _fail("captured directory became unsafe")
        if captured_fd is not None:
            opened.append(captured_fd)
        if ((captured_fd is None) != (captured_expected is None)
                or captured_fd is not None
                and not _same(os.fstat(captured_fd), captured_expected)):
            _fail("captured directory identity changed")
    except ContractError:
        raise
    except OSError:
        _fail("vault root became unsafe")
    finally:
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def _scan(captured_fd: int | None, digest: str) -> tuple[tuple[tuple[str, int, int, int, int, int, int], ...], dict[str, object] | None, bytes]:
    if captured_fd is None:
        return (), None, b""
    try:
        names = sorted(os.listdir(captured_fd))
    except OSError:
        _fail("captured directory cannot be enumerated")
    if len(names) > MAX_CAPTURE_ENTRIES:
        _fail("captured directory exceeds entry limit", limit=True)
    inventory = []
    matches: list[tuple[str, os.stat_result]] = []
    for name in names:
        try:
            info = os.stat(name, dir_fd=captured_fd, follow_symlinks=False)
        except OSError:
            _fail("captured entry changed during enumeration")
        inventory.append((name, info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns))
        if name.startswith(digest + "."):
            if _NAME.fullmatch(name) is None:
                _fail("matching captured name is not portable")
            if not stat.S_ISREG(info.st_mode):
                _fail("matching captured entry is not regular")
            matches.append((name, info))
    if len(matches) > 1:
        _fail("multiple matching captured siblings")
    if not matches:
        return tuple(inventory), None, b""
    name, info = matches[0]
    if info.st_size > MAX_CAPTURE_BYTES:
        _fail("captured payload exceeds byte limit", limit=True)
    try:
        fd = os.open(name, _file_flags(), dir_fd=captured_fd)
        try:
            opened = os.fstat(fd)
            if not _same(opened, info):
                _fail("matching captured entry identity changed")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(1024 * 1024, MAX_CAPTURE_BYTES + 1 - total))
                if not chunk: break
                chunks.append(chunk); total += len(chunk)
                if total > MAX_CAPTURE_BYTES: _fail("captured payload exceeds byte limit", limit=True)
            data = b"".join(chunks)
            if not _same(os.fstat(fd), info): _fail("matching captured entry changed while read")
        finally:
            os.close(fd)
    except ContractError:
        raise
    except OSError:
        _fail("matching captured entry cannot be read")
    if hashlib.sha256(data).hexdigest() != digest:
        _fail("matching captured bytes differ from filename digest")
    sibling = {"path": ".raw/captured/" + name, "kind": "regular", "sha256": digest, "mode": stat.S_IMODE(info.st_mode)}
    return tuple(inventory), sibling, data


@contextmanager
def capture_snapshot(vault_root: Path, digest: str) -> Iterator[CapturedSnapshot]:
    owned: list[int] = []
    try:
        vault_fd = os.open(vault_root, _dir_flags()); owned.append(vault_fd)
        try: raw_fd = os.open(".raw", _dir_flags(), dir_fd=vault_fd)
        except FileNotFoundError: raw_fd = None
        except OSError: _fail("raw directory is unsafe")
        if raw_fd is not None: owned.append(raw_fd)
        captured_fd = None
        if raw_fd is not None:
            try: captured_fd = os.open("captured", _dir_flags(), dir_fd=raw_fd)
            except FileNotFoundError: pass
            except OSError: _fail("captured directory is unsafe")
        if captured_fd is not None: owned.append(captured_fd)
        identities = tuple(os.fstat(fd) if fd is not None else None for fd in (vault_fd, raw_fd, captured_fd))
        _verify_directory_lineage(
            vault_root, (vault_fd, raw_fd, captured_fd), identities,
        )
        try:
            inventory, sibling, payload = _scan(captured_fd, digest)
        except BaseException:
            _verify_directory_lineage(
                vault_root, (vault_fd, raw_fd, captured_fd), identities,
            )
            raise
        else:
            _verify_directory_lineage(
                vault_root, (vault_fd, raw_fd, captured_fd), identities,
            )
        stored = sibling["path"] if sibling else f".raw/captured/{digest}.pdf"
        value = CapturedSnapshot(vault_root, digest, vault_fd, raw_fd, captured_fd, identities, inventory, str(stored), sibling, payload)
        value.verify()
        try:
            yield value
        except BaseException:
            value.verify()
            raise
        else:
            value.verify()
    except ContractError:
        raise
    except OSError:
        _fail("vault root is not a safe directory")
    finally:
        for fd in reversed(owned):
            try: os.close(fd)
            except OSError: pass
