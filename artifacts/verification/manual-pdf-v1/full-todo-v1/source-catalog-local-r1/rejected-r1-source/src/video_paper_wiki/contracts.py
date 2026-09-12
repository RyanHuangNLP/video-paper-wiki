"""Production schema registry and in-memory prospective identity validator."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

from video_paper_wiki import identity
from video_paper_wiki.identity import IdentityError
from video_paper_wiki.jcs import CanonicalJsonError
from video_paper_wiki.resources import _RESOURCE_VIEW, load_schema_json, schema_resource_names

SCHEMA_INVALID = "SCHEMA_INVALID"
INVALID_PAPER_ID = identity.INVALID_PAPER_ID
CANONICAL_JSON_INVALID = identity.CANONICAL_JSON_INVALID
PLAN_HASH_MISMATCH = identity.PLAN_HASH_MISMATCH
PIPELINE_FINGERPRINT_MISMATCH = "PIPELINE_FINGERPRINT_MISMATCH"
CLAIM_ID_MISMATCH = identity.CLAIM_ID_MISMATCH
EVENT_ID_MISMATCH = identity.EVENT_ID_MISMATCH
EVIDENCE_FINGERPRINT_MISMATCH = identity.EVIDENCE_FINGERPRINT_MISMATCH
RECEIPT_INTENT_MISMATCH = identity.RECEIPT_INTENT_MISMATCH
CROSS_OBJECT_IDENTITY_MISMATCH = "CROSS_OBJECT_IDENTITY_MISMATCH"
PRIMARY_OWNER_INVALID = "PRIMARY_OWNER_INVALID"
ASSESSMENT_CHAIN_INVALID = "ASSESSMENT_CHAIN_INVALID"
IDENTITY_CONFLICT = identity.IDENTITY_CONFLICT
CLAIM_ID_COLLISION = identity.CLAIM_ID_COLLISION

PAPER_HOSTS = frozenset({"arxiv.org", "export.arxiv.org", "api.openalex.org"})
CODE_HOSTS = frozenset(
    {"api.github.com", "github.com", "raw.githubusercontent.com", "codeload.github.com"}
)
DOCLING_VERSION = "2.117.0"
DOCLING_CORE_VERSION = "2.92.0"
MAX_PAGES = 300
MAX_BYTES = 64 * 1024 * 1024
MAX_REQUESTS = 4

_SCHEMA_TITLES = {
    "video-paper-wiki.projection-input.v1",
    "video-paper-wiki.projection-generation.v1",
    "video-paper-wiki.catalog-rows.v1",
    "video-paper-wiki.upstream-chunk-profile.v1",
    "video-paper-wiki.upstream-bm25-profile.v1",
    "video-paper-wiki.transaction-facade.v1",
    "video-paper-wiki.upstream-authority.v1",
    "video-paper-wiki.upstream-capture-authority.v1",
    "video-paper-wiki.transaction-staging.v1",
    "video-paper-wiki.staged-pdf-capture-request.v1",
    "video-paper-wiki.staged-pdf-capture-authority.v1",
    "video-paper-wiki.staged-code-capture-request.v1",
    "video-paper-wiki.staged-code-capture-authority.v1",
    "video-paper-wiki.operation-result-authority.v1",
    "video-paper-wiki.operation-head.v1",
    "video-paper-wiki.capture-inspection.v1",
    "video-paper-wiki.code-evidence-manifest.v1",
    "video-paper-wiki.ingest-plan.v1",
    "video-paper-wiki.prepared.v1",
    "video-paper-wiki.paper-analysis-draft.v1",
    "video-paper-wiki.paper-code-alignment.v1",
    "video-paper-wiki.paper-record.v1",
    "video-paper-wiki.repo-record.v1",
    "video-paper-wiki.assessment-event.v1",
    "video-paper-wiki.gate-decision.v1",
    "video-paper-wiki.operation-receipt.v1",
    "video-paper-wiki.run-manifest.v1",
    "video-paper-wiki.cli-envelope.v1",
    "video-paper-wiki.compile-input.v1",
    "video-paper-wiki.evidence-inventory.v1",
    "video-paper-wiki.retrieval-config.v1",
    "video-paper-wiki.retrieval-policy.v1",
    "video-paper-wiki.retrieval-gold.v1",
    "video-paper-wiki.backup-manifest.v1",
    "video-paper-wiki.evidence-join-request.v1",
    "video-paper-wiki.evidence-mapping-authority.v1",
    "video-paper-wiki.integrity-audit-authority.v1",
    "video-paper-wiki.knowledge-publication-request.v1",
    "video-paper-wiki.publication-authority.v1",
    "video-paper-wiki.review-decision.v1",
    "video-paper-wiki.review-invalidation-request.v1",
    "video-paper-wiki.review-transition-authority.v1",
    "video-paper-wiki.docling-artifact-set.v1",
    "video-paper-wiki.locator-migration-proposal.v1",
    "video-paper-wiki.search-catalog-generation.v1",
    "video-paper-wiki.search-catalog-export.v1",
    "video-paper-wiki.catalog-report.v1",
    "video-paper-wiki.gate-publication-request.v1",
    "video-paper-wiki.gate-head-registry.v1",
    "video-paper-wiki.gate-consumption.v1",
    "video-paper-wiki.gate-publication-authority.v1",
}


class ContractError(ValueError):
    """Fail-closed contract error with stable code/message/details."""

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


def _from_identity(exc: IdentityError | CanonicalJsonError) -> ContractError:
    exit_code = int(getattr(exc, "exit_code", 2))
    return ContractError(
        str(getattr(exc, "code", CANONICAL_JSON_INVALID)),
        str(getattr(exc, "message", exc)),
        dict(getattr(exc, "details", {}) or {}),
        exit_code=exit_code,
    )


def _pointer(path: Sequence[Any]) -> str:
    if not path:
        return ""
    parts: list[str] = []
    for item in path:
        text = str(item)
        parts.append(text.replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(parts)


def _schema_error(
    message: str,
    *,
    schema: str,
    instance_pointer: str = "",
    keyword: str = "const",
    extra: dict[str, Any] | None = None,
) -> ContractError:
    details: dict[str, Any] = {
        "schema": schema,
        "instance_pointer": instance_pointer,
        "keyword": keyword,
    }
    if extra:
        details.update(extra)
    return ContractError(SCHEMA_INVALID, message, details)


def _build_registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    resources: list[tuple[str, Resource]] = []
    by_title: dict[str, dict[str, Any]] = {}
    for filename in schema_resource_names():
        schema = load_schema_json(filename)
        if schema is None:
            raise ContractError(
                SCHEMA_INVALID,
                f"schema resource is missing: {filename}",
                {"filename": filename},
            )
        schema_id = str(schema.get("$id", ""))
        title = str(schema.get("title", ""))
        if not schema_id:
            raise ContractError(
                SCHEMA_INVALID,
                f"schema is missing $id: {filename}",
                {"filename": filename},
            )
        resources.append((schema_id, Resource.from_contents(schema)))
        if title:
            by_title[title] = schema
    return Registry().with_resources(resources), by_title


@lru_cache(maxsize=1)
def _default_registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    return _build_registry()


def _registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    view = _RESOURCE_VIEW.get()
    if view is None:
        return _default_registry()
    # ContextVar copies inherit the immutable view by reference. Build parsed
    # objects afresh so copied contexts cannot share mutable schema contents.
    return _build_registry()


def schema_by_title(title: str) -> dict[str, Any]:
    _registry_obj, by_title = _registry()
    schema = by_title.get(title)
    if schema is None:
        raise _schema_error(
            f"unknown schema: {title}",
            schema=title,
            keyword="$id",
        )
    return schema


def _validator_for(schema: Mapping[str, Any]) -> Draft202012Validator:
    registry, _by_title = _registry()
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _raise_validation_error(error: ValidationError, schema_name: str) -> None:
    raise _schema_error(
        error.message,
        schema=schema_name,
        instance_pointer=_pointer(list(error.absolute_path)),
        keyword=str(error.validator or "unknown"),
        extra={"schema_path": _pointer(list(error.schema_path))},
    )


def _url_hostname(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return None
    if parsed.username is not None or parsed.password is not None or "@" in url.split("://", 1)[-1].split("/", 1)[0]:
        return None
    host = parsed.hostname
    if host is None:
        return None
    return host.casefold()


def _is_blocked_literal_host(host: str) -> bool:
    if host == "*" or "*" in host:
        return True
    if host in {"localhost", "ip6-localhost"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _path_has_illegal_segments(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return True
    if "\\" in path or path.startswith("/"):
        return True
    segments = path.split("/")
    return any(segment in {"", ".", ".."} for segment in segments)


def _reject_illegal_path(path: str, *, schema_name: str, pointer: str) -> None:
    if _path_has_illegal_segments(path):
        raise _schema_error(
            "path must not contain empty, '.', or '..' segments",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="pattern",
            extra={"path": path},
        )


def _plan_allowed_hosts(plan_kind: object) -> frozenset[str] | None:
    if plan_kind == "paper-source":
        return PAPER_HOSTS
    if plan_kind == "code-evidence":
        return CODE_HOSTS
    return None


def _check_https_input_url(
    url: str,
    *,
    schema_name: str,
    pointer: str,
    allowed: frozenset[str] | None,
    declared_host: str | None = None,
    declared_hosts: set[str] | None = None,
) -> str:
    hostname = _url_hostname(url)
    if hostname is None:
        raise _schema_error(
            "url must be HTTPS without userinfo",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="format",
            extra={"url": url},
        )
    if _is_blocked_literal_host(hostname):
        raise _schema_error(
            "host must be a public exact hostname",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="pattern",
            extra={"url": url, "host": hostname},
        )
    if allowed is not None and hostname not in allowed:
        raise _schema_error(
            "host is not on the plan-kind whitelist",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="enum",
            extra={"url": url, "host": hostname},
        )
    if declared_host is not None and hostname != declared_host.casefold():
        raise _schema_error(
            "url hostname must equal declared host",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="const",
            extra={"url": url, "host": declared_host, "hostname": hostname},
        )
    if declared_hosts and hostname not in declared_hosts:
        raise _schema_error(
            "url hostname must equal declared host",
            schema=schema_name,
            instance_pointer=pointer,
            keyword="const",
            extra={"url": url, "hostname": hostname, "declared_hosts": sorted(declared_hosts)},
        )
    return hostname


def _check_network_targets(document: Mapping[str, Any], schema_name: str) -> None:
    targets = document.get("network_targets")
    if not isinstance(targets, list):
        return
    allowed = _plan_allowed_hosts(document.get("plan_kind"))
    plan_kind = document.get("plan_kind")
    for index, target in enumerate(targets):
        if not isinstance(target, Mapping):
            continue
        pointer = f"/network_targets/{index}"
        url = str(target.get("url", ""))
        host = str(target.get("host", ""))
        if _is_blocked_literal_host(host.casefold()):
            raise _schema_error(
                "host must be a public exact hostname",
                schema=schema_name,
                instance_pointer=f"{pointer}/host",
                keyword="pattern",
                extra={"host": host},
            )
        _check_https_input_url(
            url,
            schema_name=schema_name,
            pointer=f"{pointer}/url",
            allowed=allowed,
            declared_host=host,
        )
        if allowed is not None and host.casefold() not in allowed:
            raise _schema_error(
                "host is not on the plan-kind whitelist",
                schema=schema_name,
                instance_pointer=f"{pointer}/host",
                keyword="enum",
                extra={"host": host, "plan_kind": plan_kind},
            )
        redirects = target.get("redirect_hosts")
        if isinstance(redirects, list):
            for rindex, redirect in enumerate(redirects):
                redirect_host = str(redirect)
                if _is_blocked_literal_host(redirect_host.casefold()) or redirect_host == "*":
                    raise _schema_error(
                        "redirect host must be a public exact hostname",
                        schema=schema_name,
                        instance_pointer=f"{pointer}/redirect_hosts/{rindex}",
                        keyword="pattern",
                        extra={"host": redirect_host},
                    )
                if allowed is not None and redirect_host.casefold() not in allowed:
                    raise _schema_error(
                        "redirect host is not on the plan-kind whitelist",
                        schema=schema_name,
                        instance_pointer=f"{pointer}/redirect_hosts/{rindex}",
                        keyword="enum",
                        extra={"host": redirect_host, "plan_kind": plan_kind},
                    )


def _declared_network_hosts(document: Mapping[str, Any]) -> set[str]:
    targets = document.get("network_targets")
    hosts: set[str] = set()
    if not isinstance(targets, list):
        return hosts
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        host = target.get("host")
        if isinstance(host, str) and host:
            hosts.add(host.casefold())
        redirects = target.get("redirect_hosts")
        if isinstance(redirects, list):
            for redirect in redirects:
                if isinstance(redirect, str) and redirect:
                    hosts.add(redirect.casefold())
    return hosts


def _check_plan_input(document: Mapping[str, Any], schema_name: str) -> None:
    source = document.get("input")
    if not isinstance(source, Mapping):
        return
    allowed = _plan_allowed_hosts(document.get("plan_kind"))
    declared = _declared_network_hosts(document)
    pdf_url = source.get("pdf_url")
    if isinstance(pdf_url, str):
        _check_https_input_url(
            pdf_url,
            schema_name=schema_name,
            pointer="/input/pdf_url",
            allowed=allowed,
            declared_hosts=declared or None,
        )
    for key, value in source.items():
        if key == "pdf_url" or not isinstance(value, str):
            continue
        if "://" in value and key.endswith("url"):
            _check_https_input_url(
                value,
                schema_name=schema_name,
                pointer=f"/input/{key}",
                allowed=allowed,
                declared_hosts=declared or None,
            )
    arxiv_id = source.get("arxiv_id")
    if arxiv_id is not None:
        if not isinstance(arxiv_id, str) or not identity.is_version_stripped_arxiv_id(arxiv_id):
            raise _schema_error(
                "arxiv_id must be a version-stripped arXiv identifier",
                schema=schema_name,
                instance_pointer="/input/arxiv_id",
                keyword="pattern",
                extra={"arxiv_id": arxiv_id},
            )


def _check_plan_object(document: Mapping[str, Any], schema_name: str) -> None:
    _check_network_targets(document, schema_name)
    _check_plan_input(document, schema_name)
    limits = document.get("limits")
    targets = document.get("network_targets")
    if isinstance(limits, Mapping) and isinstance(targets, list):
        req_key = "max_" + "req" + "uests"
        req_cap = limits.get(req_key)
        max_bytes = limits.get("max_bytes")
        if isinstance(req_cap, int) and len(targets) > req_cap:
            raise _schema_error(
                "network_targets exceed the plan request budget",
                schema=schema_name,
                instance_pointer="/network_targets",
                keyword="maxItems",
                extra={"count": len(targets), "limit": req_cap},
            )
        if isinstance(max_bytes, int):
            total = 0
            for index, target in enumerate(targets):
                if not isinstance(target, Mapping):
                    continue
                item_max = target.get("max_bytes")
                if isinstance(item_max, int):
                    if item_max > max_bytes:
                        raise _schema_error(
                            "target max_bytes exceeds plan max_bytes",
                            schema=schema_name,
                            instance_pointer=f"/network_targets/{index}/max_bytes",
                            keyword="maximum",
                        )
                    total += item_max
            if total > max_bytes:
                raise _schema_error(
                    "cumulative target max_bytes exceed plan max_bytes",
                    schema=schema_name,
                    instance_pointer="/limits/max_bytes",
                    keyword="maximum",
                    extra={"cumulative_bytes": total, "max_bytes": max_bytes},
                )
    subject = document.get("stable_subject_id")
    plan_kind = document.get("plan_kind")
    source = document.get("input")
    if isinstance(subject, str) and not identity.is_stable_subject_id(subject):
        raise _schema_error(
            "stable_subject_id is not a legal stable subject",
            schema=schema_name,
            instance_pointer="/stable_subject_id",
            keyword="pattern",
        )
    if plan_kind == "paper-source" and isinstance(subject, str) and not subject.startswith("paper:"):
        raise _schema_error(
            "paper-source plan must use a paper stable subject",
            schema=schema_name,
            instance_pointer="/stable_subject_id",
            keyword="pattern",
        )
    if plan_kind == "code-evidence" and isinstance(subject, str) and not subject.startswith("repo:"):
        raise _schema_error(
            "code-evidence plan must use a repo stable subject",
            schema=schema_name,
            instance_pointer="/stable_subject_id",
            keyword="pattern",
        )
    if isinstance(source, Mapping) and isinstance(subject, str):
        kind = source.get("kind")
        if kind == "arxiv" and subject.startswith("paper:"):
            try:
                expected = identity.paper_subject_id(identity.normalize_arxiv_id(str(source.get("arxiv_id", ""))))
            except IdentityError as exc:
                raise _from_identity(exc) from exc
            if subject != expected:
                raise ContractError(
                    CROSS_OBJECT_IDENTITY_MISMATCH,
                    "plan subject does not match arXiv input",
                    {"stable_subject_id": subject, "expected": expected},
                )
        if kind == "local-blob":
            arxiv_raw = source.get("arxiv_id")
            if isinstance(arxiv_raw, str) and arxiv_raw.strip():
                try:
                    canonical_arxiv = identity.normalize_arxiv_id(arxiv_raw)
                    arxiv_subject = identity.paper_subject_id(canonical_arxiv)
                except IdentityError as exc:
                    raise _from_identity(exc) from exc
                if subject.startswith("paper:arxiv:") and subject != arxiv_subject:
                    raise ContractError(
                        CROSS_OBJECT_IDENTITY_MISMATCH,
                        "plan subject does not match local blob arXiv input",
                        {"stable_subject_id": subject, "expected": arxiv_subject},
                    )
                if subject.startswith("paper:") and not subject.startswith("paper:arxiv:"):
                    raise ContractError(
                        IDENTITY_CONFLICT,
                        "arXiv identifier is present but canonical subject is lower-priority",
                        {
                            "stable_subject_id": subject,
                            "arxiv_id": canonical_arxiv,
                            "expected": arxiv_subject,
                        },
                        exit_code=75,
                    )
            if subject.startswith("paper:sha256:"):
                try:
                    expected = identity.paper_subject_id(identity.normalize_pdf_sha256(str(source.get("local_sha256", ""))))
                except IdentityError as exc:
                    raise _from_identity(exc) from exc
                if subject != expected:
                    raise ContractError(
                        CROSS_OBJECT_IDENTITY_MISMATCH,
                        "plan subject does not match local blob SHA-256",
                        {"stable_subject_id": subject, "expected": expected},
                    )
        if kind == "github-repo" and subject.startswith("repo:"):
            try:
                expected = identity.repo_subject_id(str(source.get("repository", "")))
            except IdentityError as exc:
                raise _from_identity(exc) from exc
            if subject != expected:
                raise ContractError(
                    CROSS_OBJECT_IDENTITY_MISMATCH,
                    "plan subject does not match repository",
                    {"stable_subject_id": subject, "expected": expected},
                )
    stated = document.get("approval_hash")
    if isinstance(stated, str):
        try:
            expected = identity.plan_approval_hash(document)
        except IdentityError as exc:
            raise _from_identity(exc) from exc
        except CanonicalJsonError as exc:
            raise _from_identity(exc) from exc
        if stated != expected:
            raise ContractError(
                PLAN_HASH_MISMATCH,
                "approval_hash does not match the plan JCS digest",
                {"stated": stated, "expected": expected},
            )
    parser = document.get("parser")
    if isinstance(document.get("pipeline_fingerprint"), str):
        pipeline = _bound_pipeline_from_parser(parser) if isinstance(parser, Mapping) else None
        _assert_pipeline_fingerprint(document.get("pipeline_fingerprint"), pipeline)


def _check_receipt_object(document: Mapping[str, Any]) -> None:
    schema_name = "video-paper-wiki.operation-receipt.v1"
    writes = document.get("writes")
    if isinstance(writes, list):
        for index, entry in enumerate(writes):
            if isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
                _reject_illegal_path(
                    str(entry["path"]),
                    schema_name=schema_name,
                    pointer=f"/writes/{index}/path",
                )
    claimed = document.get("claimed_inputs")
    if isinstance(claimed, list):
        for index, entry in enumerate(claimed):
            if isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
                _reject_illegal_path(
                    str(entry["path"]),
                    schema_name=schema_name,
                    pointer=f"/claimed_inputs/{index}/path",
                )
    stated = document.get("intent_sha256")
    if not isinstance(stated, str):
        return
    try:
        expected = identity.receipt_intent_sha256(document)
    except IdentityError as exc:
        raise _from_identity(exc) from exc
    if stated != expected:
        raise ContractError(
            RECEIPT_INTENT_MISMATCH,
            "intent_sha256 does not match {sequence, previous, operation_id, writes, claimed_inputs}",
            {"stated": stated, "expected": expected},
        )
    sequence = document.get("sequence")
    previous = document.get("previous")
    if sequence == 1 and previous is not None:
        raise ContractError(
            CROSS_OBJECT_IDENTITY_MISMATCH,
            "genesis receipt must have previous=null",
            {"sequence": sequence},
        )
    if isinstance(sequence, int) and sequence > 1 and previous is None:
        raise ContractError(
            CROSS_OBJECT_IDENTITY_MISMATCH,
            "non-genesis receipt must cite the previous receipt",
            {"sequence": sequence},
        )


def _check_event_object(document: Mapping[str, Any], schema_name: str) -> None:
    stated = document.get("event_id")
    if not isinstance(stated, str):
        return
    prefix = identity.GATE_EVENT_ID_PREFIX if schema_name.endswith("gate-decision.v1") else identity.EVENT_ID_PREFIX
    try:
        expected = identity.event_id(document, prefix=prefix)
    except IdentityError as exc:
        raise _from_identity(exc) from exc
    if stated != expected:
        raise ContractError(
            EVENT_ID_MISMATCH,
            "event_id does not match JCS digest of the object without event_id",
            {"stated": stated, "expected": expected, "schema": schema_name},
        )


def _claim_missing(code: str, message: str, details: dict[str, Any]) -> ContractError:
    exit_code = 75 if code == CLAIM_ID_COLLISION else 2
    return ContractError(code, message, details, exit_code=exit_code)


def _check_draft_object(document: Mapping[str, Any]) -> None:
    paper_id = document.get("paper_id")
    if not isinstance(paper_id, str) or not identity.is_canonical_paper_id(paper_id):
        raise ContractError(
            INVALID_PAPER_ID,
            "paper_id is not a canonical paper ID",
            {"paper_id": paper_id},
        )
    subject = identity.paper_subject_id(paper_id)
    claims = document.get("claims")
    if not isinstance(claims, list):
        raise _schema_error(
            "claims must be an array",
            schema="video-paper-wiki.paper-analysis-draft.v1",
            instance_pointer="/claims",
            keyword="type",
        )
    seen: dict[str, Mapping[str, Any]] = {}
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            raise _schema_error(
                "claim must be an object",
                schema="video-paper-wiki.paper-analysis-draft.v1",
                instance_pointer=f"/claims/{index}",
                keyword="type",
            )
        stated = claim.get("claim_id")
        text = claim.get("claim_text")
        if not isinstance(stated, str):
            raise _schema_error(
                "claim is missing claim_id",
                schema="video-paper-wiki.paper-analysis-draft.v1",
                instance_pointer=f"/claims/{index}/claim_id",
                keyword="required",
            )
        if not isinstance(text, str):
            raise _claim_missing(
                CLAIM_ID_MISMATCH,
                "claim is missing claim_text",
                {"claim_id": stated, "index": index},
            )
        if stated in seen:
            raise _claim_missing(
                CLAIM_ID_COLLISION,
                "same claim_id with different ref attributes",
                {"claim_id": stated, "index": index},
            )
        seen[stated] = claim
        locators = claim.get("locators")
        if isinstance(locators, list):
            for lindex, locator in enumerate(locators):
                if not isinstance(locator, Mapping):
                    continue
                artifact_path = locator.get("artifact_path")
                if isinstance(artifact_path, str):
                    _reject_illegal_path(
                        artifact_path,
                        schema_name="video-paper-wiki.paper-analysis-draft.v1",
                        pointer=f"/claims/{index}/locators/{lindex}/artifact_path",
                    )
        try:
            expected = identity.claim_id(subject, text, claim.get("locators"))
        except IdentityError as exc:
            raise _from_identity(exc) from exc
        if stated != expected:
            raise ContractError(
                CLAIM_ID_MISMATCH,
                "claim_id does not match identity material",
                {"claim_id": stated, "expected": expected, "index": index},
            )


def _check_paper_record_object(document: Mapping[str, Any]) -> None:
    paper_id = document.get("paper_id")
    if not isinstance(paper_id, str) or not identity.is_canonical_paper_id(paper_id):
        raise ContractError(
            INVALID_PAPER_ID,
            "paper_id is not a canonical paper ID",
            {"paper_id": paper_id},
        )
    extraction = document.get("active_extraction_path")
    if isinstance(extraction, str):
        _reject_illegal_path(
            extraction,
            schema_name="video-paper-wiki.paper-record.v1",
            pointer="/active_extraction_path",
        )


def _check_prepared_object(document: Mapping[str, Any]) -> None:
    fingerprint = document.get("pipeline_fingerprint")
    if fingerprint is not None:
        _assert_pipeline_fingerprint(fingerprint, _bound_pipeline_from_prepared(document))
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list):
        return
    for index, artifact in enumerate(artifacts):
        if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
            _reject_illegal_path(
                str(artifact["path"]),
                schema_name="video-paper-wiki.prepared.v1",
                pointer=f"/artifacts/{index}/path",
            )
    for kind, field in (
        ("parser_config", "parser_config_sha256"),
        ("model_manifest", "model_manifest_sha256"),
    ):
        artifact = _artifact_by_kind(document, kind)
        if artifact is None:
            continue
        stated = document.get(field)
        digest = artifact.get("sha256")
        if stated != digest:
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                f"{field} does not match {kind} artifact",
                {"stated": stated, "artifact": digest, "kind": kind},
            )


def _check_run_manifest_object(document: Mapping[str, Any]) -> None:
    fingerprint = document.get("pipeline_fingerprint")
    if not isinstance(fingerprint, str):
        return
    pipeline = _bound_pipeline_from_run_manifest(document)
    _assert_pipeline_fingerprint(fingerprint, pipeline)


def _check_repo_record_object(document: Mapping[str, Any]) -> None:
    repo = document.get("repo_id")
    canonical = document.get("canonical_repository")
    if isinstance(repo, str) and isinstance(canonical, str):
        try:
            expected = identity.repo_id(canonical)
        except IdentityError as exc:
            raise _from_identity(exc) from exc
        if repo != expected:
            raise ContractError(
                CROSS_OBJECT_IDENTITY_MISMATCH,
                "repo_id does not match casefold canonical repository",
                {"repo_id": repo, "expected": expected},
            )
    paper_ids = document.get("paper_ids")
    if isinstance(paper_ids, list):
        for index, item in enumerate(paper_ids):
            if not isinstance(item, str) or not identity.is_canonical_paper_id(item):
                raise ContractError(
                    INVALID_PAPER_ID,
                    "paper_id is not a canonical paper ID",
                    {"paper_id": item, "index": index},
                )


def _check_alignment_object(document: Mapping[str, Any]) -> None:
    paper_id = document.get("paper_id")
    if isinstance(paper_id, str) and not identity.is_canonical_paper_id(paper_id):
        raise ContractError(
            INVALID_PAPER_ID,
            "paper_id is not a canonical paper ID",
            {"paper_id": paper_id},
        )


def _post_schema_checks(document: Mapping[str, Any], schema_name: str) -> None:
    if schema_name in {
        "video-paper-wiki.source-publication-request.v1", "video-paper-wiki.source-publication-authority.v1",
        "video-paper-wiki.source-publication-proposal.v1", "video-paper-wiki.assessment-heads.v2",
    }:
        from video_paper_wiki.source_publication_contracts import check_document

        check_document(document, schema_name)
        return
    if schema_name in {
        "video-paper-wiki.source-version-association.v1", "video-paper-wiki.source-display-decision.v1",
        "video-paper-wiki.source-display-heads.v1", "video-paper-wiki.paper-record.v2",
        "video-paper-wiki.ledger-locator.v2", "video-paper-wiki.assessment-event.v2",
        "video-paper-wiki.compile-input.v2",
    }:
        from video_paper_wiki.source_semantics_contracts import check_document

        check_document(document, schema_name)
        return
    if schema_name.startswith("video-paper-wiki.markdown-"):
        from video_paper_wiki.markdown_source_contracts import check_document

        check_document(document, schema_name)
    elif schema_name in {"video-paper-wiki.transaction-facade.v1", "video-paper-wiki.operation-head.v1"}:
        from video_paper_wiki.transaction_contracts import _check_transaction, _check_operation_head

        (_check_transaction if schema_name == "video-paper-wiki.transaction-facade.v1" else _check_operation_head)(document)
    elif schema_name == "video-paper-wiki.capture-inspection.v1":
        from video_paper_wiki.capture_contracts import _check_capture_inspection

        _check_capture_inspection(document)
    elif schema_name == "video-paper-wiki.code-evidence-manifest.v1":
        from video_paper_wiki.code_evidence_contracts import _check_code_evidence_manifest

        _check_code_evidence_manifest(document)
    elif schema_name == "video-paper-wiki.upstream-authority.v1":
        from video_paper_wiki.upstream_adapter import _check_upstream_authority

        _check_upstream_authority(document)
    elif schema_name == "video-paper-wiki.upstream-capture-authority.v1":
        from video_paper_wiki.upstream_adapter import _check_upstream_capture_authority

        _check_upstream_capture_authority(document)
    elif schema_name == "video-paper-wiki.transaction-staging.v1":
        from video_paper_wiki.transaction_staging import _check_transaction_staging

        _check_transaction_staging(document)
    elif schema_name == "video-paper-wiki.staged-pdf-capture-request.v1":
        from video_paper_wiki.staged_capture import _check_request

        _check_request(document)
    elif schema_name == "video-paper-wiki.staged-pdf-capture-authority.v1":
        from video_paper_wiki.staged_capture import _check_authority

        _check_authority(document)
    elif schema_name in {"video-paper-wiki.staged-code-capture-request.v1", "video-paper-wiki.staged-code-capture-authority.v1"}:
        from video_paper_wiki.staged_code_capture import _check_authority, _check_request

        (_check_request if schema_name.endswith("request.v1") else _check_authority)(document)
    elif schema_name == "video-paper-wiki.knowledge-publication-request.v1":
        from video_paper_wiki.publication import _check_request
        _check_request(document)
    elif schema_name == "video-paper-wiki.publication-authority.v1":
        from video_paper_wiki.publication import _check_authority
        _check_authority(document)
    elif schema_name == "video-paper-wiki.operation-result-authority.v1":
        from video_paper_wiki.operation_result import _check_result_authority

        _check_result_authority(document)
    elif schema_name in {"video-paper-wiki.gate-publication-request.v1", "video-paper-wiki.gate-head-registry.v1",
                         "video-paper-wiki.gate-consumption.v1", "video-paper-wiki.gate-publication-authority.v1"}:
        from video_paper_wiki.gate_decision import _check_authority, _check_consumption, _check_registry, _check_request
        {"video-paper-wiki.gate-publication-request.v1":_check_request,
         "video-paper-wiki.gate-head-registry.v1":_check_registry,
         "video-paper-wiki.gate-consumption.v1":_check_consumption,
         "video-paper-wiki.gate-publication-authority.v1":_check_authority}[schema_name](document)
    elif schema_name == "video-paper-wiki.ingest-plan.v1":
        _check_plan_object(document, schema_name)
    elif schema_name == "video-paper-wiki.prepared.v1":
        _check_prepared_object(document)
    elif schema_name == "video-paper-wiki.operation-receipt.v1":
        _check_receipt_object(document)
    elif schema_name in {"video-paper-wiki.assessment-event.v1", "video-paper-wiki.gate-decision.v1"}:
        _check_event_object(document, schema_name)
    elif schema_name == "video-paper-wiki.paper-analysis-draft.v1":
        _check_draft_object(document)
    elif schema_name == "video-paper-wiki.paper-record.v1":
        _check_paper_record_object(document)
    elif schema_name == "video-paper-wiki.repo-record.v1":
        _check_repo_record_object(document)
    elif schema_name == "video-paper-wiki.paper-code-alignment.v1":
        _check_alignment_object(document)
    elif schema_name == "video-paper-wiki.run-manifest.v1":
        _check_run_manifest_object(document)


def validate_document(document: object, expected_schema: str | None = None) -> dict[str, Any]:
    """Validate one document against the production schema registry."""

    semantics_names = {
        "video-paper-wiki.source-version-association.v1", "video-paper-wiki.source-display-decision.v1",
        "video-paper-wiki.source-display-heads.v1", "video-paper-wiki.paper-record.v2",
        "video-paper-wiki.ledger-locator.v2", "video-paper-wiki.assessment-event.v2",
        "video-paper-wiki.compile-input.v2",
    }
    requested = expected_schema or (document.get("schema") if type(document) is dict else None)
    is_semantics = type(requested) is str and requested in semantics_names
    is_source_publication = type(requested) is str and requested in {
        "video-paper-wiki.source-publication-request.v1", "video-paper-wiki.source-publication-authority.v1",
        "video-paper-wiki.source-publication-proposal.v1", "video-paper-wiki.assessment-heads.v2",
    }
    if is_source_publication:
        from video_paper_wiki.source_semantics_contracts import preflight

        preflight(document)
    if is_semantics:
        from video_paper_wiki.source_semantics_contracts import preflight

        preflight(document, evidence_scope="compile" if requested == "video-paper-wiki.compile-input.v2" else None)
    if expected_schema in (
        "video-paper-wiki.upstream-chunk-profile.v1",
        "video-paper-wiki.upstream-bm25-profile.v1",
    ):
        from video_paper_wiki.projection_runtime import validate_runtime_record

        kind = "chunk" if expected_schema == "video-paper-wiki.upstream-chunk-profile.v1" else "bm25"
        return validate_runtime_record(kind, document)
    if not isinstance(document, dict):
        raise _schema_error(
            "document must be an object",
            schema=expected_schema or "",
            keyword="type",
        )
    if "schema" in document and not isinstance(document["schema"], str):
        raise _schema_error(
            "document schema must be a string",
            schema=expected_schema or "",
            instance_pointer="/schema",
            keyword="type",
        )
    schema_name = expected_schema or document.get("schema")
    if isinstance(schema_name, str) and schema_name.startswith("video-paper-wiki.markdown-"):
        from video_paper_wiki.markdown_source_contracts import json_preflight

        json_preflight(document)
    if not isinstance(schema_name, str) or not schema_name:
        raise _schema_error(
            "document is missing schema",
            schema=str(expected_schema or ""),
            keyword="required",
        )
    if expected_schema is not None and document.get("schema") not in {None, expected_schema}:
        raise _schema_error(
            "document schema does not match expected schema",
            schema=expected_schema,
            instance_pointer="/schema",
            keyword="const",
            extra={"stated": document.get("schema")},
        )
    if schema_name in {
        "video-paper-wiki.capture-inspection.v1",
        "video-paper-wiki.code-evidence-manifest.v1",
    } and any(not isinstance(key, str) for key in document):
        raise _schema_error(
            "document keys must be strings",
            schema=schema_name,
            keyword="type",
        )
    if schema_name in {
        "video-paper-wiki.transaction-facade.v1",
        "video-paper-wiki.operation-head.v1",
        "video-paper-wiki.upstream-authority.v1",
        "video-paper-wiki.upstream-capture-authority.v1",
        "video-paper-wiki.transaction-staging.v1",
        "video-paper-wiki.staged-pdf-capture-request.v1",
        "video-paper-wiki.staged-pdf-capture-authority.v1",
    }:
        from video_paper_wiki.transaction_contracts import _json_preflight

        _json_preflight(document)
    schema = schema_by_title(schema_name)
    validator = _validator_for(schema)
    try:
        errors = list(validator.iter_errors(document))
    except (ValueError, RecursionError) as exc:
        if schema_name not in {
            "video-paper-wiki.transaction-facade.v1",
            "video-paper-wiki.operation-head.v1",
            "video-paper-wiki.upstream-authority.v1",
            "video-paper-wiki.upstream-capture-authority.v1",
            "video-paper-wiki.transaction-staging.v1",
        }:
            raise
        raise _schema_error(
            "document cannot be schema-validated",
            schema=schema_name,
            keyword="type",
        ) from exc
    if errors:
        if is_source_publication:
            errors.sort(key=lambda error: (tuple(str(x) for x in error.absolute_path), str(error.validator)))
            try:
                _raise_validation_error(errors[0], schema_name)
            except ContractError as exc:
                raise ContractError("SOURCE_PUBLICATION_INVALID", exc.message, exc.details) from None
        if is_semantics:
            errors.sort(key=lambda error: (tuple(str(x) for x in error.absolute_path), str(error.validator)))
            _raise_validation_error(errors[0], schema_name)
        _raise_validation_error(best_match(iter(errors)) or errors[0], schema_name)
    _post_schema_checks(document, schema_name)
    return document


def _require_mapping(bundle: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = bundle.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ContractError(
            SCHEMA_INVALID,
            f"bundle.{key} must be an object",
            {"key": key},
        )
    return value


def _mismatch(message: str, details: dict[str, Any]) -> ContractError:
    return ContractError(CROSS_OBJECT_IDENTITY_MISMATCH, message, details)


def _pdf_artifact_hashes(node: object, acc: list[str]) -> None:
    if isinstance(node, Mapping):
        if node.get("kind") == "pdf" and isinstance(node.get("artifact_sha256"), str):
            acc.append(str(node["artifact_sha256"]))
        for value in node.values():
            _pdf_artifact_hashes(value, acc)
    elif isinstance(node, list):
        for item in node:
            _pdf_artifact_hashes(item, acc)


def _collect_arxiv_candidates(*documents: Mapping[str, Any] | None) -> list[str]:
    found: list[str] = []
    for document in documents:
        if not isinstance(document, Mapping):
            continue
        source = document.get("input")
        if isinstance(source, Mapping) and isinstance(source.get("arxiv_id"), str) and source["arxiv_id"].strip():
            found.append(str(source["arxiv_id"]))
        if isinstance(document.get("arxiv_id"), str) and str(document["arxiv_id"]).strip():
            found.append(str(document["arxiv_id"]))
        meta = document.get("metadata_candidates")
        if isinstance(meta, Mapping) and isinstance(meta.get("arxiv_id"), str) and meta["arxiv_id"].strip():
            found.append(str(meta["arxiv_id"]))
        subject = document.get("stable_subject_id")
        if isinstance(subject, str) and subject.startswith("paper:arxiv:"):
            found.append(subject[len("paper:") :])
        paper_id = document.get("paper_id")
        if isinstance(paper_id, str) and paper_id.startswith("arxiv:"):
            found.append(paper_id)
    return found


def _artifact_by_kind(prepared: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    artifacts = prepared.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    matches = [item for item in artifacts if isinstance(item, Mapping) and item.get("kind") == kind]
    if len(matches) != 1:
        return None
    return matches[0]


def _bound_pipeline_from_parser(parser: Mapping[str, Any]) -> dict[str, str]:
    return identity.bound_pipeline_object(
        engine=str(parser.get("engine", "")),
        engine_version=str(parser.get("engine_version", "")),
        core_version=str(parser.get("core_version", "")),
        config_sha256=str(parser.get("config_sha256", "")),
        model_manifest_sha256=str(parser.get("model_manifest_sha256", "")),
    )


def _bound_pipeline_from_prepared(prepared: Mapping[str, Any]) -> dict[str, str]:
    return identity.bound_pipeline_object(
        engine="docling",
        engine_version=str(prepared.get("docling_version", "")),
        core_version=str(prepared.get("docling_core_version", "")),
        config_sha256=str(prepared.get("parser_config_sha256", "")),
        model_manifest_sha256=str(prepared.get("model_manifest_sha256", "")),
    )


def _bound_pipeline_from_run_manifest(manifest: Mapping[str, Any]) -> dict[str, str] | None:
    versions = manifest.get("tool_versions")
    hashes = manifest.get("input_hashes")
    if not isinstance(versions, Mapping) or not isinstance(hashes, Mapping):
        return None
    engine_version = versions.get("docling")
    core_version = versions.get("docling_core")
    config_sha256 = hashes.get("parser_config_sha256")
    model_manifest_sha256 = hashes.get("model_manifest_sha256")
    if not all(
        isinstance(value, str) and value
        for value in (engine_version, core_version, config_sha256, model_manifest_sha256)
    ):
        return None
    return identity.bound_pipeline_object(
        engine="docling",
        engine_version=str(engine_version),
        core_version=str(core_version),
        config_sha256=str(config_sha256),
        model_manifest_sha256=str(model_manifest_sha256),
    )


def _assert_pipeline_fingerprint(stated: object, pipeline: Mapping[str, Any] | None) -> None:
    if not isinstance(stated, str):
        return
    if pipeline is None:
        raise ContractError(
            PIPELINE_FINGERPRINT_MISMATCH,
            "pipeline_fingerprint is present but cannot be bound to a pipeline object",
            {"stated": stated},
        )
    try:
        expected = identity.pipeline_fingerprint(pipeline)
    except IdentityError as exc:
        raise _from_identity(exc) from exc
    if stated != expected:
        raise ContractError(
            PIPELINE_FINGERPRINT_MISMATCH,
            "pipeline_fingerprint does not match the bound pipeline object",
            {"stated": stated, "expected": expected},
        )


def _line_range_ok(locator: Mapping[str, Any]) -> bool:
    lines = locator.get("lines")
    if not isinstance(lines, Mapping):
        return True
    start = lines.get("start")
    end = lines.get("end")
    if isinstance(start, int) and isinstance(end, int):
        return start <= end
    return True


def _collect_claim_owners(bundle: Mapping[str, Any]) -> dict[str, list[tuple[str, str, str]]]:
    owners: dict[str, list[tuple[str, str, str]]] = {}
    paper = bundle.get("paper_record")
    if isinstance(paper, Mapping):
        refs = paper.get("section_claim_refs")
        paper_id = str(paper.get("paper_id", ""))
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, Mapping):
                    continue
                claim = ref.get("claim_id")
                lifecycle = str(ref.get("lifecycle", ""))
                if isinstance(claim, str):
                    owners.setdefault(claim, []).append(("paper", paper_id, lifecycle))
    repo = bundle.get("repo_record")
    if isinstance(repo, Mapping):
        refs = repo.get("capability_claim_refs")
        repo_id = str(repo.get("repo_id", ""))
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, Mapping):
                    continue
                claim = ref.get("claim_id")
                lifecycle = str(ref.get("lifecycle", ""))
                if isinstance(claim, str):
                    owners.setdefault(claim, []).append(("repo", repo_id, lifecycle))
    return owners


def _claim_entries(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    claims = bundle.get("claims")
    if isinstance(claims, list):
        for item in claims:
            if isinstance(item, Mapping):
                entries.append(dict(item))
    draft = bundle.get("draft")
    if isinstance(draft, Mapping) and isinstance(draft.get("claims"), list):
        paper_id = str(draft.get("paper_id", ""))
        subject = f"paper:{paper_id}" if paper_id else ""
        for item in draft["claims"]:
            if not isinstance(item, Mapping):
                continue
            entries.append(
                {
                    "claim_id": item.get("claim_id"),
                    "stable_subject_id": subject,
                    "canonical_claim_text": item.get("claim_text"),
                    "evidence": item.get("evidence") or [],
                    "locators": item.get("locators") or [],
                }
            )
    return entries


def _assert_unique_claim_refs(
    claims: Sequence[Any],
    *,
    ref_key: str,
    pointer_prefix: str,
) -> None:
    seen: dict[str, Any] = {}
    for index, item in enumerate(claims):
        if not isinstance(item, Mapping):
            raise _schema_error(
                "claim must be an object",
                schema="",
                instance_pointer=f"{pointer_prefix}/{index}",
                keyword="type",
            )
        stated = item.get("claim_id")
        if not isinstance(stated, str):
            raise _schema_error(
                "claim is missing claim_id",
                schema="",
                instance_pointer=f"{pointer_prefix}/{index}/claim_id",
                keyword="required",
            )
        refs = item.get(ref_key)
        if stated in seen:
            raise ContractError(
                CLAIM_ID_COLLISION,
                "same claim_id with different ref attributes",
                {"claim_id": stated, "index": index},
                exit_code=75,
            )
        seen[stated] = refs


def _validate_claim_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    existing_claim_bindings: Mapping[str, tuple[str, str]],
) -> dict[str, tuple[str, str]]:
    bindings = dict(existing_claim_bindings)
    for item in entries:
        stated = item.get("claim_id")
        subject = item.get("stable_subject_id")
        text = item.get("canonical_claim_text")
        if not isinstance(stated, str):
            raise _schema_error(
                "claim is missing claim_id",
                schema="",
                instance_pointer="/claim_id",
                keyword="required",
            )
        if not isinstance(subject, str) or not isinstance(text, str):
            raise ContractError(
                CLAIM_ID_MISMATCH,
                "claim is missing required identity fields",
                {"claim_id": stated, "stable_subject_id": subject},
            )
        try:
            identity.bind_claim_id(
                stated_claim_id=stated,
                subject=subject,
                canonical_claim_text=text,
                existing_claim_bindings=bindings,
                locators=item.get("locators"),
            )
        except IdentityError as exc:
            raise _from_identity(exc) from exc
        bindings[stated] = identity.claim_identity_material(subject, text)
    return bindings


def _validate_events(bundle: Mapping[str, Any], claim_entries: Sequence[Mapping[str, Any]]) -> None:
    events = bundle.get("events")
    if events is None:
        return
    if not isinstance(events, list):
        raise ContractError(SCHEMA_INVALID, "bundle.events must be an array", {"key": "events"})
    by_id: dict[str, Mapping[str, Any]] = {}
    by_claim: dict[str, list[Mapping[str, Any]]] = {}
    evidence_by_claim: dict[str, list[Any]] = {}
    text_by_claim: dict[str, str] = {}
    for item in claim_entries:
        claim = item.get("claim_id")
        if isinstance(claim, str):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                stored = evidence_by_claim.get(claim)
                if stored is None or (not stored and evidence):
                    evidence_by_claim[claim] = list(evidence)
            text = item.get("canonical_claim_text")
            if isinstance(text, str) and text:
                text_by_claim[claim] = text
    for event in events:
        if not isinstance(event, Mapping):
            raise ContractError(SCHEMA_INVALID, "assessment event must be an object")
        schema_name = str(event.get("schema") or "video-paper-wiki.assessment-event.v1")
        validate_document(dict(event), expected_schema=schema_name)
        event_id = str(event.get("event_id", ""))
        if event_id in by_id:
            raise ContractError(
                ASSESSMENT_CHAIN_INVALID,
                "duplicate assessment event_id",
                {"event_id": event_id},
            )
        by_id[event_id] = event
        claim_id = str(event.get("claim_id", ""))
        by_claim.setdefault(claim_id, []).append(event)
        text = text_by_claim.get(claim_id)
        stated_text_hash = event.get("claim_text_sha256")
        if text is not None and isinstance(stated_text_hash, str):
            expected_hash = identity.sha256_hex(text)
            if stated_text_hash != expected_hash:
                raise _mismatch(
                    "claim_text_sha256 does not match claim text",
                    {"claim_id": claim_id, "stated": stated_text_hash, "expected": expected_hash},
                )
    designated = bundle.get("assessment_heads")
    designated_heads = designated if isinstance(designated, Mapping) else {}
    for claim_id, chain in by_claim.items():
        previous_counts: dict[str | None, int] = {}
        children: dict[str | None, list[str]] = {}
        ids = {str(event.get("event_id")) for event in chain}
        for event in chain:
            previous = event.get("previous_event_id")
            event_id = str(event.get("event_id"))
            previous_counts[previous] = previous_counts.get(previous, 0) + 1
            children.setdefault(previous, []).append(event_id)
            if previous is None:
                continue
            parent = by_id.get(previous)
            if parent is None:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "dangling assessment predecessor",
                    {"event_id": event_id, "previous_event_id": previous},
                )
            if str(parent.get("claim_id")) != claim_id:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "cross-claim assessment parent",
                    {
                        "event_id": event_id,
                        "claim_id": claim_id,
                        "parent_claim_id": parent.get("claim_id"),
                    },
                )
            if parent.get("to_assessment") != event.get("from_assessment"):
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "parent to_assessment must equal child from_assessment",
                    {
                        "event_id": event_id,
                        "previous_event_id": previous,
                        "parent_to_assessment": parent.get("to_assessment"),
                        "from_assessment": event.get("from_assessment"),
                    },
                )
            if previous not in ids:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "dangling assessment predecessor",
                    {"event_id": event_id, "previous_event_id": previous},
                )
        for previous, count in previous_counts.items():
            if count > 1:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "assessment chain fork",
                    {"claim_id": claim_id, "previous_event_id": previous},
                )
        referenced = {event.get("previous_event_id") for event in chain if event.get("previous_event_id")}
        heads = [str(event.get("event_id")) for event in chain if event.get("event_id") not in referenced]
        if len(heads) != 1:
            raise ContractError(
                ASSESSMENT_CHAIN_INVALID,
                "assessment chain must have exactly one head",
                {"claim_id": claim_id, "heads": heads},
            )
        # A materialized claim describes the current head.  Earlier events may
        # intentionally retain older evidence fingerprints after a system
        # invalidation, so only the unique terminal event binds current evidence.
        if claim_id in evidence_by_claim:
            evidence=evidence_by_claim[claim_id]
            try:expected=identity.evidence_fingerprint(evidence)
            except IdentityError as exc:raise _from_identity(exc) from exc
            fingerprint=by_id[heads[0]].get("evidence_fingerprint")
            if fingerprint != expected:
                raise ContractError(EVIDENCE_FINGERPRINT_MISMATCH,
                    "head evidence_fingerprint does not match identity fields",
                    {"claim_id":claim_id,"stated":fingerprint,"expected":expected})
        seen: set[str] = set()
        cursor: str | None = heads[0]
        while cursor is not None:
            if cursor in seen:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "assessment chain cycle",
                    {"claim_id": claim_id, "event_id": cursor},
                )
            seen.add(cursor)
            event = by_id[cursor]
            cursor = event.get("previous_event_id") if isinstance(event.get("previous_event_id"), str) else None
        if designated_heads:
            stated_head = designated_heads.get(claim_id)
            if stated_head != heads[0]:
                raise ContractError(
                    ASSESSMENT_CHAIN_INVALID,
                    "designated assessment head is not the unique chain head",
                    {"claim_id": claim_id, "stated": stated_head, "expected": heads[0]},
                )


def _validate_plan_prepared_draft_record(
    bundle: Mapping[str, Any],
    *,
    existing_paper_bindings: Mapping[str, str],
) -> None:
    plan = bundle.get("plan") if isinstance(bundle.get("plan"), Mapping) else None
    prepared = bundle.get("prepared") if isinstance(bundle.get("prepared"), Mapping) else None
    draft = bundle.get("draft") if isinstance(bundle.get("draft"), Mapping) else None
    record = bundle.get("paper_record") if isinstance(bundle.get("paper_record"), Mapping) else None
    alignment = bundle.get("alignment") if isinstance(bundle.get("alignment"), Mapping) else None
    repo = bundle.get("repo_record") if isinstance(bundle.get("repo_record"), Mapping) else None

    if plan is not None and prepared is not None:
        if plan.get("batch_id") != prepared.get("batch_id"):
            raise _mismatch("plan and prepared batch_id differ", {
                "plan_batch_id": plan.get("batch_id"),
                "prepared_batch_id": prepared.get("batch_id"),
            })
        parser = plan.get("parser") if isinstance(plan.get("parser"), Mapping) else {}
        if parser.get("engine_version") != prepared.get("docling_version"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan Docling version does not match prepared",
                {"plan": parser.get("engine_version"), "prepared": prepared.get("docling_version")},
            )
        if parser.get("core_version") != prepared.get("docling_core_version"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan docling-core version does not match prepared",
                {"plan": parser.get("core_version"), "prepared": prepared.get("docling_core_version")},
            )
        if parser.get("config_sha256") != prepared.get("parser_config_sha256"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan parser config hash does not match prepared",
                {"plan": parser.get("config_sha256"), "prepared": prepared.get("parser_config_sha256")},
            )
        if parser.get("model_manifest_sha256") != prepared.get("model_manifest_sha256"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan model manifest hash does not match prepared",
                {
                    "plan": parser.get("model_manifest_sha256"),
                    "prepared": prepared.get("model_manifest_sha256"),
                },
            )
        parser_config = _artifact_by_kind(prepared, "parser_config")
        if parser_config is not None and parser.get("config_sha256") != parser_config.get("sha256"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan parser config hash does not match prepared parser_config artifact",
                {"plan": parser.get("config_sha256"), "artifact": parser_config.get("sha256")},
            )
        model_manifest = _artifact_by_kind(prepared, "model_manifest")
        if model_manifest is not None and parser.get("model_manifest_sha256") != model_manifest.get("sha256"):
            raise ContractError(
                PIPELINE_FINGERPRINT_MISMATCH,
                "plan model manifest hash does not match prepared model_manifest artifact",
                {
                    "plan": parser.get("model_manifest_sha256"),
                    "artifact": model_manifest.get("sha256"),
                },
            )
        expected_pipeline = _bound_pipeline_from_parser(parser) if isinstance(parser, Mapping) else _bound_pipeline_from_prepared(prepared)
        if isinstance(plan.get("pipeline_fingerprint"), str):
            _assert_pipeline_fingerprint(plan.get("pipeline_fingerprint"), expected_pipeline)
        if isinstance(prepared.get("pipeline_fingerprint"), str):
            _assert_pipeline_fingerprint(prepared.get("pipeline_fingerprint"), expected_pipeline)
        source = plan.get("input") if isinstance(plan.get("input"), Mapping) else {}
        local_sha = source.get("local_sha256")
        if isinstance(local_sha, str) and local_sha != prepared.get("pdf_sha256"):
            raise _mismatch(
                "plan local blob SHA-256 does not match prepared pdf_sha256",
                {"plan": local_sha, "prepared": prepared.get("pdf_sha256")},
            )

    paper_id = None
    pdf_sha = None
    if draft is not None:
        paper_id = draft.get("paper_id")
    if record is not None:
        if paper_id is None:
            paper_id = record.get("paper_id")
        elif record.get("paper_id") != paper_id:
            raise _mismatch(
                "draft and paper record paper_id differ",
                {"draft": paper_id, "paper_record": record.get("paper_id")},
            )
    if plan is not None and isinstance(paper_id, str) and identity.is_canonical_paper_id(paper_id):
        stated_subject = plan.get("stable_subject_id")
        try:
            expected_subject = identity.paper_subject_id(paper_id)
        except IdentityError as exc:
            raise _from_identity(exc) from exc
        if stated_subject != expected_subject:
            raise _mismatch(
                "plan subject does not match draft/record paper ID",
                {
                    "stable_subject_id": stated_subject,
                    "paper_id": paper_id,
                    "expected": expected_subject,
                },
            )
    if prepared is not None:
        pdf_sha = prepared.get("pdf_sha256")
    arxiv_candidates = _collect_arxiv_candidates(plan, prepared, record)
    if isinstance(paper_id, str) and paper_id.strip():
        source = plan.get("input") if plan is not None and isinstance(plan.get("input"), Mapping) else {}
        local_sha = source.get("local_sha256") if isinstance(source, Mapping) else None
        digest = pdf_sha if isinstance(pdf_sha, str) else local_sha if isinstance(local_sha, str) else None
        try:
            identity.establish_canonical_paper_id(
                arxiv_ids=arxiv_candidates,
                pdf_sha256=digest if isinstance(digest, str) else None,
                existing_paper_id=paper_id,
            )
        except IdentityError as exc:
            raise _from_identity(exc) from exc
    if isinstance(paper_id, str) and isinstance(pdf_sha, str):
        bound = existing_paper_bindings.get(paper_id)
        if bound is not None and bound != pdf_sha:
            raise ContractError(
                IDENTITY_CONFLICT,
                "canonical paper ID is bound to a different PDF SHA-256",
                {"paper_id": paper_id, "bound_sha256": bound, "pdf_sha256": pdf_sha},
                exit_code=75,
            )
        for other_id, other_sha in existing_paper_bindings.items():
            if other_sha == pdf_sha and other_id != paper_id:
                raise ContractError(
                    IDENTITY_CONFLICT,
                    "PDF SHA-256 is already bound to a different paper ID",
                    {"paper_id": paper_id, "bound_paper_id": other_id, "pdf_sha256": pdf_sha},
                    exit_code=75,
                )
    if prepared is not None:
        document_json = _artifact_by_kind(prepared, "document_json")
        if record is not None and document_json is not None:
            if record.get("active_extraction_path") != document_json.get("path"):
                raise _mismatch(
                    "active extraction path does not match prepared document_json",
                    {
                        "active_extraction_path": record.get("active_extraction_path"),
                        "document_json_path": document_json.get("path"),
                    },
                )
            if record.get("active_extraction_sha256") != document_json.get("sha256"):
                raise _mismatch(
                    "active extraction hash does not match prepared document_json",
                    {
                        "active_extraction_sha256": record.get("active_extraction_sha256"),
                        "document_json_sha256": document_json.get("sha256"),
                    },
                )
        if document_json is not None and (draft is not None or bundle.get("claims") is not None or alignment is not None):
            locator_hashes: list[str] = []
            for key in ("draft", "alignment", "claims"):
                _pdf_artifact_hashes(bundle.get(key), locator_hashes)
            expected_doc_hash = document_json.get("sha256")
            for stated_hash in locator_hashes:
                if stated_hash != expected_doc_hash:
                    raise ContractError(
                        EVIDENCE_FINGERPRINT_MISMATCH,
                        "locator/evidence document hash does not match prepared document_json",
                        {"stated": stated_hash, "document_json_sha256": expected_doc_hash},
                    )
        if record is not None:
            page_count = prepared.get("page_count")
            refs = []
            if draft is not None and isinstance(draft.get("claims"), list):
                refs.extend(draft["claims"])
            for claim in refs:
                if not isinstance(claim, Mapping):
                    continue
                locators = claim.get("locators")
                if not isinstance(locators, list):
                    continue
                for locator in locators:
                    if not isinstance(locator, Mapping) or locator.get("kind") != "pdf":
                        continue
                    page = locator.get("page")
                    if isinstance(page, int) and isinstance(page_count, int) and page > page_count:
                        raise _mismatch(
                            "PDF locator page exceeds prepared page_count",
                            {"page": page, "page_count": page_count},
                        )
    if alignment is not None:
        if isinstance(paper_id, str) and alignment.get("paper_id") != paper_id:
            raise _mismatch(
                "alignment paper_id does not match paper identity",
                {"alignment": alignment.get("paper_id"), "paper_id": paper_id},
            )
        if repo is not None:
            try:
                expected_repo = identity.repo_id(str(alignment.get("repository", "")))
            except IdentityError as exc:
                raise _from_identity(exc) from exc
            if repo.get("repo_id") != expected_repo:
                raise _mismatch(
                    "alignment repository does not match repo record",
                    {"alignment": alignment.get("repository"), "repo_id": repo.get("repo_id")},
                )
            if alignment.get("commit") != repo.get("canonical_commit"):
                raise _mismatch(
                    "alignment commit does not match repo record",
                    {"alignment": alignment.get("commit"), "repo": repo.get("canonical_commit")},
                )
            if str(repo.get("canonical_repository", "")).casefold() != str(alignment.get("repository", "")).casefold():
                raise _mismatch(
                    "alignment repository does not match canonical repository",
                    {
                        "alignment": alignment.get("repository"),
                        "canonical_repository": repo.get("canonical_repository"),
                    },
                )
            paper_ids = repo.get("paper_ids")
            if isinstance(paper_ids, list) and isinstance(paper_id, str) and paper_id not in paper_ids:
                raise _mismatch(
                    "repo record does not list the paper ID",
                    {"paper_id": paper_id, "paper_ids": paper_ids},
                )
        capabilities = alignment.get("capabilities")
        if isinstance(capabilities, list):
            for capability in capabilities:
                if not isinstance(capability, Mapping):
                    continue
                locators = capability.get("locators")
                if not isinstance(locators, list):
                    continue
                for locator in locators:
                    if not isinstance(locator, Mapping):
                        continue
                    if locator.get("kind") == "code":
                        if not _line_range_ok(locator):
                            raise _mismatch(
                                "code locator line start must be <= end",
                                {"lines": locator.get("lines")},
                            )
                        if repo is not None:
                            if str(locator.get("repository", "")).casefold() != str(repo.get("canonical_repository", "")).casefold():
                                raise _mismatch(
                                    "code locator repository does not match repo record",
                                    {
                                        "locator": locator.get("repository"),
                                        "canonical_repository": repo.get("canonical_repository"),
                                    },
                                )
                            if locator.get("commit") != repo.get("canonical_commit"):
                                raise _mismatch(
                                    "code locator commit does not match repo record",
                                    {
                                        "locator": locator.get("commit"),
                                        "canonical_commit": repo.get("canonical_commit"),
                                    },
                                )
    _validate_run_manifest_hashes(bundle)


def _validate_run_manifest_hashes(bundle: Mapping[str, Any]) -> None:
    manifest = bundle.get("run_manifest")
    if not isinstance(manifest, Mapping):
        return
    plan = bundle.get("plan") if isinstance(bundle.get("plan"), Mapping) else None
    prepared = bundle.get("prepared") if isinstance(bundle.get("prepared"), Mapping) else None
    draft = bundle.get("draft") if isinstance(bundle.get("draft"), Mapping) else None
    receipt = bundle.get("receipt") if isinstance(bundle.get("receipt"), Mapping) else None
    input_hashes = manifest.get("input_hashes") if isinstance(manifest.get("input_hashes"), Mapping) else {}
    output_hashes = manifest.get("output_hashes") if isinstance(manifest.get("output_hashes"), Mapping) else {}
    fingerprint = manifest.get("pipeline_fingerprint")
    if isinstance(fingerprint, str):
        pipeline = None
        if prepared is not None:
            pipeline = _bound_pipeline_from_prepared(prepared)
        elif plan is not None and isinstance(plan.get("parser"), Mapping):
            pipeline = _bound_pipeline_from_parser(plan["parser"])
        else:
            pipeline = _bound_pipeline_from_run_manifest(manifest)
        _assert_pipeline_fingerprint(fingerprint, pipeline)

    def _check(stated: object, expected: object, message: str) -> None:
        if not isinstance(stated, str):
            return
        if stated != expected:
            raise _mismatch(message, {"stated": stated, "expected": expected})

    try:
        if plan is not None:
            _check(
                input_hashes.get("ingest_plan_sha256"),
                identity.canonical_object_sha256(plan),
                "run manifest ingest_plan_sha256 does not match plan",
            )
        if prepared is not None:
            _check(
                input_hashes.get("prepared_sha256"),
                identity.canonical_object_sha256(prepared),
                "run manifest prepared_sha256 does not match prepared",
            )
            _check(
                input_hashes.get("source_sha256"),
                prepared.get("pdf_sha256"),
                "run manifest source_sha256 does not match prepared pdf_sha256",
            )
            _check(
                input_hashes.get("parser_config_sha256"),
                prepared.get("parser_config_sha256"),
                "run manifest parser_config_sha256 does not match prepared",
            )
            _check(
                input_hashes.get("model_manifest_sha256"),
                prepared.get("model_manifest_sha256"),
                "run manifest model_manifest_sha256 does not match prepared",
            )
            document_json = _artifact_by_kind(prepared, "document_json")
            if document_json is not None:
                _check(
                    output_hashes.get("document_json_sha256"),
                    document_json.get("sha256"),
                    "run manifest document_json_sha256 does not match prepared document_json",
                )
        elif plan is not None:
            source = plan.get("input") if isinstance(plan.get("input"), Mapping) else {}
            _check(
                input_hashes.get("source_sha256"),
                source.get("local_sha256") if isinstance(source, Mapping) else None,
                "run manifest source_sha256 does not match plan local blob SHA-256",
            )
        if draft is not None:
            _check(
                output_hashes.get("draft_sha256"),
                identity.canonical_object_sha256(draft),
                "run manifest draft_sha256 does not match draft",
            )
        if receipt is not None:
            _check(
                output_hashes.get("receipt_sha256"),
                identity.canonical_object_sha256(receipt),
                "run manifest receipt_sha256 does not match receipt",
            )
    except IdentityError as exc:
        raise _from_identity(exc) from exc


def _validate_owners(bundle: Mapping[str, Any], claim_entries: Sequence[Mapping[str, Any]]) -> None:
    owners = _collect_claim_owners(bundle)
    claim_ids = [
        item.get("claim_id")
        for item in claim_entries
        if isinstance(item.get("claim_id"), str)
    ]
    record_present = isinstance(bundle.get("paper_record"), Mapping) or isinstance(bundle.get("repo_record"), Mapping)
    if not record_present:
        return
    unique_ids = list(dict.fromkeys(claim_ids))
    for claim_id in unique_ids:
        found = owners.get(str(claim_id), [])
        if len(found) != 1:
            raise ContractError(
                PRIMARY_OWNER_INVALID,
                "each claim must have exactly one primary owner",
                {"claim_id": claim_id, "owners": found},
            )
    for claim_id, found in owners.items():
        if len(found) != 1:
            raise ContractError(
                PRIMARY_OWNER_INVALID,
                "each claim must have exactly one primary owner",
                {"claim_id": claim_id, "owners": found},
            )


def validate_prospective(
    bundle: object,
    *,
    existing_paper_bindings: Mapping[str, str] | None = None,
    existing_claim_bindings: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """In-memory identity/consistency validator. Does not read or write a Vault."""

    if not isinstance(bundle, Mapping):
        raise _schema_error("prospective bundle must be an object", schema="", keyword="type")
    paper_bindings = {str(key): str(value) for key, value in dict(existing_paper_bindings or {}).items()}
    claim_bindings: dict[str, tuple[str, str]] = {}
    for key, value in dict(existing_claim_bindings or {}).items():
        if isinstance(value, (list, tuple)) and len(value) == 2:
            claim_bindings[str(key)] = (str(value[0]), str(value[1]))
        elif isinstance(value, Mapping) and "stable_subject_id" in value and "canonical_claim_text" in value:
            claim_bindings[str(key)] = (
                str(value["stable_subject_id"]),
                str(value["canonical_claim_text"]),
            )
    for key, schema_name in (
        ("plan", "video-paper-wiki.ingest-plan.v1"),
        ("prepared", "video-paper-wiki.prepared.v1"),
        ("draft", "video-paper-wiki.paper-analysis-draft.v1"),
        ("paper_record", "video-paper-wiki.paper-record.v1"),
        ("repo_record", "video-paper-wiki.repo-record.v1"),
        ("alignment", "video-paper-wiki.paper-code-alignment.v1"),
        ("receipt", "video-paper-wiki.operation-receipt.v1"),
        ("run_manifest", "video-paper-wiki.run-manifest.v1"),
        ("gate", "video-paper-wiki.gate-decision.v1"),
    ):
        document = bundle.get(key)
        if document is None:
            continue
        if not isinstance(document, Mapping):
            raise _schema_error(
                f"bundle.{key} must be an object",
                schema=schema_name,
                keyword="type",
            )
        validate_document(dict(document), expected_schema=schema_name)
    if "claims" in bundle:
        top_claims = bundle["claims"]
        if not isinstance(top_claims, list):
            raise ContractError(
                SCHEMA_INVALID,
                "bundle.claims must be an array",
                {"key": "claims"},
            )
        _assert_unique_claim_refs(top_claims, ref_key="evidence", pointer_prefix="/claims")
    claim_entries = _claim_entries(bundle)
    _validate_claim_entries(claim_entries, existing_claim_bindings=claim_bindings)
    _validate_plan_prepared_draft_record(bundle, existing_paper_bindings=paper_bindings)
    _validate_owners(bundle, claim_entries)
    _validate_events(bundle, claim_entries)
    return dict(bundle)


__all__ = [
    "ASSESSMENT_CHAIN_INVALID",
    "CANONICAL_JSON_INVALID",
    "CLAIM_ID_COLLISION",
    "CLAIM_ID_MISMATCH",
    "CODE_HOSTS",
    "CROSS_OBJECT_IDENTITY_MISMATCH",
    "ContractError",
    "DOCLING_CORE_VERSION",
    "DOCLING_VERSION",
    "EVENT_ID_MISMATCH",
    "EVIDENCE_FINGERPRINT_MISMATCH",
    "IDENTITY_CONFLICT",
    "INVALID_PAPER_ID",
    "MAX_BYTES",
    "MAX_PAGES",
    "MAX_REQUESTS",
    "PAPER_HOSTS",
    "PIPELINE_FINGERPRINT_MISMATCH",
    "PLAN_HASH_MISMATCH",
    "PRIMARY_OWNER_INVALID",
    "RECEIPT_INTENT_MISMATCH",
    "SCHEMA_INVALID",
    "schema_by_title",
    "validate_document",
    "validate_prospective",
]
