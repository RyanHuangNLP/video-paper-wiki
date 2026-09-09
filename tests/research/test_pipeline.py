"""End-to-end research pipeline: intake → capture → admit → package → paper → QA/writing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, TEXT, UPSTREAM, fixture_converter, stdout_json, synthetic_document, write_pdf
from tests.research.pipeline_support import (
    apply_inspected_publication,
    bootstrap_genesis,
    capture_pdf_bytes,
    load_saved_json,
    read_vault_file_state,
)
from tests.support import make_checkout
from video_paper_wiki.identity import claim_id, paper_subject_id
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki_parser_executor.exporter import export_run, set_test_converter
from video_paper_wiki_research.catalog_index import build_published_catalog
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.contracts import SECTION_SPECS, exact_ref, sha256_bytes
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.publication_bridge import bind_capture_operation, bridge_publication
from video_paper_wiki_research.qa import import_and_check
from video_paper_wiki_research.source_admission import admit_source
from video_paper_wiki_research.source_context import analyze_proposal, build_context
from video_paper_wiki_research.storage import load_saved_document, open_research_session
from video_paper_wiki_research.writing import import_and_render


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata

    real = importlib.metadata.version

    def version(name: str) -> str:
        pinned = {"docling": "2.117.0", "docling-core": "2.92.0"}
        if name in pinned:
            return pinned[name]
        return real(name)

    monkeypatch.setattr(importlib.metadata, "version", version)


def _unsealed_proposal(context_path: Path) -> dict:
    loaded, raw = load_saved_document(context_path, kind="context", invalid_code="SOURCE_CONTEXT_INVALID")
    assert sha256_bytes(raw) == exact_ref(loaded)["sha256"]
    data = loaded["data"]
    wire = data["blocks"][0]["locator"]
    paper_id = data["paper_id"]
    cid = claim_id(paper_subject_id(paper_id), TEXT)
    return {
        "context": exact_ref(loaded),
        "generator": {
            "model": {"value": "unknown", "identity_source": "unknown", "reason": "fixture-unidentified-model"},
            "runtime": {"value": "unknown", "identity_source": "unknown", "reason": "fixture-unidentified-runtime"},
        },
        "generated_at": "2026-09-06T00:00:00Z",
        "prompt_sha256": data["prompt_sha256"],
        "transport_draft": {
            "schema": "video-paper-wiki-research.paper-analysis-transport.v1",
            "paper_id": paper_id,
            "title": "Synthetic paper",
            "title_zh": "合成论文",
            "sections": [{"id": section_id, "heading_zh": heading} for section_id, heading in SECTION_SPECS],
            "taxonomy": [],
            "claims": [
                {
                    "claim_id": cid,
                    "claim_text": TEXT,
                    "section": "method",
                    "core": True,
                    "locators": [wire],
                    "assessment": "provisional",
                }
            ],
        },
    }


def test_manual_pdf_to_publication_to_qa_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    _patch_runtime(monkeypatch)
    models = tmp_path / "models"
    (models / "layout").mkdir(parents=True)
    (models / "layout" / "weights.bin").write_bytes(b"synthetic-model-bytes")
    (models / "config.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    pdf_path = write_pdf(checkout / "paper.pdf")
    pdf_bytes = pdf_path.read_bytes()

    assert research_main(["pdf", "intake", "--pdf", str(pdf_path), "--session", SESSION]) == 0
    intake_cli = stdout_json(capsys)
    assert intake_cli["data"]["capture_authorized"] is False
    assert intake_cli["data"]["receipt_backed"] is False
    assert intake_cli["data"]["published"] is False
    intake_path = Path(intake_cli["data"]["path"])
    intake_doc = load_saved_json(intake_path)
    assert intake_doc["data"]["pdf_sha256"] == sha256_bytes(pdf_bytes)

    with open_research_session(SESSION) as session:
        profile = create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))
        profile_path = Path(profile["path"])
        set_test_converter(
            fixture_converter(
                synthetic_document(
                    origin="TOPLEFT",
                    text=TEXT,
                )
                | {
                    "texts": [
                        {
                            "self_ref": "#/texts/0",
                            "text": TEXT,
                            "prov": [
                                {
                                    "page_no": 1,
                                    "charspan": [0, len(TEXT)],
                                    "bbox": {
                                        "l": 0.0,
                                        "t": 1.5,
                                        "r": 40.25,
                                        "b": 20.75,
                                        "coord_origin": "TOPLEFT",
                                    },
                                }
                            ],
                        }
                    ]
                }
            )
        )
        try:
            exported = export_run(
                session,
                intake_path=intake_path,
                profile_path=profile_path,
                artifacts_path=models,
                run_id="run-1",
            )
        finally:
            set_test_converter(None)
        run_dir = checkout / Path(exported["paths"]["document_json"]).parent
        assert (run_dir / "document.json").is_file()
        assert (run_dir / "parser-config.json").is_file()
        assert (run_dir / "model-manifest.json").is_file()
        assert (run_dir / "run.json").is_file()
        context = build_context(
            session,
            intake_path=intake_path,
            profile_path=profile_path,
            run_dir=run_dir,
            upstream_root=UPSTREAM,
        )
    assert context["capture_authorized"] is False
    assert context["receipt_backed"] is False
    assert context["published"] is False
    context_path = Path(context["path"])
    loaded, _raw = load_saved_document(context_path, kind="context", invalid_code="SOURCE_CONTEXT_INVALID")
    locator = loaded["data"]["blocks"][0]["locator"]
    proposal_path = checkout / "proposal.unsealed.json"
    proposal_path.write_bytes(json.dumps(_unsealed_proposal(context_path), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with open_research_session(SESSION) as session:
        analyzed = analyze_proposal(
            session,
            context_path=context_path,
            proposal_path=proposal_path,
            upstream_root=UPSTREAM,
        )
    assert analyzed["published"] is False
    assert analyzed["capture_authorized"] is False
    legacy_draft_path = Path(analyzed["legacy_draft_path"])
    draft = load_saved_json(legacy_draft_path)
    assert draft["schema"] == "video-paper-wiki.paper-analysis-draft.v1"
    assert draft["claims"][0]["locators"][0]["ref"] == "#/texts/0"
    assert draft["claims"][0]["locators"][0]["kind"] == "pdf"
    decoded_page = draft["claims"][0]["locators"][0]["page"]
    assert decoded_page == 1

    vault = tmp_path / "vault"
    bootstrap_genesis(checkout, vault, tmp_path)
    captured = capture_pdf_bytes(checkout, vault, pdf_bytes, batch_id="research-capture")
    assert captured["digest"] == intake_doc["data"]["pdf_sha256"]
    assert captured["after"][captured["stored_path"]]["sha256"] == captured["digest"]
    assert captured["before"][captured["stored_path"]] is None
    replay = bind_capture_operation(
        inspected_transaction=captured["authority"]["upstream_authority"]["transaction"],
        apply_result=captured["applied"],
        vault_before=read_vault_file_state(vault, captured["applied"]["changed_paths"]),
        vault_after=read_vault_file_state(vault, captured["applied"]["changed_paths"]),
        expected_pdf_sha256=captured["digest"],
        stored_path=captured["stored_path"],
    )
    assert replay["result"]["status"] == "complete"

    admitted = admit_source(
        intake=intake_doc,
        capture_authority=captured["authority"],
        vault_root=vault,
        upstream_root=UPSTREAM,
        batch_id="research-admit",
        operation_id="research-admit",
    )
    assert admitted["receipt_backed"] is False
    assert admitted["published"] is False
    apply_inspected_publication(
        checkout,
        vault,
        request_path=admitted["request_path"],
        operation_id="research-admit",
        batch_id="research-admit",
    )
    after_admit = audit_integrity(vault)
    assert admitted["stored_path"] in after_admit["ever_claimed_raw"]

    bridged = bridge_publication(
        intake=intake_doc,
        capture_bind=captured["bound"],
        captured_pdf=vault / admitted["stored_path"],
        document_json=run_dir / "document.json",
        parser_config=run_dir / "parser-config.json",
        model_manifest=run_dir / "model-manifest.json",
        run_manifest=run_dir / "run.json",
        legacy_draft=legacy_draft_path,
        source_id=admitted["source_id"],
        vault_root=vault,
        package_batch_id="research-package",
        package_operation_id="research-package",
        paper_batch_id="research-paper",
        paper_operation_id="research-paper",
    )
    packaged = bridged["package"]
    paper = bridged["paper"]
    assert packaged["already_packaged"] is False
    assert paper["pages_included"] is False
    apply_inspected_publication(
        checkout,
        vault,
        request_path=packaged["request_path"],
        operation_id="research-package",
        batch_id="research-package",
    )
    after_package = audit_integrity(vault)
    document = next(item for item in packaged["artifact_set"]["artifacts"] if item["kind"] == "document_json")
    assert (vault / document["path"]).is_file()
    apply_inspected_publication(
        checkout,
        vault,
        request_path=paper["request_path"],
        operation_id="research-paper",
        batch_id="research-paper",
    )
    after_paper = audit_integrity(vault)
    assert after_package["classification"] == "receipt_backed"
    assert after_paper["classification"] == "receipt_backed"
    slug = paper["paper_id"].replace(":", "-")
    assert (vault / "wiki" / "meta" / "records" / "papers" / f"{slug}.json").is_file()

    catalog = build_published_catalog(vault_root=vault, upstream_root=UPSTREAM)
    paper_id = paper["paper_id"]
    assert paper_id in catalog["papers"]
    config_path = catalog["config_path"]

    assert research_main(
        [
            "qa",
            "export",
            "--question",
            TEXT,
            "--vault-root",
            str(vault),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            config_path,
        ]
    ) == 0
    qa_context = stdout_json(capsys)
    assert qa_context["ok"] is True
    assert qa_context["kind"] == "qa-context"
    assert qa_context["evidence"]
    unit = qa_context["evidence"][0]
    assert unit["paper_id"] == paper_id
    assert unit["claim_text"] == TEXT
    assert unit["claim_text_kind"] == "proposal"
    assert unit["source_excerpt"] == TEXT
    assert unit["source_excerpt_kind"] == "original-document"
    bbox = unit["locator"]["bbox"]
    assert type(bbox) is list and len(bbox) == 4
    assert any(type(item) is float and not item.is_integer() for item in bbox)
    assert type(qa_context["papers"][0].get("score")) is float
    context_blob = json.dumps(qa_context, ensure_ascii=False)
    synthetic_answer = {
        "text": (
            "SYNTHETIC FIXTURE ANSWER drawn from source_excerpt="
            f"{unit['source_excerpt']} and claim_text={unit['claim_text']}."
        ),
        "citations": [
            {
                "paper_id": unit["paper_id"],
                "evidence_unit_id": unit["evidence_unit_id"],
                "locator_fingerprint": unit["locator_fingerprint"],
            }
        ],
        "synthetic_fixture": True,
    }
    assert TEXT in synthetic_answer["text"]
    assert TEXT in context_blob
    checked = import_and_check(context=qa_context, answer=synthetic_answer)
    assert checked["ok"] is True
    assert checked["citation_check"]["accepted"] is True
    invalid = import_and_check(
        context=qa_context,
        answer={
            "text": "SYNTHETIC FIXTURE with an invented citation.",
            "citations": [{"paper_id": "arxiv:0000.00000", "evidence_unit_id": "evu-" + "0" * 20}],
            "synthetic_fixture": True,
        },
    )
    assert invalid["ok"] is False
    assert invalid["status"] == "INVALID_CITATION"

    assert research_main(
        [
            "writing",
            "export",
            "--topic",
            TEXT,
            "--requirements",
            "Write a short editable overview with sources.",
            "--paper-id",
            paper_id,
            "--vault-root",
            str(vault),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            config_path,
        ]
    ) == 0
    writing_context = stdout_json(capsys)
    assert writing_context["ok"] is True
    assert writing_context["kind"] == "writing-context"
    writing_unit = writing_context["evidence"][0]
    assert writing_unit["source_excerpt"] == TEXT
    assert writing_unit["claim_text"] == TEXT
    rendered = import_and_render(
        context=writing_context,
        draft={
            "markdown": f"SYNTHETIC FIXTURE DRAFT for {TEXT}. [{writing_unit['evidence_unit_id']}]",
            "citations": [
                {
                    "paper_id": writing_unit["paper_id"],
                    "evidence_unit_id": writing_unit["evidence_unit_id"],
                }
            ],
            "synthetic_fixture": True,
        },
    )
    assert rendered["ok"] is True
    markdown = rendered["markdown"]
    assert markdown.startswith(f"# {TEXT}")
    assert "Write a short editable overview with sources." in markdown
    assert "## 参考文献" in markdown
    assert paper_id in markdown
    assert locator.startswith("vpwiki-locator-v1:")
    del replay
