from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
root=Path('.work/parallel/source-catalog-v1/terminal-1/source').resolve(); cf=Path('artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/CF/installed-wheel-cli-r3').resolve()
r3=json.loads((root.parent.parent.parent.parent/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/local-candidate-r3.json').read_text()) if False else json.loads((Path('artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/local-candidate-r3.json')).read_text())
r2=json.loads((Path('artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/local-candidate-r2.json')).read_text())
rows=[]
for x in r3['files']:
 b=(root/x['path']).read_bytes(); rows.append({'path':x['path'],'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b),'matches_r3_record':hashlib.sha256(b).hexdigest()==x['sha256']})
changed=[x['path'] for x,y in zip(r2['files'],r3['files']) if x['sha256']!=y['sha256']]
status=subprocess.run(['git','-C',str(root),'status','--short'],capture_output=True,text=True).stdout.splitlines()
source_catalog=(root/'src/video_paper_wiki/source_catalog.py').read_text()
checks={
 'snapshot_matches_r3_record':all(x['matches_r3_record'] for x in rows) and r3['snapshot_sha256']=='23229333c19462d6cba2423f1ee215523d126a54d1bddfa8b30aa7e3d1f293c5',
 'changed_from_r2_exactly':changed==['src/video_paper_wiki/source_catalog.py','tests/unit/test_source_catalog.py'],
 'status_allowed_paths_exactly_19':len(status)==19,
 'handler_imports_envelopes':('from video_paper_wiki.envelope import emit_error, emit_success' in source_catalog),
 'handler_returns_integer':('return emit_error(command, exc.code, exc.message, exc.details, exit_code=exc.exit_code)' in source_catalog and 'return emit_success(command, result)' in source_catalog),
 'staging_conflict_exit_75_fallback':('getattr(exc, "exit_code", 75 if code == "STAGING_CONFLICT" else 2)' in source_catalog),
 'direct_dispatch_separate':('def _dispatch_source_catalog_command(args):' in source_catalog and 'def run_source_catalog_command(args):' in source_catalog),
 'targeted_regressions_exit_0':Path(cf/'review/targeted.returncode').read_text().strip()=='0',
}
result={'schema':'full-todo.source-catalog-installed-wheel-cli-r3.independent-review.v1','candidate_head':r3['head'],'candidate_tree':r3['tree'],'candidate_snapshot_sha256':r3['snapshot_sha256'],'r3_files':rows,'r2_snapshot_sha256':r2['snapshot_sha256'],'changed_from_r2':changed,'git_status_lines':status,'checks':checks,'pass':all(checks.values())}
(cf/'review/independent-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'pass':result['pass'],'changed_from_r2':changed,'status_count':len(status),'checks':checks},sort_keys=True))
