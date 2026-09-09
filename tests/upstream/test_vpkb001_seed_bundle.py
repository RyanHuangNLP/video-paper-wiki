from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
from video_paper_wiki.domain import render_seed_catalog

def _run(argv): return subprocess.run(argv,capture_output=True,text=True,check=True)
def test_seed_bundle_after_real_init_is_inspected_and_applied(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2]; upstream=root/'vendor/claude-obsidian'; cli=[sys.executable,'-I','-B','-X','utf8',str(upstream/'scripts/claude-obsidian.py')]
    assert _run(['git','-C',str(upstream),'rev-parse','HEAD']).stdout.strip()=='9f8c1199047eac2c3828496279fbb7ba9540b90b'
    checkout=tmp_path/'work';checkout.mkdir();_run(['git','init','-q',str(checkout)]);(checkout/'pyproject.toml').write_text('[project]\nname="video-paper-wiki"\nversion="0"\n')
    vault=tmp_path/'vault'; op='seed-fixture-init'; generated='2026-09-02T00:00:00Z'
    dry=json.loads(_run([*cli,'init',str(vault),'--operation-id',op,'--generated-at',generated]).stdout)
    applied=json.loads(_run([*cli,'init',str(vault),'--operation-id',op,'--generated-at',generated,'--approved-plan-sha256',dry['approved_plan_sha256'],'--apply']).stdout);assert applied['status']=='complete'
    monkeypatch.chdir(checkout);staged=render_seed_catalog('seed-public');bundle=Path(staged['bundle_path'])
    plan=json.loads(_run([*cli,'transaction','inspect',str(bundle),'--vault',str(vault)]).stdout);assert plan['valid'] is True and len(plan['changed_paths'])==74
    result=json.loads(_run([*cli,'transaction','apply',str(bundle),'--vault',str(vault),'--approved-plan-sha256',plan['approval_sha256']]).stdout)
    assert result['status']=='complete' and len(result['changed_paths'])==74
    assert (vault/'wiki/video-papers/catalog.md').is_file() and len(list((vault/'wiki/papers').glob('*.md'))) == 67
    lint=subprocess.run([*cli,'lint','--vault',str(vault),'--strict','--format','json','--as-of','2026-09-02'],capture_output=True,text=True,check=False)
    assert lint.returncode==0,lint.stdout+lint.stderr
    report=json.loads(lint.stdout); assert report['summary']['issues_found']==0
