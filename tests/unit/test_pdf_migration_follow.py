"""FOLLOW regressions for DRIVE-B-R1 REJECT of 0f8249a."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.pdf_samples import sample_pdf_bytes
from tests.support import make_checkout
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_locations import sha256_bytes
from video_paper_wiki.pdf_migration import (
    PDF_APPLY_CHANGED,
    PLAN_HASH_MISMATCH,
    PdfMigrationError,
    apply_plan_to_root,
    build_inventory,
    build_report,
    parse_roots,
    prepare_migration,
    prepare_unverified_link,
)
from video_paper_wiki.staging import resolve_checkout_root
import video_paper_wiki.pdf_migration as pdf_migration

INVENTORY_SHA256_REQUIRED = getattr(pdf_migration, "INVENTORY_SHA256_REQUIRED", "INVENTORY_SHA256_REQUIRED")
PDF_FORMAL_TRANSACTION_REQUIRED = getattr(
    pdf_migration, "PDF_FORMAL_TRANSACTION_REQUIRED", "PDF_FORMAL_TRANSACTION_REQUIRED"
)
PDF_UPSTREAM_INVALID = getattr(pdf_migration, "PDF_UPSTREAM_INVALID", "PDF_UPSTREAM_INVALID")
PDF_UPSTREAM_REQUIRED = getattr(pdf_migration, "PDF_UPSTREAM_REQUIRED", "PDF_UPSTREAM_REQUIRED")
plan_content_digest = getattr(pdf_migration, "plan_content_digest", None)
load_uploaded_manifest = getattr(pdf_migration, "load_uploaded_manifest", None)
verify_pinned_upstream_root = getattr(pdf_migration, "verify_pinned_upstream_root", None)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _operator_module():
    import importlib.util

    path = REPO_ROOT / "operator/src/video_paper_wiki_operator/pdf_migration.py"
    spec = importlib.util.spec_from_file_location("vpwiki_operator_pdf_follow_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
DRIVE_A = "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW"


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


def test_apply_rejects_tampered_location_path_outside_root(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    vault.mkdir()
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="escape-1",
        drive_file_id=FILE_ID,
    )
    approved = plan["plan_sha256"]
    tampered = json.loads(json.dumps(plan))
    tampered["items"][0]["location_path"] = "../escaped-location.json"
    if plan_content_digest is not None:
        assert plan_content_digest(tampered) != tampered["plan_sha256"]
    parsed = parse_roots(json.loads(roots.read_text()))
    with pytest.raises(PdfMigrationError) as exc:
        apply_plan_to_root(
            plan=tampered,
            roots=parsed,
            root_id="notes-main",
            approved_plan_sha256=approved,
            confirm=True,
        )
    assert exc.value.code == PLAN_HASH_MISMATCH
    assert not (tmp_path / "escaped-location.json").exists()
    assert not (vault.parent / "escaped-location.json").exists()


def test_apply_refuses_changed_pdf_and_registration(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    research = tmp_path / "ws"
    paper_dir = research / "papers" / ("a" * 64)
    paper_dir.mkdir(parents=True)
    digest, size = _write_pdf(paper_dir / "original.pdf")
    source = paper_dir / "source.json"
    source.write_text(
        json.dumps(
            {
                "paper_id": "arxiv:2204.03458",
                "source": {"sha256": digest, "path": str(paper_dir / "original.pdf"), "size_bytes": size},
            }
        ),
        encoding="utf-8",
    )
    roots = _write_roots(
        research,
        [{"root_id": "ws-main", "kind": "research-workspace", "path": str(research), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id="chg-inv")
    included = [item for item in inventory["items"] if item["status"] == "included"]
    assert included
    item = included[0]
    manifest = _manifest_for(item)
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    man_path = tmp_path / "manifest.json"
    man_path.write_bytes(canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / "chg-inv" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id="chg-plan",
    )
    (paper_dir / "original.pdf").write_bytes(sample_pdf_bytes("tiny") + b"%changed")
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    parsed = parse_roots(json.loads(roots.read_text()))
    with pytest.raises(PdfMigrationError) as exc:
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="ws-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert exc.value.code == PDF_APPLY_CHANGED
    loc = research / plan["items"][0]["location_path"]
    assert not loc.exists()


def test_page_conflict_does_not_leave_orphan_location_or_done_report(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    page = vault / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\npaper_id: arxiv-2204.03458\n---\nbody\n", encoding="utf-8")
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="atomic-1",
        drive_file_id=FILE_ID,
    )
    page.write_text(page.read_text(encoding="utf-8") + "parallel edit\n", encoding="utf-8")
    parsed = parse_roots(json.loads(roots.read_text()))
    with pytest.raises(PdfMigrationError) as exc:
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="notes-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert exc.value.code == PDF_APPLY_CHANGED
    loc = vault / plan["items"][0]["location_path"]
    assert not loc.exists()
    plan_path = Path(resolve_checkout_root()) / ".work" / "atomic-1" / "pdf-migration" / "plan.json"
    report = build_report(plan_path=plan_path, roots_path=roots)
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0
    assert all(item["state"] != "linked" for item in report["items"])


def test_inventory_excludes_unbound_digest_blob(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    paper = vault / "papers" / "arxiv-2204.03458.md"
    paper.parent.mkdir(parents=True)
    paper.write_text("---\npaper_id: arxiv-2204.03458\n---\n# body\n", encoding="utf-8")
    data = sample_pdf_bytes("tiny")
    digest = sha256_bytes(data)
    blob = vault / ".work" / "blobs" / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(data)
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id="bind-1")
    sha_items = [item for item in inventory["items"] if item["paper_id"].startswith("sha256:")]
    assert sha_items
    assert all(item["status"] != "included" for item in sha_items)
    assert all(item["bindings"] == [] for item in sha_items)
    arxiv = [item for item in inventory["items"] if item["paper_id"] == "arxiv:2204.03458"]
    assert arxiv
    assert arxiv[0]["status"] == "blocked"
    assert arxiv[0]["blockers"][0]["code"] == "SOURCE_MISSING"


def test_prepare_writes_only_bound_roots(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    research = tmp_path / "ws"
    notes = tmp_path / "notes"
    paper_dir = research / "papers" / ("b" * 64)
    paper_dir.mkdir(parents=True)
    digest, size = _write_pdf(paper_dir / "original.pdf")
    (paper_dir / "source.json").write_text(
        json.dumps(
            {
                "paper_id": "arxiv:2204.03458",
                "source": {"sha256": digest, "path": str(paper_dir / "original.pdf"), "size_bytes": size},
            }
        ),
        encoding="utf-8",
    )
    notes.mkdir()
    roots = _write_roots(
        tmp_path,
        [
            {"root_id": "ws-main", "kind": "research-workspace", "path": str(research), "role": "target"},
            {"root_id": "notes-main", "kind": "notes-vault", "path": str(notes), "role": "target"},
        ],
    )
    inventory = build_inventory(roots_path=roots, batch_id="roots-inv")
    included = [item for item in inventory["items"] if item["status"] == "included"]
    assert included
    item = included[0]
    assert {row["root_id"] for row in item["bindings"]} == {"ws-main"}
    manifest = _manifest_for(item)
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    man_path = tmp_path / "manifest.json"
    man_path.write_bytes(canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / "roots-inv" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id="roots-plan",
    )
    assert [row["root_id"] for row in plan["items"]] == ["ws-main"]


def test_prepare_reuses_drive_a_manifest_path(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    research = tmp_path / "ws"
    paper_dir = research / "papers" / ("c" * 64)
    paper_dir.mkdir(parents=True)
    digest, size = _write_pdf(paper_dir / "original.pdf")
    (paper_dir / "source.json").write_text(
        json.dumps(
            {
                "paper_id": "arxiv:2204.03458",
                "source": {"sha256": digest, "path": str(paper_dir / "original.pdf"), "size_bytes": size},
            }
        ),
        encoding="utf-8",
    )
    roots = _write_roots(
        research,
        [{"root_id": "ws-main", "kind": "research-workspace", "path": str(research), "role": "target"}],
    )
    inventory = build_inventory(roots_path=roots, batch_id="path-inv")
    item = next(row for row in inventory["items"] if row["status"] == "included")
    drive_path = "pdfs/Video Generation/arxiv-2204.03458/original.pdf"
    manifest = _manifest_for(item, drive_path=drive_path)
    manifest["inventory_sha256"] = inventory["inventory_sha256"]
    man_path = tmp_path / "manifest.json"
    man_path.write_bytes(canonicalize(manifest))
    inv_path = Path(resolve_checkout_root()) / ".work" / "path-inv" / "pdf-migration" / "inventory.json"
    plan = prepare_migration(
        inventory_path=inv_path,
        manifest_path=man_path,
        roots_path=roots,
        batch_id="path-plan",
    )
    assert plan["items"][0]["location"]["pdfs"][0]["drive"]["relative_path"] == drive_path


def test_link_prepare_dedupes_same_file_id(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "notes"
    vault.mkdir()
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    first = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="dedupe-1",
        drive_file_id=FILE_ID,
    )
    parsed = parse_roots(json.loads(roots.read_text()))
    apply_plan_to_root(
        plan=first,
        roots=parsed,
        root_id="notes-main",
        approved_plan_sha256=first["plan_sha256"],
        confirm=True,
    )
    second = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="dedupe-2",
        drive_url=f"https://drive.google.com/file/d/{FILE_ID}/view",
    )
    apply_plan_to_root(
        plan=second,
        roots=parsed,
        root_id="notes-main",
        approved_plan_sha256=second["plan_sha256"],
        confirm=True,
    )
    from video_paper_wiki.pdf_migration import resolve_from_root

    resolved = resolve_from_root(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        prefer="drive",
        offline=False,
        pdf_sha256=None,
    )
    assert resolved["drive_file_id"] == FILE_ID
    loc = json.loads((vault / first["items"][0]["location_path"]).read_text(encoding="utf-8"))
    assert len(loc["pdfs"]) == 1


def test_draft_manifest_without_inventory_digest_is_refused(tmp_path) -> None:
    draft = {
        "schema": "video-paper-wiki.pdf-upload-manifest.v1-draft",
        "root_folder_id": DRIVE_A,
        "inventory_sha256": None,
        "items": [
            {
                "item_id": "arxiv-2204.03458:" + ("a" * 64),
                "paper_id": "arxiv-2204.03458",
                "result": "reused",
                "drive_file_id": FILE_ID,
                "drive_url": f"https://drive.google.com/file/d/{FILE_ID}/view",
                "root_folder_id": DRIVE_A,
                "parent_chain": [{"id": DRIVE_A, "title": "video-paper-wiki", "role": "root"}],
                "drive_relative_path": "pdfs/Video Generation/arxiv-2204.03458/original.pdf",
                "remote_size_bytes": 12,
                "remote_pdf_sha256": "a" * 64,
                "local_pdf_sha256": "a" * 64,
                "verified_at": "2026-09-20T02:15:41Z",
                "error": None,
            }
        ],
    }
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    assert load_uploaded_manifest is not None
    with pytest.raises(PdfMigrationError) as exc:
        load_uploaded_manifest(path)
    assert exc.value.code == INVENTORY_SHA256_REQUIRED


def test_library_apply_refuses_formal_vault(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "formal"
    vault.mkdir()
    (vault / ".raw").mkdir()
    roots = _write_roots(
        vault,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-lib",
        drive_file_id=FILE_ID,
    )
    parsed = parse_roots(json.loads(roots.read_text()))
    with pytest.raises(PdfMigrationError) as exc:
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="vault-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert exc.value.code == PDF_FORMAL_TRANSACTION_REQUIRED
    assert not (vault / plan["items"][0]["location_path"]).exists()


def test_fake_upstream_does_not_write_formal_locations(tmp_path, monkeypatch) -> None:
    apply_pdf_migration = _operator_module().apply_pdf_migration

    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "formal"
    vault.mkdir()
    (vault / ".raw").mkdir()
    page = vault / "wiki" / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Paper\n", encoding="utf-8")
    roots = _write_roots(
        vault,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-fake",
        drive_file_id=FILE_ID,
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "formal-fake" / "pdf-migration" / "plan.json"
    fake = tmp_path / "not-upstream"
    fake.mkdir()
    with pytest.raises(PdfMigrationError) as missing:
        apply_pdf_migration(
            plan_path=plan_path,
            roots_path=roots,
            root_id="vault-main",
            approved_plan_sha256=plan["plan_sha256"],
            upstream_root=None,
            confirm=lambda _summary: True,
        )
    assert missing.value.code == PDF_UPSTREAM_REQUIRED
    with pytest.raises(PdfMigrationError) as bogus:
        apply_pdf_migration(
            plan_path=plan_path,
            roots_path=roots,
            root_id="vault-main",
            approved_plan_sha256=plan["plan_sha256"],
            upstream_root=fake,
            confirm=lambda _summary: True,
        )
    assert bogus.value.code == PDF_UPSTREAM_INVALID
    assert not (vault / plan["items"][0]["location_path"]).exists()
    assert "Drive PDF" not in page.read_text(encoding="utf-8")


def test_formal_apply_uses_upstream_receipt(tmp_path, monkeypatch) -> None:
    import subprocess
    import sys

    apply_pdf_migration = _operator_module().apply_pdf_migration

    repo = Path(__file__).resolve().parents[2]
    upstream = repo / "vendor" / "claude-obsidian"
    cli = [sys.executable, "-I", "-B", "-X", "utf8", str(upstream / "scripts" / "claude-obsidian.py")]
    if verify_pinned_upstream_root is None:
        pytest.fail("verify_pinned_upstream_root is missing")
    try:
        verify_pinned_upstream_root(upstream)
    except PdfMigrationError as exc:
        pytest.skip(f"upstream pin is not clean: {exc.code}")
    work = tmp_path / "work"
    work.mkdir()
    make_checkout(work)
    monkeypatch.chdir(work)
    vault = tmp_path / "vault"
    dry = json.loads(
        subprocess.run(
            [*cli, "init", str(vault), "--operation-id", "pdf-follow-init", "--generated-at", "2026-09-02T00:00:00Z"],
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
            "pdf-follow-init",
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
    roots = _write_roots(
        work,
        [{"root_id": "vault-main", "kind": "formal-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="vault-main",
        paper_id="arxiv:2204.03458",
        batch_id="formal-real",
        drive_file_id=FILE_ID,
    )
    plan_path = Path(resolve_checkout_root()) / ".work" / "formal-real" / "pdf-migration" / "plan.json"
    result = apply_pdf_migration(
        plan_path=plan_path,
        roots_path=roots,
        root_id="vault-main",
        approved_plan_sha256=plan["plan_sha256"],
        upstream_root=upstream,
        confirm=lambda _summary: True,
    )
    assert result["kind"] == "formal-vault"
    assert result.get("receipt_path")
    assert (vault / result["receipt_path"]).is_file()
    loc = vault / plan["items"][0]["location_path"]
    assert loc.is_file()
    report = build_report(plan_path=plan_path, roots_path=roots)
    applied = report["counts"]["linked"] + report["counts"]["unverified"]
    assert applied == 1
    assert report["items"][0]["state"] in {"linked", "unverified"}
    assert report["status"] in {"PARTIAL", "DONE"}
    assert Path(result["journal_path"]).is_file()


def test_pinned_upstream_helper_accepts_vendor() -> None:
    root = Path(__file__).resolve().parents[2] / "vendor" / "claude-obsidian"
    if not (root / "scripts" / "claude-obsidian.py").is_file():
        pytest.skip("pinned upstream is not checked out")
    if verify_pinned_upstream_root is None:
        pytest.fail("verify_pinned_upstream_root is missing")
    try:
        verified = verify_pinned_upstream_root(root)
    except PdfMigrationError as exc:
        pytest.skip(f"upstream pin is not clean: {exc.code}")
    assert verified == root.resolve()
