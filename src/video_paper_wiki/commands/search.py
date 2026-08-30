"""Local notes grep, stat, list, and show commands. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.notes.grep import scan_matches
from video_paper_wiki.notes.list import scan_list
from video_paper_wiki.notes.show import load_paper
from video_paper_wiki.notes.stat import scan_stat

COMMAND = "VAULT.GREP".lower()
STAT_COMMAND = "VAULT.STAT".lower()
LIST_COMMAND = "VAULT.LIST".lower()
SHOW_COMMAND = "VAULT.SHOW".lower()
_MISSING_DIR = "VAULT_NOT_FOUND"
NOT_FOUND = "PAPER_NOT_FOUND"


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
    raw_topic = _attr(_args, "topic_id")
    if raw_topic is not None and str(raw_topic) == "":
        return emit_error(
            LIST_COMMAND, "USAGE", f"{LIST_COMMAND} requires a non-empty --topic"
        )
    raw_year = _attr(_args, "year_raw")
    year: int | None = None
    if raw_year is not None:
        token = str(raw_year)
        if not token.isdigit() or int(token) < 1:
            return emit_error(
                LIST_COMMAND,
                "USAGE",
                f"{LIST_COMMAND} requires a positive integer --year",
            )
        year = int(token)
    if not root.is_dir():
        return emit_error(
            LIST_COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    return emit_success(
        LIST_COMMAND,
        scan_list(
            root,
            None if raw_topic is None else str(raw_topic),
            year,
        ),
    )


def show(_args: object | None = None) -> int:
    raw_id = _attr(_args, "paper_id")
    if raw_id is None or str(raw_id) == "":
        return emit_error(
            SHOW_COMMAND, "USAGE", f"{SHOW_COMMAND} requires a non-empty paper_id"
        )
    raw_root = _attr(_args, "notes_root")
    if raw_root is None or str(raw_root).strip() == "":
        return emit_error(
            SHOW_COMMAND, "USAGE", f"{SHOW_COMMAND} requires --{('VAULT').lower()}"
        )
    root = Path(str(raw_root)).expanduser()
    if not root.is_dir():
        return emit_error(
            SHOW_COMMAND,
            _MISSING_DIR,
            "directory is missing or not a directory; this command does not create it",
            {"path": str(raw_root)},
        )
    record = load_paper(root, str(raw_id))
    if record is None:
        return emit_error(
            SHOW_COMMAND,
            NOT_FOUND,
            "paper note is missing; this command does not create it",
            {"paper_id": str(raw_id)},
        )
    return emit_success(SHOW_COMMAND, record)
