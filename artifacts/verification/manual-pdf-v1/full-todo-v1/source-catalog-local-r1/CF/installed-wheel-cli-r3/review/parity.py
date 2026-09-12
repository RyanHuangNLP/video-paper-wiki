from __future__ import annotations
import hashlib,json,sys,zipfile
from pathlib import Path

root=Path('.work/parallel/source-catalog-v1/terminal-1/source').resolve()
cf=Path('artifacts/verification/manual-pdf-v1/full-todo-v1/source-catalog-local-r1/CF/installed-wheel-cli-r3').resolve()
wheel=next((cf/'wheel').glob('*.whl'))
def row(path: str, data: bytes): return {'path':path,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
def manifest(rows): return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':'),sort_keys=False).encode()).hexdigest()
def filesystem_rows(base:Path, prefix:str, suffix:str):
    pattern=suffix if suffix.startswith('*') else '*'+suffix
    return [row(prefix+'/'+p.relative_to(base).as_posix(),p.read_bytes()) for p in sorted(base.rglob(pattern)) if p.is_file()]
def wheel_rows(prefix:str, rootprefix:str, suffix:str):
    with zipfile.ZipFile(wheel) as z:
        names=sorted(n for n in z.namelist() if n.startswith(rootprefix+'/') and n.endswith(suffix))
        return [row(n,z.read(n)) for n in names]
def group(name,src,wheelr,src_prefix,wheel_prefix):
    sp={x['path'][len(src_prefix):]:x for x in src}; wp={x['path'][len(wheel_prefix):]:x for x in wheelr}
    missing=sorted(set(sp)-set(wp)); extra=sorted(set(wp)-set(sp)); mismatches=[]
    for p in sorted(set(sp)&set(wp)):
        if sp[p]['sha256']!=wp[p]['sha256'] or sp[p]['size_bytes']!=wp[p]['size_bytes']:
            mismatches.append({'path':p,'source':sp[p],'wheel':wp[p]})
    return {'name':name,'pass':not(missing or extra or mismatches),'source_count':len(src),'wheel_count':len(wheelr),'source_manifest_sha256':manifest(src),'wheel_manifest_sha256':manifest(wheelr),'missing':missing,'extra':extra,'mismatches':mismatches,'source_rows':src,'wheel_rows':wheelr}
def group_research(name,src,wheelr):
    sp={x['path'][len('src/video_paper_wiki_research/'):]:x for x in src}; wp={x['path'][len('video_paper_wiki_research/'):]:x for x in wheelr}
    missing=sorted(set(sp)-set(wp)); extra=sorted(set(wp)-set(sp)); mismatches=[]
    for p in sorted(set(sp)&set(wp)):
        if sp[p]['sha256']!=wp[p]['sha256'] or sp[p]['size_bytes']!=wp[p]['size_bytes']: mismatches.append({'path':p,'source':sp[p],'wheel':wp[p]})
    return {'name':name,'pass':not(missing or extra or mismatches),'source_count':len(src),'wheel_count':len(wheelr),'source_manifest_sha256':manifest(src),'wheel_manifest_sha256':manifest(wheelr),'missing':missing,'extra':extra,'mismatches':mismatches,'source_rows':src,'wheel_rows':wheelr}
core_s=filesystem_rows(root/'src/video_paper_wiki','src/video_paper_wiki','.py'); core_w=wheel_rows('video_paper_wiki','video_paper_wiki','.py')
research_s=filesystem_rows(root/'src/video_paper_wiki_research','src/video_paper_wiki_research','.py'); research_w=wheel_rows('video_paper_wiki_research','video_paper_wiki_research','.py')
schema_s=filesystem_rows(root/'schemas','schemas','*.schema.json'); schema_w=wheel_rows('video_paper_wiki/schemas','video_paper_wiki/schemas','.schema.json')
seed_s=filesystem_rows(root/'docs/seed','docs/seed','*.json'); seed_w=wheel_rows('video_paper_wiki/seed','video_paper_wiki/seed','.json')
cat_s=filesystem_rows(root/'catalog','catalog','*'); cat_w=wheel_rows('video_paper_wiki/catalog','video_paper_wiki/catalog','')
tax_s=[row('taxonomy/v1.json',(root/'taxonomy/v1.json').read_bytes())];
with zipfile.ZipFile(wheel) as z: tax_w=[row('video_paper_wiki/taxonomy/v1.json',z.read('video_paper_wiki/taxonomy/v1.json'))]
groups=[group('core_python',core_s,core_w,'src/video_paper_wiki/','video_paper_wiki/'),group_research('research_python',research_s,research_w),group('schemas',schema_s,schema_w,'schemas/','video_paper_wiki/schemas/'),group('seed',seed_s,seed_w,'docs/seed/','video_paper_wiki/seed/'),group('catalog',cat_s,cat_w,'catalog/','video_paper_wiki/catalog/'),group('taxonomy',tax_s,tax_w,'taxonomy/','video_paper_wiki/taxonomy/')]
result={'schema':'full-todo.source-catalog-installed-wheel-cli-r3.resource-parity.v1','candidate_head':'7ed55cfc2590268488c7bb34c18b572886fb950c','candidate_tree':'f0734fa1834e126c749bed302c1c6a578f1c2fd2','wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'wheel_size_bytes':wheel.stat().st_size,'groups':groups}
out=cf/'resource-parity.json'; out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=False)+'\n',encoding='utf-8'); print(out)
