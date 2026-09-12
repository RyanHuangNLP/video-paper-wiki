"""Independent history goldens: standard-library oracle; no application imports."""
from pathlib import Path
import copy,hashlib,json,re,unicodedata
H=lambda b:hashlib.sha256(b).hexdigest()
def canonical(v):
 # Every object key in generated identity material is ASCII; sorting therefore
 # agrees with UTF-16 order. No float enters any identity material.
 def walk(x):
  if type(x) is dict:
   assert all(type(k)is str and k.isascii() for k in x)
   for val in x.values():walk(val)
  elif type(x)is list:
   for val in x:walk(val)
  else:assert x is None or type(x) in (str,int,bool)
 walk(v)
 return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def claimid(subject,text):return 'clm-'+H(b'video-paper-wiki.claim.v1\0'+subject.encode()+b'\0'+re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text)).strip().encode())[:20]
PDF=('relation','kind','source_id','page','ref','artifact_path','artifact_sha256','text_sha256');CODE=('relation','kind','source_id','repository','commit','path','lines','snippet_sha256')
def fingerprint(items):
 rows=[]
 for e in items:
  d={k:copy.deepcopy(e[k]) for k in (PDF if e['kind']=='pdf' else CODE)}
  if d['kind']=='code':d['repository']=d['repository'].casefold()
  rows.append(d)
 return H(canonical(sorted(rows,key=canonical)))
def sign(e):
 e['event_id']='ase-'+H(canonical({k:v for k,v in e.items() if k!='event_id'}))[:20]
 return e
PDF_E={'kind':'pdf','source_id':'src-abc','page':1,'ref':'#/texts/0','artifact_path':'.raw/derived/paper/docling/fp/document.json','artifact_sha256':'a'*64,'text_sha256':'b'*64,'bbox':[0.1,0.25,2.0,3.5],'charspan':[0,7],'relation':'supports'}
CODE_E={'kind':'code','source_id':'src-code','repository':'Owner/Repo','commit':'c'*40,'path':'src/a.py','lines':{'start':1,'end':3},'snippet_sha256':'d'*64,'symbol':'  Compute.α  ','relation':'uncertain'}
PAPER='paper:sha256:'+'1'*64;REPO='repo:github:owner/repo'
def binding(text='A\u00a0claim',subject=PAPER,evidence=None):
 evidence=copy.deepcopy([] if evidence is None else evidence)
 return {'claim_id':claimid(subject,text),'stable_subject_id':subject,'canonical_claim_text':text,'evidence':evidence,'assessment':'provisional','reviewed_at':None}
def event(b,parent=None,*,to='provisional',fp=None,time='2026-09-01T00:00:00Z',system=False):
 genesis=parent is None;system=system or genesis
 return sign({'schema':'video-paper-wiki.assessment-event.v1','claim_id':b['claim_id'],'previous_event_id':None if genesis else parent['event_id'],'actor_kind':'system' if system else 'human','transition_kind':'genesis' if genesis else 'evidence_invalidation' if system else 'human_assessment','from_assessment':None if genesis else parent['to_assessment'],'to_assessment':to,'claim_text_sha256':H(b['canonical_claim_text'].encode()),'evidence_fingerprint':fingerprint(b['evidence']) if fp is None else fp,'decided_by':'fixture actor, not authorization','decided_at':time,'reason':' synthetic independent fixture  '})
def finish(b,events):
 b['assessment']=events[-1]['to_assessment'];b['reviewed_at']=events[-1]['decided_at'][:10] if events[-1]['actor_kind']=='human' else None
 return {'claims':[b],'events':events}
def genesis(evidence=None,text='A\u00a0claim',subject=PAPER):
 b=binding(text,subject,evidence);return finish(b,[event(b)])
def human(evidence=None,to='accepted',time='2026-09-01T00:00:00Z'):
 b=binding(evidence=evidence);g=event(b);return finish(b,[g,event(b,g,to=to,time=time)])
pos=[];neg=[]
def positive(name,v):
 heads={b['claim_id']:next(e['event_id'] for e in v['events'] if e['claim_id']==b['claim_id'] and not any(x['previous_event_id']==e['event_id'] for x in v['events'])) for b in v['claims']}
 pos.append({'name':name,'input':v,'expected_heads':dict(sorted(heads.items())),'current_fingerprints':{b['claim_id']:fingerprint(b['evidence']) for b in v['claims']},'raw_text_sha256':{b['claim_id']:H(b['canonical_claim_text'].encode()) for b in v['claims']}})
def negative(name,v,code,pointer=None,exit_code=2,note=None):
 d={'name':name,'input':v,'expected_error':code,'exit_code':exit_code}
 if pointer is not None:d['pointer']=pointer
 if note:d['note']=note
 neg.append(d)
positive('empty',{'claims':[],'events':[]});positive('paper_genesis_empty_evidence',genesis());positive('repo_genesis_code_evidence',genesis([CODE_E],subject=REPO));positive('raw_unicode_text_fractional_bbox',human([PDF_E,CODE_E],time='0001-01-01T00:00:00.000000001Z'));positive('max_gregorian_date',human(time='9999-12-31T23:59:59.999999999Z'))
# Every permitted non-no-op human edge across all five assessments.
for start in ['provisional','accepted','contested','unsupported','deprecated']:
 for end in ['accepted','contested','unsupported','deprecated']:
  if start==end:continue
  b=binding();es=[event(b)]
  if start!='provisional':es.append(event(b,es[-1],to=start))
  es.append(event(b,es[-1],to=end));positive('human_edge_'+start+'_to_'+end,finish(b,es))
# Changed FP after invalidation, later return to a prior FP, decreasing UTC.
b=binding(evidence=[PDF_E]);empty=fingerprint([]);current=fingerprint([PDF_E]);es=[event(b,fp=empty),];es.append(event(b,es[-1],to='accepted',fp=empty,time='2026-09-01T00:00:00.100Z'));es.append(event(b,es[-1],system=True,fp=current,time='2026-08-31T00:00:00Z'));es.append(event(b,es[-1],to='contested',fp=current,time='2026-08-31T00:00:00Z'));es.append(event(b,es[-1],system=True,fp=empty));es.append(event(b,es[-1],system=True,fp=current));positive('historical_and_returned_fingerprint_provisional_invalidation',finish(b,es))
a=human([PDF_E]);z=genesis([CODE_E],subject=REPO);positive('multiple_claims_shuffled',{'claims':z['claims']+a['claims'],'events':list(reversed(a['events']+z['events']))})
a=human([PDF_E,CODE_E]);a['claims'][0]['evidence'].reverse();positive('evidence_permutation',a)
a=human([PDF_E,CODE_E]);a['claims'][0]['evidence'][0]['bbox']=[2.5,1.5,0.5,-0.0];a['claims'][0]['evidence'][0]['charspan']=[3,8];a['claims'][0]['evidence'][1]['symbol']='other display';positive('display_fields_do_not_invalidate',a)
positive('duplicate_evidence_is_retained',human([PDF_E,PDF_E]));positive('raw_text_65536_ascii',genesis(text='a'*65536));positive('raw_text_65536_utf8',genesis(text='界'*21845+'a'))
b=binding();es=[event(b)]
for i in range(1,801):es.append(event(b,es[-1],to='accepted' if i%2 else 'contested'))
positive('iterative_801_event_chain',finish(b,es))
# Negatives isolate specific later relationships using honest freshly signed IDs.
a=genesis();a['claims'][0]['claim_id']='clm-'+'0'*20;negative('claim_id_mismatch',a,'CLAIM_ID_MISMATCH')
a=genesis();a['claims'].append(copy.deepcopy(a['claims'][0]));negative('duplicate_equal_binding',a,'PRIMARY_OWNER_INVALID')
a=genesis();d=copy.deepcopy(a['claims'][0]);d['canonical_claim_text']='different identity text';a['claims'].append(d);negative('stated_id_collision_before_mismatch',a,'CLAIM_ID_COLLISION',exit_code=75,note='Conflicting supplied bindings sharing a stated ID, not a discovered genuine hash collision.')
a=genesis();d=copy.deepcopy(a['claims'][0]);d['canonical_claim_text']='A claim';a['claims'].append(d);negative('nfkc_equivalent_duplicate_binding',a,'PRIMARY_OWNER_INVALID')
a=genesis();a['events']=[];negative('missing_history',a,'ASSESSMENT_CHAIN_INVALID','/claims/0/claim_id')
a=genesis();a['claims']=[];negative('unknown_claim_history',a,'ASSESSMENT_CHAIN_INVALID')
a=genesis();a['events'].append(copy.deepcopy(a['events'][0]));negative('duplicate_event',a,'ASSESSMENT_CHAIN_INVALID')
a=genesis();e=copy.deepcopy(a['events'][0]);e['reason']='second genesis';sign(e);a['events'].append(e);negative('two_geneses',a,'ASSESSMENT_CHAIN_INVALID')
a=human();a['events'][-1]['previous_event_id']='ase-'+'f'*20;sign(a['events'][-1]);negative('dangling_parent',a,'ASSESSMENT_CHAIN_INVALID')
a=human();z=genesis(subject=REPO);a['events'][-1]['previous_event_id']=z['events'][0]['event_id'];sign(a['events'][-1]);a['claims']+=z['claims'];a['events']+=z['events'];negative('cross_claim_parent',a,'ASSESSMENT_CHAIN_INVALID')
a=human();s=copy.deepcopy(a['events'][-1]);s['to_assessment']='contested';sign(s);a['events'].append(s);negative('fork',a,'ASSESSMENT_CHAIN_INVALID')
a=human(to='contested');a['events'][-1]['from_assessment']='accepted';sign(a['events'][-1]);negative('state_edge_mismatch',a,'ASSESSMENT_CHAIN_INVALID')
a=human();e=event(a['claims'][0],a['events'][-1],to='accepted');a['events'].append(e);negative('human_noop',a,'ASSESSMENT_CHAIN_INVALID')
a=human();a['events'][-1]['evidence_fingerprint']=fingerprint([PDF_E]);sign(a['events'][-1]);negative('human_changes_fingerprint',a,'EVIDENCE_FINGERPRINT_MISMATCH')
a=genesis();a['events'].append(event(a['claims'][0],a['events'][-1],system=True));negative('invalidation_unchanged_fingerprint',a,'EVIDENCE_FINGERPRINT_MISMATCH')
a=genesis();a['claims'][0]['evidence']=[PDF_E];negative('head_current_fingerprint_mismatch',a,'EVIDENCE_FINGERPRINT_MISMATCH')
a=human([PDF_E]);a['claims'][0]['evidence'].append(copy.deepcopy(PDF_E));negative('evidence_multiplicity_changed',a,'EVIDENCE_FINGERPRINT_MISMATCH')
a=human([PDF_E]);a['claims'][0]['evidence'][0]['relation']='contradicts';negative('evidence_relation_changed',a,'EVIDENCE_FINGERPRINT_MISMATCH')
a=human();a['claims'][0]['canonical_claim_text']='A claim';negative('same_claim_id_changed_persisted_text',a,'CROSS_OBJECT_IDENTITY_MISMATCH')
a=human();a['events'][-1]['claim_text_sha256']='0'*64;sign(a['events'][-1]);negative('event_exact_text_mismatch',a,'CROSS_OBJECT_IDENTITY_MISMATCH')
a=genesis();a['events'][0]['event_id']='ase-'+'0'*20;negative('event_id_mismatch',a,'EVENT_ID_MISMATCH')
a=human();a['claims'][0]['assessment']='unsupported';negative('ledger_assessment_mismatch',a,'CROSS_OBJECT_IDENTITY_MISMATCH')
a=human();a['claims'][0]['reviewed_at']='2026-08-31';negative('human_utc_date_mismatch',a,'CROSS_OBJECT_IDENTITY_MISMATCH')
a=genesis();a['claims'][0]['reviewed_at']='2026-09-01';negative('system_head_reviewed_at_not_null',a,'CROSS_OBJECT_IDENTITY_MISMATCH')
for label,date in [('nonleap','2025-02-29T00:00:00Z'),('year_zero','0000-01-01T00:00:00Z'),('leap_second','2026-01-01T00:00:60Z'),('offset','2026-01-01T00:00:00+00:00'),('newline','2026-01-01T00:00:00Z\n'),('ten_fractional_digits','2026-01-01T00:00:00.1234567890Z')]:
 a=human(time=date);negative('invalid_timestamp_'+label,a,'SCHEMA_INVALID')
a=genesis();a['claims'][0]['reviewed_at']='2025-02-29';negative('invalid_review_date',a,'SCHEMA_INVALID')
a=genesis();a['claims'][0]['stable_subject_id']='concept:v1:test';negative('concept_subject_outside_profile',a,'SCHEMA_INVALID')
a=genesis([PDF_E]);a['claims'][0]['evidence'][0]['page']=True;negative('bool_page_not_int',a,'LEDGER_LOCATOR_INVALID','/claims/0/evidence/0/page')
a=genesis([PDF_E]);a['claims'][0]['evidence'][0]['source_id']+='\n';negative('locator_fullmatch_source',a,'LEDGER_LOCATOR_INVALID','/claims/0/evidence/0/source_id')
a=genesis([PDF_E]);a['claims'][0]['evidence'][0]['relation']='context';negative('domain_context_not_uncertain',a,'LEDGER_EVIDENCE_INVALID','/claims/0/evidence/0/relation')
a=genesis();a['claims'][0]['canonical_claim_text']='a'*65537;negative('raw_text_65537_ascii',a,'PROJECTION_LIMIT_EXCEEDED')
a=genesis();a['claims'][0]['canonical_claim_text']='界'*21845+'ab';negative('raw_text_65537_utf8',a,'PROJECTION_LIMIT_EXCEEDED')
# No fixed point is pretended: malformed cyclic references retain known-invalid IDs.
a=human();a['events'][0]['previous_event_id']=a['events'][-1]['event_id'];a['events'][0]['actor_kind']='human';a['events'][0]['transition_kind']='human_assessment';a['events'][0]['from_assessment']='accepted';a['events'][0]['to_assessment']='contested';negative('cycle_without_hash_fixed_point',a,'EVENT_ID_MISMATCH',note='Synthetic cycle is not signed consistently; end-to-end refusal is expected before graph traversal. Graph routine needs separately labelled stub/synthetic-ID coverage.')
root=Path('<REPO>');spec=root/'docs/ai/contracts/assessment-history-v1.md';assert H(spec.read_bytes())=='ff7e7830d9931c52c447a2a95818dca091cb6d5bc97184d1be1103072ecf44cb'
out={'contract_sha256':H(spec.read_bytes()),'baseline':'3e2bebb1d50928a7af95e07b4868bdbe8113cd0b','oracle':'Independent stdlib compact sorted ASCII-key JSON; explicit evidence field set, repository casefold, SHA256, NFKC+whitespace identity; no application import or pending API invocation.','positive':pos,'negative':neg,'source_authority_sha256':{str(p.relative_to(root)):H(p.read_bytes()) for p in [root/'src/video_paper_wiki/identity.py',root/'src/video_paper_wiki/jcs.py',root/'src/video_paper_wiki/ledger_locator.py',root/'src/video_paper_wiki/projection_runtime.py',root/'schemas/video-paper-wiki.assessment-event.v1.schema.json']}}
Path('<TMP>/vph-steward-vectors.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'positive':len(pos),'negative':len(neg),'sha256':H(Path('<TMP>/vph-steward-vectors.json').read_bytes())}))
