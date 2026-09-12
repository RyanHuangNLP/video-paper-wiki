"""Launch the exact reviewed read-only Grok resource generation once."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
FREEZE = ROOT / 'docs/ai/packets/full-todo-v1/CODE-PROOF-RESOURCE-freeze-r1.json'
EXPECTED = '294180fbdd1c76d9e23969fd12299f9050712035cc86b4676b481a0f2f109830'
E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resources-r1'


def check(ref, allow_symlink=False):
    path = Path(ref['path'])
    assert path.is_file() and (allow_symlink or not path.is_symlink()), path
    raw = path.read_bytes()
    assert len(raw) == ref['size_bytes'], path
    assert hashlib.sha256(raw).hexdigest() == ref['sha256'], path


raw = FREEZE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
go = json.loads((E / 'architect-resource-dispatch-go-r1.json').read_bytes())
assert go['decision'] == 'GO_FOR_EXACT_RESOURCE_READ_ONLY_OUTPUT_LAUNCH'
assert go['freeze']['sha256'] == EXPECTED
assert go['launcher']['path'] == str(Path(__file__).resolve())
for key in ('freeze', 'launcher', 'independent_review'):
    check(go[key])
for key in ('prompt', 'config_exact_local_acceptance', 'input_descriptor',
            'preparation_script', 'existing_count_test'):
    check(record[key])
for key in ('preparation_reviews', 'local_fixture_inputs', 'baseline_tracked_files', 'old_schema_files'):
    for item in record[key]:
        check(item)
for item in record['semantic_inputs']:
    check(item['original'])
    check(item['copy'])
source = Path(record['source_root'])


def git(*args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()


assert git('rev-parse', 'HEAD') == record['baseline_head']
assert git('rev-parse', 'HEAD^{tree}') == record['baseline_tree']
assert not git('status', '--porcelain')
for item in record['baseline_gitlinks']:
    directory = source / item['relative_path']
    assert directory.is_dir() and not directory.is_symlink() and not list(directory.iterdir())
    assert git('ls-files', '--stage', '--', item['relative_path']) == (
        item['mode'] + ' ' + item['oid'] + ' 0\t' + item['relative_path'])
for path in record['initially_absent_paths']:
    target = source / path
    assert not target.exists() and not target.is_symlink()
directory = Path(record['input_directory'])
assert directory.is_dir() and not directory.is_symlink()
expected_names = {Path(item['copy']['path']).name for item in record['semantic_inputs']}
expected_names.add('invocation-inputs.json')
assert len(expected_names) == record['model_input_file_count'] == 25
assert {item.name for item in directory.iterdir()} == expected_names
assert all(item.is_file() and not item.is_symlink() for item in directory.iterdir())
runtime = record['runtime']
check(runtime['executable'], allow_symlink=True)
check(runtime['executable_realpath'])
assert str(Path(runtime['executable']['path']).resolve()) == runtime['executable_realpath']['path']
assert runtime['cwd'] == str(directory)
assert runtime['model'] == 'grok-4.6' and runtime['reasoning_effort'] == 'xhigh'
assert runtime['permission_mode'] == 'default' and runtime['max_turns'] == 64
args = [runtime['executable']['path'], '--model', 'grok-4.6',
        '--reasoning-effort', 'xhigh', '--permission-mode', 'default',
        '--no-plan', '--no-subagents', '--disable-web-search', '--no-auto-update',
        '--tools', 'read_file',
        '--disallowed-tools', 'search_replace,write,run_terminal_command,run_terminal_cmd,grep,list_dir,todo_write,web_search,web_fetch,Agent',
        '--deny', 'Edit', '--deny', 'Write', '--deny', 'Bash', '--deny', 'Grep',
        '--deny', 'MCPTool(*)', '--deny', 'WebFetch(*)', '--deny', 'WebSearch(*)',
        '--rules', 'Read only the 25 named prepared input files in the current input directory. Read all their content. Return exactly the two complete Python files in the required BEGIN_FILE format and an honest unrun-test brief. Do not request writes, shell, web, MCP or agents.',
        '--session-id', runtime['session_id'], '--max-turns', '64',
        '--output-format', 'plain', '--prompt-file', record['prompt']['path']]
env = dict(os.environ, GROK_DISABLE_AUTOUPDATER='1', GROK_MEMORY='0',
           GROK_WRITE_FILE='0', GROK_SUBAGENTS='0')
with Path(runtime['stdout']).open('xb') as stdout, Path(runtime['stderr']).open('xb') as stderr:
    os.dup2(stdout.fileno(), 1)
    os.dup2(stderr.fileno(), 2)
    os.chdir(directory)
    os.execve(args[0], args, env)
