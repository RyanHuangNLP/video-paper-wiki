from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import run_module_cli
from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_experiment_store import valid_condition_input
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_revision import import_article_revision
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_versions import build_domain_source_version_view
from video_paper_wiki.experiment_store import INPUT_KEYS, record_experiment_condition
from video_paper_wiki.flow.actions import PREPARE_SCHEMA, SELECTION_SCHEMA
from video_paper_wiki.flow.actions import FlowError
from video_paper_wiki.flow import prepare as prepare_mod
from video_paper_wiki.flow.prepare import prepare_flow
from video_paper_wiki.flow.selection import select_flow
from video_paper_wiki.flow.status import build_flow_status
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import StagingError


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _vault(world):
    return str(world["vault"])


def _expect(function, code):
    with pytest.raises(FlowError) as exc:
        function()
    assert exc.value.code == code
    return exc.value


def _papers_of(world):
    _three_chain(world)
    return _papers(world)


def _assert_kind_binding(document):
    validate_document(document, PREPARE_SCHEMA)
    if document["kind"] == "experiment":
        assert document["experiment_binding"] is not None
        assert document["article_binding"] is None
    else:
        assert document["kind"] == "article"
        assert document["article_binding"] is not None
        assert document["experiment_binding"] is None


def test_select_refusals_derived_and_conflict(world):
    papers = _papers_of(world)
    p1 = world["association"]["paper_id"]
    nine = ["sha256:" + format(index, "064x") for index in range(9)]
    err = _expect(
        lambda: select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=nine),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["instance_pointer"] == "/paper_ids"
    err = _expect(
        lambda: select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=["not-a-paper"]),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["instance_pointer"] == "/paper_ids/0"
    err = _expect(
        lambda: select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=["sha256:" + "f" * 64]),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["reason"] == "unknown_paper"
    assert "known_paper_count" in err.details
    err = _expect(
        lambda: select_flow(
            vault_root=_vault(world),
            batch_id="s1",
            paper_ids=[p1],
            association_id="sva-" + "0" * 64,
        ),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["reason"] == "association_not_of_paper"
    err = _expect(
        lambda: select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=[p1], question="x" * 513),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["instance_pointer"] == "/question"
    err = _expect(
        lambda: select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=[p1], question="bad\nline"),
        "FLOW_SELECTION_INVALID",
    )
    assert err.details["instance_pointer"] == "/question"
    first = select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=[p1])
    assert first["derived"] == ["association_id"]
    path = world["checkout"] / ".work" / "s1" / "flow" / "selection.json"
    raw = path.read_bytes()
    validate_document(json.loads(raw.decode("utf-8")), SELECTION_SCHEMA)
    assert canonicalize(json.loads(raw.decode("utf-8"))) == raw
    again = select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=[p1])
    assert again["state"] == "already_selected"
    assert path.read_bytes() == raw
    with pytest.raises(StagingError) as staged:
        select_flow(vault_root=_vault(world), batch_id="s1", paper_ids=[papers[1] if papers[1] != p1 else papers[0]])
    assert staged.value.code == "STAGING_CONFLICT"


def test_experiment_prepare_end_to_end(world, monkeypatch):
    _three_chain(world)
    p1 = world["association"]["paper_id"]
    p2 = next(item for item in _papers(world) if item != p1)
    select_flow(vault_root=_vault(world), batch_id="sess1", paper_ids=[p1])
    valid = valid_condition_input(world)
    before_vault = _snapshot(world["vault"])
    session = world["checkout"] / ".work" / "sess1"
    before_session = _snapshot(session) if session.exists() else {}
    prepared = prepare_flow(
        vault_root=_vault(world),
        batch_id="sess1",
        kind="experiment",
        setting_key="table9-row1-flow",
    )
    _assert_kind_binding(prepared)
    relative = Path(".work/sess1/flow/experiments/table9-row1-flow/input.json")
    path = world["checkout"] / relative
    assert path.is_file()
    draft = json.loads(path.read_bytes().decode("utf-8"))
    assert set(draft) == INPUT_KEYS
    assert draft["paper_id"] == valid["paper_id"]
    assert draft["source_association"] == valid["source_association"]
    assert draft["source_digest"] == valid["source_digest"]
    versions = build_domain_source_version_view(vault_root=_vault(world))
    d1 = next(row for row in versions["lineages"] if row["paper_id"] == p1)
    assert draft["code_binding"] == {
        "lineage_id": d1["lineage_id"],
        "annotation_id": d1["head_annotation_id"],
        "repository": d1["repository"],
        "commit": d1["commit"],
    }
    assert draft["claim_refs"] == []
    for name, slot in draft["conditions"].items():
        assert slot["status"] == "unknown"
        assert slot["search_scope"]["artifact_paths"] == [draft["source_digest"]["path"]]
        assert slot["search_scope"]["search_terms"] == [name]
    assert prepared["outputs"][0]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    after_vault = _snapshot(world["vault"])
    assert after_vault == before_vault
    after_session = _snapshot(session)
    for key in after_session:
        assert key.startswith("flow/") or key in before_session
    draft["conditions"] = valid["conditions"]
    path.write_bytes(canonicalize(draft))
    record_experiment_condition(
        input_path=str(path),
        vault_root=_vault(world),
        batch_id="rec1",
        recorded_by="fixture",
        recorded_at="2026-09-15T00:00:00Z",
    )
    existing = prepare_flow(
        vault_root=_vault(world),
        batch_id="sess1",
        kind="experiment",
        setting_key="table2-row3-vbench-512",
    )
    record_action = next(item for item in existing["next_actions"] if item["id"] == "compare-record-experiment")
    assert "--previous-record-id" in record_action["argv"]
    head = record_action["argv"][record_action["argv"].index("--previous-record-id") + 1]
    assert existing["experiment_binding"]["previous_record_id"] == head
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess2",
            kind="experiment",
            setting_key="table9-row1-flow",
            paper_ids=[p2],
        ),
        "FLOW_PREPARE_BLOCKED",
    )
    assert err.details["reason"] == "no_lineage"
    real = prepare_mod.build_domain_source_version_view(vault_root=_vault(world))

    def unbound(**_kwargs):
        document = copy.deepcopy(real)
        for row in document["lineages"]:
            row["association_status"] = "changed"
        return document

    monkeypatch.setattr(prepare_mod, "build_domain_source_version_view", unbound)
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess3",
            kind="experiment",
            setting_key="table9-row1-flow",
            paper_ids=[p1],
        ),
        "FLOW_PREPARE_BLOCKED",
    )
    assert err.details["reason"] == "association_unbound"
    monkeypatch.undo()
    before = _snapshot(world["checkout"] / ".work") if (world["checkout"] / ".work").exists() else {}
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess4",
            kind="experiment",
            setting_key="TABLE",
            paper_ids=[p1],
        ),
        "FLOW_INVALID",
    )
    assert err.details["instance_pointer"] == "/setting_key"
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess4",
            kind="experiment",
            setting_key="bad/key",
            paper_ids=[p1],
        ),
        "FLOW_INVALID",
    )
    assert err.details["instance_pointer"] == "/setting_key"
    after = _snapshot(world["checkout"] / ".work") if (world["checkout"] / ".work").exists() else {}
    assert after == before
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess4",
            kind="article",
            setting_key="x",
            paper_ids=[p1],
        ),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "kind_argument"
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="sess4",
            kind="experiment",
            setting_key="table9-row1-flow",
            question="q",
            paper_ids=[p1],
        ),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "kind_argument"
    err = _expect(
        lambda: prepare_flow(
            vault_root=_vault(world),
            batch_id="no-sel",
            kind="experiment",
            setting_key="table9-row1-flow",
        ),
        "FLOW_SELECTION_MISSING",
    )
    assert err.details["instance_pointer"] == "/batch_id"


def test_article_prepare_end_to_end(world):
    _three_chain(world)
    papers = _papers(world)
    question = _question(world)
    select_flow(
        vault_root=_vault(world),
        batch_id="sess1",
        paper_ids=papers,
        question=question,
    )
    before_vault = _snapshot(world["vault"])
    prepared = prepare_flow(vault_root=_vault(world), batch_id="sess1", kind="article")
    _assert_kind_binding(prepared)
    ctx = world["checkout"] / prepared["outputs"][0]["path"]
    doc = world["checkout"] / prepared["outputs"][1]["path"]
    cli = run_module_cli(
        world["checkout"],
        ["articles", "export", "--vault-root", _vault(world), "--question", question]
        + [token for paper in papers for token in ("--paper-id", paper)],
    )
    assert cli.returncode == 0
    assert ctx.read_bytes() == cli.stdout.encode("utf-8").removesuffix(b"\n")
    body = json.loads(doc.read_bytes().decode("utf-8"))
    envelope = json.loads(ctx.read_bytes().decode("utf-8"))
    roles = list(envelope["data"]["context"]["required_roles"])
    if "comparison" not in roles:
        roles.append("comparison")
    assert [section["role"] for section in body["sections"]] == roles
    assert all(section["status"] == "unwritten" for section in body["sections"])
    imported = import_article_revision(
        vault_root=_vault(world),
        batch_id="imp1",
        context=str(ctx),
        document=str(doc),
        recorded_by="fixture",
        recorded_at="2026-09-15T00:00:00Z",
    )
    status = build_flow_status(vault_root=_vault(world), batch_id="imp1")
    articles = [item for row in status["papers"] for item in row["articles"]]
    assert articles[0]["head_location"] == "staged"
    assert articles[0]["next_section_id"] == "s1"
    assert prepared["article_binding"]["article_id"] == articles[0]["article_id"]
    assert imported["record"]["article_id"] == articles[0]["article_id"]
    assert _snapshot(world["vault"]) == before_vault
    single = prepare_flow(
        vault_root=_vault(world),
        batch_id="sess2",
        kind="article",
        paper_ids=[papers[0]],
        question=question,
    )
    single_doc = json.loads((world["checkout"] / single["outputs"][1]["path"]).read_bytes().decode("utf-8"))
    assert "comparison" not in [section["role"] for section in single_doc["sections"]]
    import_article_revision(
        vault_root=_vault(world),
        batch_id="imp2",
        context=str(world["checkout"] / single["outputs"][0]["path"]),
        document=str(world["checkout"] / single["outputs"][1]["path"]),
        recorded_by="fixture",
        recorded_at="2026-09-15T00:00:00Z",
    )
    err = _expect(
        lambda: prepare_flow(vault_root=_vault(world), batch_id="sess3", kind="article", paper_ids=[papers[0]]),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "question_required"
    again = prepare_flow(vault_root=_vault(world), batch_id="sess1", kind="article")
    assert all(item["staging"] == "already_staged" for item in again["outputs"])
    assert (world["checkout"] / again["outputs"][0]["path"]).read_bytes() == ctx.read_bytes()
