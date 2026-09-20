"""FOLLOW2 regressions for DRIVE-B REJECT of 2fda4a7."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.pdf_samples import sample_pdf_bytes
from tests.support import make_checkout
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_locations import locations_bytes, roots_digest, sha256_bytes, sha256_json
from video_paper_wiki.pdf_migration import (
    PDF_APPLY_CHANGED,
    PDF_MIGRATION_INVALID,
    PdfMigrationError,
    apply_plan_to_root,
    build_inventory,
    build_report,
    load_uploaded_manifest,
    parse_roots,
    prepare_migration,
    prepare_unverified_link,
)
from video_paper_wiki.staging import resolve_checkout_root
import video_paper_wiki.pdf_migration as pdf_migration

REPO_ROOT = Path(__file__).resolve().parents[2]
FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
DRIVE_A = "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW"
UPSTREAM = REPO_ROOT / "vendor" / "claude-obsidian"


def _operator_module():
    import importlib.util

    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/pdf_migration.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_pdf_follow2_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_roots(path: Path, rows: list[dict[str, str]]) -> Path:
    dest = path / "roots.json"
    dest.write_text(json.dumps({"roots": rows}), encoding="utf-8")
    return dest


def _write_pdf(path: Path) -> tuple[str, int]:
    data = sample_pdf_bytes("tiny")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data), len(data)


def _manifest_for(item: dict[str, object], *, drive_path: str | None = None) -> dict[str, object]:
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
                "drive_relative_path": drive_path or item["drive_relative_path"],
                "remote_size_bytes": item["size_bytes"],
                "remote_pdf_sha256": item["pdf_sha256"],
                "verified_at": "2026-09-20T00:00:00Z",
                "error": None,
            }
        ],
    }


def _verified_notes_plan(tmp_path: Path, *, batch_prefix: str, with_page: bool = True) -> dict[str, object]:
    vault = tmp_path / "notes"
    vault.mkdir()
    if with_page:
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
        "page": vault / "papers" / "arxiv-2204.03458.md",
        "pdf": captured,
        "record": record,
        "item": item,
        "inventory": inventory,
        "manifest_path": man_path,
    }


def _init_formal_vault(vault: Path, operation_id: str) -> None:
    if not (UPSTREAM / "scripts" / "claude-obsidian.py").is_file():
        pytest.skip("pinned upstream is not checked out")
    verify = getattr(pdf_migration, "verify_pinned_upstream_root", None)
    if verify is None:
        pytest.skip("verify_pinned_upstream_root is missing")
    try:
        verify(UPSTREAM)
    except PdfMigrationError as exc:
        pytest.skip(f"upstream pin is not clean: {exc.code}")
    cli = [sys.executable, "-I", "-B", "-X", "utf8", str(UPSTREAM / "scripts" / "claude-obsidian.py")]
    dry = json.loads(
        subprocess.run(
            [*cli, "init", str(vault), "--operation-id", operation_id, "--generated-at", "2026-09-02T00:00:00Z"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    subprocess.run(
        [
            *cli,
            "init",
            str(vault),
            "--operation-id",
            operation_id,
            "--generated-at",
            "2026-09-02T00:00:00Z",
            "--approved-plan-sha256",
            dry["approved_plan_sha256"],
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_roots_digest_binds_path_and_directory_identity(tmp_path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    rows_one = [{"root_id": "notes-main", "kind": "notes-vault", "path": str(first), "role": "target"}]
    rows_two = [{"root_id": "notes-main", "kind": "notes-vault", "path": str(second), "role": "target"}]
    assert roots_digest(parse_roots({"roots": rows_one})) != roots_digest(parse_roots({"roots": rows_two}))
    role_changed = [{"root_id": "notes-main", "kind": "notes-vault", "path": str(first), "role": "source-only"}]
    assert roots_digest(parse_roots({"roots": rows_one})) != roots_digest(parse_roots({"roots": role_changed}))


def test_formal_apply_refuses_source_only_role_after_prepare(tmp_path, monkeypatch) -> None:
    apply_pdf_migration = _operator_module().apply_pdf_migration
    work = tmp_path / "work"
    work.mkdir()
    make_checkout(work)
    monkeypatch.chdir(work)
    vault = tmp_path / "vault"
    _init_formal_vault(vault, "follow2-role")
    roots = _write_roots(
        work,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-role",
        drive_file_id=FILE_ID,
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "formal-role" / "pdf-migration" / "plan.json"
    payload = json.loads(roots.read_text(encoding="utf-8"))
    payload["roots"][0]["role"] = "source-only"
    roots.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PdfMigrationError) as exc:
        apply_pdf_migration(
            plan_path=plan_path,
            roots_path=roots,
            root_id="vault-main",
            approved_plan_sha256=plan["plan_sha256"],
            upstream_root=UPSTREAM,
            confirm=lambda _summary: True,
        )
    assert exc.value.code in {PDF_MIGRATION_INVALID, PDF_APPLY_CHANGED}
    assert not (vault / plan["items"][0]["location_path"]).exists()


def test_formal_apply_refuses_changed_valid_location(tmp_path, monkeypatch) -> None:
    apply_pdf_migration = _operator_module().apply_pdf_migration
    work = tmp_path / "work"
    work.mkdir()
    make_checkout(work)
    monkeypatch.chdir(work)
    vault = tmp_path / "vault"
    _init_formal_vault(vault, "follow2-loc")
    roots = _write_roots(
        work,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-loc",
        drive_file_id=FILE_ID,
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "formal-loc" / "pdf-migration" / "plan.json"
    other = json.loads(json.dumps(plan["items"][0]["location"]))
    other["pdfs"][0]["drive"]["file_id"] = "2AbCdefGhijkLMNOPqrstUVwxyz0123456"
    other["pdfs"][0]["drive"]["url"] = "https://drive.google.com/file/d/2AbCdefGhijkLMNOPqrstUVwxyz0123456/view"
    location = vault / plan["items"][0]["location_path"]
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_bytes(locations_bytes(other))
    before = location.read_bytes()
    with pytest.raises(PdfMigrationError) as exc:
        apply_pdf_migration(
            plan_path=plan_path,
            roots_path=roots,
            root_id="vault-main",
            approved_plan_sha256=plan["plan_sha256"],
            upstream_root=UPSTREAM,
            confirm=lambda _summary: True,
        )
    assert exc.value.code == PDF_APPLY_CHANGED
    assert location.read_bytes() == before


def test_formal_and_notes_refuse_roots_path_relocation(tmp_path, monkeypatch) -> None:
    apply_pdf_migration = _operator_module().apply_pdf_migration
    work = tmp_path / "work"
    work.mkdir()
    make_checkout(work)
    monkeypatch.chdir(work)

    notes = tmp_path / "notes"
    notes.mkdir()
    notes_roots = _write_roots(
        notes,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(notes), "role": "target"}],
    )
    notes_plan = prepare_unverified_link(
        roots_path=notes_roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="notes-reloc",
        drive_file_id=FILE_ID,
    )
    other_notes = tmp_path / "other-notes"
    other_notes.mkdir()
    notes_payload = json.loads(notes_roots.read_text(encoding="utf-8"))
    notes_payload["roots"][0]["path"] = str(other_notes)
    notes_roots.write_text(json.dumps(notes_payload), encoding="utf-8")
    with pytest.raises(PdfMigrationError) as notes_exc:
        apply_plan_to_root(
            plan=notes_plan,
            roots=parse_roots(json.loads(notes_roots.read_text(encoding="utf-8"))),
            root_id="notes-main",
            approved_plan_sha256=notes_plan["plan_sha256"],
            confirm=True,
        )
    assert notes_exc.value.code == PDF_APPLY_CHANGED
    loc_rel = notes_plan["items"][0]["location_path"]
    assert not (notes / loc_rel).exists()
    assert not (other_notes / loc_rel).exists()

    vault = tmp_path / "vault"
    _init_formal_vault(vault, "follow2-reloc")
    other_vault = tmp_path / "other-vault"
    _init_formal_vault(other_vault, "follow2-reloc-other")
    formal_roots = _write_roots(
        work,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    formal_plan = prepare_unverified_link(
        roots_path=formal_roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-reloc",
        drive_file_id=FILE_ID,
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "formal-reloc" / "pdf-migration" / "plan.json"
    formal_payload = json.loads(formal_roots.read_text(encoding="utf-8"))
    formal_payload["roots"][0]["path"] = str(other_vault)
    formal_roots.write_text(json.dumps(formal_payload), encoding="utf-8")
    with pytest.raises(PdfMigrationError) as formal_exc:
        apply_pdf_migration(
            plan_path=plan_path,
            roots_path=formal_roots,
            root_id="vault-main",
            approved_plan_sha256=formal_plan["plan_sha256"],
            upstream_root=UPSTREAM,
            confirm=lambda _summary: True,
        )
    assert formal_exc.value.code == PDF_APPLY_CHANGED
    formal_rel = formal_plan["items"][0]["location_path"]
    assert not (vault / formal_rel).exists()
    assert not (other_vault / formal_rel).exists()


def test_notes_mid_edit_after_location_write_preserves_user_text(tmp_path, monkeypatch) -> None:
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
        batch_id="mid-edit-link",
        drive_file_id=FILE_ID,
    )
    location = vault / plan["items"][0]["location_path"]
    original = page.read_bytes()
    raw_write = pdf_migration._atomic_write

    def edit_after_location(path: Path, data: bytes) -> None:
        raw_write(path, data)
        if path == location:
            page.write_bytes(original + b"CONCURRENT USER EDIT\n")

    parsed = parse_roots(json.loads(roots.read_text(encoding="utf-8")))
    with patch.object(pdf_migration, "_atomic_write", edit_after_location):
        with pytest.raises(PdfMigrationError) as exc:
            apply_plan_to_root(
                plan=plan,
                roots=parsed,
                root_id="notes-main",
                approved_plan_sha256=plan["plan_sha256"],
                confirm=True,
            )
    assert exc.value.code == PDF_APPLY_CHANGED
    assert b"CONCURRENT USER EDIT" in page.read_bytes()
    assert not location.exists()


def test_verified_mid_edit_report_is_not_done(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    setup = _verified_notes_plan(tmp_path, batch_prefix="mid-ver")
    plan = setup["plan"]
    location = setup["vault"] / plan["items"][0]["location_path"]
    page = setup["page"]
    original = page.read_bytes()
    raw_write = pdf_migration._atomic_write

    def edit_after_location(path: Path, data: bytes) -> None:
        raw_write(path, data)
        if path == location:
            page.write_bytes(original + b"CONCURRENT USER EDIT\n")

    parsed = parse_roots(json.loads(setup["roots"].read_text(encoding="utf-8")))
    with patch.object(pdf_migration, "_atomic_write", edit_after_location):
        with pytest.raises(PdfMigrationError) as exc:
            apply_plan_to_root(
                plan=plan,
                roots=parsed,
                root_id="notes-main",
                approved_plan_sha256=plan["plan_sha256"],
                confirm=True,
            )
    assert exc.value.code == PDF_APPLY_CHANGED
    assert b"CONCURRENT USER EDIT" in page.read_bytes()
    assert not location.exists()
    report = build_report(plan_path=setup["plan_path"], roots_path=setup["roots"])
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0


def test_formal_report_rejects_empty_receipt_object(tmp_path, monkeypatch) -> None:
    apply_pdf_migration = _operator_module().apply_pdf_migration
    work = tmp_path / "work"
    work.mkdir()
    make_checkout(work)
    monkeypatch.chdir(work)
    vault = tmp_path / "vault"
    _init_formal_vault(vault, "follow2-receipt")
    data = sample_pdf_bytes("tiny")
    digest = sha256_bytes(data)
    captured = vault / ".raw" / "captured" / digest
    captured.parent.mkdir(parents=True, exist_ok=True)
    captured.write_bytes(data)
    record = vault / "wiki" / "meta" / "records" / "papers" / "arxiv-2204.03458.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"paper_id": "arxiv:2204.03458", "pdf_sha256": digest}), encoding="utf-8")
    page = vault / "wiki" / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# Paper\n\nUser notes\n", encoding="utf-8")
    roots = _write_roots(
        work,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id="receipt-inv")
    item = next(row for row in inventory["items"] if row["status"] == "included")
    manifest = _manifest_for(item)
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    man_path = work / "manifest.json"
    man_path.write_bytes(canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / "receipt-inv" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id="receipt-plan",
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "receipt-plan" / "pdf-migration" / "plan.json"
    result = apply_pdf_migration(
        plan_path=plan_path,
        roots_path=roots,
        root_id="vault-main",
        approved_plan_sha256=plan["plan_sha256"],
        upstream_root=UPSTREAM,
        confirm=lambda _summary: True,
    )
    receipt = vault / result["receipt_path"]
    assert receipt.is_file()
    receipt.write_text("{}\n", encoding="utf-8")
    report = build_report(plan_path=plan_path, roots_path=roots)
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0


def test_real_intake_pdf_is_not_included(tmp_path, monkeypatch) -> None:
    from video_paper_wiki_research.manual_pdf import intake_pdf
    from video_paper_wiki_research.storage import open_research_session

    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(sample_pdf_bytes("tiny"))
    with open_research_session("only-intake") as session:
        intake = intake_pdf(session, pdf, paper_id="arxiv:2204.03458")
    assert intake["state"] == "staged_input"
    assert intake["capture_authorized"] is False
    assert intake["published"] is False
    assert intake["receipt_backed"] is False
    roots = _write_roots(
        tmp_path,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(tmp_path), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id="intake-only")
    assert inventory["counts"]["included"] == 0
    assert all(item["status"] != "included" for item in inventory["items"])
    assert inventory["counts"]["intake_only"] >= 1 or inventory["counts"]["blocked"] >= 1


def test_cross_root_source_pdf_change_refuses_apply(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    setup = _verified_notes_plan(tmp_path, batch_prefix="cross", with_page=True)
    cache = tmp_path / "source-cache"
    cache.mkdir()
    cached = cache / "original.pdf"
    setup["pdf"].replace(cached)
    roots_payload = json.loads(setup["roots"].read_text(encoding="utf-8"))
    roots_payload["roots"].append({"root_id": "cache", "kind": "file-cache", "path": str(cache), "role": "source-only"})
    setup["roots"].write_text(json.dumps(roots_payload), encoding="utf-8")
    inventory = json.loads(
        (Path(resolve_checkout_root()) / ".work" / "cross-inv" / "pdf-migration" / "inventory.json").read_text(
            encoding="utf-8"
        )
    )
    item = next(row for row in inventory["items"] if row["status"] == "included")
    item["local_copies"] = [
        {
            "root_id": "cache",
            "relative_path": "original.pdf",
            "pdf_sha256": item["pdf_sha256"],
            "size_bytes": item["size_bytes"],
        }
    ]
    inventory["roots_sha256"] = roots_digest(parse_roots(roots_payload))
    inventory["inventory_sha256"] = sha256_json(
        {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    )
    new_inv = tmp_path / "inventory-cross.json"
    new_inv.write_bytes(canonicalize(inventory))
    manifest = json.loads(setup["manifest_path"].read_text(encoding="utf-8"))
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    setup["manifest_path"].write_bytes(canonicalize(manifest))
    plan = prepare_migration(
        inventory_path=new_inv,
        manifest_path=setup["manifest_path"],
        roots_path=setup["roots"],
        batch_id="cross-replan",
    )
    copies = plan["items"][0]["input_preconditions"]["local_copies"]
    assert any(row["root_id"] == "cache" for row in copies)
    cached.write_bytes(cached.read_bytes() + b"%CHANGED")
    parsed = parse_roots(json.loads(setup["roots"].read_text(encoding="utf-8")))
    with pytest.raises(PdfMigrationError) as exc:
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="notes-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert exc.value.code == PDF_APPLY_CHANGED
    loc = setup["vault"] / plan["items"][0]["location_path"]
    assert not loc.exists()
    plan_path = Path(resolve_checkout_root()) / ".work" / "cross-replan" / "pdf-migration" / "plan.json"
    report = build_report(plan_path=plan_path, roots_path=setup["roots"])
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0


def test_verified_notes_rerun_is_idempotent(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    setup = _verified_notes_plan(tmp_path, batch_prefix="rerun", with_page=True)
    parsed = parse_roots(json.loads(setup["roots"].read_text(encoding="utf-8")))
    first = apply_plan_to_root(
        plan=setup["plan"],
        roots=parsed,
        root_id="notes-main",
        approved_plan_sha256=setup["plan"]["plan_sha256"],
        confirm=True,
    )
    assert first["results"][0]["state"] == "linked"
    second = apply_plan_to_root(
        plan=setup["plan"],
        roots=parsed,
        root_id="notes-main",
        approved_plan_sha256=setup["plan"]["plan_sha256"],
        confirm=True,
    )
    assert second["results"][0]["state"] == "linked"
    report = build_report(plan_path=setup["plan_path"], roots_path=setup["roots"])
    assert report["counts"]["linked"] == 1


def test_draft_seed_item_id_with_inventory_digest_loads(tmp_path) -> None:
    digest = "b" * 64
    draft = {
        "schema": "video-paper-wiki.pdf-upload-manifest.v1-draft",
        "root_folder_id": DRIVE_A,
        "inventory_sha256": "a" * 64,
        "items": [
            {
                "item_id": "arxiv-2204.03458:" + digest,
                "paper_id": "arxiv-2204.03458",
                "result": "reused",
                "drive_file_id": FILE_ID,
                "drive_url": f"https://drive.google.com/file/d/{FILE_ID}/view",
                "root_folder_id": DRIVE_A,
                "parent_chain": [{"id": DRIVE_A, "title": "video-paper-wiki", "role": "root"}],
                "drive_relative_path": "pdfs/Video Generation/arxiv-2204.03458/original.pdf",
                "remote_size_bytes": 12,
                "remote_pdf_sha256": digest,
                "local_pdf_sha256": digest,
                "verified_at": "2026-09-20T02:15:41Z",
                "error": None,
            }
        ],
    }
    path = tmp_path / "draft-with-digest.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    document, extras = load_uploaded_manifest(path)
    assert document["schema"] == "video-paper-wiki.pdf-upload-manifest.v1"
    assert len(document["entries"][0]["item_id"]) == 64
    assert extras[0]["item_id"] == "arxiv-2204.03458:" + digest
