from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.research.conftest import SESSION, stdout_json, write_pdf
from tests.support import make_checkout
from video_paper_wiki_research.cli import main as research_main
from video_paper_wiki_research.storage import open_research_session


def test_named_directory_replacement_is_unsafe(checkout: Path, capsys) -> None:
    pdf = write_pdf(checkout / "paper.pdf")
    with pytest.raises(Exception) as exc:
        with open_research_session(SESSION) as session:
            output = session.output_root
            outside = checkout / "replacement-manual-pdf"
            outside.mkdir()
            os.replace(output, checkout / "old-manual-pdf")
            os.replace(outside, output)
            session.verify()
    assert getattr(exc.value, "code", None) == "WORK_PATH_UNSAFE"
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", "fresh"]) == 0
    stdout_json(capsys)


def test_commands_do_not_touch_vault_or_catalog(checkout: Path, capsys) -> None:
    vault = checkout / "vault"
    vault.mkdir()
    (vault / "keep.txt").write_text("untouched\n", encoding="utf-8")
    catalog = checkout / "catalog"
    catalog.mkdir()
    (catalog / "keep.json").write_text("{}\n", encoding="utf-8")
    before_vault = {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    before_catalog = {path: path.read_bytes() for path in catalog.rglob("*") if path.is_file()}
    pdf = write_pdf(checkout / "paper.pdf")
    assert research_main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION]) == 0
    stdout_json(capsys)
    after_vault = {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    after_catalog = {path: path.read_bytes() for path in catalog.rglob("*") if path.is_file()}
    assert after_vault == before_vault
    assert after_catalog == before_catalog


def test_work_root_symlink_is_unsafe(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-work"
    outside.mkdir()
    (checkout / ".work").symlink_to(outside)
    pdf = write_pdf(checkout / "paper.pdf")
    from video_paper_wiki_research.cli import main

    code = main(["pdf", "intake", "--pdf", str(pdf), "--session", SESSION])
    assert code == 2
    assert list(outside.iterdir()) == []
