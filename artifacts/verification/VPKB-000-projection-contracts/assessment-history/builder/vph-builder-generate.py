# Independent stdlib-only calculation: fixture object keys are ASCII, and all
# identity material is strings/integers, so sorted compact UTF-8 JSON equals JCS.
import hashlib
import json
import unicodedata
from pathlib import Path

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

pdf = {'relation': 'supports', 'kind': 'pdf', 'source_id': 'src-history-pdf', 'page': 2,
       'ref': '#/texts/4', 'artifact_path': '.raw/derived/history/document.json',
       'artifact_sha256': 'a' * 64, 'text_sha256': 'b' * 64,
       'bbox': [0.1, -0.0, 20, 30.5], 'charspan': [1, 7]}
code = {'relation': 'uncertain', 'kind': 'code', 'source_id': 'src-history-code',
        'repository': 'Owner/Repo', 'commit': 'c' * 40, 'path': 'src/model.py',
        'lines': {'start': 1, 'end': 3}, 'snippet_sha256': 'd' * 64, 'symbol': 'Model.forward'}
fields = {'pdf': ['relation','kind','source_id','page','ref','artifact_path','artifact_sha256','text_sha256'],
          'code': ['relation','kind','source_id','repository','commit','path','lines','snippet_sha256']}

def fingerprint(items):
    values = [{key: item[key] for key in fields[item['kind']]} for item in items]
    for value in values:
        if value['kind'] == 'code':
            value['repository'] = value['repository'].casefold()
    values.sort(key=lambda value: canonical(value).encode('utf-8'))
    return digest(canonical(values)), canonical(values)

fingerprints = {name: {'sha256': fingerprint(items)[0], 'canonical_utf8': fingerprint(items)[1]}
                for name, items in [('empty', []), ('pdf', [pdf]), ('code', [code]),
                                    ('pdf_duplicate', [pdf,pdf]), ('both', [pdf,code])]}
claims = []
events = []
vectors = []
claim_vectors = []
for subject, text, current, steps in [
    ('paper:arxiv:2311.15127', '  A\u2003café model claim.  ', [], [
        ('genesis', 'provisional', 'empty', '2026-09-01T12:00:00.123456789Z'),
        ('human_assessment', 'accepted', 'empty', '2026-08-30T12:00:00.100Z'),
        ('evidence_invalidation', 'provisional', 'pdf', '2026-08-30T12:00:00.1Z'),
        ('human_assessment', 'contested', 'pdf', '2026-08-30T12:00:00Z'),
        ('evidence_invalidation', 'provisional', 'empty', '2026-08-29T12:00:00Z'),
        ('human_assessment', 'deprecated', 'empty', '2026-08-29T12:00:00Z')]),
    ('repo:github:owner/repo', 'The model contains three layers.', [code], [
        ('genesis', 'provisional', 'empty', '0001-01-01T00:00:00Z'),
        ('evidence_invalidation', 'provisional', 'code', '9999-12-31T23:59:59.999999999Z'),
        ('human_assessment', 'unsupported', 'code', '2024-02-29T23:59:59.0Z'),
        ('human_assessment', 'deprecated', 'code', '2024-02-29T23:59:59Z')])]:
    material = 'video-paper-wiki.claim.v1\0' + subject + '\0' + ' '.join(unicodedata.normalize('NFKC', text).split())
    claim_id = 'clm-' + digest(material)[:20]
    previous = None
    state = None
    for kind, target, fp, at in steps:
        event = {'schema': 'video-paper-wiki.assessment-event.v1', 'claim_id': claim_id,
                 'previous_event_id': previous, 'actor_kind': 'human' if kind == 'human_assessment' else 'system',
                 'transition_kind': kind, 'from_assessment': state, 'to_assessment': target,
                 'claim_text_sha256': digest(text), 'evidence_fingerprint': fingerprints[fp]['sha256'],
                 'decided_by': 'fixture actor', 'decided_at': at, 'reason': 'Synthetic history fixture.'}
        preimage = canonical(event)
        event_id = 'ase-' + digest(preimage)[:20]
        event['event_id'] = event_id
        events.append(event)
        vectors.append({'event_id': event_id, 'canonical_utf8': preimage, 'sha256': digest(preimage)})
        previous, state = event_id, target
    claims.append({'claim_id': claim_id, 'stable_subject_id': subject, 'canonical_claim_text': text,
                   'evidence': current, 'assessment': state, 'reviewed_at': steps[-1][3][:10]})
    claim_vectors.append({'claim_id': claim_id, 'material_utf8': material, 'text_sha256': digest(text)})
heads = {claim['claim_id']: next(event['event_id'] for event in reversed(events) if event['claim_id'] == claim['claim_id']) for claim in sorted(claims,key=lambda c:c['claim_id'])}
result = {'authority': 'Independent stdlib hashlib + compact sorted UTF-8 JSON; ASCII object keys, integer-only identity values; no production helper imports.',
          'claims': claims, 'events': events, 'heads': heads, 'event_vectors': vectors,
          'claim_vectors': claim_vectors, 'fingerprints': fingerprints, 'evidence': {'pdf':pdf,'code':code}}
Path('tests/fixtures/assessment-history/complete-vectors.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
