"""Read hashes/archive data only. Never import, install or run inspected packages."""
from pathlib import Path
import datetime,email.parser,hashlib,json,subprocess,tarfile,tomllib,zipfile
root=Path('<TMP>/vpkb-dependency-source-review');repo=Path.cwd();sha=lambda b:hashlib.sha256(b).hexdigest()
lock=tomllib.loads((repo/'uv.lock').read_text());packages={p['name']:p for p in lock['package']};result=[]
for name in ['docling','docling-slim','docling-core']:
 spec=packages[name];entry=spec['wheels'][0];wheel=root/entry['url'].rsplit('/',1)[-1];raw=wheel.read_bytes();assert sha(raw)==entry['hash'].split(':')[1] and len(raw)==entry['size']
 dest=root/'metadata'/name;dest.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(wheel) as z:
  metadata_name=next(n for n in z.namelist() if n.endswith('/METADATA'));b=z.read(metadata_name);(dest/'METADATA').write_bytes(b);meta=email.parser.Parser().parsestr(b.decode())
  licenses=[]
  for member in z.namelist():
   if not member.endswith('/') and 'license' in member.lower():
    data=z.read(member);target=dest/Path(member).name;target.write_bytes(data);licenses.append({'member':member,'sha256':sha(data),'bytes':len(data),'saved':str(target.relative_to(root))})
  source_members=[n for n in z.namelist() if n.endswith('.py') and '.dist-info/' not in n]
 result.append({'name':name,'version':spec['version'],'wheel_url':entry['url'],'wheel_sha256':sha(raw),'wheel_bytes':len(raw),'lock_hash_and_size_verified':True,'metadata_member':metadata_name,'metadata_sha256':sha(b),'license_expression':meta.get('License-Expression'),'license_files_declared':meta.get_all('License-File',[]),'license_members':licenses,'project_urls':meta.get_all('Project-URL',[]),'requires_docling_distributions':[r for r in meta.get_all('Requires-Dist',[]) if r.startswith('docling')],'python_source_member_count':len(source_members),'python_source_names_sample':source_members[:12],'observation':'exact artifact inspected; no installation, import or parser execution'})
entry=packages['docling']['sdist'];p=root/entry['url'].rsplit('/',1)[-1];assert sha(p.read_bytes())==entry['hash'].split(':')[1] and p.stat().st_size==entry['size']
with tarfile.open(p) as t:
 names=t.getnames();license_members=[n for n in names if 'license' in n.lower()];pkg=next(n for n in names if n.endswith('/PKG-INFO'));info=t.extractfile(pkg).read();(root/'metadata/docling/PKG-INFO').write_bytes(info)
sdist={'name':'docling','version':'2.117.0','url':entry['url'],'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,'license_members':license_members,'all_members':names,'pkg_info_sha256':sha(info),'observation':'Neither locked docling wheel nor sdist contains a separate LICENSE; METADATA/PKG-INFO declare MIT.'}
source_names=['docling_core/types/doc/document.py','docling_core/types/doc/base.py','docling_core/types/base.py','docling_core/types/doc/common/reference.py','docling_core/types/doc/common/scalars.py','docling_core/types/doc/common/constants.py','docling_core/types/doc/items/node.py','docling_core/types/doc/items/content.py','docling_core/types/doc/items/text.py']
extracted=[]
with zipfile.ZipFile(root/'docling_core-2.92.0-py3-none-any.whl') as z:
 for name in source_names:
  b=z.read(name);p=root/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);extracted.append({'wheel_member':name,'sha256':sha(b),'bytes':len(b),'saved':str(p.relative_to(root))})
up=repo/'vendor/claude-obsidian';head=subprocess.check_output(['git','-C',str(up),'rev-parse','HEAD'],text=True).strip();status=subprocess.check_output(['git','-C',str(up),'status','--porcelain','--untracked-files=all'],text=True);detached=subprocess.run(['git','-C',str(up),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
assert head=='9f8c1199047eac2c3828496279fbb7ba9540b90b' and not status and detached
licensebytes=(up/'LICENSE').read_bytes();(root/'vendor-LICENSE').write_bytes(licensebytes)
summary={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Only docling2.117.0/docling-slim2.117.0/docling-core2.92.0 and existing pinned claude-obsidian; artifact/source/license statements, not legal compliance conclusions.','upstream_manifest_sha256':sha((repo/'docs/dependencies/vpkb-000-upstream.json').read_bytes()),'uv_lock_sha256':sha((repo/'uv.lock').read_bytes()),'manifest_status':'Repository two-pin manifest remains pinned; not rewritten by this review.','python_distributions':result,'docling_sdist':sdist,'vendor':{'head':head,'detached':detached,'tracked_and_untracked_clean':not status,'license_sha256':sha(licensebytes),'source_url':'https://github.com/AgriciDaniel/claude-obsidian','license_observation':'LICENSE text identifies MIT; this observation does not cover unrelated packages/models.'},'extracted_read_only_core_sources':extracted,'not_verified':['No parser/model execution or initialization','No optional extras/model artifacts downloaded or installed','No transitive dependency license audit','No source commit/tag resolution for PyPI releases; project URLs are declarations, not exact upstream Git provenance','No legal compliance or permission-to-redistribute conclusion','No actual DoclingDocument parsing or Pydantic validation; extracted files are source text only'],'cache_lookup':'No matching named wheel/sdist/Docling metadata paths found under existing uv caches; downloaded only exact files.pythonhosted.org URLs recorded in uv.lock.'}
(root/'source-license-observation.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'distributions':[(d['name'],d['license_expression'],d['python_source_member_count'],[(x['member'],x['sha256']) for x in d['license_members']]) for d in result],'core_sources':len(extracted),'vendor_license_sha':sha(licensebytes)},indent=2))
