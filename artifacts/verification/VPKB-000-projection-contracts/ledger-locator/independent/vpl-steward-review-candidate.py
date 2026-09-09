from pathlib import Path
import copy,hashlib,json,sys
from video_paper_wiki import ledger_locator as ll
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import evidence_fingerprint
P=Path;sha=lambda b:hashlib.sha256(b).hexdigest();manifest=json.loads(P('<TMP>/vpl-candidate.json').read_text());before={n:sha(P(n).read_bytes()) for n in manifest['files']};assert before==manifest['files']
old=json.loads(P('<TMP>/vpr-acceptance-final/source-files.json').read_text());assert all(sha(P(n).read_bytes())==s for n,s in old['files'].items())
v=json.loads(P('<TMP>/vpl-steward-vectors.json').read_text());results=[]
def check(name,fn):
 try:fn();results.append({'case':name,'status':'passed'})
 except Exception as e:results.append({'case':name,'status':'failed','type':type(e).__name__,'code':getattr(e,'code',None),'details':getattr(e,'details',None),'message':str(e)[:400]})
def valid(row):
 original=copy.deepcopy(row['input_locator']);wire=ll.encode_ledger_locator(row['input_locator']);assert wire==row['expected_wire'] and sha(wire.encode())==row['wire_sha256'];assert row['input_locator']==original
 restored=ll.decode_ledger_locator(wire);assert restored==row['expected_decoded_locator'];assert ll.encode_ledger_locator(restored)==wire
 assert ll.encode_ledger_locator(dict(reversed(list(row['input_locator'].items()))))==wire
 for relation,mapped in v['relation_map'].items():
  domain=dict(row['input_locator'],relation=relation);e=ll.encode_ledger_evidence(domain);assert e=={'source_id':domain['source_id'],'relation':mapped,'locator':wire}
  decoded=ll.decode_ledger_evidence(e);assert decoded==dict(row['expected_decoded_locator'],relation=relation)
  assert evidence_fingerprint([decoded])==row['evidence_fingerprints'][relation]
def invalid(row):
 try:ll.decode_ledger_locator(row['wire'])
 except ContractError as e:
  assert e.code==row['code'],(e.code,row['code'])
  if 'pointer' in row:assert e.details['instance_pointer']==row['pointer'],e.details
 else:raise AssertionError('expected refusal')
for row in v['valid_vectors']:check('vector/'+row['name'],lambda row=row:valid(row))
for row in v['invalid_wire_vectors']:check('wire/'+row['name'],lambda row=row:invalid(row))
pdf=v['valid_vectors'][1]['input_locator'];code=v['valid_vectors'][6]['input_locator']
def refuse(name,fn,expected,pointer):
 def task():
  try:fn()
  except ContractError as e:assert e.code==expected and e.details.get('instance_pointer')==pointer,(e.code,e.details)
  else:raise AssertionError('expected refusal')
 check(name,task)
for kind,loc,fields in [('pdf',pdf,['source_id','artifact_path','artifact_sha256','text_sha256']),('code',code,['source_id','repository','commit','path','snippet_sha256'])]:
 for field in fields:
  changed=copy.deepcopy(loc);changed[field]+='\n';refuse(kind+'/'+field+'/LF',lambda x=changed:ll.encode_ledger_locator(x),'LEDGER_LOCATOR_INVALID','/'+field)
class Hostile:
 def __repr__(self):raise AssertionError('custom repr invoked')
 def __str__(self):raise AssertionError('custom str invoked')
class D(dict):pass
class S(str):pass
class I(int):pass
class L(list):pass
for field,value in [('page',True),('page',1.0),('source_id',Hostile()),('ref',S('x')),('charspan',L([0,1]))]:
 x=copy.deepcopy(pdf);x[field]=value;refuse('strict/'+field+'/'+type(value).__name__,lambda x=x:ll.encode_ledger_locator(x),'LEDGER_LOCATOR_INVALID','/'+field)
refuse('custom-root',lambda:ll.encode_ledger_evidence(D(pdf,relation='supports')),'LEDGER_EVIDENCE_INVALID','')
refuse('flat-custom-source',lambda:ll.encode_ledger_evidence(dict(pdf,source_id=Hostile(),relation='supports')),'LEDGER_LOCATOR_INVALID','/source_id')
refuse('flat-custom-relation',lambda:ll.encode_ledger_evidence(dict(pdf,relation=Hostile())),'LEDGER_EVIDENCE_INVALID','/relation')
refuse('flat-invalid-key',lambda:ll.encode_ledger_evidence({**pdf,'relation':'supports',None:1}),'LEDGER_EVIDENCE_INVALID','')
refuse('outer-wire-custom',lambda:ll.decode_ledger_evidence({'source_id':pdf['source_id'],'relation':'supports','locator':Hostile()}),'LEDGER_EVIDENCE_INVALID','/locator')
refuse('inner-wire-invalid',lambda:ll.decode_ledger_evidence({'source_id':pdf['source_id'],'relation':'supports','locator':ll.PREFIX+'{"locator":{}}'}),'LEDGER_LOCATOR_INVALID','')
x=copy.deepcopy(pdf);x['page']=0;env={'schema':ll.TITLE,'locator':{k:a for k,a in x.items() if k!='bbox'},'bbox_rationals':[[1,3],[1,1],[2,1],[3,1]]};wire=ll.PREFIX+json.dumps(env,sort_keys=True,separators=(',',':'))
refuse('shape-before-ratio',lambda:ll.decode_ledger_locator(wire),'LEDGER_LOCATOR_INVALID','/locator/page')
# Alias/copy checks use a shared original optional list but never retain it.
def alias():
 src=copy.deepcopy(pdf);original=copy.deepcopy(src);wire=ll.encode_ledger_locator(src);a=ll.decode_ledger_locator(wire);b=ll.decode_ledger_locator(wire);a['bbox'][0]=999;a['charspan'][0]=888;assert b==original and src==original
 e=ll.decode_ledger_evidence(ll.encode_ledger_evidence(dict(src,relation='uncertain')));e['bbox'][0]=7;assert src==original
check('alias',alias)
# Warm packaged schema first; no installed-package imports executed upstream.
ll.encode_ledger_locator(pdf)
def noio():
 import builtins,socket,subprocess
 from unittest.mock import patch
 def forbidden(*args,**kwargs):raise AssertionError('caller I/O attempted')
 with patch.object(builtins,'open',forbidden),patch.object(P,'open',forbidden),patch.object(socket,'socket',forbidden),patch.object(subprocess,'Popen',forbidden):
  assert ll.decode_ledger_locator(ll.encode_ledger_locator(pdf))==pdf
check('warm-registry-noio',noio)
after={n:sha(P(n).read_bytes()) for n in manifest['files']};assert after==before;assert all(sha(P(n).read_bytes())==s for n,s in old['files'].items())
out={'source_candidate':manifest['filelist_sha256'],'python':sys.version,'before':before,'after':after,'original_283_sources_unchanged':True,'independent_expectation_file_sha256':sha(P('<TMP>/vpl-steward-vectors.json').read_bytes()),'cases':results,'passed':sum(x['status']=='passed' for x in results),'failed':sum(x['status']=='failed' for x in results)}
P('<TMP>/vpl-steward-review-candidate.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'passed':out['passed'],'failed':out['failed'],'failures':[x for x in results if x['status']=='failed']},indent=2));sys.exit(bool(out['failed']))
