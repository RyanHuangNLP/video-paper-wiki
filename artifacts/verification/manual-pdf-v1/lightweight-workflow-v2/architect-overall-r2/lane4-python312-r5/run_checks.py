from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys

E = Path(__file__).resolve().parent
ROOT = E.parents[5]
SOURCE = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/source'
TMP = Path(json.loads((E / 'local-integration-authorization.json').read_text())['temporary_directory'])
mode = sys.argv[1]
assert mode in ('before312', 'full312', 'target313')
python = TMP / 'locked-312/bin/python' if mode != 'target313' else ROOT / '.venv/bin/python'
wheel = ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-4/wheels/r3/video_paper_wiki-0.1.0-py3-none-any.whl'
test = SOURCE / 'tests/research/test_light_workflow_installed.py'
before = hashlib.sha256(test.read_bytes()).hexdigest()
if mode == 'before312':
    assert before == '541d2ee195d1eb9ed5aa7948bfae4a56eed431121050d26a4a6e01ced786de4e'
argv = [str(python), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp', str(TMP / mode), '--junitxml', str(E / (mode + '.xml'))]
if mode != 'full312':
    argv.append('tests/research/test_light_workflow_installed.py')
env = dict(os.environ)
env.pop('LW2_INSTALLED_KEEP', None)
env.pop('LW2_PYTHON', None)
env.update({'PATH': '/Users/huangzhanpeng/.hermes/bin:' + env.get('PATH', '/usr/bin:/bin'), 'PYTHONPATH': str(SOURCE / 'src'), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'UV_OFFLINE': '1', 'UV_PYTHON_DOWNLOADS': 'never', 'GIT_OPTIONAL_LOCKS': '0', 'LW2_UV': '/Users/huangzhanpeng/.hermes/bin/uv', 'LW2_UV_CACHE': '/Users/huangzhanpeng/.cache/uv', 'UV_CACHE_DIR': '/Users/huangzhanpeng/.cache/uv', 'LW2_INSTALLED_WHEEL': str(wheel)})
record = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'argv': argv, 'cwd': str(SOURCE), 'temporary_directory': str(TMP / mode), 'test_sha256': before, 'production_wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'environment_setup': 'Existing Python3.12.14; exact locked default dependencies installed once in uniquely owned temporary venv. No extras, project-source installation or model/interpreteter downloads. Test execution is offline.', 'external_model_invocation': False}
(E / (mode + '-start.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
with (E / (mode + '.log')).open('xb') as log:
    cp = subprocess.run(argv, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
assert hashlib.sha256(test.read_bytes()).hexdigest() == before
record.update({'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'returncode': cp.returncode, 'source_test_unchanged': True, 'log_sha256': hashlib.sha256((E / (mode + '.log')).read_bytes()).hexdigest()})
(E / (mode + '-result.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(cp.returncode)
