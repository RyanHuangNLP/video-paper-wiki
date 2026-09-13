"""Synthetic history and source inventory tests; no real operator authority."""
from __future__ import annotations

import copy
import json

import pytest

from tests.source_semantics_fixture import (
    inventory_arguments, observed_source, registration_material, reseal_receipts,
    selection, source_fixture,
)
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.source_registration import historical_source_ledger, registration_proof
from video_paper_wiki.source_semantics_contracts import association_id, association_reference, sha
from video_paper_wiki.source_versions import (
    associate_source, association_inventory, derive_display_heads, validate_source_inventory,
)


def test_unknown_reuse_preserves_complete_observation_and_never_selects():
    a, raw, authority = source_fixture()
    before = copy.deepcopy((a, authority))
    result = associate_source(a["observation"], raw_bytes=raw, existing=[a], **authority)
    assert result == {"state": "reused", "association": a}
    assert result["association"] is not a
    assert a["version"] == {"kind": "unknown", "label": None}
    assert derive_display_heads([a], [])["heads"] == []
    assert (a, authority) == before


@pytest.mark.parametrize("field,value", [("title", "Changed observed title"), ("source_metadata_sha256", "c" * 64), ("original_pdf_sha256", "d" * 64)])
def test_same_bytes_changed_provenance_is_explicit_variant(field, value):
    a, raw, authority = source_fixture(label="draft")
    observation = copy.deepcopy(a["observation"])
    observation[field] = value
    with pytest.raises(ContractError) as caught:
        associate_source(observation, raw_bytes=raw, existing=[a], **authority)
    assert (caught.value.code, caught.value.exit_code) == ("SOURCE_PROVENANCE_VARIANT", 75)
    assert caught.value.details["prior_association"] == association_reference(a)
    assert caught.value.details["proposed_observation_sha256"] == sha(canonicalize(observation))


def test_declared_label_conflict_and_distinct_same_byte_versions():
    a, raw, authority = source_fixture(label="v1")
    observation = copy.deepcopy(a["observation"])
    observation["version"]["label"] = "v2"
    b = associate_source(observation, raw_bytes=raw, existing=[a], **authority)["association"]
    assert a["source_id"] == b["source_id"] and a["association_id"] != b["association_id"]
    assert a["extraction"] != b["extraction"]
    assert len(validate_source_inventory([b, a], **inventory_arguments([a, b], raw, authority))) == 2
    changed, different = observed_source(label="v1", text="Other exact bytes.")
    with pytest.raises(ContractError) as caught:
        associate_source(changed, raw_bytes=different, existing=[a], **registration_material(changed))
    assert (caught.value.code, caught.value.exit_code) == ("SOURCE_VERSION_CONFLICT", 75)


@pytest.mark.parametrize("case", ["duplicate", "duplicate_key", "foreign_owner", "raw_path", "source_id", "extraction"])
def test_association_conflicts_and_cross_field_binding(case):
    a, _, _ = source_fixture()
    b = copy.deepcopy(a)
    if case == "duplicate_key":
        b["observation"]["title"] = "Another observation"
        from video_paper_wiki.source_semantics_contracts import extraction_descriptor
        b["extraction"] = extraction_descriptor(b["observation"])
    elif case == "foreign_owner":
        b["paper_id"] = b["observation"]["paper_id"] = "arxiv:2311.15127"
        from video_paper_wiki.source_semantics_contracts import extraction_descriptor
        b["extraction"] = extraction_descriptor(b["observation"])
    elif case == "raw_path":
        b["raw"]["path"] = ".raw/captured/" + "0" * 64 + ".md"
    elif case == "source_id":
        b["source_id"] = "src-" + "0" * 20
    elif case == "extraction":
        b["extraction"]["sha256"] = "0" * 64
    b["association_id"] = association_id(b)
    with pytest.raises(ContractError) as caught:
        association_inventory([a, b])
    assert caught.value.code == "SOURCE_ASSOCIATION_INVALID"


@pytest.mark.parametrize("key", ["raw_sources", "extraction_artifacts", "registration_ledgers"])
@pytest.mark.parametrize("case", ["missing", "orphan", "wrong_type", "wrong_bytes"])
def test_source_material_exact_sets_and_bytes(key, case):
    a, raw, authority = source_fixture()
    kwargs = inventory_arguments([a], raw, authority)
    target = kwargs[key]
    path = next(iter(target))
    if case == "missing":
        target.pop(path)
    elif case == "orphan":
        target["extra"] = b"{}"
    elif case == "wrong_type":
        target[path] = bytearray(target[path])
    else:
        target[path] += b"\n"
    with pytest.raises(ContractError) as caught:
        validate_source_inventory([a], **kwargs)
    assert type(caught.value.details["instance_pointer"]) is str


@pytest.mark.parametrize("bad", [[], None, {1: b"x"}, {"x": bytearray(b"x")}])
def test_empty_inventory_still_validates_all_material_types(bad):
    with pytest.raises(ContractError) as caught:
        validate_source_inventory([], raw_sources={}, extraction_artifacts={}, registration_ledgers={}, head_bytes=None, receipt_bytes=bad)
    assert caught.value.code == "SOURCE_INVENTORY_INVALID"


@pytest.mark.parametrize("case", ["head_whitespace", "receipt_whitespace", "wrong_head_hash", "wrong_intent", "orphan", "missing", "huge_sequence", "wrong_filename", "write_raw", "earlier_non_ingest"])
def test_registration_requires_complete_canonical_first_ingest_proof(case):
    a, _, kwargs = source_fixture()
    kwargs = copy.deepcopy(kwargs)
    path = next(iter(kwargs["receipt_bytes"]))
    receipt = json.loads(kwargs["receipt_bytes"][path])
    if case == "head_whitespace":
        kwargs["head_bytes"] += b"\n"
    elif case == "receipt_whitespace":
        kwargs["receipt_bytes"][path] += b"\n"
    elif case in {"wrong_head_hash", "huge_sequence"}:
        head = json.loads(kwargs["head_bytes"])
        head["receipt_sha256" if case == "wrong_head_hash" else "sequence"] = "0" * 64 if case == "wrong_head_hash" else 8193
        if case == "huge_sequence":
            head["receipt_path"] = "wiki/meta/operations/000000008193-synthetic-registration.json"
        kwargs["head_bytes"] = canonicalize(head)
    elif case == "wrong_intent":
        receipt["intent_sha256"] = "0" * 64
        kwargs["receipt_bytes"][path] = canonicalize(receipt)
    elif case == "missing":
        kwargs["receipt_bytes"] = {}
    elif case == "orphan":
        kwargs["receipt_bytes"]["wiki/meta/operations/000000000001-orphan.json"] = kwargs["receipt_bytes"][path]
    elif case == "wrong_filename":
        kwargs["receipt_bytes"][path + "\n"] = kwargs["receipt_bytes"].pop(path)
    elif case == "write_raw":
        receipt["writes"].append({"path": a["raw"]["path"], "mode": "replace", "before_sha256": a["raw"]["sha256"], "after_sha256": a["raw"]["sha256"]})
        kwargs["head_bytes"], kwargs["receipt_bytes"] = reseal_receipts([receipt])
    else:
        receipt["operation_type"] = "generic"
        kwargs["head_bytes"], kwargs["receipt_bytes"] = reseal_receipts([receipt])
    with pytest.raises(ContractError) as caught:
        registration_proof(a["raw"], a["source_id"], **kwargs)
    assert caught.value.code == ("SOURCE_SEMANTICS_LIMIT" if case == "huge_sequence" else "SOURCE_REGISTRATION_INVALID")


@pytest.mark.parametrize("field,value", [("generated_at", "2026-02-30T00:00:00Z"), ("authority", "official"), ("origin", {"kind": "file", "locator": "../bad"}), ("pages", ["wiki/a/../x.md"]), ("ingested_at", "2026-09-31"), ("extra", True)])
def test_historical_ledger_binds_closed_fields_and_real_dates(field, value):
    a, _, kwargs = source_fixture()
    ledger = json.loads(kwargs["ledger_bytes"])
    if field == "generated_at":
        ledger[field] = value
    else:
        ledger["sources"][a["source_id"]][field] = value
    kwargs["ledger_bytes"] = canonicalize(ledger)
    receipt = json.loads(next(iter(kwargs["receipt_bytes"].values())))
    receipt["writes"][0]["after_sha256"] = sha(kwargs["ledger_bytes"])
    kwargs["head_bytes"], kwargs["receipt_bytes"] = reseal_receipts([receipt])
    with pytest.raises(ContractError) as caught:
        registration_proof(a["raw"], a["source_id"], **kwargs)
    assert caught.value.code == "SOURCE_REGISTRATION_INVALID"


def test_exact_noncanonical_historical_ledger_is_allowed_but_not_substituted():
    a, _, kwargs = source_fixture()
    pretty = json.dumps(json.loads(kwargs["ledger_bytes"]), indent=2).encode()
    assert historical_source_ledger(pretty) == json.loads(kwargs["ledger_bytes"])
    with pytest.raises(ContractError):
        registration_proof(a["raw"], a["source_id"], **(kwargs | {"ledger_bytes": pretty}))


def test_later_ledger_update_cannot_replace_the_first_historical_snapshot():
    a, _, kwargs = source_fixture()
    first = json.loads(next(iter(kwargs["receipt_bytes"].values())))
    ledger = json.loads(kwargs["ledger_bytes"])
    ledger["sources"][a["source_id"]]["title"] = "Later synthetic metadata"
    later_bytes = canonicalize(ledger)
    second = {"schema": first["schema"], "operation_id": "later-metadata", "operation_type": "generic",
              "writes": [{"path": "wiki/meta/ledgers/source-ledger.json", "mode": "replace",
                          "before_sha256": sha(kwargs["ledger_bytes"]), "after_sha256": sha(later_bytes)}], "claimed_inputs": []}
    kwargs["head_bytes"], kwargs["receipt_bytes"] = reseal_receipts([first, second])
    assert registration_proof(a["raw"], a["source_id"], **kwargs) == a["registration"]
    with pytest.raises(ContractError) as caught:
        registration_proof(a["raw"], a["source_id"], **(kwargs | {"ledger_bytes": later_bytes}))
    assert caught.value.code == "SOURCE_REGISTRATION_INVALID"


@pytest.mark.parametrize("case", ["replace_unknown", "duplicate_claim", "duplicate_write", "claim_hash_change", "earlier_generic_claim"])
def test_full_replay_checks_preconditions_and_first_touch(case):
    a, _, kwargs = source_fixture()
    first = json.loads(next(iter(kwargs["receipt_bytes"].values())))
    receipts = [first]
    if case == "replace_unknown":
        first["writes"][0].update(mode="replace", before_sha256="0" * 64)
    elif case == "duplicate_claim":
        first["claimed_inputs"].append(copy.deepcopy(first["claimed_inputs"][0]))
    elif case == "duplicate_write":
        first["writes"].append(copy.deepcopy(first["writes"][0]))
    else:
        second = copy.deepcopy(first)
        second["operation_id"] = "later-registration"
        second["writes"][0].update(mode="replace", before_sha256=first["writes"][0]["after_sha256"])
        if case == "claim_hash_change":
            second["claimed_inputs"][0]["sha256"] = "0" * 64
        else:
            first["operation_type"] = "generic"
        receipts.append(second)
    kwargs["head_bytes"], kwargs["receipt_bytes"] = reseal_receipts(receipts)
    with pytest.raises(ContractError) as caught:
        registration_proof(a["raw"], a["source_id"], **kwargs)
    assert caught.value.code == "SOURCE_REGISTRATION_INVALID"


def test_display_selection_and_explicit_rollback_are_append_only():
    a, raw, authority = source_fixture()
    observation = copy.deepcopy(a["observation"])
    observation["version"] = {"kind": "declared", "label": "v2"}
    b = associate_source(observation, raw_bytes=raw, existing=[a], **authority)["association"]
    first = selection(a)
    second = selection(b, previous=first)
    rollback = selection(a, previous=second)
    heads = derive_display_heads([b, a], [rollback, first, second])["heads"]
    assert heads == [{"paper_id": a["paper_id"], "decision_id": rollback["decision_id"],
                      "decision_sha256": sha(canonicalize(rollback)), "association": association_reference(a), "sequence": 3}]


@pytest.mark.parametrize("case", ["duplicate", "branch", "missing", "foreign", "backwards", "hash"])
def test_display_chains_reject_ambiguity(case):
    a, _, _ = source_fixture()
    first = selection(a)
    second = selection(a, previous=first, reason="Second synthetic selection.")
    decisions = [first, second]
    if case == "duplicate":
        decisions.append(first)
    elif case == "branch":
        decisions.append(selection(a, previous=first, reason="Competing branch."))
    elif case == "missing":
        decisions = [second]
    elif case == "foreign":
        decisions = [selection(a, paper_id="arxiv:2311.15127")]
    elif case == "backwards":
        decisions[1] = selection(a, previous=first, decided_at="2026-09-08T23:59:59Z")
    else:
        decisions = [selection(a, association={"association_id": a["association_id"], "sha256": "0" * 64})]
    with pytest.raises(ContractError) as caught:
        derive_display_heads([a], decisions)
    assert caught.value.code == "SOURCE_DISPLAY_INVALID"
