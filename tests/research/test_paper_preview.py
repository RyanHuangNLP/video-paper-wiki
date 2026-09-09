import json
from pathlib import Path

import pytest

from tests.preview_fixture import NOW, metadata_flow, observation, page, preview_flow, write_json
from video_paper_wiki_research.cli import main
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.paper_preview import (
    decide_paper, list_papers, observe_paper, preview_context, render_preview, request_paper, validate_preview,
)
from video_paper_wiki_research.preview_contracts import reference, saved_bytes, seal, task_prompt
from video_paper_wiki_research.preview_storage import open_preview_session


def choice(preview, *, event="choice-1", action="later", **kwargs):
    return decide_paper(session="preview", preview=preview, action=action, event_id=event,
                        user_text="Synthetic fixture choice", source="fixture", **kwargs)


def test_public_cli_complete_flow(checkout, capsys, network_attempts):
    def run(*args):
        status = main(["paper", *args, "--session", "preview"])
        result = json.loads(capsys.readouterr().out)
        assert status == 0, result
        assert result["ok"] is True
        return result["data"]

    requested = run("request", "--arxiv", "2408.06072v2", "--now", NOW)
    assert requested["fetch_required"] is True
    request = json.loads(Path(requested["request"]["path"]).read_bytes())
    bridge = write_json(checkout / "bridge.json", observation(request))
    observed = run("observe", "--request", requested["request"]["path"], "--observation", str(bridge))
    context = run("preview", "context", "--metadata", observed["metadata"]["path"])
    proposal = context["expected_proposal"]
    proposal["generated_at"] = NOW
    path = write_json(checkout / "proposal.json", proposal)
    preview = run("preview", "validate", "--metadata", observed["metadata"]["path"], "--proposal", str(path))
    rendered = run("preview", "render", "--preview", preview["preview"]["path"])
    assert "abstract-only" in rendered["markdown"] and "unknown" in rendered["markdown"]
    assert run("list")["previews"][0]["state"] == "pending"
    decision = run("decide", "--preview", preview["preview"]["path"], "--action", "ingest",
                   "--event-id", "fixture-selection", "--user-text", "Synthetic choose v2",
                   "--source", "fixture", "--selected-version", "2", "--recorded-at", NOW)
    handoff = decision["handoff"]
    assert handoff["source"] == "fixture" and handoff["selected_version"] == 2
    assert handoff["metadata"] == observed["metadata"]["reference"]
    assert handoff["observation"] == observed["observation"]["reference"]
    assert handoff["preview"] == preview["preview"]["reference"]
    assert handoff["decision"] == decision["decision"]["reference"]
    assert handoff["ingested"] is False and handoff["operator_authorized"] is False
    assert run("list")["previews"][0]["state"] == "ingest"
    assert network_attempts == []


def test_cache_ttl_policy_future_refresh(checkout):
    observed = metadata_flow(checkout)
    options = {"arxiv": "2408.06072v2", "session": "preview"}
    cached = request_paper(**options, now=NOW)
    assert cached["fetch_required"] is False
    assert cached["cache"]["metadata"] == observed["metadata"]
    assert request_paper(**options, now="2026-09-10T01:00:00Z")["fetch_required"] is False
    assert request_paper(**options, now="2026-09-10T01:00:01Z")["fetch_required"] is True
    assert request_paper(**options, now="2026-09-09T00:59:59Z")["fetch_required"] is True
    assert request_paper(**options, now=NOW, refresh=True)["fetch_required"] is True
    assert request_paper(arxiv="2408.06072", session="preview", now=NOW)["fetch_required"] is True
    assert request_paper(arxiv="2408.06072v1", session="preview", now=NOW)["fetch_required"] is True


def test_cache_tie_uses_exact_hash(checkout):
    first = metadata_flow(checkout)
    second = metadata_flow(checkout, text=page().replace("Synthetic Video Paper", "Synthetic Alternate Title"))
    result = request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    expected = max((first["metadata"], second["metadata"]), key=lambda item: item["reference"]["sha256"])
    assert result["cache"]["metadata"] == expected


@pytest.mark.parametrize("status,explicit,code", [
    ("not_found", True, "ARXIV_VERSION_UNAVAILABLE"), ("not_found", False, "ARXIV_ENTRY_NOT_FOUND"),
    ("timeout", True, "CONNECTOR_TIMEOUT"), ("rate_limited", True, "CONNECTOR_RATE_LIMITED"),
    ("failure", True, "CONNECTOR_FAILURE"),
])
def test_failure_observation_is_retained_without_metadata(checkout, status, explicit, code):
    result = request_paper(arxiv="2408.06072v2" if explicit else "2408.06072", session="preview", now=NOW)
    request = json.loads(Path(result["request"]["path"]).read_bytes())
    data = observation(request, status=status)
    data["outcome"]["retry_after_seconds"] = 60 if status == "rate_limited" else None
    bridge = write_json(checkout / "bridge.json", data)
    with pytest.raises(ResearchError) as caught:
        observe_paper(session="preview", request=result["request"]["path"], observation=bridge)
    assert caught.value.code == code
    saved = caught.value.details["observation"]
    assert Path(saved["path"]).is_file()
    with open_preview_session("preview") as store:
        assert len(store.all("observation")) == 1 and store.all("metadata") == []
    assert list_papers(session="preview")["previews"] == []


def test_cross_request_binding_refused_before_write(checkout):
    first = request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    second = request_paper(arxiv="2408.06073v2", session="preview", now=NOW)
    request = json.loads(Path(second["request"]["path"]).read_bytes())
    bridge = write_json(checkout / "bridge.json", observation(request))
    with pytest.raises(ResearchError) as caught:
        observe_paper(session="preview", request=first["request"]["path"], observation=bridge)
    assert caught.value.code == "OBSERVATION_BINDING_MISMATCH"
    with open_preview_session("preview") as store:
        assert store.all("observation") == []


def test_byte_exact_cli_unavailable_without_raw_read(checkout, monkeypatch):
    result = request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    request = json.loads(Path(result["request"]["path"]).read_bytes())
    data = observation(request)
    data["capability_profile"] = "byte-exact"
    data["payload"] = {"format": "raw-response-reference-v1", "path": "nonexistent/raw", "sha256": "a" * 64,
                       "bytes": 100, "executor_receipt_sha256": "b" * 64}
    for key, value in {"final_url": data["source_url"], "redirect_chain": [], "content_type": "text/html",
                       "raw_response_sha256": "a" * 64}.items():
        data["transport"][key] = {"value": value, "unavailable_reason": None}
    bridge = write_json(checkout / "bridge.json", data)
    with pytest.raises(ResearchError) as caught:
        observe_paper(session="preview", request=result["request"]["path"], observation=bridge)
    assert caught.value.code == "CONNECTOR_CAPABILITY_UNAVAILABLE"
    with open_preview_session("preview") as store:
        assert store.all("observation") == []


@pytest.mark.parametrize("tamper,code", [
    (lambda p: p.update(prompt_sha256="a" * 64), "PREVIEW_SCOPE_INVALID"),
    (lambda p: p.update(extra=True), "PREVIEW_PROPOSAL_INVALID"),
    (lambda p: p["generator"]["model"].update(reason=""), "PREVIEW_PROPOSAL_INVALID"),
    (lambda p: p["generator"]["runtime"].update(value="claimed runtime"), "PREVIEW_PROPOSAL_INVALID"),
    (lambda p: p["sections"]["one_sentence"].update(text="   "), "PREVIEW_PROPOSAL_INVALID"),
])
def test_proposal_refusals(checkout, tamper, code):
    result = metadata_flow(checkout)
    context = preview_context(session="preview", metadata=result["metadata"]["path"])
    metadata = json.loads(Path(result["metadata"]["path"]).read_bytes())
    assert context["task_prompt"].encode() == task_prompt(metadata)
    proposal = context["expected_proposal"]
    proposal["generated_at"] = NOW
    tamper(proposal)
    path = write_json(checkout / "proposal.json", proposal)
    with pytest.raises(ResearchError) as caught:
        validate_preview(session="preview", metadata=result["metadata"]["path"], proposal=path)
    assert caught.value.code == code


def test_resealed_metadata_cannot_forge_abstract(checkout):
    result = metadata_flow(checkout)
    original = json.loads(Path(result["metadata"]["path"]).read_bytes())
    data = original["data"]
    data["abstract"] = "Fabricated findings"
    fake = seal("metadata", data)
    target = Path(result["metadata"]["path"]).with_name(fake["content_sha256"] + ".json")
    target.write_bytes(saved_bytes(fake))
    with pytest.raises(ResearchError) as caught:
        request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    assert caught.value.code == "ARTIFACT_BINDING_MISMATCH"


def test_decisions_append_sequence_idempotency_and_conflicts(checkout):
    result = preview_flow(checkout)
    path = result["preview"]["path"]
    first = choice(path, action="later", recorded_at=NOW)
    replay = choice(path, action="later")
    assert replay["decision"] == first["decision"] and replay["already_recorded"] is True
    with pytest.raises(ResearchError) as caught:
        choice(path, action="skip")
    assert caught.value.code == "DECISION_CONFLICT" and caught.value.exit_code == 75
    second = choice(path, event="choice-2", action="skip", recorded_at="2026-09-08T01:00:00Z")
    third = choice(path, event="choice-3", action="ingest", selected_version=2)
    docs = [json.loads(Path(item["decision"]["path"]).read_bytes()) for item in (first, second, third)]
    assert [doc["data"]["sequence"] for doc in docs] == [1, 2, 3]
    assert docs[1]["data"]["previous"] == reference(docs[0]) and docs[2]["data"]["previous"] == reference(docs[1])
    assert list_papers(session="preview")["previews"][0]["state"] == "ingest"
    assert len(list(Path(first["decision"]["path"]).parent.iterdir())) == 3


@pytest.mark.parametrize("action,selected", [("ingest", None), ("ingest", 1), ("ingest", True), ("skip", 2), ("later", 2)])
def test_selected_version_must_be_explicit_and_match(checkout, action, selected):
    result = preview_flow(checkout)
    with pytest.raises(ResearchError):
        choice(result["preview"]["path"], action=action, selected_version=selected)
    assert list_papers(session="preview")["decision_count"] == 0


def test_latest_unknown_render_and_untrusted_prose(checkout):
    result = preview_flow(checkout, text=page(complete=False).replace("Synthetic Video Paper", "[Injected](https://evil.test)"))
    rendered = render_preview(session="preview", preview=result["preview"]["path"])
    assert rendered["latest_label"] == "latest_unknown"
    assert "# Injected" in rendered["markdown"] and "evil.test" not in rendered["markdown"]
    assert "https://arxiv.org/abs/2408.06072v2" in rendered["markdown"]


@pytest.mark.parametrize("args", [["paper"], ["paper", "request"], ["paper", "request", "--arxiv", "2408.06072", "--session", "ok", "--unknown"],
                                   ["paper", "decide", "--selected-version", "nonsense"]])
def test_usage_json(args, capsys):
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "USAGE_ERROR"
