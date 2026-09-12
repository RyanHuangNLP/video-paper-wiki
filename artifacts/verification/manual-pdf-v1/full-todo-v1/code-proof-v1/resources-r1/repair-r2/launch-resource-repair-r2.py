"""Launch the exact independently reviewed read-only resource repair once."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
FREEZE = ROOT / 'docs/ai/packets/full-todo-v1/CODE-PROOF-RESOURCE-repair-freeze-r2.json'
EXPECTED = '45ada8fe77b52cdff113bb697f1faf3c601f0b9ad9a19701ac26a6697360c60a'
E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resources-r1/repair-r2'


def check(ref, allow_symlink=False):
    path = Path(ref['path'])
    assert path.is_file() and (allow_symlink or not path.is_symlink()), path
    raw = path.read_bytes()
    assert len(raw) == ref['size_bytes'], path
    assert hashlib.sha256(raw).hexdigest() == ref['sha256'], path


assert __debug__, 'optimized Python is not permitted'
raw = FREEZE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
record = json.loads(raw)
go = json.loads((E / 'architect-resource-repair-dispatch-go-r2.json').read_bytes())
assert go['decision'] == 'GO_FOR_EXACT_RESOURCE_REPAIR_READ_ONLY_LAUNCH'
assert go['freeze']['sha256'] == EXPECTED
assert go['launcher']['path'] == str(Path(__file__).resolve())
for key in ('freeze', 'launcher', 'independent_review', 'patch_applier_review'):
    check(go[key])
for key in ('prior_resource_freeze', 'prior_returned_output_freeze', 'prior_rejection',
            'prior_boundary_review', 'prior_test_review', 'source_guard_reference',
            'user_resource_egress_authorization', 'packet', 'prompt',
            'input_descriptor', 'patch_applier', 'extended_boundary_probe',
            'extended_boundary_r1_results'):
    check(record[key])
prior = json.loads(Path(record['source_guard_reference']['path']).read_bytes())
for item in prior['baseline_tracked_files']:
    check(item)
for item in record['semantic_inputs']:
    check(item['original'])
    check(item['copy'])
source = Path(record['source_root'])


def git(*args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()


assert git('rev-parse', 'HEAD') == record['baseline_head']
assert git('rev-parse', 'HEAD^{tree}') == record['baseline_tree']
assert not git('status', '--porcelain', '--untracked-files=all')
for item in prior['baseline_gitlinks']:
    directory = source / item['relative_path']
    assert directory.is_dir() and not directory.is_symlink() and not list(directory.iterdir())
    assert git('ls-files', '--stage', '--', item['relative_path']) == (
        item['mode'] + ' ' + item['oid'] + ' 0\t' + item['relative_path'])
for path in record['initially_absent_paths']:
    target = source / path
    assert not target.exists() and not target.is_symlink()
directory = Path(record['input_directory'])
assert directory.is_dir() and not directory.is_symlink()
names = {Path(item['copy']['path']).name for item in record['semantic_inputs']}
names.add('invocation-inputs.json')
assert len(names) == record['model_input_file_count'] == 8
assert {item.name for item in directory.iterdir()} == names
assert all(item.is_file() and not item.is_symlink() for item in directory.iterdir())
runtime = record['runtime']
check(runtime['executable'], allow_symlink=True)
check(runtime['executable_realpath'])
assert str(Path(runtime['executable']['path']).resolve()) == runtime['executable_realpath']['path']
assert runtime['cwd'] == str(directory)
assert runtime['model'] == 'grok-4.6' and runtime['reasoning_effort'] == 'xhigh'
assert runtime['permission_mode'] == 'default' and runtime['max_turns'] == 64
assert runtime['session_id'] == '32086f3c-2d4a-45ac-a173-fb01cb643aa2'
args = [runtime['executable']['path'], '--model', 'grok-4.6',
        '--reasoning-effort', 'xhigh', '--permission-mode', 'default',
        '--no-plan', '--no-subagents', '--disable-web-search', '--no-auto-update',
        '--tools', 'read_file',
        '--disallowed-tools', 'search_replace,write,run_terminal_command,run_terminal_cmd,grep,list_dir,todo_write,web_search,web_fetch,Agent',
        '--deny', 'Edit', '--deny', 'Write', '--deny', 'Bash', '--deny', 'Grep',
        '--deny', 'MCPTool(*)', '--deny', 'WebFetch(*)', '--deny', 'WebSearch(*)',
        '--rules', 'Read only the eight named prepared input files in the current input directory, all of them. Return exactly one BEGIN_PATCH code-resource-r2 block containing the declarative exact-text JSON patch and honest unrun-test brief required by R2. Do not request writes, shell, web, MCP or agents.',
        '--session-id', runtime['session_id'], '--max-turns', '64',
        '--output-format', 'plain', '--prompt-file', record['prompt']['path']]
env = dict(os.environ, GROK_DISABLE_AUTOUPDATER='1', GROK_MEMORY='0',
           GROK_WRITE_FILE='0', GROK_SUBAGENTS='0')
with Path(runtime['stdout']).open('xb') as stdout, Path(runtime['stderr']).open('xb') as stderr:
    os.dup2(stdout.fileno(), 1)
    os.dup2(stderr.fileno(), 2)
    os.chdir(directory)
    os.execve(args[0], args, env)
