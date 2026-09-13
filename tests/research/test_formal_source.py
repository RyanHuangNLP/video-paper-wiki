from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.markdown_source_fixture import LIGHT_ID, approval_fixture, light_source
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki_research.cli import main


def _output(capsys):
    captured = capsys.readouterr()
    assert not captured.err
    assert len(captured.out.splitlines()) == 1
    return json.loads(captured.out)


def test_public_plan_and_prepare_envelope(checkout, capsys, network_attempts):
    workspace, *_ = light_source(checkout)
    assert main(["formal-source", "plan", "--workspace-root", str(workspace), "--paper-id", LIGHT_ID,
                 "--batch-id", "public"]) == 0
    planned = _output(capsys)
    assert planned["ok"]
    path = planned["data"]["plan_path"]
    assert main(["formal-source", "prepare", "--plan", path]) == 2
    missing = _output(capsys)
    assert missing["error"]["code"] == "MARKDOWN_APPROVAL_REQUIRED"
    ref = checkout / ".work/public-ref.json"
    ref.write_bytes(canonicalize(approval_fixture(json.loads(Path(path).read_bytes()))))
    assert main(["formal-source", "prepare", "--plan", path, "--approval-ref", str(ref)]) == 0
    assert _output(capsys)["data"]["state"] == "awaiting_capture_inspect"
    assert not network_attempts


@pytest.mark.parametrize("argv", [["formal-source"], ["formal-source", "plan"],
                                  ["formal-source", "plan", "--workspace", "x"],
                                  ["formal-source", "bind-result", "--authority", "x", "--result", "x", "--before", "x", "--after", "x"],
                                  ["formal-source", "prepare", "--plan", "/tmp/../invalid"]])
def test_invalid_public_inputs_have_one_error_no_traceback(checkout, capsys, argv):
    assert main(argv) != 0
    value = _output(capsys)
    assert not value["ok"] and value["error"]["code"]


def test_public_capture_result_and_registration_chain(checkout, capsys):
    from tests.markdown_source_fixture import prepared_source
    from tests.research.conftest import UPSTREAM
    from tests.research.test_source_admission import _apply_bundle, bootstrap_genesis
    from video_paper_wiki.markdown_source_contracts import sha
    import stat

    vault = checkout / "fixture-vault"
    bootstrap_genesis(checkout, vault, checkout)
    _, prepared, _ = prepared_source(checkout)
    assert main(["formal-source", "inspect", "--prepared", prepared["request_path"],
                 "--operation-id", "public-capture", "--vault-root", str(vault),
                 "--upstream-root", str(UPSTREAM)]) == 0
    inspection = _output(capsys)["data"]
    assert inspection["state"] == "awaiting_operator_capture"
    authority = inspection["authority"]
    bundle = checkout / ".work/md-capture" / authority["transaction_staging"]["bundle_file"]
    actual = _apply_bundle(vault, bundle, authority["upstream_authority"]["transaction"]["inspection"]["approval_sha256"])
    target = authority["stored_path"]
    after = {target: {"sha256": sha((vault / target).read_bytes()), "mode": stat.S_IMODE((vault / target).stat().st_mode)}}
    inputs = {"authority": authority, "result": actual, "before": {target: None}, "after": after}
    argv = ["formal-source", "bind-result"]
    for name, value in inputs.items():
        path = checkout / ".work" / (name + ".json")
        path.write_bytes(canonicalize(value))
        argv.extend(["--" + name, str(path)])
    assert main(argv) == 0
    bound = _output(capsys)["data"]
    proof = checkout / ".work/bound.json"
    proof.write_bytes(canonicalize(bound))
    assert main(["formal-source", "admit", "--authority", str(checkout / ".work/authority.json"),
                 "--capture-result", str(proof), "--batch-id", "public-admit", "--operation-id", "public-admit",
                 "--vault-root", str(vault), "--upstream-root", str(UPSTREAM),
                 "--ingested-at", "2026-09-09T00:00:00Z"]) == 0
    pending = _output(capsys)["data"]
    assert pending["state"] == "source_registration_prepared"
    assert pending["receipt_backed"] is pending["published"] is False
