from __future__ import annotations
import copy, hashlib, json, os, shutil, stat, sys, tempfile
from pathlib import Path

REPO=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
SOURCE=REPO/'.work/parallel/source-publication-v1/terminal-1/source'
UPSTREAM=SOURCE/'vendor/claude-obsidian'
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE),str(SOURCE/'vendor/claude-obsidian')]

from tests.support import make_checkout, code_evidence_request, complete_ingest_plan, make_approval_ref
from tests.research.test_source_admission import apply_capture, bootstrap_genesis, _apply_bundle
from tests.research.pipeline_support import capture_pdf_bytes
from tests.closure import _installed_fixture_builder as fixture_builder
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.canonical_compiler import compile_pages as legacy_compile_pages
from video_paper_wiki.canonical_compiler_v2 import concept_items_for_papers
from video_paper_wiki.code_evidence_contracts import code_manifest_hash, code_snippet_sha256, code_text_metadata
from video_paper_wiki.contracts import ContractError, DOCLING_CORE_VERSION, DOCLING_VERSION
from video_paper_wiki.identity import assessment_event_id, evidence_fingerprint, pipeline_fingerprint, claim_id, paper_page_slug, repo_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import encode_ledger_evidence
from video_paper_wiki.markdown_locator import encode_evidence
from video_paper_wiki.receipt_audit import HEAD, _Snapshot, audit_integrity
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, SOURCE_LEDGER
from video_paper_wiki.source_semantics_contracts import sha, source_id
from video_paper_wiki.source_state import collect_source_state
from video_paper_wiki.staged_code_capture import inspect_staged_code_capture, validate_staged_code_capture_request
from video_paper_wiki.staging import _stage_prepared_pdf_capture, stage_bytes
from video_paper_wiki.approval import approval_ref_sha256
from video_paper_wiki.publication import _assemble_publication_transaction
from video_paper_wiki.staging import _open_batch_session

STAMP='2026-09-09T00:00:00Z'

def h(raw: bytes)->str:return hashlib.sha256(raw).hexdigest()
def write_json(path: Path, value: object)->bytes:
    raw=canonicalize(value); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw); return raw
def pdf_artifacts(root: Path, pdf_sha: str, index: int):
    config=canonicalize({'profile':f'legacy-probe-{index}'})
    model=canonicalize({'models':[]})
    fp=pipeline_fingerprint({'engine':'docling','engine_version':DOCLING_VERSION,'core_version':DOCLING_CORE_VERSION,
        'config_sha256':h(config),'model_manifest_sha256':h(model)})
    document=canonicalize({'text':f'Legacy parser artifact {index}','pages':[{'page_no':1}]})
    base=f'.raw/derived/{pdf_sha}/docling/{fp}'
    run={'schema':'video-paper-wiki.run-manifest.v1','run_id':f'legacy-probe-run-{index}',
        'tool_versions':{'vpwiki':'0.1.0','python':'3.13','docling':DOCLING_VERSION,'docling_core':DOCLING_CORE_VERSION},
        'input_hashes':{'parser_config_sha256':h(config),'model_manifest_sha256':h(model)},
        'output_hashes':{'document_json_sha256':h(document)},'started_at':STAMP,'ended_at':'2026-09-09T00:00:01Z',
        'error_code':None,'pipeline_fingerprint':fp}
    return {'document':(base+'/document.json',document),'parser':(base+'/parser-config.json',config),
            'model':(base+'/model-manifest.json',model),'run':(f'.raw/derived/{pdf_sha}/runs/{run["run_id"]}.json',canonicalize(run)),
            'fp':fp}

def make_initial_material(fixture_dir: Path):
    material=json.loads((fixture_dir/'compile-input.json').read_bytes())
    code=(fixture_dir/'code.py').read_bytes(); code_sha=h(code)
    triple=fixture_builder.code_triple(code, material['papers'][0]['record']['paper_id'])
    # Replace the builder's synthetic code source with the actual source id used below.
    code_sid='src-repo'
    triple['manifest']['capture']['source_id']=code_sid
    triple['manifest']['capture']['source_identity']=code_sha
    triple['manifest']['capture']['stored_path']=f'.raw/captured/{code_sha}.pdf'
    triple['manifest']['payload']={'sha256':code_sha,'size_bytes':len(code)}
    triple['manifest'].update(code_text_metadata(code))
    triple['manifest']['manifest_sha256']=code_manifest_hash(triple['manifest'])
    for cap in triple['alignment']['capabilities']:
        for loc in cap['locators']:
            loc['source_id']=code_sid
            loc['snippet_sha256']=code_snippet_sha256(code,loc['lines']['start'],loc['lines']['end'])
    # Build three actual receipt-backed PDF captures, parser artifacts, and v1 records.
    pdfs=[]; artifacts=[]
    for index,paper in enumerate(material['papers'],1):
        raw=(fixture_dir/f'paper-{index}.pdf').read_bytes(); digest=h(raw)
        sid=source_id({'path': f'.raw/captured/{digest}.pdf', 'sha256': digest})
        art=pdf_artifacts(REPO,digest,index); artifacts.append(art); pdfs.append((raw,digest,sid,art))
        rec=paper['record']; rec['source_ids']=[sid]; rec['active_extraction_path']=art['document'][0]; rec['active_extraction_sha256']=h(art['document'][1])
        claim=paper['claims'][0]; text=claim['canonical_claim_text']
        ev={'relation':'supports','kind':'pdf','source_id':sid,'page':1,'ref':'#/texts/0','bbox':[1,2,10,20],
            'charspan':[0,len(text)],'artifact_path':art['document'][0],'artifact_sha256':h(art['document'][1]),'text_sha256':h(text.encode())}
        claim['evidence']=[ev]; claim['claim_id']=claim_id('paper:'+rec['paper_id'],text); claim['stable_subject_id']='paper:'+rec['paper_id']
        fp=evidence_fingerprint(claim['evidence']); genesis={'schema':'video-paper-wiki.assessment-event.v1','event_id':'ase-'+'0'*20,
            'claim_id':claim['claim_id'],'previous_event_id':None,'actor_kind':'system','transition_kind':'genesis',
            'from_assessment':None,'to_assessment':'provisional','claim_text_sha256':h(text.encode()),'evidence_fingerprint':fp,
            'decided_by':'legacy-probe','decided_at':STAMP,'reason':'Synthetic legacy genesis.'}; genesis['event_id']=assessment_event_id(genesis)
        accepted={**genesis,'event_id':'ase-'+'0'*20,'previous_event_id':genesis['event_id'],'actor_kind':'human',
            'transition_kind':'human_assessment','from_assessment':'provisional','to_assessment':'accepted','decided_by':'legacy-probe-human','reason':'Synthetic legacy acceptance.'}; accepted['event_id']=assessment_event_id(accepted)
        paper['events']=[accepted,genesis]; claim['assessment']='accepted'; claim['reviewed_at']='2026-09-09'
        # Recomputed below by the unchanged v1 compiler after replacing the
        # fixture claim/evidence/event lineage.
        paper.pop('assessment_heads', None)
    triple['alignment']['paper_id']=material['papers'][0]['record']['paper_id']
    # Keep this legacy code group unclaimed; the fixture's synthetic repository
    # capability ref intentionally overlaps a paper claim and is not a valid
    # single-primary-owner legacy graph.
    triple['repo_record']['capability_claim_refs'] = []
    aligned=material['papers'][0]['claims'][0]['evidence'][0]
    officiality = {k:v for k,v in aligned.items() if k!='relation'}
    # Exercise the accepted legacy contextual float slot in alignment evidence;
    # compiler claims/events remain integer-JCS-safe and retain one exact
    # fingerprint lineage.
    officiality['bbox'] = [1.25, 2.5, 10.0, 20.75]
    triple['alignment']['officiality']['evidence']=[officiality]
    material['code']=[triple]
    material['concepts']=concept_items_for_papers([x['record'] for x in material['papers']])
    return material,code,pdfs,artifacts,triple

def payloads_for_legacy(material,code,pdfs,artifacts,triple):
    payloads={}
    source_rows={'schema':'claude-obsidian.source-ledger.v1','generated_at':STAMP,'sources':{
        sid:{'origin':{'kind':'file','locator':f'.raw/captured/{digest}.pdf'},'content_kind':'document','title':f'Legacy PDF {i}',
            'authority':'primary','review_status':'active','pages':[],'content_sha256':digest,'ingested_at':'2026-09-09',
            'retrieved_at':None,'refresh_due':'2099-01-01','independence_key':f'legacy-pdf-{i}','supersedes':None}
        for i,(_raw,digest,sid,_art) in enumerate(pdfs,1)}}
    code_sid = triple['manifest']['capture']['source_id']
    source_rows['sources'][code_sid]={'origin':{'kind':'file','locator':triple['manifest']['capture']['stored_path']},'content_kind':'code',
        'title':'Legacy code capture','authority':'primary','review_status':'active','pages':[],'content_sha256':h(code),'ingested_at':'2026-09-09',
        'retrieved_at':None,'refresh_due':'2099-01-01','independence_key':'legacy-code','supersedes':None}
    ledger_rows={}
    for paper in material['papers']:
        claim=paper['claims'][0]; page='wiki/papers/'+paper_page_slug(paper['record']['paper_id'])+'.md'
        ledger_rows[claim['claim_id']]={'text':claim['canonical_claim_text'],'risk':'normal','assessment':'accepted','confidence':'high',
            'reviewed_at':'2026-09-09','location':{'path':page},'evidence':[encode_evidence(claim['evidence'][0])], 'notes':None,'supersedes':None}
    payloads[SOURCE_LEDGER]=canonicalize(source_rows)
    payloads[CLAIM_LEDGER]=canonicalize({'schema':'claude-obsidian.claim-ledger.v1','generated_at':STAMP,'claims':ledger_rows})
    for i,(raw,digest,sid,art) in enumerate(pdfs,1):
        payloads[f'.raw/captured/{digest}.pdf']=raw
        for path,data in (art['document'],art['parser'],art['model'],art['run']):payloads[path]=data
        paper=material['papers'][i-1]; rec=paper['record']; slug=paper_page_slug(rec['paper_id'])
        payloads[f'wiki/meta/records/papers/{slug}.json']=canonicalize(rec)
        for event in paper['events']:payloads[f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json"]=canonicalize(event)
        # The generic v1 publisher expects the legacy prospective triple's
        # compiler-input paths. These are integer-only legacy claim material;
        # the positive float compatibility probe lives in alignment's
        # contextual officiality evidence above.
        payloads[f'.raw/derived/compiler-input/{slug}-claims.json']=canonicalize(paper['claims'])
        payloads[f'.raw/derived/compiler-input/{slug}-events.json']=canonicalize(paper['events'])
    payloads[triple['manifest']['capture']['stored_path']]=code
    manifest_raw=canonicalize(triple['manifest'])
    # Legacy alignment is an existing projection resource: its contextual PDF
    # evidence admits finite bbox numbers, while the closed JCS encoder rejects
    # all floats. Preserve that legacy JSON spelling for the receipt-backed
    # fixture; source_state parses it through parse_projection_json.
    alignment_raw=json.dumps(triple['alignment'], ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    payloads[f'.raw/derived/code-manifests/{h(manifest_raw)}.json']=manifest_raw
    payloads[f'.raw/derived/alignment-manifests/{h(alignment_raw)}.json']=alignment_raw
    repo=triple['repo_record'];payloads[f'wiki/meta/records/repos/{repo_page_slug(repo["repo_id"])}.json']=canonicalize(repo)
    payloads.update(legacy_compile_pages(material))
    return payloads

def legacy_groups(material):
    groups=[]
    for paper in material['papers']:
        slug=paper_page_slug(paper['record']['paper_id']); groups.append({'group_id':'paper-'+slug,
            'paper_record':f'wiki/meta/records/papers/{slug}.json','claims':f'.raw/derived/compiler-input/{slug}-claims.json','events':f'.raw/derived/compiler-input/{slug}-events.json'})
    repo=material['code'][0]['repo_record']; manifest=canonicalize(material['code'][0]['manifest'])
    alignment=json.dumps(material['code'][0]['alignment'], ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    groups.append({'group_id':'code-'+repo_page_slug(repo['repo_id']),'code_manifest':f'.raw/derived/code-manifests/{h(manifest)}.json',
        'repo_record':f'wiki/meta/records/repos/{repo_page_slug(repo["repo_id"])}.json','alignment':f'.raw/derived/alignment-manifests/{h(alignment)}.json'})
    return groups

def capture_code_bytes(checkout: Path, vault: Path, code: bytes, *, batch_id: str, repository: str, commit: str, source_path: str):
    digest = h(code)
    plan = complete_ingest_plan(code_evidence_request(batch_id=batch_id, repository=repository, commit=commit, source_path=source_path))
    plan_bytes = canonicalize(plan)
    stage_bytes(batch_id=batch_id, relative=("plan", "ingest-plan.v1.json"), data=plan_bytes)
    ref = make_approval_ref(plan, input_sha256=digest)
    from video_paper_wiki.code_evidence_contracts import code_proposal_hash, code_text_metadata, validate_code_evidence_manifest
    proposal = {
        "schema": "video-paper-wiki.code-evidence-manifest.v1", "state": "proposal",
        "origin": {"repository": repository, "commit": commit, "path": source_path},
        "payload": {"sha256": digest, "size_bytes": len(code)}, "media_type": "text/plain", "encoding": "utf-8",
        "line_canonicalization": "utf8-lf-v1", **code_text_metadata(code), "proposal_sha256": "0" * 64,
    }
    proposal["proposal_sha256"] = code_proposal_hash(proposal)
    proposal = validate_code_evidence_manifest(proposal, payload=code)
    request = validate_staged_code_capture_request({
        "schema": "video-paper-wiki.staged-code-capture-request.v1", "batch_id": batch_id,
        "plan_sha256": h(plan_bytes), "plan_size_bytes": len(plan_bytes), "approval_ref": ref,
        "approval_ref_sha256": approval_ref_sha256(ref), "payload_file": f"prepared/{digest}.blob", "manifest": proposal,
    })
    staged = _stage_prepared_pdf_capture(batch_id=batch_id, plan_bytes=plan_bytes,
        plan_identity=(checkout / ".work" / batch_id / "plan" / "ingest-plan.v1.json").lstat(),
        blob_name=f"{digest}.blob", blob=code, request_factory=lambda: canonicalize(request),
        request_name="staged-code-capture-request.v1.json")
    authority = inspect_staged_code_capture(prepared=staged.request_path, operation_id=batch_id, upstream_root=UPSTREAM, vault_root=vault)
    applied = apply_capture(checkout, vault, authority)
    return authority, applied

def build_legacy(tmp:Path):
    checkout=tmp/'checkout';checkout.mkdir();make_checkout(checkout);os.chdir(checkout)
    vault=tmp/'vault';bootstrap_genesis(checkout,vault,tmp)
    fixture_dir=tmp/'fixture';fixture_builder.main(fixture_dir)
    material,code,pdfs,artifacts,triple=make_initial_material(fixture_dir)
    # Establish all raw captures through the isolated staged-capture receipt
    # path first. The subsequent generic publication may then bind these
    # immutable bytes and add only ledgers/records/derived artifacts/pages.
    for index, (raw, _digest, _sid, _art) in enumerate(pdfs, 1):
        capture_pdf_bytes(checkout, vault, raw, batch_id=f'legacy-capture-{index}')
    code_capture, _code_applied = capture_code_bytes(checkout, vault, code, batch_id='legacy-code-capture',
        repository=triple['manifest']['origin']['repository'], commit=triple['manifest']['origin']['commit'], source_path=triple['manifest']['origin']['path'])
    # The pinned code adapter chooses the exact source ID and `.bin` path from
    # the inspected receipt; bind the legacy manifest/alignment to that output.
    triple['manifest'] = code_capture['manifest']
    code_sid = triple['manifest']['capture']['source_id']
    code_path = triple['manifest']['capture']['stored_path']
    triple['manifest']['capture']['stored_path'] = code_path
    triple['manifest']['manifest_sha256'] = code_manifest_hash(triple['manifest'])
    for cap in triple['alignment']['capabilities']:
        for loc in cap['locators']:
            loc['source_id'] = code_sid
    payloads=payloads_for_legacy(material,code,pdfs,artifacts,triple)
    payloads={path: raw for path, raw in payloads.items() if not path.startswith('.raw/captured/')}
    # The generic publication facade intentionally decodes every JSON payload
    # with its integer-only strict reader. Legacy alignment projections are
    # allowed to retain contextual finite bbox floats, so exercise that exact
    # existing receipt path with the shared transaction assembler directly;
    # no production code or Vault outside this temporary fixture is touched.
    snap0 = _Snapshot(vault)
    audit0 = audit_integrity(vault, _snapshot=snap0)
    payload_bytes = dict(payloads)
    prior_receipt_bytes = {audit0['head']['receipt_path']: snap0.read(audit0['head']['receipt_path'])}
    with _open_batch_session('legacy-state', create=True) as session:
        children = _assemble_publication_transaction(operation_id='legacy-state', operation_type='ingest',
            batch='legacy-state', payload_bytes=payload_bytes, claimed_input_paths=[], read_bytes=prior_receipt_bytes,
            audit=audit0, snapshot=snap0, session=session, upstream_root=UPSTREAM, checkout=checkout, vault=vault)
    snap0.close()
    bundle = Path(children['transaction_staging']['bundle_file'])
    if not bundle.is_absolute(): bundle = checkout / '.work' / 'legacy-state' / bundle
    applied = _apply_bundle(vault, bundle, children['transaction']['inspection']['approval_sha256'])
    authority=children
    snap=_Snapshot(vault)
    try:
        audit=audit_integrity(vault,_snapshot=snap)
        state=collect_source_state(snap,audit)
        return {'checkout':checkout,'vault':vault,'material':material,'code':code,'pdfs':pdfs,'triple':triple,'payloads':payloads,'audit':audit,'state':state,'authority':authority,'snap':snap}
    except:
        snap.close();raise

def _error_record(exc: Exception) -> dict:
    return {"error_type": type(exc).__name__, "code": getattr(exc, "code", None),
            "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}

def _apply_direct_overlay(checkout: Path, vault: Path, payloads: dict[str, bytes], operation_id: str) -> None:
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        previous = {audit['head']['receipt_path']: snapshot.read(audit['head']['receipt_path'])}
        with _open_batch_session(operation_id, create=True) as session:
            children = _assemble_publication_transaction(operation_id=operation_id, operation_type='ingest',
                batch=operation_id, payload_bytes=dict(payloads), claimed_input_paths=[], read_bytes=previous,
                audit=audit, snapshot=snapshot, session=session, upstream_root=UPSTREAM, checkout=checkout, vault=vault)
        bundle = Path(children['transaction_staging']['bundle_file'])
        if not bundle.is_absolute(): bundle = checkout / '.work' / operation_id / bundle
        _apply_bundle(vault, bundle, children['transaction']['inspection']['approval_sha256'])
    finally:
        snapshot.close()

def _refusal(checkout: Path, vault: Path, payloads: dict[str, bytes], label):
    _apply_direct_overlay(checkout, vault, payloads, 'legacy-' + label)
    snapshot = _Snapshot(vault)
    try:
        audit = audit_integrity(vault, _snapshot=snapshot)
        collect_source_state(snapshot, audit)
    except Exception as exc:
        snapshot.close()
        return {"label": label, "accepted": False, **_error_record(exc)}
    snapshot.close()
    return {"label": label, "accepted": True, "error_type": None, "code": None,
            "message": "unexpectedly accepted", "details": {}}

def main():
    tmp=Path(tempfile.mkdtemp(prefix='source-state-legacy-r1-',dir='/private/tmp'))
    result=build_legacy(tmp)
    state, audit, payloads = result['state'], result['audit'], result['payloads']
    out = Path(__file__).resolve().parent / 'result'
    actual_root = out / 'payloads' / 'actual'
    if actual_root.exists(): shutil.rmtree(actual_root)
    actual_root.mkdir(parents=True, exist_ok=True)
    for path, raw in sorted(state['bytes'].items()):
        target = actual_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    alignment_path = next(path for path in payloads if path.startswith('.raw/derived/alignment-manifests/'))
    alignment_raw = payloads[alignment_path]
    alignment_doc = json.loads(alignment_raw)
    float_bbox = alignment_doc['officiality']['evidence'][0]['bbox']
    float_bbox_admitted = any(type(value) is float for value in float_bbox)

    # Add a second validly shaped alignment for the same repository/commit.
    # The complete code-group join must refuse the ambiguity rather than choose
    # the first directory entry.
    ambiguous_doc = copy.deepcopy(alignment_doc)
    ambiguous_doc['officiality']['evidence'][0]['bbox'] = [1, 2, 10, 20]
    ambiguous_raw = canonicalize(ambiguous_doc)
    ambiguous_path = '.raw/derived/alignment-manifests/' + h(ambiguous_raw) + '.json'

    # Add a canonical alignment for an unrepresented repository/commit. The
    # complete join must reject the orphan rather than discard it.
    orphan_doc = copy.deepcopy(alignment_doc)
    orphan_doc['repository'] = 'OrphanOrg/OrphanRepo'
    orphan_doc['commit'] = 'b' * 40
    orphan_doc['officiality']['evidence'][0]['bbox'] = [1, 2, 10, 20]
    for capability in orphan_doc['capabilities']:
        for locator in capability['locators']:
            if locator['kind'] == 'code':
                locator['repository'] = orphan_doc['repository']
                locator['commit'] = orphan_doc['commit']
    orphan_raw = canonicalize(orphan_doc)
    orphan_path = '.raw/derived/alignment-manifests/' + h(orphan_raw) + '.json'

    ambiguous_vault = tmp / 'ambiguous-vault'
    orphan_vault = tmp / 'orphan-vault'
    shutil.copytree(result['vault'], ambiguous_vault)
    shutil.copytree(result['vault'], orphan_vault)
    refusals = [
        _refusal(result['checkout'], ambiguous_vault, {ambiguous_path: ambiguous_raw}, 'ambiguous-code-alignment'),
        _refusal(result['checkout'], orphan_vault, {orphan_path: orphan_raw}, 'orphan-code-alignment'),
    ]
    summary = {
        'probe': 'source-state-legacy-r1',
        'temporary_fixture_only': True,
        'audit_classification': audit['classification'],
        'head_sequence': audit['head']['sequence'],
        'receipt_paths': sorted(audit['receipts']),
        'ever_claimed_raw_count': len(audit['ever_claimed_raw']),
        'state_profile': state['profile'],
        'state_structural_only': state['structural_only'],
        'counts': state['counts'],
        'page_paths': sorted(state['pages']),
        'basis': state['basis'],
        'float_bbox_admitted_in_legacy_alignment': float_bbox_admitted,
        'float_bbox': [repr(value) for value in float_bbox],
        'source_ids': sorted(state['source_ledger']['sources']),
        'refusals': refusals,
    }
    result_path = out / 'source-state-legacy-r1-result.json'
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_bytes(canonicalize(summary))
    result['snap'].close()
    print(json.dumps(summary, ensure_ascii=False, separators=(',', ':')))

if __name__=='__main__':main()
