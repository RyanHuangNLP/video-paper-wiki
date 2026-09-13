import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path('<REPO>')
OUT = Path('<TMP>/vph-acceptance')
OUT.mkdir(exist_ok=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory():
    previous = json.loads((ROOT / 'artifacts/verification/VPKB-000-projection-contracts/ledger-locator/local/source-files.json').read_text())
    candidate = json.loads(Path('<TMP>/vph-candidate.json').read_text())
    paths = set(previous['files']) | set(candidate['files']) | {'docs/ai/contracts/assessment-history-v1.md'}
    files = {path: digest(ROOT / path) for path in sorted(paths)}
    return {'files': files, 'file_count': len(files), 'snapshot_sha256': hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}

if sys.argv[1] == 'snapshot':
    value = inventory()
    value.update(packet='VPKB-000-projection-contracts', scope='Frozen assessment history slice source plus previous accepted locator inputs; unfinished input/catalog drafts and status/evidence are excluded.',
                 baseline_head='3e2bebb1d50928a7af95e07b4868bdbe8113cd0b',
                 snapshot_encoding='SHA256 of UTF-8 json.dumps(files, sort_keys=True, separators=(comma, colon))', source_kind='working-tree candidate, not a commit')
    (OUT / 'source-files.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: value[key] for key in ('file_count', 'snapshot_sha256')}))
    raise SystemExit(0)

label = sys.argv[1]
assert label in ('312', '313')
python = '<TMP>/vpkb-py312-venv/bin/python' if label == '312' else str(ROOT / '.venv/bin/python')
expected = json.loads((OUT / 'source-files.json').read_text())
before = inventory()
assert before['files'] == expected['files']
command = [python, '-m', 'pytest', '-q', '--basetemp=<TMP>/vphf' + label,
           '--junitxml=' + str(OUT / ('python' + label + '.xml'))]
environment = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
start = time.time()
with (OUT / ('python' + label + '.log')).open('wb') as log:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
after = inventory()
tree = ET.parse(OUT / ('python' + label + '.xml'))
suites = list(tree.getroot()) if tree.getroot().tag == 'testsuites' else [tree.getroot()]
counts = {key: sum(int(suite.get(key, '0')) for suite in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
record = dict(label=label, argv=command, cwd=str(ROOT), environment={'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
              python=subprocess.check_output([python, '--version'], text=True).strip(), exit_code=result.returncode,
              elapsed_seconds=time.time()-start, counts=counts, source_snapshot_sha256=expected['snapshot_sha256'],
              source_unchanged=after['files'] == before['files'], log_sha256=digest(OUT / ('python' + label + '.log')),
              junit_sha256=digest(OUT / ('python' + label + '.xml')), runner_sha256=digest(Path(__file__)))
(OUT / ('python' + label + '-result.json')).write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
(OUT / ('python' + label + '-source-after.json')).write_text(json.dumps(after, indent=2, sort_keys=True) + '\n')
print(json.dumps(record))
assert record['source_unchanged']
raise SystemExit(result.returncode)
