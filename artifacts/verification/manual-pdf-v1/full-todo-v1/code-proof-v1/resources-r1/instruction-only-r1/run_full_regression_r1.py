"""Run one locked local regression suite against the frozen resource candidate."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

R = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
I = Path(__file__).parent
candidate = json.loads((I / 'fourteen-path-candidate-r1.json').read_text())
freeze = json.loads((R / 'docs/ai/packets/full-todo-v1/CODE-PROOF-RESOURCE-freeze-r1.json').read_text())
expected = {row['relative_path']: row for row in freeze['baseline_tracked_files']}
expected.update({row['relative_path']: row for row in candidate['product_paths']})


def guard():
    for source in (candidate['source_root'], candidate['test_root']):
        root = Path(source)
        for rel, row in expected.items():
            path = root / rel
            assert path.is_file() and not path.is_symlink(), str(path)
            data = path.read_bytes()
            assert len(data) == row['size_bytes'], str(path)
            assert hashlib.sha256(data).hexdigest() == row['sha256'], str(path)
        for rev, field in [('HEAD', 'baseline_head'), ('HEAD^{tree}', 'baseline_tree')]:
            actual = subprocess.check_output(['git', '-C', source, 'rev-parse', rev], text=True).strip()
            assert actual == candidate[field], (source, rev, actual)
    return {'all_expected_files_equal': len(expected), 'source_and_mirror_unchanged': True}


tag = sys.argv[1]
assert tag in ('312', '313')
interpreter = '/private/tmp/l4r5.s54ypl35/locked-312/bin/python' if tag == '312' else str(R / '.venv/bin/python')
record_path = I / f'full-py{tag}.execution.json'
stdout_path = I / f'full-py{tag}.stdout.log'
stderr_path = I / f'full-py{tag}.stderr.log'
assert not any(p.exists() for p in (record_path, stdout_path, stderr_path))
before = guard()
scratch = Path(tempfile.mkdtemp(prefix=f'cf{tag}-', dir='/private/tmp'))
cmd = [interpreter, '-B', '-m', 'pytest', '-q', '--basetemp', str(scratch / 'p'), '-o', f'cache_dir={scratch / "cache"}']
env = dict(os.environ)
env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONPATH=f'{candidate["test_root"]}/src:{candidate["test_root"]}')
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps({'started_at_utc': started, 'command': cmd, 'snapshot_sha256': candidate['snapshot_sha256']}), flush=True)
with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
    result = subprocess.run(cmd, cwd=candidate['test_root'], env=env, stdout=stdout, stderr=stderr)
record = {
    'schema': 'full-todo.code-resource-local-full-regression.v1',
    'started_at_utc': started,
    'completed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': cmd,
    'cwd': candidate['test_root'],
    'snapshot_sha256': candidate['snapshot_sha256'],
    'exit_code': result.returncode,
    'before': before,
    'after': guard(),
    'stdout': {'path': str(stdout_path), 'size_bytes': stdout_path.stat().st_size, 'sha256': hashlib.sha256(stdout_path.read_bytes()).hexdigest()},
    'stderr': {'path': str(stderr_path), 'size_bytes': stderr_path.stat().st_size, 'sha256': hashlib.sha256(stderr_path.read_bytes()).hexdigest()},
    'tail': stdout_path.read_text(errors='replace')[-6000:],
    'remote_ci': False,
}
record_path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(result.returncode)
