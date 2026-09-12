"""Cross-check fixture value spans against independent stdlib parsed subtrees."""
import decimal
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'
path = E / 'static-vectors-r1.json'
raw = path.read_bytes()
fixture = json.loads(raw)
findings = []
count = 0

def exact(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is decimal.Decimal:
        return a.as_tuple() == b.as_tuple()
    return a == b

for case in fixture['success_vectors']:
    source = case['source_utf8']
    body = source.encode()
    complete = (json.loads(source, parse_float=decimal.Decimal) if case['format'] == 'json'
                else tomllib.loads(source, parse_float=decimal.Decimal))
    assert hashlib.sha256(body).hexdigest() == case['source']['body_sha256']
    assert len(body) == case['source']['body_size_bytes']
    for node in case['expected_nodes']:
        expected = complete
        if node['path']:
            for escaped in node['path'][1:].split('/'):
                part = escaped.replace('~1', '/').replace('~0', '~')
                expected = expected[int(part)] if type(expected) is list else expected[part]
        span = node['value_span']
        if span is None:
            continue
        count += 1
        subset = body[span['byte_start']:span['byte_end']]
        row = {'vector': case['id'], 'path': node['path'], 'byte_start': span['byte_start'], 'byte_end': span['byte_end']}
        try:
            value = (json.loads(subset, parse_float=decimal.Decimal) if case['format'] == 'json'
                     else tomllib.loads('value = ' + subset.decode(), parse_float=decimal.Decimal)['value'])
        except (ValueError, UnicodeError) as error:
            findings.append({**row, 'condition': 'value span is not one complete parseable value', 'exception_type': type(error).__name__})
        else:
            if not exact(value, expected):
                findings.append({**row, 'condition': 'value span parses to a different typed subtree than its exact path'})
        if source[span['codepoint_start']:span['codepoint_end']].encode() != subset:
            findings.append({**row, 'condition': 'byte and codepoint slices differ'})

record = {'schema': 'full-todo.code-config-architect-span-review.v1', 'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'fixture_size_bytes': len(raw), 'production_imported': False, 'vectors_checked': len(fixture['success_vectors']), 'value_spans_checked': count, 'findings': findings, 'decision': 'REJECTED_STATIC_FIXTURE_VALUE_SPANS' if findings else 'PASS_STATIC_VALUE_SPAN_SUBTREES_ONLY'}
(E / 'architect-span-review-r1.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
sys.exit(1 if findings else 0)
