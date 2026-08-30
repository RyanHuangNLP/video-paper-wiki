"""Local ingest put. Copies a local file into the blob store. Zero network."""

from __future__ import annotations

from pathlib import Path

from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.envelope import emit_error, emit_success


def put(_args: object | None = None) -> int:
    raw = None if _args is None else getattr(_args, "path", None)
    if raw is None or str(raw).strip() == "":
        return emit_error(
            "ingest.put",
            "USAGE",
            "ingest.put requires --path",
        )
    path = Path(str(raw)).expanduser()
    try:
        if not path.is_file():
            return emit_error(
                "ingest.put",
                "BLOB_SOURCE_NOT_FOUND",
                "local source file is missing or unreadable; this command does not download",
                {"path": str(raw)},
            )
        store = BlobStore(resolve_blob_root())
        digest = store.put_from_path(path)
    except OSError as exc:
        return emit_error(
            "ingest.put",
            "BLOB_SOURCE_NOT_FOUND",
            "local source file is missing or unreadable; this command does not download",
            {"path": str(raw), "reason": str(exc)},
        )
    stored = store.path_for(digest)
    return emit_success(
        "ingest.put",
        {
            "sha256": digest,
            "path": stored.as_posix(),
        },
    )
