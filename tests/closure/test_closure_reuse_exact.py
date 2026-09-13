from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from video_paper_wiki.backup_archive import restore_backup_archive
from video_paper_wiki.backup_manifest import build_backup_manifest
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.jcs import canonicalize


def test_canonical_head_anchor(closure_backup):
    source,manifest,_archive=closure_backup;authority=audit_integrity(source)
    assert authority['head']['receipt_sha256']==manifest['source_anchor']
    assert authority['head']['receipt_path']=='wiki/meta/operations/000000000001-closure-genesis.json'


def test_caller_old_head(closure_backup):
    source,_manifest,_archive=closure_backup;head=audit_integrity(source)['head'];stale={**head,'sequence':head['sequence']+1}
    with pytest.raises(ContractError) as caught:build_backup_manifest(source,operation_head=stale)
    assert caught.value.code=='BACKUP_MANIFEST_INVALID'


def test_backup_vault_meta_excluded(closure_backup):
    source,_manifest,_archive=closure_backup;sentinel=source/'.vault-meta/cache/private';sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'ignore')
    for path in (sentinel.parent,sentinel):path.chmod(0o700 if path.is_dir() else 0o600)
    manifest=build_backup_manifest(source);paths={x['path'] for x in manifest['directories']+manifest['files']}
    assert all(not path.startswith('.vault-meta/') for path in paths)


def test_backup_work_excluded(closure_backup):
    source,_manifest,_archive=closure_backup;sentinel=source/'.work/batch/private';sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'ignore')
    for path in (source/'.work',sentinel.parent,sentinel):path.chmod(0o700 if path.is_dir() else 0o600)
    manifest=build_backup_manifest(source);paths={x['path'] for x in manifest['directories']+manifest['files']}
    assert all(not path.startswith('.work/') for path in paths)


def test_backup_missing_claimed(closure_backup):
    source,manifest,_archive=closure_backup;raw=next(x['path'] for x in manifest['files'] if x['path'].startswith('.raw/captured/'));(source/raw).unlink()
    with pytest.raises(ContractError) as caught:build_backup_manifest(source)
    assert caught.value.code=='BACKUP_MANIFEST_INVALID'


def test_restore_distinct_0700(closure_backup,tmp_path:Path):
    source,manifest,archive=closure_backup;target=tmp_path/'restored';target.mkdir(mode=0o700);target.chmod(0o700)
    result=restore_backup_archive(archive=archive,source_root=source,restore_root=target,manifest=manifest)
    assert result['manifest_sha256']==manifest['manifest_sha256'] and result['restore_root']==target.as_posix()
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob('*'))==sorted([x['path'] for x in manifest['directories']+manifest['files']])


def test_review_invalidation(tmp_path: Path, monkeypatch):
    from tests.unit.test_publication_wave import _review_vault, _vault_with_files
    from video_paper_wiki import identity, review_workflow
    from video_paper_wiki.canonical_compiler import compile_pages, concept_items_for_papers
    from video_paper_wiki.ledger_locator import encode_ledger_evidence

    checkout=tmp_path/'checkout';checkout.mkdir();(checkout/'.git').mkdir()
    (checkout/'pyproject.toml').write_text('[project]\nname="video-paper-wiki"\n');monkeypatch.chdir(checkout)
    vault=tmp_path/'vault';vault.mkdir();claim,events,ledger=_review_vault(vault)
    paper=json.loads((vault/'wiki/meta/records/paper.json').read_text())
    supporting=json.loads(json.dumps(claim));supporting['canonical_claim_text']='An accepted supporting claim.'
    supporting['claim_id']=identity.claim_id(supporting['stable_subject_id'],supporting['canonical_claim_text'])
    supporting['assessment']='accepted';supporting['reviewed_at']='2026-09-01'
    supporting_genesis_claim=json.loads(json.dumps(supporting));supporting_genesis_claim['assessment']='provisional';supporting_genesis_claim['reviewed_at']=None
    supporting_event={'schema':'video-paper-wiki.assessment-event.v1','event_id':'ase-'+'0'*20,
        'claim_id':supporting['claim_id'],'previous_event_id':None,'actor_kind':'system','transition_kind':'genesis',
        'from_assessment':None,'to_assessment':'provisional',
        'claim_text_sha256':hashlib.sha256(supporting['canonical_claim_text'].encode()).hexdigest(),
        'evidence_fingerprint':identity.evidence_fingerprint(supporting['evidence']),'decided_by':'fixture',
        'decided_at':'2026-09-01T00:00:00Z','reason':'Synthetic genesis.'}
    supporting_event['event_id']=identity.assessment_event_id(supporting_event)
    supporting_accept=review_workflow._event(supporting,supporting_event,actor='human',transition='human_assessment',target='accepted',
        decided_by='human:fixture',decided_at='2026-09-01T00:00:01Z',reason='Synthetic accepted fixture.')
    ledger['claims'][supporting['claim_id']]={'text':supporting['canonical_claim_text'],'risk':'low','assessment':'accepted',
        'confidence':'medium','location':{'path':'wiki/papers/arxiv-2311.15127.md','anchor':'^'+supporting['claim_id']},
        'reviewed_at':'2026-09-01','notes':None,'supersedes':None,
        'evidence':[encode_ledger_evidence(x) for x in supporting['evidence']]}
    paper['section_claim_refs'].append({'section':'one_sentence_conclusion','claim_id':supporting['claim_id'],'core':True,'lifecycle':'active'})
    shutil.rmtree(vault);vault.mkdir()
    _vault_with_files(vault,{'wiki/meta/ledgers/claim-ledger.json':canonicalize(ledger),
        'wiki/meta/records/paper.json':canonicalize(paper),
        f"wiki/meta/reviews/{claim['claim_id']}/{events[0]['event_id']}.json":canonicalize(events[0]),
        f"wiki/meta/reviews/{supporting['claim_id']}/{supporting_event['event_id']}.json":canonicalize(supporting_event),
        f"wiki/meta/reviews/{supporting['claim_id']}/{supporting_accept['event_id']}.json":canonicalize(supporting_accept)})
    changed=json.loads(json.dumps(claim));changed['evidence'][0]['lines']['end']+=1
    future=json.loads(json.dumps(ledger));future['generated_at']='2026-09-02T02:03:04Z'
    row=future['claims'][claim['claim_id']];row['evidence']=[encode_ledger_evidence(x) for x in changed['evidence']]
    row['assessment']='provisional';row['reviewed_at']=None
    new_claim=review_workflow._claim(row,'arxiv:2311.15127',claim['claim_id'])
    event=review_workflow._event(new_claim,events[0],actor='system',transition='evidence_invalidation',target='provisional',
        decided_by='video-paper-wiki',decided_at=future['generated_at'],reason='Locator changed.')
    pp='wiki/meta/records/paper-input.json';cp='wiki/meta/records/claims-input.json';ep='wiki/meta/records/events-input.json'
    material={'schema':'video-paper-wiki.compile-input.v1','operation_id':'invalidate-one',
        'papers':[{'record':paper,'claims':[new_claim,supporting],'events':events+[event,supporting_event,supporting_accept]}],'code':[],'concepts':[]}
    material['concepts']=concept_items_for_papers([paper]);pages=compile_pages(material)
    context={'operation_id':'invalidate-one','payloads':{'wiki/meta/ledgers/claim-ledger.json':canonicalize(future),
        pp:canonicalize(paper),cp:canonicalize([new_claim,supporting]),ep:canonicalize(events+[event,supporting_event,supporting_accept])}|pages,
        'claimed_input_paths':[],'prospective_groups':[{'group_id':'paper','paper_record':pp,'claims':cp,'events':ep}]}
    request={'schema':'video-paper-wiki.review-invalidation-request.v1','claim_id':claim['claim_id'],
        'expected_previous_event_id':events[0]['event_id'],
        'expected_old_evidence_fingerprint':identity.evidence_fingerprint(claim['evidence']),
        'expected_new_claim_sha256':hashlib.sha256(canonicalize(new_claim)).hexdigest(),
        'decided_at':future['generated_at'],'reason':'Locator changed.'}
    result=review_workflow.prepare_evidence_invalidation(request=request,publication_context=context,
        batch_id='invalidate-batch',vault_root=vault)
    assert result['transition_kind']=='evidence_invalidation'
    assert result['claim']==new_claim and result['events']==[event] and result['claim_ledger']==future
    assert result['events'][0]['actor_kind']=='system'
    assert review_workflow.validate_review_transition_authority(result)==result
    from video_paper_wiki.contracts import validate_prospective
    forged=json.loads(json.dumps(material['papers'][0]));forged['events'][1]['evidence_fingerprint']='f'*64
    forged['events'][1]['event_id']=identity.assessment_event_id(forged['events'][1])
    with pytest.raises(ContractError) as caught:validate_prospective(forged)
    assert caught.value.code=='EVIDENCE_FINGERPRINT_MISMATCH'
