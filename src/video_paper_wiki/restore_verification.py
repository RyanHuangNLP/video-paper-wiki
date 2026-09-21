"""Read-only semantic verification for an already restored private Vault."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from video_paper_wiki.backup_manifest import verify_restored_tree
from video_paper_wiki.catalog_reporting import catalog_report
from video_paper_wiki.catalog_store import catalog_status,query_catalog
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.upstream_runtime import lint_vault

def verify_restored_vault(*,source_root:Path|str,restore_root:Path|str,manifest:object,upstream_root:Path|str,config:object)->dict[str,Any]:
    tree=verify_restored_tree(restore_root,manifest,source_root=source_root)
    try:
        audit=audit_integrity(restore_root);lint=lint_vault(vault_root=restore_root,upstream_root=upstream_root)
        if lint['exit_code']!=0:raise ContractError('RESTORE_VERIFICATION_FAILED','strict lint rejected restored Vault')
        status=catalog_status(restore_root,upstream_root,config)
        if status['state']!='current':raise ContractError('RESTORE_VERIFICATION_FAILED','restored catalog is stale')
        query=query_catalog(restore_root,upstream_root,config,'视频论文')
        report=catalog_report(vault_root=restore_root,upstream_root=upstream_root,retrieval_config=config,report_kind='evidence-coverage')
    except ContractError as exc:
        if exc.code=='RESTORE_VERIFICATION_FAILED':raise
        raise ContractError('RESTORE_VERIFICATION_FAILED','restored semantic authority differs',exc.details) from None
    return {'valid':True,'tree':tree,'audit':audit,'strict_lint_summary':lint['data'].get('summary'), 'catalog_status':status,'query_generation_sha256':query['catalog_generation_sha256'],'report_generation_sha256':report['catalog_generation_sha256'],'external_backup_observation':False}

def _vault_semantics(restore_root:Path|str,upstream_root:Path|str,config:object)->dict[str,Any]:
    try:
        audit=audit_integrity(restore_root);lint=lint_vault(vault_root=restore_root,upstream_root=upstream_root)
        if lint['exit_code']!=0:raise ContractError('RESTORE_VERIFICATION_FAILED','strict lint rejected restored Vault')
        status=catalog_status(restore_root,upstream_root,config)
        if status['state']!='current':raise ContractError('RESTORE_VERIFICATION_FAILED','restored catalog is stale')
        query=query_catalog(restore_root,upstream_root,config,'视频论文')
        report=catalog_report(vault_root=restore_root,upstream_root=upstream_root,retrieval_config=config,report_kind='evidence-coverage')
    except ContractError as exc:
        if exc.code=='RESTORE_VERIFICATION_FAILED':raise
        raise ContractError('RESTORE_VERIFICATION_FAILED','restored semantic authority differs',exc.details) from None
    return {'audit':audit,'strict_lint_summary':lint['data'].get('summary'),'catalog_status':status,'query_generation_sha256':query['catalog_generation_sha256'],'report_generation_sha256':report['catalog_generation_sha256']}

def _research_reads(root:Path,manifest:dict[str,Any])->dict[str,Any]:
    import os
    from video_paper_wiki.article_revision import article_history,status_article_store
    from video_paper_wiki.code_proof_public import status_code_proof
    from video_paper_wiki.domain_store import status_domain_store
    from video_paper_wiki.experiment_store import status_experiment_store
    from video_paper_wiki.flow.status import build_flow_status
    from video_paper_wiki.staging import StagingError,resolve_checkout_root
    try:checkout=resolve_checkout_root()
    except StagingError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','research verify requires the restored checkout',{}) from exc
    if not os.path.samefile(checkout,root):raise ContractError('RESTORE_VERIFICATION_FAILED','research verify cwd is not the restored checkout')
    coverage={(row['batch_id'],row['rule_id']):row for row in manifest['coverage']}
    batches=[]
    for batch in manifest['scope']['batch_ids']:
        item={'batch_id':batch}
        if coverage[(batch,'code-evidence')]['state']=='included':item['code_proof']=status_code_proof(batch_id=batch)
        if coverage[(batch,'flow')]['state']=='included':item['flow']=build_flow_status(vault_root=root,batch_id=batch)
        if coverage[(batch,'articles')]['state']=='included':
            articles=status_article_store(vault_root=root,batch_id=batch);item['articles']=articles
            item['article_histories']=[article_history(vault_root=root,article_id=row['article_id'],batch_id=batch if row.get('head_location')=='staged' else None) for row in articles['articles']]
        batches.append(item)
    included=lambda rule:any(coverage[(batch,rule)]['state']=='included' for batch in manifest['scope']['batch_ids'])
    return {'batches':batches,'domain':status_domain_store(vault_root=root) if included('domain') else None,'experiments':status_experiment_store(vault_root=root) if included('experiments') else None}

def verify_restored_research(*,restore_root:Path|str,manifest:object,expected_manifest_sha256:str,upstream_root:Path|str,config:object,research_reads:bool=False)->dict[str,Any]:
    """Vault checks always run on the restored tree. Research reads stay pending until requested."""
    from video_paper_wiki.backup_manifest import verify_restored_research_tree
    tree=verify_restored_research_tree(restore_root,manifest,expected_manifest_sha256=expected_manifest_sha256)
    semantics=_vault_semantics(restore_root,upstream_root,config)
    if not isinstance(manifest,dict):raise ContractError('BACKUP_MANIFEST_INVALID','research manifest is not an object')
    document=manifest
    value={'valid':False,'research_validation':'pending','vault_verified':True,'manifest_sha256':tree['manifest_sha256'],'source_anchor':tree['source_anchor'],'vault_manifest_sha256':tree['vault_manifest_sha256'],'coverage_counts':{'batches':tree['batch_count'],'included_rules':tree['included_rules'],'absent_rules':tree['absent_rules'],'file_count':tree['file_count']},'byte_checks':[{'path':row['path'],'sha256':row['sha256'],'size_bytes':row['size_bytes'],'matched':True} for row in document['files']],'tree':tree,'external_backup_observation':False,'research_reads':None}
    value.update(semantics)
    if not research_reads:return value
    try:reads=_research_reads(Path(restore_root),document)
    except ContractError:raise
    except Exception as exc:
        code=getattr(exc,'code',None)
        if type(code) is str:raise ContractError(code,str(getattr(exc,'message',exc)),dict(getattr(exc,'details',{}) or {})) from exc
        raise ContractError('RESTORE_VERIFICATION_FAILED','research read failed',{}) from exc
    value['research_reads']=reads;value['research_validation']='passed';value['valid']=True
    return value

__all__=['verify_restored_vault','verify_restored_research']
