from __future__ import annotations
import copy, json, hashlib, sys
from pathlib import Path
sys.path.insert(0, '/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/source-semantics-v1/terminal-1/source/tests')
from source_semantics_fixture import GOLDEN_AUTHORITY, GOLDEN_LEGACY, GOLDEN_MIXED, GOLDEN_MIXED_PAGES, inventory_arguments, compile_fixture
from video_paper_wiki.canonical_compiler import compile_pages as compile_v1
from video_paper_wiki.canonical_compiler_v2 import compile_pages
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import assessment_event_id
from video_paper_wiki.markdown_locator import evidence_fingerprint_versioned, evidence_profile
from video_paper_wiki.source_semantics_contracts import COMPILE

EMPTY={'raw_sources':{},'extraction_artifacts':{},'registration_ledgers':{},'head_bytes':None,'receipt_bytes':{}}

def run(label, material, kwargs, expected=None, expect_pass=False, check=None):
    try:
        out=compile_pages(material, **kwargs)
    except Exception as exc:
        if not isinstance(exc, ContractError):
            return {'id':label,'status':'error','exception':type(exc).__name__,'message':str(exc)}
        got={'code':exc.code,'exit_code':exc.exit_code,'pointer':exc.details.get('instance_pointer'),'message':exc.message}
        status='pass' if expected and (got['code'],got['exit_code'])==tuple(expected) else 'fail'
        return {'id':label,'status':status,'observed':got,'expected':None if expected is None else {'code':expected[0],'exit_code':expected[1]}}
    try:
        check_result=check(out) if check else None
        ok=(expect_pass and (check_result is None or check_result is True))
    except Exception as exc:
        return {'id':label,'status':'fail','unexpected_success':True,'check_exception':type(exc).__name__+': '+str(exc)}
    return {'id':label,'status':'pass' if ok else 'fail','success':True,'check':check_result}

results=[]

def reseal_claim_events(group):
    new_fp=evidence_fingerprint_versioned(group["claims"][0]["evidence"])
    events=group["events"]
    old_to_new={}
    remaining=list(events)
    while remaining:
        progress=False
        for event in list(remaining):
            old=event["event_id"]
            previous=event["previous_event_id"]
            if previous is not None and previous not in old_to_new:
                continue
            event["evidence_fingerprint"]=new_fp
            if event["schema"].endswith("assessment-event.v2"):
                event["evidence_profile"]=evidence_profile(group["claims"][0]["evidence"])
            if previous is not None:
                event["previous_event_id"]=old_to_new[previous]
            event["event_id"]=assessment_event_id(event)
            old_to_new[old]=event["event_id"]
            remaining.remove(event); progress=True
        if not progress: raise AssertionError("event chain cannot be resealed")
results.append(run('baseline-mixed', copy.deepcopy(GOLDEN_MIXED), copy.deepcopy(GOLDEN_AUTHORITY), expect_pass=True, check=lambda out: out=={p:t.encode() for p,t in GOLDEN_MIXED_PAGES.items()}))
# Root/group closed shape beats owner/graph.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'].append(copy.deepcopy(m['papers'][1])); m['papers'][1]['record']['title']=None
results.append(run('shape-before-duplicate-owner',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('SCHEMA_INVALID',2)))
# Real calendar validation beats graph errors.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['record']['updated_at']='2026-02-30T00:00:00Z'; m['papers'][1]['record']['aliases'].append(m['papers'][0]['record']['paper_id'])
results.append(run('date-before-alias-graph',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('SCHEMA_INVALID',2)))
# Owner/alias phase beats source maps.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['record']['aliases'].append('arxiv:2311.15127'); kw=copy.deepcopy(GOLDEN_AUTHORITY); kw['raw_sources']={}
results.append(run('owner-before-source-map',m,kw,expected=('COMPILE_INPUT_INVALID',2)))
# Complete map phase beats display head.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['record']['display_head']['sha256']='0'*64; kw=copy.deepcopy(GOLDEN_AUTHORITY); kw['raw_sources']={}
results.append(run('source-map-before-display',m,kw,expected=('SOURCE_INVENTORY_INVALID',2)))
# Display phase beats assessment/event failure.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['display_decisions'][0]['association']['association_id']='sva-'+'0'*64; m['papers'][1]['events'][0]['event_id']='ase-'+'0'*20
results.append(run('display-before-assessment',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('SOURCE_DISPLAY_INVALID',2)))
# Assessment graph phase beats locator and taxonomy failure.
m=copy.deepcopy(GOLDEN_MIXED); g=m['papers'][1]; human=next(e for e in g['events'] if e['transition_kind']=='human_assessment'); human['from_assessment']='accepted'; human['event_id']=assessment_event_id(human); loc=next(e for e in g['claims'][0]['evidence'] if e['kind']=='markdown'); loc['charspan']=[0,1]; m['concepts'][0]['label_zh']='forged'
results.append(run('assessment-before-locator',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('ASSESSMENT_CHAIN_INVALID',2)))
# Locator phase beats taxonomy/label failure.
m=copy.deepcopy(GOLDEN_MIXED); loc=next(e for e in m['papers'][1]['claims'][0]['evidence'] if e['kind']=='markdown'); loc['charspan']=[0,1]; reseal_claim_events(m['papers'][1]); m['papers'][1]['assessment_heads']=derive_assessment_heads(claims=m['papers'][1]['claims'],events=m['papers'][1]['events']); m['concepts'][0]['label_zh']='forged'
results.append(run('locator-before-taxonomy',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('MARKDOWN_LOCATOR_INVALID',2)))
# Taxonomy validation follows all content graphs.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['record']['taxonomy'][0]['slug']='unknown-term'
results.append(run('taxonomy-after-graphs',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('COMPILE_INPUT_INVALID',2)))
# Empty, unselected v2 paper remains legal with empty source authority.
m=copy.deepcopy(GOLDEN_MIXED); g=m['papers'][1]; r=g['record']; g['claims']=[]; g['events']=[]; g['associations']=[]; g['display_decisions']=[]; g['assessment_heads']={}; r['section_claim_refs']=[]; r['source_associations']=[]; r['display_head']=None; r['active_extraction_path']=None; r['active_extraction_sha256']=None; r['source_ids']=[]
results.append(run('empty-unselected-v2',m,copy.deepcopy(EMPTY),expected=('SCHEMA_INVALID',2)))
# Provisional claim retains evidence but does not invent a conclusion.
m,kw=compile_fixture(selected=False,accepted=False)
results.append(run('provisional-evidence-status',m,kw,expect_pass=True,check=lambda out: '- 暂无已审核的核心结论。' in next(iter(out.values())).decode() and 'assessment: `provisional`' in next(iter(out.values())).decode()))
# Empty evidence is intentionally probed for phase/code stability.
m=copy.deepcopy(GOLDEN_MIXED); m['papers'][1]['claims'][0]['evidence']=[]; reseal_claim_events(m['papers'][1]); m['papers'][1]['assessment_heads']=derive_assessment_heads(claims=m['papers'][1]['claims'],events=m['papers'][1]['events'])
results.append(run('empty-claim-evidence',m,copy.deepcopy(GOLDEN_AUTHORITY),expected=('COMPILE_INPUT_INVALID',2)))
# Legacy-only delegated bytes and no-v2 authority refusal.
results.append({'id':'legacy-delegation-empty-authority','status':'pass' if compile_pages(GOLDEN_LEGACY|{'schema':COMPILE},**EMPTY)==compile_v1(GOLDEN_LEGACY) else 'fail','success':True})
try:
    compile_pages(GOLDEN_LEGACY|{'schema':COMPILE},**GOLDEN_AUTHORITY)
except ContractError as exc:
    results.append({'id':'legacy-refuses-unrelated-authority','status':'pass' if (exc.code,exc.exit_code)==('SOURCE_INVENTORY_INVALID',2) else 'fail','observed':{'code':exc.code,'exit_code':exc.exit_code,'pointer':exc.details.get('instance_pointer')}})
else: results.append({'id':'legacy-refuses-unrelated-authority','status':'fail','unexpected_success':True})
# Mixed legacy + modern baseline is a code/legacy compatibility probe.
results.append({'id':'mixed-code-legacy-compatibility','status':'pass' if set(compile_pages(copy.deepcopy(GOLDEN_MIXED),**copy.deepcopy(GOLDEN_AUTHORITY)))==set(GOLDEN_MIXED_PAGES) else 'fail','success':True})

report={'schema':'video-paper-wiki.source-semantics-local-compiler-probes.v1','candidate':'/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/source-semantics-v1/terminal-1/source','contract_sha256':'ad21572558bf1053a248f07d5bb3e950780765aecb8ed4ef4da29025047366f9','results':results,'summary':{'total':len(results),'passed':sum(x['status']=='pass' for x in results),'failed':sum(x['status']=='fail' for x in results),'errors':sum(x['status']=='error' for x in results)}}
path=Path('/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/source-semantics-local-r1/probes/compiler-phase-review.json')
path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))
