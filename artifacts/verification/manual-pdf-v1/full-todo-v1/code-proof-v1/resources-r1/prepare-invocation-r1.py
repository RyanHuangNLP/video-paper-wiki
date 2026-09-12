"""Prepare a bounded, hash-pinned resource request; never launch a model."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
P = ROOT / 'docs/ai/packets/full-todo-v1'
E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1'
OUT = E / 'resources-r1'
SOURCE = ROOT / '.work/parallel/code-proof-v1/terminal-1/source'
HEAD = '4ab1830939cd41981983909763434d5612df6070'
TREE = '22fc77a38704386eaad5ad9be8a9268f0a1a5392'
ZERO = '0' * 64
FREEZE = P / 'CODE-PROOF-RESOURCE-freeze-r1.json'
PROMPT = P / 'GROK-CODE-PROOF-RESOURCE-GENERATE-R1.md'
CONTRACTS = (
    'CODE-PROOF-DESIGN-R2.md', 'CODE-PROOF-CLOSURE-R3.md',
    'CODE-PROOF-IDENTITY-LAYOUT-R4.md', 'CODE-PROOF-STATE-AND-INSTALL-R5.md',
    'CODE-PROOF-RETAINED-IO-R6.md', 'CODE-PROOF-WIRE-R7.md',
    'CODE-PROOF-RETAINED-CLARIFICATIONS-R8.md', 'CODE-PROOF-PUBLIC-CLOSURE-R9.md',
    'CODE-PROOF-INPUT-CAPS-R10.md', 'CODE-PROOF-CAP-DISPOSITION-R11.md',
    'CODE-PROOF-RESOURCE-CONTRACT-R12.md',
    'CODE-GIT-KERNEL-R1.md', 'CODE-GIT-KERNEL-CLARIFICATIONS-R2.md',
    'CODE-CONFIG-KERNEL-R1.md', 'CODE-CONFIG-CLARIFICATIONS-R2.md',
    'CODE-CONFIG-ORACLE-CLARIFICATIONS-R3.md',
    'CODE-PROOF-RESOURCE-GENERATION-PLAN-R1.md',
    'CODE-PROOF-RESOURCE-OUTPUT-CONTRACT-R1.md',
    'CODE-PROOF-RESOURCE-INTERFACE-FACTS-R1.md',
)
KINDS = (
    'code-proof-common', 'code-proof-request-input', 'code-proof-observe-input',
    'code-proof-command-result', 'code-proof-request', 'code-git-bundle',
    'code-acquisition-intent', 'code-proof-observation', 'code-config-evidence',
    'code-source-handoff',
)


def ref(path, allow_symlink=False):
    assert path.is_file() and (allow_symlink or not path.is_symlink()), path
    raw = path.read_bytes()
    return {'path': str(path), 'size_bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def emit(path, value):
    data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if path.exists():
        assert not path.is_symlink() and path.read_bytes() == data, path
        return ref(path)
    with path.open('xb') as handle:
        handle.write(data)
    return ref(path)


def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()


def fixture_rows(directory):
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    assert manifest['profile_sha256'] == ZERO
    pins = {}

    def collect(value):
        if isinstance(value, dict):
            if {'path', 'size_bytes', 'sha256'} <= value.keys():
                path = value['path']
                if path in pins:
                    assert (pins[path]['sha256'], pins[path]['size_bytes']) == (
                        value['sha256'], value['size_bytes'])
                pins[path] = value
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(manifest)
    result = []
    for path, pin in sorted(pins.items()):
        assert not Path(path).is_absolute() and '..' not in Path(path).parts
        actual = ref(directory / path)
        assert actual['sha256'] == pin['sha256'] and actual['size_bytes'] == pin['size_bytes']
        if not path.endswith('.json'):
            continue
        value = json.loads((directory / path).read_bytes())
        if path.startswith('saved/'):
            title = value['schema']
        elif path.startswith('success-data/'):
            title = 'video-paper-wiki.code-proof-command-result.v1'
        elif path.startswith('inputs/') and ('request-input' in Path(path).name):
            title = 'video-paper-wiki.code-proof-request-input.v1'
        elif path.startswith('inputs/') and ('observe-input' in Path(path).name):
            title = 'video-paper-wiki.code-proof-observe-input.v1'
        else:
            raise AssertionError(path)
        result.append({'path': path, 'title': title, 'instance': value, 'pin': actual})
    return result


assert not FREEZE.exists()
assert git('rev-parse', 'HEAD') == HEAD
assert git('rev-parse', 'HEAD^{tree}') == TREE
assert not git('status', '--porcelain')
tracked = subprocess.check_output(['git', '-C', str(SOURCE), 'ls-files', '-z']).decode().split('\0')[:-1]
staged = subprocess.check_output(['git', '-C', str(SOURCE), 'ls-files', '--stage', '-z']).decode().split('\0')[:-1]
gitlinks = []
for row in staged:
    metadata, path = row.split('\t', 1)
    mode, oid, stage = metadata.split()
    assert stage == '0'
    if mode == '160000':
        directory = SOURCE / path
        assert directory.is_dir() and not directory.is_symlink() and not list(directory.iterdir())
        gitlinks.append({'relative_path': path, 'mode': mode, 'oid': oid,
                         'physical_state': 'uninitialized_empty_directory'})
    else:
        assert mode in ('100644', '100755'), (mode, path)
tracked = [path for path in tracked if path not in {row['relative_path'] for row in gitlinks}]
baseline = [dict(relative_path=p, **ref(SOURCE / p)) for p in sorted(tracked)]
source_tests = [row for row in baseline if row['relative_path'].startswith(('src/', 'tests/'))]
old_schemas = [row for row in baseline if row['relative_path'].startswith('schemas/') and row['relative_path'].endswith('.schema.json')]
assert len(source_tests) == 564 and len(old_schemas) == 71
resources = [f'schemas/video-paper-wiki.{kind}.v1.schema.json' for kind in KINDS]
resources.append('src/video_paper_wiki/profiles/code-proof-v1.json')
new_paths = resources + ['tests/contract/test_code_proof_resources.py', 'tests/fixtures/code-proof-resource-v1.json']
for path in new_paths:
    assert not (SOURCE / path).exists() and not (SOURCE / path).is_symlink()
count_path = SOURCE / 'tests/contract/test_schemas.py'
assert count_path.read_text().count('assert len(schema_paths) == 71') == 1
acceptance = ref(E / 'config-r1/architect-exact-local-head-acceptance-r5.json')
assert acceptance['sha256'] == 'd0533c40e7a87f65bc6819d0e94cb3fcd96f687c806ad6c77462e47c4993fae8'
reviews = [ref(E / name) for name in (
    'kernel-r1/architect-exact-local-head-acceptance-r8.json',
    'architect-resource-fixture-review-r3.json', 'architect-typed-fixture-review-r2.json',
    'resource-generation-plan-review-r1.json', 'resource-output-review-errata-r2.json',
    'resource-interface-facts-review-r1.json', 'public-resource-negative-errata-review-r3.json',
    'resources-r1/legacy-value-facts-r1.provenance.json',
    'resources-r1/architect-legacy-value-facts-review-r1.json',
    'resources-r1/fixture-packing-r1/architect-packer-review-r1.json',
)]
base = fixture_rows(E / 'resource-fixtures-r3')
typed = fixture_rows(E / 'resource-fixtures-typed-r2')
assert len(base) == 82 and len(typed) == 182
selected_typed = [row for row in typed if row['path'].startswith('saved/') and row['path'].endswith('-sha1/config.json')]
assert len(selected_typed) == 7
selected = []
inventory = []
for group, rows in [('base', base), ('typed', typed)]:
    for row in rows:
        name = group + '/' + row['path']
        inventory.append({'name': name, 'title': row['title'], 'sha256': row['pin']['sha256'], 'size_bytes': row['pin']['size_bytes'], 'transmitted_instance': group == 'base' or row in selected_typed})
        if group == 'base' or row in selected_typed:
            selected.append({'name': name, 'title': row['title'], 'instance': row['instance']})
selected.sort(key=lambda row: row['name'])
inventory.sort(key=lambda row: row['name'])
assert len(selected) == 89 and len(inventory) == 264
examples = emit(OUT / 'selected-positive-examples-r1.json', {
    'schema': 'video-paper-wiki.code-proof-resource-fixtures.v1',
    'profile_sha256': ZERO, 'cases': selected})
coverage = emit(OUT / 'positive-coverage-inventory-r1.json', {
    'schema': 'full-todo.code-resource-positive-inventory.v1', 'synthetic_only': True,
    'actual_public_workflow_execution': False, 'prepared_profile_sha256': ZERO,
    'case_count': 264, 'transmitted_instance_count': 89, 'cases': inventory})
directory = Path(tempfile.mkdtemp(prefix='grok-resources-r1-', dir='/private/tmp'))
originals = [P / name for name in CONTRACTS] + [
    E / 'public-resource-negative-cases-r2.json',
    E / 'public-resource-negative-case-errata-r3.md',
    OUT / 'legacy-value-facts-r1.md', Path(examples['path']), Path(coverage['path'])]
inputs = []
for original in originals:
    target = directory / original.name
    with target.open('xb') as handle:
        handle.write(original.read_bytes())
    inputs.append({'original': ref(original), 'copy': ref(target)})
descriptor = emit(directory / 'invocation-inputs.json', {
    'schema': 'full-todo.code-resource-generation-inputs.v1',
    'baseline_head': HEAD, 'baseline_tree': TREE,
    'config_acceptance_sha256': acceptance['sha256'],
    'preparation_review_sha256s': [row['sha256'] for row in reviews],
    'input_files': [{'name': Path(row['copy']['path']).name, 'size_bytes': row['copy']['size_bytes'], 'sha256': row['copy']['sha256']} for row in inputs],
    'all_named_files_must_be_read': True,
    'local_only_material': 'Full source and test preimages, whole fixture generators and 175 unselected positive instances are not provided to the model. Only named copies and the separate prompt are model inputs.',
    'sample_scope': {'synthetic_only': True, 'base_instances': 82, 'typed_sha1_config_instances': 7, 'complete_local_bundle_case_count': 264, 'placeholder_profile': ZERO},
    'required_outputs': ['generate_code_proof_resources.py', 'tests/contract/test_code_proof_resources.py'],
})
runtime = json.loads((P / 'CODE-CONFIG-KERNEL-freeze-r1.json').read_bytes())['runtime']
binary = ref(Path(runtime['executable']['path']), allow_symlink=True)
assert binary == runtime['executable']
record = {
    'schema': 'full-todo.code-proof-resource-generation-freeze.v1', 'revision': 1,
    'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'FROZEN_PENDING_INDEPENDENT_DISPATCH_REVIEW',
    'source_root': str(SOURCE), 'baseline_head': HEAD, 'baseline_tree': TREE,
    'config_exact_local_acceptance': acceptance, 'preparation_reviews': reviews,
    'preparation_script': ref(Path(__file__).resolve()),
    'local_fixture_inputs': [ref(E / name) for name in (
        'resource-fixtures-r3/generate_resource_fixtures.py',
        'resource-fixtures-r3/manifest.json',
        'resource-fixtures-typed-r1/generate_typed_fixtures.py',
        'resource-fixtures-typed-r2/manifest.json',
        'config-r1/static-vectors-r4.json',
        'resources-r1/fixture-packing-r1/pack_resource_fixtures.py',
        'resources-r1/fixture-packing-r1/packed-zero-r1.json',
    )],
    'prompt': ref(PROMPT), 'input_directory': str(directory), 'semantic_inputs': inputs,
    'input_descriptor': descriptor, 'baseline_tracked_files': baseline,
    'baseline_gitlinks': gitlinks,
    'baseline_tracked_snapshot_sha256': hashlib.sha256(json.dumps(baseline, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    'baseline_source_test_count': len(source_tests), 'old_schema_files': old_schemas,
    'source_writes_stopped': True, 'source_clean': True,
    'allowed_product_paths': new_paths + ['tests/contract/test_schemas.py'],
    'initially_absent_paths': new_paths, 'resource_paths': resources,
    'existing_count_test': ref(count_path),
    'mechanical_integration_amendment': {
        'product_authorship': 'Grok alone authors full resources through its returned generator and new resource contract tests.',
        'coordinator_operations_after_independent_output_review': [
            'Execute reviewed generator only at a fresh absent local temporary output directory; verify all eleven resulting resources before installation.',
            'Rebuild base R3 and typed R1 generators against actual profile SHA under exact accepted-source/acceptance guards, preserving source-derived values and resealing all ce1 references.',
            'Use independently reviewed packer to form full 264-case bundle and mechanically copy it to the named new product fixture.',
            'Mechanically copy all eleven reviewed generated resources and exact Grok new test module into their named product paths.',
            'Change only assert len(schema_paths) == 71 to assert len(schema_paths) == 81 in the existing count test.',
            'Freeze all fourteen product paths after complete mechanical integration and before validation.'
        ], 'all_other_tracked_bytes_preserved': True,
    },
    'runtime': {
        'executable': binary, 'executable_realpath': ref(Path(binary['path']).resolve()),
        'observed_version': runtime['observed_version'],
        'model': 'grok-4.6', 'reasoning_effort': 'xhigh', 'permission_mode': 'default',
        'session_id': str(uuid.uuid4()), 'cwd': str(directory), 'tools': ['read_file'],
        'max_turns': 64, 'output_format': 'plain',
        'stdout': str(OUT / 'builder-resource-r1.stdout.log'),
        'stderr': str(OUT / 'builder-resource-r1.stderr.log'),
        'expected_model_service_destination': 'cli-chat-proxy.grok.com',
        'payload_scope': 'Exact prompt and 25 named prepared input files including descriptor; design contracts, required legacy value excerpts and synthetic fixtures may contain unpublished project implementation details.',
    },
    'model_input_file_count': len(inputs) + 1,
    'model_input_total_bytes_including_prompt': sum(row['copy']['size_bytes'] for row in inputs) + descriptor['size_bytes'] + ref(PROMPT)['size_bytes'],
    'validation_after_complete_candidate_freeze': [
        'Independent full generated-resource review, reference closure and exact byte/profile/hash inventory.',
        'All final positive fixtures and structural negatives with strict integer checker on both locked Pythons.',
        'Affected contract suites and full repository regression suites on locked Python 3.12 and 3.13.',
        'Independent wheel byte parity for all eleven generated resources and preservation of all 71 old schemas.'
    ],
    'resource_acceptance_completes_CODE': False,
    'actual_public_semantic_workflow_checks': 'Pending later public implementation.',
    'git_or_network_delivery_authorized': False, 'launch_authorized': False,
}
assert record['model_input_file_count'] == 25
assert git('rev-parse', 'HEAD') == HEAD and not git('status', '--porcelain')
assert baseline == [dict(relative_path=p, **ref(SOURCE / p)) for p in sorted(tracked)]
print(json.dumps({'freeze': emit(FREEZE, record), 'cwd': str(directory),
                  'session_id': record['runtime']['session_id'],
                  'payload_bytes': record['model_input_total_bytes_including_prompt']}, indent=2))
