from pathlib import Path
import copy,hashlib,json,sys,importlib.util
H=lambda b:hashlib.sha256(b).hexdigest();candidate=json.loads(Path('<TMP>/vph-candidate.json').read_text());before={n:H(Path(n).read_bytes()) for n in candidate['files']};assert before==candidate['files'];assert H(Path(candidate['contract']).read_bytes())==candidate['contract_sha256'];old=json.loads(Path('<TMP>/vpl-acceptance/source-files.json').read_text());assert all(H(Path(n).read_bytes())==h for n,h in old['files'].items());prep=json.loads(Path('<TMP>/vph-steward-preparation.json').read_text());assert all(H(Path(n).read_bytes())==x['sha256'] for n,x in prep['files'].items())
from video_paper_wiki import assessment_history as ah
from video_paper_wiki.contracts import ContractError
rows=[]
def check(name,fn):
 try:fn();rows.append({'case':name,'status':'passed'})
 except Exception as e:rows.append({'case':name,'status':'failed','exception':type(e).__name__,'code':getattr(e,'code',None),'details':getattr(e,'details',None),'message':str(e)[:400]})
def positive(row):
 data=copy.deepcopy(row['input']);snapshot=copy.deepcopy(data);got=ah.derive_assessment_heads(**data);assert got==row['expected_heads'] and list(got)==sorted(got) and data==snapshot
 perm=copy.deepcopy(data);perm['claims'].reverse();perm['events'].reverse();again=ah.derive_assessment_heads(**perm);assert got==again and got is not again
 got['clm-'+'f'*20]='ase-'+'f'*20;assert ah.derive_assessment_heads(**data)==row['expected_heads']
def refuse(data,code,exit_code=2,pointer=None):
 try:ah.derive_assessment_heads(**data)
 except ContractError as e:
  assert e.code==code and e.exit_code==exit_code,(e.code,e.exit_code,code)
  assert type(e.details.get('instance_pointer'))is str
  if pointer is not None:assert e.details['instance_pointer']==pointer,e.details
 else:raise AssertionError('expected typed refusal')
v=json.loads(Path('<TMP>/vph-steward-vectors.json').read_text())
for row in v['positive']:check('positive/'+row['name'],lambda row=row:positive(row))
for row in v['negative']:check('negative/'+row['name'],lambda row=row:refuse(row['input'],row['expected_error'],row['exit_code'],row.get('pointer')))
spec=importlib.util.spec_from_file_location('independent_cases','<TMP>/vph-steward-runtime-cases.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for name,data,code in module.cases():check('python/'+name,lambda data=data,code=code:refuse(data,code))
# Allowed alias is reused bbox/charspan across distinct evidence items, not a
# duplicate claim binding. It must be treated by occurrence and remain unchanged.
def aliases():
 data=copy.deepcopy(next(r['input'] for r in v['positive'] if r['name']=='duplicate_evidence_is_retained'));data['claims'][0]['evidence'][1]=data['claims'][0]['evidence'][0];expected=copy.deepcopy(data);ah.derive_assessment_heads(**data);assert data==expected and data['claims'][0]['evidence'][0] is data['claims'][0]['evidence'][1]
check('allowed_alias_no_mutation',aliases)
def graph_disconnected_cycle():
 g=copy.deepcopy(v['positive'][1]['input']['events'][0]);a=copy.deepcopy(g);b=copy.deepcopy(g)
 a.update(event_id='synthetic-a',previous_event_id='synthetic-b',actor_kind='human',transition_kind='human_assessment',from_assessment='accepted',to_assessment='contested');b.update(event_id='synthetic-b',previous_event_id='synthetic-a',actor_kind='human',transition_kind='human_assessment',from_assessment='contested',to_assessment='accepted')
 chain=list(enumerate([g,a,b]));ids={e['event_id']:(i,e) for i,e in chain}
 try:ah._chain_head(chain,ids)
 except ContractError as e:assert e.code=='ASSESSMENT_CHAIN_INVALID'
 else:raise AssertionError('unreachable cyclic component accepted')
check('synthetic_graph_only_disconnected_cycle_no_hash_claim',graph_disconnected_cycle)
def safe_diagnostic():
 data=copy.deepcopy(v['positive'][1]['input']);data['claims'][0]['secret~/field']='DO_NOT_LEAK_SECRET_TEXT';
 try:ah.derive_assessment_heads(**data)
 except ContractError as e:
  assert e.code=='SCHEMA_INVALID' and e.details['instance_pointer']=='/claims/0/secret~0~1field';assert 'DO_NOT_LEAK_SECRET_TEXT' not in str(e)+json.dumps(e.details)
 else:raise AssertionError('unknown field accepted')
check('escaped_pointer_no_value_leak',safe_diagnostic)
def noio():
 import builtins,socket,subprocess,time,os
 from unittest.mock import patch
 from contextlib import ExitStack
 data=copy.deepcopy(v['positive'][3]['input']);expected=ah.derive_assessment_heads(**data)
 def denied(*a,**kw):raise AssertionError('unexpected I/O, process, clock or environment read')
 class DateTime(ah.datetime):
  now=classmethod(denied);utcnow=classmethod(denied);today=classmethod(denied)
 class Date(ah.date):today=classmethod(denied)
 with ExitStack() as stack:
  for obj,name in [(builtins,'open'),(Path,'open'),(Path,'read_bytes'),(Path,'read_text'),(socket,'socket'),(subprocess,'Popen'),(time,'time'),(os,'getenv')]:stack.enter_context(patch.object(obj,name,denied))
  stack.enter_context(patch.object(ah,'datetime',DateTime));stack.enter_context(patch.object(ah,'date',Date))
  assert ah.derive_assessment_heads(**data)==expected
check('warm_schema_noio_clock_environment',noio)
after={n:H(Path(n).read_bytes()) for n in candidate['files']};assert after==before;assert all(H(Path(n).read_bytes())==h for n,h in old['files'].items());out={'contract_sha256':candidate['contract_sha256'],'before':before,'after':after,'old_288_unchanged':True,'expected_vectors_sha256':H(Path('<TMP>/vph-steward-vectors.json').read_bytes()),'python':sys.version,'cases':rows,'passed':sum(r['status']=='passed' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'limits':['Temporary independent checks; not Architect full acceptance.','Synthetic graph-only cycle control deliberately does not validate event hashes.','Warmed schema resources permit immutable packaged schema reads before the no-I/O probe.']};Path('<TMP>/vph-steward-review-candidate.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'passed':out['passed'],'failed':out['failed'],'failures':[r for r in rows if r['status']=='failed']},indent=2));sys.exit(bool(out['failed']))
