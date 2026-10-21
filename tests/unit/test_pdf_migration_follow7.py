"""FOLLOW7 regressions for DRIVE-B REJECT of 7b01300 (hardlink replace window)."""

from __future__ import annotations

import ast
import errno
import inspect
import json
from pathlib import Path

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
import video_paper_wiki.pdf_migration as pdf_migration

FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
DRIVE_A = "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW"
PDF_APPLY_EXCHANGE_UNAVAILABLE = getattr(
    pdf_migration, "PDF_APPLY_EXCHANGE_UNAVAILABLE", "PDF_APPLY_EXCHANGE_UNAVAILABLE"
)


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


def _force_exchange_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate renameat2 → ENOSYS: dest exchange is unavailable."""

    def _renameat2_enosys(src: Path, dest: Path) -> bool:
        import ctypes

        ctypes.set_errno(errno.ENOSYS)
        return False

    monkeypatch.setattr(pdf_migration, "_try_rename_exchange", _renameat2_enosys)


def _function_name_calls(func: object, name: str) -> int:
    tree = ast.parse(inspect.getsource(func))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id == name:
            count += 1
    return count


def _spy_plain_replace_onto(monkeypatch: pytest.MonkeyPatch, page: Path) -> list[tuple[str, str]]:
    """Record builtin replace calls whose dest is the live page."""

    recorded: list[tuple[str, str]] = []
    real = pdf_migration._OS_REPLACE
    page_key = page.resolve()

    def wrapped(src, dst, *args, **kwargs):
        dest = Path(dst)
        try:
            dest_key = dest.resolve()
        except OSError:
            dest_key = dest
        if dest_key == page_key:
            recorded.append((str(src), str(dst)))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(pdf_migration, "_OS_REPLACE", wrapped)
    return recorded


def _apply_notes(plan: dict[str, object], roots_path: Path) -> None:
    parsed = parse_roots(json.loads(roots_path.read_text(encoding="utf-8")))
    apply_plan_to_root(
        plan=plan,
        roots=parsed,
        root_id="notes-main",
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )


def _assert_safe_exchange_unavailable_outcome(
    *,
    raised: PdfMigrationError | None,
    page: Path,
    location: Path,
    original: bytes,
    planned_after: str,
    page_plain_replaces: list[tuple[str, str]],
) -> None:
    """A: refuse without covering the page. B: succeed only without plain replace."""

    assert page_plain_replaces == []
    if raised is None:
        return
    assert raised.code == PDF_APPLY_CHANGED
    assert raised.details.get("reason") in {None, PDF_APPLY_EXCHANGE_UNAVAILABLE}
    assert page.read_bytes() == original
    assert sha256_bytes(page.read_bytes()) != planned_after
    assert not location.exists()
    assert not page.with_name(page.name + ".displaced-tmp").exists()
    assert not page.with_name(page.name + ".live-displaced-tmp").exists()
    assert not page.with_name(page.name + ".tmp").exists()


def test_exchange_unavailable_refuses_or_preserves_without_plain_replace(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    _force_exchange_unavailable(monkeypatch)
    vault = tmp_path / "notes"
    page = vault / "papers" / "arxiv-2204.03458.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Paper\n\nUser notes\n", encoding="utf-8")
    original = page.read_bytes()
    roots = _write_roots(
        vault,
        [{"root_id": "notes-main", "kind": "notes-vault", "path": str(vault), "role": "target"}],
    )
    plan = prepare_unverified_link(
        roots_path=roots,
        root_id="notes-main",
        paper_id="arxiv:2204.03458",
        batch_id="follow7-exchange-unavailable-link",
        drive_file_id=FILE_ID,
    )
    location = vault / plan["items"][0]["location_path"]
    page_plain_replaces = _spy_plain_replace_onto(monkeypatch, page)
    raised: PdfMigrationError | None = None
    try:
        _apply_notes(plan, roots)
    except PdfMigrationError as exc:
        raised = exc
    _assert_safe_exchange_unavailable_outcome(
        raised=raised,
        page=page,
        location=location,
        original=original,
        planned_after=plan["items"][0]["after_page_sha256"],
        page_plain_replaces=page_plain_replaces,
    )
    if raised is not None:
        assert raised.details.get("reason") == PDF_APPLY_EXCHANGE_UNAVAILABLE


def test_verified_exchange_unavailable_report_is_not_done_unless_atomic(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    _force_exchange_unavailable(monkeypatch)
    setup = _verified_notes_plan(tmp_path, batch_prefix="follow7-exchange-ver")
    plan = setup["plan"]
    page = setup["page"]
    original = page.read_bytes()
    location = setup["vault"] / plan["items"][0]["location_path"]
    page_plain_replaces = _spy_plain_replace_onto(monkeypatch, page)
    raised: PdfMigrationError | None = None
    try:
        _apply_notes(plan, setup["roots"])
    except PdfMigrationError as exc:
        raised = exc
    _assert_safe_exchange_unavailable_outcome(
        raised=raised,
        page=page,
        location=location,
        original=original,
        planned_after=plan["items"][0]["after_page_sha256"],
        page_plain_replaces=page_plain_replaces,
    )
    report = build_report(plan_path=setup["plan_path"], roots_path=setup["roots"])
    if raised is None:
        assert page_plain_replaces == []
        return
    assert raised.details.get("reason") == PDF_APPLY_EXCHANGE_UNAVAILABLE
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0


def test_check_then_plain_replace_window_is_closed_without_hook_timing() -> None:
    """Another dest read or hardlink cannot close hook→replace. Refuse that install."""

    fallback = getattr(pdf_migration, "_install_via_hardlink_witness", None)
    preserve = getattr(pdf_migration, "_install_preserving_displaced", None)
    assert callable(fallback)
    assert callable(preserve)
    assert _function_name_calls(fallback, "_OS_REPLACE") == 0
    assert _function_name_calls(fallback, "_fail") >= 1
    assert "_try_rename_exchange" in inspect.getsource(preserve)
