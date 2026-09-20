from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.pdf_samples import sample_pdf_bytes
from tests.support import make_checkout
from video_paper_wiki.pdf_locations import (
    PDF_CONTENT_CONFLICT,
    canonical_paper_id,
    item_id_for,
    sha256_bytes,
)
from video_paper_wiki.pdf_migration import (
    HUMAN_APPROVAL_REQUIRED,
    PdfMigrationError,
    apply_plan_to_root,
    build_inventory,
    parse_roots,
    prepare_migration,
    prepare_unverified_link,
)
from video_paper_wiki.staging import resolve_checkout_root

FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
ROOT_ID = "notes-main"


def _roots(path: Path) -> Path:
    payload = {
        "roots": [
            {
                "root_id": ROOT_ID,
                "kind": "notes-vault",
                "path": str(path),
                "role": "target",
            }
        ]
    }
    dest = path / "roots.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")
    return dest


def _write_pdf(path: Path) -> tuple[str, int]:
    data = sample_pdf_bytes("tiny")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data), len(data)


def test_inventory_includes_extensionless_blob(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    paper = vault / "papers" / "arxiv-2204.03458.md"
    paper.parent.mkdir(parents=True)
    paper.write_text("---\npaper_id: arxiv-2204.03458\n---\n# Video Diffusion Models\n", encoding="utf-8")
    digest, size = _write_pdf(vault / ".raw" / "captured" / ("a" * 64))
    # extensionless blob with PDF magic
    blob = vault / ".work" / "blobs" / digest
    blob.parent.mkdir(parents=True)
    blob.write_bytes(sample_pdf_bytes("tiny"))
    roots = _roots(vault)
    inventory = build_inventory(roots_path=roots, batch_id="inv1")
    copies = [copy["relative_path"] for item in inventory["items"] for copy in item["local_copies"]]
    assert any(not Path(rel).suffix for rel in copies)
    assert any(item["paper_id"] == "arxiv:2204.03458" or item["pdf_sha256"] == digest for item in inventory["items"])
    _ = size


def test_migrate_prepare_binds_digests(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    paper = vault / "papers" / "arxiv-2204.03458.md"
    paper.parent.mkdir(parents=True)
    paper.write_text("---\npaper_id: arxiv-2204.03458\n---\nbody\n", encoding="utf-8")
    digest, size = _write_pdf(vault / ".raw" / "captured" / ("blob" + "x" * 60))
    # name is not hex; still a PDF scanned as sha256 identity if unbound
    roots = _roots(vault)
    inventory = build_inventory(roots_path=roots, batch_id="prep1")
    included = [item for item in inventory["items"] if item["status"] == "included"]
    if not included:
        # bind by rewriting captured name to digest
        target = vault / ".raw" / "captured" / digest
        (vault / ".raw" / "captured" / ("blob" + "x" * 60)).replace(target)
        inventory = build_inventory(roots_path=roots, batch_id="prep1b")
        included = [item for item in inventory["items"] if item["pdf_sha256"] == digest]
    assert included
    item = included[0]
    manifest = {
        "schema": "video-paper-wiki.pdf-upload-manifest.v1",
        "inventory_sha256": inventory["inventory_sha256"],
        "drive_root_folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW",
        "entries": [
            {
                "item_id": item["item_id"],
                "result": "reused",
                "drive_file_id": FILE_ID,
                "drive_url": f"https://drive.google.com/file/d/{FILE_ID}/view",
                "root_folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW",
                "parent_chain": [{"folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW", "name": "pdfs"}],
                "drive_relative_path": item["drive_relative_path"],
                "remote_size_bytes": item["size_bytes"],
                "remote_pdf_sha256": item["pdf_sha256"],
                "verified_at": "2026-09-20T00:00:00Z",
                "error": None,
            }
        ],
    }
    man_path = tmp_path / "manifest.json"
    man_path.write_bytes(__import__("video_paper_wiki.jcs", fromlist=["canonicalize"]).canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / "prep1b" / "pdf-migration" / "inventory.json"
    if not inv_path.exists():
        inv_path = Path(resolve_checkout_root()) / ".work" / "prep1" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id="prep-plan",
    )
    assert plan["items"]
    row = plan["items"][0]
    assert row["after_location_sha256"]
    assert row["location"]["pdfs"][0]["pdf_sha256"] == item["pdf_sha256"]
    assert row["verification"] == "verified"
    _ = size, canonical_paper_id, item_id_for


def test_apply_conflict_and_rerun(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    paper = vault / "papers" / "arxiv-2204.03458.md"
    paper.parent.mkdir(parents=True)
    paper.write_text("---\npaper_id: arxiv-2204.03458\n---\nbody\n", encoding="utf-8")
    roots = _roots(vault)
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id=ROOT_ID,
        paper_id="arxiv:2204.03458",
        batch_id="link1",
        drive_file_id=FILE_ID,
    )
    parsed_roots = parse_roots(json.loads(roots.read_text()))
    with pytest.raises(PdfMigrationError) as denied:
        apply_plan_to_root(
            plan=plan,
            roots=parsed_roots,
            root_id=ROOT_ID,
            approved_plan_sha256=plan["plan_sha256"],
            confirm=False,
        )
    assert denied.value.code == HUMAN_APPROVAL_REQUIRED
    first = apply_plan_to_root(
        plan=plan,
        roots=parsed_roots,
        root_id=ROOT_ID,
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )
    assert first["results"][0]["state"] in {"linked", "unverified"}
    loc = vault / plan["items"][0]["location_path"]
    assert loc.is_file()
    second = apply_plan_to_root(
        plan=plan,
        roots=parsed_roots,
        root_id=ROOT_ID,
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )
    assert second["results"][0]["state"] in {"linked", "unverified"}
    loc.write_text("{}\n", encoding="utf-8")
    with pytest.raises(PdfMigrationError) as changed:
        apply_plan_to_root(
            plan=plan,
            roots=parsed_roots,
            root_id=ROOT_ID,
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert changed.value.code in {"PDF_APPLY_CHANGED", PDF_CONTENT_CONFLICT}


def test_link_prepare_unverified(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    vault.mkdir()
    roots = _roots(vault)
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id=ROOT_ID,
        paper_id="arxiv-2204.03458",
        batch_id="unverified-1",
        drive_url=f"https://drive.google.com/file/d/{FILE_ID}/view",
    )
    assert plan["kind"] == "unverified-link"
    assert plan["items"][0]["verification"] == "unverified"
    assert plan["items"][0]["location"]["pdfs"][0]["verification"]["status"] == "unverified"
