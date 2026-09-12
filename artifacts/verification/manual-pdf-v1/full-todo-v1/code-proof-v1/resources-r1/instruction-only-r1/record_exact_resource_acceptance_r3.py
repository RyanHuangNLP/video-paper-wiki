"""Bind reviewed local resource bytes and full tests to a delivered local commit."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

I = Path(__file__).parent
R = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
P = R / 'docs/ai/packets/full-todo-v1'
candidate = json.loads((I / 'fifteen-path-candidate-r2.json').read_text())
local = json.loads((I / 'architect-local-resource-acceptance-r3.json').read_text())
W = Path(candidate['source_root'])
head, tree, delivery_path = sys.argv[1:]
delivery_path = Path(delivery_path)
output = I / 'architect-exact-local-resource-acceptance-r3.json'
assert not output.exists()


def git(*args):
    return subprocess.check_output(['git', '-C', str(W), *args])


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


assert local['decision'] == 'PASSED_LOCAL_RESOURCE_PREREQUISITE_PENDING_EXACT_LOCAL_COMMIT'
assert local['candidate_snapshot_sha256'] == candidate['snapshot_sha256']
assert git('rev-parse', 'HEAD').decode().strip() == head
assert git('rev-parse', 'HEAD^{tree}').decode().strip() == tree
assert git('rev-parse', 'HEAD^').decode().strip() == candidate['baseline_head']
parents = git('rev-list', '--parents', '-n', '1', 'HEAD').decode().split()
assert parents == [head, candidate['baseline_head']]
assert git('branch', '--show-current').decode().strip() == 'codex/code-proof-v1'
assert not git('status', '--porcelain', '--untracked-files=all').strip()
assert not git('diff', '--cached', '--name-only').strip()
git('diff', '--check', 'HEAD^', 'HEAD')
paths = sorted(git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').decode().splitlines())
assert paths == sorted(row['relative_path'] for row in candidate['product_paths'])
freeze = json.loads((P / 'CODE-PROOF-RESOURCE-freeze-r1.json').read_text())
expected = {row['relative_path']: row for row in freeze['baseline_tracked_files']}
expected.update({row['relative_path']: row for row in candidate['product_paths']})
for relative_path, row in expected.items():
    path = W / relative_path
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    assert len(data) == row['size_bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
    blob = git('show', f'{head}:{relative_path}')
    assert blob == data, relative_path

record = {
    'schema': 'full-todo.code-resource-exact-local-acceptance.v3',
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'decision': 'ACCEPTED_CODE_PROOF_RESOURCE_PREREQUISITE_AT_EXACT_LOCAL_HEAD',
    'head': head,
    'tree': tree,
    'parents': parents[1:],
    'branch': 'codex/code-proof-v1',
    'source_root': str(W),
    'candidate_snapshot_sha256': candidate['snapshot_sha256'],
    'changed_product_paths': paths,
    'all_tracked_file_blobs_equal_reviewed_bytes': len(expected),
    'working_tree_and_index_clean': True,
    'resource_profile_sha256': candidate['resource_profile_sha256'],
    'full_regression_results': local['full_regressions'],
    'new_schemas': 10,
    'new_profile': 1,
    'all_schema_count': 81,
    'candidate': pin(I / 'fifteen-path-candidate-r2.json'),
    'local_acceptance': pin(I / 'architect-local-resource-acceptance-r3.json'),
    'steward_delivery': pin(delivery_path),
    'delivery_go': pin(I / 'architect-local-resource-delivery-go-r3.json'),
    'source_and_test_relationship': 'The committed file blobs equal the exact frozen bytes exercised by both full R3 suites; the source commit did not alter tested content.',
    'remote_ci_run': None,
    'remote_push_performed': False,
    'public_CODE_complete': False,
    'full_TODO_complete': False,
    'human_semantic_gates_closed': False,
    'next_authorized_preparation': 'Freeze the independently reviewed two-file private resource foundation against this exact local baseline; main implementation remains Grok instruction-only output.',
}
with output.open('x') as stream:
    stream.write(json.dumps(record, indent=2) + '\n')
print(json.dumps(pin(output)))
