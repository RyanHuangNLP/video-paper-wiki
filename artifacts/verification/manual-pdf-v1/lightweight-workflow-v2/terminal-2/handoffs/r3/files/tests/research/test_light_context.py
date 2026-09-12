from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import (
    LIGHT_CONTEXT_INVALID,
    LIGHT_OUTPUT_CONFLICT,
    LIGHT_SELECTION_INVALID,
    LIGHT_WORKSPACE_MISMATCH,
    export_context,
    import_document,
    render_document,
    validate_live_context,
)
from video_paper_wiki_research.light_index import (
    INDEX_DIRNAME,
    INDEX_FILENAME,
    INDEX_STALE,
    OK,
    build_index,
)
from video_paper_wiki_research.light_qa import INVALID_CITATION, export_qa_context, render_answer

PAPER_A = "sha256:" + SHA_A
PAPER_B = "sha256:" + SHA_B


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Alpha paper", ["Synthetic quasar method evidence."])
    _write_paper(workspace, SHA_B, "Beta paper", ["Nebula writing token evidence."])
    build_index(workspace)
    return workspace


def _answer(context: dict) -> dict:
    chunk = context["evidence"][0]["chunk_id"]
    return {"text": f"Synthetic method [@{chunk}].", "citations": [{"chunk_id": chunk}]}


def _draft(context: dict) -> dict:
    chunk = context["evidence"][0]["chunk_id"]
    return {"markdown": f"Draft cites the method. [@{chunk}]", "citations": [{"chunk_id": chunk}]}


def _index_path(workspace: Path) -> Path:
    return workspace / INDEX_DIRNAME / INDEX_FILENAME


def _load_index(workspace: Path) -> dict:
    return json.loads(_index_path(workspace).read_text(encoding="utf-8"))


def _write_index(workspace: Path, payload: dict) -> None:
    _index_path(workspace).write_bytes(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    )


def _assert_citation_slices(workspace: Path, result: dict) -> None:
    assert result["ok"] is True
    for item in result["citations"]:
        source = workspace / item["markdown_path"]
        markdown = source.read_text(encoding="utf-8")
        quoted = None
        for line in result["markdown"].splitlines():
            if line.startswith("   > "):
                quoted = line[5:]
                break
        evidence_text = None
        start = None
        end = None
        stored = _load_index(workspace)
        for chunk in stored["chunks"]:
            if chunk["chunk_id"] == item["chunk_id"]:
                evidence_text = chunk["text"]
                start = chunk["text_start"]
                end = chunk["text_end"]
                break
        assert evidence_text is not None
        assert markdown[start:end] == evidence_text
        assert item["text_sha256"] == hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
        assert quoted == evidence_text.replace("\n", " ").strip()


def test_valid_export_import_and_live_validation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    assert context["ok"] is True
    assert context["schema"] == "video-paper-wiki.light-context.v1"
    assert context["selected_paper_ids"] == []
    assert context["workspace_root"] == str(workspace.resolve())
    live = validate_live_context(workspace, context)
    assert live == {
        "ok": True,
        "status": OK,
        "index_id": context["index_id"],
        "workspace_root": str(workspace.resolve()),
        "message": live["message"],
    }
    output = tmp_path / "notes" / "qa answer.md"
    rendered = render_document(workspace, context, _answer(context), output=output)
    assert rendered["ok"] is True
    assert not output.exists()
    assert output.parent.exists() is False
    imported = import_document(workspace, context, _answer(context), output=output)
    assert imported["ok"] is True
    assert imported["status"] == OK
    assert Path(imported["path"]) == output.resolve()
    assert output.is_file()
    assert imported["output_sha256"] == _sha(output.read_bytes())
    assert " " in output.name
    assert "<" in imported["markdown"] or "source.md#page-1" in imported["markdown"]
    _assert_citation_slices(workspace, imported)
    writing = export_context(workspace, kind="writing", query="nebula writing", requirements="one paragraph")
    dpath = tmp_path / "notes" / "writing draft.md"
    draft = import_document(workspace, writing, _draft(writing), output=dpath)
    assert draft["ok"] is True
    _assert_citation_slices(workspace, draft)


def test_reproduced_import_gaps_are_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    output = tmp_path / "valid.md"
    control = import_document(workspace, context, _answer(context), output=output)
    assert control["ok"] is True
    assert output.exists()
    original = output.read_bytes()

    tampered = json.loads(json.dumps(context))
    row = tampered["evidence"][0]
    row["text"] = "Synthetic fabricated evidence absent from source."
    row["text_sha256"] = hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
    forged_out = tmp_path / "tampered.md"
    forged = import_document(workspace, tampered, _answer(context), output=forged_out)
    assert forged["ok"] is False
    assert forged["status"] == LIGHT_CONTEXT_INVALID
    assert not forged_out.exists()
    assert output.read_bytes() == original

    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar method evidence", "nebula changed evidence"))
    stale_out = tmp_path / "stale.md"
    stale = import_document(workspace, context, _answer(context), output=stale_out)
    assert stale["ok"] is False
    assert stale["status"] == INDEX_STALE
    assert not stale_out.exists()
    assert output.read_bytes() == original

    rebuilt = build_index(workspace)
    assert rebuilt["ok"] is True
    assert rebuilt["index_id"] != context["index_id"]
    old_out = tmp_path / "old.md"
    after = import_document(workspace, context, _answer(context), output=old_out)
    assert after["ok"] is False
    assert after["status"] == INDEX_STALE
    assert not old_out.exists()
    assert output.read_bytes() == original


def test_finite_score_is_not_source_identity(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    mutated = json.loads(json.dumps(context))
    mutated["evidence"][0]["score"] = float(mutated["evidence"][0]["score"]) + 1.25
    assert validate_live_context(workspace, mutated)["ok"] is True
    mutated["evidence"][0]["score"] = float("nan")
    assert validate_live_context(workspace, mutated)["status"] == LIGHT_CONTEXT_INVALID


def test_legacy_context_without_selected_paper_ids_still_checks_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    found = __import__("video_paper_wiki_research.light_index", fromlist=["search"]).search(workspace, "quasar")
    legacy = export_qa_context("quasar", found)
    assert "selected_paper_ids" not in legacy
    live = validate_live_context(workspace, legacy)
    assert live["ok"] is True
    tampered = json.loads(json.dumps(legacy))
    tampered["evidence"][0]["title"] = "Forged title"
    assert validate_live_context(workspace, tampered)["status"] == LIGHT_CONTEXT_INVALID


def test_workspace_mismatch_and_unused_bad_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    other = tmp_path / "other"
    other.mkdir()
    _write_paper(other, SHA_A, "Alpha paper", ["Synthetic quasar method evidence."])
    build_index(other)
    mismatch = dict(context)
    mismatch["workspace_root"] = str(other.resolve())
    result = validate_live_context(workspace, mismatch)
    assert result["status"] == LIGHT_WORKSPACE_MISMATCH
    unused = json.loads(json.dumps(context))
    unused["evidence"].append(
        {
            **unused["evidence"][0],
            "chunk_id": "chk-unused-bad",
            "text": "unused forged row",
            "text_sha256": hashlib.sha256(b"unused forged row").hexdigest(),
        }
    )
    assert validate_live_context(workspace, unused)["status"] == LIGHT_CONTEXT_INVALID
    extra_out = tmp_path / "unused.md"
    imported = import_document(workspace, unused, _answer(context), output=extra_out)
    assert imported["status"] == LIGHT_CONTEXT_INVALID
    assert not extra_out.exists()


def test_forged_index_and_context_together_are_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    stored = _load_index(workspace)
    stored["chunks"][0]["text"] = "forged together with context"
    stored["chunks"][0]["text_sha256"] = hashlib.sha256(b"forged together with context").hexdigest()
    _write_index(workspace, stored)
    forged = json.loads(json.dumps(context))
    forged["evidence"][0]["text"] = stored["chunks"][0]["text"]
    forged["evidence"][0]["text_sha256"] = stored["chunks"][0]["text_sha256"]
    forged["index_id"] = stored["index_id"]
    live = validate_live_context(workspace, forged)
    assert live["status"] == INDEX_STALE
    out = tmp_path / "together.md"
    imported = import_document(workspace, forged, _answer(context), output=out)
    assert imported["status"] == INDEX_STALE
    assert not out.exists()


def test_identity_field_and_chunk_set_tampering(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    fields = {
        "title": "mutated-title",
        "page": 9,
        "markdown_path": "papers/" + SHA_B + "/source.md",
        "text_start": 0,
        "text_end": 4,
        "chunk_id": "chk-mutated",
        "text_sha256": "a" * 64,
        "markdown_sha256": "b" * 64,
        "source_sha256": "c" * 64,
        "paper_id": PAPER_B,
    }
    for key, value in fields.items():
        mutated = json.loads(json.dumps(context))
        mutated["evidence"][0][key] = value
        assert validate_live_context(workspace, mutated)["status"] == LIGHT_CONTEXT_INVALID
    stored = _load_index(workspace)
    original = json.loads(json.dumps(stored))
    stored["chunks"].append(json.loads(json.dumps(stored["chunks"][0])))
    stored["chunks"][-1]["chunk_id"] = "chk-duplicate-extra"
    stored["chunk_count"] = len(stored["chunks"])
    _write_index(workspace, stored)
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    _write_index(workspace, original)
    stored = json.loads(json.dumps(original))
    stored["chunks"] = stored["chunks"][1:]
    stored["chunk_count"] = len(stored["chunks"])
    _write_index(workspace, stored)
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    _write_index(workspace, original)
    stored = json.loads(json.dumps(original))
    stored["df"]["quasar"] = 99
    _write_index(workspace, stored)
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    _write_index(workspace, original)
    stored = json.loads(json.dumps(original))
    stored["chunks"][0]["token_count"] = 0
    _write_index(workspace, stored)
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    _write_index(workspace, original)
    bad_types = json.loads(json.dumps(context))
    bad_types["evidence"] = [1]
    assert validate_live_context(workspace, bad_types)["status"] == LIGHT_CONTEXT_INVALID
    missing = json.loads(json.dumps(context))
    del missing["evidence"][0]["text"]
    assert validate_live_context(workspace, missing)["status"] == LIGHT_CONTEXT_INVALID


def test_noop_rebuild_keeps_context_and_source_edit_invalidates(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    first = context["index_id"]
    source = workspace / "papers" / SHA_A / "source.md"
    original = source.read_bytes()
    rebuild = build_index(workspace)
    assert rebuild["index_id"] == first
    assert validate_live_context(workspace, context)["ok"] is True
    source.write_bytes(original)
    source.write_text(source.read_text(encoding="utf-8").replace("quasar", "quasar INSERT"))
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    build_index(workspace)
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    source.write_bytes(original)
    build_index(workspace)
    assert validate_live_context(workspace, context)["ok"] is True


def test_delete_paper_and_metadata_edit(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    meta = workspace / "papers" / SHA_A / "source.json"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    payload["title"] = "Edited title"
    meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert validate_live_context(workspace, context)["status"] == INDEX_STALE
    build_index(workspace)
    assert validate_live_context(workspace, context)["status"] in {INDEX_STALE, LIGHT_CONTEXT_INVALID}
    removed = workspace / "papers" / SHA_B
    for child in removed.iterdir():
        child.unlink()
    removed.rmdir()
    later = export_context(workspace, kind="qa", query="quasar method")
    assert later["status"] == INDEX_STALE
    assert export_context(workspace, kind="qa", query="quasar", paper_ids=[PAPER_B])["status"] == LIGHT_SELECTION_INVALID


def test_atomic_create_only_and_preserve_existing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    output = tmp_path / "keep.md"
    output.write_text("old output\n", encoding="utf-8")
    before = output.read_bytes()
    digest = _sha(before)
    conflict = import_document(workspace, context, _answer(context), output=output, overwrite=False)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_OUTPUT_CONFLICT
    assert output.read_bytes() == before
    assert _sha(output.read_bytes()) == digest
    replaced = import_document(workspace, context, _answer(context), output=output, overwrite=True)
    assert replaced["ok"] is True
    assert output.read_bytes() != before
    fresh = tmp_path / "fresh.md"
    created = import_document(workspace, context, _answer(context), output=fresh, overwrite=False)
    assert created["ok"] is True
    again = import_document(workspace, context, _answer(context), output=fresh, overwrite=False)
    assert again["status"] == LIGHT_OUTPUT_CONFLICT
    assert created["output_sha256"] == _sha(fresh.read_bytes())


def test_symlink_and_managed_output_are_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    target = tmp_path / "real.md"
    target.write_text("keep-me\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)
    before = target.read_bytes()
    refused = import_document(workspace, context, _answer(context), output=link)
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_OUTPUT_CONFLICT
    assert target.read_bytes() == before
    assert link.is_symlink()
    managed = workspace / "papers" / SHA_A / "source.md"
    original = managed.read_bytes()
    with pytest.raises(ResearchError) as exc:
        import_document(workspace, context, _answer(context), output=managed)
    assert exc.value.code == "WORKSPACE_INVALID"
    assert managed.read_bytes() == original
    index_target = _index_path(workspace)
    index_before = index_target.read_bytes()
    with pytest.raises(ResearchError) as exc:
        import_document(workspace, context, _answer(context), output=index_target)
    assert exc.value.code == "WORKSPACE_INVALID"
    assert index_target.read_bytes() == index_before


def test_parent_not_created_on_validation_failure(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    tampered = json.loads(json.dumps(context))
    tampered["evidence"][0]["text"] = "nope"
    tampered["evidence"][0]["text_sha256"] = hashlib.sha256(b"nope").hexdigest()
    parent = tmp_path / "missing-parent"
    output = parent / "out.md"
    result = import_document(workspace, tampered, _answer(context), output=output)
    assert result["ok"] is False
    assert not parent.exists()
    assert not output.exists()


def test_io_failure_and_mid_validation_change_preserve_output(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    blocker = tmp_path / "blocked"
    blocker.write_text("not-a-directory", encoding="utf-8")
    output = blocker / "out.md"
    failed = import_document(workspace, context, _answer(context), output=output)
    assert failed["ok"] is False
    assert failed["status"] == LIGHT_OUTPUT_CONFLICT
    assert blocker.is_file()
    keep = tmp_path / "keep-io.md"
    keep.write_text("preserve\n", encoding="utf-8")
    before = keep.read_bytes()
    source = workspace / "papers" / SHA_A / "source.md"
    original = source.read_bytes()
    calls = {"n": 0}
    real = validate_live_context

    def wrapped(workspace_root, context_doc):
        calls["n"] += 1
        result = real(workspace_root, context_doc)
        if calls["n"] == 1:
            source.write_text(source.read_text(encoding="utf-8").replace("quasar", "changed"))
        return result

    monkey = pytest.MonkeyPatch()
    monkey.setattr("video_paper_wiki_research.light_context.validate_live_context", wrapped)
    try:
        changed = import_document(workspace, context, _answer(context), output=keep)
    finally:
        monkey.undo()
        source.write_bytes(original)
    assert changed["ok"] is False
    assert changed["status"] == INDEX_STALE
    assert keep.read_bytes() == before


def test_create_only_race_at_most_one_winner(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    output = tmp_path / "race.md"
    results: list[dict] = []

    def run() -> None:
        results.append(import_document(workspace, context, _answer(context), output=output, overwrite=False))

    workers = [threading.Thread(target=run) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    winners = [item for item in results if item.get("ok") is True]
    assert len(winners) <= 1
    assert output.is_file()
    assert any(item.get("status") == LIGHT_OUTPUT_CONFLICT for item in results) or len(winners) == 1
    if len(winners) == 1:
        assert _sha(output.read_bytes()) == winners[0]["output_sha256"]


def test_render_is_readonly_and_pure_renderer_still_works(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    output = tmp_path / "readonly.md"
    rendered = render_document(workspace, context, _answer(context), output=output)
    assert rendered["ok"] is True
    assert not output.exists()
    assert rendered["path"] == str(output.resolve())
    pure = render_answer(context, _answer(context))
    assert pure["ok"] is True
    assert "papers/" + SHA_A + "/source.md#page-1" in pure["markdown"]


def test_writing_import_gaps_and_bad_citations(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="writing", query="nebula writing", requirements="one paragraph")
    keep = tmp_path / "writing-keep.md"
    keep.write_text("old-writing\n", encoding="utf-8")
    before = keep.read_bytes()
    ok = import_document(workspace, context, _draft(context), output=tmp_path / "writing-ok.md")
    assert ok["ok"] is True
    tampered = json.loads(json.dumps(context))
    tampered["evidence"][0]["text"] = "forged writing evidence"
    tampered["evidence"][0]["text_sha256"] = hashlib.sha256(b"forged writing evidence").hexdigest()
    bad = import_document(workspace, tampered, _draft(context), output=tmp_path / "writing-forged.md")
    assert bad["status"] == LIGHT_CONTEXT_INVALID
    assert not (tmp_path / "writing-forged.md").exists()
    invented = import_document(
        workspace,
        context,
        {"markdown": "Invented [@chk-missing]", "citations": [{"chunk_id": "chk-missing"}]},
        output=tmp_path / "writing-bad-cite.md",
    )
    assert invented["ok"] is False
    assert invented["status"] == INVALID_CITATION
    assert not (tmp_path / "writing-bad-cite.md").exists()
    assert keep.read_bytes() == before


def test_broken_anchors_are_source_invalid_and_export_kind_is_checked(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    md = workspace / "papers" / SHA_A / "source.md"
    md.write_text(md.read_text(encoding="utf-8").replace('<a id="page-1"></a>', ""), encoding="utf-8")
    live = validate_live_context(workspace, context)
    assert live["status"] == "SOURCE_INVALID"
    out = tmp_path / "broken.md"
    imported = import_document(workspace, context, _answer(context), output=out)
    assert imported["status"] == "SOURCE_INVALID"
    assert not out.exists()
    with pytest.raises(ResearchError) as exc:
        export_context(workspace, kind="draft", query="quasar")
    assert exc.value.code == LIGHT_CONTEXT_INVALID


def test_malformed_kind_and_index_fields_are_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    keep = tmp_path / "keep-shape.md"
    keep.write_text("owned\n", encoding="utf-8")
    before = keep.read_bytes()
    bad_kind = json.loads(json.dumps(context))
    bad_kind["kind"] = []
    kind_result = validate_live_context(workspace, bad_kind)
    assert kind_result["ok"] is False
    assert kind_result["status"] == LIGHT_CONTEXT_INVALID
    index_path = _index_path(workspace)
    original_index = index_path.read_bytes()
    payload = _load_index(workspace)
    del payload["papers"][0]["markdown_sha256"]
    _write_index(workspace, payload)
    stale = validate_live_context(workspace, context)
    assert stale["status"] == INDEX_STALE
    imported = import_document(workspace, context, _answer(context), output=tmp_path / "missing-hash.md")
    assert imported["status"] == INDEX_STALE
    assert not (tmp_path / "missing-hash.md").exists()
    overwrite = import_document(workspace, context, _answer(context), output=keep)
    assert overwrite["status"] == INDEX_STALE
    assert keep.read_bytes() == before
    index_path.write_bytes(original_index)


def test_required_context_fields_must_be_well_shaped(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    keep = tmp_path / "keep-schema.md"
    keep.write_text("owned-schema\n", encoding="utf-8")
    before = keep.read_bytes()
    cases = {
        "evidence_null": None,
        "evidence_zero": 0,
        "evidence_false": False,
        "evidence_empty_string": "",
        "missing_evidence": "missing",
        "evidence_empty_list": [],
    }
    for name, value in cases.items():
        mutated = json.loads(json.dumps(context))
        if value == "missing":
            del mutated["evidence"]
        else:
            mutated["evidence"] = value
        live = validate_live_context(workspace, mutated)
        assert live["ok"] is False, name
        assert live["status"] == LIGHT_CONTEXT_INVALID, name
        imported = import_document(workspace, mutated, _answer(context), output=tmp_path / f"{name}.md")
        assert imported["status"] == LIGHT_CONTEXT_INVALID, name
        assert not (tmp_path / f"{name}.md").exists()
    missing_query = json.loads(json.dumps(context))
    del missing_query["query"]
    assert validate_live_context(workspace, missing_query)["status"] == LIGHT_CONTEXT_INVALID
    assert keep.read_bytes() == before


def test_revalidate_after_staging_preserves_or_omits_output(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    context = export_context(workspace, kind="qa", query="quasar method")
    source = workspace / "papers" / SHA_A / "source.md"
    original_source = source.read_bytes()
    original_write = Path.write_bytes

    def _inject(output: Path, *, overwrite: bool, existing: bytes | None) -> dict:
        injected = {"done": False}

        def write_with_source_change(path, data):
            result = original_write(path, data)
            if path.name.endswith(".light-out.tmp") and not injected["done"]:
                injected["done"] = True
                original_write(source, original_source.replace(b"quasar", b"changed-source"))
            return result

        Path.write_bytes = write_with_source_change
        try:
            result = import_document(workspace, context, _answer(context), output=output, overwrite=overwrite)
        finally:
            Path.write_bytes = original_write
            source.write_bytes(original_source)
        assert injected["done"] is True
        leftovers = list(output.parent.glob("*.light-out.tmp"))
        assert leftovers == []
        return result

    keep = tmp_path / "keep-staged.md"
    keep.write_text("user-owned existing output\n", encoding="utf-8")
    before = keep.read_bytes()
    overwritten = _inject(keep, overwrite=True, existing=before)
    assert overwritten["ok"] is False
    assert overwritten["status"] == INDEX_STALE
    assert keep.read_bytes() == before
    assert validate_live_context(workspace, context)["ok"] is True
    created = tmp_path / "new-staged.md"
    create_only = _inject(created, overwrite=False, existing=None)
    assert create_only["ok"] is False
    assert create_only["status"] == INDEX_STALE
    assert not created.exists()


def test_relative_output_uses_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "work space" / "ws"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Alpha paper", ["Synthetic quasar method evidence."])
    build_index(workspace)
    context = export_context(workspace, kind="qa", query="quasar method")
    cwd = tmp_path / "cwd space"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    imported = import_document(workspace, context, _answer(context), output=Path("rel out.md"))
    assert imported["ok"] is True
    target = (cwd / "rel out.md").resolve()
    assert Path(imported["path"]) == target
    assert target.is_file()
    assert "<../work space/ws/papers/" in imported["markdown"] or "<" in imported["markdown"]
