from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from video_paper_wiki import transaction_staging as staging
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.staging import StagingError
from video_paper_wiki.transaction_contracts import transaction_declaration_hash
from video_paper_wiki.upstream_adapter import _compact_bundle_bytes as adapter_bundle_bytes

ROOT = Path(__file__).resolve().parents[2]
VALID = ROOT / "tests/fixtures/contracts/valid/video-paper-wiki.upstream-authority.v1.json"


def proposal_and_bytes() -> tuple[dict, dict[str, bytes], dict[str, bytes | None], dict[str, bytes | None]]:
    proposal = copy.deepcopy(json.loads(VALID.read_text())["transaction"])
    proposal["phase"] = "proposal"
    proposal["inspection"] = None
    proposal["runtime_result"] = None
    writes = {
        proposal["writes"][0]["path"]: b"{}",
        proposal["writes"][1]["path"]: canonicalize(proposal["receipt"]),
        proposal["writes"][2]["path"]: canonicalize(proposal["head"]),
    }
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    originals = {path: None for path in writes}
    return proposal, writes, originals, {}


def test_stage_exact_transport_then_reuse(checkout: Path) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    first = staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes=reads, batch_id="stage-1",
    )
    second = staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes=reads, batch_id="stage-1",
    )
    assert first["already_staged"] is False
    assert second["already_staged"] is True
    directory = checkout / ".work/stage-1/transaction-inspect"
    raw = directory.joinpath("bundle.json").read_bytes()
    assert raw == adapter_bundle_bytes(proposal, code="unused")
    assert not raw.startswith(b"\xef\xbb\xbf") and not raw.endswith(b"\n")
    assert first["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert [item["sha256"] for item in first["content_files"]] == sorted(
        {write["sha256"] for write in proposal["writes"]}
    )


def test_partial_exact_repair_is_not_full_reuse(checkout: Path) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    first_write = proposal["writes"][0]
    content = checkout / ".work/repair/transaction-inspect/content"
    content.mkdir(parents=True)
    content.joinpath(first_write["sha256"]).write_bytes(writes[first_write["path"]])
    result = staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes=reads, batch_id="repair",
    )
    assert result["already_staged"] is False
    assert (content.parent / "bundle.json").is_file()


def test_all_pure_checks_precede_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    proposal["phase"] = "inspected"
    proposal["inspection"] = copy.deepcopy(
        json.loads(VALID.read_text())["transaction"]["inspection"]
    )
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    touched = False

    def touch(*_args, **_kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("filesystem touched")

    monkeypatch.setattr(staging, "_stage_transaction_inspect_files", touch)
    with pytest.raises(ContractError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="pure",
        )
    assert caught.value.code == "TRANSACTION_UPSTREAM_MISMATCH"
    assert not touched


@pytest.mark.parametrize("value", [bytearray(b"{}"), b"wrong"])
def test_exact_bytes_are_required_before_filesystem(
    monkeypatch: pytest.MonkeyPatch, value: object,
) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    writes[proposal["writes"][0]["path"]] = value  # type: ignore[assignment]
    monkeypatch.setattr(
        staging, "_stage_transaction_inspect_files",
        lambda **_kwargs: pytest.fail("filesystem touched"),
    )
    with pytest.raises(ContractError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="pure",
        )
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


@pytest.mark.parametrize("which", ["write-subclass", "missing-original", "extra-read"])
def test_byte_map_keysets_and_builtin_dicts_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    which: str,
) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()

    class DictSubclass(dict):
        pass

    if which == "write-subclass":
        writes = DictSubclass(writes)
    elif which == "missing-original":
        originals.pop(next(iter(originals)))
    else:
        reads["wiki/meta/extra.json"] = None
    monkeypatch.setattr(
        staging, "_stage_transaction_inspect_files",
        lambda **_kwargs: pytest.fail("filesystem touched"),
    )
    with pytest.raises(ContractError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="pure",
        )
    assert caught.value.code == "TRANSACTION_BYTES_MISMATCH"


def test_invalid_batch_precedes_bundle_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    monkeypatch.setattr(
        staging, "_compact_bundle_bytes",
        lambda _proposal: pytest.fail("bundle encoded"),
    )
    with pytest.raises(StagingError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="bad/segment",
        )
    assert getattr(caught.value, "code", None) == "INVALID_BATCH_ID"


def test_bundle_digest_mismatch_precedes_bundle_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    monkeypatch.setattr(staging, "_compact_bundle_bytes", lambda _proposal: b"x" * (8 * 1024 * 1024 + 1))
    monkeypatch.setattr(
        staging, "_stage_transaction_inspect_files",
        lambda **_kwargs: pytest.fail("filesystem touched"),
    )
    with pytest.raises(ContractError) as caught:
        staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="pure",
        )
    assert caught.value.code == "TRANSACTION_STAGING_MISMATCH"


@pytest.mark.parametrize(
    "size,expected",
    [(8 * 1024 * 1024, None), (8 * 1024 * 1024 + 1, "TRANSACTION_LIMIT_EXCEEDED")],
)
def test_bundle_limit_is_inclusive_and_precedes_filesystem(
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    expected: str | None,
) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    raw = b"x" * size
    proposal["input_bundle_sha256"] = hashlib.sha256(raw).hexdigest()
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    monkeypatch.setattr(staging, "_compact_bundle_bytes", lambda _proposal: raw)
    if expected is None:
        monkeypatch.setattr(
            staging,
            "_stage_transaction_inspect_files",
            lambda **kwargs: type("Result", (), {
                "content_already_staged": tuple(False for _ in kwargs["content"]),
                "bundle_already_staged": False,
            })(),
        )
        result = staging.stage_transaction_inspect_transport(
            proposal, write_bytes=writes, original_bytes=originals,
            read_bytes=reads, batch_id="limit",
        )
        assert result["bundle_size_bytes"] == size
    else:
        monkeypatch.setattr(
            staging, "_stage_transaction_inspect_files",
            lambda **_kwargs: pytest.fail("filesystem touched"),
        )
        with pytest.raises(ContractError) as caught:
            staging.stage_transaction_inspect_transport(
                proposal, write_bytes=writes, original_bytes=originals,
                read_bytes=reads, batch_id="limit",
            )
        assert caught.value.code == expected


def test_result_does_not_share_mutable_input(checkout: Path) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    result = staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes=reads, batch_id="copy",
    )
    proposal["writes"].clear()
    writes.clear()
    assert result["content_files"]


def test_duplicate_payload_is_one_physical_file_but_two_ordered_bundle_writes(
    checkout: Path,
) -> None:
    proposal, writes, originals, reads = proposal_and_bytes()
    first = proposal["writes"][0]
    duplicate_path = "wiki/meta/records/genesisz.json"
    duplicate = copy.deepcopy(first)
    duplicate["path"] = duplicate_path
    proposal["writes"].insert(1, duplicate)
    proposal["expected_hashes"][duplicate_path] = None
    writes[duplicate_path] = writes[first["path"]]
    originals[duplicate_path] = None
    proposal["receipt"]["writes"].append({
        "path": duplicate_path,
        "mode": "create",
        "before_sha256": None,
        "after_sha256": duplicate["sha256"],
    })
    proposal["receipt"]["intent_sha256"] = receipt_intent_sha256(proposal["receipt"])
    receipt_write = next(item for item in proposal["writes"] if item["role"] == "receipt")
    receipt_data = canonicalize(proposal["receipt"])
    receipt_write["sha256"] = hashlib.sha256(receipt_data).hexdigest()
    receipt_write["size_bytes"] = len(receipt_data)
    writes[receipt_write["path"]] = receipt_data
    proposal["head"]["receipt_sha256"] = receipt_write["sha256"]
    head_write = next(item for item in proposal["writes"] if item["role"] == "head")
    head_data = canonicalize(proposal["head"])
    head_write["sha256"] = hashlib.sha256(head_data).hexdigest()
    head_write["size_bytes"] = len(head_data)
    writes[head_write["path"]] = head_data
    raw = json.dumps(
        staging._bundle_value(proposal), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode()
    proposal["input_bundle_sha256"] = hashlib.sha256(raw).hexdigest()
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    result = staging.stage_transaction_inspect_transport(
        proposal, write_bytes=writes, original_bytes=originals,
        read_bytes=reads, batch_id="dedup",
    )
    assert len(result["content_files"]) == len(proposal["writes"]) - 1
    bundle = json.loads(
        (checkout / ".work/dedup/transaction-inspect/bundle.json").read_bytes()
    )
    refs = [item["content_file"] for item in bundle["writes"]]
    expected_ref = "content/" + first["sha256"]
    assert refs.count(expected_ref) == 2
