"""Pure binding of an externally executed upstream transaction result."""
from __future__ import annotations
import copy, hashlib
from collections.abc import Mapping
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.transaction_contracts import attach_runtime_result, validate_transaction

SCHEMA='video-paper-wiki.operation-result-authority.v1'

def _fail(pointer:str,message:str): raise ContractError('OPERATION_RESULT_MISMATCH',message,{'instance_pointer':pointer})

def _check_result_authority(doc:Mapping)->None:
    transaction=validate_transaction(doc['transaction'])
    result=doc['result']
    if transaction['runtime_result'] != result or transaction['phase']!='inspected':
        _fail('/transaction','transaction is not the inspected result-bound facade')
    if doc['bundle_sha256']!=transaction['input_bundle_sha256']:
        _fail('/bundle_sha256','bundle digest differs')
    before,after=doc['vault_before'],doc['vault_after']
    expected=set(result['changed_paths'])
    if set(before)!=expected or set(after)!=expected: _fail('/vault_after','snapshot coverage differs')
    for path in expected:
        old=before[path]; new=after[path]
        if old is not None and (type(old) is not dict or set(old)!={'sha256','mode'}): _fail('/vault_before','invalid prior descriptor')
        if type(new) is not dict or set(new)!={'sha256','mode'} or new['sha256']!=result['hashes'][path] or new['mode']!=result['modes'][path]: _fail('/vault_after','result does not bind final bytes and mode')

def validate_operation_result_authority(document:object)->dict[str,object]:
    return copy.deepcopy(validate_document(document,SCHEMA))

def bind_operation_result(inspected:object,result:object,*,vault_before:object,vault_after:object)->dict[str,object]:
    transaction=attach_runtime_result(inspected,result)
    value={'schema':SCHEMA,'transaction':transaction,'result':copy.deepcopy(result),'bundle_sha256':transaction['input_bundle_sha256'],'vault_before':copy.deepcopy(vault_before),'vault_after':copy.deepcopy(vault_after)}
    return validate_operation_result_authority(value)
