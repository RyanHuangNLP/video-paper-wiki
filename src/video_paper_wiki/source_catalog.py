"""Agent-safe current-source catalog commands; only build writes .work."""
from __future__ import annotations

import re
from collections import Counter
from functools import wraps

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.secure_io import SecureIOError
from video_paper_wiki.source_catalog_contracts import PROFILE, checksum, choice, fail, integer, invalid, parse_cache, text
from video_paper_wiki.source_catalog_io import catalog_slot, generation
from video_paper_wiki.source_catalog_projection import reconstruct
from video_paper_wiki.source_catalog_query import lookup, query_parameters, search
from video_paper_wiki.source_publication import _vault
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.source_state import collect_source_state
from video_paper_wiki.staging import StagingError, validate_batch_id


def _boundary(function):
    @wraps(function)
    def call(**kwargs):
        try:
            return function(**kwargs)
        except (ContractError, SecureIOError, StagingError) as exc:
            code = "WORK_PATH_UNSAFE" if exc.code == "AUDIT_RACE" else exc.code
            exit_code = getattr(exc, "exit_code", 75 if code == "STAGING_CONFLICT" else 2)
            raise ContractError(code, exc.message, {"instance_pointer": "", **exc.details}, exit_code=exit_code) from exc
        except OSError as exc:
            fail("WORK_PATH_UNSAFE", "catalog filesystem group is unavailable: " + type(exc).__name__)
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            invalid("catalog input is invalid: " + type(exc).__name__)
    return call


def _binding(catalog):
    return {"profile": PROFILE, "catalog_sha256": catalog["catalog_sha256"], "basis": catalog["basis"],
            "counts": {k: len(v) for k, v in catalog["rows"].items()}}


def _perform(*, vault_root, batch_id, action, expected=None, result=None):
    batch = validate_batch_id(batch_id)
    vault_root = checked_path(vault_root)
    with catalog_slot(batch, create=action == "build") as slot:
        with generation() as live_generation:
            with _vault(vault_root, None) as (vault, snapshot, _):
                audit = audit_integrity(vault, _snapshot=snapshot)
                state = collect_source_state(snapshot, audit, require_rendered=True)
                catalog, raw = reconstruct(state, live_generation)
                binding = _binding(catalog)
                if action == "build":
                    status = slot.install(raw)
                    return {**binding, "state": status, "cache_path": str(slot.path / "catalog.json")}
                cache = slot.data
                if cache is not None:
                    parse_cache(cache)
                cache_state = "absent" if cache is None else "current" if cache == raw else "stale"
                if action == "status":
                    coverage_counts = dict(sorted(Counter(r["state"] for r in catalog["rows"]["coverage"]).items()))
                    return {**binding, "state": cache_state, "cache_sha256": None if cache is None else sha(cache),
                        "expected_catalog_sha256": catalog["catalog_sha256"], "coverage_counts": coverage_counts,
                        "uncovered_count": sum(coverage_counts.get(s, 0) for s in
                            ("registered_unclaimed", "captured_unregistered", "derived_unreferenced"))}
                if cache_state != "current":
                    fail("SOURCE_CATALOG_" + cache_state.upper(), "source catalog must be built for this exact current generation")
                if expected is not None and expected != catalog["catalog_sha256"]:
                    fail("SOURCE_CATALOG_STALE", "caller catalog digest differs from current reconstruction", "/catalog_sha256")
                return {**binding, **result(catalog["rows"])}


@_boundary
def build_source_catalog(*, vault_root, batch_id):
    return _perform(vault_root=vault_root, batch_id=batch_id, action="build")


@_boundary
def source_catalog_status(*, vault_root, batch_id):
    return _perform(vault_root=vault_root, batch_id=batch_id, action="status")


@_boundary
def lookup_source_catalog(*, vault_root, batch_id, kind, key, catalog_sha256=None):
    choice(kind, {"paper", "repository", "source", "claim"}, "/kind")
    text(key, "/key")
    expected = checksum(catalog_sha256)
    return _perform(vault_root=vault_root, batch_id=batch_id, action="lookup", expected=expected,
                    result=lambda rows: lookup(rows, kind, key))


@_boundary
def query_source_catalog(*, vault_root, batch_id, text, scope="all", paper_id=None, assessment="all",
                         lifecycle="active", limit=20, offset=0, catalog_sha256=None):
    query = query_parameters(text, scope, paper_id, assessment, lifecycle, limit, offset)
    expected = checksum(catalog_sha256)
    return _perform(vault_root=vault_root, batch_id=batch_id, action="query", expected=expected,
        result=lambda rows: search(rows, query, scope=scope, paper_id=paper_id, assessment=assessment,
                                   lifecycle=lifecycle, limit=limit, offset=offset))


@_boundary
def resolve_source_catalog(*, vault_root, batch_id, claim_id, evidence_ordinal, catalog_sha256=None):
    text(claim_id, "/claim_id")
    if re.fullmatch(r"clm-[0-9a-f]{20}", claim_id) is None:
        invalid("claim ID is not canonical", "/claim_id")
    if type(evidence_ordinal) is not int:
        invalid("evidence ordinal must be an exact integer", "/evidence_ordinal")
    expected = checksum(catalog_sha256)
    def resolve(rows):
        claim = next((c for c in rows["claims"] if c["claim_id"] == claim_id), None)
        evidence = next((e for e in rows["evidence"] if e["claim_id"] == claim_id and e["ordinal"] == evidence_ordinal), None)
        if claim is None or evidence is None:
            fail("SOURCE_CATALOG_NOT_FOUND", "claim or evidence ordinal is not in the current catalog")
        return {"claim_id": claim_id, "evidence_ordinal": evidence_ordinal, "evidence": evidence,
                "assessment": claim["assessment"], "lifecycle": claim["reference"]["lifecycle"]}
    return _perform(vault_root=vault_root, batch_id=batch_id, action="resolve", expected=expected, result=resolve)


def _dispatch_source_catalog_command(args):
    shared = {"vault_root": args.vault_root, "batch_id": args.batch_id}
    command = args.source_catalog_cmd
    if command == "build":
        return build_source_catalog(**shared)
    if command == "status":
        return source_catalog_status(**shared)
    shared["catalog_sha256"] = args.catalog_sha256
    if command == "lookup":
        return lookup_source_catalog(**shared, kind=args.kind, key=args.key)
    if command == "resolve":
        return resolve_source_catalog(**shared, claim_id=args.claim_id, evidence_ordinal=args.evidence_ordinal)
    return query_source_catalog(**shared, text=args.text, scope=args.scope, paper_id=args.paper_id,
        assessment=args.assessment, lifecycle=args.lifecycle, limit=args.limit, offset=args.offset)


def run_source_catalog_command(args):
    command = "source-catalog." + args.source_catalog_cmd
    try:
        result = _dispatch_source_catalog_command(args)
    except ContractError as exc:
        return emit_error(command, exc.code, exc.message, exc.details, exit_code=exc.exit_code)
    return emit_success(command, result)
