from __future__ import annotations

import copy, sqlite3

import pytest

from video_paper_wiki.catalog_reporting import catalog_report
from video_paper_wiki.catalog_store import DB_RELATIVE, build_catalog_database
from video_paper_wiki.contracts import ContractError
from tests.unit.test_catalog_store import material

def _built(tmp_path,monkeypatch):
    value=material();vault=tmp_path/'v';path=vault/DB_RELATIVE;path.parent.mkdir(parents=True);build_catalog_database(path,value)
    monkeypatch.setattr('video_paper_wiki.catalog_store.verify_upstream',lambda root:root)
    monkeypatch.setattr('video_paper_wiki.catalog_collector.collect_current_catalog_material',lambda **_kw:value)
    return value,vault

@pytest.mark.parametrize('kind', ['code-openness','paper-lifecycle','evidence-coverage'])
def test_reports_are_closed_and_deterministic(tmp_path,monkeypatch,kind):
    value,vault=_built(tmp_path,monkeypatch)
    first=catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind=kind)
    second=catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind=kind)
    assert first==second and first['report_kind']==kind and first['catalog_state']=='current'
    assert [x['paper_id'] for x in first['rows']]==['arxiv:2311.15127']

def test_filter_hit_and_miss(tmp_path,monkeypatch):
    value,vault=_built(tmp_path,monkeypatch)
    hit=catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind='paper-lifecycle',paper_id='arxiv:2311.15127')
    miss=catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind='paper-lifecycle',paper_id='arxiv:0001.00001')
    assert len(hit['rows'])==1 and miss['rows']==[]

def test_report_rejects_stale_config_and_bad_kind(tmp_path,monkeypatch):
    value,vault=_built(tmp_path,monkeypatch);bad=copy.deepcopy(value['config']);bad['query_version']='changed'
    with pytest.raises(ContractError) as exc:catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=bad,report_kind='code-openness')
    assert exc.value.code=='CATALOG_STALE'
    with pytest.raises(ContractError) as exc:catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind='other')
    assert exc.value.code=='CATALOG_REPORT_INVALID'

def test_report_detects_cross_table_corruption(tmp_path,monkeypatch):
    value,vault=_built(tmp_path,monkeypatch);path=vault/DB_RELATIVE
    con=sqlite3.connect(path);con.execute('pragma foreign_keys=off');con.execute("update papers set title='' ");con.commit();con.close()
    with pytest.raises(ContractError) as exc:catalog_report(vault_root=vault,upstream_root='pin',retrieval_config=value['config'],report_kind='paper-lifecycle')
    assert exc.value.code=='CATALOG_STALE'
