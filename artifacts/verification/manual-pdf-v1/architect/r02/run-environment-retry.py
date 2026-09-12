from pathlib import Path
import hashlib,json,os,subprocess,time
from datetime import datetime,timezone
base=Path(__file__).parent
meta=json.loads((base/'start.json').read_text())
for check in meta['checks']:
    assert hashlib.sha256((Path(meta['source'])/check['path']).read_bytes()).hexdigest()==check['expected'],check['path']
nodes=json.loads((base/'retry-nodes.json').read_text())
env=os.environ.copy()
env.update({'PATH':'/Users/huangzhanpeng/.hermes/bin:'+env.get('PATH',''),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','UV_PYTHON_DOWNLOADS':'never','UV_OFFLINE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
env.pop('PYTHONPATH',None)
cmd=[meta['python'],'-B','-m','pytest','-q',*nodes,'--basetemp',meta['run_root']+'/r','-o','cache_dir='+meta['run_root']+'/retry-cache']
start=time.monotonic()
with (base/'environment-retry.log').open('w') as log:
    p=subprocess.Popen(cmd,cwd=meta['source'],env=env,stdout=log,stderr=subprocess.STDOUT)
    launch={'pid':p.pid,'argv':cmd,'cwd':meta['source'],'started_utc':datetime.now(timezone.utc).isoformat()}
    (base/'environment-retry-launch.json').write_text(json.dumps(launch,indent=2)+'\n')
    print(json.dumps({'pid':p.pid,'selected_tests':len(nodes),'started_utc':launch['started_utc']}),flush=True)
    rc=p.wait()
result={'exit_code':rc,'elapsed_seconds':round(time.monotonic()-start,3)}
(base/'environment-retry-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
print('\n'.join((base/'environment-retry.log').read_text().splitlines()[-12:]),flush=True)
raise SystemExit(rc)
