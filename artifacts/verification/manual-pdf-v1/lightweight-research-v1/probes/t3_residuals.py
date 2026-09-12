"""Architect independent replay of the four observed T3 R2 residuals."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--handoff', required=True)
p.add_argument('--report', required=True)
a = p.parse_args()
s = Path(a.source).resolve()
sys.path[:0] = [str(s / 'src'), str(s)]
from tests.research.test_light_writing_project import _workspace, _writing_context, _outline_document, _create_project
from video_paper_wiki_research import light_writing_project as w

h = json.loads(Path(a.handoff).read_text())
def check_source():
    for f in h['files']:
        b = (s / f['path']).read_bytes()
        assert len(b) == f['size_bytes'] and hashlib.sha256(b).hexdigest() == f['sha256']

def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}

rows = []
def record(name, passed, result):
    rows.append({'case': name, 'passed': bool(passed), 'result': result})

check_source()
with tempfile.TemporaryDirectory(prefix='t3res.', dir='/private/tmp') as tmp:
    root = Path(tmp)
    ws = _workspace(root / 'initial')
    ctx = _writing_context(ws)
    wrapper = w.export_writing_outline(ws, ctx)
    doc = _outline_document(ctx)
    original = w._publish_revision
    def after_revision(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('Architect interruption immediately after first revision install')
    w._publish_revision = after_revision
    try:
        first = w.import_writing_outline(ws, wrapper, doc)
    finally:
        w._publish_revision = original
    retry = w.import_writing_outline(ws, wrapper, doc)
    revisions = list((ws / '.light-writing/projects').glob('*/revisions/*'))
    record('initial_post_revision_interruption_recovers', first.get('ok') is False and retry.get('ok') is True and len(revisions) == 1,
           {'first': first, 'retry': retry, 'revision_count': len(revisions)})

    ws = _workspace(root / 'kind')
    ctx, wrapper, result = _create_project(ws)
    f = w._revision_dir(ws, result['project_id'], result['revision_id']) / 'document.json'
    doc = json.loads(f.read_text())
    doc['kind'] = []
    f.write_bytes(w.persisted_bytes(doc))
    before = snapshot(ws)
    try:
        blockers = w.writing_backup_blockers(ws)
        record('stored_kind_list_backup_closed', bool(blockers) and snapshot(ws) == before, blockers)
    except Exception as exc:
        record('stored_kind_list_backup_closed', False, {'exception': type(exc).__name__, 'message': str(exc)})

    ws = _workspace(root / 'unwritten')
    ctx, wrapper, result = _create_project(ws)
    pid, parent = result['project_id'], result['revision_id']
    doc = json.loads((w._revision_dir(ws, pid, parent) / 'document.json').read_text())
    doc.update(kind='section', parent_revision_id=parent, target_section_id='s1')
    rid = w._revision_identity(project_id=pid, parent_revision_id=parent, context_sha256=w.sha256_canonical(ctx), document=doc)
    files = w._revision_files(workspace=ws, project_id=pid, revision_id=rid, parent_revision_id=parent, context=ctx, document=doc)
    dest = w._revision_dir(ws, pid, rid)
    dest.mkdir()
    for name, data in files.items():
        (dest / name).write_bytes(data)
    w._head_path(ws, pid).write_bytes(w.persisted_bytes({'schema': w.HEAD_SCHEMA, 'project_id': pid, 'revision_id': rid}))
    before = snapshot(ws)
    history = w.writing_project_history(ws, project_id=pid)
    export = w.export_writing_section(ws, project_id=pid, section_id='s1')
    blockers = w.writing_backup_blockers(ws)
    record('forged_selected_unwritten_history', history.get('ok') is False, history)
    record('forged_selected_unwritten_export', export.get('ok') is False, export)
    record('forged_selected_unwritten_backup', bool(blockers) and snapshot(ws) == before, blockers)

    for name, score in [('overflow_integer', 10**400), ('bool', True), ('nonfinite_nan', float('nan')), ('nonfinite_inf', float('inf'))]:
        ws = _workspace(root / name)
        ctx = _writing_context(ws)
        ctx['evidence'][0]['score'] = score
        before = snapshot(ws)
        try:
            result = w.export_writing_outline(ws, ctx)
            record('live_score_' + name, result.get('ok') is False and result.get('status') == 'LIGHT_CONTEXT_INVALID' and snapshot(ws) == before, result)
        except Exception as exc:
            record('live_score_' + name, False, {'exception': type(exc).__name__, 'message': str(exc)})

check_source()
report = {'schema': 'lightweight-research-architect-t3-residual-replay.v1', 'snapshot_sha256': h['snapshot_sha256'],
          'source_hashes_verified_before_after': True, 'source_root': str(s), 'module_file': w.__file__, 'python': sys.version,
          'observations': rows, 'passed': sum(x['passed'] for x in rows), 'total': len(rows)}
Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
print(json.dumps({'passed': report['passed'], 'total': report['total'], 'cases': [{'case': x['case'], 'passed': x['passed']} for x in rows]}))
