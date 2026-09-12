"""Independently resolve full product hrefs and bind them to their own export payload."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
KEY = 'lightweight-r08-fix-parallel-v1'
EV = ROOT / 'artifacts/verification/manual-pdf-v1' / KEY
WORK = ROOT / '.work/parallel' / KEY
REPORT = Path(__file__).parent

def sha(value):
    return hashlib.sha256(value).hexdigest()

results = []
for shell in ('bash', 'zsh'):
    groups = [
        ('T3', EV / 'terminal-3' / (shell + ' import out'), WORK / 'terminal-3/.work' / (shell + '-ws')),
        ('T4', WORK / 'terminal-4' / (shell + ' import out'), WORK / 'terminal-4' / (shell + '-ws')),
        ('Architect', WORK / 'architect-r09' / (shell + ' output notes'), WORK / 'architect-r09/.work' / (shell + '-workspace')),
    ]
    for label, output_root, workspace in groups:
        for kind, model_file, md_file in (('qa', 'qa-answer.json', 'qa answer.md'), ('writing', 'writing-draft.json', 'writing draft.md')):
            context = json.loads((output_root / (kind + '-context.json')).read_text())
            model = json.loads((output_root / model_file).read_text())
            evidence = {e['chunk_id']: e for e in context['evidence']}
            expected = set()
            for citation in model['citations']:
                e = evidence[citation['chunk_id']]
                source = workspace / e['markdown_path']
                source_bytes = source.read_bytes()
                assert sha(source_bytes) == e['markdown_sha256']
                chunk = source_bytes.decode()[e['text_start']:e['text_end']]
                assert chunk == e['text'] and sha(chunk.encode()) == e['text_sha256']
                expected.add((str(source.resolve()), 'page-' + str(e['page'])))
            output = output_root / md_file
            markdown = output.read_text()
            hrefs = {a or b for a, b in re.findall(r'\]\((?:<([^>]+)>|([^\s)]+))\)', markdown)}
            hrefs.update(re.findall(r'`([^`]*source\.md#[^`]+)`', markdown))
            actual = set()
            for href in hrefs:
                parsed = urlsplit(href)
                if not parsed.path.endswith('source.md'):
                    continue
                assert not parsed.scheme and not parsed.netloc and not parsed.query
                source = (output.parent / unquote(parsed.path)).resolve()
                fragment = unquote(parsed.fragment)
                assert source.is_file()
                assert '<a id="' + fragment + '"></a>' in source.read_text()
                actual.add((str(source), fragment))
            assert actual == expected and actual
            results.append({'terminal': label, 'shell': shell, 'output': str(output),
                            'sha256': sha(output.read_bytes()), 'source_targets': sorted(actual),
                            'export_chunks_and_hashes_match': True, 'ok': True})
(REPORT / 'output-links.json').write_text(json.dumps({'ok': True, 'output_count': len(results),
    'unique_targets_per_output_total': sum(len(r['source_targets']) for r in results), 'results': results},
    ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'ok': True, 'outputs': len(results), 'source_targets': sum(len(r['source_targets']) for r in results)}))
