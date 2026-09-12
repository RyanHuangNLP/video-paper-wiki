from __future__ import annotations
import hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/no-pdf-v1/terminal-1/source')
sys.path.insert(0, str(ROOT))
from tests.pdf_samples import sample_pdf_bytes, sample_pdf_path

out = {'checks': [], 'failures': [], 'observations': {}}
def check(name, ok, detail=None):
    out['checks'].append({'name':name, 'ok':bool(ok), 'detail':detail})
    if not ok:
        out['failures'].append(name)

def run(cmd, *, cwd=ROOT, **kw):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, **kw)

# exact bytes, parser behavior, path placement, and process-local identity
expected = {
    'tiny': (674, 'c37df90f89d97fd1e575ee894c8fce6c2a979b2de76332a20105f1af70d8c7b9', 1, 'Tiny VPKB paper'),
    'sectioned': (1206, '03645f6fdd81c46f7377ab28602aa070e51109c0c95500f06496d07de1badc4b', 2, 'Sectioned VPKB Paper'),
}
from pypdf import PdfReader
from io import BytesIO
for name, (size, digest, pages, title) in expected.items():
    data = sample_pdf_bytes(name)
    path = sample_pdf_path(name)
    reader = PdfReader(BytesIO(data))
    check(f'{name}:exact-bytes', len(data)==size and hashlib.sha256(data).hexdigest()==digest)
    check(f'{name}:pypdf', len(reader.pages)==pages and reader.metadata.title==title)
    check(f'{name}:outside-root', not path.is_relative_to(ROOT) and path.parent.parent==Path('/tmp').resolve())
    check(f'{name}:stable-path', sample_pdf_path(name)==path and path.read_bytes()==data)

for name in ['', 'tiny.pdf', '../tiny', '/tmp/tiny', 'unknown']:
    try:
        sample_pdf_path(name)
    except ValueError:
        ok = True
    else:
        ok = False
    check(f'unknown:{name!r}', ok)

# fresh child processes get separate roots and cleanup on ordinary exit.
code = "from tests.pdf_samples import sample_pdf_path; print(sample_pdf_path('tiny'))"
children=[]
for i in range(2):
    p=run([sys.executable,'-c',code])
    path=Path(p.stdout.strip())
    children.append(path)
    check(f'child-{i}:success', p.returncode==0 and bool(p.stdout.strip()))
    check(f'child-{i}:cleaned', not path.parent.exists())
check('child-processes:separate', children[0].parent != children[1].parent)

# Ignore patterns, including newline names, in a disposable repository.
for name in ['paper.pdf','paper.PDF','nested/paper.pDf','nested space/line\nbreak.PdF']:
    p=run(['git','check-ignore','--no-index','-q','--',name])
    check(f'ignore:{name!r}', p.returncode==0, p.stderr)

# Extract and execute the actual workflow guard in a disposable repo with NUL-safe paths.
workflow=(ROOT/'.github/workflows/tests.yml').read_text()
m=re.search(r"      - name: Reject tracked PDF files\n        run: \|\n((?:          .*\n)+)", workflow)
check('workflow:guard-present', m is not None)
if m:
    guard='\n'.join(line[10:] for line in m.group(1).splitlines())
    with tempfile.TemporaryDirectory(prefix='no-pdf-guard-', dir='/private/tmp') as td:
        repo=Path(td)
        e=os.environ.copy(); e.pop('GIT_DIR',None); e.pop('GIT_WORK_TREE',None); e.pop('GIT_INDEX_FILE',None)
        subprocess.run(['git','init','--quiet',str(repo)], env=e, check=True, capture_output=True)
        (repo/'.gitignore').write_text((ROOT/'.gitignore').read_text())
        (repo/'guide.md').write_text('fixture\n')
        (repo/'untracked.PdF').write_bytes(b'placeholder')
        subprocess.run(['git','add','--','.gitignore','guide.md'], cwd=repo, env=e, check=True, capture_output=True)
        p= subprocess.run(['bash','-e','-o','pipefail','-c',guard],cwd=repo,env=e,text=True,capture_output=True)
        check('workflow:untracked-pdf-allowed',p.returncode==0,p.stderr)
        # Use one disposable repository per spelling: macOS case-insensitive filesystems
        # can otherwise make paper.PDF alias a prior paper.pdf path.
        for name in ['paper.pdf','paper.PDF','nested/space and\nline.pDf']:
            case=repo / ('case-' + str(len(list(repo.glob('case-*')))));
            case.mkdir()
            subprocess.run(['git','init','--quiet',str(case)], env=e, check=True, capture_output=True)
            (case/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
            (case/'guide.md').write_text('test repository\n')
            subprocess.run(['git','add','--','.gitignore','guide.md'], cwd=case, env=e, check=True, capture_output=True)
            path=case/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'synthetic tracked placeholder')
            subprocess.run(['git','add','--force','--',name], cwd=case, env=e, check=True, capture_output=True)
            p=subprocess.run(['bash','-e','-o','pipefail','-c',guard], cwd=case, env=e, text=True, capture_output=True)
            check(f'workflow:reject:{name!r}', p.returncode==1 and 'Tracked PDF files are forbidden:' in p.stderr and repr(name) in p.stderr, p.stderr)


# All frozen consumers must use the helper instead of the deleted repository fixtures.
freeze=json.loads((ROOT.parent.parent.parent.parent/'docs/ai/packets/no-pdf-v1/freeze-r2.json').read_text()) if False else json.loads(Path('/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/no-pdf-v1/freeze-r2.json').read_text())
old_refs=[]; missing=[]
for rel in freeze['consumer_paths']:
    text=(ROOT/rel).read_text()
    if 'tests/fixtures/pdfs/' in text or 'fixtures/pdfs/' in text:
        old_refs.append(rel)
    if 'from tests.pdf_samples import sample_pdf_path' not in text:
        missing.append(rel)
check('consumers:no-old-fixture-reference', not old_refs, old_refs)
check('consumers:all-helper-imports', not missing, missing)
out['observations']['consumer_count']=len(freeze['consumer_paths'])
out['observations']['old_refs']=old_refs
out['observations']['missing_helper_imports']=missing

# Candidate outer-tree physical PDFs and prospective path set.
outer_pdfs=[str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf' and 'vendor/claude-obsidian/' not in str(p.relative_to(ROOT))]
out['observations']['outer_physical_pdfs']=outer_pdfs
check('candidate:no-outer-physical-pdfs', not outer_pdfs, outer_pdfs)
submodule_pdfs=[str(p.relative_to(ROOT)) for p in (ROOT/'vendor/claude-obsidian').rglob('*') if p.is_file() and p.suffix.lower()=='.pdf']
out['observations']['nested_submodule_pdfs']=submodule_pdfs

# Diff hygiene and exact deletion/helper presence.
p=run(['git','diff','--check'])
check('candidate:diff-check',p.returncode==0,p.stdout+p.stderr)
check('candidate:deletions', all(not (ROOT/x).exists() for x in freeze['deleted_paths']))
check('candidate:helper-tests', (ROOT/'tests/pdf_samples.py').is_file() and (ROOT/'tests/test_pdf_samples.py').is_file())

# Verify workflow guard is before dependency setup.
if m:
    check('workflow:ordering', workflow.index('name: Check out source') < m.start() < workflow.index('name: Set up uv and select Python'))

out['ok']=not out['failures']
print(json.dumps(out, ensure_ascii=False, indent=2))
