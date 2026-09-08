"""Read-only inspection of a lightweight research workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import (
    INDEX_DIRNAME,
    INDEX_FILENAME,
    _HEX64,
    _index_is_current,
    _index_path,
    _load_index,
    _paper_dirs,
)
from video_paper_wiki_research.light_library_state import library_diagnostics
from video_paper_wiki_research.light_pdf import (
    SOURCE_INVALID,
    TRANSACTIONS_DIR,
    WORKSPACE_INVALID,
    classify_paper_dir,
    iter_markers,
    lock_is_held,
    lock_path_for,
)

SCHEMA = "video-paper-wiki.light-workspace.v1"
OK = "OK"


def _fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _diagnostic(relative_path: str, code: str, message: str) -> dict[str, str]:
    return {"relative_path": relative_path, "code": code, "message": message}


def _resolved_root(workspace_root: Path) -> Path:
    root = Path(workspace_root)
    if root.is_symlink():
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory", {"path": str(root)})
    if root.exists() and not root.is_dir():
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory", {"path": str(root)})
    return root.resolve()


def _paper_row(loaded: dict[str, Any]) -> dict[str, Any]:
    warnings = loaded["metadata"].get("warnings")
    if type(warnings) is not list:
        warning_rows: list[str] = []
    else:
        warning_rows = [item for item in warnings if type(item) is str]
    return {
        "paper_id": loaded["paper_id"],
        "title": loaded["title"],
        "page_count": loaded["page_count"],
        "markdown_path": loaded["markdown_path"],
        "markdown_sha256": loaded["markdown_sha256"],
        "metadata_stale": bool(loaded["metadata_stale"]),
        "warnings": warning_rows,
    }


def _index_state(workspace: Path, valid_papers: list[dict[str, Any]]) -> tuple[str, str | None, list[dict[str, str]]]:
    diagnostics: list[dict[str, str]] = []
    path = _index_path(workspace)
    relative = f"{INDEX_DIRNAME}/{INDEX_FILENAME}"
    if not path.exists() and not path.is_symlink():
        return "missing", None, diagnostics
    if path.is_symlink():
        diagnostics.append(_diagnostic(relative, "INDEX_INVALID", "index path is a symlink"))
        return "invalid", None, diagnostics
    stored = _load_index(workspace)
    if stored is None:
        diagnostics.append(_diagnostic(relative, "INDEX_INVALID", "index file is missing or not a valid light-index"))
        return "invalid", None, diagnostics
    index_id = stored.get("index_id")
    index_id_s = index_id if type(index_id) is str else None
    if _index_is_current(stored, valid_papers):
        return "current", index_id_s, diagnostics
    return "stale", index_id_s, diagnostics


def _scan_unexpected_papers(workspace: Path) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    papers = workspace / "papers"
    if not papers.exists() and not papers.is_symlink():
        return diagnostics
    if papers.is_symlink() or not papers.is_dir():
        diagnostics.append(_diagnostic("papers", "PAPER_UNEXPECTED_PATH", "papers/ is not a regular directory"))
        return diagnostics
    for item in sorted(papers.iterdir(), key=lambda path: path.name):
        relative = f"papers/{item.name}"
        if item.is_symlink():
            diagnostics.append(_diagnostic(relative, "PAPER_SYMLINK", "unexpected symlink under papers/"))
            continue
        if item.is_dir():
            if not _HEX64.fullmatch(item.name):
                diagnostics.append(_diagnostic(relative, "PAPER_UNEXPECTED_PATH", "paper directory name is not a SHA-256 digest"))
            continue
        diagnostics.append(_diagnostic(relative, "PAPER_UNEXPECTED_PATH", "unexpected non-directory entry under papers/"))
    return diagnostics


def _scan_transactions(workspace: Path) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    tx_dir = workspace / TRANSACTIONS_DIR
    if not tx_dir.exists() and not tx_dir.is_symlink():
        return diagnostics
    if tx_dir.is_symlink() or not tx_dir.is_dir():
        diagnostics.append(
            _diagnostic(TRANSACTIONS_DIR, "TRANSACTION_UNKNOWN", "transaction directory is not a regular directory")
        )
        return diagnostics
    recognized_markers = {path.name for path, _marker in iter_markers(workspace)}
    recognized_staging: set[str] = set()
    for _path, marker in iter_markers(workspace):
        recognized_staging.add(f"{marker['digest']}--{marker['token']}")
        lock = lock_path_for(workspace, marker["digest"])
        active = lock_is_held(lock)
        code = "TRANSACTION_ACTIVE" if active else "TRANSACTION_ABANDONED"
        word = "active" if active else "abandoned"
        diagnostics.append(
            _diagnostic(
                f"{TRANSACTIONS_DIR}/{_path.name}",
                code,
                f"{word} transaction for digest {marker['digest']}",
            )
        )
    for item in sorted(tx_dir.iterdir(), key=lambda path: path.name):
        relative = f"{TRANSACTIONS_DIR}/{item.name}"
        if item.name.endswith(".lock"):
            if item.is_symlink() or not item.is_file():
                diagnostics.append(_diagnostic(relative, "TRANSACTION_UNKNOWN", "lock path is not a regular file"))
            continue
        if item.name.endswith(".owner.json"):
            if item.name not in recognized_markers:
                diagnostics.append(_diagnostic(relative, "TRANSACTION_UNKNOWN", "transaction marker is not a recognized owned set"))
            continue
        if item.name == "staging":
            if item.is_symlink() or not item.is_dir():
                diagnostics.append(_diagnostic(relative, "TRANSACTION_UNKNOWN", "staging path is not a regular directory"))
                continue
            for child in sorted(item.iterdir(), key=lambda path: path.name):
                child_rel = f"{relative}/{child.name}"
                if child.name in recognized_staging:
                    continue
                diagnostics.append(_diagnostic(child_rel, "TRANSACTION_UNKNOWN", "staging directory has no proven ownership marker"))
            continue
        diagnostics.append(_diagnostic(relative, "TRANSACTION_UNKNOWN", "unexpected transaction entry"))
    return diagnostics


def _state(*, damage: bool, pending: bool, paper_count: int, index_state: str) -> str:
    if damage or pending:
        return "needs_attention"
    if paper_count == 0:
        return "empty"
    if index_state != "current":
        return "needs_index"
    return "ready"


def _next_actions(state: str, diagnostics: list[dict[str, str]], index_state: str) -> list[str]:
    if state == "empty":
        return ["Add a local PDF to this workspace."]
    actions: list[str] = []
    if state == "needs_attention":
        if any(item["code"].startswith("TRANSACTION_") for item in diagnostics):
            actions.append("Inspect abandoned or unknown transactions; do not delete unrecognized files.")
        if any(item["code"].startswith("LIBRARY_") for item in diagnostics):
            actions.append("Call recover_library to finish or inspect the pending library operation.")
        if any(item["code"].startswith("PAPER_") or item["code"] == SOURCE_INVALID for item in diagnostics):
            actions.append("Resolve damaged or unexpected paper entries without deleting unknown files.")
        if any(item["code"] == "INDEX_INVALID" for item in diagnostics):
            actions.append("Replace or rebuild the unreadable lexical index.")
    if state == "needs_index" or (state == "ready" and index_state != "current"):
        actions.append("Build the lexical index.")
    if state == "needs_index" and index_state == "missing":
        actions = ["Build the lexical index."]
    if state == "ready":
        return ["Workspace papers are complete and the index is current."]
    if not actions:
        actions.append("Inspect workspace diagnostics.")
    return actions


def inspect_workspace(workspace_root: Path) -> dict[str, Any]:
    """Read-only workspace diagnosis. Never creates or rewrites paths."""

    root = _resolved_root(Path(workspace_root))
    diagnostics: list[dict[str, str]] = []
    papers: list[dict[str, Any]] = []
    valid_loaded: list[dict[str, Any]] = []
    if not root.exists():
        return {
            "ok": True,
            "status": OK,
            "message": "workspace does not exist",
            "schema": SCHEMA,
            "workspace_root": str(root),
            "state": "empty",
            "index_state": "missing",
            "index_id": None,
            "papers": [],
            "diagnostics": [],
            "next_actions": ["Add a local PDF to create this workspace."],
        }

    diagnostics.extend(_scan_unexpected_papers(root))
    for directory in _paper_dirs(root):
        classified = classify_paper_dir(directory, directory.name)
        relative = f"papers/{directory.name}"
        kind = classified["kind"]
        if kind == "complete":
            loaded = classified["loaded"]
            papers.append(_paper_row(loaded))
            valid_loaded.append(loaded)
            continue
        if kind == "partial":
            diagnostics.append(_diagnostic(relative, "PAPER_PAIR_MISSING", classified.get("reason") or "paper pair is incomplete"))
        elif kind == "identity":
            diagnostics.append(_diagnostic(relative, SOURCE_INVALID, classified.get("reason") or "source identity does not match"))
        elif kind == "invalid":
            diagnostics.append(_diagnostic(relative, classified.get("code") or SOURCE_INVALID, classified.get("reason") or "paper is invalid"))
        else:
            diagnostics.append(_diagnostic(relative, "PAPER_UNEXPECTED_PATH", classified.get("reason") or "paper directory is unsafe"))

    index_state, index_id, index_diagnostics = _index_state(root, valid_loaded)
    diagnostics.extend(index_diagnostics)
    tx_diagnostics = _scan_transactions(root)
    diagnostics.extend(tx_diagnostics)
    diagnostics.extend(library_diagnostics(root))
    diagnostics.sort(key=lambda item: (item["relative_path"], item["code"], item["message"]))
    papers.sort(key=lambda item: item["paper_id"])
    pending = any(
        item["code"]
        in {
            "TRANSACTION_ACTIVE",
            "TRANSACTION_ABANDONED",
            "TRANSACTION_UNKNOWN",
            "LIBRARY_OPERATION_PENDING",
            "LIBRARY_STAGING_NONEMPTY",
            "LIBRARY_JOURNAL_FOREIGN",
        }
        for item in diagnostics
    )
    damage = any(
        item["code"]
        in {
            "PAPER_PAIR_MISSING",
            "PAPER_UNEXPECTED_PATH",
            "PAPER_SYMLINK",
            SOURCE_INVALID,
            "INDEX_INVALID",
        }
        or item.get("code") == "SOURCE_INVALID"
        for item in diagnostics
    )
    state = _state(damage=damage, pending=pending, paper_count=len(papers), index_state=index_state)
    return {
        "ok": True,
        "status": OK,
        "message": f"workspace state is {state}",
        "schema": SCHEMA,
        "workspace_root": str(root),
        "state": state,
        "index_state": index_state,
        "index_id": index_id,
        "papers": papers,
        "diagnostics": diagnostics,
        "next_actions": _next_actions(state, diagnostics, index_state),
    }
