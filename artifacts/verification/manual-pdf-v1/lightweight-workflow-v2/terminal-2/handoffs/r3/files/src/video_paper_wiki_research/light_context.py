"""Live evidence validation, shared paper selection, and atomic Markdown I/O."""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import (
    INDEX_DIRNAME,
    INDEX_STALE,
    LIGHT_SELECTION_INVALID,
    OK,
    _derived_chunks,
    _index_is_current,
    _load_index,
    _load_paper,
    _normalize_paper_ids,
    _paper_dirs,
    _sha256_bytes,
    _sha256_text,
    _snapshot_id,
    _workspace_paper_ids,
    search,
)
from video_paper_wiki_research.light_qa import (
    CONTEXT_SCHEMA,
    copy_evidence,
    export_qa_context,
    render_answer,
)
from video_paper_wiki_research.light_writing import export_writing_context, render_draft

LIGHT_CONTEXT_INVALID = "LIGHT_CONTEXT_INVALID"
LIGHT_OUTPUT_CONFLICT = "LIGHT_OUTPUT_CONFLICT"
LIGHT_WORKSPACE_MISMATCH = "LIGHT_WORKSPACE_MISMATCH"
SOURCE_INVALID = "SOURCE_INVALID"
WORKSPACE_INVALID = "WORKSPACE_INVALID"
KINDS = frozenset({"qa", "writing"})
EVIDENCE_IDENTITY_FIELDS = (
    "chunk_id",
    "paper_id",
    "title",
    "source_sha256",
    "page",
    "markdown_path",
    "markdown_sha256",
    "text_start",
    "text_end",
    "text_sha256",
    "text",
)
_MANAGED_ROOTS = frozenset({INDEX_DIRNAME, "papers", ".light-transactions", ".light-workflow"})
_MD_SOURCE_LINK = re.compile(r"\]\((?:<)?(papers/[0-9a-f]{64}/source\.md#page-\d+)(?:>)?\)")
_TICK_SOURCE_LINK = re.compile(r"`(papers/[0-9a-f]{64}/source\.md#page-\d+)`")
_OUTPUT_TMP_SUFFIX = ".light-out.tmp"


def _fail(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "status": status,
        "message": message,
        "markdown": "",
        "citations": [],
    }
    payload.update(extra)
    return payload


def _require_workspace(workspace_root: Path) -> Path:
    if not isinstance(workspace_root, Path):
        workspace_root = Path(workspace_root)
    if workspace_root.is_symlink() or not workspace_root.is_dir():
        raise ResearchError(WORKSPACE_INVALID, "workspace_root must be a regular directory")
    return workspace_root.resolve()


def _load_live_papers(workspace_root: Path) -> list[dict[str, Any]]:
    return [_load_paper(directory) for directory in _paper_dirs(workspace_root)]


def _normalize_selection(paper_ids: object) -> tuple[list[str] | None, str | None]:
    return _normalize_paper_ids(paper_ids)


def _selection_payload(
    *,
    kind: str,
    query: str,
    requirements: str,
    workspace: Path,
    index_id: object,
    message: str,
) -> dict[str, Any]:
    return _fail(
        LIGHT_SELECTION_INVALID,
        message,
        schema=CONTEXT_SCHEMA,
        kind=kind,
        query=query,
        requirements=requirements,
        paper_ids=[],
        selected_paper_ids=[],
        index_id=index_id,
        workspace_root=str(workspace),
        evidence=[],
        prompt="",
    )


def _attach_export_fields(payload: dict[str, Any], *, workspace: Path, selected: list[str]) -> dict[str, Any]:
    result = dict(payload)
    result["workspace_root"] = str(workspace)
    result["selected_paper_ids"] = list(selected)
    result.setdefault("markdown", "")
    result.setdefault("citations", [])
    return result


def export_context(
    workspace_root: Path,
    *,
    kind: str,
    query: str,
    requirements: str = "",
    paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search the live index and export a kind-specific light-context.v1 document."""
    workspace = _require_workspace(workspace_root)
    if type(kind) is not str or kind not in KINDS:
        raise ResearchError(LIGHT_CONTEXT_INVALID, "kind must be exactly qa or writing")
    if type(query) is not str:
        raise ResearchError("QUERY_INVALID", "query must be a string")
    if type(requirements) is not str:
        raise ResearchError("QUERY_INVALID", "requirements must be a string")
    selected, selection_error = _normalize_selection(paper_ids)
    stored = _load_index(workspace)
    index_id = stored.get("index_id") if type(stored) is dict else None
    if selection_error is not None:
        return _selection_payload(
            kind=kind,
            query=query,
            requirements=requirements,
            workspace=workspace,
            index_id=index_id,
            message=selection_error,
        )
    assert selected is not None
    present = _workspace_paper_ids(workspace)
    if selected and any(item not in present for item in selected):
        return _selection_payload(
            kind=kind,
            query=query,
            requirements=requirements,
            workspace=workspace,
            index_id=index_id,
            message="selected paper_id is not present in the current workspace",
        )
    retrieval = search(workspace, query, paper_ids=selected or None)
    if kind == "qa":
        exported = export_qa_context(query, retrieval)
    else:
        exported = export_writing_context(query, requirements, selected, retrieval)
    return _attach_export_fields(exported, workspace=workspace, selected=selected)


def _context_workspace_mismatch(context: Mapping[str, Any], workspace: Path) -> bool:
    stored = context.get("workspace_root")
    if stored is None:
        return False
    if type(stored) is not str or not stored.strip():
        return True
    try:
        return Path(stored).expanduser().resolve() != workspace
    except (OSError, RuntimeError):
        return True


def _derived_by_chunk(papers: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
    derived = _derived_chunks(papers)
    by_id: dict[str, dict[str, Any]] = {}
    for chunk in derived:
        chunk_id = chunk["chunk_id"]
        if chunk_id in by_id:
            return None
        by_id[chunk_id] = chunk
    return by_id


def _evidence_matches_chunk(row: Mapping[str, Any], chunk: Mapping[str, Any]) -> bool:
    for field in EVIDENCE_IDENTITY_FIELDS:
        if row.get(field) != chunk.get(field):
            return False
    return True


def _successful_context_shape(context: Mapping[str, Any], workspace: Path) -> dict[str, Any] | None:
    kind = context.get("kind")
    if type(kind) is not str or kind not in KINDS:
        return _fail(LIGHT_CONTEXT_INVALID, "context kind must be qa or writing", workspace_root=str(workspace))
    if type(context.get("query")) is not str:
        return _fail(LIGHT_CONTEXT_INVALID, "query must be a string", workspace_root=str(workspace))
    if type(context.get("requirements")) is not str:
        return _fail(LIGHT_CONTEXT_INVALID, "requirements must be a string", workspace_root=str(workspace))
    paper_ids = context.get("paper_ids")
    if type(paper_ids) is not list or any(type(item) is not str for item in paper_ids):
        return _fail(LIGHT_CONTEXT_INVALID, "paper_ids must be a list of strings", workspace_root=str(workspace))
    if type(context.get("index_id")) is not str or not context.get("index_id"):
        return _fail(LIGHT_CONTEXT_INVALID, "index_id must be a nonempty string", workspace_root=str(workspace))
    evidence = context.get("evidence")
    if type(evidence) is not list:
        return _fail(LIGHT_CONTEXT_INVALID, "evidence must be a list", workspace_root=str(workspace))
    if not evidence:
        return _fail(LIGHT_CONTEXT_INVALID, "successful context must contain evidence", workspace_root=str(workspace))
    if type(context.get("prompt")) is not str:
        return _fail(LIGHT_CONTEXT_INVALID, "prompt must be a string", workspace_root=str(workspace))
    return None


def validate_live_context(workspace_root: Path, context: object) -> dict[str, Any]:
    """Read-only check that a context still matches the live source/index snapshot."""
    workspace = _require_workspace(workspace_root)
    if type(context) is not dict:
        return _fail(LIGHT_CONTEXT_INVALID, "context must be an object", workspace_root=str(workspace))
    if _context_workspace_mismatch(context, workspace):
        return _fail(
            LIGHT_WORKSPACE_MISMATCH,
            "context workspace_root does not match the explicit workspace",
            workspace_root=str(workspace),
        )
    if context.get("schema") != CONTEXT_SCHEMA:
        return _fail(LIGHT_CONTEXT_INVALID, "context schema must be light-context.v1", workspace_root=str(workspace))
    if context.get("ok") is not True or context.get("status") != OK:
        return _fail(LIGHT_CONTEXT_INVALID, "context is not a successful export", workspace_root=str(workspace))
    shaped = _successful_context_shape(context, workspace)
    if shaped is not None:
        return shaped
    try:
        papers = _load_live_papers(workspace)
    except ResearchError as exc:
        if exc.code == SOURCE_INVALID:
            return _fail(SOURCE_INVALID, exc.message, workspace_root=str(workspace))
        raise
    stored = _load_index(workspace)
    try:
        index_current = stored is not None and _index_is_current(stored, papers)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        index_current = False
    if stored is None or not index_current:
        return _fail(
            INDEX_STALE,
            "workspace Markdown or paper set disagrees with the stored index",
            workspace_root=str(workspace),
            index_id=None if stored is None else stored.get("index_id") if type(stored) is dict else None,
        )
    current_id = stored.get("index_id")
    if type(current_id) is not str or context.get("index_id") != current_id:
        return _fail(
            INDEX_STALE,
            "context index_id is not the current source snapshot",
            workspace_root=str(workspace),
            index_id=current_id,
        )
    if current_id != _snapshot_id(papers):
        return _fail(
            INDEX_STALE,
            "workspace Markdown or paper set disagrees with the stored index",
            workspace_root=str(workspace),
            index_id=current_id,
        )
    present = {paper["paper_id"] for paper in papers}
    if "selected_paper_ids" in context:
        selected, selection_error = _normalize_selection(context.get("selected_paper_ids"))
        if selection_error is not None or selected is None:
            return _fail(
                LIGHT_SELECTION_INVALID,
                selection_error or "selected_paper_ids is invalid",
                workspace_root=str(workspace),
                index_id=current_id,
            )
        if selected and any(item not in present for item in selected):
            return _fail(
                LIGHT_SELECTION_INVALID,
                "selected paper_id is not present in the current workspace",
                workspace_root=str(workspace),
                index_id=current_id,
            )
    else:
        selected = []
    try:
        evidence = copy_evidence(context["evidence"])
    except ResearchError:
        return _fail(
            LIGHT_CONTEXT_INVALID,
            "evidence rows are malformed",
            workspace_root=str(workspace),
            index_id=current_id,
        )
    derived = _derived_by_chunk(papers)
    if derived is None:
        return _fail(
            INDEX_STALE,
            "workspace Markdown or paper set disagrees with the stored index",
            workspace_root=str(workspace),
            index_id=current_id,
        )
    allowed_papers = set(selected) if selected else present
    for row in evidence:
        chunk = derived.get(row["chunk_id"])
        if chunk is None or not _evidence_matches_chunk(row, chunk):
            return _fail(
                LIGHT_CONTEXT_INVALID,
                "evidence row does not match a current derived source chunk",
                workspace_root=str(workspace),
                index_id=current_id,
            )
        if row["paper_id"] not in allowed_papers:
            return _fail(
                LIGHT_CONTEXT_INVALID,
                "evidence row is outside the selected papers",
                workspace_root=str(workspace),
                index_id=current_id,
            )
        live_text = chunk["text"]
        paper = next(item for item in papers if item["paper_id"] == chunk["paper_id"])
        slice_text = paper["markdown"][chunk["text_start"] : chunk["text_end"]]
        if row["text"] != live_text or live_text != slice_text or _sha256_text(slice_text) != row["text_sha256"]:
            return _fail(
                LIGHT_CONTEXT_INVALID,
                "evidence text is not the current source Unicode slice",
                workspace_root=str(workspace),
                index_id=current_id,
            )
    return {
        "ok": True,
        "status": OK,
        "index_id": current_id,
        "workspace_root": str(workspace),
        "message": "context matches the current source and index snapshot",
    }


def _resolve_output(output: Path) -> Path:
    if not isinstance(output, Path):
        output = Path(output)
    output = output.expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    return output


def _symlink_in_parents(path: Path) -> bool:
    current = path.parent
    seen: set[Path] = set()
    while current not in seen:
        seen.add(current)
        if current.exists() and current.is_symlink():
            return True
        if current.parent == current:
            break
        current = current.parent
    return False


def _managed_target(output: Path, workspace: Path) -> bool:
    try:
        relative = output.resolve().relative_to(workspace)
    except ValueError:
        return False
    parts = relative.parts
    if not parts:
        return True
    return parts[0] in _MANAGED_ROOTS


def _output_conflict(message: str, **extra: Any) -> dict[str, Any]:
    return _fail(LIGHT_OUTPUT_CONFLICT, message, **extra)


def _prepare_output_path(output: Path, workspace: Path, *, overwrite: bool) -> tuple[Path, dict[str, Any] | None]:
    given = _resolve_output(output)
    if given.name in {"", ".", ".."}:
        return given, _output_conflict("output must be a Markdown file path", path=str(given))
    if given.is_symlink():
        return given, _output_conflict("output target must be a regular file", path=str(given))
    if given.exists() and given.is_dir():
        return given, _output_conflict("output must be a Markdown file path", path=str(given))
    if _symlink_in_parents(given):
        raise ResearchError(WORKSPACE_INVALID, "output parent path must not traverse a symlink", {"path": str(given)})
    candidate = given.parent.resolve() / given.name
    if _managed_target(candidate, workspace):
        raise ResearchError(
            WORKSPACE_INVALID,
            "output must not alias workspace papers, index, or session state",
            {"path": str(candidate)},
        )
    if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
        return candidate, _output_conflict("output target must be a regular file", path=str(candidate))
    if not overwrite and (candidate.exists() or candidate.is_symlink()):
        return candidate, _output_conflict("output already exists", path=str(candidate))
    return candidate, None


def _display_source_href(workspace_href: str, *, workspace: Path, output_parent: Path) -> str:
    relative, anchor = workspace_href.split("#", 1)
    source = (workspace / relative).resolve()
    display = Path(os.path.relpath(source, output_parent)).as_posix()
    return f"{display}#{anchor}"


def rewrite_markdown_links(markdown: str, *, workspace: Path, output: Path) -> str:
    output_parent = output.parent

    def as_href(workspace_href: str) -> str:
        return _display_source_href(workspace_href, workspace=workspace, output_parent=output_parent)

    def link_sub(match: re.Match[str]) -> str:
        href = as_href(match.group(1))
        if any(ch in href for ch in " ()"):
            return f"](<{href}>)"
        return f"]({href})"

    rewritten = _MD_SOURCE_LINK.sub(link_sub, markdown)
    rewritten = _TICK_SOURCE_LINK.sub(lambda match: f"`{as_href(match.group(1))}`", rewritten)
    return rewritten


def _render_kind(context: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    if context.get("kind") == "writing":
        return render_draft(context, document)
    return render_answer(context, document)


def render_document(workspace_root: Path, context: object, document: object, *, output: Path) -> dict[str, Any]:
    """Validate live context and return prospective Markdown bytes without writing."""
    workspace = _require_workspace(workspace_root)
    resolved, conflict = _prepare_output_path(output, workspace, overwrite=True)
    if conflict is not None:
        return conflict
    live = validate_live_context(workspace, context)
    if live.get("ok") is not True:
        return live
    if type(document) is not dict:
        raise ResearchError(LIGHT_CONTEXT_INVALID, "document must be an object")
    if type(context) is not dict:
        return _fail(LIGHT_CONTEXT_INVALID, "context must be an object", workspace_root=str(workspace))
    rendered = _render_kind(context, document)
    if rendered.get("ok") is not True:
        payload = dict(rendered)
        payload.setdefault("markdown", "")
        payload.setdefault("citations", [])
        payload["workspace_root"] = str(workspace)
        payload["index_id"] = live.get("index_id")
        return payload
    markdown = rewrite_markdown_links(str(rendered.get("markdown") or ""), workspace=workspace, output=resolved)
    encoded = markdown.encode("utf-8")
    result = dict(rendered)
    result["markdown"] = markdown
    result["path"] = str(resolved)
    result["output_sha256"] = _sha256_bytes(encoded)
    result["workspace_root"] = str(workspace)
    result["index_id"] = live.get("index_id")
    return result


def _owned_tmp(output: Path) -> Path:
    token = secrets.token_hex(8)
    return output.with_name(f".{output.name}.{token}{_OUTPUT_TMP_SUFFIX}")


def _cleanup_tmp(path: Path) -> None:
    try:
        if path.is_file() and path.name.endswith(_OUTPUT_TMP_SUFFIX) and not path.is_symlink():
            path.unlink()
    except OSError:
        return


def _abandon_stage(tmp: Path | None, parent: Path, created_parent: bool) -> None:
    if tmp is not None:
        _cleanup_tmp(tmp)
    if created_parent:
        try:
            parent.rmdir()
        except OSError:
            pass


def _stage_output_bytes(output: Path, data: bytes) -> tuple[Path | None, bool, dict[str, Any] | None]:
    tmp = _owned_tmp(output)
    parent = output.parent
    created_parent = False
    try:
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
            created_parent = True
        elif parent.is_symlink() or not parent.is_dir():
            return None, False, _output_conflict("output parent is not a regular directory", path=str(output))
        tmp.write_bytes(data)
    except OSError as exc:
        _abandon_stage(tmp, parent, created_parent)
        return None, False, _output_conflict(f"cannot install output: {exc}", path=str(output))
    return tmp, created_parent, None


def _commit_staged_output(tmp: Path, output: Path, *, overwrite: bool) -> dict[str, Any] | None:
    try:
        if overwrite:
            os.replace(tmp, output)
        else:
            try:
                os.link(tmp, output)
            except FileExistsError:
                _cleanup_tmp(tmp)
                return _output_conflict("output already exists", path=str(output))
            _cleanup_tmp(tmp)
    except OSError as exc:
        _cleanup_tmp(tmp)
        return _output_conflict(f"cannot install output: {exc}", path=str(output))
    return None


def import_document(
    workspace_root: Path,
    context: object,
    document: object,
    *,
    output: Path,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Render, revalidate, and atomically install Markdown."""
    if type(overwrite) is not bool:
        raise ResearchError(LIGHT_CONTEXT_INVALID, "overwrite must be a boolean")
    workspace = _require_workspace(workspace_root)
    resolved, conflict = _prepare_output_path(output, workspace, overwrite=overwrite)
    if conflict is not None:
        return conflict
    rendered = render_document(workspace, context, document, output=resolved)
    if rendered.get("ok") is not True:
        return rendered
    live = validate_live_context(workspace, context)
    if live.get("ok") is not True:
        return live
    encoded = str(rendered["markdown"]).encode("utf-8")
    if _sha256_bytes(encoded) != rendered.get("output_sha256"):
        return _fail(LIGHT_CONTEXT_INVALID, "rendered Markdown changed before install", workspace_root=str(workspace))
    tmp, created_parent, staged_fail = _stage_output_bytes(resolved, encoded)
    if staged_fail is not None:
        return staged_fail
    assert tmp is not None
    live = validate_live_context(workspace, context)
    if live.get("ok") is not True:
        _abandon_stage(tmp, resolved.parent, created_parent)
        return live
    failed = _commit_staged_output(tmp, resolved, overwrite=overwrite)
    if failed is not None:
        _abandon_stage(tmp, resolved.parent, created_parent)
        return failed
    result = dict(rendered)
    result["path"] = str(resolved)
    result["output_sha256"] = _sha256_bytes(encoded)
    result["workspace_root"] = str(workspace)
    result["index_id"] = live.get("index_id")
    return result
