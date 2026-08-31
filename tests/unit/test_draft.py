from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.support import make_checkout, plant_blob, work_draft
from video_paper_wiki.cli import main
from video_paper_wiki.commands import draft
from video_paper_wiki.parse.docling_local import ParserUnavailable
from video_paper_wiki.parse.draft_document import EVIDENCE_STATUS_TEXT, claims_from_body, claims_from_parse_fields
from video_paper_wiki.parse.pypdf_local import parse_pdf_to_draft_fields as parse_pypdf_fields

ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
TINY_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "tiny.pdf"
SECTIONED_PDF = ROOT / "tests" / "fixtures" / "pdfs" / "sectioned.pdf"
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


def test_draft_export_no_args_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = draft.export()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_draft_validate_no_args_is_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = draft.validate()
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["command"] == "draft.validate"
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_export_missing_blob_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["draft", "export", "--sha256", "a" * 64, "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "BLOB_NOT_FOUND"
    assert network_attempts == []


def test_export_invalid_sha256_no_network(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["draft", "export", "--sha256", "not-a-sha", "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "INVALID_SHA256"
    assert network_attempts == []


def test_export_parser_unavailable_no_download(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())

    def _unavailable(_path: Path) -> dict:
        raise ParserUnavailable("docling extra is not installed")

    monkeypatch.setattr(
        "video_paper_wiki.commands.draft.parse_pdf_to_draft_fields",
        _unavailable,
    )
    code = main(["draft", "export", "--sha256", digest, "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "PARSER_MODEL_NOT_FETCHED"
    assert network_attempts == []
    assert not (tmp_path / ".work" / "b1" / "draft").exists()


def test_export_success_mocked_parser_writes_schema_valid_draft(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())

    def _stub(_path: Path) -> dict:
        return {"title": "Stub Paper", "title_zh": ""}

    monkeypatch.setattr(
        "video_paper_wiki.commands.draft.parse_pdf_to_draft_fields",
        _stub,
    )
    code = main(["draft", "export", "--sha256", digest, "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.export"
    paper_id = digest[:12]
    written = work_draft(tmp_path, "b1")
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
    make_checkout(tmp_path)
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
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["draft", "validate", "--path", str(tmp_path / "missing.json")])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["error"]["code"] == "DRAFT_INVALID"
    assert network_attempts == []


@pytest.mark.parametrize("paper_id", ["   ", "a\n..", "/tmp", "../"])
def test_validate_rejects_unsafe_paper_id(
    paper_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = main(["draft", "validate", "--path", str(path)])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "draft.validate"
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
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    code = main(["draft", "export", "--sha256", digest, "--batch-id", "b1"])
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
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))

    sha256 = plant_blob(blob_root, TINY_PDF.read_bytes())

    export_code = main(["draft", "export", "--sha256", sha256, "--batch-id", "b1"])
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
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    monkeypatch.setenv("DOCLING_ARTIFACTS_PATH", str(tmp_path / "no-models"))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    paper_id = "arxiv-2311.15127"
    code = main(["draft", "export", "--sha256", digest, "--paper-id", paper_id, "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "draft.export"
    written = work_draft(tmp_path, "b1")
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
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    code = main(["draft", "export", "--sha256", "a" * 64, "--paper-id", paper_id, "--batch-id", "b1"])
    assert code == 2
    payload = _stdout_json(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "draft.export"
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert not (tmp_path / ".work").exists()
    assert network_attempts == []


MULTI_HEADING_BODY = """Video Paper Title
Abstract
Frozen tokenizers enable efficient video generation. This is extra abstract.
1 Introduction
We ask whether a frozen tokenizer method is enough for video.
Training
The dataset contains ten million video clips.
3) Experiments
Results show a twelve percent FVD gain on the benchmark.
Limitations
The model fails on long uncurated videos.
Related Work
Prior diffusion video models include VideoGPT.
https://github.com/example/vpkb-demo
"""


def _minimal_pdf(pages: list[list[str]], *, title: str = "") -> bytes:
    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def content_stream(lines: list[str]) -> bytes:
        out = ["BT\n/F1 12 Tf\n18 TL\n72 720 Td\n"]
        for index, line in enumerate(lines):
            if index:
                out.append("T*\n")
            out.append(f"({esc(line)}) Tj\n")
        out.append("ET\n")
        return "".join(out).encode("latin-1")

    n_pages = len(pages)
    font_obj = 3 + 2 * n_pages
    info_obj = 4 + 2 * n_pages
    objs: dict[int, bytes] = {}
    kids = " ".join(f"{3 + index} 0 R" for index in range(n_pages))
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode("ascii")
    for index, lines in enumerate(pages):
        page_obj = 3 + index
        content_obj = 3 + n_pages + index
        objs[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_obj} 0 R /Resources << /Font << /F1 {font_obj} 0 R >> >> >>"
        ).encode("ascii")
        stream = content_stream(lines)
        objs[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )
    objs[font_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objs[info_obj] = f"<< /Title ({esc(title)}) >>".encode("latin-1") if title else b"<< >>"

    header = b"%PDF-1.4\n%\x80\x80\x80\x80\n"
    pieces = [header]
    offsets: dict[int, int] = {}
    pos = len(header)
    max_obj = info_obj
    for number in range(1, max_obj + 1):
        serialized = f"{number} 0 obj\n".encode("ascii") + objs[number] + b"\nendobj\n"
        offsets[number] = pos
        pieces.append(serialized)
        pos += len(serialized)
    xref_lines = [f"xref\n0 {max_obj + 1}\n", "0000000000 65535 f \n"]
    for number in range(1, max_obj + 1):
        xref_lines.append(f"{offsets[number]:010d} 00000 n \n")
    trailer = (
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R /Info {info_obj} 0 R >>\n"
        f"startxref\n{pos}\n%%EOF\n"
    )
    pieces.append("".join(xref_lines).encode("ascii"))
    pieces.append(trailer.encode("ascii"))
    return b"".join(pieces)


def _claims_by_section(document: dict) -> dict[str, dict]:
    return {claim["section"]: claim for claim in document["claims"]}


def _assert_locator(claim: dict, sha256: str) -> None:
    assert claim["assessment"] == "provisional"
    assert claim["claim_text"]
    locator = claim["locators"][0]
    for field in LOCATOR_FIELDS:
        assert field in locator
    assert locator["kind"] == "pdf"
    assert locator["page"] >= 1
    assert locator["ref"] == f"#/page/{locator['page']}"
    assert locator["artifact_sha256"] == sha256
    assert locator["source_id"] == sha256[:12]
    assert locator["text_sha256"] == hashlib.sha256(claim["claim_text"].encode("utf-8")).hexdigest()


def test_pypdf_extracts_up_to_twenty_pages(tmp_path, network_attempts) -> None:
    pages = [[f"Page {index} visible text"] for index in range(1, 22)]
    pdf_path = tmp_path / "many.pdf"
    pdf_path.write_bytes(_minimal_pdf(pages, title="Many Pages"))
    fields = parse_pypdf_fields(pdf_path)
    assert fields["parser"] == "pypdf"
    assert fields["title"] == "Many Pages"
    assert [item["page"] for item in fields["pages"]] == list(range(1, 21))
    assert "Page 20 visible text" in fields["body_text"]
    assert "Page 21 visible text" not in fields["body_text"]
    assert network_attempts == []


def test_claims_from_body_maps_multi_heading_string(network_attempts) -> None:
    digest = "ab" * 32
    claims = claims_from_body(
        body_text=MULTI_HEADING_BODY,
        artifact_sha256=digest,
        artifact_path="sources/demo/paper.pdf",
        title="Video Paper Title",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert by_section["one_sentence_conclusion"]["claim_text"] == (
        "Frozen tokenizers enable efficient video generation."
    )
    assert "Video Paper Title" not in by_section["one_sentence_conclusion"]["claim_text"]
    assert "frozen tokenizer method" in by_section["research_question"]["claim_text"]
    assert "ten million video clips" in by_section["training_data"]["claim_text"]
    assert "twelve percent FVD" in by_section["experiments_results"]["claim_text"]
    assert "long uncurated videos" in by_section["limitations"]["claim_text"]
    assert "VideoGPT" in by_section["related"]["claim_text"]
    assert "github.com" in by_section["code_resources"]["claim_text"]
    assert by_section["evidence_status"]["claim_text"] == EVIDENCE_STATUS_TEXT
    assert by_section["one_sentence_conclusion"]["core"] is True
    for section, claim in by_section.items():
        if section != "one_sentence_conclusion":
            assert claim["core"] is False
        _assert_locator(claim, digest)
        assert claim["locators"][0]["artifact_path"] == "sources/demo/paper.pdf"
    assert network_attempts == []


def test_heading_matcher_ignores_long_sentences_with_keywords(network_attempts) -> None:
    body = (
        "This long sentence describes the method and the training data used "
        "in our study without being a heading."
    )
    claims = claims_from_body(
        body_text=body,
        artifact_sha256="cd" * 32,
        artifact_path="x.pdf",
        title="",
    )
    assert {claim["section"] for claim in claims} == {
        "one_sentence_conclusion",
        "evidence_status",
    }
    assert network_attempts == []


def test_tiny_pdf_exports_required_claims(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    blob_root = tmp_path / "blobs"
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    code = main(["draft", "export", "--sha256", digest, "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    document = json.loads(Path(payload["data"]["path"]).read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    by_section = _claims_by_section(document)
    assert "one_sentence_conclusion" in by_section
    assert "evidence_status" in by_section
    assert by_section["evidence_status"]["claim_text"] == EVIDENCE_STATUS_TEXT
    assert by_section["one_sentence_conclusion"]["core"] is True
    for section, claim in by_section.items():
        if section != "one_sentence_conclusion":
            assert claim["core"] is False
        _assert_locator(claim, digest)
    assert network_attempts == []


def test_sectioned_pdf_fills_abstract_and_method(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    blob_root = tmp_path / "blobs"
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, SECTIONED_PDF.read_bytes())
    code = main(["draft", "export", "--sha256", digest, "--batch-id", "b1"])
    assert code == 0
    payload = _stdout_json(capsys)
    draft_path = Path(payload["data"]["path"])
    document = json.loads(draft_path.read_text(encoding="utf-8"))
    _schema_validator().validate(document)
    assert document["title"] == "Sectioned VPKB Paper"
    by_section = _claims_by_section(document)
    conclusion = by_section["one_sentence_conclusion"]["claim_text"]
    assert conclusion == "This abstract sentence is the conclusion claim."
    assert conclusion != document["title"]
    assert "diffusion transformer" in by_section["method"]["claim_text"]
    assert by_section["evidence_status"]["claim_text"] == EVIDENCE_STATUS_TEXT
    assert by_section["method"]["locators"][0]["page"] == 2
    assert by_section["one_sentence_conclusion"]["core"] is True
    for section, claim in by_section.items():
        if section != "one_sentence_conclusion":
            assert claim["core"] is False
        _assert_locator(claim, digest)
    assert network_attempts == []


FIGURE_TABLE_BODY = """Method
We train a frozen tokenizer for video generation.
Figure 9
Raw Processed
0.12 0.34 0.56 12% 8.1 0.99
"""

CONCLUSION_THEN_LIMITATIONS_BODY = """Abstract
A tokenizer paper about video generation.
Conclusion
We recap that the frozen tokenizer works well overall.
Limitations
The model fails on long uncurated videos.
"""

JUNK_LABEL_BODY = """Raw Processed
(a)
(b)
"""

BACKFILL_BODY = """Video generation is a challenging open problem.
We present a method that uses a frozen tokenizer.
We train a U-Net for latent video synthesis.
The training dataset of ten million clips is curated from the web.
"""

RELATED_WORK_ONLY_BODY = """Related Work
Prior work uses a training dataset of images and a U-Net model.
"""


def test_figure_table_not_used_as_method_claim(network_attempts) -> None:
    claims = claims_from_body(
        body_text=FIGURE_TABLE_BODY,
        artifact_sha256="11" * 32,
        artifact_path="figure-table.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" in by_section
    method_text = by_section["method"]["claim_text"]
    assert "frozen tokenizer" in method_text
    assert "We train" in method_text
    assert "Figure 9" not in method_text
    assert "Raw Processed" not in method_text
    assert "0.12" not in method_text
    assert "12%" not in method_text
    for claim in claims:
        assert "Figure 9" not in claim["claim_text"]
        assert "0.12 0.34" not in claim["claim_text"]
    assert network_attempts == []


def test_figure_table_pdf_keeps_method_prose(tmp_path, network_attempts) -> None:
    pdf_path = tmp_path / "figure-table.pdf"
    pdf_path.write_bytes(
        _minimal_pdf(
            [
                [
                    "Method",
                    "We train a frozen tokenizer for video generation.",
                    "Figure 9",
                    "Raw Processed",
                    "0.12 0.34 0.56 12% 8.1 0.99",
                ]
            ],
            title="Figure Table Paper",
        )
    )
    fields = parse_pypdf_fields(pdf_path)
    digest = "22" * 32
    claims = claims_from_parse_fields(
        fields,
        artifact_sha256=digest,
        artifact_path="sources/demo/figure-table.pdf",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" in by_section
    method_text = by_section["method"]["claim_text"]
    assert "frozen tokenizer" in method_text
    assert "Figure 9" not in method_text
    assert "Raw Processed" not in method_text
    assert "0.12" not in method_text
    assert network_attempts == []


def test_conclusion_heading_does_not_fill_limitations(network_attempts) -> None:
    claims = claims_from_body(
        body_text=CONCLUSION_THEN_LIMITATIONS_BODY,
        artifact_sha256="33" * 32,
        artifact_path="x.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "limitations" in by_section
    limitations = by_section["limitations"]["claim_text"]
    assert "long uncurated videos" in limitations
    assert "recap" not in limitations
    assert "works well overall" not in limitations
    assert network_attempts == []


def test_short_junk_labels_are_not_section_claims(network_attempts) -> None:
    claims = claims_from_body(
        body_text=JUNK_LABEL_BODY,
        artifact_sha256="44" * 32,
        artifact_path="x.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "training_data" not in by_section
    assert "method" not in by_section
    assert "representation_architecture" not in by_section
    for claim in claims:
        lowered = claim["claim_text"].lower()
        assert "raw processed" not in lowered
        assert claim["claim_text"].strip() not in {"(a)", "(b)", "Raw Processed"}
    if "evidence_status" in by_section:
        assert by_section["evidence_status"]["claim_text"] == EVIDENCE_STATUS_TEXT
    assert network_attempts == []


def test_keyword_backfill_without_method_heading(network_attempts) -> None:
    claims = claims_from_body(
        body_text=BACKFILL_BODY,
        artifact_sha256="55" * 32,
        artifact_path="x.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    filled = set(by_section) & {"method", "representation_architecture", "training_data"}
    assert filled
    if "method" in by_section:
        assert "method" in by_section["method"]["claim_text"].lower()
    if "representation_architecture" in by_section:
        assert "U-Net" in by_section["representation_architecture"]["claim_text"]
    if "training_data" in by_section:
        assert "training dataset" in by_section["training_data"]["claim_text"]
    assert by_section["one_sentence_conclusion"]["claim_text"].startswith(
        "Video generation is a challenging open problem."
    )
    assert network_attempts == []


def test_backfill_does_not_steal_related_work(network_attempts) -> None:
    claims = claims_from_body(
        body_text=RELATED_WORK_ONLY_BODY,
        artifact_sha256="66" * 32,
        artifact_path="x.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "related" in by_section
    assert "training dataset" in by_section["related"]["claim_text"]
    assert "training_data" not in by_section
    assert "method" not in by_section
    assert "representation_architecture" not in by_section
    assert network_attempts == []

GSO_CAPTION_BODY = """Method
Figure 9
Objects (GSO) test dataset on the (b) Training progress of the model.
We train a frozen tokenizer on video latents.
"""

GSO_CAPTION_WITH_FIGURE_MENTION_BODY = """Method
Figure 9
Objects (GSO) test dataset on the (b) Training progress of the model. Figure 9
"""

GSO_CAPTION_ONLY_BODY = """Method
Figure 9
Objects (GSO) test dataset on the (b) Training progress of the model.
"""

TRUNCATED_LEAD_BODY = """Method
ing a diffusion model for video.
We train a U-Net on latents.
"""

TRUNCATED_LEAD_ONLY_BODY = """Method
ing a diffusion model for video.
"""

TRAINING_PANEL_CAPTION_BODY = """Training
Left: Optical Flow Score
Right: Temporal consistency of warped frames.
"""

BACKFILL_GSO_CAPTION_BODY = """Video generation is a challenging open problem.
Objects (GSO) test dataset on the (b) Training progress of the model.
"""


def test_gso_caption_remnant_not_method_claim(network_attempts) -> None:
    claims = claims_from_body(
        body_text=GSO_CAPTION_BODY,
        artifact_sha256="77" * 32,
        artifact_path="gso.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" in by_section
    method_text = by_section["method"]["claim_text"]
    assert "frozen tokenizer" in method_text
    assert "GSO" not in method_text
    assert "Figure 9" not in method_text
    assert "(b) Training progress" not in method_text
    for claim in claims:
        assert "GSO" not in claim["claim_text"]
        assert "Figure 9" not in claim["claim_text"]
        assert "(b) Training progress" not in claim["claim_text"]
    assert network_attempts == []


def test_gso_caption_with_figure_mention_not_method_claim(network_attempts) -> None:
    claims = claims_from_body(
        body_text=GSO_CAPTION_WITH_FIGURE_MENTION_BODY,
        artifact_sha256="88" * 32,
        artifact_path="gso-figure.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" not in by_section
    for claim in claims:
        assert "GSO" not in claim["claim_text"]
        assert "Figure 9" not in claim["claim_text"]
        assert "(b) Training progress" not in claim["claim_text"]
    assert network_attempts == []


def test_gso_caption_only_does_not_fill_method(network_attempts) -> None:
    claims = claims_from_body(
        body_text=GSO_CAPTION_ONLY_BODY,
        artifact_sha256="99" * 32,
        artifact_path="gso-only.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" not in by_section
    for claim in claims:
        assert "GSO" not in claim["claim_text"]
        assert "Figure 9" not in claim["claim_text"]
        assert "(b) Training progress" not in claim["claim_text"]
    assert network_attempts == []


def test_truncated_leading_word_is_not_a_claim(network_attempts) -> None:
    claims = claims_from_body(
        body_text=TRUNCATED_LEAD_BODY,
        artifact_sha256="aa" * 32,
        artifact_path="truncated.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    for claim in claims:
        assert "ing a diffusion model" not in claim["claim_text"]
    assert "method" in by_section
    assert "U-Net on latents" in by_section["method"]["claim_text"]
    assert network_attempts == []


def test_truncated_leading_word_without_followup_skips_section(network_attempts) -> None:
    claims = claims_from_body(
        body_text=TRUNCATED_LEAD_ONLY_BODY,
        artifact_sha256="bb" * 32,
        artifact_path="truncated-only.pdf",
        title="",
    )
    for claim in claims:
        assert "ing a diffusion model" not in claim["claim_text"]
    assert "method" not in {claim["section"] for claim in claims}
    assert network_attempts == []


def test_training_panel_caption_not_used_as_training_data(network_attempts) -> None:
    claims = claims_from_body(
        body_text=TRAINING_PANEL_CAPTION_BODY,
        artifact_sha256="cc" * 32,
        artifact_path="training-caption.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "training_data" not in by_section
    for claim in claims:
        lowered = claim["claim_text"].lower()
        assert "optical flow score" not in lowered
        assert not lowered.startswith("left:")
        assert not lowered.startswith("right:")
    assert network_attempts == []


def test_backfill_does_not_use_gso_caption(network_attempts) -> None:
    claims = claims_from_body(
        body_text=BACKFILL_GSO_CAPTION_BODY,
        artifact_sha256="dd" * 32,
        artifact_path="backfill-gso.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    assert "method" not in by_section
    assert "training_data" not in by_section
    for claim in claims:
        assert "GSO" not in claim["claim_text"]
        assert "(b) Training progress" not in claim["claim_text"]
    assert network_attempts == []

TRUNCATED_SAME_LINE_BODY = """Method
ing a diffusion model for video. We train a U-Net on latents.
"""

HYPHENATION_LEFTOVER_BODY = """Method
changes to accommodate the video backbone.
We train a U-Net on latents.
"""


def test_truncated_lead_same_line_uses_next_sentence(network_attempts) -> None:
    claims = claims_from_body(
        body_text=TRUNCATED_SAME_LINE_BODY,
        artifact_sha256="ee" * 32,
        artifact_path="truncated-same-line.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    for claim in claims:
        assert "ing a diffusion model" not in claim["claim_text"]
    assert "method" in by_section
    assert "U-Net on latents" in by_section["method"]["claim_text"]
    assert network_attempts == []


def test_hyphenation_leftover_not_used_as_method_claim(network_attempts) -> None:
    claims = claims_from_body(
        body_text=HYPHENATION_LEFTOVER_BODY,
        artifact_sha256="ff" * 32,
        artifact_path="hyphenation.pdf",
        title="",
    )
    by_section = {claim["section"]: claim for claim in claims}
    for claim in claims:
        assert not claim["claim_text"].startswith("changes to accommodate")
    assert "method" in by_section
    assert "U-Net on latents" in by_section["method"]["claim_text"]
    assert network_attempts == []

