import copy, json
from pathlib import Path
import pytest
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.staged_capture import validate_staged_pdf_capture_authority, validate_staged_pdf_capture_request
V=Path('tests/fixtures/contracts/valid')

def load(name): return json.loads((V/name).read_text())

def test_frozen_request_and_authority_dispatch():
    req=load('video-paper-wiki.staged-pdf-capture-request.v1.json')
    auth=load('video-paper-wiki.staged-pdf-capture-authority.v1.json')
    assert validate_staged_pdf_capture_request(req)==validate_document(req)
    assert validate_staged_pdf_capture_authority(auth)==validate_document(auth)

def test_authority_crossed_request_is_rejected():
    auth=load('video-paper-wiki.staged-pdf-capture-authority.v1.json')
    auth['requested_operation_id']='different'
    # reuse request id is deliberately independent, so change the bound payload instead.
    auth['inspection']['source_identity']='a'*64
    with pytest.raises(ContractError): validate_staged_pdf_capture_authority(auth)

def test_non_json_and_cycles_are_schema_invalid():
    req=load('video-paper-wiki.staged-pdf-capture-request.v1.json')
    req[1]=True
    with pytest.raises(ContractError) as exc: validate_staged_pdf_capture_request(req)
    assert exc.value.code=='SCHEMA_INVALID'
    cycle={}; cycle['cycle']=cycle
    with pytest.raises(ContractError) as exc: validate_staged_pdf_capture_request(cycle)
    assert exc.value.code=='SCHEMA_INVALID'
