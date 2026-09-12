"""Review the shipped CLI's default and explicit output link resolution."""
import json
from pathlib import Path
import re
import sys
import tempfile

SOURCE = Path('/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration')
ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
from tests.research.test_light_pipeline import _pdf_with_page_texts
from tests.research.light_real_demo import run_argv, add_pdf, build_workspace_index, export_qa, export_writing

with tempfile.TemporaryDirectory(prefix='vp.r05.links.', dir='/private/tmp') as temporary:
    root = Path(temporary)
    workspace = root / '.work' / 'papers-ws'
    pdf = root / 'paper.pdf'
    pdf.write_bytes(_pdf_with_page_texts(['Hybrid linear attention for efficient video generation.']))
    assert add_pdf(pdf, workspace)['ok']
    assert build_workspace_index(workspace)['ok']
    rows = []
    for kind, context, document_key, input_flag in [
        ('qa', export_qa('hybrid linear attention', workspace), 'text', '--answer'),
        ('writing', export_writing('hybrid linear attention', 'one sentence', workspace), 'markdown', '--draft'),
    ]:
        assert context['ok']
        chunk = context['evidence'][0]
        context_path = root / (kind + '-context.json')
        input_path = root / (kind + '-input.json')
        context_path.write_text(json.dumps(context))
        input_path.write_text(json.dumps({document_key: 'Hybrid linear attention. [@' + chunk['chunk_id'] + ']', 'citations': [{'chunk_id': chunk['chunk_id']}]}))
        for mode, output in [('explicit_current_directory', root / (kind + '.md')), ('implicit_context_sibling', context_path.with_suffix('.md')), ('nested_workspace', workspace / 'notes' / (kind + '.md'))]:
            argv = [kind, 'import', '--context', str(context_path), input_flag, str(input_path)]
            if mode != 'implicit_context_sibling':
                argv += ['--output', str(output)]
            result = run_argv(argv)
            assert result['ok'] and result['_exit_code'] == 0
            links = re.findall(r'\]\((papers/[^)]+#page-\d+)\)', output.read_text())
            assert links
            for link in links:
                path, anchor = link.split('#', 1)
                row = {'kind': kind, 'mode': mode, 'cli_status': result['status'], 'output': str(output), 'link': link, 'resolved_from_output_exists': (output.parent / path).is_file(), 'resolved_from_workspace_exists': (workspace / path).is_file(), 'source_anchor_exists': ('id="' + anchor + '"') in (workspace / path).read_text()}
                assert not row['resolved_from_output_exists'] and row['resolved_from_workspace_exists'] and row['source_anchor_exists']
                rows.append(row)
    delivered = []
    evidence = ROOT / 'artifacts/verification/manual-pdf-v1/lightweight-parallel-v1/terminal-4/sana'
    for file in ['sana-qa.md', 'sana-writing.md']:
        output = evidence / file
        links = sorted(set(re.findall(r'\]\((papers/[^)]+#page-\d+)\)', output.read_text())))
        delivered.append({'file': str(output), 'unique_links': len(links), 'broken_links': sum(not (output.parent / link.split('#', 1)[0]).is_file() for link in links)})
    print(json.dumps({'fixture_cases': rows, 'delivered_sana_artifacts': delivered}, ensure_ascii=False, indent=2))
