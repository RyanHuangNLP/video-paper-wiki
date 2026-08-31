"""Local content-addressed blob store. Read-only. Zero network."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


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

    def get(self, sha256: str) -> Path | None:
        digest = _normalize_sha256(sha256)
        path = self.path_for(digest)
        if not path.is_file():
            return None
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            return None
        return path
