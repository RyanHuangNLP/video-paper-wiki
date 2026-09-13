"""Unit tests for retained code-evidence I/O and interrupt recovery."""

from __future__ import annotations

import errno
import hashlib
import os
import socket
import stat
from pathlib import Path

import pytest

from video_paper_wiki import code_proof_io as io
from video_paper_wiki import code_proof_resources as cpr
from video_paper_wiki.code_git_objects import (
    CODE_PROOF_INPUT_INVALID,
    CODE_PROOF_OBJECT_EXTRA,
    CODE_PROOF_OBJECT_UNAVAILABLE,
    CodeGitProofError,
)
from video_paper_wiki.code_proof_io import CodeProofIOError, open_code_session
from video_paper_wiki.code_proof_resources import (
    CodeProofStructureError,
    resource_origin_plan,
)

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMAS = _ROOT / "schemas"
_PROFILE = _ROOT / "src" / "video_paper_wiki" / "profiles" / "code-proof-v1.json"
_RESOURCES_PY = _ROOT / "src" / "video_paper_wiki" / "code_proof_resources.py"
_PYPROJECT = '[project]\nname = "video-paper-wiki"\n'
_MARKER = "MARKER_SECRET_9f3a_do_not_leak"
_HARD_OUTPUT = {
    "max_request_bytes": 65536,
    "max_intent_bytes": 1048576,
    "max_bundle_bytes": 1048576,
    "max_observation_bytes": 2097152,
    "max_config_document_bytes": 2097152,
    "max_handoff_bytes": 131072,
    "max_output_peak_bytes": 134217728,
}
_HARD_GIT = {
    "max_targets": 32,
    "max_objects": 2048,
    "max_tree_entries": 32768,
    "max_object_bytes": 8388608,
    "max_total_object_bytes": 33554432,
}
_OID_A = "0" * 40
_OID_B = "1" * 40
_OID64_A = "a" * 64
_OID64_B = "b" * 64


def _make_checkout(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()
    (path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return path


def _copy_source_layout(dst: Path) -> Path:
    pkg = dst / "src" / "video_paper_wiki"
    pkg.mkdir(parents=True)
    schemas = dst / "schemas"
    schemas.mkdir()
    profiles = pkg / "profiles"
    profiles.mkdir()
    target = pkg / "code_proof_resources.py"
    target.write_bytes(_RESOURCES_PY.read_bytes())
    for pin in resource_origin_plan().resources:
        name = pin.relative_path.split("/", 1)[1]
        if pin.relative_path.startswith("schemas/"):
            (schemas / name).write_bytes((_SCHEMAS / name).read_bytes())
        else:
            (profiles / name).write_bytes(_PROFILE.read_bytes())
    return target


def _copy_installed_layout(dst: Path) -> Path:
    pkg = dst / "site" / "video_paper_wiki"
    pkg.mkdir(parents=True)
    schemas = pkg / "schemas"
    profiles = pkg / "profiles"
    schemas.mkdir()
    profiles.mkdir()
    target = pkg / "code_proof_resources.py"
    target.write_bytes(_RESOURCES_PY.read_bytes())
    for pin in resource_origin_plan().resources:
        name = pin.relative_path.split("/", 1)[1]
        if pin.relative_path.startswith("schemas/"):
            (schemas / name).write_bytes((_SCHEMAS / name).read_bytes())
        else:
            (profiles / name).write_bytes(_PROFILE.read_bytes())
    return target


def _replace_keep_alive(path: Path, data: bytes) -> int:
    """Replace the named edge while keeping the original inode live."""
    fd = os.open(path, os.O_RDONLY)
    sibling = path.parent / (path.name + ".repl")
    sibling.write_bytes(data)
    os.rename(sibling, path)
    return fd


def _assert_io(exc, code, **fields):
    assert type(exc) is CodeProofIOError
    assert exc.code == code
    assert exc.message == {
        "WORKSPACE_ROOT_INVALID": "CODE workspace root is invalid",
        "INVALID_BATCH_ID": "CODE batch identifier is invalid",
        "WORK_PATH_UNSAFE": "CODE retained path is unsafe",
        "CODE_PROOF_IO_ERROR": "CODE evidence I/O failed",
        "CODE_PROOF_RESOURCE_INVALID": "CODE evidence resource is invalid",
        "CODE_PROOF_LIMIT_EXCEEDED": "CODE evidence limit exceeded",
        "CODE_PROOF_CONFLICT": "CODE evidence artifact conflicts",
        "CODE_PROOF_BUSY": "CODE evidence workspace is busy",
    }[code]
    assert exc.exit_code == 2
    details = exc.details
    details["phase"] = "mutated"
    assert exc.details != details
    for key, value in fields.items():
        assert exc.details[key] == value, (key, exc.details, value)


def _object_record(oid: str, body: bytes, object_type: str = "blob") -> dict:
    framed = object_type.encode("ascii") + b" " + str(len(body)).encode("ascii") + b"\0" + body
    return {
        "oid": oid,
        "object_type": object_type,
        "body_size_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "framed_sha256": hashlib.sha256(framed).hexdigest(),
    }


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_checkout(tmp_path / "co")
    monkeypatch.chdir(root)
    return root


def test_empty_session_no_work_creates_nothing(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        assert session.snapshot() == {}
        state = session.layout_state()
        assert state["initial_namespace_present"] is False
        assert state["current_namespace_present"] is False
        assert state["initial_files"] == []
        assert state["current_files"] == []
        assert state["current_file_bytes"] == 0
        assert state["initial_families"] == {
            "objects": False,
            "configs": False,
            "handoffs": False,
        }
        session.verify()
        digest = session.profile_sha256
        assert type(digest) is str and len(digest) == 64
        session.materialize_limits(None)
    assert not (checkout / ".work").exists()


def test_absent_batch_and_namespace_are_empty(checkout: Path) -> None:
    (checkout / ".work").mkdir()
    with open_code_session(batch_id="missingBatch") as session:
        assert session.snapshot() == {}
        assert session.layout_state()["initial_namespace_present"] is False
    (checkout / ".work" / "present").mkdir()
    with open_code_session(batch_id="present") as session:
        assert session.snapshot() == {}
        assert session.layout_state()["initial_namespace_present"] is False
    ns = checkout / ".work" / "present" / "code-evidence-v1"
    ns.mkdir()
    os.chmod(ns, 0o700)
    with open_code_session(batch_id="present") as session:
        assert session.snapshot() == {}
        state = session.layout_state()
        assert state["initial_namespace_present"] is True
        assert state["current_files"] == []


def test_invalid_batch_id(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="-bad"):
            pass
    _assert_io(caught.value, "INVALID_BATCH_ID", reason="batch_id")
    with pytest.raises(CodeProofIOError):
        with open_code_session(batch_id="bad-"):
            pass
    with pytest.raises(CodeProofIOError):
        with open_code_session(batch_id=""):
            pass
    with pytest.raises(CodeProofIOError):
        with open_code_session(batch_id="x" * 129):
            pass


def test_missing_checkout_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "nomark"
    root.mkdir()
    monkeypatch.chdir(root)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(caught.value, "WORKSPACE_ROOT_INVALID", reason="missing")
    (root / ".git").mkdir()
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(caught.value, "WORKSPACE_ROOT_INVALID", reason="missing")
    (root / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(caught.value, "WORKSPACE_ROOT_INVALID", reason="marker_invalid")


def test_closed_session_rejects_wrappers(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        held = session
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.snapshot()
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.layout_state()
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.retain_input("x", maximum=65536)
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.retain_bundle_manifest(".work/x")
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.retain_bundle_bodies(object_format="sha1", objects=[], limits=_HARD_GIT)
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.set_output_limits(_HARD_OUTPUT)
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.install("request.json", b"{}\n")
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.verify()
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.validate_structure("video-paper-wiki.code-proof-common.v1", {})
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        held.materialize_limits(None)
    with pytest.raises(RuntimeError, match="CODE session is not active"):
        _ = held.profile_sha256
    assert held._state == "closed"
    assert held._resource_context is None
    assert held._resource_plan is None
    assert held._resource_records is None
    assert held._schemas_directory is None
    assert held._profiles_directory is None
    assert held._nodes == []
    assert held._fd_order == []
    assert held._install.temp_node is None
    assert held._install.temp_fd is None
    assert held._install.parent_node is None
    assert held._install.final_node is None
    assert held._install.payload is None
    with open_code_session(batch_id="b2") as session:
        session.set_output_limits(_HARD_OUTPUT)
        session.install("request.json", b"{}\n")
        held_install = session
    assert held_install._state == "closed"
    assert held_install._install.temp_node is None
    assert held_install._install.temp_fd is None
    assert held_install._install.parent_node is None
    assert held_install._install.final_node is None
    assert held_install._install.payload is None


def test_capability_missing_primitive_creates_nothing(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = io._capability_snapshot()
    snap["O_NOFOLLOW"] = None
    monkeypatch.setattr(io, "_capability_snapshot", lambda: snap)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", reason="unavailable_primitive")
    assert not (checkout / ".work").exists()


def test_lock_busy(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def busy(fd, flags):
        raise OSError(errno.EAGAIN, "busy")

    monkeypatch.setattr(io, "_flock", busy)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(caught.value, "CODE_PROOF_BUSY", reason="lock_busy", operation="flock")


def test_lock_unsupported(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported(fd, flags):
        raise OSError(errno.ENOSYS, "no")

    monkeypatch.setattr(io, "_flock", unsupported)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(
        caught.value,
        "CODE_PROOF_IO_ERROR",
        reason="unavailable_primitive",
        operation="flock",
    )


def test_checkout_fsync_unsupported(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = io._fsync
    seen = {"n": 0}

    def wrapped(fd):
        seen["n"] += 1
        if seen["n"] == 1:
            raise OSError(errno.ENOTSUP, "no")
        return real(fd)

    monkeypatch.setattr(io, "_fsync", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b"):
            pass
    _assert_io(
        caught.value,
        "CODE_PROOF_IO_ERROR",
        reason="unavailable_primitive",
        operation="fsync",
    )


def test_install_reuse_and_fresh(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    payload = b'{"ok":true}\n'
    target = ns / "request.json"
    target.write_bytes(payload)
    os.chmod(target, 0o600)
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        assert session.install("request.json", payload) is True
        assert session.snapshot()["request.json"] == payload
        assert session.install("intent.json", b'{"i":1}\n') is False
        snap = session.snapshot()
        assert snap["intent.json"] == b'{"i":1}\n'
        assert snap["request.json"] == payload
        state = session.layout_state()
        assert "intent.json" in state["current_files"]
        assert "request.json" in state["initial_files"]
        assert "intent.json" not in state["initial_files"]
    assert (ns / "intent.json").read_bytes() == b'{"i":1}\n'
    assert stat.S_IMODE((ns / "intent.json").stat().st_mode) == 0o600


def test_stable_conflict(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    (ns / "request.json").write_bytes(b"first\n")
    os.chmod(ns / "request.json", 0o600)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"second\n")
    _assert_io(
        caught.value,
        "CODE_PROOF_CONFLICT",
        instance_pointer="/request",
        reason="artifact_changed",
    )


def test_install_before_set_and_second_setter(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        with pytest.raises(RuntimeError, match="CODE output limits are not set"):
            session.install("request.json", b"{}\n")
        session.set_output_limits(_HARD_OUTPUT)
        with pytest.raises(RuntimeError, match="CODE output limits are already set"):
            session.set_output_limits(_HARD_OUTPUT)


def test_setter_type_and_bounds(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        with pytest.raises(CodeProofStructureError) as caught:
            session.set_output_limits("no")
        assert caught.value.reason == "limits"
        bad = dict(_HARD_OUTPUT)
        bad["max_request_bytes"] = 0
        with pytest.raises(CodeProofStructureError):
            session.set_output_limits(bad)
        extra = dict(_HARD_OUTPUT)
        extra["nope"] = 1
        with pytest.raises(CodeProofStructureError):
            session.set_output_limits(extra)
        missing = dict(_HARD_OUTPUT)
        missing.pop("max_handoff_bytes")
        with pytest.raises(CodeProofStructureError):
            session.set_output_limits(missing)
        as_bool = dict(_HARD_OUTPUT)
        as_bool["max_request_bytes"] = True
        with pytest.raises(CodeProofStructureError):
            session.set_output_limits(as_bool)


def test_request_over_hard_cap_reports_per_file_limit(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    (ns / "request.json").write_bytes(b"x" * 65537)
    os.chmod(ns / "request.json", 0o600)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/output",
        limit_name="max_request_bytes",
        limit=65536,
        observed=65537,
    )


def test_install_payload_over_cap(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"x" * 65537)
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/request",
        limit_name="max_request_bytes",
        limit=65536,
        observed=65537,
    )


def test_install_argument_order(checkout: Path) -> None:
    class HostileStr(str):
        def __eq__(self, other):
            raise AssertionError("eq")

        def __hash__(self):
            raise AssertionError("hash")

        def __len__(self):
            raise AssertionError("len")

    class HostileBytes(bytes):
        def __eq__(self, other):
            raise AssertionError("eq")

        def __len__(self):
            raise AssertionError("len")

    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        with pytest.raises(CodeProofStructureError) as caught:
            session.install(HostileStr("request.json"), b"{}\n")
        assert caught.value.reason == "type"
        with pytest.raises(CodeProofStructureError) as caught:
            session.install("request.json", HostileBytes(b"{}\n"))
        assert caught.value.reason == "type"
        with pytest.raises(CodeProofIOError) as caught:
            session.install("nope.json", b"{}\n")
        _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="path_spelling", group="installation")


def test_retain_input_type_and_maximum_order(checkout: Path) -> None:
    class Pathish:
        def __fspath__(self):
            raise AssertionError("fspath")

        def __str__(self):
            raise AssertionError("str")

    with open_code_session(batch_id="b1") as session:
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_input(Pathish(), maximum=65536)
        assert caught.value.reason == "type"
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_input("input.json", maximum=True)
        assert caught.value.reason == "limits"
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_input("input.json", maximum=12)
        assert caught.value.reason == "limits"


def test_retain_input_success_and_limit(checkout: Path) -> None:
    src = checkout / "input.json"
    src.write_bytes(b'{"a":1}\n')
    with open_code_session(batch_id="b1") as session:
        assert session.retain_input("input.json", maximum=65536) == b'{"a":1}\n'
    src.write_bytes(b"x" * 65537)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_input("input.json", maximum=65536)
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/input",
        limit_name="max_request_input_bytes",
        limit=65536,
        observed=65537,
    )


def test_retain_input_overlap_output(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_input(".work/b1/code-evidence-v1/request.json", maximum=65536)
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="overlap", group="metadata")


def test_late_namespace_file_refuses(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            assert session.snapshot() == {}
            foreign = ns / "foreign.bin"
            foreign.write_bytes(b"nope")
            os.chmod(foreign, 0o600)
            session.verify()
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="set_changed")


def test_late_request_json_refuses(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            (ns / "request.json").write_bytes(b"{}\n")
            os.chmod(ns / "request.json", 0o600)
            session.snapshot()
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_installed_file_then_tamper_refuses(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            assert session.install("request.json", b"first\n") is False
            target = checkout / ".work" / "b1" / "code-evidence-v1" / "request.json"
            keep = _replace_keep_alive(target, b"wrong\n")
            try:
                session.snapshot()
            finally:
                os.close(keep)
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_failed_install_blocks_views(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RuntimeError, match="parent boom"):
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)

            def boom(_name):
                raise RuntimeError("parent boom")

            session._ensure_install_parent = boom
            try:
                session.install("request.json", b"{}\n")
            except RuntimeError:
                assert session._install.failed is True
                assert session._install.phase == "idle"
                with pytest.raises(CodeProofIOError) as caught:
                    session.snapshot()
                _assert_io(
                    caught.value,
                    "WORK_PATH_UNSAFE",
                    reason="phase_mismatch",
                    group="installation",
                )
                with pytest.raises(CodeProofIOError):
                    session.layout_state()
                with pytest.raises(CodeProofIOError):
                    session.install("intent.json", b"{}\n")
                raise
    assert not (checkout / ".work" / "b1" / "code-evidence-v1" / "request.json").exists()


def test_second_install_failed_write_cleans_only_second(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_write = io._write
    calls = {"n": 0}

    def wrapped(fd, data):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError(errno.EIO, "write fail")
        return real_write(fd, data)

    monkeypatch.setattr(io, "_write", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            assert session.install("request.json", b"one\n") is False
            session.install("intent.json", b"two\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="write")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert (ns / "request.json").read_bytes() == b"one\n"
    assert not (ns / "intent.json").exists()
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []


def test_finalizer_continues_later_groups(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        calls = []
        orig = session._verify_group_names

        def wrapped(group):
            calls.append(group)
            if group == "checkout":
                raise RuntimeError("group boom")
            return orig(group)

        session._verify_group_names = wrapped
        result = session._finalize(None)
        assert isinstance(result, CodeProofIOError)
        assert result.code == "WORK_PATH_UNSAFE"
        assert "checkout" in calls
        assert "ancestors" in calls
        assert "resources" in calls
        assert "output_layout" in calls
        assert calls.index("checkout") < calls.index("resources")
        assert session._state == "closed"


def test_original_baseexception_identity(checkout: Path) -> None:
    class Boom(BaseException):
        pass

    marker = Boom("same-object")
    with pytest.raises(Boom) as caught:
        with open_code_session(batch_id="b1"):
            raise marker
    assert caught.value is marker


def test_prior_getter_escape_uses_null(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = checkout / "input.json"
    src.write_bytes(b'{"a":1}\n')

    class Hostile(CodeProofIOError):
        def __init__(self, wrapped):
            object.__setattr__(self, "_wrapped", wrapped)

        @property
        def code(self):
            raise RuntimeError("fixture code getter failure")

        @property
        def details(self):
            raise RuntimeError("fixture details getter failure")

        @property
        def message(self):
            return self._wrapped.message

        @property
        def exit_code(self):
            return 2

    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_input("input.json", maximum=65536)
            keep = _replace_keep_alive(src, b'{"a":1}\n')
            try:
                session.verify()
            except CodeProofIOError as original:
                os.close(keep)
                hostile = Hostile(original)
                selected = session._finalize(hostile)
                if selected is not None:
                    raise selected
                raise
    _assert_io(
        caught.value,
        "WORK_PATH_UNSAFE",
        prior_code=None,
        prior_operation=None,
        prior_errno=None,
    )


def test_resource_persistent_missing_overrides_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = _copy_source_layout(tmp_path / "origin")
    profile = origin.parent / "profiles" / "code-proof-v1.json"
    blob = bytearray(profile.read_bytes())
    blob[-1] = 0x20 if blob[-1] == 0x0A else 0x0A
    profile.write_bytes(bytes(blob))
    profile_pin = next(
        pin
        for pin in resource_origin_plan().resources
        if pin.relative_path == "profiles/code-proof-v1.json"
    )
    assert len(profile.read_bytes()) == profile_pin.size_bytes
    monkeypatch.setattr(cpr, "__file__", str(origin))
    checkout = _make_checkout(tmp_path / "co")
    monkeypatch.chdir(checkout)
    real_read = io._read
    later_path = (
        origin.parent.parent.parent
        / "schemas"
        / "video-paper-wiki.code-acquisition-intent.v1.schema.json"
    )
    later_st = later_path.stat()
    removed = {"done": False}

    def wrapped(fd, n):
        data = real_read(fd, n)
        if not removed["done"]:
            try:
                st = os.fstat(fd)
            except OSError:
                st = None
            if (
                st is not None
                and st.st_ino == later_st.st_ino
                and st.st_dev == later_st.st_dev
            ):
                try:
                    profile.unlink()
                except FileNotFoundError:
                    pass
                removed["done"] = True
        return data

    monkeypatch.setattr(io, "_read", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(
        caught.value,
        "WORK_PATH_UNSAFE",
        group="resources",
        reason="missing",
    )
    assert caught.value.details["prior_code"] == "CODE_PROOF_RESOURCE_INVALID"


def test_source_and_installed_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _copy_source_layout(tmp_path / "src-origin")
    monkeypatch.setattr(cpr, "__file__", str(source))
    checkout = _make_checkout(tmp_path / "co")
    monkeypatch.chdir(checkout)
    with open_code_session(batch_id="b1") as session:
        assert session.profile_sha256 == (
            "650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32"
        )
    installed = _copy_installed_layout(tmp_path / "inst-origin")
    monkeypatch.setattr(cpr, "__file__", str(installed))
    with open_code_session(batch_id="b2") as session:
        session.set_output_limits(_HARD_OUTPUT)
        assert session.install("request.json", b"{}\n") is False


def test_reverse_close_lock_dup_last(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = []
    real = io._close

    def wrapped(fd):
        closed.append(fd)
        return real(fd)

    monkeypatch.setattr(io, "_close", wrapped)
    with open_code_session(batch_id="b1") as session:
        order = list(session._fd_order)
        dup = session._lock_dup_fd
        assert dup not in order
    assert closed == list(reversed(order)) + [dup]


def test_close_failure_not_retried(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io._close
    seen = []

    def wrapped(fd):
        seen.append(fd)
        if len(seen) == 1:
            raise OSError(errno.EIO, "close fail")
        return real(fd)

    monkeypatch.setattr(io, "_close", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="close")
    assert len(seen) == len(set(seen))


def test_bundle_path_spelling(checkout: Path) -> None:
    with open_code_session(batch_id="b1") as session:
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_bundle_manifest(b".work/x")
        assert caught.value.reason == "type"
        for bad in (
            "work/x",
            ".work/",
            ".work//x",
            ".work/x/",
            ".work/./x",
            ".work/../x",
            ".work/x\\y",
            ".work/x\n",
            "a" * 4097,
        ):
            with pytest.raises(CodeProofIOError) as caught:
                session.retain_bundle_manifest(bad)
            _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="path_spelling")
        nfc = ".work/" + "e\u0301"
        with pytest.raises(CodeProofIOError) as caught:
            session.retain_bundle_manifest(nfc)
        _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="path_spelling")


def test_bundle_raw_root_and_objects_replacement(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    (raw / "manifest.json").write_bytes(b"{}\n")
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_bundle_manifest(".work/raw")
            (raw / "foreign.bin").write_bytes(b"x")
            session.verify()
    _assert_io(caught.value, "WORK_PATH_UNSAFE")
    raw2 = checkout / ".work" / "raw2"
    objects = raw2 / "objects"
    objects.mkdir(parents=True)
    (raw2 / "manifest.json").write_bytes(b"{}\n")
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_bundle_manifest(".work/raw2")
            aside = checkout / ".work" / "objects-aside"
            os.rename(objects, aside)
            replacement = raw2 / "objects"
            replacement.mkdir()
            session.verify()
    _assert_io(caught.value, "WORK_PATH_UNSAFE")
    assert aside.is_dir()
    assert replacement.is_dir()


def test_bundle_inventory_closure_and_order(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    (raw / "manifest.json").write_bytes(b"{}\n")
    (objects / (_OID_A + ".body")).write_bytes(b"a")
    (objects / (_OID_B + ".body")).write_bytes(b"b")
    rec_a = _object_record(_OID_A, b"a")
    rec_b = _object_record(_OID_B, b"b")
    with open_code_session(batch_id="b1") as session:
        session.retain_bundle_manifest(".work/raw")
        extra = dict(rec_a)
        extra["nope"] = 1
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[extra],
                limits=_HARD_GIT,
            )
        assert caught.value.reason == "shape"
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[rec_b, rec_a],
                limits=_HARD_GIT,
            )
        assert caught.value.reason == "shape"
        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[rec_a, rec_a],
                limits=_HARD_GIT,
            )
        assert caught.value.reason == "shape"

        class HostileDict(dict):
            def __getitem__(self, key):
                raise AssertionError("getitem")

        with pytest.raises(CodeProofStructureError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[HostileDict(rec_a)],
                limits=_HARD_GIT,
            )
        assert caught.value.reason == "type"
        opened = []
        real_open = io._open

        def tracking(path, flags, *args, **kwargs):
            if isinstance(path, str) and path.endswith(".body"):
                opened.append(path)
            return real_open(path, flags, *args, **kwargs)

        # no body open on extra-key refusal already asserted
        bodies = session.retain_bundle_bodies(
            object_format="sha1",
            objects=[rec_a, rec_b],
            limits=_HARD_GIT,
        )
        assert list(bodies) == [_OID_A, _OID_B]
        assert bodies[_OID_A] == b"a"
        bodies[_OID_A] = b"mut"
        rec_a["oid"] = "mutated"
        assert session._bundle_bodies[_OID_A] == b"a"


def test_bundle_reconciliation_width_extra_missing(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    (raw / "manifest.json").write_bytes(b"{}\n")
    (objects / (_OID_A + ".body")).write_bytes(b"a")
    (objects / (_OID64_A + ".body")).write_bytes(b"z")
    rec_a = _object_record(_OID_A, b"a")
    rec64 = _object_record(_OID64_A, b"z")
    rec64["oid"] = _OID64_A
    with open_code_session(batch_id="b1") as session:
        session.retain_bundle_manifest(".work/raw")
        opens = []
        real = io._open

        def tracking(path, flags, *args, **kwargs):
            if isinstance(path, str) and path.endswith(".body"):
                opens.append(path)
            return real(path, flags, *args, **kwargs)

        io._open = tracking
        try:
            with pytest.raises(CodeGitProofError) as caught:
                session.retain_bundle_bodies(
                    object_format="sha1",
                    objects=[rec_a],
                    limits=_HARD_GIT,
                )
            assert caught.value.code == CODE_PROOF_INPUT_INVALID
            assert caught.value.message == "code git proof input is invalid"
            assert caught.value.details == {
                "instance_pointer": "/bodies",
                "reason": "invalid_oid_key",
            }
            assert caught.value.exit_code == 2
            assert opens == []
        finally:
            io._open = real
    raw2 = checkout / ".work" / "raw2"
    objs = raw2 / "objects"
    objs.mkdir(parents=True)
    (raw2 / "manifest.json").write_bytes(b"{}\n")
    (objs / (_OID_A + ".body")).write_bytes(b"a")
    (objs / (_OID_B + ".body")).write_bytes(b"b")
    with open_code_session(batch_id="b1") as session:
        session.retain_bundle_manifest(".work/raw2")
        rec_only_a = _object_record(_OID_A, b"a")
        with pytest.raises(CodeGitProofError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[rec_only_a],
                limits=_HARD_GIT,
            )
        assert caught.value.code == CODE_PROOF_OBJECT_EXTRA
        assert caught.value.message == "undeclared git object bodies were supplied"
        assert caught.value.details == {
            "instance_pointer": "/bodies",
            "extra_oids": [_OID_B],
        }
    raw3 = checkout / ".work" / "raw3"
    objs = raw3 / "objects"
    objs.mkdir(parents=True)
    (raw3 / "manifest.json").write_bytes(b"{}\n")
    (objs / (_OID_A + ".body")).write_bytes(b"a")
    with open_code_session(batch_id="b1") as session:
        session.retain_bundle_manifest(".work/raw3")
        with pytest.raises(CodeGitProofError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[_object_record(_OID_A, b"a"), _object_record(_OID_B, b"b")],
                limits=_HARD_GIT,
            )
        assert caught.value.code == CODE_PROOF_OBJECT_UNAVAILABLE
        assert caught.value.message == "required git object is unavailable"
        assert caught.value.details == {
            "instance_pointer": "/bodies",
            "missing_oids": [_OID_B],
        }


def test_bundle_count_cap_before_width(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    (raw / "manifest.json").write_bytes(b"{}\n")
    (objects / (_OID_A + ".body")).write_bytes(b"a")
    (objects / (_OID_B + ".body")).write_bytes(b"b")
    lowered = dict(_HARD_GIT)
    lowered["max_objects"] = 1
    with open_code_session(batch_id="b1") as session:
        session.retain_bundle_manifest(".work/raw")
        with pytest.raises(CodeProofIOError) as caught:
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[_object_record(_OID_A, b"a")],
                limits=lowered,
            )
        _assert_io(
            caught.value,
            "CODE_PROOF_LIMIT_EXCEEDED",
            instance_pointer="/bodies",
            limit_name="max_objects",
            limit=1,
            observed=2,
        )


def test_peak_c_plus_two_n(checkout: Path) -> None:
    limits = dict(_HARD_OUTPUT)
    limits["max_output_peak_bytes"] = 9
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(limits)
            session.install("request.json", b"12345")
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/output",
        limit_name="max_output_peak_bytes",
        limit=9,
        observed=10,
    )
    limits["max_output_peak_bytes"] = 10
    with open_code_session(batch_id="b2") as session:
        session.set_output_limits(limits)
        assert session.install("request.json", b"12345") is False
        with pytest.raises(CodeProofIOError) as caught:
            session.install("intent.json", b"abcd")
        _assert_io(
            caught.value,
            "CODE_PROOF_LIMIT_EXCEEDED",
            instance_pointer="/output",
            limit_name="max_output_peak_bytes",
            limit=10,
            observed=13,
        )


def test_mkdir_raise_after_create_is_late_arrival(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io._mkdir

    def wrapped(name, mode, dir_fd=None):
        real(name, mode, dir_fd=dir_fd)
        raise OSError(errno.EIO, "created-then-raise")

    monkeypatch.setattr(io, "_mkdir", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="late_arrival")
    assert (checkout / ".work").is_dir()


def test_zero_write(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(io, "_write", lambda fd, data: 0)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", reason="zero_write", operation="write")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []
    assert not (ns / "request.json").exists()


def test_link_failure_before_effect(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise OSError(errno.EIO, "link fail")

    monkeypatch.setattr(io, "_link", boom)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="link")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert not (ns / "request.json").exists()
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []


def test_foreign_final_not_adopted(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = io._link

    def wrapped(*args, **kwargs):
        ns = Path(os.getcwd()) / ".work" / "b1" / "code-evidence-v1"
        (ns / "request.json").write_bytes(b"foreign\n")
        os.chmod(ns / "request.json", 0o600)
        raise OSError(errno.EEXIST, "exists")

    monkeypatch.setattr(io, "_link", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "WORK_PATH_UNSAFE")
    assert caught.value.details["reason"] in {"late_arrival", "set_changed"}
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert (ns / "request.json").read_bytes() == b"foreign\n"


def test_input_replacement_during_read_is_lineage(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = checkout / "input.json"
    src.write_bytes(b"hello-world\n")
    real = io._read
    keep = {"fd": None}

    def wrapped(fd, n):
        if keep["fd"] is None:
            keep["fd"] = _replace_keep_alive(src, b"hello-world\n")
            raise OSError(errno.EIO, "read fail")
        return real(fd, n)

    monkeypatch.setattr(io, "_read", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_input("input.json", maximum=65536)
    if keep["fd"] is not None:
        os.close(keep["fd"])
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_later_arrival_of_missing_work(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            assert session.snapshot() == {}
            (checkout / ".work").mkdir()
            session.verify()
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_unknown_namespace_entry(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    (ns / "nope.bin").write_bytes(b"x")
    os.chmod(ns / "nope.bin", 0o600)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unknown_entry")


def test_cwd_change_does_not_redirect(checkout: Path, tmp_path: Path) -> None:
    other = _make_checkout(tmp_path / "other")
    with open_code_session(batch_id="b1") as session:
        os.chdir(other)
        session.set_output_limits(_HARD_OUTPUT)
        session.install("request.json", b"{}\n")
    os.chdir(checkout)
    assert (checkout / ".work" / "b1" / "code-evidence-v1" / "request.json").is_file()
    assert not (other / ".work").exists()


def test_error_context_rejects_bad_construction() -> None:
    with pytest.raises(ValueError, match="Invalid CODE I/O error context"):
        CodeProofIOError("NOPE", {})
    with pytest.raises(ValueError, match="Invalid CODE I/O error context"):
        CodeProofIOError("WORK_PATH_UNSAFE", {"reason": "missing"})


def test_zero_egress_during_session(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_a, **_k):
        raise AssertionError(_MARKER)

    monkeypatch.setattr(socket, "socket", blocked)
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        session.install("request.json", b"{}\n")
        session.snapshot()


def test_family_install_and_layout(checkout: Path) -> None:
    name = "configs/" + ("ab" * 32) + ".json"
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        assert session.install("request.json", b"{}\n") is False
        assert session.install(name, b'{"c":1}\n') is False
        state = session.layout_state()
        assert state["current_families"]["configs"] is True
        assert name in state["current_files"]
        assert name not in state["initial_files"]
    path = checkout / ".work" / "b1" / "code-evidence-v1" / "configs" / (("ab" * 32) + ".json")
    assert path.read_bytes() == b'{"c":1}\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_short_write_cadence(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = io._write
    reads = {"n": 0}
    real_read = io._read

    def one_byte(fd, data):
        if not data:
            return real(fd, data)
        return real(fd, data[:1])

    def counting(fd, n):
        reads["n"] += 1
        return real_read(fd, n)

    monkeypatch.setattr(io, "_write", one_byte)
    monkeypatch.setattr(io, "_read", counting)
    payload = b"abcdef"
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        before = reads["n"]
        session.install("request.json", payload)
        after = reads["n"]
    assert after - before < 200
    assert (checkout / ".work" / "b1" / "code-evidence-v1" / "request.json").read_bytes() == payload


def test_namespace_cap_plus_one(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    for name in ("request.json", "intent.json", "bundle.json", "observation.json"):
        (ns / name).write_bytes(b"{}\n")
        os.chmod(ns / name, 0o600)
    for family in ("objects", "configs", "handoffs"):
        d = ns / family
        d.mkdir()
        os.chmod(d, 0o700)
    extra = ns / "extra.bin"
    extra.write_bytes(b"x")
    os.chmod(extra, 0o600)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unknown_entry")


def test_symlink_slot_refused(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    target = checkout / "other.json"
    target.write_bytes(b"{}\n")
    os.symlink(target, ns / "request.json")
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unsafe_type")


def test_late_object_body_refuses(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    objs = ns / "objects"
    objs.mkdir(parents=True)
    os.chmod(ns, 0o700)
    os.chmod(objs, 0o700)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            body = objs / (_OID_A + ".body")
            body.write_bytes(b"x")
            os.chmod(body, 0o600)
            session.verify()
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_keyboard_interrupt_identity(checkout: Path) -> None:
    marker = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as caught:
        with open_code_session(batch_id="b1"):
            raise marker
    assert caught.value is marker


def test_file_fsync_failure(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = io._fsync

    def wrapped(fd):
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode):
            raise OSError(errno.EIO, "file fsync")
        return real(fd)

    monkeypatch.setattr(io, "_fsync", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="fsync")


def test_setter_lowers_retained_file(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o700)
    (ns / "request.json").write_bytes(b"x" * 100)
    os.chmod(ns / "request.json", 0o600)
    lowered = dict(_HARD_OUTPUT)
    lowered["max_request_bytes"] = 50
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(lowered)
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/output",
        limit_name="max_request_bytes",
        limit=50,
        observed=100,
    )


def test_bundle_overlap_output(checkout: Path) -> None:
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_bundle_manifest(".work/b1/code-evidence-v1")
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="overlap", group="bundle")


def test_input_parent_directory_replacement_is_lineage(checkout: Path) -> None:
    parent = checkout / "in_dir"
    parent.mkdir()
    src = parent / "input.json"
    src.write_bytes(b'{"a":1}\n')
    keep = None
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            assert session.retain_input("in_dir/input.json", maximum=65536) == b'{"a":1}\n'
            keep = os.open(parent, os.O_RDONLY)
            aside = checkout / "in_dir_aside"
            os.rename(parent, aside)
            parent.mkdir()
            (parent / "input.json").write_bytes(b'{"a":1}\n')
            session.verify()
    if keep is not None:
        os.close(keep)
    _assert_io(caught.value, "WORK_PATH_UNSAFE")


def test_existing_namespace_requires_0700(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    ns.mkdir(parents=True)
    os.chmod(ns, 0o755)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unsafe_mode")


def test_existing_family_requires_0700(checkout: Path) -> None:
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    fam = ns / "configs"
    ns.mkdir(parents=True)
    fam.mkdir()
    os.chmod(ns, 0o700)
    os.chmod(fam, 0o755)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1"):
            pass
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unsafe_mode")


def test_bundle_manifest_unsafe_mode_on_cached_observe(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    man = raw / "manifest.json"
    man.write_bytes(b"{}\n")
    os.chmod(man, 0o666)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_bundle_manifest(".work/raw")
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="unsafe_mode")


def test_body_total_budget_charges_actual_bytes(checkout: Path) -> None:
    raw = checkout / ".work" / "raw"
    objects = raw / "objects"
    objects.mkdir(parents=True)
    (raw / "manifest.json").write_bytes(b"{}\n")
    body_a = b"a" * 10
    body_b = b"b" * 10
    (objects / (_OID_A + ".body")).write_bytes(body_a)
    (objects / (_OID_B + ".body")).write_bytes(body_b)
    rec_a = _object_record(_OID_A, body_a)
    rec_b = _object_record(_OID_B, body_b)
    rec_a["body_size_bytes"] = 1
    rec_b["body_size_bytes"] = 1
    lowered = dict(_HARD_GIT)
    lowered["max_total_object_bytes"] = 15
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.retain_bundle_manifest(".work/raw")
            session.retain_bundle_bodies(
                object_format="sha1",
                objects=[rec_a, rec_b],
                limits=lowered,
            )
    _assert_io(
        caught.value,
        "CODE_PROOF_LIMIT_EXCEEDED",
        instance_pointer="/objects",
        limit_name="max_total_object_bytes",
        limit=15,
        observed=20,
    )


def test_unlink_failure_before_effect(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_k):
        raise OSError(errno.EIO, "unlink fail")

    monkeypatch.setattr(io, "_unlink", boom)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="unlink")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert (ns / "request.json").read_bytes() == b"{}\n"
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover != []


def test_unlink_failure_after_effect(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io._unlink

    def wrapped(*args, **kwargs):
        real(*args, **kwargs)
        raise OSError(errno.EIO, "unlinked-then-raise")

    monkeypatch.setattr(io, "_unlink", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="unlink")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert (ns / "request.json").read_bytes() == b"{}\n"
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        assert session.install("request.json", b"{}\n") is True


def test_cleanup_requires_identity_before_unlink(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_unlink = io._unlink
    seen = {"n": 0}

    def wrapped(*args, **kwargs):
        seen["n"] += 1
        return real_unlink(*args, **kwargs)

    monkeypatch.setattr(io, "_unlink", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            session.set_output_limits(_HARD_OUTPUT)

            def clearing(fd, data):
                session._install.temp_node = None
                session._install.temp_fd = None
                raise OSError(errno.EIO, "write fail")

            monkeypatch.setattr(io, "_write", clearing)
            session.install("request.json", b"{}\n")
    assert seen["n"] == 0
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover != []
    _assert_io(caught.value, "WORK_PATH_UNSAFE", reason="temp_ownership_lost")


def test_directory_fsync_failure_after_cleaned_then_reentry(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io._fsync
    with pytest.raises(CodeProofIOError) as caught:
        with open_code_session(batch_id="b1") as session:
            def wrapped(fd):
                if session._install.phase == "cleaned" and stat.S_ISDIR(
                    os.fstat(fd).st_mode
                ):
                    raise OSError(errno.EIO, "dir fsync after cleaned")
                return real(fd)

            monkeypatch.setattr(io, "_fsync", wrapped)
            session.set_output_limits(_HARD_OUTPUT)
            session.install("request.json", b"{}\n")
    _assert_io(caught.value, "CODE_PROOF_IO_ERROR", operation="fsync")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    assert (ns / "request.json").read_bytes() == b"{}\n"
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []
    monkeypatch.setattr(io, "_fsync", real)
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(_HARD_OUTPUT)
        assert session.install("request.json", b"{}\n") is True


def test_keyboard_interrupt_during_close_finishes_remaining(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io._close
    seen = []

    def wrapped(fd):
        seen.append(fd)
        if len(seen) == 1:
            raise KeyboardInterrupt()
        return real(fd)

    monkeypatch.setattr(io, "_close", wrapped)
    with pytest.raises(KeyboardInterrupt):
        with open_code_session(batch_id="b1"):
            pass
    assert len(seen) == len(set(seen))
    assert len(seen) >= 2
