"""Independent pre-implementation verification of synthetic static Git vectors."""
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
E = ROOT / 'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1'
W = ROOT / '.work/parallel/code-proof-v1/terminal-1/source'
F = E / 'independent-git-fixture-v1.json'
raw = F.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'b8936db0a65d58d533016840e3d7cfbc686f819b240c812207e73638165955f0'
fixture = json.loads(raw)
results = {}
for fmt, variant in fixture['formats'].items():
    rows = {r['oid']: r for r in variant['all_objects']}
    trees = {}
    for oid, row in rows.items():
        body = bytes.fromhex(row['body_hex'])
        frame = row['type'].encode() + b' ' + str(len(body)).encode() + b'\0' + body
        assert len(body) == row['size']
        assert hashlib.sha256(body).hexdigest() == row['body_sha256']
        assert hashlib.sha256(frame).hexdigest() == row['framed_sha256']
        assert hashlib.new(fmt, frame, usedforsecurity=False).hexdigest() == oid
        if row['type'] == 'tree':
            entries, pos, order = {}, 0, []
            while pos < len(body):
                space = body.index(b' ', pos)
                nul = body.index(b'\0', space)
                mode, name = body[pos:space].decode(), body[space+1:nul]
                end = nul + 1 + variant['oid_width'] // 2
                assert end <= len(body) and name not in entries
                child = body[nul+1:end].hex()
                entries[name] = (mode, child)
                order.append(name + (b'/' if mode == '40000' else b'\0'))
                pos = end
            assert order == sorted(order)
            trees[oid] = entries
    commit_body = bytes.fromhex(rows[variant['commit_oid']]['body_hex'])
    assert commit_body.startswith(('tree ' + variant['root_tree_oid'] + '\n').encode())
    assert commit_body.split(b'\n\n', 1)[0].count(b'\nparent ') == 2
    counts = {}
    for name, case in variant['cases'].items():
        used = {variant['commit_oid'], variant['root_tree_oid']}
        expected = []
        for target in case['targets']:
            tree = variant['root_tree_oid']
            parts = target['path'].encode().split(b'/')
            for index, part in enumerate(parts):
                entry = trees[tree].get(part)
                if entry is None:
                    outcome, reason = 'missing', 'absent_entry'
                    break
                mode, oid = entry
                if index < len(parts) - 1:
                    if mode != '40000':
                        outcome, reason = 'unsafe', 'non_directory_intermediate'
                        break
                    assert rows[oid]['type'] == 'tree'
                    used.add(oid)
                    tree = oid
                elif mode == '100644' or (mode == '100755' and target['allow_executable_source']):
                    assert rows[oid]['type'] == 'blob'
                    used.add(oid)
                    outcome, reason = 'permitted_regular_blob', None
                else:
                    outcome = 'unsafe'
                    reason = {'100755': 'executable_without_permission', '40000': 'directory', '120000': 'symlink', '160000': 'gitlink'}[mode]
            expected.append({'path': target['path'], 'outcome': outcome, 'reason': reason})
        assert expected == case['expected'], name
        assert sorted(used) == case['required_object_oids'], name
        assert not (set(variant['parent_oids']) & used)
        counts[name] = {'target_count': len(expected), 'required_object_count': len(used)}
    results[fmt] = {'verified_objects': len(rows), 'verified_trees': len(trees), 'cases': counts}

def git(*args):
    return subprocess.check_output(['git', '-C', str(W), *args], text=True).strip()

assert git('rev-parse', 'HEAD') == '8728aafc9aa7af5caf90d60bfa6ab2ba89419f75'
assert git('rev-parse', 'HEAD^{tree}') == 'cefcd1be9797d1f4202153d7b9dc4ee1d8423f14'
assert git('status', '--porcelain') == ''
record = {'schema': 'full-todo.code-git-kernel-architect-fixture-check.v1', 'status': 'PASS', 'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'fixture_size_bytes': len(raw), 'checks': results, 'source_worktree': str(W), 'head': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'), 'clean': True, 'production_imported': False, 'git_mutated': False}
out = E / 'architect-fixture-check-r1.json'
out.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
