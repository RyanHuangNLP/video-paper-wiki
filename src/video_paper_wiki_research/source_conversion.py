"""Convert one retained current lightweight record to a publication proposal."""
from __future__ import annotations

import re
from functools import wraps

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import AUTHORITY, validate
from video_paper_wiki.markdown_source_io import json_bytes
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.source_publication import _prepare_source_publication_retained, _vault
from video_paper_wiki.source_publication_contracts import (
    ASSESSMENT_HEADS, DISPLAY_HEADS, operation_name,
)
from video_paper_wiki.source_semantics_contracts import fail
from video_paper_wiki.source_state import collect_source_state, validate_payload_documents
from video_paper_wiki.staging import validate_batch_id
from video_paper_wiki_research import light_knowledge
from video_paper_wiki_research.formal_source import _observe, _source_paths
from video_paper_wiki_research.light_index import _derived_chunks, _load_paper
from video_paper_wiki_research.source_conversion_io import retained_inputs, safe_path, validator_mirror
from video_paper_wiki_research.source_conversion_model import assemble_conversion, invalid, proposal_time


def _boundary(function):
    @wraps(function)
    def call(**kwargs):
        try:
            return function(**kwargs)
        except ContractError as exc:
            if exc.code == "AUDIT_RACE":
                raise ContractError("WORK_PATH_UNSAFE", exc.message,
                    {"instance_pointer": "", **exc.details}, exit_code=exc.exit_code) from exc
            if "instance_pointer" in exc.details:
                raise
            raise ContractError(exc.code, exc.message, {"instance_pointer": "", **exc.details}, exit_code=exc.exit_code) from exc
        except Exception as exc:
            if hasattr(exc, "code"):
                raise ContractError(exc.code, exc.message, {"instance_pointer": "", **getattr(exc, "details", {})},
                                    exit_code=getattr(exc, "exit_code", 2)) from exc
            if isinstance(exc, (OSError, TypeError, ValueError, UnicodeError, RecursionError)):
                invalid("conversion input is invalid: " + type(exc).__name__)
            raise
    return call


def _current_record(workspace, paper_id, record_id):
    if light_knowledge.current_head_record_id(workspace, paper_id) != record_id:
        fail("SOURCE_CONVERSION_STALE", "selected lightweight record is not the validated current head", "/record_id", exit_code=75)
    bundle = light_knowledge._owned_record_bundle(workspace, record_id=record_id, paper_id=paper_id)
    if bundle is None:
        invalid("selected lightweight record or its completed ancestry is invalid", "/record_id")
    record_path = workspace / ".light-knowledge/records" / record_id
    if light_knowledge._record_source_status(workspace, record_path) != "current":
        fail("SOURCE_CONVERSION_STALE", "lightweight record source or citation chunks are stale", "/record_id", exit_code=75)
    paper = _load_paper(workspace / "papers" / paper_id.split(":", 1)[1])
    chunks = {chunk["chunk_id"]: chunk for chunk in _derived_chunks([paper])}
    if light_knowledge.current_head_record_id(workspace, paper_id) != record_id:
        fail("SOURCE_CONVERSION_STALE", "lightweight head changed during validation", "/record_id", exit_code=75)
    return bundle["document"], chunks


@_boundary
def convert_source_knowledge(*, workspace_root, paper_id, record_id, capture_authority,
                             batch_id, operation_id, vault_root, proposed_at, metadata=None):
    batch, operation = validate_batch_id(batch_id), operation_name(operation_id)
    proposed_at = proposal_time(proposed_at)
    if type(record_id) is not str or re.fullmatch(r"[0-9a-f]{64}", record_id) is None:
        invalid("record_id must be a canonical lightweight record hash", "/record_id")
    workspace, markdown_path, source_path = _source_paths(safe_path(workspace_root), paper_id)
    with retained_inputs(workspace=workspace, markdown_path=markdown_path, source_path=source_path,
                         authority_path=capture_authority, metadata_path=metadata) as (files, tree):
        authority = validate(json_bytes(files[2].data, code="MARKDOWN_AUTHORITY_MISMATCH"), AUTHORITY)
        captured_observation = authority["request"]["plan"]["observation"]
        observation = _observe(files[0].data, files[1].data, light_paper_id=paper_id,
            paper_id=captured_observation["paper_id"], version_label=captured_observation["version"]["label"])
        if observation != captured_observation:
            fail("SOURCE_CONVERSION_STALE", "lightweight source differs from the capture observation", "/capture_authority", exit_code=75)
        metadata_value = None if metadata is None else json_bytes(files[3].data, code="SOURCE_CONVERSION_INVALID")
        with validator_mirror(batch=batch, light_paper_id=paper_id, tree=tree,
                              markdown=files[0].data, metadata=files[1].data) as mirror:
            document, chunks = _current_record(mirror, paper_id, record_id)
            with _vault(safe_path(vault_root), None) as (vault, snapshot, _captured):
                audit = audit_integrity(vault, _snapshot=snapshot)
                current = collect_source_state(snapshot, audit, allow_legacy_structural=True)
                if current["bytes"].get(authority["stored_path"]) != files[0].data:
                    fail("SOURCE_REGISTRATION_INVALID", "retained registered raw capture differs from the current source", "/capture_authority")
                payloads, summary = assemble_conversion(current=current, observation=observation,
                    raw=files[0].data, document=document, chunks=chunks, record_id=record_id,
                    metadata=metadata_value, proposed_at=proposed_at)
                prospective = collect_source_state(snapshot, audit, overlay=payloads, require_rendered=False)
                stored_pages = {p for p in current["bytes"]
                                if p.startswith(("wiki/papers/", "wiki/code/", "wiki/concepts/"))}
                if stored_pages - prospective["pages"].keys():
                    fail("SOURCE_PUBLICATION_UNSUPPORTED_CHANGE", "page retirement requires a separate deletion path",
                         "/compiled_pages", exit_code=75)
                payloads.update(prospective["pages"])
                payloads[ASSESSMENT_HEADS] = canonicalize(prospective["assessment_heads"])
                payloads[DISPLAY_HEADS] = canonicalize(prospective["display_heads"])
                result = _prepare_source_publication_retained(batch=batch, operation=operation,
                    snapshot=snapshot, audit=audit, current=current,
                    payloads=validate_payload_documents(payloads))
                return {**result, "conversion": summary}
