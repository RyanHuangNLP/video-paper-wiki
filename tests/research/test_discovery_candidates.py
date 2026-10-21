from __future__ import annotations

import itertools
from fractions import Fraction

from tests.research.discovery_fixture import pure_round, resources_scope, result, sealed_observation
from video_paper_wiki_research.discovery_candidates import projections, round_counts
from video_paper_wiki_research.discovery_contracts import saved_bytes, unique


def project(observations, pure):
    conf,_,session,plan,requests=pure
    return projections(conf,session,plan,observations,requests)


def test_cooccurrence_is_not_identity_and_same_work_is_explicit():
    pure=pure_round();request=next(iter(pure[-1].values()))
    ids=unique([{'namespace':'arxiv','value':'2401.12345','version':1},{'namespace':'doi','value':'10.1234/video','version':None}])
    raw=result(request,ids=ids)
    obs=sealed_observation(request,results=[raw])
    candidates,rank,components=project([obs],pure)
    assert len(components)==2 and len(rank['data']['fused'])==2
    assert round_counts(components,[],[obs])['total_hits']==2
    for relation in ['preprint_of','published_as','same_work']:
        raw['identity_links']=[{'left':ids[0],'right':ids[1],'relation':relation,'locator':'https://example.org/crosswalk'}]
        candidate,_,_=project([sealed_observation(request,results=[raw])],pure)
        assert len(candidate['data']['items'])==(1 if relation=='same_work' else 2)


def test_conflicting_namespace_is_retained_and_excluded_from_rank():
    pure=pure_round();request=next(iter(pure[-1].values()))
    ids=unique([{'namespace':'doi','value':'10.1234/a','version':None},{'namespace':'doi','value':'10.1234/b','version':None}])
    raw=result(request,ids=ids,identity_links=[{'left':ids[0],'right':ids[1],'relation':'same_work','locator':'https://example.org/claim'}])
    candidates,rank,_=project([sealed_observation(request,results=[raw])],pure)
    assert len(candidates['data']['items'])==1
    assert candidates['data']['items'][0]['conflicts'][0]['namespace']=='doi'
    assert rank['data']['fused']==[] and rank['data']['lists']==[]


def test_all_admitted_observation_orders_produce_identical_projections():
    pure=pure_round();reqs=list(pure[-1].values())[:3]
    observations=[sealed_observation(r,results=[result(r,locator=f'https://example.org/result-{i}',title=f'Video diffusion {i}')]) for i,r in enumerate(reqs)]
    first=None
    for order in itertools.permutations(observations):
        candidates,rank,_=project(order,pure)
        pair=saved_bytes(candidates),saved_bytes(rank)
        if first is None:first=pair
        assert pair==first


def test_unknown_independence_collapses_across_all_lists():
    pure=pure_round();reqs=list(pure[-1].values())[:3]
    observations=[sealed_observation(r,results=[result(r,locator=f'https://example.org/result-{i}')]) for i,r in enumerate(reqs)]
    _,rank,_=project(observations,pure);fused=rank['data']['fused'][0]
    assert (fused['numerator'],fused['denominator'])==('1','61')
    assert len(fused['contributions'])==1
    assert len([s for s in fused['suppressed'] if s['reason']=='independence_unknown_duplicate'])==2


def test_known_mirrors_and_unknown_mixture_follow_exact_suppression():
    pure=pure_round();reqs=list(pure[-1].values())[:4];observations=[]
    for i,r in enumerate(reqs):
        mirror={'group':('publisher-a' if i<2 else 'publisher-b'),'provenance':'host_observed','reason':None} if i<3 else {'group':None,'provenance':'unknown','reason':'unreported'}
        observations.append(sealed_observation(r,results=[result(r,locator=f'https://example.org/{i}',mirror=mirror)]))
    _,rank,_=project(observations,pure);row=rank['data']['fused'][0]
    assert len(row['contributions'])==2
    assert Fraction(int(row['numerator']),int(row['denominator']))==Fraction(2,61)
    assert {s['reason'] for s in row['suppressed']}=={'same_mirror_class','independence_unknown_with_known'}
    assert row['score']==1000000*2//61


def test_same_url_with_conflicting_labels_joins_one_known_class():
    pure=pure_round();reqs=list(pure[-1].values())[:2]
    observations=[sealed_observation(r,results=[result(r,locator='HTTPS://EXAMPLE.ORG:443/source#'+str(i),mirror={'group':'label-'+str(i),'provenance':'host_observed','reason':None})]) for i,r in enumerate(reqs)]
    _,rank,_=project(observations,pure);row=rank['data']['fused'][0]
    assert len(row['classes'])==1 and row['classes'][0]['group_labels']==['label-0','label-1']
    assert len(row['contributions'])==1 and row['suppressed'][0]['reason']=='same_mirror_class'


def test_same_list_result_duplicates_have_one_rank_term():
    pure=pure_round();r=next(iter(pure[-1].values()))
    o=sealed_observation(r,results=[result(r,number=i+1,locator=f'https://example.org/{i}',mirror={'group':f'publisher-{i}','provenance':'host_observed','reason':None}) for i in range(3)])
    _,rank,components=project([o],pure);row=rank['data']['fused'][0]
    assert len(row['contributions'])==1 and len(row['suppressed'])==2
    assert {s['reason'] for s in row['suppressed']}=={'same_list_candidate'}
    assert round_counts(components,[],[o])=={'total_hits':3,'repeated_hits':2,'new_components':1,'new_relevant':1}


def test_exact_fraction_ties_and_provider_score_display_only():
    pure=pure_round();r=next(iter(pure[-1].values()))
    raw=[]
    for i in range(2):
        raw.append(result(r,number=i+1,ids=[{'namespace':'doi','value':f'10.1234/{i}','version':None}],provider_score='9999' if i else '-9999',cited_by_count=10-i))
    _,rank,_=project([sealed_observation(r,results=raw)],pure)
    fused=rank['data']['fused']
    assert [(f['numerator'],f['denominator']) for f in fused]==[('1','61'),('1','62')]
    assert rank['data']['lists'][0]['entries'][0]['signals']['max_cited_by_count']==10


def test_exact_fraction_tie_orders_by_candidate_key():
    pure=pure_round();reqs=list(pure[-1].values())[:2]
    observations=[sealed_observation(r,results=[result(r,ids=[{'namespace':'doi','value':f'10.1234/independent-{i}','version':None}],locator=f'https://example.org/{i}')]) for i,r in enumerate(reqs)]
    _,rank,_=project(observations,pure)
    fused=rank['data']['fused']
    assert [(r['numerator'],r['denominator']) for r in fused]==[('1','61'),('1','61')]
    assert [r['candidate_key'] for r in fused]==sorted(r['candidate_key'] for r in fused)
