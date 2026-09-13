from __future__ import annotations

import copy, hashlib, json
from pathlib import Path

import pytest

from video_paper_wiki.catalog_store import (
    build_catalog_database, canonical_export_from_database,
    canonical_search_catalog_export, mapping_from_database, prepare_catalog_material,
)
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.evidence_join import join_evidence
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.projection_runtime import parse_projection_json
from video_paper_wiki.secure_io import SecureIOError

ROOT=Path(__file__).resolve().parents[2]

def material()->dict:
    base=json.loads((ROOT/'tests/fixtures/projection-catalog/complete-baseline.json').read_text())
    paper='arxiv:2311.15127';paths=[
        ('wiki/papers/arxiv-2311.15127.md','paper',paper,'c-000001'),
        ('wiki/code/repo.md','code',None,'c-000002'),
        ('wiki/concepts/task-generation.md','concept',None,'c-000003'),
        ('wiki/index.md','other',None,'l-000004')]
    pages=[];chunks=[];docs={};mapping_chunks=[]
    for i,(path,role,owner,address) in enumerate(paths):
        raw=(f'# {role}\n\nbody {i}\n').encode();body='sha256:'+hashlib.sha256(raw).hexdigest()
        text=raw.decode();record={'schema_version':1,'page_path':path,'page_address':address,'chunk_index':0,'raw_text':text,'contextualized_text':text,'prefix':'','prefix_source':'synthetic','char_count':len(text),'body_hash':body,'page_body_hash':body,'created_at':'2026-09-02T00:00:00Z'}
        chunk_path=f'.vault-meta/chunks/{address}/chunk-000.json';chunk_raw=canonicalize(record)
        pages.append({'path':path,'role':role,'bytes':raw,'paper_id':owner,'page_address':address})
        chunks.append({'path':chunk_path,'bytes':chunk_raw,'record':record})
        cid=address+':0';docs[cid]={'path':chunk_path,'body_hash':body,'page_body_hash':body,'dl':0}
        mapping_chunks.append({'chunk_id':cid,'path':chunk_path,'body_hash':body,'page_body_hash':body,'paper_id':owner,'evidence_unit_ids':[],'default_evidence_unit_ids':[]})
    bm25={'schema_version':2,'params':{'k1':1.2,'b':0.75},'doc_count':len(docs),'avg_dl':0.0,'updated_at':'2026-09-02T00:00:00Z','vocab':{},'docs':docs}
    mapping=join_evidence(inventory={'schema':'video-paper-wiki.evidence-inventory.v1','units':[]},pages={x['path']:x['bytes'] for x in pages},chunks={x['record']['page_address']+':0':x['record'] for x in chunks},bm25=bm25)
    join=mapping['generation_sha256']
    cfg={'schema':'video-paper-wiki.retrieval-config.v1','corpus_version':'fixture','query_version':'fixture','top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,'generation_sha256':join,'mapping_sha256':mapping['mapping_sha256'],'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc','chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}
    builders=[]
    for name in ('video_paper_wiki/catalog_store.py','video_paper_wiki/catalog_reporting.py'):
        builders.append({'path':name,'sha256':hashlib.sha256((ROOT/'src'/name).read_bytes()).hexdigest()})
    builders.sort(key=lambda x:x['path'].encode())
    pages.sort(key=lambda x:x['path'].encode());chunks.sort(key=lambda x:x['path'].encode())
    bm25_raw=json.dumps(bm25,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'base_generation_material':base['generation_material'],'base_tables':base['tables'],'mapping':mapping,'config':cfg,'indexed_pages':pages,'compiled_pages':[{'path':x['path'],'compiler_role':x['role'],'bytes':x['bytes']} for x in pages if x['role']!='other'],'chunks':chunks,'bm25':{'path':'.vault-meta/bm25/index.json','bytes':b' '+bm25_raw+b'\n','record':bm25},'builder_files':builders}

def test_prepare_store_export_is_permutation_stable(tmp_path):
    value=material();prepared=prepare_catalog_material(value);expected=canonical_search_catalog_export(prepared)
    path=tmp_path/'catalog.sqlite';result=build_catalog_database(path,value)
    assert canonical_export_from_database(path)==expected
    assert result['catalog_generation_sha256']==prepared['meta']['catalog_generation_sha256']
    clone=material();clone['base_tables'].reverse()
    for table in clone['base_tables']:table['rows'].reverse()
    assert canonical_search_catalog_export(prepare_catalog_material(clone))==expected

def test_reconstructed_mapping_is_exact(tmp_path):
    value=material();path=tmp_path/'catalog.sqlite';build_catalog_database(path,value)
    import sqlite3
    con=sqlite3.connect(path)
    try:
        cols=[x[1] for x in con.execute('pragma table_info(search_catalog_meta)')]
        meta=dict(zip(cols,con.execute('select * from search_catalog_meta').fetchone()))
        assert mapping_from_database(con,meta)==value['mapping']
    finally:con.close()

@pytest.mark.parametrize('mutation,code',[
    ('mapping','RETRIEVAL_GENERATION_MISMATCH'),('page-extra','CATALOG_INPUT_INVALID'),
    ('owner','CATALOG_ROWS_INVALID'),('compiled','CATALOG_INPUT_INVALID'),('bool','CATALOG_ROWS_INVALID')])
def test_material_refusals(mutation,code):
    value=material()
    if mutation=='mapping':value['config']['mapping_sha256']='f'*64
    elif mutation=='page-extra':
        value['indexed_pages'].append(copy.deepcopy(next(x for x in value['indexed_pages'] if x['role']=='other')));value['indexed_pages'][-1]['path']='wiki/z.md';value['indexed_pages'][-1]['page_address']='l-000099'
    elif mutation=='owner':value['indexed_pages'][0]['paper_id']='arxiv:0001.00001'
    elif mutation=='compiled':value['compiled_pages'][0]['bytes']+=b'x'
    else:
        table=next(x for x in value['base_tables'] if x['name']=='canonical_inputs');table['rows'][0][3]=True
    with pytest.raises(ContractError) as exc:prepare_catalog_material(value)
    assert exc.value.code==code

def test_atomic_failures_preserve_old_database(tmp_path):
    value=material();path=tmp_path/'catalog.sqlite';build_catalog_database(path,value);old=path.read_bytes()
    for phase in ('before-commit','before-replace','after-replace'):
        def fault(observed,phase=phase):
            if observed==phase:raise OSError('injected')
        with pytest.raises(ContractError):build_catalog_database(path,value,fault=fault)
        assert path.read_bytes()==old

def test_retained_reader_rejects_named_parent_replacement(tmp_path):
    from video_paper_wiki.catalog_store import _RetainedFile
    parent=tmp_path/'parent';parent.mkdir();target=parent/'catalog.sqlite';target.write_bytes(b'x')
    held=_RetainedFile(target);moved=tmp_path/'moved';parent.rename(moved);parent.mkdir();(parent/'catalog.sqlite').write_bytes(b'x')
    try:
        with pytest.raises(ContractError) as exc:held.verify()
        assert exc.value.code=='CATALOG_STALE'
    finally:held.close()

def test_retained_reader_allows_unrelated_ancestor_metadata_but_rejects_target_change(tmp_path):
    from video_paper_wiki.catalog_store import _RetainedFile
    parent=tmp_path/'parent';parent.mkdir();target=parent/'catalog.sqlite';target.write_bytes(b'catalog')
    held=_RetainedFile(target)
    try:
        sibling=tmp_path/'readonly-scratch';sibling.mkdir();sibling.rmdir()
        held.verify()
        target.write_bytes(b'changed')
        with pytest.raises(ContractError) as exc:held.verify()
        assert exc.value.code=='CATALOG_STALE'
    finally:held.close()

def test_rollback_never_removes_foreign_replacement(tmp_path):
    path=tmp_path/'catalog.sqlite';foreign=b'foreign database identity'
    def fault(phase):
        if phase=='after-replace':
            replacement=tmp_path/'replacement';replacement.write_bytes(foreign);replacement.replace(path)
            raise OSError('injected after foreign replacement')
    with pytest.raises(ContractError) as exc:build_catalog_database(path,material(),fault=fault)
    assert exc.value.code=='CATALOG_RECOVERY_REQUIRED'
    assert path.read_bytes()==foreign

def test_post_activation_pre_hold_failure_is_recovery_required(tmp_path):
    path=tmp_path/'catalog.sqlite'
    def fault(phase):
        if phase=='after-activation-rename':raise OSError('injected pre-hold failure')
    with pytest.raises(ContractError) as exc:build_catalog_database(path,material(),fault=fault)
    assert exc.value.code=='CATALOG_RECOVERY_REQUIRED'
    assert path.is_file()

def test_git_blob_uses_captured_commit_not_head(monkeypatch,tmp_path):
    import subprocess
    from video_paper_wiki.catalog_store import _git_blob
    seen=[];commit='a'*40
    def run(argv,**_kwargs):
        seen.append(argv);return subprocess.CompletedProcess(argv,0,b'exact pinned bytes',b'')
    monkeypatch.setattr('video_paper_wiki.catalog_store.subprocess.run',run)
    assert _git_blob(tmp_path,commit,'scripts/bm25-index.py')==b'exact pinned bytes'
    assert f'{commit}:scripts/bm25-index.py' in seen[0] and not any(x.startswith('HEAD:') for x in seen[0])

def test_catalog_builder_rejects_vault_root_symlink_before_children(monkeypatch,tmp_path):
    from video_paper_wiki.catalog_store import build_current_catalog
    target=tmp_path/'real';(target/'.vault-meta').mkdir(parents=True);alias=tmp_path/'alias';alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr('video_paper_wiki.catalog_store.verify_upstream',lambda _root:tmp_path/'upstream')
    monkeypatch.setattr('video_paper_wiki.catalog_store._config',lambda _value,**_kw:({},b''))
    monkeypatch.setattr('video_paper_wiki.catalog_store._run_builders',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('child invoked')))
    with pytest.raises(SecureIOError) as exc:build_current_catalog(vault_root=alias,upstream_root='pin',retrieval_config={})
    assert exc.value.code=='CATALOG_BUILD_RACE'

def test_lock_tombstone_does_not_overwrite_second_foreign_lock(monkeypatch,tmp_path):
    from video_paper_wiki.catalog_store import build_current_catalog
    vault=tmp_path/'vault';(vault/'.vault-meta').mkdir(parents=True)
    monkeypatch.setattr('video_paper_wiki.catalog_store.verify_upstream',lambda _root:tmp_path/'upstream')
    monkeypatch.setattr('video_paper_wiki.catalog_store._config',lambda _value,**_kw:({},b''))
    monkeypatch.setattr('video_paper_wiki.catalog_store._run_builders',lambda *_a,**_k:None)
    monkeypatch.setattr('video_paper_wiki.catalog_store.build_catalog_database',lambda *_a,**_k:{'ok':True})
    def collector(**_kwargs):return {}
    def fault(phase):
        if phase=='after-lock-tombstone':(vault/'.vault-meta/locks/catalog-build.lock').write_bytes(b'foreign second lock')
    with pytest.raises(ContractError) as exc:build_current_catalog(vault_root=vault,upstream_root='pin',retrieval_config={},_collector=collector,fault=fault)
    assert exc.value.code=='CATALOG_BUILD_RACE'
    assert (vault/'.vault-meta/locks/catalog-build.lock').read_bytes()==b'foreign second lock'
    assert len(list((vault/'.vault-meta/locks').glob('.catalog-build-owned-*')))==1

def test_exact_extension_ddl_and_resources():
    import sqlite3
    con=sqlite3.connect(':memory:');con.executescript((ROOT/'catalog/base-catalog-v1.sql').read_text());con.executescript((ROOT/'catalog/search-catalog-v1.sql').read_text())
    names=[x[0] for x in con.execute("select name from sqlite_schema where type='table' and name like 'search_%' order by name")]
    assert names==['search_catalog_inputs','search_catalog_meta','search_chunk_evidence','search_chunks','search_compiled_pages','search_evidence_units','search_pages']
    assert con.execute('pragma foreign_key_check').fetchall()==[]

def test_policy_bootstrap_runs_each_child_and_activation_once(monkeypatch,tmp_path):
    from video_paper_wiki import catalog_store as module
    vault=tmp_path/'vault';(vault/'.vault-meta').mkdir(parents=True);events=[]
    policy={'schema':'video-paper-wiki.retrieval-policy.v1','corpus_version':'c','query_version':'q',
        'top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,
        'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc',
        'chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}
    mapping={'generation_sha256':'a'*64,'mapping_sha256':'b'*64}
    monkeypatch.setattr(module,'verify_upstream',lambda _root:tmp_path/'upstream')
    monkeypatch.setattr(module,'_run_builders',lambda _v,_u,observer:[observer(x) for x in ('prefix','bm25')])
    def activate(_path,material,**_kw):
        events.append('sqlite');assert material['config']['generation_sha256']=='a'*64
        config_sha=hashlib.sha256(canonicalize(material['config'])).hexdigest()
        return {'database':module.DB_RELATIVE,'catalog_generation_sha256':'c'*64,'export_sha256':'d'*64,
            'digests':{'join_generation_sha256':'a'*64,'mapping_sha256':'b'*64,
                'retrieval_config_sha256':config_sha,'catalog_generation_sha256':'c'*64}}
    monkeypatch.setattr(module,'build_catalog_database',activate)
    result=module.build_current_catalog(vault_root=vault,upstream_root='pin',retrieval_config=policy,
        _collector=lambda **_kw:{'mapping':mapping},child_observer=events.append)
    assert events==['prefix','bm25','sqlite']
    assert result['retrieval_config']['mapping_sha256']=='b'*64
    assert result['retrieval_config_sha256']==hashlib.sha256(canonicalize(result['retrieval_config'])).hexdigest()
