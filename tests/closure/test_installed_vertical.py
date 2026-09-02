from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import pty
import select
import stat
import time
from pathlib import Path

import pytest


ROOT=Path(__file__).resolve().parents[2]

# The pinned upstream runtime permits exactly one volatile root timestamp in
# each chunk/index record.  Those fixed-width timestamps consequently change
# only these directly-derived catalog export cells on a deterministic rebuild.
_REBUILD_EXPORT_VOLATILE_CELLS={
    '$':('catalog_generation_sha256',),
    'search_catalog_inputs':('raw_sha256[upstream-chunk|upstream-bm25]',),
    'search_chunks':('raw_sha256',),
    'search_catalog_meta':('catalog_generation_sha256','upstream_chunk_set_sha256','upstream_index_raw_sha256'),
}


def _normalized_catalog_export(raw:bytes,authority:dict)->dict:
    from video_paper_wiki.jcs import canonicalize

    # First prove that every unmodified cell is the independently reconstructed
    # value for this run.  Normalization is never applied to an unbound export.
    assert hashlib.sha256(raw).hexdigest()==authority['export_sha256']
    value=json.loads(raw)
    generation=json.loads(json.dumps(authority['generation']))
    assert value['catalog_generation_sha256']==authority['meta']['catalog_generation_sha256']
    for row in generation['upstream_chunks']:row['raw_sha256']=row['runtime_sha256']
    generation['upstream_bm25']['raw_sha256']=generation['upstream_bm25']['runtime_sha256']
    normalized_generation=hashlib.sha256(canonicalize(generation)).hexdigest()
    normalized_chunk_set=hashlib.sha256(canonicalize(generation['upstream_chunks'])).hexdigest()
    value['catalog_generation_sha256']=normalized_generation
    for table in value['tables']:
        columns=table['columns']
        if table['name']=='search_catalog_inputs':
            kind=columns.index('input_kind');digest=columns.index('raw_sha256');runtime=columns.index('runtime_sha256')
            for row in table['rows']:
                if row[kind] in {'upstream-chunk','upstream-bm25'}:
                    assert row[runtime] is not None
                    row[digest]=row[runtime]
        elif table['name']=='search_chunks':
            digest=columns.index('raw_sha256');runtime=columns.index('runtime_sha256')
            for row in table['rows']:row[digest]=row[runtime]
        elif table['name']=='search_catalog_meta':
            for row in table['rows']:
                row[columns.index('catalog_generation_sha256')]=normalized_generation
                row[columns.index('upstream_chunk_set_sha256')]=normalized_chunk_set
                runtime=row[columns.index('upstream_index_runtime_sha256')]
                row[columns.index('upstream_index_raw_sha256')]=runtime
    return value


def _normalized_query(value:dict)->dict:
    copied=json.loads(json.dumps(value))
    copied['catalog_generation_sha256']='<runtime-timestamp-derived>'
    return copied


def _normalized_report(value:dict)->dict:
    copied=json.loads(json.dumps(value))
    copied['catalog_generation_sha256']='<runtime-timestamp-derived>'
    return copied


def _material_hash()->str:
    digest=hashlib.sha256()
    for base in (ROOT/'src',ROOT/'operator/src',ROOT/'schemas',ROOT/'pyproject.toml',ROOT/'operator/pyproject.toml'):
        paths=[base] if base.is_file() else sorted(p for p in base.rglob('*') if p.is_file())
        for path in paths:digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@pytest.fixture(scope='session')
def installed_cli(tmp_path_factory):
    # CI installs the locked environment before switching uv to offline mode.
    # Reuse that job-local uv cache, while building and installing the product
    # wheels into a fresh checkout-external environment with network disabled.
    uv_raw=shutil.which('uv')
    assert uv_raw is not None,'the test job must provide its pinned uv on PATH'
    uv=Path(uv_raw).resolve()
    assert uv.is_file() and os.access(uv,os.X_OK)
    uv_version=subprocess.run([str(uv),'--version'],check=True,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True).stdout.strip()
    assert uv_version.split()[:2]==['uv','0.12.7'],uv_version
    wheel_python=Path(sys.executable).resolve()
    assert wheel_python.is_file() and os.access(wheel_python,os.X_OK)
    base=tmp_path_factory.mktemp('vpwiki-closure-installed');venv=base/'venv'
    assert ROOT not in base.parents and base!=ROOT
    wheels=base/'wheels';wheels.mkdir()
    uv_env={**os.environ,'UV_OFFLINE':'1','UV_PYTHON_DOWNLOADS':'never'}
    # Do not inherit an operator workstation's local flat-index shortcut.  The
    # locked CI setup has already populated uv's job cache; offline resolution
    # must succeed from that cache or fail closed without attempting a network.
    uv_env.pop('UV_FIND_LINKS',None)
    for project in (ROOT,ROOT/'operator'):
        subprocess.run([str(uv),'build','--offline','--wheel','--out-dir',str(wheels),str(project)],
            check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=uv_env)
    subprocess.run([str(uv),'venv','--python',str(wheel_python),str(venv)],check=True,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=uv_env)
    python=venv/'bin/python';artifacts=sorted(str(p) for p in wheels.glob('*.whl'))
    assert len(artifacts)==2
    subprocess.run([str(uv),'pip','install','--offline','--python',str(python),*artifacts],
        check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=uv_env)
    return venv/'bin'


def _env(bin_dir:Path,tmp_path:Path)->dict[str,str]:
    home=tmp_path/'home';home.mkdir(exist_ok=True)
    process_tmp=tmp_path/'tmp';process_tmp.mkdir(exist_ok=True)
    return {'PATH':str(bin_dir)+':/usr/bin:/bin','HOME':str(home),'TMPDIR':str(process_tmp),'PYTHONDONTWRITEBYTECODE':'1'}


def _json(argv,*,cwd,env,expected=0,_evidence_out=None,_phase=None):
    result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
    assert result.returncode==expected,(argv,result.returncode,result.stdout,result.stderr)
    try:value=json.loads(result.stdout)
    except Exception:
        lines=result.stdout.splitlines();assert len(lines)==1,(argv,lines,result.stderr)
        value=json.loads(lines[0])
    if _evidence_out is not None:
        _evidence_out.append({'phase':_phase,'argv':[str(x) for x in argv],'returncode':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr,'prompt':None,'prompt_count':0,'token_write_count':0,
            'canonical_single_line':result.stdout==json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'})
    return value


def _pty_json(argv,token,*,cwd,env,_evidence_out=None,_phase=None):
    master,slave=pty.openpty();read_fd,write_fd=os.pipe();proc=subprocess.Popen([str(x) for x in argv],cwd=cwd,env=env,stdin=slave,stderr=slave,stdout=write_fd,close_fds=True)
    os.close(slave);os.close(write_fd);transcript=bytearray();prompt=("Type "+repr(token)+" to run the pinned upstream command: ").encode();sent=False;deadline=time.monotonic()+180
    writes=0
    try:
        while proc.poll() is None:
            if time.monotonic()>deadline:proc.kill();raise TimeoutError(argv)
            ready,_,_=select.select([master],[],[],0.25)
            if ready:
                try:part=os.read(master,65536)
                except OSError:part=b''
                transcript.extend(part)
                if not sent and prompt in transcript:os.write(master,token.encode()+b'\n');sent=True;writes+=1
        stdout=b''
        while True:
            part=os.read(read_fd,65536)
            if not part:break
            stdout+=part
    finally:os.close(master);os.close(read_fd)
    assert sent and proc.returncode==0,(argv,proc.returncode,bytes(transcript),stdout)
    try:value=json.loads(stdout)
    except Exception:
        lines=stdout.splitlines();assert len(lines)==1,(argv,lines,bytes(transcript));value=json.loads(lines[0])
    if _evidence_out is not None:
        decoded=stdout.decode('utf-8');transcript_text=bytes(transcript).decode('utf-8','replace')
        _evidence_out.append({'phase':_phase,'argv':[str(x) for x in argv],'returncode':proc.returncode,
            'stdout':decoded,'stderr':transcript_text,'prompt':prompt.decode(),'prompt_count':bytes(transcript).count(prompt),
            'token_write_count':writes,'canonical_single_line':decoded==json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',
            'traceback':b'Traceback' in stdout or b'Traceback' in transcript})
    return value,bytes(transcript)


@pytest.fixture(scope='session')
def installed_vertical_session(installed_cli,tmp_path_factory):
    """One ordered installed-wheel evidence chain shared by the mapped nodes."""
    root=tmp_path_factory.mktemp('vpwiki-installed-vertical');fixture_script=ROOT/'tests/closure/_installed_fixture_builder.py'
    raw=subprocess.run([str(installed_cli/'python'),str(fixture_script),str(root/'fixture')],
        cwd=root,env=_env(installed_cli,root),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    fixture=json.loads(raw.stdout);source=root/'source-vault';restore=root/'restore-vault'
    checkout=root/'checkout';checkout.mkdir();(checkout/'pyproject.toml').write_text('[project]\nname="video-paper-wiki"\nversion="0"\n')
    env=_env(installed_cli,root);env['VPWIKI_BLOB_ROOT']=str(root/'blobs');(root/'blobs').mkdir()
    subprocess.run(['git','init','-q'],cwd=checkout,env=env,check=True);subprocess.run(['git','add','pyproject.toml'],cwd=checkout,env=env,check=True)
    subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],cwd=checkout,env=env,check=True)
    admin=installed_cli/'vpwiki-admin';vpwiki=installed_cli/'vpwiki';upstream=ROOT/'vendor/claude-obsidian'
    process_evidence=[];refusal_effects={};operator_audits={};audit_dir=root/'operator-audit';audit_dir.mkdir()
    audit_launcher=ROOT/'tests/closure/_installed_operator_audit.py'
    def audited_admin(phase,argv):
        audit_path=audit_dir/(phase+'.json');operator_audits[phase]=audit_path
        return [installed_cli/'python',audit_launcher,audit_path,admin,*argv[1:]]
    init_argv=[admin,'--upstream-root',upstream,'init',source,'--operation-id','vertical-init','--generated-at','2026-09-02T00:00:00Z']
    before=_tree_snapshot(root);refusal=_json(init_argv,cwd=checkout,env=env,expected=2,_evidence_out=process_evidence,_phase='init-refusal');after=_tree_snapshot(root);refusal_effects['init']=(before,after)
    assert refusal['error']['code']=='OPERATOR_CONFIRMATION_REQUIRED' and before==after
    dry,init_plan_transcript=_pty_json(init_argv,'init '+str(source),cwd=checkout,env=env,_evidence_out=process_evidence,_phase='init-plan');approval=dry['approved_plan_sha256']
    applied,init_apply_transcript=_pty_json([*init_argv,'--approved-plan-sha256',approval,'--apply'],'init '+str(source),cwd=checkout,env=env,_evidence_out=process_evidence,_phase='init-apply')
    assert applied['status']=='complete'
    # Establish the real domain genesis while the pinned init Vault is still
    # pristine.  Later captures are claimed by the canonical successor.
    from video_paper_wiki.jcs import canonicalize
    from video_paper_wiki.publication import stage_publication_request
    bootstrap_payload={'wiki/meta/records/bootstrap.json':canonicalize({'fixture':'installed-vertical-bootstrap'})}
    original_cwd=Path.cwd();os.chdir(checkout)
    try:
        stage_publication_request(batch_id='vertical-bootstrap',operation_id='vertical-bootstrap',
            operation_type='generic',payloads=bootstrap_payload,claimed_input_paths=[
                'wiki/meta/ledgers/claim-ledger.json','wiki/meta/ledgers/source-ledger.json'])
    finally:os.chdir(original_cwd)
    bootstrap_source=root/'bootstrap-source/publication-input';bootstrap_source.parent.mkdir();shutil.copytree(
        checkout/'.work/vertical-bootstrap/publication-input',bootstrap_source)
    shutil.rmtree(checkout/'.work/vertical-bootstrap')
    bootstrap_prepared=_json([vpwiki,'publication','prepare','--request',
        bootstrap_source/'knowledge-publication-request.v1.json','--batch-id','vertical-bootstrap'],cwd=checkout,env=env)['data']
    bootstrap_authority=_json([vpwiki,'publication','inspect','--prepared',bootstrap_prepared['request_path'],
        '--operation-id','vertical-bootstrap','--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data']
    bootstrap_argv=[admin,'transaction','apply','--bundle',checkout/'.work/vertical-bootstrap/transaction-inspect/bundle.json',
        '--vault-root',source,'--upstream-root',upstream,'--approved-plan-sha256',
        bootstrap_authority['transaction']['inspection']['approval_sha256']]
    _json(bootstrap_argv,cwd=checkout,env=env,expected=2);_pty_json(bootstrap_argv,'transaction apply',cwd=checkout,env=env)
    # Run the four installed plan/prepare/capture chains and apply each inspected
    # transaction.  Fixture construction itself is not counted as product evidence.
    capture_evidence=[];paper_public=[]
    from tests.support import make_approval_ref
    from video_paper_wiki.upstream_adapter import verify_pinned_source_id
    for index in range(1,4):
        payload=(root/'fixture'/f'paper-{index}.pdf').read_bytes();digest=hashlib.sha256(payload).hexdigest();(root/'blobs'/digest).write_bytes(payload)
        request=root/'fixture'/f'paper-{index}.request.json';planned=_json([vpwiki,'ingest','plan','--request',request],cwd=checkout,env=env)['data'];plan=planned['plan']
        approval_path=root/'fixture'/f'paper-{index}.runtime-approval.json';approval_path.write_bytes(canonicalize(make_approval_ref(plan,input_sha256=digest)))
        prepared=_json([vpwiki,'ingest','prepare','--plan',planned['plan_path'],'--approval-ref',approval_path],cwd=checkout,env=env)['data']['request_path']
        operation=f'vertical-paper-{index}-capture';created=_json([vpwiki,'capture','inspect','--prepared',prepared,'--operation-id',operation,'--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data']
        assert created['disposition']=='create';txapproval=created['upstream_authority']['transaction']['inspection']['approval_sha256'];bundle=checkout/f'.work/vertical-paper-{index}/transaction-inspect/bundle.json'
        argv=[admin,'transaction','apply','--bundle',bundle,'--vault-root',source,'--upstream-root',upstream,'--approved-plan-sha256',txapproval]
        _json(argv,cwd=checkout,env=env,expected=2);_pty_json(argv,'transaction apply',cwd=checkout,env=env)
        reused=_json([vpwiki,'capture','inspect','--prepared',prepared,'--operation-id',operation,'--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data'];assert reused['disposition']=='reuse'
        paper_public.append({'plan':planned,'inspection':created,'reuse':reused})
        capture_evidence.append({'sha256':digest,'stored_path':created['inspection']['stored_path'],
            'source_id':verify_pinned_source_id(created['inspection']['stored_path'],digest,upstream_root=upstream),'reuse':True})
    code=(root/'fixture/code.py').read_bytes();code_sha=hashlib.sha256(code).hexdigest();(root/'blobs'/code_sha).write_bytes(code)
    planned=_json([vpwiki,'code-map','plan','--request',root/'fixture/code.request.json'],cwd=checkout,env=env)['data'];approval_path=root/'fixture/code.runtime-approval.json';approval_path.write_bytes(canonicalize(make_approval_ref(planned['plan'],input_sha256=code_sha)))
    prepared=_json([vpwiki,'code-map','prepare','--plan',planned['plan_path'],'--approval-ref',approval_path,'--source-path','train.py'],cwd=checkout,env=env)['data']['request_path']
    created=_json([vpwiki,'code-map','inspect','--prepared',prepared,'--operation-id','vertical-code-capture','--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data'];txapproval=created['upstream_authority']['transaction']['inspection']['approval_sha256'];bundle=checkout/'.work/vertical-code/transaction-inspect/bundle.json'
    argv=[admin,'transaction','apply','--bundle',bundle,'--vault-root',source,'--upstream-root',upstream,'--approved-plan-sha256',txapproval];_json(argv,cwd=checkout,env=env,expected=2);_pty_json(argv,'transaction apply',cwd=checkout,env=env)
    reused=_json([vpwiki,'code-map','inspect','--prepared',prepared,'--operation-id','vertical-code-capture','--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data'];assert reused['disposition']=='reuse'
    # Publish the canonical records/history/artifact authorities as one generic
    # fixture transaction, then publish exactly the installed compiler bytes.
    material=json.loads((root/'fixture/compile-input.json').read_bytes());material['code'][0]['manifest']=created['manifest']
    actual_source=created['manifest']['capture']['source_id']
    from video_paper_wiki import identity
    from video_paper_wiki.contracts import DOCLING_CORE_VERSION,DOCLING_VERSION
    from video_paper_wiki.ledger_locator import encode_ledger_evidence
    shared_config=canonicalize({'profile':'installed-vertical'})
    shared_model=canonicalize({'models':[]})
    shared_fp=identity.pipeline_fingerprint({'engine':'docling','engine_version':DOCLING_VERSION,
        'core_version':DOCLING_CORE_VERSION,'config_sha256':hashlib.sha256(shared_config).hexdigest(),
        'model_manifest_sha256':hashlib.sha256(shared_model).hexdigest()})
    extractions=[]
    for index,(paper,capture) in enumerate(zip(material['papers'],capture_evidence,strict=True),1):
        document=canonicalize({'text':f'Synthetic extraction {index}','score':index})
        base=f".raw/derived/{capture['sha256']}/docling/{shared_fp}"
        run_id=f'run-installed-{index}'
        run={'schema':'video-paper-wiki.run-manifest.v1','run_id':run_id,
            'tool_versions':{'vpwiki':'0.1.0','python':'3.12','docling':DOCLING_VERSION,'docling_core':DOCLING_CORE_VERSION},
            'input_hashes':{'parser_config_sha256':hashlib.sha256(shared_config).hexdigest(),
                'model_manifest_sha256':hashlib.sha256(shared_model).hexdigest()},
            'output_hashes':{'document_json_sha256':hashlib.sha256(document).hexdigest()},
            'started_at':'2026-09-02T00:00:00Z','ended_at':'2026-09-02T00:00:01Z','error_code':None,
            'pipeline_fingerprint':shared_fp}
        run_raw=canonicalize(run);extractions.append({'base':base,'document':document,'run':run_raw,'run_id':run_id})
        claim=paper['claims'][0];claim['evidence']=[{'relation':'supports','kind':'pdf','source_id':capture['source_id'],
            'page':1,'ref':'#/texts/0','artifact_path':base+'/document.json','artifact_sha256':hashlib.sha256(document).hexdigest(),
            'text_sha256':hashlib.sha256(claim['canonical_claim_text'].encode()).hexdigest(),'bbox':[0,0,10,10],'charspan':[0,1]}]
        fingerprint=identity.evidence_fingerprint(claim['evidence']);previous=None;events=[]
        for old in reversed(paper['events']):
            event={**old,'event_id':'ase-'+'0'*20,'previous_event_id':previous,'evidence_fingerprint':fingerprint};event['event_id']=identity.assessment_event_id(event);events.append(event);previous=event['event_id']
        paper['events']=events;paper['assessment_heads']={claim['claim_id']:events[-1]['event_id']}
    for paper,capture,extraction in zip(material['papers'],capture_evidence,extractions,strict=True):
        paper['record']['source_ids']=[capture['source_id']]
        paper['record']['active_extraction_path']=extraction['base']+'/document.json'
        paper['record']['active_extraction_sha256']=hashlib.sha256(extraction['document']).hexdigest()
    alignment=material['code'][0]['alignment']
    # Capability status is carried by the validated alignment.  This fixture
    # does not invent an additional repository-owned scientific claim.
    material['code'][0]['repo_record']['capability_claim_refs']=[]
    aligned_paper=next(paper for paper in material['papers'] if paper['record']['paper_id']==alignment['paper_id'])
    alignment['officiality']['evidence']=[
        {key:value for key,value in aligned_paper['claims'][0]['evidence'][0].items() if key!='relation'}]
    for capability in alignment['capabilities']:
        for locator in capability['locators']:locator['source_id']=actual_source
    claims={}
    for paper in material['papers']:
        claim=paper['claims'][0];claims[claim['claim_id']]={'text':claim['canonical_claim_text'],'risk':'normal','assessment':'accepted','confidence':'high',
            'location':{'path':'wiki/papers/'+identity.paper_page_slug(paper['record']['paper_id'])+'.md','anchor':'^'+claim['claim_id']},
            'reviewed_at':'2026-09-02','notes':None,'supersedes':None,'evidence':[encode_ledger_evidence(x) for x in claim['evidence']]}
    raw_path=created['manifest']['capture']['stored_path']
    sources={actual_source:{
        'origin':{'kind':'file','locator':raw_path},'content_kind':'code','title':'Synthetic code fixture','authority':'primary',
        'content_sha256':code_sha,'ingested_at':'2026-09-02','retrieved_at':None,'refresh_due':'2099-01-01','review_status':'active',
        'independence_key':'synthetic-fixture-code','pages':[],'supersedes':None}}
    for index,capture in enumerate(capture_evidence,1):
        sources[capture['source_id']]={'origin':{'kind':'file','locator':capture['stored_path']},'content_kind':'document',
            'title':f'Synthetic paper {index}','authority':'primary','content_sha256':capture['sha256'],
            'ingested_at':'2026-09-02','retrieved_at':None,'refresh_due':'2099-01-01','review_status':'active',
            'independence_key':f'synthetic-fixture-paper-{index}','pages':[],'supersedes':None}
    source_ledger={'schema':'claude-obsidian.source-ledger.v1','generated_at':'2026-09-02T00:00:00Z','sources':sources}
    payloads={'wiki/meta/ledgers/source-ledger.json':canonicalize(source_ledger),
        'wiki/meta/ledgers/claim-ledger.json':canonicalize({'schema':'claude-obsidian.claim-ledger.v1','generated_at':'2026-09-02T00:00:00Z','claims':claims})}
    for paper in material['papers']:
        record=paper['record'];payloads[f"wiki/meta/records/papers/{identity.paper_page_slug(record['paper_id'])}.json"]=canonicalize(record)
        for event in paper['events']:payloads[f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json"]=canonicalize(event)
    repo=material['code'][0]['repo_record'];payloads['wiki/meta/records/repos/'+identity.repo_page_slug(repo['repo_id'])+'.json']=canonicalize(repo)
    raw_fixture_payloads={}
    for prefix,obj in (('code-manifests',material['code'][0]['manifest']),('alignment-manifests',alignment)):
        objraw=canonicalize(obj);raw_fixture_payloads[f'.raw/derived/{prefix}/{hashlib.sha256(objraw).hexdigest()}.json']=objraw
    # Two immutable external Docling fixture fingerprints remain explicitly
    # mechanical; publication of bytes does not claim a Docling run occurred.
    for capture,extraction in zip(capture_evidence,extractions,strict=True):
        raw_fixture_payloads[extraction['base']+'/document.json']=extraction['document']
        raw_fixture_payloads[extraction['base']+'/parser-config.json']=shared_config
        raw_fixture_payloads[extraction['base']+'/model-manifest.json']=shared_model
        raw_fixture_payloads[f".raw/derived/{capture['sha256']}/runs/{extraction['run_id']}.json"]=extraction['run']
    # A second deterministic parser fingerprint for the first captured PDF.
    alternate_config=canonicalize({'profile':'installed-vertical-alternate'})
    second=identity.pipeline_fingerprint({'engine':'docling','engine_version':DOCLING_VERSION,'core_version':DOCLING_CORE_VERSION,
        'config_sha256':hashlib.sha256(alternate_config).hexdigest(),'model_manifest_sha256':hashlib.sha256(shared_model).hexdigest()})
    fingerprints=[shared_fp,second]
    second_base=f".raw/derived/{capture_evidence[0]['sha256']}/docling/{second}"
    second_document=canonicalize({'text':'synthetic extraction alternate','score':99})
    raw_fixture_payloads[second_base+'/document.json']=second_document
    raw_fixture_payloads[second_base+'/parser-config.json']=alternate_config
    raw_fixture_payloads[second_base+'/model-manifest.json']=shared_model
    second_run={'schema':'video-paper-wiki.run-manifest.v1','run_id':'run-installed-alternate',
        'tool_versions':{'vpwiki':'0.1.0','python':'3.12','docling':DOCLING_VERSION,'docling_core':DOCLING_CORE_VERSION},
        'input_hashes':{'parser_config_sha256':hashlib.sha256(alternate_config).hexdigest(),
            'model_manifest_sha256':hashlib.sha256(shared_model).hexdigest()},
        'output_hashes':{'document_json_sha256':hashlib.sha256(second_document).hexdigest()},
        'started_at':'2026-09-02T00:01:00Z','ended_at':'2026-09-02T00:01:01Z','error_code':None,
        'pipeline_fingerprint':second}
    raw_fixture_payloads[f".raw/derived/{capture_evidence[0]['sha256']}/runs/run-installed-alternate.json"]=canonicalize(second_run)
    for paper in material['papers']:
        record=paper['record'];payloads[f"wiki/meta/records/papers/{identity.paper_page_slug(record['paper_id'])}.json"]=canonicalize(record)
    payloads.update(raw_fixture_payloads)
    prospective=[]
    for paper in material['papers']:
        slug=identity.paper_page_slug(paper['record']['paper_id'])
        claims_path=f'.raw/derived/compiler-input/{slug}-claims.json'
        events_path=f'.raw/derived/compiler-input/{slug}-events.json'
        payloads[claims_path]=canonicalize(paper['claims']);payloads[events_path]=canonicalize(paper['events'])
        prospective.append({'group_id':'paper-'+slug,
            'paper_record':f'wiki/meta/records/papers/{slug}.json','claims':claims_path,'events':events_path})
    code_manifest_raw=canonicalize(material['code'][0]['manifest'])
    alignment_raw=canonicalize(alignment)
    code_manifest_path=f'.raw/derived/code-manifests/{hashlib.sha256(code_manifest_raw).hexdigest()}.json'
    alignment_path=f'.raw/derived/alignment-manifests/{hashlib.sha256(alignment_raw).hexdigest()}.json'
    prospective.append({'group_id':'code-'+identity.repo_page_slug(repo['repo_id']),
        'code_manifest':code_manifest_path,'repo_record':'wiki/meta/records/repos/'+identity.repo_page_slug(repo['repo_id'])+'.json',
        'alignment':alignment_path})
    from video_paper_wiki.canonical_compiler import compile_pages
    compiled_pages=compile_pages(material);payloads.update(compiled_pages)
    # Build the source tree with the local staging primitive as test setup, but
    # make every publication observation and mutation through the installed
    # product.  Raw-derived fixture material is retained out of the Vault until
    # its dedicated extraction publication path is exercised.
    original_cwd=Path.cwd();os.chdir(checkout)
    try:
        seeded=stage_publication_request(batch_id='vertical-authority',operation_id='vertical-authority',
            operation_type='ingest',payloads=payloads,claimed_input_paths=sorted({
                *[row['stored_path'] for row in capture_evidence],created['manifest']['capture']['stored_path']}),
            prospective_groups=prospective)
    finally:os.chdir(original_cwd)
    publication_source=root/'authority-source/publication-input';publication_source.parent.mkdir();shutil.copytree(
        checkout/'.work/vertical-authority/publication-input',publication_source)
    shutil.rmtree(checkout/'.work/vertical-authority')
    prepared_publication=_json([vpwiki,'publication','prepare','--request',
        publication_source/'knowledge-publication-request.v1.json','--batch-id','vertical-authority'],cwd=checkout,env=env)['data']
    authority=_json([vpwiki,'publication','inspect','--prepared',prepared_publication['request_path'],
        '--operation-id','vertical-authority','--upstream-root',upstream,'--vault-root',source],cwd=checkout,env=env)['data']
    publication_bundle=checkout/'.work/vertical-authority/transaction-inspect/bundle.json'
    publication_approval=authority['transaction']['inspection']['approval_sha256']
    publication_argv=[admin,'transaction','apply','--bundle',publication_bundle,'--vault-root',source,
        '--upstream-root',upstream,'--approved-plan-sha256',publication_approval]
    before=_tree_snapshot(source);publication_refusal=_json(publication_argv,cwd=checkout,env=env,expected=2,_evidence_out=process_evidence,_phase='publication-refusal');after=_tree_snapshot(source);refusal_effects['publication']=(before,after)
    assert before==after
    _publication_applied,publication_transcript=_pty_json(publication_argv,'transaction apply',cwd=checkout,env=env,_evidence_out=process_evidence,_phase='publication-apply')
    for path in source.rglob('*'):
        if path.is_dir():path.chmod(0o700)
    material_path=root/'fixture/runtime-compile-input.json';material_path.write_bytes(canonicalize(material))
    validated=_json([vpwiki,'compile','validate','--path',material_path],cwd=checkout,env=env)['data'];rendered=_json([vpwiki,'compile','render','--path',material_path,'--batch-id','vertical-compile'],cwd=checkout,env=env)['data']
    preview=json.loads(Path(rendered['bundle_path']).read_bytes())
    assert {row['path']:row['sha256'] for row in preview['writes']}=={
        path:hashlib.sha256(data).hexdigest() for path,data in compiled_pages.items()}
    policy={'schema':'video-paper-wiki.retrieval-policy.v1','corpus_version':'installed-vertical-v1',
        'query_version':'installed-query-v1','top_chunks':10,'top_papers':10,'evidence_limit':8,
        'per_paper_evidence_limit':2,'eligibility':'active-not-deprecated',
        'paper_tie_break':'score-desc-paper-id-asc','chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}
    policy_path=root/'retrieval-policy.json';policy_path.write_bytes(canonicalize(policy))
    catalog_argv=[admin,'catalog','build','--vault-root',source,'--upstream-root',upstream,'--config',policy_path]
    before=_tree_snapshot(source);_json(catalog_argv,cwd=checkout,env=env,expected=2,_evidence_out=process_evidence,_phase='catalog-refusal');after=_tree_snapshot(source);refusal_effects['catalog']=(before,after);assert before==after
    catalog_result,catalog_transcript=_pty_json(audited_admin('catalog-build',catalog_argv),'catalog build',cwd=checkout,env=env,_evidence_out=process_evidence,_phase='catalog-build')
    catalog_data=catalog_result['data'];final_config=root/'retrieval-config.json'
    final_config.write_bytes(canonicalize(catalog_data['retrieval_config']))
    status=_json([vpwiki,'index','status','--vault-root',source,'--upstream-root',upstream,'--config',final_config],cwd=checkout,env=env)['data']
    query=_json([vpwiki,'query','--json','--text','synthetic evidence','--vault-root',source,
        '--upstream-root',upstream,'--config',final_config],cwd=checkout,env=env)['data']
    reports={kind:_json([vpwiki,'catalog','report','--json','--vault-root',source,'--upstream-root',upstream,
        '--config',final_config,'--kind',kind],cwd=checkout,env=env)['data']
        for kind in ('code-openness','paper-lifecycle','evidence-coverage')}
    audit=subprocess.run([str(vpwiki),'audit','--vault-root',str(source),'--upstream-root',str(upstream)],
        cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    # Authoritative disaster-recovery baseline is taken only after the catalog
    # runtime and all read-only product observations are complete.
    source_snapshot=_tree_snapshot(source)
    manifest_doc=_json([vpwiki,'backup','manifest','--vault-root',source],cwd=checkout,env=env)['data']
    manifest_path=root/'backup-manifest.json';manifest_path.write_bytes(canonicalize(manifest_doc))
    archive=root/'backup.zip';create_argv=[admin,'backup','create','--vault-root',source,'--manifest',manifest_path,
        '--destination',archive]
    create_before=_tree_snapshot(source);create_refusal=_json(create_argv,cwd=checkout,env=env,expected=2,_evidence_out=process_evidence,_phase='backup-create-refusal');create_after=_tree_snapshot(source);refusal_effects['backup-create']=(create_before,create_after)
    assert create_refusal['error']['code']=='HUMAN_APPROVAL_REQUIRED' and not archive.exists() and create_after==create_before
    archive_result,archive_transcript=_pty_json(create_argv,'backup create',cwd=checkout,env=env,_evidence_out=process_evidence,_phase='backup-create')
    restore.mkdir(mode=0o700)
    restore_argv=[admin,'backup','restore','--archive',archive,'--source-root',source,'--restore-root',restore,
        '--manifest',manifest_path,'--upstream-root',upstream,'--config',final_config]
    restore_before=_tree_snapshot(restore);restore_refusal=_json(restore_argv,cwd=checkout,env=env,expected=2,_evidence_out=process_evidence,_phase='backup-restore-refusal');restore_after=_tree_snapshot(restore);refusal_effects['backup-restore']=(restore_before,restore_after)
    assert restore_refusal['error']['code']=='HUMAN_APPROVAL_REQUIRED' and restore_before==restore_after and list(restore.iterdir())==[]
    restore_result,restore_transcript=_pty_json(audited_admin('backup-restore',restore_argv),'backup restore',cwd=checkout,env=env,_evidence_out=process_evidence,_phase='backup-restore')
    manifest_files={row['path'] for row in manifest_doc['files']};manifest_dirs={row['path'] for row in manifest_doc['directories']}
    restored_payload_files={path.relative_to(restore).as_posix() for path in restore.rglob('*') if path.is_file()
        and path.relative_to(restore).parts[0] in {'.raw','wiki'}}
    restored_payload_dirs={path.relative_to(restore).as_posix() for path in restore.rglob('*') if path.is_dir()
        and path.relative_to(restore).parts[0] in {'.raw','wiki'}}
    restored_runtime_files={path.relative_to(restore).as_posix() for path in (restore/'.vault-meta').rglob('*') if path.is_file()}
    assert restored_payload_files==manifest_files and restored_payload_dirs==manifest_dirs
    operator_audit_docs={phase:json.loads(path.read_bytes()) for phase,path in operator_audits.items()}
    restored_config=root/'restored-retrieval-config.json'
    restored_config.write_bytes(canonicalize(restore_result['retrieval_config']))
    restored_status=_json([vpwiki,'index','status','--vault-root',restore,'--upstream-root',upstream,
        '--config',restored_config],cwd=checkout,env=env)['data']
    restored_query=_json([vpwiki,'query','--json','--text','synthetic evidence','--vault-root',restore,
        '--upstream-root',upstream,'--config',restored_config],cwd=checkout,env=env)['data']
    restored_reports={kind:_json([vpwiki,'catalog','report','--json','--vault-root',restore,'--upstream-root',upstream,
        '--config',restored_config,'--kind',kind],cwd=checkout,env=env)['data']
        for kind in ('paper-lifecycle','evidence-coverage')}
    restored_audit=subprocess.run([str(vpwiki),'audit','--vault-root',str(restore),'--upstream-root',str(upstream)],
        cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    restored_compile_validate=_json([vpwiki,'compile','validate','--path',material_path],cwd=checkout,env=env)['data']
    restored_compile_render=_json([vpwiki,'compile','render','--path',material_path,
        '--batch-id','vertical-restored-compile'],cwd=checkout,env=env)['data']
    restored_preview=json.loads(Path(restored_compile_render['bundle_path']).read_bytes())
    restored_page_hashes={row['path']:hashlib.sha256((restore/row['path']).read_bytes()).hexdigest()
        for row in restored_preview['writes']}
    assert restored_page_hashes=={row['path']:row['sha256'] for row in restored_preview['writes']}
    # Fixture-only disaster injection over an exact observed projection
    # allowlist. Canonical raw, records, ledgers, receipts and reviews remain.
    truth_paths=sorted(p for p in restore.rglob('*') if p.is_file() and
        (p.relative_to(restore).as_posix().startswith('.raw/') or
         p.relative_to(restore).as_posix().startswith('wiki/meta/')))
    truth_before={p.relative_to(restore).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in truth_paths}
    page_allowlist=sorted(restored_page_hashes)
    runtime_allowlist=sorted(p.relative_to(restore).as_posix() for p in (restore/'.vault-meta').rglob('*')
        if p.is_file() and (p.relative_to(restore).as_posix()=='.vault-meta/catalog.sqlite' or
            p.relative_to(restore).as_posix()=='.vault-meta/bm25/index.json' or
            p.relative_to(restore).as_posix().startswith('.vault-meta/chunks/')))
    deletion_allowlist=page_allowlist+runtime_allowlist
    for relative in deletion_allowlist:(restore/relative).unlink()
    assert all(not (restore/relative).exists() for relative in deletion_allowlist)
    truth_after={p.relative_to(restore).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in truth_paths}
    assert truth_after==truth_before
    # Refill only the exact compiler bundle paths as a harness action, then let
    # the installed sole builder recreate every runtime projection in-place.
    bundle_writes=restored_preview['writes'];assert sorted(row['path'] for row in bundle_writes)==page_allowlist
    content_root=Path(restored_compile_render['bundle_path']).parent/'content'
    for row in bundle_writes:
        raw=(content_root/row['sha256']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256']
        target=restore/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);target.chmod(0o600)
    rebuild_argv=[admin,'catalog','build','--vault-root',restore,'--upstream-root',upstream,'--config',policy_path]
    rebuild_envelope,_=_pty_json(rebuild_argv,'catalog build',cwd=checkout,env=env);rebuild_result=rebuild_envelope['data']
    rebuild_config=root/'rebuild-retrieval-config.json';rebuild_config.write_bytes(canonicalize(rebuild_result['retrieval_config']))
    rebuild_status=_json([vpwiki,'index','status','--vault-root',restore,'--upstream-root',upstream,
        '--config',rebuild_config],cwd=checkout,env=env)['data']
    rebuild_query=_json([vpwiki,'query','--json','--text','synthetic evidence','--vault-root',restore,
        '--upstream-root',upstream,'--config',rebuild_config],cwd=checkout,env=env)['data']
    rebuild_reports={kind:_json([vpwiki,'catalog','report','--json','--vault-root',restore,
        '--upstream-root',upstream,'--config',rebuild_config,'--kind',kind],cwd=checkout,env=env)['data']
        for kind in ('code-openness','paper-lifecycle','evidence-coverage')}
    markdown_identical=all((source/path).read_bytes()==(restore/path).read_bytes() for path in page_allowlist)
    from video_paper_wiki.projection_runtime import parse_projection_json,runtime_projection_equal
    rebuilt_runtime=sorted(p.relative_to(restore).as_posix() for p in (restore/'.vault-meta').rglob('*')
        if p.is_file() and (p.relative_to(restore).as_posix()=='.vault-meta/catalog.sqlite' or
            p.relative_to(restore).as_posix()=='.vault-meta/bm25/index.json' or
            p.relative_to(restore).as_posix().startswith('.vault-meta/chunks/')))
    runtime_identical=rebuilt_runtime==runtime_allowlist
    for path in runtime_allowlist:
        if path.startswith('.vault-meta/chunks/'):
            runtime_identical &= runtime_projection_equal('chunk',parse_projection_json((source/path).read_bytes()),parse_projection_json((restore/path).read_bytes()))
        elif path=='.vault-meta/bm25/index.json':
            runtime_identical &= runtime_projection_equal('bm25',parse_projection_json((source/path).read_bytes()),parse_projection_json((restore/path).read_bytes()))
    from video_paper_wiki.catalog_store import canonical_export_from_database
    source_export=canonical_export_from_database(source/'.vault-meta/catalog.sqlite')
    rebuild_export=canonical_export_from_database(restore/'.vault-meta/catalog.sqlite')
    authority_script=ROOT/'tests/closure/_installed_catalog_authority.py'
    source_authority=_json([installed_cli/'python',authority_script,source,upstream,final_config],cwd=root,env=env)
    rebuild_authority=_json([installed_cli/'python',authority_script,restore,upstream,rebuild_config],cwd=root,env=env)
    assert catalog_data['catalog_generation_sha256']==source_authority['meta']['catalog_generation_sha256']
    assert rebuild_result['catalog_generation_sha256']==rebuild_authority['meta']['catalog_generation_sha256']
    assert catalog_data['export_sha256']==hashlib.sha256(source_export).hexdigest()
    assert rebuild_result['export_sha256']==hashlib.sha256(rebuild_export).hexdigest()
    source_normalized=_normalized_catalog_export(source_export,source_authority)
    rebuild_normalized=_normalized_catalog_export(rebuild_export,rebuild_authority)
    export_identical=source_normalized==rebuild_normalized
    nonvolatile_tamper=json.loads(json.dumps(source_normalized))
    nonvolatile_tamper['base_catalog_rows_sha256']='0'*64
    assert nonvolatile_tamper!=rebuild_normalized
    assert query['catalog_generation_sha256']==status['catalog_generation_sha256']
    assert rebuild_query['catalog_generation_sha256']==rebuild_status['catalog_generation_sha256']
    query_identical=_normalized_query(query)==_normalized_query(rebuild_query)
    reports_identical=True
    for kind in reports:
        assert reports[kind]['catalog_generation_sha256']==status['catalog_generation_sha256']
        assert rebuild_reports[kind]['catalog_generation_sha256']==rebuild_status['catalog_generation_sha256']
        reports_identical &= _normalized_report(reports[kind])==_normalized_report(rebuild_reports[kind])
    truth_broken=root/'truth-broken';shutil.copytree(restore,truth_broken)
    next((truth_broken/'wiki/meta/records/papers').glob('*.json')).unlink()
    broken_audit=_json([vpwiki,'audit','--vault-root',truth_broken,'--upstream-root',upstream],cwd=checkout,env=env,expected=1)
    stale_head=root/'stale-head';shutil.copytree(restore,stale_head)
    stale_head_path=stale_head/'wiki/meta/registries/operation-head.json';stale_head_doc=json.loads(stale_head_path.read_bytes())
    stale_head_doc['sequence']+=1;stale_head_path.write_bytes(canonicalize(stale_head_doc))
    stale_head_result=_json([vpwiki,'query','--json','--text','synthetic evidence','--vault-root',stale_head,
        '--upstream-root',upstream,'--config',rebuild_config],cwd=checkout,env=env,expected=2)
    stale_index=root/'stale-index';shutil.copytree(restore,stale_index)
    stale_index_path=stale_index/'.vault-meta/bm25/index.json';stale_index_path.write_bytes(stale_index_path.read_bytes()+b' ')
    stale_index_result=_json([vpwiki,'query','--json','--text','synthetic evidence','--vault-root',stale_index,
        '--upstream-root',upstream,'--config',rebuild_config],cwd=checkout,env=env,expected=2)
    head=json.loads((source/'wiki/meta/registries/operation-head.json').read_bytes())
    return {'root':root,'fixture':fixture,'source':source,'restore':restore,'source_snapshot':source_snapshot,
        'audit_exit':audit.returncode,'audit':json.loads(audit.stdout),'installed':installed_cli,'captures':capture_evidence,
        'code_capture':{'sha256':code_sha,'stored_path':created['manifest']['capture']['stored_path'],'reuse':True},'fingerprints':fingerprints,
        'compile':{'input_path':material_path,'validate':validated,'render':rendered},
        'catalog':catalog_data,'config_path':final_config,'status':status,'query':query,'reports':reports,'head':head,
        'backup_manifest':manifest_doc,'archive':archive_result,'restore_result':restore_result,
        'restore_catalog':restored_status,'restored_query':restored_query,'restored_reports':restored_reports,
        'restore_config_path':rebuild_config,
        'restored_audit_exit':restored_audit.returncode,'restored_audit':json.loads(restored_audit.stdout),
        'restored_compile':{'validate':restored_compile_validate,'render':restored_compile_render,
            'page_hashes':restored_page_hashes},
        'delete':{'fixture_disaster_injection':True,'allowlist':deletion_allowlist,'truth_unchanged':truth_after==truth_before},
        'rebuild':{'markdown_identical':markdown_identical,'export_identical':export_identical,
            'runtime_identical':runtime_identical,'mapping_identical':query['mapping_sha256']==rebuild_query['mapping_sha256'],
            'query_identical':query_identical,'reports_identical':reports_identical,
            'volatile_allowlist':_REBUILD_EXPORT_VOLATILE_CELLS,'status':rebuild_status},
        'truth_delete_error':broken_audit['error']['details']['domain_error']['code'],
        'stale_head_error':stale_head_result['error']['code'],
        'stale_index_error':stale_index_result['error']['code'],
        'operator_evidence':{'installed_admin':str(admin),'init_status':applied['status'],'catalog_ok':catalog_result['ok'],
            'create_refusal':create_refusal['error']['code'],'restore_refusal':restore_refusal['error']['code'],
            'publication_refusal':publication_refusal['error']['code'],
            'archive_sha256':archive_result['archive_sha256'],'archive_size_bytes':archive.stat().st_size,
            'archive_actual_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'archive_manifest_sha256':archive_result['manifest_sha256'],
            'restore_valid':restore_result['verification']['valid'],'restore_mode':stat.S_IMODE(restore.stat().st_mode),
            'restore_source_anchor':restore_result['verification']['tree']['source_anchor'],
            'manifest_source_anchor':manifest_doc['source_anchor'],
            'head_bound':head==authority['transaction']['head'],
            'catalog_bound':(catalog_data['catalog_generation_sha256']==status['catalog_generation_sha256']
                and catalog_data['retrieval_config']['generation_sha256']==status['join_generation_sha256']
                and catalog_data['retrieval_config']['mapping_sha256']==status['mapping_sha256']
                and hashlib.sha256(canonicalize(catalog_data['retrieval_config'])).hexdigest()==status['retrieval_config_sha256']),
            'processes':process_evidence,'refusal_effects':refusal_effects,'operator_audits':operator_audit_docs,
            'restore_inventory':{'manifest_files':sorted(manifest_files),'actual_files':sorted(restored_payload_files),
                'manifest_dirs':sorted(manifest_dirs),'actual_dirs':sorted(restored_payload_dirs),
                'runtime_files':sorted(restored_runtime_files)},
            'transcript_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in {
                'init-plan':init_plan_transcript,'init-apply':init_apply_transcript,'publication':publication_transcript,
                'catalog':catalog_transcript,'backup-create':archive_transcript,'backup-restore':restore_transcript}.items()}},
        'public_gate_observations':{'paper':paper_public,'code-plan':planned,'code-inspection':created,
            'publication':authority,'compile-validate':validated,'compile-render':rendered,'audit':json.loads(audit.stdout),
            'status':status,'query':query,'reports':reports,'backup-manifest':manifest_doc,
            'backup-create':archive_result,'backup-restore':restore_result},
        'external_gates':{key:fixture[key] for key in ('external_gate_satisfied','human_assessment','provenance_verified','license_verified','visual_acceptance')},
        'product_delete_capability':False,'fixture_disaster_injection':True}


def _tree_snapshot(root:Path)->list[dict]:
    import stat
    root_info=root.lstat();rows=[{'path':'','mode':stat.S_IFMT(root_info.st_mode)|stat.S_IMODE(root_info.st_mode),
        'dev':root_info.st_dev,'ino':root_info.st_ino,'nlink':root_info.st_nlink,'size':root_info.st_size,'sha256':None}]
    for path in sorted(root.rglob('*'),key=lambda p:p.relative_to(root).as_posix().encode()):
        info=path.lstat();rows.append({'path':path.relative_to(root).as_posix(),
            'mode':stat.S_IFMT(info.st_mode)|stat.S_IMODE(info.st_mode),
            'dev':info.st_dev,'ino':info.st_ino,'nlink':info.st_nlink,'size':info.st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None})
    return rows


def _assert_external_gates_remain_open(installed_vertical_session,real_gate_session,tmp_path,monkeypatch):
    from tests.support import make_checkout
    from tests.unit.test_publication_wave import _vault_with_files
    from video_paper_wiki.contracts import DOCLING_CORE_VERSION,DOCLING_VERSION
    from video_paper_wiki.extraction_artifact import prepare_docling_publication
    from video_paper_wiki.identity import pipeline_fingerprint
    from video_paper_wiki.jcs import canonicalize
    gates=installed_vertical_session['external_gates']
    assert set(gates)=={'external_gate_satisfied','human_assessment','provenance_verified','license_verified','visual_acceptance'}
    assert all(value is False for value in gates.values())
    gate=real_gate_session['authority'];assert 'human_gate_satisfied' in gate and gate['human_gate_satisfied'] is False
    assert 'external_gate_satisfied' in real_gate_session['applied'] and real_gate_session['applied']['external_gate_satisfied'] is False
    checkout=tmp_path/'checkout';checkout.mkdir();make_checkout(checkout);monkeypatch.chdir(checkout)
    vault=tmp_path/'vault';vault.mkdir();pdf=b'%PDF external gate';pdf_sha=hashlib.sha256(pdf).hexdigest();captured=f'.raw/captured/{pdf_sha}.pdf'
    _vault_with_files(vault,{captured:pdf})
    data={'document_json':b'{"text":"external"}','parser_config':b'{"profile":"external"}','model_manifest':b'{"models":[]}'}
    fp=pipeline_fingerprint({'engine':'docling','engine_version':DOCLING_VERSION,'core_version':DOCLING_CORE_VERSION,
        'config_sha256':hashlib.sha256(data['parser_config']).hexdigest(),'model_manifest_sha256':hashlib.sha256(data['model_manifest']).hexdigest()})
    run={'schema':'video-paper-wiki.run-manifest.v1','run_id':'run-external-gate','tool_versions':{'vpwiki':'fixture','python':'3.13','docling':DOCLING_VERSION,'docling_core':DOCLING_CORE_VERSION},
        'input_hashes':{'parser_config_sha256':hashlib.sha256(data['parser_config']).hexdigest(),'model_manifest_sha256':hashlib.sha256(data['model_manifest']).hexdigest()},
        'output_hashes':{'document_json_sha256':hashlib.sha256(data['document_json']).hexdigest()},'started_at':'2026-09-02T00:00:00Z','ended_at':'2026-09-02T00:00:01Z','error_code':None,'pipeline_fingerprint':fp}
    data['run_manifest']=canonicalize(run);paths={'captured_pdf':vault/captured}
    for kind,raw in data.items():paths[kind]=tmp_path/kind;paths[kind].write_bytes(raw)
    extraction=prepare_docling_publication(**paths,publication_context={'operation_id':'external-gate','claimed_input_paths':[],'prospective_groups':[]},batch_id='external-gate',vault_root=vault)
    assert 'external_gate_satisfied' in extraction and extraction['external_gate_satisfied'] is False
    restored=installed_vertical_session['restore_result']
    assert 'external_backup_observation' in restored and restored['external_backup_observation'] is False
    assert 'external_backup_observation' in restored['verification'] and restored['verification']['external_backup_observation'] is False
    forbidden={'external_gate_satisfied','human_gate_satisfied','external_backup_observation',
        'provenance_verified','license_verified','visual_acceptance'}
    def fields(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in forbidden or key.endswith(('_accepted','_satisfied')):yield key,item
                yield from fields(item)
        elif isinstance(value,list):
            for item in value:yield from fields(item)
    for name,public in installed_vertical_session['public_gate_observations'].items():
        observed=list(fields(public));assert all(value is False for _key,value in observed),(name,observed)
        if name not in {'backup-create','backup-restore'}:assert observed==[],(name,observed)
    explicit=list(fields({'gate-inspect':gate,'gate-apply':real_gate_session['applied'],'extraction':extraction}))
    assert explicit and all(value is False for _key,value in explicit)


def test_prospective_wheel_operator_phase(installed_vertical_session):
    value=installed_vertical_session['operator_evidence']
    assert Path(value['installed_admin']).resolve()==(installed_vertical_session['installed']/'vpwiki-admin').resolve()
    assert value['init_status']=='complete' and value['catalog_ok'] is True
    assert value['publication_refusal']=='OPERATOR_CONFIRMATION_REQUIRED'
    assert value['create_refusal']==value['restore_refusal']=='HUMAN_APPROVAL_REQUIRED'
    assert value['archive_sha256']==value['archive_actual_sha256'] and value['archive_size_bytes']>0
    assert value['archive_manifest_sha256']==installed_vertical_session['backup_manifest']['manifest_sha256']
    assert value['restore_valid'] is True and value['restore_mode']==0o700
    assert value['restore_source_anchor']==value['manifest_source_anchor']
    assert value['head_bound'] is True and value['catalog_bound'] is True
    assert set(value['transcript_sha256'])=={'init-plan','init-apply','publication','catalog','backup-create','backup-restore'}
    assert all(len(digest)==64 for digest in value['transcript_sha256'].values())
    processes={row['phase']:row for row in value['processes']}
    refusal_phases={'init-refusal','publication-refusal','catalog-refusal','backup-create-refusal','backup-restore-refusal'}
    pty_phases={'init-plan','init-apply','publication-apply','catalog-build','backup-create','backup-restore'}
    assert set(processes)==refusal_phases|pty_phases
    expected_refusals={'init-refusal':'OPERATOR_CONFIRMATION_REQUIRED','publication-refusal':'OPERATOR_CONFIRMATION_REQUIRED',
        'catalog-refusal':'OPERATOR_CONFIRMATION_REQUIRED','backup-create-refusal':'HUMAN_APPROVAL_REQUIRED',
        'backup-restore-refusal':'HUMAN_APPROVAL_REQUIRED'}
    for phase in refusal_phases:
        row=processes[phase]
        assert row['argv'][0]==value['installed_admin'] and row['returncode']==2
        assert row['canonical_single_line'] is True and row['stdout'].count('\n')==1 and row['stderr']==''
        assert row['prompt'] is None and row['prompt_count']==row['token_write_count']==0
        assert json.loads(row['stdout'])['error']['code']==expected_refusals[phase]
    assert set(value['refusal_effects'])=={'init','publication','catalog','backup-create','backup-restore'}
    assert all(before==after for before,after in value['refusal_effects'].values())
    expected_tokens={'init-plan':'init '+str(installed_vertical_session['source']),'init-apply':'init '+str(installed_vertical_session['source']),
        'publication-apply':'transaction apply','catalog-build':'catalog build','backup-create':'backup create','backup-restore':'backup restore'}
    for phase in pty_phases:
        row=processes[phase]
        assert row['returncode']==0 and row['canonical_single_line'] is True and row['stdout'].count('\n')==1,(phase,row['stdout'])
        assert row['prompt_count']==row['token_write_count']==1 and row['traceback'] is False
        assert row['stderr'].count(row['prompt'])==1 and 'Traceback' not in row['stderr']
        assert row['prompt']=="Type "+repr(expected_tokens[phase])+" to run the pinned upstream command: "
    audits=value['operator_audits'];assert set(audits)=={'catalog-build','backup-restore'}
    venv=installed_vertical_session['installed'].parent.resolve()
    for phase,audit in audits.items():
        assert Path(audit['entrypoint']).resolve()==Path(value['installed_admin']).resolve()
        assert audit['entrypoint_argv'][0]==value['installed_admin']
        for origin in audit['origins'].values():
            resolved=Path(origin).resolve();assert resolved.is_relative_to(venv) and not resolved.is_relative_to(ROOT)
        writers=[]
        for child in audit['children']:
            words=child['argv'];joined=' '.join(words)
            if any(word.endswith('/scripts/contextual-prefix.py') for word in words):writers.append('prefix')
            if any(word.endswith('/scripts/bm25-index.py') for word in words) and 'build' in words:writers.append('bm25')
            assert ' index build ' not in ' '+joined+' '
        assert writers==['prefix','bm25'],(phase,writers,audit['children'])
    assert audits['catalog-build']['entrypoint_argv'][1:3]==['catalog','build']
    assert audits['backup-restore']['entrypoint_argv'][1:3]==['backup','restore']
    assert audits['catalog-build']['entrypoint_argv']==[value['installed_admin'],'catalog','build','--vault-root',
        str(installed_vertical_session['source']),'--upstream-root',str(ROOT/'vendor/claude-obsidian'),'--config',
        str(installed_vertical_session['root']/'retrieval-policy.json')]
    assert audits['backup-restore']['entrypoint_argv']==[value['installed_admin'],'backup','restore','--archive',
        str(installed_vertical_session['root']/'backup.zip'),'--source-root',str(installed_vertical_session['source']),
        '--restore-root',str(installed_vertical_session['restore']),'--manifest',str(installed_vertical_session['root']/'backup-manifest.json'),
        '--upstream-root',str(ROOT/'vendor/claude-obsidian'),'--config',str(installed_vertical_session['root']/'retrieval-config.json')]


def test_three_paper_one_repo(installed_vertical_session):
    evidence=installed_vertical_session
    restore=evidence['restore'];captured=sorted((restore/'.raw/captured').iterdir())
    assert len([p for p in captured if p.suffix=='.pdf'])==3
    assert len([p for p in captured if p.suffix=='.bin'])==1
    artifact_dirs=sorted((restore/'.raw/derived').glob('*/docling/*'))
    assert len(artifact_dirs)==4
    assert len({path.name for path in artifact_dirs})==2
    assert all({p.name for p in path.iterdir()}=={'document.json','model-manifest.json','parser-config.json'} for path in artifact_dirs)
    assert len(list((restore/'.raw/derived').glob('*/runs/*.json')))==4
    assert evidence['compile']['validate']=={'valid':True,'page_count':5}
    code_rows=evidence['reports']['code-openness']['rows']
    assert len(code_rows)==3 and sum(len(row['repositories']) for row in code_rows)==1
    assert evidence['head']['sequence']==2
    assert evidence['audit']['data']['domain']['orphans']==[]


def test_postrestore_domain_audit(installed_vertical_session):
    evidence=installed_vertical_session
    assert evidence['restored_audit_exit']==0 and evidence['restored_audit']['data']['domain']['valid'] is True


def test_postrestore_locator_resolution(installed_vertical_session):
    evidence=installed_vertical_session;source=evidence['restore']
    rows=evidence['restored_reports']['paper-lifecycle']['rows']
    assert len(rows)==len(evidence['captures'])==3
    for paper in rows:
        page=source/f"wiki/papers/{paper['paper_id'].replace(':','-')}.md"
        assert page.is_file() and page.read_text().count('^clm-')==1


def test_postrestore_compile(installed_vertical_session):
    evidence=installed_vertical_session;pages=sorted((evidence['restore']/'wiki/papers').glob('*.md'))
    assert evidence['restored_compile']['validate']=={'valid':True,'page_count':5}
    assert len(pages)==3 and all(path.read_bytes() for path in pages)


def test_postrestore_strict_lint(installed_vertical_session):
    lint=installed_vertical_session['restored_audit']['data']['strict_lint']
    assert lint['exit_code']==0 and lint['data']['summary']['issues_found']==0


def test_postrestore_runtime_rebuild(installed_vertical_session):
    result=installed_vertical_session.get('restore_catalog')
    assert result and result['state']=='current' and result['reasons']==[]
    assert all(len(result[key])==64 for key in ('join_generation_sha256','mapping_sha256',
        'retrieval_config_sha256','catalog_generation_sha256'))


def test_postrestore_query(installed_vertical_session):
    query=installed_vertical_session.get('restored_query')
    assert query and query['raw_hits'] and query['ranking']['top10']
    assert query['ranking']['top5']==query['ranking']['top10'][:5]


def test_delete_projections(installed_vertical_session):
    value=installed_vertical_session.get('delete')
    assert value and value['fixture_disaster_injection'] is True and value['truth_unchanged'] is True


def test_rebuild_markdown(installed_vertical_session):
    assert installed_vertical_session.get('rebuild',{}).get('markdown_identical') is True


def test_rebuild_export(installed_vertical_session):
    result=installed_vertical_session.get('rebuild',{})
    assert result.get('export_identical') is True
    assert result.get('volatile_allowlist')=={
        '$':('catalog_generation_sha256',),
        'search_catalog_inputs':('raw_sha256[upstream-chunk|upstream-bm25]',),
        'search_chunks':('raw_sha256',),
        'search_catalog_meta':('catalog_generation_sha256','upstream_chunk_set_sha256','upstream_index_raw_sha256'),
    }


def test_rebuild_runtime(installed_vertical_session):
    assert installed_vertical_session.get('rebuild',{}).get('runtime_identical') is True


def test_rebuild_mapping_query(installed_vertical_session):
    result=installed_vertical_session.get('rebuild',{})
    assert result.get('mapping_identical') is True and result.get('query_identical') is True
    assert result.get('reports_identical') is True


def test_delete_truth(installed_vertical_session):
    assert installed_vertical_session.get('truth_delete_error')=='OUT_OF_BAND_WRITE'


def test_catalog_stale_head(installed_vertical_session):
    assert installed_vertical_session.get('stale_head_error')=='CATALOG_STALE'


def test_catalog_stale_index(installed_vertical_session):
    assert installed_vertical_session.get('stale_index_error')=='CATALOG_STALE'


def test_prospective_operator_restore_rebuild(installed_vertical_session):
    result=installed_vertical_session.get('restore_result')
    assert result and result['verification']['valid'] is True
    assert result['retrieval_config_sha256']==hashlib.sha256(
        json.dumps(result['retrieval_config'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert stat.S_IMODE(installed_vertical_session['restore'].stat().st_mode)==0o700
    manifest=installed_vertical_session['backup_manifest'];restore=installed_vertical_session['restore']
    assert result['verification']['tree']['manifest_sha256']==manifest['manifest_sha256']
    assert result['verification']['tree']['source_anchor']==manifest['source_anchor']
    inventory=installed_vertical_session['operator_evidence']['restore_inventory']
    assert inventory['actual_files']==inventory['manifest_files']==sorted(row['path'] for row in manifest['files'])
    assert inventory['actual_dirs']==inventory['manifest_dirs']==sorted(row['path'] for row in manifest['directories'])
    expected_runtime=sorted(path for path in installed_vertical_session['delete']['allowlist'] if path.startswith('.vault-meta/'))
    assert inventory['runtime_files']==expected_runtime
    for row in manifest['files']:
        target=restore/row['path']
        assert target.is_file() and len(target.read_bytes())==row['size_bytes']
        assert hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']
        assert stat.S_IMODE(target.stat().st_mode)==row['mode']
    assert result['verification']['catalog_status']['state']=='current'
    assert result['verification']['query_generation_sha256']==result['verification']['report_generation_sha256']
    status=result['verification']['catalog_status'];config=result['retrieval_config']
    assert status['mapping_sha256']==config['mapping_sha256']
    assert status['join_generation_sha256']==config['generation_sha256']
    assert status['retrieval_config_sha256']==result['retrieval_config_sha256']
    operator=installed_vertical_session['operator_evidence'];restore_process=[row for row in operator['processes'] if row['phase']=='backup-restore']
    assert len(restore_process)==1 and restore_process[0]['returncode']==0
    assert operator['archive_sha256']==operator['archive_actual_sha256']==result['archive_sha256']
    assert operator['archive_manifest_sha256']==result['manifest_sha256']==manifest['manifest_sha256']
    assert operator['operator_audits']['backup-restore']['entrypoint_argv'][1:3]==['backup','restore']
    assert installed_vertical_session['restored_audit']['data']['domain']['valid'] is True
