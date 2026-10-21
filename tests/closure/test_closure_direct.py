from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from video_paper_wiki.backup_archive import restore_backup_archive
from video_paper_wiki.backup_manifest import verify_restored_tree
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from tests.closure.test_installed_vertical import (installed_cli,installed_vertical_session,_env,_json,_pty_json,_tree_snapshot,
    _assert_external_gates_remain_open)

ROOT=Path(__file__).resolve().parents[2]


def test_restore_same_root(closure_backup):
    source,manifest,archive=closure_backup
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive,source_root=source,restore_root=source,manifest=manifest)
    assert caught.value.code=='RESTORE_ROOT_UNSAFE',caught.value.message


def test_restore_0755(closure_backup,tmp_path:Path):
    source,manifest,archive=closure_backup;target=tmp_path/'restore';target.mkdir(mode=0o755);target.chmod(0o755)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert caught.value.code=='RESTORE_ROOT_UNSAFE',(caught.value.message,caught.value.details)


def test_restore_extra_file(closure_backup,tmp_path:Path):
    source,manifest,_archive=closure_backup;target=tmp_path/'restore-extra'
    import shutil
    shutil.copytree(source,target);target.chmod(0o700);extra=target/'wiki/extra.md';extra.write_bytes(b'extra');extra.chmod(0o600)
    with pytest.raises(ContractError) as caught:verify_restored_tree(target,manifest,source_root=source)
    assert caught.value.code=='RESTORE_VERIFICATION_FAILED'


def test_archive_manifest_mismatch(closure_backup,tmp_path:Path):
    source,manifest,archive=closure_backup;target=tmp_path/'restore-mismatch';target.mkdir(mode=0o700);target.chmod(0o700)
    wrong=copy.deepcopy(manifest);wrong['source_anchor']='f'*64
    wrong['manifest_sha256']=hashlib.sha256(canonicalize({k:v for k,v in wrong.items() if k!='manifest_sha256'})).hexdigest()
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=wrong)
    assert caught.value.code=='BACKUP_ARCHIVE_INVALID'


def _entry_limit_manifest(count:int):
    value={'schema':'video-paper-wiki.backup-manifest.v1','policy':'vpwiki-private-archive-complete-set-v1','source_anchor':'a'*64,
        'excluded':['.vault-meta','.work'],'roots':['.raw','wiki'],'directories':[{'path':f'd{i:05d}','mode':0o700} for i in range(count)],
        'files':[],'raw_included':True,'manifest_sha256':'0'*64}
    value['manifest_sha256']=hashlib.sha256(canonicalize({k:v for k,v in value.items() if k!='manifest_sha256'})).hexdigest();return value


def test_prospective_zip_classic_max(tmp_path:Path):
    from video_paper_wiki.backup_archive import encode_backup_archive,_decode
    manifest=_entry_limit_manifest(65_534);raw=encode_backup_archive(vault_root=tmp_path,manifest=manifest)
    assert _decode(raw)[0]['manifest_sha256']==manifest['manifest_sha256']


def test_prospective_zip_classic_overflow(tmp_path:Path):
    from video_paper_wiki.backup_archive import encode_backup_archive
    with pytest.raises(ContractError) as caught:encode_backup_archive(vault_root=tmp_path,manifest=_entry_limit_manifest(65_535))
    assert caught.value.code=='BACKUP_MANIFEST_INVALID'


def test_restore_symlink_root_is_unsafe(closure_backup,tmp_path:Path):
    source,manifest,archive=closure_backup;real=tmp_path/'real';real.mkdir(mode=0o700);real.chmod(0o700);link=tmp_path/'restore-link';link.symlink_to(real)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive,source_root=source,restore_root=link,manifest=manifest)
    assert caught.value.code=='RESTORE_ROOT_UNSAFE',(caught.value.message,caught.value.details)


def test_restore_symlink_parent(closure_backup,tmp_path:Path):
    source,manifest,archive=closure_backup;real=tmp_path/'real-parent';real.mkdir(mode=0o700);real.chmod(0o700)
    root=real/'restore';root.mkdir(mode=0o700);root.chmod(0o700);link=tmp_path/'linked-parent';link.symlink_to(real)
    with pytest.raises(ContractError) as caught:
        restore_backup_archive(archive=archive,source_root=source,restore_root=link/'restore',manifest=manifest)
    assert caught.value.code=='RESTORE_ROOT_UNSAFE'


def test_gate_holder_retains_bundle_and_all_transaction_content(tmp_path:Path,monkeypatch):
    from tests.support import make_checkout
    from video_paper_wiki import gate_decision as module
    from video_paper_wiki.identity import gate_event_id
    make_checkout(tmp_path);monkeypatch.chdir(tmp_path)
    manifest=canonicalize({'papers':3,'repositories':5});decision={'schema':'video-paper-wiki.gate-decision.v1',
        'gate_id':module.GATE,'event_id':'gde-'+'0'*20,'previous_event_id':None,'actor_kind':'human',
        'choice':'keep-modelscope','baseline_manifest_sha256':hashlib.sha256(manifest).hexdigest(),
        'derived_full_map_repo_ids':module.CHOICES['keep-modelscope'],'decided_by':'synthetic-test-only',
        'decided_at':'2026-09-02T00:00:00Z','reason':'mechanical fixture'}
    decision['event_id']=gate_event_id(decision);dpath=tmp_path/'decision.json';mpath=tmp_path/'manifest.json'
    dpath.write_bytes(canonicalize(decision));mpath.write_bytes(manifest)
    prepared=module.prepare_gate(decision_path=dpath,baseline_manifest_path=mpath,batch_id='gate-held')['request_path']
    base=tmp_path/'.work/gate-held/transaction-inspect';content=base/'content';content.mkdir(parents=True)
    payload=b'payload';digest=hashlib.sha256(payload).hexdigest();(content/digest).write_bytes(payload)
    bundle=b'{}';(base/'bundle.json').write_bytes(bundle)
    publication_content=b'publication';publication_digest=hashlib.sha256(publication_content).hexdigest()
    pcontent=tmp_path/'.work/gate-held/publication-input/content';pcontent.mkdir(parents=True)
    (pcontent/publication_digest).write_bytes(publication_content)
    (pcontent.parent/'knowledge-publication-request.v1.json').write_bytes(b'{}')
    staging={'batch_id':'gate-held','bundle_file':'transaction-inspect/bundle.json',
        'bundle_sha256':hashlib.sha256(bundle).hexdigest(),'bundle_size_bytes':len(bundle),
        'content_files':[{'content_file':f'transaction-inspect/content/{digest}','sha256':digest,'size_bytes':len(payload)}]}
    authority={'publication_authority':{'transaction_staging':staging,'request':{'payloads':[
        {'content_file':f'publication-input/content/{publication_digest}'}]}}}
    monkeypatch.setattr(module,'validate_document',lambda value,_schema:value)
    with pytest.raises(ContractError) as caught:
        with module._retained_gate_bundle(prepared,authority):
            replacement=content/'replacement';replacement.write_bytes(payload);os.replace(replacement,content/digest)
    assert caught.value.code=='GATE_STATE_INVALID'


def test_backup_extra_managed(closure_backup):
    from video_paper_wiki.backup_manifest import build_backup_manifest
    source,manifest,_archive=closure_backup
    extra=source/'wiki/papers/unreceipted.md';extra.write_bytes(b'extra');extra.chmod(0o600)
    with pytest.raises(ContractError) as caught:build_backup_manifest(source)
    assert caught.value.code=='BACKUP_MANIFEST_INVALID'


def test_review_gate_forgery(monkeypatch,tmp_path:Path,capsys):
    import importlib.util,subprocess
    spec=importlib.util.spec_from_file_location('closure_operator_review',Path('operator/src/video_paper_wiki_operator/cli.py'))
    assert spec and spec.loader;cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    class Held:
        def __init__(self,*_a,**_kw):pass
        def verify(self):pass
        def close(self):pass
    monkeypatch.setattr(cli,'_verified_root',lambda _raw:tmp_path/'upstream')
    monkeypatch.setattr('video_paper_wiki.gate_decision._Prepared',Held);monkeypatch.setattr('video_paper_wiki.receipt_audit._Snapshot',Held)
    class AuthorityHolder:
        bundle_path=tmp_path/'bundle.json'
        def verify(self):pass
        def close(self):pass
        def __exit__(self,*_a):self.close();return False
    def inspected(**kw):
        if kw.get('_apply_holder_out') is not None:kw['_apply_holder_out'].append((AuthorityHolder(),tmp_path/'bundle.json'))
        return {'publication_authority':{'transaction':{'inspection':{'approval_sha256':'a'*64}}}}
    monkeypatch.setattr('video_paper_wiki.gate_decision.inspect_gate',inspected)
    calls=[];monkeypatch.setattr(cli.subprocess,'run',lambda *_a,**_kw:calls.append(1) or subprocess.CompletedProcess([],0))
    code=cli.main(['gate','apply','--prepared','p','--operation-id','g','--upstream-root','u','--vault-root','v','--approved-plan-sha256','b'*64])
    assert code==2 and calls==[]
    assert __import__('json').loads(capsys.readouterr().out)['error']['code']=='HUMAN_APPROVAL_REQUIRED'


def _gate_source(tmp_path:Path,monkeypatch,*,choice='keep-modelscope',repos=None,manifest_raw=None,batch='gate-direct'):
    from tests.support import make_checkout
    from video_paper_wiki import gate_decision as module
    from video_paper_wiki.identity import gate_event_id
    make_checkout(tmp_path);monkeypatch.chdir(tmp_path)
    raw=manifest_raw if manifest_raw is not None else canonicalize({'papers':3,'repositories':5})
    decision={'schema':'video-paper-wiki.gate-decision.v1','gate_id':module.GATE,'event_id':'gde-'+'0'*20,
        'previous_event_id':None,'actor_kind':'human','choice':choice,'baseline_manifest_sha256':hashlib.sha256(raw).hexdigest(),
        'derived_full_map_repo_ids':repos if repos is not None else module.CHOICES.get(choice,[]),'decided_by':'synthetic-test-only',
        'decided_at':'2026-09-02T00:00:00Z','reason':'mechanical fixture'}
    decision['event_id']=gate_event_id(decision);d=tmp_path/f'{batch}-decision.json';m=tmp_path/f'{batch}-manifest.json'
    d.write_bytes(canonicalize(decision));m.write_bytes(raw)
    return module,d,m


def test_prospective_gate_prepare_baseline_float(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,manifest_raw=b'{"papers":3.5,"repositories":5}',batch='float')
    with pytest.raises(ContractError) as caught:module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='float')
    assert caught.value.code=='GATE_MANIFEST_INVALID'


def test_prospective_gate_prepare_baseline_duplicate_key(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,manifest_raw=b'{"papers":3,"papers":3,"repositories":5}',batch='duplicate')
    with pytest.raises(ContractError) as caught:module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='duplicate')
    assert caught.value.code=='GATE_MANIFEST_INVALID'


def test_prospective_gate_five_keep_exact(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,choice='keep-modelscope',batch='keepfive')
    result=module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='keepfive')
    assert module.CHOICES['keep-modelscope']==['github:stability-ai/generative-models','github:thudm/cogvideo','github:snap-research/panda-70m','github:ji4chenli/t2v-turbo','github:vchitect/vbench']
    raw=d.read_bytes();assert result['request']['decision']=={'content_file':'gate-input/content/'+hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}


def test_prospective_gate_five_replace_exact(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,choice='replace-with-open-sora',batch='replacefive')
    result=module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='replacefive')
    assert module.CHOICES['replace-with-open-sora']==['github:stability-ai/generative-models','github:hpcaitech/open-sora','github:snap-research/panda-70m','github:ji4chenli/t2v-turbo','github:vchitect/vbench']
    raw=d.read_bytes();assert result['request']['decision']['sha256']==hashlib.sha256(raw).hexdigest()


def test_prospective_gate_five_order(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,repos=list(reversed(__import__('video_paper_wiki.gate_decision',fromlist=['CHOICES']).CHOICES['keep-modelscope'])),batch='badorder')
    with pytest.raises(ContractError) as caught:module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='badorder')
    assert caught.value.code=='GATE_DECISION_INVALID'


def test_prospective_gate_five_alias_case(tmp_path:Path,monkeypatch):
    module,d,m=_gate_source(tmp_path,monkeypatch,repos=[x.upper() for x in __import__('video_paper_wiki.gate_decision',fromlist=['CHOICES']).CHOICES['keep-modelscope']],batch='badcase')
    with pytest.raises(ContractError) as caught:module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='badcase')
    assert caught.value.code=='GATE_DECISION_INVALID'


def test_prospective_restore_source_required(capsys):
    import importlib.util
    spec=importlib.util.spec_from_file_location('closure_operator',Path('operator/src/video_paper_wiki_operator/cli.py'))
    assert spec and spec.loader;cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.main(['backup','restore','--archive','a','--restore-root','r','--manifest','m','--upstream-root','u','--config','c'])==2
    assert __import__('json').loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'


def test_prospective_agent_verify_no_build(monkeypatch,installed_cli,installed_vertical_session):
    session=installed_vertical_session;restore=session['restore'];before=_tree_snapshot(restore)
    helper=ROOT/'tests/closure/_installed_restore_verify.py'
    process_tmp=session['root']/'verify-tmp';process_tmp.mkdir()
    completed=subprocess.run([str(installed_cli/'python'),str(helper),str(session['source']),str(restore),
        str(session['root']/'backup-manifest.json'),str(ROOT/'vendor/claude-obsidian'),
        str(session['restore_config_path'])],cwd=session['root'],env={'PATH':'/usr/bin:/bin','HOME':str(session['root']),
        'TMPDIR':str(process_tmp),'PYTHONDONTWRITEBYTECODE':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    observed=json.loads(completed.stdout);result=observed['result']
    assert result['valid'] is True and result['tree']['valid'] is True
    assert result['audit']['classification']=='receipt_backed'
    assert result['catalog_status']['state']=='current'
    assert result['query_generation_sha256']==result['report_generation_sha256']==result['catalog_status']['catalog_generation_sha256']
    assert result['external_backup_observation'] is False and result['strict_lint_summary']['issues_found']==0
    assert _tree_snapshot(restore)==before and observed['unchanged'] is True and observed['writers']==[]
    assert observed['children'] and all(' build' not in ' '.join(argv) and ' apply' not in ' '.join(argv)
        for argv in observed['children'])


def _inspect_gate_fixture(tmp_path:Path,monkeypatch,*,successor:bool=False,fork:bool=False):
    module,d,m=_gate_source(tmp_path,monkeypatch,batch='gatesuccessor' if successor else 'gategenesis')
    if successor:
        prior=__import__('json').loads(d.read_text());prior['event_id']='gde-'+'0'*20;prior['previous_event_id']=None
        from video_paper_wiki.identity import gate_event_id
        prior['event_id']=gate_event_id(prior);prior_raw=canonicalize(prior)
        current=__import__('json').loads(d.read_text());current['previous_event_id']='gde-'+'f'*20 if fork else prior['event_id'];current['event_id']='gde-'+'0'*20;current['event_id']=gate_event_id(current);d.write_bytes(canonicalize(current))
    prepared=module.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='gatesuccessor' if successor else 'gategenesis')['request_path']
    vault=tmp_path/'vault';vault.mkdir();current_paths=[]
    if successor:
        baseline=m.read_bytes();event=f'wiki/meta/gates/{module.GATE}/{prior["event_id"]}.json';base=f'.raw/derived/gates/{prior["baseline_manifest_sha256"]}.json'
        registry={'schema':'video-paper-wiki.gate-head-registry.v1','gate_id':module.GATE,'event_id':prior['event_id'],'event_path':event,
            'event_sha256':hashlib.sha256(prior_raw).hexdigest(),'choice':prior['choice'],'baseline_path':base,'baseline_sha256':hashlib.sha256(baseline).hexdigest(),
            'repository_ids':prior['derived_full_map_repo_ids'],'decided_at':prior['decided_at']}
        for relative,data in ((event,prior_raw),(base,baseline),('wiki/meta/registries/gate-heads.json',canonicalize(registry))):
            target=vault/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(0o600);current_paths.append(relative)
        for path in vault.rglob('*'):
            if path.is_dir():path.chmod(0o700)
    monkeypatch.setattr('video_paper_wiki.receipt_audit.audit_integrity',lambda *_a,**_kw:{'classification':'receipt_backed','current_paths':current_paths})
    monkeypatch.setattr(module,'stage_publication_request',lambda **_kw:{'request_path':'publication'})
    monkeypatch.setattr(module,'inspect_publication',lambda **_kw:{'request':{'operation_id':'gatesuccessor' if successor else 'gategenesis'}})
    real=module.validate_document
    monkeypatch.setattr(module,'validate_document',lambda value,title:value if title=='video-paper-wiki.gate-publication-authority.v1' else real(value,title))
    return module,prepared,vault


@pytest.mark.parametrize('variant',['absent','out-of-band','different'])
def test_gate_baseline_refusals_happen_before_staging(tmp_path,monkeypatch,variant):
    successor=variant=='different'
    module,prepared,vault=_inspect_gate_fixture(tmp_path,monkeypatch,successor=successor)
    request,decision_raw,manifest_raw=module._prepared(prepared);decision=json.loads(decision_raw)
    baseline=f'.raw/derived/gates/{decision["baseline_manifest_sha256"]}.json'
    if variant=='out-of-band':
        target=vault/baseline;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(manifest_raw);target.chmod(0o600)
        for path in target.parents:
            if path==vault:break
            path.chmod(0o700)
    elif variant=='different':
        (vault/baseline).write_bytes(b'{"different":true}')
    before=_tree_snapshot(vault);calls=[]
    monkeypatch.setattr(module,'stage_publication_request',lambda **_kw:calls.append(_kw) or (_ for _ in ()).throw(AssertionError('staged')))
    with pytest.raises(ContractError) as caught:
        module.inspect_gate(prepared=prepared,operation_id=request['operation_id'],upstream_root='u',vault_root=vault)
    assert caught.value.code=='GATE_STATE_INVALID' and calls==[] and _tree_snapshot(vault)==before
    assert not (Path(prepared).parents[1]/'publication-input').exists()


def test_gate_fork_refusal_happens_before_staging(tmp_path,monkeypatch):
    module,prepared,vault=_inspect_gate_fixture(tmp_path,monkeypatch,successor=True,fork=True)
    before=_tree_snapshot(vault);calls=[]
    monkeypatch.setattr(module,'stage_publication_request',lambda **_kw:calls.append(_kw) or (_ for _ in ()).throw(AssertionError('staged')))
    with pytest.raises(ContractError) as caught:
        module.inspect_gate(prepared=prepared,operation_id='gatesuccessor',upstream_root='u',vault_root=vault)
    assert caught.value.code=='GATE_STATE_INVALID' and calls==[] and _tree_snapshot(vault)==before


@pytest.fixture(scope='module')
def real_gate_session(installed_cli,installed_vertical_session,tmp_path_factory):
    from tests.support import make_checkout
    from video_paper_wiki.contracts import validate_document
    from video_paper_wiki.gate_decision import CHOICES,GATE
    from video_paper_wiki.identity import gate_event_id
    root=tmp_path_factory.mktemp('vpwiki-real-gate');checkout=root/'checkout';checkout.mkdir();make_checkout(checkout)
    vault=root/'vault';shutil.copytree(installed_vertical_session['source'],vault)
    env=_env(installed_cli,root);vpwiki=installed_cli/'vpwiki';admin=installed_cli/'vpwiki-admin';upstream=ROOT/'vendor/claude-obsidian'
    baseline=canonicalize({'papers':3,'repositories':5});baseline_path=root/'baseline.json';baseline_path.write_bytes(baseline)
    baseline_relative=f'.raw/derived/gates/{hashlib.sha256(baseline).hexdigest()}.json'
    from video_paper_wiki.publication import stage_publication_request
    def publish_baseline(raw,batch):
        relative=f'.raw/derived/gates/{hashlib.sha256(raw).hexdigest()}.json'
        previous_cwd=Path.cwd();os.chdir(checkout)
        try:stage_publication_request(batch_id=batch,operation_id=batch,
            operation_type='ingest',payloads={relative:raw},claimed_input_paths=[])
        finally:os.chdir(previous_cwd)
        publication=_json([vpwiki,'publication','inspect','--prepared',
            checkout/f'.work/{batch}/publication-input/knowledge-publication-request.v1.json',
            '--operation-id',batch,'--upstream-root',upstream,'--vault-root',vault],cwd=checkout,env=env)['data']
        approval=publication['transaction']['inspection']['approval_sha256']
        _pty_json([admin,'transaction','apply','--bundle',checkout/f'.work/{batch}/transaction-inspect/bundle.json',
            '--vault-root',vault,'--upstream-root',upstream,'--approved-plan-sha256',approval],
            'transaction apply',cwd=checkout,env=env)
        return relative
    publish_baseline(baseline,'gate-baseline-real')
    def decision(previous,when,reason,manifest=baseline):
        value={'schema':'video-paper-wiki.gate-decision.v1','gate_id':GATE,'event_id':'gde-'+'0'*20,
            'previous_event_id':previous,'actor_kind':'human','choice':'keep-modelscope',
            'baseline_manifest_sha256':hashlib.sha256(manifest).hexdigest(),
            'derived_full_map_repo_ids':CHOICES['keep-modelscope'],'decided_by':'synthetic-test-only',
            'decided_at':when,'reason':reason}
        value['event_id']=gate_event_id(value);return value
    def prepare_inspect(value,batch,*,manifest_path=baseline_path,expected=0):
        path=root/(batch+'-decision.json');path.write_bytes(canonicalize(value))
        prepared=_json([vpwiki,'gate','prepare','--decision',path,'--baseline-manifest',manifest_path,
            '--batch-id',batch],cwd=checkout,env=env)['data']['request_path']
        before=_tree_snapshot(vault)
        observed=_json([vpwiki,'gate','inspect','--prepared',prepared,'--operation-id',batch,
            '--upstream-root',upstream,'--vault-root',vault],cwd=checkout,env=env,expected=expected)
        after=_tree_snapshot(vault);assert before==after
        return prepared,observed,before
    genesis=decision(None,'2026-09-02T01:00:00Z','mechanical genesis fixture')
    prepared,genesis_envelope,genesis_before=prepare_inspect(genesis,'gate-genesis-real')
    authority=genesis_envelope['data'];validate_document(authority,'video-paper-wiki.gate-publication-authority.v1')
    pre_head=json.loads((vault/'wiki/meta/registries/operation-head.json').read_bytes())
    approval=authority['publication_authority']['transaction']['inspection']['approval_sha256']
    applied,_=_pty_json([admin,'gate','apply','--prepared',prepared,'--operation-id','gate-genesis-real',
        '--upstream-root',upstream,'--vault-root',vault,'--approved-plan-sha256',approval],
        'gate apply',cwd=checkout,env=env)
    applied=applied['data'];post_head=json.loads((vault/'wiki/meta/registries/operation-head.json').read_bytes())
    receipt=json.loads((vault/post_head['receipt_path']).read_bytes())
    registry=json.loads((vault/'wiki/meta/registries/gate-heads.json').read_bytes())
    alternate=canonicalize({'papers':3,'repositories':5,'revision':2});alternate_path=root/'baseline-alternate.json';alternate_path.write_bytes(alternate)
    alternate_relative=publish_baseline(alternate,'gate-baseline-alternate-real')
    successor=decision(registry['event_id'],'2026-09-02T02:00:00Z','mechanical successor fixture')
    successor_prepared,successor_envelope,successor_before=prepare_inspect(successor,'gate-successor-real')
    successor_authority=successor_envelope['data'];validate_document(successor_authority,'video-paper-wiki.gate-publication-authority.v1')
    changed=decision(registry['event_id'],'2026-09-02T02:30:00Z','mechanical changed baseline fixture',alternate)
    _changed_prepared,changed_envelope,changed_before=prepare_inspect(changed,'gate-successor-changed-real',manifest_path=alternate_path)
    changed_authority=changed_envelope['data'];validate_document(changed_authority,'video-paper-wiki.gate-publication-authority.v1')
    fork=decision('gde-'+'f'*20,'2026-09-02T03:00:00Z','mechanical fork rejection fixture')
    _fork_prepared,fork_envelope,fork_before=prepare_inspect(fork,'gate-fork-real',expected=2)
    return {'vault':vault,'baseline':baseline,'baseline_relative':baseline_relative,'genesis':genesis,'authority':authority,'genesis_before':genesis_before,
        'applied':applied,'pre_head':pre_head,'post_head':post_head,'receipt':receipt,'registry':registry,
        'successor':successor,'successor_authority':successor_authority,'successor_before':successor_before,
        'successor_prepared':successor_prepared,'alternate':alternate,'alternate_relative':alternate_relative,
        'changed':changed,'changed_authority':changed_authority,'changed_before':changed_before,
        'fork':fork,'fork_envelope':fork_envelope,'fork_before':fork_before}


def test_prospective_gate_inspect_genesis(real_gate_session):
    value=real_gate_session;authority=value['authority'];publication=authority['publication_authority']
    assert authority['decision']==value['genesis'] and authority['decision']['previous_event_id'] is None
    assert authority['registry']['event_id']==authority['decision']['event_id']
    assert authority['human_gate_satisfied'] is False and value['applied']['external_gate_satisfied'] is False
    assert value['applied']['published_gate_state']=='closed' and value['applied']['receipt_audit']['classification']=='receipt_backed'
    payloads={row['path'] for row in publication['request']['payloads']}
    assert payloads=={authority['registry']['event_path'],'wiki/meta/registries/gate-heads.json'}
    assert authority['registry']['baseline_path'] in publication['request']['claimed_input_paths']
    assert value['post_head']==publication['transaction']['head']
    assert value['receipt']['sequence']==value['pre_head']['sequence']+1
    assert value['receipt']['previous']=={'path':value['pre_head']['receipt_path'],'sha256':value['pre_head']['receipt_sha256']}
    assert json.loads((value['vault']/authority['registry']['event_path']).read_bytes())==authority['decision']
    assert (value['vault']/authority['registry']['baseline_path']).read_bytes()==value['baseline']


def test_prospective_gate_inspect_successor(real_gate_session):
    value=real_gate_session;authority=value['successor_authority'];prior=value['registry']
    assert authority['decision']==value['successor']
    assert authority['decision']['previous_event_id']==prior['event_id']
    assert authority['registry']['event_id']==authority['decision']['event_id']!=prior['event_id']
    request=authority['publication_authority']['request'];claimed=set(request['claimed_input_paths'])
    assert claimed=={prior['event_path'],prior['baseline_path']}
    transaction=authority['publication_authority']['transaction']
    assert transaction['expected_hashes']['wiki/meta/registries/gate-heads.json']==hashlib.sha256(canonicalize(prior)).hexdigest()
    registry_write=next(row for row in transaction['writes'] if row['path']=='wiki/meta/registries/gate-heads.json')
    assert registry_write['mode']=='replace'
    assert {row['path'] for row in request['payloads']}=={
        authority['registry']['event_path'],'wiki/meta/registries/gate-heads.json'}
    assert _tree_snapshot(value['vault'])==value['successor_before']


def test_gate_successor_changed_baseline_claims_both_receipt_backed_baselines(real_gate_session):
    value=real_gate_session;authority=value['changed_authority'];prior=value['registry']
    claims=set(authority['publication_authority']['request']['claimed_input_paths'])
    assert claims=={prior['event_path'],prior['baseline_path'],value['alternate_relative']}
    assert {row['path'] for row in authority['publication_authority']['request']['payloads']}=={
        authority['registry']['event_path'],'wiki/meta/registries/gate-heads.json'}
    assert authority['registry']['baseline_path']==value['alternate_relative']
    assert _tree_snapshot(value['vault'])==value['changed_before']


def test_gate_successor_changed_baseline_missing_prior_claim_is_rejected(real_gate_session):
    from video_paper_wiki.contracts import validate_document
    value=real_gate_session;forged=copy.deepcopy(value['changed_authority'])
    claims=forged['publication_authority']['request']['claimed_input_paths']
    claims.remove(value['registry']['baseline_path'])
    with pytest.raises(ContractError) as caught:
        validate_document(forged,'video-paper-wiki.gate-publication-authority.v1')
    assert caught.value.code=='GATE_STATE_INVALID'


def test_gate_successor_second_extra_baseline_claim_is_rejected(real_gate_session):
    from video_paper_wiki.contracts import validate_document
    forged=copy.deepcopy(real_gate_session['changed_authority'])
    forged['publication_authority']['request']['claimed_input_paths'].append('.raw/derived/gates/'+'f'*64+'.json')
    forged['publication_authority']['request']['claimed_input_paths'].sort()
    with pytest.raises(ContractError) as caught:
        validate_document(forged,'video-paper-wiki.gate-publication-authority.v1')
    assert caught.value.code=='GATE_STATE_INVALID'


def test_prospective_gate_inspect_fork(real_gate_session):
    value=real_gate_session
    assert value['fork_envelope']['error']['code']=='GATE_STATE_INVALID'
    assert _tree_snapshot(value['vault'])==value['fork_before']


def test_external_gates_remain_open(installed_vertical_session,real_gate_session,tmp_path,monkeypatch):
    _assert_external_gates_remain_open(installed_vertical_session,real_gate_session,tmp_path,monkeypatch)
