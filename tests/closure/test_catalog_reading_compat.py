"""Real reading install reaches upstream strict lint; bad pages still fail it."""

from __future__ import annotations

import os
from pathlib import Path

from tests.contract.test_catalog_reading_compat import seal_receipt_vault
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_reading_apply import _apply_reading, _compile, _prepared
from tests.unit.test_reading_view import _build
from video_paper_wiki.reading_publication import inspect_reading_publication
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER
from video_paper_wiki.upstream_runtime import lint_vault

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "vendor" / "claude-obsidian"


def _frontmatter(title, kind):
    return (
        "---\n"
        f"title: {title}\n"
        f"type: {kind}\n"
        "status: active\n"
        "created: 2026-09-08\n"
        "updated: 2026-09-08\n"
        "tags: [sample]\n"
        "---\n\n"
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def _source_and_page(vault: Path) -> None:
    from tests.contract.test_catalog_reading_compat import _claim_page, _source_ledger

    _source_ledger(vault)
    _claim_page(vault)


def test_reading_apply_passes_strict_lint_and_keeps_user_files(tmp_path, monkeypatch):
    world = make_world(tmp_path, monkeypatch)
    _three_chain(world)
    vault = world["vault"]
    _source_and_page(vault)
    note = vault / "wiki" / "reading-notes" / "user.md"
    unmarked = vault / "wiki" / "reading" / "mine.md"
    _write(unmarked, _frontmatter("Mine", "note") + "# Mine\n\n无生成标记。\n")
    _write(
        note,
        _frontmatter("User note", "note")
        + "# User note\n\n不要覆盖。\n\n[mine](../reading/mine.md)\n\n[论文](../papers/paper.md)\n",
    )
    page = vault / "wiki" / "papers" / "paper.md"
    page.write_text(page.read_text(encoding="utf-8") + "\n[用户笔记](../reading-notes/user.md)\n", encoding="utf-8")
    os.chmod(page, 0o600)
    note_bytes = note.read_bytes()
    unmarked_bytes = unmarked.read_bytes()
    _build(world, "rd1")
    _compile(world, "rd1")
    inspected = inspect_reading_publication(prepared=_prepared(world, "rd1"), vault_root=str(vault))
    assert inspected["staged_verified"] is True
    assert inspected["audit_coverage"] == "not_wired"
    _apply_reading(world, "rd1")
    assert note.read_bytes() == note_bytes
    assert unmarked.read_bytes() == unmarked_bytes
    report = lint_vault(vault_root=vault, upstream_root=UPSTREAM, as_of="2026-09-09")
    findings = {
        name: entries
        for name, entries in report["data"].items()
        if name not in {"version", "engine_version", "as_of", "summary"} and entries
    }
    assert report["exit_code"] == 0, findings
    assert (vault / CLAIM_LEDGER).is_file()


def test_independent_bad_pages_still_fail_strict_lint(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    os.chmod(vault, 0o700)
    _write(vault / "wiki/papers/kept.md", _frontmatter("Kept", "paper") + "# Kept\n\n保留的正式页。\n")
    seal_receipt_vault(vault)
    assert audit_integrity(vault)["classification"] == "receipt_backed"
    _write(vault / "wiki/reading/bare.md", "# Bare\n\n没有前言。\n")
    _write(
        vault / "wiki/reading/dead.md",
        _frontmatter("Dead", "note") + "# Dead\n\n[缺失](does-not-exist.md)\n",
    )
    _write(
        vault / "wiki/reading/index.md",
        _frontmatter("Index", "index") + "# Index\n\n[过期](also-missing.md)\n",
    )
    _write(
        vault / "wiki/reading/nested/index.md",
        _frontmatter("Nested", "index") + "# Nested\n\n另一份 index。\n",
    )
    _write(
        vault / "wiki/reading/empty.md",
        _frontmatter("Empty", "note") + "# Empty\n\n## 空节\n\n# 下一节\n\n还有正文。\n",
    )
    assert audit_integrity(vault)["classification"] == "receipt_backed"
    report = lint_vault(vault_root=vault, upstream_root=UPSTREAM, as_of="2026-09-09")
    counts = report["data"]["summary"]["category_counts"]
    assert report["exit_code"] != 0
    assert counts["missing_frontmatter"] >= 1
    assert counts["dead_links"] >= 1
    assert counts["duplicate_basenames"] >= 1
    assert counts["empty_sections"] >= 1
    assert counts["stale_index_entries"] >= 1
