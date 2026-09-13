from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from tests.closure.test_installed_vertical import installed_cli, _env
from tests.support import make_checkout
from video_paper_wiki.identity import gate_event_id
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize


def _policy(path: Path) -> None:
    path.write_bytes(canonicalize({'schema':'video-paper-wiki.retrieval-policy.v1','corpus_version':'closure',
        'query_version':'closure','top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,
        'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc',
        'chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}))

def _tree(root:Path):
    rows=[]
    for path in sorted(root.rglob('*')):
        info=path.lstat();relative=path.relative_to(root).as_posix()
        rows.append((relative,info.st_mode,hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None))
    return rows


def test_operator_nontty_catalog_build(installed_cli, tmp_path: Path):
    policy=tmp_path/'policy.json';_policy(policy);vault=tmp_path/'vault';vault.mkdir()
    result=subprocess.run([str(installed_cli/'vpwiki-admin'),'catalog','build','--vault-root',str(vault),
        '--upstream-root',str(tmp_path/'never-authenticated'),'--config',str(policy)],cwd=tmp_path,
        env=_env(installed_cli,tmp_path),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert result.returncode==2
    assert json.loads(result.stdout)['error']['code']=='OPERATOR_CONFIRMATION_REQUIRED'
    assert not (vault/'.vault-meta').exists()


def test_gate_apply_real_nontty(installed_cli, closure_backup, tmp_path: Path):
    from video_paper_wiki import gate_decision
    source,_manifest,_archive=closure_backup
    checkout=tmp_path/'checkout';checkout.mkdir();make_checkout(checkout)
    baseline=canonicalize({'papers':3,'repositories':5});manifest=tmp_path/'baseline.json';manifest.write_bytes(baseline)
    baseline_sha=hashlib.sha256(baseline).hexdigest();baseline_path=f'.raw/derived/gates/{baseline_sha}.json'
    head_path=source/'wiki/meta/registries/operation-head.json';head=json.loads(head_path.read_text());previous_raw=(source/head['receipt_path']).read_bytes()
    successor={'schema':'video-paper-wiki.operation-receipt.v1','sequence':2,
        'previous':{'path':head['receipt_path'],'sha256':hashlib.sha256(previous_raw).hexdigest()},
        'operation_id':'gate-baseline','operation_type':'ingest','intent_sha256':'0'*64,
        'writes':[{'path':baseline_path,'mode':'create','before_sha256':None,'after_sha256':baseline_sha}],
        'claimed_inputs':[]}
    successor['intent_sha256']=receipt_intent_sha256(successor);successor_raw=canonicalize(successor)
    receipt_path='wiki/meta/operations/000000000002-gate-baseline.json';target=source/receipt_path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(successor_raw)
    baseline_target=source/baseline_path;baseline_target.parent.mkdir(parents=True,exist_ok=True);baseline_target.write_bytes(baseline)
    head={'schema':'video-paper-wiki.operation-head.v1','sequence':2,'receipt_path':receipt_path,'receipt_sha256':hashlib.sha256(successor_raw).hexdigest()};head_path.write_bytes(canonicalize(head))
    for item in source.rglob('*'):item.chmod(0o700 if item.is_dir() else 0o600)
    decision={'schema':'video-paper-wiki.gate-decision.v1','gate_id':gate_decision.GATE,
        'event_id':'gde-'+'0'*20,'previous_event_id':None,'actor_kind':'human','choice':'keep-modelscope',
        'baseline_manifest_sha256':baseline_sha,
        'derived_full_map_repo_ids':gate_decision.CHOICES['keep-modelscope'],'decided_by':'human:synthetic-fixture',
        'decided_at':'2026-09-02T00:00:00Z','reason':'Mechanical closure fixture.'}
    decision['event_id']=gate_event_id(decision);decision_path=tmp_path/'decision.json';decision_path.write_bytes(canonicalize(decision))
    old=os.getcwd();os.chdir(checkout)
    try:prepared=gate_decision.prepare_gate(decision_path=decision_path,baseline_manifest_path=manifest,batch_id='installed-gate')['request_path']
    finally:os.chdir(old)
    old=os.getcwd();os.chdir(checkout)
    try:
        from video_paper_wiki.receipt_audit import _Snapshot
        held_prepared=gate_decision._Prepared(prepared);held_vault=_Snapshot(source)
        try:
            direct=gate_decision.inspect_gate(prepared=prepared,operation_id='installed-gate',
                upstream_root=Path(__file__).resolve().parents[2]/'vendor/claude-obsidian',vault_root=source,
                _prepared_snapshot=held_prepared,_vault_snapshot=held_vault)
            with gate_decision._retained_gate_bundle(prepared,direct):pass
            held_prepared.verify();held_vault.verify()
        finally:held_vault.close();held_prepared.close()
    finally:os.chdir(old)
    inspected=subprocess.run([str(installed_cli/'vpwiki'),'gate','inspect','--prepared',prepared,
        '--operation-id','installed-gate','--upstream-root',str(Path(__file__).resolve().parents[2]/'vendor/claude-obsidian'),
        '--vault-root',str(source)],cwd=checkout,env=_env(installed_cli,tmp_path),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert inspected.returncode==0,inspected.stdout+inspected.stderr
    approval=json.loads(inspected.stdout)['data']['publication_authority']['transaction']['inspection']['approval_sha256']
    before=_tree(source)
    operator_env=_env(installed_cli,tmp_path);operator_env['PATH']=str(installed_cli)+':/usr/bin:/bin'
    result=subprocess.run([str(installed_cli/'vpwiki-admin'),'gate','apply','--prepared',prepared,
        '--operation-id','installed-gate','--upstream-root',str(Path(__file__).resolve().parents[2]/'vendor/claude-obsidian'),
        '--vault-root',str(source),'--approved-plan-sha256',approval],cwd=checkout,env=operator_env,
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert result.returncode==2
    assert json.loads(result.stdout)['error']['code']=='HUMAN_APPROVAL_REQUIRED',result.stdout+result.stderr
    assert _tree(source)==before and not (source/'wiki/meta/registries/gate-heads.json').exists()
