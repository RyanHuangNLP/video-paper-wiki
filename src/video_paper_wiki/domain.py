"""Video-paper domain compilation and evidence/result shaping."""
from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Mapping, Sequence
from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest
from video_paper_wiki.contracts import ContractError, validate_document

from video_paper_wiki.resources import load_seed_json
from video_paper_wiki.secure_io import read_regular_file,parse_strict_json
SEED='engine-mvp.json'
SEED_DATE='2026-01-01'

def _yaml(value:object)->str:
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))

def _markdown(value:object)->str:
    text=str(value).replace('\r',' ').replace('\n',' ')
    for old,new in (('\\','\\\\'),('[','\\['),(']','\\]'),('*','\\*'),('_','\\_')): text=text.replace(old,new)
    return text

def _frontmatter(*,title:str,page_type:str,tags:Sequence[str],extra:Sequence[tuple[str,object]]=(),status:str='provisional',created:str=SEED_DATE,updated:str=SEED_DATE)->str:
    lines=['---',f'title: {_yaml(title)}',f'type: {page_type}',f'status: {status}',f'created: {created}',f'updated: {updated}',f'tags: {_yaml(list(tags))}']
    lines.extend(f'{key}: {_yaml(value)}' for key,value in extra)
    return '\n'.join(lines+['---',''])

def validate_seed_catalog(path:Path|str|None=SEED)->dict:
    try:
        value=load_seed_json(SEED) if path in (None,SEED) else parse_strict_json(read_regular_file(Path(path),missing_code='SEED_INVALID',unsafe_code='SEED_INVALID',changed_code='SEED_INVALID',max_bytes=67108864,limit_code='SEED_INVALID'),invalid_code='SEED_INVALID')
    except Exception: raise ContractError('SEED_INVALID','seed catalog is unreadable')
    if type(value) is not dict or set(value)!={'papers'} or type(value['papers']) is not list: raise ContractError('SEED_INVALID','seed catalog shape differs')
    ids=[]
    for item in value['papers']:
        if type(item) is not dict or set(item)!={'title','arxiv_id','paper_id','abs_url'}: raise ContractError('SEED_INVALID','seed paper shape differs')
        if item['paper_id']!='arxiv-'+item['arxiv_id'] or item['abs_url']!='https://arxiv.org/abs/'+item['arxiv_id']: raise ContractError('SEED_INVALID','seed paper identity differs')
        ids.append(item['paper_id'])
    if len(ids)!=67 or len(set(ids))!=67: raise ContractError('SEED_INVALID','seed catalog must contain 67 unique papers')
    return value

def render_seed_catalog(batch_id:object)->dict:
    """Render metadata-only provisional pages below .work; never claim ingestion."""
    from video_paper_wiki.staging import stage_bytes, validate_batch_id
    batch=validate_batch_id(batch_id); catalog=validate_seed_catalog(); topic_doc=load_seed_json('engine-mvp-topics.json')
    topics=topic_doc.get('topics',[]) if isinstance(topic_doc,dict) else []
    memberships={paper:[] for paper in (p['paper_id'] for p in catalog['papers'])}
    for topic in topics:
        for paper in topic.get('paper_ids',[]):
            if paper in memberships: memberships[paper].append(topic['id'])
    from video_paper_wiki.transaction_staging import encode_transaction_inspect_bundle
    files=[]; outputs={}
    for paper in catalog['papers']:
        selected=sorted(memberships[paper['paper_id']])
        text=_frontmatter(title=paper['title'],page_type='paper',tags=['video-paper','provisional'],extra=(('paper_id',paper['paper_id']),('source','seed-metadata-only'),('taxonomy',[f'topic/{x}' for x in selected])))+f"\n# {_markdown(paper['title'])}\n\n> 尚未摄取正文；此页仅来自确定性 seed 元数据。\n\n- [arXiv]({paper['abs_url']})\n- [[../video-papers/catalog|视频论文种子目录]]\n"
        rel=('seed','wiki','papers',paper['paper_id']+'.md'); result=stage_bytes(batch_id=batch,relative=rel,data=text.encode()); files.append(result.path.as_posix())
        outputs['wiki/papers/'+paper['paper_id']+'.md']=text.encode()
    for topic in topics:
        links='\n'.join(f"- [[../papers/{p}|{p}]]" for p in topic.get('paper_ids',[]) if p in memberships)
        text=_frontmatter(title=topic['heading_zh'],page_type='concept',tags=['concept','video-paper','provisional'],extra=(('concept_id',topic['id']),('source','seed-metadata-only')))+f"\n# {_markdown(topic['heading_zh'])}\n\n{links}\n"
        result=stage_bytes(batch_id=batch,relative=('seed','wiki','concepts',topic['id']+'.md'),data=text.encode()); files.append(result.path.as_posix())
        outputs['wiki/concepts/'+topic['id']+'.md']=text.encode()
    paper_links='\n'.join(f"- [[../papers/{p['paper_id']}|{_markdown(p['title'])}]]" for p in catalog['papers'])
    concept_links='\n'.join(f"- [[../concepts/{topic['id']}|{_markdown(topic['heading_zh'])}]]" for topic in topics)
    index=_frontmatter(title='视频论文种子目录',page_type='meta',tags=['meta','video-paper','catalog','provisional'])+'\n# 视频论文种子目录\n\n> provisional / metadata-only\n\n## 论文\n\n'+paper_links+'\n\n## 概念\n\n'+concept_links+'\n'
    result=stage_bytes(batch_id=batch,relative=('seed','wiki','video-papers','catalog.md'),data=index.encode());files.append(result.path.as_posix())
    outputs['wiki/video-papers/catalog.md']=index.encode()
    import hashlib
    descriptors=[{'path':path,'mode':'create','sha256':hashlib.sha256(data).hexdigest()} for path,data in sorted(outputs.items())]
    bundle=encode_transaction_inspect_bundle({'operation_id':'seed-'+batch,'operation_type':'generic','writes':descriptors,'expected_hashes':{x['path']:None for x in descriptors},'read_preconditions':{}})
    for digest,data in sorted({hashlib.sha256(data).hexdigest():data for data in outputs.values()}.items()):
        stage_bytes(batch_id=batch,relative=('transaction-inspect','content',digest),data=data)
    staged_bundle=stage_bytes(batch_id=batch,relative=('transaction-inspect','bundle.json'),data=bundle)
    return {'batch_id':batch,'paper_count':len(catalog['papers']),'concept_count':len(topics),'status':'provisional','files':files,'bundle_path':staged_bundle.path.as_posix(),'bundle_sha256':hashlib.sha256(bundle).hexdigest()}

def compile_paper_page(record:object,claims:Sequence[Mapping]=())->str:
    doc=validate_document(record,'video-paper-wiki.paper-record.v1')
    title=doc.get('title') or doc['paper_id']; taxonomy=[f"{item['axis']}/{item['slug']}" for item in doc['taxonomy']]
    allowed={item['claim_id'] for item in doc['section_claim_refs']}; seen=set(); checked=[]
    if isinstance(claims,(str,bytes)) or not isinstance(claims,Sequence): raise ContractError('CLAIM_INVALID','claims must be a sequence')
    for claim in claims:
        if not isinstance(claim,Mapping) or type(claim.get('claim_id')) is not str or claim['claim_id'] not in allowed or claim['claim_id'] in seen or type(claim.get('text')) is not str or not claim['text']:
            raise ContractError('CLAIM_INVALID','claim does not bind a unique paper claim reference')
        seen.add(claim['claim_id']); checked.append(claim)
    lines=[_frontmatter(title=title,page_type='paper',tags=taxonomy or ['video-paper'],extra=(('paper_id',doc['paper_id']),('taxonomy',taxonomy)),status='generated',created=doc['created_at'][:10],updated=doc['updated_at'][:10]).rstrip(),'',f'# {_markdown(title)}','','## 核心主张','']
    lines += [f"- {_markdown(c['text'])} (`{_markdown(c['claim_id'])}`)" for c in checked] or ['- 暂无已验证主张。']
    lines += ['','## 证据','',f"- 记录：`{doc['paper_id']}`",'','## 代码与资源','','- 由 code-evidence manifest 连接。','']
    return '\n'.join(lines)

def compile_code_page(manifest:object)->str:
    doc=validate_code_evidence_manifest(manifest); origin=doc['origin']
    title=f"{origin['repository']} · {origin['path']}"
    return _frontmatter(title=title,page_type='code',tags=['code','video-paper'],extra=(('repository',origin['repository']),('commit',origin['commit']),('source_path',origin['path'])),status='generated')+'\n'+ '\n'.join([f"# {_markdown(title)}",'','## 捕获状态','',f"- state: `{doc['state']}`",f"- payload: `{doc['payload']['sha256']}`",f"- normalized: `{doc['normalized_sha256']}`",''])

def compile_concept_page(*,axis:str,slug:str,label_zh:str,label_en:str)->str:
    if not all(type(x) is str and x for x in (axis,slug,label_zh,label_en)): raise ContractError('CONCEPT_INVALID','concept fields are required')
    from video_paper_wiki.resources import read_projection_resource_bytes
    taxonomy=json.loads((read_projection_resource_bytes('taxonomy','v1.json') or b'null').decode('utf-8'))
    allowed={(item['slug'],term['slug']):(term['label_zh'],term.get('label_en',term['slug'])) for item in taxonomy['axes'] for term in item['terms']}
    if (axis,slug) not in allowed or allowed[(axis,slug)]!=(label_zh,label_en): raise ContractError('CONCEPT_INVALID','concept tuple is not in pinned taxonomy')
    return _frontmatter(title=label_zh,page_type='concept',tags=['concept',axis+'/'+slug],extra=(('axis',axis),('slug',slug)),status='generated')+f'\n# {_markdown(label_zh)}\n\n{_markdown(label_en)}\n'

def shape_query_results(results:object)->list[dict]:
    if type(results) is not list: raise ContractError('QUERY_RESULT_INVALID','upstream result must be a list')
    shaped=[]
    for rank,item in enumerate(results,1):
        path=item.get('path') if type(item) is dict else None; score=item.get('score') if type(item) is dict else None
        chunk=item.get('chunk_id') if type(item) is dict else None
        hashes=(item.get('body_hash'),item.get('page_body_hash')) if type(item) is dict else (None,None)
        if (type(item) is not dict or set(item)!={'chunk_id','score','path','body_hash','page_body_hash'} or type(path) is not str or not path or path.startswith('/') or '\\' in path or any(x in {'','.','..'} for x in path.split('/'))
                or type(score) not in (int,float) or not math.isfinite(score)
                or type(chunk) is not str or re.fullmatch(r'(?:(?:c|l)-[0-9]{6}|syn-[0-9a-f]{64}):(?:0|[1-9][0-9]*)',chunk) is None
                or any(type(value) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}',value) is None for value in hashes)):
            raise ContractError('QUERY_RESULT_INVALID','upstream result item differs')
        shaped.append({'rank':rank,'path':item['path'],'score':item['score'],'chunk_id':item['chunk_id'],'body_hash':item['body_hash'],'page_body_hash':item['page_body_hash']})
    return shaped
