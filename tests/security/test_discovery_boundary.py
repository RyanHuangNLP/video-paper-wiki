from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.research.discovery_fixture import begin, checkout, config, observation, requests, resources_scope, write
from video_paper_wiki_research import discovery
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_contracts import RESOURCE_PATHS
from video_paper_wiki_research.discovery_storage import DiscoveryStore, RetainedTree, checked_path, open_store


@pytest.mark.parametrize('name',['../bad','UPPER','two words','a/b','a'*65,'é'])
def test_session_spelling_cannot_escape(tmp_path,monkeypatch,name):
    root=checkout(tmp_path,monkeypatch)
    with pytest.raises(ResearchError):discovery.status(session=name)
    assert not (root/'.work').exists()


@pytest.mark.parametrize('suffix',['/./input.json','/x/../input.json','//input.json','/input.json\x7f','/e\u0301.json','/input\\file.json'])
def test_external_input_alias_spelling_refused(tmp_path,monkeypatch,suffix):
    root=checkout(tmp_path,monkeypatch)
    with pytest.raises(ResearchError) as caught:
        discovery.init(session='example',config_input=str(root)+suffix)
    assert caught.value.code=='WORK_PATH_UNSAFE'
    assert not (root/'.work').exists()


@pytest.mark.parametrize('kind',['symlink','hardlink','fifo'])
def test_input_must_be_single_link_regular_file(tmp_path,monkeypatch,kind):
    root=checkout(tmp_path,monkeypatch);source=root/'real.json';write(source,config());target=root/'input.json'
    if kind=='symlink':target.symlink_to(source)
    elif kind=='hardlink':os.link(source,target)
    else:os.mkfifo(target)
    with pytest.raises(ResearchError) as caught:discovery.init(session='example',config_input=str(target))
    assert caught.value.code=='WORK_PATH_UNSAFE'
    assert not (root/'.work').exists()


@pytest.mark.parametrize('slot',['.work','.work/research','.work/research/example','.work/research/example/discovery-v1'])
def test_existing_parent_symlinks_are_not_followed(tmp_path,monkeypatch,slot):
    root=checkout(tmp_path,monkeypatch);target=root/slot;target.parent.mkdir(parents=True,exist_ok=True)
    outside=tmp_path/'outside';outside.mkdir();target.symlink_to(outside,target_is_directory=True)
    before=list(outside.iterdir())
    with pytest.raises(ResearchError) as caught:discovery.status(session='example')
    assert caught.value.code=='WORK_PATH_UNSAFE' and list(outside.iterdir())==before


@pytest.mark.parametrize('entry',['unknown.txt','bad.json','0'*64+'.json'])
def test_unknown_or_unsafe_family_entries_refuse(tmp_path,monkeypatch,entry):
    root=checkout(tmp_path,monkeypatch);begin(root)
    family=root/'.work/research/example/discovery-v1/observations';outside=root/'outside';outside.write_text('unrelated')
    target=family/entry;target.symlink_to(outside)
    with pytest.raises(ResearchError) as caught:discovery.status(session='example')
    assert caught.value.code=='WORK_PATH_UNSAFE'
    assert outside.read_text()=='unrelated'


@pytest.mark.parametrize('failure',[False,True])
@pytest.mark.parametrize('surface',['input','checkout','work','family','resource'])
def test_all_exits_retain_bytes_named_edges_and_resources(tmp_path,monkeypatch,failure,surface):
    root=checkout(tmp_path,monkeypatch);configuration=config();input_path=root/'config.json'
    discovery.init(session='example',config_input=write(input_path,configuration))
    package=tmp_path/'resources';package.mkdir()
    from importlib import resources
    real_package=resources.files('video_paper_wiki_research')
    for name in RESOURCE_PATHS:
        path=package/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(real_package.joinpath(name).read_bytes())
    import video_paper_wiki_research.discovery_storage as storage
    monkeypatch.setattr(storage.resources,'files',lambda name:package)
    original=discovery.normalize_config
    def change(value):
        if surface=='input':input_path.write_bytes(input_path.read_bytes()+b' ')
        elif surface=='resource':
            p=package/'prompts/discovery-assessment-v1.md';p.write_bytes(p.read_bytes()+b'changed')
        else:
            path=root if surface=='checkout' else root/'.work' if surface=='work' else root/'.work/research/example/discovery-v1/metadata'
            path.rename(path.with_name(path.name+'-retired'));path.mkdir()
        if failure:raise ResearchError('DISCOVERY_INPUT_INVALID','synthetic semantic failure')
        return original(value)
    monkeypatch.setattr(discovery,'normalize_config',change)
    with pytest.raises(ResearchError) as caught:discovery.init(session='example',config_input=str(input_path))
    assert caught.value.code=='WORK_PATH_UNSAFE'


@pytest.mark.parametrize('same_bytes',[False,True])
def test_foreign_first_absence_target_is_never_adopted(tmp_path,monkeypatch,same_bytes):
    root=checkout(tmp_path,monkeypatch)
    import video_paper_wiki_research.discovery_storage as storage
    original=storage._atomic_install
    def race(work_fd,parent_fd,filename,data,**kwargs):
        fd=os.open(filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=parent_fd)
        try:os.write(fd,data if same_bytes else b'foreign')
        finally:os.close(fd)
        return original(work_fd,parent_fd,filename,data,**kwargs)
    monkeypatch.setattr(storage,'_atomic_install',race)
    with pytest.raises(ResearchError) as caught:discovery.init(session='example',config_input=write(root/'c.json',config()))
    assert caught.value.code=='WORK_PATH_UNSAFE'


def test_nonblocking_directory_lock_precedes_store_scan_and_is_released(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch)
    source=Path(__file__).resolve().parents[2]/'src'
    code="from video_paper_wiki_research.discovery import status\nfrom video_paper_wiki_research.contracts import ResearchError\ntry:\n print(status(session='example')['base_state'])\nexcept ResearchError as e:\n print(e.code)\n"
    env={**os.environ,'PYTHONPATH':str(source)}
    with open_store('example'):
        result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,check=True)
        assert result.stdout.strip()=='DISCOVERY_BUSY' and not result.stderr
        assert not (root/'.work').exists()
    after=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,check=True)
    assert after.stdout.strip()=='absent' and not (root/'.work').exists()


def test_cli_workflow_has_no_network_subprocess_or_vault_write(tmp_path,monkeypatch):
    root=checkout(tmp_path,monkeypatch);vault=root/'real-vault';vault.mkdir();sentinel=vault/'protected.md';sentinel.write_text('preserve')
    def forbidden(*args,**kwargs):raise AssertionError('discovery attempted external execution')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    begin(root,configuration=config(per_round_requests=1));r=requests()[0]
    discovery.observe(session='example',request=r['id'],observation_input=write(root/'o.json',observation(r,outcome='capability_unavailable')))
    assert discovery.context(session='example')['assessment_context']['operation_health'][0]['outcome']=='capability_unavailable'
    assert sentinel.read_text()=='preserve' and list(vault.iterdir())==[sentinel]
