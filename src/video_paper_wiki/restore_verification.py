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

__all__=['verify_restored_vault']
