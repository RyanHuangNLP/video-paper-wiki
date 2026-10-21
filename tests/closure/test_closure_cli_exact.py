from __future__ import annotations

import json

from video_paper_wiki.cli import main


def _usage(argv,capsys):
    assert main(argv)==2;payload=json.loads(capsys.readouterr().out)
    assert payload['ok'] is False and payload['error']['code']=='USAGE'


def test_cli_obsolete_catalog_status(capsys):_usage(['catalog','status'],capsys)

def test_cli_query_mapping_injection(capsys):
    _usage(['query','--json','--text','x','--vault-root','v','--upstream-root','u','--config','c','--mapping','m'],capsys)

def test_cli_report_field(capsys):
    _usage(['catalog','report','--json','--vault-root','v','--upstream-root','u','--config','c','--kind','code-openness','--field','x'],capsys)

def test_cli_agent_build(capsys):
    _usage(['index','build'],capsys);_usage(['catalog','build'],capsys)
