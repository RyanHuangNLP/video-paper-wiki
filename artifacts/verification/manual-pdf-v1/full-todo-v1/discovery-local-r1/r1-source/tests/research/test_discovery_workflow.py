from __future__ import annotations

import json

import pytest

from tests.research.discovery_fixture import assessment, begin, checkout, complete, config, observation, requests, user, write
from video_paper_wiki_research import discovery
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_storage import open_store


def test_absent_status_resume_context_do_not_create(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    for action in (discovery.status, discovery.resume, discovery.context, discovery.render):
        assert action(session="example")["base_state"] == "absent"
        assert not (root / ".work").exists()


def test_actual_round_and_exact_replays(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    state = begin(root)
    assert len(state["missing_observations"]) == 8
    assert state["budget"]["request_slots_reserved"] == 8
    assert state["physical"]["charged_total_bytes"] >= 14680064
    result = complete(root)
    assert result["base_state"] == "complete_continue"
    assert result["budget"]["rounds_completed"] == 1
    assert result["budget"]["terminal_observations"] == 8
    assert result["budget"]["candidate_slots_reserved"] == 1
    assert result["pending_candidate_introductions"] == 0
    assert discovery.resume(session="example")["budget"] == result["budget"]
    assert discovery.finish(session="example", assessment_input=str(root / "assessment.json"))["budget"] == result["budget"]
    with open_store("example") as store:
        stop = next(d for d in store.documents.values() if d["kind"] == "research-stop-decision")
        assert stop["data"]["metrics"]["total_hits"] == 8
        assert stop["data"]["metrics"]["repeated_hits"] == 7
        assert len(store.documents) == 24


def test_pending_never_fabricates_outcomes_or_assessment(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    begin(root)
    result = discovery.finish(session="example", assessment_input=str(root / "missing.json"))
    assert result["base_state"] == "plan_pending_observations"
    assert result["budget"]["terminal_observations"] == 0
    assert discovery.resume(session="example")["budget"] == result["budget"]


def test_explicit_stop_and_resume_keep_pending_requests(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    initial = begin(root)
    state = discovery.control(session="example", action="user_stop", **user("stop"))
    assert state["effective_state"] == "user_stopped"
    assert state["budget"] == initial["budget"]
    for action in (discovery.plan, discovery.resume):
        with pytest.raises(ResearchError) as caught:
            action(session="example")
        assert caught.value.code == "DISCOVERY_STOPPED"
    resumed = discovery.control(session="example", action="resume", **user("resume"))
    assert resumed["effective_state"] == "plan_pending_observations"
    assert resumed["budget"] == initial["budget"]
    assert discovery.control(session="example", action="resume", **user("resume")) == resumed


def test_candidate_handoff_is_data_only_and_exact_w1_request(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    begin(root)
    result = complete(root)
    with open_store("example") as store:
        candidates = store.documents[result["candidate_set"]["reference"]["id"]]
    choice = discovery.decide(session="example", candidate_set=candidates["id"],
        candidate_key=candidates["data"]["items"][0]["candidate_key"], action="preview",
        selected_arxiv="2401.12345v1", **user("choose"))
    handoff = discovery.handoff(session="example", decision=choice["decision"]["reference"]["id"])
    from video_paper_wiki_research.paper_preview import make_request
    assert handoff["handoff"]["request_document"] == make_request("2401.12345v1")
    assert not handoff["handoff"]["created"]
    assert not (root / ".work/research/example/preview-v1").exists()
    assert not (root / "wiki").exists()


def test_cli_json_success_and_error(tmp_path, monkeypatch, capsys):
    checkout(tmp_path, monkeypatch)
    from video_paper_wiki_research.cli import main
    assert main(["discovery", "status", "--session", "example"]) == 0
    first = capsys.readouterr()
    assert json.loads(first.out)["data"]["base_state"] == "absent"
    assert not first.err and len(first.out.splitlines()) == 1
    assert main(["discovery", "status", "--session", "../outside"]) == 2
    second = capsys.readouterr()
    assert json.loads(second.out)["error"]["code"] == "DISCOVERY_INPUT_INVALID"
    assert not second.err and len(second.out.splitlines()) == 1


def test_capability_binding_rejects_before_observation_install(tmp_path, monkeypatch):
    root=checkout(tmp_path,monkeypatch);begin(root,configuration=config(per_round_requests=1));request=requests()[0]
    value=observation(request)
    value['executor']['capability_profile']='openalex-rest-normalized-v1' if request['data']['spec']['provider']=='platform-web-search-normalized-v1' else 'platform-web-search-normalized-v1'
    with pytest.raises(ResearchError) as caught:
        discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',value))
    assert caught.value.code=='DISCOVERY_GRAPH_INVALID'
    state=discovery.status(session='example');assert state['budget']['terminal_observations']==0
    assert state['pending_candidate_introductions']==0


def test_strict_overcap_observation_has_no_hidden_debit(tmp_path,monkeypatch):
    from tests.research.discovery_fixture import result
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1,unique_candidates=1);begin(root,configuration=c);request=requests()[0]
    hits=[result(request,number=i+1,ids=[{'namespace':'arxiv','value':f'240{i+1}.12345','version':1}]) for i in range(2)]
    with pytest.raises(ResearchError) as caught:
        discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request,results=hits)))
    assert caught.value.code=='DISCOVERY_LIMIT_EXCEEDED'
    state=discovery.status(session='example');assert state['budget']['terminal_observations']==0
    assert state['budget']['request_slots_reserved']==1 and state['pending_candidate_introductions']==0
    failure=observation(request,outcome='failure');failure['failure'].update(code='local_normalization_failed',message='Actual synthetic two-component input exceeded the configured bound.')
    accepted=discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',failure))
    assert accepted['budget']['terminal_observations']==1 and accepted['pending_candidate_introductions']==0


def test_assessment_span_must_resolve_before_any_assessment_write(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1);begin(root,configuration=c);request=requests()[0]
    discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request)))
    with open_store('example') as store:
        from video_paper_wiki_research.discovery_contracts import reference
        obs=reference(store.graph.observations[0])
    value=assessment(c);value['lenses'][0].update(state='covered',reason=None,evidence=[{'observation':obs,'ordinal':1,'field':'title','start':0,'end':5,'excerpt_sha256':'0'*64}])
    with pytest.raises(ResearchError) as caught:discovery.finish(session='example',assessment_input=write(root/'a.json',value))
    assert caught.value.code=='DISCOVERY_GRAPH_INVALID'
    with open_store('example') as store:assert not store.graph.by_kind['research-assessment']
    assert discovery.status(session='example')['base_state']=='assessment_required'


def test_preview_requires_actually_observed_version_and_global_event_id(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1);begin(root,configuration=c);final=complete(root,configuration=c)
    with open_store('example') as store:row=store.graph.candidates['data']['items'][0]
    kwargs={'session':'example','candidate_set':final['candidate_set']['reference']['id'],'candidate_key':row['candidate_key'],'action':'preview',**user('choose')}
    with pytest.raises(ResearchError) as caught:discovery.decide(**kwargs,selected_arxiv='2401.12345v2')
    assert caught.value.code=='DISCOVERY_IDENTITY_UNRESOLVED'
    accepted=discovery.decide(**kwargs,selected_arxiv='2401.12345v1')
    assert discovery.decide(**kwargs,selected_arxiv='2401.12345v1')==accepted
    with pytest.raises(ResearchError) as caught:discovery.control(session='example',action='user_stop',**user('choose'))
    assert caught.value.code=='DISCOVERY_CONFLICT'


def test_render_observation_title_is_literal(tmp_path,monkeypatch):
    from tests.research.discovery_fixture import result
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1);begin(root,configuration=c);request=requests()[0]
    title='<script>alert(1)</script> [click](javascript:bad) *video*'
    discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request,results=[result(request,title=title)])))
    discovery.finish(session='example',assessment_input=write(root/'a.json',assessment(c)))
    rendered=discovery.render(session='example')['markdown']
    assert '<script>' not in rendered and '[click](javascript:' not in rendered
    assert r'\[click\]\(javascript:bad\)' in rendered
