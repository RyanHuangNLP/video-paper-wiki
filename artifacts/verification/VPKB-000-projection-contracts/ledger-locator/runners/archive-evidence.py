from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET,datetime
R=Path('<REPO>');BASE=R/'artifacts/verification/VPKB-000-projection-contracts';L=BASE/'ledger-locator';D=BASE/'dependency-source';TMP=Path('<TMP>');H=lambda b:hashlib.sha256(b).hexdigest();entries={}
for p in (L,D):p.mkdir(exist_ok=True)
def norm(text):
 return text.replace(str(R),'<REPO>').replace('<USER_HOME>','<USER_HOME>').replace('<TMP>','<TMP>')
def put(src,dest,verbatim=False):
 src=Path(src);raw=src.read_bytes();b=raw if verbatim else norm(raw.decode()).encode()
 if src.suffix in ('.log','.stdout','.stderr'):b=('\n'.join(x.rstrip(' \t') for x in b.decode().splitlines()).rstrip('\n')+'\n').encode() if b else b
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
 entries[str(dest.relative_to(BASE))]={'original_path':norm(str(src)),'raw_sha256':H(raw),'raw_bytes':len(raw),'archived_sha256':H(b),'archived_bytes':len(b),'transform':'byte-exact' if b==raw else 'path tokens; plain logs also remove trailing spaces/tabs and excess blank EOF'}
def write(dest,value):dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
A=TMP/'vpl-acceptance'
for name in ['source-files.json','python312-source-after.json','python313-source-after.json','python312-result.json','python313-result.json','python312.log','python313.log','wheel-result.json','wheel-build.log','wheel-install.log','wheel-smoke.log','wheel-smoke.py']:put(A/name,L/'local'/name)
for name in ['vpl-run-suites.py','vpl-run-wheel.py']:put(TMP/name,L/'runners'/name)
for name in ['vpl-steward-build-vectors.py','vpl-steward-vectors.json','vpl-steward-review-outline.md','vpl-steward-review-candidate.py','vpl-steward-review-candidate.json','vpl-steward-review-final.json','vpl-steward-focus.log']:put(TMP/name,L/'independent'/name)
for name in ['vpkb-ledger-locator-spec-review.json','vpkb-locator-contract-review-builder.md']:put(TMP/name,L/'spec-review'/name)
for name in ['vpl-candidate.json','vpl-target2.log']:put(TMP/name,L/'builder'/name)
P=TMP/'vpl-target2/test_pinned_public_cli_preserv0'
for name in ['commands.json','codec-transport-results.json','source-provenance.json','source-after.json','fixture-document.json']:put(P/name,L/'public-cli'/name)
for row in json.loads((P/'commands.json').read_text()):
 for key in ['stdout_file','stderr_file']:put(P/row[key],L/'public-cli'/row[key])
for name in ['claim-ledger.json','source-ledger.json']:put(P/'v/wiki/meta/ledgers'/name,L/'public-cli/persisted'/name)
junits={}
for label,path in [('python312',A/'python312.xml'),('python313',A/'python313.xml'),('independent-focused',TMP/'vpl-steward-focus.xml'),('builder-targeted',TMP/'vpl-target2.xml')]:
 root=ET.parse(path).getroot();ss=list(root) if root.tag=='testsuites' else [root];counts={k:sum(int(s.get(k,0)) for s in ss) for k in ['tests','failures','errors','skipped']}
 junits[label]={'original_path':norm(str(path)),'raw_sha256':H(path.read_bytes()),'raw_bytes':path.stat().st_size,'counts':counts,'suite_seconds':sum(float(s.get('time',0)) for s in ss),'archived_xml':False}
write(L/'junit-summary.json',junits)
source=json.loads((A/'source-files.json').read_text());assert source['file_count']==288
assert all(H((R/n).read_bytes())==s for n,s in source['files'].items())
for label in ['312','313']:
 result=json.loads((A/('python'+label+'-result.json')).read_text());assert result['exit_code']==0 and result['counts']=={'tests':1464,'failures':0,'errors':0,'skipped':0};assert json.loads((A/('python'+label+'-source-after.json')).read_text())['files']==source['files']
wheel=json.loads((A/'wheel-result.json').read_text());assert all(x['exit_code']==0 for x in wheel['commands'])
write(L/'local-results.json',{'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'baseline_head':'208c206801214bb8f6e2f58f995ad7755ce87332','candidate_kind':'working-tree candidate; no candidate commit yet','contract_revision':1,'contract_sha256':'493fc3d135141512c7956f3729726ae72febbb1a34cc8cd5669add96af16e191','source_count':288,'source_snapshot_sha256':source['snapshot_sha256'],'source_before_after_equal':True,'local_status':'passed','full_tests':{'Python 3.12.14':junits['python312']['counts'],'Python 3.13.13':junits['python313']['counts']},'independent_probes':{'passed':54,'failed':0,'independent_golden_vectors':{'positive':10,'negative':21,'relations':3}},'focused_tests':junits['independent-focused']['counts'],'builder_targeted':junits['builder-targeted']['counts'],'wheel':{'status':'passed','commands_exit_codes':[x['exit_code'] for x in wheel['commands']],'sha256':wheel['wheel_sha256'],'schemas':18,'archive_included':False},'public_cli':{'commands':9,'exit_codes':[x['exit_code'] for x in json.loads((P/'commands.json').read_text())],'expected_refusal':'unsupported uncertain relation; context accepted','source_inventory_count':201,'inventory_before_after_equal':True,'steward_reran_cli':False},'ci_status':'not observed for new candidate; previous runtime CI is historical only','limits':['Local evidence only; Architect final candidate/CI acceptance remains separate.','Standalone ledger locator slice, not complete projection inputs/history/SQLite/generation or VPKB-000 completion.','Synthetic metadata transport only: no parser, artifact closure, scientific correctness, human acceptance or real Vault authorization.','Two before/after source snapshots do not claim continuous filesystem monitoring.']})
DEP=TMP/'vpkb-dependency-source-review'
for name in ['source-license-observation.json','locked-artifacts.json','collect.py','vendor-LICENSE']:put(DEP/name,D/name,verbatim=name in ['source-license-observation.json','locked-artifacts.json','vendor-LICENSE'])
for p in sorted((DEP/'metadata').rglob('*')):
 if p.is_file():put(p,D/p.relative_to(DEP),verbatim=True)
write(L/'archive-manifest.json',{'normalization':'Replace repository root with <REPO>, remaining user home with <USER_HOME>, and <TMP> with <TMP>. Plain logs/stdout/stderr additionally remove per-line trailing spaces/tabs and excess blank EOF; preserve all internal whitespace and numbers. JSON numeric/wire content unchanged. Embedded source/log/JUnit SHA fields always describe originals, not normalized copies. JUnit XML is not copied.','files':{k:v for k,v in entries.items() if k.startswith('ledger-locator/')}})
write(D/'archive-manifest.json',{'normalization':'Observation JSON, lock URL list, METADATA, PKG-INFO and LICENSE are byte-exact copies. Collector is a normalized historical script. All source/ archive saved-path entries in the original observation refer to <TMP>/vpkb-dependency-source-review, not files in this repository.','files':{k:v for k,v in entries.items() if k.startswith('dependency-source/')}})
print(json.dumps({'locator_archived_files':len(list(L.rglob('*'))),'dependency_archived_files':len(list(D.rglob('*'))),'source_still_matches':True}))
