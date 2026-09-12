"""Record local resource acceptance only after both actual full R3 passes."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

I = Path(__file__).parent
R = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
P = R / 'docs/ai/packets/full-todo-v1'
SNAPSHOT = '0499b45b6b4f40a3bb330dd6fa63687d1182db7dfebce3136f9e3f814aa6654f'
PROFILE = '650a6a51a1f08651d659262424577a90233649e4949bfc0cc4850d7a7777ee32'
OUT = I / 'architect-local-resource-acceptance-r3.json'
assert not OUT.exists()


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(name):
    return json.loads((I / name).read_text())


candidate = read('fifteen-path-candidate-r2.json')
assert candidate['snapshot_sha256'] == SNAPSHOT
rows = candidate['product_paths']
assert len(rows) == 15
assert hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == SNAPSHOT
freeze = json.loads((P / 'CODE-PROOF-RESOURCE-freeze-r1.json').read_text())
expected = {row['relative_path']: row for row in freeze['baseline_tracked_files']}
expected.update({row['relative_path']: row for row in rows})
for source in (candidate['source_root'], candidate['test_root']):
    for relative_path, row in expected.items():
        path = Path(source) / relative_path
        assert path.is_file() and not path.is_symlink(), str(path)
        actual = pin(path)
        assert actual['size_bytes'] == row['size_bytes'] and actual['sha256'] == row['sha256'], str(path)
    for rev, field in [('HEAD', 'baseline_head'), ('HEAD^{tree}', 'baseline_tree')]:
        assert subprocess.check_output(['git', '-C', source, 'rev-parse', rev], text=True).strip() == candidate[field]

full = {}
for tag in ('312', '313'):
    execution = read(f'full-r3-py{tag}.execution.json')
    assert execution['exit_code'] == 0
    assert execution['snapshot_sha256'] == SNAPSHOT
    assert execution['before']['source_and_mirror_unchanged'] and execution['after']['source_and_mirror_unchanged']
    assert execution['installed_wheel_unchanged']
    for channel in ('stdout', 'stderr'):
        assert pin(Path(execution[channel]['path'])) == execution[channel]
    assert execution['stderr']['size_bytes'] == 0
    text = Path(execution['stdout']['path']).read_text()
    assert '3782 passed' in text and '108 subtests passed' in text, text[-2000:]
    full[tag] = {
        'execution': pin(I / f'full-r3-py{tag}.execution.json'),
        'exit_code': 0,
        'passed': 3782,
        'subtests_passed': 108,
        'result': text.strip().splitlines()[-1],
        'actual_command': execution['command'],
        'fresh_wheel_hook_used': True,
    }
    audit = read(f'fixture-audit-{tag}.stdout.json')
    assert audit['fixture_cases'] == 264 and audit['resolved_references'] == 314
    assert audit['profile_sha256'] == PROFILE
    assert read(f'fixture-audit-{tag}.execution.json')['exit_code'] == 0
    boundaries = read(f'boundaries-{tag}.stdout.json')
    assert boundaries['check_count'] == 60 and boundaries['mismatch_count'] == 0
    directory = read(f'directory-scope-{tag}.stdout.json')
    assert directory['decision'] == 'PASS' and len(directory['checks']) == 6
    assert all(row['expected'] == row['actual'] for row in directory['checks'])

correction = read('I/wheel-environment-r3/wheel-ready-r3-correction-r1.json')
assert correction['candidate_snapshot_sha256'] == SNAPSHOT
assert correction['decision'] == 'PASS_TARGETED_INSTALLED_MODULE_REPLAY_BOTH_LOCKED_RUNTIMES'
assert all(row['exit_code'] == 0 for row in correction['targeted_replays'])
assert pin(Path(correction['wheel']['path'])) == correction['wheel']
assert read('I/fixture-identity-review-r1.json')['decision'] == 'GO_FOR_PACKED_FIXTURE_IDENTITY_ORIGIN_AND_INPUT_REVIEW'
assert read('I/local-delivery-preflight-r2.json')['decision'] == 'PASS_READ_ONLY_15_PATH_DELIVERY_PREFLIGHT'

evidence_names = [
    'fifteen-path-candidate-r2.json',
    'architect-fifteen-path-integration-go-r2.json',
    'architect-generation-go-r1.json',
    'I/steward-returned-test-review-r1.json',
    'I/fixture-identity-review-r1.json',
    'closure-integration-r1/controller-closure-integration-review-r1.json',
    'closure-integration-r1/architect-closure-probes-r1.json',
    'wheel-r1/installed-wheel-verification-r1.json',
    'I/wheel-environment-r3/wheel-ready-r3.json',
    'I/wheel-environment-r3/wheel-ready-r3-correction-r1.json',
    'I/local-delivery-preflight-r2.json',
    'architect-initial-full-regression-observation-r1.json',
    'architect-full-r2-environment-failure-r3.json',
    'run_full_regression_r3_ready.py',
]
for tag in ('312', '313'):
    evidence_names.extend([
        f'fixture-audit-{tag}.stdout.json', f'fixture-audit-{tag}.execution.json',
        f'boundaries-{tag}.stdout.json', f'boundaries-{tag}.execution.json',
        f'directory-scope-{tag}.stdout.json', f'directory-scope-{tag}.execution.json',
    ])
record = {
    'schema': 'full-todo.code-resource-local-acceptance.v3',
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'decision': 'PASSED_LOCAL_RESOURCE_PREREQUISITE_PENDING_EXACT_LOCAL_COMMIT',
    'candidate_snapshot_sha256': SNAPSHOT,
    'candidate_path_count': 15,
    'baseline_head': candidate['baseline_head'],
    'baseline_tree': candidate['baseline_tree'],
    'source_root': candidate['source_root'],
    'test_root': candidate['test_root'],
    'all_expected_files_guarded_both_roots': len(expected),
    'resource_profile_sha256': PROFILE,
    'new_schemas': 10,
    'existing_schemas_unchanged': 71,
    'new_profiles': 1,
    'structural_fixture_cases_each_python': 264,
    'reference_checks_each_python': 314,
    'independent_boundary_cases_each_python': 60,
    'directory_scope_cases_each_python': 6,
    'independent_focused_tests_each_python': 86,
    'full_regressions': full,
    'fresh_wheel': correction['wheel'],
    'evidence': [pin(I / name) for name in evidence_names],
    'limitations': [
        'Resource prerequisite only; private production loader, retained I/O and public five-command workflow remain pending.',
        'Structural validation and synthetic fixture identity review do not establish public semantic replay or real-source officiality.',
        'The original instruction-only Grok process returned code, but its actual exit code was not recovered; source acceptance uses reviewed bytes and real executions.',
        'Initial full R1 and R2 failures remain immutable; only actual full R3 exit-zero results support this local acceptance.',
        'No remote CI, public push, merge, main mutation, real Vault/admin action or human semantic approval is inferred.',
    ],
    'exact_local_commit_accepted': False,
    'remote_ci_passed_for_candidate': False,
    'public_CODE_complete': False,
    'full_TODO_complete': False,
}
with OUT.open('x') as stream:
    stream.write(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(pin(OUT)))
