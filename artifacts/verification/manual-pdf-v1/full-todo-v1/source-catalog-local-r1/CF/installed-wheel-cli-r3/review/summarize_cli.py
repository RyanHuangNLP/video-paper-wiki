from __future__ import annotations
import hashlib,json,os
from pathlib import Path
cf=Path('artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/CF/installed-wheel-cli-r3').resolve(); fix=json.loads((cf/'cli/fixture/fixture.json').read_text());
def meta(p):
 b=p.read_bytes(); return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b),'text':b.decode('utf-8')}
def parse_one(p):
 t=p.read_text(); lines=[x for x in t.splitlines() if x.strip()];
 try: value=json.loads(lines[0]) if len(lines)==1 else None
 except Exception: value=None
 return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size,'nonempty_line_count':len(lines),'json':value}
def command_record(r,name,expected_rc,kind):
 base=cf/f'cli/runtime-{r}'; rc=int((base/(name+'.returncode')).read_text()); out=parse_one(base/(name+'.stdout')); err=meta(base/(name+'.stderr')); val=out['json']; return {'runtime':int(r),'name':name,'kind':kind,'expected_returncode':expected_rc,'returncode':rc,'returncode_ok':rc==expected_rc,'stdout':out,'stderr':err,'envelope_ok':isinstance(val,dict) and set(val)==({'ok','command','data'} if expected_rc==0 else {'ok','command','error'}) and val.get('ok') is (expected_rc==0)}
records=[]
for r in (312,313):
 for name in ('build','status','lookup','query','resolve'): records.append(command_record(r,name,0,'source-catalog-success'))
 for name,code in (('invalid-batch','INVALID_BATCH_ID'),('missing-catalog','SOURCE_CATALOG_ABSENT')):
  rec=command_record(r,name,2 if name=='invalid-batch' else 75,'source-catalog-error'); rec['expected_error_code']=code; rec['actual_error_code']=rec['stdout']['json'].get('error',{}).get('code') if rec['stdout']['json'] else None; rec['error_code_ok']=rec['actual_error_code']==code;records.append(rec)
 rec=command_record(r,'legacy-index-status',75,'legacy-refusal'); rec['expected_error_code']='SOURCE_PROFILE_REQUIRED';rec['actual_error_code']=rec['stdout']['json'].get('error',{}).get('code') if rec['stdout']['json'] else None;rec['error_code_ok']=rec['actual_error_code']=='SOURCE_PROFILE_REQUIRED'; records.append(rec)
# semantic success assertions
for r in (312,313):
 by={x['name']:x for x in records if x['runtime']==r}; values={n:by[n]['stdout']['json']['data'] for n in ('build','status','lookup','query','resolve')}
 digest=values['build']['catalog_sha256']; cache=cf/f'cli/runtime-{r}/cwd/.work/cli-catalog/source-catalog/catalog.json'
 files=sorted(str(p.relative_to(cf/f'cli/runtime-{r}/cwd')) for p in (cf/f'cli/runtime-{r}/cwd').rglob('*') if p.is_file())
 for n in values: by[n]['semantic_ok']=values[n].get('catalog_sha256')==digest and values[n].get('profile')=='source-catalog-v1'
 by['build']['semantic_ok'] &= values['build']['state'] in ('created','reused') and cache.is_file()
 by['status']['semantic_ok'] &= values['status']['state']=='current'
 by['lookup']['semantic_ok'] &= bool(values['lookup']['matches']) and values['lookup']['matches'][0].get('paper_id')==fix['paper_id']
 by['query']['semantic_ok'] &= values['query']['total_matches']>0 and bool(values['query']['hits'])
 by['resolve']['semantic_ok'] &= values['resolve']['claim_id']==fix['claim_id'] and values['resolve']['evidence']['resolution']['state']=='RESOLVED'
 by['cwd_files']=files
# cwd allowed files
cwd_checks={}
for r in (312,313):
 files=sorted(str(p.relative_to(cf/f'cli/runtime-{r}/cwd')) for p in (cf/f'cli/runtime-{r}/cwd').rglob('*') if p.is_file())
 cwd_checks[str(r)]={'files':files,'expected':['.work/cli-catalog/source-catalog/catalog.json','pyproject.toml'],'only_expected':files==['.work/cli-catalog/source-catalog/catalog.json','pyproject.toml']}
legacy_before=json.loads((cf/'cli/fixture/legacy-before-manifest.json').read_text());legacy_after=json.loads((cf/'cli/fixture/legacy-after-manifest.json').read_text())
legacy_snapshot={'before_count':len(legacy_before),'after_count':len(legacy_after),'equal':legacy_before==legacy_after,'before_sha256':hashlib.sha256((cf/'cli/fixture/legacy-before-manifest.json').read_bytes()).hexdigest(),'after_sha256':hashlib.sha256((cf/'cli/fixture/legacy-after-manifest.json').read_bytes()).hexdigest()}
result={'schema':'full-todo.source-catalog-installed-wheel-cli-r3.v1','candidate_head':'7ed55cfc2590268488c7bb34c18b572886fb950c','candidate_tree':'f0734fa1834e126c749bed302c1c6a578f1c2fd2','fixture':{k:fix[k] for k in ('vault','paper_id','claim_id','evidence_ordinal')},'records':records,'cwd_checks':cwd_checks,'legacy_snapshot':legacy_snapshot}
result['pass']=all(x['returncode_ok'] and x['envelope_ok'] and x.get('semantic_ok',True) and x.get('error_code_ok',True) for x in records) and all(x['only_expected'] for x in cwd_checks.values()) and legacy_snapshot['equal']
(cf/'cli-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'pass':result['pass'],'records':len(records),'cwd_checks':cwd_checks,'legacy_snapshot':legacy_snapshot},sort_keys=True))
