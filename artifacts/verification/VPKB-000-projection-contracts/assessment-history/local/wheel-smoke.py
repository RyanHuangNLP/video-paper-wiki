import copy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import video_paper_wiki
from video_paper_wiki.capture_contracts import capture_approval_hash, validate_capture_inspection
from video_paper_wiki.code_evidence_contracts import (
    code_proposal_hash, code_manifest_hash, code_snippet_sha256, code_text_metadata,
    normalize_code_bytes, validate_code_evidence_manifest, validate_code_capture_binding,
    validate_code_locator,
)
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.resources import schema_resource_names

root = Path('<REPO>')
assert not Path(video_paper_wiki.__file__).resolve().is_relative_to(root)
names = list(schema_resource_names())
assert len(names) == 18
for title in ('capture-inspection', 'code-evidence-manifest'):
    name = 'video-paper-wiki.' + title + '.v1'
    validate_document(json.loads((root / 'tests/fixtures/contracts/valid' / (name + '.json')).read_text()))

raw = b'a\n'
sha = '87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7'
proposal = {
    'schema': 'video-paper-wiki.code-evidence-manifest.v1', 'state': 'proposal',
    'origin': {'repository': 'Owner/Repo', 'commit': 'a' * 40, 'path': 'src/A.py'},
    'payload': {'sha256': sha, 'size_bytes': 2}, 'media_type': 'text/plain', 'encoding': 'utf-8',
    'line_canonicalization': 'utf8-lf-v1', 'newline_style': 'lf', 'ends_with_newline': True,
    'line_count': 1, 'normalized_sha256': sha,
    'proposal_sha256': '8f497138ddcdbbaaf2a4ea357ca52a490b37d890bc6e63d1fd4ca1dcd0194662',
}
assert code_proposal_hash(proposal) == proposal['proposal_sha256']
inspection = {
    'schema': 'video-paper-wiki.capture-inspection.v1', 'route': 'staged-capture',
    'media_type': 'text/plain', 'payload': copy.deepcopy(proposal['payload']), 'source_path': None,
    'proposal_sha256': proposal['proposal_sha256'], 'stored_path': f'.raw/captured/{sha}.bin',
    'source_identity': sha, 'siblings': [], 'would_change': True, 'operation_id': 'capture-001',
    'upstream_plan_sha256': 'b' * 64,
    'approval_hash': '25967b20d190cf27571c6e0a448b43b2c7c48dcd70ac940473aa1564cb660422',
}
assert capture_approval_hash(inspection) == inspection['approval_hash']
manifest = dict(proposal, state='inspected', capture={
    'stored_path': inspection['stored_path'], 'source_identity': sha, 'source_id': 'src:declared-001',
    'inspection_approval_hash': inspection['approval_hash'], 'operation_id': 'capture-001',
}, manifest_sha256='7e9e2a057aaaff0e5e418cb9cfbf1606fd19b690edc12fa4384f30da856c8ae6')
assert code_manifest_hash(manifest) == manifest['manifest_sha256']
validate_capture_inspection(inspection, payload=raw)
validate_code_evidence_manifest(manifest, payload=raw)
validate_code_capture_binding(manifest, inspection)
locator = dict(kind='code', source_id='src:declared-001', repository='owner/repo',
               commit='a' * 40, path='src/A.py', lines={'start': 1, 'end': 1},
               snippet_sha256='0' * 64)
# Valid digest syntax alone must not satisfy the byte-backed locator.
try:
    validate_code_locator(locator, manifest, raw)
except ContractError as exc:
    assert exc.code == 'CODE_LOCATOR_MISMATCH'
else:
    raise AssertionError('incorrect snippet digest accepted')
locator['snippet_sha256'] = 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb'
validate_code_locator(locator, manifest, raw)

cases = ranges = 0
for size in range(6):
    for parts in itertools.product(('a', '\n', '\r\n', 'β'), repeat=size):
        data = ''.join(parts).encode()
        expected = data.replace(b'\r\n', b'\n')
        lines = expected.split(b'\n') if expected else []
        if expected.endswith(b'\n'):
            lines.pop()
        assert normalize_code_bytes(data) == expected
        assert code_text_metadata(data)['line_count'] == len(lines)
        for start in range(1, len(lines) + 1):
            for end in range(start, len(lines) + 1):
                assert code_snippet_sha256(data, start, end) == hashlib.sha256(b'\n'.join(lines[start-1:end])).hexdigest()
                ranges += 1
        cases += 1
outside = subprocess.run(['<TMP>/vpkb-wheel-venv/bin/vpwiki', 'doctor'],
                         cwd='<TMP>', capture_output=True, text=True)
assert outside.returncode == 2
assert json.loads(outside.stdout)['error']['code'] == 'WORKSPACE_ROOT_INVALID'
with tempfile.TemporaryDirectory(prefix='vpc-wheel-', dir='<TMP>') as directory:
    workspace = Path(directory)
    (workspace / '.git').mkdir()
    (workspace / 'pyproject.toml').write_text('[project]\nname = "video-paper-wiki"\n')
    doctor = subprocess.run(['<TMP>/vpkb-wheel-venv/bin/vpwiki', 'doctor'],
                            cwd=workspace, capture_output=True, text=True, check=True)
    assert json.loads(doctor.stdout)['ok'] is True
print(json.dumps({'status': 'passed', 'python': sys.version.split()[0],
    'module_path': video_paper_wiki.__file__, 'schema_count': len(names),
    'golden_hash_graph': 'passed', 'locator_success_and_refusal': 'passed',
    'exhaustive_texts': cases, 'exhaustive_line_ranges': ranges,
    'doctor_exit_code': doctor.returncode, 'outside_workspace_refusal': 'WORKSPACE_ROOT_INVALID'}, ensure_ascii=False))

from video_paper_wiki.transaction_contracts import (
    validate_transaction, validate_operation_head, transaction_declaration_hash,
    attach_upstream_inspection, attach_runtime_result, verify_transaction_bytes,
)
from video_paper_wiki.jcs import canonicalize
transaction = json.loads((root / 'tests/fixtures/contracts/valid/video-paper-wiki.transaction-facade.v1.json').read_text())
assert transaction_declaration_hash(transaction) == 'a5aa140c16d78ab24d44f49577cff41ad138b9a3afc5d0c8ce5d49eda0626c7c'
validate_operation_head(transaction['head'])
assert validate_transaction(transaction) == transaction
paths = [w['path'] for w in transaction['writes']]
plan = {
    'schema':'claude-obsidian.transaction-plan.v1','operation_id':'genesis',
    'operation_type':'generic','valid':True,'changed_paths':paths,
    'hashes':{w['path']:w['sha256'] for w in transaction['writes']},
    'modes':{p:384 for p in paths},
    'input_bundle_sha256':transaction['input_bundle_sha256'],
    'expanded_bundle_sha256':transaction['input_bundle_sha256'],
    'vault_identity':{'state':'existing','device':1,'inode':2},
    'approval_sha256':'b'*64,
}
inspected = attach_upstream_inspection(transaction, plan)
result = {key:copy.deepcopy(plan[key]) for key in (
    'operation_id','operation_type','changed_paths','hashes','modes',
    'expanded_bundle_sha256','approval_sha256')}
result.update(schema='claude-obsidian.transaction-result.v1', status='complete',
              bundle_sha256=plan['input_bundle_sha256'])
completed = attach_runtime_result(inspected,result)
assert transaction['inspection'] is None and inspected['runtime_result'] is None
blobs = {paths[0]:b'{}', paths[1]:canonicalize(transaction['receipt']),
         paths[2]:canonicalize(transaction['head'])}
verify_transaction_bytes(completed,write_bytes=blobs,
                         original_bytes={p:None for p in paths},read_bytes={})
plan['modes'].clear(); result['hashes'].clear()
assert completed['runtime_result']['hashes'] and completed['inspection']['modes']
changed=copy.deepcopy(completed); changed['runtime_result']['changed_paths'].reverse()
try: validate_transaction(changed)
except ContractError as exc: assert exc.code=='TRANSACTION_UPSTREAM_MISMATCH'
else: raise AssertionError('wrong head ordering accepted')
changed_blobs=dict(blobs); changed_blobs[paths[1]] += b'\n'
try: verify_transaction_bytes(completed,write_bytes=changed_blobs,
                              original_bytes={p:None for p in paths},read_bytes={})
except ContractError as exc: assert exc.code=='TRANSACTION_BYTES_MISMATCH'
else: raise AssertionError('noncanonical receipt accepted')
print(json.dumps({'packet':'VPKB-000-transaction-facade','status':'passed',
    'schema_count':len(names),'known_declaration_hash':'passed','supplied_plan_result_correlations':'passed',
    'exact_receipt_head_bytes':'passed','ordering_and_byte_refusals':'passed','copy_isolation':'passed',
    'limitations':'Synthetic supplied evidence, not runtime execution/authentication or full historical-chain proof.'}))

import math
from video_paper_wiki.projection_runtime import (
    parse_projection_json, projection_value_bytes, projection_value_sha256,
    validate_runtime_record, runtime_projection_bytes, runtime_projection_equal,
    runtime_projection_sha256, markdown_projection_equal, PROFILE_TITLES,
)
values = {'null':None, 'true':True, 'one_int':1, 'one_float':1.0, 'zero_int':0,
 'negative_zero':-0.0, 'point_one':0.1, 'next_one':math.nextafter(1.0, math.inf),
 'k1':1.5, 'b':0.75, 'subnormal':float.fromhex('0x0.0000000000001p-1022'),
 'max_float':float.fromhex('0x1.fffffffffffffp+1023'), 'tag_like_array':['number',1,1],
 'utf16_order':{chr(0xe000):1,chr(0x10000):2}}
vectors = json.loads((root / 'tests/fixtures/projection-runtime/number-vectors.json').read_text())
for name, value in values.items():
    assert projection_value_bytes(value, profile=vectors['profile']) == vectors['vectors'][name]['canonical_utf8'].encode()
    assert projection_value_sha256(value, profile=vectors['profile']) == vectors['vectors'][name]['sha256']
fixture = Path('<TMP>/vpr-root-target2/test_pinned_public_rebuild_cjk0')
chunks = sorted((fixture / 'round-1/.vault-meta/chunks').glob('*/*.json'))
assert chunks
for path in chunks:
    document = parse_projection_json(path.read_bytes())
    validate_document(document, expected_schema=PROFILE_TITLES['chunk'])
    assert validate_runtime_record('chunk', document) == document
    changed = copy.deepcopy(document); changed['created_at'] = '2026-09-02T00:00:00Z'
    assert runtime_projection_equal('chunk', document, changed)
    assert runtime_projection_sha256('chunk', document) == hashlib.sha256(runtime_projection_bytes('chunk', document)).hexdigest()
index = parse_projection_json((fixture / 'round-1/index.json').read_bytes())
assert validate_document(index, expected_schema=PROFILE_TITLES['bm25']) == index
assert runtime_projection_equal('bm25', index, parse_projection_json((fixture / 'round-2/index.json').read_bytes()))
changed = copy.deepcopy(index); changed['params']['b'] = math.nextafter(changed['params']['b'], math.inf)
assert not runtime_projection_equal('bm25', index, changed)
changed = copy.deepcopy(index); changed['extra'] = 1
try: validate_runtime_record('bm25', changed)
except ContractError as exc: assert exc.code == 'RUNTIME_PROFILE_INVALID'
else: raise AssertionError('upstream extension silently accepted')
assert markdown_projection_equal(b'x', b'x') and not markdown_projection_equal(b'x', b'x\n')
print(json.dumps({'packet':'VPKB-000-projection-contracts', 'slice':'runtime', 'status':'passed',
    'schema_count':len(names), 'independent_vectors':14, 'actual_fixture_chunks':len(chunks),
    'actual_fixture_bm25_docs':index['doc_count'], 'module_path':video_paper_wiki.__file__,
    'limitations':'Installed package validates supplied fixture bytes; no production builder/SQLite/complete inventory validator or human acceptance.'}))

from video_paper_wiki.ledger_locator import (
    encode_ledger_locator, decode_ledger_locator,
    encode_ledger_evidence, decode_ledger_evidence,
)
from video_paper_wiki.identity import evidence_fingerprint
locator_vectors_path = Path('<TMP>/vpl-steward-vectors.json')
assert hashlib.sha256(locator_vectors_path.read_bytes()).hexdigest() == '4cb4fac91a9df6746daaa79b93be8dfa839f06c9111fd09ed1acb4ec534d5c16'
locator_vectors = json.loads(locator_vectors_path.read_text())
for vector in locator_vectors['valid_vectors']:
    original = vector['input_locator']
    before = copy.deepcopy(original)
    wire = encode_ledger_locator(original)
    assert wire == vector['expected_wire']
    assert hashlib.sha256(wire.encode()).hexdigest() == vector['wire_sha256']
    restored = decode_ledger_locator(wire)
    assert restored == vector['expected_decoded_locator']
    assert encode_ledger_locator(restored) == wire
    for relation, upstream in locator_vectors['relation_map'].items():
        domain = dict(original, relation=relation)
        encoded = encode_ledger_evidence(domain)
        assert encoded == {'source_id':original['source_id'], 'relation':upstream, 'locator':wire}
        decoded = decode_ledger_evidence(encoded)
        assert decoded == dict(vector['expected_decoded_locator'], relation=relation)
        assert evidence_fingerprint([decoded]) == vector['evidence_fingerprints'][relation]
    if 'bbox' in restored: restored['bbox'][0] = 777
    if 'lines' in restored: restored['lines']['start'] = 777
    assert original == before
for vector in locator_vectors['invalid_wire_vectors']:
    try: decode_ledger_locator(vector['wire'])
    except ContractError as exc:
        assert exc.code == vector['code'], vector['name']
        if vector.get('pointer') is not None:
            assert exc.details['instance_pointer'] == vector['pointer'], vector['name']
    else: raise AssertionError('invalid wire accepted: '+vector['name'])
print(json.dumps({'packet':'VPKB-000-projection-contracts', 'slice':'ledger-locator', 'status':'passed',
    'independent_positive_vectors':len(locator_vectors['valid_vectors']),
    'independent_negative_vectors':len(locator_vectors['invalid_wire_vectors']),
    'relations':3, 'schema_count':len(names), 'module_path':video_paper_wiki.__file__,
    'limitations':'Pure supplied-data codec only; not complete inventory, real coordinates, SQLite, adapter or human acceptance.'}))

from video_paper_wiki.assessment_history import derive_assessment_heads
history_vectors_path = Path('<TMP>/vph-steward-vectors.json')
assert hashlib.sha256(history_vectors_path.read_bytes()).hexdigest() == '43b38f50b725a98ac3d265124c946cbc18d8100bc9d78cb7666e79896fcbbe40'
history_vectors = json.loads(history_vectors_path.read_text())
for vector in history_vectors['positive']:
    supplied = copy.deepcopy(vector['input'])
    before = copy.deepcopy(supplied)
    heads = derive_assessment_heads(**supplied)
    assert heads == vector['expected_heads'], vector['name']
    assert type(heads) is dict and list(heads) == sorted(heads)
    assert supplied == before, vector['name']
    reverse = {'claims':list(reversed(supplied['claims'])), 'events':list(reversed(supplied['events']))}
    assert derive_assessment_heads(**reverse) == vector['expected_heads'], vector['name']
    heads.clear()
    assert derive_assessment_heads(**supplied) == vector['expected_heads'], vector['name']
for vector in history_vectors['negative']:
    try: derive_assessment_heads(**vector['input'])
    except ContractError as exc:
        assert exc.code == vector['expected_error'], (vector['name'], exc.code)
        assert exc.exit_code == vector['exit_code'], vector['name']
    else: raise AssertionError('invalid history accepted: '+vector['name'])
print(json.dumps({'packet':'VPKB-000-projection-contracts', 'slice':'assessment-history', 'status':'passed',
    'independent_positive_vectors':len(history_vectors['positive']),
    'independent_negative_vectors':len(history_vectors['negative']),
    'schema_count':len(names), 'module_path':video_paper_wiki.__file__,
    'limitations':'Pure supplied history consistency only; no actual human authorization, Vault membership, source/artifact closure or transaction integrity.'}))
