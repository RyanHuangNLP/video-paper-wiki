"""Staged UTF-8 code capture using the accepted transaction-inspect boundary."""
from __future__ import annotations
import copy, hashlib, json, os, re, stat
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.approval import bind_approval_ref
from video_paper_wiki.capture_contracts import capture_approval_hash, validate_capture_inspection
from video_paper_wiki.captured_snapshot import capture_snapshot
from video_paper_wiki.code_evidence_contracts import code_manifest_hash, validate_code_capture_binding, validate_code_evidence_manifest
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json, read_regular_file
from video_paper_wiki.staging import WORK_DIRNAME, _open_batch_session, resolve_checkout_root, validate_batch_id
from video_paper_wiki.transaction_staging import _check_transaction_staging
from video_paper_wiki.transaction_contracts import transaction_declaration_hash, validate_transaction
from video_paper_wiki.transaction_staging import encode_transaction_inspect_bundle, _stage_transaction_inspect_transport
from video_paper_wiki.upstream_adapter import _check_upstream_authority_fields, inspect_pinned_transaction, verify_pinned_source_id

REQUEST_SCHEMA='video-paper-wiki.staged-code-capture-request.v1'
AUTHORITY_SCHEMA='video-paper-wiki.staged-code-capture-authority.v1'
REQUEST_FILE='staged-code-capture-request.v1.json'
_OP=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')

def _fail(code:str,pointer:str,message:str):
    raise ContractError(code,message,{'instance_pointer':pointer})

def _stamp(value:os.stat_result)->tuple[int,int,int,int,int]:
    return value.st_dev,value.st_ino,value.st_mode,value.st_size,value.st_mtime_ns

def _stable_file(path:Path,maximum:int=67108864)->tuple[bytes,os.stat_result]:
    try:
        before=path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_size>maximum: raise OSError
        data=read_regular_file(path,missing_code='WORK_PATH_UNSAFE',unsafe_code='WORK_PATH_UNSAFE',changed_code='WORK_PATH_UNSAFE',max_bytes=maximum,limit_code='WORK_PATH_UNSAFE')
        after=path.lstat()
        if (before.st_dev,before.st_ino,before.st_mode,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_mode,after.st_size,after.st_mtime_ns): raise OSError
        return data,after
    except (OSError,SecureIOError): _fail('WORK_PATH_UNSAFE','/prepared','prepared input is unsafe or changed')

def _verify_file(path:Path,expected:os.stat_result)->None:
    try: current=path.lstat()
    except OSError: _fail('WORK_PATH_UNSAFE','/prepared','prepared input is unsafe or changed')
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode) or _stamp(current)!=_stamp(expected):
        _fail('WORK_PATH_UNSAFE','/prepared','prepared input is unsafe or changed')

def _stable_dir(path:Path)->os.stat_result:
    try: value=path.lstat()
    except OSError: _fail('WORK_PATH_UNSAFE','/prepared','prepared directory is unsafe')
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode): _fail('WORK_PATH_UNSAFE','/prepared','prepared directory is unsafe')
    return value

def _verify_dir(path:Path,expected:os.stat_result)->None:
    try: value=path.lstat()
    except OSError: _fail('WORK_PATH_UNSAFE','/prepared','prepared directory changed')
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode) or _stamp(value)!=_stamp(expected): _fail('WORK_PATH_UNSAFE','/prepared','prepared directory changed')

def _check_request(doc:Mapping[str,Any])->None:
    manifest=validate_code_evidence_manifest(doc['manifest'])
    if manifest['state']!='proposal' or doc['payload_file']!=f"prepared/{manifest['payload']['sha256']}.blob":
        _fail('STAGED_CODE_REQUEST_MISMATCH','/manifest','request does not bind proposal payload')
    if doc['approval_ref_sha256']!=hashlib.sha256(canonicalize(doc['approval_ref'])).hexdigest():
        _fail('STAGED_CODE_REQUEST_MISMATCH','/approval_ref_sha256','approval reference digest differs')

def validate_staged_code_capture_request(document:object)->dict[str,object]:
    return copy.deepcopy(validate_document(document,REQUEST_SCHEMA))

def _check_authority(doc:Mapping[str,Any])->None:
    req=validate_staged_code_capture_request(doc['request'])
    inspection=validate_capture_inspection(doc['inspection'])
    manifest=validate_code_evidence_manifest(doc['manifest'])
    validate_code_capture_binding(manifest,inspection)
    if doc['request_sha256']!=hashlib.sha256(canonicalize(req)).hexdigest():
        _fail('STAGED_CODE_RESULT_MISMATCH','/request_sha256','authority request binding differs')
    create=doc['disposition']=='create'
    if create != (doc['transaction_staging'] is not None and doc['upstream_authority'] is not None and inspection['would_change']):
        _fail('STAGED_CODE_RESULT_MISMATCH','/disposition','authority branch differs')
    if not create and (doc['transaction_staging'] is not None or doc['upstream_authority'] is not None or inspection['would_change']):
        _fail('STAGED_CODE_RESULT_MISMATCH','/disposition','reuse must be side-effect free')
    if create and inspection['operation_id'] != doc['requested_operation_id']:
        _fail('STAGED_CODE_RESULT_MISMATCH','/requested_operation_id','create operation differs')
    if not create and inspection['operation_id'] is not None:
        _fail('STAGED_CODE_RESULT_MISMATCH','/inspection/operation_id','reuse must not claim an operation')
    if req['manifest']['payload'] != inspection['payload'] or req['manifest']['proposal_sha256'] != inspection['proposal_sha256']:
        _fail('STAGED_CODE_RESULT_MISMATCH','/inspection','inspection does not bind request manifest')
    if manifest['origin'] != req['manifest']['origin'] or manifest['payload'] != req['manifest']['payload'] or manifest['proposal_sha256'] != req['manifest']['proposal_sha256']:
        _fail('STAGED_CODE_RESULT_MISMATCH','/manifest','inspected manifest does not bind request proposal')
    if create:
        staging=doc['transaction_staging']; upstream=doc['upstream_authority']
        _check_transaction_staging(staging); _check_upstream_authority_fields(upstream)
        tx=upstream['transaction']; digest=req['manifest']['payload']['sha256']; size=req['manifest']['payload']['size_bytes']; target=f'.raw/captured/{digest}.bin'
        if (staging['batch_id']!=req['batch_id'] or staging['operation_id']!=doc['requested_operation_id'] or staging['operation_type']!='capture'
                or tx['operation_id']!=doc['requested_operation_id'] or tx['operation_type']!='capture'
                or staging['transaction_declaration_sha256']!=tx['declaration_sha256']
                or staging['bundle_sha256']!=upstream['transport']['bundle_sha256']
                or staging['bundle_sha256']!=tx['input_bundle_sha256']):
            _fail('STAGED_CODE_RESULT_MISMATCH','/transaction_staging','transaction layers differ')
        business=[item for item in tx['writes'] if item['role']=='business']
        if business != [{'path':target,'role':'business','mode':'create','sha256':digest,'size_bytes':size,'original_size_bytes':0,'original_mode':None}]:
            _fail('STAGED_CODE_RESULT_MISMATCH','/upstream_authority/transaction/writes','transaction payload differs')
        if (inspection['stored_path']!=target or inspection['upstream_plan_sha256']!=tx['inspection']['approval_sha256']
                or staging['content_files']!=[{'content_file':'transaction-inspect/content/'+digest,'sha256':digest,'size_bytes':size}]):
            _fail('STAGED_CODE_RESULT_MISMATCH','/inspection','capture and transport layers differ')

def validate_staged_code_capture_authority(document:object)->dict[str,object]:
    return copy.deepcopy(validate_document(document,AUTHORITY_SCHEMA))

def _proposal(operation_id:str,payload:bytes)->dict[str,Any]:
    digest=hashlib.sha256(payload).hexdigest(); target=f'.raw/captured/{digest}.bin'
    material={'operation_id':operation_id,'operation_type':'capture','writes':[{'path':target,'mode':'create','sha256':digest}], 'expected_hashes':{target:None},'read_preconditions':{}}
    bundle=encode_transaction_inspect_bundle(material)
    doc={'schema':'video-paper-wiki.transaction-facade.v1','phase':'proposal','operation_id':operation_id,'operation_type':'capture','writes':[{'path':target,'role':'business','mode':'create','sha256':digest,'size_bytes':len(payload),'original_size_bytes':0,'original_mode':None}], 'expected_hashes':{target:None},'read_preconditions':{},'claimed_inputs':[],'address_requests':[],'source_manifest_updates':{},'engine_expanded_paths':[],'receipt':None,'head':None,'input_bundle_sha256':hashlib.sha256(bundle).hexdigest(),'declaration_sha256':'0'*64,'inspection':None,'runtime_result':None}
    doc['declaration_sha256']=transaction_declaration_hash(doc); return validate_transaction(doc)

def _inspection(request:Mapping[str,Any], sibling:dict|None, operation_id:str|None, approval:str|None)->dict:
    payload=request['manifest']['payload']; digest=payload['sha256']
    value={'schema':'video-paper-wiki.capture-inspection.v1','route':'staged-capture','media_type':'text/plain','payload':payload,'source_path':None,'proposal_sha256':request['manifest']['proposal_sha256'],'stored_path':sibling['path'] if sibling else f'.raw/captured/{digest}.bin','source_identity':digest,'siblings':[copy.deepcopy(sibling)] if sibling else [],'would_change':sibling is None,'operation_id':operation_id if sibling is None else None,'upstream_plan_sha256':approval if sibling is None else None,'approval_hash':'0'*64}
    value['approval_hash']=capture_approval_hash(value); return validate_capture_inspection(value)

def inspect_staged_code_capture(*,prepared:Path|str,operation_id:object,upstream_root:Path|str,vault_root:Path|str)->dict[str,object]:
    if type(operation_id) is not str or not _OP.fullmatch(operation_id): _fail('SCHEMA_INVALID','/operation_id','invalid operation id')
    checkout=resolve_checkout_root(); path=Path(os.path.abspath(os.fspath(prepared))); work=checkout/WORK_DIRNAME
    try: rel=path.relative_to(work); batch=validate_batch_id(rel.parts[0])
    except Exception: _fail('ADAPTER_PATH_INVALID','/prepared','prepared request path is invalid')
    if rel.parts != (batch,'prepared',REQUEST_FILE): _fail('ADAPTER_PATH_INVALID','/prepared','prepared request path is not fixed')
    with _open_batch_session(batch,create=False) as session:
        prepared_dir_stat=_stable_dir(path.parent)
        raw,request_stat=_stable_file(path,1048576)
        retained:list[tuple[Path,os.stat_result]]=[(path,request_stat)]
        dirs:list[tuple[Path,os.stat_result]]=[(path.parent,prepared_dir_stat)]
        def verify_inputs()->None:
            session.verify()
            for input_dir,input_stat in dirs: _verify_dir(input_dir,input_stat)
            for input_path,input_stat in retained: _verify_file(input_path,input_stat)
        try:
            verify_inputs()
            obj=parse_strict_json(raw,invalid_code='SCHEMA_INVALID'); request=validate_staged_code_capture_request(obj)
            if canonicalize(request)!=raw or request['batch_id']!=batch: _fail('STAGED_CODE_REQUEST_MISMATCH','/request','request is not canonical or batch-bound')
            verify_inputs()
            plan_path=work/batch/'plan'/'ingest-plan.v1.json'; plan_dir_stat=_stable_dir(plan_path.parent); dirs.append((plan_path.parent,plan_dir_stat))
            plan_raw,plan_stat=_stable_file(plan_path,1048576); retained.append((plan_path,plan_stat)); verify_inputs()
            plan=validate_document(parse_strict_json(plan_raw,invalid_code='SCHEMA_INVALID'),'video-paper-wiki.ingest-plan.v1')
            if request['plan_sha256']!=hashlib.sha256(plan_raw).hexdigest() or request['plan_size_bytes']!=len(plan_raw) or plan['plan_kind']!='code-evidence': _fail('STAGED_CODE_REQUEST_MISMATCH','/plan_sha256','plan binding differs')
            bind_approval_ref(plan,request['approval_ref']); verify_inputs()
            blob_path=work/batch/request['payload_file']; payload,blob_stat=_stable_file(blob_path); retained.append((blob_path,blob_stat)); verify_inputs()
            proposal_manifest=validate_code_evidence_manifest(request['manifest'],payload=payload); verify_inputs()
            digest=proposal_manifest['payload']['sha256']
            with capture_snapshot(Path(vault_root),digest) as snapshot:
                if snapshot.sibling is None:
                    proposal=_proposal(operation_id,payload); target=proposal['writes'][0]['path']
                    staging=_stage_transaction_inspect_transport(proposal,write_bytes={target:payload},original_bytes={target:None},read_bytes={},batch_id=batch,session=session)
                    verify_inputs()
                    upstream=inspect_pinned_transaction(proposal,upstream_root=upstream_root,work_root=work,vault_root=vault_root,bundle_path=work/batch/'transaction-inspect'/'bundle.json')
                    inspection=_inspection(request,None,operation_id,upstream['transaction']['inspection']['approval_sha256']); disposition='create'
                else:
                    staging=upstream=None; inspection=_inspection(request,snapshot.sibling,None,None); disposition='reuse'
                source_id=verify_pinned_source_id(inspection['stored_path'],digest,upstream_root=upstream_root)
                manifest=copy.deepcopy(proposal_manifest); manifest['state']='inspected'; manifest['capture']={'stored_path':inspection['stored_path'],'source_identity':digest,'source_id':source_id,'inspection_approval_hash':inspection['approval_hash'],'operation_id':inspection['operation_id']}; manifest['manifest_sha256']='0'*64; manifest['manifest_sha256']=code_manifest_hash(manifest); manifest=validate_code_evidence_manifest(manifest,payload=payload)
                value={'schema':AUTHORITY_SCHEMA,'requested_operation_id':operation_id,'request_sha256':hashlib.sha256(raw).hexdigest(),'request':request,'disposition':disposition,'inspection':inspection,'manifest':manifest,'transaction_staging':staging,'upstream_authority':upstream}
                snapshot.verify(); verify_inputs(); return validate_staged_code_capture_authority(value)
        except BaseException:
            verify_inputs(); raise

def run_code_inspect_command(args:object)->int:
    from video_paper_wiki.envelope import emit_error,emit_staging_error,emit_success
    try:
        value=inspect_staged_code_capture(prepared=getattr(args,'prepared',None),operation_id=getattr(args,'operation_id',None),upstream_root=getattr(args,'upstream_root',None),vault_root=getattr(args,'vault_root',None))
        return emit_success('code-map.inspect',value)
    except Exception as exc:
        if hasattr(exc,'code'): return emit_error('code-map.inspect',exc.code,getattr(exc,'message',str(exc)),getattr(exc,'details',{}),exit_code=getattr(exc,'exit_code',2))
        return emit_error('code-map.inspect','STAGED_CODE_EXECUTION_FAILED','code capture inspection failed',exit_code=1)
