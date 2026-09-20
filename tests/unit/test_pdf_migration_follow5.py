"""FOLLOW5 regressions for DRIVE-B REJECT of 812a5d7 (native atomic-save race)."""

from __future__ import annotations

import inspect
import json
import os
import select
import subprocess
import sys
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
USER_EDIT = b"CONCURRENT USER EDIT AT NATIVE REPLACE\n"


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


def _apply_with_page_atomic_save_at_native_replace(
    plan: dict[str, object],
    roots_path: Path,
    page: Path,
    location: Path,
    observed: dict[str, object],
) -> None:
    """Independent writer at the real os.rename audit; temp + os.replace, no product patch."""

    original = page.read_bytes()
    page_key = page.resolve()
    primitive = getattr(pdf_migration, "_OS_REPLACE", os.replace)
    observed["native_primitive_is_builtin"] = inspect.isbuiltin(primitive)
    observed["native_primitive_module"] = getattr(primitive, "__module__", None)
    worker_code = r"""
from pathlib import Path
import hashlib, json, os, sys
page, snapshot = map(Path, sys.argv[1:3])
print('READY', flush=True)
assert sys.stdin.readline().strip() == 'EDIT'
edited = page.read_bytes() + b'CONCURRENT USER EDIT AT NATIVE REPLACE\n'
before_inode = page.stat().st_ino
writer_temp = page.with_name(page.name + '.writer-tmp')
with writer_temp.open('xb') as handle:
    handle.write(edited)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(writer_temp, page)
after_inode = page.stat().st_ino
assert before_inode != after_inode
snapshot.write_bytes(edited)
print(json.dumps({'worker_pid': os.getpid(), 'writer_mode': 'atomic-save', 'before_inode': before_inode, 'after_inode': after_inode, 'edited_sha256': hashlib.sha256(edited).hexdigest(), 'edited_size': len(edited)}), flush=True)
"""
    worker = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", worker_code, str(page), str(page.with_name(page.name + ".concurrent"))],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    hook_active = True

    def read_worker_line() -> str:
        if worker.stdout is None or not select.select([worker.stdout], [], [], 10)[0]:
            raise RuntimeError("writer did not respond within 10 seconds; probe invalid")
        return worker.stdout.readline().strip()

    assert read_worker_line() == "READY"

    def before_native_rename(event: str, args: tuple[object, ...]) -> None:
        if not hook_active or event != "os.rename" or observed.get("audit_event"):
            return
        dest = Path(os.fsdecode(args[1])).resolve()
        if dest != page_key:
            return
        src = Path(os.fsdecode(args[0]))
        temp = src.read_bytes()
        item = plan["items"][0]
        observed.update(
            audit_event=event,
            audit_src=str(src),
            audit_dst=str(dest),
            location_already_installed=location.is_file(),
            location_matches_plan=sha256_bytes(location.read_bytes()) == item["after_location_sha256"]
            if location.is_file()
            else False,
            page_temp_complete=src.is_file(),
            page_temp_matches_plan=sha256_bytes(temp) == item["after_page_sha256"],
            before_page_matches_plan=sha256_bytes(page.read_bytes()) == item["before_page_sha256"],
            main_pid=os.getpid(),
        )
        assert worker.stdin is not None
        worker.stdin.write("EDIT\n")
        worker.stdin.flush()
        observed.update(json.loads(read_worker_line()))
        observed["edit_visible_before_syscall"] = page.read_bytes() == original + USER_EDIT
        observed["independent_writer"] = observed["worker_pid"] != os.getpid()
        observed["writer_used_new_inode"] = observed["before_inode"] != observed["after_inode"]
        assert all(
            observed[key]
            for key in (
                "location_already_installed",
                "location_matches_plan",
                "page_temp_complete",
                "page_temp_matches_plan",
                "before_page_matches_plan",
                "edit_visible_before_syscall",
                "independent_writer",
                "native_primitive_is_builtin",
                "writer_used_new_inode",
            )
        )

    sys.addaudithook(before_native_rename)
    try:
        parsed = parse_roots(json.loads(roots_path.read_text(encoding="utf-8")))
        apply_plan_to_root(
            plan=plan,
            roots=parsed,
            root_id="notes-main",
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    finally:
        hook_active = False
        if not observed.get("audit_event"):
            worker.terminate()
        worker.wait(timeout=10)
    if not observed.get("audit_event"):
        raise RuntimeError("native os.rename audit did not fire; probe invalid")


def test_page_atomic_save_at_native_replace_preserves_user_text(tmp_path, monkeypatch) -> None:
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
        batch_id="native-atomic-save-link",
        drive_file_id=FILE_ID,
    )
    location = vault / plan["items"][0]["location_path"]
    observed: dict[str, object] = {}
    with pytest.raises(PdfMigrationError) as exc:
        _apply_with_page_atomic_save_at_native_replace(plan, roots, page, location, observed)
    assert exc.value.code == PDF_APPLY_CHANGED
    assert observed["location_already_installed"] is True
    assert observed["page_temp_complete"] is True
    assert observed["edit_visible_before_syscall"] is True
    assert observed["independent_writer"] is True
    assert observed["native_primitive_is_builtin"] is True
    assert observed["writer_mode"] == "atomic-save"
    assert observed["writer_used_new_inode"] is True
    assert USER_EDIT in page.read_bytes()
    assert not location.exists()


def test_verified_page_atomic_save_at_native_replace_report_is_not_done(tmp_path, monkeypatch) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    setup = _verified_notes_plan(tmp_path, batch_prefix="native-atomic-ver")
    plan = setup["plan"]
    page = setup["page"]
    location = setup["vault"] / plan["items"][0]["location_path"]
    observed: dict[str, object] = {}
    with pytest.raises(PdfMigrationError) as exc:
        _apply_with_page_atomic_save_at_native_replace(plan, setup["roots"], page, location, observed)
    assert exc.value.code == PDF_APPLY_CHANGED
    assert observed["location_already_installed"] is True
    assert observed["location_matches_plan"] is True
    assert observed["page_temp_complete"] is True
    assert observed["page_temp_matches_plan"] is True
    assert observed["before_page_matches_plan"] is True
    assert observed["edit_visible_before_syscall"] is True
    assert observed["independent_writer"] is True
    assert observed["writer_mode"] == "atomic-save"
    assert observed["writer_used_new_inode"] is True
    assert USER_EDIT in page.read_bytes()
    assert not location.exists()
    report = build_report(plan_path=setup["plan_path"], roots_path=setup["roots"])
    assert report["status"] != "DONE"
    assert report["counts"]["linked"] == 0
