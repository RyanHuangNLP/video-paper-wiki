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
    sha1 = build_case(source_root, output, "sha1")
    sha256_case = build_case(source_root, output, "sha256")
    normalized = build_normalized(source_root, output)
    fixture = source_root / "tests/fixtures/code-git-objects-v1.json"
    manifest = {
        "schema": "video-paper-wiki.code-proof-resource-fixture-manifest.v1",
        "revision": 2,
        "fixture_revision": 2,
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
            "r1_manifest": {"path": "artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resource-fixtures-r1/manifest.json", "sha256": sha256((Path(__file__).resolve().parent.parent / "resource-fixtures-r1" / "manifest.json").read_bytes())},
            "generator": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).read_bytes())},
            "readme": {"path": str(output / "README.md"), "sha256": sha256((output / "README.md").read_bytes()) if (output / "README.md").is_file() else None},
            "git_fixture": str(fixture),
            "git_fixture_sha256": sha256(fixture.read_bytes()),
            "subset": "synthetic commit + root tree + config.json blob; verifier consumed exactly three objects per raw case",
            "metadata_helper_checks": METADATA_HELPER_CHECKS,
        },
        "cases": {"sha1_raw": sha1, "sha256_raw": sha256_case, "normalized": normalized},
        "ordinary_input_shapes": ["request-input", "observe-input"],
        "saved_envelope_kinds": ["code-proof-request", "code-git-bundle", "code-acquisition-intent", "code-proof-observation", "code-config-evidence", "code-source-handoff"],
        "success_data_kinds": ["request", "observe", "status", "config", "handoff"],
        "ordinary_inputs": [],
    }
    # Ordinary inputs are written last so they carry the same fixed request/observe shapes.
    for fmt in ("sha1", "sha256"):
        fx=json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"][fmt]
        path = output / "inputs" / f"request-input-{fmt}.json"
        entry = write_json(path, request_data(fmt, fx["commit_oid"], {"path":TARGET_PATH,"roles":TARGET_ROLES,"allow_executable_source":False}, include_profile=False))
        entry["path"] = path.relative_to(output).as_posix()
        manifest["ordinary_inputs"].append(entry)
    fixture_formats = json.loads((source_root / "tests/fixtures/code-git-objects-v1.json").read_bytes())["formats"]
    for name, value in (("observe-input-raw-sha1.json", observe_raw("sha1", fixture_formats["sha1"]["commit_oid"])), ("observe-input-raw-sha256.json", observe_raw("sha256", fixture_formats["sha256"]["commit_oid"])), ("observe-input-normalized.json", observe_normalized(fixture_formats["sha1"]["commit_oid"]))):
        path = output / "inputs" / name
        entry = write_json(path, value)
        entry["path"] = path.relative_to(output).as_posix()
        manifest["ordinary_inputs"].append(entry)
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output_dir": str(output), "manifest": str(output / "manifest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
