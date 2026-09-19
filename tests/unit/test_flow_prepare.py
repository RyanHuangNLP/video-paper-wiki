from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import parse_envelope, run_module_cli
from tests.unit.test_article_revision import _papers, _question
from tests.unit.test_domain_proposal import _snapshot, make_world
from tests.unit.test_experiment_store import valid_condition_input
from tests.unit.test_graph_projection import _three_chain
from video_paper_wiki.article_revision import import_article_revision
from video_paper_wiki.article_store import MAX_TITLE, article_id_from_question
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


def _question_len(world, length, *, fill="x", suffix=""):
    base = _question(world) + " "
    need = length - len(base) - len(suffix)
    assert need >= 0
    if len(fill) == 1 and fill.isascii():
        extra, leftover = divmod(need, 2)
        mid = ("a " * extra) + ("a" * leftover)
    else:
        mid = fill * need
    text = base + mid + suffix
    assert len(text) == length
    return text


def _fill_placeholders(argv, mapping):
    filled = []
    for token in argv:
        filled.append(mapping[token] if token in mapping else token)
    for token in filled:
        assert not str(token).startswith("<")
    return filled


def _run_filled(world, action, mapping):
    proc = run_module_cli(world["checkout"], _fill_placeholders(action["argv"], mapping))
    return proc


def _cite_retry_paper_ids(argv):
    ids = []
    for index, token in enumerate(argv):
        if token == "--paper-id":
            ids.append(argv[index + 1])
    return ids


def _assert_cite_retry_argv(argv, *, vault, batch_id, paper_ids):
    assert argv[:10] == [
        "flow",
        "prepare",
        "--vault-root",
        vault,
        "--batch-id",
        batch_id,
        "--kind",
        "article",
        "--question",
        "<question>",
    ]
    expected = [("--paper-id", paper_id) for paper_id in paper_ids]
    assert list(zip(argv[10::2], argv[11::2], strict=True)) == expected
    assert len(argv) == 10 + 2 * len(paper_ids)
    assert _cite_retry_paper_ids(argv) == list(paper_ids)


def _recover_cite_prepare(world, err, question):
    proc = _run_filled(world, {"argv": err.details["argv"]}, {"<question>": question})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    prepared = parse_envelope(proc)["data"]
    _assert_kind_binding(prepared)
    return prepared


def _import_prepared_article(world, prepared):
    proc = _run_filled(
        world,
        _action(prepared, "survey-import-article"),
        {"<recorded_by>": "fixture", "<recorded_at>": "2026-09-15T00:00:00Z"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    imported = parse_envelope(proc)
    assert imported["ok"] is True
    assert imported["data"]["record"]["article_id"] == prepared["article_binding"]["article_id"]
    return imported


def _action(document, action_id=None, *, prefix=None):
    if action_id is not None:
        return next(item for item in document["next_actions"] if item["id"] == action_id)
    return next(item for item in document["next_actions"] if item["id"].startswith(prefix))


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


def test_article_title_bounds_prepare_import(world):
    _three_chain(world)
    papers = [_papers(world)[0]]
    vault = _vault(world)
    select_flow(vault_root=vault, batch_id="title1", paper_ids=papers, question=_question(world))
    before_vault = _snapshot(world["vault"])
    cases = ((300, "x"), (301, "😀"), (512, "测"))
    last_prepared = None
    for length, fill in cases:
        question = _question_len(world, length, fill=fill)
        prepared = prepare_flow(
            vault_root=vault,
            batch_id="title1",
            kind="article",
            paper_ids=papers,
            question=question,
        )
        _assert_kind_binding(prepared)
        ctx = world["checkout"] / prepared["outputs"][0]["path"]
        doc = world["checkout"] / prepared["outputs"][1]["path"]
        body = json.loads(doc.read_bytes().decode("utf-8"))
        envelope = json.loads(ctx.read_bytes().decode("utf-8"))
        expected_title = question if length <= MAX_TITLE else question[:MAX_TITLE]
        assert len(expected_title) == min(length, MAX_TITLE)
        assert body["title"] == expected_title
        assert not body["title"].endswith("...")
        if fill != "x":
            assert len(expected_title.encode("utf-8")) > len(expected_title)
        assert envelope["data"]["context"]["question"] == question
        assert envelope["data"]["article_id"] == article_id_from_question(question, papers)
        assert prepared["article_binding"]["question"] == question
        assert prepared["article_binding"]["article_id"] == envelope["data"]["article_id"]
        import_action = _action(prepared, "survey-import-article")
        assert set(import_action["placeholders"]) == {"<recorded_by>", "<recorded_at>"}
        assert import_action["argv"][import_action["argv"].index("--context") + 1] == prepared["outputs"][0]["path"]
        assert import_action["argv"][import_action["argv"].index("--document") + 1] == prepared["outputs"][1]["path"]
        proc = _run_filled(
            world,
            import_action,
            {"<recorded_by>": "fixture", "<recorded_at>": "2026-09-15T00:00:00Z"},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        imported = parse_envelope(proc)
        assert imported["ok"] is True
        assert imported["data"]["record"]["article_id"] == prepared["article_binding"]["article_id"]
        last_prepared = prepared
    again = prepare_flow(
        vault_root=vault,
        batch_id="title1",
        kind="article",
        paper_ids=papers,
        question=_question_len(world, 512, fill="测"),
    )
    assert all(item["staging"] == "already_staged" for item in again["outputs"])
    assert again["outputs"][0]["sha256"] == last_prepared["outputs"][0]["sha256"]
    assert again["outputs"][1]["sha256"] == last_prepared["outputs"][1]["sha256"]
    assert _snapshot(world["vault"]) == before_vault


def test_article_cite_mark_rejected_then_recovered(world):
    _three_chain(world)
    papers = [_papers(world)[0]]
    vault = _vault(world)
    inside = _question_len(world, 80, suffix="[@cite]")
    beyond = _question_len(world, 308, suffix="[@z]")
    assert "[@" in inside[:MAX_TITLE]
    assert "[@" not in beyond[:MAX_TITLE]
    assert "[@" in beyond
    select_flow(vault_root=vault, batch_id="cite1", paper_ids=papers, question=inside)
    work = world["checkout"] / ".work" / "cite1"
    before_vault = _snapshot(world["vault"])
    before_work = _snapshot(work)
    err = _expect(lambda: prepare_flow(vault_root=vault, batch_id="cite1", kind="article"), "FLOW_INVALID")
    assert err.details["instance_pointer"] == "/question"
    assert err.details["reason"] == "cite_mark_in_title"
    _assert_cite_retry_argv(err.details["argv"], vault=vault, batch_id="cite1", paper_ids=papers)
    assert _snapshot(work) == before_work
    err = _expect(
        lambda: prepare_flow(vault_root=vault, batch_id="cite1", kind="article", question=beyond),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "cite_mark_in_title"
    assert err.details["instance_pointer"] == "/question"
    _assert_cite_retry_argv(err.details["argv"], vault=vault, batch_id="cite1", paper_ids=papers)
    assert _snapshot(work) == before_work
    assert not (work / "flow" / "articles").exists()
    fixed = beyond.replace("[@", "(")
    assert "[@" not in fixed
    prepared = _recover_cite_prepare(world, err, fixed)
    _import_prepared_article(world, prepared)
    body = json.loads((world["checkout"] / prepared["outputs"][1]["path"]).read_bytes().decode("utf-8"))
    assert body["title"] == fixed[:MAX_TITLE]
    assert prepared["article_binding"]["question"] == fixed
    assert prepared["article_binding"]["paper_ids"] == papers
    assert _snapshot(world["vault"]) == before_vault


def test_article_cite_mark_recovery_argv_without_selection(world):
    _three_chain(world)
    ordered = _papers(world)[:2]
    assert len(ordered) == 2
    vault = _vault(world)
    batch_id = "cite-no-sel"
    bad = _question_len(world, 80, suffix="[@cite]")
    work = world["checkout"] / ".work" / batch_id
    before_vault = _snapshot(world["vault"])
    assert not (work / "flow" / "selection.json").exists()
    err = _expect(
        lambda: prepare_flow(
            vault_root=vault,
            batch_id=batch_id,
            kind="article",
            paper_ids=list(reversed(ordered)),
            question=bad,
        ),
        "FLOW_INVALID",
    )
    assert err.details["instance_pointer"] == "/question"
    assert err.details["reason"] == "cite_mark_in_title"
    _assert_cite_retry_argv(err.details["argv"], vault=vault, batch_id=batch_id, paper_ids=ordered)
    assert not work.exists() or not (work / "flow" / "articles").exists()
    assert not (work / "flow" / "selection.json").exists()
    fixed = bad.replace("[@", "(")
    assert "[@" not in fixed
    prepared = _recover_cite_prepare(world, err, fixed)
    assert prepared["paper_ids"] == ordered
    assert prepared["article_binding"]["paper_ids"] == ordered
    _import_prepared_article(world, prepared)
    assert not (work / "flow" / "selection.json").exists()
    assert _snapshot(world["vault"]) == before_vault


def test_article_cite_mark_recovery_argv_keeps_explicit_single_paper(world):
    _three_chain(world)
    p1 = world["association"]["paper_id"]
    p2 = next(item for item in _papers(world) if item != p1)
    vault = _vault(world)
    batch_id = "cite-multi"
    selected = select_flow(vault_root=vault, batch_id=batch_id, paper_ids=[p1, p2])
    saved_ids = selected["selection"]["paper_ids"]
    assert set(saved_ids) == {p1, p2}
    assert len(saved_ids) == 2
    bad = _question_len(world, 80, suffix="[@cite]")
    work = world["checkout"] / ".work" / batch_id
    before_vault = _snapshot(world["vault"])
    before_selection = (work / "flow" / "selection.json").read_bytes()
    err = _expect(
        lambda: prepare_flow(
            vault_root=vault,
            batch_id=batch_id,
            kind="article",
            paper_ids=[p2],
            question=bad,
        ),
        "FLOW_INVALID",
    )
    assert err.details["instance_pointer"] == "/question"
    assert err.details["reason"] == "cite_mark_in_title"
    _assert_cite_retry_argv(err.details["argv"], vault=vault, batch_id=batch_id, paper_ids=[p2])
    assert not (work / "flow" / "articles").exists()
    assert (work / "flow" / "selection.json").read_bytes() == before_selection
    fixed = bad.replace("[@", "(")
    assert "[@" not in fixed
    prepared = _recover_cite_prepare(world, err, fixed)
    assert prepared["paper_ids"] == [p2]
    assert prepared["article_binding"]["paper_ids"] == [p2]
    assert p1 not in prepared["paper_ids"]
    live_selection = json.loads((work / "flow" / "selection.json").read_bytes().decode("utf-8"))
    assert live_selection["paper_ids"] == saved_ids
    _import_prepared_article(world, prepared)
    body = json.loads((world["checkout"] / prepared["outputs"][1]["path"]).read_bytes().decode("utf-8"))
    assert "comparison" not in [section["role"] for section in body["sections"]]
    assert _snapshot(world["vault"]) == before_vault


def test_experiment_multiselect_primary_prepare(world):
    _three_chain(world)
    p1 = world["association"]["paper_id"]
    p2 = next(item for item in _papers(world) if item != p1)
    vault = _vault(world)
    before_vault = _snapshot(world["vault"])
    selected = select_flow(vault_root=vault, batch_id="exp-multi", paper_ids=[p2, p1])
    assert selected["selection"]["paper_ids"] == sorted([p1, p2], key=lambda item: item.encode("utf-8"))
    action = _action(selected, prefix="compare-prepare-experiment-")
    assert action["argv"].count("--paper-id") == 1
    primary = action["argv"][action["argv"].index("--paper-id") + 1]
    assert primary == p1
    assert action["id"] == "compare-prepare-experiment-" + primary
    assert primary in action["reason"]
    assert set(action["placeholders"]) == {"<setting_key>"}
    err = _expect(
        lambda: prepare_flow(
            vault_root=vault,
            batch_id="exp-multi",
            kind="experiment",
            setting_key="table9-row1-flow",
        ),
        "FLOW_INVALID",
    )
    assert err.details["reason"] == "single_paper_required"
    proc = _run_filled(world, action, {"<setting_key>": "table9-row1-flow"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    prepared = parse_envelope(proc)["data"]
    _assert_kind_binding(prepared)
    assert prepared["paper_ids"] == [primary]
    assert prepared["experiment_binding"]["paper_id"] == primary
    draft = json.loads((world["checkout"] / prepared["outputs"][0]["path"]).read_bytes().decode("utf-8"))
    assert draft["paper_id"] == primary
    live_selection = json.loads(
        (world["checkout"] / ".work" / "exp-multi" / "flow" / "selection.json").read_bytes().decode("utf-8")
    )
    assert live_selection["paper_ids"] == selected["selection"]["paper_ids"]
    assert p2 in live_selection["paper_ids"]
    reversed_sel = select_flow(vault_root=vault, batch_id="exp-order", paper_ids=[p1, p2])
    reversed_action = _action(reversed_sel, prefix="compare-prepare-experiment-")
    assert reversed_action["argv"][reversed_action["argv"].index("--paper-id") + 1] == primary
    assert reversed_action["id"] == action["id"]
    only_unbound = select_flow(vault_root=vault, batch_id="exp-none", paper_ids=[p2])
    ids = [item["id"] for item in only_unbound["next_actions"]]
    assert not any(item.startswith("compare-prepare-experiment-") for item in ids)
    reselect = _action(only_unbound, "session-select-new-batch")
    assert reselect["argv"][reselect["argv"].index("--batch-id") + 1] == "<batch_id>"
    assert "<batch_id>" in reselect["placeholders"]
    missing = next(item for item in only_unbound["missing_inputs"] if item["id"] == "experiment-paper-id")
    assert missing["field"] == "paper_id"
    assert p2 in missing["candidates"]
    assert _snapshot(world["vault"]) == before_vault
