from pathlib import Path
import json,os,subprocess,time
from datetime import datetime,timezone
evidence=Path(__file__).parent
meta=json.loads((evidence/'start.json').read_text())
env=os.environ.copy()
env.update({'PATH':'/Users/huangzhanpeng/.hermes/bin:'+env.get('PATH',''),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','UV_PYTHON_DOWNLOADS':'never','UV_OFFLINE':'1'})
env.pop('PYTHONPATH',None)
cmd=[meta['python'],'-B','-m','pytest','-q','--basetemp',meta['run_root']+'/p','-o','cache_dir='+meta['run_root']+'/cache']
start=time.monotonic()
with (evidence/'full-pytest.log').open('w') as log:
    p=subprocess.Popen(cmd,cwd=meta['source'],env=env,stdout=log,stderr=subprocess.STDOUT)
    launch={'pid':p.pid,'argv':cmd,'cwd':meta['source'],'started_utc':datetime.now(timezone.utc).isoformat(),'run_root':meta['run_root']}
    (evidence/'full-pytest-launch.json').write_text(json.dumps(launch,indent=2)+'\n')
    print(json.dumps(launch),flush=True)
    rc=p.wait()
result={'exit_code':rc,'elapsed_seconds':round(time.monotonic()-start,3)}
(evidence/'full-pytest-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
print('\n'.join((evidence/'full-pytest.log').read_text().splitlines()[-12:]),flush=True)
raise SystemExit(rc)
