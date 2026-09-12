"""Architect-owned bounded probes of the frozen Agent 2 r2 candidate."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile

from tests.research.test_light_index import SHA_A, _write_paper
from video_paper_wiki_research import light_context as lc, light_index as li


def observe(name, call, output=None):
    try:
        r = call()
        row = {'name': name, 'ok': r.get('ok'), 'status': r.get('status'), 'evidence_count': len(r.get('evidence', []))}
    except Exception as exc:
        row = {'name': name, 'exception': type(exc).__name__, 'message': str(exc)}
    if output is not None:
        row['output_exists'] = output.exists()
        row['output_text'] = output.read_text() if output.exists() else None
    return row


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='lw2probe-', dir='/private/tmp') as tmp:
        root = Path(tmp)
        workspace = root / 'ws'
        workspace.mkdir()
        _write_paper(workspace, SHA_A, 'Example', ['quasar method evidence from a synthetic page'])
        li.build_index(workspace)
        context = lc.export_context(workspace, kind='qa', query='quasar')
        cid = context['evidence'][0]['chunk_id']
        answer = {'text': f'Evidence [@{cid}]', 'citations': [{'chunk_id': cid}]}
        rows.append(observe('valid_control', lambda: lc.import_document(workspace, context, answer, output=root/'ok.md')))
        for label, selected in [('empty', []), ('blank', ['']), ('valid_plus_blank', ['sha256:'+SHA_A, '']), ('valid_plus_unknown', ['sha256:'+SHA_A, 'sha256:'+'f'*64])]:
            rows.append(observe('search_selection_'+label, lambda selected=selected: li.search(workspace, 'quasar', paper_ids=selected)))
        bad = copy.deepcopy(context)
        bad['kind'] = []
        rows.append(observe('context_kind_list', lambda: lc.validate_live_context(workspace, bad)))
        index = workspace/'.light-index/index.v1.json'
        original_index = index.read_bytes()
        payload = json.loads(original_index)
        del payload['papers'][0]['markdown_sha256']
        index.write_text(json.dumps(payload))
        rows.append(observe('index_paper_missing_markdown_hash_validate', lambda: lc.validate_live_context(workspace, context)))
        rows.append(observe('index_paper_missing_markdown_hash_import', lambda: lc.import_document(workspace, context, answer, output=root/'bad.md'), root/'bad.md'))
        index.write_bytes(original_index)
        source = workspace/'papers'/SHA_A/'source.md'
        original_source = source.read_bytes()
        target = root/'keep.md'
        target.write_text('user-owned existing output\n')
        before_output = target.read_bytes()
        original_write = Path.write_bytes
        injected = {'done': False}
        def write_with_source_change(path, data):
            result = original_write(path, data)
            if path.name.endswith('.light-out.tmp') and not injected['done']:
                injected['done'] = True
                original_write(source, original_source.replace(b'quasar', b'changed-source'))
            return result
        Path.write_bytes = write_with_source_change
        try:
            row = observe('source_changed_after_output_staging_before_install', lambda: lc.import_document(workspace, context, answer, output=target))
            row.update(injected=injected['done'], old_output_preserved=target.read_bytes()==before_output, subsequent_live_status=lc.validate_live_context(workspace, context).get('status'))
            rows.append(row)
        finally:
            Path.write_bytes = original_write
            source.write_bytes(original_source)
    result = {'synthetic_only': True, 'temporary_workspace_cleaned': True, 'observations': rows, 'modules': {str(Path(m.__file__)): hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (lc, li)}}
    output = Path(__file__).with_name('probe-results.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
