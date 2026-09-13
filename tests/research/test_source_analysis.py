from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, TEXT, UPSTREAM, fixture_converter, stdout_json, write_pdf
from video_paper_wiki.identity import claim_id, paper_subject_id
from video_paper_wiki.parse.draft_document import SECTION_SPECS
from video_paper_wiki_parser_executor.exporter import export_run, set_test_converter
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.contracts import SECTION_SPECS as RESEARCH_SECTIONS, sha256_bytes
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.source_context import analyze_proposal, build_context
from video_paper_wiki_research.storage import open_research_session


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "video_paper_wiki_research.parser_profile.importlib.metadata.version",
        lambda name: {"docling": "2.117.0", "docling-core": "2.92.0"}[name],
    )


def _pipeline(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> dict:
    _patch_runtime(monkeypatch)
    pdf = write_pdf(checkout / "paper.pdf")
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    intake = Path(stdout_json(capsys)["data"]["path"])
    with open_research_session(SESSION) as session:
        profile = Path(create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))["path"])
        set_test_converter(fixture_converter())
        try:
            exported = export_run(
                session,
                intake_path=intake,
                profile_path=profile,
                artifacts_path=models,
                run_id="run-1",
            )
        finally:
            set_test_converter(None)
        context = build_context(
            session,
            intake_path=intake,
            profile_path=profile,
            run_dir=checkout / Path(exported["paths"]["document_json"]).parent,
            upstream_root=UPSTREAM,
        )
    return {
        "intake": intake,
        "profile": profile,
        "export": exported,
        "context": context,
        "context_path": Path(context["path"]),
    }


def _unsealed(context_doc: dict, *, locator: str | None = None, claim_text: str = TEXT, assessment: str = "provisional") -> dict:
    data = context_doc["data"]
    wire = locator if locator is not None else data["blocks"][0]["locator"]
    paper_id = data["paper_id"]
    cid = claim_id(paper_subject_id(paper_id), claim_text)
    return {
        "context": {"id": context_doc["id"], "sha256": sha256_bytes(
            (json.dumps(context_doc) if False else Path("x")).read_bytes() if False else b""
        )},
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
            "sections": [{"id": section_id, "heading_zh": heading} for section_id, heading in RESEARCH_SECTIONS],
            "taxonomy": [],
            "claims": [
                {
                    "claim_id": cid,
                    "claim_text": claim_text,
                    "section": "method",
                    "core": True,
                    "locators": [wire],
                    "assessment": assessment,
                }
            ],
        },
    }


def test_vertical_provisional_proposal(checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    pipe = _pipeline(checkout, models, monkeypatch, capsys)
    context_path = pipe["context_path"]
    context_doc = json.loads(context_path.read_text(encoding="utf-8"))
    assert context_doc["data"]["blocks"]
    assert context_doc["data"]["state"] == "staged_extraction"
    assert context_doc["data"]["published"] is False
    from video_paper_wiki_research.contracts import exact_ref, saved_bytes

    sealed = json.loads(context_path.read_bytes())
    # Reload as canonical document: file is already JCS+LF.
    from video_paper_wiki_research.storage import load_saved_document

    loaded, raw = load_saved_document(context_path, kind="context", invalid_code="SOURCE_CONTEXT_INVALID")
    ref = exact_ref(loaded)
    data = loaded["data"]
    wire = data["blocks"][0]["locator"]
    assert wire.startswith("vpwiki-locator-v1:")
    assert data["blocks"][0]["text"] == TEXT
    paper_id = data["paper_id"]
    cid = claim_id(paper_subject_id(paper_id), TEXT)
    unsealed = {
        "context": ref,
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
            "sections": [{"id": section_id, "heading_zh": heading} for section_id, heading in RESEARCH_SECTIONS],
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
    proposal_path = checkout / "proposal.unsealed.json"
    proposal_path.write_bytes(json.dumps(unsealed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with open_research_session(SESSION) as session:
        result = analyze_proposal(
            session,
            context_path=context_path,
            proposal_path=proposal_path,
            upstream_root=UPSTREAM,
        )
    assert result["state"] == "staged_analysis_proposal"
    assert result["published"] is False
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "provisional" in markdown
    assert TEXT in markdown
    assert cid in markdown
    assert data["pdf_sha256"] in markdown
    draft = json.loads(Path(result["legacy_draft_path"]).read_text(encoding="utf-8"))
    assert draft["schema"] == "video-paper-wiki.paper-analysis-draft.v1"
    assert draft["claims"][0]["assessment"] == "provisional"
    assert draft["claims"][0]["locators"][0]["kind"] == "pdf"
    del sealed, raw


@pytest.mark.parametrize("field", ["ref", "text", "page", "source_id", "artifact_path", "artifact_sha256"])
def test_tampered_locator_fields(
    checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys, field: str
) -> None:
    pipe = _pipeline(checkout, models, monkeypatch, capsys)
    context_path = pipe["context_path"]
    from video_paper_wiki.ledger_locator import decode_ledger_locator, encode_ledger_locator
    from video_paper_wiki_research.contracts import exact_ref
    from video_paper_wiki_research.storage import load_saved_document

    loaded, _raw = load_saved_document(context_path, kind="context", invalid_code="SOURCE_CONTEXT_INVALID")
    data = loaded["data"]
    original = decode_ledger_locator(data["blocks"][0]["locator"])
    mutated = dict(original)
    if field == "ref":
        mutated["ref"] = "#/texts/99"
    elif field == "text":
        mutated["text_sha256"] = "a" * 64
    elif field == "page":
        mutated["page"] = 2
    elif field == "source_id":
        mutated["source_id"] = "src-not-the-pinned-source"
    elif field == "artifact_path":
        mutated["artifact_path"] = ".raw/derived/" + ("b" * 64) + "/docling/" + ("c" * 64) + "/document.json"
    else:
        mutated["artifact_sha256"] = "d" * 64
    wire = encode_ledger_locator(mutated)
    paper_id = data["paper_id"]
    cid = claim_id(paper_subject_id(paper_id), TEXT)
    unsealed = {
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
            "sections": [{"id": section_id, "heading_zh": heading} for section_id, heading in RESEARCH_SECTIONS],
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
    proposal_path = checkout / f"tamper-{field}.json"
    proposal_path.write_bytes(json.dumps(unsealed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with open_research_session(SESSION) as session:
        with pytest.raises(Exception) as exc:
            analyze_proposal(
                session,
                context_path=context_path,
                proposal_path=proposal_path,
                upstream_root=UPSTREAM,
            )
    assert exc.value.code in {"SOURCE_ANALYSIS_BINDING_MISMATCH", "SOURCE_ANALYSIS_INVALID", "LEDGER_LOCATOR_INVALID"}


def test_prompt_mismatch_and_empty_claims(
    checkout: Path, models: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    pipe = _pipeline(checkout, models, monkeypatch, capsys)
    context_path = pipe["context_path"]
    from video_paper_wiki_research.contracts import exact_ref
    from video_paper_wiki_research.storage import load_saved_document

    loaded, _raw = load_saved_document(context_path, kind="context", invalid_code="SOURCE_CONTEXT_INVALID")
    data = loaded["data"]
    paper_id = data["paper_id"]
    cid = claim_id(paper_subject_id(paper_id), TEXT)
    base = {
        "context": exact_ref(loaded),
        "generator": {
            "model": {"value": "unknown", "identity_source": "unknown", "reason": "fixture-unidentified-model"},
            "runtime": {"value": "unknown", "identity_source": "unknown", "reason": "fixture-unidentified-runtime"},
        },
        "generated_at": "2026-09-06T00:00:00Z",
        "prompt_sha256": "e" * 64,
        "transport_draft": {
            "schema": "video-paper-wiki-research.paper-analysis-transport.v1",
            "paper_id": paper_id,
            "title": "Synthetic paper",
            "title_zh": "合成论文",
            "sections": [{"id": section_id, "heading_zh": heading} for section_id, heading in RESEARCH_SECTIONS],
            "taxonomy": [],
            "claims": [
                {
                    "claim_id": cid,
                    "claim_text": TEXT,
                    "section": "method",
                    "core": True,
                    "locators": [data["blocks"][0]["locator"]],
                    "assessment": "provisional",
                }
            ],
        },
    }
    bad_prompt = checkout / "bad-prompt.json"
    bad_prompt.write_bytes(json.dumps(base, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with open_research_session(SESSION) as session:
        with pytest.raises(Exception) as exc:
            analyze_proposal(session, context_path=context_path, proposal_path=bad_prompt, upstream_root=UPSTREAM)
    assert exc.value.code == "SOURCE_ANALYSIS_BINDING_MISMATCH"
    empty = dict(base)
    empty["prompt_sha256"] = data["prompt_sha256"]
    empty["transport_draft"] = dict(base["transport_draft"])
    empty["transport_draft"]["claims"] = []
    empty_path = checkout / "empty.json"
    empty_path.write_bytes(json.dumps(empty, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with open_research_session(SESSION) as session:
        with pytest.raises(Exception) as empty_exc:
            analyze_proposal(session, context_path=context_path, proposal_path=empty_path, upstream_root=UPSTREAM)
    assert empty_exc.value.code in {"SOURCE_ANALYSIS_EMPTY", "SOURCE_ANALYSIS_INVALID"}
