"""Review upgrade recovery using the byte-verified r05 wheel's real index code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

SOURCE = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')
OLD = SOURCE / '.work/wheel-prefix/venv/lib/python3.13/site-packages/video_paper_wiki_research/light_index.py'
OLD_SHA = '9a7c978213d90da59d2e97391f8a10d94f5a6a2be67d6c4df2f4fcfb3f122eee'
assert hashlib.sha256(OLD.read_bytes()).hexdigest() == OLD_SHA
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
from tests.research.test_light_pipeline import _pdf_with_page_texts
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research import light_index as fixed

spec = importlib.util.spec_from_file_location('r05_historical_index', OLD)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

with tempfile.TemporaryDirectory(prefix='vp.r06.upgrade.', dir='/private/tmp') as temporary:
    root = Path(temporary)
    pdf = root / 'two-pages.pdf'
    pdf.write_bytes(_pdf_with_page_texts(['quasar describes the first PDF page only.', 'nebula describes the second PDF page only.']))
    workspace = root / '.work' / 'workspace'
    added = extract_pdf(pdf, workspace)
    md_path = Path(added['markdown_path'])
    meta_path = Path(added['metadata_path'])
    md = md_path.read_text()
    meta = json.loads(meta_path.read_text())
    old.build_index(workspace)
    gap = meta['pages'][1]['text_start'] - meta['pages'][0]['text_start']
    prefix = 'Reader note: ' + '.' * (gap - len('Reader note: ') - 2) + '\n\n'
    md_path.write_text(prefix + md)
    old.build_index(workspace)
    old_results = {word: old.search(workspace, word) for word in ['quasar', 'nebula']}
    assert old_results['quasar']['evidence'][0]['page'] == 2
    assert old_results['nebula']['status'] == 'NO_RESULTS'
    before = {word: fixed.search(workspace, word) for word in ['quasar', 'nebula']}
    build = fixed.build_index(workspace)
    after = {word: fixed.search(workspace, word) for word in ['quasar', 'nebula']}
    report = {
        'scenario': 'The old r05 build_index really writes stale offsets and fresh digests; then the new candidate opens and explicitly rebuilds that workspace without editing Markdown again.',
        'old_module_sha256': OLD_SHA,
        'new_module_sha256': hashlib.sha256(Path(fixed.__file__).read_bytes()).hexdigest(),
        'fixed_reader_before_rebuild': before,
        'fixed_build': build,
        'fixed_reader_after_rebuild': after,
        'original_page_text_preserved': all(s in md_path.read_text() for s in ['quasar describes the first PDF page only.', 'nebula describes the second PDF page only.']),
        'still_wrong_page': any(e['page'] == 2 for e in after['quasar']['evidence']),
        'still_missing_page_two': after['nebula']['status'] == 'NO_RESULTS',
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert build['ok'] and report['still_wrong_page'] and report['still_missing_page_two']
