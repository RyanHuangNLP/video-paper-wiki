"""Local content-addressed blob store. Zero network."""

from __future__ import annotations

import hashlib
import os
import shutil
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

    def put_from_path(self, src: Path) -> str:
        data = Path(src).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        dest = self.path_for(digest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        return digest

    def stage(self, sha256: str, dest_dir: Path) -> Path:
        source = self.get(sha256)
        if source is None:
            raise FileNotFoundError(sha256)
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / _normalize_sha256(sha256)
        shutil.copy2(source, dest)
        return dest
