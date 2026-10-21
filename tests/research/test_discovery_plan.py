from __future__ import annotations

import copy
from urllib.parse import parse_qsl, urlsplit

import pytest

from tests.research.discovery_fixture import assessment, begin, checkout, complete, config, observation, pure_round, requests, resources_scope, result, sealed_observation, user, write
from video_paper_wiki_research import discovery
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_contracts import PROVIDERS, reference, seal, spec_key, unique
from video_paper_wiki_research.discovery_plan import frontier, make_spec, plan_document, request_document, target, validate_explicit
from video_paper_wiki_research.discovery_storage import DiscoveryStore, open_store


def test_three_seed_base_schedule_has_exact_ten_topic_jobs_and_round_robin():
    c=config();first=c['seeds'][0]
    c['seeds']=[{**copy.deepcopy(first),'key':f'seed-{i}','ids':[{'namespace':'arxiv','value':f'240{i+1}.12345','version':None}],'author_terms':[f'Author {i}'],'project_terms':['official repo']} for i in range(3)]
    available=frontier(c,[],[],{})
    specs=available['specs'];assert len(specs)==16
    assert sum(s['operation']=='topic' for s in specs)==10
    assert sum(s['operation']=='lookup' for s in specs)==3
    assert sum(s['operation']=='project' for s in specs)==3
    assert [s['operation'] for s in specs[:3]]==['lookup','topic','project']
    assert len(available['capability_entries'])==9
    assert available==frontier(c,[],[],{})


def test_openalex_singleton_and_topic_encoding_exact():
    c=config();c['seeds'][0]['ids']=[{'namespace':'doi','value':'10.1234/a:b','version':None}]
    available=frontier(c,[],[],{})
    lookup=next(s for s in available['specs'] if s['operation']=='lookup')
    url=target(lookup)['url']
    assert url.startswith('https://api.openalex.org/works/doi:10.1234/a%3Ab?select=')
    assert [k for k,v in parse_qsl(urlsplit(url).query)]==['select']
    topic=next(s for s in available['specs'] if s['operation']=='topic' and s['provider']==PROVIDERS[0])
    url=target(topic)['url']
    assert '%20' in url and '+' not in url
    assert [k for k,v in parse_qsl(urlsplit(url).query)]==['search','per_page','select','sort']
    assert dict(parse_qsl(urlsplit(url).query))['sort']=='relevance_score:desc'


def test_neighborhoods_bind_observed_openalex_and_exact_sorted_ids():
    c=config();c['seeds'][0]['ids']=[{'namespace':'openalex','value':'W123','version':None}]
    pure=pure_round(c,count=1);request=next(iter(pure[-1].values()))
    raw=result(request,ids=c['seeds'][0]['ids'],referenced_ids=unique([{'namespace':'openalex','value':'W3','version':None},{'namespace':'openalex','value':'W2','version':None}]),related_ids=[{'namespace':'openalex','value':'W4','version':None}])
    obs=sealed_observation(request,results=[raw]);available=frontier(c,[pure[3]],[obs],pure[-1])
    for operation,expected in [('citations','cites:W123'),('references','openalex:W2|W3'),('related','openalex:W4')]:
        spec=next(s for s in available['specs'] if s['operation']==operation)
        assert spec['continuation']==reference(obs)
        parameters=parse_qsl(urlsplit(target(spec)['url']).query)
        assert [k for k,v in parameters]==['filter','per_page','select','sort']
        assert dict(parameters)['filter']==expected
        assert dict(parameters)['sort']=='cited_by_count:desc'


def test_explicit_retry_matches_terminal_failure_and_preserves_base():
    pure=pure_round(count=1);c,_,_,plan,reqs=pure;request=next(iter(reqs.values()))
    old=sealed_observation(request,outcome='timeout')
    retry=copy.deepcopy(request['data']['spec']);retry['retry']={'observation':reference(old),'reason':'timeout'};retry['request_key']=spec_key(retry)
    available=frontier(c,[plan],[old],reqs)
    assert validate_explicit([retry],available,[plan],[old],reqs,c)==[retry]
    for field,value in [('depth',1),('query','different'),('seed_key','invented')]:
        bad=copy.deepcopy(retry);bad[field]=value;bad['request_key']=spec_key(bad)
        with pytest.raises(ResearchError):validate_explicit([bad],available,[plan],[old],reqs,c)
    success=sealed_observation(request)
    bad=copy.deepcopy(retry);bad['retry']['observation']=reference(success);bad['request_key']=spec_key(bad)
    with pytest.raises(ResearchError):validate_explicit([bad],available,[plan],[success],reqs,c)


def test_cursor_uses_actual_prior_next_cursor_and_preserves_query():
    pure=pure_round();c,_,_,plan,reqs=pure
    request=next(r for r in reqs.values() if r['data']['spec']['operation']=='topic' and r['data']['spec']['provider']==PROVIDERS[0])
    value=observation(request);value['payload']['next_cursor']='cursor+value/='
    old=seal('discovery-observation',{'request':reference(request),**value})
    cursor=copy.deepcopy(request['data']['spec']);cursor.update(cursor='cursor+value/=',continuation=reference(old),retry=None);cursor['request_key']=spec_key(cursor)
    available=frontier(c,[plan],[old],reqs)
    assert validate_explicit([cursor],available,[plan],[old],reqs,c)==[cursor]
    assert target(cursor)['url'].endswith('cursor=cursor%2Bvalue%2F%3D')
    cursor['cursor']='made-up';cursor['request_key']=spec_key(cursor)
    with pytest.raises(ResearchError):validate_explicit([cursor],available,[plan],[old],reqs,c)


def test_largest_automatic_feasible_prefix_and_zero_outcomes(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);discovery.init(session='example',config_input=write(root/'c.json',config()))
    original=DiscoveryStore.capacity
    def capacity(self,extra=(),*,pending_plan=...):
        result=original(self,extra,pending_plan=pending_plan)
        plan=self.pending_plan if pending_plan is ... else pending_plan
        if plan is not None and len(plan['data']['request_specs'])>3:
            result={**result,'fits':False,'limiting_bounds':['synthetic-family-bound']}
        return result
    monkeypatch.setattr(DiscoveryStore,'capacity',capacity)
    state=discovery.status(session='example')
    assert state['planning']['chosen_count']==3 and state['planning']['available_frontier_count']==11
    assert discovery.plan(session='example')['budget']['request_slots_reserved']==3
    monkeypatch.setattr(DiscoveryStore,'capacity',original)
    assert discovery.status(session='example')['budget']['request_slots_reserved']==3


def test_zero_feasible_prefix_installs_no_plan(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);discovery.init(session='example',config_input=write(root/'c.json',config()))
    original=DiscoveryStore.capacity
    def capacity(self,extra=(),*,pending_plan=...):
        value=original(self,extra,pending_plan=pending_plan)
        if pending_plan is not ... and pending_plan is not None:return {**value,'fits':False,'limiting_bounds':['synthetic-total-bound']}
        return value
    monkeypatch.setattr(DiscoveryStore,'capacity',capacity)
    result=discovery.plan(session='example');assert result['matched_reasons']==['budget_exhausted']
    assert result['planning']['chosen_count']==0
    with open_store('example') as store:assert len(store.documents)==2


def test_declared_empty_frontier_is_needs_scope_without_empty_plan(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);discovery.init(session='example',config_input=write(root/'c.json',config()))
    monkeypatch.setattr(discovery,'frontier',lambda *a,**k:{'specs':[],'capability_entries':[],'selection_lineages':[]})
    result=discovery.plan(session='example');assert result['base_state']=='needs_scope'
    assert result['budget']['rounds_planned']==0
    with open_store('example') as store:assert len(store.documents)==2


def test_duplicate_threshold_equality_and_two_complete_rounds(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=2)
    c['stopping']['duplicate_percent']=50
    begin(root,configuration=c);first=complete(root,configuration=c)
    assert first['matched_reasons']==[]
    discovery.plan(session='example');second=complete(root,configuration=c)
    assert second['matched_reasons']==['duplicate_ratio']
    with open_store('example') as store:
        assert store.graph.stops[0]['data']['metrics']['total_hits']==2
        assert store.graph.stops[0]['data']['metrics']['repeated_hits']==1
    with pytest.raises(ResearchError) as caught:discovery.plan(session='example')
    assert caught.value.code=='DISCOVERY_STOPPED'


def test_zero_hits_low_yield_and_no_fabricated_duplicate(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1)
    begin(root,configuration=c);first=complete(root,configuration=c,outcome='capability_unavailable')
    assert not first['matched_reasons']
    discovery.plan(session='example');second=complete(root,configuration=c,outcome='capability_unavailable')
    assert second['matched_reasons']==['yield_below_threshold']


def test_budget_stop_precedence_with_cited_provisional_coverage(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(rounds=1,per_round_requests=1)
    begin(root,configuration=c);request=requests()[0]
    discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request)))
    with open_store('example') as store:observed=store.graph.observations[0]
    from video_paper_wiki_research.discovery_contracts import sha
    a=assessment(c)
    for lens in a['lenses']:
        lens.update(state='covered',statement='Synthetic cited observation only.',reason=None,evidence=[{'observation':reference(observed),'ordinal':1,'field':'title','start':0,'end':5,'excerpt_sha256':sha(b'Video')}])
    final=discovery.finish(session='example',assessment_input=write(root/'a.json',a))
    assert final['matched_reasons']==['budget_exhausted','paths_covered']
    assert final['scientific_assessment']=='provisional_scientific_assessment'


def test_completed_seed_identity_conflict_remains_inspectable(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);c=config(per_round_requests=1)
    c['seeds'][0]['ids']=[{'namespace':'openalex','value':'W1','version':None}]
    begin(root,configuration=c);request=requests()[0]
    ids=unique([{'namespace':'openalex','value':'W1','version':None},{'namespace':'openalex','value':'W2','version':None}])
    hit=result(request,ids=ids,identity_links=[{'left':ids[0],'right':ids[1],'relation':'same_work','locator':'https://example.org/crosswalk'}])
    discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request,results=[hit])))
    final=discovery.finish(session='example',assessment_input=write(root/'a.json',assessment(c)))
    assert final['base_state']=='needs_scope'
    assert final['planning']['capability_entries']
    assert {v['reason'] for v in final['planning']['capability_entries']}=={'identity_conflicted'}
    assert discovery.status(session='example')['base_state']=='needs_scope'
    with open_store('example') as store:
        assert store.graph.candidates['data']['items'][0]['conflicts']
        assert store.graph.rank['data']['fused']==[]


def test_three_expansion_selections_are_durable_before_request_materialization(tmp_path,monkeypatch):
    from tests.research.test_discovery_recovery import Interrupt, interrupt_after
    root=checkout(tmp_path,monkeypatch);c=config();begin(root,configuration=c)
    index=0
    for round_number in (1,2):
        if round_number==2:discovery.plan(session='example')
        for request in [r for r in requests() if r['data']['sequence']==round_number]:
            value=f'2401.{10000+index}';index+=1
            hit=result(request,ids=[{'namespace':'arxiv','value':value,'version':1}],locator='https://arxiv.org/abs/'+value+'v1')
            discovery.observe(session='example',request=request['id'],observation_input=write(root/'o.json',observation(request,results=[hit])))
        discovery.finish(session='example',assessment_input=write(root/'a.json',assessment(c)))
    ready=discovery.status(session='example');assert ready['selection_lineages']==[]
    assert ready['planning']['chosen_count']==3
    original,_=interrupt_after(monkeypatch,1)
    with pytest.raises(Interrupt):discovery.plan(session='example')
    monkeypatch.setattr(DiscoveryStore,'install',original)
    pending=discovery.status(session='example')
    assert pending['base_state']=='plan_pending_requests'
    assert len(pending['selection_lineages'])==3
    assert {l['depth'] for l in pending['selection_lineages']}=={1}
    assert {l['plan_sequence'] for l in pending['selection_lineages']}=={3}
    frozen=pending['selection_lineages']
    assert discovery.resume(session='example')['selection_lineages']==frozen
    assert discovery.status(session='example')['selection_lineages']==frozen


def test_selection_lineage_alias_merge_never_refunds_historical_introductions():
    from video_paper_wiki_research.discovery_plan import selected_lineages
    # This isolated algorithm vector has explicit synthetic origin refs. Full
    # public membership/receipt validation is exercised by the workflow test.
    pure=pure_round();c,_,session,_,reqs=pure;r=next(iter(reqs.values()))
    origin=lambda key:{'candidate_set':{'id':'rw3:paper-candidate-set:'+'1'*64,'sha256':'2'*64},'candidate_key':key*64}
    ids=[{'namespace':'arxiv','value':f'2401.{20000+i}','version':None} for i in range(4)]
    plans=[]
    for sequence in (1,2,3):
        spec=copy.deepcopy(r['data']['spec']);spec.update(subject_ids=[ids[sequence-1]],subject_origin=origin(str(sequence)),depth=1,seed_key='seed');spec['request_key']=spec_key(spec)
        plans.append({'data':{'sequence':sequence,'request_specs':[spec]}})
    before=selected_lineages(c,plans,[],{})
    assert len(before)==3
    bridge_request=copy.deepcopy(r);bridge_request['data']['sequence']=3
    joined=unique(ids[:2]);hit=result(bridge_request,ids=joined,identity_links=[{'left':joined[0],'right':joined[1],'relation':'same_work','locator':'https://example.org/bridge'}])
    old=sealed_observation(bridge_request,results=[hit])
    reqmap={bridge_request['id']:bridge_request}
    same=copy.deepcopy(plans[-1]['data']['request_specs'][0]);same.update(subject_ids=joined,subject_origin=origin('4'));same['request_key']=spec_key(same)
    assert len(selected_lineages(c,plans+[{'data':{'sequence':4,'request_specs':[same]}}],[old],reqmap))==3
    fourth=copy.deepcopy(same);fourth['subject_ids']=[ids[3]];fourth['request_key']=spec_key(fourth)
    with pytest.raises(ResearchError) as caught:selected_lineages(c,plans+[{'data':{'sequence':4,'request_specs':[fourth]}}],[old],reqmap)
    assert caught.value.code=='DISCOVERY_LIMIT_EXCEEDED'


def test_public_expansion_reaches_depth_two_without_requesting_depth_three(tmp_path, monkeypatch):
    root = checkout(tmp_path, monkeypatch)
    c = config()
    begin(root, configuration=c)
    ids = [{'namespace': 'arxiv', 'value': f'2402.{30000+i}', 'version': 1} for i in range(3)]
    for sequence in range(1, 5):
        if sequence > 1:
            discovery.plan(session='example')
        current = [r for r in requests() if r['data']['sequence'] == sequence]
        if sequence >= 3:
            assert len(current) == 1
            assert current[0]['data']['spec']['depth'] == sequence - 2
            assert current[0]['data']['spec']['subject_origin'] is not None
        for ordinal, request in enumerate(current):
            if sequence == 1 and ordinal == 0:
                hits = [result(request, ids=[ids[0]])]
            elif sequence >= 3:
                hits = [result(request, number=n+1, ids=[identifier])
                        for n, identifier in enumerate(ids[sequence-3:sequence-1])]
            else:
                hits = []
            supplied = observation(request, results=hits) if hits else observation(request, outcome='capability_unavailable')
            discovery.observe(session='example', request=request['id'], observation_input=write(root/'o.json', supplied))
        final = discovery.finish(session='example', assessment_input=write(root/'a.json', assessment(c)))
        assert final['matched_reasons'] == []
    assert final['base_state'] == 'needs_scope'
    assert final['planning']['available_frontier_count'] == 0
    assert [lineage['depth'] for lineage in final['selection_lineages']] == [1, 2]
    assert discovery.plan(session='example')['budget']['rounds_planned'] == 4
    assert max(r['data']['spec']['depth'] for r in requests()) == 2


def test_neighbor_slices_require_complete_unseen_canonical_prefix():
    c = config(per_page=2)
    c['seeds'][0]['ids'] = [{'namespace': 'openalex', 'value': 'W1', 'version': None}]
    _, _, session, first_plan, reqs = pure_round(c, count=1)
    singleton = next(iter(reqs.values()))
    neighbors = unique([{'namespace': 'openalex', 'value': value, 'version': None}
                        for value in ('W2', 'W10', 'W3', 'W4', 'W5')])
    old = sealed_observation(singleton, results=[result(singleton, ids=c['seeds'][0]['ids'], referenced_ids=neighbors)])
    available = frontier(c, [first_plan], [old], reqs)
    base = next(spec for spec in available['specs'] if spec['operation'] == 'references')
    assert base['neighbor_ids'] == neighbors[:2]
    second_plan = plan_document(session, 2, None, None, [base], [first_plan])
    plans = [first_plan, second_plan]
    continued = copy.deepcopy(base)
    continued['neighbor_ids'] = neighbors[2:4]
    continued['request_key'] = spec_key(continued)
    available = frontier(c, plans, [old], reqs)
    assert validate_explicit([continued], available, plans, [old], reqs, c) == [continued]
    for wrong in (neighbors[:2], neighbors[3:5], neighbors[2:3]):
        invalid_slice = copy.deepcopy(continued)
        invalid_slice['neighbor_ids'] = wrong
        invalid_slice['request_key'] = spec_key(invalid_slice)
        with pytest.raises(ResearchError):
            validate_explicit([invalid_slice], available, plans, [old], reqs, c)
    third_plan = plan_document(session, 3, None, None, [continued], plans)
    plans.append(third_plan)
    final_slice = copy.deepcopy(base)
    final_slice['neighbor_ids'] = neighbors[4:]
    final_slice['request_key'] = spec_key(final_slice)
    available = frontier(c, plans, [old], reqs)
    assert validate_explicit([final_slice], available, plans, [old], reqs, c) == [final_slice]
