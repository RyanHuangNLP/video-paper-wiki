import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('<REPO>')
OUT = Path('<TMP>/vpl-acceptance')
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
smoke = Path('<TMP>/vpr-acceptance-final/wheel-smoke.py').read_text()
smoke = smoke.replace('no runtime builder/SQLite/input codec implementation or human acceptance', 'no production builder/SQLite/complete inventory validator or human acceptance')
smoke += '''
from video_paper_wiki.ledger_locator import (
    encode_ledger_locator, decode_ledger_locator,
    encode_ledger_evidence, decode_ledger_evidence,
)
from video_paper_wiki.identity import evidence_fingerprint
locator_vectors_path = Path('<TMP>/vpl-steward-vectors.json')
assert hashlib.sha256(locator_vectors_path.read_bytes()).hexdigest() == '4cb4fac91a9df6746daaa79b93be8dfa839f06c9111fd09ed1acb4ec534d5c16'
locator_vectors = json.loads(locator_vectors_path.read_text())
for vector in locator_vectors['valid_vectors']:
    original = vector['input_locator']
    before = copy.deepcopy(original)
    wire = encode_ledger_locator(original)
    assert wire == vector['expected_wire']
    assert hashlib.sha256(wire.encode()).hexdigest() == vector['wire_sha256']
    restored = decode_ledger_locator(wire)
    assert restored == vector['expected_decoded_locator']
    assert encode_ledger_locator(restored) == wire
    for relation, upstream in locator_vectors['relation_map'].items():
        domain = dict(original, relation=relation)
        encoded = encode_ledger_evidence(domain)
        assert encoded == {'source_id':original['source_id'], 'relation':upstream, 'locator':wire}
        decoded = decode_ledger_evidence(encoded)
        assert decoded == dict(vector['expected_decoded_locator'], relation=relation)
        assert evidence_fingerprint([decoded]) == vector['evidence_fingerprints'][relation]
    if 'bbox' in restored: restored['bbox'][0] = 777
    if 'lines' in restored: restored['lines']['start'] = 777
    assert original == before
for vector in locator_vectors['invalid_wire_vectors']:
    try: decode_ledger_locator(vector['wire'])
    except ContractError as exc:
        assert exc.code == vector['code'], vector['name']
        if vector.get('pointer') is not None:
            assert exc.details['instance_pointer'] == vector['pointer'], vector['name']
    else: raise AssertionError('invalid wire accepted: '+vector['name'])
print(json.dumps({'packet':'VPKB-000-projection-contracts', 'slice':'ledger-locator', 'status':'passed',
    'independent_positive_vectors':len(locator_vectors['valid_vectors']),
    'independent_negative_vectors':len(locator_vectors['invalid_wire_vectors']),
    'relations':3, 'schema_count':len(names), 'module_path':video_paper_wiki.__file__,
    'limitations':'Pure supplied-data codec only; not complete inventory, real coordinates, SQLite, adapter or human acceptance.'}))
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
