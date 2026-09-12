from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

V = Path(__file__).resolve().parent
ROOT = V.parents[5]
SOURCE = ROOT / '.work/parallel/lightweight-workflow-v2/terminal-4/source'
F = V.parent / 'final-integration-r5'
OLD = V.parent / 'final-integration-r4'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads(p.read_text())
def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as stream:
        stream.write(json.dumps(data, indent=2) + '\n')
def record(p):
    return {'path': str(p), 'sha256': sha(p), 'size_bytes': p.stat().st_size}
manifest = read(V / 'source-manifest.json')
for row in manifest['files']:
    p = SOURCE / row['relative_path']
    assert sha(p) == row['sha256'] and p.stat().st_size == row['size_bytes']
full = read(V / 'full312installed-result.json')
target = read(V / 'target313-result.json')
assert full['returncode'] == target['returncode'] == 0
counts = {}
for mode, expected in [('full312installed', 2382), ('target313', 1)]:
    suite = ET.parse(V / (mode + '.xml')).getroot().find('testsuite')
    count = {name: int(suite.attrib[name]) for name in ('tests', 'failures', 'errors', 'skipped')}
    assert count == {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}, count
    result = read(V / (mode + '-result.json'))
    assert sha(V / (mode + '.log')) == result['log_sha256']
    counts[mode] = count
for version in ('312', '313'):
    assert read(V / ('native-smoke' + version + '.json'))['decision'] == 'PASS_NATIVE_INSTALLED_ENVIRONMENT_AND_EQUIVALENT_WORKFLOW_STATUS'
review = read(V / 'independent-review/final-verification-review.json')
assert 'GO' in json.dumps(review.get('decision', review.get('verdict', ''))), review.keys()
F.mkdir(exist_ok=False)
shutil.copyfile(V / 'source-manifest.json', F / 'source-manifest.json')
for row in manifest['files']:
    dest = F / 'files' / row['relative_path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / row['relative_path'], dest)
inputs = [V / name for name in ('local-integration-authorization.json', 'before312-result.json', 'before312.log', 'full312-result.json', 'missing-runtime-entrypoint-observation.json', 'full312installed-result.json', 'full312installed.log', 'full312installed.xml', 'target313-result.json', 'target313.log', 'target313.xml', 'runtime-setup-observation.json', 'native-smoke312.json', 'native-smoke313.json', 'native-installed-observation312.json', 'native-installed-observation313.json', 'native-dependency-proof.json', 'independent-review/post-fix-review.json', 'independent-review/final-verification-review.json')]
inputs += [OLD / 'ci-failure-observation-r1.json', OLD / 'architect-local-acceptance.json', V.parent / 'lane4-native-verification-r4/wheel-reuse-verification.json']
summary = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'source_manifest_sha256': sha(F / 'source-manifest.json'),
    'final_local_checks': counts, 'native_module_and_console_equivalence': {'python312': 'PASS', 'python313': 'PASS'},
    'native_dependencies': record(V / 'native-dependency-proof.json'), 'inputs': [record(p) for p in inputs],
    'history': 'R4 exact ca63bdeb failed both Python3.12 CI jobs. R5 before312 reproduced that error. First R5 full312 passed the fixed installed test but failed one runtime-entrypoint check; installing the current wheel into the temporary runtime corrected setup. All failed records are preserved.',
    'python313_full_suite': 'R4 local and CI historical passes only; R5 local verification is the changed installed test plus native checks. New exact-head four-job CI is still required.',
    'wheel': {'sha256': full['production_wheel_sha256'], 'unchanged_python_modules': 109, 'unchanged_schemas': 53, 'test_not_packaged': True},
    'evidence_custody': 'Records named in the delivery manifest are carried in Git; other raw historical, native and real-PDF records remain local protected inputs identified by exact hashes.'}
write(F / 'verification-summary.json', summary)
handoff = {'schema': 'lightweight-workflow-v2-architect-integration-candidate.v1', 'revision': 'architect-integration-r5',
    'created_at_utc': datetime.now(timezone.utc).isoformat(), 'producer': 'Architect permitted small test-only integration fix, independently reviewed by Luna; no external Cursor/Grok invocation for R5',
    'baseline_head': manifest['baseline_head'], 'delivery_baseline_head': manifest['delivery_baseline_head'],
    'contract_sha256': manifest['contract_sha256'], 'source_manifest_sha256': sha(F / 'source-manifest.json'), 'files': manifest['files'],
    'delta_from_r4': ['tests/research/test_light_workflow_installed.py'], 'change': 'Include the existing locked typing-extensions runtime dependency in the isolated wheel fixture only on Python below3.13.',
    'verification_summary': record(F / 'verification-summary.json'), 'source_stopped_writing': True, 'status': 'ready_for_architect',
    'architect_accepted': False, 'exact_head_ci_required': True, 'human_gates': 'unchanged/open'}
write(F / 'handoff.json', handoff)
shutil.copyfile(F / 'handoff.json', F / 'ready.json')
acceptance = {'schema': 'lightweight-workflow-v2-architect-local-acceptance.v1', 'observed_at_utc': datetime.now(timezone.utc).isoformat(),
    'decision': 'ACCEPTED_LIGHTWEIGHT_WORKFLOW_V2_LOCAL_INTEGRATION_R5_PENDING_EXACT_COMMIT_AND_CI',
    'baseline_head': manifest['baseline_head'], 'delivery_baseline_head': manifest['delivery_baseline_head'],
    'contract_sha256': manifest['contract_sha256'], 'source_manifest_sha256': sha(F / 'source-manifest.json'),
    'handoff_ready_sha256': sha(F / 'handoff.json'), 'path_count': 25, 'changed_product_paths_from_r4': 1,
    'final_local_checks': counts, 'native_dependencies': record(V / 'native-dependency-proof.json'),
    'independent_fix_review': record(V / 'independent-review/post-fix-review.json'), 'independent_verification_review': record(V / 'independent-review/final-verification-review.json'),
    'verification_summary': record(F / 'verification-summary.json'),
    'acceptance_scope': 'Three-line isolated installation fixture correction; existing production implementation, assertions, dependency lock, schemas and real-PDF artifacts unchanged.',
    'remaining_requirements': ['Exact serialized commit and draft PR95 update targeting integration', 'Fresh Linux/macOS x Python3.12/3.13 CI', 'Separate Architect exact-head post-CI acceptance'],
    'source_stopped_writing': True, 'external_model_invocation_for_this_test_fix': False, 'merge_authorized': False, 'human_gates_closed': False}
write(F / 'architect-local-acceptance.json', acceptance)
release = (OLD / 'release.md').read_text()
start = release.index('The product implementation combines')
end = release.index('The unchanged real-PDF trial')
replacement = '''The product implementation combines accepted T1 r3, T2 r4 and T3 r4 with T4 r3 CLI, documentation and tests. Architect made two small independently reviewed installation-test corrections: preserve observations from the original native virtual environment, and copy the locked `typing-extensions` dependency into that fixture when running Python below 3.13. Production code, assertions and dependency pins remain unchanged.

The first delivered head `ca63bdeb283dd3182db458d784909fed4c98bec5` failed the isolated-install test in both Python 3.12 CI jobs because the fixture omitted that conditional dependency; both Python 3.13 jobs passed. The failure record remains immutable. Revision 5 reproduces the original error and passes 2,382 tests on locked Python 3.12.14, plus the affected installed test on Python 3.13.13. Native module/console execution passes under both versions. The earlier full Python 3.13 results remain historical evidence; new exact-head CI must certify the current revision on all four jobs.

The offline wheel has SHA-256 `3b3f08e1e903b1abdfd21a9b141b557ffa237753670739b0e70877044aa08522`; all 109 packaged Python modules and 53 schemas match current source. Only an unpackaged test changed, so the same current wheel was reused. The native environments preserve actual executable, module-origin and schema observations outside the source checkout. Python 3.12 imports locked `typing-extensions 4.16.0`; Python 3.13 uses its standard library typing support.

'''
with (F / 'release.md').open('x') as stream:
    stream.write(release[:start] + replacement + release[end:])
payload = [('tests/research/test_light_workflow_installed.py', F / 'files/tests/research/test_light_workflow_installed.py'), ('docs/ai/releases/lightweight-workflow-v2.md', F / 'release.md')]
prefix = 'artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/release-r5/'
for name in ('source-manifest.json', 'handoff.json', 'architect-local-acceptance.json', 'verification-summary.json'):
    payload.append((prefix + name, F / name))
for name in ('full312installed-result.json', 'full312installed.log', 'target313-result.json', 'target313.log', 'native-dependency-proof.json', 'runtime-setup-observation.json', 'missing-runtime-entrypoint-observation.json', 'before312-result.json'):
    payload.append((prefix + name, V / name))
payload.extend([(prefix + 'independent-fix-review.json', V / 'independent-review/post-fix-review.json'), (prefix + 'independent-verification-review.json', V / 'independent-review/final-verification-review.json'), (prefix + 'r4-ci-failure-observation.json', OLD / 'ci-failure-observation-r1.json')])
files = []
for relative, origin in payload:
    dest = F / 'delivery-files' / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin, dest)
    files.append({'relative_path': relative, 'source_path': str(dest), 'sha256': sha(dest), 'size_bytes': dest.stat().st_size, 'kind': 'product-test-fix' if relative.startswith('tests/') else 'release-evidence'})
write(F / 'delivery-manifest.json', {'schema': 'lightweight-workflow-v2-exact-delivery-manifest.v1', 'baseline_head': manifest['delivery_baseline_head'],
    'target_existing_branch': 'integrate/manual-pdf-pipeline', 'target_pr': 95, 'target_base_ref': 'integration', 'observed_base_head': '08709894adfb20ec07e976783f0ba436d975b74f',
    'source_manifest_sha256': sha(F / 'source-manifest.json'), 'local_acceptance_sha256': sha(F / 'architect-local-acceptance.json'), 'allowlist_count': len(files), 'files': files,
    'source_write_frozen': True, 'include_unlisted_paths': False, 'preserve_release_r4': True, 'merge_authorized': False})
print(json.dumps({'delivery_manifest': record(F / 'delivery-manifest.json'), 'acceptance': record(F / 'architect-local-acceptance.json'), 'handoff': record(F / 'handoff.json'), 'allowlist_count': len(files)}))
