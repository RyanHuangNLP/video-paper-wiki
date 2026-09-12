from pathlib import Path
import sys,os,json,hashlib,datetime,subprocess,tempfile,time
R=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
W=R/'.work/parallel/code-proof-v1/terminal-1/source'
C=R/'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'
H=C/'architect-stopped-candidate-r5.json'
label=sys.argv[1]
assert label in ('py312','py313')
handoff=json.loads(H.read_bytes())
freeze=json.loads((R/'docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-freeze-r1.json').read_bytes())
refs=freeze['baseline_source_test_files']+[dict(x,path=str(W/x['path'])) for x in handoff['candidate_files']]
def check_sources():
 for row in refs:
  b=Path(row['path']).read_bytes()
  assert len(b)==row['size_bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],row['path']
check_sources()
assert handoff['source_writes_stopped'] is True
stage=Path(tempfile.mkdtemp(prefix='cv5-',dir='/private/tmp'))
env=os.environ.copy();env.update(PYTHONPATH=str(W/'src'),PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
commands=[('focused',[sys.executable,'-B','-m','pytest','-q','--tb=short','--color=no','tests/unit/test_code_config_parser.py','-o','cache_dir='+str(stage/'cache'),'--basetemp='+str(stage/'base')])]
for name,script in [('generated','architect-generated-json-r2.py'),('adversarial','architect-adversarial-r1.py')]:
 commands.append((name,[sys.executable,'-I','-B',str(C/script),str(H),str(C/('architect-'+name+'-'+label+'-r5.json'))]))
probe_code="""from pathlib import Path
import importlib.util,json
p=Path(__import__('sys').argv[1]);out=Path(__import__('sys').argv[2]);assert not out.exists()
spec=importlib.util.spec_from_file_location('independent_key_probe',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=out;m.main()
d=json.loads(out.read_bytes());assert d['integrity']['unchanged']
for value in d['probes'].values():
 assert value['outcome']=='CODE_CONFIG_ERROR' and value['code']=='CODE_CONFIG_PARSER_MISMATCH'
 assert value['details']=={'instance_pointer':'/payload','reason':'object key type mismatch'}
assert d['probes']['str_subclass_callback']['callbacks']==[]
print('PASS: original independent probe now rejects both keys with bounded mismatch and zero callbacks')
"""
commands.append(('stdlib-key',[sys.executable,'-I','-B','-c',probe_code,str(C/'steward-review-r1/stdlib-key-probe-r1.py'),str(C/('architect-stdlib-key-probe-'+label+'-r5.json'))]))
checks=[]
for name,command in commands:
 started=time.monotonic();run=subprocess.run(command,cwd=W,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 log=C/('architect-'+name+'-'+label+'-r5.log')
 with log.open('xb') as f:f.write(run.stdout)
 checks.append({'check':name,'command':command,'exit_code':run.returncode,'elapsed_seconds':time.monotonic()-started,'log':str(log),'log_sha256':hashlib.sha256(run.stdout).hexdigest(),'tail':run.stdout.decode(errors='replace')[-2000:]})
check_sources()
record={'schema':'full-todo.code-config-architect-validation.v1','revision':5,'label':label,'python':sys.version,'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate_snapshot_sha256':handoff['candidate_snapshot_sha256'],'handoff_sha256':hashlib.sha256(H.read_bytes()).hexdigest(),'verified_source_references':len(refs),'source_unchanged':True,'status':'PASS' if all(x['exit_code']==0 for x in checks) else 'FAILED','checks':checks}
out=C/('architect-validation-'+label+'-r5.json')
with out.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(json.dumps({'status':record['status'],'label':label,'output':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'checks':[{'name':x['check'],'exit_code':x['exit_code'],'tail':x['tail']} for x in checks]},indent=2))
sys.exit(0 if record['status']=='PASS' else 1)
