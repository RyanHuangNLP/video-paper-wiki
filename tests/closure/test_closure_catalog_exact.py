from __future__ import annotations

import os

import pytest

from tests.unit.test_catalog_store import material
from video_paper_wiki import catalog_store as module
from video_paper_wiki.contracts import ContractError


def test_public_catalog_reader_db_replace(monkeypatch,tmp_path):
    vault=tmp_path/'vault';(vault/'.vault-meta').mkdir(parents=True);value=material();db=vault/'.vault-meta/catalog.sqlite'
    module.build_catalog_database(db,value)
    monkeypatch.setattr(module,'verify_upstream',lambda _root:tmp_path/'upstream')
    def barrier(phase):
        assert phase=='before-reader-recheck';replacement=db.with_name('replacement.sqlite');replacement.write_bytes(db.read_bytes());os.replace(replacement,db)
    with pytest.raises(ContractError) as caught:
        module.catalog_status(vault,tmp_path/'upstream',value['config'],_collector=lambda **_kw:value,barrier=barrier)
    assert caught.value.code=='CATALOG_STALE'


def test_catalog_writer_lock_race(monkeypatch,tmp_path):
    vault=tmp_path/'vault';(vault/'.vault-meta').mkdir(parents=True)
    monkeypatch.setattr(module,'verify_upstream',lambda _root:tmp_path/'upstream')
    monkeypatch.setattr(module,'_config',lambda _value,**_kw:({},b''))
    monkeypatch.setattr(module,'_run_builders',lambda *_a,**_kw:None)
    monkeypatch.setattr(module,'build_catalog_database',lambda *_a,**_kw:{'ok':True})
    def fault(phase):
        if phase=='after-lock-tombstone':(vault/'.vault-meta/locks/catalog-build.lock').write_bytes(b'foreign')
    with pytest.raises(ContractError) as caught:
        module.build_current_catalog(vault_root=vault,upstream_root='pin',retrieval_config={},_collector=lambda **_kw:{},fault=fault)
    assert caught.value.code=='CATALOG_BUILD_RACE'
    assert (vault/'.vault-meta/locks/catalog-build.lock').read_bytes()==b'foreign'
