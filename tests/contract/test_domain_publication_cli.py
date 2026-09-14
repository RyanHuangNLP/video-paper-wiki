from __future__ import annotations

import json
import os
import socket
import stat

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli, write_bytes
from tests.unit.test_domain_proposal import (
    _snapshot,
    make_world,
    valid_proposal,
    write_proposal,
)
from tests.unit.test_domain_store import (
    BATCH,
    LATER_AT,
    RECORDED_AT,
    RECORDED_BY,
    _add_code_batch,
    _apply_staged,
    _decision_for,
    _proposal_from,
    _record,
    _successor_proposal,
)
from video_paper_wiki.cli import build_parser, main
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_cli_record_compile_inspect_review_status_flow(world):
    proposal = valid_proposal(world)
    write_proposal(world["checkout"], proposal)
    vault_before = _snapshot(world["vault"])
    record_proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "record",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            RECORDED_AT,
        ],
    )
    record_payload = parse_envelope(record_proc)
    assert record_proc.returncode == 0
    compile_proc = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", BATCH],
    )
    compile_payload = parse_envelope(compile_proc)
    assert compile_proc.returncode == 0
    assert compile_payload["command"] == "domain.compile"
    data = compile_payload["data"]
    assert data["state"] == "domain_publication_prepared"
    assert data["publication"] == "unpublished"
    assert data["applied"] is False
    assert data["receipt_backed"] is False
    assert data["audit_coverage"] == "not_wired"
    assert data["transaction_authority"] == "not_wired"
    assert data["canonical_official"] is False
    assert data["current_supported_typed_fact"] is False
    request_path = world["checkout"] / data["request_path"]
    assert request_path.is_file()
    request = json.loads(request_path.read_bytes())
    validate_document(request, "video-paper-wiki.domain-publication-request.v1")
    assert _snapshot(world["vault"]) == vault_before
    inspect_proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "publish-inspect",
            "--prepared",
            data["request_path"],
            "--vault-root",
            str(world["vault"]),
        ],
    )
    inspect_payload = parse_envelope(inspect_proc)
    assert inspect_proc.returncode == 0
    assert inspect_payload["command"] == "domain.publish-inspect"
    inspection = inspect_payload["data"]
    validate_document(inspection, "video-paper-wiki.domain-publication-inspection.v1")
    assert inspection["basis_verified"] is True
    assert inspection["content_verified"] is True
    assert inspection["backup_coverage"] == "not_wired"
    assert inspection["next_action"] == "apply_requires_later_slice"
    assert _snapshot(world["vault"]) == vault_before
    _apply_staged(world, BATCH)
    decision = _decision_for(world, record_payload["data"], officiality="official")
    write_bytes(world["checkout"] / "decision.json", canonicalize(decision) + b"\n")
    review_proc = run_module_cli(
        world["checkout"],
        [
            "domain",
            "review",
            "--decision",
            "decision.json",
            "--vault-root",
            str(world["vault"]),
            "--batch-id",
            "d2r",
        ],
    )
    assert review_proc.returncode == 0
    review_compile = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", "d2r"],
    )
    review_compile_payload = parse_envelope(review_compile)
    assert review_compile.returncode == 0
    review_compile_again = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", "d2r"],
    )
    assert review_compile_again.returncode == 0
    assert review_compile_again.stdout == review_compile.stdout
    review_request = json.loads(
        (world["checkout"] / review_compile_payload["data"]["request_path"]).read_bytes()
    )
    heads = next(item for item in review_request["payloads"] if item["path"].endswith("heads.json"))
    assert heads["mode"] == "replace"
    review_inspect = run_module_cli(
        world["checkout"],
        [
            "domain",
            "publish-inspect",
            "--prepared",
            review_compile_payload["data"]["request_path"],
            "--vault-root",
            str(world["vault"]),
        ],
    )
    assert review_inspect.returncode == 0
    _apply_staged(world, "d2r")
    status_proc = run_module_cli(
        world["checkout"],
        ["domain", "status", "--vault-root", str(world["vault"])],
    )
    status_payload = parse_envelope(status_proc)
    assert status_proc.returncode == 0
    assert status_payload["data"]["canonical_official"] is False
    assert status_payload["data"]["current_supported_typed_fact"] is False
    again = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", BATCH],
    )
    assert again.returncode == 2
    again_payload = parse_envelope(again)
    assert again_payload["error"]["code"] == "DOMAIN_COMPILE_ALREADY_PUBLISHED"


def test_cli_help_six_leaves(capsys):
    parser = build_parser()
    parent = None
    for action in parser._actions:
        if getattr(action, "choices", None) and "domain" in action.choices:
            parent = action.choices["domain"]
            break
    assert parent is not None
    leaves = {}
    for action in parent._actions:
        if getattr(action, "choices", None):
            leaves.update(action.choices)
    assert set(leaves) == {
        "inspect",
        "record",
        "relations",
        "review",
        "status",
        "compile",
        "publish-inspect",
    }
    compile_help = leaves["compile"].format_help()
    assert "--vault-root" in compile_help
    assert "--batch-id" in compile_help
    inspect_help = leaves["publish-inspect"].format_help()
    assert "--prepared" in inspect_help
    assert "--vault-root" in inspect_help
    code = main(["domain", "compile"])
    out = capsys.readouterr().out
    envelope = json.loads(out.strip().splitlines()[-1])
    assert code == 2
    assert envelope["error"]["code"] == "USAGE"


def test_cli_error_envelope_exit_codes(world):
    missing = run_module_cli(world["checkout"], ["domain", "compile"])
    payload = parse_envelope(missing)
    assert missing.returncode == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    unsafe = run_module_cli(
        world["checkout"],
        [
            "domain",
            "publish-inspect",
            "--prepared",
            "decision.json",
            "--vault-root",
            str(world["vault"]),
        ],
    )
    unsafe_payload = parse_envelope(unsafe)
    assert unsafe.returncode == 2
    assert unsafe_payload["error"]["code"] == "WORK_PATH_UNSAFE"
    first = _record(world, valid_proposal(world), name="g.json", batch="st1")
    _apply_staged(world, "st1")
    _record(
        world,
        _successor_proposal(world),
        name="s.json",
        previous=first["record"]["annotation_id"],
        recorded_at=LATER_AT,
        batch="st2",
    )
    other = _add_code_batch(world, "cli-other", repository="Cli/Other")
    other_proposal = _proposal_from(world, other, repository="Cli/Other")
    _record(world, other_proposal, name="o.json", batch="st3")
    _apply_staged(world, "st3")
    stale = run_module_cli(
        world["checkout"],
        ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", "st2"],
    )
    stale_payload = parse_envelope(stale)
    assert stale.returncode == 75
    assert stale_payload["error"]["code"] == "DOMAIN_COMPILE_STALE"
    assert stale_payload["error"]["details"]["next_action"] == "re_record_or_re_review"


def test_cli_determinism_zero_writes_and_no_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    write_proposal(world["checkout"], valid_proposal(world))
    run_module_cli(
        world["checkout"],
        [
            "domain",
            "record",
            "--input",
            "proposal.json",
            "--vault-root",
            str(world["vault"]),
            "--code-batch-id",
            "d1",
            "--batch-id",
            BATCH,
            "--recorded-by",
            RECORDED_BY,
            "--recorded-at",
            RECORDED_AT,
        ],
    )
    argv = ["domain", "compile", "--vault-root", str(world["vault"]), "--batch-id", BATCH]
    vault_before = _snapshot(world["vault"])
    ledger_before = (world["vault"] / CLAIM_LEDGER).read_bytes()
    first = run_module_cli(world["checkout"], argv)
    second = run_module_cli(world["checkout"], argv)
    assert first.returncode == 0
    assert first.stdout == second.stdout
    assert canonicalize(parse_envelope(first)) == first.stdout.encode("utf-8").strip()
    assert _snapshot(world["vault"]) == vault_before
    assert (world["vault"] / CLAIM_LEDGER).read_bytes() == ledger_before
    prepared = parse_envelope(first)["data"]["request_path"]
    inspect_argv = [
        "domain",
        "publish-inspect",
        "--prepared",
        prepared,
        "--vault-root",
        str(world["vault"]),
    ]
    work_before = _snapshot(world["checkout"] / ".work")
    inspect_first = run_module_cli(world["checkout"], inspect_argv)
    inspect_second = run_module_cli(world["checkout"], inspect_argv)
    assert inspect_first.returncode == 0
    assert inspect_first.stdout == inspect_second.stdout
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    request_file = world["checkout"] / prepared
    st = request_file.lstat()
    assert not stat.S_ISLNK(st.st_mode)
    assert os.path.isfile(request_file)
