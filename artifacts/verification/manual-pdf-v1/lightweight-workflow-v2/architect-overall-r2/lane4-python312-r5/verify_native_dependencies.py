from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

E = Path(__file__).resolve().parent
ROOT = E.parents[5]
SOURCE = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/source'
manifest = json.loads((E / 'source-manifest.json').read_text())
for row in manifest['files']:
    data = (SOURCE / row['relative_path']).read_bytes()
    assert len(data) == row['size_bytes']
    assert hashlib.sha256(data).hexdigest() == row['sha256']

probe = '''
from pathlib import Path
import hashlib, importlib.metadata as md, importlib.util, json, sys
import referencing, referencing.typing, jsonschema
spec = importlib.util.find_spec('typing_extensions')
extra = None
if spec is not None:
    import typing_extensions
    typing_extensions.TypeVar('Probe', default=object)
    extra = {'version': md.version('typing-extensions'), 'file': typing_extensions.__file__}
print(json.dumps({'version': sys.version, 'prefix': sys.prefix, 'executable': sys.executable,
    'referencing_version': md.version('referencing'), 'referencing_typing_file': referencing.typing.__file__,
    'referencing_typing_sha256': hashlib.sha256(Path(referencing.typing.__file__).read_bytes()).hexdigest(),
    'jsonschema_version': md.version('jsonschema'), 'typing_extensions': extra}))
'''
observations = {}
for version in ('312', '313'):
    installed = json.loads((E / ('native-installed-observation' + version + '.json')).read_text())
    python = installed['venv_python']
    env = {'PATH': str(Path(python).parent) + ':/usr/bin:/bin', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    cp = subprocess.run([python, '-I', '-B', '-c', probe], cwd='/private/tmp', env=env, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    result = json.loads(cp.stdout)
    assert result['prefix'] == installed['venv']
    assert result['executable'] == python
    assert result['referencing_version'] == '0.37.0'
    assert Path(result['referencing_typing_file']).is_relative_to(Path(installed['venv']))
    if version == '312':
        assert result['version'].startswith('3.12.14')
        assert result['typing_extensions']['version'] == '4.16.0'
        assert Path(result['typing_extensions']['file']).is_relative_to(Path(installed['venv']))
    else:
        assert result['version'].startswith('3.13.13')
        assert result['typing_extensions'] is None
    observations[version] = result

out = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'decision': 'PASS_NATIVE_PYTHON_VERSION_CONDITIONAL_DEPENDENCIES',
    'source_manifest_sha256': hashlib.sha256((E / 'source-manifest.json').read_bytes()).hexdigest(),
    'all_25_source_paths_unchanged': True, 'observations': observations,
    'uv_lock_sha256': hashlib.sha256((SOURCE / 'uv.lock').read_bytes()).hexdigest(),
    'scope': 'Read-only native import verification; original installed venvs, no copying, relocation, package mutation, model invocation or network'}
with (E / 'native-dependency-proof.json').open('x') as stream:
    stream.write(json.dumps(out, indent=2) + '\n')
print(json.dumps(out))
