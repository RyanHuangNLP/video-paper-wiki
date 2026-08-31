"""Canonical paper/repo/claim/event/receipt identity. Production authority."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from video_paper_wiki.jcs import CanonicalJsonError, canonicalize

INVALID_PAPER_ID = "INVALID_PAPER_ID"
SCHEMA_INVALID = "SCHEMA_INVALID"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
CLAIM_ID_COLLISION = "CLAIM_ID_COLLISION"
CLAIM_ID_MISMATCH = "CLAIM_ID_MISMATCH"
EVENT_ID_MISMATCH = "EVENT_ID_MISMATCH"
EVIDENCE_FINGERPRINT_MISMATCH = "EVIDENCE_FINGERPRINT_MISMATCH"
RECEIPT_INTENT_MISMATCH = "RECEIPT_INTENT_MISMATCH"
PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
CANONICAL_JSON_INVALID = "CANONICAL_JSON_INVALID"

CLAIM_ID_PREFIX = "clm-"
EVENT_ID_PREFIX = "ase-"
GATE_EVENT_ID_PREFIX = "gde-"
CLAIM_NAMESPACE = "video-paper-wiki.claim.v1"

_ARXIV_NEW = re.compile(r"^([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?$")
_ARXIV_OLD = re.compile(r"^([a-z-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v[0-9]+)?$", re.I)
_ARXIV_CANON = re.compile(r"^arxiv:(?:[0-9]{4}\.[0-9]{4,5}|[a-z-]+(?:\.[a-z]{2})?/[0-9]{7})$")
_DOI_CANON = re.compile(r"^doi:10\.[0-9]{4,9}/.+$")
_OPENALEX_CANON = re.compile(r"^openalex:W[0-9]+$")
_SHA_CANON = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPENALEX_BODY = re.compile(r"^W[0-9]+$")
_DOI_BODY = re.compile(r"^10\.[0-9]{4,9}/\S+$")
_REPO_PAIR = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_REPO_ID = re.compile(r"^github:[a-z0-9._-]+/[a-z0-9._-]+$")
_PAPER_SUBJECT = re.compile(r"^paper:.+$")
_REPO_SUBJECT = re.compile(r"^repo:github:[a-z0-9._-]+/[a-z0-9._-]+$")
_CONCEPT_SUBJECT = re.compile(r"^concept:v[0-9]+:[a-z0-9]+(?:[-_][a-z0-9]+)*$")

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi.org/",
    "dx.doi.org/",
    "doi:",
)

_PDF_FIELDS = (
    "relation",
    "kind",
    "source_id",
    "page",
    "ref",
    "artifact_path",
    "artifact_sha256",
    "text_sha256",
)
_CODE_FIELDS = (
    "relation",
    "kind",
    "source_id",
    "repository",
    "commit",
    "path",
    "lines",
    "snippet_sha256",
)

RECEIPT_INTENT_FIELDS = ("sequence", "previous", "operation_id", "writes", "claimed_inputs")


class IdentityError(ValueError):
    """Fail-closed identity error with a stable envelope code."""

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


def nfkc_collapse(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def is_canonical_paper_id(value: str) -> bool:
    raw = str(value)
    return bool(
        _ARXIV_CANON.fullmatch(raw)
        or _DOI_CANON.fullmatch(raw)
        or _OPENALEX_CANON.fullmatch(raw)
        or _SHA_CANON.fullmatch(raw)
    )


def is_repo_id(value: str) -> bool:
    return bool(_REPO_ID.fullmatch(str(value)))


def is_stable_subject_id(value: str) -> bool:
    raw = str(value)
    if _REPO_SUBJECT.fullmatch(raw) or _CONCEPT_SUBJECT.fullmatch(raw):
        return True
    if not _PAPER_SUBJECT.fullmatch(raw):
        return False
    return is_canonical_paper_id(raw[len("paper:") :])


def paper_page_slug(paper_id: str) -> str:
    """Portable directory/path slug. Never a canonical ID, subject, or record ID."""

    value = str(paper_id).strip()
    if not is_canonical_paper_id(value):
        raise IdentityError(
            INVALID_PAPER_ID,
            "paper_id is not a canonical paper ID",
            {"paper_id": paper_id},
        )
    if value.startswith("doi:"):
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"doi-{digest}"
    scheme, rest = value.split(":", 1)
    return f"{scheme}-{rest}"


def catalog_seed_key(paper_id: str) -> str:
    """Map a canonical paper ID to the paused-catalog-67 page slug used in seed files."""

    value = str(paper_id).strip()
    if is_canonical_paper_id(value):
        return paper_page_slug(value)
    return value


def _invalid_paper(paper_id: object, *, reason: str) -> IdentityError:
    return IdentityError(
        INVALID_PAPER_ID,
        "paper_id is not a canonical paper ID",
        {"paper_id": paper_id, "reason": reason},
    )


def normalize_arxiv_id(candidate: str) -> str:
    raw = str(candidate).strip()
    if not raw:
        raise _invalid_paper(candidate, reason="empty arxiv candidate")
    lowered = raw
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "https://arxiv.org/pdf/", "http://arxiv.org/pdf/"):
        if lowered.lower().startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if raw.lower().startswith("arxiv.org/abs/"):
        raw = raw[len("arxiv.org/abs/") :]
    if raw.lower().startswith("arxiv:"):
        raw = raw[6:]
    raw = raw.strip().removesuffix(".pdf")
    match = _ARXIV_NEW.fullmatch(raw)
    if match:
        return f"arxiv:{match.group(1)}"
    match = _ARXIV_OLD.fullmatch(raw)
    if match:
        return f"arxiv:{match.group(1).lower()}"
    raise _invalid_paper(candidate, reason="malformed arxiv identifier")


def normalize_doi(candidate: str) -> str:
    raw = str(candidate).strip()
    if not raw:
        raise _invalid_paper(candidate, reason="empty doi candidate")
    lowered = raw.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            raw = raw[len(prefix) :]
            lowered = raw.lower()
            break
    body = lowered.strip()
    if not _DOI_BODY.fullmatch(body):
        raise _invalid_paper(candidate, reason="malformed doi identifier")
    return f"doi:{body}"


def normalize_openalex_id(candidate: str) -> str:
    raw = str(candidate).strip()
    if not raw:
        raise _invalid_paper(candidate, reason="empty openalex candidate")
    lowered = raw
    for prefix in ("https://openalex.org/", "http://openalex.org/", "openalex:"):
        if lowered.lower().startswith(prefix):
            raw = raw[len(prefix) :]
            break
    body = raw.strip()
    if body[:1].lower() == "w" and body[1:].isdigit():
        body = "W" + body[1:]
    if not _OPENALEX_BODY.fullmatch(body):
        raise _invalid_paper(candidate, reason="malformed openalex identifier")
    return f"openalex:{body}"


def normalize_pdf_sha256(candidate: str) -> str:
    raw = str(candidate).strip().lower()
    if not raw:
        raise _invalid_paper(candidate, reason="empty sha256 candidate")
    if raw.startswith("sha256:"):
        raw = raw[7:]
    if not _SHA256.fullmatch(raw):
        raise _invalid_paper(candidate, reason="sha256 must be the full 64 lowercase hex digest")
    return f"sha256:{raw}"


def _unique_normalized(values: Sequence[str], normalizer) -> list[str]:
    seen: list[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        normalized = normalizer(text)
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _conflict(message: str, details: dict[str, Any]) -> IdentityError:
    return IdentityError(IDENTITY_CONFLICT, message, details, exit_code=75)


def establish_canonical_paper_id(
    *,
    arxiv_ids: Sequence[str] = (),
    dois: Sequence[str] = (),
    openalex_ids: Sequence[str] = (),
    pdf_sha256: str | None = None,
    existing_paper_id: str | None = None,
    existing_paper_bindings: Mapping[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Choose or preserve canonical paper ID. Later identifiers become aliases only."""

    bindings = dict(existing_paper_bindings or {})
    arxiv = _unique_normalized(arxiv_ids, normalize_arxiv_id)
    doi = _unique_normalized(dois, normalize_doi)
    openalex = _unique_normalized(openalex_ids, normalize_openalex_id)
    sha: list[str] = []
    if pdf_sha256 is not None and str(pdf_sha256).strip():
        sha = [normalize_pdf_sha256(pdf_sha256)]

    if len(arxiv) > 1:
        raise _conflict("conflicting arXiv identifiers at the same priority", {"arxiv_ids": arxiv})
    if len(doi) > 1:
        raise _conflict("conflicting DOI identifiers at the same priority", {"dois": doi})
    if len(openalex) > 1:
        raise _conflict("conflicting OpenAlex identifiers at the same priority", {"openalex_ids": openalex})
    if len(sha) > 1:
        raise _conflict("conflicting PDF SHA-256 identifiers at the same priority", {"sha256": sha})

    discovered = [*arxiv, *doi, *openalex, *sha]
    chosen: str | None = None
    for group in (arxiv, doi, openalex, sha):
        if group:
            chosen = group[0]
            break
    if chosen is None:
        raise IdentityError(
            INVALID_PAPER_ID,
            "paper_id is not a canonical paper ID",
            {"reason": "no identity candidates"},
        )

    if existing_paper_id is not None and str(existing_paper_id).strip():
        existing = str(existing_paper_id).strip()
        if not is_canonical_paper_id(existing):
            raise _invalid_paper(existing_paper_id, reason="existing paper ID is not canonical")
        bound = bindings.get(existing)
        if sha and bound is not None and bound != sha[0][len("sha256:") :]:
            raise _conflict(
                "canonical paper ID is bound to a different PDF SHA-256",
                {"paper_id": existing, "bound_sha256": bound, "pdf_sha256": sha[0][len("sha256:") :]},
            )
        if sha:
            for other_id, other_sha in bindings.items():
                if other_sha == sha[0][len("sha256:") :] and other_id != existing:
                    raise _conflict(
                        "PDF SHA-256 is already bound to a different paper ID",
                        {"paper_id": existing, "bound_paper_id": other_id, "pdf_sha256": other_sha},
                    )
        aliases = tuple(item for item in discovered if item != existing)
        return existing, aliases

    if sha:
        digest = sha[0][len("sha256:") :]
        for other_id, other_sha in bindings.items():
            if other_id == chosen and other_sha != digest:
                raise _conflict(
                    "canonical paper ID is bound to a different PDF SHA-256",
                    {"paper_id": chosen, "bound_sha256": other_sha, "pdf_sha256": digest},
                )
            if other_sha == digest and other_id != chosen:
                raise _conflict(
                    "PDF SHA-256 is already bound to a different paper ID",
                    {"paper_id": chosen, "bound_paper_id": other_id, "pdf_sha256": digest},
                )

    aliases = tuple(item for item in discovered if item != chosen)
    return chosen, aliases


def paper_id_from_pdf_sha256(pdf_sha256: str) -> str:
    return normalize_pdf_sha256(pdf_sha256)


def repo_id(repository: str) -> str:
    raw = str(repository).strip()
    if raw.lower().startswith("github:"):
        raw = raw[7:]
    if not _REPO_PAIR.fullmatch(raw):
        raise IdentityError(
            SCHEMA_INVALID,
            "repository is not owner/repo",
            {"repository": repository},
        )
    owner, name = raw.split("/", 1)
    return f"github:{owner.casefold()}/{name.casefold()}"


def paper_subject_id(paper_id: str) -> str:
    value = str(paper_id).strip()
    if not is_canonical_paper_id(value):
        raise _invalid_paper(paper_id, reason="not a canonical paper ID")
    return f"paper:{value}"


def repo_subject_id(repository: str) -> str:
    return f"repo:{repo_id(repository)}"


def claim_id(subject: str, canonical_claim_text: str, locators: object | None = None) -> str:
    """Compute claim identity; locators are accepted only to prove they are ignored."""

    if not is_stable_subject_id(subject):
        raise IdentityError(
            SCHEMA_INVALID,
            f"Invalid stable_subject_id: {subject}",
            {"stable_subject_id": subject},
        )
    payload = (
        CLAIM_NAMESPACE.encode("utf-8")
        + b"\0"
        + subject.encode("utf-8")
        + b"\0"
        + nfkc_collapse(canonical_claim_text).encode("utf-8")
    )
    return CLAIM_ID_PREFIX + hashlib.sha256(payload).hexdigest()[:20]


def claim_identity_material(subject: str, canonical_claim_text: str) -> tuple[str, str]:
    return (str(subject), nfkc_collapse(canonical_claim_text))


def bind_claim_id(
    *,
    stated_claim_id: str,
    subject: str,
    canonical_claim_text: str,
    existing_claim_bindings: Mapping[str, tuple[str, str]] | None = None,
    locators: object | None = None,
) -> str:
    expected = claim_id(subject, canonical_claim_text, locators)
    material = claim_identity_material(subject, canonical_claim_text)
    bindings = dict(existing_claim_bindings or {})
    bound = bindings.get(stated_claim_id)
    if bound is not None and bound != material:
        raise IdentityError(
            CLAIM_ID_COLLISION,
            "truncated claim ID collides with different identity material",
            {
                "claim_id": stated_claim_id,
                "bound_subject": bound[0],
                "bound_text": bound[1],
                "stable_subject_id": subject,
            },
            exit_code=75,
        )
    expected_bound = bindings.get(expected)
    if expected_bound is not None and expected_bound != material:
        raise IdentityError(
            CLAIM_ID_COLLISION,
            "truncated claim ID collides with different identity material",
            {
                "claim_id": expected,
                "bound_subject": expected_bound[0],
                "bound_text": expected_bound[1],
                "stable_subject_id": subject,
            },
            exit_code=75,
        )
    if stated_claim_id != expected:
        raise IdentityError(
            CLAIM_ID_MISMATCH,
            "claim_id does not match identity material",
            {
                "claim_id": stated_claim_id,
                "expected": expected,
                "stable_subject_id": subject,
            },
        )
    return expected


def event_id(event: Mapping[str, Any], *, prefix: str = EVENT_ID_PREFIX) -> str:
    payload = {key: value for key, value in event.items() if key != "event_id"}
    try:
        digest = hashlib.sha256(canonicalize(payload)).hexdigest()[:20]
    except CanonicalJsonError as exc:
        raise IdentityError(CANONICAL_JSON_INVALID, exc.message, exc.details) from exc
    return prefix + digest


def assessment_event_id(event: Mapping[str, Any]) -> str:
    return event_id(event, prefix=EVENT_ID_PREFIX)


def gate_event_id(event: Mapping[str, Any]) -> str:
    return event_id(event, prefix=GATE_EVENT_ID_PREFIX)


def _evidence_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    kind = item.get("kind")
    fields = _PDF_FIELDS if kind == "pdf" else _CODE_FIELDS if kind == "code" else ()
    if not fields or item.get("relation") not in {"supports", "contradicts", "uncertain"}:
        raise IdentityError(
            EVIDENCE_FINGERPRINT_MISMATCH,
            "Invalid evidence kind or relation",
            {"kind": kind, "relation": item.get("relation")},
        )
    identity = {field: item[field] for field in fields if field in item}
    missing = set(fields) - identity.keys()
    if missing:
        raise IdentityError(
            EVIDENCE_FINGERPRINT_MISMATCH,
            "Missing evidence identity fields",
            {"missing": sorted(missing)},
        )
    if kind == "code":
        identity["repository"] = str(identity["repository"]).casefold()
    return identity


def evidence_fingerprint(evidence: Sequence[Mapping[str, Any]]) -> str:
    identities = [_evidence_identity(item) for item in evidence]
    try:
        identities.sort(key=canonicalize)
        return hashlib.sha256(canonicalize(identities)).hexdigest()
    except CanonicalJsonError as exc:
        raise IdentityError(CANONICAL_JSON_INVALID, exc.message, exc.details) from exc


def receipt_intent_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {field: receipt.get(field) for field in RECEIPT_INTENT_FIELDS}


def receipt_intent_sha256(receipt: Mapping[str, Any]) -> str:
    try:
        return hashlib.sha256(canonicalize(receipt_intent_payload(receipt))).hexdigest()
    except CanonicalJsonError as exc:
        raise IdentityError(CANONICAL_JSON_INVALID, exc.message, exc.details) from exc


def plan_approval_hash(plan: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in plan.items() if key != "approval_hash"}
    try:
        return hashlib.sha256(canonicalize(payload)).hexdigest()
    except CanonicalJsonError as exc:
        raise IdentityError(CANONICAL_JSON_INVALID, exc.message, exc.details) from exc


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
