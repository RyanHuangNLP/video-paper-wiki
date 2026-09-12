"""Independent semantic probes; requires a frozen, reviewed two-file candidate."""

import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).parent
R = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
candidate = json.loads((HERE / 'candidate-r1.json').read_text())
freeze_path = R / 'docs/ai/packets/full-todo-v1/CODE-PROOF-FOUNDATION-freeze-r1.json'
freeze_bytes = freeze_path.read_bytes()
assert hashlib.sha256(freeze_bytes).hexdigest() == '69e7073ea4f9ce69fb9f2dac890b253a69344a41c53aa35da6de5915c9fab8cc'
freeze = json.loads(freeze_bytes)
source = Path(candidate['source_root'])
assert source == Path(freeze['source_root'])
assert candidate['baseline_head'] == freeze['baseline_head']
expected = {row['relative_path']: row for row in freeze['baseline_tracked_files']}
assert {row['relative_path'] for row in candidate['product_paths']} == set(freeze['allowed_product_paths'])
expected.update({row['relative_path']: row for row in candidate['product_paths']})


def guard():
    for relative, row in expected.items():
        path = source / relative
        assert path.is_file() and not path.is_symlink(), relative
        data = path.read_bytes()
        assert len(data) == row['size_bytes'], relative
        assert hashlib.sha256(data).hexdigest() == row['sha256'], relative
    return len(expected)


before = guard()
sys.path.insert(0, str(source / 'src'))
m = importlib.import_module('video_paper_wiki.code_proof_resources')
assert Path(m.__file__) == source / 'src/video_paper_wiki/code_proof_resources.py'
retained = {}
for row in freeze['resource_pins']:
    relative = row['relative_path']
    logical = relative.removeprefix('src/video_paper_wiki/')
    retained[logical] = (source / relative).read_bytes()
context = m.compile_code_proof_resources(retained)
common_title = 'video-paper-wiki.code-proof-common.v1'
checks = []


def checked(name, action):
    action()
    checks.append(name)


def rejects(call, cls, reason):
    try:
        call()
    except cls as exc:
        assert exc.reason == reason
        prefix = 'resource' if cls is m.CodeProofResourceError else 'structure'
        assert str(exc) == f'CODE proof {prefix}: {reason}'
        assert 'SECRET_MARKER' not in str(exc)
    else:
        raise AssertionError('expected private boundary refusal')


def common_accepts(value):
    assert context.validate_structure(common_title, value) is None


deep = {}
cursor = deep
for _ in range(10000):
    child = {}
    cursor['child'] = child
    cursor = child
checked('common root permits deep acyclic JSON without a new depth cap', lambda: common_accepts(deep))
checked('common root permits an exact large integer without a new JCS range cap', lambda: common_accepts({'n': 10 ** 5000}))
shared = {'text': 'e\u0301'}
checked('acyclic sharing is accepted without Unicode normalization', lambda: common_accepts({'a': shared, 'b': shared}))
assert shared['text'] == 'e\u0301'
checked('definitions-only common schema accepts a preflight-valid list', lambda: common_accepts([]))

cyclic_list = []
cyclic_dict = {'child': cyclic_list}
cyclic_list.append(cyclic_dict)
checked('mixed list/dict cycle refuses', lambda: rejects(lambda: common_accepts(cyclic_dict), m.CodeProofStructureError, 'type'))


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class ListSubclass(list):
    pass


class DictSubclass(dict):
    pass


for index, bad in enumerate([1.0, float('nan'), float('inf'), StringSubclass('x'), IntegerSubclass(1), ListSubclass(), DictSubclass(), ('x',), b'x', {'\ud800': 1}, {'x': '\udfff'}, {1: 'x'}]):
    checked(f'exact JSON boundary negative {index}', lambda bad=bad: rejects(lambda: common_accepts({'payload': bad}), m.CodeProofStructureError, 'type'))


class UnsafeReason:
    def __eq__(self, other):
        raise RuntimeError('SECRET_MARKER equality must not run')

    def __hash__(self):
        raise RuntimeError('SECRET_MARKER hash must not run')

    def __str__(self):
        raise RuntimeError('SECRET_MARKER formatting must not run')


def invalid_reason(cls):
    try:
        cls(UnsafeReason())
    except ValueError as exc:
        assert str(exc) == 'Invalid CODE proof error reason'
    else:
        raise AssertionError('invalid reason did not refuse safely')


checked('resource error constructor never evaluates untrusted reason', lambda: invalid_reason(m.CodeProofResourceError))
checked('structure error constructor never evaluates untrusted reason', lambda: invalid_reason(m.CodeProofStructureError))

input_copy = dict(retained)
independent = m.compile_code_proof_resources(input_copy)
input_copy.clear()
checked('compiled context survives caller mapping mutation', lambda: independent.validate_structure(common_title, {}))
assert independent is not context
limits = context.materialize_limits(None)
expected_limits = copy.deepcopy(limits)
for group, values in expected_limits.items():
    for key, maximum in values.items():
        for good in (1, maximum):
            value = copy.deepcopy(expected_limits)
            value[group][key] = good
            actual = context.materialize_limits(value)
            assert actual == value and actual is not value
            assert all(actual[g] is not value[g] for g in value)
        for bad in (0, -1, True, False, 1.0, maximum + 1):
            value = copy.deepcopy(expected_limits)
            value[group][key] = bad
            rejects(lambda value=value: context.materialize_limits(value), m.CodeProofStructureError, 'limits')
        missing = copy.deepcopy(expected_limits)
        del missing[group][key]
        rejects(lambda missing=missing: context.materialize_limits(missing), m.CodeProofStructureError, 'limits')
        checks.append(f'limits exact 1/max and invalid boundaries {group}.{key}')
limits.clear()
assert context.materialize_limits(None) == expected_limits
checks.append('limits returned maps never mutate installed maxima')

for group, values in expected_limits.items():
    changed_group = {StringSubclass(g) if g == group else g: dict(v) for g, v in expected_limits.items()}
    rejects(lambda changed_group=changed_group: context.materialize_limits(changed_group), m.CodeProofStructureError, 'limits')
    for key in values:
        changed_key = copy.deepcopy(expected_limits)
        changed_key[group] = {StringSubclass(k) if k == key else k: v for k, v in values.items()}
        rejects(lambda changed_key=changed_key: context.materialize_limits(changed_key), m.CodeProofStructureError, 'limits')
        changed_value = copy.deepcopy(expected_limits)
        changed_value[group][key] = IntegerSubclass(values[key])
        rejects(lambda changed_value=changed_value: context.materialize_limits(changed_value), m.CodeProofStructureError, 'limits')
    checks.append(f'limits reject non-builtin key/value types throughout {group}')


class ArmedKey:
    def __init__(self):
        self.armed = False
        self.calls = []

    def __hash__(self):
        if self.armed:
            self.calls.append('hash')
            raise AssertionError('SECRET_MARKER hash must not run')
        return 1971

    def __eq__(self, other):
        if self.armed:
            self.calls.append('equality')
            raise AssertionError('SECRET_MARKER equality must not run')
        return self is other

    def __str__(self):
        self.calls.append('format')
        raise AssertionError('SECRET_MARKER formatting must not run')


for nested in (False, True):
    key = ArmedKey()
    changed = copy.deepcopy(expected_limits)
    if nested:
        changed['git'][key] = 1
    else:
        changed[key] = {}
    key.armed = True
    rejects(lambda changed=changed: context.materialize_limits(changed), m.CodeProofStructureError, 'limits')
    assert key.calls == []
    checks.append(f'limits refuse armed object key without invoking callbacks nested={nested}')

checked('public direct context construction refuses', lambda: rejects(lambda: m.CodeProofResources(), m.CodeProofResourceError, 'resource_shape'))
try:
    m.CodeProofResources(profile_sha256='SECRET_MARKER', resource_pins=(), validators={}, hard_limits={})
except TypeError:
    checks.append('caller cannot supply context validation configuration')
else:
    raise AssertionError('caller configuration bypass remains')
for property_name in ('profile_sha256', 'resource_pins'):
    try:
        setattr(context, property_name, 'SECRET_MARKER')
    except AttributeError:
        checks.append(f'context property remains read-only {property_name}')
    else:
        raise AssertionError('context public metadata is writable')

schemas = {json.loads(blob)['$id']: json.loads(blob) for key, blob in retained.items() if key.startswith('schemas/')}
common_id = 'https://video-paper-wiki.dev/schemas/video-paper-wiki.code-proof-common.v1.schema.json'
huge_pointer = copy.deepcopy(schemas)
huge_pointer[common_id]['probe_array'] = [{}]
huge_pointer[common_id]['$ref'] = '#/probe_array/' + '9' * 5000
checked('large impossible pointer index is a safe resource error', lambda: rejects(lambda: m._validate_schema_references(huge_pointer), m.CodeProofResourceError, 'resource_shape'))
for value in ({StringSubclass('x'): 1}, {'\ud800': 1}, {'x': '\udfff'}):
    changed = copy.deepcopy(schemas)
    changed[common_id]['probe'] = value
    checked('schema graph rejects non-builtin or surrogate nested data', lambda changed=changed: rejects(lambda: m._validate_schema_references(changed), m.CodeProofResourceError, 'resource_shape'))
shared_schema = {'plain': []}
changed = copy.deepcopy(schemas)
changed[common_id]['probe'] = [shared_schema, shared_schema]
checked('schema reference helper accepts shared acyclic anonymous graph', lambda: m._validate_schema_references(changed))
profile = json.loads(retained['profiles/code-proof-v1.json'])
for selector in ((), ('limits',), ('limits', 'git'), ('admission',), ('schemas', 0)):
    changed = copy.deepcopy(profile)
    target = changed
    for component in selector:
        target = target[component]
    key = next(iter(target))
    value = target.pop(key)
    target[StringSubclass(key)] = value
    checked('profile closed map rejects str-subclass key', lambda changed=changed: rejects(lambda: m._validate_profile_inventory(changed), m.CodeProofResourceError, 'resource_shape'))

bad_mapping = dict(retained)
first_key = sorted(bad_mapping)[0]
bad_mapping[first_key] = bad_mapping[first_key] + b'\n'
checked('resource bytes pin rejects before parse', lambda: rejects(lambda: m.compile_code_proof_resources(bad_mapping), m.CodeProofResourceError, 'resource_hash'))
for value in (DictSubclass(retained), list(retained.items()), {**retained, 'extra': b'{}\n'}, {StringSubclass(k): v for k, v in retained.items()}):
    checked('strict complete input mapping refuses', lambda value=value: rejects(lambda: m.compile_code_proof_resources(value), m.CodeProofResourceError, 'resource_shape'))

for malformed in (b'\xef\xbb\xbf{}\n', b'{"a":1,"a":2}\n', b'{"n":1.0}\n', b'{"n":NaN}\n', b'{"x":"\\ud800"}\n', b'{}\n\n', b'{} trailing', b'[]\n'):
    checked('strict private resource parser negative', lambda malformed=malformed: rejects(lambda: m._parse_resource_bytes(malformed), m.CodeProofResourceError, 'resource_shape'))

after = guard()
print(json.dumps({'decision': 'PASS_INDEPENDENT_FOUNDATION_SEMANTIC_PROBES', 'candidate_snapshot_sha256': candidate['snapshot_sha256'], 'python': sys.version, 'module': m.__file__, 'checks': checks, 'check_count': len(checks), 'files_verified_before': before, 'files_verified_after': after}, ensure_ascii=False))
