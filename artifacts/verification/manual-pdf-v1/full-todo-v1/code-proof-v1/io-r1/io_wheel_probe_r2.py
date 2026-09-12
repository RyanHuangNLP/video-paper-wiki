#!/usr/bin/env python3
"""Probe an explicitly pinned retained-I/O wheel in both locked runtimes.

This module is inert on import.  The future probe requires a candidate JSON
and a wheel-record JSON.  The latter has this exact shape::

    {
      "schema": "full-todo.code-proof-io-wheel-record.v1",
      "candidate": {"path": "...", "size_bytes": 0, "sha256": "..."},
      "freeze": {"path": "...", "size_bytes": 0, "sha256": "..."},
      "wheel": {"path": "...", "size_bytes": 0, "sha256": "..."},
      "record": {"member": "...dist-info/RECORD", "size_bytes": 0, "sha256": "..."}
    }

The candidate and wheel-record files are themselves pinned by required
``--candidate-size/--candidate-sha256`` and
``--wheel-record-size/--wheel-record-sha256`` arguments.  No wheel or result
pin is fabricated here.  Each runtime gets a fresh offline target and empty
CWD.  The child checks installed origins, exact I/O/foundation/resource bytes,
then exercises a fresh install and byte-identical reuse through the sole
``code_proof_io._getcwd`` seam.  It never patches the foundation module's
``__file__``.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build_io_wheel_r2 import (  # noqa: E402
    ALLOWED_PRODUCT_PATHS,
    FOUNDATION_MODULE_PATH,
    FREEZE_PATH,
    FREEZE_SHA256,
    FREEZE_SIZE,
    RECORD_SCHEMA,
    _read_json,
    _safe_relative,
    load_candidate,
    load_freeze,
    manifest_guard,
    sha256_bytes,
)


HARD_OUTPUT_LIMITS = {
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_bundle_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}


def _digest_row(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"relative_path", "size_bytes", "sha256"}:
        raise RuntimeError(f"{label} row shape mismatch")
    rel = _safe_relative(value["relative_path"])
    size = value["size_bytes"]
    digest = value["sha256"]
    if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"{label} digest row mismatch")
    return {"relative_path": rel, "size_bytes": size, "sha256": digest}


def _path_record(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "size_bytes", "sha256"}:
        raise RuntimeError(f"{label} record shape mismatch")
    path = value["path"]
    if not isinstance(path, str) or not os.path.isabs(path):
        raise RuntimeError(f"{label} path must be absolute")
    size = value["size_bytes"]
    digest = value["sha256"]
    if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"{label} digest mismatch")
    return {"path": path, "size_bytes": size, "sha256": digest}


def load_wheel_record(path: Path, *, expected_candidate: dict[str, Any], expected_freeze: dict[str, Any], expected_size: int, expected_sha256: str) -> dict[str, Any]:
    raw = path.resolve().read_bytes()
    if len(raw) != expected_size or sha256_bytes(raw) != expected_sha256:
        raise RuntimeError("wheel-record file size/hash mismatch")
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("schema") != RECORD_SCHEMA:
        raise RuntimeError("wheel-record schema mismatch")
    expected_candidate_record = {
        "path": str(Path(expected_candidate["candidate_path"]).resolve()),
        "size_bytes": expected_candidate["candidate_size_bytes"],
        "sha256": expected_candidate["candidate_sha256"],
    }
    if record.get("candidate") != expected_candidate_record:
        raise RuntimeError("wheel-record candidate pin mismatch")
    if record.get("freeze") != expected_freeze:
        raise RuntimeError("wheel-record freeze pin mismatch")
    wheel = _path_record(record.get("wheel"), label="wheel")
    wheel_path = Path(wheel["path"])
    wheel_bytes = wheel_path.read_bytes()
    if len(wheel_bytes) != wheel["size_bytes"] or sha256_bytes(wheel_bytes) != wheel["sha256"]:
        raise RuntimeError("wheel size/hash mismatch")
    rec = record.get("record")
    if not isinstance(rec, dict) or set(rec) != {"member", "size_bytes", "sha256"}:
        raise RuntimeError("wheel RECORD pin shape mismatch")
    member = rec["member"]
    if not isinstance(member, str) or not member.endswith(".dist-info/RECORD"):
        raise RuntimeError("wheel RECORD member mismatch")
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
        names = archive.namelist()
        if names.count(member) != 1:
            raise RuntimeError("wheel RECORD member missing or duplicated")
        record_bytes = archive.read(member)
    if len(record_bytes) != rec["size_bytes"] or sha256_bytes(record_bytes) != rec["sha256"]:
        raise RuntimeError("wheel RECORD size/hash mismatch")
    return {"path": path.resolve(), "wheel": wheel, "record": rec, "wheel_record_bytes": record_bytes}


def _zip_member_path(relative_path: str) -> str:
    if relative_path.startswith("src/video_paper_wiki/"):
        return "video_paper_wiki/" + relative_path[len("src/video_paper_wiki/"):]
    if relative_path.startswith("schemas/"):
        return "video_paper_wiki/" + relative_path
    raise RuntimeError(f"unexpected frozen resource path: {relative_path}")


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def inspect_wheel(wheel: Path, candidate: dict[str, Any], freeze: dict[str, Any], record_pin: dict[str, Any], source_root: Path) -> dict[str, Any]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise RuntimeError("wheel contains duplicate members")
        if record_pin["member"] not in names:
            raise RuntimeError("pinned RECORD member is absent")
        record_bytes = archive.read(record_pin["member"])
        if len(record_bytes) != record_pin["size_bytes"] or sha256_bytes(record_bytes) != record_pin["sha256"]:
            raise RuntimeError("wheel RECORD changed")
        rows = list(csv.reader(io.StringIO(record_bytes.decode("utf-8"))))
        row_map: dict[str, list[str]] = {}
        for row in rows:
            if len(row) != 3:
                raise RuntimeError("wheel RECORD row shape mismatch")
            member, digest, size = row
            if member in row_map:
                raise RuntimeError("wheel RECORD duplicate row")
            row_map[member] = row
            if member == record_pin["member"]:
                if digest or size:
                    raise RuntimeError("RECORD row must have empty self digest and size")
                continue
            if member not in names:
                raise RuntimeError(f"RECORD names missing wheel member: {member}")
            data = archive.read(member)
            if digest != _record_hash(data) or size != str(len(data)):
                raise RuntimeError(f"RECORD digest/size mismatch: {member}")
        for member in names:
            info = archive.getinfo(member)
            if not info.is_dir() and member not in row_map:
                raise RuntimeError(f"wheel file missing RECORD row: {member}")
        expected_files: dict[str, bytes] = {}
        for row in candidate["product_paths"]:
            if row["relative_path"] == "src/video_paper_wiki/code_proof_io.py":
                expected_files["video_paper_wiki/code_proof_io.py"] = (source_root / row["relative_path"]).read_bytes()
        foundation = candidate["foundation_module"]
        expected_files["video_paper_wiki/code_proof_resources.py"] = (source_root / foundation["relative_path"]).read_bytes()
        for row in freeze["resource_pins"]:
            expected_files[_zip_member_path(row["relative_path"])] = (source_root / row["relative_path"]).read_bytes()
        for member, expected in expected_files.items():
            if member not in names or archive.read(member) != expected:
                raise RuntimeError(f"wheel bytes mismatch: {member}")
        if "tests/unit/test_code_proof_io.py" in names:
            raise RuntimeError("unit test must remain candidate/source evidence, not a wheel member")
    return {"record_member": record_pin["member"], "record_rows": len(rows), "byte_exact_members": len(expected_files)}


CHILD_SOURCE = r'''
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile


HARD_OUTPUT_LIMITS = {
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_bundle_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(path, root):
    path = os.path.normpath(os.path.abspath(path))
    root = os.path.normpath(os.path.abspath(root))
    return path == root or path.startswith(root + os.sep)


def main():
    if len(sys.argv) != 7:
        raise AssertionError("wheel child requires install, source, candidate, freeze, wheel and repo-root")
    install_target, source_root, candidate_path, freeze_path, wheel_path, repo_root = map(os.path.abspath, sys.argv[1:])
    cwd_before = os.getcwd()
    candidate = json.loads(open(candidate_path, "rb").read().decode("utf-8"))
    freeze = json.loads(open(freeze_path, "rb").read().decode("utf-8"))
    product_row = next(row for row in candidate["product_paths"] if row["relative_path"] == "src/video_paper_wiki/code_proof_io.py")
    io_source = open(os.path.join(source_root, product_row["relative_path"]), "rb").read()
    foundation_row = candidate["foundation_module"]
    foundation_source = open(os.path.join(source_root, foundation_row["relative_path"]), "rb").read()
    resource_bytes = {}
    for row in freeze["resource_pins"]:
        source_rel = row["relative_path"]
        resource_bytes[source_rel] = open(os.path.join(source_root, source_rel), "rb").read()
    # Block project/source/build/editable entries while retaining the locked
    # interpreter's dependency site-packages (which may live under repo_root,
    # especially the .venv bridge used by Python 3.13).
    forbidden_exact = {
        os.path.normpath(path)
        for path in {
            source_root,
            os.path.join(source_root, "src"),
            os.path.join(repo_root, "src"),
            repo_root,
            os.path.dirname(wheel_path),
            os.path.dirname(os.path.dirname(wheel_path)),
            os.path.join(repo_root, "build"),
            os.path.join(repo_root, "dist"),
        }
    }
    forbidden_prefixes = [
        os.path.normpath(source_root),
        os.path.normpath(os.path.join(source_root, "src")),
        os.path.normpath(os.path.join(repo_root, "src")),
        os.path.normpath(os.path.dirname(wheel_path)),
        os.path.normpath(os.path.dirname(os.path.dirname(wheel_path))),
        os.path.normpath(os.path.join(repo_root, "build")),
        os.path.normpath(os.path.join(repo_root, "dist")),
    ]
    def is_forbidden(path):
        path = os.path.normpath(os.path.abspath(path or cwd_before))
        return path in forbidden_exact or any(path.startswith(item + os.sep) for item in forbidden_prefixes)
    before = list(sys.path)
    retained = [raw for raw in before if not is_forbidden(raw)]
    sys.path[:] = retained
    sys.path.insert(0, install_target)
    if any(is_forbidden(raw) for raw in sys.path):
        raise AssertionError("source/editable path remained in sys.path")
    import video_paper_wiki
    import video_paper_wiki.code_proof_io as io_module
    import video_paper_wiki.code_proof_resources as resources
    package_root = os.path.dirname(os.path.abspath(video_paper_wiki.__file__))
    io_origin = os.path.abspath(io_module.__file__)
    foundation_origin = os.path.abspath(resources.__file__)
    if not inside(package_root, install_target) or not inside(io_origin, install_target) or not inside(foundation_origin, install_target):
        raise AssertionError("package/module origin escaped install target")
    if os.path.basename(os.path.dirname(foundation_origin)) == "src":
        raise AssertionError("foundation origin is named src")
    package_resource_root = package_root
    installed_io = open(io_origin, "rb").read()
    if installed_io != io_source:
        raise AssertionError("installed code_proof_io.py differs from candidate")
    if open(foundation_origin, "rb").read() != foundation_source:
        raise AssertionError("installed foundation module differs from accepted pin")
    installed_paths = []
    for row in freeze["resource_pins"]:
        rel = row["relative_path"]
        if rel.startswith("schemas/"):
            installed_rel = os.path.join("schemas", rel[len("schemas/"):])
        elif rel == "src/video_paper_wiki/profiles/code-proof-v1.json":
            installed_rel = os.path.join("profiles", "code-proof-v1.json")
        else:
            raise AssertionError("unexpected resource pin")
        target = os.path.join(package_resource_root, installed_rel)
        data = open(target, "rb").read()
        if data != resource_bytes[rel] or len(data) != row["size_bytes"] or digest(data) != row["sha256"]:
            raise AssertionError("installed resource pin mismatch")
        installed_paths.append(os.path.abspath(target))
    plan = resources.resource_origin_plan()
    if getattr(plan, "layout", None) != "installed":
        raise AssertionError("resource origin plan did not select installed layout")
    for attr in ("package_directory", "schemas_directory", "profiles_directory"):
        value = os.path.abspath(str(getattr(plan, attr)))
        if not inside(value, install_target):
            raise AssertionError("resource origin escaped install target")
    if len(getattr(plan, "resources", ())) != 11:
        raise AssertionError("resource plan did not retain eleven resources")
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="code-proof-io-wheel-session-", dir="/private/tmp"))
    (scratch / ".git").mkdir()
    (scratch / "pyproject.toml").write_bytes(b'[project]\nname = "video-paper-wiki"\nversion = "0"\n')
    original_getcwd = io_module._getcwd
    io_module._getcwd = lambda: str(scratch)
    first_result = None
    second_result = None
    try:
        with io_module.open_code_session(batch_id="wheelProbe") as session:
            session.set_output_limits(dict(HARD_OUTPUT_LIMITS))
            first_result = session.install("request.json", b"{}\n")
            session.verify()
        with io_module.open_code_session(batch_id="wheelProbe") as session:
            session.set_output_limits(dict(HARD_OUTPUT_LIMITS))
            second_result = session.install("request.json", b"{}\n")
            session.verify()
    finally:
        io_module._getcwd = original_getcwd
    if first_result is not False or second_result is not True:
        raise AssertionError("fresh install/reuse disposition mismatch")
    imported_origins = {}
    for name, module in sorted(sys.modules.items()):
        if name == "video_paper_wiki" or name.startswith("video_paper_wiki."):
            origin = getattr(module, "__file__", None)
            if not isinstance(origin, str) or not inside(origin, install_target):
                raise AssertionError("an imported video_paper_wiki module escaped the wheel target")
            imported_origins[name] = os.path.abspath(origin)
    if not imported_origins:
        raise AssertionError("no video_paper_wiki origins recorded")
    return {
        "cwd": cwd_before,
        "package_origin": os.path.abspath(video_paper_wiki.__file__),
        "io_origin": io_origin,
        "foundation_origin": foundation_origin,
        "installed_resources": installed_paths,
        "resource_layout": getattr(plan, "layout", None),
        "resource_comparisons": len(installed_paths),
        "imported_module_origins": imported_origins,
        "fresh_install": first_result,
        "reuse_install": second_result,
        "scratch_checkout": str(scratch),
        "only_io_getcwd_patch": True,
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
'''


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-size", type=int, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--wheel-record", type=Path, required=True)
    parser.add_argument("--wheel-record-size", type=int, required=True)
    parser.add_argument("--wheel-record-sha256", required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python312", type=Path, required=True)
    parser.add_argument("--python313", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--runtime-output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args(argv)


def _run(argv: list[str], *, cwd: Path, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _file_ref(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size_bytes": len(data), "sha256": sha256_bytes(data)}


def _execution_record(path: Path, record: dict[str, Any]) -> None:
    _write_exclusive(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_root = args.source_root.resolve()
    freeze = load_freeze(args.freeze, source_root)
    candidate = load_candidate(args.candidate, freeze, source_root, args.candidate_size, args.candidate_sha256)
    expected_candidate = {
        "candidate_path": str(args.candidate.resolve()),
        "candidate_size_bytes": args.candidate_size,
        "candidate_sha256": args.candidate_sha256,
    }
    expected_freeze = {"path": str(args.freeze.resolve()), "size_bytes": FREEZE_SIZE, "sha256": FREEZE_SHA256}
    wheel_record = load_wheel_record(
        args.wheel_record,
        expected_candidate=expected_candidate,
        expected_freeze=expected_freeze,
        expected_size=args.wheel_record_size,
        expected_sha256=args.wheel_record_sha256,
    )
    wheel = Path(wheel_record["wheel"]["path"])
    wheel_inspection = inspect_wheel(wheel, candidate, freeze, wheel_record["record"], source_root)
    if not args.uv.is_file() or not args.python312.is_file() or not args.python313.is_file():
        raise RuntimeError("required uv or locked Python runtime is absent")
    guard_before = manifest_guard(freeze, candidate, source_root)
    runtime_output_dir = args.runtime_output_dir.resolve()
    expected_runtime_paths = [
        runtime_output_dir / f"{name}-{kind}"
        for name in ("py312", "py313")
        for kind in ("install.stdout.log", "install.stderr.log", "probe.stdout.log", "probe.stderr.log", "execution.json")
    ]
    existing = [str(path) for path in [args.evidence.resolve(), runtime_output_dir, *expected_runtime_paths] if path.exists()]
    if existing:
        raise RuntimeError("refusing overwrite of evidence or runtime logs: " + ", ".join(existing))
    runtime_output_dir.mkdir(parents=True)
    child_bytes = CHILD_SOURCE.encode("utf-8")
    runner_path = Path(__file__).resolve()
    runner_bytes = runner_path.read_bytes()
    run_records: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, runtime in (("py312", args.python312), ("py313", args.python313)):
        temp_root = Path(tempfile.mkdtemp(prefix=f"code-proof-io-wheel-{name}-", dir="/private/tmp"))
        target = temp_root / "installed"
        cwd = temp_root / "empty-cwd"
        target.mkdir()
        cwd.mkdir()
        install_argv = [str(args.uv), "pip", "install", "--offline", "--no-deps", "--python", str(runtime), "--target", str(target), str(wheel)]
        record: dict[str, Any] = {
            "name": name,
            "runtime": str(runtime.resolve()),
            "target": str(target),
            "cwd": str(cwd),
            "status": "failed",
            "install": {"argv": install_argv},
        }
        install_stdout = b""
        install_stderr = b""
        probe_stdout = b""
        probe_stderr = b""
        try:
            install = _run(install_argv, cwd=cwd)
            install_stdout, install_stderr = install.stdout, install.stderr
            record["install"].update({
                "exit_code": install.returncode,
                "stdout": _file_ref(runtime_output_dir / f"{name}-install.stdout.log", install_stdout),
                "stderr": _file_ref(runtime_output_dir / f"{name}-install.stderr.log", install_stderr),
            })
            _write_exclusive(runtime_output_dir / f"{name}-install.stdout.log", install_stdout)
            _write_exclusive(runtime_output_dir / f"{name}-install.stderr.log", install_stderr)
            if install.returncode != 0:
                raise RuntimeError(f"offline wheel install failed: {install.stderr.decode(errors='replace')}")
            child_argv = [str(runtime), "-I", "-B", "-", str(target), str(source_root), str(args.candidate.resolve()), str(args.freeze.resolve()), str(wheel.resolve()), str(args.repo_root.resolve())]
            child = _run(child_argv, cwd=cwd, input_bytes=child_bytes)
            probe_stdout, probe_stderr = child.stdout, child.stderr
            record["probe"] = {
                "argv": child_argv,
                "exit_code": child.returncode,
                "stdin": {"size_bytes": len(child_bytes), "sha256": sha256_bytes(child_bytes)},
                "stdout": _file_ref(runtime_output_dir / f"{name}-probe.stdout.log", probe_stdout),
                "stderr": _file_ref(runtime_output_dir / f"{name}-probe.stderr.log", probe_stderr),
            }
            _write_exclusive(runtime_output_dir / f"{name}-probe.stdout.log", probe_stdout)
            _write_exclusive(runtime_output_dir / f"{name}-probe.stderr.log", probe_stderr)
            if child.returncode != 0:
                raise RuntimeError(f"installed wheel probe failed: {child.stderr.decode(errors='replace')}")
            record["result"] = json.loads(child.stdout.decode("utf-8"))
            record["status"] = "passed"
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            failures.append(f"{name}: {exc}")
            if "stdout" not in record["install"]:
                _write_exclusive(runtime_output_dir / f"{name}-install.stdout.log", install_stdout)
                _write_exclusive(runtime_output_dir / f"{name}-install.stderr.log", install_stderr)
                record["install"].update({
                    "exit_code": None,
                    "stdout": _file_ref(runtime_output_dir / f"{name}-install.stdout.log", install_stdout),
                    "stderr": _file_ref(runtime_output_dir / f"{name}-install.stderr.log", install_stderr),
                })
            if not (runtime_output_dir / f"{name}-probe.stdout.log").exists():
                _write_exclusive(runtime_output_dir / f"{name}-probe.stdout.log", probe_stdout)
                _write_exclusive(runtime_output_dir / f"{name}-probe.stderr.log", probe_stderr)
                record["probe"] = {
                    "argv": record.get("probe", {}).get("argv"),
                    "exit_code": None,
                    "stdin": {"size_bytes": len(child_bytes), "sha256": sha256_bytes(child_bytes)},
                    "stdout": _file_ref(runtime_output_dir / f"{name}-probe.stdout.log", probe_stdout),
                    "stderr": _file_ref(runtime_output_dir / f"{name}-probe.stderr.log", probe_stderr),
                }
        execution_path = runtime_output_dir / f"{name}-execution.json"
        record["execution_record"] = str(execution_path.resolve())
        _execution_record(execution_path, record)
        run_records.append(record)
    post_errors: list[str] = []
    guard_after = None
    candidate_after = None
    wheel_record_after = None
    wheel_inspection_after = None
    try:
        guard_after = manifest_guard(freeze, candidate, source_root)
        candidate_after = load_candidate(args.candidate, freeze, source_root, args.candidate_size, args.candidate_sha256)
        wheel_record_after = load_wheel_record(
            args.wheel_record,
            expected_candidate=expected_candidate,
            expected_freeze=expected_freeze,
            expected_size=args.wheel_record_size,
            expected_sha256=args.wheel_record_sha256,
        )
        if wheel_record_after["wheel"] != wheel_record["wheel"] or wheel_record_after["record"] != wheel_record["record"]:
            raise RuntimeError("wheel or RECORD pin changed during runtime probes")
        wheel_inspection_after = inspect_wheel(wheel, candidate_after, freeze, wheel_record_after["record"], source_root)
    except Exception as exc:
        post_errors.append(f"post-run revalidation: {exc}")
        failures.extend(post_errors)
    evidence = {
        "schema": "full-todo.code-proof-io-wheel-probe-evidence-r2.v1",
        "candidate": {"path": str(args.candidate.resolve()), "size_bytes": args.candidate_size, "sha256": args.candidate_sha256, "snapshot_sha256": candidate["snapshot_sha256"]},
        "freeze": expected_freeze,
        "wheel_record": {"path": str(args.wheel_record.resolve()), "size_bytes": args.wheel_record_size, "sha256": args.wheel_record_sha256},
        "wheel": wheel_record["wheel"],
        "wheel_inspection": wheel_inspection,
        "manifest_guard_before": guard_before,
        "manifest_guard_after": guard_after,
        "child_source": {"size_bytes": len(child_bytes), "sha256": sha256_bytes(child_bytes)},
        "runner": {"path": str(runner_path), "size_bytes": len(runner_bytes), "sha256": sha256_bytes(runner_bytes)},
        "runtime_output_dir": str(runtime_output_dir),
        "runs": run_records,
        "failures": failures,
        "post_run_wheel_inspection": wheel_inspection_after,
    }
    _write_exclusive(args.evidence, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    if failures:
        raise RuntimeError("one or more bounded runtime checks failed: " + " | ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
