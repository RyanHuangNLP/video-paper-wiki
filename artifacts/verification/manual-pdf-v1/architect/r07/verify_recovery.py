"""Independent source/wheel recovery check; uses the interpreter's product import."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import video_paper_wiki_research.light_index as index

parser = argparse.ArgumentParser()
parser.add_argument('--fixture', type=Path, required=True)
parser.add_argument('--expected-sha', required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
module_path = Path(index.__file__).resolve()
assert sha(module_path) == args.expected_sha
provenance = json.loads((args.fixture / 'provenance.json').read_text())
with tempfile.TemporaryDirectory(prefix='vp.r07.recovery.', dir='/private/tmp') as directory:
    workspace = Path(directory) / '.work' / 'workspace'
    for name, target in provenance['materialize'].items():
        source = args.fixture / name
        assert sha(source) == provenance['fixture_files'][name]
        destination = workspace / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    paths = {name: workspace / target for name, target in provenance['materialize'].items()}
    old_hashes = {name: sha(path) for name, path in paths.items()}
    old_metadata = json.loads(paths['source.json'].read_text())
    before = {word: index.search(workspace, word) for word in ('quasar', 'nebula')}
    assert all(result['status'] == 'INDEX_STALE' and not result['evidence'] for result in before.values())
    assert old_hashes == {name: sha(path) for name, path in paths.items()}
    first = index.build_index(workspace)
    assert first['ok']
    md = paths['source.md'].read_text()
    after = {}
    for word, page, expected in [('quasar', 1, 'quasar describes the first PDF page only.'), ('nebula', 2, 'nebula describes the second PDF page only.')]:
        result = index.search(workspace, word)
        assert result['status'] == 'OK'
        hit = result['evidence'][0]
        assert hit['page'] == page and hit['text'] == expected
        assert hit['text_start'] == md.index(expected)
        assert hit['text_end'] == md.index(expected) + len(expected)
        assert hit['text_sha256'] == hashlib.sha256(expected.encode()).hexdigest()
        after[word] = {'page': hit['page'], 'text_start': hit['text_start'], 'text_end': hit['text_end'], 'text_sha256': hit['text_sha256']}
    new_metadata = json.loads(paths['source.json'].read_text())
    assert new_metadata['source'] == old_metadata['source'] and new_metadata['paper_id'] == old_metadata['paper_id']
    assert sha(paths['source.md']) == old_hashes['source.md']
    stable_hashes = {name: sha(path) for name, path in paths.items()}
    second = index.build_index(workspace)
    assert first['index_id'] == second['index_id']
    assert stable_hashes == {name: sha(path) for name, path in paths.items()}
    report = {'ok': True, 'module': str(module_path), 'module_sha256': sha(module_path), 'sys_path': sys.path, 'legacy_before': {word: r['status'] for word, r in before.items()}, 'after_rebuild': after, 'source_pdf_identity_unchanged': True, 'markdown_unchanged': True, 'repeat_rebuild_bytes_and_index_id_stable': True}
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'sys_path'}, ensure_ascii=False))
