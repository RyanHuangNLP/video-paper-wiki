"""Independent declarative Git DAG oracle; run only after a frozen handoff."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import random
import sys
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def execute(source, handoff):
    assert handoff['source_writes_stopped'] is True
    assert Path(handoff['source_root']).resolve() == source.resolve()
    for row in handoff['candidate_files']:
        data = (source / row['path']).read_bytes()
        assert len(data) == row['size_bytes'] and digest(data) == row['sha256']
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / 'src'))
    module = importlib.import_module('video_paper_wiki.code_git_objects')
    rng = random.Random(612867)
    results = []
    for fmt in ('sha1', 'sha256'):
        for sample in range(64):
            records, bodies, trees = {}, {}, {}

            def add(kind, body):
                frame = kind.encode('ascii') + b' ' + str(len(body)).encode('ascii') + b'\0' + body
                oid = (hashlib.sha1(frame, usedforsecurity=False).hexdigest()
                       if fmt == 'sha1' else digest(frame))
                records[oid] = dict(oid=oid, object_type=kind, body_size_bytes=len(body),
                                    body_sha256=digest(body), framed_sha256=digest(frame))
                bodies[oid] = body
                return oid

            def tree(entries):
                # Expected traversal uses declarative tuples, never re-parses bytes.
                ordered = sorted(entries, key=lambda e: e[0] + (b'/' if e[1] == '40000' else b'\0'))
                raw = b''.join(mode.encode('ascii') + b' ' + name + b'\0' + bytes.fromhex(oid)
                               for name, mode, oid in ordered)
                oid = add('tree', raw)
                trees[oid] = {name: (mode, target) for name, mode, target in ordered}
                return oid

            blob_a = add('blob', rng.randbytes(sample % 19))
            blob_b = add('blob', b'blob 07\0' + rng.randbytes(3))
            unmaterialized = ('ed' * (20 if fmt == 'sha1' else 32))
            empty = tree([])
            shared = tree([(b'.hidden', '100644', blob_a), (b'copy', '100644', blob_a),
                           (b'run', '100755', blob_b), (b'link', '120000', unmaterialized),
                           (b'empty', '40000', empty), (b'git', '160000', unmaterialized),
                           (b'\xffopaque', '100644', unmaterialized)])
            root = tree([(b'foo.bar', '100644', blob_b), (b'foo', '40000', shared),
                         (b'foo0', '40000', shared), (b'other', '100644', blob_a)])
            commit = add('commit', ('tree ' + root + '\nparent ' + unmaterialized +
                                   '\ngpgsig header\n continuation\nauthor opaque\n\n').encode() + rng.randbytes(4))
            choices = ['foo.bar', 'foo/.hidden', 'foo/copy', 'foo/run', 'foo/link',
                       'foo/git', 'foo/empty/missing', 'foo/no-file', 'foo0/.hidden',
                       'foo0/run', 'foo0/link/x', 'other/x', 'missing/deep']
            paths = sorted(rng.sample(choices, rng.randint(1, len(choices))))
            targets = [dict(path=path, allow_executable_source=bool(rng.getrandbits(1))) for path in paths]
            consumed = {root, commit}
            expected_targets = []
            for target in targets:
                parent, walk, blob = root, [], None
                parts = target['path'].split('/')
                for index, name in enumerate(parts):
                    consumed.add(parent)
                    found = trees[parent].get(name.encode('ascii'))
                    if found is None:
                        stopped = dict(component_index=index, tree_oid=parent,
                                       name_hex=name.encode().hex(), mode=None, oid=None)
                        outcome, reason = 'missing', 'absent_entry'
                        break
                    mode, oid = found
                    edge = dict(tree_oid=parent, name_hex=name.encode().hex(), mode=mode, oid=oid)
                    walk.append(edge)
                    stopped = dict(component_index=index, **edge)
                    if index < len(parts) - 1:
                        if mode == '40000':
                            parent = oid
                            continue
                        outcome, reason = 'unsafe', 'non_directory_intermediate'
                    elif mode == '100644' or (mode == '100755' and target['allow_executable_source']):
                        outcome, reason = 'permitted_regular_blob', None
                        consumed.add(oid)
                        blob = {k: records[oid][k] for k in ('oid', 'body_size_bytes', 'body_sha256', 'framed_sha256')}
                    else:
                        outcome = 'unsafe'
                        reason = {'100755': 'executable_without_permission', '120000': 'symlink',
                                  '160000': 'gitlink', '40000': 'directory'}[mode]
                    break
                expected_targets.append(dict(path=target['path'], outcome=outcome, reason=reason,
                                             walk=walk, stopped_at=stopped, blob=blob))
            ordered = sorted(consumed)
            inputs = dict(object_format=fmt, commit_oid=commit, root_tree_oid=root,
                          objects=[records[oid] for oid in ordered],
                          bodies={oid: bodies[oid] for oid in ordered}, targets=targets,
                          limits=dict(module.CODE_GIT_PROFILE_LIMITS))
            pristine = copy.deepcopy(inputs)
            expected = dict(object_format=fmt, commit_oid=commit, root_tree_oid=root,
                            object_records=inputs['objects'], consumed_oids=ordered,
                            budget=dict(object_count=len(ordered),
                                        declared_body_bytes=sum(len(bodies[oid]) for oid in ordered),
                                        actual_body_bytes=sum(len(bodies[oid]) for oid in ordered),
                                        parsed_tree_entries=sum(len(trees[oid]) for oid in ordered if oid in trees),
                                        target_count=len(targets),
                                        walk_edges=sum(len(t['walk']) for t in expected_targets)),
                            targets=expected_targets)
            actual = module.verify_code_git_objects(**inputs)
            assert actual == expected, (fmt, sample, 'oracle mismatch', actual, expected)
            assert inputs == pristine, (fmt, sample, 'input mutation')
            assert module.verify_code_git_objects(**inputs) == actual
            # Key order is contract data independently of ordinary dict equality.
            assert json.dumps(actual) == json.dumps(expected), (fmt, sample, 'key order')
            actual['object_records'][0]['body_size_bytes'] = -1
            actual['targets'][0]['walk'].clear()
            assert inputs == pristine, (fmt, sample, 'mutable output alias')
            results.append(dict(object_format=fmt, sample=sample, target_count=len(targets),
                                proof_sha256=digest(json.dumps(expected).encode())))
    return dict(status='PASS', independent_declarative_graphs=len(results),
                candidate_snapshot_sha256=handoff['candidate_snapshot_sha256'], cases=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--handoff', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text())
    result = execute(Path(handoff['source_root']), handoff)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
