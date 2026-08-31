from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import (
    ROOT,
    code_evidence_request,
    complete_ingest_plan,
    make_checkout,
    paper_source_request,
    work_plan,
    write_json,
)
from video_paper_wiki.cli import main
from video_paper_wiki.identity import pipeline_fingerprint, plan_approval_hash
from video_paper_wiki.jcs import canonicalize

PREFLIGHT = ROOT / "tests" / "fixtures" / "preflight"


def _payload(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    return json.loads(lines[0])


def test_plan_key_order_independent_jcs(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request = paper_source_request(local_sha256="a" * 64)
    first = tmp_path / "req-a.json"
    write_json(first, request)
    reversed_items = dict(reversed(list(request.items())))
    second = tmp_path / "req-b.json"
    write_json(second, reversed_items)
    assert main(["ingest", "plan", "--request", str(first)]) == 0
    payload = _payload(capsys)
    plan = payload["data"]["plan"]
    path = Path(payload["data"]["plan_path"])
    assert path == work_plan(tmp_path, "batch-0001")
    assert path.read_bytes() == canonicalize(plan)
    assert payload["data"]["approval_hash"] == plan_approval_hash(plan)
    assert payload["data"]["pipeline_fingerprint"] == pipeline_fingerprint(plan["parser"])
    assert payload["data"]["already_staged"] is False
    assert "human_approved" not in payload["data"]
    assert main(["ingest", "plan", "--request", str(second)]) == 0
    again = _payload(capsys)
    assert again["data"]["already_staged"] is True
    assert again["data"]["approval_hash"] == payload["data"]["approval_hash"]
    assert again["data"]["pipeline_fingerprint"] == payload["data"]["pipeline_fingerprint"]
    assert again["data"]["plan"]["approval_hash"] == plan["approval_hash"]
    assert network_attempts == []
    assert not (tmp_path / "blobs").exists()


def test_plan_family_mismatch_is_rejected(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    paper = write_json(tmp_path / "paper.json", paper_source_request(local_sha256="a" * 64))
    code = write_json(tmp_path / "code.json", code_evidence_request())
    assert main(["code-map", "plan", "--request", str(paper)]) == 2
    payload = _payload(capsys)
    assert payload["error"]["code"] == "PLAN_KIND_MISMATCH"
    assert main(["ingest", "plan", "--request", str(code)]) == 2
    payload = _payload(capsys)
    assert payload["error"]["code"] == "PLAN_KIND_MISMATCH"
    assert not (tmp_path / ".work").exists() or list((tmp_path / ".work").rglob("*")) == []
    assert network_attempts == []


def test_plan_rejects_derived_fields_duplicate_float_utf8_and_illegal_batch(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request = paper_source_request(local_sha256="a" * 64)
    derived = dict(request)
    derived["approval_hash"] = "a" * 64
    write_json(tmp_path / "derived.json", derived)
    assert main(["ingest", "plan", "--request", str(tmp_path / "derived.json")]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_REQUEST_INVALID"

    finger = dict(request)
    finger["pipeline_fingerprint"] = "b" * 64
    write_json(tmp_path / "finger.json", finger)
    assert main(["ingest", "plan", "--request", str(tmp_path / "finger.json")]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_REQUEST_INVALID"

    dup = tmp_path / "dup.json"
    body = json.dumps(request)
    dup.write_text(body[:-1] + ',"schema":"video-paper-wiki.ingest-plan.v1"}', encoding="utf-8")
    assert main(["ingest", "plan", "--request", str(dup)]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_REQUEST_INVALID"

    floated = dict(request)
    floated["limits"] = dict(request["limits"])
    floated["limits"]["max_pages"] = 1.5
    (tmp_path / "float.json").write_text(
        json.dumps(floated).replace("50", "50", 1), encoding="utf-8"
    )
    raw = json.dumps(request)
    (tmp_path / "float.json").write_text(raw.replace('"max_pages": 200', '"max_pages": 1.5'), encoding="utf-8")
    assert main(["ingest", "plan", "--request", str(tmp_path / "float.json")]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_REQUEST_INVALID"

    (tmp_path / "bad-utf8.json").write_bytes(b'{"schema":"x"\xff}')
    assert main(["ingest", "plan", "--request", str(tmp_path / "bad-utf8.json")]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_REQUEST_INVALID"

    dotted = dict(request)
    dotted["batch_id"] = "batch.0001"
    write_json(tmp_path / "dotted.json", dotted)
    assert main(["ingest", "plan", "--request", str(tmp_path / "dotted.json")]) == 2
    payload = _payload(capsys)
    assert payload["error"]["code"] == "PLAN_REQUEST_INVALID"
    assert not list((tmp_path / ".work").rglob("*")) if (tmp_path / ".work").exists() else True
    assert network_attempts == []


def test_plan_fixture_roundtrip_and_conflict(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request_path = PREFLIGHT / "paper-source.request.json"
    assert main(["ingest", "plan", "--request", str(request_path)]) == 0
    payload = _payload(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.plan"
    staged = Path(payload["data"]["plan_path"])
    assert staged == work_plan(tmp_path, "batch-0001")
    expected = complete_ingest_plan(json.loads(request_path.read_text(encoding="utf-8")))
    assert json.loads(staged.read_bytes().decode("utf-8")) == expected
    staged.write_bytes(b'{"not":"the-plan"}')
    assert main(["ingest", "plan", "--request", str(request_path)]) == 75
    payload = _payload(capsys)
    assert payload["error"]["code"] == "STAGING_CONFLICT"
    assert network_attempts == []


def test_plan_code_map_fixture(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request_path = PREFLIGHT / "code-evidence.request.json"
    assert main(["code-map", "plan", "--request", str(request_path)]) == 0
    payload = _payload(capsys)
    assert payload["command"] == "code-map.plan"
    assert payload["data"]["plan"]["plan_kind"] == "code-evidence"
    assert Path(payload["data"]["plan_path"]) == work_plan(tmp_path, "batch-code-1")
    assert network_attempts == []


@pytest.mark.parametrize("family,factory", [
    ("ingest", lambda: paper_source_request(local_sha256="a" * 64)),
    ("code-map", lambda: code_evidence_request()),
])
@pytest.mark.parametrize(
    "kind",
    ["missing_field", "additional_properties", "wrong_schema"],
)
def test_plan_request_schema_failures_are_plan_request_invalid(
    family, factory, kind, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request = factory()
    if kind == "missing_field":
        request.pop("limits")
    elif kind == "additional_properties":
        request["note"] = "extra"
    else:
        request["schema"] = "video-paper-wiki.ingest-plan.v0"
    path = write_json(tmp_path / f"{family}-{kind}.json", request)
    code = main([family, "plan", "--request", str(path)])
    payload = _payload(capsys)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PLAN_REQUEST_INVALID"
    assert "SCHEMA_INVALID" not in json.dumps(payload)
    assert network_attempts == []


def test_plan_missing_request_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["ingest", "plan"]) == 2
    payload = _payload(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_vpwiki_has_no_approval_ref_issuer(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    from video_paper_wiki.cli import build_parser

    leaves = []

    def walk(parser, prefix=()):
        import argparse

        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            leaves.append(list(prefix))
            return
        for action in subs:
            for name, child in action.choices.items():
                walk(child, prefix + (name,))

    walk(build_parser())
    flat = [" ".join(item) for item in leaves]
    for forbidden in ("approval", "approval-ref", "issue", "approve"):
        assert all(forbidden not in item.split() for item in flat)
    for argv in (
        ["approval"],
        ["approval-ref"],
        ["ingest", "approve"],
        ["ingest", "issue"],
        ["code-map", "approve"],
    ):
        assert main(argv) == 2
        assert _payload(capsys)["error"]["code"] == "USAGE"
    text = "\n".join(p.read_text() for p in (ROOT / "src" / "video_paper_wiki").rglob("*.py"))
    assert "def issue_approval" not in text
    assert "human_approved" not in text
    assert network_attempts == []
