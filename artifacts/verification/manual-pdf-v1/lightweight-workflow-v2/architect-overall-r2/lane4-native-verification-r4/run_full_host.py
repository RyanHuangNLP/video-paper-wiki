from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import tempfile

E = Path(__file__).resolve().parent
ROOT = E.parents[5]
SOURCE = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/source'
PYTHON = ROOT / '.venv/bin/python'
WHEEL = ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-4/wheels/r3/video_paper_wiki-0.1.0-py3-none-any.whl'
assert SOURCE.is_dir() and PYTHON.is_file() and WHEEL.is_file()
tmp = Path(tempfile.mkdtemp(prefix='l4r4h.', dir='/private/tmp')).resolve()
(tmp / 'owner.json').write_text(json.dumps({'owner': 'architect-lane4-r4', 'evidence': str(E)}))
env = dict(os.environ)
env.pop('LW2_INSTALLED_KEEP', None)
env.update({
    'PATH': '/Users/huangzhanpeng/.hermes/bin:' + env.get('PATH', '/usr/bin:/bin'),
    'PYTHONPATH': str(SOURCE / 'src'),
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
    'UV_OFFLINE': '1',
    'UV_PYTHON_DOWNLOADS': 'never',
    'GIT_OPTIONAL_LOCKS': '0',
    'LW2_UV': '/Users/huangzhanpeng/.hermes/bin/uv',
    'LW2_UV_CACHE': '/Users/huangzhanpeng/.cache/uv',
    'UV_CACHE_DIR': '/Users/huangzhanpeng/.cache/uv',
    'LW2_INSTALLED_WHEEL': str(WHEEL),
})
argv = [str(PYTHON), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp', str(tmp / 'base'), '--junitxml', str(E / 'host-full-pytest.xml')]
start = datetime.now(timezone.utc).isoformat()
record = {'started_at_utc': start, 'argv': argv, 'cwd': str(SOURCE), 'temporary_directory': str(tmp), 'external_model_invocation': False}
(E / 'host-full-start.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
with (E / 'host-full-pytest.log').open('xb') as log:
    result = subprocess.run(argv, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
record.update({'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'returncode': result.returncode, 'log_sha256': hashlib.sha256((E / 'host-full-pytest.log').read_bytes()).hexdigest()})
frozen = json.loads((E / 'source-freeze-before.json').read_text())
for row in frozen['files']:
    assert hashlib.sha256((SOURCE / row['relative_path']).read_bytes()).hexdigest() == row['sha256'], row['relative_path']
record['source_25_paths_unchanged_after_full_suite'] = True
(E / 'host-full-result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(result.returncode)
