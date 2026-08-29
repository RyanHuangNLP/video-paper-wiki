"""Reference implementations for identity contract tests (not production code)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from .jcs import canonicalize

_PAPER_SUBJECT = re.compile(r"^paper:[^\s]+$")
_REPO_SUBJECT = re.compile(r"^repo:github:[a-z0-9._-]+/[a-z0-9._-]+$")
_CONCEPT_SUBJECT = re.compile(r"^concept:v[0-9]+:[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_PDF_FIELDS = ("relation", "kind", "source_id", "page", "ref", "artifact_path", "artifact_sha256", "text_sha256")
_CODE_FIELDS = ("relation", "kind", "source_id", "repository", "commit", "path", "lines", "snippet_sha256")


def nfkc_collapse(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def is_stable_subject_id(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in (_PAPER_SUBJECT, _REPO_SUBJECT, _CONCEPT_SUBJECT))


def claim_id(subject: str, canonical_claim_text: str, locators: object | None = None) -> str:
    """Compute claim identity; locators are accepted only to prove they are ignored."""

    if not is_stable_subject_id(subject):
        raise ValueError(f"Invalid stable_subject_id: {subject}")
    payload = b"video-paper-wiki.claim.v1\0" + subject.encode("utf-8") + b"\0" + nfkc_collapse(canonical_claim_text).encode("utf-8")
    return "clm-" + hashlib.sha256(payload).hexdigest()[:20]


def event_id(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_id"}
    return "ase-" + hashlib.sha256(canonicalize(payload)).hexdigest()[:20]


def _evidence_identity(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get("kind")
    fields = _PDF_FIELDS if kind == "pdf" else _CODE_FIELDS if kind == "code" else ()
    if not fields or item.get("relation") not in {"supports", "contradicts", "uncertain"}:
        raise ValueError("Invalid evidence kind or relation")
    identity = {field: item[field] for field in fields if field in item}
    missing = set(fields) - identity.keys()
    if missing:
        raise ValueError(f"Missing evidence identity fields: {sorted(missing)}")
    if kind == "code":
        identity["repository"] = identity["repository"].casefold()
    return identity


def evidence_fingerprint(evidence: list[dict[str, Any]]) -> str:
    identities = [_evidence_identity(item) for item in evidence]
    identities.sort(key=canonicalize)
    return hashlib.sha256(canonicalize(identities)).hexdigest()
