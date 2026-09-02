"""Agent-safe domain commands; mutations are delegated to vpwiki-admin."""
from __future__ import annotations
from video_paper_wiki.contracts import SCHEMA_INVALID, ContractError,validate_document
from video_paper_wiki.domain import render_seed_catalog,shape_query_results,validate_seed_catalog
from video_paper_wiki.envelope import emit_error,emit_success
from video_paper_wiki.secure_io import SOURCE_CHANGED, SecureIOError, load_strict_json
from video_paper_wiki.upstream_runtime import bm25_query,bm25_status,doctor,lint_vault,verify_upstream

def _json(path):
    return load_strict_json(path,missing_code='DOCUMENT_NOT_FOUND',unsafe_code='DOCUMENT_PATH_UNSAFE',invalid_code=SCHEMA_INVALID,changed_code=SOURCE_CHANGED,max_bytes=67108864)

def _error(command,exc): return emit_error(command,getattr(exc,'code','DOMAIN_FAILED'),getattr(exc,'message',str(exc)),getattr(exc,'details',{}),exit_code=getattr(exc,'exit_code',2))
def seed_validate(args):
    try: data=validate_seed_catalog(getattr(args,'catalog',None) if args is not None else None); return emit_success('seed.validate',{'valid':True,'paper_count':len(data['papers'])})
    except Exception as e:return _error('seed.validate',e)
def seed_status(args):
    try: data=validate_seed_catalog(getattr(args,'catalog',None) if args is not None else None); return emit_success('seed.status',{'paper_count':len(data['papers']),'first':data['papers'][0]['paper_id'],'last':data['papers'][-1]['paper_id']})
    except Exception as e:return _error('seed.status',e)
def seed_render(args):
    try:return emit_success('seed.render',render_seed_catalog(args.batch_id))
    except Exception as e:return _error('seed.render',e)
def init_plan(args): return emit_success('init.plan',{'workflow':['vpwiki seed validate','python <upstream>/scripts/claude-obsidian.py init <vault>','python <upstream>/scripts/claude-obsidian.py init <vault> --approved-plan-sha256 <sha> --apply','vpwiki ingest prepare','vpwiki capture inspect','python <upstream>/scripts/claude-obsidian.py transaction apply <bundle> --vault <vault> --approved-plan-sha256 <sha>','python <upstream>/scripts/bm25-index.py --vault <vault> build','vpwiki audit']})
def init_inspect(args):
    try:
        root=verify_upstream(args.upstream_root); observed=doctor(vault_root=args.vault_root,upstream_root=root); return emit_success('init.inspect',{'ready':True,'upstream_root':root.as_posix(),'doctor':observed,'agent_writes':'.work/**','operator':'pinned claude-obsidian public CLI'})
    except Exception as e:return _error('init.inspect',e)
def inspect_document(args,command):
    try:
        value=load_strict_json(args.path,missing_code='DOCUMENT_NOT_FOUND',unsafe_code='DOCUMENT_PATH_UNSAFE',invalid_code=SCHEMA_INVALID,changed_code=SOURCE_CHANGED)
        doc=validate_document(value,getattr(args,'schema',None)); return emit_success(command,{'valid':True,'schema':doc['schema']})
    except Exception as e:return _error(command,e)
def index_status(args):
    try:
        from video_paper_wiki.catalog_store import catalog_status
        return emit_success('index.status',catalog_status(args.vault_root,args.upstream_root,args.config))
    except Exception as e:return _error('index.status',e)
def query(args):
    try:
        from video_paper_wiki.catalog_store import query_catalog
        return emit_success('query',query_catalog(args.vault_root,args.upstream_root,args.config,args.text))
    except Exception as e:return _error('query',e)
def catalog_report(args):
    try:
        from video_paper_wiki.catalog_reporting import catalog_report as report
        return emit_success('catalog.report',report(vault_root=args.vault_root,upstream_root=args.upstream_root,retrieval_config=args.config,report_kind=args.kind,paper_id=args.paper_id))
    except Exception as e:return _error('catalog.report',e)
def audit(args):
    from video_paper_wiki.receipt_audit import audit_integrity
    domain_report=None; domain_error=None; lint_report=None; lint_error=None
    try: domain_report=audit_integrity(args.vault_root)
    except Exception as exc: domain_error={'code':getattr(exc,'code','INTEGRITY_AUDIT_FAILED'),'message':getattr(exc,'message',str(exc)),'details':getattr(exc,'details',{})}
    try:
        observed=lint_vault(vault_root=args.vault_root,upstream_root=args.upstream_root,as_of=getattr(args,'as_of',None)); lint_report={'exit_code':observed['exit_code'],'data':observed['data']}
    except Exception as exc: lint_error={'code':getattr(exc,'code','UPSTREAM_LINT_FAILED'),'message':getattr(exc,'message',str(exc)),'details':getattr(exc,'details',{})}
    valid=domain_error is None and lint_error is None and lint_report['exit_code']==0
    result={'valid':valid,'domain':domain_report,'domain_error':domain_error,'strict_lint':lint_report,'strict_lint_error':lint_error}
    if valid:return emit_success('audit',result)
    return emit_error('audit','AUDIT_FAILED','domain integrity or strict lint failed',result,exit_code=1)

def compile_validate(args):
    try:
        from video_paper_wiki.canonical_compiler import compile_pages
        pages=compile_pages(_json(args.path));return emit_success('compile.validate',{'valid':True,'page_count':len(pages)})
    except Exception as e:return _error('compile.validate',e)
def compile_render(args):
    try:
        from video_paper_wiki.canonical_compiler import stage_compilation
        return emit_success('compile.render',stage_compilation(_json(args.path),batch_id=args.batch_id))
    except Exception as e:return _error('compile.render',e)
def evidence_join(args):
    try:
        from video_paper_wiki.evidence_join import join_evidence_files
        value=_json(args.path)
        return emit_success('evidence.join',join_evidence_files(vault_root=args.vault_root,request=value))
    except Exception as e:return _error('evidence.join',e)
def retrieval_validate(args):
    try:
        from video_paper_wiki.retrieval import validate_retrieval_config,validate_retrieval_gold
        cfg=validate_retrieval_config(_json(args.config));gold=validate_retrieval_gold(_json(args.gold),_json(args.inventory),cfg)
        return emit_success('retrieval.validate',{'valid':True,'corpus_version':cfg['corpus_version'],'gold_count':len(gold['entries'])})
    except Exception as e:return _error('retrieval.validate',e)
def retrieval_evaluate(args):
    try:
        from video_paper_wiki.retrieval import evaluate_retrieval
        return emit_success('retrieval.evaluate',evaluate_retrieval(gold=_json(args.gold),inventory=_json(args.inventory),config=_json(args.config),mapping=_json(args.mapping),results=_json(args.results)))
    except Exception as e:return _error('retrieval.evaluate',e)
def backup_build(args):
    try:
        from video_paper_wiki.backup_manifest import build_backup_manifest
        return emit_success('backup.manifest',build_backup_manifest(args.vault_root,operation_head=_json(args.expected_operation_head) if args.expected_operation_head else None,expected_claimed_raw=_json(args.expected_claimed_raw) if args.expected_claimed_raw else None))
    except Exception as e:return _error('backup.manifest',e)
def backup_verify(args):
    try:
        from video_paper_wiki.restore_verification import verify_restored_vault
        return emit_success('backup.verify',verify_restored_vault(restore_root=args.restore_root,source_root=args.source_root,manifest=_json(args.manifest),upstream_root=args.upstream_root,config=args.config))
    except Exception as e:return _error('backup.verify',e)
def gate_prepare(args):
    try:
        from video_paper_wiki.gate_decision import prepare_gate
        return emit_success('gate.prepare',prepare_gate(decision_path=args.decision,baseline_manifest_path=args.baseline_manifest,batch_id=args.batch_id))
    except Exception as e:return _error('gate.prepare',e)
def gate_inspect(args):
    try:
        from video_paper_wiki.gate_decision import inspect_gate
        return emit_success('gate.inspect',inspect_gate(prepared=args.prepared,operation_id=args.operation_id,upstream_root=args.upstream_root,vault_root=args.vault_root))
    except Exception as e:return _error('gate.inspect',e)
