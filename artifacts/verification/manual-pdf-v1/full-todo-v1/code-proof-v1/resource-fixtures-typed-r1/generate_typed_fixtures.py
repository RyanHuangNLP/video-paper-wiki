#!/usr/bin/env python3
"""Generate typed CODE proof fixtures after an exact CONFIG acceptance.

This file is deliberately a preparation generator.  It does not import the
configuration implementation at module import time.  A run must name the
accepted CONFIG commit, tree, and acceptance-record digest; the run checks the
source checkout before loading the parser and producing any typed result.
All Git objects are synthetic loose-object bytes built in memory.  No Git
object is written to a repository and no provider is contacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[6]
STATIC_REL = Path(
    "artifacts/verification/manual-pdf-v1/full-todo-v1/"
    "code-proof-v1/config-r1/static-vectors-r4.json"
)
STATIC_SHA256 = "512384681dac91c737106d6cb84949aa446a9de9c015694582703be71485dfff"
ZERO_SHA256 = "0" * 64
PAPER_ID = "arxiv:2401.01234"
REPOSITORY = "synthetic-owner/synthetic-repo"
OBSERVED_AT = "2026-09-10T00:00:00Z"
TARGET_ROLES = ["configuration"]
AUTHOR = b"Synthetic Fixture Author <fixture-author@example.invalid> 1700000200 +0000"
COMMITTER = b"Synthetic Fixture Committer <fixture-committer@example.invalid> 1700000260 +0000"
PUBLIC_LIMITS = {
    "max_bundle_bytes": 1048576,
    "max_inline_normalized_bytes": 16384,
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize(value: Any) -> bytes:
    # Imported only by main after the accepted CONFIG gate.  Keeping this
    # function lazy also prevents accidental imports during static review.
    from video_paper_wiki.jcs import canonicalize as encode

    return encode(value)


def write_json(path: Path, value: Any) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
    raw = canonicalize(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    return {"path": path.as_posix(), "size_bytes": len(raw), "sha256": sha256(raw)}


def write_bytes(root: Path, relative: str, data: bytes, kind: str) -> dict[str, Any]:
    path = root / relative
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return {
        "path": relative,
        "size_bytes": len(data),
        "sha256": sha256(data),
        "kind": kind,
    }


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


def request_limits(config_limits: dict[str, int]) -> dict[str, dict[str, int]]:
    return {
        "git": {
            "max_targets": 32,
            "max_objects": 2048,
            "max_tree_entries": 32768,
            "max_object_bytes": 8388608,
            "max_total_object_bytes": 33554432,
        },
        "config": dict(config_limits),
        "public": dict(PUBLIC_LIMITS),
    }


def request_data(
    *,
    object_format: str,
    commit_oid: str,
    target_path: str,
    config_limits: dict[str, int],
    profile_sha256: str,
    include_profile: bool = True,
) -> dict[str, Any]:
    value = {
        "paper_id": PAPER_ID,
        "source_association": None,
        "repository": REPOSITORY,
        "object_format": object_format,
        "commit_oid": commit_oid,
        "targets": [
            {
                "path": target_path,
                "roles": TARGET_ROLES,
                "allow_executable_source": False,
            }
        ],
        "require_repository_assertion": False,
        "limits": request_limits(config_limits),
    }
    if include_profile:
        value["profile_sha256"] = profile_sha256
    return value


def observe_input(*, object_format: str, commit_oid: str) -> dict[str, Any]:
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


def source_metadata(body: bytes) -> dict[str, Any]:
    """Compute the accepted TextMetadata shape without importing other product modules."""
    if body.startswith(b"\xef\xbb\xbf"):
        raise ValueError("fixture text unexpectedly has a BOM")
    text = body.decode("utf-8", errors="strict")
    forbidden = set(range(0, 9)) | {11, 12} | set(range(14, 32)) | set(range(127, 160)) | {0x2028, 0x2029}
    if any(ord(char) in forbidden for char in text):
        raise ValueError("fixture text contains a forbidden control")
    normalized = text.replace("\r\n", "\n").encode("utf-8")
    if b"\r" in normalized:
        raise ValueError("fixture text contains bare CR")
    crlf = body.count(b"\r\n")
    lf = body.count(b"\n") - crlf
    style = "mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "none"
    return {
        "normalized_size_bytes": len(normalized),
        "normalized_sha256": sha256(normalized),
        "newline_style": style,
        "ends_with_newline": normalized.endswith(b"\n"),
        "line_count": 0 if not normalized else normalized.count(b"\n") + (not normalized.endswith(b"\n")),
    }


def git_object(object_format: str, object_type: bytes, body: bytes) -> tuple[str, bytes, dict[str, Any]]:
    framed = object_type + b" " + str(len(body)).encode("ascii") + b"\0" + body
    digest = hashlib.new(object_format, framed).hexdigest()
    record = {
        "oid": digest,
        "object_type": object_type.decode("ascii"),
        "body_size_bytes": len(body),
        "body_sha256": sha256(body),
        "framed_sha256": sha256(framed),
    }
    return digest, body, record


def synthetic_git_case(
    *, object_format: str, target_path: str, case_name: str, source: bytes
) -> dict[str, Any]:
    """Build one regular-blob/root-tree/commit set without invoking Git."""
    blob_oid, blob_body, blob_record = git_object(object_format, b"blob", source)
    tree_body = b"100644 " + target_path.encode("ascii") + b"\0" + bytes.fromhex(blob_oid)
    tree_oid, _, tree_record = git_object(object_format, b"tree", tree_body)
    commit_body = (
        b"tree "
        + tree_oid.encode("ascii")
        + b"\nauthor "
        + AUTHOR
        + b"\ncommitter "
        + COMMITTER
        + b"\n\nSynthetic typed CONFIG fixture "
        + case_name.encode("ascii")
        + b".\n"
    )
    commit_oid, _, commit_record = git_object(object_format, b"commit", commit_body)
    records = sorted([blob_record, tree_record, commit_record], key=lambda item: item["oid"])
    bodies = {blob_oid: blob_body, tree_oid: tree_body, commit_oid: commit_body}
    return {
        "object_format": object_format,
        "commit_oid": commit_oid,
        "root_tree_oid": tree_oid,
        "blob_oid": blob_oid,
        "records": records,
        "bodies": bodies,
    }


def gate_source_checkout(
    source_root: Path,
    expected_head: str,
    expected_tree: str,
    acceptance_sha256: str,
) -> None:
    if not (len(expected_head) == 40 and all(c in "0123456789abcdef" for c in expected_head)):
        raise ValueError("--accepted-config-head must be 40 lowercase hex characters")
    if not (len(expected_tree) == 40 and all(c in "0123456789abcdef" for c in expected_tree)):
        raise ValueError("--accepted-config-tree must be 40 lowercase hex characters")
    if not (len(acceptance_sha256) == 64 and all(c in "0123456789abcdef" for c in acceptance_sha256)):
        raise ValueError("--accepted-config-acceptance-sha256 must be 64 lowercase hex characters")
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
    }
    def read(*args: str) -> str:
        result = subprocess.run(
            ["git", "--no-optional-locks", "--no-replace-objects", "-C", str(source_root), *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CONFIG acceptance gate could not read Git state: {result.stderr.strip()}")
        return result.stdout.strip()
    actual_head = read("rev-parse", "HEAD")
    actual_tree = read("rev-parse", "HEAD^{tree}")
    if actual_head != expected_head or actual_tree != expected_tree:
        raise RuntimeError(
            "refusing typed fixture generation: source checkout is not the exact accepted CONFIG head/tree"
        )


def load_runtime(source_root: Path) -> tuple[Any, Any, Any, dict[str, int]]:
    source_src = source_root / "src"
    if not source_src.is_dir():
        raise ValueError(f"accepted source root has no src directory: {source_src}")
    sys.path.insert(0, str(source_src))
    from video_paper_wiki.code_config_parser import (  # noqa: PLC0415
        CODE_CONFIG_PROFILE_LIMITS,
        parse_code_config_bytes,
    )
    from video_paper_wiki.code_git_objects import (  # noqa: PLC0415
        CODE_GIT_PROFILE_LIMITS,
        verify_code_git_objects,
    )

    return (
        parse_code_config_bytes,
        verify_code_git_objects,
        CODE_GIT_PROFILE_LIMITS,
        dict(CODE_CONFIG_PROFILE_LIMITS),
    )


def build_case(
    *,
    vector: dict[str, Any],
    object_format: str,
    profile_sha256: str,
    config_limits: dict[str, int],
    parse_config: Callable[..., dict[str, Any]],
    verify_git: Callable[..., dict[str, Any]],
    git_limits: dict[str, int],
    output: Path,
) -> dict[str, Any]:
    case_name = f"{vector['id']}-{object_format}"
    target_path = f"config.{vector['format']}"
    source = vector["source_utf8"].encode("utf-8")
    parsed = parse_config(payload=source, config_format=vector["format"], limits=config_limits)
    expected = {
        "config_format": vector["format"],
        "source": vector["source"],
        "nodes": vector["expected_nodes"],
    }
    if parsed["config_format"] != expected["config_format"]:
        raise AssertionError((case_name, "config_format"))
    if parsed["source"] != expected["source"] or parsed["nodes"] != expected["nodes"]:
        raise AssertionError((case_name, "accepted parser output differs from independent vector"))

    git = synthetic_git_case(
        object_format=object_format,
        target_path=target_path,
        case_name=case_name,
        source=source,
    )
    target = {"path": target_path, "allow_executable_source": False}
    proof = verify_git(
        object_format=object_format,
        commit_oid=git["commit_oid"],
        root_tree_oid=git["root_tree_oid"],
        objects=git["records"],
        bodies=git["bodies"],
        targets=[target],
        limits=dict(git_limits),
    )
    proof_target = proof["targets"][0]
    if proof_target["outcome"] != "permitted_regular_blob":
        raise AssertionError((case_name, proof_target))
    if proof_target["path"] != target_path:
        raise AssertionError((case_name, "Git verifier path mismatch"))
    metadata = source_metadata(source)
    batch_id = f"typed-config-{case_name}"
    logical_root = f".work/{batch_id}/code-evidence-v1"
    raw_ref = {
        "path": f"{logical_root}/objects/{git['blob_oid']}.body",
        "size_bytes": len(source),
        "sha256": sha256(source),
    }
    req_document, req_saved, req_ref = envelope(
        "code-proof-request",
        request_data(
            object_format=object_format,
            commit_oid=git["commit_oid"],
            target_path=target_path,
            config_limits=config_limits,
            profile_sha256=profile_sha256,
        ),
    )
    bundle_document, bundle_saved, bundle_ref = envelope(
        "code-git-bundle",
        {
            "request": req_ref,
            "object_format": object_format,
            "repository": REPOSITORY,
            "commit_oid": git["commit_oid"],
            "root_tree_oid": git["root_tree_oid"],
            "objects": git["records"],
        },
    )
    acquisition = observe_input(object_format=object_format, commit_oid=git["commit_oid"])
    intent_document, intent_saved, intent_ref = envelope(
        "code-acquisition-intent",
        {
            "request": req_ref,
            "mode": "git_objects",
            "acquisition": acquisition,
            "bundle": {"directory": f".work/{batch_id}/raw-input", "reference": bundle_ref},
        },
    )
    observed_target = {"path": target_path, "status": "source_text", "reason": None, "text": metadata}
    capabilities = {
        "git_objects_verified": True,
        "raw_bytes_retained": True,
        "repository_assertion": "host_asserted",
        "source_association_verified": False,
    }
    eligibility = {
        "complete_target_set": True,
        "repository_requirement_met": True,
        "source_handoff_eligible": True,
    }
    observation_document, observation_saved, observation_ref = envelope(
        "code-proof-observation",
        {
            "request": req_ref,
            "intent": intent_ref,
            "bundle": bundle_ref,
            "mode": "git_objects",
            "git_proof": proof,
            "targets": [observed_target],
            "capabilities": capabilities,
            "eligibility": eligibility,
        },
    )
    config_document, config_saved, config_ref = envelope(
        "code-config-evidence",
        {
            "request": req_ref,
            "observation": observation_ref,
            "bundle": bundle_ref,
            "path": target_path,
            "object_format": object_format,
            "blob_oid": git["blob_oid"],
            "raw_body": raw_ref,
            "format": vector["format"],
            "result": parsed,
            "source_only_reason": None,
        },
    )
    handoff_document, handoff_saved, handoff_ref = envelope(
        "code-source-handoff",
        {
            "successor_only": True,
            "request": req_ref,
            "observation": observation_ref,
            "bundle": bundle_ref,
            "paper_id": PAPER_ID,
            "source_association": None,
            "repository": REPOSITORY,
            "object_format": object_format,
            "commit_oid": git["commit_oid"],
            "root_tree_oid": git["root_tree_oid"],
            "path": target_path,
            "roles": TARGET_ROLES,
            "allow_executable_source": False,
            "blob": proof_target["blob"],
            "raw_body": raw_ref,
            "text": metadata,
            "proof": proof_target,
            "repository_assertion": "host_asserted",
            "source_association_verified": False,
        },
    )
    path_key = sha256(target_path.encode("ascii"))
    configs = [{"path": target_path, "reference": config_ref, "stored_path": f"{logical_root}/configs/{path_key}.json"}]
    handoffs = [{"path": target_path, "reference": handoff_ref, "stored_path": f"{logical_root}/handoffs/{path_key}.json"}]
    status = {
        "batch_id": batch_id,
        "state": "observed",
        "request": req_ref,
        "intent": intent_ref,
        "bundle": bundle_ref,
        "observation": observation_ref,
        "mode": "git_objects",
        "missing": [],
        "targets": [observed_target],
        "capabilities": capabilities,
        "eligibility": eligibility,
        "configs": configs,
        "handoffs": handoffs,
        "next_action": "successor_capture",
    }
    success = {
        "request": {
            "batch_id": batch_id,
            "request": req_ref,
            "already_staged": False,
            "acquisition_targets": [
                {
                    "path": target_path,
                    "github_url": f"https://github.com/{REPOSITORY}/blob/{git['commit_oid']}/{target_path}",
                    "raw_url": f"https://raw.githubusercontent.com/{REPOSITORY}/{git['commit_oid']}/{target_path}",
                }
            ],
        },
        "observe": {"batch_id": batch_id, "observation": observation_ref, "status": status},
        "status": status,
        "config": {
            "batch_id": batch_id,
            "path": target_path,
            "config": config_ref,
            "stored_path": configs[0]["stored_path"],
            "already_staged": False,
        },
        "handoff": {
            "batch_id": batch_id,
            "handoffs": [
                {
                    "path": target_path,
                    "handoff": handoff_ref,
                    "stored_path": handoffs[0]["stored_path"],
                    "source_body_path": raw_ref["path"],
                    "already_staged": False,
                }
            ],
        },
    }
    files: list[dict[str, Any]] = []
    for name, saved, kind in (
        ("request.json", req_saved, "request"),
        ("bundle.json", bundle_saved, "bundle"),
        ("intent.json", intent_saved, "intent"),
        ("observation.json", observation_saved, "observation"),
        ("config.json", config_saved, "config"),
        ("handoff.json", handoff_saved, "handoff"),
    ):
        files.append(write_bytes(output, f"saved/{case_name}/{name}", saved, kind))
    for record in git["records"]:
        files.append(write_bytes(output, f"saved/{case_name}/objects/{record['oid']}.body", git["bodies"][record["oid"]], "raw-body"))
    for name, payload in success.items():
        written = write_json(output / "success-data" / f"{case_name}-{name}.json", payload)
        written.update({"path": f"success-data/{case_name}-{name}.json", "kind": f"success:{name}"})
        files.append(written)
    for name, payload in (
        (
            "request-input.json",
            request_data(
                object_format=object_format,
                commit_oid=git["commit_oid"],
                target_path=target_path,
                config_limits=config_limits,
                profile_sha256=profile_sha256,
                include_profile=False,
            ),
        ),
        ("observe-input.json", acquisition),
    ):
        written = write_json(output / "inputs" / f"{case_name}-{name}", payload)
        written.update({"path": f"inputs/{case_name}-{name}", "kind": f"input:{name[:-5]}"})
        files.append(written)
    return {
        "name": case_name,
        "vector": vector["id"],
        "format": vector["format"],
        "object_format": object_format,
        "batch_id": batch_id,
        "commit_oid": git["commit_oid"],
        "root_tree_oid": git["root_tree_oid"],
        "blob_oid": git["blob_oid"],
        "target_path": target_path,
        "raw_body_sha256": sha256(source),
        "typed_result": config_ref,
        "handoff": handoff_ref,
        "repository_assertion": "host_asserted_synthetic",
        "officiality_claim": None,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--accepted-config-head", required=True)
    parser.add_argument("--accepted-config-tree", required=True)
    parser.add_argument("--accepted-config-acceptance-sha256", required=True)
    parser.add_argument("--profile-sha256", default=ZERO_SHA256)
    parser.add_argument("--static-vectors", type=Path, default=ROOT / STATIC_REL)
    args = parser.parse_args()
    if len(args.profile_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.profile_sha256):
        parser.error("--profile-sha256 must be 64 lowercase hex characters")
    source_root = args.source_root.resolve()
    output = args.output_dir.resolve()
    static_path = args.static_vectors.resolve()
    if output.exists():
        raise SystemExit(f"refusing non-fresh output directory: {output}")
    gate_source_checkout(source_root, args.accepted_config_head, args.accepted_config_tree, args.accepted_config_acceptance_sha256)
    if not static_path.is_file() or sha256(static_path.read_bytes()) != STATIC_SHA256:
        raise SystemExit("refusing typed fixture generation: frozen static vectors are missing or changed")
    parse_config, verify_git, git_limits, config_limits = load_runtime(source_root)
    vectors = json.loads(static_path.read_bytes())["success_vectors"]
    if [item["id"] for item in vectors] != [
        "json-nested-lf",
        "json-unicode-crlf-tabs",
        "json-pointer-escaping",
        "toml-nested-lf",
        "toml-unicode-crlf-inline",
        "toml-dotted-promotion",
        "toml-numeric-boundaries",
    ]:
        raise SystemExit("refusing typed fixture generation: success-vector inventory changed")
    output.mkdir(parents=True)
    cases = []
    for vector in vectors:
        for object_format in ("sha1", "sha256"):
            cases.append(
                build_case(
                    vector=vector,
                    object_format=object_format,
                    profile_sha256=args.profile_sha256,
                    config_limits=config_limits,
                    parse_config=parse_config,
                    verify_git=verify_git,
                    git_limits=git_limits,
                    output=output,
                )
            )
    manifest = {
        "schema": "video-paper-wiki.code-proof-typed-fixture-manifest.v1",
        "revision": 1,
        "fixture_revision": 1,
        "synthetic_only": True,
        "configuration_parser_invoked": True,
        "public_command_execution": False,
        "network_or_provider": False,
        "officiality_claim": None,
        "profile_sha256": args.profile_sha256,
        "accepted_config": {
            "head": args.accepted_config_head,
            "tree": args.accepted_config_tree,
            "acceptance_record_sha256": args.accepted_config_acceptance_sha256,
        },
        "static_vectors": {
            "path": STATIC_REL.as_posix(),
            "sha256": STATIC_SHA256,
            "success_vector_count": len(vectors),
        },
        "formats": ["json", "toml"],
        "object_formats": ["sha1", "sha256"],
        "saved_envelope_kinds": [
            "code-proof-request",
            "code-git-bundle",
            "code-acquisition-intent",
            "code-proof-observation",
            "code-config-evidence",
            "code-source-handoff",
        ],
        "cases": sorted(cases, key=lambda item: item["name"]),
        "generator": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).read_bytes())},
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output_dir": str(output), "manifest": str(output / "manifest.json"), "case_count": len(cases)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
