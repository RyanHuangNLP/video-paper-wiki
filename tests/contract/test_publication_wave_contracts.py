from __future__ import annotations

import copy
import pytest

from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
from video_paper_wiki.publication import validate_publication_request


@pytest.mark.parametrize("title", [
    "video-paper-wiki.integrity-audit-authority.v1",
    "video-paper-wiki.knowledge-publication-request.v1",
    "video-paper-wiki.publication-authority.v1",
    "video-paper-wiki.review-decision.v1",
    "video-paper-wiki.review-invalidation-request.v1",
    "video-paper-wiki.review-transition-authority.v1",
    "video-paper-wiki.docling-artifact-set.v1",
    "video-paper-wiki.locator-migration-proposal.v1",
])
def test_wave_schemas_are_in_offline_registry(title):
    assert schema_by_title(title)["title"] == title


def test_publication_request_is_closed_and_sorted():
    h = "a" * 64
    value = {"schema":"video-paper-wiki.knowledge-publication-request.v1","batch_id":"batch",
        "operation_id":"op","operation_type":"generic","payloads":[
            {"path":"wiki/meta/records/a.json","content_file":"publication-input/content/"+h,"sha256":h,"size_bytes":1}],
        "claimed_input_paths":[],"additional_read_paths":[],"prospective_groups":[]}
    assert validate_publication_request(value) == value
    for bad in ({**value,"extra":True},{**value,"claimed_input_paths":["z","a"]}):
        with pytest.raises(ContractError) as caught: validate_publication_request(bad)
        assert caught.value.code in {"SCHEMA_INVALID","PUBLICATION_REQUEST_INVALID"}


def test_gate_mechanics_semantics_reject_coherent_shape_forgeries():
    from video_paper_wiki.gate_decision import gate_consumption_id
    request={'schema':'video-paper-wiki.gate-publication-request.v1','batch_id':'g1','operation_id':'g1','gate_id':'HUMAN-GATE-BASELINE-001',
             'decision':{'content_file':'gate-input/content/'+'a'*64,'sha256':'a'*64,'size_bytes':1},
             'baseline_manifest':{'content_file':'gate-input/content/'+'b'*64,'sha256':'b'*64,'size_bytes':2}}
    assert validate_document(request,request['schema'])==request
    bad=copy.deepcopy(request);bad['decision']['content_file']='gate-input/content/'+'c'*64
    with pytest.raises(ContractError,match='descriptor'):validate_document(bad,bad['schema'])
    bad=copy.deepcopy(request);bad['operation_id']='other'
    with pytest.raises(ContractError,match='batch'):validate_document(bad,bad['schema'])
    consumption={'schema':'video-paper-wiki.gate-consumption.v1','consumer_id':'gco-'+'0'*20,'gate_id':'HUMAN-GATE-BASELINE-001','gate_event_id':'gde-'+'1'*20,'work_package':'VPKB-004','artifact_paths':['wiki/papers/a.md'],'recorded_at':'2026-09-02T00:00:00Z'}
    consumption['consumer_id']=gate_consumption_id(consumption);assert validate_document(consumption,consumption['schema'])==consumption
    bad=copy.deepcopy(consumption);bad['artifact_paths']=['wiki/papers/b.md','wiki/papers/a.md'];bad['consumer_id']=gate_consumption_id(bad)
    with pytest.raises(ContractError,match='consumption'):validate_document(bad,bad['schema'])
