from pathlib import Path
from urllib.parse import urlsplit
from email.parser import BytesParser
import datetime,hashlib,json,subprocess,tarfile,tomllib,zipfile
root=Path('<REPO>');p=Path('<TMP>/vpkb-dependency-source-review');o=json.loads((p/'source-license-observation.json').read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest();lock=tomllib.loads((root/'uv.lock').read_text());byname={x['name']:x for x in lock['package']}
assert sha((root/'uv.lock').read_bytes())==o['uv_lock_sha256']
assert sha((root/'docs/dependencies/vpkb-000-upstream.json').read_bytes())==o['upstream_manifest_sha256']
counts={}
for d in o['python_distributions']:
 art=p/Path(urlsplit(d['wheel_url']).path).name;b=art.read_bytes();entry=next(x for x in byname[d['name']]['wheels'] if x['url']==d['wheel_url']);assert len(b)==d['wheel_bytes']==entry['size'] and sha(b)==d['wheel_sha256']==entry['hash'].split(':')[1]
 with zipfile.ZipFile(art) as z:
  meta=z.read(d['metadata_member']);assert sha(meta)==d['metadata_sha256']
  parsed=BytesParser().parsebytes(meta);assert parsed['Name']==d['name'] and parsed['Version']==d['version'] and parsed['License-Expression']=='MIT'
  names=sorted(x for x in z.namelist() if not x.endswith('/') and 'license' in x.lower());assert names==sorted(x['member'] for x in d['license_members'])
  for x in d['license_members']:
   lb=z.read(x['member']);assert sha(lb)==x['sha256'] and len(lb)==x['bytes'] and lb==(p/x['saved']).read_bytes()
  counts[d['name']]=len([x for x in z.namelist() if x.endswith('.py')])
sd=o['docling_sdist'];entry=byname['docling']['sdist'];art=p/Path(urlsplit(sd['url']).path).name;b=art.read_bytes();assert len(b)==sd['bytes']==entry['size'] and sha(b)==sd['sha256']==entry['hash'].split(':')[1]
with tarfile.open(art) as t:
 assert t.getnames()==sd['all_members'];assert not [x for x in t.getnames() if 'license' in x.lower()];assert sha(t.extractfile('docling-2.117.0/PKG-INFO').read())==sd['pkg_info_sha256']
with zipfile.ZipFile(p/'docling_core-2.92.0-py3-none-any.whl') as z:
 for x in o['extracted_read_only_core_sources']:
  b=z.read(x['wheel_member']);assert sha(b)==x['sha256'] and len(b)==x['bytes'] and b==(p/x['saved']).read_bytes()
v=root/'vendor/claude-obsidian';head=subprocess.check_output(['git','-C',str(v),'rev-parse','HEAD']).decode().strip();assert head==o['vendor']['head']
assert not subprocess.check_output(['git','-C',str(v),'status','--porcelain','--untracked-files=all'])
assert subprocess.run(['git','-C',str(v),'symbolic-ref','-q','HEAD'],capture_output=True).returncode==1
assert sha((v/'LICENSE').read_bytes())==o['vendor']['license_sha256']
r={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reviewer':'Architect','status':'independent bounded source/artifact/license-declaration observations verified','source_observation_sha256':sha((p/'source-license-observation.json').read_bytes()),'uv_lock_sha256':o['uv_lock_sha256'],'upstream_manifest_sha256':o['upstream_manifest_sha256'],'verified_wheels':3,'verified_sdist':1,'python_member_counts':counts,'verified_source_texts':9,'verified_vendor_head':head,'manifest_status':'pinned, unchanged','scope':'VPKB-000 named dependency/source-digest/license inventory evidence; not a human license gate decision','not_claimed':['Legal compliance or redistribution permission','Exact Git commit provenance for PyPI releases','Transitive dependency or model license audit','Parser execution, models, source/artifact closure or production acceptance']}
Path('<TMP>/vpkb-dependency-architect-review.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
