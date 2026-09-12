"""Independent full-source/path/span replay of corrected static config goldens."""
import decimal
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
W = ROOT / '.work/parallel/code-proof-v1/terminal-1/source'
sys.path.insert(0, str(W / 'src'))
from video_paper_wiki.code_evidence_contracts import code_snippet_sha256, code_text_metadata

E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'
fixture_path = E / 'static-vectors-r2.json'
raw = fixture_path.read_bytes()
fixture = json.loads(raw)
counts = {'vectors': 0, 'nodes': 0, 'value_spans': 0, 'declarations': 0}

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

def pointer(base, key):
    return base + '/' + str(key).replace('~', '~0').replace('/', '~1')

def flattened(value, base=''):
    result = [(base, value)]
    keys = sorted(value, key=lambda s: s.encode()) if type(value) is dict else range(len(value)) if type(value) is list else []
    for key in keys:
        result.extend(flattened(value[key], pointer(base, key)))
    return result

def number(value):
    if type(value) is int:
        return str(value)
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text

for case in fixture['success_vectors']:
    counts['vectors'] += 1
    source = case['source_utf8']
    body = source.encode()
    expected_source = {'body_size_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(), **code_text_metadata(body)}
    assert case['source'] == expected_source, case['id']
    complete = (json.loads(source, parse_float=decimal.Decimal) if case['format'] == 'json'
                else tomllib.loads(source, parse_float=decimal.Decimal))
    rows = flattened(complete)
    assert [node['path'] for node in case['expected_nodes']] == [p for p, _ in rows], case['id']
    by_path = {n['path']: n for n in case['expected_nodes']}

    def check_span(span):
        a, b = span['codepoint_start'], span['codepoint_end']
        assert 0 <= a < b <= len(source)
        assert span['byte_start'] == len(source[:a].encode())
        assert span['byte_end'] == len(source[:b].encode())
        for pos, suffix in ((a, 'start'), (b, 'end')):
            assert not (pos > 0 and pos < len(source) and source[pos - 1:pos + 1] == '\r\n')
            before = source[:pos]
            assert span['line_' + suffix] == before.count('\n') + 1
            assert span['column_' + suffix] == pos - before.rfind('\n')
        selected = source[a:b].encode()
        assert span['raw_sha256'] == hashlib.sha256(selected).hexdigest()
        last_line = span['line_end'] - (span['column_end'] == 1 and span['line_end'] > span['line_start'])
        assert span['snippet_sha256'] == code_snippet_sha256(body, span['line_start'], last_line)
        return selected

    for node, (path, value) in zip(case['expected_nodes'], rows):
        counts['nodes'] += 1
        kind = {dict: 'object', list: 'array', str: 'string', int: 'integer', decimal.Decimal: 'decimal', bool: 'boolean', type(None): 'null'}[type(value)]
        assert node['kind'] == kind, (case['id'], path, 'kind')
        expected_value = None if kind in ('object', 'array') else number(value) if kind in ('integer', 'decimal') else value
        assert type(node['value']) is type(expected_value) and node['value'] == expected_value, (case['id'], path, 'value')
        keys = sorted(value, key=lambda s: s.encode()) if type(value) is dict else range(len(value)) if type(value) is list else []
        assert node['children'] == [pointer(path, key) for key in keys]
        span = node['value_span']
        if span is not None:
            counts['value_spans'] += 1
            selected = check_span(span)
            parsed = (json.loads(selected, parse_float=decimal.Decimal) if case['format'] == 'json'
                      else tomllib.loads('value = ' + selected.decode(), parse_float=decimal.Decimal)['value'])
            assert exact(parsed, value), (case['id'], path, 'span subtree')
            if kind in ('integer', 'decimal'):
                assert node['numeric_lexeme'] == selected.decode()
            else:
                assert node['numeric_lexeme'] is None
            for child in node['children']:
                child_span = by_path[child]['value_span']
                if child_span is not None:
                    assert span['byte_start'] < child_span['byte_start'] < child_span['byte_end'] < span['byte_end']
            if kind == 'array':
                starts = [by_path[c]['value_span']['byte_start'] for c in node['children']]
                assert starts == sorted(set(starts))
        else:
            assert case['format'] == 'toml' and kind == 'object'
            assert node['numeric_lexeme'] is None
        decls = node['declarations']
        assert decls == sorted(decls, key=lambda d: (d['span']['byte_start'], d['span']['byte_end'], d['kind']))
        assert len(decls) == len({json.dumps(d, sort_keys=True) for d in decls})
        for decl in decls:
            counts['declarations'] += 1
            selected = check_span(decl['span']).decode()
            if decl['kind'] == 'json_key':
                key = json.loads(selected)
            elif decl['kind'] == 'toml_key':
                parsed_key = tomllib.loads(selected + ' = 0')
                assert len(parsed_key) == 1
                key = next(iter(parsed_key))
            elif decl['kind'] == 'toml_table':
                table_paths = dict(flattened(tomllib.loads(selected)))
                assert path in table_paths and type(table_paths[path]) is dict
                continue
            else:
                raise AssertionError(decl['kind'])
            assert path and key == path.split('/')[-1].replace('~1', '/').replace('~0', '~'), (case['id'], path, 'key declaration')

record = {'schema': 'full-todo.code-config-architect-span-review.v2', 'decision': 'PASS_CORRECTED_STATIC_CONFIG_FIXTURE', 'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'fixture_size_bytes': len(raw), 'runtime': sys.version, 'new_config_parser_imported': False, 'existing_text_contract_parity': True, 'complete_semantics_and_spans': True, 'counts': counts}
(E / 'architect-span-review-r2.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
