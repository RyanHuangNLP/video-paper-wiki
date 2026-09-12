from __future__ import annotations
import hashlib, json, re, tomllib
from decimal import Decimal, getcontext, localcontext, InvalidOperation
from pathlib import Path

OUT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1')
OUT.mkdir(parents=True, exist_ok=True)

INPUTS = {
    'config_kernel_r1': {'path':'docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-R1.md','sha256':'997ef4dce91e493f161b327ff5686aa349bd747e25ee13727248a68ba4d375d4'},
    'code_proof_closure_r3': {'path':'docs/ai/packets/full-todo-v1/CODE-PROOF-CLOSURE-R3.md','sha256':'3240bfcd29e0f159af389161037581e05c171893305e18182984395f1de0b6a5'},
    'independent_span_advice_r3': {'path':'artifacts/verification/manual-pdf-v1/full-todo-v1/E/code-config-span-advice-r3.json','sha256':'33eda350997482d91cce8ea8bf1e8a329591dd0cdb1284eff78437afea427b20'},
    'clarifications_r2': {'path':'docs/ai/packets/full-todo-v1/CODE-CONFIG-CLARIFICATIONS-R2.md','sha256':'d9051b3de39dd501dd6f99dd0b64b73c0496fedd498989fec129f1bf157ec37d'},
    'toml_transition_matrix_r2': {'path':'docs/ai/packets/full-todo-v1/CODE-CONFIG-TOML-MATRIX-R2.json','sha256':'18fc7340d6ceba4732c24b2c803fe0902732d6f3ed5dc4b761f90153c1c226bf'},
}

LIMITS = {
    'max_source_bytes':262144,'max_depth':32,'max_nodes':1024,'max_array_items':256,
    'max_object_keys':1024,'max_key_bytes':256,'max_string_codepoints':16384,
    'max_scalars':512,'max_numeric_lexeme_bytes':128,'max_numeric_coefficient_digits':64,
    'max_numeric_abs_exponent':128,'max_numeric_canonical_bytes':256,'max_declarations':4096,
}

# Small constructors used to author expected semantic trees independently from token scans.
def S(kind, value, lexeme=None): return {'kind':kind, 'value':value, 'lexeme':lexeme}
def I(value, lexeme=None): return S('integer', str(value), lexeme or str(value))
def D(value, lexeme): return S('decimal', str(value), lexeme)
def ST(value): return S('string', value)
def B(value): return S('boolean', bool(value))
def N(): return S('null', None)
def O(**items): return {'kind':'object','value':items}
def A(*items): return {'kind':'array','value':list(items)}

def find_n(source: str, needle: str, n=0, start=0):
    pos = start
    for _ in range(n+1):
        pos = source.index(needle, pos)
        if _ < n: pos += len(needle)
    return pos, pos + len(needle)

def line_info(text: str):
    # Physical lines; CRLF and LF are accepted; sources in this fixture contain no bare CR.
    starts=[0]
    i=0
    while i < len(text):
        if text[i]=='\n': starts.append(i+1)
        i += 1
    return starts

def snippet_sha256(payload: bytes, line_start: int, line_end: int):
    text=payload.decode('utf-8')
    norm=text.replace('\r\n','\n').encode('utf-8')
    lines=norm.splitlines(keepends=True)
    # code_snippet_sha256 excludes a terminal LF from the selected physical lines.
    selected=b''.join(lines[line_start-1:line_end])
    if selected.endswith(b'\n'): selected=selected[:-1]
    return hashlib.sha256(selected).hexdigest()

def make_span(source: str, a: int, b: int):
    assert 0 <= a < b <= len(source)
    raw=source[a:b].encode('utf-8')
    # UTF-8 byte offsets are computed from exact source prefix.
    ba=len(source[:a].encode('utf-8')); be=ba+len(raw)
    starts=line_info(source)
    def lc(offset):
        # line/column are 1-based and columns count codepoints, including CR in CRLF.
        import bisect
        line=bisect.bisect_right(starts, offset)
        return line, offset-starts[line-1]+1
    ls,cs=lc(a); le,ce=lc(b)
    # Valid authored spans never split a CRLF pair.
    assert not (a > 0 and source[a-1]=='\r' and a < len(source) and source[a]=='\n')
    assert not (b > 0 and source[b-1]=='\r' and b < len(source) and source[b]=='\n')
    physical_start=ls
    physical_end=le
    return {
        'byte_start':ba,'byte_end':be,
        'codepoint_start':a,'codepoint_end':b,
        'line_start':ls,'column_start':cs,'line_end':le,'column_end':ce,
        'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'snippet_sha256':snippet_sha256(source.encode('utf-8'), physical_start, physical_end),
    }

def span_token(source, token, occurrence=0, start=0):
    a,b=find_n(source, token, occurrence, start)
    return make_span(source,a,b)

def span_between(source, left, right, occurrence=0, start=0):
    a,_=find_n(source,left,occurrence,start)
    rstart=a+len(left)
    _,b=find_n(source,right,0,rstart)
    return make_span(source,a,b)

def source_metadata(source):
    payload=source.encode('utf-8'); norm=source.replace('\r\n','\n').encode('utf-8')
    crlf=source.count('\r\n'); lf=source.count('\n')-crlf
    style='mixed' if crlf and lf else 'crlf' if crlf else 'lf' if lf else 'none'
    return {
        'body_size_bytes':len(payload),
        'body_sha256':hashlib.sha256(payload).hexdigest(),
        'normalized_sha256':hashlib.sha256(norm).hexdigest(),
        'newline_style':style,
        'ends_with_newline':norm.endswith(b'\n'),
        'line_count':0 if not norm else norm.count(b'\n') + (0 if norm.endswith(b'\n') else 1),
    }

def parse_json(source):
    pairs=[]
    def hook(items):
        pairs.extend(items)
        return dict(items)
    value=json.loads(source, parse_int=int, parse_float=Decimal, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)), object_pairs_hook=hook)
    return value

def parse_toml(source): return tomllib.loads(source, parse_float=Decimal)

def py_semantic(value):
    if isinstance(value, bool): return B(value)
    if value is None: return N()
    if isinstance(value, int): return I(value)
    if isinstance(value, Decimal):
        # Parser decimal kind is preserved by authored wrapper separately; this helper is for verification values.
        return D(canonical_decimal(value), '')
    if isinstance(value, float): raise AssertionError('float escaped parse')
    if isinstance(value, str): return ST(value)
    if isinstance(value, list): return A(*(py_semantic(v) for v in value))
    if isinstance(value, dict): return O(**{k:py_semantic(v) for k,v in value.items()})
    raise TypeError(type(value))

def canonical_decimal(value: Decimal):
    if not value.is_finite(): raise AssertionError(value)
    t=value.as_tuple(); digits=''.join(map(str,t.digits)) or '0'; sign='-' if t.sign else ''
    exp=t.exponent
    if exp >= 0: out=digits + ('0'*exp)
    else:
        cut=len(digits)+exp
        out=('0.' + ('0'*(-cut)) + digits) if cut <= 0 else digits[:cut] + '.' + digits[cut:]
        if '.' in out: out=out.rstrip('0').rstrip('.')
    out=out.lstrip('0') or '0'
    if out.startswith('.'): out='0'+out
    return ('-' if sign and out!='0' else '') + out

def path_escape(s): return str(s).replace('~','~0').replace('/','~1')
def path_join(base, key): return base+'/'+path_escape(key)

def node_records(tree, source, value_spans, declarations):
    records=[]
    def walk(node, path):
        kind=node['kind']; val=node['value']
        if kind=='object':
            keys=sorted(val, key=lambda x:x.encode('utf-8'))
            children=[path_join(path,k) for k in keys]
            value=None
            for k in keys: walk(val[k], path_join(path,k))
        elif kind=='array':
            children=[path+'/'+str(i) for i in range(len(val))]
            value=None
            for i,v in enumerate(val): walk(v,path+'/'+str(i))
        else:
            children=[]; value=val
        rec={'path':path,'kind':kind,'value':value,
             'numeric_lexeme':node.get('lexeme') if kind in ('integer','decimal') else None,
             'children':children,
             'value_span':value_spans.get(path),
             'declarations':sorted(declarations.get(path,[]), key=lambda d:(d['span']['byte_start'],d['span']['byte_end'],d['kind']))}
        records.append(rec)
    walk(tree,'')
    # walk currently postorders children before parent; required DFS preorder.
    def rebuild(node,path):
        kind=node['kind']; val=node['value']
        rec={'path':path,'kind':kind,'value':None if kind in ('object','array') else val,
             'numeric_lexeme':node.get('lexeme') if kind in ('integer','decimal') else None,
             'children':([path_join(path,k) for k in sorted(val,key=lambda x:x.encode('utf-8'))] if kind=='object' else [path+'/'+str(i) for i in range(len(val))] if kind=='array' else []),
             'value_span':value_spans.get(path),
             'declarations':sorted(declarations.get(path,[]), key=lambda d:(d['span']['byte_start'],d['span']['byte_end'],d['kind']))}
        out=[rec]
        if kind=='object':
            for k in sorted(val,key=lambda x:x.encode('utf-8')): out.extend(rebuild(val[k],path_join(path,k)))
        elif kind=='array':
            for i,v in enumerate(val): out.extend(rebuild(v,path+'/'+str(i)))
        return out
    return rebuild(tree,'')

def dec(source, kind, token, path, *, occurrence=0, table=False, key_path=None, after=0):
    d={'kind':kind,'span':span_token(source,token,occurrence,after)}
    return path,d

def add_decl(decls, source, path, kind, token, occurrence=0, after=0):
    decls.setdefault(path,[]).append({'kind':kind,'span':span_token(source,token,occurrence,after)})

def scalar_spans_from_tokens(source, specs):
    out={}
    for path, token, occ, after in specs:
        out[path]=span_token(source,token,occ,after)
    return out

def object_spans(source, specs):
    return scalar_spans_from_tokens(source,specs)

def vector(id, fmt, source, tree, spans, decls, purposes, parser_name, parser_values=None, parser_notes=None):
    parsed=parse_json(source) if fmt=='json' else parse_toml(source)
    # Confirm independently authored tree has same complete key/array/scalar shape.
    expected=tree
    def plain(n):
        if n['kind']=='object': return {k:plain(v) for k,v in n['value'].items()}
        if n['kind']=='array': return [plain(v) for v in n['value']]
        if n['kind'] in ('integer','decimal'):
            return int(n['value']) if n['kind']=='integer' else Decimal(n['value'])
        return n['value']
    assert plain(expected)==parsed, (id, plain(expected), parsed)
    return {
        'id':id,'format':fmt,'purposes':purposes,
        'source_utf8':source,'source':source_metadata(source),
        'parser_cross_check':{'stdlib':parser_name,'parse_float':'Decimal','complete_tree_matches_authored':True, **(parser_values or {}), **(parser_notes or {})},
        'expected_nodes':node_records(tree,source,spans,decls),
    }

vectors=[]
# 1. JSON advice vector, full nested tree with numbers and beta array.
s='''{\n  "optimizer": {\n    "name": "AdamW",\n    "learning_rate": 1e-4,\n    "betas": [0.9, 0.999],\n    "weight_decay": 0.01\n  },\n  "schedule": {\n    "warmup_steps": 1000,\n    "gamma": 0.95\n  }\n}\n'''
t=O(optimizer=O(name=ST('AdamW'),learning_rate=D('0.0001','1e-4'),betas=A(D('0.9','0.9'),D('0.999','0.999')),weight_decay=D('0.01','0.01')),schedule=O(warmup_steps=I('1000'),gamma=D('0.95','0.95')))
sp={
 '':span_between(s,'{','}',0), '/optimizer':span_between(s,'{','}',1), '/optimizer/betas':span_between(s,'[',']',0), '/schedule':span_between(s,'{','}',2),
 '/optimizer/name':span_token(s,'"AdamW"'), '/optimizer/learning_rate':span_token(s,'1e-4'), '/optimizer/betas/0':span_token(s,'0.9'), '/optimizer/betas/1':span_token(s,'0.999'), '/optimizer/weight_decay':span_token(s,'0.01'), '/schedule/warmup_steps':span_token(s,'1000'), '/schedule/gamma':span_token(s,'0.95')}
d={}
for p,tok,occ in [('/optimizer','"optimizer"',0),('/schedule','"schedule"',0),('/optimizer/name','"name"',0),('/optimizer/learning_rate','"learning_rate"',0),('/optimizer/betas','"betas"',0),('/optimizer/weight_decay','"weight_decay"',0),('/schedule/warmup_steps','"warmup_steps"',0),('/schedule/gamma','"gamma"',0)]: add_decl(d,s,p,'json_key',tok,occ)
vectors.append(vector('json-nested-lf','json',s,t,sp,d,['nested maps','1e-4','betas [0.9,0.999]','integer and decimal kinds'],'json.loads',{'learning_rate_parser_value':'0.0001','warmup_steps_parser_value':1000}))

# 2. JSON CRLF, tabs, literal/escaped Unicode, empty containers and mixed scalars.
s='''{\r\n\t"学习率": 1e-4,\r\n\t"备注": "β\\n",\r\n\t"empty": {},\r\n\t"list": [true, null, "", []]\r\n}\r\n'''
t=O(**{'学习率':D('0.0001','1e-4'),'备注':ST('β\n'),'empty':O(),'list':A(B(True),N(),ST(''),A())})
sp={'':span_between(s,'{','}',0),'/学习率':span_token(s,'1e-4'),'/备注':span_token(s,'"β\\n"'),'/empty':span_between(s,'{','}',1),'/list':span_between(s,'[',']',0),'/list/0':span_token(s,'true'),'/list/1':span_token(s,'null'),'/list/2':span_token(s,'""'),'/list/3':span_between(s,'[',']',1)}
d={}
for p,tok in [('/学习率','"学习率"'),('/备注','"备注"'),('/empty','"empty"'),('/list','"list"')]: add_decl(d,s,p,'json_key',tok)
vectors.append(vector('json-unicode-crlf-tabs','json',s,t,sp,d,['CRLF','TAB columns','Unicode byte/codepoint divergence','escaped newline','empty object/array','null/boolean'],'json.loads',{'learning_rate_parser_value':'0.0001','unicode_key':'学习率'}))

# 3. JSON pointer escaping and escaped key spellings.
s='''{"a/b": {"~key": 1}, "\\u0065": "é", "empty": []}'''
t=O(**{'a/b':O(**{'~key':I('1')}),'e':ST('é'),'empty':A()})
sp={'':span_between(s,'{','}',0),'/a~1b':span_between(s,'{','}',1),'/a~1b/~0key':span_token(s,'1'),'/e':span_token(s,'"é"'),'/empty':span_between(s,'[',']',0)}
d={}
for p,tok in [('/a~1b','"a/b"'),('/a~1b/~0key','"~key"'),('/e','"\\u0065"'),('/empty','"empty"')]: add_decl(d,s,p,'json_key',tok)
vectors.append(vector('json-pointer-escaping','json',s,t,sp,d,['JSON Pointer ~0/~1 escaping','escaped Unicode key','literal Unicode scalar','empty array'],'json.loads',{'decoded_key':'e'}))

# 4. TOML advice vector, ordinary tables and trailing array comma.
s='''[optimizer]\nname = "AdamW"\nlearning_rate = 1e-4\nbetas = [0.9, 0.999]\nweight_decay = 0.01\n\n[schedule]\nwarmup_steps = 1000\ngamma = 0.95\n'''
t=O(optimizer=O(name=ST('AdamW'),learning_rate=D('0.0001','1e-4'),betas=A(D('0.9','0.9'),D('0.999','0.999')),weight_decay=D('0.01','0.01')),schedule=O(warmup_steps=I('1000'),gamma=D('0.95','0.95')))
sp={'/optimizer/name':span_token(s,'"AdamW"'),'/optimizer/learning_rate':span_token(s,'1e-4'),'/optimizer/betas':span_between(s,'[',']',0),'/optimizer/betas/0':span_token(s,'0.9'),'/optimizer/betas/1':span_token(s,'0.999'),'/optimizer/weight_decay':span_token(s,'0.01'),'/schedule/warmup_steps':span_token(s,'1000'),'/schedule/gamma':span_token(s,'0.95')}
d={}
add_decl(d,s,'/optimizer','toml_key','optimizer'); add_decl(d,s,'/optimizer','toml_table','[optimizer]')
for p,tok in [('/optimizer/name','name'),('/optimizer/learning_rate','learning_rate'),('/optimizer/betas','betas'),('/optimizer/weight_decay','weight_decay')]: add_decl(d,s,p,'toml_key',tok)
add_decl(d,s,'/schedule','toml_key','schedule'); add_decl(d,s,'/schedule','toml_table','[schedule]')
for p,tok in [('/schedule/warmup_steps','warmup_steps'),('/schedule/gamma','gamma')]: add_decl(d,s,p,'toml_key',tok)
vectors.append(vector('toml-nested-lf','toml',s,t,sp,d,['ordinary tables','1e-4','betas with trailing comma','decimal/integer kinds'],'tomllib.loads',{'learning_rate_parser_value':'0.0001','warmup_steps_parser_value':1000}))

# 5. TOML CRLF, Unicode/quoted keys, inline table and mixed nested array.
s='''# unicode and inline data\r\n[model]\r\n\t"学习率" = 1e-4 # rate\r\n\t"foo.bar" = "β"\r\nnested = {enabled = true, betas = [0.9, 0.999,], empty = []}\r\n'''
t=O(model=O(**{'学习率':D('0.0001','1e-4'),'foo.bar':ST('β'),'nested':O(enabled=B(True),betas=A(D('0.9','0.9'),D('0.999','0.999')),empty=A())}))
sp={'/model/学习率':span_token(s,'1e-4'),'/model/foo.bar':span_token(s,'"β"'),'/model/nested':span_between(s,'{','}',0),'/model/nested/enabled':span_token(s,'true'),'/model/nested/betas':span_between(s,'[',']',0),'/model/nested/betas/0':span_token(s,'0.9'),'/model/nested/betas/1':span_token(s,'0.999'),'/model/nested/empty':span_between(s,'[',']',1)}
d={}
add_decl(d,s,'/model','toml_key','model'); add_decl(d,s,'/model','toml_table','[model]')
add_decl(d,s,'/model/学习率','toml_key','"学习率"'); add_decl(d,s,'/model/foo.bar','toml_key','"foo.bar"'); add_decl(d,s,'/model/nested','toml_key','nested')
for p,tok in [('/model/nested/enabled','enabled'),('/model/nested/betas','betas'),('/model/nested/empty','empty')]: add_decl(d,s,p,'toml_key',tok)
vectors.append(vector('toml-unicode-crlf-inline','toml',s,t,sp,d,['CRLF','Unicode quoted key','literal dot inside quoted key','inline table','mixed array','comments'],'tomllib.loads',{'unicode_key':'学习率','inline_table_path':'/model/nested'}))

# 6. TOML dotted keys and implicit-parent promotion accepted by tomllib.
s='''x.y = 1\n[x.z]\nvalue = 2\n[a.b]\nvalue = 3\n[a]\nflag = true\n'''
t=O(x=O(y=I('1'),z=O(value=I('2'))),a=O(b=O(value=I('3')),flag=B(True)))
sp={'/x/y':span_token(s,'1'),'/x/z/value':span_token(s,'2'),'/a/b/value':span_token(s,'3'),'/a/flag':span_token(s,'true')}
d={}
add_decl(d,s,'/x','toml_key','x'); add_decl(d,s,'/x/y','toml_key','y')
add_decl(d,s,'/x','toml_key','x',1); add_decl(d,s,'/x/z','toml_key','z'); add_decl(d,s,'/x/z','toml_table','[x.z]')
add_decl(d,s,'/a','toml_key','a'); add_decl(d,s,'/a/b','toml_key','b'); add_decl(d,s,'/a/b','toml_table','[a.b]')
add_decl(d,s,'/a','toml_key','a',1); add_decl(d,s,'/a','toml_table','[a]'); add_decl(d,s,'/a/flag','toml_key','flag')
vectors.append(vector('toml-dotted-promotion','toml',s,t,sp,d,['dotted key','repeated prefix declarations','implicit parent promotion','ordinary headers'],'tomllib.loads',{'promotion':'[a.b] then [a] accepted'}))

# 7. TOML numeric forms including plus/underscore, 1e0 decimal kind, exponent and coefficient boundaries.
s='''plus = +1_000\nrate = 1_0.5_0e+1\nunit = 1e0\ntiny = 1e-128\ncoefficient = 1111111111111111111111111111111111111111111111111111111111111111\n'''
t=O(plus=I('1000','+1_000'),rate=D('105','1_0.5_0e+1'),unit=D('1','1e0'),tiny=D('0.'+'0'*127+'1','1e-128'),coefficient=I('1'*64,'1'*64))
sp={'/plus':span_token(s,'+1_000'),'/rate':span_token(s,'1_0.5_0e+1'),'/unit':span_token(s,'1e0'),'/tiny':span_token(s,'1e-128'),'/coefficient':span_token(s,'1'*64)}
d={}
for p,tok in [('/plus','plus'),('/rate','rate'),('/unit','unit'),('/tiny','tiny'),('/coefficient','coefficient')]: add_decl(d,s,p,'toml_key',tok)
vectors.append(vector('toml-numeric-boundaries','toml',s,t,sp,d,['TOML plus sign','digit separators','decimal kind for 1e0','explicit exponent -128','64 coefficient digits'],'tomllib.loads',{'unit_parser_type':'Decimal','unit_parser_value':'1','coefficient_digits':64}))

# Refusal vectors are separately authored and checked by the independent verifier below.
refusals=[]
def refusal(id, fmt, source, code, reason, purpose, anchor=None, limits=None):
    rec={'id':id,'format':fmt,'source_utf8':source,'source':source_metadata(source),'expected':{'code':code,'reason':reason},'purposes':purpose}
    if anchor is not None:
        token=anchor
        a,b=find_n(source,token)
        rec['expected']['anchor_span']=make_span(source,a,b)
        rec['expected']['anchor_lexeme']=token
    if limits: rec['expected']['limit_context']=limits
    refusals.append(rec)

refusal('json-duplicate-escaped-key','json','{"x": 1, "\\u0078": 2}','CODE_CONFIG_DUPLICATE_KEY','decoded key collision',['escaped duplicate keys'],'"\\u0078"')
refusal('json-plus-sign','json','{"rate": +1}','CODE_CONFIG_SYNTAX_INVALID','plus sign outside JSON number grammar',['JSON plus grammar'],'+')
refusal('json-leading-zero','json','{"n": 01}','CODE_CONFIG_SYNTAX_INVALID','leading zero outside JSON number grammar',['JSON leading-zero grammar'],'01')
refusal('json-underscore','json','{"n": 1_000}','CODE_CONFIG_SYNTAX_INVALID','underscore outside JSON number grammar',['JSON underscore grammar'],'1_000')
refusal('json-trailing-comma','json','{"n": 1,}','CODE_CONFIG_SYNTAX_INVALID','trailing comma outside JSON grammar',['JSON trailing comma'],'}')
refusal('json-nonfinite','json','{"n": NaN}','CODE_CONFIG_SYNTAX_INVALID','nonfinite constant outside JSON grammar',['nonfinite refusal'],'NaN')
refusal('json-negative-zero-integer','json','-0','CODE_CONFIG_NUMBER_INVALID','negative zero is refused',['negative-zero variants'],'-0')
refusal('json-negative-zero-decimal','json','-0.0','CODE_CONFIG_NUMBER_INVALID','negative zero is refused',['negative-zero variants'],'-0.0')
refusal('json-explicit-exponent-over','json','1e-129','CODE_CONFIG_LIMIT_EXCEEDED','numeric absolute exponent exceeds profile',['explicit exponent cap'],limits={'limit_name':'max_numeric_abs_exponent','limit':128,'observed':129})
refusal('json-tuple-exponent-over','json','0.'+'0'*128+'1','CODE_CONFIG_LIMIT_EXCEEDED','exact Decimal tuple exponent exceeds profile',['tuple exponent cap'],limits={'limit_name':'max_numeric_abs_exponent','limit':128,'observed':129})
refusal('json-coefficient-over','json','1'*65,'CODE_CONFIG_LIMIT_EXCEEDED','numeric coefficient digit count exceeds profile',['coefficient cap'],limits={'limit_name':'max_numeric_coefficient_digits','limit':64,'observed':65})
refusal('json-lowered-canonical-cap','json','1e-3','CODE_CONFIG_LIMIT_EXCEEDED','canonical decimal length exceeds supplied lowered profile',['lowered canonical-length boundary'],limits={'limit_name':'max_numeric_canonical_bytes','limit':3,'observed':5})
refusal('json-bom','json','\ufeff{"x": 1}','CODE_CONFIG_BYTES_INVALID','initial UTF-8 BOM',['BOM refusal'],'\ufeff')
refusal('json-bare-cr','json','{"x":\r1}','CODE_CONFIG_BYTES_INVALID','bare CR',['bare CR refusal'],'\r')
refusal('json-comment','json','{"x": 1 // comment\n}','CODE_CONFIG_SYNTAX_INVALID','comments outside JSON grammar',['comment refusal'],'//')
refusal('toml-negative-zero-integer','toml','n = -0','CODE_CONFIG_NUMBER_INVALID','negative zero is refused',['negative-zero variants'],'-0')
refusal('toml-negative-zero-decimal','toml','n = -0.0','CODE_CONFIG_NUMBER_INVALID','negative zero is refused',['negative-zero variants'],'-0.0')
refusal('toml-underscore-leading','toml','n = 1__0','CODE_CONFIG_SYNTAX_INVALID','invalid TOML digit separator placement',['TOML underscore grammar'],'1__0')
refusal('toml-base-prefixed','toml','n = 0x10','CODE_CONFIG_UNSUPPORTED','base-prefixed integer outside subset',['unsupported numeric forms'],'0x10')
refusal('toml-date','toml','when = 2026-09-09T00:00:00Z','CODE_CONFIG_UNSUPPORTED','date/time outside subset',['unsupported date/time'],'2026-09-09')
refusal('toml-nan','toml','rate = nan','CODE_CONFIG_UNSUPPORTED','nonfinite TOML value outside subset',['unsupported nonfinite'],'nan')
refusal('toml-multiline-array','toml','x = [\n  1,\n  2\n]\n','CODE_CONFIG_UNSUPPORTED','physical newline inside array outside subset',['unsupported multiline array'],'[')
refusal('toml-array-of-tables','toml','[[items]]\nvalue = 1\n','CODE_CONFIG_UNSUPPORTED','array of tables outside subset',['unsupported array of tables'],'[[items]]')
refusal('toml-inline-trailing-comma','toml','x = {a = 1,}\n','CODE_CONFIG_SYNTAX_INVALID','trailing comma not allowed in inline table',['inline trailing comma'],'}')
refusal('toml-duplicate-header','toml','[a]\nx = 1\n[a]\ny = 2\n','CODE_CONFIG_DUPLICATE_KEY','repeated explicit table header',['TOML header redefinition'],'[a]')
refusal('toml-inline-extension','toml','x = {a = 1}\n[x]\nb = 2\n','CODE_CONFIG_DUPLICATE_KEY','inline-table boundary cannot be extended',['inline-table boundary'],'[x]')
refusal('toml-dynamic-interpolation','toml','rate = "${BASE_RATE}"\n','CODE_CONFIG_DYNAMIC_UNSUPPORTED','interpolation marker in decoded string',['dynamic marker'],'"${BASE_RATE}"')
refusal('toml-dynamic-callable','toml','optimizer = "torch.optim.AdamW(lr=1e-4)"\n','CODE_CONFIG_DYNAMIC_UNSUPPORTED','callable-looking string',['callable marker'],'"torch.optim.AdamW(lr=1e-4)"')
refusal('toml-comment-dynamic-looking','toml','# ${BASE_RATE} and torch.optim.AdamW(x)\n','CODE_CONFIG_EMPTY','whitespace/comments-only document',['comment dynamic text'])
refusal('toml-multiline-string','toml','x = """line\ntext"""\n','CODE_CONFIG_UNSUPPORTED','multiline string outside subset',['unsupported multiline string'],'"""')
refusal('toml-comment-only','toml','# comment\n  # another\n','CODE_CONFIG_EMPTY','whitespace/comments-only document',['comment-only refusal'])

fixture={
 '$schema':'video-paper-wiki.code-config-kernel-fixture-r1.v1',
 'revision':1,
 'status':'INDEPENDENT_STATIC_AUTHORED_VECTORS_READY_FOR_IMPLEMENTATION_REVIEW',
 'scope':'Bounded data-only JSON/TOML source vectors; expected spans and parser values are authored separately from any implementation scanner.',
 'inputs':INPUTS,
 'profile_limits':LIMITS,
 'supplementary_observations':{
   'toml_transition_matrix': {'case_count':26,'py312_observation':{'path':'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1/architect-toml-matrix-py312-r2.json','sha256':'64c695830774b933524d043ef08eae65fc244788c420833bc861aa9a38f36fac','passed':26},'py313_observation':{'path':'artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1/architect-toml-matrix-py313-r2.json','sha256':'492cb659ce7eb82a9b68e4151ca28a38acd47da9764ff5592d5a85c9ec6c9194','passed':26}},
   'clarification_dynamic_positions':'CODE_CONFIG_DYNAMIC_UNSUPPORTED anchors the opening quote for quoted value tokens or first character for TOML bare keys; instance pointer /payload; reasons dynamic_key, dynamic_marker, callable_string with marker precedence.',
   'clarification_toml_states':'Ordinary headers, current/finalized dotted prefixes, implicit parents and closed inline boundaries are tracked; matrix is supplemental and not a whitelist.',
 },
 'span_contract':{
   'offsets':'original UTF-8 bytes and decoded Python codepoints, zero-based half-open',
   'lines':'one-based physical lines; columns are one-based codepoint columns; CRLF is two codepoints/bytes and one line advance',
   'snippet_sha256':'existing code_snippet_sha256 rule over CRLF-normalized selected physical lines, excluding terminal LF and excluding a following line at exclusive end',
   'normalization':'only CRLF to LF for normalized_sha256 and line_count; no Unicode normalization',
 },
 'success_vectors':vectors,
 'refusal_vectors':refusals,
 'coverage':{
   'success_vector_count':len(vectors),'refusal_vector_count':len(refusals),
   'formats':['json','toml'],'required_topics':[
    '1e-4','betas [0.9,0.999]','decimal 1e0','plus/underscore TOML grammar','JSON pointer escaping','Unicode and escaped Unicode','CRLF/LF/TAB','empty strings/keys/containers','TOML dotted keys and header promotion','inline arrays/tables','comments','negative-zero variants','explicit exponent cap','Decimal tuple exponent cap','coefficient boundary','lowered canonical-length boundary','unsupported multiline/date/base/inf/nan','dynamic markers and harmless comment text'
   ],
 },
 'claims_not_made':['No whole-parser acceptance claim','No public error-wire freeze','No implementation or production/test mutation','No official repository or capability claim'],
}
# Ensure artifact itself is deterministic and UTF-8; source bytes are represented exactly in source_utf8 strings.
out=OUT/'static-vectors-r1.json'
out.write_text(json.dumps(fixture,ensure_ascii=False,sort_keys=False,indent=2)+'\n',encoding='utf-8')
print(out)
print('bytes',out.stat().st_size,'sha256',hashlib.sha256(out.read_bytes()).hexdigest())
print('success',len(vectors),'refusal',len(refusals))
