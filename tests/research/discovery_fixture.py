"""Synthetic discovery inputs; no fixture claims live provider or human authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from video_paper_wiki_research.discovery_contracts import HARD_LIMITS, LENSES


def config(**limits):
    return {"question": "Video diffusion evidence", "seeds": [{"key": "seed", "ids": [
                {"namespace": "arxiv", "value": "2401.12345", "version": None}],
                "title": "Video generation", "author_terms": [], "project_terms": []}],
            "query_terms": ["video"], "lenses": [{"lens": lens, "terms": ["diffusion"],
                "scope": "Video diffusion " + lens} for lens in LENSES],
            "limits": {**HARD_LIMITS, **limits}, "ranking": {"rrf_k": 60, "score_scale": 1000000},
            "stopping": {"consecutive_rounds": 2, "min_new_relevant": 1, "duplicate_percent": 80}}


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return str(path)


def checkout(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "video-paper-wiki"\n')
    monkeypatch.chdir(root)
    return root


def user(event_id="test", text="Synthetic fixture instruction"):
    return {"event_id": event_id, "user_text": text, "source": "fixture", "recorded_at": "2026-09-09T00:00:00Z"}


def result(request, *, number=1, ids=None, **overrides):
    return {"ordinal": number, "ids": ids or [{"namespace": "arxiv", "value": "2401.12345", "version": 1}],
            "identity_links": [], "title": "Video diffusion study", "summary": "Synthetic video diffusion evidence.",
            "authors": ["Fixture Author"], "published_at": "2024-01-01", "cited_by_count": 10,
            "provider_score": None, "locator": "https://arxiv.org/abs/2401.12345v1",
            "relation": request["data"]["spec"]["operation"], "referenced_ids": None, "related_ids": None,
            "mirror": {"group": None, "provenance": "unknown", "reason": "No independence evidence in fixture"}, **overrides}


def observation(request, *, results=None, outcome="success", **overrides):
    return {"observed_at": "2026-09-09T00:00:00Z", "executor": {
                "tool_name": "synthetic-fixture", "identity_source": "self_reported",
                "capability_profile": request["data"]["spec"]["provider"], "locator": None, "reason": None},
            "outcome": outcome, "payload": {"results": [result(request)] if results is None else results,
                "next_cursor": None, "total_count": None, "completeness": "visible_page"} if outcome in {"success", "partial"} else None,
            "failure": None if outcome == "success" else {"code": outcome, "message": "Synthetic terminal observation", "retry_after_seconds": None}, **overrides}


def assessment(configuration=None):
    configured = config() if configuration is None else configuration
    return {"lenses": [{"lens": lens["lens"], "state": "gap", "scope": lens["scope"],
                "statement": "Evidence remains incomplete.", "evidence": [], "reason": "Synthetic fixture has no scientific coverage review."}
                for lens in configured["lenses"]],
            "generator": {"value": "synthetic-fixture", "identity_source": "self_reported", "reason": None},
            "recorded_at": "2026-09-09T00:00:00Z"}


def begin(root, *, session="example", configuration=None):
    from video_paper_wiki_research import discovery
    conf = config() if configuration is None else copy.deepcopy(configuration)
    discovery.init(session=session, config_input=write(root / "config.json", conf))
    return discovery.plan(session=session)


def requests(*, session="example"):
    from video_paper_wiki_research.discovery_storage import open_store
    with open_store(session) as store:
        return sorted([d for d in store.documents.values() if d["kind"] == "discovery-request"],
                      key=lambda d: (d["data"]["sequence"], d["data"]["slot"]))


def complete(root, *, session="example", configuration=None, outcome="success"):
    from video_paper_wiki_research import discovery
    for request in requests(session=session):
        discovery.observe(session=session, request=request["id"],
            observation_input=write(root / "observation.json", observation(request, outcome=outcome)))
    return discovery.finish(session=session, assessment_input=write(root / "assessment.json", assessment(configuration)))


def pure_round(configuration=None, count=8):
    from video_paper_wiki_research.discovery_contracts import reference, seal
    from video_paper_wiki_research.discovery_plan import frontier, plan_document, request_document
    conf = config() if configuration is None else configuration
    config_doc = seal("research-config", conf)
    session_doc = seal("research-session", {"session_key": "example", "config": reference(config_doc)})
    available = frontier(conf, [], [], {})
    plan_doc = plan_document(session_doc, 1, None, None, available["specs"][:count], [])
    reqs = {r["id"]: r for r in [request_document(session_doc, plan_doc, slot) for slot in range(count)]}
    return conf, config_doc, session_doc, plan_doc, reqs


def sealed_observation(request, **options):
    from video_paper_wiki_research.discovery_contracts import reference, seal
    return seal("discovery-observation", {"request": reference(request), **observation(request, **options)})


import pytest


@pytest.fixture(autouse=True)
def resources_scope():
    from video_paper_wiki_research.discovery_contracts import bound_resources, resource_state
    with bound_resources(resource_state()[3]):
        yield
