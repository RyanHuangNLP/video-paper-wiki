from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
