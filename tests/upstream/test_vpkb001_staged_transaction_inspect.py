from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.upstream import test_vpkb001_transaction_inspect as accepted
from tests.upstream._transaction_staging_fixture import prepare, transport_paths, vault_snapshot
from video_paper_wiki.transaction_staging import stage_transaction_inspect_transport
from video_paper_wiki.upstream_adapter import inspect_pinned_transaction


@pytest.mark.parametrize("kind", ["capture", "generic", "later-generic", "ingest"])
def test_staged_transport_is_consumed_by_real_pinned_public_inspect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    proposal, supplied, originals, reads, checkout, vault, state = prepare(
        tmp_path, monkeypatch, kind,
    )
    work, bundle = transport_paths(checkout)
    authority = inspect_pinned_transaction(
        proposal,
        upstream_root=accepted.UPSTREAM,
        work_root=work,
        vault_root=vault,
        bundle_path=bundle,
    )
    assert vault_snapshot(vault) == state["before"]
    assert authority["transaction"]["phase"] == "inspected"
    assert authority["transport"]["bundle_sha256"] == proposal["input_bundle_sha256"]
    assert authority["transport"]["bundle_size_bytes"] == bundle.stat().st_size
    observed = {
        (item["sha256"], item["size_bytes"])
        for item in authority["transport"]["content_files"]
    }
    staged_files = {
        (item["sha256"], item["size_bytes"])
        for item in state["staged"]["content_files"]
    }
    assert observed == staged_files
    second = stage_transaction_inspect_transport(
        copy.deepcopy(proposal), write_bytes=dict(supplied),
        original_bytes=dict(originals), read_bytes=dict(reads),
        batch_id="staged-inspect",
    )
    assert second["already_staged"] is True
