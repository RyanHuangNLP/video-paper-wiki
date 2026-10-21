"""Read-only domain annotation and paper-code relation candidate inspect."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from video_paper_wiki.code_proof_io import CodeProofIOError, open_code_session
from video_paper_wiki.code_proof_public import CodeProofPublicError, status_code_proof
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import repo_id
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.markdown_locator import decode_evidence, evidence_fingerprint_versioned
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.secure_io import (
    JSON_MAX_BYTES,
    SecureIOError,
    load_strict_json,
    parse_strict_json,
)
from video_paper_wiki.source_publication import _vault
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_state import _claim_ledger
from video_paper_wiki.staging import StagingError, validate_batch_id

PROPOSAL_SCHEMA = "video-paper-wiki.domain-proposal.v1"
REPORT_SCHEMA = "video-paper-wiki.domain-proposal-report.v1"
COMMAND = "domain.inspect"

CONCEPT_KINDS = (
    "Method",
    "Model",
    "ArchitectureComponent",
    "TrainingRecipe",
    "Dataset",
    "Benchmark",
    "InferenceRecipe",
    "EvaluationMetric",
)
CLAIM_KINDS = (
    "architecture",
    "training",
    "empirical_result",
    "implementation",
    "ablation",
    "limitation",
    "reproducibility",
    "license",
    "resource_requirement",
)
RELATION_KINDS = (
    "this_paper_implementation",
    "baseline",
    "dependency",
    "third_party_reproduction",
    "unknown",
)
CAPABILITY_NAMES = ("training", "inference", "data", "evaluation", "checkpoints")
SHORTCUTS = (
    "url_match",
    "account_similarity",
    "organization_affiliation",
    "reverse_citation_only",
    "config_filename",
    "hash_verified",
)
MESSAGES = {
    "DOMAIN_PROPOSAL_INVALID": "domain proposal is invalid",
    "DOMAIN_PROPOSAL_LIMIT": "domain proposal exceeds a closed bound",
    "DOMAIN_PROPOSAL_LOCATOR_INVALID": "domain proposal locator is invalid",
    "DOMAIN_PROPOSAL_BINDING_MISMATCH": "domain proposal binding mismatch",
    "DOMAIN_PROPOSAL_INPUT_MISSING": "required domain proposal input is missing",
    "DOMAIN_PROPOSAL_INPUT_CHANGED": "required domain proposal input changed",
}

_ASSOCIATION_DIR = "wiki/meta/records/source-versions/"
_EVENT_DIR = "wiki/meta/reviews/"


class DomainProposalError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def _fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise DomainProposalError(
        code, MESSAGES.get(code, code), details, exit_code=exit_code
    )


def _pointer(*parts):
    out = ""
    for part in parts:
        out += "/" + str(part).replace("~", "~0").replace("/", "~1")
    return out


def inspect_domain_proposal(*, input_path, vault_root, code_batch_id):
    batch = _batch(code_batch_id)
    vault = _vault_root(vault_root)
    proposal = _load_proposal(input_path)
    if proposal["code_batch_id"] != batch:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/code_batch_id",
            "repair_bindings",
            {"field": "code_batch_id"},
        )
    self_reported = proposal.get("self_reported")
    authority = _read_vault(vault, proposal)
    code = _read_code(batch, proposal)
    _bind_paper_code(proposal, authority, code)
    concepts = _concepts(proposal["concepts"])
    claims, unannotated = _claims(proposal["claim_annotations"], authority)
    relation = _relation(proposal["relation"], proposal, authority, code)
    capabilities = _capabilities(proposal["capabilities"], proposal, code)
    report = {
        "schema": REPORT_SCHEMA,
        "status": "proposal_only",
        "publication": "unpublished",
        "review": "pending_semantic_review",
        "successor_only": True,
        "source_association_verified": False,
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "paper_id": proposal["paper_id"],
        "source_association": dict(proposal["source_association"]),
        "source_digest": dict(proposal["source_digest"]),
        "repository": code["repository"],
        "commit": code["commit"],
        "code_batch_id": batch,
        "code_refs": {
            "request": dict(proposal["code_refs"]["request"]),
            "observation": dict(proposal["code_refs"]["observation"]),
            "handoffs": [dict(row) for row in proposal["code_refs"]["handoffs"]],
        },
        "concepts": concepts,
        "claim_annotations": claims,
        "unannotated_claims": unannotated,
        "relation": relation,
        "capabilities": capabilities,
        "bindings": {
            "source_digest_verified": True,
            "claim_bindings_verified": True,
            "assessment_heads_verified": True,
            "code_refs_verified": True,
        },
        "next_action": "semantic_review_required",
    }
    if self_reported is not None:
        _ignore_self_reported(self_reported, report)
    try:
        sealed = json.loads(canonicalize(report).decode("utf-8"))
    except CanonicalJsonError:
        _fail("DOMAIN_PROPOSAL_INVALID", "", "repair_input", {"reason": "canonical_bytes"})
    validate_document(sealed, REPORT_SCHEMA)
    if (
        sealed["canonical_official"] is not False
        or sealed["current_supported_typed_fact"] is not False
        or sealed["successor_only"] is not True
        or sealed["source_association_verified"] is not False
        or sealed["status"] != "proposal_only"
        or sealed["publication"] != "unpublished"
    ):
        _fail("DOMAIN_PROPOSAL_INVALID", "", "repair_input", {"reason": "publication_guard"})
    return sealed


def _batch(value):
    try:
        return validate_batch_id(value)
    except StagingError as exc:
        raise DomainProposalError(
            exc.code,
            exc.message,
            {"instance_pointer": "/code_batch_id", "next_action": "repair_input", **exc.details},
        ) from exc


def _vault_root(value):
    try:
        return checked_path(value)
    except ContractError as exc:
        raise DomainProposalError(
            exc.code,
            exc.message,
            {"instance_pointer": "/vault_root", "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc


def _load_proposal(input_path):
    try:
        path = Path(input_path)
        parsed = load_strict_json(
            path,
            missing_code="DOMAIN_PROPOSAL_INPUT_MISSING",
            unsafe_code="WORK_PATH_UNSAFE",
            invalid_code="DOMAIN_PROPOSAL_INVALID",
            changed_code="DOMAIN_PROPOSAL_INPUT_CHANGED",
            max_bytes=JSON_MAX_BYTES,
        )
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = exc.code
        if reason == "depth":
            code = "DOMAIN_PROPOSAL_LIMIT"
        elif code == "DOMAIN_PROPOSAL_INPUT_CHANGED":
            pass
        elif code not in MESSAGES and code != "WORK_PATH_UNSAFE":
            code = "DOMAIN_PROPOSAL_INVALID"
        next_action = "repeat_read" if code == "DOMAIN_PROPOSAL_INPUT_CHANGED" else "repair_input"
        raise DomainProposalError(
            code,
            MESSAGES.get(code, exc.message),
            {"instance_pointer": "/input", "next_action": next_action, **exc.details},
            exit_code=75 if code == "DOMAIN_PROPOSAL_INPUT_CHANGED" else getattr(exc, "exit_code", 2),
        ) from exc
    if type(parsed) is not dict:
        _fail("DOMAIN_PROPOSAL_INVALID", "/input", "repair_input", {"reason": "type"})
    try:
        return validate_document(parsed, PROPOSAL_SCHEMA)
    except ContractError as exc:
        _map_schema(exc, "repair_input")


def _map_schema(exc, next_action):
    pointer = exc.details.get("instance_pointer") or ""
    code = "DOMAIN_PROPOSAL_INVALID"
    if exc.code in {"SOURCE_SEMANTICS_LIMIT", "TRANSACTION_LIMIT_EXCEEDED"}:
        code = "DOMAIN_PROPOSAL_LIMIT"
    raise DomainProposalError(
        code,
        MESSAGES[code],
        {"instance_pointer": pointer, "next_action": next_action, **exc.details},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _read_json(snapshot, relative, pointer):
    try:
        raw = snapshot.read(relative)
    except ContractError as exc:
        _missing(pointer, relative, exc)
    except OSError:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", pointer, "repair_input", {"path": relative})
    try:
        return parse_strict_json(raw, invalid_code="DOMAIN_PROPOSAL_INVALID"), raw
    except SecureIOError as exc:
        reason = exc.details.get("reason")
        code = "DOMAIN_PROPOSAL_LIMIT" if reason == "depth" else "DOMAIN_PROPOSAL_INVALID"
        _fail(code, pointer, "repair_input", {"path": relative, **exc.details})


def _missing(pointer, relative, exc):
    code = exc.code
    if code in {"AUDIT_RACE"}:
        _fail(
            "DOMAIN_PROPOSAL_INPUT_CHANGED",
            pointer,
            "repeat_read",
            {"path": relative, **exc.details},
            exit_code=75,
        )
    _fail(
        "DOMAIN_PROPOSAL_INPUT_MISSING",
        pointer,
        "repair_input",
        {"path": relative, "prior_code": code, **exc.details},
        exit_code=getattr(exc, "exit_code", 2),
    )


def _read_bytes(snapshot, relative, pointer):
    try:
        return snapshot.read(relative)
    except ContractError as exc:
        _missing(pointer, relative, exc)


def _read_vault(vault_root, proposal):
    assoc_ref = proposal["source_association"]
    assoc_path = _ASSOCIATION_DIR + assoc_ref["association_id"] + ".json"
    try:
        with _vault(vault_root, None) as (_root, snapshot, _captured):
            assoc_doc, assoc_raw = _read_json(snapshot, assoc_path, "/source_association")
            if sha(assoc_raw) != assoc_ref["sha256"]:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/source_association/sha256",
                    "repair_bindings",
                    {"field": "source_association"},
                )
            try:
                validate_document(assoc_doc, "video-paper-wiki.source-version-association.v1")
            except ContractError as exc:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/source_association",
                    "repair_bindings",
                    {"prior_code": exc.code, **exc.details},
                )
            if assoc_doc["paper_id"] != proposal["paper_id"]:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/paper_id",
                    "repair_bindings",
                    {"field": "paper_id"},
                )
            digest = proposal["source_digest"]
            if digest["path"] != assoc_doc["raw"]["path"]:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/source_digest/path",
                    "repair_bindings",
                    {"field": "source_digest"},
                )
            source_raw = _read_bytes(snapshot, digest["path"], "/source_digest")
            if sha(source_raw) != digest["sha256"] or len(source_raw) != digest["size_bytes"]:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/source_digest",
                    "repair_bindings",
                    {"field": "source_digest"},
                )
            if digest["sha256"] != assoc_doc["raw"]["sha256"] or digest["size_bytes"] != assoc_doc["raw"]["size_bytes"]:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    "/source_digest",
                    "repair_bindings",
                    {"field": "source_digest"},
                )
            ledger_raw = _read_bytes(snapshot, CLAIM_LEDGER, "/claim_annotations")
            try:
                ledger = _claim_ledger(ledger_raw, structural=False)
            except ContractError as exc:
                _fail(
                    "DOMAIN_PROPOSAL_INPUT_MISSING",
                    "/claim_annotations",
                    "repair_input",
                    {"prior_code": exc.code, **exc.details},
                )
            heads_doc, heads_raw = _read_json(snapshot, ASSESSMENT_HEADS, "/claim_annotations")
            try:
                validate_document(heads_doc, "video-paper-wiki.assessment-heads.v2")
            except ContractError as exc:
                _fail(
                    "DOMAIN_PROPOSAL_INPUT_MISSING",
                    "/claim_annotations",
                    "repair_input",
                    {"prior_code": exc.code, **exc.details},
                )
            events = {}
            for annotation in proposal["claim_annotations"]:
                cid = annotation["claim_id"]
                eid = annotation["assessment_head"]["event_id"]
                event_path = _EVENT_DIR + cid + "/" + eid + ".json"
                event_doc, event_raw = _read_json(
                    snapshot, event_path, _pointer("claim_annotations", "assessment_head")
                )
                events[eid] = (event_doc, event_raw)
            local_files = {}
            relation = proposal["relation"]
            page = relation["evidence_classes"]["B"]["project_page"]
            if relation["evidence_classes"]["B"]["present"] and page is not None:
                path = page["local_digest"]["path"]
                local_files[path] = _read_bytes(snapshot, path, "/relation/evidence_classes/B")
            snapshot.verify()
    except DomainProposalError:
        raise
    except ContractError as exc:
        code = exc.code
        if code == "AUDIT_RACE":
            _fail(
                "DOMAIN_PROPOSAL_INPUT_CHANGED",
                "/vault_root",
                "repeat_read",
                dict(exc.details),
                exit_code=75,
            )
        raise DomainProposalError(
            code if code == "WORK_PATH_UNSAFE" else "DOMAIN_PROPOSAL_INPUT_MISSING",
            exc.message,
            {"instance_pointer": "/vault_root", "next_action": "repair_input", **exc.details},
            exit_code=getattr(exc, "exit_code", 2),
        ) from exc
    except StagingError as exc:
        raise DomainProposalError(
            exc.code,
            exc.message,
            {"instance_pointer": "/vault_root", "next_action": "repair_input", **exc.details},
        ) from exc
    return {
        "association": assoc_doc,
        "association_raw": assoc_raw,
        "source_raw": source_raw,
        "ledger": ledger,
        "heads": heads_doc,
        "heads_raw": heads_raw,
        "events": events,
        "local_files": local_files,
    }


def _read_code(batch, proposal):
    try:
        status = status_code_proof(batch_id=batch)
    except (CodeProofPublicError, CodeProofIOError) as exc:
        _code_error(exc)
    except StagingError as exc:
        raise DomainProposalError(
            exc.code,
            exc.message,
            {"instance_pointer": "/code_batch_id", "next_action": "repair_input", **exc.details},
        ) from exc
    if status["state"] != "observed":
        _fail(
            "DOMAIN_PROPOSAL_INPUT_MISSING",
            "/code_refs",
            "supply_code_handoff",
            {"state": status["state"]},
        )
    if status["request"] is None or status["observation"] is None:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", "/code_refs", "supply_code_handoff")
    refs = proposal["code_refs"]
    if status["request"] != refs["request"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/code_refs/request",
            "repair_bindings",
            {"field": "request"},
        )
    if status["observation"] != refs["observation"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/code_refs/observation",
            "repair_bindings",
            {"field": "observation"},
        )
    by_path = {row["path"]: row["reference"] for row in status["handoffs"]}
    if not refs["handoffs"]:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", "/code_refs/handoffs", "supply_code_handoff")
    for index, row in enumerate(refs["handoffs"]):
        found = by_path.get(row["path"])
        if found is None or found["id"] != row["id"] or found["sha256"] != row["sha256"]:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                _pointer("code_refs", "handoffs", index),
                "repair_bindings",
                {"field": "handoff"},
            )
    try:
        with open_code_session(batch_id=batch) as session:
            snap = session.snapshot()
            request_env = _parse_envelope(snap.get("request.json"), "/code_refs/request")
            observation_env = _parse_envelope(snap.get("observation.json"), "/code_refs/observation")
            bodies = {}
            handoff_rows = []
            for index, row in enumerate(refs["handoffs"]):
                name = "handoffs/" + hashlib.sha256(row["path"].encode("ascii")).hexdigest() + ".json"
                payload = snap.get(name)
                env = _parse_envelope(payload, _pointer("code_refs", "handoffs", index))
                data = env["data"]
                if data.get("successor_only") is not True:
                    _fail(
                        "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                        _pointer("code_refs", "handoffs", index, "successor_only"),
                        "repair_bindings",
                    )
                if data.get("source_association_verified") is not False:
                    _fail(
                        "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                        _pointer("code_refs", "handoffs", index, "source_association_verified"),
                        "repair_bindings",
                    )
                blob_oid = data["blob"]["oid"]
                body_name = "objects/" + blob_oid + ".body"
                if body_name in snap:
                    bodies[row["path"]] = snap[body_name]
                handoff_rows.append(data)
            session.verify()
    except DomainProposalError:
        raise
    except (CodeProofPublicError, CodeProofIOError) as exc:
        _code_error(exc)
    except StagingError as exc:
        raise DomainProposalError(
            exc.code,
            exc.message,
            {"instance_pointer": "/code_batch_id", "next_action": "repair_input", **exc.details},
        ) from exc
    request_data = request_env["data"]
    return {
        "status": status,
        "request": request_data,
        "observation": observation_env["data"],
        "handoffs": handoff_rows,
        "bodies": bodies,
        "paper_id": request_data["paper_id"],
        "repository": request_data["repository"],
        "commit": request_data["commit_oid"],
        "source_association": request_data["source_association"],
        "targets": [item["path"] for item in request_data["targets"]],
    }


def _parse_envelope(payload, pointer):
    if payload is None:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", pointer, "supply_code_handoff")
    try:
        env = parse_strict_json(payload, invalid_code="DOMAIN_PROPOSAL_INVALID")
    except SecureIOError as exc:
        _fail("DOMAIN_PROPOSAL_INVALID", pointer, "repair_input", dict(exc.details))
    if type(env) is not dict or "data" not in env:
        _fail("DOMAIN_PROPOSAL_INVALID", pointer, "repair_input")
    return env


def _code_error(exc):
    code = getattr(exc, "code", "DOMAIN_PROPOSAL_INPUT_MISSING")
    details = dict(getattr(exc, "details", {}) or {})
    pointer = details.get("instance_pointer") or "/code_refs"
    if code in {"CODE_PROOF_NOT_READY", "CODE_PROOF_STATE_INVALID", "CODE_PROOF_TARGET_INELIGIBLE"}:
        mapped = "DOMAIN_PROPOSAL_INPUT_MISSING"
        next_action = "supply_code_handoff"
    elif code in {"CODE_PROOF_BINDING_MISMATCH", "CODE_PROOF_CONFLICT"}:
        mapped = "DOMAIN_PROPOSAL_BINDING_MISMATCH"
        next_action = "repair_bindings"
    elif code in {"WORK_PATH_UNSAFE", "INVALID_BATCH_ID", "WORKSPACE_ROOT_INVALID"}:
        mapped = code
        next_action = "repair_input"
    else:
        mapped = "DOMAIN_PROPOSAL_INPUT_MISSING"
        next_action = "repair_input"
    raise DomainProposalError(
        mapped,
        MESSAGES.get(mapped, getattr(exc, "message", mapped)),
        {"instance_pointer": pointer, "next_action": next_action, "prior_code": code, **details},
        exit_code=getattr(exc, "exit_code", 2),
    ) from exc


def _bind_paper_code(proposal, authority, code):
    if code["paper_id"] != proposal["paper_id"]:
        _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", "/paper_id", "repair_bindings", {"field": "paper_id"})
    assoc = code["source_association"]
    expected = proposal["source_association"]
    if assoc != expected:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/source_association",
            "repair_bindings",
            {"field": "source_association"},
        )
    try:
        left = repo_id(proposal["repository"])
        right = repo_id(code["repository"])
    except Exception:
        _fail("DOMAIN_PROPOSAL_INVALID", "/repository", "repair_input")
    if left != right:
        _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", "/repository", "repair_bindings", {"field": "repository"})
    if proposal["commit"] != code["commit"]:
        _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", "/commit", "repair_bindings", {"field": "commit"})
    if authority["association"]["paper_id"] != code["paper_id"]:
        _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", "/paper_id", "repair_bindings", {"field": "paper_id"})


def _taxonomy_pairs():
    raw = read_projection_resource_bytes("taxonomy", "v1.json")
    if raw is None:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", "/concepts", "repair_input", {"resource": "taxonomy/v1.json"})
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", "/concepts", "repair_input", {"resource": "taxonomy/v1.json"})
    pairs = set()
    axes = data.get("axes") if type(data) is dict else None
    if type(axes) is not list:
        return pairs
    for axis in axes:
        if type(axis) is not dict:
            continue
        axis_slug = axis.get("slug")
        terms = axis.get("terms")
        if type(axis_slug) is not str or type(terms) is not list:
            continue
        for term in terms:
            if type(term) is dict and type(term.get("slug")) is str:
                pairs.add((axis_slug, term["slug"]))
    return pairs


def _concepts(rows):
    known = _taxonomy_pairs()
    seen_kinds = set()
    out = []
    for index, row in enumerate(rows):
        pointer = _pointer("concepts", index)
        tax = row["taxonomy_ref"]
        proposal = row["normalization_proposal"]
        if tax is None and proposal is None:
            _fail("DOMAIN_PROPOSAL_INVALID", pointer, "repair_input", {"reason": "term_classification"})
        if tax is not None and proposal is not None:
            _fail("DOMAIN_PROPOSAL_INVALID", pointer, "repair_input", {"reason": "taxonomy_v1_inplace"})
        if tax is not None:
            pair = (tax["axis"], tax["slug"])
            if pair not in known:
                _fail(
                    "DOMAIN_PROPOSAL_INVALID",
                    pointer + "/taxonomy_ref",
                    "repair_input",
                    {"reason": "unknown_taxonomy_term"},
                )
            term_status = "taxonomy_v1"
        else:
            term_status = "normalization_proposal"
        seen_kinds.add(row["concept_kind"])
        out.append(
            {
                "concept_kind": row["concept_kind"],
                "surface_form": row["surface_form"],
                "taxonomy_ref": None if tax is None else {"axis": tax["axis"], "slug": tax["slug"]},
                "normalization_proposal": None if proposal is None else dict(proposal),
                "term_status": term_status,
            }
        )
    return out


def _claims(annotations, authority):
    ledger_claims = authority["ledger"]["claims"]
    heads = authority["heads"]["heads"]
    used = set()
    rows = []
    for index, item in enumerate(annotations):
        pointer = _pointer("claim_annotations", index)
        cid = item["claim_id"]
        if cid in used:
            _fail("DOMAIN_PROPOSAL_INVALID", pointer + "/claim_id", "repair_input", {"reason": "duplicate_claim"})
        used.add(cid)
        row = ledger_claims.get(cid)
        if row is None:
            _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", pointer + "/claim_id", "repair_bindings", {"field": "claim_id"})
        if row["text"] != item["claim_text"]:
            _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", pointer + "/claim_text", "repair_bindings", {"field": "claim_text"})
        try:
            decoded = [decode_evidence(entry) for entry in row["evidence"]]
            fingerprint = evidence_fingerprint_versioned(decoded)
        except ContractError as exc:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/evidence_fingerprint",
                "repair_bindings",
                {"prior_code": exc.code, **exc.details},
            )
        if fingerprint != item["evidence_fingerprint"]:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/evidence_fingerprint",
                "repair_bindings",
                {"field": "evidence_fingerprint"},
            )
        head = heads.get(cid)
        if head is None:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/assessment_head",
                "repair_bindings",
                {"field": "assessment_head"},
            )
        stated = item["assessment_head"]
        if (
            stated["event_id"] != head["event_id"]
            or stated["event_sha256"] != head["event_sha256"]
            or stated["evidence_profile"] != head["evidence_profile"]
        ):
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/assessment_head",
                "repair_bindings",
                {"field": "assessment_head"},
            )
        event_doc, event_raw = authority["events"][stated["event_id"]]
        if sha(event_raw) != stated["event_sha256"]:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/assessment_head/event_sha256",
                "repair_bindings",
                {"field": "assessment_head"},
            )
        if event_doc.get("claim_id") != cid:
            _fail(
                "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                pointer + "/assessment_head/event_id",
                "repair_bindings",
                {"field": "assessment_head"},
            )
        rows.append(
            {
                "claim_id": cid,
                "claim_kind": item["claim_kind"],
                "assessment": row["assessment"],
                "freshness": "head_bound",
                "claim_text": row["text"],
                "evidence_fingerprint": fingerprint,
                "assessment_head": {
                    "event_id": head["event_id"],
                    "event_sha256": head["event_sha256"],
                    "evidence_profile": head["evidence_profile"],
                },
            }
        )
    unannotated = []
    for cid in sorted(ledger_claims):
        if cid in used:
            continue
        row = ledger_claims[cid]
        unannotated.append(
            {
                "claim_id": cid,
                "claim_kind": None,
                "assessment": row["assessment"],
                "freshness": "unannotated",
                "claim_text": row["text"],
            }
        )
    return rows, unannotated


def _relation(relation, proposal, authority, code):
    classes = relation["evidence_classes"]
    _class_shape(classes["A"], True, "/relation/evidence_classes/A")
    _class_shape(classes["C"], True, "/relation/evidence_classes/C")
    if classes["A"]["present"] and not classes["A"]["locators"]:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/A/locators", "repair_input")
    if not classes["A"]["present"] and classes["A"]["locators"]:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/A/locators", "repair_input")
    if classes["B"]["present"]:
        if classes["B"]["project_page"] is None:
            _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/B/project_page", "repair_input")
        _check_project_page(classes["B"]["project_page"], authority)
    elif classes["B"]["project_page"] is not None:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/B/project_page", "repair_input")
    if classes["C"]["present"] and not classes["C"]["locators"]:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/C/locators", "repair_input")
    if not classes["C"]["present"] and classes["C"]["locators"]:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/C/locators", "repair_input")
    for index, locator in enumerate(classes["C"]["locators"]):
        _check_repo_text(locator, proposal, code, _pointer("relation", "evidence_classes", "C", "locators", index))
    if classes["D"]["present"]:
        if classes["D"]["author_control"] is None:
            _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/D/author_control", "repair_input")
    elif classes["D"]["author_control"] is not None:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", "/relation/evidence_classes/D/author_control", "repair_input")
    present = {
        "A": bool(classes["A"]["present"]),
        "B": bool(classes["B"]["present"]),
        "C": bool(classes["C"]["present"]),
        "D": bool(classes["D"]["present"]),
    }
    shortcuts = list(relation["shortcuts_observed"])
    allowed, gaps, reason = _officiality(present, relation, shortcuts)
    stated = relation["officiality_candidate"]
    if stated not in allowed:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/relation/officiality_candidate",
            "repair_bindings",
            {
                "field": "officiality_candidate",
                "stated": stated,
                "allowed": sorted(allowed),
            },
        )
    if relation["kind"] == "third_party_reproduction" and not relation["third_party_statement"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            "/relation/kind",
            "repair_bindings",
            {"field": "relation_kind"},
        )
    return {
        "kind": relation["kind"],
        "officiality_candidate": stated,
        "evidence_classes": present,
        "locators": {
            "A": [dict(item) for item in classes["A"]["locators"]],
            "B": None if classes["B"]["project_page"] is None else dict(classes["B"]["project_page"]),
            "C": [dict(item) for item in classes["C"]["locators"]],
            "D": None if classes["D"]["author_control"] is None else dict(classes["D"]["author_control"]),
        },
        "refused_shortcuts": list(shortcuts),
        "gaps": gaps,
        "reason": reason,
    }


def _class_shape(value, _has_locators, pointer):
    if type(value) is not dict:
        _fail("DOMAIN_PROPOSAL_INVALID", pointer, "repair_input")


def _officiality(present, relation, shortcuts):
    allowed = {"unverified_candidate"}
    gaps = []
    if relation["third_party_statement"]:
        allowed.add("third_party")
    if present["A"]:
        allowed.add("pending_review")
        if not present["C"]:
            gaps.append("C")
            gaps.append("reverse_citation")
    if present["D"] and relation["repository_statement"] and not present["A"]:
        allowed.add("pending_review")
        gaps.append("A")
        gaps.append("paper_backlink")
    if not present["A"] and not present["B"] and "third_party" not in allowed:
        if "A" not in gaps:
            gaps.append("A")
        if "B" not in gaps:
            gaps.append("B")
    if present["C"] and not present["A"] and not present["B"]:
        if "A" not in gaps:
            gaps.append("A")
        if "B" not in gaps:
            gaps.append("B")
    if relation["third_party_statement"]:
        reason = "explicit third-party reproduction statement"
    elif present["A"] and not present["C"]:
        reason = "credible direct publication missing reverse citation"
    elif present["D"] and relation["repository_statement"] and not present["A"]:
        reason = "verified author control with repository statement missing paper backlink"
    elif present["C"] and not present["A"] and not present["B"]:
        reason = "reverse citation alone does not establish officiality"
    elif not present["A"] and not present["B"]:
        reason = "insufficient relationship evidence"
    else:
        reason = "relationship remains proposal-only pending semantic review"
    if shortcuts:
        reason = reason + "; shortcuts do not upgrade officiality"
    return allowed, gaps, reason


def _check_project_page(page, authority):
    pointer = "/relation/evidence_classes/B/project_page"
    if page.get("kind") != "project_page":
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/kind", "repair_input")
    digest = page["local_digest"]
    raw = authority["local_files"].get(digest["path"])
    if raw is None:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", pointer + "/local_digest", "repair_input")
    if sha(raw) != digest["sha256"] or len(raw) != digest["size_bytes"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            pointer + "/local_digest",
            "repair_bindings",
            {"field": "project_page"},
        )
    _check_fragment(page["fragment"], raw, pointer + "/fragment")


def _check_repo_text(locator, proposal, code, pointer):
    if locator.get("kind") != "repository_text":
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/kind", "repair_input")
    if locator["commit"] != proposal["commit"] or locator["commit"] != code["commit"]:
        _fail("DOMAIN_PROPOSAL_BINDING_MISMATCH", pointer + "/commit", "repair_bindings", {"field": "commit"})
    path = locator["path"]
    body = code["bodies"].get(path)
    if body is None:
        _fail("DOMAIN_PROPOSAL_INPUT_MISSING", pointer + "/path", "supply_code_handoff", {"path": path})
    digest = locator["local_digest"]
    if sha(body) != digest["sha256"] or len(body) != digest["size_bytes"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            pointer + "/local_digest",
            "repair_bindings",
            {"field": "repository_text"},
        )
    _check_fragment(locator["fragment"], body, pointer + "/fragment")


def _check_fragment(fragment, raw, pointer):
    start = fragment["start"]
    end = fragment["end"]
    if not 0 <= start < end <= len(raw):
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer, "repair_input", {"reason": "span"})
    excerpt = raw[start:end]
    if sha(excerpt) != fragment["text_sha256"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            pointer + "/text_sha256",
            "repair_bindings",
            {"field": "fragment"},
        )


def _capabilities(rows, proposal, code):
    names = [row["name"] for row in rows]
    if sorted(names) != sorted(CAPABILITY_NAMES) or len(set(names)) != 5:
        _fail("DOMAIN_PROPOSAL_INVALID", "/capabilities", "repair_input", {"reason": "capability_set"})
    out = []
    targets = set(code["targets"])
    repo = code["repository"]
    commit = code["commit"]
    for index, row in enumerate(rows):
        pointer = _pointer("capabilities", index)
        status = row["status"]
        kind = row["declaration_kind"]
        locators = row["locators"]
        absence = row["absence_scope"]
        if "checkpoint_kind" in row and row["name"] != "checkpoints":
            _fail("DOMAIN_PROPOSAL_INVALID", pointer + "/checkpoint_kind", "repair_input")
        if status in {"present", "partial"}:
            if kind not in {"code", "config"}:
                _fail(
                    "DOMAIN_PROPOSAL_LOCATOR_INVALID",
                    pointer + "/declaration_kind",
                    "repair_input",
                    {"reason": "positive_capability_requires_code_or_config"},
                )
            if not locators:
                _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/locators", "repair_input")
            if absence is not None:
                _fail("DOMAIN_PROPOSAL_INVALID", pointer + "/absence_scope", "repair_input")
        elif kind == "readme_only":
            if status != "unverified":
                _fail(
                    "DOMAIN_PROPOSAL_LOCATOR_INVALID",
                    pointer + "/declaration_kind",
                    "repair_input",
                    {"reason": "readme_only_is_declaration"},
                )
        if status == "absent":
            if absence is None:
                _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/absence_scope", "repair_input")
            if absence["commit"] != commit:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    pointer + "/absence_scope/commit",
                    "repair_bindings",
                    {"field": "commit"},
                )
            if locators:
                _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/locators", "repair_input")
        if status == "unverified":
            if absence is not None:
                _fail(
                    "DOMAIN_PROPOSAL_INVALID",
                    pointer + "/absence_scope",
                    "repair_input",
                    {"reason": "unobtained_files_stay_unverified"},
                )
        for loc_index, locator in enumerate(locators):
            loc_pointer = pointer + _pointer("locators", loc_index)
            if locator.get("kind") != "code":
                _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", loc_pointer + "/kind", "repair_input")
            if locator["commit"] != commit:
                _fail(
                    "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                    loc_pointer + "/commit",
                    "repair_bindings",
                    {"field": "commit"},
                )
            try:
                if repo_id(locator["repository"]) != repo_id(repo):
                    _fail(
                        "DOMAIN_PROPOSAL_BINDING_MISMATCH",
                        loc_pointer + "/repository",
                        "repair_bindings",
                        {"field": "repository"},
                    )
            except Exception:
                _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", loc_pointer + "/repository", "repair_input")
            if locator["path"] not in targets:
                _fail(
                    "DOMAIN_PROPOSAL_LOCATOR_INVALID",
                    loc_pointer + "/path",
                    "repair_input",
                    {"reason": "path_not_in_code_batch"},
                )
            body = code["bodies"].get(locator["path"])
            if body is None:
                _fail("DOMAIN_PROPOSAL_INPUT_MISSING", loc_pointer + "/path", "supply_code_handoff")
            _check_code_snippet(locator, body, loc_pointer)
        out.append(
            {
                "name": row["name"],
                "status": status,
                "declaration_kind": kind,
                "locators": [dict(item) for item in locators],
                "absence_scope": None if absence is None else dict(absence),
            }
        )
    out.sort(key=lambda item: CAPABILITY_NAMES.index(item["name"]))
    return out


def _check_code_snippet(locator, body, pointer):
    lines = locator["lines"]
    start = lines["start"]
    end = lines["end"]
    if start > end:
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/lines", "repair_input")
    text = body.decode("utf-8")
    split = text.splitlines()
    if end > len(split):
        _fail("DOMAIN_PROPOSAL_LOCATOR_INVALID", pointer + "/lines", "repair_input", {"reason": "line_range"})
    excerpt = "\n".join(split[start - 1 : end]).encode("utf-8")
    if sha(excerpt) != locator["snippet_sha256"]:
        _fail(
            "DOMAIN_PROPOSAL_BINDING_MISMATCH",
            pointer + "/snippet_sha256",
            "repair_bindings",
            {"field": "snippet"},
        )


def _ignore_self_reported(self_reported, report):
    if self_reported.get("accepted") or self_reported.get("verified") or self_reported.get("official"):
        report["canonical_official"] = False
        report["current_supported_typed_fact"] = False
        report["source_association_verified"] = False
        report["status"] = "proposal_only"
        report["publication"] = "unpublished"
