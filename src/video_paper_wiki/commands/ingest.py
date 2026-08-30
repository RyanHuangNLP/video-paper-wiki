"""Local ingest put and run. Copies a local file into the blob store. Zero network."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.commands import draft as draft_commands
from video_paper_wiki.commands import review as review_commands
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.parse.draft_document import InvalidPaperId, validate_paper_id

_COPY_KEY = "VAULT_PATH".lower()


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


def _invoke(handler: Callable[..., int], ns: object) -> tuple[int, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        code = handler(ns)
    return code, buf.getvalue()


def _replay(captured: str, code: int) -> int:
    sys.stdout.write(captured)
    sys.stdout.flush()
    return code


def run(_args: object | None = None) -> int:
    raw = None if _args is None else getattr(_args, "path", None)
    notes_root = None if _args is None else getattr(_args, "notes_root", None)
    paper_id_arg = None if _args is None else getattr(_args, "paper_id", None)
    if paper_id_arg is not None:
        try:
            validate_paper_id(str(paper_id_arg))
        except InvalidPaperId:
            return emit_error(
                "ingest.run",
                "INVALID_PAPER_ID",
                "paper_id is empty or not a safe path segment",
                {"paper_id": str(paper_id_arg)},
            )

    code, captured = _invoke(put, Namespace(path=raw))
    if code != 0:
        return _replay(captured, code)
    put_data = json.loads(captured.strip())["data"]
    sha256 = put_data["sha256"]

    code, captured = _invoke(
        draft_commands.export,
        Namespace(sha256=sha256, paper_id=paper_id_arg),
    )
    if code != 0:
        return _replay(captured, code)
    export_data = json.loads(captured.strip())["data"]
    draft_path = export_data["path"]
    paper_id = export_data["paper_id"]

    code, captured = _invoke(draft_commands.validate, Namespace(path=draft_path))
    if code != 0:
        return _replay(captured, code)

    code, captured = _invoke(
        review_commands.export,
        Namespace(draft=draft_path, notes_root=notes_root),
    )
    if code != 0:
        return _replay(captured, code)
    review_data = json.loads(captured.strip())["data"]

    data: dict[str, Any] = {
        "sha256": sha256,
        "paper_id": paper_id,
        "draft_path": draft_path,
        "note_path": review_data["path"],
    }
    if _COPY_KEY in review_data:
        data[_COPY_KEY] = review_data[_COPY_KEY]
    return emit_success("ingest.run", data)
