"""Replay the final document's Bash fences; keep protocol checks distinct from model quality."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
REPORT = Path(__file__).parent
EV = ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1'
BASE = json.loads((EV / 'baseline.json').read_text())
SRC = Path(BASE['source_root'])
DOC = SRC / 'docs/lightweight-pdf-quickstart.md'
WORK = ROOT / '.work/parallel/lightweight-r08-fix-parallel-v1/architect-r09'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(argv, env, name):
    p = subprocess.run(argv, env=env, cwd='/private/tmp', capture_output=True, text=True, timeout=180)
    (REPORT / (name + '.log')).write_text(p.stdout + '\nSTDERR:\n' + p.stderr)
    return {'argv': argv, 'cwd': '/private/tmp', 'exit_code': p.returncode,
            'log': str(REPORT / (name + '.log'))}

def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    text = DOC.read_text()
    blocks = re.findall(r'```bash\n(.*?)```', text, re.S)
    assert len(blocks) == 12
    assert sha(DOC) == '0c66d84539417e7d902925f1144e558b54fe481b79fd8b77258e562a9c74910e'
    assert sha(BASE['pdf_input']['path']) == BASE['pdf_input']['sha256']
    assert sha(BASE['wheel']['path']) == BASE['wheel']['sha256']
    helper = EV / 'terminal-3/protocol_from_export.py'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
    env.pop('PYTHONPATH', None)
    env['PATH'] = str(Path(BASE['wheel_python']).parent) + os.pathsep + env['PATH']
    results = []
    for shell, args in (('bash', ['/bin/bash', '--noprofile', '--norc']), ('zsh', ['/bin/zsh', '-f'])):
        ws = WORK / '.work' / (shell + '-workspace')
        out = WORK / (shell + ' output notes')
        setup = blocks[3]
        for var, value in {'PDF': BASE['pdf_input']['path'], 'WS': str(ws), 'OUT': str(out)}.items():
            setup = re.sub(r'^' + var + r'=.*$', var + '=' + shlex.quote(value), setup, flags=re.M)
        # Every actual CLI command below comes unchanged from the final document.
        sequence = [blocks[0], blocks[1], setup, blocks[4], blocks[5], blocks[6], blocks[7],
                    'python -I -B ' + shlex.quote(str(helper)) + ' --context "$CTX" --answer "$ANS"',
                    blocks[8], blocks[9],
                    'python -I -B ' + shlex.quote(str(helper)) + ' --context "$WCTX" --draft "$DRAFT"',
                    blocks[10], blocks[11]]
        script = REPORT / (shell + '-actual-document.sh')
        script.write_text('set -eu\n' + '\n'.join(sequence))
        result = run(args + [str(script)], env, shell + '-actual-document')
        result.update(shell=shell, script_sha256=sha(script), workspace=str(ws), output=str(out))
        results.append(result)
        if result['exit_code'] != 0:
            continue
        source_setup = blocks[2].replace('/absolute/path/to/integration/src', shlex.quote(str(SRC / 'src')))
        source_script = REPORT / (shell + '-actual-source.sh')
        source_script.write_text('set -eu\n' + source_setup + '\n' +
            'CLI=(python -B -m video_paper_wiki_research)\n' +
            setup.split('\n', 1)[1] + '\n' + blocks[4] + '\nCTX="$OUT/source-qa-context.json"\n' + blocks[7])
        source_env = dict(env)
        source_env['PATH'] = str(ROOT / '.venv/bin') + os.pathsep + os.environ['PATH']
        source = run(args + [str(source_script)], source_env, shell + '-actual-source')
        source['script_sha256'] = sha(source_script)
        result['source'] = source
        result['source_export_equals_installed'] = (out / 'qa-context.json').read_bytes() == (out / 'source-qa-context.json').read_bytes()
        links = []
        for filename in ('qa answer.md', 'writing draft.md'):
            output = out / filename
            report = REPORT / (shell + '-' + filename.replace(' ', '-') + '-links.json')
            link = run([BASE['wheel_python'], '-I', '-B', str(EV / 'terminal-1/verify_links.py'),
                        '--workspace', str(ws), '--output', str(output), '--report', str(report)], env,
                       shell + '-' + filename.replace(' ', '-') + '-verifier')
            link['report'] = json.loads(report.read_text())
            links.append(link)
        result['links'] = links
    result = {'document': str(DOC), 'document_sha256': sha(DOC), 'commands_from_final_document': True,
              'substitutions': ['PDF, WS, OUT paths', 'source PYTHONPATH'],
              'protocol_helper_sha256': sha(helper), 'model_quality_evaluation': False,
              'pdf_unchanged': sha(BASE['pdf_input']['path']) == BASE['pdf_input']['sha256'],
              'results': results}
    result['ok'] = all(r['exit_code'] == 0 and r['source']['exit_code'] == 0 and
                       r['source_export_equals_installed'] and
                       all(x['exit_code'] == 0 and x['report']['ok'] for x in r['links']) for r in results)
    (REPORT / 'document-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'ok': result['ok'], 'shells': [(r['shell'], r['exit_code']) for r in results]}))
    raise SystemExit(0 if result['ok'] else 1)

if __name__ == '__main__':
    main()
