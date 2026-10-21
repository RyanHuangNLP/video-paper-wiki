from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
import pytest
from tests.support import make_checkout
from video_paper_wiki.cli import main
from video_paper_wiki.contracts import ContractError,validate_document
from video_paper_wiki.domain import compile_code_page,render_seed_catalog,shape_query_results,validate_seed_catalog
from video_paper_wiki.operation_result import bind_operation_result,validate_operation_result_authority
from video_paper_wiki.transaction_contracts import attach_upstream_inspection
from tests.contract.test_transaction_independent import _capture,_plan,_result

def test_packaged_seed_and_rendered_generic_bundle(tmp_path,monkeypatch,capsys):
    make_checkout(tmp_path);monkeypatch.chdir(tmp_path)
    assert len(validate_seed_catalog()['papers'])==67
    assert main(['seed','render','--batch-id','seed1'])==0
    value=json.loads(capsys.readouterr().out)['data']
    assert value['paper_count']==67 and value['concept_count']==6 and value['status']=='provisional'
    bundle=Path(value['bundle_path']); raw=bundle.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==value['bundle_sha256']
    doc=json.loads(raw); assert doc['schema']=='claude-obsidian.transaction.v1' and len(doc['writes'])==74
    assert doc['writes'][-1]['path']=='wiki/video-papers/catalog.md'
    for write in doc['writes']:
        content=bundle.parent/write['content_file']; assert hashlib.sha256(content.read_bytes()).hexdigest()==write['sha256']
    assert 'provisional / metadata-only' in (tmp_path/'.work/seed1/seed/wiki/video-papers/catalog.md').read_text()
    for path in (tmp_path/'.work/seed1/seed/wiki').rglob('*.md'):
        text=path.read_text(); assert text.startswith('---\n') and 'created: 2026-01-01\n' in text and 'tags: [' in text

def test_query_shaping_is_closed_and_ordered():
    value=shape_query_results([{'chunk_id':'syn-'+('a'*64)+':0','score':1.25,'path':'.vault-meta/chunks/syn-'+('a'*64)+'/chunk-000.json','body_hash':'sha256:'+'b'*64,'page_body_hash':'sha256:'+'c'*64}])
    assert value==[{'rank':1,'path':'.vault-meta/chunks/syn-'+('a'*64)+'/chunk-000.json','score':1.25,'chunk_id':'syn-'+('a'*64)+':0','body_hash':'sha256:'+'b'*64,'page_body_hash':'sha256:'+'c'*64}]
    with pytest.raises(ContractError): shape_query_results({'bad':True})

def test_code_page_uses_valid_manifest_fixture():
    manifest=json.loads(Path('tests/fixtures/contracts/valid/video-paper-wiki.code-evidence-manifest.v1.json').read_text())
    text=compile_code_page(manifest); assert '# Owner/Repo · src/model.py' in text and 'status: generated' in text

def test_paper_page_uses_taxonomy_and_escapes_markdown():
    record=json.loads(Path('tests/fixtures/contracts/valid/video-paper-wiki.paper-record.v1.json').read_text())
    record['title']='Unsafe [title]\nnext'
    text=__import__('video_paper_wiki.domain',fromlist=['compile_paper_page']).compile_paper_page(record)
    assert 'tags: ["backbone/dit"]' in text and 'topics:' not in text
    assert '# Unsafe \\[title\\] next' in text
    with pytest.raises(ContractError,match='claim'):
        __import__('video_paper_wiki.domain',fromlist=['compile_paper_page']).compile_paper_page(record,[{'claim_id':'clm-wrong','text':'x'}])

def test_operation_result_authority_binds_result_and_final_bytes():
    proposal=_capture(); plan=_plan(proposal); inspected=attach_upstream_inspection(proposal,plan); result=_result(plan); path=result['changed_paths'][0]
    authority=bind_operation_result(inspected,result,vault_before={path:None},vault_after={path:{'sha256':result['hashes'][path],'mode':result['modes'][path]}})
    assert validate_operation_result_authority(authority)==authority
    bad=copy.deepcopy(authority);bad['vault_after'][path]['sha256']='0'*64
    with pytest.raises(ContractError,match='result does not bind'):validate_operation_result_authority(bad)

def test_inspect_document_uses_strict_bounded_nofollow_reader(tmp_path,capsys):
    from types import SimpleNamespace
    from video_paper_wiki.domain_cli import inspect_document
    target=tmp_path/'doc.json'; target.write_text('{"schema":"x","schema":"x"}')
    assert inspect_document(SimpleNamespace(path=str(target),schema=None),'review.inspect')==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='SCHEMA_INVALID'
    target.unlink(); target.symlink_to(tmp_path/'missing')
    assert inspect_document(SimpleNamespace(path=str(target),schema=None),'review.inspect')==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='DOCUMENT_PATH_UNSAFE'

def test_readonly_upstream_child_uses_private_scratch(tmp_path,monkeypatch):
    import subprocess
    from video_paper_wiki import upstream_runtime
    root=tmp_path/'upstream'; root.mkdir()
    observed={}
    monkeypatch.setattr(upstream_runtime,'verify_upstream',lambda _value:root)
    def run(argv,**kwargs):
        observed.update(kwargs); observed['env_copy']=dict(kwargs['env']); observed['scratch_exists']=Path(kwargs['env']['HOME']).is_dir()
        return subprocess.CompletedProcess(argv,0,b'{}',b'')
    monkeypatch.setattr(upstream_runtime.subprocess,'run',run)
    assert upstream_runtime.bm25_status(vault_root=tmp_path/'vault',upstream_root=root)=={}
    assert set(observed['env_copy'])=={'HOME','TEMP','TMP','TMPDIR'}
    assert len(set(observed['env_copy'].values()))==1 and observed['scratch_exists']
    assert observed['env_copy']['HOME']!=str(root) and not Path(observed['env_copy']['HOME']).exists()
