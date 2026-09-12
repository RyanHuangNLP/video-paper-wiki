"""Read-only candidate review: exercise shipped pypdf extraction and index rebuild."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

SOURCE = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
from tests.research.test_light_pipeline import _pdf_with_page_texts
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_index import build_index, search

with tempfile.TemporaryDirectory(prefix='vp.r05.rebuild.', dir='/private/tmp') as temporary:
    root = Path(temporary)
    pdf = root / 'two-pages.pdf'
    pdf.write_bytes(_pdf_with_page_texts([
        'quasar describes the first PDF page only.',
        'nebula describes the second PDF page only.',
    ]))
    workspace = root / '.work' / 'workspace'
    added = extract_pdf(pdf, workspace)
    md_path = Path(added['markdown_path'])
    meta_path = Path(added['metadata_path'])
    original_md = md_path.read_text()
    original_meta = json.loads(meta_path.read_text())
    build_index(workspace)
    before = {word: search(workspace, word) for word in ('quasar', 'nebula')}
    offset_difference = original_meta['pages'][1]['text_start'] - original_meta['pages'][0]['text_start']
    prefix = 'Reader note: ' + '.' * (offset_difference - len('Reader note: ') - 2) + '\n\n'
    assert len(prefix) == offset_difference
    md_path.write_text(prefix + original_md)
    stale = search(workspace, 'quasar')
    rebuild = build_index(workspace)
    after = {word: search(workspace, word) for word in ('quasar', 'nebula')}
    final_meta = json.loads(meta_path.read_text())
    result = {
        'scenario': 'Insert an introductory line before all PDF page anchors; all extracted page text remains unchanged.',
        'inserted_codepoints': len(prefix),
        'before': before,
        'after_edit_before_rebuild': stale,
        'rebuild': rebuild,
        'after_rebuild': after,
        'all_original_page_text_still_present': all(s in md_path.read_text() for s in ('quasar describes the first PDF page only.', 'nebula describes the second PDF page only.')),
        'page_offsets_unchanged': [(p['text_start'], p['text_end']) for p in original_meta['pages']] == [(p['text_start'], p['text_end']) for p in final_meta['pages']],
        'metadata_digest_updated': final_meta['document']['sha256'] == hashlib.sha256(md_path.read_bytes()).hexdigest(),
        'reproduced_wrong_page': any(hit['page'] == 2 for hit in after['quasar']['evidence']),
        'reproduced_lost_page': after['nebula']['status'] == 'NO_RESULTS',
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert before['quasar']['evidence'][0]['page'] == 1
    assert before['nebula']['evidence'][0]['page'] == 2
    assert stale['status'] == 'INDEX_STALE'
    assert rebuild['status'] == 'OK'
    assert result['reproduced_wrong_page'] and result['reproduced_lost_page']
