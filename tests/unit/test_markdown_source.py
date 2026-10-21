from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.markdown_source_fixture import LIGHT_ID, approval_fixture, light_source, prepared_source
from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import APPROVAL, AUTHORITY, OBSERVATION, PLAN, REQUEST, SCHEMAS, digest, validate
from video_paper_wiki.markdown_source_io import json_bytes
from video_paper_wiki_research.formal_source import plan_markdown_source, prepare_markdown_source


def test_plan_prepare_exact_bytes_and_idempotence(checkout, network_attempts):
    planned, prepared, payload = prepared_source(checkout)
    request = prepared["request"]
    obs = request["plan"]["observation"]
    assert obs["version"] == {"kind": "unknown", "label": None}
    assert obs["original_pdf_sha256"] == "a" * 64
    assert obs["light_paper_id"] == LIGHT_ID
    assert "original_path" not in json.dumps(obs)
    stage = Path(prepared["request_path"]).parent
    assert (stage / (obs["markdown"]["sha256"] + ".md")).read_bytes() == payload
    before = {p.name: (p.stat().st_ino, p.read_bytes()) for p in stage.iterdir()}
    assert plan_markdown_source(workspace_root=request["plan"]["workspace_root"], paper_id=LIGHT_ID, batch_id="md-capture")["reused"]
    assert prepare_markdown_source(plan=planned["plan_path"], approval_ref=checkout / ".work/fixture-approval.json")["reused"]
    assert before == {p.name: (p.stat().st_ino, p.read_bytes()) for p in stage.iterdir()}
    assert not network_attempts


def test_declared_version_and_entity_are_explicit(checkout):
    workspace, *_ = light_source(checkout)
    result = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, canonical_paper_id="arxiv:2501.12345",
                                  version_label="author-supplied v2", batch_id="declared")
    assert result["observation"]["paper_id"] == "arxiv:2501.12345"
    assert result["observation"]["version"] == {"kind": "declared", "label": "author-supplied v2"}


def test_missing_approval_leaves_only_plan(checkout):
    workspace, *_ = light_source(checkout)
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="pending")
    with pytest.raises(ContractError, match="external") as err:
        prepare_markdown_source(plan=planned["plan_path"])
    assert err.value.code == "MARKDOWN_APPROVAL_REQUIRED"
    assert [p.name for p in Path(planned["plan_path"]).parent.iterdir()] == ["plan.json"]


@pytest.mark.parametrize("field,replacement", [("plan_sha256", "b" * 64), ("batch_id", "other"),
                                               ("paper_id", "arxiv:2501.12345"), ("markdown_sha256", "b" * 64)])
def test_each_approval_binding(checkout, field, replacement):
    workspace, *_ = light_source(checkout)
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="pending")
    plan = json.loads(Path(planned["plan_path"]).read_bytes())
    reference = approval_fixture(plan)
    reference[field] = replacement
    ref = checkout / ".work/ref.json"
    ref.write_bytes(canonicalize(reference))
    with pytest.raises(ContractError) as err:
        prepare_markdown_source(plan=planned["plan_path"], approval_ref=ref)
    assert err.value.code == "MARKDOWN_APPROVAL_MISMATCH"
    assert sorted(p.name for p in Path(planned["plan_path"]).parent.iterdir()) == ["plan.json"]


@pytest.mark.parametrize("mutation", ["markdown", "metadata", "anchor", "offset"])
def test_stale_or_invalid_source_refuses(checkout, mutation):
    workspace, md, meta_path = light_source(checkout)
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id="pending")
    plan = json.loads(Path(planned["plan_path"]).read_bytes())
    ref = checkout / ".work/ref.json"
    ref.write_bytes(canonicalize(approval_fixture(plan)))
    if mutation == "markdown":
        md.write_bytes(md.read_bytes() + b"changed")
    elif mutation == "anchor":
        md.write_bytes(md.read_bytes().replace(b"page-1", b"page-2"))
    else:
        meta = json.loads(meta_path.read_bytes())
        if mutation == "metadata":
            meta["title"] = "changed"
        else:
            meta["pages"][0]["text_start"] += 1
        meta_path.write_bytes(canonicalize(meta))
    with pytest.raises(ContractError) as err:
        prepare_markdown_source(plan=planned["plan_path"], approval_ref=ref)
    assert err.value.code in {"MARKDOWN_SOURCE_STALE", "MARKDOWN_SOURCE_INVALID"}


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.0}', b'{"x":"\\ud800"}', b'[' * 1000])
def test_strict_json_rejects_closed_invalid_inputs(payload):
    with pytest.raises(Exception) as err:
        json_bytes(payload, code="MARKDOWN_SOURCE_INVALID")
    assert getattr(err.value, "code", None) == "MARKDOWN_SOURCE_INVALID"


def test_schemas_and_integer_only_public_validation(checkout):
    _planned, prepared, _payload = prepared_source(checkout)
    for schema in SCHEMAS:
        assert schema_by_title(schema)["additionalProperties"] is False
    request = prepared["request"]
    bad = copy.deepcopy(request)
    bad["plan"]["observation"]["pages"][0]["page"] = 1.0
    with pytest.raises(ContractError):
        validate_document(bad, REQUEST)
    bad = copy.deepcopy(request)
    bad["plan"]["extra"] = True
    with pytest.raises(ContractError):
        validate_document(bad, REQUEST)


@pytest.mark.parametrize("field", ["request_sha256", "stored_path", "transaction_staging", "source_id"])
def test_reuse_authority_bindings(checkout, field):
    _, prepared, _ = prepared_source(checkout)
    request = prepared["request"]
    target = ".raw/captured/" + request["plan"]["observation"]["markdown"]["sha256"] + ".md"
    from video_paper_wiki.markdown_source_contracts import sha
    source_id = "src-" + sha(f'file\0{target}\0{request["plan"]["observation"]["markdown"]["sha256"]}'.encode())[:20]
    authority = {"schema": AUTHORITY, "requested_operation_id": "inspect", "request": request,
                 "request_sha256": digest(request), "disposition": "reuse", "stored_path": target,
                 "source_id": source_id, "transaction_staging": None, "upstream_authority": None}
    validate(authority, AUTHORITY)
    authority[field] = {"request_sha256": "b" * 64, "stored_path": target[:-2] + "pdf",
                        "transaction_staging": {}, "source_id": "invalid"}[field]
    with pytest.raises(ContractError):
        validate(authority, AUTHORITY)
