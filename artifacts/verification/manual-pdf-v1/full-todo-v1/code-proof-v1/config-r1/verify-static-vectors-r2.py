from __future__ import annotations
import bisect, decimal, hashlib, json, sys, tomllib
from pathlib import Path

ROOT=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
DIR=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'
R1=DIR/'static-vectors-r1.json'; R2=DIR/'static-vectors-r2.json'
fixture=json.loads(R2.read_text(encoding='utf-8')); r1=json.loads(R1.read_text(encoding='utf-8'))
assert fixture['$schema']=='video-paper-wiki.code-config-kernel-fixture-r2.v1'
assert hashlib.sha256(R1.read_bytes()).hexdigest()=='a835382c7924969ee1d1b12b26e38fae126cc3ee03770ecfc23937b1b5915b24'
assert fixture['r1_immutable_source']['sha256']=='a835382c7924969ee1d1b12b26e38fae126cc3ee03770ecfc23937b1b5915b24'

def source_meta(source):
    b=source.encode(); n=source.replace('\r\n','\n').encode(); crlf=source.count('\r\n');lf=source.count('\n')-crlf
    return {'body_size_bytes':len(b),'body_sha256':hashlib.sha256(b).hexdigest(),'normalized_sha256':hashlib.sha256(n).hexdigest(),'newline_style':'mixed' if crlf and lf else 'crlf' if crlf else 'lf' if lf else 'none','ends_with_newline':n.endswith(b'\n'),'line_count':0 if not n else n.count(b'\n')+(0 if n.endswith(b'\n') else 1)}

def snippet(source,ls,le):
    b=source.replace('\r\n','\n').encode(); x=b''.join(b.splitlines(keepends=True)[ls-1:le]); x=x[:-1] if x.endswith(b'\n') else x; return hashlib.sha256(x).hexdigest()

def starts(source):
    x=[0]
    for i,c in enumerate(source):
        if c=='\n':x.append(i+1)
    return x

def span_check(source,sp):
    assert list(sp)==['byte_start','byte_end','codepoint_start','codepoint_end','line_start','column_start','line_end','column_end','raw_sha256','snippet_sha256']
    a,b=sp['codepoint_start'],sp['codepoint_end']; assert 0<=a<b<=len(source)
    raw=source[a:b].encode(); ba=len(source[:a].encode()); assert (sp['byte_start'],sp['byte_end'])==(ba,ba+len(raw))
    ss=starts(source)
    def lc(x):
        line=bisect.bisect_right(ss,x); return line,x-ss[line-1]+1
    assert (sp['line_start'],sp['column_start'])==lc(a); assert (sp['line_end'],sp['column_end'])==lc(b)
    assert hashlib.sha256(raw).hexdigest()==sp['raw_sha256']; assert sp['snippet_sha256']==snippet(source,sp['line_start'],sp['line_end'])
    assert not (a>0 and source[a-1]=='\r' and a<len(source) and source[a]=='\n')
    assert not (b>0 and source[b-1]=='\r' and b<len(source) and source[b]=='\n')
    assert source[a:b].encode()==raw

def exact(a,b):
    if type(a) is not type(b): return False
    if isinstance(a,decimal.Decimal): return a.as_tuple()==b.as_tuple()
    if type(a) is dict:return a.keys()==b.keys() and all(exact(a[k],b[k]) for k in a)
    if type(a) is list:return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a==b

def json_unique(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ValueError('duplicate')
        out[k]=v
    return out

def parse(fmt,s):
    if fmt=='json':return json.loads(s,parse_int=int,parse_float=decimal.Decimal,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),object_pairs_hook=json_unique)
    return tomllib.loads(s,parse_float=decimal.Decimal)

def pointer_get(value,path):
    cur=value
    if not path:return cur
    for seg in path[1:].split('/'):
        seg=seg.replace('~1','/').replace('~0','~')
        cur=cur[int(seg)] if type(cur) is list else cur[seg]
    return cur

def path_decode(path):
    if not path:return []
    return [x.replace('~1','/').replace('~0','~') for x in path[1:].split('/')]

def actual_kind(v):
    if type(v) is bool:return 'boolean'
    if v is None:return 'null'
    if type(v) is int:return 'integer'
    if isinstance(v,decimal.Decimal):return 'decimal'
    if type(v) is str:return 'string'
    if type(v) is list:return 'array'
    if type(v) is dict:return 'object'
    raise AssertionError(type(v))

def children_for(v,path):
    if type(v) is dict:
        return [path+'/'+k.replace('~','~0').replace('/','~1') for k in sorted(v,key=lambda x:x.encode('utf-8'))]
    if type(v) is list:return [path+'/'+str(i) for i in range(len(v))]
    return []

def key_from_toml_token(raw):
    obj=tomllib.loads(raw+' = 1\n')
    assert len(obj)==1
    return next(iter(obj))

def header_path(raw):
    obj=tomllib.loads(raw+'\nx=1\n')
    cur=obj; parts=[]
    while isinstance(cur,dict) and set(cur)=={'x'} and False: pass
    # Find the unique path to the inserted sentinel x.
    def find(cur,prefix):
        if isinstance(cur,dict) and 'x' in cur and cur['x']==1:return prefix
        if isinstance(cur,dict):
            for k,v in cur.items():
                hit=find(v,prefix+[k])
                if hit is not None:return hit
        return None
    hit=find(obj,[]); assert hit; return hit

def verify_decl(v,node,complete):
    source=v['source_utf8']; fmt=v['format']; path=node['path']; last=path_decode(path)[-1] if path_decode(path) else None
    for dec in node['declarations']:
        span_check(source,dec['span']); raw=source[dec['span']['codepoint_start']:dec['span']['codepoint_end']]
        if fmt=='json':
            assert dec['kind']=='json_key'; assert last is not None; assert json.loads(raw)==last
        elif dec['kind']=='toml_key':
            assert last is not None; assert key_from_toml_token(raw)==last
        elif dec['kind']=='toml_table':
            assert path_decode(path)==header_path(raw)
        else: raise AssertionError(dec['kind'])

def verify_value_spans(v):
    s=v['source_utf8']; body=s.encode(); complete=parse(v['format'],s); nodes=v['expected_nodes']; assert v['source']==source_meta(s)
    seen={n['path']:n for n in nodes}; count=0
    for n in nodes:
        assert n['path'] in seen
        verify_decl(v,n,complete)
        sp=n['value_span']
        if sp is not None:
            count+=1; span_check(s,sp); subset=body[sp['byte_start']:sp['byte_end']]; assert s[sp['codepoint_start']:sp['codepoint_end']].encode()==subset
            expected=pointer_get(complete,n['path'])
            if v['format']=='json': got=json.loads(subset.decode(),parse_int=int,parse_float=decimal.Decimal,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),object_pairs_hook=json_unique)
            else: got=tomllib.loads('value = '+subset.decode(),parse_float=decimal.Decimal)['value']
            assert exact(got,expected),(v['id'],n['path'],subset,got,expected)
            if n['kind'] in ('integer','decimal'): assert subset.decode()==n['numeric_lexeme']
        if n['kind']==actual_kind(pointer_get(complete,n['path'])): pass
        else: raise AssertionError((v['id'],n['path'],n['kind'],actual_kind(pointer_get(complete,n['path']))))
        child_expected=children_for(pointer_get(complete,n['path']),n['path']); assert n['children']==child_expected
        # typed leaf values are compared without allowing bool/int equality collapse.
        actual=pointer_get(complete,n['path']); k=actual_kind(actual)
        if k in ('object','array'): assert n['value'] is None
        elif k=='decimal':
            # canonical textual value is compared through Decimal, preserving kind.
            assert decimal.Decimal(n['value'])==actual
        elif k=='integer': assert type(actual) is int and n['value']==str(actual)
        else: assert n['value']==actual
    # Complete DFS preorder path order.
    ordered=[]
    def walk(x,path):
        ordered.append(path)
        if type(x) is dict:
            for k in sorted(x,key=lambda x:x.encode('utf-8')):walk(x[k],path+'/'+k.replace('~','~0').replace('/','~1'))
        elif type(x) is list:
            for i,y in enumerate(x):walk(y,path+'/'+str(i))
    walk(complete,''); assert ordered==[n['path'] for n in nodes]
    # Value span containment and array source order for every explicit container.
    for n in nodes:
        psp=n['value_span']
        if psp is None: continue
        direct=[seen[c] for c in n['children']]
        child_spans=[c['value_span'] for c in direct if c['value_span'] is not None]
        for csp in child_spans:
            assert psp['byte_start']<=csp['byte_start']<csp['byte_end']<=psp['byte_end'],(v['id'],n['path'],csp)
        if n['kind']=='array':
            assert child_spans==sorted(child_spans,key=lambda z:z['byte_start'])
            for a,b in zip(child_spans,child_spans[1:]): assert a['byte_end']<=b['byte_start']
    # JSON root span is the complete parsed value; TOML root is intentionally null.
    root=seen['']
    if v['format']=='json':
        assert root['value_span'] is not None; raw=body[root['value_span']['byte_start']:root['value_span']['byte_end']]; assert exact(json.loads(raw,parse_float=decimal.Decimal),complete)
    else: assert root['value_span'] is None
    return count

def compare_preserved():
    assert len(r1['success_vectors'])==len(fixture['success_vectors'])==7
    assert len(r1['refusal_vectors'])==len(fixture['refusal_vectors'])==31
    for a,b in zip(r1['success_vectors'],fixture['success_vectors']):
        for key in ('id','format','purposes','source_utf8','source','parser_cross_check'):
            assert a[key]==b[key],(a['id'],key)
        for na,nb in zip(a['expected_nodes'],b['expected_nodes']):
            for key in ('path','kind','value','numeric_lexeme','children','declarations'):
                assert na[key]==nb[key],(a['id'],na['path'],key)
        assert len(a['expected_nodes'])==len(b['expected_nodes'])
    assert r1['refusal_vectors']==fixture['refusal_vectors']

compare_preserved()
counts=[verify_value_spans(v) for v in fixture['success_vectors']]
assert sum(counts)==50,counts
# Supplementary groups are self-contained: replay does not reach into packet docs.
tm=fixture['supplementary_groups']['toml_transition_matrix_r2']; dv=fixture['supplementary_groups']['dynamic_offset_vectors_r2']
assert tm['source_path'].endswith('CODE-CONFIG-TOML-MATRIX-R2.json') and len(tm['source_sha256'])==64 and tm['source_size_bytes']>0
assert dv['source_path'].endswith('CODE-CONFIG-DYNAMIC-VECTORS-R2.json') and len(dv['source_sha256'])==64 and dv['source_size_bytes']>0
assert tm['content']['schema']=='full-todo.code-config-toml-transition-matrix.v1'
assert len(tm['content']['cases'])==26
assert dv['content']['schema']=='full-todo.code-config-dynamic-offset-vectors.v1'
assert len(dv['content']['vectors'])==9
critical={
 ('json-nested-lf',''):'{\n  "optimizer": {\n    "name": "AdamW",\n    "learning_rate": 1e-4,\n    "betas": [0.9, 0.999],\n    "weight_decay": 0.01\n  },\n  "schedule": {\n    "warmup_steps": 1000,\n    "gamma": 0.95\n  }\n}',
 ('json-unicode-crlf-tabs',''):'{\r\n\t"学习率": 1e-4,\r\n\t"备注": "β\\n",\r\n\t"empty": {},\r\n\t"list": [true, null, "", []]\r\n}',
 ('json-unicode-crlf-tabs','/list'):'[true, null, "", []]',
 ('json-pointer-escaping',''):'{"a/b": {"~key": 1}, "\\u0065": "é", "empty": []}',
 ('toml-nested-lf','/optimizer/betas'):'[0.9, 0.999]',
 ('toml-unicode-crlf-inline','/model/nested/betas'):'[0.9, 0.999,]',
 ('toml-unicode-crlf-inline','/model/nested/empty'):'[]',
}
critical_records=[]
for v in fixture['success_vectors']:
 for n in v['expected_nodes']:
    key=(v['id'],n['path'])
    if key in critical:
      sp=n['value_span']; raw=v['source_utf8'][sp['codepoint_start']:sp['codepoint_end']]; assert raw==critical[key],(key,raw)
      critical_records.append({'vector':v['id'],'path':n['path'],'raw':raw,'byte_start':sp['byte_start'],'byte_end':sp['byte_end'],'raw_sha256':sp['raw_sha256']})
assert len(critical_records)==len(critical)
report={'$schema':'video-paper-wiki.code-config-kernel-fixture-verification-r2.v1','fixture_path':str(R2.relative_to(ROOT)),'fixture_sha256':hashlib.sha256(R2.read_bytes()).hexdigest(),'fixture_size_bytes':R2.stat().st_size,'runtime':{'python':sys.version.split()[0],'production_imported':False,'network_or_provider':False},'r1_preservation':{'r1_fixture_sha256':hashlib.sha256(R1.read_bytes()).hexdigest(),'r1_fixture_unchanged':True,'success_vectors':7,'refusal_vectors':31,'semantic_and_source_fields_preserved':True},'success_replay':{'vectors':7,'value_spans_checked':sum(counts),'nodes_checked':sum(len(v['expected_nodes']) for v in fixture['success_vectors']),'all_value_spans_complete_exact_path':True,'container_containment':True,'array_element_source_order':True,'root_spans_complete':True,'declaration_key_correspondence':True,'coordinate_and_hash_checks':True},'supplementary_groups':{'toml_transition_matrix_r2':{'source_sha256':fixture['supplementary_groups']['toml_transition_matrix_r2']['source_sha256'],'case_count':26,'embedded_content_self_contained':True},'dynamic_offset_vectors_r2':{'source_sha256':fixture['supplementary_groups']['dynamic_offset_vectors_r2']['source_sha256'],'vector_count':9,'embedded_content_self_contained':True}},'critical_span_assertions':critical_records,'result':'PASS_R2_EXACT_VALUE_SPANS_AND_EMBEDDED_SUPPLEMENTS'}
out=DIR/('independent-verification-r2-py312.json' if sys.version_info[:2]==(3,12) else 'independent-verification-r2-py313.json'); out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(out);print('sha256',hashlib.sha256(out.read_bytes()).hexdigest(),'bytes',out.stat().st_size); print('counts',counts)
