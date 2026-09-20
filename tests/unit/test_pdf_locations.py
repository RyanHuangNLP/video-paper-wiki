from __future__ import annotations

from pathlib import Path

import pytest

from tests.pdf_samples import sample_pdf_bytes
from video_paper_wiki.pdf_locations import (
    PDF_DRIVE_ID_MISMATCH,
    PDF_DRIVE_URL_INVALID,
    PDF_PARAMETER_CONFLICT,
    PDF_UNAVAILABLE_OFFLINE,
    PDF_VERSION_AMBIGUOUS,
    PdfLocationError,
    build_locations_document,
    build_pdf_entry,
    canonical_paper_id,
    category_for_paper,
    drive_relative_path,
    normalize_drive_locator,
    resolve_open_target,
    verify_local_cache,
)

FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
OTHER_ID = "1ZyxWvUtSrQpOnMlKjIhGfEdCbA0987654"


def test_seed_id_maps_to_canonical_arxiv() -> None:
    assert canonical_paper_id("arxiv-2204.03458") == "arxiv:2204.03458"
    assert canonical_paper_id("arxiv:2204.03458") == "arxiv:2204.03458"
    assert category_for_paper("arxiv-2204.03458") == "engine-mvp"
    assert drive_relative_path("arxiv-2204.03458") == "pdfs/engine-mvp/arxiv-2204.03458/original.pdf"


def test_normalize_file_id_and_url_agree() -> None:
    from_id = normalize_drive_locator(file_id=FILE_ID)
    from_url = normalize_drive_locator(url=f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing")
    assert from_id == from_url
    both = normalize_drive_locator(file_id=FILE_ID, url=from_url["url"])
    assert both["file_id"] == FILE_ID


def test_reject_folder_http_and_mismatched_ids() -> None:
    with pytest.raises(PdfLocationError) as folder:
        normalize_drive_locator(url="https://drive.google.com/drive/folders/1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW")
    assert folder.value.code == PDF_DRIVE_URL_INVALID
    with pytest.raises(PdfLocationError) as http:
        normalize_drive_locator(url=f"http://drive.google.com/file/d/{FILE_ID}/view")
    assert http.value.code == PDF_DRIVE_URL_INVALID
    with pytest.raises(PdfLocationError) as host:
        normalize_drive_locator(url=f"https://example.com/file/d/{FILE_ID}/view")
    assert host.value.code == PDF_DRIVE_URL_INVALID
    with pytest.raises(PdfLocationError) as mismatch:
        normalize_drive_locator(file_id=OTHER_ID, url=f"https://drive.google.com/file/d/{FILE_ID}/view")
    assert mismatch.value.code == PDF_DRIVE_ID_MISMATCH
    kept = normalize_drive_locator(url=f"https://drive.google.com/file/d/{FILE_ID}/view?resourcekey=0-abc")
    assert "resourcekey=0-abc" in kept["url"]


def test_unverified_link_entry_is_showable() -> None:
    entry = build_pdf_entry(file_id=FILE_ID, verified=False)
    doc = build_locations_document("arxiv:2204.03458", [entry])
    assert doc["pdfs"][0]["verification"]["status"] == "unverified"
    assert doc["pdfs"][0]["pdf_sha256"] is None
    resolved = resolve_open_target(doc, roots={}, prefer="drive")
    assert resolved["target_kind"] == "drive"
    assert resolved["verified"] is False


def test_resolve_offline_and_ambiguous(tmp_path: Path) -> None:
    pdf = tmp_path / "original.pdf"
    pdf.write_bytes(sample_pdf_bytes("tiny"))
    from video_paper_wiki.pdf_locations import sha256_bytes

    digest = sha256_bytes(pdf.read_bytes())
    local_entry = build_pdf_entry(
        file_id=FILE_ID,
        pdf_sha256=digest,
        size_bytes=len(pdf.read_bytes()),
        media_type="application/pdf",
        local_refs=[{"root_id": "cache", "relative_path": "original.pdf"}],
        verified=True,
        checked_at="2026-09-20T00:00:00Z",
    )
    other = build_pdf_entry(
        file_id=OTHER_ID,
        pdf_sha256="b" * 64,
        size_bytes=12,
        media_type="application/pdf",
        verified=True,
        checked_at="2026-09-20T00:00:00Z",
    )
    single = build_locations_document("arxiv:2204.03458", [local_entry])
    roots = {"cache": tmp_path}
    auto = resolve_open_target(single, roots=roots, prefer="auto")
    assert auto["target_kind"] == "local"
    assert Path(auto["target"]) == pdf.resolve()
    offline = resolve_open_target(single, roots=roots, prefer="auto", offline=True)
    assert offline["target_kind"] == "local"
    with pytest.raises(PdfLocationError) as conflict:
        resolve_open_target(single, roots=roots, prefer="drive", offline=True)
    assert conflict.value.code == PDF_PARAMETER_CONFLICT
    with pytest.raises(PdfLocationError) as unavailable:
        resolve_open_target(single, roots={}, prefer="auto", offline=True)
    assert unavailable.value.code == PDF_UNAVAILABLE_OFFLINE
    multi = build_locations_document("arxiv:2204.03458", [local_entry, other])
    with pytest.raises(PdfLocationError) as ambiguous:
        resolve_open_target(multi, roots=roots, prefer="auto")
    assert ambiguous.value.code == PDF_VERSION_AMBIGUOUS
    chosen = resolve_open_target(multi, roots=roots, prefer="auto", pdf_sha256=digest)
    assert chosen["pdf_sha256"] == digest
    damaged = tmp_path / "broken.pdf"
    damaged.write_bytes(b"not-a-pdf")
    check = verify_local_cache(damaged, expected_sha256=digest)
    assert check["available"] is False
