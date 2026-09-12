#!/usr/bin/env python3
"""External installed-wheel acceptance harness for the CODE foundation.

The candidate guard is deliberately shared with the build harness.  The
expected ``candidate-r1.json`` shape and the frozen baseline pins are defined
in ``build_foundation_wheel_r1.py``.  This script does not run until that
root-created candidate exists and matches exactly two product paths.

The real run installs one freshly built wheel into two empty targets with
offline ``uv pip install --no-deps``, then invokes each locked interpreter as
``-I -B -`` from an empty directory.  The child probe reads all explicit
inputs before replacing filesystem/network/subprocess operations with refusal
stubs; the production foundation methods must then remain pure.
"""
from __future__ import annotations

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

from build_foundation_wheel_r1 import (  # noqa: E402
    ALLOWED_PRODUCT_PATHS,
    ARTIFACT_ROOT,
    CANDIDATE_PATH,
    FREEZE_PATH,
    FREEZE_SHA256,
    LOCKED_PY312,
    REPO_ROOT,
    SOURCE_ROOT,
    UV,
    _read_json,
    _safe_relative,
    _status_paths,
    _baseline_rows,
    compact_snapshot,
    load_candidate,
    load_freeze,
    manifest_guard,
    sha256_bytes,
)

PY313 = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python")
RESULT_PATH = ARTIFACT_ROOT / "foundation-wheel-probe-r1.json"
BUILD_RESULT_PATH = ARTIFACT_ROOT / "foundation-wheel-build-r1.json"
CHILD_SOURCE = r'''
from __future__ import annotations

import base64
import builtins
import copy
import hashlib
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
from pathlib import PurePosixPath


def fail(*args, **kwargs):
    raise AssertionError("CODE foundation probe observed forbidden I/O or process activity")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(path, root):
    path = os.path.normpath(path)
    root = os.path.normpath(root)
    if not os.path.isabs(path) or not os.path.isabs(root):
        return False
    return path == root or path.startswith(root + os.sep)


def safe_rel(value):
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise AssertionError("wheel path escapes its root")
    return value


def expect_limits_error(ctx, value):
    try:
        ctx.materialize_limits(value)
    except Exception as exc:
        if type(exc).__name__ != "CodeProofStructureError" or getattr(exc, "reason", None) != "limits":
            raise AssertionError("wrong limit-boundary error") from exc
        return
    raise AssertionError("invalid limits unexpectedly accepted")


def main():
    if len(sys.argv) != 9:
        raise AssertionError("probe requires install, source, candidate, freeze, fixture, wheel, source-copy and repo-root")
    install_target, source_root, candidate_path, freeze_path, fixture_path, wheel_path, source_copy, repo_root = map(os.path.abspath, sys.argv[1:])
    cwd_before = os.getcwd()
    known_temp_source = "/private/tmp/cr1.lQxPNM/source"
    candidate = json.loads(open(candidate_path, "rb").read().decode("utf-8"))
    freeze = json.loads(open(freeze_path, "rb").read().decode("utf-8"))
    rows = freeze["baseline_tracked_files"]
    schema_rows = [row for row in rows if row["relative_path"].startswith("schemas/") and row["relative_path"].endswith(".json")]
    if len(schema_rows) != 81:
        raise AssertionError("expected 81 frozen schemas")
    source_schema_bytes = {}
    for row in schema_rows:
        rel = row["relative_path"]
        data = open(os.path.join(source_root, rel), "rb").read()
        if len(data) != row["size_bytes"] or digest(data) != row["sha256"]:
            raise AssertionError("source schema baseline changed")
        source_schema_bytes[rel] = data
    fixture = json.loads(open(fixture_path, "rb").read().decode("utf-8"))
    if len(fixture["cases"]) != 264:
        raise AssertionError("expected 264 fixture cases")
    package_root = os.path.join(install_target, "video_paper_wiki")
    installed_schema_bytes = {}
    installed_schema_dir = os.path.join(package_root, "schemas")
    for rel, source_data in source_schema_bytes.items():
        name = rel[len("schemas/"):]
        target = os.path.join(installed_schema_dir, name)
        data = open(target, "rb").read()
        if data != source_data:
            raise AssertionError("installed schema bytes differ")
        installed_schema_bytes[rel] = data
    if {name for name in os.listdir(installed_schema_dir) if name.endswith(".json")} != {rel[len("schemas/"):] for rel in source_schema_bytes}:
        raise AssertionError("installed schema set differs")
    resource_pins = [
        row for row in candidate["resource_pins"]
    ] if isinstance(candidate.get("resource_pins"), list) else None
    if resource_pins is None:
        resource_pins = json.loads(open(freeze_path, "rb").read().decode("utf-8"))["resource_pins"]
    if len(resource_pins) != 11:
        raise AssertionError("expected eleven resource pins")
    retained = {}
    for row in resource_pins:
        rel = row["relative_path"]
        if rel.startswith("schemas/"):
            installed_rel = os.path.join("schemas", rel[len("schemas/"):])
        elif rel == "src/video_paper_wiki/profiles/code-proof-v1.json":
            installed_rel = os.path.join("profiles", "code-proof-v1.json")
        else:
            raise AssertionError("unexpected resource pin")
        data = open(os.path.join(package_root, installed_rel), "rb").read()
        if len(data) != row["size_bytes"] or digest(data) != row["sha256"]:
            raise AssertionError("installed resource pin mismatch")
        retained[installed_rel.replace(os.sep, "/")] = data
    candidate_module = open(os.path.join(source_root, "src/video_paper_wiki/code_proof_resources.py"), "rb").read()
    installed_module_path = os.path.join(package_root, "code_proof_resources.py")
    installed_module = open(installed_module_path, "rb").read()
    if installed_module != candidate_module:
        raise AssertionError("installed foundation module differs from candidate")
    profile_key = "profiles/code-proof-v1.json"
    profile_bytes = retained[profile_key]
    profile = json.loads(profile_bytes.decode("utf-8"))
    profile_digest = digest(profile_bytes)
    freeze_profile_digest = freeze.get("resource_profile_sha256")
    profile_pin = next((row for row in freeze["resource_pins"] if row["relative_path"] == "src/video_paper_wiki/profiles/code-proof-v1.json"), None)
    if not isinstance(freeze_profile_digest, str) or profile_digest != freeze_profile_digest:
        raise AssertionError("installed profile differs from the production freeze digest")
    if not isinstance(profile_pin, dict) or profile_pin.get("sha256") != freeze_profile_digest:
        raise AssertionError("production profile pin is inconsistent")

    # Remove known source/build paths before importing the installed package.
    # Keep the interpreter's dependency site-packages entries, including the
    # repository's .venv dependency bridge, untouched.
    forbidden = [
        source_root,
        os.path.join(source_root, "src"),
        source_copy,
        os.path.join(source_copy, "src"),
        os.path.join(source_copy, "buildsrc"),
        os.path.join(os.path.dirname(source_copy), "buildsrc"),
        os.path.join(repo_root, "src"),
        os.path.join(known_temp_source, "source"),
        known_temp_source,
        os.path.join(known_temp_source, "src"),
        wheel_path,
    ]
    forbidden = list(dict.fromkeys(os.path.normpath(path) for path in forbidden))
    sys_path_before = list(sys.path)
    sys_path_before_absolute = [os.path.abspath(entry or cwd_before) for entry in sys_path_before]

    def is_forbidden(path):
        path = os.path.normpath(path)
        return any(path == item or path.startswith(item + os.sep) for item in forbidden)

    retained_sys_path = []
    removed_sys_path = []
    for raw, absolute in zip(sys_path_before, sys_path_before_absolute):
        if is_forbidden(absolute):
            removed_sys_path.append({"raw": raw, "absolute": absolute})
        else:
            retained_sys_path.append(raw)
    sys.path[:] = retained_sys_path
    sys.path.insert(0, install_target)
    sys_path_after = list(sys.path)
    original_absolute_by_raw = {raw: absolute for raw, absolute in zip(sys_path_before, sys_path_before_absolute)}
    sys_path_after_absolute = [
        install_target if raw == install_target else original_absolute_by_raw.get(raw, raw)
        for raw in sys_path_after
    ]
    if any(is_forbidden(path) for path in sys_path_after_absolute):
        raise AssertionError("known source/build path remained in sys.path")
    import video_paper_wiki
    import video_paper_wiki.code_proof_resources as resources

    package_origin = os.path.abspath(video_paper_wiki.__file__)
    module_origin = os.path.abspath(resources.__file__)
    if not inside(package_origin, install_target) or not inside(module_origin, install_target):
        raise AssertionError("package/module origin escaped fresh installation")
    if os.path.basename(os.path.dirname(module_origin)) == "src":
        raise AssertionError("installed origin is named src")

    # All inputs and the installed bytes are loaded before the purity guard.
    mapping = dict(retained)
    fixture_cases = list(fixture["cases"])
    common_title = "video-paper-wiki.code-proof-common.v1"
    builtins.open = fail
    io.open = fail
    os.open = fail
    os.stat = fail
    os.lstat = fail
    os.scandir = fail
    os.listdir = fail
    os.access = fail
    os.readlink = fail
    os.system = fail
    os.getcwd = fail
    socket.socket = fail
    subprocess.Popen = fail
    subprocess.run = fail
    subprocess.call = fail
    subprocess.check_call = fail
    subprocess.check_output = fail
    for name in ("open", "read_bytes", "read_text", "stat", "lstat", "exists", "is_file", "is_dir", "iterdir", "rglob", "resolve"):
        if hasattr(pathlib.Path, name):
            setattr(pathlib.Path, name, fail)

    plan = resources.resource_origin_plan()
    if getattr(plan, "layout", None) != "installed":
        raise AssertionError("installed resource plan did not select installed layout")
    for attr in ("package_directory", "schemas_directory", "profiles_directory"):
        value = os.path.normpath(str(getattr(plan, attr)))
        if not inside(value, install_target):
            raise AssertionError("resource plan escaped installed target")
    records = getattr(plan, "resources", ())
    if len(records) != 11:
        raise AssertionError("resource plan did not retain eleven rows")
    context = resources.compile_code_proof_resources(mapping)
    if context.profile_sha256 != profile_digest or context.profile_sha256 != freeze_profile_digest:
        raise AssertionError("profile digest mismatch")
    for case in fixture_cases:
        if context.validate_structure(case["title"], case["instance"]) is not None:
            raise AssertionError("validate_structure must return None")
    if context.validate_structure(common_title, {}) is not None:
        raise AssertionError("validate_structure must return None")
    full = context.materialize_limits(None)
    if full != profile["limits"]:
        raise AssertionError("full limits differ from installed profile")
    full_snapshot = copy.deepcopy(full)
    lowered = {group: {key: max(1, value - 1) for key, value in values.items()} for group, values in full_snapshot.items()}
    lowered_result = context.materialize_limits(lowered)
    if lowered_result != lowered:
        raise AssertionError("lowered limits were not retained independently")
    first_group, first_key = next((group, key) for group, values in full_snapshot.items() for key in values)
    lowered_original = lowered_result[first_group][first_key]
    lowered_result[first_group][first_key] = lowered_original + 1
    if full != full_snapshot:
        raise AssertionError("lowered limits share state with full limits")
    full_original = full[first_group][first_key]
    full[first_group][first_key] = full_original + 1
    if lowered_result[first_group][first_key] != lowered_original + 1:
        raise AssertionError("full limits share state with lowered limits")
    invalid_count = 0
    for group, values in full_snapshot.items():
        for key, value in values.items():
            over = copy.deepcopy(full_snapshot)
            over[group][key] = value + 1
            expect_limits_error(context, over)
            invalid_count += 1
            zero = copy.deepcopy(full_snapshot)
            zero[group][key] = 0
            expect_limits_error(context, zero)
            invalid_count += 1
            boolean = copy.deepcopy(full_snapshot)
            boolean[group][key] = True
            expect_limits_error(context, boolean)
            invalid_count += 1
            floating = copy.deepcopy(full_snapshot)
            floating[group][key] = 1.0
            expect_limits_error(context, floating)
            invalid_count += 1
    return {
        "package_origin": package_origin,
        "module_origin": module_origin,
        "sys_path": {"before": sys_path_before, "before_absolute": sys_path_before_absolute, "removed": removed_sys_path, "after": sys_path_after, "after_absolute": sys_path_after_absolute},
        "schema_comparisons": len(installed_schema_bytes),
        "resource_comparisons": len(mapping),
        "fixture_cases": len(fixture_cases),
        "common_title_probe": True,
        "full_limits": True,
        "lowered_limits": True,
        "invalid_limit_boundaries": invalid_count,
        "zero_io_guard": True,
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
'''


def _wheel_file_safety(wheel: Path, candidate: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise RuntimeError("wheel path is absent or not a wheel")
    expected_schema_rows = [row for row in freeze["baseline_tracked_files"] if row["relative_path"].startswith("schemas/") and row["relative_path"].endswith(".json")]
    if len(expected_schema_rows) != 81:
        raise RuntimeError("frozen schema count is not 81")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("wheel contains duplicate names")
        file_names = []
        for name in names:
            safe = PurePosixPath(name)
            if safe.is_absolute() or any(part in {"", ".", ".."} for part in safe.parts):
                raise RuntimeError(f"wheel path escapes archive: {name}")
            if not name.endswith("/"):
                file_names.append(name)
        records = [name for name in file_names if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise RuntimeError("wheel must contain exactly one RECORD")
        record_name = records[0]
        record_rows: dict[str, tuple[str, str]] = {}
        for row in csv.reader(archive.read(record_name).decode("utf-8").splitlines()):
            if len(row) != 3:
                raise RuntimeError("malformed wheel RECORD row")
            path = _safe_relative(row[0])
            if path in record_rows:
                raise RuntimeError("duplicate wheel RECORD row")
            record_rows[path] = (row[1], row[2])
        if set(record_rows) != set(file_names):
            raise RuntimeError("wheel RECORD file set mismatch")
        checked = 0
        for name in file_names:
            data = archive.read(name)
            digest = "" if name == record_name else "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            size = "" if name == record_name else str(len(data))
            if record_rows[name] != (digest, size):
                raise RuntimeError(f"wheel RECORD hash/size mismatch: {name}")
            checked += 1
        module_name = "video_paper_wiki/code_proof_resources.py"
        candidate_module = (SOURCE_ROOT / ALLOWED_PRODUCT_PATHS[0]).read_bytes()
        if archive.read(module_name) != candidate_module:
            raise RuntimeError("wheel foundation module differs from candidate")
        schema_names = {row["relative_path"][len("schemas/"):] for row in expected_schema_rows}
        wheel_schema_names = {name[len("video_paper_wiki/schemas/"):] for name in file_names if name.startswith("video_paper_wiki/schemas/") and name.endswith(".json")}
        if wheel_schema_names != schema_names:
            raise RuntimeError("wheel schema set differs from 81-file baseline")
        if "video_paper_wiki/profiles/code-proof-v1.json" not in file_names:
            raise RuntimeError("wheel profile is absent")
    return {"record_name": record_name, "files_checked": checked, "schema_files_checked": len(expected_schema_rows), "module_member": module_name}


def _capture(argv: list[str], cwd: Path, *, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=cwd, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _refuse_existing(paths: tuple[Path, ...]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise RuntimeError("refusing overwrite of existing evidence: " + ", ".join(existing))


def _verify_source_copy(source_copy: Path, candidate: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    if not source_copy.is_dir() or source_copy.is_symlink():
        raise RuntimeError("recorded build source-copy is absent or non-directory")
    expected_rows = _baseline_rows(freeze)
    expected_rows.extend(candidate["product_paths"])
    expected = {row["relative_path"]: row for row in expected_rows}
    actual = set()
    for path in source_copy.rglob("*"):
        if path.is_file() and not path.is_symlink():
            actual.add(path.relative_to(source_copy).as_posix())
    if actual != set(expected):
        raise RuntimeError("recorded build source-copy file set differs from frozen baseline plus candidate")
    checked = 0
    for rel, row in expected.items():
        path = source_copy / rel
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"recorded build source-copy entry is not regular: {rel}")
        data = path.read_bytes()
        if len(data) != row["size_bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeError(f"recorded build source-copy bytes differ: {rel}")
        checked += 1
    return {"path": str(source_copy), "files_checked": checked}


def _load_build_evidence(wheel: Path, candidate: dict[str, Any], freeze: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    if not BUILD_RESULT_PATH.is_file() or BUILD_RESULT_PATH.is_symlink():
        raise RuntimeError("foundation wheel build evidence is absent or non-regular")
    build = _read_json(BUILD_RESULT_PATH)
    if build.get("schema") != "full-todo.code-proof-foundation-wheel-build-evidence.v1":
        raise RuntimeError("foundation wheel build evidence schema mismatch")
    if build.get("candidate_snapshot_sha256") != candidate["snapshot_sha256"]:
        raise RuntimeError("wheel build evidence candidate snapshot mismatch")
    if build.get("freeze_sha256") != FREEZE_SHA256 or build.get("baseline_head") != candidate["baseline_head"] or build.get("baseline_tree") != candidate["baseline_tree"]:
        raise RuntimeError("wheel build evidence baseline mismatch")
    if build.get("exit_code") != 0:
        raise RuntimeError("recorded wheel build did not pass")
    wheel_meta = build.get("wheel")
    if not isinstance(wheel_meta, dict):
        raise RuntimeError("wheel build evidence has no wheel record")
    recorded_wheel = Path(str(wheel_meta.get("path", ""))).expanduser().absolute()
    if recorded_wheel != wheel:
        raise RuntimeError("--wheel does not match the recorded build wheel path")
    if not wheel.is_file() or wheel.is_symlink():
        raise RuntimeError("recorded wheel is absent or non-regular")
    wheel_bytes = wheel.read_bytes()
    if wheel_meta.get("size_bytes") != len(wheel_bytes) or wheel_meta.get("sha256") != sha256_bytes(wheel_bytes):
        raise RuntimeError("recorded wheel bytes differ from --wheel")
    source_copy = Path(str(build.get("source_copy", ""))).expanduser().absolute()
    source_copy_record = _verify_source_copy(source_copy, candidate, freeze)
    return build, source_copy, {"recorded_wheel": wheel_meta, "source_copy": source_copy_record}


def main() -> int:
    freeze = load_freeze()
    candidate = load_candidate(freeze)
    guard_before = manifest_guard(freeze, candidate)
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--wheel", required=True)
    args = parser.parse_args()
    wheel = Path(args.wheel).expanduser().absolute()
    output_paths = [RESULT_PATH]
    for name in ("py312", "py313"):
        output_paths.extend(
            [
                ARTIFACT_ROOT / f"foundation-wheel-install-{name}.stdout.log",
                ARTIFACT_ROOT / f"foundation-wheel-install-{name}.stderr.log",
                ARTIFACT_ROOT / f"foundation-wheel-probe-{name}.stdout.log",
                ARTIFACT_ROOT / f"foundation-wheel-probe-{name}.stderr.log",
            ]
        )
    _refuse_existing(tuple(output_paths))
    build_evidence, source_copy, build_verification = _load_build_evidence(wheel, candidate, freeze)
    wheel_safety = _wheel_file_safety(wheel, candidate, freeze)
    if not UV.is_file() or not LOCKED_PY312.is_file() or not PY313.is_file():
        raise RuntimeError("required uv or locked Python interpreter is absent")
    uv_version = _capture([str(UV), "--version"], Path("/private/tmp")).stdout.decode(errors="replace").strip()
    if not uv_version.startswith("uv 0.12.7"):
        raise RuntimeError(f"unexpected uv version: {uv_version}")
    python_versions = {}
    for name, interpreter in (("py312", LOCKED_PY312), ("py313", PY313)):
        proc = _capture([str(interpreter), "-c", "import sys; print(sys.version)"], Path("/private/tmp"))
        version = proc.stdout.decode(errors="replace").strip()
        expected = "3.12" if name == "py312" else "3.13"
        if proc.returncode != 0 or not version.startswith(expected):
            raise RuntimeError(f"unexpected {name} interpreter: {version}")
        python_versions[name] = {"path": str(interpreter), "version": version}
    temp_root = Path(tempfile.mkdtemp(prefix="code-proof-foundation-probe-", dir="/private/tmp"))
    runs = []
    for name, interpreter in (("py312", LOCKED_PY312), ("py313", PY313)):
        target = temp_root / f"installed-{name}"
        cwd = temp_root / f"empty-cwd-{name}"
        target.mkdir()
        cwd.mkdir()
        install_argv = [str(UV), "pip", "install", "--offline", "--no-deps", "--python", str(interpreter), "--target", str(target), str(wheel)]
        install_proc = _capture(install_argv, cwd)
        install_stdout = ARTIFACT_ROOT / f"foundation-wheel-install-{name}.stdout.log"
        install_stderr = ARTIFACT_ROOT / f"foundation-wheel-install-{name}.stderr.log"
        _write_exclusive(install_stdout, install_proc.stdout)
        _write_exclusive(install_stderr, install_proc.stderr)
        child_argv = [str(interpreter), "-I", "-B", "-", str(target), str(SOURCE_ROOT), str(CANDIDATE_PATH), str(FREEZE_PATH), str(SOURCE_ROOT / "tests/fixtures/code-proof-resource-v1.json"), str(wheel), str(source_copy), str(REPO_ROOT)]
        child_proc = _capture(child_argv, cwd, input=CHILD_SOURCE.encode("utf-8")) if install_proc.returncode == 0 else subprocess.CompletedProcess(child_argv, 1, b"", b"install failed")
        child_stdout = ARTIFACT_ROOT / f"foundation-wheel-probe-{name}.stdout.log"
        child_stderr = ARTIFACT_ROOT / f"foundation-wheel-probe-{name}.stderr.log"
        _write_exclusive(child_stdout, child_proc.stdout)
        _write_exclusive(child_stderr, child_proc.stderr)
        result = None
        if child_proc.returncode == 0:
            result = json.loads(child_proc.stdout.decode("utf-8"))
        runs.append({
            "name": name,
            "target": str(target),
            "cwd": str(cwd),
            "install": {"argv": install_argv, "exit_code": install_proc.returncode, "stdout": {"path": str(install_stdout), "size_bytes": install_stdout.stat().st_size, "sha256": sha256_bytes(install_proc.stdout)}, "stderr": {"path": str(install_stderr), "size_bytes": install_stderr.stat().st_size, "sha256": sha256_bytes(install_proc.stderr)}},
            "probe": {"argv": child_argv, "exit_code": child_proc.returncode, "stdout": {"path": str(child_stdout), "size_bytes": child_stdout.stat().st_size, "sha256": sha256_bytes(child_proc.stdout)}, "stderr": {"path": str(child_stderr), "size_bytes": child_stderr.stat().st_size, "sha256": sha256_bytes(child_proc.stderr)}, "result": result},
        })
    guard_after = manifest_guard(freeze, candidate)
    evidence = {
        "schema": "full-todo.code-proof-foundation-wheel-probe-evidence.v1",
        "candidate": str(CANDIDATE_PATH),
        "candidate_snapshot_sha256": candidate["snapshot_sha256"],
        "freeze_sha256": FREEZE_SHA256,
        "baseline_head": candidate["baseline_head"],
        "baseline_tree": candidate["baseline_tree"],
        "manifest_guard_before": guard_before,
        "manifest_guard_after": guard_after,
        "uv": {"path": str(UV), "version": uv_version},
        "wheel": {"path": str(wheel), "size_bytes": wheel.stat().st_size, "sha256": sha256_bytes(wheel.read_bytes()), "record": wheel_safety},
        "build_evidence": {"path": str(BUILD_RESULT_PATH), "candidate_snapshot_sha256": build_evidence["candidate_snapshot_sha256"], "source_copy": build_verification["source_copy"]},
        "child_source": {"encoding": "utf-8", "size_bytes": len(CHILD_SOURCE.encode("utf-8")), "sha256": sha256_bytes(CHILD_SOURCE.encode("utf-8")), "base64": base64.b64encode(CHILD_SOURCE.encode("utf-8")).decode("ascii")},
        "python_versions": python_versions,
        "runs": runs,
        "all_passed": all(run["install"]["exit_code"] == 0 and run["probe"]["exit_code"] == 0 for run in runs),
    }
    _write_exclusive(RESULT_PATH, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if not evidence["all_passed"]:
        raise RuntimeError("installed-wheel probe failed; see evidence and raw logs")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
