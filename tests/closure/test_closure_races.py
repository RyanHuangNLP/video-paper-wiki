from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from video_paper_wiki import backup_archive as archive_module
from video_paper_wiki.backup_archive import restore_backup_archive
from video_paper_wiki.contracts import ContractError


def test_prospective_gate_held_fixed(tmp_path:Path,monkeypatch):
    """A canonical, receipt-backed consumer fixes the current gate choice."""
    from video_paper_wiki import receipt_audit
    real_audit=receipt_audit.audit_integrity
    from tests.closure.test_closure_direct import _inspect_gate_fixture
    module,prepared,vault=_inspect_gate_fixture(tmp_path,monkeypatch,successor=True)
    registry=__import__('json').loads((vault/'wiki/meta/registries/gate-heads.json').read_bytes())
    consumption={'schema':'video-paper-wiki.gate-consumption.v1','consumer_id':'gco-'+'0'*20,
        'gate_id':module.GATE,'gate_event_id':registry['event_id'],'work_package':'VPKB-004',
        'artifact_paths':['wiki/papers/held-fixed.md'],'recorded_at':'2026-09-02T00:00:00Z'}
    consumption['consumer_id']=module.gate_consumption_id(consumption)
    relative=f'wiki/meta/gates/{module.GATE}/consumers/{consumption["consumer_id"]}.json'
    target=vault/relative;target.parent.mkdir(parents=True);target.write_bytes(__import__('video_paper_wiki.jcs',fromlist=['canonicalize']).canonicalize(consumption));target.chmod(0o600)
    for path in target.parents:
        if path==vault.parent:break
        path.chmod(0o700)
    from video_paper_wiki.identity import receipt_intent_sha256
    from video_paper_wiki.jcs import canonicalize
    managed=[registry['event_path'],registry['baseline_path'],'wiki/meta/registries/gate-heads.json',relative]
    writes=[]
    for path in sorted(managed):
        raw=(vault/path).read_bytes();writes.append({'path':path,'mode':'create','before_sha256':None,'after_sha256':__import__('hashlib').sha256(raw).hexdigest()})
    receipt={'schema':'video-paper-wiki.operation-receipt.v1','sequence':1,'previous':None,'operation_id':'gate-held-fixed',
        'operation_type':'generic','intent_sha256':'0'*64,'writes':writes,'claimed_inputs':[]}
    receipt['intent_sha256']=receipt_intent_sha256(receipt);receipt_raw=canonicalize(receipt)
    receipt_path='wiki/meta/operations/000000000001-gate-held-fixed.json';rp=vault/receipt_path;rp.parent.mkdir(parents=True);rp.write_bytes(receipt_raw);rp.chmod(0o600)
    head={'schema':'video-paper-wiki.operation-head.v1','sequence':1,'receipt_path':receipt_path,'receipt_sha256':__import__('hashlib').sha256(receipt_raw).hexdigest()}
    hp=vault/'wiki/meta/registries/operation-head.json';hp.write_bytes(canonicalize(head));hp.chmod(0o600)
    for path in vault.rglob('*'):
        if path.is_dir():path.chmod(0o700)
    observed=[]
    monkeypatch.setattr(module,'_gate_inspect_barrier',lambda phase,**_kw:observed.append(phase))
    monkeypatch.setattr('video_paper_wiki.receipt_audit.audit_integrity',real_audit)
    staged=[];monkeypatch.setattr(module,'stage_publication_request',lambda **kw:staged.append(kw) or {})
    with pytest.raises(ContractError) as caught:
        module.inspect_gate(prepared=prepared,operation_id='gatesuccessor',upstream_root='u',vault_root=vault)
    assert caught.value.code=='GATE_STATE_INVALID'
    assert observed==['vault-retained'] and staged==[]


def _operator_gate_harness(monkeypatch,tmp_path:Path,*,drift_at:str):
    from tests.unit.test_operator_cli import _module
    from tests.closure.test_closure_direct import _gate_source
    from video_paper_wiki.catalog_store import _RetainedFile
    module=_module()
    gate_module,decision,manifest=_gate_source(tmp_path,monkeypatch,batch='gate-race-'+drift_at)
    prepared=Path(gate_module.prepare_gate(decision_path=decision,baseline_manifest_path=manifest,batch_id='gate-race-'+drift_at)['request_path'])
    vault=tmp_path/'race-vault';vault.mkdir();vault.chmod(0o700)
    nested=tmp_path/'retained-transaction-bundle.json';nested.write_bytes(b'{}');nested.chmod(0o600)
    root=tmp_path/'upstream';child=[]
    monkeypatch.setattr(module,'_verified_root',lambda _raw:root)
    class Holder:
        def __init__(self):
            self.item=_RetainedFile(nested);self.bundle_path=nested
        def verify(self):self.item.verify_edge('GATE_STATE_INVALID')
        def close(self):self.item.close()
        def __exit__(self,*_a):self.close();return False
    tx={'inspection':{'approval_sha256':'a'*64}}
    authority={'publication_authority':{'transaction':tx,'request':{'payloads':[]}}}
    def inspect(**kw):
        if kw.get('_apply_holder_out') is not None:
            holder=Holder();kw['_apply_holder_out'].append((holder,tmp_path/'bundle.json'))
        return authority
    monkeypatch.setattr('video_paper_wiki.gate_decision.inspect_gate',inspect)
    monkeypatch.setattr(module,'_confirm',lambda _words:True)
    def barrier(phase,**_kw):
        expected='before-prompt' if drift_at=='preprompt' else 'after-prompt'
        if phase==expected:
            replacement=nested.with_suffix('.new');replacement.write_bytes(nested.read_bytes());replacement.chmod(0o600);os.replace(replacement,nested)
    monkeypatch.setattr(module,'_gate_apply_barrier',barrier)
    monkeypatch.setattr(module.subprocess,'run',lambda *_a,**_kw:child.append(1) or __import__('subprocess').CompletedProcess([],0))
    argv=['gate','apply','--prepared',str(prepared),'--operation-id','gate-race-'+drift_at,'--upstream-root',str(root),
        '--vault-root',str(vault),'--approved-plan-sha256','a'*64]
    return module,argv,child,vault


def test_prospective_gate_apply_preprompt_drift(monkeypatch,tmp_path:Path,capsys):
    module,argv,child,_vault=_operator_gate_harness(monkeypatch,tmp_path,drift_at='preprompt')
    assert module.main(argv)==2 and child==[]
    assert __import__('json').loads(capsys.readouterr().out)['error']['code']=='GATE_STATE_INVALID'


def test_prospective_gate_apply_postprompt_drift(monkeypatch,tmp_path:Path,capsys):
    module,argv,child,_vault=_operator_gate_harness(monkeypatch,tmp_path,drift_at='postprompt')
    assert module.main(argv)==2 and child==[]
    assert __import__('json').loads(capsys.readouterr().out)['error']['code']=='GATE_STATE_INVALID'


def test_gate_post_inventory_rejects_deleted_preexisting_empty_directory(tmp_path:Path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('closure_operator_inventory',Path('operator/src/video_paper_wiki_operator/cli.py'))
    assert spec and spec.loader;module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    before=type('Snapshot',(),{'files':{},'directories':{'':'root','wiki':'wiki','wiki/meta':'meta','wiki/meta/reviews':'reviews'}})()
    after=type('Snapshot',(),{'files':{},'directories':{'':'root','wiki':'wiki','wiki/meta':'meta'}})()
    authority={'publication_authority':{'request':{'payloads':[]},'transaction':{'head':{'receipt_path':'wiki/meta/operations/000000000001-g.json'}}}}
    with pytest.raises(ContractError) as caught:module._verify_gate_post_inventory(before,after,authority)
    assert caught.value.code=='GATE_STATE_INVALID'


def _empty(root: Path) -> Path:
    root.mkdir(mode=0o700);root.chmod(0o700);return root


def test_restore_file_race(closure_backup,tmp_path:Path,monkeypatch):
    source,manifest,archive=closure_backup;target=_empty(tmp_path/'restore-file-race')
    from video_paper_wiki import backup_manifest
    original=backup_manifest.verify_restored_tree
    def barrier(root,*args,**kwargs):
        victim=Path(root)/manifest['files'][0]['path'];replacement=victim.with_name(victim.name+'.new')
        replacement.write_bytes(victim.read_bytes());replacement.chmod(manifest['files'][0]['mode']);os.replace(replacement,victim)
        return original(root,*args,**kwargs)
    monkeypatch.setattr(backup_manifest,'verify_restored_tree',barrier)
    with pytest.raises(ContractError) as caught:restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert caught.value.code=='RESTORE_VERIFICATION_FAILED'


def test_restore_parent_aba(closure_backup,tmp_path:Path,monkeypatch):
    source,manifest,archive=closure_backup;target=_empty(tmp_path/'restore-parent-aba')
    from video_paper_wiki import backup_manifest
    original=backup_manifest.verify_restored_tree
    def barrier(root,*args,**kwargs):
        root=Path(root);replacement=root.with_name(root.name+'-replacement');shutil.copytree(root,replacement);replacement.chmod(0o700)
        moved=root.with_name(root.name+'-old');root.rename(moved);replacement.rename(root)
        return original(root,*args,**kwargs)
    monkeypatch.setattr(backup_manifest,'verify_restored_tree',barrier)
    with pytest.raises(ContractError) as caught:restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert caught.value.code=='RESTORE_ROOT_UNSAFE'


def test_restore_source_aba(closure_backup,tmp_path:Path,monkeypatch):
    source,manifest,archive=closure_backup;target=_empty(tmp_path/'restore-source-aba');original=archive_module._decode
    def barrier(raw):
        moved=source.with_name(source.name+'-old');source.rename(moved);shutil.copytree(moved,source);source.chmod(0o700)
        return original(raw)
    monkeypatch.setattr(archive_module,'_decode',barrier)
    with pytest.raises(ContractError) as caught:restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert caught.value.code=='RESTORE_VERIFICATION_FAILED'


def test_restore_postcheck_failure(closure_backup,tmp_path:Path,monkeypatch):
    source,manifest,archive=closure_backup;target=_empty(tmp_path/'restore-postcheck')
    from video_paper_wiki import backup_manifest
    monkeypatch.setattr(backup_manifest,'verify_restored_tree',lambda *_a,**_kw:(_ for _ in ()).throw(ContractError('RESTORE_VERIFICATION_FAILED','postcheck failed')))
    with pytest.raises(ContractError) as caught:restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert caught.value.code=='RESTORE_VERIFICATION_FAILED'


def test_prospective_restore_source_aba(closure_backup,tmp_path:Path,monkeypatch):
    test_restore_source_aba(closure_backup,tmp_path,monkeypatch)
