"""Submit the frozen CONFIG correction for one output-only Grok response."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
PREPARATION = ROOT / 'docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-patch-preparation-r4.json'
EXPECTED = '5497ea7f4fd16531d8da7495ccdafd2fe77e4133e962b56929c65586491203b7'
EVIDENCE = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'


def check(ref):
    raw = Path(ref['path']).read_bytes()
    assert len(raw) == ref['size_bytes']
    assert hashlib.sha256(raw).hexdigest() == ref['sha256']


raw = PREPARATION.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
go = json.loads((EVIDENCE / 'architect-patch-dispatch-go-r4.json').read_bytes())
assert go['decision'] == 'GO_FOR_ONE_NORMAL_REVIEW_CONFIG_PATCH_R4_CALL'
assert go['preparation']['sha256'] == EXPECTED
for key in ('preparation', 'launcher', 'independent_review'):
    check(go[key])
for key in ('prompt', 'original_config_freeze', 'source_preimage', 'rejection',
            'prior_config_stop', 'user_config_confirmation', 'prior_grok_stdout'):
    check(record[key])
original = json.loads(Path(record['original_config_freeze']['path']).read_bytes())
for ref in original['baseline_source_test_files']:
    check(ref)
source = Path(record['source_root'])
for ref in record['source_files']:
    check(dict(ref, path=str(source / ref['path'])))
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                               text=True).strip() == record['baseline_head']
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD^{tree}'],
                               text=True).strip() == record['baseline_tree']
actual_status = set(subprocess.check_output(
    ['git', '-C', str(source), 'status', '--porcelain'], text=True).splitlines())
assert actual_status == {'?? ' + ref['path'] for ref in record['source_files']}
stopped = json.loads(Path(record['prior_config_stop']['path']).read_bytes())
assert stopped['attempt']['launcher_exit_code'] == 0
assert stopped['attempt']['launcher_exit_observed'] is True
assert stopped['attempt']['grok_process_exit_observed'] is True
directory = Path(record['cwd'])
assert directory.is_dir() and not list(directory.iterdir())
runtime = record['runtime']
check(runtime['executable'])
policy = record['invocation']
prompt = Path(record['prompt']['path']).read_text(encoding='utf-8')
args = [runtime['executable']['path'], '--model', 'grok-4.6',
        '--reasoning-effort', 'xhigh', '--permission-mode', 'default',
        '--no-plan', '--no-subagents', '--disable-web-search', '--no-auto-update',
        '--deny', 'Read', '--deny', 'Edit', '--deny', 'Bash', '--deny', 'Grep',
        '--deny', 'MCPTool(*)', '--deny', 'WebFetch(*)', '--deny', 'WebSearch(*)',
        '--tools', policy['tools'], '--disallowed-tools', policy['disallowed_tools'],
        '--rules', policy['rules'], '--session-id', runtime['session_id'],
        '--max-turns', '2', '--output-format', 'plain', '--single', prompt]
env = dict(os.environ, GROK_DISABLE_AUTOUPDATER='1', GROK_MEMORY='0',
           GROK_WRITE_FILE='0', GROK_SUBAGENTS='0')
with Path(runtime['stdout']).open('xb') as stdout, Path(runtime['stderr']).open('xb') as stderr:
    os.dup2(stdout.fileno(), 1)
    os.dup2(stderr.fileno(), 2)
    os.chdir(directory)
    os.execve(args[0], args, env)
