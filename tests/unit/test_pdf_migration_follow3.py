"""FOLLOW3 regressions for DRIVE-B REJECT of c05e28f (late page install race)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.pdf_samples import sample_pdf_bytes
from tests.support import make_checkout
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_locations import sha256_bytes
from video_paper_wiki.pdf_migration import (
    PDF_APPLY_CHANGED,
    PdfMigrationError,
    apply_plan_to_root,
    build_inventory,
    build_report,
    parse_roots,
    prepare_migration,
    prepare_unverified_link,
)
from video_paper_wiki.staging import resolve_checkout_root

FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
DRIVE_A = "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW"
USER_EDIT = b"CONCURRENT USER EDIT AT INSTALL\n"


def _write_roots(path: Path, rows: list[dict[str, str]]) -> Path:
    dest = path / "roots.json"
    dest.write_text(json.dumps({"roots": rows}), encoding="utf-8")
    return dest


def _manifest_for(item: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "video-paper-wiki.pdf-upload-manifest.v1",
        "inventory_sha256": None,
        "drive_root_folder_id": DRIVE_A,
        "entries": [
            {
                "item_id": item["item_id"],
                "result": "reused",
                "drive_file_id": FILE_ID,
                "drive_url": f"https://drive.google.com/file/d/{FILE_ID}/view",
                "root_folder_id": DRIVE_A,
                "parent_chain": [{"folder_id": DRIVE_A, "name": "pdfs"}],
                "drive_relative_path": item["drive_relative_path"],
                "remote_size_bytes": item["size_bytes"],
                "remote_pdf_sha256": item["pdf_sha256"],
                "verified_at": "2026-09-20T00:00:00Z",
                "error": None,
            }
        ],
    }


def _verified_notes_plan(tmp_path: Path, *, batch_prefix: str) -> dict[str, object]:
    vault = tmp_path / "notes"
    vault.mkdir()
    page = vault / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Paper\n\nUser notes\n", encoding="utf-8")
    data = sample_pdf_bytes("tiny")
    digest = sha256_bytes(data)
    captured = vault / ".raw" / "captured" / digest
    captured.parent.mkdir(parents=True, exist_ok=True)
    captured.write_bytes(data)
    record = vault / "wiki" / "meta" / "records" / "papers" / "arxiv-2204.03458.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"paper_id": "arxiv:2204.03458", "pdf_sha256": digest}), encoding="utf-8")
    roots = _write_roots(
        tmp_path,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id=f"{batch_prefix}-inv")
    item = next(row for row in inventory["items"] if row["status"] == "included")
    manifest = _manifest_for(item)
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    man_path = tmp_path / "manifest.json"
    man_path.write_bytes(canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / f"{batch_prefix}-inv" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id=f"{batch_prefix}-plan",
    )
    return {
        "vault": vault,
        "roots": roots,
        "plan": plan,
        "plan_path": Path(resolve_checkout_root()) / ".work" / f"{batch_prefix}-plan" / "pdf-migration" / "plan.json",
        "page": page,
        "item": item,
    }


def _apply_with_page_edit_at_install(
    plan: dict[str, object],
    roots_path: Path,
    page: Path,
    location: Path,
    observed: dict[str, object],
) -> None:
    raw_replace = os.replace

    def edit_before_page_install(src, dst, *args, **kwargs):
        if Path(dst) == page and not observed:
            current = page.read_bytes()
            edited = current + USER_EDIT
            page.write_bytes(edited)
            observed.update(
                location_already_installed=location.is_file(),
                page_temp_complete=Path(src).is_file(),
            )
        return raw_replace(src, dst, *args, **kwargs)

    parsed = parse_roots(json.loads(roots_path.read_text(encoding="utf-8")))
    with patch.object(os, "replace", edit_before_page_install):
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="notes-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )


def test_page_edit_at_install_preserves_user_text(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    page = vault / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Paper\n\nUser notes\n", encoding="utf-8")
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="install-edit-link",
        drive_file_id=FILE_ID,
    )
    location = vault / plan["items"][0]["location_path"]
    observed: dict[str, object] = {}
    with pytest.raises(PdfMigrationError) as exc:
        _apply_with_page_edit_at_install(plan, roots, page, location, observed)
    assert exc.value.code == PDF_APPLY_CHANGED
    assert observed["location_already_installed"] is True
    assert observed["page_temp_complete"] is True
    assert USER_EDIT in page.read_bytes()
    assert not location.exists()


def test_verified_page_edit_at_install_report_is_not_done(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    setup = _verified_notes_plan(tmp_path, batch_prefix="install-ver")
    plan = setup["plan"]
    page = setup["page"]
    location = setup["vault"] / plan["items"][0]["location_path"]
    observed: dict[str, object] = {}
    with pytest.raises(PdfMigrationError) as exc:
        _apply_with_page_edit_at_install(plan, setup["roots"], page, location, observed)
    assert exc.value.code == PDF_APPLY_CHANGED
    assert observed["location_already_installed"] is True
    assert observed["page_temp_complete"] is True
    assert USER_EDIT in page.read_bytes()
    assert not location.exists()
    report = build_report(plan_path=setup["plan_path"], roots_path=setup["roots"])
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0
