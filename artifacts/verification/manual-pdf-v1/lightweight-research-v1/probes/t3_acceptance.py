"""Architect probes of exact stopped writing source; disposable synthetic data."""
import argparse
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--handoff', required=True)
parser.add_argument('--report', required=True)
args = parser.parse_args()
source = Path(args.source).resolve()
sys.path[:0] = [str(source / 'src'), str(source)]
from tests.research.test_light_writing_project import _workspace, _create_project, _section_document, _chunk
from video_paper_wiki_research import light_writing_project as w

handoff = json.loads(Path(args.handoff).read_text())
def check_source():
    for row in handoff['files']:
        data = (source / row['path']).read_bytes()
        assert len(data) == row['size_bytes']
        assert hashlib.sha256(data).hexdigest() == row['sha256']
check_source()
observations = []
def record(name, result, expected_ok, **extra):
    observations.append({'case': name, 'expected_ok': expected_ok,
        'passed': result.get('ok') is expected_ok, 'result': result, **extra})
def setup(root, name):
    ws = _workspace(root / name)
    context, wrapper, initial = _create_project(ws)
    pid = initial['project_id']
    export = w.export_writing_section(ws, project_id=pid, section_id='s1')
    doc = _section_document(pid, 's1', _chunk(context), 'Synthetic method')
    return ws, context, initial, export, doc

with tempfile.TemporaryDirectory(prefix='t3probe.', dir='/private/tmp') as tmp:
    root = Path(tmp)
    ws, c, init, ex, doc = setup(root, 'multiline')
    doc['markdown'] = 'First paragraph.\n\n- Second paragraph. [@' + _chunk(c) + ']'
    record('ordinary_multiline_markdown', w.import_writing_section(ws, ex, doc), True)
    record('multiline_instructions', w.export_writing_section(ws, project_id=init['project_id'], section_id='s1', instructions='Explain method.\nPreserve uncertainty.'), True)

    ws, c, init, ex, doc = setup(root, 'retry')
    real_publish = w._publish_head
    def fail_head(*a, **kw):
        raise w.ResearchError(w.LIGHT_WRITING_PROJECT_CONFLICT, 'synthetic pointer interruption')
    w._publish_head = fail_head
    try:
        interrupted = w.import_writing_section(ws, ex, doc)
    finally:
        w._publish_head = real_publish
    record('interruption_closed', interrupted, False)
    record('exact_retry_after_revision_before_head', w.import_writing_section(ws, ex, doc), True)

    ws, c, init, ex, doc = setup(root, 'missing_head')
    w._head_path(ws, init['project_id']).unlink()
    record('missing_preexisting_head_must_not_be_recreated', w.import_writing_section(ws, ex, doc), False)

    ws, c, init, ex, doc = setup(root, 'output')
    result = w.import_writing_section(ws, ex, doc)
    assert result['ok']
    target = ws / '.light-index' / 'new-parent' / 'draft.md'
    result = w.export_writing_project(ws, project_id=init['project_id'], output=target)
    record('managed_output_nonexistent_parent', result, False, output_created=target.exists())
    other = root / 'outside' / 'subdir'
    other.mkdir(parents=True)
    link = root / '.work' / 'link'
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(other, target_is_directory=True)
    unsafe = link / '..' / 'unexpected.md'
    result = w.export_writing_project(ws, project_id=init['project_id'], output=unsafe)
    record('output_raw_symlink_dotdot', result, False, actual_resolved=str(unsafe.resolve()))

    ws, c, init, ex, doc = setup(root, 'rehashed_draft')
    pid, rid = init['project_id'], init['revision_id']
    directory = w._revision_dir(ws, pid, rid)
    draft = directory / 'draft.md'
    draft.write_text('Synthetic edited historical draft.\n')
    manifest = json.loads((directory / 'manifest.json').read_text())
    for row in manifest['files']:
        if row['path'] == 'draft.md':
            data = draft.read_bytes()
            row['sha256'] = hashlib.sha256(data).hexdigest()
            row['size_bytes'] = len(data)
    (directory / 'manifest.json').write_bytes(w.persisted_bytes(manifest))
    record('rehashed_nondeterministic_draft_history', w.writing_project_history(ws, project_id=pid), False)
    blockers = w.writing_backup_blockers(ws)
    record('rehashed_nondeterministic_draft_backup', {'ok': not blockers, 'diagnostics': blockers}, False)

    ws, c, init, ex, doc = setup(root, 'transition')
    pid, parent = init['project_id'], init['revision_id']
    directory = w._revision_dir(ws, pid, parent)
    parentdoc = json.loads((directory / 'document.json').read_text())
    childdoc = copy.deepcopy(parentdoc)
    childdoc.update(kind='section', target_section_id='s1', parent_revision_id=parent)
    childdoc['sections'][1].update(status='provisional', markdown='Fabricated unrelated-section change [@chk-missing]', citations=['chk-missing'])
    rid = w._revision_identity(project_id=pid, parent_revision_id=parent, context_sha256=w.sha256_canonical(c), document=childdoc)
    files = w._revision_files(workspace=ws, project_id=pid, revision_id=rid, parent_revision_id=parent, context=c, document=childdoc)
    childdir = w._revision_dir(ws, pid, rid)
    childdir.mkdir()
    for name, data in files.items():
        (childdir / name).write_bytes(data)
    w._head_path(ws, pid).write_bytes(w.persisted_bytes({'schema': w.HEAD_SCHEMA, 'project_id': pid, 'revision_id': rid}))
    record('selfconsistent_invalid_parent_transition_history', w.writing_project_history(ws, project_id=pid), False)
    record('selfconsistent_invalid_parent_transition_export', w.export_writing_section(ws, project_id=pid, section_id='s1'), False)
    blockers = w.writing_backup_blockers(ws)
    record('selfconsistent_invalid_parent_transition_backup', {'ok': not blockers, 'diagnostics': blockers}, False)

check_source()
report = {'schema': 'lightweight-research-t3-architect-probes.v1', 'source_root': str(source),
    'snapshot_sha256': handoff['snapshot_sha256'], 'source_hashes_verified_before_after': True,
    'module_file': w.__file__, 'python': sys.version, 'passed': sum(r['passed'] for r in observations),
    'total': len(observations), 'observations': observations}
Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
print(json.dumps({'passed': report['passed'], 'total': report['total'],
    'cases': [{k: r[k] for k in ('case','passed','expected_ok')} | {'observed_ok': r['result']['ok'], 'status': r['result'].get('status')} for r in observations]}, indent=2))
