"""Drive/local PDF location contract. Zero network. No Vault mutation."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import (
    IdentityError,
    catalog_seed_key,
    is_canonical_paper_id,
    normalize_arxiv_id,
    paper_page_slug,
)
from video_paper_wiki.jcs import canonicalize

LOCATIONS_SCHEMA = "video-paper-wiki.pdf-locations.v1"
CACHE_POLICY = "keep-local"
DRIVE_A_ROOT_FOLDER_ID = "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW"
DRIVE_HOSTS = frozenset({"drive.google.com", "docs.google.com"})
PDF_HEADING = "PDF"
PREFER_AUTO = "auto"
PREFER_LOCAL = "local"
PREFER_DRIVE = "drive"
VERIFIED = "verified"
UNVERIFIED = "unverified"
MEDIA_PDF = "application/pdf"
KIND_FORMAL = "formal-vault"
KIND_NOTES = "notes-vault"
KIND_REPO = "repository"
KIND_RESEARCH = "research-workspace"
KIND_CACHE = "file-cache"
ROOT_KINDS = frozenset({KIND_FORMAL, KIND_NOTES, KIND_REPO, KIND_RESEARCH, KIND_CACHE})
ROOT_ROLES = frozenset({"target", "source-only"})
FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,128}$")
FILE_ID_PATH_RE = re.compile(r"/file/d/([A-Za-z0-9_-]{10,128})(?:/|$)")
FOLDER_PATH_RE = re.compile(r"/folders/|/drive/u/\d+/folders/")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SEED_ARXIV_RE = re.compile(r"^arxiv-([0-9]{4}\.[0-9]{4,5})$")
# Awesome-Video-Diffusion / Drive A section titles. Spaces are significant.
# Inventory may propose a path; prepare reuses the manifest path when result=reused.
DRIVE_A_CATEGORY_BY_SEED = {
    "arxiv-1812.01717": "Evaluation Benchmarks and Metrics",
    "arxiv-2204.03458": "Video Generation",
    "arxiv-2209.14792": "Video Generation",
    "arxiv-2210.02399": "Video Generation",
    "arxiv-2212.05199": "Video Generation",
    "arxiv-2306.02018": "Video Generation",
    "arxiv-2307.06942": "Video Generation",
    "arxiv-2310.12190": "Video Generation",
    "arxiv-2311.15127": "Video Generation",
    "arxiv-2311.17982": "Evaluation Benchmarks and Metrics",
    "arxiv-2312.03641": "Controllable Video Generation",
    "arxiv-2312.14125": "Video Generation",
    "arxiv-2401.03048": "Video Generation",
    "arxiv-2401.12945": "Video Generation",
    "arxiv-2402.19479": "Evaluation Benchmarks and Metrics",
    "arxiv-2405.18750": "Video Generation",
    "arxiv-2408.06072": "Video Generation",
    "arxiv-2410.05954": "Open-source Toolboxes and Foundation Models",
    "arxiv-2412.03603": "Open-source Toolboxes and Foundation Models",
}
ENGINE_MVP_SEED_IDS = frozenset(DRIVE_A_CATEGORY_BY_SEED)
CATEGORY_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,127}$")
PAPER_DIR_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
LOCATION_RELATIVE_RE = re.compile(
    r"^(wiki/meta/pdf-locations|catalog/pdf-locations|\.pdf-locations)/"
    r"[A-Za-z0-9][A-Za-z0-9._-]*\.json$"
)
PAGE_RELATIVE_RE = re.compile(
    r"^(wiki/papers|papers)/[A-Za-z0-9][A-Za-z0-9._-]*\.md$"
)

PDF_LOCATION_INVALID = "PDF_LOCATION_INVALID"
PDF_DRIVE_URL_INVALID = "PDF_DRIVE_URL_INVALID"
PDF_DRIVE_ID_MISMATCH = "PDF_DRIVE_ID_MISMATCH"
PDF_UNAVAILABLE_OFFLINE = "PDF_UNAVAILABLE_OFFLINE"
PDF_VERSION_AMBIGUOUS = "PDF_VERSION_AMBIGUOUS"
PDF_PARAMETER_CONFLICT = "PDF_PARAMETER_CONFLICT"
PDF_NOT_FOUND = "PDF_NOT_FOUND"
PDF_CACHE_INVALID = "PDF_CACHE_INVALID"
PDF_CONTENT_CONFLICT = "PDF_CONTENT_CONFLICT"
ROOT_LAYOUT_MISMATCH = "ROOT_LAYOUT_MISMATCH"


class PdfLocationError(Exception):
    """Fail-closed PDF location error with a stable envelope code."""

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
    raise PdfLocationError(code, message, details, exit_code=exit_code)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: object) -> str:
    return sha256_bytes(canonicalize(value))


def hash_file(path: Path, *, max_bytes: int = 64 * 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                _fail(PDF_LOCATION_INVALID, "PDF exceeds the 64 MiB bound", {"path": str(path)})
            digest.update(chunk)
    return digest.hexdigest(), size


def is_pdf_bytes(data: bytes) -> bool:
    return data.startswith(b"%PDF-")


def canonical_paper_id(value: object) -> str:
    raw = str(value).strip()
    if not raw:
        _fail(PDF_LOCATION_INVALID, "paper_id is empty")
    if is_canonical_paper_id(raw):
        return raw
    match = SEED_ARXIV_RE.fullmatch(raw)
    if match is not None:
        try:
            return normalize_arxiv_id(match.group(1))
        except IdentityError as exc:
            _fail(PDF_LOCATION_INVALID, exc.message, dict(exc.details))
    if raw.lower().startswith("arxiv-"):
        try:
            return normalize_arxiv_id(raw[6:])
        except IdentityError:
            pass
    try:
        from video_paper_wiki.identity import canonicalize_stated_paper_id

        return canonicalize_stated_paper_id(raw)
    except IdentityError as exc:
        _fail(PDF_LOCATION_INVALID, "paper_id is not a canonical paper ID", {"paper_id": raw})
        raise AssertionError("unreachable") from exc


def seed_alias(paper_id: str) -> str:
    canonical = canonical_paper_id(paper_id)
    return catalog_seed_key(canonical)


def is_engine_mvp(paper_id: str) -> bool:
    canonical = canonical_paper_id(paper_id)
    return seed_alias(canonical) in ENGINE_MVP_SEED_IDS


def _category_token(value: str) -> bool:
    text = value.strip()
    return bool(text) and CATEGORY_TOKEN.fullmatch(text) is not None and ".." not in text.split("/")


def drive_a_category(paper_id: str) -> str | None:
    canonical = canonical_paper_id(paper_id)
    return DRIVE_A_CATEGORY_BY_SEED.get(seed_alias(canonical))


def category_for_paper(paper_id: str, existing: str | None = None) -> str:
    if isinstance(existing, str) and _category_token(existing):
        return existing.strip()
    known = drive_a_category(paper_id)
    if known is not None:
        return known
    if is_engine_mvp(paper_id):
        return "engine-mvp"
    return "uncategorized"


def paper_dir_for(paper_id: str, *, existing: str | None = None) -> str:
    canonical = canonical_paper_id(paper_id)
    if isinstance(existing, str) and existing.strip() and PAPER_DIR_TOKEN.fullmatch(existing.strip()):
        return existing.strip()
    if is_engine_mvp(canonical):
        return seed_alias(canonical)
    return paper_page_slug(canonical)


def is_portable_relative_path(value: str) -> bool:
    rel = value.replace("\\", "/").strip()
    if not rel or rel.startswith("/") or rel.endswith("/"):
        return False
    parts = rel.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def is_portable_drive_relative_path(value: str) -> bool:
    if not is_portable_relative_path(value):
        return False
    parts = value.replace("\\", "/").split("/")
    if len(parts) != 4 or parts[0] != "pdfs" or parts[3] != "original.pdf":
        return False
    return _category_token(parts[1]) and PAPER_DIR_TOKEN.fullmatch(parts[2]) is not None


def drive_relative_path(
    paper_id: str,
    *,
    category: str | None = None,
    paper_dir: str | None = None,
    existing_drive_relative_path: str | None = None,
) -> str:
    if isinstance(existing_drive_relative_path, str) and is_portable_drive_relative_path(existing_drive_relative_path):
        return existing_drive_relative_path.replace("\\", "/")
    canonical = canonical_paper_id(paper_id)
    chosen_category = category_for_paper(canonical, category)
    chosen_dir = paper_dir_for(canonical, existing=paper_dir)
    return f"pdfs/{chosen_category}/{chosen_dir}/original.pdf"


def resolve_inside_root(root: Path, relative: str) -> Path:
    if not is_portable_relative_path(relative):
        _fail(PDF_LOCATION_INVALID, "relative path is not portable", {"relative_path": relative})
    base = Path(root).resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        _fail(PDF_LOCATION_INVALID, "path escapes the target root", {"relative_path": relative})
    return target


def derived_location_path(kind: str, paper_id: str) -> str:
    path = location_relative_path(kind, paper_id)
    if LOCATION_RELATIVE_RE.fullmatch(path) is None:
        _fail(PDF_LOCATION_INVALID, "derived location path is not portable", {"path": path})
    return path


def derived_page_path(kind: str, paper_id: str) -> str | None:
    path = page_relative_path(kind, paper_id)
    if path is None:
        return None
    if PAGE_RELATIVE_RE.fullmatch(path) is None:
        _fail(PDF_LOCATION_INVALID, "derived page path is not portable", {"path": path})
    return path


def same_drive_link(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_drive = left.get("drive") if type(left.get("drive")) is dict else {}
    right_drive = right.get("drive") if type(right.get("drive")) is dict else {}
    left_id = left_drive.get("file_id")
    right_id = right_drive.get("file_id")
    left_url = left_drive.get("url")
    right_url = right_drive.get("url")
    if type(left_id) is str and type(right_id) is str and left_id and left_id == right_id:
        return True
    return type(left_url) is str and type(right_url) is str and bool(left_url) and left_url == right_url


def location_relative_path(kind: str, paper_id: str) -> str:
    slug = paper_page_slug(canonical_paper_id(paper_id))
    if kind in {KIND_FORMAL, KIND_NOTES}:
        return f"wiki/meta/pdf-locations/{slug}.json"
    if kind == KIND_REPO:
        return f"catalog/pdf-locations/{slug}.json"
    if kind == KIND_RESEARCH:
        return f".pdf-locations/{slug}.json"
    _fail(PDF_LOCATION_INVALID, "root kind does not store location files", {"kind": kind})
    raise AssertionError("unreachable")


def page_relative_path(kind: str, paper_id: str) -> str | None:
    canonical = canonical_paper_id(paper_id)
    if kind == KIND_FORMAL:
        return f"wiki/papers/{paper_page_slug(canonical)}.md"
    if kind == KIND_NOTES:
        return f"papers/{seed_alias(canonical)}.md"
    return None


def _strip_credentials(parsed) -> None:
    if parsed.username or parsed.password:
        _fail(PDF_DRIVE_URL_INVALID, "Drive metadata must not contain credentials")


def _file_id_from_query(parsed) -> str | None:
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key == "id" and FILE_ID_RE.fullmatch(value):
            return value
    return None


def _resourcekey(parsed) -> str | None:
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key.casefold() == "resourcekey" and value:
            if any(ch in value for ch in "/?#@:\\"):
                _fail(PDF_DRIVE_URL_INVALID, "resourcekey is not portable")
            return value
    return None


def normalize_drive_locator(*, file_id: str | None = None, url: str | None = None) -> dict[str, str]:
    """Normalize a Drive fileId and/or URL to a stored file_id + HTTPS view URL."""

    stated_id = str(file_id).strip() if file_id is not None and str(file_id).strip() else None
    stated_url = str(url).strip() if url is not None and str(url).strip() else None
    if stated_id is None and stated_url is None:
        _fail(PDF_DRIVE_URL_INVALID, "Drive file id or URL is required")
    parsed_id = stated_id
    resourcekey = None
    if stated_id is not None and not FILE_ID_RE.fullmatch(stated_id):
        _fail(PDF_DRIVE_URL_INVALID, "Drive file id is not a portable fileId", {"file_id": stated_id})
    if stated_url is not None:
        parsed = urlparse(stated_url)
        _strip_credentials(parsed)
        if parsed.scheme != "https":
            _fail(PDF_DRIVE_URL_INVALID, "Drive URL must be HTTPS")
        host = (parsed.hostname or "").casefold()
        if host not in DRIVE_HOSTS:
            _fail(PDF_DRIVE_URL_INVALID, "Drive URL host is not a Drive host", {"host": host})
        path = parsed.path or ""
        if FOLDER_PATH_RE.search(path) or "/folders/" in path:
            _fail(PDF_DRIVE_URL_INVALID, "Drive folder links are rejected")
        match = FILE_ID_PATH_RE.search(path)
        url_id = match.group(1) if match else _file_id_from_query(parsed)
        if url_id is None:
            _fail(PDF_DRIVE_URL_INVALID, "Drive URL does not identify a file")
        resourcekey = _resourcekey(parsed)
        if parsed_id is None:
            parsed_id = url_id
        elif parsed_id != url_id:
            _fail(
                PDF_DRIVE_ID_MISMATCH,
                "Drive file id and URL identify different files",
                {"file_id": parsed_id, "url_file_id": url_id},
            )
    assert parsed_id is not None
    query = urlencode({"resourcekey": resourcekey}) if resourcekey else ""
    canonical_url = urlunparse(("https", "drive.google.com", f"/file/d/{parsed_id}/view", "", query, ""))
    return {"file_id": parsed_id, "url": canonical_url}


def build_verification(*, verified: bool, checked_at: str | None = None) -> dict[str, Any]:
    if verified:
        if not checked_at:
            _fail(PDF_LOCATION_INVALID, "verified locations require checked_at")
        return {"status": VERIFIED, "checked_at": checked_at, "method": "download-sha256"}
    return {"status": UNVERIFIED, "checked_at": None, "method": None}


def build_pdf_entry(
    *,
    file_id: str | None = None,
    url: str | None = None,
    root_folder_id: str = DRIVE_A_ROOT_FOLDER_ID,
    relative_path: str = "",
    pdf_sha256: str | None = None,
    size_bytes: int | None = None,
    media_type: str | None = None,
    local_refs: list[Mapping[str, str]] | None = None,
    verified: bool = False,
    checked_at: str | None = None,
) -> dict[str, Any]:
    locator = normalize_drive_locator(file_id=file_id, url=url)
    digest = pdf_sha256.lower() if isinstance(pdf_sha256, str) and pdf_sha256 else None
    if digest is not None and not HEX64.fullmatch(digest):
        _fail(PDF_LOCATION_INVALID, "pdf_sha256 must be 64 lowercase hex digits")
    if verified and (digest is None or size_bytes is None):
        _fail(PDF_LOCATION_INVALID, "verified locations require digest and size")
    if verified:
        chosen_media = MEDIA_PDF
    else:
        chosen_media = media_type if media_type in {MEDIA_PDF, None} else None
        if digest is None:
            chosen_media = None
    refs = []
    seen = set()
    for item in local_refs or []:
        root_id = str(item.get("root_id", "")).strip()
        rel = str(item.get("relative_path", "")).strip().replace("\\", "/")
        if not root_id or not rel or rel.startswith("/") or ".." in rel.split("/"):
            _fail(PDF_LOCATION_INVALID, "local_ref is not a portable relative path", {"local_ref": dict(item)})
        key = (root_id, rel)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"root_id": root_id, "relative_path": rel})
    refs.sort(key=lambda row: (row["root_id"], row["relative_path"]))
    if relative_path and (
        relative_path.startswith("/")
        or "\\" in relative_path
        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
    ):
        _fail(PDF_LOCATION_INVALID, "drive relative_path is not portable", {"relative_path": relative_path})
    return {
        "pdf_sha256": digest,
        "size_bytes": size_bytes,
        "media_type": chosen_media,
        "drive": {
            "file_id": locator["file_id"],
            "url": locator["url"],
            "root_folder_id": str(root_folder_id),
            "relative_path": relative_path or "",
        },
        "local_refs": refs,
        "cache_policy": CACHE_POLICY,
        "verification": build_verification(verified=verified, checked_at=checked_at),
    }


def build_locations_document(paper_id: str, pdfs: list[Mapping[str, Any]]) -> dict[str, Any]:
    canonical = canonical_paper_id(paper_id)
    entries = [dict(item) for item in pdfs]
    document = {"schema": LOCATIONS_SCHEMA, "paper_id": canonical, "pdfs": entries}
    return validate_locations(document)


def validate_locations(value: object) -> dict[str, Any]:
    try:
        document = validate_document(value, LOCATIONS_SCHEMA)
    except ContractError as exc:
        raise PdfLocationError(exc.code, exc.message, dict(exc.details), exit_code=exc.exit_code) from exc
    statuses = {item["verification"]["status"] for item in document["pdfs"]}
    methods = {item["verification"]["method"] for item in document["pdfs"]}
    for item in document["pdfs"]:
        verification = item["verification"]
        if verification["status"] == VERIFIED:
            if verification["method"] != "download-sha256" or verification["checked_at"] is None:
                _fail(PDF_LOCATION_INVALID, "verified status requires download-sha256 and checked_at")
            if item["pdf_sha256"] is None or item["size_bytes"] is None or item["media_type"] != MEDIA_PDF:
                _fail(PDF_LOCATION_INVALID, "verified entries require digest, size, and application/pdf")
        else:
            if verification["method"] is not None or verification["checked_at"] is not None:
                _fail(PDF_LOCATION_INVALID, "unverified entries must not claim a verification method")
        if item["cache_policy"] != CACHE_POLICY:
            _fail(PDF_LOCATION_INVALID, "cache_policy must be keep-local")
        if "://" in item["drive"]["url"] and not item["drive"]["url"].startswith("https://"):
            _fail(PDF_DRIVE_URL_INVALID, "stored Drive URL must be HTTPS")
    _ = statuses, methods
    return document


def locations_bytes(document: Mapping[str, Any]) -> bytes:
    return canonicalize(validate_locations(document))


def load_locations_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    raw = path.read_bytes()
    from video_paper_wiki.secure_io import parse_strict_json

    parsed = parse_strict_json(raw, invalid_code=PDF_LOCATION_INVALID)
    return validate_locations(parsed)


def merge_local_ref(document: dict[str, Any], *, root_id: str, relative_path: str, pdf_sha256: str | None) -> dict[str, Any]:
    updated = validate_locations(document)
    target = None
    if pdf_sha256:
        for item in updated["pdfs"]:
            if item["pdf_sha256"] == pdf_sha256:
                target = item
                break
    if target is None:
        if len(updated["pdfs"]) == 1:
            target = updated["pdfs"][0]
        else:
            _fail(PDF_VERSION_AMBIGUOUS, "cannot attach a local ref without a unique PDF digest")
    refs = list(target["local_refs"])
    candidate = {"root_id": root_id, "relative_path": relative_path}
    if candidate not in refs:
        refs.append(candidate)
        refs.sort(key=lambda row: (row["root_id"], row["relative_path"]))
        target["local_refs"] = refs
    return validate_locations(updated)


def _regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def verify_local_cache(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Live cache check. Availability is never persisted as always-true."""

    result = {
        "path": str(path),
        "available": False,
        "readable": False,
        "sha_matching": False,
        "pdf_sha256": None,
        "size_bytes": None,
        "reason": None,
    }
    if not _regular_file(path):
        result["reason"] = "missing_or_not_regular"
        return result
    if not os.access(path, os.R_OK):
        result["reason"] = "unreadable"
        return result
    result["readable"] = True
    try:
        digest, size = hash_file(path)
    except (OSError, PdfLocationError):
        result["reason"] = "unreadable"
        result["readable"] = False
        return result
    result["pdf_sha256"] = digest
    result["size_bytes"] = size
    if expected_sha256 and digest != expected_sha256:
        result["reason"] = "digest_mismatch"
        return result
    try:
        with path.open("rb") as handle:
            head = handle.read(5)
    except OSError:
        result["reason"] = "unreadable"
        result["readable"] = False
        return result
    if not is_pdf_bytes(head):
        result["reason"] = "not_pdf"
        return result
    result["sha_matching"] = expected_sha256 is None or digest == expected_sha256
    result["available"] = result["readable"] and result["sha_matching"]
    return result


def select_pdf_entries(document: Mapping[str, Any], pdf_sha256: str | None) -> list[dict[str, Any]]:
    validated = validate_locations(document)
    if pdf_sha256:
        digest = pdf_sha256.lower()
        if not HEX64.fullmatch(digest):
            _fail(PDF_LOCATION_INVALID, "pdf_sha256 must be 64 lowercase hex digits")
        matches = [item for item in validated["pdfs"] if item["pdf_sha256"] == digest]
        if not matches:
            _fail(PDF_NOT_FOUND, "no PDF location matches the requested digest", {"pdf_sha256": digest})
        return matches
    if len(validated["pdfs"]) == 1:
        return list(validated["pdfs"])
    if not validated["pdfs"]:
        _fail(PDF_NOT_FOUND, "location document has no PDF entries")
    _fail(
        PDF_VERSION_AMBIGUOUS,
        "multiple PDF versions exist; pass --pdf-sha256",
        {"candidates": [item["pdf_sha256"] for item in validated["pdfs"]]},
    )
    raise AssertionError("unreachable")


def resolve_local_path(root_path: Path, relative_path: str) -> Path:
    rel = relative_path.replace("\\", "/")
    if rel.startswith("/") or any(part in {"", ".", ".."} for part in rel.split("/")):
        _fail(PDF_LOCATION_INVALID, "local relative_path is not portable", {"relative_path": relative_path})
    return (root_path / rel).resolve()


def resolve_open_target(
    document: Mapping[str, Any],
    *,
    roots: Mapping[str, Path],
    prefer: str = PREFER_AUTO,
    offline: bool = False,
    pdf_sha256: str | None = None,
) -> dict[str, Any]:
    if prefer not in {PREFER_AUTO, PREFER_LOCAL, PREFER_DRIVE}:
        _fail(PDF_PARAMETER_CONFLICT, "prefer must be auto, local, or drive", {"prefer": prefer})
    if offline and prefer == PREFER_DRIVE:
        _fail(PDF_PARAMETER_CONFLICT, "--offline cannot be combined with --prefer drive")
    entries = select_pdf_entries(document, pdf_sha256)
    entry = entries[0]
    local_hits: list[dict[str, Any]] = []
    for ref in entry["local_refs"]:
        root = roots.get(ref["root_id"])
        if root is None:
            continue
        candidate = root / ref["relative_path"]
        check = verify_local_cache(candidate, expected_sha256=entry["pdf_sha256"])
        check["root_id"] = ref["root_id"]
        check["relative_path"] = ref["relative_path"]
        if check["available"]:
            local_hits.append(check)
    local = local_hits[0] if local_hits else None
    drive_url = entry["drive"]["url"]
    verification = entry["verification"]["status"]
    payload = {
        "paper_id": document["paper_id"],
        "prefer": prefer,
        "offline": offline,
        "pdf_sha256": entry["pdf_sha256"],
        "size_bytes": entry["size_bytes"],
        "verification": verification,
        "verified": verification == VERIFIED,
        "local_available": local is not None,
        "local_path": None if local is None else local["path"],
        "drive_url": drive_url,
        "drive_file_id": entry["drive"]["file_id"],
        "cache_policy": CACHE_POLICY,
        "target_kind": None,
        "target": None,
        "open_submitted_only": True,
    }
    if prefer == PREFER_LOCAL or (prefer == PREFER_AUTO and local is not None):
        if local is None:
            if offline:
                _fail(
                    PDF_UNAVAILABLE_OFFLINE,
                    "no readable sha-matching local PDF is available offline",
                    {"drive_url": drive_url, "verification": verification},
                )
            _fail(PDF_NOT_FOUND, "no readable sha-matching local PDF is available")
        payload["target_kind"] = "local"
        payload["target"] = local["path"]
        return payload
    if offline:
        _fail(
            PDF_UNAVAILABLE_OFFLINE,
            "no readable sha-matching local PDF is available offline",
            {"drive_url": drive_url, "verification": verification},
        )
    payload["target_kind"] = "drive"
    payload["target"] = drive_url
    return payload


def render_pdf_section(document: Mapping[str, Any], *, local_available: Mapping[str, bool] | None = None) -> str:
    """Managed ## PDF block for notes copies and compiled paper pages."""

    validated = validate_locations(document)
    if not validated["pdfs"]:
        return ""
    lines = ["", f"## {PDF_HEADING}", ""]
    available = local_available or {}
    for item in validated["pdfs"]:
        status = item["verification"]["status"]
        digest = item["pdf_sha256"] or "unverified"
        label = "Drive PDF"
        extra = f" (`{status}`"
        if item["pdf_sha256"]:
            extra += f"; sha256 `{item['pdf_sha256']}`"
        extra += ")"
        lines.append(f"- [{label}]({item['drive']['url']}){extra}")
        for ref in item["local_refs"]:
            key = f"{ref['root_id']}:{ref['relative_path']}"
            live = available.get(key)
            note = "可用" if live else "已登记，打开时核验"
            lines.append(f"- 本地 PDF：`{ref['relative_path']}` （{note}；keep-local）")
        if not item["local_refs"] and digest == "unverified":
            lines.append("- 本地 PDF：无登记缓存")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def render_pdf_section_lines(document: Mapping[str, Any] | None) -> list[str]:
    if not document:
        return []
    block = render_pdf_section(document)
    if not block:
        return []
    # Compiler pages already have a trailing blank after H1; keep a heading block.
    text = block.strip("\n")
    return text.split("\n") + [""]


def item_id_for(*, paper_id: str, pdf_sha256: str, drive_relative_path: str) -> str:
    return sha256_json(
        {
            "paper_id": canonical_paper_id(paper_id),
            "pdf_sha256": pdf_sha256,
            "drive_relative_path": drive_relative_path,
        }
    )


def parse_roots(value: object) -> list[dict[str, Any]]:
    if type(value) is dict and "roots" in value:
        rows = value["roots"]
    else:
        rows = value
    if type(rows) is not list or not rows:
        _fail(PDF_LOCATION_INVALID, "roots must be a nonempty array")
    seen = set()
    out = []
    for index, row in enumerate(rows):
        if type(row) is not dict:
            _fail(PDF_LOCATION_INVALID, "root record must be an object", {"index": index})
        root_id = str(row.get("root_id", "")).strip()
        kind = str(row.get("kind", "")).strip()
        path = str(row.get("path", "")).strip()
        role = str(row.get("role", "")).strip()
        if not root_id or root_id in seen:
            _fail(PDF_LOCATION_INVALID, "root_id must be unique and nonempty", {"index": index})
        if kind not in ROOT_KINDS:
            _fail(PDF_LOCATION_INVALID, "root kind is not supported", {"kind": kind})
        if role not in ROOT_ROLES:
            _fail(PDF_LOCATION_INVALID, "root role must be target or source-only", {"role": role})
        if not path:
            _fail(PDF_LOCATION_INVALID, "root path is required", {"root_id": root_id})
        seen.add(root_id)
        out.append({"root_id": root_id, "kind": kind, "path": path, "role": role})
    return out


def roots_map(roots: list[Mapping[str, Any]]) -> dict[str, Path]:
    return {row["root_id"]: Path(row["path"]) for row in roots}


def roots_digest(roots: list[Mapping[str, Any]]) -> str:
    material = [{"root_id": row["root_id"], "kind": row["kind"], "role": row["role"]} for row in roots]
    return sha256_json(material)
