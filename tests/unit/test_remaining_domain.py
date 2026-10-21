from __future__ import annotations
import copy, math
from pathlib import Path
import pytest
from video_paper_wiki.backup_manifest import build_backup_manifest,verify_restored_tree
from video_paper_wiki.contracts import ContractError,validate_document
from video_paper_wiki.domain import shape_query_results,compile_concept_page
from video_paper_wiki.retrieval import evaluate_retrieval,rank_hits
from video_paper_wiki.retrieval import derive_retrieval_config
from video_paper_wiki.evidence_join import build_evidence_inventory,evidence_mapping_sha256,validate_evidence_mapping_authority
from video_paper_wiki.canonical_compiler import compile_pages

def _compile_material():
    import json,hashlib
    from video_paper_wiki import identity
    fixture_root=Path(__file__).resolve().parents[1]/'fixtures'
    record=json.loads((fixture_root/'contracts/valid/video-paper-wiki.paper-record.v1.json').read_text())
    evidence=json.loads((fixture_root/'assessment-history/complete-vectors.json').read_text())['evidence']['code']
    text='A verified compiler claim.';subject='paper:'+record['paper_id'];cid=identity.claim_id(subject,text);fp=identity.evidence_fingerprint([evidence])
    claim={'claim_id':cid,'stable_subject_id':subject,'canonical_claim_text':text,'evidence':[evidence],'assessment':'accepted','reviewed_at':'2026-09-01'}
    genesis={'schema':'video-paper-wiki.assessment-event.v1','event_id':'ase-'+'0'*20,'claim_id':cid,'previous_event_id':None,'actor_kind':'system','transition_kind':'genesis','from_assessment':None,'to_assessment':'provisional','claim_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'evidence_fingerprint':fp,'decided_by':'fixture','decided_at':'2026-09-01T00:00:00Z','reason':'Fixture genesis.'};genesis['event_id']=identity.assessment_event_id(genesis)
    accepted={**genesis,'event_id':'ase-'+'0'*20,'previous_event_id':genesis['event_id'],'actor_kind':'human','transition_kind':'human_assessment','from_assessment':'provisional','to_assessment':'accepted','decided_by':'reviewer','reason':'Fixture acceptance.'};accepted['event_id']=identity.assessment_event_id(accepted)
    record['section_claim_refs']=[{'section':'one_sentence_conclusion','claim_id':cid,'core':True,'lifecycle':'active'}]
    return {'schema':'video-paper-wiki.compile-input.v1','operation_id':'compile-test','papers':[{'record':record,'claims':[claim],'events':[accepted,genesis],'assessment_heads':{cid:accepted['event_id']}}],'code':[],'concepts':[{'axis':'task/conditioning','slug':'text-to-video','label_zh':'文生视频','label_en':'text-to-video'}]}

def test_compile_is_deterministic_and_binds_history_taxonomy():
    material=_compile_material();first=compile_pages(material);second=compile_pages(copy.deepcopy(material))
    assert first==second and sorted(first)==['wiki/concepts/task-conditioning-text-to-video.md','wiki/papers/arxiv-2311.15127.md']
    paper=first['wiki/papers/arxiv-2311.15127.md'].decode();cid=material['papers'][0]['claims'][0]['claim_id']
    assert paper.count('^'+cid)==1 and '## 实验与结果' in paper and '## 关联' in paper
    bad=copy.deepcopy(material);bad['concepts'][0]['label_zh']='伪造';
    with pytest.raises(ContractError):compile_pages(bad)

def test_query_shape_rejects_unsafe_values():
    for value in (True,float("nan"),float("inf")):
        with pytest.raises(ContractError):shape_query_results([{"path":"wiki/x.md","score":value}])
    for path in ("/x","../x","wiki\\x"):
        with pytest.raises(ContractError):shape_query_results([{"path":path,"score":1}])

def test_retrieval_policy_derivation_is_closed_and_hash_exact():
    policy={"schema":"video-paper-wiki.retrieval-policy.v1","corpus_version":"c","query_version":"q",
        "top_chunks":10,"top_papers":10,"evidence_limit":8,"per_paper_evidence_limit":2,
        "eligibility":"active-not-deprecated","paper_tie_break":"score-desc-paper-id-asc",
        "chunk_tie_break":"score-desc-paper-id-asc-chunk-id-asc"}
    result=derive_retrieval_config(policy,generation_sha256="a"*64,mapping_sha256="b"*64)
    assert result["schema"]=="video-paper-wiki.retrieval-config.v1" and result["generation_sha256"]=="a"*64
    for bad in (True,"A"*64,"a"*63):
        with pytest.raises(ContractError):derive_retrieval_config(policy,generation_sha256=bad,mapping_sha256="b"*64)
    with pytest.raises(ContractError):derive_retrieval_config({**policy,"extra":1},generation_sha256="a"*64,mapping_sha256="b"*64)

def test_concept_is_pinned_taxonomy():
    assert "文生视频" in compile_concept_page(axis="task/conditioning",slug="text-to-video",label_zh="文生视频",label_en="text-to-video")
    with pytest.raises(ContractError):compile_concept_page(axis="task/conditioning",slug="invented",label_zh="x",label_en="x")

def test_backup_manifest_round_trip_and_raw_coverage(tmp_path:Path):
    import json
    from video_paper_wiki.jcs import canonicalize
    import hashlib
    fixture_root=Path(__file__).resolve().parents[1]/'fixtures/contracts/valid'
    from video_paper_wiki.identity import receipt_intent_sha256
    receipt=json.loads((fixture_root/'video-paper-wiki.operation-receipt.v1.json').read_text());head=json.loads((fixture_root/'video-paper-wiki.operation-head.v1.json').read_text());raw_data=b"raw";page_data=b"page";raw_sha=hashlib.sha256(raw_data).hexdigest();raw_path=f'.raw/captured/{raw_sha}.pdf';receipt['claimed_inputs'][0]['path']=raw_path;receipt['claimed_inputs'][0]['sha256']=raw_sha;receipt['writes'][0]['after_sha256']=hashlib.sha256(page_data).hexdigest();receipt['intent_sha256']=receipt_intent_sha256(receipt);receipt_bytes=canonicalize(receipt);head['receipt_path']=f"wiki/meta/operations/{receipt['sequence']:012d}-{receipt['operation_id']}.json";head['receipt_sha256']=hashlib.sha256(receipt_bytes).hexdigest();head['sequence']=receipt['sequence']
    for root in (".raw/captured",".vault-meta/receipts","wiki/papers"):(tmp_path/root).mkdir(parents=True)
    (tmp_path/raw_path).write_bytes(raw_data);(tmp_path/'.raw/.manifest.json').write_bytes(b'upstream-control')
    (tmp_path/head['receipt_path']).parent.mkdir(parents=True);(tmp_path/head['receipt_path']).write_bytes(receipt_bytes);(tmp_path/"wiki/meta/registries").mkdir(parents=True);(tmp_path/"wiki/meta/registries/operation-head.json").write_bytes(canonicalize(head));(tmp_path/".vault-meta/receipts/a").write_bytes(b"receipt");(tmp_path/receipt['writes'][0]['path']).write_bytes(page_data)
    for path in tmp_path.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    manifest=build_backup_manifest(tmp_path,operation_head=head)
    assert build_backup_manifest(tmp_path)['source_anchor']==head['receipt_sha256']
    stale={**head,'sequence':head['sequence']+1}
    with pytest.raises(ContractError):build_backup_manifest(tmp_path,operation_head=stale)
    restored=tmp_path.parent/(tmp_path.name+"-restored")
    import shutil;shutil.copytree(tmp_path,restored);restored.chmod(0o700)
    assert verify_restored_tree(restored,manifest,operation_head=head,source_root=tmp_path)["valid"]
    (tmp_path/'.raw/unclaimed.bin').write_bytes(b'extra');(tmp_path/'.raw/unclaimed.bin').chmod(0o600)
    with pytest.raises(ContractError):build_backup_manifest(tmp_path,operation_head=head)
    (tmp_path/'.raw/unclaimed.bin').unlink();(tmp_path/'.raw/unclaimed-empty').mkdir(mode=0o700)
    with pytest.raises(ContractError):build_backup_manifest(tmp_path,operation_head=head)
    (tmp_path/'.raw/unclaimed-empty').rmdir();(tmp_path/'.raw/nested').mkdir(mode=0o700)
    (tmp_path/'.raw/nested/.manifest.json').write_bytes(b'forged');(tmp_path/'.raw/nested/.manifest.json').chmod(0o600)
    with pytest.raises(ContractError):build_backup_manifest(tmp_path,operation_head=head)
    (tmp_path/'.raw/nested/.manifest.json').unlink();(tmp_path/'.raw/nested').rmdir()
    (tmp_path/raw_path).unlink()
    with pytest.raises(ContractError):build_backup_manifest(tmp_path,operation_head=head)

def test_classic_zip_profile_rejects_central_forgery_and_restores(tmp_path:Path):
    import binascii,hashlib,struct
    from video_paper_wiki.backup_archive import _decode,encode_backup_archive,restore_backup_archive
    from video_paper_wiki.jcs import canonicalize
    vault=tmp_path/'source';(vault/'.raw').mkdir(parents=True);(vault/'wiki').mkdir();raw=b'alpha';unicode=b'beta'
    (vault/'.raw/a.bin').write_bytes(raw);(vault/'wiki/论文.md').write_bytes(unicode)
    for path in vault.rglob('*'):path.chmod(0o700 if path.is_dir() else 0o600)
    doc={'schema':'video-paper-wiki.backup-manifest.v1','policy':'vpwiki-private-archive-complete-set-v1','source_anchor':'a'*64,'excluded':['.vault-meta','.work'],'roots':['.raw','wiki'],
         'directories':[{'path':'.raw','mode':0o700},{'path':'wiki','mode':0o700}],
         'files':[{'path':'.raw/a.bin','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'mode':0o600},{'path':'wiki/论文.md','sha256':hashlib.sha256(unicode).hexdigest(),'size_bytes':len(unicode),'mode':0o600}],
         'raw_included':True,'manifest_sha256':'0'*64}
    doc['manifest_sha256']=hashlib.sha256(canonicalize({k:v for k,v in doc.items() if k!='manifest_sha256'})).hexdigest();archive=encode_backup_archive(vault_root=vault,manifest=doc)
    assert _decode(archive)[0]==doc
    e=struct.unpack('<IHHHHIIH',archive[-22:]);central=e[6]
    for offset in (central+16,central+20,central+38):
        bad=bytearray(archive);bad[offset]^=1
        with pytest.raises(ContractError,match='central'): _decode(bytes(bad))

def test_classic_zip_nfc_golden_is_byte_stable():
    import hashlib,json
    from video_paper_wiki.backup_archive import _decode
    root=Path('tests/fixtures/backup');raw=(root/'classic-nfc.zip').read_bytes();expected=(root/'classic-nfc.sha256').read_text().strip()
    assert hashlib.sha256(raw).hexdigest()==expected=='12d16e48d1b97db289be0b8ea38c80c9c344ce10bd6170dc1f557a05cc73504c'
    assert _decode(raw)[0]==json.loads((root/'classic-nfc.manifest.json').read_text())

def test_gate_prepare_stages_exact_content_first_request_last(tmp_path:Path,monkeypatch):
    import hashlib,json
    from tests.support import make_checkout
    from video_paper_wiki.gate_decision import CHOICES,prepare_gate
    from video_paper_wiki.identity import gate_event_id
    from video_paper_wiki.jcs import canonicalize
    make_checkout(tmp_path);monkeypatch.chdir(tmp_path);manifest={'papers':3,'repositories':5};mraw=canonicalize(manifest);decision={'schema':'video-paper-wiki.gate-decision.v1','gate_id':'HUMAN-GATE-BASELINE-001','event_id':'gde-'+'0'*20,'previous_event_id':None,'actor_kind':'human','choice':'keep-modelscope','baseline_manifest_sha256':hashlib.sha256(mraw).hexdigest(),'derived_full_map_repo_ids':CHOICES['keep-modelscope'],'decided_by':'synthetic-test-only','decided_at':'2026-09-02T00:00:00Z','reason':'mechanical fixture'};decision['event_id']=gate_event_id(decision)
    dpath=tmp_path/'decision.json';mpath=tmp_path/'manifest.json';dpath.write_bytes(canonicalize(decision));mpath.write_bytes(mraw)
    result=prepare_gate(decision_path=dpath,baseline_manifest_path=mpath,batch_id='g1');request=Path(result['request_path']);assert request.is_file()
    assert sorted(x.name for x in request.parent.iterdir())==['content','staged-gate-request.v1.json']
    assert len(list((request.parent/'content').iterdir()))==2
    bad=tmp_path/'float.json';bad.write_bytes(b'{"x":1.5}')
    decision['baseline_manifest_sha256']=hashlib.sha256(bad.read_bytes()).hexdigest();decision['event_id']=gate_event_id(decision);dpath.write_bytes(canonicalize(decision))
    with pytest.raises(Exception) as caught:prepare_gate(decision_path=dpath,baseline_manifest_path=bad,batch_id='g2')
    assert caught.value.code=='GATE_MANIFEST_INVALID'

def test_ranking_ties_and_gold_non_input():
    h="sha256:"+"b"*64
    inventory=build_evidence_inventory(_compile_material()['papers']);unit=inventory['units'][0]
    mapping={"schema":"video-paper-wiki.evidence-mapping-authority.v1","inventory":inventory,"profile":"claude-obsidian.chunk-v1+bm25-v2","generation_sha256":"a"*64,"mapping_sha256":"0"*64,"chunks":[{"chunk_id":"c-000002:0","path":".vault-meta/chunks/c-000002/chunk-000.json","body_hash":h,"page_body_hash":h,"paper_id":unit['paper_id'],"evidence_unit_ids":[],"default_evidence_unit_ids":[]},{"chunk_id":"c-000001:0","path":".vault-meta/chunks/c-000001/chunk-000.json","body_hash":h,"page_body_hash":h,"paper_id":unit['paper_id'],"evidence_unit_ids":[],"default_evidence_unit_ids":[]}]};mapping['mapping_sha256']=evidence_mapping_sha256(mapping)
    cfg={"schema":"video-paper-wiki.retrieval-config.v1","corpus_version":"v","query_version":"q","top_chunks":10,"top_papers":10,"evidence_limit":8,"per_paper_evidence_limit":2,
         "generation_sha256":"a"*64,"mapping_sha256":mapping['mapping_sha256'],"eligibility":"active-not-deprecated","paper_tie_break":"score-desc-paper-id-asc","chunk_tie_break":"score-desc-paper-id-asc-chunk-id-asc"}
    ranked=rank_hits([{"chunk_id":"c-000002:0","score":0.0,"path":".vault-meta/chunks/c-000002/chunk-000.json","body_hash":h,"page_body_hash":h},{"chunk_id":"c-000001:0","score":-0.0,"path":".vault-meta/chunks/c-000001/chunk-000.json","body_hash":h,"page_body_hash":h}],mapping,cfg)
    assert ranked["top5"]==[unit['paper_id']]

def test_evaluator_binds_mapping_requires_four_tracks_and_rounds_once():
    import hashlib
    from video_paper_wiki.jcs import canonicalize
    inventory=build_evidence_inventory(_compile_material()['papers']);first=inventory['units'][0]
    second=copy.deepcopy(first);second['paper_id']='arxiv:2311.15128'
    second['evidence_unit_id']='evu-'+hashlib.sha256(canonicalize({'paper_id':second['paper_id'],'claim_id':second['claim_id'],'locator_fingerprint':second['locator_fingerprint']})).hexdigest()[:20]
    inventory['units'].append(second);inventory['units'].sort(key=lambda x:x['evidence_unit_id'])
    generation='a'*64;h='sha256:'+'b'*64
    mapping={'schema':'video-paper-wiki.evidence-mapping-authority.v1','inventory':inventory,'profile':'claude-obsidian.chunk-v1+bm25-v2','generation_sha256':generation,'mapping_sha256':'0'*64,'chunks':[
        {'chunk_id':'c-000001:0','path':'.vault-meta/chunks/c-000001/chunk-000.json','body_hash':h,'page_body_hash':h,'paper_id':first['paper_id'],'evidence_unit_ids':[first['evidence_unit_id']],'default_evidence_unit_ids':[first['evidence_unit_id']]},
        {'chunk_id':'c-000002:0','path':'.vault-meta/chunks/c-000002/chunk-000.json','body_hash':h,'page_body_hash':h,'paper_id':second['paper_id'],'evidence_unit_ids':[second['evidence_unit_id']],'default_evidence_unit_ids':[second['evidence_unit_id']]}]}
    config={'schema':'video-paper-wiki.retrieval-config.v1','corpus_version':'c1','query_version':'q1','top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,
        'generation_sha256':generation,'mapping_sha256':'0'*64,'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc','chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}
    mapping['mapping_sha256']=evidence_mapping_sha256(mapping);config['mapping_sha256']=mapping['mapping_sha256']
    hits=[{'chunk_id':row['chunk_id'],'score':2-i,'path':row['path'],'body_hash':h,'page_body_hash':h} for i,row in enumerate(mapping['chunks'])]
    ranked=rank_hits(hits,mapping,config); entries=[]
    for kind in ('exact_title_or_id','alias_or_semantic','named_title','topic_only'):
        comparison=kind in {'named_title','topic_only'}; required=[first,second] if comparison else [first];must=[x['paper_id'] for x in required]
        entries.append({'gold_id':kind,'corpus_version':'c1','query_version':'q1','variant_kind':kind,'query':kind,'must_paper_ids':sorted(must),'supporting_paper_ids':[],
            'graded_relevance':{p:2 for p in sorted(must)},'required_evidence_units':[{k:x[k] for k in ('evidence_unit_id','paper_id','claim_id','locator_fingerprint')} for x in required]})
    gold={'schema':'video-paper-wiki.retrieval-gold.v1','entries':entries,'version':'1','change_reason':'fixed vectors'}
    results={row['gold_id']:copy.deepcopy(ranked) for row in entries}
    report=evaluate_retrieval(gold=gold,inventory=inventory,config=config,mapping=mapping,results=results)
    assert report['passed'] and report['macro']['topic_only']['metrics']['ndcg_at_5_bp']==10000
    with pytest.raises(ContractError):evaluate_retrieval(gold={**gold,'entries':entries[:-1]},inventory=inventory,config=config,mapping=mapping,results={k:v for k,v in results.items() if k!='topic_only'})
    crossed=copy.deepcopy(mapping);crossed['chunks'][0]['evidence_unit_ids']=[];crossed['chunks'][0]['default_evidence_unit_ids']=[]
    with pytest.raises(ContractError):evaluate_retrieval(gold=gold,inventory=inventory,config=config,mapping=crossed,results=results)
    coherent=copy.deepcopy(mapping);coherent['chunks'][0]['paper_id']=second['paper_id'];coherent['chunks'][0]['evidence_unit_ids']=[second['evidence_unit_id']];coherent['chunks'][0]['default_evidence_unit_ids']=[second['evidence_unit_id']];coherent['mapping_sha256']=evidence_mapping_sha256(coherent)
    with pytest.raises(ContractError):rank_hits(hits,coherent,config)
    with pytest.raises(ContractError):rank_hits(hits,mapping,{**config,'mapping_sha256':'f'*64})
    for malformed in ({k:v for k,v in mapping.items() if k!='profile'},{**mapping,'extra':True}):
        with pytest.raises(ContractError):validate_evidence_mapping_authority(malformed)
