"""Local wiki show and list commands. Read-only. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.notes.wiki_show import load_topic, scan_wiki_list

COMMAND = "wiki.show"
LIST_COMMAND = "wiki.list"
_MISSING_DIR = "VAULT_NOT_FOUND"
_MISSING_TOPIC = "TOPIC_NOT_FOUND"


def _attr(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def show(_args: object | None = None) -> int:
    raw_id = _attr(_args, "topic_id")
    if raw_id is None or str(raw_id) == "":
        return emit_error(COMMAND, "USAGE", f"{COMMAND} requires a non-empty topic_id")
    raw_root = _attr(_args, "notes_root")
    if raw_root is None or str(raw_root).strip() == "":
        return emit_error(
            COMMAND, "USAGE", f"{COMMAND} requires --{('VAULT').lower()}"
        )
    root = Path(str(raw_root)).expanduser()
    if not root.is_dir():
        return emit_error(
            COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    record = load_topic(root, str(raw_id))
    if record is None:
        return emit_error(
            COMMAND,
            _MISSING_TOPIC,
            "topic page is missing; this command does not create it",
            {"topic_id": str(raw_id)},
        )
    return emit_success(COMMAND, record)


def list_pages(_args: object | None = None) -> int:
    raw_root = _attr(_args, "notes_root")
    if raw_root is None or str(raw_root).strip() == "":
        return emit_error(
            LIST_COMMAND, "USAGE", f"{LIST_COMMAND} requires --{('VAULT').lower()}"
        )
    root = Path(str(raw_root)).expanduser()
    if not root.is_dir():
        return emit_error(
            LIST_COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    return emit_success(LIST_COMMAND, scan_wiki_list(root))

