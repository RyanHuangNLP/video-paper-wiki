from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.research.discovery_fixture import assessment, begin, checkout, complete, config, observation, requests, resources_scope, user, write
from video_paper_wiki_research import discovery
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_contracts import reference, saved_bytes, seal
from video_paper_wiki_research.discovery_graph import Graph
from video_paper_wiki_research.discovery_storage import DiscoveryStore, open_store


class Interrupt(RuntimeError):
    pass


def interrupt_after(monkeypatch, number):
    original=DiscoveryStore.install
    calls=[]
    def install(self,document):
        result=original(self,document);calls.append(document['kind'])
        if len(calls)==number:raise Interrupt('synthetic interruption after successful artifact install')
        return result
    monkeypatch.setattr(DiscoveryStore,'install',install)
    return original,calls


def test_config_only_resume_derives_exact_session(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch)
    original,calls=interrupt_after(monkeypatch,1)
    with pytest.raises(Interrupt):
        discovery.init(session='example',config_input=write(root/'config.json',config()))
    monkeypatch.setattr(DiscoveryStore,'install',original)
    assert calls==['research-config']
    state=discovery.status(session='example');assert state['base_state']=='init_pending'
    assert discovery.resume(session='example')['base_state']=='session_ready'
    assert discovery.init(session='example',config_input=str(root/'config.json'))['base_state']=='session_ready'


@pytest.mark.parametrize('slots',[1,8])
@pytest.mark.parametrize('edge',[1,2])
def test_plan_and_partial_request_reopen_reserves_every_slot(tmp_path,monkeypatch,slots,edge):
    root=checkout(tmp_path,monkeypatch);configuration=config(per_round_requests=slots)
    discovery.init(session='example',config_input=write(root/'config.json',configuration))
    original,_=interrupt_after(monkeypatch,edge)
    with pytest.raises(Interrupt):discovery.plan(session='example')
    monkeypatch.setattr(DiscoveryStore,'install',original)
    with open_store('example') as store:
        assert store.pending_plan is not None
        physical=store.capacity()
        assert physical['pending_reservation']['requests']=={'bytes':slots*65536,'files':slots}
        assert physical['pending_reservation']['observations']=={'bytes':slots*1114112,'files':slots}
        assert physical['charged_total_bytes']>=14680064
    before=discovery.status(session='example')
    assert before['budget']['request_slots_reserved']==slots
    repaired=discovery.resume(session='example')
    assert repaired['budget']['requests_materialized']==slots
    assert repaired['budget']['terminal_observations']==0
    assert repaired['budget']['request_slots_reserved']==slots


@pytest.mark.parametrize('edge',[1,2,3,4,5])
def test_every_projection_install_prefix_recovers_exactly(tmp_path,monkeypatch,edge):
    root=checkout(tmp_path,monkeypatch);configuration=config(per_round_requests=1)
    begin(root,configuration=configuration)
    request=requests()[0]
    discovery.observe(session='example',request=request['id'],observation_input=write(root/'observation.json',observation(request)))
    path=write(root/'assessment.json',assessment(configuration))
    original,calls=interrupt_after(monkeypatch,edge)
    with pytest.raises(Interrupt):discovery.finish(session='example',assessment_input=path)
    monkeypatch.setattr(DiscoveryStore,'install',original)
    before={p:p.read_bytes() for p in (root/'.work').rglob('*.json')}
    pending=discovery.status(session='example')
    assert pending['base_state']==('complete_continue' if edge==5 else 'projection_pending')
    done=discovery.resume(session='example')
    assert done['budget']['rounds_completed']==1 and done['budget']['terminal_observations']==1
    assert done['physical']['unspent_total_reservation']==0
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert discovery.finish(session='example',assessment_input=path)['budget']==done['budget']


def test_projection_prefix_survives_stop_resume_without_rewrite(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);configuration=config(per_round_requests=1)
    begin(root,configuration=configuration);r=requests()[0]
    discovery.observe(session='example',request=r['id'],observation_input=write(root/'o.json',observation(r)))
    original,_=interrupt_after(monkeypatch,3)
    with pytest.raises(Interrupt):discovery.finish(session='example',assessment_input=write(root/'a.json',assessment(configuration)))
    monkeypatch.setattr(DiscoveryStore,'install',original)
    old={p:p.read_bytes() for p in (root/'.work').rglob('*.json')}
    stop=discovery.control(session='example',action='user_stop',**user('pause'))
    assert stop['base_state']=='projection_pending' and stop['effective_state']=='user_stopped'
    with pytest.raises(ResearchError):discovery.resume(session='example')
    discovery.control(session='example',action='resume',**user('continue'))
    done=discovery.resume(session='example');assert done['budget']['rounds_completed']==1
    assert all(p.read_bytes()==raw for p,raw in old.items())
    with open_store('example') as store:
        event=store.graph.events[0]
        assert event['data']['control_head']==reference(store.graph.controls[-1])
        assert store.graph.plans[0]['data']['control_head'] is None


@pytest.mark.parametrize('kind',['paper-candidate-set','paper-rank','research-stop-decision','research-round-event'])
def test_resealed_tampered_projection_is_rejected_by_full_graph(tmp_path,monkeypatch,kind):
    root=checkout(tmp_path,monkeypatch);configuration=config(per_round_requests=1)
    begin(root,configuration=configuration);complete(root,configuration=configuration)
    with open_store('example') as store:
        original=next(d for d in store.documents.values() if d['kind']==kind)
        data=copy.deepcopy(original['data'])
        if kind=='paper-candidate-set':data['items'][0]['candidate_key']='f'*64
        elif kind=='paper-rank':data['fused'][0]['score']=0
        elif kind=='research-stop-decision':data['metrics']['total_hits']=99
        else:data['budget_after']['candidate_slots_reserved']=0
        forged=seal(kind,data)
        altered={k:v for k,v in store.documents.items() if k!=original['id']};altered[forged['id']]=forged
        with pytest.raises(ResearchError) as caught:Graph(altered,'example')
        assert caught.value.code=='DISCOVERY_GRAPH_INVALID'


def test_unknown_orphan_before_session_refuses_without_repair(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch)
    discovery.init(session='example',config_input=write(root/'c.json',config()))
    with open_store('example') as store:
        session_doc=store.graph.session
        path=store.root/'metadata'/store.filename(session_doc)
    path.unlink()
    assert discovery.status(session='example')['base_state']=='init_pending'
    orphan=Path(path).with_name('0'*64+'.json');orphan.write_bytes(b'{}\n');orphan.chmod(0o600)
    with pytest.raises(ResearchError):discovery.resume(session='example')
    assert not path.exists()
