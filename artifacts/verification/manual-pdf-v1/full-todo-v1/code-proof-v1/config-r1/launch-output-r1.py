"""Launch the frozen read-only Grok Build config implementation request once."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
FREEZE = ROOT / 'docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-freeze-r1.json'
EXPECTED = 'def0a0e66576cc56d7f3900836e9f6a4eeef3f843e15ed74118bf473d2de139d'
EVIDENCE = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'


def check(ref):
    raw = Path(ref['path']).read_bytes()
    assert len(raw) == ref['size_bytes']
    assert hashlib.sha256(raw).hexdigest() == ref['sha256']


raw = FREEZE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
go = json.loads((EVIDENCE / 'architect-dispatch-go-r1.json').read_bytes())
assert go['decision'] == 'GO_FOR_EXACT_CONFIG_READ_ONLY_OUTPUT_LAUNCH'
assert go['freeze']['sha256'] == EXPECTED
check(go['freeze'])
check(go['launcher'])
check(go['independent_review'])
for key in ('prompt', 'kernel_exact_acceptance', 'contract_preparation_acceptance',
            'generated_oracle_acceptance', 'input_descriptor'):
    check(record[key])
for item in record['semantic_inputs']:
    check(item['original'])
    check(item['copy'])
check(record['legacy_helper_input']['derived_from'])
check(record['legacy_helper_input']['copy'])
for item in record['baseline_source_test_files']:
    check(item)
source = Path(record['source_root'])
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                               text=True).strip() == record['baseline_head']
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD^{tree}'],
                               text=True).strip() == record['baseline_tree']
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'])
assert all(not (source / path).exists() for path in record['prospective_paths'])
runtime = record['runtime']
check(runtime['executable'])
directory = Path(record['input_directory'])
expected_names = {Path(item['copy']['path']).name for item in record['semantic_inputs']}
expected_names.update({'legacy-helper-interface.md', 'invocation-inputs.json'})
assert {item.name for item in directory.iterdir()} == expected_names
assert all(item.is_file() and not item.is_symlink() for item in directory.iterdir())
args = [runtime['executable']['path'], '--model', 'grok-4.6',
        '--reasoning-effort', 'xhigh', '--permission-mode', 'default',
        '--no-plan', '--no-subagents', '--disable-web-search', '--no-auto-update',
        '--tools', 'read_file',
        '--disallowed-tools', 'search_replace,write,run_terminal_command,run_terminal_cmd,grep,list_dir,todo_write,web_search,web_fetch,Agent',
        '--deny', 'Edit', '--deny', 'Write', '--deny', 'Bash', '--deny', 'Grep',
        '--deny', 'MCPTool(*)', '--deny', 'WebFetch(*)', '--deny', 'WebSearch(*)',
        '--rules', 'Use only read_file on the eight named prepared input files. Return both complete source files in the requested BEGIN_FILE format and the honest unrun-test brief. Do not request writing, shell, web, MCP or agents.',
        '--session-id', runtime['session_id'], '--max-turns', '40',
        '--output-format', 'plain', '--prompt-file', record['prompt']['path']]
env = dict(os.environ, GROK_DISABLE_AUTOUPDATER='1', GROK_MEMORY='0',
           GROK_WRITE_FILE='0', GROK_SUBAGENTS='0')
with Path(runtime['stdout']).open('xb') as stdout, Path(runtime['stderr']).open('xb') as stderr:
    os.dup2(stdout.fileno(), 1)
    os.dup2(stderr.fileno(), 2)
    os.chdir(directory)
    os.execve(args[0], args, env)
