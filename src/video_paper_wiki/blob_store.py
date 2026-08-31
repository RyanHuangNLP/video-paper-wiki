"""Local content-addressed blob store. Read-only. Zero network."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from video_paper_wiki.secure_io import (
    BLOB_HASH_MISMATCH,
    BLOB_LIMIT_EXCEEDED,
    BLOB_NOT_FOUND,
    BLOB_PATH_UNSAFE,
    SOURCE_CHANGED,
    SecureIOError,
    close_fd,
    open_dir_nofollow,
    read_child_regular,
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_sha256(sha256: str) -> str:
    return sha256.strip().lower()


def resolve_blob_root(cwd: Path | None = None) -> Path:
    raw = os.environ.get("VPWIKI_BLOB_ROOT")
    base = cwd if cwd is not None else Path.cwd()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (base / path)
    return base / ".work" / "blobs"


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, sha256: str) -> Path:
        return self.root / _normalize_sha256(sha256)

    def read(self, sha256: str, *, max_bytes: int | None = None) -> bytes:
        digest = _normalize_sha256(sha256)
        if not SHA256_RE.fullmatch(digest):
            raise SecureIOError(
                BLOB_PATH_UNSAFE,
                "blob name is not a lowercase SHA-256 digest",
                {"sha256": sha256},
            )
        root_fd: int | None = None
        target = self.path_for(digest)
        try:
            root_fd = open_dir_nofollow(
                self.root, missing_code=BLOB_NOT_FOUND, unsafe_code=BLOB_PATH_UNSAFE
            )
            data = read_child_regular(
                root_fd,
                digest,
                path=target,
                missing_code=BLOB_NOT_FOUND,
                unsafe_code=BLOB_PATH_UNSAFE,
                changed_code=SOURCE_CHANGED,
                max_bytes=max_bytes,
                limit_code=BLOB_LIMIT_EXCEEDED,
            )
        except SecureIOError as exc:
            if "path" not in exc.details:
                exc.details["path"] = target.as_posix()
            raise
        finally:
            close_fd(root_fd)
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise SecureIOError(
                BLOB_HASH_MISMATCH,
                "blob bytes do not match the digest name",
                {"expected": digest, "actual": actual},
            )
        return data

    def get(self, sha256: str) -> Path | None:
        digest = _normalize_sha256(sha256)
        try:
            self.read(digest)
        except SecureIOError:
            return None
        return self.path_for(digest)
