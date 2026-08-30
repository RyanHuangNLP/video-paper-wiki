"""Local notes grep and stat commands. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.notes.grep import scan_matches
from video_paper_wiki.notes.list import scan_list
from video_paper_wiki.notes.stat import scan_stat

COMMAND = "VAULT.GREP".lower()
STAT_COMMAND = "VAULT.STAT".lower()
LIST_COMMAND = "VAULT.LIST".lower()
_MISSING_DIR = "VAULT_NOT_FOUND"


def _attr(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def grep(_args: object | None = None) -> int:
    raw_query = _attr(_args, "query")
    if raw_query is None or str(raw_query) == "":
        return emit_error(COMMAND, "USAGE", f"{COMMAND} requires a non-empty query")
    raw_root = _attr(_args, "notes_root")
    if raw_root is None or str(raw_root).strip() == "":
        return emit_error(COMMAND, "USAGE", f"{COMMAND} requires --{('VAULT').lower()}")
    root = Path(str(raw_root)).expanduser()
    if not root.is_dir():
        return emit_error(
            COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    return emit_success(COMMAND, {"matches": scan_matches(root, str(raw_query))})


def stat(_args: object | None = None) -> int:
    raw_root = _attr(_args, "notes_root")
    if raw_root is None or str(raw_root).strip() == "":
        return emit_error(
            STAT_COMMAND, "USAGE", f"{STAT_COMMAND} requires --{('VAULT').lower()}"
        )
    root = Path(str(raw_root)).expanduser()
    if not root.is_dir():
        return emit_error(
            STAT_COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    return emit_success(STAT_COMMAND, scan_stat(root))


def list_papers(_args: object | None = None) -> int:
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
    return emit_success(LIST_COMMAND, scan_list(root))
