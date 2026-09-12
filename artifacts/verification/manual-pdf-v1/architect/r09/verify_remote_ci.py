"""Read-only exact-head CI acceptance checks against GitHub metadata and job logs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).parent
OUT = ROOT / 'remote-check'
OUT.mkdir(exist_ok=True)
REPO = 'repos/RyanHuangNLP/video-paper-wiki'
HEAD = '0fcae592acb977c6b422e7de3b2c3e0cf79df5a0'
BASE = '08709894adfb20ec07e976783f0ba436d975b74f'
MERGE = '6931e1a8f57ec4b0f22d004b92e9842e3bf48908'
RUN = 34046551184

def api(item):
    name, endpoint = item
    p = subprocess.run(['gh', 'api', REPO + endpoint], capture_output=True, timeout=60)
    (OUT / name).write_bytes(p.stdout)
    assert p.returncode == 0, (endpoint, p.stderr.decode(errors='replace'))
    return name, p.stdout

requests = [('pr.json', '/pulls/95'), ('run.json', f'/actions/runs/{RUN}'),
            ('jobs.json', f'/actions/runs/{RUN}/attempts/1/jobs'), ('merge.json', '/git/commits/' + MERGE)]
with ThreadPoolExecutor(max_workers=4) as pool:
    data = {name: json.loads(value) for name, value in pool.map(api, requests)}
pr, run, jobs, merge = (data[x] for x in ('pr.json', 'run.json', 'jobs.json', 'merge.json'))
assert pr['state'] == 'open' and pr['draft'] is True and pr['merged'] is False
assert pr['auto_merge'] is None
assert pr['head']['sha'] == HEAD and pr['base']['sha'] == BASE and pr['base']['ref'] == 'integration'
assert pr['merge_commit_sha'] == MERGE
assert run['id'] == RUN and run['run_attempt'] == 1 and run['head_sha'] == HEAD
assert run['conclusion'] == 'success' and run['status'] == 'completed' and run['event'] == 'pull_request'
assert [p['sha'] for p in merge['parents']] == [BASE, HEAD]
assert jobs['total_count'] == 4 and len(jobs['jobs']) == 4
expected = {'macos-15 / Python 3.12', 'macos-15 / Python 3.13',
            'ubuntu-24.04 / Python 3.12', 'ubuntu-24.04 / Python 3.13'}
assert {j['name'] for j in jobs['jobs']} == expected
assert all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs['jobs'])
with ThreadPoolExecutor(max_workers=4) as pool:
    logs = dict(pool.map(api, [(str(j['id']) + '.log', f"/actions/jobs/{j['id']}/logs") for j in jobs['jobs']]))
observations = []
for job in jobs['jobs']:
    name = str(job['id']) + '.log'
    log = logs[name].decode(errors='replace')
    assert f'+{MERGE}:refs/remotes/pull/95/merge' in log
    assert f'Merge {HEAD} into {BASE}' in log
    counts = re.findall(r'\b(\d+) passed in ([^\r\n]+)', log)
    assert len(counts) == 1 and counts[0][0] == '2246', counts
    assert 'uv run --offline --no-sync python -m pytest -q' in log
    assert 'git diff --exit-code -- pyproject.toml uv.lock' in log
    observations.append({'id': job['id'], 'name': job['name'], 'conclusion': job['conclusion'],
                         'tests_passed': int(counts[0][0]), 'duration_text': counts[0][1],
                         'checkout_sha': MERGE, 'log_file': str(OUT / name),
                         'log_sha256': hashlib.sha256(logs[name]).hexdigest()})
result = {'ok': True, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
          'run_id': RUN, 'run_attempt': 1, 'head': HEAD, 'base': BASE, 'merge_preview': MERGE,
          'merge_parents': [BASE, HEAD], 'pr_url': pr['html_url'], 'draft': True,
          'merged': False, 'jobs': observations,
          'metadata_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.json')}}
(ROOT / 'remote-ci-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'ok': True, 'run': RUN, 'jobs': len(observations), 'tests_per_job': 2246, 'draft': True}))
