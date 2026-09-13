from __future__ import annotations

import copy
import json

import pytest

from tests.research.discovery_fixture import config, pure_round, resources_scope, result, sealed_observation
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_contracts import (
    CAPS, PROFILE_SHA, SCHEMA_FILES, config_input, identifier, parse_json, reference,
    resource_state, saved_bytes, seal, sha, source_url, validate,
)


def test_registry_exact_profile_and_content_envelope():
    state = resource_state()
    assert len(SCHEMA_FILES) == len(state[1]) == 13
    assert sha(state[3]['profiles/discovery-v1.json']) == PROFILE_SHA
    document = seal('research-config', config())
    raw = saved_bytes(document)
    assert raw.endswith(b'\n') and not raw.endswith(b'\n\n')
    assert reference(document)['sha256'] == sha(raw)
    bad = copy.deepcopy(document)
    bad['data']['question'] += ' altered'
    with pytest.raises(ResearchError):
        validate(bad)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.2}', b'\xef\xbb\xbf{}', b'{"x":"\\ud800"}', b'[' * 33 + b'0' + b']' * 33])
def test_strict_input_refusals(raw):
    with pytest.raises(ResearchError):
        parse_json(raw)


@pytest.mark.parametrize('change', [
    lambda c: c.update(extra=True), lambda c: c['limits'].update(requests=True),
    lambda c: c['limits'].update(rounds=9), lambda c: c['ranking'].update(score_scale=10),
    lambda c: c['lenses'][0].update(extra='unknown'), lambda c: c['lenses'].reverse(),
    lambda c: c['seeds'][0]['ids'].append({'namespace':'arxiv','value':'2402.12345','version':None}),
    lambda c: c.update(question='e\u0301'), lambda c: c.update(question='video\nquery'),
    lambda c: c.update(question='video\x85query'), lambda c: c['seeds'][0].update(key='../escape'),
])
def test_config_nested_closed_and_typed(change):
    c = config();change(c)
    with pytest.raises(ResearchError):
        config_input(c)


def test_declared_terms_preserved_identifier_input_normalized():
    c=config();c['query_terms']=['Z term','Alpha'];c['seeds'][0]['ids']=[{'namespace':'arxiv','value':'https://arxiv.org/abs/2401.12345v2','version':None}]
    normalized=config_input(c)
    assert normalized['query_terms']==['Z term','Alpha']
    assert normalized['seeds'][0]['ids']==[{'namespace':'arxiv','value':'2401.12345','version':2}]
    with pytest.raises(ResearchError):seal('research-config',c)


@pytest.mark.parametrize('value', [
    {'namespace':'openalex','value':'W01','version':None},
    {'namespace':'openalex','value':'w123','version':None},
    {'namespace':'doi','value':'10.1234/ABC','version':None},
    {'namespace':'doi','value':'10.1234/x','version':1},
    {'namespace':'arxiv','value':'2413.12345','version':None},
    {'namespace':'arxiv','value':'2401.12345','version':True},
    {'namespace':'arxiv','value':'2401.12345v2','version':3},
])
def test_sealed_ids_refuse_aliases_and_invalid_versions(value):
    with pytest.raises(ResearchError):identifier(value)


@pytest.mark.parametrize('url',['http://example.org/x','https://user:pass@example.org/x','https://127.0.0.1/x','https://localhost/x','https://host.local/x','https://example.org:8443/x','https://example.org/\npath','https://example.org\\other/x'])
def test_locator_refusals(url):
    with pytest.raises(ResearchError):source_url(url)


def test_mirror_grouping_retains_path_and_query_bytes():
    assert source_url('HTTPS://EXAMPLE.ORG:443/a?b=2#fragment',grouping=True)=='https://example.org/a?b=2'
    assert source_url('https://example.org/a?b=2',grouping=True)!=source_url('https://example.org/a?b=3',grouping=True)


@pytest.mark.parametrize('mutation', [
    lambda d:d['executor'].update(secret='x'), lambda d:d['executor'].update(identity_source='unknown'),
    lambda d:d['executor'].update(tool_name='unknown'), lambda d:d['payload']['results'][0]['mirror'].update(group='fake'),
    lambda d:d['payload']['results'][0].update(provider_score='1.00'), lambda d:d['payload']['results'][0].update(provider_score='-0'),
    lambda d:d['payload']['results'][0].update(provider_score=1.5), lambda d:d['payload']['results'][0].update(published_at='2024-02-30'),
    lambda d:d['payload']['results'][0].update(ordinal=2), lambda d:d.update(outcome='timeout'),
    lambda d:d.update(failure={'code':'bad','message':'actual','retry_after_seconds':None}),
    lambda d:d['payload']['results'][0]['ids'].append(d['payload']['results'][0]['ids'][0]),
])
def test_observation_nested_semantics(mutation):
    _,_,_,_,reqs=pure_round();request=next(iter(reqs.values()))
    original=sealed_observation(request);data=copy.deepcopy(original['data']);mutation(data)
    with pytest.raises(ResearchError):seal('discovery-observation',data)


def test_evidence_newline_allowed_but_size_refused():
    _,_,_,_,reqs=pure_round();request=next(iter(reqs.values()))
    observed=sealed_observation(request,results=[result(request,summary='Line one\nLine two\tvalue')])
    assert validate(observed)==observed
    with pytest.raises(ResearchError):
        sealed_observation(request,results=[result(request,summary='x'*16385)])
    with pytest.raises(ResearchError):parse_json(b' '*(CAPS['research-config']+1),maximum=CAPS['research-config'])
