import copy, json, hashlib, sys
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
SOURCE=ROOT/'.work/parallel/source-catalog-v1/terminal-1/source'
OLD=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/rejected-r1-source/schemas/video-paper-wiki.source-catalog.v1.schema.json'
FIX=SOURCE/'tests/fixtures/contracts/valid/video-paper-wiki.source-catalog.v1.json'

def load_schema(path): return json.loads(path.read_text())
def make_registry(schema_dir, override=None):
  rs=[]
  for p in schema_dir.glob('*.schema.json'):
    d=load_schema(p)
    rs.append((d['$id'],Resource.from_contents(d)))
  if override:
    d=load_schema(override); rs=[x for x in rs if x[0]!=d['$id']];rs.append((d['$id'],Resource.from_contents(d)))
  return Registry().with_resources(rs)

def err_summary(v, obj):
  es=list(v.iter_errors(obj));
  return [{'path':'/'+'/'.join(map(str,e.absolute_path)),'keyword':str(e.validator),'message':e.message} for e in es[:8]]

def schema_result(v,obj):
  es=list(v.iter_errors(obj)); return {'accepted':not es,'errors':err_summary(v,obj)}

base=load_schema(FIX)
oldv=Draft202012Validator(load_schema(OLD),registry=make_registry(SOURCE/'schemas',OLD),format_checker=FormatChecker())
new_path=SOURCE/'schemas/video-paper-wiki.source-catalog.v1.schema.json'
newv=Draft202012Validator(load_schema(new_path),registry=make_registry(SOURCE/'schemas'),format_checker=FormatChecker())

def ev(res,kind='markdown'):
  pos={'markdown':{'kind':'markdown','charspan':[0,5],'page_anchor':None},'pdf':{'kind':'pdf','page':1,'ref':'p1','charspan':[0,5]},'code':{'kind':'code','lines':{'start':1,'end':2}}}[kind]
  return {'claim_id':'clm-'+'a'*20,'ordinal':0,'source_id':'src-test','kind':kind,'wire':{'source_id':'src-test','relation':'supports','locator':'loc-1'},'association_id':None,'display_association_id':None,'resolution':res | {'source_path':'notes/a.md','source_sha256':'a'*64,'position':pos}}

def resolved(kind): return {'state':'RESOLVED','reason':None,'excerpt':'hello','excerpt_sha256':'b'*64} 
def unsupported(reason): return {'state':'UNSUPPORTED_LEGACY_RESOLUTION','reason':reason,'excerpt':None,'excerpt_sha256':None,'position':None}

def root_with(**kw):
  d=copy.deepcopy(base); d['rows']['evidence']=[]
  d.update(kw)
  return d

def coverage(state,kind=None):
  source_states={'registered_owned':'source_has_canonical_owner','registered_unclaimed':'source_has_no_canonical_owner'}
  art_states={'captured_registered':'capture_has_registered_source','captured_unregistered':'capture_has_no_source_row','derived_referenced':'artifact_in_canonical_evidence_ancestry','derived_unreferenced':'artifact_without_canonical_evidence_reference'}
  if state in source_states: k='source'; reason=source_states[state]
  else: k='artifact'; reason=art_states[state]
  return {'kind':k,'id':'src-test' if k=='source' else 'art-test','state':state,'source_ids':['src-test'],'paper_ids':['arxiv:2311.15127'],'repo_ids':[],'reason':reason}

cases=[]
# root/base
cases.append(('base_empty_catalog',base))
for kind in ('markdown','pdf','code'):
 cases.append((f'resolved_{kind}',root_with(rows={**base['rows'],'evidence':[ev(resolved(kind),kind)]})))
for reason in ('legacy_json_pointer_unavailable','legacy_object_not_text','legacy_page_not_reconstructable','legacy_charspan_unavailable','excerpt_limit'):
  e=ev(unsupported(reason)); e['resolution'].pop('position',None); e['resolution']['position']=None
  cases.append((f'unsupported_{reason}',root_with(rows={**base['rows'],'evidence':[e]})))
# invalid resolution mutations
mutations=[]
e=ev(resolved('markdown'))
for name,mut in [('resolved_null_excerpt',lambda r:r.update(excerpt=None)),('resolved_reason_nonnull',lambda r:r.update(reason='excerpt_limit')),('resolved_null_hash',lambda r:r.update(excerpt_sha256=None)),('resolved_null_position',lambda r:r.update(position=None)),('resolved_bad_position_kind',lambda r:r['position'].update(kind='pdf')),('unsupported_excerpt_string',lambda r:r.update(excerpt='oops')),('unsupported_hash_string',lambda r:r.update(excerpt_sha256='b'*64)),('unsupported_reason_null',lambda r:r.update(reason=None)),('unsupported_reason_unknown',lambda r:r.update(reason='unknown'))]:
  kind='markdown'; x=ev(resolved(kind),kind) if name.startswith('resolved') else ev(unsupported('excerpt_limit'),kind)
  mut(x['resolution'])
  cases.append((name,root_with(rows={**base['rows'],'evidence':[x]})))
# state unknown
x=ev(resolved('markdown')); x['resolution']['state']='UNSUPPORTED_LEGACY_RESOLUTION'; x['resolution']['reason']='unknown'; x['resolution']['excerpt']=None; x['resolution']['excerpt_sha256']=None; x['resolution']['position']=None
cases.append(('unsupported_state_unknown_reason',root_with(rows={**base['rows'],'evidence':[x]})))
# coverage all states + wrong reasons
for s in ('registered_owned','registered_unclaimed','captured_registered','captured_unregistered','derived_referenced','derived_unreferenced'):
 d=root_with(rows={**base['rows'],'coverage':[coverage(s)]}); cases.append((f'coverage_{s}',d))
for s in ('registered_owned','registered_unclaimed','captured_registered','captured_unregistered','derived_referenced','derived_unreferenced'):
 d=root_with(rows={**base['rows'],'coverage':[coverage(s)]}); d['rows']['coverage'][0]['reason']='wrong'; cases.append((f'coverage_{s}_wrong_reason',d))
d=root_with(rows={**base['rows'],'coverage':[coverage('registered_owned')]}); d['rows']['coverage'][0]['state']='bogus'; cases.append(('coverage_unknown_state',d))

# current contracts result (import after sys.path)
sys.path.insert(0,str(SOURCE/'src'))
from video_paper_wiki.contracts import validate_document, ContractError
contract_results={}
for name,obj in cases:
  try: validate_document(obj,expected_schema='video-paper-wiki.source-catalog.v1'); contract_results[name]={'accepted':True}
  except Exception as e: contract_results[name]={'accepted':False,'type':type(e).__name__,'code':getattr(e,'code',None),'message':str(e)[:300]}

out=[]
for name,obj in cases:
  o=schema_result(oldv,obj); n=schema_result(newv,obj)
  out.append({'name':name,'old':o,'new':n,'current_contract':contract_results[name],'parity':o['accepted']==n['accepted'],'current_matches_new':contract_results[name]['accepted']==n['accepted']})
print(json.dumps({'cases':out},indent=2,sort_keys=True))
