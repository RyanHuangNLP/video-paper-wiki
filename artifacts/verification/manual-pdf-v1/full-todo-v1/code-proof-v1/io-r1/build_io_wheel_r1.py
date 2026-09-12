#!/usr/bin/env python3
"""Build the future retained-I/O wheel from an exact, pinned source mirror.

The module is inert on import.  A future invocation must provide every
candidate and environment path as an argument.  The candidate JSON shape is:

``schema`` = ``full-todo.code-proof-io-candidate.v1``;
``source_root``, ``baseline_head``, and ``baseline_tree`` equal the I/O freeze;
``freeze`` is ``{path, size_bytes, sha256}``; ``product_paths`` is exactly the
two sorted ``{relative_path, size_bytes, sha256}`` rows for
``src/video_paper_wiki/code_proof_io.py`` and
``tests/unit/test_code_proof_io.py``; ``snapshot_encoding`` is the accepted
compact sorted-key JSON encoding and ``snapshot_sha256`` is its digest;
``foundation_module`` is one ``{relative_path, size_bytes, sha256}`` row for
the accepted ``code_proof_resources.py``; and ``resource_pins`` is the exact
eleven-row ``{relative_path, size_bytes, sha256}`` list from the freeze.

The candidate file itself is also pinned at invocation by the required
``--candidate-size`` and ``--candidate-sha256`` arguments.  No candidate or
wheel pin is invented by this harness.  A later run creates a disposable
baseline archive, overlays only the two candidate files, and invokes offline
uv/Hatch.  It writes evidence only to the explicitly supplied paths.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[6]
ARTIFACT_ROOT = Path(__file__).resolve().parent
FREEZE_RELATIVE = Path("docs/ai/packets/full-todo-v1/CODE-PROOF-IO-freeze-r1.json")
FREEZE_PATH = REPO_ROOT / FREEZE_RELATIVE
FREEZE_SHA256 = "267cd82f8dccb673eb07bdaabddcb4de0c4a38ba6fcd8055474c11e5dca9ad07"
FREEZE_SIZE = 571899
BASELINE_HEAD = "d440c7aaebb4dcc2c52cab719b0d73347a41493f"
BASELINE_TREE = "3dcff27982242ac4edbf0473e4271a91535d1b0f"
BASELINE_REGULAR_FILE_COUNT = 1378
SOURCE_ROOT = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source")
ALLOWED_PRODUCT_PATHS = (
    "src/video_paper_wiki/code_proof_io.py",
    "tests/unit/test_code_proof_io.py",
)
FOUNDATION_MODULE_PATH = "src/video_paper_wiki/code_proof_resources.py"
FOUNDATION_MODULE_SIZE = 29412
FOUNDATION_MODULE_SHA256 = "00ec3d46eb57dc7e902bfcacbae0964934a24af63a86c5c3ddc183e605943ea6"
RECORD_SCHEMA = "full-todo.code-proof-io-wheel-record.v1"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compact_snapshot(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _digest_row(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"relative_path", "size_bytes", "sha256"}:
        raise RuntimeError(f"{label} row shape mismatch")
    rel = _safe_relative(value["relative_path"])
    size = value["size_bytes"]
    digest = value["sha256"]
    if not isinstance(size, int) or size < 0:
        raise RuntimeError(f"{label} size mismatch")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise RuntimeError(f"{label} SHA-256 mismatch")
    return {"relative_path": rel, "size_bytes": size, "sha256": digest}


def load_freeze(path: Path, source_root: Path) -> dict[str, Any]:
    path = path.resolve()
    if path != FREEZE_PATH.resolve():
        raise RuntimeError(f"unexpected freeze path: {path}")
    raw = path.read_bytes()
    if len(raw) != FREEZE_SIZE or sha256_bytes(raw) != FREEZE_SHA256:
        raise RuntimeError("I/O freeze size/hash mismatch")
    freeze = json.loads(raw)
    if not isinstance(freeze, dict) or freeze.get("schema") != "full-todo.code-proof-io-freeze.v1":
        raise RuntimeError("I/O freeze schema mismatch")
    if freeze.get("baseline_head") != BASELINE_HEAD or freeze.get("baseline_tree") != BASELINE_TREE:
        raise RuntimeError("I/O baseline pin mismatch")
    if freeze.get("source_root") != str(source_root):
        raise RuntimeError("I/O source-root pin mismatch")
    if freeze.get("baseline_regular_file_count") != BASELINE_REGULAR_FILE_COUNT:
        raise RuntimeError("I/O baseline regular-file count mismatch")
    rows = freeze.get("baseline_tracked_files")
    if not isinstance(rows, list) or len(rows) != BASELINE_REGULAR_FILE_COUNT:
        raise RuntimeError("I/O baseline manifest count mismatch")
    resource_pins = freeze.get("resource_pins")
    if not isinstance(resource_pins, list) or len(resource_pins) != 11:
        raise RuntimeError("I/O resource pin count mismatch")
    normalized_resources = [_digest_row(row, label="freeze resource") for row in resource_pins]
    if len({row["relative_path"] for row in normalized_resources}) != 11:
        raise RuntimeError("I/O resource pin paths are not unique")
    freeze["resource_pins"] = normalized_resources
    return freeze


def load_candidate(path: Path, freeze: dict[str, Any], source_root: Path, expected_size: int, expected_sha256: str) -> dict[str, Any]:
    path = path.resolve()
    raw = path.read_bytes()
    if len(raw) != expected_size or sha256_bytes(raw) != expected_sha256:
        raise RuntimeError("candidate file size/hash mismatch")
    candidate = json.loads(raw)
    if not isinstance(candidate, dict) or candidate.get("schema") != "full-todo.code-proof-io-candidate.v1":
        raise RuntimeError("I/O candidate schema mismatch")
    if candidate.get("source_root") != str(source_root):
        raise RuntimeError("candidate source-root mismatch")
    if candidate.get("baseline_head") != BASELINE_HEAD or candidate.get("baseline_tree") != BASELINE_TREE:
        raise RuntimeError("candidate baseline mismatch")
    expected_freeze = {"path": str(FREEZE_PATH), "size_bytes": FREEZE_SIZE, "sha256": FREEZE_SHA256}
    if candidate.get("freeze") != expected_freeze:
        raise RuntimeError("candidate freeze pin mismatch")
    rows = candidate.get("product_paths")
    if not isinstance(rows, list) or len(rows) != 2:
        raise RuntimeError("candidate must contain exactly two product_paths")
    normalized = sorted((_digest_row(row, label="candidate product") for row in rows), key=lambda row: row["relative_path"])
    if tuple(row["relative_path"] for row in normalized) != ALLOWED_PRODUCT_PATHS:
        raise RuntimeError("candidate product path allowlist mismatch")
    expected_encoding = "SHA256 of UTF8 JSON product_paths with sorted keys, compact separators, no trailing LF"
    if candidate.get("snapshot_encoding") != expected_encoding or candidate.get("snapshot_sha256") != compact_snapshot(normalized):
        raise RuntimeError("candidate snapshot mismatch")
    foundation = _digest_row(candidate.get("foundation_module"), label="candidate foundation")
    if foundation["relative_path"] != FOUNDATION_MODULE_PATH:
        raise RuntimeError("candidate foundation path mismatch")
    if foundation["size_bytes"] != FOUNDATION_MODULE_SIZE or foundation["sha256"] != FOUNDATION_MODULE_SHA256:
        raise RuntimeError("candidate foundation pin differs from accepted foundation")
    candidate_resources = candidate.get("resource_pins")
    if not isinstance(candidate_resources, list) or len(candidate_resources) != 11:
        raise RuntimeError("candidate resource pin count mismatch")
    candidate_resources = [_digest_row(row, label="candidate resource") for row in candidate_resources]
    if candidate_resources != freeze["resource_pins"]:
        raise RuntimeError("candidate resource pins differ from freeze")
    for row in normalized:
        source = source_root / row["relative_path"]
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"candidate product is missing or non-regular: {source}")
        data = source.read_bytes()
        if len(data) != row["size_bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeError(f"candidate product bytes mismatch: {source}")
    foundation_path = source_root / foundation["relative_path"]
    if foundation_path.is_symlink() or not foundation_path.is_file():
        raise RuntimeError("accepted foundation module is missing or non-regular")
    data = foundation_path.read_bytes()
    if len(data) != foundation["size_bytes"] or sha256_bytes(data) != foundation["sha256"]:
        raise RuntimeError("accepted foundation module bytes mismatch")
    candidate["product_paths"] = normalized
    candidate["foundation_module"] = foundation
    candidate["resource_pins"] = candidate_resources
    candidate["candidate_path"] = str(path)
    candidate["candidate_size_bytes"] = expected_size
    candidate["candidate_sha256"] = expected_sha256
    return candidate


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def _baseline_rows(freeze: dict[str, Any]) -> list[dict[str, Any]]:
    rows = freeze.get("baseline_tracked_files")
    if not isinstance(rows, list) or len(rows) != BASELINE_REGULAR_FILE_COUNT:
        raise RuntimeError("baseline manifest row count mismatch")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"relative_path", "path", "size_bytes", "sha256"}:
            raise RuntimeError("baseline manifest row shape mismatch")
        clean = _digest_row({key: row[key] for key in ("relative_path", "size_bytes", "sha256")}, label="baseline")
        if clean["relative_path"] in seen:
            raise RuntimeError("baseline manifest contains duplicate paths")
        seen.add(clean["relative_path"])
        normalized.append(clean)
    return sorted(normalized, key=lambda row: row["relative_path"])


def _status_paths(source_root: Path) -> list[str]:
    raw = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=source_root)
    paths: list[str] = []
    for line in raw.splitlines():
        if not line:
            continue
        if not line.startswith("?? "):
            raise RuntimeError(f"tracked baseline changed: {line}")
        paths.append(_safe_relative(line[3:]))
    return paths


def manifest_guard(freeze: dict[str, Any], candidate: dict[str, Any], source_root: Path) -> str:
    if _git(["rev-parse", "HEAD"], cwd=source_root) != BASELINE_HEAD:
        raise RuntimeError("source HEAD changed")
    if _git(["rev-parse", "HEAD^{tree}"], cwd=source_root) != BASELINE_TREE:
        raise RuntimeError("source tree changed")
    if _git(["diff", "--quiet"], cwd=source_root) != "":
        raise RuntimeError("source tracked worktree changed")
    if _git(["diff", "--cached", "--quiet"], cwd=source_root) != "":
        raise RuntimeError("source index changed")
    if sorted(_status_paths(source_root)) != sorted(ALLOWED_PRODUCT_PATHS):
        raise RuntimeError("source has unapproved untracked paths")
    actual_paths: set[str] = set()
    for row in _baseline_rows(freeze):
        rel = row["relative_path"]
        path = source_root / rel
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"baseline entry is not a regular file: {rel}")
        data = path.read_bytes()
        if len(data) != row["size_bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeError(f"baseline bytes changed: {rel}")
        actual_paths.add(rel)
    indexed: set[str] = set()
    for record in _git(["ls-files", "-s", "-z"], cwd=source_root).split("\0"):
        if not record:
            continue
        meta, rel = record.split("\t", 1)
        if meta.split()[0] != "160000":
            indexed.add(_safe_relative(rel))
    if indexed != actual_paths:
        raise RuntimeError("baseline tracked regular-file set changed")
    for row in candidate["product_paths"]:
        path = source_root / row["relative_path"]
        data = path.read_bytes()
        if len(data) != row["size_bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeError(f"candidate bytes changed: {row['relative_path']}")
    return sha256_bytes(json.dumps(_baseline_rows(freeze), sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _extract_archive(archive: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
                raise RuntimeError(f"unsafe archive member: {member.name}")
            target = destination / Path(*rel.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError(f"archive member unreadable: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
                os.chmod(target, member.mode & 0o777)
            else:
                raise RuntimeError(f"unsupported archive member: {member.name}")


def make_source_copy(candidate: dict[str, Any], freeze: dict[str, Any], source_root: Path) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="code-proof-io-build-", dir="/private/tmp"))
    source_copy = temp_root / "source-copy"
    wheel_dir = temp_root / "wheel-output"
    source_copy.mkdir()
    wheel_dir.mkdir()
    archive = subprocess.check_output(["git", "-C", str(source_root), "archive", "--format=tar", BASELINE_HEAD])
    _extract_archive(archive, source_copy)
    expected = {row["relative_path"] for row in _baseline_rows(freeze)} | set(ALLOWED_PRODUCT_PATHS)
    for row in candidate["product_paths"]:
        source = source_root / row["relative_path"]
        target = source_copy / row["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, stat.S_IMODE(source.stat().st_mode))
    actual = {
        path.relative_to(source_copy).as_posix()
        for path in source_copy.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if any("__pycache__" in PurePosixPath(rel).parts or rel.endswith(".pyc") for rel in actual):
        raise RuntimeError("cache entered source copy")
    if actual != expected:
        raise RuntimeError("source copy contains files outside baseline plus candidate paths")
    return temp_root, wheel_dir


def _record_from_wheel(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        records = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise RuntimeError("wheel must contain exactly one RECORD")
        data = archive.read(records[0])
    return {"member": records[0], "size_bytes": len(data), "sha256": sha256_bytes(data)}


def _run_capture(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _require_absent(paths: list[Path]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise RuntimeError("refusing overwrite of existing path(s): " + ", ".join(existing))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-size", type=int, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python312", type=Path, required=True)
    parser.add_argument("--wheel-output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--stdout-log", type=Path, required=True)
    parser.add_argument("--stderr-log", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_root = args.source_root.resolve()
    freeze = load_freeze(args.freeze, source_root)
    candidate = load_candidate(args.candidate, freeze, source_root, args.candidate_size, args.candidate_sha256)
    guard_before = manifest_guard(freeze, candidate, source_root)
    _require_absent([args.evidence, args.stdout_log, args.stderr_log])
    if not args.uv.is_file() or not args.python312.is_file():
        raise RuntimeError("required uv or locked Python 3.12 is absent")
    args.wheel_output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.wheel_output_dir.glob("*.whl")):
        raise RuntimeError("wheel output directory already contains a wheel")
    uv_version = _run_capture([str(args.uv), "--version"]).stdout.decode(errors="replace").strip()
    if not uv_version.startswith("uv 0.12.7"):
        raise RuntimeError(f"unexpected uv version: {uv_version}")
    py_version = _run_capture([str(args.python312), "-c", "import sys; print(sys.version)"]).stdout.decode(errors="replace").strip()
    if not py_version.startswith("3.12"):
        raise RuntimeError(f"unexpected locked Python: {py_version}")
    temp_root, wheel_dir = make_source_copy(candidate, freeze, source_root)
    argv_build = [str(args.uv), "build", "--wheel", "--offline", "--python", str(args.python312), "--out-dir", str(args.wheel_output_dir)]
    proc = _run_capture(argv_build, cwd=temp_root / "source-copy")
    _write_exclusive(args.stdout_log, proc.stdout)
    _write_exclusive(args.stderr_log, proc.stderr)
    wheels = sorted(args.wheel_output_dir.glob("*.whl")) if proc.returncode == 0 else []
    wheel = wheels[0] if len(wheels) == 1 else None
    guard_after = manifest_guard(freeze, candidate, source_root)
    wheel_record = None if wheel is None else {
        "path": str(wheel.resolve()),
        "size_bytes": wheel.stat().st_size,
        "sha256": sha256_bytes(wheel.read_bytes()),
        "record": _record_from_wheel(wheel),
    }
    evidence = {
        "schema": "full-todo.code-proof-io-wheel-build-evidence.v1",
        "candidate": {"path": str(args.candidate.resolve()), "size_bytes": args.candidate_size, "sha256": args.candidate_sha256},
        "candidate_snapshot_sha256": candidate["snapshot_sha256"],
        "freeze": {"path": str(args.freeze.resolve()), "size_bytes": FREEZE_SIZE, "sha256": FREEZE_SHA256},
        "baseline_head": BASELINE_HEAD,
        "baseline_tree": BASELINE_TREE,
        "manifest_guard_before": guard_before,
        "manifest_guard_after": guard_after,
        "source_copy": str((temp_root / "source-copy").resolve()),
        "uv": {"path": str(args.uv.resolve()), "version": uv_version},
        "python": {"path": str(args.python312.resolve()), "version": py_version},
        "argv": argv_build,
        "exit_code": proc.returncode,
        "stdout": {"path": str(args.stdout_log.resolve()), "size_bytes": len(proc.stdout), "sha256": sha256_bytes(proc.stdout)},
        "stderr": {"path": str(args.stderr_log.resolve()), "size_bytes": len(proc.stderr), "sha256": sha256_bytes(proc.stderr)},
        "wheel": wheel_record,
    }
    _write_exclusive(args.evidence, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if proc.returncode != 0 or wheel is None:
        raise RuntimeError("offline wheel build failed; see evidence and raw logs")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
