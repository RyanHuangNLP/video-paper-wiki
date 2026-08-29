"""A local-only content-addressed blob store."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def resolve_blob_root() -> Path:
    """Resolve the blob root without consulting any external service."""
    configured = os.environ.get("VPWIKI_BLOB_ROOT")
    if configured:
        candidate = Path(configured)
        return candidate if candidate.is_absolute() else Path.cwd() / candidate
    return Path.cwd() / ".work" / "blobs"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BlobStore:
    """Store and stage blobs addressed by their SHA-256 digest."""

    def __init__(self, root: Path):
        self.root = root

    def path_for(self, sha256: str) -> Path:
        return self.root / sha256.lower()

    def get(self, sha256: str) -> Path | None:
        normalized = sha256.lower()
        candidate = self.path_for(normalized)
        if not candidate.is_file():
            return None
        if file_sha256(candidate) != normalized:
            return None
        return candidate

    def put_from_path(self, src: Path) -> str:
        digest = file_sha256(src)
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(digest)
        if self.get(digest) is None:
            shutil.copyfile(src, destination)
        return digest

    def stage(self, sha256: str, dest_dir: Path) -> Path:
        normalized = sha256.lower()
        source = self.get(normalized)
        if source is None:
            raise FileNotFoundError(normalized)
        dest_dir.mkdir(parents=True, exist_ok=True)
        destination = dest_dir / normalized
        shutil.copyfile(source, destination)
        return destination

    def stage_file(self, src: Path, dest_dir: Path) -> tuple[str, Path]:
        digest = file_sha256(src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        destination = dest_dir / digest
        shutil.copyfile(src, destination)
        return digest, destination
