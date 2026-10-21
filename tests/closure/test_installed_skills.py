from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.closure.test_installed_vertical import installed_cli, installed_vertical_session, _tree_snapshot
from tests.support import make_checkout

ROOT=Path(__file__).resolve().parents[2]
SKILLS=ROOT/'.agents/skills'

@pytest.fixture(scope='module')
def installed_skill_evidence(installed_cli,installed_vertical_session,tmp_path_factory):
    base=tmp_path_factory.mktemp('vpwiki-installed-skills');bin_dir=base/'bin';bin_dir.mkdir()
    (bin_dir/'vpwiki').symlink_to(installed_cli/'vpwiki');sentinels={}
    for name in ('vpwiki-admin','curl','wget'):
        marker=base/(name+'.called');sentinels[name]=marker
        script=bin_dir/name;script.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\nexit 99\n');script.chmod(0o700)
    home=base/'home';home.mkdir();private_tmp=base/'tmp';private_tmp.mkdir(mode=0o700)
    checkout=base/'checkout';checkout.mkdir();make_checkout(checkout)
    subprocess.run(['/usr/bin/git','init','-q'],cwd=checkout,check=True)
    subprocess.run(['/usr/bin/git','add','pyproject.toml'],cwd=checkout,check=True)
    subprocess.run(['/usr/bin/git','-c','user.name=fixture','-c','user.email=fixture@example.invalid',
        'commit','-qm','fixture'],cwd=checkout,check=True)
    evidence=installed_vertical_session;fixture=evidence['root']/'fixture';vault=base/'restored-vault'
    shutil.copytree(evidence['restore'],vault)
    env={'PATH':str(bin_dir)+':/usr/bin:/bin','HOME':str(home),'TMPDIR':str(private_tmp),'PYTHONDONTWRITEBYTECODE':'1',
         'VPWIKI_BLOB_ROOT':str(evidence['root']/'blobs')}
    assert 'PYTHONPATH' not in env and 'VIRTUAL_ENV' not in env
    origin_result=subprocess.run([str(installed_cli/'python'),'-I','-c',
        'import json,video_paper_wiki;print(json.dumps({"module":video_paper_wiki.__file__}))'],
        cwd=checkout,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    origin=json.loads(origin_result.stdout)['module']
    assert str(installed_cli.parent) in origin and str(ROOT/'src') not in origin
    before=_tree_snapshot(vault);results=[]
    def run(argv,expected=0):
        result=subprocess.run([str(x) for x in argv],cwd=checkout,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
        assert result.returncode==expected,(argv,result.stdout,result.stderr)
        payload=json.loads(result.stdout);results.append((argv,payload));return payload
    seed=run(['vpwiki','seed','validate'])
    paper_plan=run(['vpwiki','ingest','plan','--request',fixture/'paper-1.request.json'])['data']
    paper_prepared=run(['vpwiki','ingest','prepare','--plan',paper_plan['plan_path'],
        '--approval-ref',fixture/'paper-1.runtime-approval.json'])['data']['request_path']
    paper_inspect=run(['vpwiki','capture','inspect','--prepared',paper_prepared,
        '--operation-id','vertical-paper-1-capture','--upstream-root',ROOT/'vendor/claude-obsidian',
        '--vault-root',vault])['data']
    code_plan=run(['vpwiki','code-map','plan','--request',fixture/'code.request.json'])['data']
    code_prepared=run(['vpwiki','code-map','prepare','--plan',code_plan['plan_path'],
        '--approval-ref',fixture/'code.runtime-approval.json','--source-path','train.py'])['data']['request_path']
    code_inspect=run(['vpwiki','code-map','inspect','--prepared',code_prepared,
        '--operation-id','vertical-code-capture','--upstream-root',ROOT/'vendor/claude-obsidian',
        '--vault-root',vault])['data']
    audit=run(['vpwiki','audit','--vault-root',vault,'--upstream-root',ROOT/'vendor/claude-obsidian'])
    query=run(['vpwiki','query','--json','--text','synthetic evidence','--vault-root',vault,
        '--upstream-root',ROOT/'vendor/claude-obsidian','--config',evidence['restore_config_path']])
    stale=base/'stale-vault';shutil.copytree(vault,stale)
    stale_index=stale/'.vault-meta/bm25/index.json'
    stale_index.write_bytes(stale_index.read_bytes()+b' ')
    work=checkout/'.work';work.mkdir(exist_ok=True)
    stale_before=_tree_snapshot(stale);work_before=_tree_snapshot(work);tmp_before=_tree_snapshot(private_tmp);stale_results=[]
    for action in ('status','query'):
        argv=(['vpwiki','index','status'] if action=='status' else
              ['vpwiki','query','--json','--text','synthetic evidence'])
        argv += ['--vault-root',stale,'--upstream-root',ROOT/'vendor/claude-obsidian',
                 '--config',evidence['restore_config_path']]
        result=subprocess.run([str(x) for x in argv],cwd=checkout,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
        payload=json.loads(result.stdout)
        assert result.stdout==json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
        assert result.stdout.count('\n')==1 and result.stderr==''
        if action=='status':
            assert result.returncode==0 and payload['data']['state']=='stale' and payload['data']['reasons'],(
                argv,result.returncode,result.stdout,result.stderr)
        else:
            assert result.returncode==2 and payload['error']['code']=='CATALOG_STALE',(
                argv,result.returncode,result.stdout,result.stderr)
        stale_results.append({'argv':argv,'payload':payload,'returncode':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr})
    policy_verdicts={
        'no_admin':'SKILL_POLICY_INVALID' if sentinels['vpwiki-admin'].exists() else 'compliant',
        'no_egress':'SKILL_POLICY_INVALID' if any(sentinels[name].exists() for name in ('curl','wget')) else 'compliant',
        'no_vault_write':'SKILL_POLICY_INVALID' if before!=_tree_snapshot(vault) else 'compliant',
    }
    expected_paper=evidence['captures'][0];expected_code=evidence['code_capture']
    semantic={
        'seed':seed['data']=={'valid':True,'paper_count':67},
        'paper_plan':paper_plan['plan']['plan_kind']=='paper-source' and Path(paper_plan['plan_path']).is_file(),
        'paper_prepared':Path(paper_prepared).is_file() and str(Path(paper_prepared)).startswith(str(checkout/'.work/')),
        'paper_reuse':paper_inspect['disposition']=='reuse' and
            paper_inspect['inspection']['stored_path']==expected_paper['stored_path'],
        'code_plan':code_plan['plan']['plan_kind']=='code-evidence' and Path(code_plan['plan_path']).is_file(),
        'code_prepared':Path(code_prepared).is_file() and str(Path(code_prepared)).startswith(str(checkout/'.work/')),
        'code_reuse':code_inspect['disposition']=='reuse' and
            code_inspect['manifest']['capture']['stored_path']==expected_code['stored_path'] and
            code_inspect['manifest']['origin']['path']=='train.py',
        'audit':audit['data']['domain']['valid'] is True and audit['data']['domain']['orphans']==[] and
            audit['data']['strict_lint']['exit_code']==0,
        'query':bool(query['data']['raw_hits']) and bool(query['data']['ranking']['top10']) and
            all(query['data'][key]==evidence['rebuild']['status'][key] for key in
                ('join_generation_sha256','mapping_sha256','retrieval_config_sha256','catalog_generation_sha256')),
    }
    return {'results':results,'audit':audit,'query':query,'before':before,'after':_tree_snapshot(vault),
        'sentinels':sentinels,'checkout':checkout,'stale_results':stale_results,
        'stale_before':stale_before,'stale_after':_tree_snapshot(stale),'policy_verdicts':policy_verdicts,
        'work_before':work_before,'work_after':_tree_snapshot(work),'tmp_before':tmp_before,'tmp_after':_tree_snapshot(private_tmp),
        'semantic':semantic,'origin':origin,'environment':env}

def test_skills_fresh_path(installed_skill_evidence):
    assert len(installed_skill_evidence['results'])==9
    assert all(payload['ok'] is True for _argv,payload in installed_skill_evidence['results'])
    assert all(installed_skill_evidence['semantic'].values())
    assert 'PYTHONPATH' not in installed_skill_evidence['environment']
    assert 'VIRTUAL_ENV' not in installed_skill_evidence['environment']
    assert str(ROOT/'src') not in installed_skill_evidence['origin']

def test_skills_no_admin(installed_skill_evidence):
    assert installed_skill_evidence['policy_verdicts']['no_admin']=='compliant'
    assert not installed_skill_evidence['sentinels']['vpwiki-admin'].exists()
    for path in SKILLS.glob('video-paper-*/SKILL.md'):
        for line in path.read_text().splitlines():
            if 'vpwiki-admin' in line:
                lowered=line.lower();assert 'show `' in lowered and ('never' in lowered or 'do not' in lowered)

def test_skills_no_egress(installed_skill_evidence):
    assert installed_skill_evidence['policy_verdicts']['no_egress']=='compliant'
    assert all(not installed_skill_evidence['sentinels'][name].exists() for name in ('curl','wget'))
    for path in SKILLS.glob('video-paper-*/SKILL.md'):
        lowered=path.read_text().lower()
        assert all(token not in lowered for token in ('curl ','wget ','http://','https://'))

def test_skills_no_vault_write(installed_skill_evidence):
    assert installed_skill_evidence['policy_verdicts']['no_vault_write']=='compliant'
    assert installed_skill_evidence['before']==installed_skill_evidence['after']

def test_skills_stale_report(installed_skill_evidence):
    assert installed_skill_evidence['audit']['data']['domain']['valid'] is True
    assert installed_skill_evidence['query']['data']['ranking']['top10']
    query=(SKILLS/'video-paper-query/SKILL.md').read_text();audit=(SKILLS/'video-paper-audit/SKILL.md').read_text()
    assert 'vpwiki-admin catalog build' in query and 'Do not run it' in query
    assert 'vpwiki-admin backup restore --archive' in audit and 'Do not execute' in audit
    status,query=installed_skill_evidence['stale_results']
    assert status['returncode']==0 and status['payload']['data']['state']=='stale' and status['payload']['data']['reasons']
    assert status['payload']['data']['reasons']==sorted(status['payload']['data']['reasons'])
    assert query['returncode']==2 and query['payload']['error']['code']=='CATALOG_STALE'
    assert installed_skill_evidence['stale_before']==installed_skill_evidence['stale_after']
    assert installed_skill_evidence['work_before']==installed_skill_evidence['work_after']
    assert installed_skill_evidence['tmp_before']==installed_skill_evidence['tmp_after']
    assert not installed_skill_evidence['sentinels']['vpwiki-admin'].exists()

def test_prospective_wheel_skill_phase(installed_skill_evidence):
    commands=[argv[1:3] for argv,_payload in installed_skill_evidence['results']]
    assert ['ingest','plan'] in commands and ['ingest','prepare'] in commands
    assert ['code-map','plan'] in commands and ['code-map','prepare'] in commands
    assert any(argv[1]=='audit' for argv,_payload in installed_skill_evidence['results'])
    assert any(argv[1]=='query' for argv,_payload in installed_skill_evidence['results'])
    assert installed_skill_evidence['before']==installed_skill_evidence['after']
    assert all(installed_skill_evidence['semantic'].values())
    assert all(not path.exists() for path in installed_skill_evidence['sentinels'].values())
