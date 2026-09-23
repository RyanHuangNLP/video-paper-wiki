"""Notes-vault explicit PDF bind: prepare, inventory, migrate, refuse, rollback."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.pdf_samples import sample_pdf_bytes
from tests.support import make_checkout
from video_paper_wiki.cli import main
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.pdf_bindings import (
    PDF_BIND_INVALID,
    SOURCE_PAGE_NOTICE,
    PdfBindingError,
    apply_bind_plan,
    prepare_bindings,
    rollback_bind_journal,
)
from video_paper_wiki.pdf_locations import PDF_CONTENT_CONFLICT, sha256_bytes
from video_paper_wiki.pdf_migration import build_inventory, build_report, prepare_migration, prepare_unverified_link
from video_paper_wiki.staging import resolve_checkout_root
from video_paper_wiki_research.manual_pdf import intake_pdf
from video_paper_wiki_research.storage import open_research_session

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "docs" / "seed" / "engine-mvp.json"
FILE_ID = "1AbCdefGhijkLMNOPqrstUVwxyz0123456"
NOTES_ID = "notes-vault"
CACHE_ID = "pdf-cache"
REPO_ID = "seed-repo"
PAPER = "arxiv:2204.03458"
OTHER = "arxiv:2209.14792"
OUTSIDE = "arxiv:2303.12346"


def _identity(paper_id: str) -> dict[str, str]:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    alias = "arxiv-" + paper_id.split(":", 1)[1]
    row = next(item for item in payload["papers"] if item["paper_id"] == alias)
    return {
        "method": "seed-catalog",
        "seed_paper_id": alias,
        "arxiv_id": row["arxiv_id"],
        "title": row["title"],
    }


def _pdf(name: str) -> bytes:
    base = sample_pdf_bytes("tiny")
    if name == "a":
        return base
    return base + f"\n%bind-{name}\n".encode("ascii")


def _world(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    notes = tmp_path / "notes"
    cache = tmp_path / "cache"
    repo = tmp_path / "repository"
    notes.mkdir()
    cache.mkdir()
    (repo / "docs" / "seed").mkdir(parents=True)
    shutil.copyfile(SEED, repo / "docs" / "seed" / "engine-mvp.json")
    roots = {
        "roots": [
            {"root_id": NOTES_ID, "kind": "notes-vault", "path": str(notes), "role": "target"},
            {"root_id": CACHE_ID, "kind": "file-cache", "path": str(cache), "role": "source-only"},
            {"root_id": REPO_ID, "kind": "repository", "path": str(repo), "role": "source-only"},
        ]
    }
    roots_path = tmp_path / "roots.json"
    roots_path.write_text(json.dumps(roots), encoding="utf-8")
    return {"notes": notes, "cache": cache, "repo": repo, "roots": roots_path}


def _intake(pdf: Path, paper_id: str, session: str) -> str:
    with open_research_session(session) as research:
        staged = intake_pdf(research, pdf, paper_id=paper_id)
    path = Path(staged["path"]).resolve()
    return path.relative_to(resolve_checkout_root().resolve()).as_posix()


def _request_item(pdf_path: Path, paper_id: str, *, session: str, basis: str = "seed", note_sha: str | None = None) -> dict:
    data = pdf_path.read_bytes()
    identity = _identity(paper_id)
    if basis == "seed":
        basis_doc = {
            "kind": "seed",
            "root_id": REPO_ID,
            "relative_path": "docs/seed/engine-mvp.json",
            "scanned_sha256": sha256_bytes(SEED.read_bytes()),
        }
    else:
        alias = "arxiv-" + paper_id.split(":", 1)[1]
        basis_doc = {
            "kind": "existing-note",
            "root_id": NOTES_ID,
            "relative_path": f"papers/{alias}.md",
            "scanned_sha256": note_sha,
        }
    return {
        "paper_id": paper_id,
        "identity_basis": basis_doc,
        "intake": {"relative_path": _intake(pdf_path, paper_id, session)},
        "local_ref": {"root_id": CACHE_ID, "relative_path": pdf_path.name},
        "pdf_sha256": sha256_bytes(data),
        "size_bytes": len(data),
        "identity_credential": identity,
    }


def _write_request(tmp_path: Path, items: list[dict], name: str = "request.json") -> Path:
    path = tmp_path / name
    path.write_bytes(canonicalize({"schema": "video-paper-wiki.pdf-bind-request.v1", "items": items}))
    return path


def _prepare(world: dict[str, Path], request: Path, batch: str) -> dict:
    return prepare_bindings(
        roots_path=world["roots"],
        root_id=NOTES_ID,
        request_path=request,
        batch_id=batch,
    )


def _plant(cache: Path, name: str, data: bytes) -> Path:
    path = cache / name
    path.write_bytes(data)
    return path


def test_chain(tmp_path, monkeypatch, capsys) -> None:
    world = _world(tmp_path, monkeypatch)
    data = _pdf("a")
    pdf = _plant(world["cache"], "arxiv-2209.14792.pdf", data)
    _plant(world["cache"], "same-bytes-other-name.pdf", data)
    before = {path.relative_to(world["notes"]).as_posix() for path in world["notes"].rglob("*") if path.is_file()}
    request = _write_request(tmp_path, [_request_item(pdf, OTHER, session="bind-create")])
    code = main(
        [
            "pdf",
            "bind-prepare",
            "--roots",
            str(world["roots"]),
            "--root-id",
            NOTES_ID,
            "--request",
            str(request),
            "--batch-id",
            "bind-create",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["ok"] is True and payload["command"] == "pdf.bind-prepare"
    plan = payload["data"]
    assert plan["blocked"] == []
    assert plan["items"][0]["page_action"] == "create"
    assert SOURCE_PAGE_NOTICE in plan["items"][0]["page_text"]
    assert {path.relative_to(world["notes"]).as_posix() for path in world["notes"].rglob("*") if path.is_file()} == before
    staged = tmp_path / ".work" / "bind-create" / "pdf-bind" / "plan.json"
    assert staged.is_file()
    assert (tmp_path / ".work" / "bind-create" / "pdf-bind" / "diff.json").is_file()
    applied = apply_bind_plan(
        plan_path=staged,
        roots_path=world["roots"],
        root_id=NOTES_ID,
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )
    page = world["notes"] / "papers" / "arxiv-2209.14792.md"
    binding = world["notes"] / "wiki" / "meta" / "pdf-bindings" / "arxiv-2209.14792.json"
    assert page.read_text(encoding="utf-8").count(SOURCE_PAGE_NOTICE) == 1
    assert "一句话结论" not in page.read_text(encoding="utf-8")
    assert not (world["notes"] / ".raw").exists()
    document = json.loads(binding.read_text(encoding="utf-8"))
    assert document["registration"] == {
        "role": "pdf-location-source",
        "capture_authorized": False,
        "receipt_backed": False,
    }
    created = page.read_bytes()
    again = apply_bind_plan(
        plan_path=staged,
        roots_path=world["roots"],
        root_id=NOTES_ID,
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )
    assert again["results"][0]["state"] == "bound"
    assert page.read_bytes() == created
    inventory = build_inventory(roots_path=world["roots"], batch_id="after-bind")
    included = [item for item in inventory["items"] if item["status"] == "included" and item["paper_id"] == OTHER]
    assert len(included) == 1
    copies = included[0]["local_copies"]
    assert copies == [
        {
            "root_id": CACHE_ID,
            "relative_path": "arxiv-2209.14792.pdf",
            "pdf_sha256": sha256_bytes(data),
            "size_bytes": len(data),
        }
    ]
    assert all(row["root_id"] == NOTES_ID for row in included[0]["bindings"])
    assert inventory["counts"]["included"] == 1
    manifest = {
        "schema": "video-paper-wiki.pdf-upload-manifest.v1",
        "inventory_sha256": inventory["inventory_sha256"],
        "drive_root_folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW",
        "entries": [
            {
                "item_id": included[0]["item_id"],
                "result": "reused",
                "drive_file_id": FILE_ID,
                "drive_url": f"https://drive.google.com/file/d/{FILE_ID}/view",
                "root_folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW",
                "parent_chain": [{"folder_id": "1eN75WhQ-t_yf_Pud80Toi-1j6C9_aVcW", "name": "pdfs"}],
                "drive_relative_path": included[0]["drive_relative_path"],
                "remote_size_bytes": included[0]["size_bytes"],
                "remote_pdf_sha256": included[0]["pdf_sha256"],
                "verified_at": "2026-09-20T00:00:00Z",
                "error": None,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(canonicalize(manifest))
    migrated = prepare_migration(
        inventory_path=tmp_path / ".work" / "after-bind" / "pdf-migration" / "inventory.json",
        manifest_path=manifest_path,
        roots_path=world["roots"],
        batch_id="migrate-after-bind",
    )
    assert migrated["items"][0]["verification"] == "verified"
    assert migrated["items"][0]["page_path"] == "papers/arxiv-2209.14792.md"
    refs = migrated["items"][0]["location"]["pdfs"][0]["local_refs"]
    assert {"root_id": CACHE_ID, "relative_path": "arxiv-2209.14792.pdf"} in refs
    from video_paper_wiki.pdf_locations import parse_roots
    from video_paper_wiki.pdf_migration import apply_plan_to_root

    migrate_result = apply_plan_to_root(
        plan=migrated,
        roots=parse_roots(json.loads(world["roots"].read_text(encoding="utf-8"))),
        root_id=NOTES_ID,
        approved_plan_sha256=migrated["plan_sha256"],
        confirm=True,
    )
    report = build_report(
        plan_path=tmp_path / ".work" / "migrate-after-bind" / "pdf-migration" / "plan.json",
        roots_path=world["roots"],
    )
    assert report["items"][0]["state"] == "linked"
    link = prepare_unverified_link(
        roots_path=world["roots"],
        root_id=NOTES_ID,
        paper_id=OTHER,
        batch_id="still-unverified",
        drive_file_id="1AbCdefGhijkLMNOPqrstUVwxyz0123457",
    )
    assert link["items"][0]["verification"] == "unverified"
    with pytest.raises(PdfBindingError) as reverse:
        rollback_bind_journal(journal_path=Path(applied["journal_path"]), roots_path=world["roots"], confirm=True)
    assert reverse.value.code == "PDF_ROLLBACK_CONFLICT"
    from video_paper_wiki.pdf_migration import rollback_journal

    rollback_journal(journal_path=Path(migrate_result["journal_path"]), roots_path=world["roots"], confirm=True)
    assert page.read_text(encoding="utf-8").count(SOURCE_PAGE_NOTICE) == 1
    rolled = rollback_bind_journal(journal_path=Path(applied["journal_path"]), roots_path=world["roots"], confirm=True)
    assert not page.exists()
    assert not binding.exists()
    assert pdf.read_bytes() == data
    assert (world["cache"] / "same-bytes-other-name.pdf").read_bytes() == data
    assert "papers/arxiv-2209.14792.md" in rolled["restored"]


def test_existing_note_is_preserved_and_basis_can_be_the_note(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    note = world["notes"] / "papers" / "arxiv-2204.03458.md"
    note.parent.mkdir()
    body = "---\npaper_id: arxiv-2204.03458\ntitle: Video Diffusion Models\n---\n\nUSER BODY STAYS\n"
    note.write_text(body, encoding="utf-8")
    pdf = _plant(world["cache"], "arxiv-2204.03458.pdf", _pdf("note"))
    request = _write_request(
        tmp_path,
        [_request_item(pdf, PAPER, session="bind-note", basis="existing-note", note_sha=sha256_bytes(note.read_bytes()))],
    )
    plan = _prepare(world, request, "bind-note")
    assert plan["items"][0]["page_action"] == "preserve"
    assert plan["items"][0]["page_text"] is None
    apply_bind_plan(
        plan_path=tmp_path / ".work" / "bind-note" / "pdf-bind" / "plan.json",
        roots_path=world["roots"],
        root_id=NOTES_ID,
        approved_plan_sha256=plan["plan_sha256"],
        confirm=True,
    )
    assert note.read_text(encoding="utf-8") == body
    assert (world["notes"] / "wiki" / "meta" / "pdf-bindings" / "arxiv-2204.03458.json").is_file()


def test_refuses_scope_intake_only_digest_cross_paper_symlink_and_escape(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    pdf = _plant(world["cache"], "arxiv-2204.03458.pdf", _pdf("a"))
    other_pdf = _plant(world["cache"], "arxiv-2209.14792.pdf", _pdf("b"))
    outside = _write_request(
        tmp_path,
        [
            {
                "paper_id": OUTSIDE,
                "identity_basis": {
                    "kind": "seed",
                    "root_id": REPO_ID,
                    "relative_path": "docs/seed/engine-mvp.json",
                    "scanned_sha256": sha256_bytes(SEED.read_bytes()),
                },
                "intake": {
                    "relative_path": ".work/research/bind-outside/manual-pdf/intakes/" + ("ab" * 32) + ".json"
                },
                "local_ref": {"root_id": CACHE_ID, "relative_path": pdf.name},
                "pdf_sha256": sha256_bytes(pdf.read_bytes()),
                "size_bytes": pdf.stat().st_size,
                "identity_credential": _identity(OUTSIDE),
            }
        ],
        "outside.json",
    )
    with pytest.raises(PdfBindingError) as scope:
        _prepare(world, outside, "bind-outside")
    assert scope.value.code == PDF_BIND_INVALID and scope.value.details["reason"] == "out_of_scope"

    item = _request_item(pdf, PAPER, session="bind-title")
    item["identity_credential"]["title"] = "Not The Seed Title"
    titled = _write_request(tmp_path, [item], "title.json")
    with pytest.raises(PdfBindingError) as intake_only:
        _prepare(world, titled, "bind-title")
    assert intake_only.value.details["reason"] == "intake_only"

    wrong = _request_item(pdf, PAPER, session="bind-digest")
    wrong["pdf_sha256"] = "d" * 64
    with pytest.raises(PdfBindingError) as digest:
        _prepare(world, _write_request(tmp_path, [wrong], "digest.json"), "bind-digest")
    assert digest.value.code == PDF_CONTENT_CONFLICT and digest.value.details["reason"] == "digest_mismatch"

    crossed = _request_item(other_pdf, OTHER, session="bind-cross")
    crossed["intake"] = _request_item(pdf, PAPER, session="bind-cross-intake")["intake"]
    with pytest.raises(PdfBindingError) as cross:
        _prepare(world, _write_request(tmp_path, [crossed], "cross.json"), "bind-cross")
    assert cross.value.details["reason"] == "cross_paper"

    link = world["cache"] / "linked.pdf"
    link.symlink_to(pdf.name)
    linked = _request_item(pdf, PAPER, session="bind-link")
    linked["local_ref"]["relative_path"] = "linked.pdf"
    with pytest.raises(PdfBindingError) as symlink:
        _prepare(world, _write_request(tmp_path, [linked], "link.json"), "bind-link")
    assert symlink.value.details["reason"] == "symlink"

    escaped = {
        "schema": "video-paper-wiki.pdf-bind-request.v1",
        "items": [
            {
                **_request_item(pdf, PAPER, session="bind-escape"),
                "local_ref": {"root_id": CACHE_ID, "relative_path": "../notes/secret.pdf"},
            }
        ],
    }
    escape_path = tmp_path / "escape.json"
    escape_path.write_bytes(canonicalize(escaped))
    with pytest.raises(ContractError):
        _prepare(world, escape_path, "bind-escape")


def test_parallel_edit_stale_seed_root_swap_and_partial_preflight(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    note = world["notes"] / "papers" / "arxiv-2204.03458.md"
    note.parent.mkdir()
    note.write_text("---\npaper_id: arxiv-2204.03458\n---\nkeep\n", encoding="utf-8")
    pdf = _plant(world["cache"], "arxiv-2204.03458.pdf", _pdf("edit"))
    request = _write_request(
        tmp_path,
        [_request_item(pdf, PAPER, session="bind-edit", basis="existing-note", note_sha=sha256_bytes(note.read_bytes()))],
    )
    plan = _prepare(world, request, "bind-edit")
    note.write_text(note.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    with pytest.raises(PdfBindingError) as edited:
        apply_bind_plan(
            plan_path=tmp_path / ".work" / "bind-edit" / "pdf-bind" / "plan.json",
            roots_path=world["roots"],
            root_id=NOTES_ID,
            approved_plan_sha256=plan["plan_sha256"],
            confirm=True,
        )
    assert edited.value.code == "PDF_APPLY_CHANGED"
    assert not (world["notes"] / "wiki" / "meta" / "pdf-bindings" / "arxiv-2204.03458.json").exists()

    fresh = _world(tmp_path / "stale", monkeypatch)
    source = _plant(fresh["cache"], "arxiv-2209.14792.pdf", _pdf("stale"))
    stale_request = _write_request(tmp_path / "stale", [_request_item(source, OTHER, session="bind-stale")])
    stale_plan = _prepare(fresh, stale_request, "bind-stale")
    seed_path = fresh["repo"] / "docs" / "seed" / "engine-mvp.json"
    seed_path.write_bytes(seed_path.read_bytes() + b"\n")
    with pytest.raises(PdfBindingError) as stale:
        apply_bind_plan(
            plan_path=tmp_path / "stale" / ".work" / "bind-stale" / "pdf-bind" / "plan.json",
            roots_path=fresh["roots"],
            root_id=NOTES_ID,
            approved_plan_sha256=stale_plan["plan_sha256"],
            confirm=True,
        )
    assert stale.value.details["reason"] in {"stale_seed", "stale_basis"}

    swapped = _world(tmp_path / "swap", monkeypatch)
    swapped_pdf = _plant(swapped["cache"], "arxiv-2209.14792.pdf", _pdf("swap"))
    swap_request = _write_request(tmp_path / "swap", [_request_item(swapped_pdf, OTHER, session="bind-swap")])
    swap_plan = _prepare(swapped, swap_request, "bind-swap")
    swapped["notes"].rename(tmp_path / "swap" / "notes-old")
    (tmp_path / "swap" / "notes").mkdir()
    with pytest.raises(PdfBindingError) as replaced:
        apply_bind_plan(
            plan_path=tmp_path / "swap" / ".work" / "bind-swap" / "pdf-bind" / "plan.json",
            roots_path=swapped["roots"],
            root_id=NOTES_ID,
            approved_plan_sha256=swap_plan["plan_sha256"],
            confirm=True,
        )
    assert replaced.value.details["reason"] == "stale_root"

    both = _world(tmp_path / "both", monkeypatch)
    first = _plant(both["cache"], "arxiv-2204.03458.pdf", _pdf("p1"))
    second = _plant(both["cache"], "arxiv-2209.14792.pdf", _pdf("p2"))
    both_request = _write_request(
        tmp_path / "both",
        [
            _request_item(first, PAPER, session="bind-p1"),
            _request_item(second, OTHER, session="bind-p2"),
        ],
    )
    both_plan = _prepare(both, both_request, "bind-both")
    second.write_bytes(second.read_bytes() + b"%mutated")
    with pytest.raises(PdfBindingError):
        apply_bind_plan(
            plan_path=tmp_path / "both" / ".work" / "bind-both" / "pdf-bind" / "plan.json",
            roots_path=both["roots"],
            root_id=NOTES_ID,
            approved_plan_sha256=both_plan["plan_sha256"],
            confirm=True,
        )
    assert not (both["notes"] / "wiki" / "meta" / "pdf-bindings").exists()


def test_same_bytes_are_not_guessed_without_a_binding(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    _plant(world["cache"], "arxiv-2204.03458.pdf", _pdf("loose"))
    inventory = build_inventory(roots_path=world["roots"], batch_id="no-binding")
    assert all(item["paper_id"] != PAPER or item["status"] != "included" for item in inventory["items"])
    assert any(item["status"] == "intake-only" and item["paper_id"].startswith("sha256:") for item in inventory["items"])


def test_confirm_and_wrong_root_kind(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    pdf = _plant(world["cache"], "arxiv-2209.14792.pdf", _pdf("kind"))
    plan = _prepare(world, _write_request(tmp_path, [_request_item(pdf, OTHER, session="bind-kind")]), "bind-kind")
    with pytest.raises(PdfBindingError) as denied:
        apply_bind_plan(
            plan_path=tmp_path / ".work" / "bind-kind" / "pdf-bind" / "plan.json",
            roots_path=world["roots"],
            root_id=NOTES_ID,
            approved_plan_sha256=plan["plan_sha256"],
            confirm=False,
        )
    assert denied.value.code == "HUMAN_APPROVAL_REQUIRED"
    formal = {
        "roots": [
            {"root_id": "formal", "kind": "formal-vault", "path": str(world["notes"]), "role": "target"},
            {"root_id": CACHE_ID, "kind": "file-cache", "path": str(world["cache"]), "role": "source-only"},
            {"root_id": REPO_ID, "kind": "repository", "path": str(world["repo"]), "role": "source-only"},
        ]
    }
    formal_path = tmp_path / "formal-roots.json"
    formal_path.write_text(json.dumps(formal), encoding="utf-8")
    with pytest.raises(PdfBindingError) as kind:
        prepare_bindings(
            roots_path=formal_path,
            root_id="formal",
            request_path=_write_request(tmp_path, [_request_item(pdf, OTHER, session="bind-formal")], "formal.json"),
            batch_id="bind-formal",
        )
    assert kind.value.details["reason"] == "stale_root"


def test_page_identity_conflict_and_duplicate_digest(tmp_path, monkeypatch) -> None:
    world = _world(tmp_path, monkeypatch)
    note = world["notes"] / "papers" / "arxiv-2204.03458.md"
    note.parent.mkdir()
    note.write_text("---\npaper_id: arxiv-2209.14792\n---\nnope\n", encoding="utf-8")
    pdf = _plant(world["cache"], "arxiv-2204.03458.pdf", _pdf("id"))
    request = _write_request(tmp_path, [_request_item(pdf, PAPER, session="bind-id")])
    with pytest.raises(PdfBindingError) as conflict:
        _prepare(world, request, "bind-id")
    assert conflict.value.details["reason"] == "page_identity_conflict"
    shared = _pdf("shared")
    left = _plant(world["cache"], "left.pdf", shared)
    right = _plant(world["cache"], "right.pdf", shared)
    first = _request_item(left, PAPER, session="bind-left")
    second = _request_item(right, OTHER, session="bind-right")
    second["local_ref"]["relative_path"] = "right.pdf"
    with pytest.raises(PdfBindingError) as same:
        _prepare(world, _write_request(tmp_path, [first, second], "same.json"), "bind-same")
    assert same.value.code == PDF_CONTENT_CONFLICT
