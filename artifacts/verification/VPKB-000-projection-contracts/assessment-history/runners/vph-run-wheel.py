import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('<REPO>')
OUT = Path('<TMP>/vph-acceptance')
UV = '<TMP>/vpkb-tooling.r892iw/bin/uv'
PYTHON = '<TMP>/vpkb-wheel-venv/bin/python'
environment = dict(os.environ, UV_CACHE_DIR='<TMP>/vpkb-uv-cache', PYTHONDONTWRITEBYTECODE='1')
environment.pop('PYTHONPATH', None)
environment.pop('PYTHONHOME', None)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
snapshot = json.loads((OUT / 'source-files.json').read_text())
expected = snapshot['files']
assert all(sha(ROOT / path) == value for path, value in expected.items())
records = []

def run(label, command, cwd):
    start = time.time()
    with (OUT / (label + '.log')).open('wb') as log:
        result = subprocess.run(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT)
    record = dict(label=label, argv=command, cwd=str(cwd), exit_code=result.returncode,
                  elapsed_seconds=time.time()-start, log_sha256=sha(OUT / (label + '.log')))
    records.append(record)
    print(json.dumps(record), flush=True)
    if result.returncode: raise SystemExit(result.returncode)

run('wheel-build', [UV, 'build', '--offline', '--wheel', '--out-dir', str(OUT / 'dist')], ROOT)
wheels = list((OUT / 'dist').glob('*.whl'))
assert len(wheels) == 1
run('wheel-install', [UV, 'pip', 'install', '--offline', '--no-deps', '--reinstall', '--python', PYTHON, str(wheels[0])], Path('<TMP>'))
smoke = Path('<TMP>/vpl-acceptance/wheel-smoke.py').read_text()
smoke += '''
from video_paper_wiki.assessment_history import derive_assessment_heads
history_vectors_path = Path('<TMP>/vph-steward-vectors.json')
assert hashlib.sha256(history_vectors_path.read_bytes()).hexdigest() == '43b38f50b725a98ac3d265124c946cbc18d8100bc9d78cb7666e79896fcbbe40'
history_vectors = json.loads(history_vectors_path.read_text())
for vector in history_vectors['positive']:
    supplied = copy.deepcopy(vector['input'])
    before = copy.deepcopy(supplied)
    heads = derive_assessment_heads(**supplied)
    assert heads == vector['expected_heads'], vector['name']
    assert type(heads) is dict and list(heads) == sorted(heads)
    assert supplied == before, vector['name']
    reverse = {'claims':list(reversed(supplied['claims'])), 'events':list(reversed(supplied['events']))}
    assert derive_assessment_heads(**reverse) == vector['expected_heads'], vector['name']
    heads.clear()
    assert derive_assessment_heads(**supplied) == vector['expected_heads'], vector['name']
for vector in history_vectors['negative']:
    try: derive_assessment_heads(**vector['input'])
    except ContractError as exc:
        assert exc.code == vector['expected_error'], (vector['name'], exc.code)
        assert exc.exit_code == vector['exit_code'], vector['name']
    else: raise AssertionError('invalid history accepted: '+vector['name'])
print(json.dumps({'packet':'VPKB-000-projection-contracts', 'slice':'assessment-history', 'status':'passed',
    'independent_positive_vectors':len(history_vectors['positive']),
    'independent_negative_vectors':len(history_vectors['negative']),
    'schema_count':len(names), 'module_path':video_paper_wiki.__file__,
    'limitations':'Pure supplied history consistency only; no actual human authorization, Vault membership, source/artifact closure or transaction integrity.'}))
'''
path = OUT / 'wheel-smoke.py'
path.write_text(smoke)
run('wheel-smoke', [PYTHON, '-I', str(path)], Path('<TMP>'))
after = {path:sha(ROOT / path) for path in expected}
record = dict(status='passed', commands=records, wheel_sha256=sha(wheels[0]), wheel_path=str(wheels[0]),
              smoke_source_sha256=sha(path), runner_sha256=sha(Path(__file__)), source_unchanged=after == expected,
              source_snapshot_sha256=snapshot['snapshot_sha256'],
              environment_overrides={'UV_CACHE_DIR':environment['UV_CACHE_DIR'], 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':'removed', 'PYTHONHOME':'removed'})
(OUT / 'wheel-result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
print(json.dumps(record))
assert record['source_unchanged']
