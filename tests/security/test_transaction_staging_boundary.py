from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from video_paper_wiki import transaction_staging as staging
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import CODE_WORK_PATH_UNSAFE, StagingError
from video_paper_wiki.transaction_contracts import transaction_declaration_hash

ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json"


def vector() -> tuple[dict, dict[str, bytes], dict[str, None]]:
    proposal = copy.deepcopy(json.loads(VALID.read_text())["transaction"])
    proposal["phase"] = "proposal"
    proposal["inspection"] = None
    writes = {
        proposal["writes"][0]["path"]: b"{}",
        proposal["writes"][1]["path"]: canonicalize(proposal["receipt"]),
        proposal["writes"][2]["path"]: canonicalize(proposal["head"]),
    }
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    return proposal, writes, {path: None for path in writes}


def test_public_path_attempts_no_process_or_network(
    checkout: Path, network_attempts: list[str],
) -> None:
    proposal, writes, originals = vector()
    staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes={}, batch_id="isolated",
    )
    assert network_attempts == []


def test_bad_input_error_does_not_retain_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, writes, originals = vector()
    secret = b"private-secret"
    writes[proposal["writes"][0]["path"]] = secret
    monkeypatch.setattr(
        staging, "_stage_transaction_inspect_files",
        lambda **_kwargs: pytest.fail("filesystem touched"),
    )
    with pytest.raises(ContractError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes={}, batch_id="isolated",
        )
    assert secret not in repr(caught.value.details).encode()
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


def test_public_path_refuses_symlink_content_slot(checkout: Path, tmp_path: Path) -> None:
    proposal, writes, originals = vector()
    digest = proposal["writes"][0]["sha256"]
    content = checkout / ".work/unsafe/transaction-inspect/content"
    content.mkdir(parents=True)
    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    content.joinpath(digest).symlink_to(external)
    with pytest.raises(StagingError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes={}, batch_id="unsafe",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert external.read_bytes() == b"unchanged"
    assert not (content.parent / "bundle.json").exists()


@pytest.mark.parametrize("slot", ["transport-file", "content-file", "payload-fifo", "bundle-directory"])
def test_public_path_refuses_fixed_layout_file_directory_and_special_slots(
    checkout: Path,
    slot: str,
) -> None:
    proposal, writes, originals = vector()
    transport = checkout / ".work/slots/transaction-inspect"
    if slot == "transport-file":
        transport.parent.mkdir(parents=True)
        transport.write_bytes(b"not-a-directory")
    elif slot == "content-file":
        transport.mkdir(parents=True)
        transport.joinpath("content").write_bytes(b"not-a-directory")
    elif slot == "payload-fifo":
        transport.joinpath("content").mkdir(parents=True)
        os.mkfifo(transport / "content" / proposal["writes"][0]["sha256"])
    else:
        transport.joinpath("content").mkdir(parents=True)
        transport.joinpath("bundle.json").mkdir()
    with pytest.raises(StagingError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes={}, batch_id="slots",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
