from __future__ import annotations
import difflib,hashlib,json,re
from pathlib import Path
ROOT=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
CF=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/CF'
OLD=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/rejected-r1-source'
NEW=ROOT/'.work/parallel/source-catalog-v1/terminal-1/source'
R1M=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/local-candidate-r1.json'
R2M=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/local-candidate-r2.json'
def digest(p):
 b=p.read_bytes();return {'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)}
def manifest_map(p):return {x['path']:x for x in json.loads(p.read_bytes())['files']}
r1m,r2m=manifest_map(R1M),manifest_map(R2M)
paths=sorted(set(r1m)|set(r2m))
rows=[]
for rel in paths:
 old=OLD/rel;new=NEW/rel
 od=digest(old);nd=digest(new)
 rows.append({'path':rel,'r1_manifest':r1m[rel],'r2_manifest':r2m[rel],'r1_actual':od,'r2_actual':nd,'byte_identical':old.read_bytes()==new.read_bytes()})
# contracts diff normalized to exact helper rename only
oldc=(OLD/'src/video_paper_wiki/contracts.py').read_text();newc=(NEW/'src/video_paper_wiki/contracts.py').read_text()
diff=list(difflib.unified_diff(oldc.splitlines(keepends=True),newc.splitlines(keepends=True),fromfile='r1',tofile='r2'))
nonrename=[]
for line in diff:
 if line.startswith(('---','+++','@@',' ')): continue
 if line.startswith('-def _build_registry') or line.startswith('+def _schema_registry'): continue
 if line.startswith('-') and '_build_registry()' in line: continue
 if line.startswith('+') and '_schema_registry()' in line: continue
 nonrename.append(line.rstrip('\n'))
report={'schema':'full-todo.source-catalog-r1-r2-path-compare.v1','paths_total':len(paths),'unchanged_count':sum(x['byte_identical'] for x in rows),'changed_count':sum(not x['byte_identical'] for x in rows),'changed_paths':[x['path'] for x in rows if not x['byte_identical']],'all_actuals_match_manifests':all(x['r1_manifest']['sha256']==x['r1_actual']['sha256'] and x['r1_manifest']['size_bytes']==x['r1_actual']['size_bytes'] and x['r2_manifest']['sha256']==x['r2_actual']['sha256'] and x['r2_manifest']['size_bytes']==x['r2_actual']['size_bytes'] for x in rows),'contracts_diff_only_three_helper_rename':not nonrename,'contracts_diff_nonrename_lines':nonrename,'rows':rows}
print(json.dumps(report,indent=2,sort_keys=True))
