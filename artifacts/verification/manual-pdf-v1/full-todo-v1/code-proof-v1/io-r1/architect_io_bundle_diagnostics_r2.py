"""Replay raw-bundle regressions against an explicitly pinned review source."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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
    output = Path(sys.argv[1]).absolute()
    assert not output.exists()
    assert len(sys.argv) == 3, "usage: script RESULT_PATH EXACT_SOURCE_SHA256"
    expected_source_sha256 = sys.argv[2]
    assert len(expected_source_sha256) == 64 and set(expected_source_sha256) <= set("0123456789abcdef")
    initial_source = pin(Path(io.__file__))
    assert initial_source["sha256"] == expected_source_sha256
    root = Path(tempfile.mkdtemp(prefix="cio-bdiag-", dir="/private/tmp"))
    sequence = 0
    results = []

    def write(path, data):
        path.write_bytes(data)
        path.chmod(0o600)

    @contextmanager
    def fixture(bodies=()):
        nonlocal sequence
        sequence += 1
        work = root / str(sequence)
        work.mkdir(mode=0o700)
        write(work / ".git", b"gitdir: unused-marker\n")
        write(work / "pyproject.toml", b'[project]\nname = "video-paper-wiki"\n')
        (work / ".work" / "probe" / "code-evidence-v1").mkdir(parents=True, mode=0o700)
        bundle = work / ".work" / "raw"
        (bundle / "objects").mkdir(parents=True, mode=0o700)
        write(bundle / "manifest.json", b"{}\n")
        inventory = []
        for body in bodies:
            framed = b"blob " + str(len(body)).encode() + b"\0" + body
            oid = hashlib.sha1(framed).hexdigest()
            inventory.append({"oid": oid, "object_type": "blob", "body_size_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(), "framed_sha256": hashlib.sha256(framed).hexdigest()})
            write(bundle / "objects" / (oid + ".body"), body)
        inventory.sort(key=lambda row: row["oid"])
        with patch.object(io, "_getcwd", lambda: str(work)):
            yield work, bundle, inventory

    def capture(name, expected, action):
        try:
            result = {"outcome": "success", "value": action()}
        except BaseException as exc:
            result = {"outcome": "exception", "class": type(exc).__name__, "code": getattr(exc, "code", None), "reason": getattr(exc, "reason", None), "details": getattr(exc, "details", None)}
        results.append({"name": name, "expected": expected, "actual": result})

    def root_late_entry():
        with fixture() as (_work, bundle, _inventory):
            with io.open_code_session(batch_id="probe") as session:
                session.retain_bundle_manifest(".work/raw")
                write(bundle / "foreign.bin", b"late")
                session.verify()
            return {"raw_root_entries": sorted(path.name for path in bundle.iterdir())}

    capture("raw_root_complete_set", "WORK_PATH_UNSAFE after third raw-root entry appears", root_late_entry)

    def replaced_objects_directory():
        with fixture() as (work, bundle, _inventory):
            with io.open_code_session(batch_id="probe") as session:
                session.retain_bundle_manifest(".work/raw")
                old = (bundle / "objects").stat()
                (bundle / "objects").rename(work / ".work" / "held-objects")
                (bundle / "objects").mkdir(mode=0o700)
                new = (bundle / "objects").stat()
                assert (old.st_dev, old.st_ino) != (new.st_dev, new.st_ino)
                session.verify()
            return {"persistent_named_replacement": True, "both_directories_alive": True}

    capture("raw_objects_named_directory_lineage", "WORK_PATH_UNSAFE for persistent named objects directory replacement", replaced_objects_directory)

    def malformed_inventory(extra=False, unsorted=False):
        with fixture((b"x", b"y")) as (_work, _bundle, inventory):
            if extra:
                inventory[0]["unexpected"] = True
            if unsorted:
                inventory.reverse()
            with io.open_code_session(batch_id="probe") as session:
                session.retain_bundle_manifest(".work/raw")
                bodies = session.retain_bundle_bodies(object_format="sha1", objects=inventory, limits=session.materialize_limits(None)["git"])
            return {"retained_bodies": len(bodies), "returned_oids": list(bodies)}

    capture("inventory_records_are_closed", "private structure refusal for sixth object-record key before body open", lambda: malformed_inventory(extra=True))
    capture("inventory_oid_order", "private structure refusal for non-ascending inventory before body open", lambda: malformed_inventory(unsorted=True))
    record = {"schema": "full-todo.code-io-bundle-diagnostics.v1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "runtime": sys.executable, "script": pin(Path(__file__).absolute()), "source": pin(Path(io.__file__)), "scratch_root": str(root), "observations": results, "candidate_accepted": False, "product_source_modified": False}
    final_source = pin(Path(io.__file__))
    assert final_source == initial_source, "review source changed during diagnostic replay"
    record["source_unchanged"] = True
    record["expected_source_sha256"] = expected_source_sha256
    with output.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(pin(output)))


if __name__ == "__main__":
    main()
