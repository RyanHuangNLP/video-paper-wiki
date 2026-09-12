"""Independent black-box checks for the frozen private I/O session interface.

This preparation is not a test result. Run only after the two-file candidate
has been independently reviewed and installed in a disposable source mirror.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: architect_io_smoke_probes_r2.py FRESH_RESULT_JSON")
    result_path = Path(sys.argv[1]).absolute()
    if result_path.exists():
        raise SystemExit("Refusing to overwrite prior probe evidence")
    from video_paper_wiki import code_proof_resources as resources
    from video_paper_wiki import code_proof_io as io
    original_plan = resources.resource_origin_plan()
    original_module = Path(resources.__file__)
    root = Path(tempfile.mkdtemp(prefix="cio-", dir="/private/tmp"))
    package = root / "r" / "src" / "video_paper_wiki"
    package.mkdir(parents=True, mode=0o700)
    shutil.copyfile(original_module, package / "code_proof_resources.py")
    for resource in original_plan.resources:
        directory = Path(original_plan.schemas_directory if resource.relative_path.startswith("schemas/") else original_plan.profiles_directory)
        source = directory / resource.relative_path.rsplit("/", 1)[1]
        data = source.read_bytes()
        assert len(data) == resource.size_bytes and hashlib.sha256(data).hexdigest() == resource.sha256
        target = (root / "r" / resource.relative_path) if resource.relative_path.startswith("schemas/") else (package / resource.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(data)
        target.chmod(0o600)
    results = []
    sequence = 0

    @contextmanager
    def checkout():
        nonlocal sequence
        sequence += 1
        work = root / ("w" + str(sequence))
        work.mkdir(mode=0o700)
        (work / ".git").write_bytes(b"gitdir: unused-marker\n")
        (work / "pyproject.toml").write_bytes(b'[project]\nname = "video-paper-wiki"\n')
        for name in (".git", "pyproject.toml"):
            (work / name).chmod(0o600)
        with patch.object(resources, "__file__", str(package / "code_proof_resources.py")), patch.object(io, "_getcwd", lambda: str(work)):
            yield work

    def output_limits(session):
        values = session.materialize_limits(None)["public"]
        return {key: value for key, value in values.items() if key != "max_inline_normalized_bytes"}

    def run(name, function):
        try:
            function()
        except BaseException as exc:
            results.append({"name": name, "passed": False, "exception_class": type(exc).__name__, "code": getattr(exc, "code", None)})
        else:
            results.append({"name": name, "passed": True})

    def empty_and_inactive():
        with checkout() as work:
            with io.open_code_session(batch_id="probe") as session:
                assert session.snapshot() == {}
                state = session.layout_state()
                assert set(state) == {"initial_namespace_present", "current_namespace_present", "initial_families", "current_families", "initial_files", "current_files", "current_file_bytes"}
                assert state["initial_namespace_present"] is False and state["current_namespace_present"] is False
                state["current_families"]["objects"] = True
                assert session.layout_state()["current_families"]["objects"] is False
                session.verify()
            assert not (work / ".work").exists()
            try:
                session.materialize_limits(None)
            except RuntimeError as exc:
                assert str(exc) == "CODE session is not active"
            else:
                raise AssertionError("closed session exposed resource context")

    def install_reuse_conflict():
        with checkout() as work:
            with io.open_code_session(batch_id="probe") as session:
                session.set_output_limits(output_limits(session))
                assert session.install("request.json", b"first") is False
                assert session.snapshot() == {"request.json": b"first"}
            target = work / ".work" / "probe" / "code-evidence-v1" / "request.json"
            assert target.read_bytes() == b"first" and target.stat().st_mode & 0o7777 == 0o600
            with io.open_code_session(batch_id="probe") as session:
                session.set_output_limits(output_limits(session))
                assert session.install("request.json", b"first") is True
            try:
                with io.open_code_session(batch_id="probe") as session:
                    session.set_output_limits(output_limits(session))
                    session.install("request.json", b"changed")
            except io.CodeProofIOError as exc:
                assert exc.code == "CODE_PROOF_CONFLICT"
                assert exc.details == {"instance_pointer": "/request", "reason": "artifact_changed"}
            else:
                raise AssertionError("initial conflict accepted")
            assert target.read_bytes() == b"first"

    def exact_peak_before_creation():
        with checkout() as work:
            try:
                with io.open_code_session(batch_id="probe") as session:
                    limits = output_limits(session)
                    limits["max_output_peak_bytes"] = 7
                    session.set_output_limits(limits)
                    session.install("request.json", b"1234")
            except io.CodeProofIOError as exc:
                assert exc.code == "CODE_PROOF_LIMIT_EXCEEDED"
                assert exc.details == {"instance_pointer": "/output", "limit_name": "max_output_peak_bytes", "limit": 7, "observed": 8}
            else:
                raise AssertionError("peak overage accepted")
            assert not (work / ".work").exists()
            with io.open_code_session(batch_id="probe") as session:
                limits = output_limits(session)
                limits["max_output_peak_bytes"] = 8
                session.set_output_limits(limits)
                assert session.install("request.json", b"1234") is False

    def original_interruption_identity():
        with checkout() as work:
            original = KeyboardInterrupt("independent-probe")
            try:
                with io.open_code_session(batch_id="probe"):
                    raise original
            except KeyboardInterrupt as exc:
                assert exc is original
            else:
                raise AssertionError("interruption was converted to success")
            assert not (work / ".work").exists()

    def resource_replacement_overrides_original():
        with checkout():
            plan = resources.resource_origin_plan()
            first = plan.resources[0]
            directory = Path(plan.schemas_directory if first.relative_path.startswith("schemas/") else plan.profiles_directory)
            path = directory / first.relative_path.rsplit("/", 1)[1]
            original_bytes = path.read_bytes()
            old = path.with_name(path.name + ".old")
            replacement = path.with_name(path.name + ".replacement")
            original = ValueError("semantic-probe")
            try:
                try:
                    with io.open_code_session(batch_id="probe"):
                        replacement.write_bytes(original_bytes)
                        replacement.chmod(0o600)
                        path.rename(old)
                        replacement.rename(path)
                        raise original
                except io.CodeProofIOError as exc:
                    assert exc.code == "WORK_PATH_UNSAFE"
                    assert exc.details["group"] == "resources"
                    assert "resources" in exc.details["failed_groups"]
                else:
                    raise AssertionError("changed retained resource accepted")
            finally:
                if old.exists():
                    path.unlink()
                    old.rename(path)
                if replacement.exists():
                    replacement.unlink()

    try:
        for name, function in [("empty_snapshot_and_closed_context", empty_and_inactive), ("new_install_initial_reuse_stable_conflict", install_reuse_conflict), ("C_plus_2N_peak_before_creation", exact_peak_before_creation), ("original_interrupt_object_identity", original_interruption_identity), ("retained_resource_replacement_overrides_original", resource_replacement_overrides_original)]:
            run(name, function)
    finally:
        report = {"schema": "full-todo.code-io-independent-smoke-probes.v1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "runtime": sys.executable, "script": pin(Path(__file__).absolute()), "foundation_module": pin(original_module), "io_module": pin(Path(io.__file__)), "scratch_root": str(root), "check_groups": results, "all_passed": len(results) == 5 and all(row["passed"] for row in results), "full_acceptance": False}
        with result_path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps(pin(result_path)))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
