#!/usr/bin/env python3
"""Build minimal synthetic CODE public-wire examples.

This generator imports only the accepted pure JCS, text-metadata, and Git
object verifier APIs from an explicitly selected CODE worktree.  It never
parses configuration documents or invokes a public command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ZERO_SHA256 = "0" * 64
PROFILE_PLACEHOLDER = ZERO_SHA256
PAPER_ID = "arxiv:2401.01234"
REPOSITORY = "synthetic-owner/synthetic-repo"
OBSERVED_AT = "2026-09-10T00:00:00Z"
TARGET_PATH = "config.json"
TARGET_ROLES = ["configuration"]
METADATA_HELPER_CHECKS: list[dict[str, str]] = []


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonicalize(value: Any) -> bytes:
    from video_paper_wiki.jcs import canonicalize as jcs_canonicalize

    return jcs_canonicalize(value)


def write_json(path: Path, value: Any) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
    raw = canonicalize(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": path.as_posix(), "size_bytes": len(raw), "sha256": sha256(raw)}


def envelope(kind: str, data: dict[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    schema = f"video-paper-wiki.{kind}.v1"
    core = {"schema": schema, "kind": kind, "data": data}
    document = {
        "schema": schema,
        "kind": kind,
        "id": f"ce1:{kind}:{sha256(canonicalize(core))}",
        "data": data,
    }
    saved = canonicalize(document) + b"\n"
    return document, saved, {"id": document["id"], "sha256": sha256(saved)}


def ref(document: dict[str, Any], saved: bytes) -> dict[str, str]:
    return {"id": document["id"], "sha256": sha256(saved)}


def request_data(
    object_format: str,
    commit_oid: str,
    target: dict[str, Any],
    *,
    include_profile: bool = True,
) -> dict[str, Any]:
    result = {
        "paper_id": PAPER_ID,
        "source_association": None,
        "repository": REPOSITORY,
        "object_format": object_format,
        "commit_oid": commit_oid,
        "targets": [target],
        "require_repository_assertion": False,
        "limits": {
            "git": {
                "max_targets": 32,
                "max_objects": 2048,
                "max_tree_entries": 32768,
                "max_object_bytes": 8388608,
                "max_total_object_bytes": 33554432,
            },
            "config": {
                "max_source_bytes": 262144,
                "max_depth": 32,
                "max_nodes": 1024,
                "max_array_items": 256,
                "max_object_keys": 1024,
                "max_key_bytes": 256,
                "max_string_codepoints": 16384,
                "max_scalars": 512,
                "max_numeric_lexeme_bytes": 128,
                "max_numeric_coefficient_digits": 64,
                "max_numeric_abs_exponent": 128,
                "max_numeric_canonical_bytes": 256,
                "max_declarations": 4096,
            },
            "public": {
                "max_bundle_bytes": 1048576,
                "max_inline_normalized_bytes": 16384,
                "max_request_bytes": 65536,
                "max_intent_bytes": 1048576,
                "max_observation_bytes": 2097152,
                "max_config_document_bytes": 2097152,
                "max_handoff_bytes": 131072,
                "max_output_peak_bytes": 134217728,
            },
        },
    }
    if include_profile:
        result["profile_sha256"] = PROFILE_PLACEHOLDER
    return result


def observe_raw(object_format: str = "sha1", commit_oid: str = "a15a4626d79604772896e10ef0dd7c6318548fce") -> dict[str, Any]:
    return {
        "mode": "git_objects",
        "observed_at": OBSERVED_AT,
        "executor": {"kind": "host_tool", "id": "synthetic-fixture-host"},
        "hosting_assertion": {
            "provider": "github",
            "actor": {"kind": "host_tool", "id": "synthetic-fixture-host"},
            "repository": REPOSITORY,
            "object_format": object_format,
            "commit_oid": commit_oid,
            "locator": f"https://github.com/{REPOSITORY}/commit/{commit_oid}",
            "statement": "Synthetic fixture assertion; no remote lookup was performed.",
        },
    }


def observe_normalized(commit_oid: str) -> dict[str, Any]:
    text = '{\n  "learning_rate": 1e-4,\n  "betas": [0.9, 0.999]\n}\n'
    return {
        "mode": "normalized_text",
        "observed_at": OBSERVED_AT,
        "executor": {"kind": "host_tool", "id": "synthetic-fixture-host"},
        "hosting_assertion": None,
        "targets": [
            {
                "path": TARGET_PATH,
                "status": "present",
                "locator": f"https://raw.githubusercontent.com/{REPOSITORY}/{commit_oid}/{TARGET_PATH}",
                "text": text,
            }
        ],
    }


def metadata(payload: bytes) -> dict[str, Any]:
    # Keep the same local byte calculation used by the accepted helper, then
    # compare every returned field against the actual helper in the project
    # environment.  This prevents an unverified mirror from becoming evidence.
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("fixture text unexpectedly has a BOM")
    text = payload.decode("utf-8", errors="strict")
    if any(ord(char) in set(range(0, 9)) | {11, 12} | set(range(14, 32)) | set(range(127, 160)) | {0x2028, 0x2029} for char in text):
        raise ValueError("fixture text contains a forbidden control")
    normalized = text.replace("\r\n", "\n").encode("utf-8")
    if b"\r" in normalized:
        raise ValueError("fixture text contains bare CR")
    crlf = payload.count(b"\r\n")
    lf = payload.count(b"\n") - crlf
    style = "mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "none"
    line_count = 0 if not normalized else normalized.count(b"\n") + (not normalized.endswith(b"\n"))
    result = {
        "normalized_size_bytes": len(normalized),
        "normalized_sha256": sha256(normalized),
        "newline_style": style,
        "ends_with_newline": normalized.endswith(b"\n"),
        "line_count": line_count,
    }
    from video_paper_wiki.code_evidence_contracts import code_text_metadata

    legacy = code_text_metadata(payload)
    fields = ("normalized_sha256", "newline_style", "ends_with_newline", "line_count")
    if {key: result[key] for key in fields} != {key: legacy[key] for key in fields}:
        raise RuntimeError("local metadata differs from code_text_metadata")
    METADATA_HELPER_CHECKS.append({"payload_sha256": sha256(payload), "status": "passed"})
    return result


def load_git_case(source_root: Path, object_format: str) -> tuple[dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    from video_paper_wiki.code_git_objects import CODE_GIT_PROFILE_LIMITS, verify_code_git_objects

    fixture_path = source_root / "tests/fixtures/code-git-objects-v1.json"
    fixture = json.loads(fixture_path.read_bytes())
    fmt = fixture["formats"][object_format]
    blob_oid = fmt["path_facts"][TARGET_PATH]["blob_oid"]
    wanted = {fmt["commit_oid"], fmt["root_tree_oid"], blob_oid}
    records: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    for item in fmt["all_objects"]:
        if item["oid"] not in wanted:
            continue
        records.append(
            {
                "oid": item["oid"],
                "object_type": item["type"],
                "body_size_bytes": item["size"],
                "body_sha256": item["body_sha256"],
                "framed_sha256": item["framed_sha256"],
            }
        )
        bodies[item["oid"]] = bytes.fromhex(item["body_hex"])
    records.sort(key=lambda item: item["oid"])
    proof = verify_code_git_objects(
        object_format=object_format,
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=[{"path": TARGET_PATH, "allow_executable_source": False}],
        limits=dict(CODE_GIT_PROFILE_LIMITS),
    )
    return fmt, proof, bodies[blob_oid], {"records": records, "bodies": bodies, "blob_oid": blob_oid}


def build_case(source_root: Path, out_root: Path, object_format: str) -> dict[str, Any]:
    fmt, proof, raw_config, subset = load_git_case(source_root, object_format)
    target = {"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}
    batch_id = f"resource-fixtures-{object_format}"
    logical_root = f".work/{batch_id}/code-evidence-v1"
    input_directory = f".work/{batch_id}/raw-input"
    req_doc, req_saved, req_ref = envelope(
        "code-proof-request", request_data(object_format, fmt["commit_oid"], target)
    )
    bundle_data = {
        "request": req_ref,
        "object_format": object_format,
        "repository": REPOSITORY,
        "commit_oid": fmt["commit_oid"],
        "root_tree_oid": fmt["root_tree_oid"],
        "objects": subset["records"],
    }
    bundle_doc, bundle_saved, bundle_ref = envelope("code-git-bundle", bundle_data)
    acquisition = observe_raw(object_format, fmt["commit_oid"])
    intent_doc, intent_saved, intent_ref = envelope(
        "code-acquisition-intent",
        {"request": req_ref, "mode": "git_objects", "acquisition": acquisition, "bundle": {"directory": input_directory, "reference": bundle_ref}},
    )
    proof_target = proof["targets"][0]
    text_meta = metadata(raw_config)
    observed_target = {"path": TARGET_PATH, "status": "source_text", "reason": None, "text": text_meta}
    observation_data = {
        "request": req_ref,
        "intent": intent_ref,
        "bundle": bundle_ref,
        "mode": "git_objects",
        "git_proof": proof,
        "targets": [observed_target],
        "capabilities": {"git_objects_verified": True, "raw_bytes_retained": True, "repository_assertion": "host_asserted", "source_association_verified": False},
        "eligibility": {"complete_target_set": True, "repository_requirement_met": True, "source_handoff_eligible": True},
    }
    obs_doc, obs_saved, obs_ref = envelope("code-proof-observation", observation_data)
    raw_ref = {"path": f"{logical_root}/objects/{subset['blob_oid']}.body", "size_bytes": len(raw_config), "sha256": sha256(raw_config)}
    config_data = {"request": req_ref, "observation": obs_ref, "bundle": bundle_ref, "path": TARGET_PATH, "object_format": object_format, "blob_oid": subset["blob_oid"], "raw_body": raw_ref, "format": "source-only", "result": None, "source_only_reason": "explicit_source_only"}
    config_doc, config_saved, config_ref = envelope("code-config-evidence", config_data)
    handoff_data = {
        "successor_only": True,
        "request": req_ref,
        "observation": obs_ref,
        "bundle": bundle_ref,
        "paper_id": PAPER_ID,
        "source_association": None,
        "repository": REPOSITORY,
        "object_format": object_format,
        "commit_oid": fmt["commit_oid"],
        "root_tree_oid": fmt["root_tree_oid"],
        "path": TARGET_PATH,
        "roles": TARGET_ROLES,
        "allow_executable_source": False,
        "blob": proof_target["blob"],
        "raw_body": raw_ref,
        "text": text_meta,
        "proof": proof_target,
        "repository_assertion": "host_asserted",
        "source_association_verified": False,
    }
    handoff_doc, handoff_saved, handoff_ref = envelope("code-source-handoff", handoff_data)
    path_key = sha256(TARGET_PATH.encode("ascii"))
    status = {
        "batch_id": batch_id,
        "state": "observed",
        "request": req_ref,
        "intent": intent_ref,
        "bundle": bundle_ref,
        "observation": obs_ref,
        "mode": "git_objects",
        "missing": [],
        "targets": [observed_target],
        "capabilities": observation_data["capabilities"],
        "eligibility": observation_data["eligibility"],
        "configs": [{"path": TARGET_PATH, "reference": config_ref, "stored_path": f"{logical_root}/configs/{path_key}.json"}],
        "handoffs": [{"path": TARGET_PATH, "reference": handoff_ref, "stored_path": f"{logical_root}/handoffs/{path_key}.json"}],
        "next_action": "successor_capture",
    }
    success = {
        "request": {"batch_id": status["batch_id"], "request": req_ref, "already_staged": False, "acquisition_targets": [{"path": TARGET_PATH, "github_url": f"https://github.com/{REPOSITORY}/blob/{fmt['commit_oid']}/{TARGET_PATH}", "raw_url": f"https://raw.githubusercontent.com/{REPOSITORY}/{fmt['commit_oid']}/{TARGET_PATH}"}]},
        "observe": {"batch_id": status["batch_id"], "observation": obs_ref, "status": status},
        "status": status,
        "config": {"batch_id": status["batch_id"], "path": TARGET_PATH, "config": config_ref, "stored_path": f"{logical_root}/configs/{path_key}.json", "already_staged": False},
        "handoff": {"batch_id": status["batch_id"], "handoffs": [{"path": TARGET_PATH, "handoff": handoff_ref, "stored_path": f"{logical_root}/handoffs/{path_key}.json", "source_body_path": raw_ref["path"], "already_staged": False}]},
    }
    files: list[dict[str, Any]] = []
    for name, saved in (("request.json", req_saved), ("bundle.json", bundle_saved), ("intent.json", intent_saved), ("observation.json", obs_saved), ("config.json", config_saved), ("handoff.json", handoff_saved)):
        path = out_root / "saved" / f"{object_format}-raw" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
        path.write_bytes(saved)
        files.append({"path": path.relative_to(out_root).as_posix(), "size_bytes": len(saved), "sha256": sha256(saved), "kind": name[:-5]})
    # Keep the exact retained three-object body set beside each complete raw
    # case so an independent audit can replay the accepted Git kernel.
    for record in subset["records"]:
        oid = record["oid"]
        path = out_root / "saved" / f"{object_format}-raw" / "objects" / f"{oid}.body"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
        payload = subset["bodies"][oid]
        path.write_bytes(payload)
        files.append({"path": path.relative_to(out_root).as_posix(), "size_bytes": len(payload), "sha256": sha256(payload), "kind": "raw-body"})
    for name, value in success.items():
        path = out_root / "success-data" / f"{object_format}-{name}.json"
        written = write_json(path, value)
        written["path"] = path.relative_to(out_root).as_posix()
        files.append({**written, "kind": f"success:{name}"})
    return {"object_format": object_format, "commit_oid": fmt["commit_oid"], "root_tree_oid": fmt["root_tree_oid"], "blob_oid": subset["blob_oid"], "raw_body_sha256": sha256(raw_config), "verified": True, "objects_declared": len(subset["records"]), "saved_and_success_files": files, "profile_sha256": PROFILE_PLACEHOLDER}


def build_normalized(source_root: Path, out_root: Path) -> dict[str, Any]:
    fmt = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"]["sha1"]
    target = {"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}
    req_doc, req_saved, req_ref = envelope("code-proof-request", request_data("sha1", fmt["commit_oid"], target))
    acquisition = observe_normalized(fmt["commit_oid"])
    intent_doc, intent_saved, intent_ref = envelope("code-acquisition-intent", {"request": req_ref, "mode": "normalized_text", "acquisition": acquisition, "bundle": None})
    text = acquisition["targets"][0]["text"].encode()
    meta = metadata(text)
    obs_data = {"request": req_ref, "intent": intent_ref, "bundle": None, "mode": "normalized_text", "git_proof": None, "targets": [{"path": TARGET_PATH, "status": "normalized_text", "reason": None, "text": meta}], "capabilities": {"git_objects_verified": False, "raw_bytes_retained": False, "repository_assertion": "unverified", "source_association_verified": False}, "eligibility": {"complete_target_set": False, "repository_requirement_met": True, "source_handoff_eligible": False}}
    obs_doc, obs_saved, obs_ref = envelope("code-proof-observation", obs_data)
    files=[]
    for name, saved in (("request.json", req_saved), ("intent.json", intent_saved), ("observation.json", obs_saved)):
        path=out_root/"saved"/"normalized"/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
        path.write_bytes(saved)
        files.append({"path":path.relative_to(out_root).as_posix(),"size_bytes":len(saved),"sha256":sha256(saved),"kind":name[:-5]})
    return {"mode":"normalized_text","object_format":"sha1","commit_oid":fmt["commit_oid"],"saved_files":files,"raw_bytes_retained":False,"verified":False,"note":"Normalized text capability sample only; no Git proof, config result, or handoff is claimed."}


def _request_for_targets(object_format: str, commit_oid: str, targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the R7 request shape without changing the accepted limits."""
    value = request_data(object_format, commit_oid, targets[0])
    value["targets"] = targets
    return value


def _unobserved_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"path": target["path"], "status": "unobserved", "reason": None, "text": None} for target in targets]


def _status(
    batch_id: str,
    state: str,
    *,
    request: dict[str, str] | None,
    intent: dict[str, str] | None,
    bundle: dict[str, str] | None,
    observation: dict[str, str] | None,
    mode: str | None,
    missing: list[str],
    targets: list[dict[str, Any]],
    capabilities: dict[str, Any] | None,
    eligibility: dict[str, Any] | None,
    configs: list[dict[str, Any]] | None = None,
    handoffs: list[dict[str, Any]] | None = None,
    next_action: str,
) -> dict[str, Any]:
    """Build the exact closed public status payload from R7."""
    return {
        "batch_id": batch_id,
        "state": state,
        "request": request,
        "intent": intent,
        "bundle": bundle,
        "observation": observation,
        "mode": mode,
        "missing": missing,
        "targets": targets,
        "capabilities": capabilities,
        "eligibility": eligibility,
        "configs": [] if configs is None else configs,
        "handoffs": [] if handoffs is None else handoffs,
        "next_action": next_action,
    }


def _save_bytes(out_root: Path, rel: str, payload: bytes, *, kind: str) -> dict[str, Any]:
    path = out_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
    path.write_bytes(payload)
    return {"path": rel, "size_bytes": len(payload), "sha256": sha256(payload), "kind": kind}


def _save_doc(out_root: Path, case_name: str, name: str, saved: bytes, *, kind: str) -> dict[str, Any]:
    return _save_bytes(out_root, f"saved/{case_name}/{name}", saved, kind=kind)


def _save_payload(out_root: Path, case_name: str, name: str, value: Any, *, kind: str) -> dict[str, Any]:
    path = out_root / "success-data" / f"{case_name}-{name}.json"
    written = write_json(path, value)
    written.update({"path": path.relative_to(out_root).as_posix(), "kind": kind})
    return written


def _save_status_case(out_root: Path, case_name: str, status: dict[str, Any], *, files: list[dict[str, Any]], extras: dict[str, Any] | None = None) -> dict[str, Any]:
    files.append(_save_payload(out_root, case_name, "status", status, kind="success:status"))
    result = {"case": case_name, "status": status, "files": files}
    if extras:
        result.update(extras)
    return result


def _request_success(batch_id: str, request_ref: dict[str, str], targets: list[dict[str, Any]], commit_oid: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "request": request_ref,
        "already_staged": False,
        "acquisition_targets": [
            {
                "path": target["path"],
                "github_url": f"https://github.com/{REPOSITORY}/blob/{commit_oid}/{target['path']}",
                "raw_url": f"https://raw.githubusercontent.com/{REPOSITORY}/{commit_oid}/{target['path']}",
            }
            for target in targets
        ],
    }


def _load_raw_targets(source_root: Path, object_format: str, targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a retained three-object subset for any requested target list."""
    from video_paper_wiki.code_git_objects import CODE_GIT_PROFILE_LIMITS, verify_code_git_objects

    fixture = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())
    fmt = fixture["formats"][object_format]
    blob_oid = fmt["path_facts"][TARGET_PATH]["blob_oid"]
    wanted = {fmt["commit_oid"], fmt["root_tree_oid"], blob_oid}
    records: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    for item in fmt["all_objects"]:
        if item["oid"] not in wanted:
            continue
        records.append({"oid": item["oid"], "object_type": item["type"], "body_size_bytes": item["size"], "body_sha256": item["body_sha256"], "framed_sha256": item["framed_sha256"]})
        bodies[item["oid"]] = bytes.fromhex(item["body_hex"])
    records.sort(key=lambda item: item["oid"])
    proof = verify_code_git_objects(
        object_format=object_format,
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=[{"path": target["path"], "allow_executable_source": target["allow_executable_source"]} for target in targets],
        limits=dict(CODE_GIT_PROFILE_LIMITS),
    )
    return {"format": fmt, "proof": proof, "records": records, "bodies": bodies, "blob_oid": blob_oid}


def _raw_material(source_root: Path, object_format: str, batch_id: str, targets: list[dict[str, Any]]) -> dict[str, Any]:
    material = _load_raw_targets(source_root, object_format, targets)
    fmt = material["format"]
    request_targets = [{"path": target["path"], "roles": sorted(target["roles"]), "allow_executable_source": target["allow_executable_source"]} for target in targets]
    req_doc, req_saved, req_ref = envelope("code-proof-request", _request_for_targets(object_format, fmt["commit_oid"], request_targets))
    bundle_data = {"request": req_ref, "object_format": object_format, "repository": REPOSITORY, "commit_oid": fmt["commit_oid"], "root_tree_oid": fmt["root_tree_oid"], "objects": material["records"]}
    bundle_doc, bundle_saved, bundle_ref = envelope("code-git-bundle", bundle_data)
    input_directory = f".work/{batch_id}/raw-input"
    intent_data = {"request": req_ref, "mode": "git_objects", "acquisition": observe_raw(object_format, fmt["commit_oid"]), "bundle": {"directory": input_directory, "reference": bundle_ref}}
    intent_doc, intent_saved, intent_ref = envelope("code-acquisition-intent", intent_data)
    logical_root = f".work/{batch_id}/code-evidence-v1"
    proof_by_path = {item["path"]: item for item in material["proof"]["targets"]}
    raw_config = material["bodies"][material["blob_oid"]]
    metadata_by_path = {TARGET_PATH: metadata(raw_config)}
    observed_targets: list[dict[str, Any]] = []
    for target in request_targets:
        proved = proof_by_path[target["path"]]
        if proved["outcome"] == "permitted_regular_blob":
            observed_targets.append({"path": target["path"], "status": "source_text", "reason": None, "text": metadata_by_path[target["path"]]})
        else:
            # R7 requires raw rows to copy the accepted Git-kernel reason.
            observed_targets.append({"path": target["path"], "status": proved["outcome"], "reason": proved["reason"], "text": None})
    complete = all(target["status"] == "source_text" for target in observed_targets)
    capabilities = {"git_objects_verified": True, "raw_bytes_retained": True, "repository_assertion": "host_asserted", "source_association_verified": False}
    eligibility = {"complete_target_set": complete, "repository_requirement_met": True, "source_handoff_eligible": complete}
    obs_data = {"request": req_ref, "intent": intent_ref, "bundle": bundle_ref, "mode": "git_objects", "git_proof": material["proof"], "targets": observed_targets, "capabilities": capabilities, "eligibility": eligibility}
    obs_doc, obs_saved, obs_ref = envelope("code-proof-observation", obs_data)
    config_target = next(target for target in request_targets if target["path"] == TARGET_PATH)
    config_proof = proof_by_path[TARGET_PATH]
    raw_ref = {"path": f"{logical_root}/objects/{material['blob_oid']}.body", "size_bytes": len(raw_config), "sha256": sha256(raw_config)}
    config_data = {"request": req_ref, "observation": obs_ref, "bundle": bundle_ref, "path": TARGET_PATH, "object_format": object_format, "blob_oid": material["blob_oid"], "raw_body": raw_ref, "format": "source-only", "result": None, "source_only_reason": "explicit_source_only"}
    config_doc, config_saved, config_ref = envelope("code-config-evidence", config_data)
    handoff_ref = None
    handoff_saved = None
    if complete:
        proof_target = config_proof
        handoff_data = {"successor_only": True, "request": req_ref, "observation": obs_ref, "bundle": bundle_ref, "paper_id": PAPER_ID, "source_association": None, "repository": REPOSITORY, "object_format": object_format, "commit_oid": fmt["commit_oid"], "root_tree_oid": fmt["root_tree_oid"], "path": TARGET_PATH, "roles": config_target["roles"], "allow_executable_source": False, "blob": proof_target["blob"], "raw_body": raw_ref, "text": metadata_by_path[TARGET_PATH], "proof": proof_target, "repository_assertion": "host_asserted", "source_association_verified": False}
        handoff_doc, handoff_saved, handoff_ref = envelope("code-source-handoff", handoff_data)
    path_key = sha256(TARGET_PATH.encode("ascii"))
    configs = [{"path": TARGET_PATH, "reference": config_ref, "stored_path": f"{logical_root}/configs/{path_key}.json"}]
    handoffs = [{"path": TARGET_PATH, "reference": handoff_ref, "stored_path": f"{logical_root}/handoffs/{path_key}.json"}] if handoff_ref else []
    status = _status(batch_id, "observed", request=req_ref, intent=intent_ref, bundle=bundle_ref, observation=obs_ref, mode="git_objects", missing=[], targets=observed_targets, capabilities=capabilities, eligibility=eligibility, configs=configs, handoffs=handoffs, next_action="successor_capture" if complete else "new_request_or_acquisition_required")
    return {"batch_id": batch_id, "targets": request_targets, "format": fmt, "material": material, "req_ref": req_ref, "req_saved": req_saved, "intent_ref": intent_ref, "intent_saved": intent_saved, "bundle_ref": bundle_ref, "bundle_saved": bundle_saved, "obs_ref": obs_ref, "obs_saved": obs_saved, "config_ref": config_ref, "config_saved": config_saved, "handoff_ref": handoff_ref, "handoff_saved": handoff_saved, "raw_ref": raw_ref, "status": status, "logical_root": logical_root, "metadata": metadata_by_path[TARGET_PATH]}


def _write_raw_complete(source_root: Path, out_root: Path, case_name: str, object_format: str, targets: list[dict[str, Any]]) -> dict[str, Any]:
    material = _raw_material(source_root, object_format, case_name, targets)
    files: list[dict[str, Any]] = []
    for name, saved, kind in (("request.json", material["req_saved"], "request"), ("intent.json", material["intent_saved"], "intent"), ("bundle.json", material["bundle_saved"], "bundle"), ("observation.json", material["obs_saved"], "observation"), ("config.json", material["config_saved"], "config")):
        files.append(_save_doc(out_root, case_name, name, saved, kind=kind))
    if material["handoff_saved"] is not None:
        files.append(_save_doc(out_root, case_name, "handoff.json", material["handoff_saved"], kind="handoff"))
    for record in material["material"]["records"]:
        oid = record["oid"]
        files.append(_save_bytes(out_root, f"saved/{case_name}/objects/{oid}.body", material["material"]["bodies"][oid], kind="raw-body"))
    files.append(_save_payload(out_root, case_name, "request", _request_success(material["batch_id"], material["req_ref"], material["targets"], material["format"]["commit_oid"]), kind="success:request"))
    files.append(_save_payload(out_root, case_name, "observe", {"batch_id": material["batch_id"], "observation": material["obs_ref"], "status": material["status"]}, kind="success:observe"))
    files.append(_save_payload(out_root, case_name, "config", {"batch_id": material["batch_id"], "path": TARGET_PATH, "config": material["config_ref"], "stored_path": f"{material['logical_root']}/configs/{sha256(TARGET_PATH.encode('ascii'))}.json", "already_staged": False}, kind="success:config"))
    if material["handoff_ref"]:
        files.append(_save_payload(out_root, case_name, "handoff", {"batch_id": material["batch_id"], "handoffs": [{"path": TARGET_PATH, "handoff": material["handoff_ref"], "stored_path": f"{material['logical_root']}/handoffs/{sha256(TARGET_PATH.encode('ascii'))}.json", "source_body_path": material["raw_ref"]["path"], "already_staged": False}]}, kind="success:handoff"))
    return _save_status_case(out_root, case_name, material["status"], files=files, extras={"object_format": object_format, "objects_declared": len(material["material"]["records"]), "complete_target_set": material["status"]["eligibility"]["complete_target_set"]})


def _write_raw_pending(source_root: Path, out_root: Path, case_name: str, object_format: str, body_count: int | None, include_bundle: bool) -> dict[str, Any]:
    targets = [{"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}]
    material = _raw_material(source_root, object_format, case_name, targets)
    files: list[dict[str, Any]] = [_save_doc(out_root, case_name, "request.json", material["req_saved"], kind="request"), _save_doc(out_root, case_name, "intent.json", material["intent_saved"], kind="intent")]
    if include_bundle:
        files.append(_save_doc(out_root, case_name, "bundle.json", material["bundle_saved"], kind="bundle"))
    records = material["material"]["records"]
    if body_count is not None:
        for record in records[:body_count]:
            oid = record["oid"]
            files.append(_save_bytes(out_root, f"saved/{case_name}/objects/{oid}.body", material["material"]["bodies"][oid], kind="raw-body"))
    if not include_bundle:
        state = "pending_raw_bundle"
        missing = ["bundle.json", "observation.json"]
    else:
        state = "pending_raw_bodies"
        missing = [f"objects/{record['oid']}.body" for record in records[(body_count or 0):]] + ["observation.json"]
        if body_count == len(records):
            missing = ["observation.json"]
    status = _status(material["batch_id"], state, request=material["req_ref"], intent=material["intent_ref"], bundle=material["bundle_ref"] if include_bundle else None, observation=None, mode="git_objects", missing=missing, targets=_unobserved_targets(targets), capabilities=None, eligibility=None, next_action="resume_same_observation")
    files.append(_save_payload(out_root, case_name, "request", _request_success(material["batch_id"], material["req_ref"], targets, material["format"]["commit_oid"]), kind="success:request"))
    return _save_status_case(out_root, case_name, status, files=files, extras={"object_format": object_format, "objects_declared": len(records), "present_body_count": 0 if body_count is None else body_count})


def _write_requested(source_root: Path, out_root: Path, case_name: str) -> dict[str, Any]:
    fmt = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"]["sha1"]
    targets = [{"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}]
    req_doc, req_saved, req_ref = envelope("code-proof-request", _request_for_targets("sha1", fmt["commit_oid"], targets))
    files = [_save_doc(out_root, case_name, "request.json", req_saved, kind="request")]
    status = _status(case_name, "requested", request=req_ref, intent=None, bundle=None, observation=None, mode=None, missing=["intent.json"], targets=_unobserved_targets(targets), capabilities=None, eligibility=None, next_action="supply_observation")
    files.append(_save_payload(out_root, case_name, "request", _request_success(case_name, req_ref, targets, fmt["commit_oid"]), kind="success:request"))
    return _save_status_case(out_root, case_name, status, files=files)


def _write_empty(out_root: Path, case_name: str) -> dict[str, Any]:
    status = _status(case_name, "empty", request=None, intent=None, bundle=None, observation=None, mode=None, missing=[], targets=[], capabilities=None, eligibility=None, next_action="prepare_request")
    return _save_status_case(out_root, case_name, status, files=[])


def _write_pending_normalized(source_root: Path, out_root: Path, case_name: str) -> dict[str, Any]:
    fmt = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"]["sha1"]
    targets = [{"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}]
    req_doc, req_saved, req_ref = envelope("code-proof-request", _request_for_targets("sha1", fmt["commit_oid"], targets))
    acquisition = observe_normalized(fmt["commit_oid"])
    intent_doc, intent_saved, intent_ref = envelope("code-acquisition-intent", {"request": req_ref, "mode": "normalized_text", "acquisition": acquisition, "bundle": None})
    files = [_save_doc(out_root, case_name, "request.json", req_saved, kind="request"), _save_doc(out_root, case_name, "intent.json", intent_saved, kind="intent")]
    status = _status(case_name, "pending_normalized", request=req_ref, intent=intent_ref, bundle=None, observation=None, mode="normalized_text", missing=["observation.json"], targets=_unobserved_targets(targets), capabilities=None, eligibility=None, next_action="resume_same_observation")
    return _save_status_case(out_root, case_name, status, files=files)


def _normalized_other_input(commit_oid: str, status: str, reason: str) -> dict[str, Any]:
    return {"mode": "normalized_text", "observed_at": OBSERVED_AT, "executor": {"kind": "host_tool", "id": "synthetic-fixture-host"}, "hosting_assertion": None, "targets": [{"path": TARGET_PATH, "status": status, "locator": None, "reason": reason}]}


def _write_normalized_other(source_root: Path, out_root: Path, case_name: str, status_name: str, reason: str) -> dict[str, Any]:
    fmt = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"]["sha1"]
    targets = [{"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}]
    req_doc, req_saved, req_ref = envelope("code-proof-request", _request_for_targets("sha1", fmt["commit_oid"], targets))
    acquisition = _normalized_other_input(fmt["commit_oid"], status_name, reason)
    intent_doc, intent_saved, intent_ref = envelope("code-acquisition-intent", {"request": req_ref, "mode": "normalized_text", "acquisition": acquisition, "bundle": None})
    observed_target = {"path": TARGET_PATH, "status": {"missing": "host_missing", "inaccessible": "host_inaccessible", "unavailable": "host_unavailable"}[status_name], "reason": reason, "text": None}
    capabilities = {"git_objects_verified": False, "raw_bytes_retained": False, "repository_assertion": "unverified", "source_association_verified": False}
    eligibility = {"complete_target_set": False, "repository_requirement_met": True, "source_handoff_eligible": False}
    obs_data = {"request": req_ref, "intent": intent_ref, "bundle": None, "mode": "normalized_text", "git_proof": None, "targets": [observed_target], "capabilities": capabilities, "eligibility": eligibility}
    obs_doc, obs_saved, obs_ref = envelope("code-proof-observation", obs_data)
    status = _status(case_name, "observed", request=req_ref, intent=intent_ref, bundle=None, observation=obs_ref, mode="normalized_text", missing=[], targets=[observed_target], capabilities=capabilities, eligibility=eligibility, next_action="new_request_or_acquisition_required")
    files = [_save_doc(out_root, case_name, "request.json", req_saved, kind="request"), _save_doc(out_root, case_name, "intent.json", intent_saved, kind="intent"), _save_doc(out_root, case_name, "observation.json", obs_saved, kind="observation")]
    files.append(_save_payload(out_root, case_name, "request", _request_success(case_name, req_ref, targets, fmt["commit_oid"]), kind="success:request"))
    files.append(_save_payload(out_root, case_name, "observe", {"batch_id": case_name, "observation": obs_ref, "status": status}, kind="success:observe"))
    return _save_status_case(out_root, case_name, status, files=files, extras={"normalized_status": observed_target["status"], "acquisition_reason": reason})


def main() -> int:
    global PROFILE_PLACEHOLDER
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path(".work/parallel/code-proof-v1/terminal-1/source"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--profile-sha256", default=PROFILE_PLACEHOLDER)
    args = parser.parse_args()
    if type(args.profile_sha256) is not str or len(args.profile_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.profile_sha256):
        parser.error("--profile-sha256 must be 64 lowercase hex characters")
    PROFILE_PLACEHOLDER = args.profile_sha256
    source_root = args.source_root.resolve()
    sys.path.insert(0, str(source_root / "src"))
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    # Preserve the accepted R2 vectors as newly sealed R3 bytes.
    cases: dict[str, Any] = {
        "sha1_raw": build_case(source_root, output, "sha1"),
        "sha256_raw": build_case(source_root, output, "sha256"),
        "normalized_present": build_normalized(source_root, output),
    }
    cases["status_empty"] = _write_empty(output, "status-empty")
    cases["status_requested"] = _write_requested(source_root, output, "status-requested")
    cases["status_pending_normalized"] = _write_pending_normalized(source_root, output, "status-pending-normalized")
    cases["status_pending_raw_bundle"] = _write_raw_pending(source_root, output, "status-pending-raw-bundle", "sha1", None, False)
    cases["status_pending_raw_bodies_missing"] = _write_raw_pending(source_root, output, "status-pending-raw-bodies-missing", "sha256", 2, True)
    cases["status_pending_raw_bodies_complete"] = _write_raw_pending(source_root, output, "status-pending-raw-bodies-complete", "sha1", 3, True)
    cases["normalized_missing"] = _write_normalized_other(source_root, output, "normalized-missing", "missing", "host_reported_missing")
    cases["normalized_inaccessible"] = _write_normalized_other(source_root, output, "normalized-inaccessible", "inaccessible", "permission_denied")
    cases["normalized_unavailable"] = _write_normalized_other(source_root, output, "normalized-unavailable", "unavailable", "capability_unavailable")
    mixed_targets = [
        {"path": "config.json", "roles": ["configuration"], "allow_executable_source": False},
        {"path": "missing.py", "roles": ["implementation"], "allow_executable_source": False},
    ]
    cases["raw_mixed_incomplete"] = _write_raw_complete(source_root, output, "raw-mixed-incomplete", "sha1", mixed_targets)

    fixture = source_root / "tests/fixtures/code-git-objects-v1.json"
    manifest: dict[str, Any] = {
        "schema": "video-paper-wiki.code-proof-resource-fixture-manifest.v1",
        "revision": 3,
        "fixture_revision": 3,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "synthetic_only": True,
        "no_installed_resources": True,
        "public_command_execution": False,
        "configuration_parser_invoked": False,
        "profile_sha256": PROFILE_PLACEHOLDER,
        "provenance": {
            "accepted_worktree": str(source_root),
            "accepted_head": "b46e106e48438f18cbbcf0c3fbee8f0a7524f071",
            "accepted_tree": "3819b8d91ef3eb0b6649793d1b16a3d7806b87a1",
            "r2_manifest": {"path": "artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resource-fixtures-r2/manifest.json", "sha256": sha256((Path(__file__).resolve().parent.parent / "resource-fixtures-r2" / "manifest.json").read_bytes())},
            "r2_generator": {"path": "artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resource-fixtures-r2/generate_resource_fixtures.py", "sha256": sha256((Path(__file__).resolve().parent.parent / "resource-fixtures-r2" / "generate_resource_fixtures.py").read_bytes())},
            "generator": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).read_bytes())},
            "readme": {"path": str(output / "README.md"), "sha256": sha256((output / "README.md").read_bytes()) if (output / "README.md").is_file() else None},
            "git_fixture": str(fixture),
            "git_fixture_sha256": sha256(fixture.read_bytes()),
            "subset": "synthetic commit + root tree + config.json blob; accepted Git verifier consumed exactly three objects per raw case",
            "metadata_helper_checks": METADATA_HELPER_CHECKS,
            "contract_inputs": [
                {"path": "docs/ai/packets/full-todo-v1/CODE-PROOF-STATE-AND-INSTALL-R5.md", "sha256": sha256((Path("docs/ai/packets/full-todo-v1/CODE-PROOF-STATE-AND-INSTALL-R5.md")).read_bytes())},
                {"path": "docs/ai/packets/full-todo-v1/CODE-PROOF-WIRE-R7.md", "sha256": sha256((Path("docs/ai/packets/full-todo-v1/CODE-PROOF-WIRE-R7.md")).read_bytes())},
                {"path": "docs/ai/packets/full-todo-v1/CODE-PROOF-RESOURCE-CONTRACT-R12.md", "sha256": sha256((Path("docs/ai/packets/full-todo-v1/CODE-PROOF-RESOURCE-CONTRACT-R12.md")).read_bytes())},
            ],
        },
        "cases": cases,
        "ordinary_input_shapes": ["request-input", "observe-input"],
        "saved_envelope_kinds": ["code-proof-request", "code-git-bundle", "code-acquisition-intent", "code-proof-observation", "code-config-evidence", "code-source-handoff"],
        "success_data_kinds": ["request", "observe", "status", "config", "handoff"],
        "status_states": ["empty", "requested", "pending_normalized", "pending_raw_bundle", "pending_raw_bodies", "observed"],
        "ordinary_inputs": [],
    }
    fixture_formats = json.loads(fixture.read_bytes())["formats"]
    ordinary_values = [
        ("request-input-sha1.json", request_data("sha1", fixture_formats["sha1"]["commit_oid"], {"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}, include_profile=False)),
        ("request-input-sha256.json", request_data("sha256", fixture_formats["sha256"]["commit_oid"], {"path": TARGET_PATH, "roles": TARGET_ROLES, "allow_executable_source": False}, include_profile=False)),
        ("observe-input-raw-sha1.json", observe_raw("sha1", fixture_formats["sha1"]["commit_oid"])),
        ("observe-input-raw-sha256.json", observe_raw("sha256", fixture_formats["sha256"]["commit_oid"])),
        ("observe-input-normalized-present.json", observe_normalized(fixture_formats["sha1"]["commit_oid"])),
        ("observe-input-normalized-missing.json", _normalized_other_input(fixture_formats["sha1"]["commit_oid"], "missing", "host_reported_missing")),
        ("observe-input-normalized-inaccessible.json", _normalized_other_input(fixture_formats["sha1"]["commit_oid"], "inaccessible", "permission_denied")),
        ("observe-input-normalized-unavailable.json", _normalized_other_input(fixture_formats["sha1"]["commit_oid"], "unavailable", "capability_unavailable")),
        ("observe-input-raw-mixed.json", observe_raw("sha1", fixture_formats["sha1"]["commit_oid"])),
    ]
    for name, value in ordinary_values:
        path = output / "inputs" / name
        entry = write_json(path, value)
        entry["path"] = path.relative_to(output).as_posix()
        manifest["ordinary_inputs"].append(entry)
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output_dir": str(output), "manifest": str(output / "manifest.json"), "case_count": len(cases)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
