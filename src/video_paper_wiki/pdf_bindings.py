"""Explicit notes-vault PDF bindings. No upload, no Drive edits, no verified locators."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import paper_page_slug
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.pdf_locations import (
    KIND_NOTES,
    PDF_CONTENT_CONFLICT,
    PDF_LOCATION_INVALID,
    PdfLocationError,
    canonical_paper_id,
    category_for_paper,
    derived_location_path,
    drive_relative_path,
    hash_file,
    is_engine_mvp,
    is_pdf_bytes,
    is_portable_relative_path,
    item_id_for,
    load_locations_file,
    paper_dir_for,
    root_directory_identity,
    roots_digest,
    seed_alias,
    sha256_bytes,
    sha256_json,
)
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import stage_bytes, validate_batch_id

REQUEST_SCHEMA = "video-paper-wiki.pdf-bind-request.v1"
PLAN_SCHEMA = "video-paper-wiki.pdf-bind-plan.v1"
BINDING_SCHEMA = "video-paper-wiki.pdf-binding.v1"
JOURNAL_SCHEMA = "video-paper-wiki.pdf-bind-journal.internal.v1"
DIFF_SCHEMA = "video-paper-wiki.pdf-bind-plan-diff.internal.v1"
SEED_BASIS_PATH = "docs/seed/engine-mvp.json"
SOURCE_PAGE_NOTICE = "PDF 已登记，尚未生成研究内容。"
PDF_BIND_INVALID = "PDF_BIND_INVALID"
PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
PDF_APPLY_CHANGED = "PDF_APPLY_CHANGED"
PDF_ROLLBACK_CONFLICT = "PDF_ROLLBACK_CONFLICT"
SCOPE_COUNT = 19
CATALOG_COUNT = 67


class PdfBindingError(Exception):
    """Fail-closed bind error with a stable envelope code."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(code: str, message: str, details: dict[str, Any] | None = None, *, exit_code: int = 2) -> None:
    raise PdfBindingError(code, message, details, exit_code=exit_code)


def _load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        _fail(PDF_BIND_INVALID, "JSON input is not a regular file", {"path": str(path), "reason": "symlink"})
    return parse_strict_json(path.read_bytes(), invalid_code=PDF_BIND_INVALID)


def binding_bytes(document: Mapping[str, Any]) -> bytes:
    return canonicalize(validate_document(dict(document), BINDING_SCHEMA))


def render_source_page(*, paper_id: str, title: str, source_url: str) -> bytes:
    text = (
        f"# {title}\n"
        "\n"
        f"- 标识：`{paper_id}`\n"
        f"- 标题：{title}\n"
        f"- 来源：{source_url}\n"
        "\n"
        f"{SOURCE_PAGE_NOTICE}\n"
    )
    return text.encode("utf-8")


def _walk(base: Path, relative: str) -> Path:
    if not is_portable_relative_path(relative):
        _fail(
            PDF_LOCATION_INVALID,
            "relative path is not portable",
            {"relative_path": relative, "reason": "path_escape"},
        )
    if base.is_symlink():
        _fail(PDF_LOCATION_INVALID, "root path is a symlink", {"reason": "symlink"})
    current = base
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            _fail(
                PDF_LOCATION_INVALID,
                "path component is a symlink",
                {"relative_path": relative, "reason": "symlink"},
            )
    try:
        current.resolve().relative_to(base.resolve())
    except ValueError:
        _fail(
            PDF_LOCATION_INVALID,
            "path escapes its root",
            {"relative_path": relative, "reason": "path_escape"},
        )
    return current


def _regular_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _file_sha(path: Path) -> str | None:
    if not _regular_file(path):
        return None
    digest, _size = hash_file(path)
    return digest


def _root_by_id(roots: list[Mapping[str, Any]], root_id: str) -> Mapping[str, Any]:
    found = next((row for row in roots if row["root_id"] == root_id), None)
    if found is None:
        _fail(PDF_BIND_INVALID, "root_id is not in roots.json", {"root_id": root_id, "reason": "stale_root"})
    return found


def _require_scope(paper_id: str) -> str:
    try:
        canonical = canonical_paper_id(paper_id)
    except PdfLocationError as exc:
        _fail(PDF_BIND_INVALID, exc.message, {**dict(exc.details), "reason": "missing_identity_basis"})
    from video_paper_wiki.pdf_locations import ENGINE_MVP_SEED_IDS

    if len(ENGINE_MVP_SEED_IDS) != SCOPE_COUNT or not is_engine_mvp(canonical):
        _fail(
            PDF_BIND_INVALID,
            "paper is outside the frozen 19-paper bind scope",
            {"paper_id": canonical, "reason": "out_of_scope"},
        )
    return canonical


def _catalog_identity(paper_id: str) -> dict[str, str]:
    from video_paper_wiki.parse.title import catalog_paper_ids
    from video_paper_wiki.resources import load_seed_json

    ids = catalog_paper_ids()
    if len(ids) != CATALOG_COUNT:
        _fail(
            PDF_BIND_INVALID,
            "packaged seed catalog is not the frozen 67-paper set",
            {"count": len(ids), "reason": "stale_seed"},
        )
    payload = load_seed_json("engine-mvp.json")
    papers = payload.get("papers") if type(payload) is dict else None
    if type(papers) is not list:
        _fail(PDF_BIND_INVALID, "packaged seed catalog is unreadable", {"reason": "stale_seed"})
    alias = seed_alias(paper_id)
    arxiv_id = paper_id.split(":", 1)[1]
    for item in papers:
        if type(item) is not dict or item.get("paper_id") != alias:
            continue
        title = item.get("title")
        stated_arxiv = item.get("arxiv_id")
        source_url = item.get("abs_url")
        expected_url = f"https://arxiv.org/abs/{arxiv_id}"
        if (
            type(title) is not str
            or not title.strip()
            or any(char in title for char in "\r\n")
            or stated_arxiv != arxiv_id
            or source_url != expected_url
        ):
            _fail(
                PDF_BIND_INVALID,
                "packaged seed row does not match the canonical arXiv identity",
                {"paper_id": paper_id, "reason": "stale_seed"},
            )
        return {
            "seed_paper_id": alias,
            "arxiv_id": arxiv_id,
            "title": title,
            "source_url": expected_url,
        }
    _fail(
        PDF_BIND_INVALID,
        "paper is not in the frozen 67-paper seed catalog",
        {"paper_id": paper_id, "reason": "missing_identity_basis"},
    )
    raise AssertionError("unreachable")


def _seed_row(document: object, paper_id: str) -> dict[str, str]:
    papers = document.get("papers") if type(document) is dict else None
    if type(papers) is not list:
        _fail(PDF_BIND_INVALID, "seed basis is not an engine-mvp catalog", {"reason": "stale_seed"})
    alias = seed_alias(paper_id)
    for item in papers:
        if type(item) is dict and item.get("paper_id") == alias:
            title = item.get("title")
            arxiv_id = item.get("arxiv_id")
            source_url = item.get("abs_url")
            if type(title) is not str or type(arxiv_id) is not str or type(source_url) is not str:
                break
            return {
                "seed_paper_id": alias,
                "arxiv_id": arxiv_id,
                "title": title,
                "source_url": source_url,
            }
    _fail(
        PDF_BIND_INVALID,
        "seed basis has no row for this paper",
        {"paper_id": paper_id, "reason": "missing_identity_basis"},
    )
    raise AssertionError("unreachable")


def _declared_page_identity(text: str) -> str | None:
    from video_paper_wiki.notes.merge import split_frontmatter

    yaml, _body = split_frontmatter(text)
    if yaml is None:
        return None
    declared: str | None = None
    for line in yaml.splitlines():
        if not line.startswith("paper_id:"):
            continue
        raw = line.split(":", 1)[1].strip().strip("'\"")
        if not raw:
            continue
        try:
            canonical = canonical_paper_id(raw)
        except PdfLocationError:
            _fail(
                PDF_BIND_INVALID,
                "existing note declares an unusable paper id",
                {"reason": "page_identity_conflict"},
            )
        if declared is not None and declared != canonical:
            _fail(
                PDF_BIND_INVALID,
                "existing note declares conflicting paper ids",
                {"reason": "page_identity_conflict"},
            )
        declared = canonical
    return declared


def _derived_paths(paper_id: str) -> tuple[str, str]:
    binding_rel = f"wiki/meta/pdf-bindings/{paper_page_slug(paper_id)}.json"
    page_rel = f"papers/{seed_alias(paper_id)}.md"
    return binding_rel, page_rel


def _created_page_bytes(paper_id: str) -> bytes:
    identity = _catalog_identity(paper_id)
    return render_source_page(paper_id=paper_id, title=identity["title"], source_url=identity["source_url"])


def _legal_rollback_unit(paper_id: str, *, include_page: bool) -> dict[str, Any]:
    """Derived create-set for this paper. Page bytes come from the seed row, not the credential."""

    binding_rel, page_rel = _derived_paths(paper_id)
    entries: list[dict[str, Any]] = [{"role": "binding", "path": binding_rel}]
    if include_page:
        entries.append(
            {
                "role": "page",
                "path": page_rel,
                "after_sha256": sha256_bytes(_created_page_bytes(paper_id)),
            }
        )
    return {"entries": entries}


def _checked_rollback_unit(unit: object, paper_id: str) -> dict[str, Any]:
    if type(unit) is not dict or type(unit.get("entries")) is not list:
        _fail(
            PDF_BIND_INVALID,
            "rollback unit is not the derived bind write set",
            {"paper_id": paper_id, "reason": "write_set"},
        )
    entries = unit["entries"]
    without = _legal_rollback_unit(paper_id, include_page=False)["entries"]
    with_page = _legal_rollback_unit(paper_id, include_page=True)["entries"]
    if entries != without and entries != with_page:
        _fail(
            PDF_BIND_INVALID,
            "rollback unit is not the derived bind write set",
            {"paper_id": paper_id, "reason": "write_set"},
        )
    return {"entries": [dict(row) for row in entries]}


def _file_identity(path: Path) -> tuple[int, int] | None:
    if not _regular_file(path):
        return None
    try:
        info = path.lstat()
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def _excerpt_names_arxiv(excerpt: str, arxiv_id: str) -> bool:
    return re.search(rf"(?<![0-9]){re.escape(arxiv_id)}(?:v\d+)?(?![0-9])", excerpt, flags=re.IGNORECASE) is not None


def _pdf_page_text(path: Path, page: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        _fail(PDF_BIND_INVALID, "PDF page text cannot be read", {"reason": "pdf_identity"})
    try:
        reader = PdfReader(str(path))
        if page < 1 or page > len(reader.pages):
            _fail(PDF_BIND_INVALID, "PDF identity page is outside the file", {"page": page, "reason": "pdf_identity"})
        return reader.pages[page - 1].extract_text() or ""
    except PdfBindingError:
        raise
    except Exception as exc:
        _fail(
            PDF_BIND_INVALID,
            "PDF page text cannot be read",
            {"reason": "pdf_identity", "error": type(exc).__name__},
        )


def _verify_identity_credential(
    credential: object,
    *,
    paper_id: str,
    pdf_sha256: str,
    pdf_path: Path,
) -> dict[str, Any]:
    """Re-check a page-1 excerpt against the PDF. Seed titles are not identity."""

    excerpt = credential.get("excerpt") if type(credential) is dict else None
    if (
        type(credential) is not dict
        or credential.get("method") != "pdf-internal-arxiv-id"
        or credential.get("paper_id") != paper_id
        or credential.get("pdf_sha256") != pdf_sha256
        or credential.get("page") != 1
        or type(excerpt) is not str
        or not excerpt.strip()
    ):
        _fail(
            PDF_BIND_INVALID,
            "identity credential is not a re-checkable PDF page excerpt for this paper and digest",
            {"paper_id": paper_id, "reason": "pdf_identity"},
        )
    assert type(excerpt) is str
    expected = sha256_bytes(excerpt.encode("utf-8"))
    if credential.get("excerpt_sha256") != expected:
        _fail(
            PDF_BIND_INVALID,
            "identity credential excerpt digest does not match the excerpt",
            {"paper_id": paper_id, "reason": "pdf_identity"},
        )
    arxiv_id = paper_id.split(":", 1)[1]
    if not _excerpt_names_arxiv(excerpt, arxiv_id):
        _fail(
            PDF_BIND_INVALID,
            "identity credential excerpt does not cite this paper's arXiv id",
            {"paper_id": paper_id, "reason": "pdf_identity"},
        )
    if excerpt not in _pdf_page_text(pdf_path, 1):
        _fail(
            PDF_BIND_INVALID,
            "PDF page 1 does not contain the identity excerpt",
            {"paper_id": paper_id, "reason": "pdf_identity"},
        )
    return {
        "method": "pdf-internal-arxiv-id",
        "paper_id": paper_id,
        "pdf_sha256": pdf_sha256,
        "page": 1,
        "excerpt": excerpt,
        "excerpt_sha256": expected,
    }


def _note_is_sealed_basis_or_legal_migration(
    notes: Mapping[str, Any],
    *,
    paper_id: str,
    sealed_text: str,
    raw: bytes,
    pdf_sha256: str,
) -> bool:
    """Accept the sealed note bytes, or exactly the migration transform of those bytes.

    Migration reads with `Path.read_text` universal newlines, then strips
    trailing whitespace before appending the PDF section. The sealed text keeps
    the original characters, including CRLF; `render_migrated_note` applies that
    read. Guessing `head` and `head[:-1]` drops a legal trailing blank line and
    cannot prove any other edit.
    """

    try:
        sealed_bytes = sealed_text.encode("utf-8")
    except UnicodeError:
        return False
    if raw == sealed_bytes:
        return True
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return False
    try:
        loc_path = _walk(Path(notes["path"]), derived_location_path(KIND_NOTES, paper_id))
    except PdfBindingError:
        return False
    if not _regular_file(loc_path):
        return False
    try:
        location = load_locations_file(loc_path)
    except (PdfLocationError, ContractError, OSError, UnicodeError, ValueError):
        return False
    if type(location) is not dict or location.get("paper_id") != paper_id:
        return False
    pdfs = location.get("pdfs")
    if type(pdfs) is not list or not any(
        type(row) is dict and row.get("pdf_sha256") == pdf_sha256 for row in pdfs
    ):
        return False
    from video_paper_wiki.pdf_migration import render_migrated_note

    return text == render_migrated_note(sealed_text, location)


def _read_intake(relative_path: str, *, paper_id: str, pdf_sha256: str, size_bytes: int) -> dict[str, Any]:
    from video_paper_wiki.staging import resolve_checkout_root
    from video_paper_wiki_research.contracts import ResearchError
    from video_paper_wiki_research.manual_pdf import load_intake

    checkout = resolve_checkout_root()
    path = _walk(checkout, relative_path)
    if not _regular_file(path):
        _fail(
            PDF_BIND_INVALID,
            "intake file is missing",
            {"relative_path": relative_path, "reason": "intake_only"},
        )
    try:
        _session, document, raw = load_intake(path)
    except ResearchError as exc:
        _fail(
            PDF_BIND_INVALID,
            "intake seal could not be verified",
            {"reason": "intake_only", "intake_code": exc.code},
        )
    if raw != path.read_bytes():
        _fail(PDF_BIND_INVALID, "intake bytes changed while reading", {"reason": "stale_basis"})
    data = document.get("data") if type(document.get("data")) is dict else {}
    try:
        intake_paper = canonical_paper_id(data.get("paper_id"))
    except PdfLocationError:
        _fail(PDF_BIND_INVALID, "intake paper_id is not canonical", {"reason": "cross_paper"})
    if intake_paper != paper_id:
        _fail(
            PDF_CONTENT_CONFLICT,
            "intake paper_id does not match the seed-established paper",
            {"paper_id": paper_id, "intake_paper_id": intake_paper, "reason": "cross_paper"},
        )
    if data.get("pdf_sha256") != pdf_sha256 or data.get("size_bytes") != size_bytes:
        _fail(
            PDF_CONTENT_CONFLICT,
            "intake digest or size does not match the requested PDF",
            {"paper_id": paper_id, "reason": "digest_mismatch"},
        )
    blob_rel = data.get("blob_path")
    if blob_rel != f".work/blobs/{pdf_sha256}":
        _fail(PDF_BIND_INVALID, "intake blob path is not the sealed digest path", {"reason": "digest_mismatch"})
    blob = _walk(checkout, blob_rel)
    if not _regular_file(blob):
        _fail(PDF_BIND_INVALID, "intake blob is missing", {"reason": "digest_mismatch"})
    blob_digest, blob_size = hash_file(blob)
    if blob_digest != pdf_sha256 or blob_size != size_bytes:
        _fail(
            PDF_CONTENT_CONFLICT,
            "intake blob bytes do not match the sealed digest",
            {"paper_id": paper_id, "reason": "digest_mismatch"},
        )
    return document


def _read_local_pdf(roots: list[Mapping[str, Any]], local_ref: Mapping[str, Any], *, pdf_sha256: str, size_bytes: int) -> Path:
    root = _root_by_id(roots, str(local_ref["root_id"]))
    if root["role"] != "source-only":
        _fail(
            PDF_BIND_INVALID,
            "PDF local_ref must be a source-only root",
            {"root_id": root["root_id"], "reason": "path_escape"},
        )
    path = _walk(Path(root["path"]), str(local_ref["relative_path"]))
    if not _regular_file(path):
        _fail(
            PDF_BIND_INVALID,
            "local PDF is missing",
            {"relative_path": local_ref["relative_path"], "reason": "digest_mismatch"},
        )
    try:
        with path.open("rb") as handle:
            head = handle.read(5)
    except OSError:
        _fail(PDF_BIND_INVALID, "local PDF is unreadable", {"reason": "digest_mismatch"})
    if not is_pdf_bytes(head):
        _fail(PDF_BIND_INVALID, "local_ref is not a PDF", {"reason": "digest_mismatch"})
    digest, size = hash_file(path)
    if digest != pdf_sha256 or size != size_bytes:
        _fail(
            PDF_CONTENT_CONFLICT,
            "local PDF bytes do not match the requested digest",
            {"relative_path": local_ref["relative_path"], "reason": "digest_mismatch"},
        )
    return path


def _sealed_existing_note(
    basis: Mapping[str, Any],
    basis_raw: bytes,
    scanned: str,
    notes: Mapping[str, Any],
    paper_id: str,
    pdf_sha256: str,
) -> str:
    """Return the note text sealed at scan time, after checking the live page.

    The first observation copies the file itself and requires that exact digest.
    Later reads reuse `scanned_text` from the binding and accept only that text
    or `render_migrated_note` of it. A body edit matches neither.
    """

    supplied = basis.get("scanned_text")
    if type(supplied) is str:
        try:
            sealed_bytes = supplied.encode("utf-8")
        except UnicodeError:
            _fail(PDF_BIND_INVALID, "sealed note basis is not UTF-8", {"reason": "stale_basis"})
        if sha256_bytes(sealed_bytes) != scanned:
            _fail(
                PDF_BIND_INVALID,
                "sealed note basis does not match its digest",
                {"relative_path": basis.get("relative_path"), "reason": "stale_basis"},
            )
        if not _note_is_sealed_basis_or_legal_migration(
            notes,
            paper_id=paper_id,
            sealed_text=supplied,
            raw=basis_raw,
            pdf_sha256=pdf_sha256,
        ):
            _fail(
                PDF_APPLY_CHANGED,
                "identity basis changed after it was scanned",
                {"relative_path": basis.get("relative_path"), "reason": "stale_basis"},
            )
        return supplied
    if sha256_bytes(basis_raw) != scanned:
        _fail(
            PDF_APPLY_CHANGED,
            "identity basis changed after it was scanned",
            {"relative_path": basis.get("relative_path"), "reason": "stale_basis"},
        )
    try:
        return basis_raw.decode("utf-8")
    except UnicodeError:
        _fail(PDF_BIND_INVALID, "existing note is not UTF-8", {"reason": "page_identity_conflict"})


def _binding_from_live(
    item: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    notes: Mapping[str, Any],
) -> dict[str, Any]:
    paper_id = _require_scope(str(item["paper_id"]))
    identity = _catalog_identity(paper_id)
    if type(item.get("identity_credential")) is not dict:
        _fail(PDF_BIND_INVALID, "identity credential is required", {"reason": "pdf_identity"})
    basis = item.get("identity_basis")
    if type(basis) is not dict:
        _fail(PDF_BIND_INVALID, "identity basis is required", {"reason": "missing_identity_basis"})
    kind = basis.get("kind")
    alias = seed_alias(paper_id)
    page_rel = f"papers/{alias}.md"
    if kind == "seed":
        if basis.get("relative_path") != SEED_BASIS_PATH:
            _fail(PDF_BIND_INVALID, "seed basis path is fixed", {"reason": "missing_identity_basis"})
        basis_root = _root_by_id(roots, str(basis.get("root_id")))
        if basis_root["kind"] != "repository" or basis_root["role"] != "source-only":
            _fail(
                PDF_BIND_INVALID,
                "seed basis must be a source-only repository root",
                {"reason": "stale_root"},
            )
    elif kind == "existing-note":
        if basis.get("relative_path") != page_rel or basis.get("root_id") != notes["root_id"]:
            _fail(
                PDF_BIND_INVALID,
                "existing-note basis must be the target note page",
                {"reason": "missing_identity_basis"},
            )
        basis_root = notes
    else:
        _fail(PDF_BIND_INVALID, "identity basis kind is not seed or existing-note", {"reason": "missing_identity_basis"})
    basis_path = _walk(Path(basis_root["path"]), str(basis["relative_path"]))
    if not _regular_file(basis_path):
        _fail(
            PDF_BIND_INVALID,
            "identity basis file is missing",
            {"relative_path": basis.get("relative_path"), "reason": "missing_identity_basis"},
        )
    basis_raw = basis_path.read_bytes()
    scanned = basis.get("scanned_sha256")
    if type(scanned) is not str:
        _fail(PDF_BIND_INVALID, "identity basis digest is required", {"reason": "missing_identity_basis"})
    if kind == "seed":
        try:
            seed_document = parse_strict_json(basis_raw, invalid_code=PDF_BIND_INVALID)
        except PdfBindingError:
            _fail(PDF_BIND_INVALID, "seed basis is not JSON", {"reason": "stale_seed"})
        row = _seed_row(seed_document, paper_id)
        if row != identity:
            _fail(
                PDF_APPLY_CHANGED,
                "seed basis row does not match the packaged catalog",
                {"paper_id": paper_id, "reason": "stale_seed"},
            )
        if sha256_bytes(basis_raw) != scanned:
            _fail(
                PDF_APPLY_CHANGED,
                "identity basis changed after it was scanned",
                {"relative_path": basis.get("relative_path"), "reason": "stale_basis"},
            )
    else:
        try:
            note_text = basis_raw.decode("utf-8")
        except UnicodeError:
            _fail(PDF_BIND_INVALID, "existing note is not UTF-8", {"reason": "page_identity_conflict"})
        declared = _declared_page_identity(note_text)
        if declared is not None and declared != paper_id:
            _fail(
                PDF_BIND_INVALID,
                "existing note identity does not match the requested paper",
                {"paper_id": paper_id, "reason": "page_identity_conflict"},
            )
    pdf_sha = item.get("pdf_sha256")
    size = item.get("size_bytes")
    if type(pdf_sha) is not str or type(size) is not int or isinstance(size, bool):
        _fail(PDF_BIND_INVALID, "pdf digest and size are required", {"reason": "digest_mismatch"})
    local_ref = item.get("local_ref")
    if type(local_ref) is not dict:
        _fail(PDF_BIND_INVALID, "local_ref is required", {"reason": "digest_mismatch"})
    pdf_path = _read_local_pdf(roots, local_ref, pdf_sha256=pdf_sha, size_bytes=size)
    sealed_note: str | None = None
    if kind == "existing-note":
        sealed_note = _sealed_existing_note(basis, basis_raw, scanned, notes, paper_id, pdf_sha)
    credential = _verify_identity_credential(
        item.get("identity_credential"),
        paper_id=paper_id,
        pdf_sha256=pdf_sha,
        pdf_path=pdf_path,
    )
    intake_ref = item.get("intake")
    if type(intake_ref) is not dict or type(intake_ref.get("relative_path")) is not str:
        _fail(PDF_BIND_INVALID, "intake reference is required", {"reason": "intake_only"})
    intake = _read_intake(
        intake_ref["relative_path"],
        paper_id=paper_id,
        pdf_sha256=pdf_sha,
        size_bytes=size,
    )
    binding = {
        "schema": BINDING_SCHEMA,
        "paper_id": paper_id,
        "pdf_sha256": pdf_sha,
        "size_bytes": size,
        "media_type": "application/pdf",
        "local_ref": {"root_id": local_ref["root_id"], "relative_path": local_ref["relative_path"]},
        "identity_basis": {
            "kind": kind,
            "root_id": basis["root_id"],
            "relative_path": basis["relative_path"],
            "scanned_sha256": scanned,
            **({"scanned_text": sealed_note} if sealed_note is not None else {}),
        },
        "intake": {
            "relative_path": intake_ref["relative_path"],
            "content_sha256": intake["content_sha256"],
            "intake_id": intake["id"],
        },
        "identity_credential": credential,
        "source_url": identity["source_url"],
        "registration": {
            "role": "pdf-location-source",
            "capture_authorized": False,
            "receipt_backed": False,
        },
    }
    stored_unit = item.get("rollback_unit")
    if stored_unit is not None:
        binding["rollback_unit"] = _checked_rollback_unit(stored_unit, paper_id)
        validate_document(binding, BINDING_SCHEMA)
    return binding


def _request_from_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "paper_id": binding["paper_id"],
        "identity_basis": dict(binding["identity_basis"]),
        "intake": {"relative_path": binding["intake"]["relative_path"]},
        "local_ref": dict(binding["local_ref"]),
        "pdf_sha256": binding["pdf_sha256"],
        "size_bytes": binding["size_bytes"],
        "identity_credential": dict(binding["identity_credential"]),
        "rollback_unit": {
            "entries": [dict(row) for row in binding["rollback_unit"]["entries"]],
        },
    }


def _page_decision(
    notes: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    paper_id = str(binding["paper_id"])
    alias = seed_alias(paper_id)
    page_rel = f"papers/{alias}.md"
    slug = paper_page_slug(paper_id)
    binding_rel = f"wiki/meta/pdf-bindings/{slug}.json"
    if page_rel != f"papers/{alias}.md" or binding_rel != f"wiki/meta/pdf-bindings/{slug}.json":
        _fail(PDF_BIND_INVALID, "derived bind paths are not portable", {"reason": "path_escape"})
    base = Path(notes["path"])
    page_path = _walk(base, page_rel)
    binding_path = _walk(base, binding_rel)
    payload = binding_bytes(binding)
    after_binding = sha256_bytes(payload)
    if _regular_file(binding_path):
        current = binding_path.read_bytes()
        if current != payload:
            _fail(
                PDF_CONTENT_CONFLICT,
                "existing binding does not match this plan",
                {"path": binding_rel, "reason": "cross_paper"},
            )
        before_binding: str | None = after_binding
    elif binding_path.exists():
        _fail(PDF_LOCATION_INVALID, "binding path is not a regular file", {"path": binding_rel, "reason": "symlink"})
    else:
        before_binding = None
    if _regular_file(page_path):
        try:
            text = page_path.read_text(encoding="utf-8")
        except UnicodeError:
            _fail(PDF_BIND_INVALID, "existing note is not UTF-8", {"reason": "page_identity_conflict"})
        declared = _declared_page_identity(text)
        if declared is not None and declared != paper_id:
            _fail(
                PDF_BIND_INVALID,
                "existing page identity does not match the binding",
                {"path": page_rel, "reason": "page_identity_conflict"},
            )
        page_sha = sha256_bytes(page_path.read_bytes())
        return {
            "binding_path": binding_rel,
            "page_path": page_rel,
            "page_action": "preserve",
            "before_binding_sha256": before_binding,
            "after_binding_sha256": after_binding,
            "before_page_sha256": page_sha,
            "after_page_sha256": page_sha,
            "page_text": None,
            "binding_payload": payload,
        }
    if page_path.exists():
        _fail(PDF_LOCATION_INVALID, "page path is not a regular file", {"path": page_rel, "reason": "symlink"})
    page_payload = _created_page_bytes(paper_id)
    if page_payload != render_source_page(
        paper_id=paper_id,
        title=_catalog_identity(paper_id)["title"],
        source_url=str(binding["source_url"]),
    ):
        _fail(PDF_BIND_INVALID, "source page does not match the seed identity", {"reason": "stale_seed"})
    if SOURCE_PAGE_NOTICE.encode("utf-8") not in page_payload:
        _fail(PDF_BIND_INVALID, "source page is missing the registration notice", {"reason": "missing_identity_basis"})
    return {
        "binding_path": binding_rel,
        "page_path": page_rel,
        "page_action": "create",
        "before_binding_sha256": before_binding,
        "after_binding_sha256": after_binding,
        "before_page_sha256": None,
        "after_page_sha256": sha256_bytes(page_payload),
        "page_text": page_payload.decode("utf-8"),
        "binding_payload": payload,
    }


def _reject_request_conflicts(items: list[Mapping[str, Any]]) -> None:
    papers: set[str] = set()
    digests: dict[str, str] = {}
    refs: set[tuple[str, str]] = set()
    for item in items:
        paper_id = str(item["paper_id"])
        if paper_id in papers:
            _fail(PDF_CONTENT_CONFLICT, "request binds one paper more than once", {"paper_id": paper_id, "reason": "cross_paper"})
        papers.add(paper_id)
        digest = str(item["pdf_sha256"])
        previous = digests.get(digest)
        if previous is not None and previous != paper_id:
            _fail(
                PDF_CONTENT_CONFLICT,
                "one PDF digest is bound to more than one paper",
                {"pdf_sha256": digest, "reason": "cross_paper"},
            )
        digests[digest] = paper_id
        local_ref = item["local_ref"]
        key = (str(local_ref["root_id"]), str(local_ref["relative_path"]))
        if key in refs:
            _fail(PDF_CONTENT_CONFLICT, "one local_ref is bound more than once", {"reason": "cross_paper"})
        refs.add(key)


def _trusted_bindings(notes: Mapping[str, Any]) -> list[dict[str, Any]]:
    base = Path(notes["path"])
    directory = base / "wiki" / "meta" / "pdf-bindings"
    if directory.is_symlink() or not directory.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if not _regular_file(path):
            continue
        try:
            parsed = validate_document(
                parse_strict_json(path.read_bytes(), invalid_code=PDF_BIND_INVALID),
                BINDING_SCHEMA,
            )
        except (PdfBindingError, ContractError, OSError, UnicodeError, ValueError):
            continue
        found.append(parsed)
    return found


def _reject_registered_conflicts(items: list[Mapping[str, Any]], notes: Mapping[str, Any]) -> None:
    """Refuse a second paper/digest/local_ref against bindings already on the target."""

    existing = _trusted_bindings(notes)
    for item in items:
        local_ref = item["local_ref"]
        paper_id = str(item["paper_id"])
        digest = str(item["pdf_sha256"])
        ref = (str(local_ref["root_id"]), str(local_ref["relative_path"]))
        for prior in existing:
            prior_ref = (str(prior["local_ref"]["root_id"]), str(prior["local_ref"]["relative_path"]))
            same_paper = prior["paper_id"] == paper_id
            same_digest = prior["pdf_sha256"] == digest
            same_ref = prior_ref == ref
            if same_paper and same_digest and same_ref:
                continue
            if (same_digest and not same_paper) or (same_ref and not same_paper) or (same_paper and not (same_digest and same_ref)):
                _fail(
                    PDF_CONTENT_CONFLICT,
                    "existing registration already binds this paper, PDF digest, or local_ref",
                    {
                        "paper_id": paper_id,
                        "existing_paper_id": prior["paper_id"],
                        "pdf_sha256": digest,
                        "reason": "cross_paper",
                    },
                )


def _evaluate_item(
    item: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    notes: Mapping[str, Any],
) -> dict[str, Any]:
    binding = _binding_from_live(item, roots, notes)
    _binding_rel, page_rel = _derived_paths(str(binding["paper_id"]))
    page_path = _walk(Path(notes["path"]), page_rel)
    if page_path.exists() and not _regular_file(page_path):
        _fail(PDF_LOCATION_INVALID, "page path is not a regular file", {"path": page_rel, "reason": "symlink"})
    include_page = not _regular_file(page_path)
    binding["rollback_unit"] = _legal_rollback_unit(str(binding["paper_id"]), include_page=include_page)
    decision = _page_decision(notes, binding)
    if (decision["page_action"] == "create") != include_page:
        _fail(
            PDF_APPLY_CHANGED,
            "page action changed while deriving the bind write set",
            {"paper_id": binding["paper_id"], "reason": "parallel_edit"},
        )
    unit_entries = binding["rollback_unit"]["entries"]
    if decision["binding_path"] != unit_entries[0]["path"] or decision["page_path"] != page_rel:
        _fail(PDF_BIND_INVALID, "plan destination is not the derived bind path", {"reason": "path_escape"})
    if include_page and decision["after_page_sha256"] != unit_entries[1]["after_sha256"]:
        _fail(PDF_BIND_INVALID, "created page digest is not the seed source page", {"reason": "write_set"})
    item_id = sha256_json(
        {
            "paper_id": binding["paper_id"],
            "pdf_sha256": binding["pdf_sha256"],
            "binding_path": decision["binding_path"],
        }
    )
    return {
        "item_id": item_id,
        "paper_id": binding["paper_id"],
        "binding_path": decision["binding_path"],
        "page_path": decision["page_path"],
        "page_action": decision["page_action"],
        "before_binding_sha256": decision["before_binding_sha256"],
        "after_binding_sha256": decision["after_binding_sha256"],
        "before_page_sha256": decision["before_page_sha256"],
        "after_page_sha256": decision["after_page_sha256"],
        "page_text": decision["page_text"],
        "binding": binding,
    }


def _seal_plan(plan: dict[str, Any]) -> dict[str, Any]:
    plan["plan_sha256"] = sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})
    return validate_document(plan, PLAN_SCHEMA)


def _notes_target(roots: list[Mapping[str, Any]], root_id: str) -> Mapping[str, Any]:
    root = _root_by_id(roots, root_id)
    if root["kind"] != KIND_NOTES or root["role"] != "target":
        _fail(
            PDF_BIND_INVALID,
            "bind writes require kind=notes-vault and role=target",
            {"root_id": root_id, "kind": root["kind"], "role": root["role"], "reason": "stale_root"},
        )
    return root


def prepare_bindings(*, roots_path: Path, root_id: str, request_path: Path, batch_id: str) -> dict[str, Any]:
    """Read originals and the target. Write only `.work/<batch>/pdf-bind/`."""

    from video_paper_wiki.pdf_locations import parse_roots

    batch = validate_batch_id(batch_id)
    request_raw = Path(request_path).read_bytes() if _regular_file(Path(request_path)) else None
    if request_raw is None:
        _fail(PDF_BIND_INVALID, "bind request is not a regular file", {"reason": "symlink"})
    request = validate_document(parse_strict_json(request_raw, invalid_code=PDF_BIND_INVALID), REQUEST_SCHEMA)
    roots = parse_roots(_load_json(Path(roots_path)))
    notes = _notes_target(roots, root_id)
    items = list(request["items"])
    _reject_request_conflicts(items)
    _reject_registered_conflicts(items, notes)
    evaluated = [_evaluate_item(item, roots, notes) for item in items]
    plan = {
        "schema": PLAN_SCHEMA,
        "batch_id": batch,
        "root_id": root_id,
        "roots_sha256": roots_digest(roots),
        "request_sha256": sha256_bytes(request_raw),
        "plan_sha256": "0" * 64,
        "items": evaluated,
        "blocked": [],
    }
    validated = _seal_plan(plan)
    _stage_bind(batch, "plan.json", validated)
    diff = {
        "schema": DIFF_SCHEMA,
        "plan_sha256": validated["plan_sha256"],
        "item_count": len(evaluated),
        "items": [
            {
                "paper_id": item["paper_id"],
                "binding_path": item["binding_path"],
                "page_path": item["page_path"],
                "page_action": item["page_action"],
                "before_binding_sha256": item["before_binding_sha256"],
                "after_binding_sha256": item["after_binding_sha256"],
                "before_page_sha256": item["before_page_sha256"],
                "after_page_sha256": item["after_page_sha256"],
            }
            for item in evaluated
        ],
    }
    _stage_bind(batch, "diff.json", diff)
    return validated


def _stage_bind(batch_id: str, name: str, document: Mapping[str, Any]) -> Path:
    result = stage_bytes(batch_id=batch_id, relative=("pdf-bind", name), data=canonicalize(document))
    return result.path


def _approved_plan(plan: Mapping[str, Any], approved_plan_sha256: str) -> dict[str, Any]:
    if type(plan) is not dict:
        _fail(PDF_BIND_INVALID, "plan must be an object")
    recomputed = sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})
    if approved_plan_sha256 != recomputed or plan.get("plan_sha256") != recomputed:
        _fail(
            PLAN_HASH_MISMATCH,
            "approved-plan-sha256 does not match the recomputed plan content digest",
            {
                "approved_plan_sha256": approved_plan_sha256,
                "plan_sha256": plan.get("plan_sha256"),
                "recomputed_plan_sha256": recomputed,
                "reason": "stale_root",
            },
        )
    return validate_document(dict(plan), PLAN_SCHEMA)


def _assert_preserved_page(path: Path, paper_id: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        _fail(PDF_BIND_INVALID, "existing note is not UTF-8", {"reason": "page_identity_conflict"})
    declared = _declared_page_identity(text)
    if declared is not None and declared != paper_id:
        _fail(
            PDF_BIND_INVALID,
            "existing page identity does not match the binding",
            {"paper_id": paper_id, "reason": "page_identity_conflict"},
        )


def _recheck_item(item: Mapping[str, Any], roots: list[Mapping[str, Any]], notes: Mapping[str, Any]) -> dict[str, Any]:
    """Accept the planned before state or the already-applied after state."""

    live = _binding_from_live(_request_from_binding(item["binding"]), roots, notes)
    expected_unit = _legal_rollback_unit(str(item["paper_id"]), include_page=item["page_action"] == "create")
    if live.get("rollback_unit") != expected_unit:
        _fail(
            PDF_BIND_INVALID,
            "approved binding write set is not the derived bind unit",
            {"paper_id": item["paper_id"], "reason": "write_set"},
        )
    payload = binding_bytes(live)
    if payload != binding_bytes(item["binding"]) or sha256_bytes(payload) != item["after_binding_sha256"]:
        _fail(
            PDF_APPLY_CHANGED,
            "live inputs no longer match the approved binding",
            {"paper_id": item["paper_id"], "reason": "stale_basis"},
        )
    alias = seed_alias(str(item["paper_id"]))
    slug = paper_page_slug(str(item["paper_id"]))
    if item["page_path"] != f"papers/{alias}.md" or item["binding_path"] != f"wiki/meta/pdf-bindings/{slug}.json":
        _fail(PDF_BIND_INVALID, "plan destination is not the derived bind path", {"reason": "path_escape"})
    base = Path(notes["path"])
    binding_path = _walk(base, str(item["binding_path"]))
    page_path = _walk(base, str(item["page_path"]))
    live_binding = _file_sha(binding_path)
    if live_binding not in {item["before_binding_sha256"], item["after_binding_sha256"]}:
        _fail(
            PDF_APPLY_CHANGED,
            "binding file changed after prepare",
            {"path": item["binding_path"], "reason": "parallel_edit"},
        )
    live_page = _file_sha(page_path)
    page_payload: bytes | None = None
    if item["page_action"] == "preserve":
        if live_page != item["after_page_sha256"] or item["before_page_sha256"] != item["after_page_sha256"]:
            _fail(
                PDF_APPLY_CHANGED,
                "preserved note changed after prepare",
                {"path": item["page_path"], "reason": "parallel_edit"},
            )
        _assert_preserved_page(page_path, str(item["paper_id"]))
    elif item["page_action"] == "create":
        if type(item["page_text"]) is not str or SOURCE_PAGE_NOTICE not in item["page_text"]:
            _fail(PDF_BIND_INVALID, "create action is missing the source-page text", {"reason": "missing_identity_basis"})
        page_payload = item["page_text"].encode("utf-8")
        if sha256_bytes(page_payload) != item["after_page_sha256"] or item["before_page_sha256"] is not None:
            _fail(PDF_BIND_INVALID, "create action digests do not match the source page", {"reason": "stale_page"})
        if live_page not in {None, item["after_page_sha256"]}:
            _fail(
                PDF_APPLY_CHANGED,
                "source page changed after prepare",
                {"path": item["page_path"], "reason": "parallel_edit"},
            )
    else:
        _fail(PDF_BIND_INVALID, "page action is not create or preserve", {"reason": "stale_page"})
    return {"binding_payload": payload, "page_payload": page_payload}


def _pin_readonly(path: Path, sha256: str, **meta: str) -> dict[str, Any]:
    identity = _file_identity(path)
    live = _file_sha(path)
    if identity is None or live != sha256:
        _fail(
            PDF_APPLY_CHANGED,
            "read-only bind precondition changed",
            {**meta, "reason": "parallel_edit"},
        )
    return {"path": path, "sha256": sha256, "identity": identity, **meta}


def _readonly_snapshot(
    plan: Mapping[str, Any],
    roots: list[Mapping[str, Any]],
    notes: Mapping[str, Any],
    bound_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve pages, seed files, and source PDFs stay fixed for the whole commit."""

    files: list[dict[str, Any]] = []
    for item in plan["items"]:
        binding = item["binding"]
        if item["page_action"] == "preserve":
            page_path = _walk(Path(notes["path"]), str(item["page_path"]))
            files.append(
                _pin_readonly(
                    page_path,
                    str(item["after_page_sha256"]),
                    kind="preserve-page",
                    paper_id=str(item["paper_id"]),
                )
            )
        basis = binding["identity_basis"]
        if basis["kind"] == "seed":
            basis_root = _root_by_id(roots, str(basis["root_id"]))
            files.append(
                _pin_readonly(
                    _walk(Path(basis_root["path"]), str(basis["relative_path"])),
                    str(basis["scanned_sha256"]),
                    kind="seed-basis",
                    paper_id=str(item["paper_id"]),
                )
            )
        local_ref = binding["local_ref"]
        pdf_root = _root_by_id(roots, str(local_ref["root_id"]))
        files.append(
            _pin_readonly(
                _walk(Path(pdf_root["path"]), str(local_ref["relative_path"])),
                str(binding["pdf_sha256"]),
                kind="local-pdf",
                paper_id=str(item["paper_id"]),
            )
        )
    return {"notes": notes, "root": dict(bound_identity), "files": files}


def _assert_readonly_snapshot(snapshot: Mapping[str, Any]) -> None:
    notes = snapshot["notes"]
    if root_directory_identity(notes["path"]) != snapshot["root"]:
        _fail(PDF_APPLY_CHANGED, "target root directory identity changed during apply", {"reason": "stale_root"})
    for item in snapshot["files"]:
        if _file_identity(item["path"]) != item["identity"] or _file_sha(item["path"]) != item["sha256"]:
            _fail(
                PDF_APPLY_CHANGED,
                "read-only bind precondition changed during apply",
                {"kind": item["kind"], "paper_id": item["paper_id"], "reason": "parallel_edit"},
            )
        if item["kind"] == "preserve-page":
            _assert_preserved_page(item["path"], str(item["paper_id"]))


def _journal_file(root_path: Path, plan_sha256: str) -> Path:
    return root_path / ".work" / "pdf-bind" / f"journal-{plan_sha256[:16]}.json"


def apply_bind_plan(
    *,
    plan_path: Path,
    roots_path: Path,
    root_id: str,
    approved_plan_sha256: str,
    confirm: bool,
) -> dict[str, Any]:
    from video_paper_wiki.pdf_locations import parse_roots
    from video_paper_wiki.pdf_migration import (
        _INSTALL_GUARDS,
        _acquire_lock,
        _atomic_write,
        _pop_install_guard,
        _push_install_guard,
        _restore_applied_writes,
    )

    if not confirm:
        _fail(HUMAN_APPROVAL_REQUIRED, "interactive confirmation is required", {"next_action": "confirm_interactively"})
    plan = _approved_plan(_load_json(Path(plan_path)), approved_plan_sha256)
    roots = parse_roots(_load_json(Path(roots_path)))
    if roots_digest(roots) != plan["roots_sha256"]:
        _fail(PDF_APPLY_CHANGED, "roots.json no longer matches the approved plan", {"reason": "stale_root"})
    if plan["root_id"] != root_id:
        _fail(PDF_BIND_INVALID, "plan root_id does not match the requested root", {"reason": "stale_root"})
    notes = _notes_target(roots, root_id)
    base = Path(notes["path"])
    bound_identity = root_directory_identity(notes["path"])
    if not bound_identity.get("directory"):
        _fail(PDF_APPLY_CHANGED, "target root is not a directory", {"reason": "stale_root"})
    lock = _acquire_lock(base)
    applied: list[dict[str, Any]] = []
    try:
        if root_directory_identity(notes["path"]) != bound_identity:
            _fail(PDF_APPLY_CHANGED, "target root directory identity changed", {"reason": "stale_root"})
        decisions = [_recheck_item(item, roots, notes) for item in plan["items"]]
        _reject_registered_conflicts(
            [
                {
                    "paper_id": item["paper_id"],
                    "pdf_sha256": item["binding"]["pdf_sha256"],
                    "local_ref": item["binding"]["local_ref"],
                }
                for item in plan["items"]
            ],
            notes,
        )
        snapshot = _readonly_snapshot(plan, roots, notes, bound_identity)
        work = base / ".work"
        if work.is_symlink():
            _fail(PDF_LOCATION_INVALID, "target .work is a symlink", {"reason": "symlink"})
        writes: list[dict[str, Any]] = []
        for item, decision in zip(plan["items"], decisions, strict=True):
            binding_path = _walk(base, item["binding_path"])
            page_path = _walk(base, item["page_path"])
            if _file_sha(binding_path) != item["after_binding_sha256"]:
                writes.append(
                    {
                        "item_id": item["item_id"],
                        "paper_id": item["paper_id"],
                        "path": item["binding_path"],
                        "target": binding_path,
                        "data": decision["binding_payload"],
                        "before_sha256": item["before_binding_sha256"],
                        "after_sha256": item["after_binding_sha256"],
                        "before_raw": None,
                    }
                )
            if item["page_action"] == "create" and _file_sha(page_path) != item["after_page_sha256"]:
                writes.append(
                    {
                        "item_id": item["item_id"],
                        "paper_id": item["paper_id"],
                        "path": item["page_path"],
                        "target": page_path,
                        "data": decision["page_payload"],
                        "before_sha256": item["before_page_sha256"],
                        "after_sha256": item["after_page_sha256"],
                        "before_raw": None,
                    }
                )
        journal_path = _journal_file(base, plan["plan_sha256"])
        journal_touched = False
        prior_journal: bytes | None = None
        try:
            for write in writes:
                if root_directory_identity(notes["path"]) != bound_identity:
                    _fail(PDF_APPLY_CHANGED, "target root directory identity changed during apply", {"reason": "stale_root"})
                live = _file_sha(write["target"])
                if live != write["before_sha256"]:
                    _fail(
                        PDF_APPLY_CHANGED,
                        "writeset changed during apply",
                        {"path": write["path"], "reason": "parallel_edit"},
                    )
                _push_install_guard(write, root=notes, bound_identity=bound_identity)
                try:
                    _atomic_write(write["target"], write["data"])
                finally:
                    _pop_install_guard()
                if _file_sha(write["target"]) != write["after_sha256"]:
                    _fail(
                        PDF_APPLY_CHANGED,
                        "write did not produce the planned after digest",
                        {"path": write["path"], "reason": "parallel_edit"},
                    )
                applied.append(write)
                _assert_readonly_snapshot(snapshot)
            _assert_readonly_snapshot(snapshot)
            journal = _load_journal(journal_path, plan=plan, notes=notes, identity=bound_identity)
            _remember_created(journal, plan, base)
            if journal_path.parent.is_symlink():
                _fail(PDF_LOCATION_INVALID, "bind journal parent is a symlink", {"reason": "symlink"})
            journal_payload = canonicalize(journal) + b"\n"
            prior_journal = journal_path.read_bytes() if _regular_file(journal_path) else None
            journal_touched = True
            _atomic_write(journal_path, journal_payload)
            _assert_commit_boundary(snapshot, journal_path, journal_payload)
            result = {
                "root_id": root_id,
                "kind": notes["kind"],
                "plan_sha256": plan["plan_sha256"],
                "journal_path": str(journal_path),
                "journal_sha256": sha256_bytes(journal_path.read_bytes()),
                "results": [{"paper_id": item["paper_id"], "state": "bound"} for item in plan["items"]],
                "keep_local": True,
            }
            _assert_commit_boundary(snapshot, journal_path, journal_payload)
            return result
        except Exception:
            _restore_applied_writes(applied, root=notes, bound_identity=bound_identity)
            applied.clear()
            if journal_touched:
                _revert_journal_install(journal_path, prior_journal, _atomic_write)
            raise
    finally:
        _INSTALL_GUARDS.clear()
        lock.close()


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(canonicalize(value))


def _plan_content_sha(plan: Mapping[str, Any]) -> str:
    return sha256_json({key: value for key, value in plan.items() if key != "plan_sha256"})


def _creation_entries(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Files this approved plan created. Derived from the plan, not from a journal list."""

    entries: list[dict[str, Any]] = []
    for item in plan["items"]:
        paper_id = str(item["paper_id"])
        if item["before_binding_sha256"] is None:
            entries.append(
                {
                    "paper_id": paper_id,
                    "role": "binding",
                    "path": str(item["binding_path"]),
                    "before_sha256": None,
                    "after_sha256": str(item["after_binding_sha256"]),
                }
            )
        if item["page_action"] == "create" and item["before_page_sha256"] is None:
            entries.append(
                {
                    "paper_id": paper_id,
                    "role": "page",
                    "path": str(item["page_path"]),
                    "before_sha256": None,
                    "after_sha256": str(item["after_page_sha256"]),
                }
            )
    return entries


def _load_journal(
    journal_path: Path,
    *,
    plan: Mapping[str, Any],
    notes: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    if journal_path.name != f"journal-{plan['plan_sha256'][:16]}.json":
        _fail(PDF_BIND_INVALID, "bind journal path is not the approved plan journal", {"reason": "write_set"})
    return {
        "schema": JOURNAL_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "root_id": notes["root_id"],
        "kind": notes["kind"],
        "request_sha256": plan["request_sha256"],
        "roots_sha256": plan["roots_sha256"],
        "root_identity": dict(identity),
        "approved_plan": _json_copy(plan),
        "entries": [],
    }


def _remember_created(journal: dict[str, Any], plan: Mapping[str, Any], base: Path) -> None:
    expected = _creation_entries(plan)
    items = {str(item["paper_id"]): item for item in plan["items"]}
    for entry in expected:
        item = items[str(entry["paper_id"])]
        paper_id = str(item["paper_id"])
        unit = _checked_rollback_unit(item["binding"]["rollback_unit"], paper_id)
        if unit["entries"][0]["path"] != item["binding_path"]:
            _fail(PDF_BIND_INVALID, "binding path is not the derived bind path", {"reason": "write_set"})
        if entry["role"] == "page":
            page_rows = [row for row in unit["entries"] if row["role"] == "page"]
            if (
                len(page_rows) != 1
                or page_rows[0]["path"] != item["page_path"]
                or page_rows[0].get("after_sha256") != item["after_page_sha256"]
            ):
                _fail(PDF_BIND_INVALID, "created page is not in the derived bind write set", {"reason": "write_set"})
        target = _walk(base, str(entry["path"]))
        if _file_identity(target) is None or _file_sha(target) != entry["after_sha256"]:
            _fail(
                PDF_APPLY_CHANGED,
                "created bind file is not at the planned digest",
                {"path": entry["path"], "reason": "parallel_edit"},
            )
    journal["entries"] = [dict(row) for row in expected]
    journal["derived_write_set"] = [dict(row) for row in expected]


def _assert_commit_boundary(snapshot: Mapping[str, Any], journal_path: Path, payload: bytes) -> None:
    """Read-only preconditions must still hold after the journal success record is installed."""

    _assert_readonly_snapshot(snapshot)
    if not _regular_file(journal_path) or journal_path.read_bytes() != payload:
        _fail(
            PDF_APPLY_CHANGED,
            "bind journal commit did not keep the approved success record",
            {"reason": "parallel_edit"},
        )


def _revert_journal_install(path: Path, prior: bytes | None, atomic_write) -> None:
    if prior is None:
        if path.exists() or path.is_symlink():
            path.unlink()
        return
    if _regular_file(path) and path.read_bytes() == prior:
        return
    atomic_write(path, prior)


def _journal_entry_ok(entry: object) -> dict[str, Any]:
    if type(entry) is not dict:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal entry is not an object", {"reason": "write_set"})
    paper_raw = entry.get("paper_id")
    role = entry.get("role")
    relative = entry.get("path")
    before = entry.get("before_sha256")
    after = entry.get("after_sha256")
    if type(paper_raw) is not str or role not in {"binding", "page"} or type(relative) is not str:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal entry is outside the derived write set", {"reason": "write_set"})
    if before is not None or type(after) is not str or len(after) != 64:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal entry is outside the derived write set", {"reason": "write_set"})
    paper_id = _require_scope(paper_raw)
    binding_rel, page_rel = _derived_paths(paper_id)
    expected_path = binding_rel if role == "binding" else page_rel
    if relative != expected_path:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind journal path is not the derived binding or source page",
            {"path": relative, "reason": "write_set"},
        )
    return {
        "paper_id": paper_id,
        "role": role,
        "path": relative,
        "before_sha256": None,
        "after_sha256": after,
    }


def _entries_match_bindings(base: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Journal rows must be exactly the rollback units sealed inside those bindings."""

    if not entries:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal write set is empty", {"reason": "write_set"})
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        if entry["role"] != "binding" or entry["paper_id"] in seen:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind journal write set does not match the sealed binding",
                {"path": entry["path"], "reason": "write_set"},
            )
        seen.add(entry["paper_id"])
        target = _walk(base, entry["path"])
        if _file_identity(target) is None:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target no longer matches the write-after digest",
                {"path": entry["path"], "reason": "parallel_edit"},
            )
        raw = target.read_bytes()
        if sha256_bytes(raw) != entry["after_sha256"]:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target no longer matches the write-after digest",
                {"path": entry["path"], "reason": "parallel_edit"},
            )
        try:
            stored = validate_document(parse_strict_json(raw, invalid_code=PDF_BIND_INVALID), BINDING_SCHEMA)
        except (PdfBindingError, ContractError, UnicodeError, ValueError):
            _fail(PDF_ROLLBACK_CONFLICT, "bind target is not a sealed binding", {"path": entry["path"], "reason": "write_set"})
        if stored["paper_id"] != entry["paper_id"]:
            _fail(PDF_ROLLBACK_CONFLICT, "binding paper does not match the journal", {"reason": "write_set"})
        unit = _checked_rollback_unit(stored["rollback_unit"], entry["paper_id"])
        expected: list[dict[str, Any]] = []
        for row in unit["entries"]:
            after = entry["after_sha256"] if row["role"] == "binding" else row["after_sha256"]
            expected.append(
                {
                    "paper_id": entry["paper_id"],
                    "role": row["role"],
                    "path": row["path"],
                    "before_sha256": None,
                    "after_sha256": after,
                }
            )
        got = entries[index : index + len(expected)]
        if got != expected:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind journal write set does not match the sealed binding",
                {"paper_id": entry["paper_id"], "reason": "write_set"},
            )
        matched.extend(expected)
        index += len(expected)
    if matched != entries:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal write set does not match the sealed binding", {"reason": "write_set"})
    return matched


def _assert_migration_absent(base: Path, paper_id: str) -> None:
    relative = derived_location_path(KIND_NOTES, paper_id)
    path = _walk(base, relative)
    if path.exists() or path.is_symlink():
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "migration locator is still present; roll migration back before the binding",
            {"path": relative, "paper_id": paper_id, "reason": "migration_present"},
        )


def _capture_rollback_file(base: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    target = _walk(base, str(entry["path"]))
    identity = _file_identity(target)
    if identity is None:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind target no longer matches the write-after digest",
            {"path": entry["path"], "reason": "parallel_edit"},
        )
    data = target.read_bytes()
    if sha256_bytes(data) != entry["after_sha256"] or _file_identity(target) != identity:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind target no longer matches the write-after digest",
            {"path": entry["path"], "reason": "parallel_edit"},
        )
    return {"path": target, "relative": entry["path"], "identity": identity, "sha256": entry["after_sha256"], "data": data}


def _restore_rollback_files(removed: list[dict[str, Any]], atomic_write) -> None:
    for item in reversed(removed):
        path = item["path"]
        if path.exists() or path.is_symlink():
            if _file_sha(path) != item["sha256"]:
                _fail(
                    PDF_ROLLBACK_CONFLICT,
                    "bind rollback stopped without covering newer bytes",
                    {"path": item["relative"], "reason": "partial"},
                )
            continue
        atomic_write(path, item["data"])
        if _file_sha(path) != item["sha256"]:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind rollback could not restore the write unit",
                {"path": item["relative"], "reason": "partial"},
            )


def _approved_plan_from_journal(journal: Mapping[str, Any], journal_path: Path) -> dict[str, Any]:
    """Recompute the approved plan digest and refuse a journal that is not that plan."""

    approved = journal.get("approved_plan")
    plan_sha = journal.get("plan_sha256")
    request_sha = journal.get("request_sha256")
    if type(approved) is not dict or type(plan_sha) is not str or type(request_sha) is not str:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind journal is not tied to its approved plan",
            {"reason": "write_set"},
        )
    try:
        sealed = validate_document(_json_copy(approved), PLAN_SCHEMA)
    except (ContractError, CanonicalJsonError, TypeError, ValueError, UnicodeError):
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind journal is not tied to its approved plan",
            {"reason": "write_set"},
        )
    recomputed = _plan_content_sha(sealed)
    if (
        recomputed != plan_sha
        or sealed.get("plan_sha256") != recomputed
        or sealed.get("request_sha256") != request_sha
        or journal.get("roots_sha256") != sealed.get("roots_sha256")
        or journal.get("root_id") != sealed.get("root_id")
        or journal_path.name != f"journal-{recomputed[:16]}.json"
    ):
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind journal is not tied to its approved plan",
            {"reason": "write_set"},
        )
    return sealed


def _assert_installed_bindings_match_plan(base: Path, plan: Mapping[str, Any]) -> None:
    for item in plan["items"]:
        if item["before_binding_sha256"] is not None:
            continue
        relative = str(item["binding_path"])
        target = _walk(base, relative)
        if not _regular_file(target):
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target is not the approved plan binding",
                {"path": relative, "reason": "write_set"},
            )
        raw = target.read_bytes()
        if raw != binding_bytes(item["binding"]) or sha256_bytes(raw) != item["after_binding_sha256"]:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target is not the approved plan binding",
                {"path": relative, "reason": "write_set"},
            )


def _read_fd_bytes(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        chunks.append(block)
    return b"".join(chunks)


def _fd_identity(fd: int) -> tuple[int, int] | None:
    try:
        info = os.fstat(fd)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


def _restore_mutated_rollback_target(target: Path, data: bytes, atomic_write) -> None:
    if target.exists() or target.is_symlink():
        if _regular_file(target) and target.read_bytes() == data:
            return
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind target changed during removal",
            {"path": target.as_posix(), "reason": "parallel_edit"},
        )
    atomic_write(target, data)
    if not _regular_file(target) or target.read_bytes() != data:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind rollback could not preserve bytes edited during removal",
            {"path": target.as_posix(), "reason": "partial"},
        )


def _open_nofollow(path: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def _read_linked_regular(path: Path) -> tuple[tuple[int, int] | None, bytes | None]:
    """Identity and bytes of the regular file the path names right now."""

    try:
        live = _open_nofollow(path)
    except OSError:
        return None, None
    try:
        ident = _fd_identity(live)
        data = _read_fd_bytes(live)
        if _fd_identity(live) != ident:
            return None, None
        return ident, data
    finally:
        os.close(live)


def _is_unlink_target(file: object, target: Path) -> bool:
    try:
        raw = os.fspath(file)
    except TypeError:
        return False
    if isinstance(raw, bytes):
        try:
            raw = os.fsdecode(raw)
        except ValueError:
            return False
    return Path(raw) == target


def _unlink_verified_target(
    target: Path,
    *,
    identity: tuple[int, int],
    expected_sha: str,
    relative: str,
    atomic_write,
    removed: list[dict[str, Any]],
    record: dict[str, Any],
) -> None:
    """Unlink only while the path still names the verified inode and bytes.

    `Path.unlink` can replace that path before the real removal. The inode
    opened beforehand still has the approved bytes, so it cannot see the new
    object. The `os.unlink` boundary reads the directory entry that is about
    to disappear and leaves a different object in place. A removed object is
    recorded immediately, before the post-unlink read.
    """

    try:
        fd = _open_nofollow(target)
    except OSError:
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind target identity changed during rollback",
            {"path": relative, "reason": "parallel_edit"},
        )
    try:
        current = _fd_identity(fd)
        payload = _read_fd_bytes(fd)
        if current != identity or sha256_bytes(payload) != expected_sha or _fd_identity(fd) != identity:
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target no longer matches the write-after digest",
                {"path": relative, "reason": "parallel_edit"},
            )
        real_unlink = os.unlink

        def guarded_unlink(file: object, *args: object, **kwargs: object):
            if _is_unlink_target(file, target):
                try:
                    live_id, live = _read_linked_regular(target)
                except OSError:
                    live_id, live = None, None
                if (
                    live_id != identity
                    or live != payload
                    or live is None
                    or sha256_bytes(live) != expected_sha
                ):
                    _fail(
                        PDF_ROLLBACK_CONFLICT,
                        "bind target changed during removal",
                        {"path": relative, "reason": "parallel_edit"},
                    )
                result = real_unlink(file, *args, **kwargs)
                removed.append(record)
                return result
            return real_unlink(file, *args, **kwargs)

        os.unlink = guarded_unlink
        try:
            try:
                target.unlink()
            except OSError as exc:
                _fail(
                    PDF_ROLLBACK_CONFLICT,
                    "bind rollback could not remove a created file",
                    {"path": relative, "reason": "partial", "error": type(exc).__name__},
                )
        finally:
            os.unlink = real_unlink
        after_id = _fd_identity(fd)
        after = _read_fd_bytes(fd)
        if after_id != identity or after != payload or sha256_bytes(after) != expected_sha:
            _restore_mutated_rollback_target(target, after, atomic_write)
            if removed and removed[-1] is record and _regular_file(target) and target.read_bytes() == after:
                removed.pop()
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind target changed during removal",
                {"path": relative, "reason": "parallel_edit"},
            )
    finally:
        os.close(fd)


def rollback_bind_journal(*, journal_path: Path, roots_path: Path, confirm: bool) -> dict[str, Any]:
    from video_paper_wiki.pdf_locations import parse_roots
    from video_paper_wiki.pdf_migration import _acquire_lock, _atomic_write

    if not confirm:
        _fail(HUMAN_APPROVAL_REQUIRED, "interactive confirmation is required", {"next_action": "confirm_interactively"})
    path = Path(journal_path)
    journal = parse_strict_json(path.read_bytes(), invalid_code=PDF_BIND_INVALID) if _regular_file(path) else None
    if type(journal) is not dict or journal.get("schema") != JOURNAL_SCHEMA:
        _fail(PDF_BIND_INVALID, "bind journal is not a bind-rollback journal")
    sealed = _approved_plan_from_journal(journal, path)
    roots = parse_roots(_load_json(Path(roots_path)))
    if roots_digest(roots) != sealed["roots_sha256"]:
        _fail(PDF_ROLLBACK_CONFLICT, "roots.json no longer matches the bind journal", {"reason": "stale_root"})
    notes = _notes_target(roots, str(sealed["root_id"]))
    if root_directory_identity(notes["path"]) != journal.get("root_identity"):
        _fail(PDF_ROLLBACK_CONFLICT, "target root identity changed since bind apply", {"reason": "stale_root"})
    entries = journal.get("entries")
    if type(entries) is not list or journal.get("derived_write_set") != entries:
        _fail(PDF_ROLLBACK_CONFLICT, "bind journal is not tied to its derived write set", {"reason": "write_set"})
    normalized = [_journal_entry_ok(entry) for entry in entries]
    if normalized != _creation_entries(sealed):
        _fail(
            PDF_ROLLBACK_CONFLICT,
            "bind journal write set is not the approved plan creation set",
            {"reason": "write_set"},
        )
    base = Path(notes["path"])
    lock = _acquire_lock(base)
    try:
        if root_directory_identity(notes["path"]) != journal.get("root_identity"):
            _fail(PDF_ROLLBACK_CONFLICT, "target root identity changed since bind apply", {"reason": "stale_root"})
        if [_journal_entry_ok(entry) for entry in entries] != _creation_entries(sealed):
            _fail(
                PDF_ROLLBACK_CONFLICT,
                "bind journal write set is not the approved plan creation set",
                {"reason": "write_set"},
            )
        _assert_installed_bindings_match_plan(base, sealed)
        authorized = _entries_match_bindings(base, normalized)
        papers = list(dict.fromkeys(entry["paper_id"] for entry in authorized))
        for paper_id in papers:
            _assert_migration_absent(base, paper_id)
        captures = [_capture_rollback_file(base, entry) for entry in authorized]
        removed: list[dict[str, Any]] = []
        try:
            for item in reversed(captures):
                if root_directory_identity(notes["path"]) != journal.get("root_identity"):
                    _fail(PDF_ROLLBACK_CONFLICT, "target root identity changed during bind rollback", {"reason": "stale_root"})
                for paper_id in papers:
                    _assert_migration_absent(base, paper_id)
                target = _walk(base, str(item["relative"]))
                _unlink_verified_target(
                    target,
                    identity=item["identity"],
                    expected_sha=str(item["sha256"]),
                    relative=str(item["relative"]),
                    atomic_write=_atomic_write,
                    removed=removed,
                    record=item,
                )
        except Exception as original:
            try:
                _restore_rollback_files(removed, _atomic_write)
            except Exception as restore_error:
                raise restore_error from original
            raise
        return {
            "restored": [str(item["relative"]) for item in captures],
            "keep_local": True,
            "drive_unchanged": True,
        }
    finally:
        lock.close()


def _inventory_row(
    *,
    notes: Mapping[str, Any],
    binding: Mapping[str, Any],
    binding_rel: str,
    binding_sha: str,
    status: str,
    blockers: list[dict[str, str]],
    local_copies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    paper_id = str(binding["paper_id"])
    digest = str(binding["pdf_sha256"])
    drive_rel = drive_relative_path(paper_id)
    page_rel = f"papers/{seed_alias(paper_id)}.md"
    page_path = Path(notes["path"]) / page_rel
    bindings = [
        {
            "root_id": notes["root_id"],
            "paper_id": paper_id,
            "record_path": binding_rel,
            "scanned_sha256": binding_sha,
        }
    ]
    if status == "included" and _regular_file(page_path):
        bindings.append(
            {
                "root_id": notes["root_id"],
                "paper_id": paper_id,
                "record_path": page_rel,
                "scanned_sha256": sha256_bytes(page_path.read_bytes()),
            }
        )
    copies = list(local_copies or [])
    return {
        "item_id": item_id_for(paper_id=paper_id, pdf_sha256=digest, drive_relative_path=drive_rel),
        "paper_id": paper_id,
        "aliases": [{"id": seed_alias(paper_id), "basis": "pdf-binding"}],
        "pdf_sha256": digest,
        "size_bytes": int(binding["size_bytes"]),
        "media_type": "application/pdf",
        "category": category_for_paper(paper_id),
        "paper_dir": paper_dir_for(paper_id),
        "drive_relative_path": drive_rel,
        "local_copies": copies,
        "bindings": bindings,
        "status": status,
        "blockers": blockers,
    }


def explicit_binding_scan(roots: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Turn notes `pdf-bindings` plus their declared local_ref into inventory rows.

    Matching is the binding's local_ref only. Same digest or filename elsewhere
    is not attached.
    """

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for notes in roots:
        if notes.get("kind") != KIND_NOTES:
            continue
        base = Path(notes["path"])
        directory = base / "wiki" / "meta" / "pdf-bindings"
        if directory.is_symlink():
            excluded.append({"path": str(directory), "reason": "symlink"})
            continue
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            rel = f"wiki/meta/pdf-bindings/{path.name}"
            stored: dict[str, Any] | None = None
            if path.is_symlink() or not _regular_file(path):
                excluded.append({"path": rel, "reason": "symlink"})
                continue
            try:
                parsed = parse_strict_json(path.read_bytes(), invalid_code=PDF_BIND_INVALID)
                stored = validate_document(parsed, BINDING_SCHEMA)
                live = _binding_from_live(_request_from_binding(stored), roots, notes)
                if binding_bytes(live) != binding_bytes(stored) or path.read_bytes() != binding_bytes(stored):
                    raise PdfBindingError(
                        PDF_APPLY_CHANGED,
                        "stored binding does not match live inputs",
                        {"reason": "stale_basis"},
                    )
                _page_decision(notes, live)
            except (PdfBindingError, PdfLocationError, ContractError, OSError, UnicodeError, ValueError) as exc:
                code = getattr(exc, "code", PDF_BIND_INVALID)
                message = getattr(exc, "message", str(exc))
                digest = stored.get("pdf_sha256") if type(stored) is dict else None
                paper = stored.get("paper_id") if type(stored) is dict else None
                if type(paper) is str and type(digest) is str and len(digest) == 64 and type(stored) is dict:
                    try:
                        rows.append(
                            _inventory_row(
                                notes=notes,
                                binding=stored,
                                binding_rel=rel,
                                binding_sha=sha256_bytes(path.read_bytes()),
                                status="blocked",
                                blockers=[{"code": str(code), "message": str(message)[:1024]}],
                            )
                        )
                    except (PdfLocationError, PdfBindingError, ContractError, OSError, ValueError):
                        excluded.append({"path": rel, "reason": "invalid_pdf_binding"})
                else:
                    excluded.append({"path": rel, "reason": "invalid_pdf_binding"})
                continue
            copy = {
                "root_id": live["local_ref"]["root_id"],
                "relative_path": live["local_ref"]["relative_path"],
                "pdf_sha256": live["pdf_sha256"],
                "size_bytes": live["size_bytes"],
            }
            rows.append(
                _inventory_row(
                    notes=notes,
                    binding=live,
                    binding_rel=rel,
                    binding_sha=sha256_bytes(binding_bytes(live)),
                    status="included",
                    blockers=[],
                    local_copies=[copy],
                )
            )
    _demote_binding_conflicts(rows)
    return rows, excluded


def _demote_binding_conflicts(rows: list[dict[str, Any]]) -> None:
    included = [row for row in rows if row["status"] == "included"]
    by_digest: dict[str, set[str]] = {}
    by_paper: dict[str, set[str]] = {}
    for row in included:
        by_digest.setdefault(row["pdf_sha256"], set()).add(row["paper_id"])
        by_paper.setdefault(row["paper_id"], set()).add(row["pdf_sha256"])
    conflict_digests = {digest for digest, papers in by_digest.items() if len(papers) > 1}
    conflict_papers = {paper for paper, digests in by_paper.items() if len(digests) > 1}
    for row in included:
        if row["pdf_sha256"] in conflict_digests or row["paper_id"] in conflict_papers:
            row["status"] = "blocked"
            row["blockers"] = [
                {
                    "code": PDF_CONTENT_CONFLICT,
                    "message": "explicit binding conflicts with another paper or digest",
                }
            ]
            row["local_copies"] = []
