from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from video_paper_wiki.blob_store import BlobStore
from video_paper_wiki.cli import main
from video_paper_wiki.commands import draft
from video_paper_wiki.parse.docling_local import ParserUnavailable

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
DRAFT_SCHEMA = ROOT / "schemas" / "video-paper-wiki.paper-analysis-draft.v1.schema.json"
SECTION_IDS = [
    "one_sentence_conclusion",
    "research_question",
    "method",
    "representation_architecture",
    "training_data",
    "experiments_results",
    "limitations",
    "code_resources",
    "evidence_status",
    "related",
]
LOCATOR_FIELDS = (
    "kind",
    "source_id",
    "page",
    "ref",
    "artifact_path",
    "artifact_sha256",
    "text_sha256",
)


def _stdout_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(DRAFT_SCHEMA.read_text(encoding="utf-8")))


def test_draft_export_no_args_still_not_implemented(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = draft.export()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert network_attempts == []


def test_draft_validate_no_args_still_not_implemented(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = draft.validate()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.validate"
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"
    assert network_attempts == []


def test_export_missing_blob_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["draft", "export", "--sha256", "a" * 64])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_export_invalid_sha256_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["draft", "export", "--sha256", "not-a-sha"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "INVALID_SHA256"
    assert network_attempts == []


def test_export_parser_unavailable_no_download(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = BlobStore(blob_root).put_from_path(TINY_PDF)

    def _unavailable(_path: Path) -> dict:
        raise ParserUnavailable("docling extra is not installed")

    monkeypatch.setattr(
        "video_paper_wiki.commands.draft.parse_pdf_to_draft_fields",
        _unavailable,
    )
    code = main(["draft", "export", "--sha256", digest])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "PARSER_MODEL_NOT_FETCHED"
    assert network_attempts == []
    assert not (tmp_path / ".work" / "drafts").exists()


def test_export_success_mocked_parser_writes_schema_valid_draft(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = BlobStore(blob_root).put_from_path(TINY_PDF)

    def _stub(_path: Path) -> dict:
        return {"title": "Stub Paper", "title_zh": ""}

    monkeypatch.setattr(
        "video_paper_wiki.commands.draft.parse_pdf_to_draft_fields",
        _stub,
    )
    code = main(["draft", "export", "--sha256", digest])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.export"
    paper_id = digest[:12]
    written = tmp_path / ".work" / "drafts" / paper_id / "paper-analysis-draft.v1.json"
    assert payload["data"]["path"] == written.as_posix()
    assert payload["data"]["paper_id"] == paper_id
    assert payload["data"]["sha256"] == digest
    assert written.is_file()
    document = json.loads(written.read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    assert document["title"] == "Stub Paper"
    assert document["taxonomy"] == []
    assert document["claims"] == []
    assert [section["id"] for section in document["sections"]] == SECTION_IDS
    assert network_attempts == []


def test_validate_minimal_fixture(capsys, network_attempts) -> None:
    code = main(["draft", "validate", "--path", str(MINIMAL)])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.validate"
    assert payload["data"]["valid"] is True
    assert network_attempts == []


def test_validate_bad_file(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "video-paper-wiki.paper-analysis-draft.v1"}\n', encoding="utf-8")
    code = main(["draft", "validate", "--path", str(bad)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert network_attempts == []


def test_validate_missing_file(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["draft", "validate", "--path", str(tmp_path / "missing.json")])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert network_attempts == []


def test_local_parser_fails_closed_without_models(tmp_path, monkeypatch, network_attempts) -> None:
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))
    from video_paper_wiki.parse.docling_local import parse_pdf_to_draft_fields

    try:
        parse_pdf_to_draft_fields(TINY_PDF)
    except ParserUnavailable:
        pass
    else:
        raise AssertionError("expected ParserUnavailable when models are missing")
    assert network_attempts == []


def test_export_blob_present_without_models_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))
    digest = BlobStore(blob_root).put_from_path(TINY_PDF)
    code = main(["draft", "export", "--sha256", digest])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.export"
    written = Path(payload["data"]["path"])
    document = json.loads(written.read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    assert document["title"]
    assert document["claims"]
    assert [section["id"] for section in document["sections"]] == SECTION_IDS
    assert network_attempts == []


def _assert_complete_claim(document: dict, sha256: str) -> None:
    assert document["claims"]
    claim = document["claims"][0]
    assert claim["claim_text"]
    assert claim["assessment"] == "provisional"
    assert claim["section"] in SECTION_IDS
    assert isinstance(claim["core"], bool)
    assert claim["locators"]
    locator = claim["locators"][0]
    for field in LOCATOR_FIELDS:
        assert field in locator
    assert locator["kind"] == "pdf"
    assert locator["page"] >= 1
    assert locator["artifact_sha256"] == sha256
    assert locator["text_sha256"] == hashlib.sha256(claim["claim_text"].encode("utf-8")).hexdigest()
    assert [section["id"] for section in document["sections"]] == SECTION_IDS


def test_put_export_validate_pipeline_tiny_pdf(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))

    put_code = main(["ingest", "put", "--path", str(TINY_PDF)])
    assert put_code == 0
    put_payload = _stdout_json(capsys)
    sha256 = put_payload["data"]["sha256"]

    export_code = main(["draft", "export", "--sha256", sha256])
    assert export_code == 0
    export_payload = _stdout_json(capsys)
    draft_path = Path(export_payload["data"]["path"])
    document = json.loads(draft_path.read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    _assert_complete_claim(document, sha256)

    validate_code = main(["draft", "validate", "--path", str(draft_path)])
    assert validate_code == 0
    validate_payload = _stdout_json(capsys)
    assert validate_payload["ok"] is True
    assert validate_payload["command"] == "draft.validate"
    assert network_attempts == []



def test_export_paper_id_writes_stable_draft_path(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))
    digest = BlobStore(blob_root).put_from_path(TINY_PDF)
    paper_id = "arxiv-2311.15127"
    code = main(["draft", "export", "--sha256", digest, "--paper-id", paper_id])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.export"
    written = tmp_path / ".work" / "drafts" / paper_id / "paper-analysis-draft.v1.json"
    assert payload["data"]["path"] == written.as_posix()
    assert payload["data"]["paper_id"] == paper_id
    assert payload["data"]["sha256"] == digest
    assert written.is_file()
    document = json.loads(written.read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    assert document["paper_id"] == paper_id
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["", "/", "..", "a/b", "a\\b", "foo/../bar"])
def test_export_illegal_paper_id(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["draft", "export", "--sha256", "a" * 64, "--paper-id", paper_id])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []
