from __future__ import annotations
import hashlib, json, tomllib
from decimal import Decimal, getcontext, localcontext
from pathlib import Path

FIX=Path('/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1/static-vectors-r1.json')
doc=json.loads(FIX.read_text(encoding='utf-8'))
assert doc['status'].startswith('INDEPENDENT_STATIC_AUTHORED')
assert len(doc['success_vectors'])==7 and len(doc['refusal_vectors'])==31

def metadata(source):
    payload=source.encode('utf-8'); norm=source.replace('\r\n','\n').encode('utf-8')
    crlf=source.count('\r\n'); lf=source.count('\n')-crlf
    style='mixed' if crlf and lf else 'crlf' if crlf else 'lf' if lf else 'none'
    return {'body_size_bytes':len(payload),'body_sha256':hashlib.sha256(payload).hexdigest(),'normalized_sha256':hashlib.sha256(norm).hexdigest(),'newline_style':style,'ends_with_newline':norm.endswith(b'\n'),'line_count':0 if not norm else norm.count(b'\n')+(0 if norm.endswith(b'\n') else 1)}

def snippet(source, line_start,line_end):
    b=source.replace('\r\n','\n').encode('utf-8'); lines=b.splitlines(keepends=True)
    x=b''.join(lines[line_start-1:line_end]); x=x[:-1] if x.endswith(b'\n') else x
    return hashlib.sha256(x).hexdigest()

def starts(source):
    out=[0]
    for i,c in enumerate(source):
        if c=='\n': out.append(i+1)
    return out

def pos(source, off):
    import bisect
    ss=starts(source); line=bisect.bisect_right(ss,off)
    return line,off-ss[line-1]+1

def verify_span(source,span):
    keys=['byte_start','byte_end','codepoint_start','codepoint_end','line_start','column_start','line_end','column_end','raw_sha256','snippet_sha256']
    assert list(span)==keys, list(span)
    a,b=span['codepoint_start'],span['codepoint_end']; assert 0<=a<b<=len(source)
    raw=source[a:b].encode('utf-8'); ba=len(source[:a].encode('utf-8')); bb=ba+len(raw)
    assert (span['byte_start'],span['byte_end'])==(ba,bb)
    assert (span['line_start'],span['column_start'])==pos(source,a)
    assert (span['line_end'],span['column_end'])==pos(source,b)
    assert hashlib.sha256(raw).hexdigest()==span['raw_sha256']
    assert span['snippet_sha256']==snippet(source,span['line_start'],span['line_end'])
    assert not (a>0 and source[a-1]=='\r' and a<len(source) and source[a]=='\n')
    assert not (b>0 and source[b-1]=='\r' and b<len(source) and source[b]=='\n')

def canonical(d):
    assert d.is_finite(); t=d.as_tuple(); digits=''.join(map(str,t.digits)) or '0'; exp=t.exponent
    if exp>=0: out=digits+'0'*exp
    else:
        cut=len(digits)+exp
        out='0.'+'0'*(-cut)+digits if cut<=0 else digits[:cut]+'.'+digits[cut:]
        out=out.rstrip('0').rstrip('.') if '.' in out else out
    out=out.lstrip('0') or '0'
    if out.startswith('.'): out='0'+out
    return ('-' if t.sign and out!='0' else '')+out

def kind_value(v):
    if type(v) is bool:return 'boolean',v
    if v is None:return 'null',None
    if type(v) is int:return 'integer',str(v)
    if isinstance(v,Decimal): return 'decimal',canonical(v)
    if type(v) is str:return 'string',v
    if type(v) is list:return 'array',None
    if type(v) is dict:return 'object',None
    raise AssertionError(type(v))

def path_escape(k):return k.replace('~','~0').replace('/','~1')
def child_path(path,k):return path+'/'+path_escape(k)

def actual_paths(value,path=''):
    k,kv=kind_value(value); out=[(path,k,kv)]
    if k=='object':
        for key in sorted(value, key=lambda x:x.encode('utf-8')): out+=actual_paths(value[key],child_path(path,key))
    elif k=='array':
        for i,x in enumerate(value): out+=actual_paths(x,path+'/'+str(i))
    return out

def detect_duplicate_json(pairs):
    seen=set(); out={}
    for k,v in pairs:
        if k in seen: raise ValueError('duplicate')
        seen.add(k); out[k]=v
    return out

def parse(fmt,source):
    if fmt=='json':
        return json.loads(source, parse_int=int, parse_float=Decimal, parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)), object_pairs_hook=detect_duplicate_json)
    return tomllib.loads(source,parse_float=Decimal)

def expected_paths(nodes):
    return [(n['path'],n['kind'],n['value']) for n in nodes]

def _lookup(value,path):
    if path=='': return value
    cur=value
    for seg in path.split('/')[1:]:
        seg=seg.replace('~1','/').replace('~0','~')
        cur=cur[int(seg)] if isinstance(cur,list) else cur[seg]
    return cur

def verify_success(v):
    source=v['source_utf8']; fmt=v['format']; assert v['source']==metadata(source)
    actual=parse(fmt,source)
    nodes=v['expected_nodes']; assert nodes[0]['path']==''
    # Every expected span and declaration is bounded, ordered and unique.
    all_spans=[]
    for n in nodes:
        for field in ('value_span',):
            sp=n[field]
            if sp is not None: verify_span(source,sp); all_spans.append((sp['byte_start'],sp['byte_end']))
        last=None; seen=set()
        for dec in n['declarations']:
            assert list(dec)==['kind','span']; verify_span(source,dec['span'])
            key=(dec['kind'],tuple(dec['span'].items()))
            assert key not in seen; seen.add(key)
            order=(dec['span']['byte_start'],dec['span']['byte_end'],dec['kind'])
            assert last is None or order>=last; last=order
            all_spans.append((dec['span']['byte_start'],dec['span']['byte_end']))
        if n['kind'] in ('integer','decimal'):
            assert type(n['numeric_lexeme']) is str
            raw=source[n['value_span']['codepoint_start']:n['value_span']['codepoint_end']]
            assert raw==n['numeric_lexeme'],(v['id'],n['path'],raw,n['numeric_lexeme'])
        else: assert n['numeric_lexeme'] is None
    # Path ordering is complete DFS preorder by expected map-key byte order.
    assert [n['path'] for n in nodes] == [x[0] for x in actual_paths(actual)]
    for n,(path,k,val) in zip(nodes,actual_paths(actual)):
        assert n['path']==path and n['kind']==k
        if k in ('object','array'): assert n['value'] is None
        elif k in ('integer','decimal'): assert n['value']==val
        else: assert n['value']==val
        if k=='object':
            expected_children=[child_path(path,key) for key in sorted(_lookup(actual,path), key=lambda x:x.encode('utf-8'))]
        elif k=='array':
            expected_children=[path+'/'+str(i) for i in range(len(_lookup(actual,path)))]
        else:
            expected_children=[]
        assert n['children']==expected_children
    # TOML maps/ordinary tables have null spans; JSON every node has a span.
    for n in nodes:
        if fmt=='json': assert n['value_span'] is not None
        elif n['path']=='': assert n['value_span'] is None
        elif n['kind']=='object': assert n['value_span'] is None or isinstance(n['value_span'],dict)
        else: assert n['value_span'] is not None
    # Decimal constructor remains context independent, and global context is unchanged.
    before=(getcontext().prec,getcontext().Emin,getcontext().Emax)
    with localcontext() as c:
        c.prec=1; c.Emin=-1; c.Emax=1
        hostile=parse(fmt,source)
    after=(getcontext().prec,getcontext().Emin,getcontext().Emax); assert before==after
    assert [(p,k,val) for p,k,val in actual_paths(hostile)] == [(p,k,val) for p,k,val in actual_paths(actual)]
    return {'id':v['id'],'format':fmt,'nodes':len(nodes),'raw_sha256':v['source']['body_sha256']}

success=[verify_success(v) for v in doc['success_vectors']]
# Refusal sources retain exact byte metadata and authored anchors; stdlib is run to classify accepted/rejected independently.
refres=[]
for v in doc['refusal_vectors']:
    source=v['source_utf8']; assert v['source']==metadata(source)
    exp=v['expected'];
    if 'anchor_span' in exp:
        verify_span(source,exp['anchor_span']); a=exp['anchor_span']['codepoint_start']; b=exp['anchor_span']['codepoint_end']; assert source[a:b]==exp['anchor_lexeme']
    parser='accepted'
    try: parse(v['format'],source)
    except Exception as e: parser=type(e).__name__
    refres.append({'id':v['id'],'format':v['format'],'expected_code':exp['code'],'stdlib':parser})

# Explicit no-rounding checks for hostile Decimal contexts across all decimal lexemes.
lexemes=[]
for v in doc['success_vectors']:
    lexemes += [n['numeric_lexeme'] for n in v['expected_nodes'] if n['numeric_lexeme'] is not None]
neutral=[Decimal(x.replace('_','')) for x in lexemes]
with localcontext() as c:
    c.prec=1;c.Emin=-1;c.Emax=1
    hostile=[Decimal(x.replace('_','')) for x in lexemes]
assert [x.as_tuple() for x in neutral]==[x.as_tuple() for x in hostile]

report={
 '$schema':'video-paper-wiki.code-config-kernel-fixture-verification-r1.v1','fixture_path':str(FIX.relative_to('/Users/huangzhanpeng/python_code/video-paper-wiki')),
 'fixture_sha256':hashlib.sha256(FIX.read_bytes()).hexdigest(),'fixture_size_bytes':FIX.stat().st_size,
 'verification_method':'Independent stdlib json.loads/tomllib.loads parse_float=Decimal cross-check; independently recomputed UTF-8 byte/codepoint coordinates, raw/snippet SHA-256, metadata, DFS paths and Decimal-context invariance.',
 'runtime':{'python':__import__('sys').version.split()[0],'tomllib':'stdlib','egress':'none'},
 'success':{'vectors':success,'count':len(success),'total_nodes':sum(x['nodes'] for x in success)},
 'refusals':{'vectors':refres,'count':len(refres),'stdlib_accepts_expected_for_profile':sum(x['stdlib']=='accepted' for x in refres)},
 'checks':{'source_metadata':True,'all_spans_and_hashes':True,'complete_parser_tree_shape':True,'numeric_kind_and_canonical_value':True,'json_pointer_and_dfs_order':True,'toml_null_ordinary_table_spans':True,'decimal_hostile_context_no_rounding':True,'global_decimal_context_unchanged':True,'refusal_anchors':True},
 'result':'PASS_INDEPENDENT_STATIC_FIXTURE_REPLAY',
}
out=FIX.parent/'independent-verification-r1.json'; out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(out);print('sha256',hashlib.sha256(out.read_bytes()).hexdigest(),'bytes',out.stat().st_size)
print(json.dumps({'success':success,'refusal_count':len(refres),'stdlib_accepts_expected':sum(x['stdlib']=='accepted' for x in refres)},indent=2))
