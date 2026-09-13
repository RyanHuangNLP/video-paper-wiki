"""Independent expected bytes: stdlib JSON over fixed ASCII-key envelope + IEEE bits.
Never imports Builder's ledger_locator or production JCS to create expectations.
"""
from pathlib import Path
import copy,hashlib,json,math,struct
PREFIX='vpwiki-locator-v1:';SCHEMA='video-paper-wiki.ledger-locator.v1'
sha=lambda b:hashlib.sha256(b).hexdigest()
def dumps(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def ratio(v):
 if type(v) is int:return [v,1]
 bits=struct.unpack('>Q',struct.pack('>d',v))[0];sign=-1 if bits>>63 else 1;exponent=(bits>>52)&2047;fraction=bits&((1<<52)-1)
 assert exponent!=2047
 if exponent==0:mantissa=fraction;power=-1074
 else:mantissa=(1<<52)|fraction;power=exponent-1023-52
 n=sign*mantissa;d=1
 if power>=0:n<<=power
 else:d<<=-power
 g=math.gcd(abs(n),d);return [n//g,d//g]
def envelope(locator):
 base=copy.deepcopy(locator);coords=base.pop('bbox',None);e={'schema':SCHEMA,'locator':base}
 if coords is not None:e['bbox_rationals']=[ratio(x) for x in coords]
 return e
def wire(locator):return PREFIX+dumps(envelope(locator))
def fingerprint(locator,relation):
 fields=['kind','source_id','page','ref','artifact_path','artifact_sha256','text_sha256'] if locator['kind']=='pdf' else ['kind','source_id','repository','commit','path','lines','snippet_sha256']
 d={k:copy.deepcopy(locator[k]) for k in fields};d['relation']=relation
 if d['kind']=='code':d['repository']=d['repository'].casefold()
 return sha(dumps([d]).encode())
pdf={'kind':'pdf','source_id':'src-independent','page':1,'ref':'#/texts/0','artifact_path':'.raw/derived/independent/docling/fp/document.json','artifact_sha256':'a'*64,'text_sha256':'b'*64}
code={'kind':'code','source_id':'src-code','repository':'Owner/Repo','commit':'c'*40,'path':'src/main.py','lines':{'start':1,'end':3},'snippet_sha256':'d'*64}
valid=[]
def add(name,locator):
 s=wire(locator);decoded=copy.deepcopy(locator)
 if 'bbox' in decoded:decoded['bbox']=[n if d==1 else n/d for n,d in envelope(locator)['bbox_rationals']]
 valid.append({'name':name,'input_locator':locator,'expected_decoded_locator':decoded,'expected_wire':s,'wire_utf8_bytes':len(s.encode()),'wire_sha256':sha(s.encode()),'evidence_fingerprints':{rel:fingerprint(locator,rel) for rel in ['supports','contradicts','uncertain']}})
add('pdf_minimal',copy.deepcopy(pdf))
add('pdf_optional_fractional',dict(pdf,charspan=[0,12],bbox=[10.25,20.5,100.125,40.75]))
add('pdf_unicode_ref',dict(pdf,ref='  #/texts/é😀\t\n"\\  ',charspan=[0,0]))
add('pdf_integral_float_signedzero',dict(pdf,bbox=[1.0,1,-0.0,0]))
add('pdf_binary64_extremes',dict(pdf,bbox=[.1,float.fromhex('0x0.0000000000001p-1022'),float.fromhex('0x1.fffffffffffffp+1023'),-.5]))
add('pdf_large_ints_2048bits',dict(pdf,bbox=[(1<<2048)-1,-((1<<2048)-1),0,1]))
add('code_minimal',copy.deepcopy(code))
add('code_symbol_unicode',dict(code,symbol=' Class.é😀 \t\n"\\ '))
# Boundary string chosen by exact expected UTF8 length, not character count.
empty=wire(dict(pdf,ref=''));room=65536-len(empty.encode());add('wire_ascii_exact_65536',dict(pdf,ref='x'*room))
q,r=divmod(room,4);add('wire_utf8_exact_65536',dict(pdf,ref='😀'*q+'x'*r))
assert valid[-1]['wire_utf8_bytes']==valid[-2]['wire_utf8_bytes']==65536
minimum=valid[0]['expected_wire'];payload=minimum[len(PREFIX):]
invalid=[{'name':'trailing_LF','wire':minimum+'\n','code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'structural_space','wire':PREFIX+' '+payload,'code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'alternate_slash_escape','wire':minimum.replace('#/texts/0','#\\/texts\\/0'),'code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'reordered_keys','wire':PREFIX+json.dumps(envelope(pdf),ensure_ascii=False,separators=(',',':')),'code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'duplicate_schema','wire':PREFIX+payload[:-1]+',"schema":"'+SCHEMA+'"}','code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'escaped_duplicate_schema','wire':PREFIX+payload[:-1]+',"sch\\u0065ma":"'+SCHEMA+'"}','code':'LEDGER_LOCATOR_INVALID','pointer':''},{'name':'page_float_spelling','wire':minimum.replace('"page":1','"page":1.0'),'code':'LEDGER_LOCATOR_INVALID'},{'name':'page_exponent_spelling','wire':minimum.replace('"page":1','"page":1e0'),'code':'LEDGER_LOCATOR_INVALID'},{'name':'wire_ascii_65537','wire':wire(dict(pdf,ref='x'*(room+1))),'code':'PROJECTION_LIMIT_EXCEEDED'},{'name':'wire_utf8_65537','wire':valid[-1]['expected_wire'].replace('😀','😀x',1),'code':'PROJECTION_LIMIT_EXCEEDED'}]
assert invalid[-1]['wire'].isascii()==False and len(invalid[-1]['wire'].encode())==65537 and len(invalid[-1]['wire'])<65536
badpairs=[('not_power_two',[1,3]),('unreduced',[2,4]),('noncanonical_zero',[0,2]),('underflow',[1,1<<1075]),('rounded',[(1<<53)+1,1<<53]),('overflow',[(1<<2047)-1,2]),('negative_denominator',[1,-2]),('bool_numerator',[True,1]),('float_denominator',[1,2.0])]
for name,pair in badpairs:
 e=envelope(dict(pdf,bbox=[0,1,2,3]));e['bbox_rationals'][0]=pair
 invalid.append({'name':'ratio_'+name,'wire':PREFIX+dumps(e),'code':'LEDGER_LOCATOR_INVALID'})
e=envelope(dict(pdf,bbox=[0,1,2,3]));e['bbox_rationals'][0]=[1<<2048,1];invalid.append({'name':'ratio_2049bit','wire':PREFIX+dumps(e),'code':'PROJECTION_LIMIT_EXCEEDED'})
e=envelope(dict(pdf,bbox=[0,1,2,3]));invalid.append({'name':'negative_zero_spelling','wire':(PREFIX+dumps(e)).replace('[[0,1]','[[-0,1]'),'code':'LEDGER_LOCATOR_INVALID','pointer':''})
assert all(x['wire']!=minimum for x in invalid)
assert ratio(.1)==[3602879701896397,36028797018963968]
assert ratio(float.fromhex('0x0.0000000000001p-1022'))==[1,1<<1074]
root=Path.cwd();out={'status':'independent fixed expectations prepared before implementation review; not executed against Builder module','spec_sha256':'493fc3d135141512c7956f3729726ae72febbb1a34cc8cd5669add96af16e191','expected_construction':'Standard JSON with UTF8/noASCIIescaping/sorted fixed ASCIIkeys/compact separators; binary64 ratio decoded from IEEE754bits independently of float.as_integer_ratio and Builder code.','generator_sha256':sha(Path(__file__).read_bytes()),'unchanged_authority_source_sha256':{str(p):sha(p.read_bytes()) for p in [Path('src/video_paper_wiki/identity.py'),Path('src/video_paper_wiki/jcs.py'),Path('schemas/video-paper-wiki.common.v1.schema.json')]},'valid_vectors':valid,'invalid_wire_vectors':invalid,'relation_map':{'supports':'supports','contradicts':'contradicts','uncertain':'context'},'limits':'Synthetic locator fields are not extracted source truth. No upstream CLI replay or Builder implementation call performed.'}
Path('<TMP>/vpl-steward-vectors.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps({'valid_vectors':len(valid),'invalid_wire_vectors':len(invalid),'output_bytes':Path('<TMP>/vpl-steward-vectors.json').stat().st_size,'output_sha256':sha(Path('<TMP>/vpl-steward-vectors.json').read_bytes())}))
