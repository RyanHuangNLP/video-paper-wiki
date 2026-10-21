from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, stdout_json, write_pdf
from tests.support import pdf_bytes
from video_paper_wiki.identity import paper_id_from_pdf_sha256
from video_paper_wiki_research.cli import main
from video_paper_wiki_research.contracts import sha256_bytes
from video_paper_wiki_research.storage import open_research_session


def test_intake_normal_duplicate_and_ids(checkout: Path, capsys) -> None:
    pdf = write_pdf(checkout / "paper.pdf")
    digest = sha256_bytes(pdf.read_bytes())
    first = main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION])
    payload = stdout_json(capsys)
    assert first == 0
    assert payload["ok"] is True
    assert payload["command"] == "pdf.intake"
    assert payload["data"]["next_action"] == "awaiting_parser_profile"
    assert payload["data"]["paper_id"] == paper_id_from_pdf_sha256(digest)
    assert payload["data"]["pdf_sha256"] == digest
    assert payload["data"]["capture_authorized"] is False
    assert (checkout / ".work" / "blobs" / digest).is_file()
    second = main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION])
    again = stdout_json(capsys)
    assert second == 0
    assert again["data"]["already_staged"] is True
    explicit = main(
        ["pdf", "intake", "--pdf", str(pdf), "--session", "s2", "--paper-id", "arxiv:2311.15127"]
    )
    named = stdout_json(capsys)
    assert explicit == 0
    assert named["data"]["paper_id"] == "arxiv:2311.15127"


def test_intake_malformed_encrypted_zero_page_overlimit(checkout: Path, capsys) -> None:
    bad = checkout / "bad.pdf"
    bad.write_bytes(b"%PDF-not-a-document")
    assert main(["pdf", "intake", "--pdf", str(bad), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"
    enc = checkout / "enc.pdf"
    enc.write_bytes(pdf_bytes(pages=1, encrypt=True))
    assert main(["pdf", "intake", "--pdf", str(enc), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"
    empty = checkout / "empty.pdf"
    empty.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert main(["pdf", "intake", "--pdf", str(empty), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"
    huge = checkout / "pages.pdf"
    huge.write_bytes(pdf_bytes(pages=301))
    assert main(["pdf", "intake", "--pdf", str(huge), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"


def test_intake_symlink_fifo_hardlink(checkout: Path, capsys) -> None:
    pdf = write_pdf(checkout / "paper.pdf")
    link = checkout / "link.pdf"
    link.symlink_to(pdf)
    assert main(["pdf", "intake", "--pdf", str(link), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"
    fifo = checkout / "fifo.pdf"
    os.mkfifo(fifo)
    assert main(["pdf", "intake", "--pdf", str(fifo), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"
    hard = checkout / "hard.pdf"
    os.link(pdf, hard)
    assert os.stat(pdf).st_nlink == 2
    assert main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 2
    assert stdout_json(capsys)["error"]["code"] == "MANUAL_PDF_INVALID"


def test_intake_binding_conflict(checkout: Path, capsys) -> None:
    pdf = write_pdf(checkout / "paper.pdf")
    other = write_pdf(checkout / "other.pdf", pages=2)
    assert main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION, "--paper-id", "arxiv:2311.15127"]) == 0
    stdout_json(capsys)
    assert main(["pdf", "intake", "--pdf", str(other), "--session", SESSION, "--paper-id", "arxiv:2311.15127"]) == 2
    assert stdout_json(capsys)["error"]["code"] == "INTAKE_BINDING_MISMATCH"


def test_intake_source_replacement_changes_identity(checkout: Path, capsys) -> None:
    pdf = write_pdf(checkout / "paper.pdf")
    before = pdf.stat()
    replacement = checkout / "paper.pdf.replaced"
    replacement.write_bytes(pdf.read_bytes())
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, pdf)
    named = pdf.stat()
    assert (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)
    assert main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    stdout_json(capsys)
