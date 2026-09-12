"""Full regression driver for a frozen foundation candidate and verified wheel."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


R = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
F = R / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/foundation-r1'
inputs_bytes = (F / 'full-regression-inputs-r1.json').read_bytes()
inputs = json.loads(inputs_bytes)
candidate_bytes = Path(inputs['candidate']['path']).read_bytes()
assert len(candidate_bytes) == inputs['candidate']['size_bytes']
assert hashlib.sha256(candidate_bytes).hexdigest() == inputs['candidate']['sha256']
candidate = json.loads(candidate_bytes)
freeze = json.loads((R / 'docs/ai/packets/full-todo-v1/CODE-PROOF-FOUNDATION-freeze-r1.json').read_text())
expected = {row['relative_path']: row for row in freeze['baseline_tracked_files']}
expected.update({row['relative_path']: row for row in candidate['product_paths']})
assert set(row['relative_path'] for row in candidate['product_paths']) == set(freeze['allowed_product_paths'])
assert candidate['baseline_head'] == freeze['baseline_head']
assert candidate['baseline_tree'] == freeze['baseline_tree']
wheel_pin = inputs['verified_installed_wheel']
assert inputs['installed_probes_passed_py312_py313'] is True
tag = sys.argv[1]
assert tag in ('312', '313')
interpreter = '/private/tmp/l4r5.s54ypl35/locked-312/bin/python' if tag == '312' else str(R / '.venv/bin/python')
uv = '/Users/huangzhanpeng/.hermes/bin/uv'


def pin(path):
    data = Path(path).read_bytes()
    return {'path': str(path), 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def guard():
    assert (F / 'full-regression-inputs-r1.json').read_bytes() == inputs_bytes
    assert pin(inputs['candidate']['path']) == inputs['candidate']
    for source in (candidate['source_root'], inputs['test_root']):
        for relative, row in expected.items():
            path = Path(source) / relative
            assert path.is_file() and not path.is_symlink(), str(path)
            actual = pin(path)
            assert all(actual[k] == row[k] for k in ('size_bytes', 'sha256')), str(path)
    for root, head, tree in (
        (candidate['source_root'], candidate['baseline_head'], candidate['baseline_tree']),
        (inputs['test_root'], inputs['test_mirror_head'], inputs['test_mirror_tree']),
    ):
        assert subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip() == head
        assert subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD^{tree}'], text=True).strip() == tree
    assert pin(wheel_pin['path']) == wheel_pin
    return {'expected_files_each_root': len(expected), 'source_and_mirror_unchanged': True, 'wheel_unchanged': True}


record_path = F / f'foundation-full-r1-py{tag}.execution.json'
stdout_path = F / f'foundation-full-r1-py{tag}.stdout.log'
stderr_path = F / f'foundation-full-r1-py{tag}.stderr.log'
assert not any(p.exists() for p in (record_path, stdout_path, stderr_path))
before = guard()
uv_version = subprocess.check_output([uv, '--version'], text=True).strip()
assert uv_version.split()[:2] == ['uv', '0.12.7']
scratch = Path(tempfile.mkdtemp(prefix=f'cf{tag}-', dir='/private/tmp'))
command = [interpreter, '-B', '-m', 'pytest', '-q', '--basetemp', str(scratch / 'p'), '-o', f'cache_dir={scratch / "cache"}']
env = dict(os.environ)
env.update(
    UV_OFFLINE='1',
    UV_PYTHON_DOWNLOADS='never',
    UV_PYTHON=interpreter,
    LW2_INSTALLED_WHEEL=wheel_pin['path'],
    LW2_PYTHON=interpreter,
    LW2_UV=uv,
    PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
    PYTHONDONTWRITEBYTECODE='1',
    PYTHONNOUSERSITE='1',
    PYTHONPATH=f'{inputs["test_root"]}/src:{inputs["test_root"]}',
)
env['PATH'] = os.pathsep.join((str(Path(interpreter).parent), str(Path(uv).parent), env.get('PATH', '')))
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps({'started_at_utc': started, 'command': command, 'candidate_snapshot_sha256': candidate['snapshot_sha256']}), flush=True)
with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
    result = subprocess.run(command, cwd=inputs['test_root'], env=env, stdout=stdout, stderr=stderr)
record = {
    'schema': 'full-todo.code-foundation-full-regression.v1',
    'started_at_utc': started,
    'completed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'candidate_snapshot_sha256': candidate['snapshot_sha256'],
    'candidate': inputs['candidate'],
    'full_regression_inputs': pin(F / 'full-regression-inputs-r1.json'),
    'command': command,
    'cwd': inputs['test_root'],
    'exit_code': result.returncode,
    'uv_version': uv_version,
    'explicit_uv_python': interpreter,
    'verified_installed_wheel': wheel_pin,
    'before': before,
    'after': guard(),
    'stdout': pin(stdout_path),
    'stderr': pin(stderr_path),
    'tail': stdout_path.read_text(errors='replace')[-6000:],
    'remote_ci': False,
}
with record_path.open('x') as handle:
    handle.write(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(result.returncode)
