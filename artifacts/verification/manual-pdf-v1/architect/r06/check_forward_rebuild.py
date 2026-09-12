"""Independent forward checks for the new candidate, without editing shipped tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

SOURCE = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
from tests.research.test_light_pipeline import _pdf_with_page_texts
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_index import build_index, search

rows = []
with tempfile.TemporaryDirectory(prefix='vp.r06.forward.', dir='/private/tmp') as temporary:
    root = Path(temporary)
    pdf = root / 'two-pages.pdf'
    pdf.write_bytes(_pdf_with_page_texts(['quasar describes the first PDF page only.', 'nebula describes the second PDF page only.']))
    workspace = root / '.work' / 'forward'
    added = extract_pdf(pdf, workspace)
    path = Path(added['markdown_path'])
    build_index(workspace)
    mutations = [
        ('prefix', lambda text: '阅读导言：' + '前言' * 34 + '\n\n' + text),
        ('first_page_insert', lambda text: text.replace('quasar describes', 'quasar 新增段落\n\n describes')),
        ('first_page_delete', lambda text: text.replace(' 新增段落\n\n', '')),
    ]
    for name, mutate in mutations:
        path.write_text(mutate(path.read_text()))
        assert search(workspace, 'quasar')['status'] == 'INDEX_STALE'
        assert build_index(workspace)['ok']
        found = {word: search(workspace, word) for word in ['quasar', 'nebula']}
        assert found['quasar']['evidence'][0]['page'] == 1
        assert found['nebula']['evidence'][0]['page'] == 2
        for item in found['quasar']['evidence'] + found['nebula']['evidence']:
            assert item['text'] == path.read_text()[item['text_start']:item['text_end']]
            assert item['text_sha256'] == hashlib.sha256(item['text'].encode()).hexdigest()
            assert '<a id=' not in item['text'] and '## PDF' not in item['text']
        rows.append({'case': name, 'status': 'PASS', 'quasar_page': 1, 'nebula_page': 2})

    second_pdf = root / 'another.pdf'
    second_pdf.write_bytes(_pdf_with_page_texts(['different first page.', 'different second page.']))
    extract_pdf(second_pdf, workspace)
    build_index(workspace)
    directories = sorted((workspace / 'papers').iterdir())
    first, second = directories
    meta_before = {p.name: (p / 'source.json').read_bytes() for p in directories}
    index_path = workspace / '.light-index/index.v1.json'
    index_before = index_path.read_bytes()
    first_md = first / 'source.md'
    first_md.write_text('New introduction\n\n' + first_md.read_text())
    second_md = second / 'source.md'
    second_md.write_text(second_md.read_text().replace('<a id="page-2"></a>', ''))
    try:
        build_index(workspace)
    except ResearchError as exc:
        assert exc.code == 'SOURCE_INVALID'
    else:
        raise AssertionError('invalid second paper must fail')
    assert all((p / 'source.json').read_bytes() == meta_before[p.name] for p in directories)
    assert index_path.read_bytes() == index_before
    rows.append({'case': 'later_invalid_paper_leaves_all_metadata_and_index_unchanged', 'status': 'PASS'})
print(json.dumps(rows, ensure_ascii=False, indent=2))
