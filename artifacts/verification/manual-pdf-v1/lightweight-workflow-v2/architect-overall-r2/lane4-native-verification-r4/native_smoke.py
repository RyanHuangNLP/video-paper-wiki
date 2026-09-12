from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

E = Path(__file__).resolve().parent
ROOT = E.parents[5]
SOURCE = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/source'
result = json.loads((E / 'host-full-result.json').read_text())
assert result['returncode'] == 0
tmp = Path(result['temporary_directory'])
records = list(tmp.rglob('installed-observation.json'))
assert len(records) == 1, records
record = records[0]
raw = record.read_bytes()
obs = json.loads(raw)
venv = Path(obs['venv'])
python = Path(obs['venv_python'])
script = Path(obs['console_script'])
assert venv.is_relative_to(tmp)
assert Path(obs['observed_prefix']) == venv
assert Path(obs['observed_executable']) == python
assert script.read_text().splitlines()[0] == '#!' + str(python)
assert obs['schema_count'] == 53
for name, row in obs['modules'].items():
    path = Path(row['file'])
    assert path.is_relative_to(venv)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
    assert path.read_bytes() == (SOURCE / 'src/video_paper_wiki_research' / path.name).read_bytes()
(E / 'native-installed-observation.json').write_bytes(raw)
env = {'PATH': str(python.parent) + ':/usr/bin:/bin', 'VIRTUAL_ENV': str(venv), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
workspace = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/scratch/.work/real-pdf-trial-r4'
session = '813d35b2ffa07ce0f49ad7d5bdedf962aac35b361d60148f7fc933a271eb15fb'
args = ['workflow', 'status', '--workspace', str(workspace), '--session-id', session]
commands = []
def run(label, argv):
    cp = subprocess.run(argv, cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    payload = json.loads(cp.stdout)
    commands.append({'name': label, 'argv': argv, 'returncode': cp.returncode, 'stdout': payload, 'stderr': cp.stderr})
    assert cp.returncode == 0 and payload['ok'] is True and payload['state'] == 'complete', commands[-1]
    return payload
module_result = run('direct-native-module', [str(python), '-I', '-B', '-m', 'video_paper_wiki_research'] + args)
console_result = run('direct-native-console', [str(script)] + args)
assert module_result == console_result
# Execute the same installed entrypoint with a local in-process observer.
# The direct executable was independently run above; no installed files are modified.
trace = '''
import hashlib,json,runpy,sys
from pathlib import Path
target=sys.argv[1]
sys.argv=sys.argv[1:]
try:
    runpy.run_path(target,run_name='__main__')
finally:
    modules={name:{'file':str(Path(mod.__file__)), 'sha256':hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()} for name,mod in sys.modules.items() if name in ('video_paper_wiki_research.cli','video_paper_wiki_research.light_workflow')}
    print('NATIVE_ORIGIN='+json.dumps({'prefix':sys.prefix,'executable':sys.executable,'modules':modules}),file=sys.stderr)
'''
trace_result = run('observed-installed-console-script', [str(python), '-I', '-B', '-c', trace, str(script)] + args)
assert trace_result == console_result
origin_lines = [line.removeprefix('NATIVE_ORIGIN=') for line in commands[-1]['stderr'].splitlines() if line.startswith('NATIVE_ORIGIN=')]
assert len(origin_lines) == 1
origin = json.loads(origin_lines[0])
assert origin['prefix'] == str(venv) and origin['executable'] == str(python)
for name, row in origin['modules'].items():
    assert row == obs['modules'][name]
assert len(origin['modules']) == 2
out = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'decision': 'PASS_NATIVE_INSTALLED_ENVIRONMENT_AND_EQUIVALENT_WORKFLOW_STATUS', 'native_observation_original': str(record), 'native_observation_sha256': hashlib.sha256(raw).hexdigest(), 'cwd_outside_source': str(tmp), 'pythonpath_present': 'PYTHONPATH' in env, 'copied_or_relocated_venv': False, 'console_shebang': script.read_text().splitlines()[0], 'origin': origin, 'commands': commands, 'actual_module_files_checked': len(obs['modules']), 'exact_schema_count': 53, 'external_model_invocation': False}
(E / 'native-smoke.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({'decision': out['decision'], 'venv': str(venv), 'observed_modules': len(obs['modules']), 'direct_entries_equal': True}))
