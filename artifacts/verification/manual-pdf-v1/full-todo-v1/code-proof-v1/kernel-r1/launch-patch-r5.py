"""Launch the exact reviewed Grok patch-output request, without source writes."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
PREPARATION = ROOT / 'docs/ai/packets/full-todo-v1/CODE-GIT-KERNEL-patch-preparation-r5.json'
EXPECTED = '9d922c7f6f3e3a3dfbf041ebfc6a90983fceaf27a2c71d3e6f43e9ec87615fc9'
raw = PREPARATION.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
for key in ('prompt', 'source_preimage_manifest', 'prior_r4_stop', 'authorization'):
    ref = record[key]
    data = Path(ref['path']).read_bytes()
    assert len(data) == ref['size_bytes']
    assert hashlib.sha256(data).hexdigest() == ref['sha256']
handoff = json.loads(Path(record['source_preimage_manifest']['path']).read_bytes())
source = Path(handoff['source_root'])
for ref in record['source_files']:
    data = (source / ref['path']).read_bytes()
    assert len(data) == ref['size_bytes']
    assert hashlib.sha256(data).hexdigest() == ref['sha256']
stop = json.loads(Path(record['prior_r4_stop']['path']).read_bytes())
assert stop['post_stop_process']['pty55333_exit_observed'] is True
directory = Path(record['cwd'])
assert directory.is_dir() and not list(directory.iterdir())
prompt = Path(record['prompt']['path']).read_text(encoding='utf-8')
args = [
    '/Users/huangzhanpeng/.local/bin/grok',
    '--model', 'grok-4.6', '--reasoning-effort', 'xhigh',
    '--permission-mode', 'default', '--no-plan', '--no-subagents',
    '--disable-web-search',
    '--deny', 'Read', '--deny', 'Edit', '--deny', 'Bash', '--deny', 'Grep',
    '--deny', 'MCPTool(*)',
    '--session-id', record['session_id'], '--max-turns', '2',
    '--output-format', 'plain', '--single', prompt,
]
env = dict(os.environ, GROK_DISABLE_AUTOUPDATER='1', GROK_MEMORY='0',
           GROK_WRITE_FILE='0', GROK_SUBAGENTS='0')
with Path(record['stdout']).open('xb') as stdout, Path(record['stderr']).open('xb') as stderr:
    os.dup2(stdout.fileno(), 1)
    os.dup2(stderr.fileno(), 2)
    os.chdir(directory)
    os.execve(args[0], args, env)
