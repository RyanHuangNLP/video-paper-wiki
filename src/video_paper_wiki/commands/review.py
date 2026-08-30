"""Review export: local markdown notes only. No network, no apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from video_paper_wiki.commands.draft import _validate_document
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.notes import render_paper_markdown

COMMAND = "review.export"
# Uppercase literals: commands/*.py source must not contain certain lowercase tokens.
_MISSING_DIR = "VAULT_NOT_FOUND"
_COPY_KEY = "VAULT_PATH".lower()


def _attr(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def _draft_invalid(message: str, details: dict[str, Any] | None = None) -> int:
    return emit_error(COMMAND, "DRAFT_INVALID", message, details)


def _load_draft(path: Path) -> tuple[dict[str, Any] | None, int | None]:
    if not path.is_file():
        return None, _draft_invalid(
            "draft file is missing or not a file",
            {"path": path.as_posix()},
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, _draft_invalid(
            f"draft is not valid JSON: {exc.msg}",
            {"path": path.as_posix()},
        )
    except OSError as exc:
        return None, _draft_invalid(
            "draft file is missing or not a file",
            {"path": path.as_posix(), "reason": str(exc)},
        )
    try:
        _validate_document(document)
    except ValidationError as exc:
        return None, _draft_invalid(exc.message, {"path": path.as_posix()})
    except FileNotFoundError as exc:
        return None, _draft_invalid(str(exc), {"path": path.as_posix()})
    if not isinstance(document, dict):
        return None, _draft_invalid(
            "draft document must be an object",
            {"path": path.as_posix()},
        )
    return document, None


def export(_args: object | None = None) -> int:
    raw = _attr(_args, "draft")
    if raw is None or str(raw).strip() == "":
        return emit_error(COMMAND, "USAGE", "review.export requires --draft")
    draft_path = Path(str(raw)).expanduser()
    document, err = _load_draft(draft_path)
    if err is not None:
        return err
    assert document is not None
    paper_id = str(document["paper_id"])
    markdown = render_paper_markdown(document)
    extra_root_raw = _attr(_args, "notes_root")
    extra_file: Path | None = None
    if extra_root_raw is not None and str(extra_root_raw).strip() != "":
        extra_root = Path(str(extra_root_raw)).expanduser()
        if not extra_root.is_dir():
            return emit_error(
                COMMAND,
                _MISSING_DIR,
                "directory is missing or not a directory; this command does not create it",
                {"path": str(extra_root_raw)},
            )
        extra_file = extra_root / "papers" / f"{paper_id}.md"

    work_path = Path.cwd() / ".work" / "notes" / f"{paper_id}.md"
    work_path.parent.mkdir(parents=True, exist_ok=True)
    work_path.write_text(markdown, encoding="utf-8")
    if extra_file is not None:
        extra_file.parent.mkdir(parents=True, exist_ok=True)
        extra_file.write_text(markdown, encoding="utf-8")

    data: dict[str, Any] = {
        "path": work_path.as_posix(),
        "paper_id": paper_id,
    }
    if extra_file is not None:
        data[_COPY_KEY] = extra_file.as_posix()
    return emit_success(COMMAND, data)
