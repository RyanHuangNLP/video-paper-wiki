"""Mechanical HUMAN-GATE-BASELINE-001 staging and inspection; never chooses or applies."""
from __future__ import annotations
import hashlib,os,stat
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from video_paper_wiki.contracts import ContractError,validate_document
from video_paper_wiki.identity import gate_event_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import inspect_publication,stage_publication_request
from video_paper_wiki.secure_io import parse_strict_json,read_regular_file
from video_paper_wiki.staging import (_atomic_install,_close_fd,_ensure_dir_at,_existing_same_bytes,_open_batch_session,_require_exact_staged_file,resolve_checkout_root,validate_batch_id)

REQUEST='staged-gate-request.v1.json';GATE='HUMAN-GATE-BASELINE-001'
CHOICES={
'keep-modelscope':['github:stability-ai/generative-models','github:thudm/cogvideo','github:snap-research/panda-70m','github:ji4chenli/t2v-turbo','github:vchitect/vbench'],
'replace-with-open-sora':['github:stability-ai/generative-models','github:hpcaitech/open-sora','github:snap-research/panda-70m','github:ji4chenli/t2v-turbo','github:vchitect/vbench']}

def _gate_inspect_barrier(phase:str,**_observed:object)->None:
    """Private deterministic race seam; it never changes validation behavior."""
    return None

def _fail(code,msg):raise ContractError(code,msg)
def _read(path,code,max_bytes=1024*1024):return read_regular_file(Path(path),missing_code=code,unsafe_code=code,changed_code=code,max_bytes=max_bytes,limit_code=code)
def _decision(raw:bytes)->dict:
    try:doc=validate_document(parse_strict_json(raw,invalid_code='GATE_DECISION_INVALID'),'video-paper-wiki.gate-decision.v1')
    except ContractError as exc:
      if exc.code=='GATE_DECISION_INVALID':raise
      raise ContractError('GATE_DECISION_INVALID','gate decision schema differs',{}) from exc
    if canonicalize(doc)!=raw or gate_event_id(doc)!=doc['event_id'] or doc['derived_full_map_repo_ids']!=CHOICES[doc['choice']]:_fail('GATE_DECISION_INVALID','gate decision identity or exact repository selection differs')
    return doc

def _utc(value:object)->bool:
    if type(value) is not str or not value.endswith('Z') or '.' in value:return False
    try:return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H:%M:%SZ')==value
    except ValueError:return False

def _check_request(value:dict)->None:
    if value['batch_id']!=value['operation_id']:_fail('GATE_STATE_INVALID','gate batch and operation differ')
    for key in ('decision','baseline_manifest'):
        item=value[key];digest=item['sha256']
        if item['content_file']!='gate-input/content/'+digest:_fail('GATE_STATE_INVALID','gate descriptor path differs')

def _check_registry(value:dict)->None:
    if (value['event_path']!=f'wiki/meta/gates/{GATE}/{value["event_id"]}.json'
            or value['baseline_path']!=f'.raw/derived/gates/{value["baseline_sha256"]}.json'
            or value['repository_ids']!=CHOICES[value['choice']] or not _utc(value['decided_at'])):
        _fail('GATE_STATE_INVALID','gate registry correlation differs')

def _check_consumption(value:dict)->None:
    paths=value['artifact_paths']
    if (gate_consumption_id(value)!=value['consumer_id'] or paths!=sorted(set(paths)) or not _utc(value['recorded_at'])
            or any(type(p) is not str or p.startswith('/') or any(x in {'','.','..'} for x in p.split('/')) for p in paths)):
        _fail('GATE_STATE_INVALID','gate consumption correlation differs')

def _check_authority(value:dict)->None:
    request=value['gate_request'];decision=value['decision'];registry=value['registry']
    _check_request(request);_check_registry(registry)
    try:validate_document(value['publication_authority'],'video-paper-wiki.publication-authority.v1')
    except ContractError as exc:raise ContractError('GATE_STATE_INVALID','nested gate publication is invalid',{}) from exc
    if (hashlib.sha256(canonicalize(request)).hexdigest()!=value['gate_request_sha256']
            or request['gate_id']!=decision['gate_id'] or request['operation_id']!=value['publication_authority']['request']['operation_id']
            or request['decision']['sha256']!=registry['event_sha256']
            or request['baseline_manifest']['sha256']!=value['baseline_manifest_sha256']
            or value['baseline_manifest_sha256']!=registry['baseline_sha256']
            or decision['event_id']!=registry['event_id'] or decision['choice']!=registry['choice']
            or decision['derived_full_map_repo_ids']!=registry['repository_ids'] or decision['decided_at']!=registry['decided_at']):
        _fail('GATE_STATE_INVALID','gate authority correlation differs')
    publication=value['publication_authority'];prequest=publication['request'];event=registry['event_path'];baseline=registry['baseline_path'];registry_path='wiki/meta/registries/gate-heads.json'
    payloads={row['path']:row for row in prequest['payloads']};claims=prequest['claimed_input_paths']
    expected_paths={event,registry_path}
    previous=decision['previous_event_id'];new_baseline=baseline
    if previous is None:
        expected_claims={new_baseline}
    else:
        prior_event=f'wiki/meta/gates/{GATE}/{previous}.json'
        required={new_baseline,prior_event}
        extras=set(claims)-required
        valid_prior_baselines={p for p in extras if (p.startswith('.raw/derived/gates/') and p.endswith('.json')
            and len(p)==len('.raw/derived/gates/')+64+len('.json')
            and all(c in '0123456789abcdef' for c in p[len('.raw/derived/gates/'):-len('.json')]))}
        if extras!=valid_prior_baselines or len(extras)>1:_fail('GATE_STATE_INVALID','nested gate predecessor claims differ')
        expected_claims=required|extras
    registry_write=next((row for row in publication['transaction']['writes'] if row['path']==registry_path),None)
    registry_expected=publication['transaction']['expected_hashes'].get(registry_path)
    if (prequest['batch_id']!=request['batch_id'] or prequest['operation_id']!=request['operation_id'] or prequest['operation_type']!='generic'
            or prequest['additional_read_paths']!=[] or prequest['prospective_groups']!=[{'group_id':'gate','gate':event}]
            or set(payloads)!=expected_paths or set(claims)!=expected_claims or payloads[event]['sha256']!=request['decision']['sha256']
            or payloads[registry_path]['sha256']!=hashlib.sha256(canonicalize(registry)).hexdigest()
            or registry_write is None
            or (previous is None and (registry_write['mode']!='create' or registry_expected is not None))
            or (previous is not None and (registry_write['mode']!='replace' or type(registry_expected) is not str
                or len(registry_expected)!=64 or any(c not in '0123456789abcdef' for c in registry_expected)))):
        _fail('GATE_STATE_INVALID','nested gate publication differs')
    business={row['path'] for row in publication['transaction']['writes'] if row['role']=='business'}
    if business!=set(payloads):_fail('GATE_STATE_INVALID','gate transaction business paths differ')

def prepare_gate(*,decision_path:Path|str,baseline_manifest_path:Path|str,batch_id:object)->dict[str,Any]:
    from video_paper_wiki.catalog_store import _RetainedFile
    batch=validate_batch_id(batch_id);held=[]
    def retained(path,code):
      try:item=_RetainedFile(Path(path));held.append(item);fd=item.fd
      except ContractError:_fail(code,'gate source is unsafe')
      try:
       os.lseek(fd,0,os.SEEK_SET);raw=b''
       while True:
        part=os.read(fd,1024*1024)
        if not part:break
        raw+=part
        if len(raw)>1024*1024:_fail(code,'gate source exceeds limit')
       return raw
      except OSError:_fail(code,'gate source is unsafe')
    try:
      draw=retained(decision_path,'GATE_DECISION_INVALID');decision=_decision(draw);mraw=retained(baseline_manifest_path,'GATE_MANIFEST_INVALID')
      try:manifest=parse_strict_json(mraw,invalid_code='GATE_MANIFEST_INVALID')
      except Exception as exc:raise ContractError('GATE_MANIFEST_INVALID','baseline manifest is not strict JSON',{}) from exc
      if type(manifest) is not dict or canonicalize(manifest)!=mraw or hashlib.sha256(mraw).hexdigest()!=decision['baseline_manifest_sha256']:_fail('GATE_MANIFEST_INVALID','baseline manifest bytes differ')
      request={'schema':'video-paper-wiki.gate-publication-request.v1','batch_id':batch,'operation_id':batch,'gate_id':GATE,
      'decision':{'content_file':'gate-input/content/'+hashlib.sha256(draw).hexdigest(),'sha256':hashlib.sha256(draw).hexdigest(),'size_bytes':len(draw)},
      'baseline_manifest':{'content_file':'gate-input/content/'+hashlib.sha256(mraw).hexdigest(),'sha256':hashlib.sha256(mraw).hexdigest(),'size_bytes':len(mraw)}}
      request=validate_document(request,'video-paper-wiki.gate-publication-request.v1');rraw=canonicalize(request)
      with _open_batch_session(batch,create=True) as session:
       base=session.batch_path/'gate-input';content=base/'content';bfd=_ensure_dir_at(session.batch_fd,'gate-input',base,work_fd=session.work_fd);cfd=_ensure_dir_at(bfd,'content',content,work_fd=session.work_fd)
       try:
        for digest,data in sorted(((hashlib.sha256(draw).hexdigest(),draw),(hashlib.sha256(mraw).hexdigest(),mraw))):
         if not _existing_same_bytes(cfd,digest,data,content/digest):_atomic_install(session.work_fd,cfd,digest,data,target=content/digest,checkout_fd=session.checkout_fd)
         _require_exact_staged_file(cfd,digest,data,content/digest)
        if not _existing_same_bytes(bfd,REQUEST,rraw,base/REQUEST):_atomic_install(session.work_fd,bfd,REQUEST,rraw,target=base/REQUEST,checkout_fd=session.checkout_fd)
        _require_exact_staged_file(bfd,REQUEST,rraw,base/REQUEST)
        if sorted(x.name for x in os.scandir(bfd))!=sorted([REQUEST,'content']):_fail('GATE_PATH_UNSAFE','gate staging root differs')
        if sorted(x.name for x in os.scandir(cfd))!=sorted({request['decision']['sha256'],request['baseline_manifest']['sha256']}):_fail('GATE_PATH_UNSAFE','gate staging content differs')
       finally:_close_fd(cfd);_close_fd(bfd)
      for item in held:item.verify_edge('GATE_PATH_UNSAFE')
      return {'schema':request['schema'],'request_path':(base/REQUEST).as_posix(),'request_sha256':hashlib.sha256(rraw).hexdigest(),'request':request}
    except BaseException:
      for item in held:item.verify_edge('GATE_PATH_UNSAFE')
      raise
    finally:
      for item in reversed(held):item.close()

class _Prepared:
  def __init__(self,path:Path|str):
    self.held=[]
    try:self._initialize(path)
    except BaseException:
      try:
       if self.held:self.verify()
      finally:self.close()
      raise
  def _initialize(self,path:Path|str):
    from video_paper_wiki.catalog_store import _RetainedFile
    self.held=[];target=Path(path).absolute();checkout=resolve_checkout_root().absolute()
    try:parts=target.relative_to(checkout).parts
    except ValueError:_fail('GATE_PATH_UNSAFE','gate request is outside checkout')
    if len(parts)!=4 or parts[0]!='.work' or parts[2]!='gate-input' or parts[3]!=REQUEST:_fail('GATE_PATH_UNSAFE','gate request does not use the fixed layout')
    validate_batch_id(parts[1]);self.target=target
    def take(file:Path)->bytes:
      try:item=_RetainedFile(file)
      except ContractError:_fail('GATE_PATH_UNSAFE','gate prepared input is unsafe')
      self.held.append(item);fd=item.fd
      try:
       os.lseek(fd,0,os.SEEK_SET);raw=b''
       while True:
        part=os.read(fd,1024*1024)
        if not part:break
        raw+=part
        if len(raw)>1024*1024:_fail('GATE_PATH_UNSAFE','gate prepared input exceeds limit')
       return raw
      except OSError:_fail('GATE_PATH_UNSAFE','gate prepared input is unsafe')
    raw=take(target);request=validate_document(parse_strict_json(raw,invalid_code='GATE_STATE_INVALID'),'video-paper-wiki.gate-publication-request.v1')
    if canonicalize(request)!=raw or request['batch_id']!=parts[1]:_fail('GATE_STATE_INVALID','gate request bytes or batch differ')
    base=target.parent;draw=take(base/request['decision']['content_file'].removeprefix('gate-input/'));mraw=take(base/request['baseline_manifest']['content_file'].removeprefix('gate-input/'))
    for key,data in (('decision',draw),('baseline_manifest',mraw)):
      descriptor=request[key]
      if len(data)!=descriptor['size_bytes'] or hashlib.sha256(data).hexdigest()!=descriptor['sha256']:_fail('GATE_STATE_INVALID','gate prepared descriptor differs')
    self.value=(request,draw,mraw);self.expected=sorted({request['decision']['sha256'],request['baseline_manifest']['sha256']});self.verify()
  def verify(self):
    try:
      for item in self.held:item.verify_edge('GATE_PATH_UNSAFE')
      if not hasattr(self,'expected'):return
      gate_fd=self.held[0].parent_fd;fresh=os.open('.',os.O_RDONLY|getattr(os,'O_DIRECTORY',0),dir_fd=gate_fd)
      try:
       if sorted(x.name for x in os.scandir(fresh))!=sorted([REQUEST,'content']):raise OSError
      finally:_close_fd(fresh)
      content_fd=self.held[1].parent_fd;fresh=os.open('.',os.O_RDONLY|getattr(os,'O_DIRECTORY',0),dir_fd=content_fd)
      try:
       if sorted(x.name for x in os.scandir(fresh))!=self.expected:raise OSError
      finally:_close_fd(fresh)
    except ContractError:raise
    except OSError:_fail('GATE_PATH_UNSAFE','gate prepared tree changed')
  def close(self):
    for item in reversed(self.held):item.close()
    self.held=[]
  def __del__(self):
    self.close()

def _prepared(path:Path|str)->tuple[dict,bytes,bytes]:
    retained=_Prepared(path)
    try:return retained.value
    finally:retained.close()

def _prepared_legacy(path:Path|str)->tuple[dict,bytes,bytes]:
    target=Path(path).absolute();checkout=resolve_checkout_root().absolute()
    try:parts=target.relative_to(checkout).parts
    except ValueError:_fail('GATE_PATH_UNSAFE','gate request is outside checkout')
    if len(parts)!=4 or parts[0]!='.work' or parts[2]!='gate-input' or parts[3]!=REQUEST:_fail('GATE_PATH_UNSAFE','gate request does not use the fixed layout')
    validate_batch_id(parts[1]);raw=_read(target,'GATE_PATH_UNSAFE');request=validate_document(parse_strict_json(raw,invalid_code='GATE_STATE_INVALID'),'video-paper-wiki.gate-publication-request.v1')
    if canonicalize(request)!=raw or request['batch_id']!=parts[1]:_fail('GATE_STATE_INVALID','gate request bytes or batch differ')
    base=target.parent
    try:
      if sorted(x.name for x in os.scandir(base))!=sorted([REQUEST,'content']):_fail('GATE_PATH_UNSAFE','gate request root differs')
      content=base/'content';expected=sorted({request['decision']['sha256'],request['baseline_manifest']['sha256']})
      if sorted(x.name for x in os.scandir(content))!=expected:_fail('GATE_PATH_UNSAFE','gate content set differs')
    except OSError:_fail('GATE_PATH_UNSAFE','gate request tree is unsafe')
    draw=_read(base/request['decision']['content_file'].removeprefix('gate-input/'),'GATE_PATH_UNSAFE');mraw=_read(base/request['baseline_manifest']['content_file'].removeprefix('gate-input/'),'GATE_PATH_UNSAFE')
    for key,data in (('decision',draw),('baseline_manifest',mraw)):
      d=request[key]
      if len(data)!=d['size_bytes'] or hashlib.sha256(data).hexdigest()!=d['sha256']:_fail('GATE_STATE_INVALID','gate staged content differs')
    return request,draw,mraw

def inspect_gate(*,prepared:Path|str,operation_id:object,upstream_root:Path|str,vault_root:Path|str,
        _prepared_snapshot=None,_vault_snapshot=None,_apply_holder_out:list|None=None)->dict[str,Any]:
    owns_prepared=_prepared_snapshot is None;owns_vault=_vault_snapshot is None
    prepared_snapshot=_prepared_snapshot if _prepared_snapshot is not None else _Prepared(prepared)
    try:
      first=prepared_snapshot.value;request,draw,mraw=first;decision=_decision(draw)
      if operation_id!=request['operation_id'] or decision['baseline_manifest_sha256']!=hashlib.sha256(mraw).hexdigest():_fail('GATE_STATE_INVALID','gate operation binding differs')
      from video_paper_wiki.receipt_audit import _Snapshot,audit_integrity
      vault=Path(vault_root);snap=_vault_snapshot if _vault_snapshot is not None else _Snapshot(vault)
    except BaseException:
      try:prepared_snapshot.verify()
      finally:
       if owns_prepared:prepared_snapshot.close()
      raise
    try:
      audit=audit_integrity(vault,_snapshot=snap)
      if audit['classification']!='receipt_backed':_fail('GATE_STATE_INVALID','gate publication requires receipt-backed Vault')
      _gate_inspect_barrier('vault-retained',prepared=prepared_snapshot,vault=snap,holder=None)
      current=set(audit['current_paths']);registry_rel='wiki/meta/registries/gate-heads.json';registry=None
      rraw=snap.read_optional(registry_rel,max_bytes=1024*1024)
      if rraw is not None:
        registry=validate_document(parse_strict_json(rraw,invalid_code='GATE_STATE_INVALID'),'video-paper-wiki.gate-head-registry.v1')
        if canonicalize(registry)!=rraw or registry_rel not in current:_fail('GATE_STATE_INVALID','gate registry is not canonical receipt-backed state')
        eraw=snap.read(registry['event_path'],max_bytes=1024*1024);braw=snap.read(registry['baseline_path'],max_bytes=1024*1024)
        prior=_decision(eraw)
        if (hashlib.sha256(eraw).hexdigest()!=registry['event_sha256'] or hashlib.sha256(braw).hexdigest()!=registry['baseline_sha256']
              or prior['event_id']!=registry['event_id'] or prior['choice']!=registry['choice'] or prior['derived_full_map_repo_ids']!=registry['repository_ids']
              or prior['decided_at']!=registry['decided_at'] or registry['event_path'] not in current or registry['baseline_path'] not in current):
          _fail('GATE_STATE_INVALID','gate current state differs')
      previous=None if registry is None else registry['event_id']
      if decision['previous_event_id']!=previous:_fail('GATE_STATE_INVALID','gate predecessor differs')
      prefix=f'wiki/meta/gates/{GATE}/consumers/'
      for relative in sorted(p for p in current if p.startswith(prefix)):
        craw=snap.read(relative,max_bytes=1024*1024);doc=validate_document(parse_strict_json(craw,invalid_code='GATE_STATE_INVALID'),'video-paper-wiki.gate-consumption.v1')
        if canonicalize(doc)!=craw or relative!=prefix+doc['consumer_id']+'.json':_fail('GATE_STATE_INVALID','gate consumption state differs')
        if doc['gate_event_id']==previous:_fail('GATE_STATE_INVALID','current gate choice is held fixed')
      event_path=f'wiki/meta/gates/{GATE}/{decision["event_id"]}.json';baseline_path=f'.raw/derived/gates/{decision["baseline_manifest_sha256"]}.json'
      if event_path in current:_fail('GATE_STATE_INVALID','gate event already exists')
      registry_doc={'schema':'video-paper-wiki.gate-head-registry.v1','gate_id':GATE,'event_id':decision['event_id'],'event_path':event_path,'event_sha256':hashlib.sha256(draw).hexdigest(),'choice':decision['choice'],'baseline_path':baseline_path,'baseline_sha256':decision['baseline_manifest_sha256'],'repository_ids':decision['derived_full_map_repo_ids'],'decided_at':decision['decided_at']}
      registry_raw=canonicalize(validate_document(registry_doc,'video-paper-wiki.gate-head-registry.v1'));payloads={event_path:draw,registry_rel:registry_raw};claimed=[]
      existing_baseline=snap.read_optional(baseline_path,max_bytes=1024*1024)
      if existing_baseline is None or existing_baseline!=mraw or baseline_path not in current:
        _fail('GATE_STATE_INVALID','gate baseline is not exact receipt-backed state')
      claimed.append(baseline_path)
      if registry is not None:claimed.extend([registry['event_path'],registry['baseline_path']])
      staged=stage_publication_request(batch_id=request['batch_id'],operation_id=request['operation_id'],operation_type='generic',payloads=payloads,claimed_input_paths=sorted(set(claimed)),prospective_groups=[{'group_id':'gate','gate':event_path}])
      publication_holders=[]
      publication=inspect_publication(prepared=staged['request_path'],operation_id=operation_id,upstream_root=upstream_root,
          vault_root=vault_root,_authority_holder_out=publication_holders if _apply_holder_out is not None else None)
      result={'schema':'video-paper-wiki.gate-publication-authority.v1','gate_request_sha256':hashlib.sha256(canonicalize(request)).hexdigest(),'gate_request':request,'decision':decision,'baseline_manifest_sha256':decision['baseline_manifest_sha256'],'registry':registry_doc,'publication_authority':publication,'human_gate_satisfied':False}
      result=validate_document(result,'video-paper-wiki.gate-publication-authority.v1');holder=None
      try:
       if _apply_holder_out is not None:
        holder=publication_holders[0];_apply_holder_out.append((holder,holder.bundle_path))
        _gate_inspect_barrier('authority-retained',prepared=prepared_snapshot,vault=snap,holder=holder)
       prepared_snapshot.verify();snap.verify();return result
      except BaseException:
       if holder is not None:
        holder.verify();holder.close()
        if _apply_holder_out:_apply_holder_out.pop()
       raise
    except BaseException:
      prepared_snapshot.verify()
      try:snap.verify()
      except ContractError as exc:raise ContractError('GATE_STATE_INVALID','gate Vault state changed',{}) from exc
      raise
    finally:
      if owns_vault:snap.close()
      if owns_prepared:prepared_snapshot.close()

def gate_consumption_id(value:dict)->str:return 'gco-'+hashlib.sha256(canonicalize({k:v for k,v in value.items() if k!='consumer_id'})).hexdigest()[:20]

def gate_bundle_path(prepared:Path|str,authority:dict)->Path:
    retained=_Prepared(prepared)
    try:
      validate_document(authority,'video-paper-wiki.gate-publication-authority.v1');staging=authority['publication_authority']['transaction_staging']
      if staging['batch_id']!=retained.value[0]['batch_id']:_fail('GATE_STATE_INVALID','gate staging batch differs')
      target=retained.target.parents[1]/staging['bundle_file'];retained.verify();return target
    finally:retained.close()

@contextmanager
def _retained_gate_bundle(prepared:Path|str,authority:dict):
    retained=_Prepared(prepared)
    bundle=None;contents=[];publication_inputs=[]
    try:
      validate_document(authority,'video-paper-wiki.gate-publication-authority.v1')
      staging=authority['publication_authority']['transaction_staging']
      if staging['batch_id']!=retained.value[0]['batch_id']:_fail('GATE_STATE_INVALID','gate staging batch differs')
      target=retained.target.parents[1]/staging['bundle_file']
      from video_paper_wiki.catalog_store import _RetainedFile
      publication=authority['publication_authority'];prequest=publication['request'];pbase=retained.target.parents[1]
      for relative in ['publication-input/knowledge-publication-request.v1.json',*[x['content_file'] for x in prequest['payloads']]]:
       try:item=_RetainedFile(pbase/relative)
       except ContractError:_fail('GATE_PATH_UNSAFE','gate publication input is unsafe')
       publication_inputs.append(item)
      try:bundle=_RetainedFile(target)
      except ContractError:_fail('GATE_STATE_INVALID','gate bundle is unsafe')
      fd=bundle.fd;os.lseek(fd,0,os.SEEK_SET);raw=b''
      while True:
       part=os.read(fd,1024*1024)
       if not part:break
       raw+=part
       if len(raw)>8*1024*1024:_fail('GATE_STATE_INVALID','gate bundle exceeds limit')
      if len(raw)!=staging['bundle_size_bytes'] or hashlib.sha256(raw).hexdigest()!=staging['bundle_sha256']:_fail('GATE_STATE_INVALID','gate bundle differs from inspected staging')
      for descriptor in staging['content_files']:
       try:item=_RetainedFile(retained.target.parents[1]/descriptor['content_file'])
       except ContractError:_fail('GATE_STATE_INVALID','gate transaction content is unsafe')
       contents.append(item);os.lseek(item.fd,0,os.SEEK_SET);data=b''
       while True:
        part=os.read(item.fd,1024*1024)
        if not part:break
        data+=part
        if len(data)>64*1024*1024:_fail('GATE_STATE_INVALID','gate transaction content exceeds limit')
       if len(data)!=descriptor['size_bytes'] or hashlib.sha256(data).hexdigest()!=descriptor['sha256']:_fail('GATE_STATE_INVALID','gate transaction content differs')
      retained.verify();bundle.verify_edge('GATE_STATE_INVALID')
      for item in publication_inputs:item.verify_edge('GATE_PATH_UNSAFE')
      for item in contents:item.verify_edge('GATE_STATE_INVALID')
      yield target
      for item in contents:item.verify_edge('GATE_STATE_INVALID')
      for item in publication_inputs:item.verify_edge('GATE_PATH_UNSAFE')
      bundle.verify_edge('GATE_STATE_INVALID');retained.verify()
    except BaseException:
      for item in publication_inputs:item.verify_edge('GATE_PATH_UNSAFE')
      for item in contents:item.verify_edge('GATE_STATE_INVALID')
      if bundle is not None:bundle.verify_edge('GATE_STATE_INVALID')
      retained.verify();raise
    finally:
      for item in reversed(publication_inputs):item.close()
      for item in reversed(contents):item.close()
      if bundle is not None:bundle.close()
      retained.close()

__all__=['prepare_gate','inspect_gate','gate_consumption_id','gate_bundle_path']
