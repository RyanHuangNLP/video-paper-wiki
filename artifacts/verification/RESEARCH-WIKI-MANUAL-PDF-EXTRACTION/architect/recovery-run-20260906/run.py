import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

root = Path(__file__).resolve().parent
repo = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
meta = json.loads((root / 'meta.json').read_text())
prompt = repo / 'artifacts/verification/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION/monitor/grok-manual-pdf-r3-prompt.md'
assert hashlib.sha256(prompt.read_bytes()).hexdigest() == meta['prompt_sha256']
assert hashlib.sha256((repo / 'docs/ai/contracts/manual-pdf-extraction-v1.md').read_bytes()).hexdigest() == 'd09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f'
remaining = meta['deadline_unix'] - time.time()
if remaining <= 0:
    raise SystemExit('Authorized run deadline has passed; no process started.')
argv = [
    '/Users/huangzhanpeng/.local/bin/grok', '--cwd', str(repo),
    '--sandbox', 'workspace', '--permission-mode', 'auto',
    '--no-memory', '--no-subagents', '--disable-web-search',
    '--model', 'grok-4.6', '--reasoning-effort', 'xhigh',
    '--session-id', meta['session_id'], '--max-turns', '48',
    '--output-format', 'json', '--prompt-file', str(prompt),
    '--rules', 'Authorized run deadline: 2026-09-06T03:43:50Z. Implement the frozen packet, but stop and write an honest partial development brief before that deadline if unfinished. Do not start new work after the deadline. No Git mutations. Do not claim partial work is complete.',
]
started = time.time()
with (root / 'stdout.json').open('w') as out, (root / 'stderr.log').open('w') as err:
    process = subprocess.Popen(argv, cwd=repo, stdout=out, stderr=err, start_new_session=True)
    state = {'pid': process.pid, 'process_group': process.pid, 'session_id': meta['session_id'], 'started_unix': started, 'argv': argv, 'deadline_utc': meta['deadline_utc']}
    (root / 'launch.json').write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps({'state': 'process_created', 'pid': process.pid, 'session_id': meta['session_id']}), flush=True)
    try:
        code = process.wait(timeout=max(1, meta['deadline_unix'] - time.time()))
    except subprocess.TimeoutExpired:
        state['deadline_reached'] = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    state.update({'exit_code': code, 'ended_unix': time.time()})
    (root / 'completion.json').write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps({'exit_code': code, 'elapsed_seconds': state['ended_unix'] - started, 'deadline_reached': state.get('deadline_reached', False)}), flush=True)
raise SystemExit(code)
