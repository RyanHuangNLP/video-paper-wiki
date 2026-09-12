#!/usr/bin/env python3
"""Build-only external acceptance harness for the CODE foundation candidate.

This script is intentionally inert on import.  When executed it refuses to
run unless ``candidate-r1.json`` names the frozen baseline and exactly the two
allowed product files.  The expected candidate shape is documented here:

``schema`` is ``full-todo.code-proof-foundation-candidate.v1``;
``source_root``, ``baseline_head`` and ``baseline_tree`` equal the freeze;
``freeze`` contains ``path``, ``size_bytes`` and ``sha256`` for the freeze;
``product_paths`` contains exactly the two ``relative_path``/``size_bytes``/
``sha256`` rows; and ``snapshot_sha256`` is SHA-256 of the UTF-8 compact,
sorted-key JSON encoding of ``product_paths`` without a trailing LF.

No build is attempted without that candidate.  The later real run uses only
the frozen tracked tree plus those two candidate files, Hatch through the
specified offline ``uv`` executable, and the specified locked Python 3.12.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

# foundation-r1 -> code-proof-v1 -> full-todo-v1 -> manual-pdf-v1 ->
# verification -> artifacts -> repository root
REPO_ROOT = Path(__file__).resolve().parents[6]
ARTIFACT_ROOT = Path(__file__).resolve().parent
FREEZE_PATH = REPO_ROOT / "docs/ai/packets/full-todo-v1/CODE-PROOF-FOUNDATION-freeze-r1.json"
CANDIDATE_PATH = ARTIFACT_ROOT / "candidate-r1.json"
RESULT_PATH = ARTIFACT_ROOT / "foundation-wheel-build-r1.json"
FREEZE_SHA256 = "69e7073ea4f9ce69fb9f2dac890b253a69344a41c53aa35da6de5915c9fab8cc"
FREEZE_SIZE = 565635
BASELINE_HEAD = "1e3f2a4c27ff83e4ead657c1e609ac9130a5b419"
BASELINE_TREE = "7bd89542a20dcd2fff2c254f20e1620305c7662d"
SOURCE_ROOT = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source")
ALLOWED_PRODUCT_PATHS = (
    "src/video_paper_wiki/code_proof_resources.py",
    "tests/unit/test_code_proof_resources.py",
)
UV = Path("/Users/huangzhanpeng/.hermes/bin/uv")
LOCKED_PY312 = Path("/private/tmp/l4r5.s54ypl35/locked-312/bin/python")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compact_snapshot(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RuntimeError("invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe relative path: {value!r}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object: {path}")
    return value


def load_freeze() -> dict[str, Any]:
    raw = FREEZE_PATH.read_bytes()
    if len(raw) != FREEZE_SIZE or sha256_bytes(raw) != FREEZE_SHA256:
        raise RuntimeError("foundation freeze size/hash mismatch")
    freeze = json.loads(raw)
    if freeze.get("baseline_head") != BASELINE_HEAD or freeze.get("baseline_tree") != BASELINE_TREE:
        raise RuntimeError("foundation baseline pin mismatch")
    if freeze.get("source_root") != str(SOURCE_ROOT):
        raise RuntimeError("foundation source-root pin mismatch")
    if freeze.get("baseline_regular_file_count") != 1376:
        raise RuntimeError("foundation baseline regular-file count mismatch")
    return freeze


def load_candidate(freeze: dict[str, Any]) -> dict[str, Any]:
    if not CANDIDATE_PATH.is_file():
        raise RuntimeError("refusing to execute: root-created candidate-r1.json is absent")
    candidate = _read_json(CANDIDATE_PATH)
    if candidate.get("schema") != "full-todo.code-proof-foundation-candidate.v1":
        raise RuntimeError("candidate schema mismatch")
    if candidate.get("source_root") != str(SOURCE_ROOT):
        raise RuntimeError("candidate source-root mismatch")
    if candidate.get("baseline_head") != BASELINE_HEAD or candidate.get("baseline_tree") != BASELINE_TREE:
        raise RuntimeError("candidate baseline mismatch")
    expected_freeze = {"path": str(FREEZE_PATH), "size_bytes": FREEZE_SIZE, "sha256": FREEZE_SHA256}
    if candidate.get("freeze") != expected_freeze:
        raise RuntimeError("candidate freeze pin mismatch")
    rows = candidate.get("product_paths")
    if not isinstance(rows, list) or len(rows) != 2:
        raise RuntimeError("candidate must contain exactly two product_paths")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"relative_path", "size_bytes", "sha256"}:
            raise RuntimeError("candidate product row shape mismatch")
        rel = _safe_relative(row["relative_path"])
        if not isinstance(row["size_bytes"], int) or row["size_bytes"] < 0:
            raise RuntimeError("candidate product size mismatch")
        if not isinstance(row["sha256"], str) or len(row["sha256"]) != 64:
            raise RuntimeError("candidate product hash mismatch")
        normalized.append({"relative_path": rel, "size_bytes": row["size_bytes"], "sha256": row["sha256"]})
    normalized.sort(key=lambda row: row["relative_path"])
    if tuple(row["relative_path"] for row in normalized) != ALLOWED_PRODUCT_PATHS:
        raise RuntimeError("candidate product path allowlist mismatch")
    if candidate.get("snapshot_encoding") != "SHA256 of UTF8 JSON product_paths with sorted keys, compact separators, no trailing LF":
        raise RuntimeError("candidate snapshot encoding mismatch")
    if candidate.get("snapshot_sha256") != compact_snapshot(normalized):
        raise RuntimeError("candidate snapshot hash mismatch")
    for row in normalized:
        path = SOURCE_ROOT / row["relative_path"]
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"candidate product file missing or non-regular: {path}")
        actual = path.read_bytes()
        if len(actual) != row["size_bytes"] or sha256_bytes(actual) != row["sha256"]:
            raise RuntimeError(f"candidate product bytes mismatch: {path}")
    candidate["product_paths"] = normalized
    return candidate


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def _baseline_rows(freeze: dict[str, Any]) -> list[dict[str, Any]]:
    rows = freeze.get("baseline_tracked_files")
    if not isinstance(rows, list) or len(rows) != 1376:
        raise RuntimeError("baseline manifest row count mismatch")
    normalized = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not {"relative_path", "size_bytes", "sha256"}.issubset(row):
            raise RuntimeError("baseline manifest must use relative_path/size_bytes/sha256")
        if set(row) - {"relative_path", "path", "size_bytes", "sha256"}:
            raise RuntimeError("baseline manifest has unexpected fields")
        rel = _safe_relative(row["relative_path"])
        if rel in seen or not isinstance(row["size_bytes"], int) or row["size_bytes"] < 0:
            raise RuntimeError("baseline manifest row invalid")
        if not isinstance(row["sha256"], str) or len(row["sha256"]) != 64:
            raise RuntimeError("baseline manifest hash invalid")
        seen.add(rel)
        normalized.append({"relative_path": rel, "size_bytes": row["size_bytes"], "sha256": row["sha256"]})
    return sorted(normalized, key=lambda row: row["relative_path"])


def _status_paths() -> list[str]:
    raw = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=SOURCE_ROOT)
    paths = []
    for line in raw.splitlines():
        if not line:
            continue
        if not line.startswith("?? "):
            raise RuntimeError(f"tracked baseline changed: {line}")
        paths.append(line[3:])
    return paths


def manifest_guard(freeze: dict[str, Any], candidate: dict[str, Any]) -> str:
    if _git(["rev-parse", "HEAD"], cwd=SOURCE_ROOT) != BASELINE_HEAD:
        raise RuntimeError("source HEAD changed")
    if _git(["rev-parse", "HEAD^{tree}"], cwd=SOURCE_ROOT) != BASELINE_TREE:
        raise RuntimeError("source tree changed")
    if _git(["diff", "--quiet"], cwd=SOURCE_ROOT) != "":
        raise RuntimeError("source tracked worktree changed")
    if _git(["diff", "--cached", "--quiet"], cwd=SOURCE_ROOT) != "":
        raise RuntimeError("source index changed")
    expected_untracked = sorted(ALLOWED_PRODUCT_PATHS)
    if sorted(_status_paths()) != expected_untracked:
        raise RuntimeError("source has unapproved untracked paths")
    rows = _baseline_rows(freeze)
    actual_paths = set()
    for row in rows:
        rel = row["relative_path"]
        path = SOURCE_ROOT / rel
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"baseline entry is not a regular file: {rel}")
        data = path.read_bytes()
        if len(data) != row["size_bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeError(f"baseline bytes changed: {rel}")
        actual_paths.add(rel)
    indexed = set()
    for record in _git(["ls-files", "-s", "-z"], cwd=SOURCE_ROOT).split("\0"):
        if not record:
            continue
        meta, rel = record.split("\t", 1)
        mode = meta.split()[0]
        if mode != "160000":
            indexed.add(_safe_relative(rel))
    if indexed != actual_paths:
        raise RuntimeError("baseline tracked regular-file set changed")
    return sha256_bytes(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())


def _extract_archive(archive: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=__import__("io").BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
                raise RuntimeError(f"unsafe archive member: {member.name}")
            target = destination / Path(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True)
            elif member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or any(part in {"", ".", ".."} for part in link.parts):
                    raise RuntimeError(f"unsafe archive link: {member.name}")
                target.symlink_to(member.linkname)
            elif member.isfile():
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError(f"archive member unreadable: {member.name}")
                target.write_bytes(source.read())
                os.chmod(target, member.mode & 0o777)
            else:
                raise RuntimeError(f"unsupported archive member: {member.name}")


def make_source_copy(candidate: dict[str, Any]) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="code-proof-foundation-build-", dir="/private/tmp"))
    source_copy = temp_root / "source-copy"
    wheel_dir = temp_root / "wheel-output"
    source_copy.mkdir()
    wheel_dir.mkdir()
    archive = subprocess.check_output(["git", "-C", str(SOURCE_ROOT), "archive", "--format=tar", BASELINE_HEAD])
    _extract_archive(archive, source_copy)
    expected = {row["relative_path"] for row in _baseline_rows(load_freeze())}
    expected.update(ALLOWED_PRODUCT_PATHS)
    for row in candidate["product_paths"]:
        source = SOURCE_ROOT / row["relative_path"]
        target = source_copy / row["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, stat.S_IMODE(source.stat().st_mode))
    actual = set()
    for path in source_copy.rglob("*"):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(source_copy).as_posix()
            if "__pycache__" in PurePosixPath(rel).parts or rel.endswith(".pyc"):
                raise RuntimeError(f"cache entered source copy: {rel}")
            actual.add(rel)
    if actual != expected:
        raise RuntimeError("source copy contains files outside baseline plus candidate paths")
    return temp_root, wheel_dir


def _run_capture(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _refuse_existing(paths: tuple[Path, ...]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise RuntimeError("refusing overwrite of existing evidence: " + ", ".join(existing))


def main() -> int:
    freeze = load_freeze()
    candidate = load_candidate(freeze)
    guard_before = manifest_guard(freeze, candidate)
    stdout_path = ARTIFACT_ROOT / "foundation-wheel-build-r1.stdout.log"
    stderr_path = ARTIFACT_ROOT / "foundation-wheel-build-r1.stderr.log"
    _refuse_existing((RESULT_PATH, stdout_path, stderr_path))
    if not UV.is_file() or not LOCKED_PY312.is_file():
        raise RuntimeError("required uv or locked Python 3.12 is absent")
    uv_version = _run_capture([str(UV), "--version"]).stdout.decode(errors="replace").strip()
    if not uv_version.startswith("uv 0.12.7"):
        raise RuntimeError(f"unexpected uv version: {uv_version}")
    py_version = _run_capture([str(LOCKED_PY312), "-c", "import sys; print(sys.version)"]).stdout.decode(errors="replace").strip()
    if not py_version.startswith("3.12"):
        raise RuntimeError(f"unexpected locked Python: {py_version}")
    temp_root, wheel_dir = make_source_copy(candidate)
    argv = [str(UV), "build", "--wheel", "--offline", "--python", str(LOCKED_PY312), "--out-dir", str(wheel_dir)]
    proc = _run_capture(argv, cwd=temp_root / "source-copy")
    _write_exclusive(stdout_path, proc.stdout)
    _write_exclusive(stderr_path, proc.stderr)
    wheels = sorted(wheel_dir.glob("*.whl")) if proc.returncode == 0 else []
    wheel = wheels[0] if len(wheels) == 1 else None
    guard_after = manifest_guard(freeze, candidate)
    evidence = {
        "schema": "full-todo.code-proof-foundation-wheel-build-evidence.v1",
        "candidate": str(CANDIDATE_PATH),
        "candidate_snapshot_sha256": candidate["snapshot_sha256"],
        "freeze_sha256": FREEZE_SHA256,
        "baseline_head": BASELINE_HEAD,
        "baseline_tree": BASELINE_TREE,
        "manifest_guard_before": guard_before,
        "manifest_guard_after": guard_after,
        "source_copy": str(temp_root / "source-copy"),
        "uv": {"path": str(UV), "version": uv_version},
        "python": {"path": str(LOCKED_PY312), "version": py_version},
        "argv": argv,
        "exit_code": proc.returncode,
        "stdout": {"path": str(stdout_path), "size_bytes": stdout_path.stat().st_size, "sha256": sha256_bytes(proc.stdout)},
        "stderr": {"path": str(stderr_path), "size_bytes": stderr_path.stat().st_size, "sha256": sha256_bytes(proc.stderr)},
        "wheel": None if wheel is None else {"path": str(wheel), "size_bytes": wheel.stat().st_size, "sha256": sha256_bytes(wheel.read_bytes())},
    }
    _write_exclusive(RESULT_PATH, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if proc.returncode != 0 or wheel is None:
        raise RuntimeError("offline wheel build failed; see evidence and raw logs")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
