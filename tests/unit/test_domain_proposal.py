from __future__ import annotations

import copy
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from tests.code_proof_public_fixture import (
    JSON_BODY,
    README_BODY,
    SRC_BODY,
    dump_json,
    make_checkout,
    make_repo,
    observe_raw_doc,
    request_doc,
    write_bundle,
    write_bytes,
)
from tests.source_semantics_fixture import STAMP, claim_for, event_for, locator_for, source_fixture
from video_paper_wiki.code_proof_public import (
    handoff_code_proof,
    observe_code_proof,
    request_code_proof,
    status_code_proof,
)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.domain_proposal import (
    CLAIM_KINDS,
    CONCEPT_KINDS,
    DomainProposalError,
    inspect_domain_proposal,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import encode_evidence, evidence_fingerprint_versioned
from video_paper_wiki.source_publication_contracts import ASSESSMENT_HEADS, CLAIM_LEDGER, HEADS
from video_paper_wiki.source_semantics_contracts import sha


CLAIM_TEXTS = {
    "architecture": "The architecture uses a space-time attention backbone.",
    "training": "Training uses mixed precision and data parallelism.",
    "empirical_result": "The method reports improved FVD on the benchmark.",
    "implementation": "The authors release training and inference code.",
    "ablation": "Removing temporal attention reduces quality.",
    "limitation": "The model is limited to short clips.",
    "reproducibility": "A training recipe and configs are provided.",
    "license": "The code is released under Apache-2.0.",
    "resource_requirement": "Training requires eight GPUs.",
}
UNANNOTATED_TEXT = "An older untyped claim remains readable."
TAXONOMY = [
    ("Method", "backbone", "dit"),
    ("Model", "formulation/objective", "diffusion"),
    ("ArchitectureComponent", "spatial-temporal-modeling", "space-time-attention"),
    ("TrainingRecipe", "training/parallelism/optimization", "mixed-precision"),
    ("Dataset", "data/captioning/filtering", "captioning"),
    ("Benchmark", "evaluation/dataset/benchmark", "vbench"),
    ("InferenceRecipe", "inference/distillation/acceleration", "few-step-sampling"),
    ("EvaluationMetric", "evaluation/dataset/benchmark", "fvd"),
]


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.chmod(path, 0o600)


def _snippet(body: bytes, start: int = 1, end: int = 1) -> str:
    lines = body.decode("utf-8").splitlines()
    return sha("\n".join(lines[start - 1 : end]).encode("utf-8"))


def _pdf_locator(association, context: str) -> dict:
    return {
        "kind": "pdf",
        "source_id": association["source_id"],
        "page": 1,
        "ref": "#/texts/1",
        "artifact_path": ".raw/derived/" + "a" * 64 + "/document.json",
        "artifact_sha256": "d" * 64,
        "text_sha256": "b" * 64,
        "context": context,
    }


def make_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    checkout = make_checkout(tmp_path / "co")
    monkeypatch.chdir(checkout)
    association, raw, _authority = source_fixture()
    locator = locator_for(association, raw)
    evidence = [{**locator, "relation": "supports"}]
    subject = "paper:" + association["paper_id"]
    annotated = []
    events = []
    ledger_rows = {}
    page = "wiki/papers/paper.md"
    for kind in CLAIM_KINDS:
        claim = claim_for(evidence, text=CLAIM_TEXTS[kind], subject=subject)
        event = event_for(claim)
        annotated.append((kind, claim, event))
        events.append(event)
        ledger_rows[claim["claim_id"]] = {
            "text": claim["canonical_claim_text"],
            "risk": "normal",
            "confidence": "unknown",
            "assessment": "provisional",
            "reviewed_at": None,
            "location": {"path": page, "anchor": "^" + claim["claim_id"]},
            "evidence": [encode_evidence(x) for x in claim["evidence"]],
            "notes": None,
            "supersedes": None,
        }
    extra = claim_for(evidence, text=UNANNOTATED_TEXT, subject=subject)
    extra_event = event_for(extra)
    events.append(extra_event)
    ledger_rows[extra["claim_id"]] = {
        "text": extra["canonical_claim_text"],
        "risk": "normal",
        "confidence": "unknown",
        "assessment": "provisional",
        "reviewed_at": None,
        "location": {"path": page},
        "evidence": [encode_evidence(x) for x in extra["evidence"]],
        "notes": None,
        "supersedes": None,
    }
    vault = checkout / "vault"
    vault.mkdir()
    assoc_raw = canonicalize(association)
    _write(vault / "wiki/meta/records/source-versions" / (association["association_id"] + ".json"), assoc_raw)
    _write(vault / association["raw"]["path"], raw)
    ledger = {"schema": "claude-obsidian.claim-ledger.v1", "generated_at": STAMP, "claims": ledger_rows}
    _write(vault / CLAIM_LEDGER, canonicalize(ledger))
    heads = {"schema": HEADS, "heads": {}}
    for _kind, claim, event in annotated:
        heads["heads"][claim["claim_id"]] = {
            "event_id": event["event_id"],
            "event_sha256": sha(canonicalize(event)),
            "evidence_profile": event.get("evidence_profile", "legacy-v1"),
        }
    heads["heads"][extra["claim_id"]] = {
        "event_id": extra_event["event_id"],
        "event_sha256": sha(canonicalize(extra_event)),
        "evidence_profile": extra_event.get("evidence_profile", "legacy-v1"),
    }
    _write(vault / ASSESSMENT_HEADS, canonicalize(heads))
    for event in events:
        _write(
            vault / "wiki/meta/reviews" / event["claim_id"] / (event["event_id"] + ".json"),
            canonicalize(event),
        )
    page_body = b"Project page links the implementation repository.\n"
    page_rel = ".raw/derived/project-pages/" + sha(page_body) + ".md"
    _write(vault / page_rel, page_body)
    files = {
        "config.json": (JSON_BODY, False),
        "src.py": (SRC_BODY, False),
        "README.md": (README_BODY, False),
    }
    repo = make_repo("sha1", files)
    targets = [
        {"path": "README.md", "roles": ["readme"], "allow_executable_source": False},
        {"path": "config.json", "roles": ["configuration"], "allow_executable_source": False},
        {"path": "src.py", "roles": ["implementation"], "allow_executable_source": False},
    ]
    request = request_doc(repo, targets)
    request["paper_id"] = association["paper_id"]
    request["source_association"] = {
        "association_id": association["association_id"],
        "sha256": sha(assoc_raw),
    }
    write_bytes(checkout / "request.json", dump_json(request))
    req = request_code_proof(input_path="request.json", batch_id="d1")
    write_bundle(checkout, ".work/raw", repo, req["request"])
    write_bytes(checkout / "observe.json", dump_json(observe_raw_doc(repo)))
    observe_code_proof(input_path="observe.json", batch_id="d1", bundle_dir=".work/raw")
    handoff_code_proof(batch_id="d1")
    status = status_code_proof(batch_id="d1")
    return {
        "checkout": checkout,
        "vault": vault,
        "association": association,
        "assoc_raw": assoc_raw,
        "source_raw": raw,
        "annotated": annotated,
        "extra": extra,
        "extra_event": extra_event,
        "page_rel": page_rel,
        "page_body": page_body,
        "repo": repo,
        "status": status,
        "files": files,
        "ledger_bytes": (vault / CLAIM_LEDGER).read_bytes(),
    }


def valid_proposal(world: dict, **overrides) -> dict:
    association = world["association"]
    status = world["status"]
    commit = world["repo"]["commit_oid"]
    concepts = []
    for kind, axis, slug in TAXONOMY:
        if kind == "EvaluationMetric":
            concepts.append(
                {
                    "concept_kind": kind,
                    "surface_form": "CustomClipScore",
                    "taxonomy_ref": None,
                    "normalization_proposal": {
                        "surface_form": "CustomClipScore",
                        "proposed_slug": "custom-clip-score",
                        "reason": "New evaluation metric not in taxonomy v1.",
                    },
                }
            )
        else:
            concepts.append(
                {
                    "concept_kind": kind,
                    "surface_form": slug,
                    "taxonomy_ref": {"axis": axis, "slug": slug},
                    "normalization_proposal": None,
                }
            )
    annotations = []
    for kind, claim, event in world["annotated"]:
        annotations.append(
            {
                "claim_id": claim["claim_id"],
                "claim_text": claim["canonical_claim_text"],
                "evidence_fingerprint": evidence_fingerprint_versioned(claim["evidence"]),
                "assessment_head": {
                    "event_id": event["event_id"],
                    "event_sha256": sha(canonicalize(event)),
                    "evidence_profile": event.get("evidence_profile", "legacy-v1"),
                },
                "claim_kind": kind,
            }
        )
    readme = world["files"]["README.md"][0]
    proposal = {
        "schema": "video-paper-wiki.domain-proposal.v1",
        "paper_id": association["paper_id"],
        "source_association": {
            "association_id": association["association_id"],
            "sha256": sha(world["assoc_raw"]),
        },
        "source_digest": {
            "path": association["raw"]["path"],
            "sha256": association["raw"]["sha256"],
            "size_bytes": association["raw"]["size_bytes"],
        },
        "repository": "Owner/Name",
        "commit": commit,
        "code_batch_id": "d1",
        "code_refs": {
            "request": dict(status["request"]),
            "observation": dict(status["observation"]),
            "handoffs": [
                {"path": row["path"], "id": row["reference"]["id"], "sha256": row["reference"]["sha256"]}
                for row in status["handoffs"]
            ],
        },
        "concepts": concepts,
        "claim_annotations": annotations,
        "relation": {
            "kind": "this_paper_implementation",
            "officiality_candidate": "pending_review",
            "evidence_classes": {
                "A": {
                    "present": True,
                    "locators": [_pdf_locator(association, "our implementation is available at")],
                },
                "B": {
                    "present": True,
                    "project_page": {
                        "kind": "project_page",
                        "url": "https://example.invalid/paper",
                        "local_digest": {
                            "path": world["page_rel"],
                            "sha256": sha(world["page_body"]),
                            "size_bytes": len(world["page_body"]),
                        },
                        "fragment": {
                            "start": 0,
                            "end": len(world["page_body"]),
                            "text_sha256": sha(world["page_body"]),
                        },
                    },
                },
                "C": {"present": False, "locators": []},
                "D": {"present": False, "author_control": None},
            },
            "shortcuts_observed": ["url_match", "hash_verified"],
            "third_party_statement": False,
            "repository_statement": False,
            "missing_evidence": ["C", "reverse_citation"],
            "reason": "Paper links the implementation; README reverse citation is absent.",
        },
        "capabilities": [
            {
                "name": "training",
                "status": "present",
                "locators": [
                    {
                        "kind": "code",
                        "source_id": "src-repo",
                        "repository": "owner/name",
                        "commit": commit,
                        "path": "src.py",
                        "lines": {"start": 1, "end": 1},
                        "snippet_sha256": _snippet(SRC_BODY),
                    }
                ],
                "declaration_kind": "code",
                "absence_scope": None,
            },
            {
                "name": "inference",
                "status": "partial",
                "locators": [
                    {
                        "kind": "code",
                        "source_id": "src-repo",
                        "repository": "owner/name",
                        "commit": commit,
                        "path": "config.json",
                        "lines": {"start": 1, "end": 1},
                        "snippet_sha256": _snippet(JSON_BODY),
                    }
                ],
                "declaration_kind": "config",
                "absence_scope": None,
            },
            {
                "name": "data",
                "status": "unverified",
                "locators": [],
                "declaration_kind": "readme_only",
                "absence_scope": None,
            },
            {
                "name": "evaluation",
                "status": "absent",
                "locators": [],
                "declaration_kind": None,
                "absence_scope": {
                    "commit": commit,
                    "tree_prefix": "eval",
                    "search_patterns": ["eval", "benchmark"],
                    "observed_files": ["src.py", "config.json", "README.md"],
                },
            },
            {
                "name": "checkpoints",
                "status": "unverified",
                "locators": [],
                "declaration_kind": None,
                "absence_scope": None,
                "checkpoint_kind": "link_only",
            },
        ],
        "self_reported": {"accepted": True, "verified": True, "official": True},
    }
    proposal.update(overrides)
    return proposal


def write_proposal(checkout: Path, proposal: dict, name: str = "proposal.json") -> Path:
    path = checkout / name
    write_bytes(path, canonicalize(proposal) + b"\n")
    return path


def inspect_file(world: dict, proposal: dict, name: str = "proposal.json"):
    path = write_proposal(world["checkout"], proposal, name)
    return inspect_domain_proposal(
        input_path=str(path),
        vault_root=str(world["vault"]),
        code_batch_id="d1",
    )


def _snapshot(root: Path) -> dict:
    out = {}
    for path in root.rglob("*"):
        if path.is_file():
            st = path.lstat()
            out[str(path.relative_to(root))] = (path.read_bytes(), stat.S_IMODE(st.st_mode), st.st_mtime_ns)
    return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def test_eight_concepts_nine_claim_kinds_five_capabilities(world):
    report = inspect_file(world, valid_proposal(world))
    validate_document(report, "video-paper-wiki.domain-proposal-report.v1")
    assert [row["concept_kind"] for row in report["concepts"]] == list(CONCEPT_KINDS)
    assert {row["term_status"] for row in report["concepts"]} == {"taxonomy_v1", "normalization_proposal"}
    assert [row["claim_kind"] for row in report["claim_annotations"]] == list(CLAIM_KINDS)
    assert report["unannotated_claims"][0]["claim_id"] == world["extra"]["claim_id"]
    assert report["unannotated_claims"][0]["claim_kind"] is None
    assert report["unannotated_claims"][0]["freshness"] == "unannotated"
    names = [row["name"] for row in report["capabilities"]]
    assert names == ["training", "inference", "data", "evaluation", "checkpoints"]
    by_name = {row["name"]: row for row in report["capabilities"]}
    assert by_name["training"]["status"] == "present"
    assert by_name["training"]["declaration_kind"] == "code"
    assert by_name["inference"]["status"] == "partial"
    assert by_name["inference"]["declaration_kind"] == "config"
    assert by_name["data"]["declaration_kind"] == "readme_only"
    assert by_name["data"]["status"] == "unverified"
    assert by_name["evaluation"]["status"] == "absent"
    assert by_name["evaluation"]["absence_scope"]["observed_files"]
    assert by_name["checkpoints"]["status"] == "unverified"
    assert report["status"] == "proposal_only"
    assert report["publication"] == "unpublished"
    assert report["review"] == "pending_semantic_review"
    assert report["successor_only"] is True
    assert report["source_association_verified"] is False
    assert report["canonical_official"] is False
    assert report["current_supported_typed_fact"] is False
    assert report["relation"]["officiality_candidate"] == "pending_review"
    assert report["relation"]["locators"]["B"]["kind"] == "project_page"
    assert report["claim_annotations"][0]["assessment"] == "provisional"
    assert report["claim_annotations"][0]["freshness"] == "head_bound"


@pytest.mark.parametrize(
    "kind",
    [
        "this_paper_implementation",
        "baseline",
        "dependency",
        "third_party_reproduction",
        "unknown",
    ],
)
def test_relation_branches(world, kind):
    proposal = valid_proposal(world)
    proposal["relation"]["kind"] = kind
    if kind == "third_party_reproduction":
        proposal["relation"]["third_party_statement"] = True
        proposal["relation"]["officiality_candidate"] = "third_party"
        proposal["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
        proposal["relation"]["missing_evidence"] = ["A", "B"]
        proposal["relation"]["reason"] = "Explicit third-party reproduction statement."
    report = inspect_file(world, proposal, name=kind + ".json")
    assert report["relation"]["kind"] == kind
    if kind == "third_party_reproduction":
        assert report["relation"]["officiality_candidate"] == "third_party"


def test_officiality_shortcuts_do_not_upgrade(world):
    for shortcut in (
        "url_match",
        "account_similarity",
        "organization_affiliation",
        "reverse_citation_only",
        "config_filename",
        "hash_verified",
    ):
        proposal = valid_proposal(world)
        proposal["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
        proposal["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
        proposal["relation"]["shortcuts_observed"] = [shortcut]
        proposal["relation"]["officiality_candidate"] = "pending_review"
        proposal["relation"]["missing_evidence"] = ["A", "B"]
        proposal["relation"]["reason"] = "shortcut only"
        with pytest.raises(DomainProposalError) as err:
            inspect_file(world, proposal, name=shortcut + ".json")
        assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
        assert err.value.details["instance_pointer"] == "/relation/officiality_candidate"


def test_missing_backlink_pending_review_and_third_party_vs_insufficient(world):
    direct = inspect_file(world, valid_proposal(world), name="direct.json")
    assert direct["relation"]["officiality_candidate"] == "pending_review"
    assert "C" in direct["relation"]["gaps"]
    proposal = valid_proposal(world)
    proposal["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    proposal["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
    proposal["relation"]["evidence_classes"]["D"] = {
        "present": True,
        "author_control": {
            "kind": "author_control",
            "account": "owner",
            "organization": None,
            "control_evidence": "verified public control of the repository",
            "context": "repository README states this is the official implementation",
        },
    }
    proposal["relation"]["repository_statement"] = True
    proposal["relation"]["missing_evidence"] = ["A", "paper_backlink"]
    proposal["relation"]["reason"] = "Author control with repository statement missing paper backlink."
    author = inspect_file(world, proposal, name="author.json")
    assert author["relation"]["officiality_candidate"] == "pending_review"
    assert "A" in author["relation"]["gaps"]
    third = valid_proposal(world)
    third["relation"]["kind"] = "third_party_reproduction"
    third["relation"]["third_party_statement"] = True
    third["relation"]["officiality_candidate"] = "third_party"
    third["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    third["relation"]["missing_evidence"] = ["A", "B"]
    third["relation"]["reason"] = "Explicit third-party reproduction."
    third_report = inspect_file(world, third, name="third.json")
    assert third_report["relation"]["officiality_candidate"] == "third_party"
    weak = valid_proposal(world)
    weak["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    weak["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
    weak["relation"]["officiality_candidate"] = "unverified_candidate"
    weak["relation"]["missing_evidence"] = ["A", "B"]
    weak["relation"]["reason"] = "insufficient evidence"
    weak_report = inspect_file(world, weak, name="weak.json")
    assert weak_report["relation"]["officiality_candidate"] == "unverified_candidate"
    only_c = valid_proposal(world)
    only_c["relation"]["evidence_classes"]["A"] = {"present": False, "locators": []}
    only_c["relation"]["evidence_classes"]["B"] = {"present": False, "project_page": None}
    only_c["relation"]["evidence_classes"]["C"] = {
        "present": True,
        "locators": [
            {
                "kind": "repository_text",
                "path": "README.md",
                "commit": world["repo"]["commit_oid"],
                "local_digest": {"sha256": sha(README_BODY), "size_bytes": len(README_BODY)},
                "fragment": {"start": 0, "end": len(README_BODY), "text_sha256": sha(README_BODY)},
            }
        ],
    }
    only_c["relation"]["officiality_candidate"] = "pending_review"
    only_c["relation"]["shortcuts_observed"] = ["reverse_citation_only"]
    only_c["relation"]["missing_evidence"] = ["A", "B"]
    only_c["relation"]["reason"] = "C only"
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, only_c, name="only-c.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    missing_ab_unofficial = copy.deepcopy(weak)
    missing_ab_unofficial["relation"]["officiality_candidate"] = "third_party"
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, missing_ab_unofficial, name="false-unofficial.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"


def test_replace_source_claim_head_c2_and_evidence_bytes(world):
    base = valid_proposal(world)
    inspect_file(world, base, name="ok.json")
    changed_source = copy.deepcopy(base)
    changed_source["source_association"]["sha256"] = "0" * 64
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, changed_source, name="source.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    assert "source_association" in err.value.details["instance_pointer"]
    changed_claim = copy.deepcopy(base)
    changed_claim["claim_annotations"][0]["claim_text"] = "Different claim text."
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, changed_claim, name="claim.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    assert err.value.details["instance_pointer"].endswith("claim_text")
    changed_head = copy.deepcopy(base)
    changed_head["claim_annotations"][0]["assessment_head"]["event_sha256"] = "e" * 64
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, changed_head, name="head.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    assert "assessment_head" in err.value.details["instance_pointer"]
    changed_c2 = copy.deepcopy(base)
    changed_c2["code_refs"]["request"]["id"] = "ce1:code-proof-request:" + "a" * 64
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, changed_c2, name="c2.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    assert err.value.details["instance_pointer"] == "/code_refs/request"
    before = world["ledger_bytes"]
    source_path = world["vault"] / world["association"]["raw"]["path"]
    original = source_path.read_bytes()
    source_path.write_bytes(original + b"changed")
    os.chmod(source_path, 0o600)
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, base, name="bytes.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    source_path.write_bytes(original)
    os.chmod(source_path, 0o600)
    assert (world["vault"] / CLAIM_LEDGER).read_bytes() == before


def test_unknown_fields_limits_bad_locators_and_mismatch(world):
    extra = valid_proposal(world)
    extra["unexpected"] = True
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, extra, name="unknown.json")
    assert err.value.code == "DOMAIN_PROPOSAL_INVALID"
    limited = valid_proposal(world)
    limited["concepts"] = limited["concepts"] + [copy.deepcopy(limited["concepts"][0]) for _ in range(32)]
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, limited, name="limit.json")
    assert err.value.code == "DOMAIN_PROPOSAL_INVALID"
    bad = valid_proposal(world)
    bad["capabilities"][0]["locators"][0]["commit"] = "b" * 40
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, bad, name="locator.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    paper = valid_proposal(world)
    paper["paper_id"] = "arxiv:2301.00001"
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, paper, name="paper.json")
    assert err.value.code == "DOMAIN_PROPOSAL_BINDING_MISMATCH"
    present_readme = valid_proposal(world)
    present_readme["capabilities"][0]["declaration_kind"] = "readme_only"
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, present_readme, name="readme-present.json")
    assert err.value.code == "DOMAIN_PROPOSAL_LOCATOR_INVALID"
    absent = valid_proposal(world)
    absent["capabilities"][3]["absence_scope"] = None
    with pytest.raises(DomainProposalError) as err:
        inspect_file(world, absent, name="absent.json")
    assert err.value.code == "DOMAIN_PROPOSAL_LOCATOR_INVALID"


def test_determinism_zero_writes_and_no_network(world, monkeypatch):
    def blocked(*_a, **_k):
        raise AssertionError("egress")

    monkeypatch.setattr(socket, "socket", blocked)
    proposal = valid_proposal(world)
    vault_before = _snapshot(world["vault"])
    work_before = _snapshot(world["checkout"] / ".work")
    first = inspect_file(world, proposal, name="a.json")
    second = inspect_file(world, proposal, name="b.json")
    assert canonicalize(first) == canonicalize(second)
    assert _snapshot(world["vault"]) == vault_before
    assert _snapshot(world["checkout"] / ".work") == work_before
    assert (world["vault"] / CLAIM_LEDGER).read_bytes() == world["ledger_bytes"]
