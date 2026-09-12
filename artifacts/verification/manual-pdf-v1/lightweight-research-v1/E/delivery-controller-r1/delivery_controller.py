#!/usr/bin/env python3
"""Bounded exact-path delivery controller for lightweight-research-v1.

The default command is a read-only plan.  It validates a future, immutable
delivery manifest and audits the exact staged tree in a private temporary
index.  It never edits the protected target checkout unless ``--execute`` is
given together with a separately hashed Architect handoff that authorizes the
requested action.

This file is evidence/control tooling, not product code.  It deliberately
does not know the product's path names; the signed manifest supplies those.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable


DEFAULT_TARGET = "/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration"
EXPECTED_PRODUCT_FILES = 26
EXPECTED_METADATA_FILES = 6
ALLOWED_ACTIONS = {"stage", "commit", "push"}
HANDOFF_STATUSES = {
    "GO_FOR_STEWARD_DELIVERY",
    "AUTHORIZED_FOR_STEWARD_DELIVERY",
}
FORBIDDEN_DESTINATION_SEGMENTS = {
    ".work",
    "inbox",
    "tools",
    ".git",
}
FORBIDDEN_DESTINATION_SUFFIXES = (
    ".pdf",
    ".log",
    ".log.jsonl",
)


class ControllerError(RuntimeError):
    """A closed, actionable controller refusal."""


def die(message: str) -> "NoReturn":
    raise ControllerError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        die(f"cannot read {path}: {exc}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(json_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        die(f"invalid UTF-8/JSON at {path}: {exc}")
    if not isinstance(value, dict):
        die(f"JSON root must be an object: {path}")
    return value


def git(target: Path, args: list[str], *, env: dict[str, str] | None = None) -> str:
    command = ["git", "-C", str(target), *args]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        proc = subprocess.run(
            command,
            env=merged,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        die(f"cannot run {' '.join(command)}: {exc}")
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip()
        die(f"git {' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc.stdout


def git_bytes(target: Path, args: list[str], *, env: dict[str, str] | None = None) -> bytes:
    command = ["git", "-C", str(target), *args]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        proc = subprocess.run(
            command,
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        die(f"cannot run {' '.join(command)}: {exc}")
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        die(f"git {' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc.stdout


def require_hex(value: Any, name: str, length: int = 40) -> str:
    if not isinstance(value, str) or len(value) != length:
        die(f"{name} must be a {length}-character hexadecimal string")
    try:
        int(value, 16)
    except ValueError:
        die(f"{name} must be hexadecimal")
    return value.lower()


def clean_rel_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        die(f"{name} must be a non-empty POSIX relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        die(f"{name} is unsafe: {value!r}")
    normalized = p.as_posix()
    if normalized != value:
        die(f"{name} is not normalized: {value!r}")
    return normalized


def mode_from_stat(mode: int) -> str:
    return f"{stat.S_IMODE(mode):o}"


def manifest_mode(value: Any, name: str) -> str:
    if isinstance(value, int):
        value = f"{value:o}"
    if not isinstance(value, str) or value not in {"100644", "100755"}:
        die(f"{name} must be 100644 or 100755")
    return value


def validate_source(row: dict[str, Any], *, root: Path) -> dict[str, Any]:
    path = clean_rel_path(row.get("path"), "file.path")
    source_value = row.get("source")
    if not isinstance(source_value, str) or not os.path.isabs(source_value):
        die(f"{path}: source must be absolute")
    source = Path(source_value)
    try:
        source_stat = source.lstat()
    except OSError as exc:
        die(f"{path}: source is unavailable: {exc}")
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        die(f"{path}: source must be a regular non-symlink file")
    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        die(f"{path}: sha256 must be a 64-character hexadecimal string")
    try:
        int(expected_hash, 16)
    except ValueError:
        die(f"{path}: sha256 must be hexadecimal")
    size = row.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        die(f"{path}: size_bytes must be a non-negative integer")
    expected_mode = manifest_mode(row.get("git_mode"), f"{path}.git_mode")
    actual_hash = sha256_file(source)
    actual_size = source_stat.st_size
    actual_mode = "100755" if source_stat.st_mode & stat.S_IXUSR else "100644"
    if actual_hash != expected_hash.lower() or actual_size != size or actual_mode != expected_mode:
        die(
            f"{path}: source mismatch (hash {actual_hash}/{expected_hash}, "
            f"size {actual_size}/{size}, mode {actual_mode}/{expected_mode})"
        )
    return {
        "path": path,
        "source": str(source),
        "sha256": actual_hash,
        "size_bytes": actual_size,
        "git_mode": expected_mode,
        "owner": row.get("owner"),
    }


def validate_manifest(manifest_path: Path, target: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_json(manifest_path)
    schema = manifest.get("schema")
    if not isinstance(schema, str) or not schema.startswith("lightweight-research-exact-delivery-manifest.v"):
        die(f"unsupported manifest schema: {schema!r}")
    if manifest.get("target") != str(target):
        die(f"manifest target does not equal protected target: {manifest.get('target')!r}")
    if manifest.get("status") not in {
        "FROZEN_32_PATH_DELIVERY_PENDING_INDEPENDENT_METADATA_REVIEW_AND_ARCHITECT_HANDOFF",
        "FROZEN_32_PATH_DELIVERY_PENDING_HANDOFF",
        "AUTHORIZED_32_PATH_DELIVERY",
        "GO_FOR_STEWARD_DELIVERY",
    }:
        die(f"manifest is not a frozen/authorized 32-path delivery: {manifest.get('status')!r}")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 32:
        die("manifest must contain exactly 32 file rows")
    if manifest.get("product_files") != EXPECTED_PRODUCT_FILES or manifest.get("metadata_files") != EXPECTED_METADATA_FILES:
        die("manifest product_files/metadata_files must be 26 and 6")
    paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            die("each manifest file row must be an object")
        row = validate_source(raw, root=target)
        if row["path"] in paths:
            die(f"duplicate manifest path: {row['path']}")
        paths.add(row["path"])
        parts = PurePosixPath(row["path"]).parts
        if FORBIDDEN_DESTINATION_SEGMENTS.intersection(parts):
            die(f"protected/generated destination is forbidden: {row['path']}")
        if row["path"].lower().endswith(FORBIDDEN_DESTINATION_SUFFIXES):
            die(f"raw/log destination is forbidden: {row['path']}")
        normalized.append(row)
    baseline = require_hex(manifest.get("baseline"), "manifest.baseline")
    baseline_tree = require_hex(manifest.get("baseline_tree"), "manifest.baseline_tree")
    if manifest.get("base_ref") not in {"integration", "refs/heads/integration"}:
        die(f"unexpected manifest base_ref: {manifest.get('base_ref')!r}")
    if manifest.get("pr") != 95:
        die("manifest must target PR 95")
    return {**manifest, "baseline": baseline, "baseline_tree": baseline_tree}, normalized


def target_snapshot(target: Path) -> dict[str, Any]:
    if not target.is_dir():
        die(f"protected target is not a directory: {target}")
    root = Path(git(target, ["rev-parse", "--show-toplevel"]).strip()).resolve()
    if root != target.resolve():
        die(f"git root mismatch: {root} != {target.resolve()}")
    branch = git(target, ["branch", "--show-current"]).strip()
    head = git(target, ["rev-parse", "HEAD"]).strip()
    tree = git(target, ["rev-parse", "HEAD^{tree}"]).strip()
    porcelain = git(target, ["status", "--porcelain=v1", "--untracked-files=all"])
    return {
        "branch": branch,
        "head": head,
        "tree": tree,
        "clean": porcelain == "",
        "status": porcelain,
    }


def assert_target_baseline(manifest: dict[str, Any], snapshot: dict[str, Any], *, require_clean: bool = True) -> None:
    if snapshot["branch"] != manifest.get("branch"):
        die(f"target branch changed: {snapshot['branch']!r} != {manifest.get('branch')!r}")
    if snapshot["head"] != manifest["baseline"]:
        die(f"target HEAD changed: {snapshot['head']} != {manifest['baseline']}")
    if snapshot["tree"] != manifest["baseline_tree"]:
        die(f"target baseline tree changed: {snapshot['tree']} != {manifest['baseline_tree']}")
    if require_clean and not snapshot["clean"]:
        die(f"target worktree/index is not clean:\n{snapshot['status']}")


def write_pathspec(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(row["path"].encode("utf-8") + b"\0" for row in rows))


def parse_staged_entries(raw: bytes) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        left, name = item.split(b"\t", 1)
        mode, blob, _stage = left.decode("ascii").split(" ")
        path = name.decode("utf-8")
        entries[path] = (mode, blob)
    return entries


def audit_index(
    target: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    worktree: Path,
    index_file: Path,
    object_directory: Path,
) -> dict[str, Any]:
    git_dir = Path(git(target, ["rev-parse", "--git-dir"]).strip())
    if not git_dir.is_absolute():
        git_dir = (target / git_dir).resolve()
    git_common_dir = Path(git(target, ["rev-parse", "--git-common-dir"]).strip())
    if not git_common_dir.is_absolute():
        git_common_dir = (target / git_common_dir).resolve()
    env = {
        "GIT_DIR": str(git_dir),
        "GIT_WORK_TREE": str(worktree),
        "GIT_INDEX_FILE": str(index_file),
        "GIT_OBJECT_DIRECTORY": str(object_directory),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(git_common_dir / "objects"),
    }
    object_directory.mkdir(parents=True, exist_ok=True)
    git(target, ["read-tree", manifest["baseline"]], env=env)
    pathspec = worktree / ".delivery-pathspec"
    write_pathspec(pathspec, rows)
    git(target, ["add", f"--pathspec-from-file={pathspec}", "--pathspec-file-nul"], env=env)
    names = git_bytes(target, ["diff", "--cached", "--name-only", "-z"], env=env)
    actual_names = [x.decode("utf-8") for x in names.split(b"\0") if x]
    expected_names = [row["path"] for row in rows]
    if actual_names != sorted(expected_names):
        die(f"temporary index path set mismatch: {actual_names!r} != {sorted(expected_names)!r}")
    entries = parse_staged_entries(git_bytes(target, ["ls-files", "--stage", "-z"], env=env))
    expected_by_path: dict[str, tuple[str, str]] = {}
    for row in rows:
        blob = git(target, ["hash-object", row["source"]], env=env).strip()
        expected_by_path[row["path"]] = (row["git_mode"], blob)
    changed_entries = {path: entries[path] for path in actual_names}
    if changed_entries != expected_by_path:
        die(f"temporary index blob/mode mismatch: {changed_entries!r} != {expected_by_path!r}")
    check_proc = subprocess.run(
        ["git", "-C", str(target), "diff", "--cached", "--check"],
        env={**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check_proc.returncode or check_proc.stdout or check_proc.stderr:
        die(f"git diff --cached --check failed: {(check_proc.stdout + check_proc.stderr).strip()}")
    tree = git(target, ["write-tree"], env=env).strip()
    return {
        "temporary_index": str(index_file),
        "staged_path_count": len(actual_names),
        "staged_paths": actual_names,
        "tree": tree,
        "cached_diff_check": "passed",
    }


def copy_rows_to_target(target: Path, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        destination = target / row["path"]
        current = target
        for component in PurePosixPath(row["path"]).parts[:-1]:
            current = current / component
            if current.exists() and current.is_symlink():
                die(f"destination parent is a symlink: {current}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.is_symlink():
            die(f"destination is a symlink: {destination}")
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(destination.parent))
        os.close(fd)
        temporary_path = Path(temporary)
        try:
            shutil.copyfile(row["source"], temporary_path)
            os.chmod(temporary_path, 0o755 if row["git_mode"] == "100755" else 0o644)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)


def handoff_for_action(path: Path, manifest_path: Path, manifest: dict[str, Any], action: str) -> dict[str, Any]:
    handoff = load_json(path)
    if handoff.get("status") not in HANDOFF_STATUSES:
        die(f"handoff is not authorized: {handoff.get('status')!r}")
    if handoff.get("manifest_sha256") != sha256_file(manifest_path):
        die("handoff does not bind the exact manifest bytes")
    if handoff.get("target") != manifest.get("target") or handoff.get("baseline") != manifest.get("baseline"):
        die("handoff target/baseline does not bind the manifest")
    actions = handoff.get("authorized_actions")
    if not isinstance(actions, list) or action not in actions:
        die(f"handoff does not authorize action {action!r}")
    return handoff


def build_plan(manifest_path: Path, target: Path, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = target_snapshot(target)
    assert_target_baseline(manifest, snapshot)
    with tempfile.TemporaryDirectory(prefix="lightweight-research-delivery-plan-", dir="/private/tmp") as name:
        worktree = Path(name) / "tree"
        worktree.mkdir()
        archive = subprocess.run(
            ["git", "-C", str(target), "archive", manifest["baseline"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if archive.returncode:
            die(archive.stderr.decode("utf-8", "replace"))
        tar = subprocess.run(["tar", "-x", "-C", str(worktree)], input=archive.stdout, check=False)
        if tar.returncode:
            die("cannot materialize baseline archive for temporary audit")
        for row in rows:
            destination = worktree / row["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(row["source"], destination)
            os.chmod(destination, 0o755 if row["git_mode"] == "100755" else 0o644)
        audit = audit_index(
            target,
            manifest,
            rows,
            worktree=worktree,
            index_file=Path(name) / "index",
            object_directory=Path(name) / "objects",
        )
    return {
        "mode": "read-only-plan",
        "manifest_sha256": sha256_file(manifest_path),
        "target": str(target),
        "baseline": manifest["baseline"],
        "target_snapshot": snapshot,
        "source_files_validated": len(rows),
        "temporary_index_audit": audit,
        "git_mutations": False,
    }


def execute_stage(manifest_path: Path, target: Path, manifest: dict[str, Any], rows: list[dict[str, Any]], handoff_path: Path) -> dict[str, Any]:
    handoff_for_action(handoff_path, manifest_path, manifest, "stage")
    snapshot = target_snapshot(target)
    assert_target_baseline(manifest, snapshot)
    plan = build_plan(manifest_path, target, manifest, rows)
    copy_rows_to_target(target, rows)
    after_copy = target_snapshot(target)
    if after_copy["branch"] != manifest["branch"] or after_copy["head"] != manifest["baseline"]:
        die("target changed while copying; refusing to stage")
    git(target, ["add", "--", *[row["path"] for row in rows]])
    cached = git(target, ["diff", "--cached", "--name-only", "-z"]).encode("utf-8")
    names = [x.decode("utf-8") for x in cached.split(b"\0") if x]
    if names != sorted(row["path"] for row in rows):
        die(f"real index path set mismatch after staging: {names!r}")
    check = subprocess.run(
        ["git", "-C", str(target), "diff", "--cached", "--check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check.returncode or check.stdout or check.stderr:
        die("real git diff --cached --check failed; do not commit")
    return {**plan, "mode": "authorized-stage", "git_mutations": True, "real_index_path_count": len(names)}


def execute_commit(target: Path, manifest_path: Path, manifest: dict[str, Any], handoff_path: Path, message: str) -> dict[str, Any]:
    handoff_for_action(handoff_path, manifest_path, manifest, "commit")
    if not message.strip():
        die("commit message must be non-empty")
    staged = git(target, ["diff", "--cached", "--name-only", "--no-renames"]).splitlines()
    if len(staged) != 32:
        die(f"real index must already contain exactly 32 paths before commit; found {len(staged)}")
    check = subprocess.run(["git", "-C", str(target), "diff", "--cached", "--check"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check.returncode or check.stdout or check.stderr:
        die("cached diff-check failed; commit refused")
    committed = git(target, ["commit", "-m", message]).strip()
    return {"mode": "authorized-commit", "git_mutations": True, "commit_output": committed, "head": git(target, ["rev-parse", "HEAD"]).strip()}


def execute_push(target: Path, manifest_path: Path, manifest: dict[str, Any], handoff_path: Path, remote: str) -> dict[str, Any]:
    handoff_for_action(handoff_path, manifest_path, manifest, "push")
    if git(target, ["status", "--porcelain=v1"]).strip():
        die("push requires a clean worktree")
    branch = git(target, ["branch", "--show-current"]).strip()
    if branch != manifest["branch"]:
        die("push branch changed")
    output = git(target, ["push", remote, branch]).strip()
    return {"mode": "authorized-push", "git_mutations": True, "remote": remote, "branch": branch, "output": output, "head": git(target, ["rev-parse", "HEAD"]).strip()}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--target", type=Path, default=Path(DEFAULT_TARGET))
    parser.add_argument("--action", choices=["plan", *sorted(ALLOWED_ACTIONS)], default="plan")
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--commit-message", default="")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--execute", action="store_true", help="required for any Git mutation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    target = args.target.resolve()
    manifest_path = args.manifest.resolve()
    manifest, rows = validate_manifest(manifest_path, target)
    if args.action == "plan":
        result = build_plan(manifest_path, target, manifest, rows)
    else:
        if not args.execute:
            die(f"{args.action} is mutation-capable; pass --execute and a handoff")
        if args.handoff is None:
            die("mutation-capable actions require --handoff")
        if args.action == "stage":
            result = execute_stage(manifest_path, target, manifest, rows, args.handoff.resolve())
        elif args.action == "commit":
            result = execute_commit(target, manifest_path, manifest, args.handoff.resolve(), args.commit_message)
        else:
            result = execute_push(target, manifest_path, manifest, args.handoff.resolve(), args.remote)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ControllerError as exc:
        print(json.dumps({"ok": False, "status": "DELIVERY_REFUSED", "message": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
