"""Refuse non-exact primitive types before invoking their methods."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

GUARDED = False


def guarded(base):
    def call(self, *args, **kwargs):
        if GUARDED:
            raise AssertionError('untrusted primitive callback was invoked')
        return base(self, *args, **kwargs)
    return call


class UntrustedStr(str):
    __hash__ = guarded(str.__hash__)
    __eq__ = guarded(str.__eq__)
    __str__ = guarded(str.__str__)
    __repr__ = guarded(str.__repr__)
    __len__ = guarded(str.__len__)
    encode = guarded(str.encode)
    casefold = guarded(str.casefold)


class UntrustedInt(int):
    __int__ = guarded(int.__int__)
    __lt__ = guarded(int.__lt__)
    __le__ = guarded(int.__le__)
    __gt__ = guarded(int.__gt__)
    __ge__ = guarded(int.__ge__)


class UntrustedBytes(bytes):
    __len__ = guarded(bytes.__len__)


class UntrustedList(list):
    __iter__ = guarded(list.__iter__)
    __len__ = guarded(list.__len__)
    __getitem__ = guarded(list.__getitem__)


class UntrustedDict(dict):
    __iter__ = guarded(dict.__iter__)
    __len__ = guarded(dict.__len__)
    __getitem__ = guarded(dict.__getitem__)
    keys = guarded(dict.keys)
    items = guarded(dict.items)


def run(handoff):
    global GUARDED
    source = Path(handoff['source_root'])
    assert handoff['source_writes_stopped'] is True
    for row in handoff['candidate_files']:
        data = (source / row['path']).read_bytes()
        assert len(data) == row['size_bytes']
        assert hashlib.sha256(data).hexdigest() == row['sha256']
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / 'src'))
    mod = importlib.import_module('video_paper_wiki.code_git_objects')
    fixture = json.loads((source / 'tests/fixtures/code-git-objects-v1.json').read_text())
    cases = []
    for fmt, variant in fixture['formats'].items():
        case = variant['cases']['exec_opt_in']
        inventory = {r['oid']: r for r in variant['all_objects']}
        rows = [inventory[oid] for oid in sorted(case['required_object_oids'])]
        objects = [dict(oid=r['oid'], object_type=r['type'], body_size_bytes=r['size'],
                        body_sha256=r['body_sha256'], framed_sha256=r['framed_sha256']) for r in rows]
        bodies = {r['oid']: bytes.fromhex(r['body_hex']) for r in rows}
        targets = case['targets']
        good = dict(object_format=fmt, commit_oid=variant['commit_oid'],
                    root_tree_oid=variant['root_tree_oid'], objects=objects,
                    bodies=bodies, targets=targets, limits=dict(mod.CODE_GIT_PROFILE_LIMITS))
        vectors = []
        for field in ('object_format', 'commit_oid', 'root_tree_oid'):
            vectors.append((field + '_subclass', {**good, field: UntrustedStr(good[field])}))
        for field, cls in [('objects', UntrustedList), ('targets', UntrustedList),
                           ('bodies', UntrustedDict), ('limits', UntrustedDict)]:
            vectors.append((field + '_subclass', {**good, field: cls(good[field])}))
        vectors.append(('object_record_subclass', {**good, 'objects': [UntrustedDict(objects[0]), *objects[1:]]}))
        vectors.append(('target_record_subclass', {**good, 'targets': [UntrustedDict(targets[0]), *targets[1:]]}))
        for field in ('oid', 'object_type', 'body_sha256', 'framed_sha256'):
            changed = {**objects[0], field: UntrustedStr(objects[0][field])}
            vectors.append(('object_' + field + '_subclass', {**good, 'objects': [changed, *objects[1:]]}))
        vectors.append(('size_subclass', {**good, 'objects': [{**objects[0], 'body_size_bytes': UntrustedInt(objects[0]['body_size_bytes'])}, *objects[1:]]}))
        vectors.append(('limit_value_subclass', {**good, 'limits': {**good['limits'], 'max_targets': UntrustedInt(32)}}))
        vectors.append(('target_path_subclass', {**good, 'targets': [{**targets[0], 'path': UntrustedStr(targets[0]['path'])}, *targets[1:]]}))
        vectors.append(('body_subclass', {**good, 'bodies': {oid: UntrustedBytes(body) for oid, body in bodies.items()}}))
        # Exact dictionaries with same-spelling non-exact keys must not invoke
        # custom hashing/equality while checking their otherwise valid shape.
        vectors.append(('record_key_subclass', {**good, 'objects': [{UntrustedStr(k): v for k, v in objects[0].items()}, *objects[1:]]}))
        vectors.append(('target_key_subclass', {**good, 'targets': [{UntrustedStr(k): v for k, v in targets[0].items()}, *targets[1:]]}))
        vectors.append(('limit_key_subclass', {**good, 'limits': {UntrustedStr(k): v for k, v in good['limits'].items()}}))
        vectors.append(('body_key_subclass', {**good, 'bodies': {UntrustedStr(k): v for k, v in bodies.items()}}))
        for label, kwargs in vectors:
            GUARDED = True
            try:
                try:
                    mod.verify_code_git_objects(**kwargs)
                except mod.CodeGitProofError as exc:
                    assert exc.code == 'CODE_PROOF_INPUT_INVALID', (label, exc.code)
                    assert exc.exit_code == 2
                else:
                    raise AssertionError('non-exact primitive accepted: ' + label)
            finally:
                GUARDED = False
            cases.append(dict(object_format=fmt, case=label))
        # Regular valid calls still succeed after all refusals.
        assert mod.verify_code_git_objects(**good)['object_format'] == fmt
    return dict(status='PASS', checks=len(cases),
                candidate_snapshot_sha256=handoff['candidate_snapshot_sha256'], cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--handoff', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(json.loads(args.handoff.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
