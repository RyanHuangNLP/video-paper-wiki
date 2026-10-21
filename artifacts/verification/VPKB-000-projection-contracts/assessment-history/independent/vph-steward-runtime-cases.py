"""Python-only independent adversaries. No pending history API import or execution.

Factories defer allocations. Resource cases stay bounded (<=1,000,001 references),
not a large-memory stress test. Run only after stable candidate review.
"""
import copy,json
from pathlib import Path
class D(dict): pass
class L(list): pass
class S(str): pass
class I(int): pass
class Hostile:
    def __repr__(self): raise AssertionError('untrusted repr invoked')
    def __str__(self): raise AssertionError('untrusted str invoked')
def baseline():
    data=json.loads(Path('<TMP>/vph-steward-vectors.json').read_text())
    return copy.deepcopy(next(v['input'] for v in data['positive'] if v['name']=='raw_unicode_text_fractional_bbox'))
def cases():
    for name,mutate in [
        ('claims_tuple',lambda v:v.update(claims=tuple(v['claims']))),
        ('claims_subclass',lambda v:v.update(claims=L(v['claims']))),
        ('claim_subclass',lambda v:v['claims'].__setitem__(0,D(v['claims'][0]))),
        ('text_subclass',lambda v:v['claims'][0].update(canonical_claim_text=S('A claim'))),
        ('hostile_reason',lambda v:v['events'][-1].update(reason=Hostile())),
        ('nonstring_event_key',lambda v:v['events'][-1].update({None:'x'})),
        ('surrogate_text',lambda v:v['claims'][0].update(canonical_claim_text='\ud800')),
        ('subclass_page',lambda v:v['claims'][0]['evidence'][0].update(page=I(1))),
        ('nonfinite_bbox',lambda v:v['claims'][0]['evidence'][0].update(bbox=[float('inf'),0,1,1])),
    ]:
        v=baseline();mutate(v);yield name,v,'SCHEMA_INVALID'
    v=baseline();v['claims'][0]['self']=v['claims'];yield 'ancestor_cycle',v,'SCHEMA_INVALID'
    v=baseline();v['claims'][0]['evidence'][0]['bbox']=[1<<2048,0,1,1];yield '2049_bit_coordinate',v,'PROJECTION_LIMIT_EXCEEDED'
    for depth,expected in [(64,'SCHEMA_INVALID'),(65,'PROJECTION_LIMIT_EXCEEDED')]:
        # Virtual root, claims list, claim dict are the first three containers.
        x=None
        for _ in range(depth-3):x=[x]
        v=baseline();v['claims'][0]['extra']=x;yield 'virtual_container_depth_'+str(depth),v,expected
    # A shared 6-node list repeated 170k times is charged per occurrence, not ID.
    v={'claims':[[None]*5]*170000,'events':[]};yield 'aliased_occurrence_budget',v,'PROJECTION_LIMIT_EXCEEDED'
