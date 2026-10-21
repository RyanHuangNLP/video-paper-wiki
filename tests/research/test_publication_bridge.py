from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.research.test_source_admission import (
    CLAIM_TEXT,
    UPSTREAM,
    admit_source,
    apply_publication,
    bind_snapshots,
    bootstrap_genesis,
    capture_pdf,
    intake_for,
)
from tests.support import make_checkout
from video_paper_wiki.contracts import DOCLING_CORE_VERSION, DOCLING_VERSION, ContractError
from video_paper_wiki.identity import claim_id, pipeline_fingerprint
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import inspect_publication, prepare_publication_source
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki_research.publication_bridge import (
    bind_capture_operation,
    bridge_publication,
    package_extraction_run,
    prepare_paper_concept_publication,
)
from video_paper_wiki_research.source_admission import (
    SOURCE_AUTHORITY_INVALID,
    SOURCE_DUPLICATE,
    SOURCE_MISSING,
)


def _document_json() -> bytes:
    document = {
        "pages": {
            "1": {"page_no": 1, "size": {"height": 72.0, "width": 72.0}},
        },
        "texts": [
            {
                "prov": [
                    {
                        "bbox": {"b": 20.75, "coord_origin": "TOPLEFT", "l": 0.0, "r": 40.25, "t": 1.5},
                        "charspan": [0, len(CLAIM_TEXT)],
                        "page_no": 1,
                    },
                ],
                "self_ref": "#/texts/0",
                "text": CLAIM_TEXT,
            },
        ],
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"


def four_file_run(root: Path, pdf: bytes) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    parser_config = canonicalize({"profile": "manual-pdf-fixture"})
    model_manifest = canonicalize({"models": []})
    document = _document_json()
    fingerprint = pipeline_fingerprint({
        "engine": "docling",
        "engine_version": DOCLING_VERSION,
        "core_version": DOCLING_CORE_VERSION,
        "config_sha256": hashlib.sha256(parser_config).hexdigest(),
        "model_manifest_sha256": hashlib.sha256(model_manifest).hexdigest(),
    })
    run = {
        "schema": "video-paper-wiki.run-manifest.v1",
        "run_id": "run-manual-1",
        "tool_versions": {
            "vpwiki": "0.1.0", "python": "3.12",
            "docling": DOCLING_VERSION, "docling_core": DOCLING_CORE_VERSION,
        },
        "input_hashes": {
            "parser_config_sha256": hashlib.sha256(parser_config).hexdigest(),
            "model_manifest_sha256": hashlib.sha256(model_manifest).hexdigest(),
        },
        "output_hashes": {"document_json_sha256": hashlib.sha256(document).hexdigest()},
        "started_at": "2026-09-01T00:00:00Z",
        "ended_at": "2026-09-01T00:00:01Z",
        "error_code": None,
        "pipeline_fingerprint": fingerprint,
    }
    paths = {
        "document_json": root / "document.json",
        "parser_config": root / "parser-config.json",
        "model_manifest": root / "model-manifest.json",
        "run_manifest": root / "run.json",
    }
    paths["document_json"].write_bytes(document)
    paths["parser_config"].write_bytes(parser_config)
    paths["model_manifest"].write_bytes(model_manifest)
    paths["run_manifest"].write_bytes(canonicalize(run))
    return paths


def _sections() -> list[dict[str, str]]:
    return [
        {"id": "one_sentence_conclusion", "heading_zh": "一句话结论"},
        {"id": "research_question", "heading_zh": "研究问题"},
        {"id": "method", "heading_zh": "方法"},
        {"id": "representation_architecture", "heading_zh": "表示与架构"},
        {"id": "training_data", "heading_zh": "训练与数据"},
        {"id": "experiments_results", "heading_zh": "实验与结果"},
        {"id": "limitations", "heading_zh": "局限"},
        {"id": "code_resources", "heading_zh": "代码与资源"},
        {"id": "evidence_status", "heading_zh": "证据状态"},
        {"id": "related", "heading_zh": "关联"},
    ]


def legacy_draft(*, paper_id: str, source_id: str, artifact_path: str, artifact_sha256: str) -> dict:
    subject = "paper:" + paper_id
    cid = claim_id(subject, CLAIM_TEXT)
    return {
        "schema": "video-paper-wiki.paper-analysis-draft.v1",
        "paper_id": paper_id,
        "title": "Manual PDF paper",
        "title_zh": "人工 PDF 论文",
        "sections": _sections(),
        "taxonomy": [{"axis": "backbone", "slug": "dit"}],
        "claims": [
            {
                "claim_id": cid,
                "claim_text": CLAIM_TEXT,
                "section": "method",
                "core": True,
                "locators": [
                    {
                        "kind": "pdf",
                        "source_id": source_id,
                        "page": 1,
                        "ref": "#/texts/0",
                        "bbox": [0, 1, 40, 20],
                        "charspan": [0, len(CLAIM_TEXT)],
                        "artifact_path": artifact_path,
                        "artifact_sha256": artifact_sha256,
                        "text_sha256": hashlib.sha256(CLAIM_TEXT.encode("utf-8")).hexdigest(),
                    },
                ],
                "assessment": "provisional",
            },
        ],
    }


def _admitted_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, capture, applied = capture_pdf(checkout, vault)
    intake = intake_for(pdf)
    admitted = admit_source(
        intake=intake, capture_authority=capture, vault_root=vault, upstream_root=UPSTREAM,
        batch_id="research-admit", operation_id="research-admit",
    )
    inspected = inspect_publication(
        prepared=admitted["request_path"], operation_id="research-admit",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    apply_publication(checkout, vault, inspected)
    return checkout, vault, pdf, capture, applied, intake, admitted


def test_bridge_packages_float_document_and_prepares_inspectable_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout, vault, pdf, capture, applied, intake, admitted = _admitted_state(tmp_path, monkeypatch)
    before, after, stored = bind_snapshots(capture, applied, pdf)
    bound = bind_capture_operation(
        inspected_transaction=capture["upstream_authority"]["transaction"],
        apply_result=applied, vault_before=before, vault_after=after,
        expected_pdf_sha256=intake["pdf_sha256"], stored_path=stored,
    )
    assert bound["result"]["status"] == "complete"
    runs = four_file_run(tmp_path / "run", pdf)
    captured_pdf = vault / admitted["stored_path"]
    document_sha = hashlib.sha256(runs["document_json"].read_bytes()).hexdigest()
    bridged = bridge_publication(
        intake=intake, capture_bind=bound, captured_pdf=captured_pdf,
        document_json=runs["document_json"], parser_config=runs["parser_config"],
        model_manifest=runs["model_manifest"], run_manifest=runs["run_manifest"],
        legacy_draft=legacy_draft(
            paper_id=intake["paper_id"], source_id=admitted["source_id"],
            artifact_path=".raw/derived/" + ("0" * 64) + "/docling/" + ("1" * 64) + "/document.json",
            artifact_sha256="d" * 64,
        ),
        source_id=admitted["source_id"], vault_root=vault,
        package_batch_id="research-package", package_operation_id="research-package",
        paper_batch_id="research-paper", paper_operation_id="research-paper",
    )
    packaged = bridged["package"]
    paper = bridged["paper"]
    assert packaged["already_packaged"] is False
    assert packaged["request_path"]
    assert paper["source_id"] == admitted["source_id"]
    assert paper["paper_id"] == intake["paper_id"]
    assert paper["pdf_sha256"] == intake["pdf_sha256"]
    assert paper["paper_record"]["source_ids"] == [admitted["source_id"]]
    assert paper["paper_record"]["active_extraction_sha256"] == document_sha
    assert paper["pages_included"] is False
    assert paper["agent_may_run_vpwiki_admin"] is False
    assert any(step["action"] == "human_claim_assessment" for step in paper["remaining_operator_steps"])
    prepare_publication_source(request_path=packaged["request_path"], batch_id="research-package")
    package_inspect = inspect_publication(
        prepared=packaged["request_path"], operation_id="research-package",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    assert package_inspect["transaction"]["phase"] == "inspected"
    apply_publication(checkout, vault, package_inspect)
    prepare_publication_source(request_path=paper["request_path"], batch_id="research-paper")
    paper_inspect = inspect_publication(
        prepared=paper["request_path"], operation_id="research-paper",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    assert paper_inspect["transaction"]["phase"] == "inspected"
    report = audit_integrity(vault)
    assert admitted["stored_path"] in report["ever_claimed_raw"]


def test_package_missing_source_is_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, _capture, _applied = capture_pdf(checkout, vault)
    runs = four_file_run(tmp_path / "run", pdf)
    missing = vault / ".raw" / "captured" / ("ab" * 32 + ".pdf")
    with pytest.raises(ContractError) as caught:
        package_extraction_run(
            captured_pdf=missing, document_json=runs["document_json"],
            parser_config=runs["parser_config"], model_manifest=runs["model_manifest"],
            run_manifest=runs["run_manifest"], vault_root=vault,
            batch_id="missing-package", operation_id="missing-package",
        )
    assert caught.value.code == SOURCE_MISSING


def test_package_non_receipt_backed_pdf_is_invalid_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    pdf, capture, _applied = capture_pdf(checkout, vault)
    runs = four_file_run(tmp_path / "run", pdf)
    captured_pdf = vault / capture["inspection"]["stored_path"]
    with pytest.raises(ContractError) as caught:
        package_extraction_run(
            captured_pdf=captured_pdf, document_json=runs["document_json"],
            parser_config=runs["parser_config"], model_manifest=runs["model_manifest"],
            run_manifest=runs["run_manifest"], vault_root=vault,
            batch_id="orphan-package", operation_id="orphan-package",
        )
    assert caught.value.code == SOURCE_AUTHORITY_INVALID


def test_package_conflicting_derived_bytes_is_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout, vault, pdf, _capture, _applied, _intake, admitted = _admitted_state(tmp_path, monkeypatch)
    runs = four_file_run(tmp_path / "run", pdf)
    captured_pdf = vault / admitted["stored_path"]
    first = package_extraction_run(
        captured_pdf=captured_pdf, document_json=runs["document_json"],
        parser_config=runs["parser_config"], model_manifest=runs["model_manifest"],
        run_manifest=runs["run_manifest"], vault_root=vault,
        batch_id="package-one", operation_id="package-one",
    )
    inspected = inspect_publication(
        prepared=first["request_path"], operation_id="package-one",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    apply_publication(checkout, vault, inspected)
    other = json.loads(runs["document_json"].read_text(encoding="utf-8"))
    other["texts"][0]["text"] = CLAIM_TEXT + " extra"
    new_document = json.dumps(other, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    runs["document_json"].write_bytes(new_document)
    run = json.loads(runs["run_manifest"].read_text(encoding="utf-8"))
    run["output_hashes"]["document_json_sha256"] = hashlib.sha256(new_document).hexdigest()
    runs["run_manifest"].write_bytes(canonicalize(run))
    with pytest.raises(ContractError) as caught:
        package_extraction_run(
            captured_pdf=captured_pdf, document_json=runs["document_json"],
            parser_config=runs["parser_config"], model_manifest=runs["model_manifest"],
            run_manifest=runs["run_manifest"], vault_root=vault,
            batch_id="package-conflict", operation_id="package-conflict",
        )
    assert caught.value.code == SOURCE_DUPLICATE


def test_paper_duplicate_and_float_envelope_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    checkout, vault, pdf, _capture, _applied, intake, admitted = _admitted_state(tmp_path, monkeypatch)
    runs = four_file_run(tmp_path / "run", pdf)
    captured_pdf = vault / admitted["stored_path"]
    packaged = package_extraction_run(
        captured_pdf=captured_pdf, document_json=runs["document_json"],
        parser_config=runs["parser_config"], model_manifest=runs["model_manifest"],
        run_manifest=runs["run_manifest"], vault_root=vault,
        batch_id="paper-package", operation_id="paper-package",
    )
    inspect_publication(
        prepared=packaged["request_path"], operation_id="paper-package",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    document = next(item for item in packaged["artifact_set"]["artifacts"] if item["kind"] == "document_json")
    draft = legacy_draft(
        paper_id=intake["paper_id"], source_id=admitted["source_id"],
        artifact_path=document["path"], artifact_sha256=document["sha256"],
    )
    first = prepare_paper_concept_publication(
        intake=intake, legacy_draft=draft, source_id=admitted["source_id"],
        artifact_set=packaged["artifact_set"], vault_root=vault,
        batch_id="paper-one", operation_id="paper-one",
    )
    inspected = inspect_publication(
        prepared=first["request_path"], operation_id="paper-one",
        upstream_root=UPSTREAM, vault_root=vault,
    )
    apply_publication(checkout, vault, inspected)
    with pytest.raises(ContractError) as caught:
        prepare_paper_concept_publication(
            intake=intake, legacy_draft=draft, source_id=admitted["source_id"],
            artifact_set=packaged["artifact_set"], vault_root=vault,
            batch_id="paper-two", operation_id="paper-two",
        )
    assert caught.value.code == SOURCE_DUPLICATE
    float_receipt = b'{"schema":"video-paper-wiki.operation-receipt.v1","sequence":1.5}'
    with pytest.raises(Exception) as caught:
        parse_strict_json(float_receipt, invalid_code="SCHEMA_INVALID")
    assert caught.value.code == "SCHEMA_INVALID"
    float_ledger = b'{"schema":"claude-obsidian.source-ledger.v1","generated_at":"2026-09-01T00:00:00Z","sources":{"src-x":{"score":0.5}}}'
    with pytest.raises(Exception) as caught:
        parse_strict_json(float_ledger, invalid_code="SCHEMA_INVALID")
    assert caught.value.code == "SCHEMA_INVALID"
    from video_paper_wiki.publication import _decode_publication_json
    derived = ".raw/derived/" + ("a" * 64) + "/docling/" + ("b" * 64) + "/document.json"
    parsed = _decode_publication_json(derived, _document_json())
    assert parsed["texts"][0]["prov"][0]["bbox"]["l"] == 0.0
    assert parsed["pages"]["1"]["size"]["width"] == 72.0
