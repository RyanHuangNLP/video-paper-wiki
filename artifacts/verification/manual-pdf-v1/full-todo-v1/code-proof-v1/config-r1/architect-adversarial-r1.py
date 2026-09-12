"""Independent contract probes; run only against a stopped CONFIG candidate."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch


def run(handoff_path, output):
    handoff = json.loads(handoff_path.read_bytes())
    assert handoff['source_writes_stopped'] is True
    source = Path(handoff['source_root'])

    def check_files():
        for row in handoff['candidate_files']:
            data = (source / row['path']).read_bytes()
            assert len(data) == row['size_bytes']
            assert hashlib.sha256(data).hexdigest() == row['sha256']

    check_files()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / 'src'))
    parser = importlib.import_module('video_paper_wiki.code_config_parser')
    results = []

    def parse(payload=b'0', fmt='json', limits=None):
        return parser.parse_code_config_bytes(
            payload=payload, config_format=fmt,
            limits=dict(parser.CODE_CONFIG_PROFILE_LIMITS) if limits is None else limits)

    def refuse(label, code, operation, fields=None):
        try:
            operation()
        except parser.CodeConfigError as exc:
            assert exc.code == code, (label, exc.code, code)
            assert exc.exit_code == 2
            assert type(exc.message) is str and len(exc.message) <= 1024
            assert type(exc.details) is dict
            for key, value in (fields or {}).items():
                assert exc.details[key] == value, (label, key, exc.details)
            json.dumps(exc.details, allow_nan=False)
        else:
            raise AssertionError((label, 'accepted a required refusal'))
        results.append({'id': label, 'status': 'PASS'})

    # Each source has a separately counted first overshoot, not parser-derived data.
    caps = [
        ('source', b'{}', 'json', 'max_source_bytes', 1, 2),
        ('depth', b'[[0]]', 'json', 'max_depth', 1, 2),
        ('nodes', b'[0,1]', 'json', 'max_nodes', 2, 3),
        ('array', b'[0,1]', 'json', 'max_array_items', 1, 2),
        ('object', b'{"a":0,"b":1}', 'json', 'max_object_keys', 1, 2),
        ('key_bytes', '{"é":0}'.encode(), 'json', 'max_key_bytes', 1, 2),
        ('string_points', '"éé"'.encode(), 'json', 'max_string_codepoints', 1, 2),
        ('scalars', b'[0,1]', 'json', 'max_scalars', 1, 2),
        ('numeric_lexeme', b'10', 'json', 'max_numeric_lexeme_bytes', 1, 2),
        ('coefficient', b'12', 'json', 'max_numeric_coefficient_digits', 1, 2),
        ('explicit_exponent', b'1e2', 'json', 'max_numeric_abs_exponent', 1, 2),
        ('tuple_exponent', b'0.01', 'json', 'max_numeric_abs_exponent', 1, 2),
        ('canonical', b'1e2', 'json', 'max_numeric_canonical_bytes', 2, 3),
        ('declarations', b'{"a":0,"b":1}', 'json', 'max_declarations', 1, 2),
        ('toml_implicit', b'a.b=0\n', 'toml', 'max_nodes', 2, 3),
        ('toml_declarations', b'[a.b]\nx=1\n[a]\ny=2\n', 'toml', 'max_declarations', 6, 7),
    ]
    for name, payload, fmt, limit_name, cap, observed in caps:
        limits = dict(parser.CODE_CONFIG_PROFILE_LIMITS)
        limits[limit_name] = cap
        # A scanner's cap refusal must not invoke either stdlib cross-check.
        with patch('json.loads', side_effect=AssertionError('early json cross-check')), \
             patch('tomllib.loads', side_effect=AssertionError('early toml cross-check')):
            refuse('cap_' + name, 'CODE_CONFIG_LIMIT_EXCEEDED',
                   lambda: parse(payload, fmt, limits),
                   {'limit_name': limit_name, 'limit': cap, 'observed': observed})
        limits[limit_name] = observed
        parse(payload, fmt, limits)
        results.append({'id': 'equal_cap_' + name, 'status': 'PASS'})

    # Inputs are constructed before callbacks are armed. Custom key equality,
    # hash and formatting must never run while rejecting their non-exact type.
    callbacks = []
    armed = False

    class Key(str):
        def __hash__(self):
            if armed:
                callbacks.append('hash')
                raise AssertionError('custom hash called')
            return str.__hash__(self)

        def __eq__(self, other):
            if armed:
                callbacks.append('eq')
                raise AssertionError('custom equality called')
            return str.__eq__(self, other)

        def __str__(self):
            if armed:
                callbacks.append('str')
                raise AssertionError('custom string called')
            return str.__str__(self)

        def __repr__(self):
            if armed:
                callbacks.append('repr')
                raise AssertionError('custom repr called')
            return str.__repr__(self)

    for bad_name in ('max_source_bytes', 'max_declarations'):
        armed = False
        limits = {Key(k) if k == bad_name else k: v
                  for k, v in parser.CODE_CONFIG_PROFILE_LIMITS.items()}
        armed = True
        refuse('hostile_key_' + bad_name, 'CODE_CONFIG_INPUT_INVALID',
               lambda: parse(limits=limits))
        assert not callbacks
    armed = False

    class Bytes(bytes):
        pass

    class Int(int):
        pass

    class Map(dict):
        def __len__(self):
            raise AssertionError('mapping length callback')

    refuse('bytes_subclass', 'CODE_CONFIG_INPUT_INVALID', lambda: parse(Bytes(b'0')))
    refuse('format_subclass', 'CODE_CONFIG_INPUT_INVALID', lambda: parse(fmt=Key('json')))
    refuse('limits_subclass', 'CODE_CONFIG_INPUT_INVALID', lambda: parse(limits=Map()))
    for value in (True, Int(1), 0, -1, 262145):
        limits = dict(parser.CODE_CONFIG_PROFILE_LIMITS)
        limits['max_source_bytes'] = value
        refuse('bad_limit_' + type(value).__name__ + '_' + str(value),
               'CODE_CONFIG_INPUT_INVALID', lambda: parse(limits=limits))

    # Deliberately corrupt complete stdlib values with the same number of leaves.
    wrong_json = [False, 1, {'a': 1}, {'a': True, 'extra': 1},
                  {'b': True}, {'a': 'true'}, {'a': Decimal('1')}]
    for index, wrong in enumerate(wrong_json):
        with patch('json.loads', return_value=wrong):
            refuse('json_full_tree_mismatch_' + str(index), 'CODE_CONFIG_PARSER_MISMATCH',
                   lambda: parse(b'{"a":true}'))
    with patch('json.loads', return_value=[2, 1]):
        refuse('json_array_order', 'CODE_CONFIG_PARSER_MISMATCH', lambda: parse(b'[1,2]'))
    for index, wrong in enumerate(({'a': True}, {'a': 1}, {'a': '1'}, {'a': Decimal('2')})):
        with patch('tomllib.loads', return_value=wrong):
            refuse('toml_numeric_kind_value_' + str(index), 'CODE_CONFIG_PARSER_MISMATCH',
                   lambda: parse(b'a=1e0\n', 'toml'))

    numbers = [('1e-4', '0.0001'), ('123456789012345678901234567890.00100',
                '123456789012345678901234567890.001'), ('1e0', '1'), ('0e128', '0')]
    with localcontext() as context:
        context.prec = 1
        context.Emax = 1
        context.Emin = -1
        for signal in context.traps:
            context.traps[signal] = True
        before = (context.prec, context.Emax, context.Emin, dict(context.traps), dict(context.flags))
        for index, (lexeme, value) in enumerate(numbers):
            for fmt in ('json', 'toml'):
                payload = (lexeme if fmt == 'json' else 'x=' + lexeme + '\n').encode()
                result = parse(payload, fmt)
                node = result['nodes'][-1]
                assert (node['kind'], node['value'], node['numeric_lexeme']) == ('decimal', value, lexeme)
                results.append({'id': 'hostile_decimal_' + fmt + '_' + str(index), 'status': 'PASS'})
        after = (context.prec, context.Emax, context.Emin, dict(context.traps), dict(context.flags))
        assert before == after

    for fmt, payload in [('json', b'-0'), ('json', b'-0.000'), ('json', b'-0e100'),
                         ('toml', b'x=-0\n'), ('toml', b'x=-0.00e+1\n')]:
        refuse('negative_zero_' + fmt + '_' + payload.hex(), 'CODE_CONFIG_NUMBER_INVALID',
               lambda: parse(payload, fmt))
    check_files()
    record = {'status': 'PASS', 'runtime': sys.version,
              'candidate_snapshot_sha256': handoff['candidate_snapshot_sha256'],
              'handoff_sha256': hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
              'checks': len(results), 'rows': results, 'candidate_files_unchanged': True}
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'rows'}))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('handoff', type=Path)
    cli.add_argument('output', type=Path)
    options = cli.parse_args()
    run(options.handoff, options.output)
