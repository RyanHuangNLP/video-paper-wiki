"""Pinned public-CLI compatibility fixtures, ported from reviewed investigation r4.

Only stable_source_id is imported in an isolated subprocess after pin/source
checks. Fixture records and two-section pages are not complete project records;
upstream string locators do not freeze the structured domain mapping. The head
uses a fixture-only schema. Global navigation is separate setup, outside the
publication receipt. No LLM/reranker flags are not OS network isolation or real
operator approval. These fixtures do not implement the production adapter.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import platform
import stat
import subprocess
import sys
P = pathlib.Path
REPO = P(__file__).resolve().parents[2]
def _upstream():
    local = REPO / 'vendor/claude-obsidian'
    pin = P('/Users/huangzhanpeng/python_code/video-paper-wiki/vendor/claude-obsidian')
    if (local / 'scripts/claude-obsidian.py').is_file() and (local / '.git').exists():
        return local
    if (pin / 'scripts/claude-obsidian.py').is_file() and (pin / '.git').exists():
        return pin
    return local
UP = _upstream()
CORE = UP / 'scripts/claude-obsidian.py'
STAMP = '2026-08-31T00:00:00Z'
DAY = '2026-08-31'
PIN = '9f8c1199047eac2c3828496279fbb7ba9540b90b'
KNOWN = {'claude_obsidian/transaction.py': 'e007e3b7d08f72eabc4a95c7031fb596c201562432cf37cc649136b02b223de2', 'claude_obsidian/ledgers.py': '9751d56272e2256bde643e7d3effd47f4c875ce02422be09a8dc0a148113f2d1', 'skills/wiki/references/operation-transactions.md': '75a6c01950983c6210647ee11104f3be0c389fd7f81458d9d0f06306401a8f83'}
KNOWN['LICENSE'] = '1c5915b8cde3e16949e40961353e483d44a65f90fae72405465dcff60118e57f'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def dump(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def jsonbytes(v):
    return (json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()

def snapshot(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and '.git' not in p.relative_to(root).parts}

def verify_sources(out):
    if not (UP / '.git').exists():
        raise AssertionError('Pinned upstream checkout missing; initialize the recorded submodule before pytest (tests never download).')
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(out), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'LC_ALL': 'C', 'LANG': 'C'}
    observations = []
    for args in [['rev-parse', 'HEAD'], ['status', '--porcelain', '--untracked-files=all']]:
        cmd = ['git', '-C', str(UP), *args]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
        observations.append({'argv': cmd, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == 0, observations
    head = observations[0]['stdout'].strip()
    assert head == PIN, ('Pinned upstream HEAD mismatch', head, PIN)
    assert not observations[1]['stdout'], ('Pinned upstream checkout is dirty', observations[1])
    for name, wanted in KNOWN.items():
        assert sha((UP / name).read_bytes()) == wanted, ('Pinned source digest mismatch', name)
    assert '__version__ = "2.1.1"' in (UP / 'claude_obsidian/__init__.py').read_text()
    before = snapshot(UP)
    dump(out / 'source-provenance.json', {'head': head, 'version': '2.1.1', 'known_sha256': KNOWN, 'git_observations': observations, 'source_inventory': before, 'python': sys.version, 'platform': platform.platform()})
    return before
STABLE_SOURCE_SCRIPT = "\nimport json, pathlib, sys\nroot = pathlib.Path(sys.argv[1]).resolve()\nsys.path.insert(0, str(root))\nimport claude_obsidian\nfrom claude_obsidian import ledgers\nassert claude_obsidian.__version__ == '2.1.1'\nassert pathlib.Path(ledgers.__file__).resolve() == root / 'claude_obsidian/ledgers.py'\nassert ledgers.stable_source_id('file', '.raw/captured/' + 'a' * 64 + '.pdf', 'a' * 64) == 'src-42baa0cddcfa30cdd5af'\nprint(json.dumps(ledgers.stable_source_id(*sys.argv[2:])))\n"

def stable_source(runner, kind, locator, digest):
    return runner.run('stable-source-id', ['-c', STABLE_SOURCE_SCRIPT, UP, kind, locator, digest])

class Runner:

    def __init__(self, out):
        self.out = out
        self.number = 0
        self.results = []
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': str(out / 'home'), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8'}
        (out / 'home').mkdir()

    def run(self, name, args, allowed=(0,)):
        self.number += 1
        label = f'{self.number:02d}-{name}'
        cmd = [sys.executable, '-B', *map(str, args)]
        p = subprocess.run(cmd, cwd=self.out, env=self.env, capture_output=True, text=True, timeout=90)
        (self.out / f'{label}.stdout').write_text(p.stdout)
        (self.out / f'{label}.stderr').write_text(p.stderr)
        record = {'name': name, 'argv': cmd, 'cwd': str(self.out), 'environment': self.env, 'exit_code': p.returncode, 'stdout_file': f'{label}.stdout', 'stderr_file': f'{label}.stderr'}
        self.results.append(record)
        dump(self.out / 'commands.json', self.results)
        try:
            value = json.loads(p.stdout)
        except ValueError:
            value = None
        if value is not None:
            dump(self.out / f'{label}.json', value)
        assert p.returncode in allowed, (name, p.returncode, p.stdout, p.stderr)
        return value if value is not None else {'fixture_process_result': True, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}

    def cli(self, name, *args, allowed=(0,)):
        return self.run(name, [CORE, *args], allowed)

    def inspect(self, name, vault, bundle):
        path = self.out / f'{name}.bundle.json'
        dump(path, bundle)
        return self.cli(name, 'transaction', 'inspect', path, '--vault', vault)

    def apply(self, name, vault, bundle, plan):
        path = self.out / f'{name}.bundle.json'
        dump(path, bundle)
        return self.cli(name, 'transaction', 'apply', path, '--vault', vault, '--approved-plan-sha256', plan['approval_sha256'])

def init(r, vault, label):
    args = ['init', str(vault), '--operation-id', label, '--generated-at', STAMP]
    dry = r.cli(label + '-dry', *args)
    assert dry['status'] == 'dry-run'
    assert not vault.exists()
    op = dry['operation']
    assert op['operation_type'] == 'setup'
    assert all((w['mode'] == 'create' for w in op['writes']))
    assert set((w['path'] for w in op['writes'])) == set(dry['changed_paths'])
    dump(r.out / (label + '-review.json'), {'reviewed': True, 'fixture_only': True, 'purpose': 'Initialize isolated disposable vault only', 'operation_sha256': sha(jsonbytes(op)), 'paths': dry['changed_paths'], 'approval_hash': dry['approved_plan_sha256']})
    result = r.cli(label + '-apply', *args, '--approved-plan-sha256', dry['approved_plan_sha256'], '--apply')
    assert vault.is_dir()
    return result

def bundle(vault, operation, optype, contents, reads=None, requests=None, updates=None):
    writes = []
    expected = {}
    for path, data in contents.items():
        assert isinstance(data, bytes)
        target = vault / path
        prior = target.read_bytes() if target.exists() else None
        expected[path] = sha(prior) if prior is not None else None
        writes.append({'path': path, 'mode': 'replace' if prior is not None else 'create', 'content': data.decode(), 'sha256': sha(data)})
    return {'schema': 'claude-obsidian.transaction.v1', 'operation_id': operation, 'operation_type': optype, 'writes': writes, 'expected_hashes': expected, 'read_preconditions': reads or {}, 'address_requests': requests or [], 'source_manifest_updates': updates or {}}

def receipt_for(vault, operation, optype, contents, sequence, previous, claims):
    from video_paper_wiki.identity import receipt_intent_sha256
    from video_paper_wiki.contracts import validate_document
    from video_paper_wiki.jcs import canonicalize
    writes = []
    for path, data in contents.items():
        target = vault / path
        prior = target.read_bytes() if target.exists() else None
        writes.append({'path': path, 'mode': 'replace' if prior is not None else 'create', 'before_sha256': sha(prior) if prior is not None else None, 'after_sha256': sha(data)})
    receipt = {'schema': 'video-paper-wiki.operation-receipt.v1', 'sequence': sequence, 'previous': previous, 'operation_id': operation, 'operation_type': optype, 'writes': writes, 'claimed_inputs': [{'path': path, 'mode': 'read', 'sha256': digest} for path, digest in sorted(claims.items())]}
    receipt['intent_sha256'] = receipt_intent_sha256(receipt)
    validate_document(receipt)
    path = f'wiki/meta/operations/{sequence:012d}-{operation}.json'
    data = canonicalize(receipt)
    head = {'schema': 'fixture.operation-head.v1', 'sequence': sequence, 'receipt_path': path, 'receipt_sha256': sha(data)}
    return (receipt, path, data, head)

def publish(r, vault, name, contents, sequence, previous, claimed, optype):
    from video_paper_wiki.jcs import canonicalize
    contents = dict(sorted(contents.items()))
    receipt, path, data, head = receipt_for(vault, name, optype, contents, sequence, previous, claimed)
    all_contents = {**contents, path: data, 'wiki/meta/registries/operation-head.json': canonicalize(head)}
    reads = dict(claimed)
    if previous is not None:
        reads[previous['path']] = previous['sha256']
    proposal = bundle(vault, name, optype, all_contents, reads=reads)
    before = {key: {'sha256': sha((vault / key).read_bytes()), 'mode': stat.S_IMODE((vault / key).stat().st_mode)} if (vault / key).exists() else None for key in all_contents}
    plan = r.inspect(name + '-inspect', vault, proposal)
    assert plan['changed_paths'] == list(all_contents)
    assert plan['changed_paths'][-1] == 'wiki/meta/registries/operation-head.json'
    assert plan['input_bundle_sha256'] == plan['expanded_bundle_sha256']
    assert set(plan['hashes']) == set(plan['modes']) == set(all_contents)
    for key, value in all_contents.items():
        assert plan['hashes'][key] == sha(value)
        assert plan['modes'][key] == (before[key]['mode'] if before[key] is not None else 384)
    result = r.apply(name + '-apply', vault, proposal, plan)
    assert result['status'] == 'complete'
    assert result['changed_paths'] == list(all_contents)
    assert result['bundle_sha256'] == plan['input_bundle_sha256']
    assert result['expanded_bundle_sha256'] == plan['expanded_bundle_sha256']
    assert result['approval_sha256'] == plan['approval_sha256']
    assert set(result['hashes']) == set(result['modes']) == set(all_contents)
    assert result['hashes'] == plan['hashes'] and result['modes'] == plan['modes']
    for key, value in all_contents.items():
        assert (vault / key).read_bytes() == value
    for key in all_contents:
        assert stat.S_IMODE((vault / key).stat().st_mode) == result['modes'][key]
    for write in receipt['writes']:
        assert sha((vault / write['path']).read_bytes()) == write['after_sha256']
    for key, digest in reads.items():
        assert sha((vault / key).read_bytes()) == digest
    journal = json.loads((vault / '.vault-meta/transactions' / name / 'journal.json').read_text())
    assert journal['applied'] == list(all_contents)
    dump(r.out / (name + '-observations.json'), {'receipt': receipt, 'head': head, 'head_is_fixture_only': True, 'plan': plan, 'result': result, 'journal_applied': journal['applied'], 'before': before, 'after': {key: {'sha256': sha((vault / key).read_bytes()), 'mode': stat.S_IMODE((vault / key).stat().st_mode)} for key in all_contents}})
    saved = r.out / 'final-bytes' / name
    for key, value in all_contents.items():
        target = saved / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return {'path': path, 'sha256': sha(data)}

def frontmatter(title, kind='meta'):
    return f'---\ntitle: {title}\ntype: {kind}\nstatus: generated\ncreated: {DAY}\nupdated: {DAY}\ntags:\n  - fixture\n---\n\n'

def positive(r, stable_source_id):
    from video_paper_wiki.identity import claim_id
    vault = r.out / 'v'
    init(r, vault, 'fixture-init')
    raw = (REPO / 'tests/fixtures/pdfs/tiny.pdf').read_bytes() + b'\n% fixture-marker quasarnebula\n'
    digest = sha(raw)
    paper_id = 'sha256:' + digest
    paper_path = f'wiki/papers/sha256-{digest}.md'
    nav = frontmatter('Fixture Navigation') + '# Fixture Navigation\n\n' + f'- [[{paper_path[:-3]}|Fixture paper]]\n'
    nav_bundle = bundle(vault, 'fixture-navigation', 'setup', {'wiki/index.md': nav.encode()})
    nav_plan = r.inspect('setup-navigation-inspect', vault, nav_bundle)
    r.apply('setup-navigation-apply', vault, nav_bundle, nav_plan)
    dump(r.out / 'navigation-scope.json', {'fixture_only': True, 'operation_type': 'setup', 'path': 'wiki/index.md', 'reason': 'Global wiki/index.md is outside current vpwiki receipt business_managed_path; fixture navigation is established separately, not hidden inside publication receipts.'})
    pristine = {path: sha((vault / path).read_bytes()) for path in ['wiki/meta/ledgers/source-ledger.json', 'wiki/meta/ledgers/claim-ledger.json']}
    previous = publish(r, vault, 'fixture-genesis', {'wiki/meta/records/fixture-bootstrap.json': jsonbytes({'fixture_only': True, 'purpose': 'pristine-ledger receipt bootstrap'})}, 1, None, pristine, 'generic')
    before_ledgers = {path: (vault / path).read_bytes() for path in pristine}
    source = vault / 'inbox/source.pdf'
    source.write_bytes(raw)
    args = ['capture', 'apply', '--vault', str(vault), '--operation-id', 'fixture-capture', '--generated-at', STAMP, 'inbox/source.pdf']
    capture_dry = r.cli('capture-dry', *args)
    assert capture_dry['status'] == 'dry-run'
    assert len(capture_dry['items']) == 1
    capture = r.cli('capture-apply', *args, '--approved-plan-sha256', capture_dry['approved_plan_sha256'], '--apply')
    item = capture['items'][0]
    stored = item['stored_path']
    assert item['source_identity'] == digest
    assert (vault / stored).read_bytes() == raw
    assert all(((vault / path).read_bytes() == value for path, value in before_ledgers.items()))
    sid = stable_source_id('file', stored, digest)
    text = 'The fixture PDF contains the deterministic query marker quasarnebula.'
    cid = claim_id('paper:' + paper_id, text)
    record = {'paper_id': paper_id, 'title': 'Quasarnebula Fixture Paper', 'title_zh': '固定来源测试论文', 'source_ids': [sid], 'claim_ids': [cid], 'created_at': STAMP, 'updated_at': STAMP, 'topics': ['fixture'], 'taxonomy': [{'axis': 'task/conditioning', 'slug': 'fixture'}]}

    def render():
        body = ('---\ntype: paper\n' + f'''paper_id: "{record['paper_id']}"\ntitle: {record['title']}\ntitle_zh: {record['title_zh']}\n''' + f'source_ids:\n  - {sid}\nclaim_ids:\n  - {cid}\n' + f"created_at: {record['created_at']}\nupdated_at: {record['updated_at']}\n" + f"created: {record['created_at'][:10]}\nupdated: {record['updated_at'][:10]}\nstatus: generated\ntopics:\n  - fixture\ntags:\n  - fixture\n---\n\n# Quasarnebula Fixture Paper\n\n## 一句话结论\n\n{text} ^{cid}\n\n## 证据状态\n\nThis is a provisional fixture claim, not human acceptance.\n\n[[wiki/index|Fixture Navigation]]\n").encode()
        tags = sorted({item['axis'] + '/' + item['slug'] for item in record['taxonomy']})
        return body.replace(b'tags:\n  - fixture\n', ('tags:\n' + ''.join(('  - ' + tag + '\n' for tag in tags))).encode())
    page = render()
    sources = {'schema': 'claude-obsidian.source-ledger.v1', 'generated_at': STAMP, 'sources': {sid: {'origin': {'kind': 'file', 'locator': stored}, 'content_kind': 'document', 'authority': 'synthetic', 'title': 'Generated fixture PDF', 'content_sha256': digest, 'ingested_at': DAY, 'retrieved_at': None, 'refresh_due': '2099-01-01', 'review_status': 'unreviewed', 'independence_key': None, 'pages': [paper_path], 'supersedes': None}}}
    sources['sources'][sid]['content_kind'] = 'synthetic'
    claims = {'schema': 'claude-obsidian.claim-ledger.v1', 'generated_at': STAMP, 'claims': {cid: {'text': text, 'risk': 'normal', 'assessment': 'provisional', 'confidence': 'low', 'location': {'path': paper_path, 'anchor': '^' + cid}, 'reviewed_at': None, 'notes': 'Fixture-only provenance; no scientific/human acceptance claim.', 'supersedes': None, 'evidence': [{'source_id': sid, 'relation': 'supports', 'locator': 'PDF byte comment fixture-marker quasarnebula'}]}}}
    contents = {'wiki/meta/ledgers/source-ledger.json': jsonbytes(sources), 'wiki/meta/ledgers/claim-ledger.json': jsonbytes(claims), paper_path: page}
    legacy_before = (vault / '.raw/.manifest.json').read_bytes()
    current = publish(r, vault, 'fixture-ingest', contents, 2, previous, {stored: digest}, 'ingest')
    assert (vault / '.raw/.manifest.json').read_bytes() == legacy_before
    assert render() == page == (vault / paper_path).read_bytes()
    assert page.count(('^' + cid).encode()) == 1
    assert claims['claims'][cid]['location']['path'] in sources['sources'][sid]['pages']
    assert cid == claim_id('paper:' + paper_id, claims['claims'][cid]['text'])
    assert 'address:' not in page.decode()
    dump(r.out / 'fixture-record.json', record)
    dump(r.out / 'positive-binding.json', {'paper_id': paper_id, 'source_id': sid, 'raw_sha256': digest, 'raw_path': stored, 'claim_id': cid, 'page_path': paper_path, 'page_sha256': sha(page), 'second_render_sha256': sha(render()), 'head': current, 'legacy_manifest_unchanged': True, 'capture_did_not_write_ledgers': True, 'address_persisted': False})
    lint = r.cli('strict-lint', 'lint', '--vault', vault, '--as-of', DAY, '--strict', allowed=(0, 1))
    dump(r.out / 'lint-observation.json', lint)
    lint_pass = lint['summary']['issues_found'] == 0
    r.run('contextual-prefix', [UP / 'scripts/contextual-prefix.py', '--vault', vault, '--all', '--no-llm'])
    synthetic = 'syn-' + sha(paper_path.encode())
    chunks = [json.loads(p.read_text()) for p in sorted((vault / '.vault-meta/chunks' / synthetic).glob('chunk-*.json'))]
    assert chunks and all((c['page_path'] == paper_path and c['page_address'] == synthetic for c in chunks))
    assert any((cid in c['raw_text'] for c in chunks))
    r.run('bm25-build', [UP / 'scripts/bm25-index.py', '--vault', vault, 'build'])
    hits = r.run('bm25-query', [UP / 'scripts/bm25-index.py', '--vault', vault, 'query', 'quasarnebula', '--top', '10'])
    retrieval = r.run('retrieval', [UP / 'scripts/retrieve.py', '--vault', vault, 'quasarnebula', '--no-rerank', '--top', '10'])
    assert any((c['page_path'] == paper_path for c in retrieval['candidates'])), retrieval
    assert any(hit['chunk_id'].startswith(synthetic + ':') and json.loads((vault / hit['path']).read_text())['page_path'] == paper_path for hit in hits), hits
    assert (vault / paper_path).read_bytes() == page
    dump(r.out / 'positive-results.json', {'lint_zero_findings': lint_pass, 'synthetic_address': synthetic, 'paper_chunk_count': len(chunks), 'bm25_hits': hits, 'retrieval': retrieval, 'unchanged_page_after_indexing': True, 'render_repeat_equal': True})
    assert lint_pass, lint
    assert all((not value for key, value in lint.items() if isinstance(value, list))), lint
    return vault

def negative(r):
    from video_paper_wiki.jcs import canonicalize
    from video_paper_wiki.identity import receipt_intent_sha256
    from video_paper_wiki.contracts import validate_document
    vault = r.out / 'n'
    init(r, vault, 'negative-init')
    page = 'wiki/papers/AddressFixture.md'
    body = (frontmatter('Address Fixture', 'paper') + '# Address Fixture\n\nquasarnebula address fixture.\n').encode()
    req = [{'path': page, 'prefix': 'c'}]
    b0 = bundle(vault, 'address-b0', 'ingest', {page: body}, requests=req)
    p0 = r.inspect('address-b0', vault, b0)
    h = p0['hashes'][page]
    receipt, receipt_path, _, _ = receipt_for(vault, 'address-b1', 'ingest', {page: body}, 1, None, {})
    receipt['writes'][0]['after_sha256'] = h
    receipt['intent_sha256'] = receipt_intent_sha256(receipt)
    validate_document(receipt)
    head_path = 'wiki/meta/registries/operation-head.json'
    head_data = canonicalize({'schema': 'fixture.operation-head.v1', 'sequence': 1, 'receipt_path': receipt_path, 'receipt_sha256': sha(canonicalize(receipt))})
    b1 = bundle(vault, 'address-b1', 'ingest', {page: body, receipt_path: canonicalize(receipt), head_path: head_data}, requests=req)
    p1 = r.inspect('address-b1', vault, b1)
    assert p1['hashes'][page] == h and h != sha(body)
    assert p1['changed_paths'] == [page, receipt_path, head_path, '.vault-meta/address-counter.txt', '.raw/.manifest.json']
    already = body.replace(b'---\n', b'---\naddress: c-000001\n', 1)
    b2 = bundle(vault, 'address-predeclared', 'ingest', {page: already, receipt_path: canonicalize(receipt), head_path: head_data}, requests=req)
    p2 = r.inspect('address-predeclared', vault, b2)
    assert p2['hashes'][page] == sha(already) == h and p2['changed_paths'][-2:] == ['.vault-meta/address-counter.txt', '.raw/.manifest.json']
    updates = {'inbox/source.pdf': {'hash': 'fixture-legacy', 'pages_created': [page]}}
    b3 = bundle(vault, 'source-update-only', 'ingest', {page: body, receipt_path: canonicalize(receipt), head_path: head_data}, updates=updates)
    p3 = r.inspect('source-update-only', vault, b3)
    assert p3['hashes'][page] == sha(body) and p3['changed_paths'] == [page, receipt_path, head_path, '.raw/.manifest.json']
    bypass = bundle(vault, 'direct-managed', 'ingest', {page: already, '.raw/.manifest.json': jsonbytes({'version': 1, 'sources': {}, 'address_map': {page: 'c-000001'}}), head_path: head_data})
    path = r.out / 'direct-managed.bundle.json'
    dump(path, bypass)
    rejected = r.cli('direct-managed', 'transaction', 'inspect', path, '--vault', vault, allowed=(2,))
    assert 'MANAGED_METADATA_COLLISION' in json.dumps(rejected), rejected
    assert not (vault / page).exists()
    r.apply('address-b0-apply', vault, b0, p0)
    assert (vault / page).read_bytes() == already
    manifest = json.loads((vault / '.raw/.manifest.json').read_text())
    assert manifest['address_map'][page] == 'c-000001'
    existing = bundle(vault, 'existing-address', 'ingest', {page: already, receipt_path: canonicalize(receipt), head_path: head_data}, requests=req)
    p4 = r.inspect('existing-address', vault, existing)
    assert p4['hashes'][page] == h and p4['changed_paths'][-2:] == ['.vault-meta/address-counter.txt', '.raw/.manifest.json']
    dump(r.out / 'negative-results.json', {'b0_page_hash': h, 'b1_page_hash': p1['hashes'][page], 'business_hash_stable_across_receipt_append': True, 'b1_changed_paths': p1['changed_paths'], 'head_last': False, 'predeclared_address_preserves_bytes': True, 'predeclared_still_appends_metadata': True, 'actual_existing_address_preserves_bytes': True, 'existing_address_changed_paths': p4['changed_paths'], 'source_update_only_changed_paths': p3['changed_paths'], 'direct_managed_rejection': rejected, 'inspections_left_page_absent_before_explicit_b0_apply': True})

def wrong_source_id(r):
    vault = r.out / 'v'
    path = 'wiki/meta/ledgers/source-ledger.json'
    before = (vault / path).read_bytes()
    ledger = json.loads(before)
    sid = next(iter(ledger['sources']))
    ledger['sources']['src-' + '0' * 20] = ledger['sources'].pop(sid)
    proposal = bundle(vault, 'wrong-source-id', 'ingest', {path: jsonbytes(ledger)})
    p = r.out / 'wrong-source-id.bundle.json'
    dump(p, proposal)
    result = r.cli('wrong-source-id', 'transaction', 'inspect', p, '--vault', vault, allowed=(2,))
    assert 'INVALID_PROVENANCE_LEDGER' in json.dumps(result) and 'canonical identity' in json.dumps(result)
    assert (vault / path).read_bytes() == before
    dump(r.out / 'wrong-source-id-results.json', {'rejected': result, 'source_ledger_unchanged': True})
