from __future__ import annotations

import json
from collections import OrderedDict

from .paths import FIXTURES, load_json
from .identity import claim_id, event_id, evidence_fingerprint, is_stable_subject_id, nfkc_collapse
from .jcs import canonicalize


def test_jcs_integer_only_reference_behavior() -> None:
    value = {"z": [3, True, None], "a": "solidus/and\ncontrol", "é": 1}
    assert canonicalize(value) == '{"a":"solidus/and\\ncontrol","z":[3,true,null],"é":1}'.encode()
    assert not canonicalize(value).endswith(b"\n")


def test_stable_subject_id_grammar() -> None:
    formulas = load_json(FIXTURES / "identity" / "formulas.json")
    for value in formulas["stable_subject_id"]["valid"]:
        assert is_stable_subject_id(value)
    for value in formulas["stable_subject_id"]["invalid"]:
        assert not is_stable_subject_id(value)
    assert not is_stable_subject_id("repo:github:Stability-AI/generative-models")
    assert formulas["stable_subject_id"]["commit_is_not_part_of_subject"] is True


def test_claim_id_vectors_and_normalization() -> None:
    formulas = load_json(FIXTURES / "identity" / "formulas.json")
    vectors = formulas["claim_id"]["vectors"]
    actual = {vector["name"]: claim_id(vector["subject"], vector["text"]) for vector in vectors}
    assert all(actual[vector["name"]] == vector["expected"] for vector in vectors)
    assert actual["base"] == actual["whitespace_nfkc_equivalent"]
    assert actual["base"] != actual["different_text"]
    assert actual["base"] != actual["different_subject"]
    assert nfkc_collapse("  A\u2003B\tC  ") == "A B C"


def test_claim_id_ignores_locator_changes() -> None:
    subject = "paper:arxiv:2311.15127"
    text = "The model uses a diffusion transformer."
    first = [{"page": 3, "ref": "#/texts/7"}]
    second = [{"page": 99, "ref": "#/texts/800", "artifact_sha256": "changed"}]
    assert claim_id(subject, text, first) == claim_id(subject, text, second)


def test_assessment_event_vector_and_key_order_independence() -> None:
    fixture = load_json(FIXTURES / "identity" / "formulas.json")["assessment_event_id"]
    event = fixture["event"]
    assert event_id(event) == fixture["expected"]
    reversed_event = OrderedDict(reversed(list(event.items())))
    assert event_id(reversed_event) == fixture["expected"]
    with_id = dict(event, event_id="ase-00000000000000000000")
    assert event_id(with_id) == fixture["expected"]


def test_evidence_fingerprint_field_set_and_order_independence() -> None:
    identity_dir = FIXTURES / "identity"
    formulas = load_json(identity_dir / "formulas.json")
    order_a = load_json(identity_dir / "evidence_order_a.json")
    order_b = load_json(identity_dir / "evidence_order_b.json")
    fingerprint_a = evidence_fingerprint(order_a)
    fingerprint_b = evidence_fingerprint(order_b)
    assert fingerprint_a == fingerprint_b == formulas["evidence_fingerprint"]["expected"]
    assert formulas["evidence_fingerprint"]["pdf_fields"] == ["relation", "kind", "source_id", "page", "ref", "artifact_path", "artifact_sha256", "text_sha256"]
    assert formulas["evidence_fingerprint"]["code_fields"] == ["relation", "kind", "source_id", "repository", "commit", "path", "lines", "snippet_sha256"]
    assert formulas["evidence_fingerprint"]["pdf_excluded_fields"] == ["bbox", "charspan"]
    assert formulas["evidence_fingerprint"]["code_excluded_fields"] == ["symbol"]
