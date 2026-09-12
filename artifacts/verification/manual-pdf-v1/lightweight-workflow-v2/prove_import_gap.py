"""Bounded synthetic reproduction against the accepted CLI; never mutate real papers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
SRC = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')
PYTHON = ROOT / '.venv/bin/python'
REPORT = Path(__file__).parent
env = dict(os.environ, PYTHONPATH=str(SRC / 'src') + os.pathsep + str(SRC), PYTHONDONTWRITEBYTECODE='1')
observations = []
with tempfile.TemporaryDirectory(prefix='vp.v2.gap.', dir='/private/tmp') as temp:
    base = Path(temp)
    pdf = base / 'synthetic.pdf'
    p = subprocess.run([str(PYTHON), '-B', '-c',
        'from pathlib import Path; from tests.research.test_light_pdf import _pdf_with_page_texts; '
        'import sys; Path(sys.argv[1]).write_bytes(_pdf_with_page_texts(["Synthetic quasar method evidence."]))',
        str(pdf)], env=env, cwd=base, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    workspace = base / '.work' / 'workspace'

    def cli(*args):
        p = subprocess.run([str(PYTHON), '-B', '-m', 'video_paper_wiki_research', *map(str, args)],
                           cwd=base, env=env, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout), p.stderr

    code, added, _ = cli('pdf', 'add', '--pdf', pdf, '--workspace', workspace)
    assert code == 0 and added['ok']
    assert cli('index', 'build', '--workspace', workspace)[0] == 0
    code, context, _ = cli('qa', 'export', '--question', 'quasar method', '--workspace', workspace)
    assert code == 0 and context['ok'] and context['evidence']
    cp = base / 'context.json'
    cp.write_text(json.dumps(context))
    answer = base / 'answer.json'
    chunk = context['evidence'][0]['chunk_id']
    answer.write_text(json.dumps({'text': 'Synthetic method [@' + chunk + '].', 'citations': [{'chunk_id': chunk}]}))

    def attempt(name, context_path):
        output = base / (name + '.md')
        code, response, stderr = cli('qa', 'import', '--context', context_path, '--answer', answer,
                                    '--workspace', workspace, '--output', output)
        observations.append({'name': name, 'exit_code': code, 'ok': response.get('ok'),
                             'status': response.get('status'), 'output_created': output.exists(), 'stderr': stderr})

    attempt('valid_control', cp)
    tampered = json.loads(cp.read_text())
    e = tampered['evidence'][0]
    e['text'] = 'Synthetic fabricated evidence absent from source.'
    e['text_sha256'] = hashlib.sha256(e['text'].encode()).hexdigest()
    changed_context = base / 'tampered.json'
    changed_context.write_text(json.dumps(tampered))
    attempt('tampered_context_text_and_hash', changed_context)
    source = Path(added['markdown_path'])
    source.write_text(source.read_text().replace('quasar method evidence', 'nebula changed evidence'))
    attempt('source_changed_without_reindex', cp)
    assert cli('index', 'build', '--workspace', workspace)[0] == 0
    attempt('old_context_after_reindex', cp)

result = {'baseline': '0fcae592acb977c6b422e7de3b2c3e0cf79df5a0',
          'synthetic_only': True, 'temporary_inputs_cleaned': True, 'observations': observations,
          'source_modules_sha256': {p: hashlib.sha256((SRC / p).read_bytes()).hexdigest() for p in
              ('src/video_paper_wiki_research/cli.py', 'src/video_paper_wiki_research/light_qa.py',
               'src/video_paper_wiki_research/light_index.py')}}
(REPORT / 'import-gap-observation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(observations))
