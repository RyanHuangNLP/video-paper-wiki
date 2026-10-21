from __future__ import annotations
import copy,hashlib,json
from pathlib import Path
import pytest
from video_paper_wiki.contracts import ContractError,validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staged_code_capture import validate_staged_code_capture_request

def request():
    manifest=json.loads(Path('tests/fixtures/contracts/valid/video-paper-wiki.code-evidence-manifest.v1.json').read_text())
    ref=json.loads(Path('tests/fixtures/preflight/code-evidence.approval-ref.json').read_text())
    return {'schema':'video-paper-wiki.staged-code-capture-request.v1','batch_id':'batch-code-1','plan_sha256':'a'*64,'plan_size_bytes':12,'approval_ref':ref,'approval_ref_sha256':hashlib.sha256(canonicalize(ref)).hexdigest(),'payload_file':'prepared/'+manifest['payload']['sha256']+'.blob','manifest':manifest}

def test_request_valid_and_copy_isolated():
    value=request(); checked=validate_staged_code_capture_request(value);checked['manifest']['origin']['path']='x';assert value['manifest']['origin']['path']=='src/model.py'

def test_request_cross_bindings_and_closed_shape():
    for change in ('payload','approval','state','extra'):
        value=request()
        if change=='payload':value['payload_file']='prepared/'+'0'*64+'.blob'
        elif change=='approval':value['approval_ref_sha256']='0'*64
        elif change=='state':value['manifest']['state']='inspected'
        else:value['extra']=True
        with pytest.raises(ContractError):validate_staged_code_capture_request(value)

def test_new_schema_titles_resolve_offline():
    for title in ('video-paper-wiki.staged-code-capture-request.v1','video-paper-wiki.staged-code-capture-authority.v1','video-paper-wiki.operation-result-authority.v1'):
        assert validate_document if title else None
        from video_paper_wiki.contracts import schema_by_title
        assert schema_by_title(title)['title']==title
