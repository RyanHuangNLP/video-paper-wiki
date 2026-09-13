"""Bounded diagnostic reproductions for the incomplete, unaccepted I/O R1."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import errno
import hashlib
import json
import os
import sys
import tempfile
from unittest.mock import patch


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    from video_paper_wiki import code_proof_io as io
    from video_paper_wiki import code_proof_resources as resources
    result_path = Path(sys.argv[1]).absolute()
    assert not result_path.exists()
    assert pin(Path(io.__file__))["sha256"] == "a5113bf49b469a5d8f62df599b40c6c13c5162e2f29be131a2b894ad1757e431"
    root = Path(tempfile.mkdtemp(prefix="cio-diag-", dir="/private/tmp"))
    sequence = 0
    rows = []

    @contextmanager
    def checkout(namespace=True, objects=False):
        nonlocal sequence
        sequence += 1
        work = root / str(sequence)
        work.mkdir(mode=0o700)
        (work / ".git").write_bytes(b"gitdir: unused-marker\n")
        (work / "pyproject.toml").write_bytes(b'[project]\nname = "video-paper-wiki"\n')
        for name in (".git", "pyproject.toml"):
            (work / name).chmod(0o600)
        ns = work / ".work" / "probe" / "code-evidence-v1"
        if namespace:
            ns.mkdir(parents=True, mode=0o700)
            if objects:
                (ns / "objects").mkdir(mode=0o700)
        with patch.object(io, "_getcwd", lambda: str(work)):
            yield work, ns

    def write(path, data):
        path.write_bytes(data)
        path.chmod(0o600)

    def limits(session):
        return {k: v for k, v in session.materialize_limits(None)["public"].items() if k != "max_inline_normalized_bytes"}

    def capture(name, expected, function):
        try:
            value = function()
            actual = {"outcome": "success", "value": value}
        except BaseException as exc:
            actual = {"outcome": "exception", "class": type(exc).__name__, "code": getattr(exc, "code", None), "details": getattr(exc, "details", None)}
        rows.append({"name": name, "expected": expected, "actual": actual})

    def empty(namespace):
        with checkout(namespace=namespace):
            with io.open_code_session(batch_id="probe") as session:
                return session.snapshot()

    capture("missing_output_namespace", "success with empty snapshot and no creation", lambda: empty(False))
    capture("existing_empty_namespace_control", "success with empty snapshot", lambda: empty(True))

    def late_file(name, family=False):
        with checkout(objects=family) as (_work, ns):
            with io.open_code_session(batch_id="probe") as session:
                initial = session.snapshot()
                destination = ns / "objects" / name if family else ns / name
                write(destination, b"late")
                observed = session.snapshot()
                session.verify()
            return {"initial": sorted(initial), "after": sorted(observed), "external_file_remains": destination.exists()}

    capture("namespace_unknown_late_arrival", "WORK_PATH_UNSAFE for changed complete set", lambda: late_file("foreign.bin"))
    capture("fixed_slot_late_arrival", "WORK_PATH_UNSAFE for captured request absence", lambda: late_file("request.json"))
    capture("object_family_late_arrival", "WORK_PATH_UNSAFE for changed complete set", lambda: late_file("a" * 40 + ".body", True))

    def failed_input_replacement():
        with checkout() as (work, _ns):
            source = work / "input.json"
            replacement = work / "replacement"
            write(source, b"original")
            write(replacement, b"replaced")
            original_stamp = source.stat()
            original_read = io._read
            injected = False

            def fail_read(fd, size):
                nonlocal injected
                stamp = os.fstat(fd)
                if not injected and (stamp.st_dev, stamp.st_ino) == (original_stamp.st_dev, original_stamp.st_ino):
                    injected = True
                    os.replace(replacement, source)
                    raise OSError(errno.EIO, "fixture read failure after persistent replacement")
                return original_read(fd, size)

            with patch.object(io, "_read", fail_read):
                with io.open_code_session(batch_id="probe") as session:
                    session.retain_input(str(source), maximum=65536)
            assert injected

    capture("failed_input_retains_named_edge", "WORK_PATH_UNSAFE overriding original read error", failed_input_replacement)

    def oversized_request():
        with checkout() as (_work, ns):
            write(ns / "request.json", b"x" * 65537)
            with io.open_code_session(batch_id="probe"):
                pass

    capture("initial_request_per_file_limit", "CODE_PROOF_LIMIT_EXCEEDED max_request_bytes=65536 observed=65537 pointer=/output", oversized_request)

    def changed_created_output():
        with checkout() as (_work, ns):
            with io.open_code_session(batch_id="probe") as session:
                session.set_output_limits(limits(session))
                disposition = session.install("request.json", b"first")
                write(ns / "request.json", b"wrong")
                snapshot = session.snapshot()
                session.verify()
            return {"install": disposition, "reported": snapshot["request.json"].decode(), "actual": (ns / "request.json").read_text()}

    capture("newly_installed_output_is_retained", "WORK_PATH_UNSAFE for mutated current-command output", changed_created_output)

    def failed_second_install():
        with checkout() as (_work, ns):
            caught = None
            try:
                with io.open_code_session(batch_id="probe") as session:
                    session.set_output_limits(limits(session))
                    session.install("request.json", b"first")
                    def fail_write(_fd, _data):
                        raise OSError(errno.EIO, "fixture second installation failure")
                    with patch.object(io, "_write", fail_write):
                        session.install("intent.json", b"second")
            except io.CodeProofIOError as exc:
                caught = {"code": exc.code, "details": exc.details}
            return {"caught": caught, "leftover_temporaries": sorted(p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")), "request_unchanged": (ns / "request.json").read_bytes() == b"first"}

    capture("second_install_failure_checked_cleanup", "original refusal with no owned temporary left behind", failed_second_install)

    result = {"schema": "full-todo.code-io-bounded-diagnostics.v1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "runtime": sys.executable, "script": pin(Path(__file__).absolute()), "source": pin(Path(io.__file__)), "foundation": pin(Path(resources.__file__)), "scratch_root": str(root), "observations": rows, "candidate_accepted": False, "product_source_modified": False}
    with result_path.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(pin(result_path)))


if __name__ == "__main__":
    main()
