from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import make_checkout
from tests.upstream._transaction_fixture import Runner, init
from video_paper_wiki.publication import inspect_publication, stage_publication_request
from video_paper_wiki.receipt_audit import audit_integrity


def _apply(root: Path, vault: Path, authority: dict, upstream: Path) -> None:
    bundle = Path(authority["transaction_staging"]["bundle_file"])
    if not bundle.is_absolute():
        bundle = root / ".work" / authority["request"]["batch_id"] / bundle
    subprocess.run([sys.executable,"-I","-B","-X","utf8",str(upstream/"scripts/claude-obsidian.py"),
        "transaction","apply",str(bundle),"--vault",str(vault),"--approved-plan-sha256",
        authority["transaction"]["inspection"]["approval_sha256"]],check=True,capture_output=True,text=True)


def test_pristine_genesis_successor_and_receipt_audit(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]; upstream = repo / "vendor/claude-obsidian"
    checkout = tmp_path / "checkout"; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    runner_root=tmp_path/"runner";runner_root.mkdir();runner = Runner(runner_root); vault = tmp_path / "vault"; init(runner,vault,"publication-init")
    ledgers=["wiki/meta/ledgers/claim-ledger.json","wiki/meta/ledgers/source-ledger.json"]
    first=stage_publication_request(batch_id="publication-one",operation_id="publication-one",operation_type="generic",
        payloads={"wiki/meta/records/publication-one.json":b'{"fixture":1}'},claimed_input_paths=ledgers)
    authority=inspect_publication(prepared=first["request_path"],operation_id="publication-one",upstream_root=upstream,vault_root=vault)
    _apply(checkout,vault,authority,upstream)
    report=audit_integrity(vault);assert report["head"]["sequence"]==1
    second=stage_publication_request(batch_id="publication-two",operation_id="publication-two",operation_type="generic",
        payloads={"wiki/meta/records/publication-two.json":b'{"fixture":2}'})
    successor=inspect_publication(prepared=second["request_path"],operation_id="publication-two",upstream_root=upstream,vault_root=vault)
    _apply(checkout,vault,successor,upstream)
    report=audit_integrity(vault)
    assert report["head"]["sequence"]==2 and len(report["receipts"])==2


def test_inspect_accepts_finite_float_derived_document_json(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]; upstream = repo / "vendor/claude-obsidian"
    checkout = tmp_path / "checkout"; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    runner_root=tmp_path/"runner";runner_root.mkdir();runner = Runner(runner_root); vault = tmp_path / "vault"; init(runner,vault,"float-doc-init")
    ledgers=["wiki/meta/ledgers/claim-ledger.json","wiki/meta/ledgers/source-ledger.json"]
    first=stage_publication_request(batch_id="float-genesis",operation_id="float-genesis",operation_type="generic",
        payloads={"wiki/meta/records/float-genesis.json":b'{"fixture":1}'},claimed_input_paths=ledgers)
    authority=inspect_publication(prepared=first["request_path"],operation_id="float-genesis",upstream_root=upstream,vault_root=vault)
    _apply(checkout,vault,authority,upstream)
    pdf_sha="a"*64; fingerprint="b"*64
    derived=f".raw/derived/{pdf_sha}/docling/{fingerprint}/document.json"
    document=b'{"texts":[{"text":"x","prov":[{"bbox":{"l":0.5,"t":1.25,"r":10.0,"b":20.5}}]}],"ok":true}\n'
    staged=stage_publication_request(batch_id="float-document",operation_id="float-document",operation_type="ingest",
        payloads={derived:document})
    inspected=inspect_publication(prepared=staged["request_path"],operation_id="float-document",upstream_root=upstream,vault_root=vault)
    assert inspected["transaction"]["phase"]=="inspected"
    from video_paper_wiki.secure_io import parse_strict_json
    with pytest.raises(Exception) as caught:
        parse_strict_json(b'{"schema":"video-paper-wiki.operation-receipt.v1","n":1.5}',invalid_code="SCHEMA_INVALID")
    assert caught.value.code=="SCHEMA_INVALID"
