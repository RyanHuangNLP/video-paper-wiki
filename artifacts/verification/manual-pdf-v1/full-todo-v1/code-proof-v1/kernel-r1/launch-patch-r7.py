"""Run the same approved prompt with its built-in toolset removed."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
PREPARATION = ROOT / 'docs/ai/packets/full-todo-v1/CODE-GIT-KERNEL-patch-invocation-r7.json'
EXPECTED = '1f7f7dc6b99ed80cf37d02754c058d1e29ff1c575ef3d1062096d2e1b77cc3c9'
raw = PREPARATION.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
for key in ('prompt', 'source_preimage_manifest', 'prior_r6_stop', 'authorization', 'source_subset_proof'):
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
stop = json.loads(Path(record['prior_r6_stop']['path']).read_bytes())
assert stop['process']['started_observed'] is True
assert stop['process']['exit_code'] == 1
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
    '--tools', record['tool_filter']['tools'],
    '--disallowed-tools', record['tool_filter']['disallowed_tools'],
    '--rules', record['additional_rules'],
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
