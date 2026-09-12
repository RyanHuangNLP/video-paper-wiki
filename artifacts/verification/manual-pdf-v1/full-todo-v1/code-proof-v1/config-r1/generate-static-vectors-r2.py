from __future__ import annotations
import copy, hashlib, json
from pathlib import Path

ROOT=Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
DIR=ROOT/'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1'
R1=DIR/'static-vectors-r1.json'
OUT=DIR/'static-vectors-r2.json'
MATRIX_PATH=ROOT/'docs/ai/packets/full-todo-v1/CODE-CONFIG-TOML-MATRIX-R2.json'
DYNAMIC_PATH=ROOT/'docs/ai/packets/full-todo-v1/CODE-CONFIG-DYNAMIC-VECTORS-R2.json'

def line_info(text):
    starts=[0]
    for i,ch in enumerate(text):
        if ch=='\n': starts.append(i+1)
    return starts

def snippet_sha256(source,line_start,line_end):
    b=source.replace('\r\n','\n').encode('utf-8')
    lines=b.splitlines(keepends=True)
    selected=b''.join(lines[line_start-1:line_end])
    if selected.endswith(b'\n'): selected=selected[:-1]
    return hashlib.sha256(selected).hexdigest()

def make_span(source,a,b):
    assert 0<=a<b<=len(source)
    raw=source[a:b].encode('utf-8')
    starts=line_info(source)
    import bisect
    def lc(off):
        line=bisect.bisect_right(starts,off)
        return line,off-starts[line-1]+1
    ls,cs=lc(a); le,ce=lc(b)
    assert not (a>0 and source[a-1]=='\r' and a<len(source) and source[a]=='\n')
    assert not (b>0 and source[b-1]=='\r' and b<len(source) and source[b]=='\n')
    return {'byte_start':len(source[:a].encode('utf-8')),
            'byte_end':len(source[:b].encode('utf-8')),
            'codepoint_start':a,'codepoint_end':b,
            'line_start':ls,'column_start':cs,'line_end':le,'column_end':ce,
            'raw_sha256':hashlib.sha256(raw).hexdigest(),
            'snippet_sha256':snippet_sha256(source,ls,le)}

def find_token(source,token,start=0):
    a=source.index(token,start); return a,a+len(token)

def matching_span(source,opener,closer,start=0):
    # Token-aware delimiter matching for the authored single-line values; quoted
    # strings are skipped so delimiters in data are never counted.
    pos=source.index(opener,start); depth=0; quote=None; escaped=False; i=pos
    while i<len(source):
        ch=source[i]
        if quote is not None:
            if escaped: escaped=False
            elif ch=='\\': escaped=True
            elif ch==quote: quote=None
        else:
            if ch in ('"',"'"): quote=ch
            elif ch==opener: depth+=1
            elif ch==closer:
                depth-=1
                if depth==0: return make_span(source,pos,i+1)
        i+=1
    raise AssertionError((opener,closer,start))

def after_token(source,token,opener,closer,start=0):
    a,b=find_token(source,token,start)
    return matching_span(source,opener,closer,b)

r1_bytes=R1.read_bytes(); r1_sha=hashlib.sha256(r1_bytes).hexdigest(); fixture=json.loads(r1_bytes)
assert r1_sha=='a835382c7924969ee1d1b12b26e38fae126cc3ee03770ecfc23937b1b5915b24'
r2=copy.deepcopy(fixture)
r2['$schema']='video-paper-wiki.code-config-kernel-fixture-r2.v1'
r2['revision']=2
r2['status']='INDEPENDENT_STATIC_AUTHORED_VECTORS_R2_SPAN_CORRECTION_READY_FOR_REVIEW'
r2['r1_immutable_source']={'path':'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1/static-vectors-r1.json','sha256':r1_sha,'size_bytes':len(r1_bytes),'preserved_fields':['source_utf8','source','format','purposes','parser_cross_check','path/kind/value/numeric_lexeme/children and declarations except corrected dependent span facts']}

# Correct only value spans. All values/paths/purposes remain inherited byte-for-byte.
for v in r2['success_vectors']:
    sid=v['id']; s=v['source_utf8']
    nodes={n['path']:n for n in v['expected_nodes']}
    if sid=='json-nested-lf':
        nodes['']['value_span']=matching_span(s,'{','}',0)
        nodes['/optimizer']['value_span']=matching_span(s,'{','}',s.index('"optimizer"'))
        nodes['/optimizer/betas']['value_span']=after_token(s,'"betas"','[',']')
        nodes['/schedule']['value_span']=matching_span(s,'{','}',s.index('"schedule"'))
    elif sid=='json-unicode-crlf-tabs':
        nodes['']['value_span']=matching_span(s,'{','}',0)
        nodes['/list']['value_span']=after_token(s,'"list"','[',']')
        nodes['/list/3']['value_span']=after_token(s,'null','[',']')
    elif sid=='json-pointer-escaping':
        nodes['']['value_span']=matching_span(s,'{','}',0)
        nodes['/a~1b']['value_span']=matching_span(s,'{','}',s.index('"a/b"'))
        nodes['/empty']['value_span']=after_token(s,'"empty"','[',']')
    elif sid=='toml-nested-lf':
        nodes['/optimizer/betas']['value_span']=after_token(s,'betas','[',']')
    elif sid=='toml-unicode-crlf-inline':
        nodes['/model/nested']['value_span']=after_token(s,'nested','{','}')
        nodes['/model/nested/betas']['value_span']=after_token(s,'betas','[',']')
        nodes['/model/nested/empty']['value_span']=after_token(s,'empty','[',']')
    elif sid in ('toml-dotted-promotion','toml-numeric-boundaries'):
        pass
    else: raise AssertionError(sid)

# Embed the exact parsed content of the independently authored matrix/dynamic inputs.
def embed(path):
    b=path.read_bytes(); content=json.loads(b)
    return {'source_path':str(path.relative_to(ROOT)),'source_sha256':hashlib.sha256(b).hexdigest(),'source_size_bytes':len(b),'content':content}
r2['supplementary_groups']={
 'toml_transition_matrix_r2':embed(MATRIX_PATH),
 'dynamic_offset_vectors_r2':embed(DYNAMIC_PATH),
}
r2['r2_span_contract_checks']={
 'corrected_findings':['json root/container matching delimiters','TOML array/inline-table delimiter selection after key token'],
 'required_replay':['50 nonnull value spans parse as the complete stdlib value at their exact path','container containment','array element source order','declaration key correspondence and coordinates','both Python 3.12 and 3.13'],
 'no_semantic_changes':True,
}
OUT.write_text(json.dumps(r2,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
b=OUT.read_bytes(); print(OUT); print('bytes',len(b),'sha256',hashlib.sha256(b).hexdigest())
