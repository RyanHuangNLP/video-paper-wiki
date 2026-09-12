"""Cited structured knowledge records and versioned concept views."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    LIGHT_CONTEXT_INVALID,
    SOURCE_INVALID,
    WORKSPACE_INVALID,
    rewrite_markdown_links,
    validate_live_context,
)
from video_paper_wiki_research.light_index import (
    INDEX_STALE,
    LIGHT_SELECTION_INVALID,
    OK,
    PAPER_ID_PATTERN,
    _derived_chunks,
    _index_is_current,
    _load_index,
    _load_paper,
    _paper_dirs,
    _workspace_paper_ids,
)
from video_paper_wiki_research.light_qa import (
    CONTEXT_SCHEMA,
    INSUFFICIENT_EVIDENCE,
    _CITE_MARK,
    _anchor,
    _readable_mark,
    copy_evidence,
    render_markdown,
)
from video_paper_wiki_research.light_workflow import (
    LIGHT_WORKSPACE_BUSY,
    _Busy,
    _exclusive_lock,
    _workspace_lock_path,
)
from video_paper_wiki_research.light_writing import export_writing_context

LIGHT_KNOWLEDGE_INVALID = "LIGHT_KNOWLEDGE_INVALID"
LIGHT_KNOWLEDGE_CONFLICT = "LIGHT_KNOWLEDGE_CONFLICT"
KNOWLEDGE_CONTEXT_SCHEMA = "video-paper-wiki.light-knowledge-context.v1"
KNOWLEDGE_DOCUMENT_SCHEMA = "video-paper-wiki.light-knowledge-document.v1"
RECORD_SCHEMA = "video-paper-wiki.light-knowledge-record.v1"
HEADS_SCHEMA = "video-paper-wiki.light-knowledge-heads.v1"
VIEW_SCHEMA = "video-paper-wiki.light-knowledge-view.v1"
CURRENT_SCHEMA = "video-paper-wiki.light-knowledge-current.v1"
OWNERSHIP_SCHEMA = "video-paper-wiki.light-knowledge-ownership.v1"
IDENTITY_SCHEMA = "video-paper-wiki.light-knowledge-identity.v1"

KNOWLEDGE_STATE_DIR = ".light-knowledge"
RECORDS_DIRNAME = "records"
STAGING_DIRNAME = "staging"
HEADS_NAME = "HEADS.json"
VIEWS_ROOT = "knowledge"
VIEWS_DIRNAME = "views"
CURRENT_NAME = "CURRENT.json"
NOTES_NAME = "notes.md"
OWNERSHIP_NAME = "ownership.json"
PAYLOAD_DIRNAME = "payload"
DOCUMENT_NAME = "document.json"
CONTEXT_NAME = "context.json"
IDENTITY_NAME = "identity.json"
MANIFEST_NAME = "manifest.json"
KNOWLEDGE_PAGE_NAME = "knowledge.md"
INDEX_PAGE_NAME = "index.md"

SECTION_KEYS = (
    "summary",
    "method",
    "architecture",
    "training_data",
    "experiments",
    "limitations",
    "code_resources",
    "open_questions",
)
SECTION_TITLES = {
    "summary": "摘要",
    "method": "方法",
    "architecture": "架构",
    "training_data": "训练与数据",
    "experiments": "实验",
    "limitations": "局限",
    "code_resources": "代码与资源",
    "open_questions": "开放问题",
}
UNKNOWN_TEXT = "证据不足"
STATUS_PROVISIONAL = "provisional"
STATUS_UNKNOWN = "unknown"
MAX_EXPORT_CHUNKS = 48
MAX_EXPORT_CHARS = 80_000
MAX_SECTION_TEXT = 8_000
MAX_CITATIONS = 32
MAX_CONCEPTS = 20
MAX_CONCEPT_NAME = 120
HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

KNOWLEDGE_PROMPT = (
    "Using only the provided evidence chunks, author one "
    "video-paper-wiki.light-knowledge-document.v1 object for this paper. "
    "sections must be an object with exactly the keys summary, method, architecture, "
    "training_data, experiments, limitations, code_resources, open_questions. "
    "Each section has status provisional or unknown, text, and citations as chunk_id strings. "
    "Provisional text must be nonblank (max 8000 characters) with at least one citation "
    "owned by the selected paper. unknown text must be exactly 证据不足 with no citations. "
    "Do not put [@chunk_id] marks in text; the importer appends marks from citations. "
    "concepts is at most 20 objects with name and nonempty citations bound to this paper. "
    "At least one section must be provisional. Do not invent papers, pages, chunk ids, or facts."
)
KNOWLEDGE_REQUIREMENTS = (
    "Return video-paper-wiki.light-knowledge-document.v1 using only provided evidence."
)
RECORD_PAYLOAD = (DOCUMENT_NAME, CONTEXT_NAME, IDENTITY_NAME, MANIFEST_NAME, KNOWLEDGE_PAGE_NAME)


def _raise(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _closed(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": status, "message": message}
    payload.update(extra)
    return payload


def _reject_nonfinite(value: object) -> None:
    if type(value) is float and not math.isfinite(value):
        _raise(LIGHT_KNOWLEDGE_INVALID, "knowledge JSON cannot contain nonfinite numbers")
    if type(value) is dict:
        for item in value.values():
            _reject_nonfinite(item)
        return
    if type(value) is list:
        for item in value:
            _reject_nonfinite(item)


def canonical_bytes(value: object) -> bytes:
    _reject_nonfinite(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _raise(LIGHT_KNOWLEDGE_INVALID, "knowledge JSON is not canonicalizable")
        raise AssertionError("unreachable") from exc


def persisted_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def _is_regular_dir(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_dir()


def _is_regular_file(path: Path) -> bool:
    return (not path.is_symlink()) and path.is_file()


def _symlink_in_chain(path: Path) -> bool:
    cursor = path
    seen: set[Path] = set()
    while cursor not in seen:
        seen.add(cursor)
        try:
            if cursor.is_symlink():
                return True
        except OSError:
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent
    return True


def _as_path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        return value
    if type(value) is str:
        return Path(value)
    _raise(WORKSPACE_INVALID, f"{name} must be a Path")
    raise AssertionError("unreachable")


def _absolute_path(value: object, name: str) -> Path:
    path = _as_path(value, name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.normpath(path))


def require_product_workspace(workspace_root: object) -> Path:
    """Require an existing regular workspace whose given and resolved paths contain .work."""
    given = _absolute_path(workspace_root, "workspace_root")
    if ".work" not in given.parts:
        _raise(WORKSPACE_INVALID, "workspace must be under .work/**", {"path": str(given)})
    if _symlink_in_chain(given) or given.is_symlink():
        _raise(WORKSPACE_INVALID, "workspace path must not traverse a symlink", {"path": str(given)})
    if not given.exists() or not _is_regular_dir(given):
        _raise(WORKSPACE_INVALID, "workspace_root must be a regular directory under .work/**", {"path": str(given)})
    resolved = given.resolve()
    if ".work" not in resolved.parts:
        _raise(WORKSPACE_INVALID, "workspace must be under .work/**", {"path": str(resolved)})
    if resolved.is_symlink() or not _is_regular_dir(resolved):
        _raise(
            WORKSPACE_INVALID,
            "workspace_root must be a regular directory under .work/**",
            {"path": str(resolved)},
        )
    return resolved


def require_work_output(output: object, *, suffix: str = ".md", code: str = LIGHT_KNOWLEDGE_INVALID) -> Path:
    given = _absolute_path(output, "output")
    if given.suffix != suffix or given.name in {"", ".", ".."}:
        _raise(code, f"output must be a {suffix} file path", {"path": str(given)})
    if ".work" not in given.parts:
        _raise(WORKSPACE_INVALID, "output must be under .work/**", {"path": str(given)})
    if _symlink_in_chain(given):
        _raise(WORKSPACE_INVALID, "output path must not traverse a symlink", {"path": str(given)})
    resolved = given.parent.resolve() / given.name if given.parent.exists() else given
    if given.parent.exists():
        if _symlink_in_chain(given.parent) or given.parent.is_symlink():
            _raise(WORKSPACE_INVALID, "output path must not traverse a symlink", {"path": str(given)})
        resolved = given.parent.resolve() / given.name
    if ".work" not in resolved.parts:
        _raise(WORKSPACE_INVALID, "output must be under .work/**", {"path": str(resolved)})
    return given


def _hardlinked(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_nlink > 1
    except OSError:
        return True


def _require_safe_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file() or _hardlinked(path):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, f"{label} is not a safe regular file", {"path": str(path)})


def require_paper_id(paper_id: object, *, code: str = LIGHT_KNOWLEDGE_INVALID) -> str:
    if type(paper_id) is not str or not PAPER_ID_PATTERN.fullmatch(paper_id):
        _raise(code, "paper_id must be sha256:<64 lowercase hex>")
    return paper_id


def _paper_digest(paper_id: str) -> str:
    return paper_id.split(":", 1)[1]


def _has_cite_marks(text: str) -> bool:
    return _CITE_MARK.search(text) is not None


def escape_md(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("`", "\\`")
        .replace("#", "\\#")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )
    return escaped.replace("\r\n", "\n").replace("\r", "\n")


def escape_table_cell(text: str) -> str:
    return escape_md(text).replace("\n", "<br>")


def normalize_concept_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).strip().casefold()


def display_concept_name(name: str) -> str:
    return unicodedata.normalize("NFC", name).strip()


def _control_in(text: str) -> bool:
    if _CONTROL.search(text):
        return True
    return any(unicodedata.category(char).startswith("C") for char in text)


@contextmanager
def workspace_lock(workspace: Path) -> Iterator[None]:
    try:
        with _exclusive_lock(_workspace_lock_path(workspace), workspace):
            yield
    except _Busy as exc:
        raise ResearchError(LIGHT_WORKSPACE_BUSY, "workspace is busy") from exc


def _unsafe_source_reason(directory: Path) -> str | None:
    if directory.is_symlink() or not directory.is_dir() or _symlink_in_chain(directory):
        return "paper directory must be a regular path without symlink traversal"
    for name in ("source.json", "source.md"):
        path = directory / name
        if path.is_symlink() or not path.is_file() or _hardlinked(path) or _symlink_in_chain(path):
            return "source.md and source.json must be regular non-hardlinked files"
    return None


def _load_live_papers(workspace: Path) -> list[dict[str, Any]] | dict[str, Any]:
    try:
        loaded: list[dict[str, Any]] = []
        for directory in _paper_dirs(workspace):
            reason = _unsafe_source_reason(directory)
            if reason is not None:
                return _closed(SOURCE_INVALID, reason)
            loaded.append(_load_paper(directory))
        return loaded
    except ResearchError as exc:
        if exc.code == SOURCE_INVALID:
            return _closed(SOURCE_INVALID, exc.message)
        raise
    except UnicodeError:
        return _closed(SOURCE_INVALID, "source.md is not valid UTF-8")
    except OSError as exc:
        return _closed(SOURCE_INVALID, f"cannot read live paper source: {exc}")


def _require_current_index(workspace: Path) -> dict[str, Any] | tuple[dict[str, Any], list[dict[str, Any]]]:
    stored = _load_index(workspace)
    papers = _load_live_papers(workspace)
    if type(papers) is dict:
        return papers
    if stored is None or not _index_is_current(stored, papers):
        index_id = None if stored is None else stored.get("index_id") if type(stored) is dict else None
        return _closed(
            INDEX_STALE,
            "workspace Markdown or paper set disagrees with the stored index",
            index_id=index_id,
        )
    return stored, papers


def _paper_by_id(papers: list[dict[str, Any]], paper_id: str) -> dict[str, Any] | None:
    for paper in papers:
        if paper["paper_id"] == paper_id:
            return paper
    return None


def _page_spread_select(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int], bool]:
    if not chunks:
        return [], [], False
    by_page: dict[int, list[dict[str, Any]]] = {}
    for chunk in chunks:
        by_page.setdefault(int(chunk["page"]), []).append(chunk)
    pages = sorted(by_page)
    cursors = {page: 0 for page in pages}
    selected: list[dict[str, Any]] = []
    used = 0
    omitted_budget = False
    while len(selected) < MAX_EXPORT_CHUNKS and any(cursors[page] < len(by_page[page]) for page in pages):
        progressed = False
        for page in pages:
            if len(selected) >= MAX_EXPORT_CHUNKS:
                break
            index = cursors[page]
            if index >= len(by_page[page]):
                continue
            chunk = by_page[page][index]
            cursors[page] += 1
            progressed = True
            length = len(chunk["text"])
            if used + length > MAX_EXPORT_CHARS:
                omitted_budget = True
                continue
            selected.append(chunk)
            used += length
        if not progressed:
            break
    remaining = any(cursors[page] < len(by_page[page]) for page in pages)
    truncated = remaining or omitted_budget or len(selected) < len(chunks)
    exported_pages = {int(item["page"]) for item in selected}
    omitted_pages = [page for page in pages if page not in exported_pages]
    return selected, omitted_pages, truncated


def _evidence_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunks:
        rows.append(
            {
                "chunk_id": chunk["chunk_id"],
                "paper_id": chunk["paper_id"],
                "title": chunk["title"],
                "source_sha256": chunk["source_sha256"],
                "page": chunk["page"],
                "markdown_path": chunk["markdown_path"],
                "markdown_sha256": chunk["markdown_sha256"],
                "text_start": chunk["text_start"],
                "text_end": chunk["text_end"],
                "text_sha256": chunk["text_sha256"],
                "text": chunk["text"],
                "score": 1.0,
            }
        )
    return rows


def _attach_context(exported: dict[str, Any], workspace: Path, selected: list[str]) -> dict[str, Any]:
    result = dict(exported)
    result["workspace_root"] = str(workspace)
    result["selected_paper_ids"] = list(selected)
    return result


def _writing_context(
    *,
    workspace: Path,
    query: str,
    requirements: str,
    paper_ids: list[str],
    evidence: list[dict[str, Any]],
    index_id: str,
    prompt: str,
) -> dict[str, Any]:
    retrieval = {
        "ok": True,
        "status": OK,
        "query": query,
        "index_id": index_id,
        "evidence": evidence,
        "message": "derived evidence for the current conversation model",
    }
    exported = export_writing_context(query, requirements, paper_ids, retrieval)
    attached = _attach_context(exported, workspace, paper_ids)
    if attached.get("ok") is True:
        attached["prompt"] = prompt
    return attached


def _coverage_payload(
    *,
    total_chunks: int,
    exported_chunks: int,
    omitted_pages: list[int],
    truncated: bool,
) -> dict[str, Any]:
    return {
        "exported_chunks": exported_chunks,
        "omitted_pages": list(omitted_pages),
        "total_chunks": total_chunks,
        "truncated": bool(truncated),
    }


def _paper_snapshot(paper: Mapping[str, Any]) -> dict[str, str]:
    return {
        "markdown_sha256": str(paper["markdown_sha256"]),
        "paper_id": str(paper["paper_id"]),
        "source_json_sha256": str(paper["source_json_sha256"]),
    }


_KNOWLEDGE_WRAPPER_TYPES = {
    "context": dict,
    "coverage": dict,
    "paper_id": str,
    "paper_snapshot": dict,
    "prompt": str,
    "schema": str,
}


def _closed_missing_wrapper(code: str, field: str) -> dict[str, Any]:
    return _closed(code, f"context wrapper is missing required field {field}")


def _require_typed_fields(
    payload: Mapping[str, Any],
    required: Mapping[str, type],
    *,
    code: str,
) -> dict[str, Any] | None:
    for field, expected in required.items():
        if field not in payload:
            return _closed_missing_wrapper(code, field)
        if type(payload[field]) is not expected:
            return _closed(code, f"context wrapper field {field} is invalid")
    return None


def _wrapper_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    shaped = _require_typed_fields(payload, _KNOWLEDGE_WRAPPER_TYPES, code=LIGHT_KNOWLEDGE_INVALID)
    if shaped is not None:
        raise ResearchError(LIGHT_KNOWLEDGE_INVALID, str(shaped["message"]))
    return {
        "context": payload["context"],
        "coverage": payload["coverage"],
        "paper_id": payload["paper_id"],
        "paper_snapshot": payload["paper_snapshot"],
        "prompt": payload["prompt"],
        "schema": payload["schema"],
    }


def _export_knowledge_unlocked(workspace: Path, paper_id: str) -> dict[str, Any]:
    loaded = _require_current_index(workspace)
    if type(loaded) is dict:
        loaded.setdefault("paper_id", paper_id)
        loaded.setdefault("schema", KNOWLEDGE_CONTEXT_SCHEMA)
        return loaded
    stored, papers = loaded
    present = {paper["paper_id"] for paper in papers}
    if paper_id not in present or paper_id not in _workspace_paper_ids(workspace):
        return _closed(
            LIGHT_SELECTION_INVALID,
            "selected paper_id is not present in the current workspace",
            paper_id=paper_id,
            schema=KNOWLEDGE_CONTEXT_SCHEMA,
        )
    paper = _paper_by_id(papers, paper_id)
    assert paper is not None
    derived = [item for item in _derived_chunks(papers) if item["paper_id"] == paper_id]
    selected, omitted_pages, truncated = _page_spread_select(derived)
    if not selected:
        return _closed(
            INSUFFICIENT_EVIDENCE,
            "no evidence is available for the current model",
            paper_id=paper_id,
            schema=KNOWLEDGE_CONTEXT_SCHEMA,
            coverage=_coverage_payload(
                total_chunks=len(derived),
                exported_chunks=0,
                omitted_pages=omitted_pages,
                truncated=truncated or bool(derived),
            ),
        )
    query = paper["title"] if type(paper.get("title")) is str and paper["title"].strip() else paper_id
    context = _writing_context(
        workspace=workspace,
        query=query,
        requirements=KNOWLEDGE_REQUIREMENTS,
        paper_ids=[paper_id],
        evidence=_evidence_from_chunks(selected),
        index_id=str(stored["index_id"]),
        prompt=KNOWLEDGE_PROMPT,
    )
    if context.get("ok") is not True:
        payload = dict(context)
        payload["schema"] = KNOWLEDGE_CONTEXT_SCHEMA
        payload["paper_id"] = paper_id
        return payload
    live = validate_live_context(workspace, context)
    if live.get("ok") is not True:
        return live
    coverage = _coverage_payload(
        total_chunks=len(derived),
        exported_chunks=len(selected),
        omitted_pages=omitted_pages,
        truncated=truncated,
    )
    snapshot = _paper_snapshot(paper)
    wrapper = {
        "ok": True,
        "status": OK,
        "message": "exported structured knowledge context for the current conversation model",
        "schema": KNOWLEDGE_CONTEXT_SCHEMA,
        "paper_id": paper_id,
        "context": context,
        "coverage": coverage,
        "paper_snapshot": snapshot,
        "prompt": KNOWLEDGE_PROMPT,
    }
    wrapper["context_sha256"] = sha256_canonical(context)
    return wrapper


def export_knowledge_context(workspace_root: Path, *, paper_id: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    ident = require_paper_id(paper_id)
    return _export_knowledge_unlocked(workspace, ident)


def _validate_citation_ids(
    raw: object,
    *,
    evidence_ids: set[str],
    paper_id: str,
    by_chunk: Mapping[str, Mapping[str, Any]],
    code: str = LIGHT_KNOWLEDGE_INVALID,
) -> list[str]:
    if type(raw) is not list:
        _raise(code, "citations must be a list of chunk_id strings")
    if len(raw) > MAX_CITATIONS:
        _raise(code, "citations must contain at most 32 chunk ids")
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if type(item) is not str or not item:
            _raise(code, "citation chunk_id must be a nonempty string")
        if item in seen:
            _raise(code, "citation chunk_id is duplicated")
        if item not in evidence_ids:
            _raise(code, "citation chunk_id is not in the provided evidence")
        owner = by_chunk[item].get("paper_id")
        if owner != paper_id:
            _raise(code, "citation chunk_id is not owned by the selected paper")
        seen.add(item)
        result.append(item)
    return result


def validate_cited_block(
    block: object,
    *,
    evidence_ids: set[str],
    paper_id: str,
    by_chunk: Mapping[str, Mapping[str, Any]],
    extra_keys: frozenset[str] = frozenset(),
    code: str = LIGHT_KNOWLEDGE_INVALID,
) -> dict[str, Any]:
    if type(block) is not dict:
        _raise(code, "cited block must be an object")
    allowed = {"status", "text", "citations"} | set(extra_keys)
    extra = set(block) - allowed
    if extra:
        _raise(code, "cited block has unknown fields")
    missing = {"status", "text", "citations"} - set(block)
    if missing:
        _raise(code, "cited block is missing required fields")
    status = block.get("status")
    text = block.get("text")
    if status not in {STATUS_PROVISIONAL, STATUS_UNKNOWN}:
        _raise(code, "status must be provisional or unknown")
    if type(text) is not str:
        _raise(code, "text must be a string")
    if _has_cite_marks(text):
        _raise(code, "text must not contain caller-authored [@...] citation marks")
    citations = _validate_citation_ids(
        block.get("citations"),
        evidence_ids=evidence_ids,
        paper_id=paper_id,
        by_chunk=by_chunk,
        code=code,
    )
    if status == STATUS_UNKNOWN:
        if text != UNKNOWN_TEXT:
            _raise(code, "unknown text must be exactly 证据不足")
        if citations:
            _raise(code, "unknown citations must be empty")
        return {"citations": [], "status": STATUS_UNKNOWN, "text": UNKNOWN_TEXT}
    stripped = text.strip()
    if not stripped:
        _raise(code, "provisional text must be nonblank")
    if len(text) > MAX_SECTION_TEXT:
        _raise(code, "provisional text must be at most 8000 characters")
    if not citations:
        _raise(code, "provisional text requires at least one citation")
    return {"citations": citations, "status": STATUS_PROVISIONAL, "text": text}


def _validate_concept(
    item: object,
    *,
    evidence_ids: set[str],
    paper_id: str,
    by_chunk: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if type(item) is not dict:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept must be an object")
    if set(item) != {"name", "citations"}:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept must have exactly name and citations")
    name = item.get("name")
    if type(name) is not str:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept name must be a string")
    display = display_concept_name(name)
    if not display or len(display) > MAX_CONCEPT_NAME:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept name must be 1 to 120 characters")
    if _control_in(display):
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept name must not contain control characters")
    citations = _validate_citation_ids(
        item.get("citations"), evidence_ids=evidence_ids, paper_id=paper_id, by_chunk=by_chunk
    )
    if not citations:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concept citations must be nonempty")
    return {"citations": citations, "name": display}


def _validate_document(
    document: object,
    *,
    paper_id: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    if type(document) is not dict:
        _raise(LIGHT_KNOWLEDGE_INVALID, "document must be an object")
    if document.get("schema") != KNOWLEDGE_DOCUMENT_SCHEMA:
        _raise(LIGHT_KNOWLEDGE_INVALID, "document schema must be light-knowledge-document.v1")
    if set(document) != {"schema", "paper_id", "sections", "concepts"}:
        _raise(LIGHT_KNOWLEDGE_INVALID, "document must have exactly schema, paper_id, sections, and concepts")
    if document.get("paper_id") != paper_id:
        _raise(LIGHT_KNOWLEDGE_INVALID, "document paper_id does not match the selected paper")
    sections = document.get("sections")
    if type(sections) is not dict:
        _raise(LIGHT_KNOWLEDGE_INVALID, "sections must be an object")
    if set(sections) != set(SECTION_KEYS):
        _raise(LIGHT_KNOWLEDGE_INVALID, "sections must use the exact frozen keys")
    by_chunk = {item["chunk_id"]: item for item in evidence}
    evidence_ids = set(by_chunk)
    checked_sections: dict[str, Any] = {}
    provisional = 0
    for key in SECTION_KEYS:
        checked = validate_cited_block(
            sections.get(key), evidence_ids=evidence_ids, paper_id=paper_id, by_chunk=by_chunk
        )
        checked_sections[key] = checked
        if checked["status"] == STATUS_PROVISIONAL:
            provisional += 1
    concepts_raw = document.get("concepts")
    if type(concepts_raw) is not list:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concepts must be a list")
    if len(concepts_raw) > MAX_CONCEPTS:
        _raise(LIGHT_KNOWLEDGE_INVALID, "concepts must contain at most 20 objects")
    concepts = [
        _validate_concept(item, evidence_ids=evidence_ids, paper_id=paper_id, by_chunk=by_chunk)
        for item in concepts_raw
    ]
    if provisional < 1:
        return {}
    return {
        "concepts": concepts,
        "paper_id": paper_id,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": checked_sections,
    }


def _citation_rows(chunk_ids: list[str], by_chunk: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        rows.append(dict(by_chunk[chunk_id]))
    return rows


def _append_marks(text: str, citations: list[str]) -> str:
    if not citations:
        return text
    return text + "".join(f" [@{item}]" for item in citations)


def _render_knowledge_markdown(
    *,
    workspace: Path,
    output: Path,
    paper: Mapping[str, Any],
    document: Mapping[str, Any],
    evidence: list[dict[str, Any]],
) -> str:
    by_chunk = {item["chunk_id"]: item for item in evidence}
    title = escape_md(str(paper.get("title") or paper["paper_id"]))
    lines = [
        f"# {title}",
        "",
        "本文档是模型建议的结构化笔记，不是已核验的科学结论。",
        "",
    ]
    used: list[str] = []
    for key in SECTION_KEYS:
        section = document["sections"][key]
        lines.append(f"## {SECTION_TITLES[key]}")
        lines.append("")
        lines.append(_append_marks(section["text"], section["citations"]))
        lines.append("")
        used.extend(section["citations"])
    if document["concepts"]:
        lines.append("## 概念")
        lines.append("")
        for concept in document["concepts"]:
            label = escape_md(concept["name"])
            lines.append(f"- **{label}**" + "".join(f" [@{item}]" for item in concept["citations"]))
            used.extend(concept["citations"])
        lines.append("")
    body = "\n".join(lines).rstrip()
    citations = _citation_rows(used, by_chunk)
    rendered = render_markdown(body, citations)
    return rewrite_markdown_links(rendered, workspace=workspace, output=output)


def _knowledge_root(workspace: Path) -> Path:
    return workspace / KNOWLEDGE_STATE_DIR


def _records_root(workspace: Path) -> Path:
    return _knowledge_root(workspace) / RECORDS_DIRNAME


def _staging_root(workspace: Path) -> Path:
    return _knowledge_root(workspace) / STAGING_DIRNAME


def _heads_path(workspace: Path) -> Path:
    return _knowledge_root(workspace) / HEADS_NAME


def _views_root(workspace: Path) -> Path:
    return workspace / VIEWS_ROOT / VIEWS_DIRNAME


def _current_path(workspace: Path) -> Path:
    return workspace / VIEWS_ROOT / CURRENT_NAME


def _notes_path(workspace: Path) -> Path:
    return workspace / VIEWS_ROOT / NOTES_NAME


def _ensure_regular_dir(path: Path, *, stop_at: Path) -> None:
    if path.is_symlink():
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "managed path must not be a symlink", {"path": str(path)})
    if path.exists():
        if not path.is_dir():
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "managed path must be a regular directory", {"path": str(path)})
        return
    if path == stop_at:
        _raise(WORKSPACE_INVALID, "workspace_root must be a regular directory")
    _ensure_regular_dir(path.parent, stop_at=stop_at)
    path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "managed path must be a regular directory", {"path": str(path)})


def _load_persisted_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file() or _hardlinked(path):
        return None
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict:
        return None
    try:
        if raw != persisted_bytes(value):
            return None
    except ResearchError:
        return None
    return value


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _file_row(relative: str, data: bytes) -> dict[str, Any]:
    return {"path": relative, "sha256": sha256_bytes(data), "size_bytes": len(data)}


def _sorted_file_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: item["path"])


def _expected_parent_dirs(paths: Mapping[str, bytes] | Iterable[str]) -> set[str]:
    names = paths if isinstance(paths, Mapping) else paths
    parents: set[str] = set()
    for relative in names:
        current = Path(str(relative)).as_posix()
        parent = str(Path(current).parent.as_posix())
        while parent not in {"", "."}:
            parents.add(parent)
            parent = str(Path(parent).parent.as_posix())
    return parents


def _inspect_tree(directory: Path) -> tuple[dict[str, bytes], set[str]] | None:
    if not _is_regular_dir(directory):
        return None
    files: dict[str, bytes] = {}
    dirs: set[str] = set()
    pending = [directory]
    while pending:
        current = pending.pop()
        if current is not directory:
            if current.is_symlink() or not current.is_dir():
                return None
            dirs.add(current.relative_to(directory).as_posix())
        try:
            entries = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError:
            return None
        for item in entries:
            if item.is_symlink():
                return None
            if item.is_dir():
                pending.append(item)
                continue
            if not item.is_file() or _hardlinked(item):
                return None
            files[item.relative_to(directory).as_posix()] = item.read_bytes()
    return files, dirs


def _inventory_bytes(directory: Path) -> dict[str, bytes] | None:
    inspected = _inspect_tree(directory)
    if inspected is None:
        return None
    files, _dirs = inspected
    return files


def _complete_set_match(directory: Path, expected: Mapping[str, bytes]) -> bool:
    inspected = _inspect_tree(directory)
    if inspected is None:
        return False
    files, dirs = inspected
    if set(files) != set(expected) or dirs != _expected_parent_dirs(expected):
        return False
    return all(files[key] == expected[key] for key in expected)


def _bytes_match(expected: Mapping[str, bytes], actual: Mapping[str, bytes] | None) -> bool:
    if actual is None or set(expected) != set(actual):
        return False
    return all(expected[key] == actual[key] for key in expected)


def _record_relative(record_id: str) -> str:
    return f"{KNOWLEDGE_STATE_DIR}/{RECORDS_DIRNAME}/{record_id}"


def _view_relative(view_id: str) -> str:
    return f"{VIEWS_ROOT}/{VIEWS_DIRNAME}/{view_id}"


def _staging_prefix(kind: str, target_id: str) -> str:
    return f"{kind}-{target_id}-"


def _ownership_payload(
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> dict[str, Any]:
    return {
        "allowed_payload_set": sorted(allowed_payload_set),
        "intended_relative_target": intended_relative_target,
        "kind": kind,
        "schema": OWNERSHIP_SCHEMA,
        "target_id": target_id,
        "version": 1,
    }


def _valid_ownership_shape(marker: Mapping[str, Any] | None) -> bool:
    if marker is None:
        return False
    allowed = marker.get("allowed_payload_set")
    return (
        set(marker) == {"allowed_payload_set", "intended_relative_target", "kind", "schema", "target_id", "version"}
        and marker.get("schema") == OWNERSHIP_SCHEMA
        and marker.get("version") == 1
        and type(marker.get("kind")) is str
        and type(marker.get("target_id")) is str
        and type(marker.get("intended_relative_target")) is str
        and type(allowed) is list
        and allowed == sorted(str(item) for item in allowed)
        and all(type(item) is str and item and "\\" not in item and ".." not in Path(item).parts for item in allowed)
    )


def _ownership_matches(
    marker: Mapping[str, Any] | None,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> bool:
    expected = _ownership_payload(
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    )
    return _valid_ownership_shape(marker) and canonical_bytes(marker) == canonical_bytes(expected)


def _list_staging(workspace: Path) -> list[dict[str, Any]]:
    root = _staging_root(workspace)
    rows: list[dict[str, Any]] = []
    if not root.exists() and not root.is_symlink():
        return rows
    if root.is_symlink() or not root.is_dir():
        return [{"relative_path": f"{KNOWLEDGE_STATE_DIR}/{STAGING_DIRNAME}", "status": "unsafe"}]
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        rel = f"{KNOWLEDGE_STATE_DIR}/{STAGING_DIRNAME}/{item.name}"
        if item.is_symlink() or not item.is_dir():
            rows.append({"relative_path": rel, "status": "unsafe"})
            continue
        marker = _load_persisted_object(item / OWNERSHIP_NAME)
        payload = item / PAYLOAD_DIRNAME
        if not _valid_ownership_shape(marker):
            rows.append({"relative_path": rel, "status": "unknown"})
            continue
        assert marker is not None
        inspected = _inspect_tree(payload) if payload.exists() or payload.is_symlink() else ({}, set())
        if payload.exists() and inspected is None:
            rows.append(
                {
                    "kind": marker.get("kind"),
                    "relative_path": rel,
                    "status": "unknown",
                    "target_id": marker.get("target_id"),
                }
            )
            continue
        files, dirs = inspected or ({}, set())
        allowed = set(marker["allowed_payload_set"])
        extra = set(files) - allowed
        unexpected_dirs = dirs - _expected_parent_dirs(files)
        if extra or unexpected_dirs:
            rows.append(
                {
                    "kind": marker.get("kind"),
                    "relative_path": rel,
                    "status": "unknown",
                    "target_id": marker.get("target_id"),
                }
            )
            continue
        rows.append(
            {
                "kind": marker.get("kind"),
                "relative_path": rel,
                "status": "owned-partial" if set(files) != allowed else "owned-complete",
                "target_id": marker.get("target_id"),
            }
        )
    return rows


def _prefix_staging_dirs(workspace: Path, *, kind: str, target_id: str) -> list[Path]:
    root = _staging_root(workspace)
    found: list[Path] = []
    if not _is_regular_dir(root):
        return found
    prefix = _staging_prefix(kind, target_id)
    for item in root.iterdir():
        if item.name.startswith(prefix):
            found.append(item)
    return found


def _owned_staging_dirs(
    workspace: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> list[Path]:
    found: list[Path] = []
    for item in _prefix_staging_dirs(workspace, kind=kind, target_id=target_id):
        if item.is_symlink() or not item.is_dir():
            continue
        marker = _load_persisted_object(item / OWNERSHIP_NAME)
        if _ownership_matches(
            marker,
            kind=kind,
            target_id=target_id,
            intended_relative_target=intended_relative_target,
            allowed_payload_set=allowed_payload_set,
        ):
            found.append(item)
    return found


def _stage_surface_ok(directory: Path) -> bool:
    try:
        names = {item.name for item in directory.iterdir()}
    except OSError:
        return False
    return names <= {OWNERSHIP_NAME, PAYLOAD_DIRNAME}


def _remove_validated_owned_stage(directory: Path, expected: Mapping[str, bytes]) -> bool:
    if not _is_regular_dir(directory) or not _stage_surface_ok(directory):
        return False
    marker = _load_persisted_object(directory / OWNERSHIP_NAME)
    if not _valid_ownership_shape(marker):
        return False
    payload = directory / PAYLOAD_DIRNAME
    if payload.exists() or payload.is_symlink():
        inspected = _inspect_tree(payload)
        if inspected is None:
            return False
        files, dirs = inspected
        if set(files) - set(expected) or dirs != _expected_parent_dirs(files):
            return False
        if any(files[name] != expected[name] for name in files):
            return False
        for rel in list(files):
            path = payload / rel
            if not _is_regular_file(path):
                return False
            path.unlink()
        for dirpath, dirnames, filenames in os.walk(payload, topdown=False, followlinks=False):
            root = Path(dirpath)
            if not filenames and not dirnames and root != payload and _is_regular_dir(root):
                try:
                    root.rmdir()
                except OSError:
                    return False
        try:
            payload.rmdir()
        except OSError:
            return False
    marker_path = directory / OWNERSHIP_NAME
    if _is_regular_file(marker_path):
        marker_path.unlink()
    try:
        directory.rmdir()
    except OSError:
        return False
    return True


def _classify_owned_stage(
    directory: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
    expected: Mapping[str, bytes],
) -> str:
    if directory.is_symlink() or not directory.is_dir() or not _stage_surface_ok(directory):
        return "conflict"
    marker = _load_persisted_object(directory / OWNERSHIP_NAME)
    if not _ownership_matches(
        marker,
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    ):
        return "conflict"
    payload = directory / PAYLOAD_DIRNAME
    if not payload.exists() and not payload.is_symlink():
        return "owned-empty"
    inspected = _inspect_tree(payload)
    if inspected is None:
        return "conflict"
    files, dirs = inspected
    if dirs != _expected_parent_dirs(files) or set(files) - set(expected):
        return "conflict"
    if any(files[name] != expected[name] for name in files):
        return "conflict"
    if not files:
        return "owned-empty"
    if set(files) == set(expected):
        return "owned-complete"
    return "owned-partial"


def _create_staging(
    workspace: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
) -> Path:
    root = _staging_root(workspace)
    _ensure_regular_dir(root, stop_at=workspace)
    token = secrets.token_hex(8)
    staged = root / f"{kind}-{target_id}-{token}"
    if staged.exists() or staged.is_symlink():
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging path already exists", {"path": str(staged)})
    staged.mkdir()
    if staged.is_symlink() or not staged.is_dir():
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging path must be a regular directory")
    ownership = _ownership_payload(
        kind=kind,
        target_id=target_id,
        intended_relative_target=intended_relative_target,
        allowed_payload_set=allowed_payload_set,
    )
    _write_bytes(staged / OWNERSHIP_NAME, persisted_bytes(ownership))
    payload = staged / PAYLOAD_DIRNAME
    payload.mkdir()
    return staged


def _write_payload_tree(payload: Path, files: Mapping[str, bytes]) -> None:
    for relative, data in files.items():
        if Path(relative).is_absolute() or "\\" in relative or ".." in Path(relative).parts:
            _raise(LIGHT_KNOWLEDGE_INVALID, "payload path is unsafe")
        target = payload / relative
        _ensure_regular_dir(target.parent, stop_at=payload)
        _write_bytes(target, data)


def _publish_directory(payload: Path, destination: Path) -> None:
    if destination.is_symlink() or _symlink_in_chain(destination):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "publication destination must not be a symlink")
    if destination.exists():
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "publication destination already exists", {"path": str(destination)})
    os.rename(payload, destination)
    if not _is_regular_dir(destination):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "publication destination is unsafe")


def _cleanup_empty_staging(staged: Path, expected: Mapping[str, bytes] | None = None) -> None:
    if not _is_regular_dir(staged) or not _stage_surface_ok(staged):
        return
    marker = _load_persisted_object(staged / OWNERSHIP_NAME)
    if not _valid_ownership_shape(marker):
        return
    payload = staged / PAYLOAD_DIRNAME
    if payload.exists() or payload.is_symlink():
        inspected = _inspect_tree(payload)
        if inspected is None:
            return
        files, dirs = inspected
        if files or dirs:
            if expected is None or not _complete_set_match(payload, expected):
                return
            return
        try:
            payload.rmdir()
        except OSError:
            return
    marker_path = staged / OWNERSHIP_NAME
    if _is_regular_file(marker_path):
        try:
            marker_path.unlink()
        except OSError:
            return
    try:
        staged.rmdir()
    except OSError:
        return


def _reconcile_prefix_staging(
    workspace: Path,
    *,
    kind: str,
    target_id: str,
    intended_relative_target: str,
    allowed_payload_set: list[str],
    expected: Mapping[str, bytes],
    destination_ready: bool = False,
) -> Path | None:
    complete: Path | None = None
    for staged in _prefix_staging_dirs(workspace, kind=kind, target_id=target_id):
        status = _classify_owned_stage(
            staged,
            kind=kind,
            target_id=target_id,
            intended_relative_target=intended_relative_target,
            allowed_payload_set=allowed_payload_set,
            expected=expected,
        )
        if status == "conflict":
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging contains unknown or edited bytes")
        if status == "owned-complete":
            if complete is not None:
                _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging contains duplicate complete payloads")
            complete = staged
            continue
        if not _remove_validated_owned_stage(staged, expected):
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging contains unknown or edited bytes")
    if complete is not None and destination_ready:
        if not _remove_validated_owned_stage(complete, expected):
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge staging contains unknown or edited bytes")
        return None
    return complete


def _record_files(
    *,
    workspace: Path,
    record_id: str,
    document: dict[str, Any],
    context: dict[str, Any],
    paper: Mapping[str, Any],
    wrapper: Mapping[str, Any],
) -> dict[str, bytes]:
    identity = {
        "chunks": [
            {
                "chunk_id": item["chunk_id"],
                "page": item["page"],
                "paper_id": item["paper_id"],
                "text_end": item["text_end"],
                "text_sha256": item["text_sha256"],
                "text_start": item["text_start"],
            }
            for item in context["evidence"]
        ],
        "markdown_path": paper["markdown_path"],
        "paper_snapshot": _paper_snapshot(paper),
        "schema": IDENTITY_SCHEMA,
        "wrapper": _wrapper_identity(wrapper),
    }
    page_relative = f"{_record_relative(record_id)}/{KNOWLEDGE_PAGE_NAME}"
    markdown = _render_knowledge_markdown(
        workspace=workspace,
        output=workspace / page_relative,
        paper=paper,
        document=document,
        evidence=context["evidence"],
    )
    if not markdown.endswith("\n"):
        markdown += "\n"
    encoded_md = markdown.encode("utf-8")
    files = {
        DOCUMENT_NAME: persisted_bytes(document),
        CONTEXT_NAME: persisted_bytes(context),
        IDENTITY_NAME: persisted_bytes(identity),
        KNOWLEDGE_PAGE_NAME: encoded_md,
    }
    manifest = {
        "context_sha256": wrapper["context_sha256"],
        "document_sha256": sha256_canonical(document),
        "files": _sorted_file_rows([_file_row(name, data) for name, data in files.items()]),
        "knowledge_sha256": sha256_bytes(encoded_md),
        "page_relative": page_relative,
        "paper_id": paper["paper_id"],
        "paper_snapshot": _paper_snapshot(paper),
        "record_id": record_id,
        "schema": RECORD_SCHEMA,
        "source": {
            "markdown_path": paper["markdown_path"],
            "markdown_sha256": paper["markdown_sha256"],
            "source_json_sha256": paper["source_json_sha256"],
        },
    }
    files[MANIFEST_NAME] = persisted_bytes(manifest)
    manifest["files"] = _sorted_file_rows([_file_row(name, data) for name, data in files.items() if name != MANIFEST_NAME])
    files[MANIFEST_NAME] = persisted_bytes(manifest)
    return files


def _default_heads() -> dict[str, Any]:
    return {"heads": {}, "schema": HEADS_SCHEMA}


def _valid_heads_pointer(payload: Mapping[str, Any] | None) -> bool:
    if payload is None or set(payload) != {"heads", "schema"} or payload.get("schema") != HEADS_SCHEMA:
        return False
    heads = payload.get("heads")
    if type(heads) is not dict:
        return False
    for key, value in heads.items():
        if type(key) is not str or not PAPER_ID_PATTERN.fullmatch(key):
            return False
        if type(value) is not str or not HEX64.fullmatch(value):
            return False
    return True


def _valid_current_pointer(payload: Mapping[str, Any] | None) -> bool:
    if payload is None or set(payload) != {"index_relative", "schema", "view_id"}:
        return False
    if payload.get("schema") != CURRENT_SCHEMA:
        return False
    view_id = payload.get("view_id")
    if type(view_id) is not str or not HEX64.fullmatch(view_id):
        return False
    return payload.get("index_relative") == f"{_view_relative(view_id)}/{INDEX_PAGE_NAME}"


def _load_heads(workspace: Path) -> dict[str, Any]:
    path = _heads_path(workspace)
    if not path.exists() and not path.is_symlink():
        return _default_heads()
    loaded = _load_persisted_object(path)
    if not _valid_heads_pointer(loaded):
        return _closed(LIGHT_KNOWLEDGE_CONFLICT, "knowledge head map is not a validated managed pointer")
    assert loaded is not None
    heads = {key: loaded["heads"][key] for key in sorted(loaded["heads"])}
    return {"heads": heads, "schema": HEADS_SCHEMA}


def _publish_json_pointer(workspace: Path, *, kind: str, target_id: str, relative_target: str, payload: dict[str, Any]) -> None:
    if kind == "heads" and not _valid_heads_pointer(payload):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "managed pointer payload is not a validated object")
    if kind == "current" and not _valid_current_pointer(payload):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "managed pointer payload is not a validated object")
    destination = workspace / relative_target
    encoded = persisted_bytes(payload)
    name = Path(relative_target).name
    expected = {name: encoded}
    allowed = [name]
    already = False
    if destination.exists() or destination.is_symlink():
        _require_safe_file(destination, relative_target)
        if destination.read_bytes() == encoded:
            already = True
        else:
            existing = _load_persisted_object(destination)
            valid_existing = (
                _valid_heads_pointer(existing)
                if kind == "heads"
                else _valid_current_pointer(existing)
                if kind == "current"
                else existing is not None
            )
            if not valid_existing:
                _raise(LIGHT_KNOWLEDGE_CONFLICT, "existing managed pointer is not a validated object")
    complete = _reconcile_prefix_staging(
        workspace,
        kind=kind,
        target_id=target_id,
        intended_relative_target=relative_target,
        allowed_payload_set=allowed,
        expected=expected,
        destination_ready=already,
    )
    if already:
        return
    if complete is not None:
        tmp = complete / PAYLOAD_DIRNAME / name
        _ensure_regular_dir(destination.parent, stop_at=workspace)
        os.replace(tmp, destination)
        _cleanup_empty_staging(complete, expected)
        return
    staged = _create_staging(
        workspace,
        kind=kind,
        target_id=target_id,
        intended_relative_target=relative_target,
        allowed_payload_set=allowed,
    )
    try:
        _write_bytes(staged / PAYLOAD_DIRNAME / name, encoded)
        _ensure_regular_dir(destination.parent, stop_at=workspace)
        os.replace(staged / PAYLOAD_DIRNAME / name, destination)
    finally:
        _cleanup_empty_staging(staged, expected)


def _set_head(workspace: Path, paper_id: str, record_id: str) -> None:
    current = _load_heads(workspace)
    if current.get("ok") is False:
        _raise(str(current["status"]), str(current["message"]))
    heads = dict(current["heads"])
    heads[paper_id] = record_id
    ordered = {key: heads[key] for key in sorted(heads)}
    payload = {"heads": ordered, "schema": HEADS_SCHEMA}
    _publish_json_pointer(
        workspace,
        kind="heads",
        target_id=sha256_canonical(payload),
        relative_target=f"{KNOWLEDGE_STATE_DIR}/{HEADS_NAME}",
        payload=payload,
    )


def _publish_record(workspace: Path, record_id: str, files: Mapping[str, bytes]) -> bool:
    dest = _records_root(workspace) / record_id
    _ensure_regular_dir(_records_root(workspace), stop_at=workspace)
    dest_ready = False
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or not dest.is_dir():
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge record destination is unsafe")
        if not _complete_set_match(dest, files):
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge record already exists with different bytes")
        dest_ready = True
    allowed = list(RECORD_PAYLOAD)
    intended = _record_relative(record_id)
    complete = _reconcile_prefix_staging(
        workspace,
        kind="record",
        target_id=record_id,
        intended_relative_target=intended,
        allowed_payload_set=allowed,
        expected=files,
        destination_ready=dest_ready,
    )
    if dest_ready:
        return True
    if complete is not None:
        _publish_directory(complete / PAYLOAD_DIRNAME, dest)
        _cleanup_empty_staging(complete, files)
        return False
    staged = _create_staging(
        workspace,
        kind="record",
        target_id=record_id,
        intended_relative_target=intended,
        allowed_payload_set=allowed,
    )
    try:
        _write_payload_tree(staged / PAYLOAD_DIRNAME, files)
        _publish_directory(staged / PAYLOAD_DIRNAME, dest)
    finally:
        _cleanup_empty_staging(staged, files)
    return False


_KNOWLEDGE_WRAPPER_IMPORT_TYPES = {
    **_KNOWLEDGE_WRAPPER_TYPES,
    "context_sha256": str,
}


def _current_knowledge_inputs(workspace: Path, paper_id: str) -> dict[str, Any]:
    fresh = _export_knowledge_unlocked(workspace, paper_id)
    if fresh.get("ok") is not True:
        return fresh
    live = validate_live_context(workspace, fresh["context"])
    if live.get("ok") is not True:
        return live
    return fresh


def _import_knowledge_locked(workspace: Path, wrapper: object, document: object) -> dict[str, Any]:
    if type(wrapper) is not dict:
        _raise(LIGHT_KNOWLEDGE_INVALID, "context must be an object")
    shaped = _require_typed_fields(wrapper, _KNOWLEDGE_WRAPPER_IMPORT_TYPES, code=LIGHT_KNOWLEDGE_INVALID)
    if shaped is not None:
        return shaped
    try:
        paper_id = require_paper_id(wrapper.get("paper_id"))
        identity = _wrapper_identity(wrapper)
    except ResearchError as exc:
        if exc.code == LIGHT_KNOWLEDGE_INVALID:
            return _closed(LIGHT_KNOWLEDGE_INVALID, exc.message)
        raise
    fresh = _current_knowledge_inputs(workspace, paper_id)
    if fresh.get("ok") is not True:
        return fresh
    try:
        if wrapper.get("schema") != KNOWLEDGE_CONTEXT_SCHEMA:
            return _closed(LIGHT_KNOWLEDGE_INVALID, "context schema must be light-knowledge-context.v1")
        if sha256_canonical(wrapper["context"]) != fresh["context_sha256"]:
            return _closed(LIGHT_KNOWLEDGE_INVALID, "context wrapper does not match a current knowledge export")
        if wrapper.get("context_sha256") != fresh["context_sha256"]:
            return _closed(LIGHT_KNOWLEDGE_INVALID, "context_sha256 does not match the inner context bytes")
        if canonical_bytes(identity) != canonical_bytes(_wrapper_identity(fresh)):
            return _closed(LIGHT_KNOWLEDGE_INVALID, "context wrapper does not match a current knowledge export")
    except ResearchError as exc:
        if exc.code == LIGHT_KNOWLEDGE_INVALID:
            return _closed(LIGHT_KNOWLEDGE_INVALID, exc.message)
        raise
    try:
        checked = _validate_document(
            document, paper_id=paper_id, evidence=copy_evidence(fresh["context"]["evidence"])
        )
    except ResearchError as exc:
        if exc.code == LIGHT_KNOWLEDGE_INVALID:
            return _closed(LIGHT_KNOWLEDGE_INVALID, exc.message)
        raise
    if not checked:
        return _closed(
            INSUFFICIENT_EVIDENCE,
            "all knowledge sections are unknown",
            paper_id=paper_id,
        )
    record_id = sha256_canonical({"document": checked, "wrapper": _wrapper_identity(fresh)})
    papers = _load_live_papers(workspace)
    if type(papers) is dict:
        return papers
    paper = _paper_by_id(papers, paper_id)
    assert paper is not None
    files = _record_files(
        workspace=workspace,
        record_id=record_id,
        document=checked,
        context=fresh["context"],
        paper=paper,
        wrapper=fresh,
    )
    after_render = _current_knowledge_inputs(workspace, paper_id)
    if after_render.get("ok") is not True:
        return after_render
    if canonical_bytes(_wrapper_identity(after_render)) != canonical_bytes(_wrapper_identity(fresh)):
        return _closed(LIGHT_KNOWLEDGE_INVALID, "live source changed during knowledge publication")
    if _paper_snapshot(paper) != after_render["paper_snapshot"]:
        return _closed(LIGHT_KNOWLEDGE_INVALID, "live source changed during knowledge publication")
    reused = _publish_record(workspace, record_id, files)
    before_head = _current_knowledge_inputs(workspace, paper_id)
    if before_head.get("ok") is not True:
        return before_head
    if canonical_bytes(_wrapper_identity(before_head)) != canonical_bytes(_wrapper_identity(fresh)):
        return _closed(LIGHT_KNOWLEDGE_INVALID, "live source changed during knowledge publication")
    _set_head(workspace, paper_id, record_id)
    page = (_records_root(workspace) / record_id / KNOWLEDGE_PAGE_NAME).resolve()
    return {
        "ok": True,
        "status": OK,
        "message": "reused structured knowledge record" if reused else "published structured knowledge record",
        "record_id": record_id,
        "paper_id": paper_id,
        "page_path": str(page),
        "source_status": "current",
        "reused": reused,
    }


def import_knowledge(workspace_root: Path, context: object, document: object) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        with workspace_lock(workspace):
            return _import_knowledge_locked(workspace, context, document)
    except ResearchError as exc:
        if exc.code == LIGHT_WORKSPACE_BUSY:
            return _closed(LIGHT_WORKSPACE_BUSY, exc.message)
        if exc.code == LIGHT_KNOWLEDGE_CONFLICT:
            return _closed(LIGHT_KNOWLEDGE_CONFLICT, exc.message)
        raise


def _identity_chunks(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item["chunk_id"],
            "page": item["page"],
            "paper_id": item["paper_id"],
            "text_end": item["text_end"],
            "text_sha256": item["text_sha256"],
            "text_start": item["text_start"],
        }
        for item in evidence
    ]


def _document_citation_ids(document: Mapping[str, Any]) -> list[str]:
    used: list[str] = []
    sections = document.get("sections")
    if type(sections) is dict:
        for key in SECTION_KEYS:
            block = sections.get(key)
            if type(block) is dict and type(block.get("citations")) is list:
                used.extend(item for item in block["citations"] if type(item) is str)
    concepts = document.get("concepts")
    if type(concepts) is list:
        for item in concepts:
            if type(item) is dict and type(item.get("citations")) is list:
                used.extend(value for value in item["citations"] if type(value) is str)
    return used


def _record_source_status(workspace: Path, record_dir: Path) -> str:
    if not HEX64.fullmatch(record_dir.name) or record_dir.is_symlink() or not record_dir.is_dir():
        return "conflict"
    inspected = _inspect_tree(record_dir)
    if inspected is None:
        return "conflict"
    files, dirs = inspected
    if set(files) != set(RECORD_PAYLOAD) or dirs:
        return "conflict"
    manifest = _load_persisted_object(record_dir / MANIFEST_NAME)
    identity = _load_persisted_object(record_dir / IDENTITY_NAME)
    document = _load_persisted_object(record_dir / DOCUMENT_NAME)
    context = _load_persisted_object(record_dir / CONTEXT_NAME)
    page = record_dir / KNOWLEDGE_PAGE_NAME
    if manifest is None or identity is None or document is None or context is None:
        return "conflict"
    if not _is_regular_file(page) or _hardlinked(page):
        return "conflict"
    if manifest.get("schema") != RECORD_SCHEMA or identity.get("schema") != IDENTITY_SCHEMA:
        return "conflict"
    if manifest.get("record_id") != record_dir.name:
        return "conflict"
    paper_id = manifest.get("paper_id")
    if type(paper_id) is not str or not PAPER_ID_PATTERN.fullmatch(paper_id):
        return "conflict"
    if document.get("paper_id") != paper_id:
        return "conflict"
    if manifest.get("page_relative") != f"{_record_relative(record_dir.name)}/{KNOWLEDGE_PAGE_NAME}":
        return "conflict"
    expected_rows = _sorted_file_rows([_file_row(name, files[name]) for name in files if name != MANIFEST_NAME])
    if type(manifest.get("files")) is not list or canonical_bytes(manifest["files"]) != canonical_bytes(expected_rows):
        return "conflict"
    if manifest.get("document_sha256") != sha256_canonical(document):
        return "conflict"
    if manifest.get("context_sha256") != sha256_canonical(context):
        return "conflict"
    if manifest.get("knowledge_sha256") != sha256_bytes(files[KNOWLEDGE_PAGE_NAME]):
        return "conflict"
    wrapper = identity.get("wrapper")
    if type(wrapper) is not dict:
        return "conflict"
    try:
        shaped = _wrapper_identity(wrapper)
        if canonical_bytes(shaped["context"]) != canonical_bytes(context):
            return "conflict"
        if shaped["paper_id"] != paper_id:
            return "conflict"
        if sha256_canonical({"document": document, "wrapper": shaped}) != record_dir.name:
            return "conflict"
        evidence = context.get("evidence")
        if type(evidence) is not list:
            return "conflict"
        checked = _validate_document(document, paper_id=paper_id, evidence=copy_evidence(evidence))
    except ResearchError:
        return "conflict"
    if not checked or canonical_bytes(checked) != canonical_bytes(document):
        return "conflict"
    if identity.get("chunks") != _identity_chunks(evidence):
        return "conflict"
    source = manifest.get("source") if type(manifest.get("source")) is dict else {}
    snapshot = manifest.get("paper_snapshot") if type(manifest.get("paper_snapshot")) is dict else {}
    identity_snapshot = identity.get("paper_snapshot") if type(identity.get("paper_snapshot")) is dict else {}
    if (
        canonical_bytes(snapshot) != canonical_bytes(identity_snapshot)
        or snapshot.get("paper_id") != paper_id
        or source.get("markdown_path") != identity.get("markdown_path")
    ):
        return "conflict"
    digest = _paper_digest(paper_id)
    paper_dir = workspace / "papers" / digest
    if not paper_dir.exists() and not paper_dir.is_symlink():
        return "missing-source"
    if _unsafe_source_reason(paper_dir) is not None:
        return "conflict"
    try:
        paper = _load_paper(paper_dir)
    except (ResearchError, UnicodeError, OSError):
        return "conflict"
    live_snapshot = _paper_snapshot(paper)
    if (
        source.get("markdown_sha256") != live_snapshot["markdown_sha256"]
        or source.get("source_json_sha256") != live_snapshot["source_json_sha256"]
        or snapshot != live_snapshot
        or source.get("markdown_path") != paper["markdown_path"]
        or identity.get("markdown_path") != paper["markdown_path"]
    ):
        return "stale"
    derived = {item["chunk_id"]: item for item in _derived_chunks([paper])}
    for item in identity.get("chunks") or []:
        if type(item) is not dict:
            return "conflict"
        live = derived.get(item.get("chunk_id"))
        if live is None:
            return "stale"
        for field in ("page", "paper_id", "text_start", "text_end", "text_sha256"):
            if item.get(field) != live.get(field):
                return "stale"
    for chunk_id in _document_citation_ids(document):
        live = derived.get(chunk_id)
        if live is None or live.get("paper_id") != paper_id:
            return "conflict"
    return "current"


def _iter_records(workspace: Path) -> list[Path]:
    root = _records_root(workspace)
    if not root.exists() and not root.is_symlink():
        return []
    if root.is_symlink() or not root.is_dir():
        return []
    found: list[Path] = []
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if item.is_symlink() or not item.is_dir():
            continue
        found.append(item)
    return found


def list_knowledge(workspace_root: Path) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    heads_state = _load_heads(workspace)
    if heads_state.get("ok") is False:
        return heads_state
    heads: dict[str, str] = heads_state["heads"]
    records: list[dict[str, Any]] = []
    for directory in _iter_records(workspace):
        if not HEX64.fullmatch(directory.name):
            records.append(
                {
                    "record_id": directory.name,
                    "paper_id": "",
                    "page_path": "",
                    "source_status": "conflict",
                    "is_head": False,
                }
            )
            continue
        manifest = _load_persisted_object(directory / MANIFEST_NAME)
        paper_id = ""
        if manifest is not None and type(manifest.get("paper_id")) is str:
            paper_id = manifest["paper_id"]
        page = directory / KNOWLEDGE_PAGE_NAME
        records.append(
            {
                "is_head": bool(paper_id) and heads.get(paper_id) == directory.name,
                "page_path": str(page.resolve()) if page.exists() else "",
                "paper_id": paper_id,
                "record_id": directory.name,
                "source_status": _record_source_status(workspace, directory),
            }
        )
    records.sort(key=lambda item: (item["paper_id"], item["record_id"]))
    return {
        "ok": True,
        "status": OK,
        "message": "listed structured knowledge records",
        "records": records,
        "heads": {key: heads[key] for key in sorted(heads)},
        "staging": _list_staging(workspace),
    }


def _current_head_records(workspace: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    listing = list_knowledge(workspace)
    if listing.get("ok") is not True:
        return {}, []
    current: dict[str, dict[str, Any]] = {}
    historical: list[dict[str, Any]] = []
    for row in listing["records"]:
        if row["source_status"] == "current" and row["is_head"]:
            current[row["paper_id"]] = row
        else:
            historical.append(row)
    return current, historical


def _load_record_document(workspace: Path, record_id: str) -> dict[str, Any] | None:
    return _load_persisted_object(_records_root(workspace) / record_id / DOCUMENT_NAME)


def _concept_file_id(key: str) -> str:
    return sha256_bytes(key.encode("utf-8"))


def _view_payload(
    workspace: Path,
    *,
    view_id: str,
    current: Mapping[str, dict[str, Any]],
    historical: list[dict[str, Any]],
    papers: list[dict[str, Any]],
) -> dict[str, bytes]:
    by_paper = {paper["paper_id"]: paper for paper in papers}
    groups: dict[str, dict[str, Any]] = {}
    for paper_id, row in current.items():
        document = _load_record_document(workspace, row["record_id"])
        if document is None:
            continue
        for concept in document.get("concepts") or []:
            if type(concept) is not dict or type(concept.get("name")) is not str:
                continue
            key = normalize_concept_key(concept["name"])
            group = groups.setdefault(
                key,
                {"display": display_concept_name(concept["name"]), "paper_ids": [], "record_ids": []},
            )
            if paper_id not in group["paper_ids"]:
                group["paper_ids"].append(paper_id)
            if row["record_id"] not in group["record_ids"]:
                group["record_ids"].append(row["record_id"])
    files: dict[str, bytes] = {}
    paper_links: dict[str, str] = {}
    for paper_id in sorted(current):
        digest = _paper_digest(paper_id)
        paper_links[paper_id] = f"papers/{digest}.md"
    concept_links: dict[str, str] = {}
    for key in sorted(groups):
        concept_links[key] = f"concepts/{_concept_file_id(key)}.md"
    index_lines = [
        "# 知识视图",
        "",
        "当前关系只使用来源仍匹配的现行记录。过期或历史记录单独列出，不构成支持/反对或官方论文关系。",
        "",
        "## 现行论文",
        "",
    ]
    if not current:
        index_lines.append("（无现行知识记录）")
        index_lines.append("")
    for paper_id in sorted(current):
        paper = by_paper.get(paper_id)
        title = escape_md(str(paper["title"] if paper else paper_id))
        index_lines.append(f"- [{title}]({paper_links[paper_id]}) — `{paper_id}`")
    index_lines.extend(["", "## 概念", ""])
    if not groups:
        index_lines.append("（无现行概念）")
        index_lines.append("")
    for key in sorted(groups):
        label = escape_md(groups[key]["display"])
        index_lines.append(f"- [{label}]({concept_links[key]})")
    index_lines.extend(["", "## 过期或历史记录", ""])
    if not historical:
        index_lines.append("（无）")
        index_lines.append("")
    for row in historical:
        status = escape_md(str(row["source_status"]))
        index_lines.append(
            f"- `{row['record_id']}` — `{row['paper_id']}` — {status}"
        )
    index_lines.append("")
    files[INDEX_PAGE_NAME] = ("\n".join(index_lines)).encode("utf-8")
    for paper_id, row in current.items():
        paper = by_paper.get(paper_id)
        title = escape_md(str(paper["title"] if paper else paper_id))
        document = _load_record_document(workspace, row["record_id"])
        digest = _paper_digest(paper_id)
        knowledge_rel = os.path.relpath(
            workspace / _record_relative(row["record_id"]) / KNOWLEDGE_PAGE_NAME,
            workspace / _view_relative(view_id) / "papers",
        )
        source_rel = os.path.relpath(
            workspace / f"papers/{digest}/source.md",
            workspace / _view_relative(view_id) / "papers",
        )
        related: list[str] = []
        own_keys = {
            normalize_concept_key(item["name"])
            for item in (document.get("concepts") if document else []) or []
            if type(item) is dict and type(item.get("name")) is str
        }
        for other_id in sorted(current):
            if other_id == paper_id:
                continue
            shared = []
            other_doc = _load_record_document(workspace, current[other_id]["record_id"])
            for item in (other_doc.get("concepts") if other_doc else []) or []:
                if type(item) is not dict or type(item.get("name")) is not str:
                    continue
                key = normalize_concept_key(item["name"])
                if key in own_keys:
                    shared.append(groups[key]["display"])
            if shared:
                other_title = escape_md(str(by_paper.get(other_id, {}).get("title") or other_id))
                labels = ", ".join(escape_md(name) for name in dict.fromkeys(shared))
                related.append(
                    f"- [{other_title}]({_paper_digest(other_id)}.md) — 共享概念: {labels}"
                )
        lines = [
            f"# {title}",
            "",
            f"- 记录: [{row['record_id']}]({Path(knowledge_rel).as_posix()})",
            f"- 来源: [{digest[:12]}]({Path(source_rel).as_posix()})",
            "",
            "## 相同概念建议",
            "",
            "这些是相同概念建议，不是支持/反对或官方论文关系。",
            "",
        ]
        if related:
            lines.extend(related)
        else:
            lines.append("（无）")
        lines.append("")
        files[f"papers/{digest}.md"] = ("\n".join(lines)).encode("utf-8")
    for key, group in groups.items():
        label = escape_md(group["display"])
        lines = [
            f"# {label}",
            "",
            "这些是相同概念建议，不是支持/反对或官方论文关系。",
            "",
        ]
        for paper_id in group["paper_ids"]:
            if paper_id not in current:
                continue
            paper = by_paper.get(paper_id)
            title = escape_md(str(paper["title"] if paper else paper_id))
            lines.append(f"- [{title}](../{paper_links[paper_id]})")
        lines.append("")
        files[f"concepts/{_concept_file_id(key)}.md"] = ("\n".join(lines)).encode("utf-8")
    view_manifest = {
        "files": _sorted_file_rows([_file_row(name, data) for name, data in files.items()]),
        "heads": {key: current[key]["record_id"] for key in sorted(current)},
        "schema": VIEW_SCHEMA,
        "view_id": view_id,
    }
    files[MANIFEST_NAME] = persisted_bytes(view_manifest)
    return files


def _view_fingerprint(
    *,
    current: Mapping[str, dict[str, Any]],
    historical: list[dict[str, Any]],
    papers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "heads": {key: current[key]["record_id"] for key in sorted(current)},
        "historical": [
            {"paper_id": item["paper_id"], "record_id": item["record_id"], "source_status": item["source_status"]}
            for item in historical
        ],
        "papers": [
            _paper_snapshot(paper)
            for paper in sorted(papers, key=lambda item: item["paper_id"])
            if paper["paper_id"] in current
        ],
        "schema": VIEW_SCHEMA,
    }


def _publish_view(workspace: Path, view_id: str, files: Mapping[str, bytes]) -> bool:
    dest = _views_root(workspace) / view_id
    _ensure_regular_dir(_views_root(workspace), stop_at=workspace)
    notes = _notes_path(workspace)
    if notes.exists() and (notes.is_symlink() or not notes.is_file()):
        _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge/notes.md must remain a regular user file")
    dest_ready = False
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or not dest.is_dir():
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge view destination is unsafe")
        if not _complete_set_match(dest, files):
            _raise(LIGHT_KNOWLEDGE_CONFLICT, "knowledge view already exists with different bytes")
        dest_ready = True
    allowed = sorted(files)
    intended = _view_relative(view_id)
    complete = _reconcile_prefix_staging(
        workspace,
        kind="view",
        target_id=view_id,
        intended_relative_target=intended,
        allowed_payload_set=allowed,
        expected=files,
        destination_ready=dest_ready,
    )
    if dest_ready:
        return True
    if complete is not None:
        _publish_directory(complete / PAYLOAD_DIRNAME, dest)
        _cleanup_empty_staging(complete, files)
        return False
    staged = _create_staging(
        workspace,
        kind="view",
        target_id=view_id,
        intended_relative_target=intended,
        allowed_payload_set=allowed,
    )
    try:
        _write_payload_tree(staged / PAYLOAD_DIRNAME, files)
        _publish_directory(staged / PAYLOAD_DIRNAME, dest)
    finally:
        _cleanup_empty_staging(staged, files)
    return False


def _reload_view_inputs(workspace: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]] | dict[str, Any]:
    loaded = _require_current_index(workspace)
    if type(loaded) is dict:
        return loaded
    _stored, papers = loaded
    current, historical = _current_head_records(workspace)
    heads_state = _load_heads(workspace)
    if heads_state.get("ok") is False:
        return heads_state
    return heads_state, current, historical, papers


def _build_views_locked(workspace: Path) -> dict[str, Any]:
    loaded = _reload_view_inputs(workspace)
    if type(loaded) is dict:
        return loaded
    _heads_state, current, historical, papers = loaded
    view_id = sha256_canonical(_view_fingerprint(current=current, historical=historical, papers=papers))
    files = _view_payload(workspace, view_id=view_id, current=current, historical=historical, papers=papers)
    after_render = _reload_view_inputs(workspace)
    if type(after_render) is dict:
        return after_render
    _heads2, current2, historical2, papers2 = after_render
    if sha256_canonical(_view_fingerprint(current=current2, historical=historical2, papers=papers2)) != view_id:
        return _closed(LIGHT_KNOWLEDGE_CONFLICT, "knowledge view inputs changed during publication")
    reused = _publish_view(workspace, view_id, files)
    before_pointer = _reload_view_inputs(workspace)
    if type(before_pointer) is dict:
        return before_pointer
    _heads3, current3, historical3, papers3 = before_pointer
    if sha256_canonical(_view_fingerprint(current=current3, historical=historical3, papers=papers3)) != view_id:
        return _closed(LIGHT_KNOWLEDGE_CONFLICT, "knowledge view inputs changed during publication")
    pointer = {
        "index_relative": f"{_view_relative(view_id)}/{INDEX_PAGE_NAME}",
        "schema": CURRENT_SCHEMA,
        "view_id": view_id,
    }
    _publish_json_pointer(
        workspace,
        kind="current",
        target_id=view_id,
        relative_target=f"{VIEWS_ROOT}/{CURRENT_NAME}",
        payload=pointer,
    )
    index_path = (_views_root(workspace) / view_id / INDEX_PAGE_NAME).resolve()
    return {
        "ok": True,
        "status": OK,
        "message": "reused knowledge views" if reused else "published knowledge views",
        "view_id": view_id,
        "index_path": str(index_path),
        "reused": reused,
    }


def build_knowledge_views(workspace_root: Path) -> dict[str, Any]:
    workspace = require_product_workspace(workspace_root)
    try:
        with workspace_lock(workspace):
            return _build_views_locked(workspace)
    except ResearchError as exc:
        if exc.code == LIGHT_WORKSPACE_BUSY:
            return _closed(LIGHT_WORKSPACE_BUSY, exc.message)
        if exc.code == LIGHT_KNOWLEDGE_CONFLICT:
            return _closed(LIGHT_KNOWLEDGE_CONFLICT, exc.message)
        raise
