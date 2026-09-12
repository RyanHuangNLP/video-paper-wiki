"""Architect-only, read-only source inventory; writes this run's baseline once."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
E = ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-workflow-v2'
HEAD = '0fcae592acb977c6b422e7de3b2c3e0cf79df5a0'
TREE = 'd2d592f25d2361d5cbcc3bf58ca441a2824c256b'
VENDOR = '9f8c1199047eac2c3828496279fbb7ba9540b90b'
INTEGRATION = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ['git', '-C', str(root), *args],
        env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'},
        text=True,
    ).strip()


def file_map(root: Path, names: list[str]) -> dict[str, str]:
    result = {}
    for name in names:
        p = root / name
        if p.is_symlink() or not p.is_file():
            raise ValueError(f'not a regular baseline source: {p}')
        result[name] = digest(p.read_bytes())
    return result


def main() -> None:
    target = E / 'baseline.json'
    if target.exists():
        raise SystemExit('baseline already exists; do not overwrite')
    rows = git(INTEGRATION, 'ls-tree', '-r', '--full-tree', HEAD).splitlines()
    names = [row.split('\t', 1)[1] for row in rows if row.split()[1] == 'blob']
    gitlinks = {row.split('\t', 1)[1]: row.split()[2] for row in rows if row.split()[1] == 'commit'}
    expected = file_map(INTEGRATION, names)
    assert len(expected) == 859 and gitlinks == {'vendor/claude-obsidian': VENDOR}
    assert git(INTEGRATION, 'rev-parse', 'HEAD') == HEAD
    assert git(INTEGRATION, 'rev-parse', 'HEAD^{tree}') == TREE
    assert not git(INTEGRATION, 'status', '--porcelain=v1')
    worktrees = []
    for number in range(1, 5):
        wt = ROOT / f'.work/parallel/lightweight-workflow-v2/terminal-{number}/source'
        assert git(wt, 'rev-parse', 'HEAD') == HEAD
        assert git(wt, 'rev-parse', 'HEAD^{tree}') == TREE
        assert git(wt, 'branch', '--show-current') == f'codex/lightweight-workflow-v2-t{number}'
        assert not git(wt, 'status', '--porcelain=v1')
        assert git(wt / 'vendor/claude-obsidian', 'rev-parse', 'HEAD') == VENDOR
        assert not git(wt / 'vendor/claude-obsidian', 'status', '--porcelain=v1')
        assert file_map(wt, names) == expected
        worktrees.append({'terminal': number, 'source_root': str(wt), 'branch': f'codex/lightweight-workflow-v2-t{number}', 'head': HEAD, 'tree': TREE, 'vendor': VENDOR, 'source_matches_baseline': True})
    old = json.loads((ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/baseline.json').read_text())
    protected = dict(old['protected_history'])
    for name in ('result.json', 'exact-head-acceptance.json', 'completion.md', 'remote-ci-check.json'):
        p = ROOT / 'artifacts/verification/manual-pdf-v1/architect/r09' / name
        protected[str(p)] = digest(p.read_bytes())
    for path, sha in protected.items():
        assert digest(Path(path).read_bytes()) == sha, path
    dirty = git(ROOT, 'diff', '--name-only').splitlines()
    dirty_map = file_map(ROOT, dirty)
    pdf = old['pdf_input']
    assert digest(Path(pdf['path']).read_bytes()) == pdf['sha256']
    setup = E / 'setup.json'
    assert digest(setup.read_bytes()) == '91b400299d27ad33bd8fa89cbad9c221bb10df41fb27b56b9dd4d5874c1eab66'
    result = {
        'schema': 'lightweight-workflow-v2-baseline.v1',
        'head': HEAD, 'tree': TREE, 'gitlinks': gitlinks,
        'source_files': expected,
        'source_map_sha256': digest(json.dumps(expected, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()),
        'source_file_count': len(expected), 'worktrees': worktrees,
        'integration_read_only_root': str(INTEGRATION),
        'main_checkout': {'root': str(ROOT), 'head': git(ROOT, 'rev-parse', 'HEAD'), 'branch': git(ROOT, 'branch', '--show-current'), 'protected_dirty_tracked': dirty_map},
        'protected_history': protected, 'pdf_input': pdf,
        'python': str(ROOT / '.venv/bin/python'),
        'python_version': subprocess.check_output([str(ROOT / '.venv/bin/python'), '--version'], text=True).strip(),
        'offline_cache': str(ROOT / '.work/cache/uv-tests'),
        'setup_sha256': digest(setup.read_bytes()),
        'import_gap_observation_sha256': digest((E / 'import-gap-observation.json').read_bytes()),
        'coordination_is_not_source_delivery': True,
    }
    target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'baseline_sha256': digest(target.read_bytes()), 'source_file_count': len(expected), 'protected_history_count': len(protected), 'worktrees': len(worktrees)}))


if __name__ == '__main__':
    main()
