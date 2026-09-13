"""Builders for public code-evidence tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from video_paper_wiki.code_git_objects import git_object_ids
from video_paper_wiki.code_proof_io import open_code_session
from video_paper_wiki.jcs import canonicalize

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
_PYPROJECT = '[project]\nname = "video-paper-wiki"\n'
_AUTHOR = "Fixture Author <fixture@example.invalid> 1700000000 +0000"
PAPER_ID = "arxiv:2301.00001"
REPO_INPUT = "Owner/Name"
REPO_SAVED = "owner/name"
OBSERVED_AT = "2026-01-02T03:04:05Z"
JSON_BODY = b'{"name":"demo"}\n'
TOML_BODY = b'name = "demo"\n'
SRC_BODY = b"print(1)\n"
README_BODY = b"# demo\n"
OUTPUT_LIMITS = {
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_bundle_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}
HARD_LIMITS = {
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
}


def make_checkout(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()
    (path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return path


def dump_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _tree_body(object_format: str, entries: list[tuple[str, str, str]]) -> bytes:
    raw_len = 20 if object_format == "sha1" else 32

    def sort_key(item: tuple[str, str, str]) -> bytes:
        mode, name, _oid = item
        return name.encode("ascii") + (b"/" if mode == "40000" else b"\0")

    chunks = []
    for mode, name, oid in sorted(entries, key=sort_key):
        raw = bytes.fromhex(oid)
        assert len(raw) == raw_len
        chunks.append(mode.encode("ascii") + b" " + name.encode("ascii") + b"\0" + raw)
    return b"".join(chunks)


def _commit_body(tree_oid: str) -> bytes:
    return (
        "tree "
        + tree_oid
        + "\n"
        + "author "
        + _AUTHOR
        + "\n"
        + "committer "
        + _AUTHOR
        + "\n"
        + "\n"
        + "synthetic\n"
    ).encode("ascii")


def _record(object_format: str, object_type: str, body: bytes) -> dict:
    oid, body_sha, framed_sha = git_object_ids(object_format, object_type, body)
    return {
        "oid": oid,
        "object_type": object_type,
        "body_size_bytes": len(body),
        "body_sha256": body_sha,
        "framed_sha256": framed_sha,
        "body": body,
    }


def make_repo(object_format: str, files: dict[str, tuple[bytes, bool]]) -> dict:
    blob_records = []
    tree_entries = []
    for name in files:
        body, executable = files[name]
        rec = _record(object_format, "blob", body)
        blob_records.append(rec)
        mode = "100755" if executable else "100644"
        tree_entries.append((mode, name, rec["oid"]))
    tree = _record(object_format, "tree", _tree_body(object_format, tree_entries))
    commit = _record(object_format, "commit", _commit_body(tree["oid"]))
    records = []
    bodies = {}
    for rec in blob_records + [tree, commit]:
        bodies[rec["oid"]] = rec["body"]
        records.append(
            {
                "oid": rec["oid"],
                "object_type": rec["object_type"],
                "body_size_bytes": rec["body_size_bytes"],
                "body_sha256": rec["body_sha256"],
                "framed_sha256": rec["framed_sha256"],
            }
        )
    records.sort(key=lambda item: item["oid"])
    return {
        "object_format": object_format,
        "commit_oid": commit["oid"],
        "root_tree_oid": tree["oid"],
        "objects": records,
        "bodies": bodies,
    }


def request_doc(repo: dict, targets: list[dict], **extra) -> dict:
    doc = {
        "paper_id": PAPER_ID,
        "source_association": None,
        "repository": extra.get("repository", REPO_INPUT),
        "object_format": repo["object_format"],
        "commit_oid": repo["commit_oid"],
        "targets": targets,
        "require_repository_assertion": extra.get(
            "require_repository_assertion", False
        ),
    }
    if "limits" in extra:
        doc["limits"] = extra["limits"]
    return doc


def default_targets() -> list[dict]:
    return [
        {
            "path": "config.json",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ]


def default_files() -> dict[str, tuple[bytes, bool]]:
    return {
        "config.json": (JSON_BODY, False),
        "src.py": (SRC_BODY, False),
    }


def hosting_assertion(repo: dict) -> dict:
    return {
        "provider": "github",
        "actor": {"kind": "unknown", "id": None},
        "repository": REPO_SAVED,
        "object_format": repo["object_format"],
        "commit_oid": repo["commit_oid"],
        "locator": (
            "https://github.com/"
            + REPO_SAVED
            + "/commit/"
            + repo["commit_oid"]
        ),
        "statement": "host recorded this commit.",
    }


def observe_raw_doc(repo: dict, *, hosting=None) -> dict:
    return {
        "mode": "git_objects",
        "observed_at": OBSERVED_AT,
        "executor": {"kind": "unknown", "id": None},
        "hosting_assertion": hosting,
    }


def observe_norm_doc(repo: dict, texts: dict[str, str], *, hosting=None) -> dict:
    targets = []
    for item in default_targets():
        path = item["path"]
        locator = (
            "https://github.com/"
            + REPO_SAVED
            + "/blob/"
            + repo["commit_oid"]
            + "/"
            + path
        )
        if path in texts:
            targets.append(
                {
                    "path": path,
                    "status": "present",
                    "locator": locator,
                    "text": texts[path],
                }
            )
        else:
            targets.append(
                {
                    "path": path,
                    "status": "missing",
                    "locator": None,
                    "reason": "host_reported_missing",
                }
            )
    return {
        "mode": "normalized_text",
        "observed_at": OBSERVED_AT,
        "executor": {"kind": "unknown", "id": None},
        "hosting_assertion": hosting,
        "targets": targets,
    }


def seal(kind: str, data: dict) -> bytes:
    schema = "video-paper-wiki." + kind + ".v1"
    core = {"schema": schema, "kind": kind, "data": data}
    digest = __import__("hashlib").sha256(canonicalize(core)).hexdigest()
    ident = "ce1:" + kind + ":" + digest
    envelope = {"schema": schema, "kind": kind, "id": ident, "data": data}
    return canonicalize(envelope) + b"\n"


def write_bundle(checkout: Path, relative: str, repo: dict, request_ref: dict) -> str:
    root = checkout / relative
    objects = root / "objects"
    objects.mkdir(parents=True)
    data = {
        "request": request_ref,
        "object_format": repo["object_format"],
        "repository": REPO_SAVED,
        "commit_oid": repo["commit_oid"],
        "root_tree_oid": repo["root_tree_oid"],
        "objects": repo["objects"],
    }
    payload = seal("code-git-bundle", data)
    (root / "manifest.json").write_bytes(payload)
    for record in repo["objects"]:
        body = repo["bodies"][record["oid"]]
        dest = objects / (record["oid"] + ".body")
        dest.write_bytes(body)
        os.chmod(dest, 0o600)
    os.chmod(root / "manifest.json", 0o600)
    return relative


def public_limits(**public_overrides):
    copied = {
        "git": dict(HARD_LIMITS["git"]),
        "config": dict(HARD_LIMITS["config"]),
        "public": dict(HARD_LIMITS["public"]),
    }
    copied["public"].update(public_overrides)
    return copied


def copy_outputs(src_batch: str, dst_batch: str, names: list[str]) -> None:
    src_ns = Path(".work") / src_batch / "code-evidence-v1"
    with open_code_session(batch_id=dst_batch) as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        for name in names:
            session.install(name, (src_ns / name).read_bytes())


def run_module_cli(checkout: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not previous else str(SRC) + os.pathsep + previous
    return subprocess.run(
        [sys.executable, "-m", "video_paper_wiki.cli", *argv],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_envelope(proc: subprocess.CompletedProcess[str]) -> dict:
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, proc.stdout + proc.stderr
    return json.loads(lines[0])


def nested_json_object(depth: int) -> bytes:
    text = "1"
    for _ in range(depth):
        text = '{"k":' + text + "}"
    return text.encode("ascii") + b"\n"
