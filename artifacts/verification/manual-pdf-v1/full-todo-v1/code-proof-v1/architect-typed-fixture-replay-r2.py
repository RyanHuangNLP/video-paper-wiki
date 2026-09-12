from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
WORK = ROOT / '.work/parallel/code-proof-v1/terminal-1/source'
EVIDENCE = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1'
CONFIG = EVIDENCE / 'config-r1'
GENERATOR = EVIDENCE / 'resource-fixtures-typed-r1/generate_typed_fixtures.py'
ORIGINAL = EVIDENCE / 'resource-fixtures-typed-r1/generated-r1'
ACCEPTANCE = CONFIG / 'architect-exact-local-head-acceptance-r5.json'
LABEL = sys.argv[1]
assert LABEL in ('py312', 'py313')
PROFILE = ('f' if LABEL == 'py312' else '0') * 64
OUTPUT = (Path(tempfile.mkdtemp(prefix='typed-r2-', dir='/private/tmp')) / 'generated'
          if LABEL == 'py312' else EVIDENCE / 'resource-fixtures-typed-r2')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    raw = path.read_bytes()
    return {'path': str(path), 'size_bytes': len(raw), 'sha256': sha(raw)}


acceptance = json.loads(ACCEPTANCE.read_bytes())
assert sha(ACCEPTANCE.read_bytes()) == 'd0533c40e7a87f65bc6819d0e94cb3fcd96f687c806ad6c77462e47c4993fae8'
assert sha(GENERATOR.read_bytes()) == '3b861aa0073a7a0f14ca9ca6325e32a791d465a9d0c3c4313fd16bb7b6491d46'
assert acceptance['decision'] == 'ACCEPTED_CODE_CONFIG_KERNEL_AT_EXACT_LOCAL_HEAD'
freeze = json.loads((ROOT / 'docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-freeze-r1.json').read_bytes())
candidate = json.loads((CONFIG / 'architect-stopped-candidate-r5.json').read_bytes())
source_refs = freeze['baseline_source_test_files'] + [
    dict(row, path=str(WORK / row['path'])) for row in candidate['candidate_files']
]


def check_source():
    for revision, expected in [('HEAD', acceptance['accepted_head']), ('HEAD^{tree}', acceptance['accepted_tree'])]:
        actual = subprocess.check_output(['git', '-C', str(WORK), 'rev-parse', revision], text=True).strip()
        assert actual == expected
    assert not subprocess.check_output(['git', '-C', str(WORK), 'status', '--porcelain'], text=True).strip()
    for row in source_refs:
        raw = Path(row['path']).read_bytes()
        assert len(raw) == row['size_bytes'] and sha(raw) == row['sha256'], row['path']


check_source()
sys.path.insert(0, str(WORK / 'src'))
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.code_git_objects import verify_code_git_objects, git_object_ids
from video_paper_wiki.code_config_parser import parse_code_config_bytes
from video_paper_wiki.code_evidence_contracts import code_text_metadata

vectors = {v['id']: v for v in json.loads((CONFIG / 'static-vectors-r4.json').read_bytes())['success_vectors']}
assert not OUTPUT.exists()
command = [sys.executable, '-I', '-B', str(GENERATOR), '--source-root', str(WORK),
           '--output-dir', str(OUTPUT), '--accepted-config-head', acceptance['accepted_head'],
           '--accepted-config-tree', acceptance['accepted_tree'],
           '--accepted-config-acceptance-sha256', sha(ACCEPTANCE.read_bytes()),
           '--profile-sha256', PROFILE]
run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
assert run.returncode == 0, run.stdout.decode()
manifest = json.loads((OUTPUT / 'manifest.json').read_bytes())
assert manifest['accepted_config'] == {
    'head': acceptance['accepted_head'], 'tree': acceptance['accepted_tree'],
    'acceptance_record_sha256': sha(ACCEPTANCE.read_bytes()),
}
assert len(manifest['cases']) == 14
reference_count = 0
file_count = 0
for case in manifest['cases']:
    base = OUTPUT / 'saved' / case['name']
    docs = {}
    by_id = {}
    instances = []
    for row in case['files']:
        raw = (OUTPUT / row['path']).read_bytes()
        assert len(raw) == row['size_bytes'] and sha(raw) == row['sha256']
        file_count += 1
        if row['path'].endswith('.json'):
            value = json.loads(raw)
            assert canonicalize(value) + b'\n' == raw
            instances.append(value)
            if 'id' in value and 'kind' in value:
                assert set(value) == {'schema', 'kind', 'id', 'data'}
                core = {k: value[k] for k in ('schema', 'kind', 'data')}
                assert value['id'] == 'ce1:' + value['kind'] + ':' + sha(canonicalize(core))
                docs[value['kind']] = value['data']
                by_id[value['id']] = sha(raw)
        prior = (ORIGINAL / row['path']).read_bytes()
        if LABEL == 'py313' or row['kind'] == 'raw-body' or row['kind'].startswith('input:'):
            assert raw == prior
        else:
            assert raw != prior
    request = docs['code-proof-request']
    bundle = docs['code-git-bundle']
    observation = docs['code-proof-observation']
    config = docs['code-config-evidence']
    handoff = docs['code-source-handoff']
    intent = docs['code-acquisition-intent']
    assert request['profile_sha256'] == PROFILE
    assert config['source_only_reason'] is None and config['format'] == case['format']
    bodies = {p.name[:-5]: p.read_bytes() for p in (base / 'objects').iterdir()}
    assert len(bodies) == 3
    for obj in bundle['objects']:
        raw = bodies[obj['oid']]
        assert len(raw) == obj['body_size_bytes']
        assert git_object_ids(request['object_format'], obj['object_type'], raw) == (
            obj['oid'], obj['body_sha256'], obj['framed_sha256'])
    raw = bodies[config['blob_oid']]
    vector = vectors[case['vector']]
    assert raw == vector['source_utf8'].encode('utf-8')
    parsed = parse_code_config_bytes(payload=raw, config_format=config['format'], limits=request['limits']['config'])
    assert parsed == config['result']
    assert parsed['source'] == vector['source'] and parsed['nodes'] == vector['expected_nodes']
    proof = verify_code_git_objects(
        object_format=request['object_format'], commit_oid=request['commit_oid'],
        root_tree_oid=bundle['root_tree_oid'], objects=bundle['objects'], bodies=bodies,
        targets=[{k: t[k] for k in ('path', 'allow_executable_source')} for t in request['targets']],
        limits=request['limits']['git'])
    assert proof == observation['git_proof'] and handoff['proof'] == proof['targets'][0]
    legacy = code_text_metadata(raw)
    metadata = observation['targets'][0]['text']
    assert {k: metadata[k] for k in legacy} == legacy
    assert metadata['normalized_size_bytes'] == len(raw.replace(b'\r\n', b'\n'))
    assert handoff['text'] == metadata
    logical_root = '.work/' + case['batch_id'] + '/code-evidence-v1'
    raw_ref = {'path': logical_root + '/objects/' + config['blob_oid'] + '.body',
               'size_bytes': len(raw), 'sha256': sha(raw)}
    assert config['raw_body'] == handoff['raw_body'] == raw_ref
    assert intent['bundle']['directory'] == '.work/' + case['batch_id'] + '/raw-input'

    def walk(value):
        global reference_count
        if isinstance(value, dict):
            if set(value) == {'id', 'sha256'}:
                assert by_id[value['id']] == value['sha256']
                reference_count += 1
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for value in instances:
        walk(value)
    ordinary = json.loads((OUTPUT / 'inputs' / (case['name'] + '-request-input.json')).read_bytes())
    assert 'profile_sha256' not in ordinary

before = {str(p.relative_to(OUTPUT)): sha(p.read_bytes()) for p in OUTPUT.rglob('*') if p.is_file()}
repeat = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
assert repeat.returncode != 0
assert before == {str(p.relative_to(OUTPUT)): sha(p.read_bytes()) for p in OUTPUT.rglob('*') if p.is_file()}
check_source()
record = {
    'schema': 'full-todo.typed-fixture-replay.v1', 'revision': 2, 'status': 'PASS',
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'label': LABEL, 'python': sys.version, 'output': str(OUTPUT),
    'manifest': ref(OUTPUT / 'manifest.json'), 'generator': ref(GENERATOR),
    'actual_config_acceptance': ref(ACCEPTANCE), 'cases': 14, 'fixture_files': file_count,
    'saved_envelopes': 84, 'references_verified': reference_count,
    'typed_parser_replays': 14, 'git_verifier_replays': 14, 'legacy_metadata_parity': 14,
    'profile_sha256': PROFILE, 'profile_binding_comparison_passed': True,
    'rerun_refusal_unchanged': True, 'source_references_unchanged': len(source_refs),
}
destination = EVIDENCE / ('architect-typed-fixture-' + LABEL + '-r2.json')
with destination.open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps(record, indent=2))
print(json.dumps(ref(destination)))
