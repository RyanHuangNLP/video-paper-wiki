from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.markdown_source_fixture import LIGHT_ID
from tests.research.conftest import UPSTREAM
from tests.research.test_light_knowledge import _knowledge_document
from tests.research.test_source_admission import apply_publication
from tests.source_publication_fixture import registered_source
from tests.upstream.test_markdown_source import _snapshot
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_publication import audit_source_state, inspect_source_publication
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki_research.light_index import build_index
from video_paper_wiki_research.light_knowledge import export_knowledge_context, import_knowledge
from video_paper_wiki_research.source_conversion import convert_source_knowledge
from video_paper_wiki_research.source_conversion_model import METADATA

STAMP = "2026-09-09T01:00:00Z"


def conversion_fixture(checkout, *, legacy_registration=False):
    vault, capture, _, _ = registered_source(checkout, legacy=legacy_registration)
    workspace = checkout / ".work/light-library"
    assert build_index(workspace)["ok"]
    context = export_knowledge_context(workspace, paper_id=LIGHT_ID)
    assert context["ok"]
    document = _knowledge_document(LIGHT_ID, context["context"]["evidence"][0]["chunk_id"])
    imported = import_knowledge(workspace, context, document)
    assert imported["ok"]
    metadata = {"schema": METADATA, "paper_id": LIGHT_ID, "title": "Test paper", "title_zh": "合成论文",
                "authors": [], "published_at": "2024-01-02T12:34:56.123Z", "aliases": [], "taxonomy": [], "code_urls": []}
    authority_path, metadata_path = checkout / "capture.json", checkout / "metadata.json"
    authority_path.write_bytes(canonicalize(capture))
    metadata_path.write_bytes(canonicalize(metadata))
    kwargs = dict(workspace_root=workspace, paper_id=LIGHT_ID, record_id=imported["record_id"],
                  capture_authority=authority_path, metadata=metadata_path, batch_id="convert", operation_id="convert",
                  vault_root=vault, proposed_at=STAMP)
    return kwargs, document, context, capture


def publish_conversion(checkout, kwargs):
    prepared = convert_source_knowledge(**kwargs)
    assert prepared["state"] == "source_publication_prepared"
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id=kwargs["operation_id"],
        vault_root=kwargs["vault_root"], upstream_root=UPSTREAM)
    apply_publication(checkout, kwargs["vault_root"], authority)
    return prepared, authority


@pytest.mark.parametrize("legacy_registration", [False, True])
def test_actual_import_convert_inspect_apply_audit_and_noop(checkout, legacy_registration):
    kwargs, document, _, _ = conversion_fixture(checkout, legacy_registration=legacy_registration)
    vault = kwargs["vault_root"]
    before = _snapshot(vault)
    prepared = convert_source_knowledge(**kwargs)
    assert _snapshot(vault) == before
    assert prepared["published"] is prepared["applied"] is False
    summary = prepared["conversion"]
    assert len(summary["created_claim_ids"]) == 1
    assert summary["association_state"] == "proposed"
    assert summary["unmapped_concepts"] == document["concepts"]
    assert not summary["invalidated_claim_ids"] and not summary["unchanged_claim_ids"]
    authority = inspect_source_publication(prepared=prepared["request_path"], operation_id="convert",
        vault_root=vault, upstream_root=UPSTREAM)
    assert _snapshot(vault) == before
    assert authority["transaction"]["claimed_inputs"] == []
    apply_publication(checkout, vault, authority)
    state = audit_source_state(vault_root=vault)
    assert state["profile"] == "source-v1" and state["receipt_backed"]
    assert state["counts"]["claims"] == state["counts"]["papers"] == state["counts"]["associations"] == 1
    before_noop = _snapshot(vault)
    noop = convert_source_knowledge(**(kwargs | dict(batch_id="noop", operation_id="noop", metadata=None,
                                                     proposed_at="2000-01-01T00:00:00Z")))
    assert noop["state"] == "no_change" and noop["request_path"] is None
    assert noop["conversion"]["unchanged_claim_ids"] == summary["created_claim_ids"]
    assert noop["conversion"]["association_state"] == "reused"
    assert not noop["conversion"]["created_claim_ids"]
    assert _snapshot(vault) == before_noop
    assert not (checkout / ".work/noop/source-publication").exists()


@pytest.mark.parametrize("timestamp", ["2026-02-30T00:00:00Z", "2026-09-09T01:00:00.1Z", "2026-09-09", "", None])
def test_proposal_date_refusal_precedes_input_io(checkout, timestamp):
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(workspace_root="missing", paper_id=LIGHT_ID, record_id="a" * 64,
            capture_authority="missing", batch_id="convert", operation_id="convert", vault_root="missing", proposed_at=timestamp)
    assert err.value.code in {"SOURCE_CONVERSION_INVALID", "SCHEMA_INVALID"}
    assert err.value.details["instance_pointer"] == "/proposed_at"
    assert not (checkout / ".work/convert").exists()


@pytest.mark.parametrize("change", ["stale-head", "missing-metadata", "wrong-metadata-id", "different-observation", "old-timestamp"])
def test_refusals_preserve_actual_vault_without_publication_request(checkout, change):
    kwargs, _, _, _ = conversion_fixture(checkout)
    if change == "stale-head":
        kwargs["record_id"] = "f" * 64
    elif change == "missing-metadata":
        kwargs["metadata"] = None
    elif change == "wrong-metadata-id":
        value = json.loads(kwargs["metadata"].read_bytes())
        value["paper_id"] = "sha256:" + "b" * 64
        kwargs["metadata"].write_bytes(canonicalize(value))
    elif change == "different-observation":
        path = kwargs["workspace_root"] / "papers" / ("a" * 64) / "source.json"
        value = json.loads(path.read_bytes())
        value["title"] = "Changed title"
        path.write_bytes(canonicalize(value))
    else:
        kwargs["proposed_at"] = "2000-01-01T00:00:00Z"
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**kwargs)
    assert err.value.code == ("SOURCE_CONVERSION_STALE" if change in {"stale-head", "different-observation"} else "SOURCE_CONVERSION_INVALID")
    assert _snapshot(kwargs["vault_root"]) == before
    assert not (checkout / ".work/convert/source-publication").exists()


def test_second_light_record_with_same_evidence_keeps_event_bytes(checkout):
    kwargs, document, context, _ = conversion_fixture(checkout)
    prepared, _ = publish_conversion(checkout, kwargs)
    vault = kwargs["vault_root"]
    before = _snapshot(vault)
    document["concepts"] = [{**document["concepts"][0], "name": "Different unmapped suggestion"}]
    imported = import_knowledge(kwargs["workspace_root"], context, document)
    assert imported["ok"] and imported["record_id"] != kwargs["record_id"]
    noop = convert_source_knowledge(**(kwargs | dict(record_id=imported["record_id"], batch_id="different-light",
                                                    operation_id="different-light", metadata=None)))
    assert noop["state"] == "no_change"
    assert noop["conversion"]["unchanged_claim_ids"] == prepared["conversion"]["created_claim_ids"]
    assert noop["conversion"]["unmapped_concepts"] == document["concepts"]
    assert before == _snapshot(vault)


def test_cli_conversion_has_one_closed_success_envelope(checkout, capsys):
    from video_paper_wiki_research.cli import main
    kwargs, _, _, _ = conversion_fixture(checkout)
    capsys.readouterr()
    argv = ["formal-source", "convert"]
    for key, value in kwargs.items():
        argv.extend(["--" + key.replace("_", "-"), str(value)])
    assert main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] and output["command"] == "formal-source.convert"
    assert output["data"]["state"] == "source_publication_prepared"


def test_completed_batch_and_refresh_ancestry_validate_in_private_mirror(checkout):
    from tests.research.test_light_knowledge_batch import _run_batches
    from tests.research.test_light_knowledge_refresh import _run_refresh_to_candidate
    from video_paper_wiki_research.light_knowledge_refresh import apply_knowledge_refresh, export_knowledge_diff
    kwargs, _, _, _ = conversion_fixture(checkout)
    workspace = kwargs["workspace_root"]
    batched = _run_batches(workspace, LIGHT_ID)
    assert batched["ok"] and batched["advanced_head"]
    kwargs["record_id"] = batched["record_id"]
    before = _snapshot(workspace)
    prepared, _ = publish_conversion(checkout, kwargs)
    assert _snapshot(workspace) == before
    planned = _run_refresh_to_candidate(workspace, LIGHT_ID)
    assert planned["batch_count"] == 0
    diff = export_knowledge_diff(workspace, base_record_id=batched["record_id"],
                                candidate_record_id=planned["candidate"]["record_id"])
    assert diff["ok"]
    applied = apply_knowledge_refresh(workspace, diff, accept_sections=["summary"], accept_concepts=False)
    assert applied["ok"] and applied["record_id"] != batched["record_id"]
    original_plans = {str(p.relative_to(workspace)): p.read_bytes() for p in (workspace / ".light-knowledge").rglob("plan.json")}
    assert original_plans
    kwargs.update(record_id=applied["record_id"], batch_id="refresh-convert", operation_id="refresh-convert", metadata=None)
    before = _snapshot(workspace)
    noop = convert_source_knowledge(**kwargs)
    assert noop["state"] == "no_change"
    assert noop["conversion"]["unchanged_claim_ids"] == prepared["conversion"]["created_claim_ids"]
    assert _snapshot(workspace) == before
    mirror = next((checkout / ".work/refresh-convert/source-conversion").iterdir())
    for path, raw in original_plans.items():
        assert (mirror / path).read_bytes() == raw


def test_light_index_is_not_required_for_record_conversion(checkout):
    kwargs, _, _, _ = conversion_fixture(checkout)
    from video_paper_wiki_research.light_index import INDEX_DIRNAME
    import shutil
    index = kwargs["workspace_root"] / INDEX_DIRNAME
    assert index.exists()
    shutil.rmtree(index)
    prepared, _ = publish_conversion(checkout, kwargs)
    assert prepared["state"] == "source_publication_prepared"
    assert not index.exists()


def test_all_eight_sections_map_to_distinct_cited_provisional_claims(checkout):
    kwargs, document, context, _ = conversion_fixture(checkout)
    expected = {"summary": "one_sentence_conclusion", "method": "method",
        "architecture": "representation_architecture", "training_data": "training_data",
        "experiments": "experiments_results", "limitations": "limitations",
        "code_resources": "code_resources", "open_questions": "research_question"}
    citation = document["sections"]["summary"]["citations"][0]
    for key in expected:
        document["sections"][key] = {"status": "provisional", "citations": [citation], "text": "Evidence for " + key + "."}
    imported = import_knowledge(kwargs["workspace_root"], context, document)
    assert imported["ok"]
    kwargs["record_id"] = imported["record_id"]
    prepared, _ = publish_conversion(checkout, kwargs)
    assert len(prepared["conversion"]["created_claim_ids"]) == 8
    record = json.loads(next((kwargs["vault_root"] / "wiki/meta/records/papers").glob("*.json")).read_bytes())
    ledger = json.loads((kwargs["vault_root"] / CLAIM_LEDGER).read_bytes())["claims"]
    for ref in record["section_claim_refs"]:
        row = ledger[ref["claim_id"]]
        key = row["text"].removeprefix("Evidence for ").removesuffix(".")
        assert ref == {"section": expected[key], "core": key == "summary", "lifecycle": "active", "claim_id": ref["claim_id"]}
        assert row["assessment"] == "provisional" and row["reviewed_at"] is None
        assert len(row["evidence"]) == 1 and row["evidence"][0]["relation"] == "supports"


@pytest.mark.parametrize("different_spelling", [False, True])
def test_two_sections_cannot_claim_one_normalized_identity(checkout, different_spelling):
    kwargs, document, context, _ = conversion_fixture(checkout)
    document["sections"]["method"] = copy.deepcopy(document["sections"]["summary"])
    if different_spelling:
        document["sections"]["method"]["text"] = document["sections"]["method"]["text"].replace(" ", "  ")
    imported = import_knowledge(kwargs["workspace_root"], context, document)
    assert imported["ok"]
    kwargs["record_id"] = imported["record_id"]
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**kwargs)
    assert err.value.code == "SOURCE_CONVERSION_INVALID"
    assert before == _snapshot(kwargs["vault_root"])
    assert not (checkout / ".work/convert/source-publication").exists()


def test_existing_exact_claim_text_cannot_be_replaced_by_normalization_collision(checkout):
    kwargs, document, context, _ = conversion_fixture(checkout)
    publish_conversion(checkout, kwargs)
    document["sections"]["summary"]["text"] = document["sections"]["summary"]["text"].replace(" ", "  ")
    imported = import_knowledge(kwargs["workspace_root"], context, document)
    assert imported["ok"]
    kwargs.update(record_id=imported["record_id"], batch_id="collision", operation_id="collision")
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        convert_source_knowledge(**kwargs)
    assert err.value.code == "CLAIM_ID_COLLISION" and err.value.exit_code == 75
    assert before == _snapshot(kwargs["vault_root"])
    assert not (checkout / ".work/collision/source-publication").exists()


@pytest.mark.parametrize("failure", ["duplicate-metadata-key", "invalid-timestamp"])
def test_cli_refusal_is_one_structured_envelope_without_traceback(checkout, capsys, failure):
    from video_paper_wiki_research.cli import main
    kwargs, _, _, _ = conversion_fixture(checkout)
    if failure == "duplicate-metadata-key":
        kwargs["metadata"].write_bytes(b'{"title":"one","title":"two"}')
    else:
        kwargs["proposed_at"] = "2026-02-30T00:00:00Z"
    before = _snapshot(kwargs["vault_root"])
    capsys.readouterr()
    argv = ["formal-source", "convert"]
    for key, value in kwargs.items():
        argv.extend(["--" + key.replace("_", "-"), str(value)])
    assert main(argv) == 2
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert not output["ok"] and output["error"]["code"] in {"SOURCE_CONVERSION_INVALID", "SCHEMA_INVALID"}
    assert "Traceback" not in captured.out + captured.err
    assert before == _snapshot(kwargs["vault_root"])
    assert not (checkout / ".work/convert/source-publication").exists()
