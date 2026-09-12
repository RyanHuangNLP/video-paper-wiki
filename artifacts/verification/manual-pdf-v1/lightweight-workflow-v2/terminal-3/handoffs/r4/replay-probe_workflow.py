"""Architect probes: actual T3 backend, synthetic sources, no product edits."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
from tests.research.test_light_index import SHA_A, _write_paper
from video_paper_wiki_research import light_workflow as lw, light_index as li, light_context as lc


def setup(base):
    ws = base / 'ws'
    ws.mkdir(parents=True)
    _write_paper(ws, SHA_A, 'Synthetic', ['quasar evidence on a native synthetic page'])
    li.build_index(ws)
    return ws


def prepare(ws):
    return lw.prepare_workflow(ws, kind='qa', query='quasar')


def document(prepared):
    cid = prepared['context']['evidence'][0]['chunk_id']
    return {'text': f'Synthetic evidence [@{cid}]', 'citations': [{'chunk_id': cid}]}


def brief(result):
    return {k: result.get(k) for k in ('ok', 'status', 'state', 'session_id', 'message')}


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='lw3p-', dir='/private/tmp') as temporary:
        root = Path(temporary)
        ws = setup(root / 'control')
        p = prepare(ws)
        r = lw.complete_workflow(ws, p['session_id'], document(p), output=root/'control.md')
        rows.append({'case': 'valid_control', 'prepare': brief(p), 'complete': brief(r)})

        ws = setup(root / 'publication')
        source = ws / 'papers' / SHA_A / 'source.md'
        original_write = lw._write_persisted
        injected = False
        def write_and_edit(path, value):
            nonlocal injected
            data = original_write(path, value)
            if path.name == lw.MANIFEST_NAME and not injected:
                injected = True
                source.write_text(source.read_text().replace('quasar', 'changed-source'))
            return data
        lw._write_persisted = write_and_edit
        try:
            p = prepare(ws)
        finally:
            lw._write_persisted = original_write
        rows.append({'case': 'source_change_after_staging_before_publication', 'injected': injected,
                     'result': brief(p), 'published_sessions': len(list((ws/'.light-workflow/sessions').iterdir()))})

        for edge in ('.light-workflow', '.light-workflow/sessions', '.light-workflow/staging', '.light-workflow/locks'):
            base = root / ('symlink-' + edge.replace('/', '-'))
            ws = setup(base)
            external = base / 'outside'
            external.mkdir()
            link = ws / edge
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(external, target_is_directory=True)
            try:
                p = prepare(ws)
                observation = brief(p)
            except Exception as exc:
                observation = {'exception': type(exc).__name__, 'code': getattr(exc, 'code', None)}
            rows.append({'case': 'symlink_state_' + edge, 'result': observation,
                         'external_files': sorted(str(x.relative_to(external)) for x in external.rglob('*') if x.is_file())})

        ws = setup(root / 'temporary')
        p = prepare(ws)
        target = ws/'.light-workflow/staging'/f".{p['session_id']}.completion-intent.json.tmp"
        target.write_text('unrecognized user-owned file\n')
        r = lw.complete_workflow(ws, p['session_id'], document(p), output=root/'temporary.md')
        rows.append({'case': 'unowned_fixed_temporary_file', 'result': brief(r),
                     'unknown_file_preserved': target.exists() and target.read_text() == 'unrecognized user-owned file\n'})

        ws = setup(root / 'request')
        p = prepare(ws)
        old_dir = Path(p['manifest_path']).parent
        request = json.loads((old_dir/lw.REQUEST_NAME).read_bytes())
        context = json.loads((old_dir/lw.CONTEXT_NAME).read_bytes())
        request['kind'] = 'invalid-kind'
        request['query'] = []
        request['selected_paper_ids'] = ['invalid-selection']
        request['extra'] = 'not allowed by contract'
        request_sha = lw.sha256_persisted(request)
        context_sha = lw.sha256_persisted(context)
        new_id = lw.session_identity(request_sha, context_sha)
        manifest = lw.build_manifest(session_id=new_id, workspace_root=ws, index_id=context['index_id'],
                                     request_sha256=request_sha, context_sha256=context_sha)
        (old_dir/lw.REQUEST_NAME).write_bytes(lw.persisted_bytes(request))
        (old_dir/lw.MANIFEST_NAME).write_bytes(lw.persisted_bytes(manifest))
        new_dir = old_dir.with_name(new_id)
        old_dir.rename(new_dir)
        status = lw.workflow_status(ws, session_id=new_id)
        result = lw.complete_workflow(ws, new_id, document(p), output=root/'request.md')
        rows.append({'case': 'rehashed_invalid_request_fields', 'status': brief(status), 'complete': brief(result)})
    report = {'synthetic_only': True, 'temporary_workspace_cleaned': True,
              'modules': {str(Path(m.__file__)): hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (lw, li, lc)},
              'observations': rows}
    Path(__file__).with_name('probe-workflow-results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
