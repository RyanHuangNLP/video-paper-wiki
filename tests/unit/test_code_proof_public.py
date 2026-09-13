"""Unit tests for the public code-evidence workflow."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import (
    JSON_BODY,
    OBSERVED_AT,
    OUTPUT_LIMITS,
    PAPER_ID,
    README_BODY,
    REPO_SAVED,
    SRC_BODY,
    TOML_BODY,
    copy_outputs,
    default_files,
    default_targets,
    dump_json,
    hosting_assertion,
    make_checkout,
    make_repo,
    nested_json_object,
    observe_norm_doc,
    observe_raw_doc,
    public_limits,
    request_doc,
    run_module_cli,
    parse_envelope,
    seal,
    write_bundle,
    write_bytes,
)
from video_paper_wiki import code_proof_io as io
from video_paper_wiki import code_proof_public as public
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.code_proof_io import CodeProofIOError, open_code_session
from video_paper_wiki.code_proof_public import (
    CodeProofPublicError,
    config_code_proof,
    handoff_code_proof,
    observe_code_proof,
    request_code_proof,
    status_code_proof,
)
from video_paper_wiki.jcs import canonicalize


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = make_checkout(tmp_path / "co")
    monkeypatch.chdir(root)
    return root


def _write_request(checkout: Path, repo: dict, **extra) -> Path:
    path = checkout / "request.json"
    write_bytes(path, dump_json(request_doc(repo, extra.pop("targets", default_targets()), **extra)))
    return path


def _write_observe_raw(checkout: Path, repo: dict, **extra) -> Path:
    path = checkout / "observe.json"
    write_bytes(path, dump_json(observe_raw_doc(repo, **extra)))
    return path


def _write_observe_norm(checkout: Path, repo: dict, texts: dict[str, str], **extra) -> Path:
    path = checkout / "observe.json"
    write_bytes(path, dump_json(observe_norm_doc(repo, texts, **extra)))
    return path


def _complete_raw(checkout: Path, object_format: str = "sha1", **req_extra):
    repo = make_repo(object_format, default_files())
    _write_request(checkout, repo, **req_extra)
    result = request_code_proof(input_path="request.json", batch_id="b1")
    rel = write_bundle(checkout, ".work/raw", repo, result["request"])
    _write_observe_raw(checkout, repo, hosting=req_extra.get("hosting"))
    observed = observe_code_proof(
        input_path="observe.json",
        batch_id="b1",
        bundle_dir=rel,
    )
    return repo, result, observed


def test_keyword_only_public_api(checkout: Path) -> None:
    with pytest.raises(TypeError):
        request_code_proof("request.json", "b1")
    with pytest.raises(TypeError):
        status_code_proof("b1")
    with pytest.raises(TypeError):
        handoff_code_proof("b1")


def test_status_empty_creates_nothing(checkout: Path) -> None:
    data = status_code_proof(batch_id="b1")
    assert data["state"] == "empty"
    assert data["next_action"] == "prepare_request"
    assert data["missing"] == []
    assert data["targets"] == []
    assert not (checkout / ".work").exists()


def test_request_observe_status_config_handoff_sha1(checkout: Path) -> None:
    repo, requested, observed = _complete_raw(checkout, "sha1")
    assert requested["already_staged"] is False
    assert requested["request"]["id"].startswith("ce1:code-proof-request:")
    assert [row["path"] for row in requested["acquisition_targets"]] == [
        "config.json",
        "src.py",
    ]
    assert observed["status"]["state"] == "observed"
    assert observed["status"]["next_action"] == "prepare_source_handoff"
    status = status_code_proof(batch_id="b1")
    assert status["state"] == "observed"
    assert status["eligibility"]["source_handoff_eligible"] is True
    again = request_code_proof(input_path="request.json", batch_id="b1")
    assert again["already_staged"] is True
    again_obs = observe_code_proof(
        input_path="observe.json", batch_id="b1", bundle_dir=".work/raw"
    )
    assert again_obs["observation"] == observed["observation"]
    cfg = config_code_proof(path="config.json", config_format="json", batch_id="b1")
    assert cfg["already_staged"] is False
    cfg2 = config_code_proof(path="config.json", config_format="json", batch_id="b1")
    assert cfg2["already_staged"] is True
    _ = repo


def test_config_format_conflict_and_source_only(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    config_code_proof(path="config.json", config_format="json", batch_id="b1")
    with pytest.raises(CodeProofIOError) as caught:
        config_code_proof(path="config.json", config_format="toml", batch_id="b1")
    assert caught.value.code == "CODE_PROOF_CONFLICT"
    assert caught.value.details["reason"] == "config_format_changed"
    copy_outputs(
        "b1",
        "b2",
        ["request.json", "intent.json", "bundle.json", "observation.json"]
        + [
            "objects/" + rec["oid"] + ".body"
            for rec in make_repo("sha1", default_files())["objects"]
        ],
    )
    source = config_code_proof(
        path="config.json", config_format="source-only", batch_id="b2"
    )
    assert source["already_staged"] is False
    files = {"config.toml": (TOML_BODY, False), "src.py": (SRC_BODY, False)}
    repo = make_repo("sha1", files)
    targets = [
        {
            "path": "config.toml",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ]
    write_bytes(checkout / "toml-request.json", dump_json(request_doc(repo, targets)))
    req = request_code_proof(input_path="toml-request.json", batch_id="toml")
    rel = write_bundle(checkout, ".work/rawtoml", repo, req["request"])
    write_bytes(checkout / "toml-observe.json", dump_json(observe_raw_doc(repo)))
    observe_code_proof(
        input_path="toml-observe.json", batch_id="toml", bundle_dir=rel
    )
    parsed = config_code_proof(
        path="config.toml", config_format="toml", batch_id="toml"
    )
    assert parsed["path"] == "config.toml"


def test_handoff_and_sha256_and_normalized(checkout: Path) -> None:
    repo, requested, observed = _complete_raw(checkout, "sha1")
    hand = handoff_code_proof(batch_id="b1")
    assert [row["path"] for row in hand["handoffs"]] == ["config.json", "src.py"]
    assert all(row["source_body_path"].endswith(".body") for row in hand["handoffs"])
    status = status_code_proof(batch_id="b1")
    assert status["next_action"] == "successor_capture"
    again = handoff_code_proof(batch_id="b1")
    assert all(row["already_staged"] is True for row in again["handoffs"])

    repo256 = make_repo("sha256", default_files())
    _write_request(checkout, repo256)
    req = request_code_proof(input_path="request.json", batch_id="sha256")
    rel = write_bundle(checkout, ".work/raw256", repo256, req["request"])
    _write_observe_raw(checkout, repo256)
    obs = observe_code_proof(
        input_path="observe.json", batch_id="sha256", bundle_dir=rel
    )
    assert obs["status"]["state"] == "observed"
    config_code_proof(path="config.json", config_format="source-only", batch_id="sha256")
    handoff_code_proof(batch_id="sha256")

    _write_request(checkout, repo)
    request_code_proof(input_path="request.json", batch_id="norm")
    texts = {"config.json": JSON_BODY.decode("utf-8"), "src.py": SRC_BODY.decode("utf-8")}
    _write_observe_norm(checkout, repo, texts)
    norm = observe_code_proof(input_path="observe.json", batch_id="norm")
    assert norm["status"]["state"] == "observed"
    assert norm["status"]["eligibility"]["source_handoff_eligible"] is False
    assert norm["status"]["next_action"] == "new_request_or_acquisition_required"
    with pytest.raises(CodeProofPublicError) as caught:
        config_code_proof(path="config.json", config_format="json", batch_id="norm")
    assert caught.value.code == "CODE_PROOF_NOT_READY"
    assert caught.value.details["reason"] == "raw_evidence_required"
    with pytest.raises(CodeProofPublicError) as caught:
        handoff_code_proof(batch_id="norm")
    assert caught.value.details["reason"] == "raw_evidence_required"
    _ = requested, observed


def test_six_states_and_prefix_resume(checkout: Path) -> None:
    empty = status_code_proof(batch_id="empty")
    assert empty["state"] == "empty"
    repo, requested, observed = _complete_raw(checkout, "sha1")
    names = [
        "request.json",
        "intent.json",
        "bundle.json",
        "observation.json",
    ]
    for record in make_repo("sha1", default_files())["objects"]:
        names.append("objects/" + record["oid"] + ".body")
    repo = make_repo("sha1", default_files())
    object_names = ["objects/" + rec["oid"] + ".body" for rec in repo["objects"]]
    copy_outputs("b1", "req", ["request.json"])
    st = status_code_proof(batch_id="req")
    assert st["state"] == "requested"
    assert st["missing"] == ["intent.json"]
    assert st["next_action"] == "supply_observation"

    copy_outputs("b1", "pn", ["request.json", "intent.json"])
    # raw intent exists; without bundle this is pending_raw_bundle
    st = status_code_proof(batch_id="pn")
    assert st["state"] == "pending_raw_bundle"
    assert st["missing"] == ["bundle.json", "observation.json"]
    assert st["next_action"] == "resume_same_observation"

    copy_outputs("b1", "pb", ["request.json", "intent.json", "bundle.json"])
    st = status_code_proof(batch_id="pb")
    assert st["state"] == "pending_raw_bodies"
    assert st["missing"][-1] == "observation.json"
    assert st["missing"][0].startswith("objects/")

    copy_outputs(
        "b1",
        "bodies",
        ["request.json", "intent.json", "bundle.json", *object_names],
    )
    st = status_code_proof(batch_id="bodies")
    assert st["state"] == "pending_raw_bodies"
    assert st["missing"] == ["observation.json"]

    _write_observe_raw(checkout, repo)
    resumed = observe_code_proof(
        input_path="observe.json", batch_id="bodies", bundle_dir=".work/raw"
    )
    assert resumed["status"]["state"] == "observed"

    copy_outputs("b1", "obsmiss", ["request.json", "intent.json"])
    write_bytes(checkout / "norm-request.json", dump_json(request_doc(repo, default_targets())))
    request_code_proof(input_path="request.json", batch_id="normp")
    texts = {"config.json": JSON_BODY.decode("utf-8"), "src.py": SRC_BODY.decode("utf-8")}
    _write_observe_norm(checkout, repo, texts)
    observe_code_proof(input_path="observe.json", batch_id="normp")
    copy_outputs("normp", "np", ["request.json", "intent.json"])
    st = status_code_proof(batch_id="np")
    assert st["state"] == "pending_normalized"
    assert st["missing"] == ["observation.json"]
    _ = requested, observed, names


def test_handoff_prefix_and_config_subset(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    ns = Path(".work/b1/code-evidence-v1")
    src = ns / "handoffs"
    # install only first handoff via public then check prefix
    # derive first by installing through public after copying none
    copy_outputs("b1", "pre", ["request.json", "intent.json", "bundle.json", "observation.json"])
    repo = make_repo("sha1", default_files())
    for rec in repo["objects"]:
        copy_outputs("b1", "pre", ["objects/" + rec["oid"] + ".body"])
    first = None
    from video_paper_wiki.code_proof_public import _derive_handoff, _inspect
    from video_paper_wiki.code_proof_io import open_code_session

    limits = {
        "max_request_bytes": 65536,
        "max_intent_bytes": 1048576,
        "max_bundle_bytes": 1048576,
        "max_observation_bytes": 2097152,
        "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072,
        "max_output_peak_bytes": 134217728,
    }
    with open_code_session(batch_id="pre") as session:
        session.set_output_limits(limits)
        view = _inspect(session, "pre")
        env, saved, ref = _derive_handoff(
            batch_id="pre",
            request_data=view["request_data"],
            request_ref=view["request_ref"],
            observation_ref=view["observation_ref"],
            bundle_ref=view["bundle_ref"],
            observation_data=view["observation_data"],
            git_proof=view["git_proof"],
            bodies=view["bodies"],
            path="config.json",
        )
        first = "handoffs/" + __import__("hashlib").sha256(b"config.json").hexdigest() + ".json"
        session.install(first, saved)
    st = status_code_proof(batch_id="pre")
    assert [row["path"] for row in st["handoffs"]] == ["config.json"]
    assert st["next_action"] == "prepare_source_handoff"
    finished = handoff_code_proof(batch_id="pre")
    assert [row["path"] for row in finished["handoffs"]] == ["config.json", "src.py"]
    assert finished["handoffs"][0]["already_staged"] is True
    assert finished["handoffs"][1]["already_staged"] is False

    cfg = config_code_proof(path="config.json", config_format="json", batch_id="pre")
    assert cfg["path"] == "config.json"
    _ = src


def test_mixed_targets_and_hosting(checkout: Path) -> None:
    files = dict(default_files())
    repo = make_repo("sha1", files)
    targets = [
        {
            "path": "config.json",
            "roles": ["configuration"],
            "allow_executable_source": False,
        },
        {
            "path": "missing.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
        {
            "path": "src.py",
            "roles": ["implementation"],
            "allow_executable_source": False,
        },
    ]
    _write_request(checkout, repo, targets=targets)
    req = request_code_proof(input_path="request.json", batch_id="mix")
    rel = write_bundle(checkout, ".work/rawmix", repo, req["request"])
    _write_observe_raw(checkout, repo)
    obs = observe_code_proof(
        input_path="observe.json", batch_id="mix", bundle_dir=rel
    )
    assert obs["status"]["eligibility"]["complete_target_set"] is False
    cfg = config_code_proof(path="config.json", config_format="json", batch_id="mix")
    assert cfg["path"] == "config.json"
    with pytest.raises(CodeProofPublicError) as caught:
        handoff_code_proof(batch_id="mix")
    assert caught.value.code == "CODE_PROOF_TARGET_INELIGIBLE"
    assert caught.value.details["reason"] == "complete_target_set_required"
    assert caught.value.details["blockers"][0]["path"] == "missing.py"

    _write_request(checkout, repo, require_repository_assertion=True)
    req = request_code_proof(input_path="request.json", batch_id="host")
    rel = write_bundle(checkout, ".work/rawhost", repo, req["request"])
    _write_observe_raw(checkout, repo, hosting=None)
    obs = observe_code_proof(
        input_path="observe.json", batch_id="host", bundle_dir=rel
    )
    assert obs["status"]["eligibility"]["repository_requirement_met"] is False
    with pytest.raises(CodeProofPublicError) as caught:
        handoff_code_proof(batch_id="host")
    assert caught.value.details["reason"] == "repository_assertion_required"
    assert caught.value.details["blockers"] == []

    _write_request(checkout, repo, require_repository_assertion=True)
    req = request_code_proof(input_path="request.json", batch_id="host2")
    rel = write_bundle(checkout, ".work/rawhost2", repo, req["request"])
    _write_observe_raw(checkout, repo, hosting=hosting_assertion(repo))
    observe_code_proof(
        input_path="observe.json", batch_id="host2", bundle_dir=rel
    )
    hosted = handoff_code_proof(batch_id="host2")
    assert [row["path"] for row in hosted["handoffs"]] == ["config.json", "src.py"]


def test_changed_request_and_forged_observation(checkout: Path) -> None:
    repo, requested, observed = _complete_raw(checkout, "sha1")
    other = request_doc(repo, default_targets(), repository="other/name")
    write_bytes(checkout / "other.json", dump_json(other))
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="other.json", batch_id="b1")
    assert caught.value.details["reason"] == "request_changed"

    copy_outputs(
        "b1",
        "forge",
        ["request.json", "intent.json", "bundle.json"]
        + ["objects/" + rec["oid"] + ".body" for rec in repo["objects"]],
    )
    ns = Path(".work/b1/code-evidence-v1")
    original = json.loads((ns / "observation.json").read_text())
    original["data"]["targets"][0]["text"]["line_count"] = original["data"]["targets"][0]["text"]["line_count"] + 1
    forged = seal("code-proof-observation", original["data"])
    from video_paper_wiki.code_proof_io import open_code_session

    limits = {
        "max_request_bytes": 65536,
        "max_intent_bytes": 1048576,
        "max_bundle_bytes": 1048576,
        "max_observation_bytes": 2097152,
        "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072,
        "max_output_peak_bytes": 134217728,
    }
    with open_code_session(batch_id="forge") as session:
        session.set_output_limits(limits)
        session.install("observation.json", forged)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="forge")
    assert caught.value.code == "CODE_PROOF_BINDING_MISMATCH"
    assert caught.value.details["reason"] == "derived"
    _ = requested, observed


def test_input_caps_and_peak_preflight(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    doc = request_doc(repo, default_targets())
    raw = dump_json(doc)
    pad = 65536 - len(raw)
    write_bytes(checkout / "cap.json", raw[:-1] + b" " * pad + b"\n")
    request_code_proof(input_path="cap.json", batch_id="cap")
    write_bytes(checkout / "cap1.json", raw[:-1] + b" " * (pad + 1) + b"\n")
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="cap1.json", batch_id="cap1")
    assert caught.value.details["observed"] == 65537
    assert caught.value.details["limit_name"] == "max_request_input_bytes"
    assert not (checkout / ".work" / "cap1").exists()

    huge = checkout / "huge.json"
    huge.write_bytes(b"x" * 200000)
    transferred = {"n": 0}
    from video_paper_wiki import code_proof_io as io

    real = io._read

    def wrapped(fd, n):
        data = real(fd, n)
        transferred["n"] += len(data)
        return data

    monkeypatch.setattr(io, "_read", wrapped)
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="huge.json", batch_id="huge")
    assert caught.value.details["observed"] == 65537
    assert caught.value.details["limit_name"] == "max_request_input_bytes"

    hard = {
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
            "max_output_peak_bytes": 4000,
        },
    }
    _write_request(checkout, repo, limits=hard)
    request_code_proof(input_path="request.json", batch_id="peak")
    texts = {"config.json": JSON_BODY.decode("utf-8"), "src.py": SRC_BODY.decode("utf-8")}
    _write_observe_norm(checkout, repo, texts)
    before = list((checkout / ".work" / "peak" / "code-evidence-v1").iterdir())
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(input_path="observe.json", batch_id="peak")
    assert caught.value.details["limit_name"] == "max_output_peak_bytes"
    after = list((checkout / ".work" / "peak" / "code-evidence-v1").iterdir())
    assert sorted(p.name for p in before) == sorted(p.name for p in after)
    assert not (checkout / ".work" / "peak" / "code-evidence-v1" / "intent.json").exists()


def test_status_zero_write_and_zero_egress(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    data = status_code_proof(batch_id="b1")
    assert data["state"] == "empty"
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    request_code_proof(input_path="request.json", batch_id="eg")
    ns = checkout / ".work" / "eg" / "code-evidence-v1"
    before = {p.name: p.stat().st_mtime_ns for p in ns.iterdir()}
    status_code_proof(batch_id="eg")
    after = {p.name: p.stat().st_mtime_ns for p in ns.iterdir()}
    assert before == after


def test_cli_help_and_usage(capsys) -> None:
    parser = build_parser()
    text = parser.format_help()
    assert "code-evidence" in text
    leaves = {
        action.dest: action.choices
        for action in parser._actions
        if getattr(action, "choices", None) and "code-evidence" in str(action.choices)
    }
    assert leaves
    code = main(["code-evidence", "request"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 2
    assert payload["error"]["code"] == "USAGE"
    assert payload["command"] == "code-evidence.request"


def test_bundle_required_and_forbidden(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    request_code_proof(input_path="request.json", batch_id="b1")
    _write_observe_raw(checkout, repo)
    with pytest.raises(CodeProofPublicError) as caught:
        observe_code_proof(input_path="observe.json", batch_id="b1")
    assert caught.value.details["reason"] == "shape"
    texts = {"config.json": JSON_BODY.decode("utf-8"), "src.py": SRC_BODY.decode("utf-8")}
    _write_observe_norm(checkout, repo, texts)
    write_bundle(
        checkout,
        ".work/raw",
        repo,
        request_code_proof(input_path="request.json", batch_id="b1")["request"],
    )
    with pytest.raises(CodeProofPublicError) as caught:
        observe_code_proof(
            input_path="observe.json", batch_id="b1", bundle_dir=".work/raw"
        )
    assert caught.value.details["reason"] == "shape"


def test_json_invalid_before_decode(checkout: Path) -> None:
    write_bytes(checkout / "bad.json", b"\xef\xbb\xbf{}")
    with pytest.raises(CodeProofPublicError) as caught:
        request_code_proof(input_path="bad.json", batch_id="b1")
    assert caught.value.code == "CODE_PROOF_JSON_INVALID"
    assert caught.value.details["reason"] == "bom"


def test_nonprefix_handoffs(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    repo = make_repo("sha1", default_files())
    copy_outputs(
        "b1",
        "np",
        ["request.json", "intent.json", "bundle.json", "observation.json"]
        + ["objects/" + rec["oid"] + ".body" for rec in repo["objects"]],
    )
    from video_paper_wiki.code_proof_io import open_code_session
    from video_paper_wiki.code_proof_public import _derive_handoff, _inspect
    import hashlib

    limits = {
        "max_request_bytes": 65536,
        "max_intent_bytes": 1048576,
        "max_bundle_bytes": 1048576,
        "max_observation_bytes": 2097152,
        "max_config_document_bytes": 2097152,
        "max_handoff_bytes": 131072,
        "max_output_peak_bytes": 134217728,
    }
    with open_code_session(batch_id="np") as session:
        session.set_output_limits(limits)
        view = _inspect(session, "np")
        _env, saved, _ref = _derive_handoff(
            batch_id="np",
            request_data=view["request_data"],
            request_ref=view["request_ref"],
            observation_ref=view["observation_ref"],
            bundle_ref=view["bundle_ref"],
            observation_data=view["observation_data"],
            git_proof=view["git_proof"],
            bodies=view["bodies"],
            path="src.py",
        )
        name = "handoffs/" + hashlib.sha256(b"src.py").hexdigest() + ".json"
        session.install(name, saved)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="np")
    assert caught.value.details["reason"] == "nonprefix_handoffs"


def _replace_keep_alive(path: Path, data: bytes) -> int:
    fd = os.open(path, os.O_RDONLY)
    sibling = path.parent / (path.name + ".repl")
    sibling.write_bytes(data)
    os.rename(sibling, path)
    return fd


def _dir_bytes(path: Path) -> dict[str, bytes]:
    if not path.exists():
        return {}
    out = {}
    for current, _dirs, files in os.walk(path):
        rel_dir = os.path.relpath(current, path)
        for name in files:
            rel = name if rel_dir == "." else rel_dir + "/" + name
            out[rel] = Path(current, name).read_bytes()
    return out


def test_tampered_pending_body_refuses(checkout: Path) -> None:
    repo, _requested, _observed = _complete_raw(checkout, "sha1")
    copy_outputs("b1", "tamper", ["request.json", "intent.json", "bundle.json"])
    bundle = json.loads(
        (Path(".work/b1/code-evidence-v1") / "bundle.json").read_bytes()
    )
    first_oid = bundle["data"]["objects"][0]["oid"]
    with open_code_session(batch_id="tamper") as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        session.install("objects/" + first_oid + ".body", b"tampered-body\n")
    ns = checkout / ".work" / "tamper" / "code-evidence-v1"
    before = _dir_bytes(ns)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="tamper")
    assert caught.value.code == "CODE_PROOF_BINDING_MISMATCH"
    assert caught.value.details["reason"] == "raw_body"
    assert _dir_bytes(ns) == before


def test_resealed_reordered_targets_refuses(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    env = json.loads(
        (Path(".work/b1/code-evidence-v1") / "request.json").read_bytes()
    )
    data = dict(env["data"])
    data["targets"] = list(reversed(data["targets"]))
    forged = seal("code-proof-request", data)
    with open_code_session(batch_id="reorder") as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        session.install("request.json", forged)
    ns = checkout / ".work" / "reorder" / "code-evidence-v1"
    before = _dir_bytes(ns)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="reorder")
    assert caught.value.code == "CODE_PROOF_DOCUMENT_INVALID"
    assert caught.value.details["reason"] == "target_order"
    assert _dir_bytes(ns) == before
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    with pytest.raises(CodeProofPublicError) as caught:
        request_code_proof(input_path="request.json", batch_id="reorder")
    assert caught.value.code == "CODE_PROOF_DOCUMENT_INVALID"
    assert caught.value.details["reason"] == "target_order"
    assert not (ns / "intent.json").exists()
    assert _dir_bytes(ns) == before


def test_orphan_intent_request_refuses_without_new_output(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    with open_code_session(batch_id="orphan") as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        session.install("intent.json", seal("code-acquisition-intent", {
            "request": {"id": "ce1:code-proof-request:" + "a" * 64, "sha256": "b" * 64},
            "mode": "git_objects",
            "acquisition": observe_raw_doc(repo),
            "bundle": None,
        }))
    ns = checkout / ".work" / "orphan" / "code-evidence-v1"
    before = _dir_bytes(ns)
    with pytest.raises(CodeProofPublicError) as caught:
        request_code_proof(input_path="request.json", batch_id="orphan")
    assert caught.value.code == "CODE_PROOF_STATE_INVALID"
    assert caught.value.details["reason"] == "missing_dependency"
    assert not (ns / "request.json").exists()
    assert _dir_bytes(ns) == before


def test_observation_without_intent_is_missing_dependency(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    copy_outputs("b1", "obsorphan", ["request.json", "observation.json"])
    ns = checkout / ".work" / "obsorphan" / "code-evidence-v1"
    before = _dir_bytes(ns)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="obsorphan")
    assert caught.value.code == "CODE_PROOF_STATE_INVALID"
    assert caught.value.details["reason"] == "missing_dependency"
    assert _dir_bytes(ns) == before


def test_leading_whitespace_json_is_accepted(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    raw = dump_json(request_doc(repo, default_targets()))
    write_bytes(checkout / "ws.json", b"\n\t " + raw)
    result = request_code_proof(input_path="ws.json", batch_id="ws")
    assert result["already_staged"] is False
    assert result["request"]["id"].startswith("ce1:code-proof-request:")


def test_deep_nested_json_is_structured_depth_reject(checkout: Path) -> None:
    write_bytes(checkout / "deep.json", nested_json_object(80))
    with pytest.raises(CodeProofPublicError) as caught:
        request_code_proof(input_path="deep.json", batch_id="deep")
    assert caught.value.code == "CODE_PROOF_JSON_INVALID"
    assert caught.value.details["reason"] == "depth"
    assert not (checkout / ".work" / "deep").exists()


def test_recursion_error_is_structured_depth_reject(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    real_parse = public._parse_json_bytes
    real_raw = json.JSONDecoder.raw_decode

    def boom(self, s, idx=0):
        raise RecursionError("fixture decoder recursion")

    def wrapped(payload, pointer):
        monkeypatch.setattr(json.JSONDecoder, "raw_decode", boom)
        try:
            return real_parse(payload, pointer)
        finally:
            monkeypatch.setattr(json.JSONDecoder, "raw_decode", real_raw)

    monkeypatch.setattr(public, "_parse_json_bytes", wrapped)
    with pytest.raises(CodeProofPublicError) as caught:
        request_code_proof(input_path="request.json", batch_id="rec")
    assert caught.value.code == "CODE_PROOF_JSON_INVALID"
    assert caught.value.details["reason"] == "depth"
    assert not (checkout / ".work" / "rec" / "code-evidence-v1" / "request.json").exists()
    code = main(
        [
            "code-evidence",
            "request",
            "--input",
            "request.json",
            "--batch-id",
            "rec2",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "RecursionError" not in captured.err
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["error"]["code"] == "CODE_PROOF_JSON_INVALID"
    assert payload["error"]["details"]["reason"] == "depth"


def test_config_non_ascii_path_is_structured_reject(checkout: Path, capsys) -> None:
    _complete_raw(checkout, "sha1")
    with pytest.raises(CodeProofPublicError) as caught:
        config_code_proof(path="配置.json", config_format="json", batch_id="b1")
    assert caught.value.code == "CODE_PROOF_DOCUMENT_INVALID"
    assert caught.value.details["reason"] == "path"
    code = main(
        [
            "code-evidence",
            "config",
            "--path",
            "配置.json",
            "--format",
            "json",
            "--batch-id",
            "b1",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "UnicodeEncodeError" not in captured.err
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["command"] == "code-evidence.config"
    assert payload["error"]["code"] == "CODE_PROOF_DOCUMENT_INVALID"
    assert payload["error"]["details"]["reason"] == "path"


def test_changed_commit_file_and_config(checkout: Path) -> None:
    repo, requested, _observed = _complete_raw(checkout, "sha1")
    ns = checkout / ".work" / "b1" / "code-evidence-v1"
    original = (ns / "request.json").read_bytes()
    other = request_doc(repo, default_targets())
    other["commit_oid"] = "a" * 40
    write_bytes(checkout / "commit.json", dump_json(other))
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="commit.json", batch_id="b1")
    assert caught.value.code == "CODE_PROOF_CONFLICT"
    assert caught.value.details["reason"] == "request_changed"
    assert (ns / "request.json").read_bytes() == original

    files = request_doc(
        repo,
        [
            {
                "path": "src.py",
                "roles": ["implementation"],
                "allow_executable_source": False,
            }
        ],
    )
    write_bytes(checkout / "files.json", dump_json(files))
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="files.json", batch_id="b1")
    assert caught.value.details["reason"] == "request_changed"
    assert (ns / "request.json").read_bytes() == original

    _write_observe_raw(checkout, repo)
    changed = observe_raw_doc(repo)
    changed["observed_at"] = "2026-01-02T03:04:06Z"
    write_bytes(checkout / "obs-changed.json", dump_json(changed))
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(
            input_path="obs-changed.json",
            batch_id="b1",
            bundle_dir=".work/raw",
        )
    assert caught.value.details["reason"] == "acquisition_changed"
    assert (ns / "observation.json").exists()

    config_code_proof(path="config.json", config_format="json", batch_id="b1")
    cfg_name = "configs/" + hashlib.sha256(b"config.json").hexdigest() + ".json"
    original_cfg = (ns / cfg_name).read_bytes()
    original_data = json.loads(original_cfg)["data"]
    assert original_data["raw_body"]["path"].startswith(".work/b1/")
    control_status = status_code_proof(batch_id="b1")
    assert control_status["state"] == "observed"
    control_cfg = config_code_proof(
        path="config.json", config_format="json", batch_id="b1"
    )
    assert control_cfg["already_staged"] is True
    assert (ns / cfg_name).read_bytes() == original_cfg

    mutated = json.loads(original_cfg)
    value_changes = 0
    for node in mutated["data"]["result"]["nodes"]:
        if node.get("value") == "demo":
            node["value"] = "other"
            value_changes += 1
    assert value_changes == 1
    assert mutated["data"]["raw_body"] == original_data["raw_body"]
    assert mutated["data"]["blob_oid"] == original_data["blob_oid"]
    assert mutated["data"]["path"] == original_data["path"]
    assert mutated["data"]["format"] == original_data["format"]
    forged_cfg = seal("code-config-evidence", mutated["data"])
    assert forged_cfg != original_cfg
    assert json.loads(forged_cfg)["data"]["raw_body"] == original_data["raw_body"]

    (ns / cfg_name).unlink()
    with open_code_session(batch_id="b1") as session:
        session.set_output_limits(dict(OUTPUT_LIMITS))
        session.install(cfg_name, forged_cfg)
    before_cfg = _dir_bytes(ns)
    with pytest.raises(CodeProofPublicError) as caught:
        status_code_proof(batch_id="b1")
    assert caught.value.code == "CODE_PROOF_BINDING_MISMATCH"
    assert caught.value.details["reason"] == "derived"
    assert caught.value.details["instance_pointer"] == "/config"
    assert _dir_bytes(ns) == before_cfg
    with pytest.raises(CodeProofPublicError) as caught:
        config_code_proof(path="config.json", config_format="json", batch_id="b1")
    assert caught.value.code == "CODE_PROOF_BINDING_MISMATCH"
    assert caught.value.details["reason"] == "derived"
    assert caught.value.details["instance_pointer"] == "/config"
    assert _dir_bytes(ns) == before_cfg
    assert (ns / cfg_name).read_bytes() == forged_cfg
    _ = requested


def test_public_input_replacement_refuses(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    src = _write_request(checkout, repo)
    original = src.read_bytes()
    src_st = src.stat()
    keep = {"fd": None}
    real = io._read

    def wrapped(fd, n):
        data = real(fd, n)
        try:
            st = os.fstat(fd)
        except OSError:
            return data
        if (
            keep["fd"] is None
            and st.st_ino == src_st.st_ino
            and st.st_dev == src_st.st_dev
        ):
            keep["fd"] = _replace_keep_alive(src, original)
            raise OSError(errno.EIO, "read fail")
        return data

    monkeypatch.setattr(io, "_read", wrapped)
    try:
        with pytest.raises(CodeProofIOError) as caught:
            request_code_proof(input_path="request.json", batch_id="repl")
        assert caught.value.code == "WORK_PATH_UNSAFE"
    finally:
        if keep["fd"] is None:
            pass
        else:
            os.close(keep["fd"])
    ns = checkout / ".work" / "repl" / "code-evidence-v1"
    assert not (ns / "request.json").exists()


def test_public_install_fail_zero_write(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)

    def boom(_fd, _data):
        raise OSError(errno.EIO, "write fail")

    monkeypatch.setattr(io, "_write", boom)
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="request.json", batch_id="wfail")
    assert caught.value.code == "CODE_PROOF_IO_ERROR"
    ns = checkout / ".work" / "wfail" / "code-evidence-v1"
    assert not (ns / "request.json").exists()
    if ns.exists():
        leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
        assert leftover == []


def test_public_observe_install_fail_keeps_request(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    result = request_code_proof(input_path="request.json", batch_id="ofail")
    rel = write_bundle(checkout, ".work/raw-ofail", repo, result["request"])
    _write_observe_raw(checkout, repo)
    ns = checkout / ".work" / "ofail" / "code-evidence-v1"
    before = _dir_bytes(ns)

    def boom(_fd, _data):
        raise OSError(errno.EIO, "write fail")

    monkeypatch.setattr(io, "_write", boom)
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(
            input_path="observe.json", batch_id="ofail", bundle_dir=rel
        )
    assert caught.value.code == "CODE_PROOF_IO_ERROR"
    assert _dir_bytes(ns) == before
    leftover = [p.name for p in ns.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []


def test_public_interrupt_preserves_identity(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    marker = KeyboardInterrupt()

    def boom(_fd, _data):
        raise marker

    monkeypatch.setattr(io, "_write", boom)
    with pytest.raises(KeyboardInterrupt) as caught:
        request_code_proof(input_path="request.json", batch_id="intr")
    assert caught.value is marker
    ns = checkout / ".work" / "intr" / "code-evidence-v1"
    assert not (ns / "request.json").exists()


def test_public_lineage_overrides_semantic(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo("sha1", default_files())
    src = _write_request(checkout, repo)
    keep = {"fd": None}
    real = public._parse_json_bytes

    def wrapped(payload, pointer):
        keep["fd"] = _replace_keep_alive(src, payload)
        public._document("", "shape")

    monkeypatch.setattr(public, "_parse_json_bytes", wrapped)
    try:
        with pytest.raises(CodeProofIOError) as caught:
            request_code_proof(input_path="request.json", batch_id="prio")
        assert caught.value.code == "WORK_PATH_UNSAFE"
        assert caught.value.details["prior_code"] == "CODE_PROOF_DOCUMENT_INVALID"
    finally:
        if keep["fd"] is not None:
            os.close(keep["fd"])
    ns = checkout / ".work" / "prio" / "code-evidence-v1"
    assert not (ns / "request.json").exists()
    _ = real


def test_failed_status_zero_write(checkout: Path) -> None:
    _complete_raw(checkout, "sha1")
    copy_outputs("b1", "failst", ["request.json", "observation.json"])
    ns = checkout / ".work" / "failst" / "code-evidence-v1"
    before = _dir_bytes(ns)
    mtimes = {p.name: p.stat().st_mtime_ns for p in ns.iterdir()}
    with pytest.raises(CodeProofPublicError):
        status_code_proof(batch_id="failst")
    assert _dir_bytes(ns) == before
    assert {p.name: p.stat().st_mtime_ns for p in ns.iterdir()} == mtimes


def test_saved_artifact_limit_bounds(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())
    _write_request(checkout, repo)
    probe = request_code_proof(input_path="request.json", batch_id="probe")
    rel = write_bundle(checkout, ".work/raw-probe", repo, probe["request"])
    _write_observe_raw(checkout, repo)
    observe_code_proof(input_path="observe.json", batch_id="probe", bundle_dir=rel)
    config_code_proof(path="config.json", config_format="json", batch_id="probe")
    handoff_code_proof(batch_id="probe")
    ns = Path(".work/probe/code-evidence-v1")
    intent_size = len((ns / "intent.json").read_bytes())
    obs_size = len((ns / "observation.json").read_bytes())
    cfg_name = "configs/" + hashlib.sha256(b"config.json").hexdigest() + ".json"
    cfg_size = len((ns / cfg_name).read_bytes())
    hand_name = "handoffs/" + hashlib.sha256(b"config.json").hexdigest() + ".json"
    hand_size = len((ns / hand_name).read_bytes())

    def stage(batch, **public_overrides):
        assert len(batch) == 5
        write_bytes(
            checkout / "lim-request.json",
            dump_json(request_doc(repo, default_targets(), limits=public_limits(**public_overrides))),
        )
        req = request_code_proof(input_path="lim-request.json", batch_id=batch)
        bundle = write_bundle(checkout, ".work/raw-" + batch, repo, req["request"])
        write_bytes(checkout / "lim-observe.json", dump_json(observe_raw_doc(repo)))
        return req, bundle

    _req, bundle = stage("icap0", max_intent_bytes=intent_size)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="icap0", bundle_dir=bundle
    )
    _req, bundle = stage("icap1", max_intent_bytes=intent_size + 1)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="icap1", bundle_dir=bundle
    )
    _req, bundle = stage("icapx", max_intent_bytes=intent_size - 1)
    before = _dir_bytes(checkout / ".work" / "icapx" / "code-evidence-v1")
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(
            input_path="lim-observe.json", batch_id="icapx", bundle_dir=bundle
        )
    assert caught.value.details["limit_name"] == "max_intent_bytes"
    assert caught.value.details["observed"] == intent_size
    assert _dir_bytes(checkout / ".work" / "icapx" / "code-evidence-v1") == before
    assert not (
        checkout / ".work" / "icapx" / "code-evidence-v1" / "intent.json"
    ).exists()

    _req, bundle = stage("ocap0", max_observation_bytes=obs_size)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="ocap0", bundle_dir=bundle
    )
    _req, bundle = stage("ocapx", max_observation_bytes=obs_size - 1)
    before = _dir_bytes(checkout / ".work" / "ocapx" / "code-evidence-v1")
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(
            input_path="lim-observe.json", batch_id="ocapx", bundle_dir=bundle
        )
    assert caught.value.details["limit_name"] == "max_observation_bytes"
    assert caught.value.details["observed"] == obs_size
    assert _dir_bytes(checkout / ".work" / "ocapx" / "code-evidence-v1") == before
    assert not (
        checkout / ".work" / "ocapx" / "code-evidence-v1" / "intent.json"
    ).exists()

    _req, bundle = stage("ccap0", max_config_document_bytes=cfg_size)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="ccap0", bundle_dir=bundle
    )
    config_code_proof(path="config.json", config_format="json", batch_id="ccap0")
    _req, bundle = stage("ccapx", max_config_document_bytes=cfg_size - 1)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="ccapx", bundle_dir=bundle
    )
    before = _dir_bytes(checkout / ".work" / "ccapx" / "code-evidence-v1")
    with pytest.raises(CodeProofIOError) as caught:
        config_code_proof(path="config.json", config_format="json", batch_id="ccapx")
    assert caught.value.details["limit_name"] == "max_config_document_bytes"
    assert caught.value.details["observed"] == cfg_size
    assert _dir_bytes(checkout / ".work" / "ccapx" / "code-evidence-v1") == before

    src_hand = "handoffs/" + hashlib.sha256(b"src.py").hexdigest() + ".json"
    hand_max = max(hand_size, len((ns / src_hand).read_bytes()))
    _req, bundle = stage("hcap0", max_handoff_bytes=hand_max)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="hcap0", bundle_dir=bundle
    )
    handoff_code_proof(batch_id="hcap0")
    _req, bundle = stage("hcapx", max_handoff_bytes=hand_size - 1)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="hcapx", bundle_dir=bundle
    )
    before = _dir_bytes(checkout / ".work" / "hcapx" / "code-evidence-v1")
    with pytest.raises(CodeProofIOError) as caught:
        handoff_code_proof(batch_id="hcapx")
    assert caught.value.details["limit_name"] == "max_handoff_bytes"
    assert caught.value.details["observed"] == hand_size
    assert _dir_bytes(checkout / ".work" / "hcapx" / "code-evidence-v1") == before


def test_saved_request_and_canonical_bundle_limit_bounds(checkout: Path) -> None:
    repo = make_repo("sha1", default_files())

    def write_limited(name, **public_overrides):
        write_bytes(
            checkout / (name + ".json"),
            dump_json(
                request_doc(
                    repo,
                    default_targets(),
                    limits=public_limits(**public_overrides),
                )
            ),
        )

    def saved_request_size(batch, max_request_bytes):
        write_limited(batch, max_request_bytes=max_request_bytes)
        request_code_proof(input_path=batch + ".json", batch_id=batch)
        path = checkout / ".work" / batch / "code-evidence-v1" / "request.json"
        return len(path.read_bytes())

    size = saved_request_size("rprobe", 65536)
    for step in range(3):
        nxt = saved_request_size("rprobe" + str(step), size)
        if nxt == size:
            break
        size = nxt
    else:
        raise AssertionError("saved request size did not stabilize")
    assert len(str(size - 1)) == len(str(size)) == len(str(size + 1))

    write_limited("rcap0", max_request_bytes=size)
    request_code_proof(input_path="rcap0.json", batch_id="rcap0")
    assert (
        len((checkout / ".work" / "rcap0" / "code-evidence-v1" / "request.json").read_bytes())
        == size
    )
    write_limited("rcap1", max_request_bytes=size + 1)
    request_code_proof(input_path="rcap1.json", batch_id="rcap1")
    assert (
        len((checkout / ".work" / "rcap1" / "code-evidence-v1" / "request.json").read_bytes())
        == size
    )

    write_limited("rcapx", max_request_bytes=size - 1)
    nsx = checkout / ".work" / "rcapx" / "code-evidence-v1"
    before = _dir_bytes(nsx)
    with pytest.raises(CodeProofIOError) as caught:
        request_code_proof(input_path="rcapx.json", batch_id="rcapx")
    assert caught.value.code == "CODE_PROOF_LIMIT_EXCEEDED"
    assert caught.value.details["limit_name"] == "max_request_bytes"
    assert caught.value.details["instance_pointer"] == "/request"
    assert caught.value.details["limit"] == size - 1
    assert caught.value.details["observed"] == size
    assert _dir_bytes(nsx) == before
    assert not (nsx / "request.json").exists()
    if nsx.exists():
        leftover = [p.name for p in nsx.iterdir() if p.name.startswith(".ce-tmp-")]
        assert leftover == []

    write_limited("bprobe")
    probe = request_code_proof(input_path="bprobe.json", batch_id="bprobe")
    rel = write_bundle(checkout, ".work/raw-bprobe", repo, probe["request"])
    write_bytes(checkout / "lim-observe.json", dump_json(observe_raw_doc(repo)))
    observe_code_proof(input_path="lim-observe.json", batch_id="bprobe", bundle_dir=rel)
    bundle_size = len(
        (checkout / ".work" / "bprobe" / "code-evidence-v1" / "bundle.json").read_bytes()
    )

    def stage_bundle(batch, max_bundle_bytes):
        write_limited(batch, max_bundle_bytes=max_bundle_bytes)
        req = request_code_proof(input_path=batch + ".json", batch_id=batch)
        return write_bundle(checkout, ".work/raw-" + batch, repo, req["request"])

    bundle = stage_bundle("bcap0", bundle_size)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="bcap0", bundle_dir=bundle
    )
    assert (
        len((checkout / ".work" / "bcap0" / "code-evidence-v1" / "bundle.json").read_bytes())
        == bundle_size
    )
    bundle = stage_bundle("bcap1", bundle_size + 1)
    observe_code_proof(
        input_path="lim-observe.json", batch_id="bcap1", bundle_dir=bundle
    )

    bundle = stage_bundle("bcapx", bundle_size - 1)
    nsb = checkout / ".work" / "bcapx" / "code-evidence-v1"
    before = _dir_bytes(nsb)
    with pytest.raises(CodeProofIOError) as caught:
        observe_code_proof(
            input_path="lim-observe.json", batch_id="bcapx", bundle_dir=bundle
        )
    assert caught.value.code == "CODE_PROOF_LIMIT_EXCEEDED"
    assert caught.value.details["limit_name"] == "max_bundle_bytes"
    assert caught.value.details["instance_pointer"] == "/bundle"
    assert caught.value.details["limit"] == bundle_size - 1
    assert caught.value.details["observed"] == bundle_size
    assert _dir_bytes(nsb) == before
    assert not (nsb / "intent.json").exists()
    assert not (nsb / "bundle.json").exists()
    assert not (nsb / "observation.json").exists()
    leftover = [p.name for p in nsb.iterdir() if p.name.startswith(".ce-tmp-")]
    assert leftover == []
