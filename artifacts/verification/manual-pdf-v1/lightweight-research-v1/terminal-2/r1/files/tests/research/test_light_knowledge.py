from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import threading
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import SOURCE_INVALID, import_document
from video_paper_wiki_research.light_index import INDEX_STALE, LIGHT_SELECTION_INVALID, OK, build_index
from video_paper_wiki_research.light_knowledge import (
    CURRENT_SCHEMA,
    HEADS_NAME,
    HEADS_SCHEMA,
    KNOWLEDGE_CONTEXT_SCHEMA,
    KNOWLEDGE_DOCUMENT_SCHEMA,
    KNOWLEDGE_PAGE_NAME,
    KNOWLEDGE_STATE_DIR,
    LIGHT_KNOWLEDGE_CONFLICT,
    LIGHT_KNOWLEDGE_INVALID,
    LIGHT_WORKSPACE_BUSY,
    RECORDS_DIRNAME,
    SECTION_KEYS,
    UNKNOWN_TEXT,
    WORKSPACE_INVALID,
    _write_bytes,
    build_knowledge_views,
    export_knowledge_context,
    import_knowledge,
    list_knowledge,
    persisted_bytes,
    sha256_bytes,
    sha256_canonical,
)
from video_paper_wiki_research.light_qa import INSUFFICIENT_EVIDENCE
from video_paper_wiki_research.light_workflow import _exclusive_lock, _workspace_lock_path

PAPER_A = "sha256:" + SHA_A
PAPER_B = "sha256:" + SHA_B


def _workspace(tmp_path: Path, *, pages_a: list[str] | None = None, pages_b: list[str] | None = None) -> Path:
    workspace = tmp_path / ".work" / "ws"
    workspace.mkdir(parents=True)
    _write_paper(
        workspace,
        SHA_A,
        "Alpha paper",
        pages_a or ["Synthetic quasar method evidence uniquealpha sharedconcept."],
    )
    _write_paper(
        workspace,
        SHA_B,
        "Beta paper",
        pages_b or ["Nebula writing token evidence uniquebeta sharedconcept."],
    )
    built = build_index(workspace)
    assert built["ok"] is True
    return workspace


def _unknown() -> dict:
    return {"citations": [], "status": "unknown", "text": UNKNOWN_TEXT}


def _knowledge_document(paper_id: str, chunk_id: str, *, concept: str = "Synthetic Method", extra_provisional: str | None = None) -> dict:
    sections = {key: _unknown() for key in SECTION_KEYS}
    sections["summary"] = {"citations": [chunk_id], "status": "provisional", "text": "The paper describes a synthetic method."}
    if extra_provisional:
        sections[extra_provisional] = {
            "citations": [chunk_id],
            "status": "provisional",
            "text": "Additional provisional section.",
        }
    return {
        "concepts": [{"citations": [chunk_id], "name": concept}],
        "paper_id": paper_id,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": sections,
    }


def test_export_import_list_views_and_reuse(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    assert exported["ok"] is True
    assert exported["schema"] == KNOWLEDGE_CONTEXT_SCHEMA
    assert exported["paper_id"] == PAPER_A
    assert exported["context"]["kind"] == "writing"
    assert exported["context"]["ok"] is True
    assert exported["coverage"]["exported_chunks"] >= 1
    assert exported["coverage"]["total_chunks"] >= 1
    assert exported["coverage"]["truncated"] is False
    assert exported["paper_snapshot"]["paper_id"] == PAPER_A
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    document = _knowledge_document(PAPER_A, chunk)
    first = import_knowledge(workspace, exported, document)
    assert first["ok"] is True
    assert first["status"] == OK
    assert first["reused"] is False
    assert first["source_status"] == "current"
    page = Path(first["page_path"])
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "[@ " not in text
    assert "source.md#page-1" in text
    assert "模型建议" in text
    listed = list_knowledge(workspace)
    assert listed["ok"] is True
    assert listed["heads"][PAPER_A] == first["record_id"]
    assert listed["records"][0]["source_status"] == "current"
    assert listed["records"][0]["is_head"] is True
    assert "quasar" not in json.dumps(listed)
    again = import_knowledge(workspace, exported, document)
    assert again["ok"] is True
    assert again["reused"] is True
    assert again["record_id"] == first["record_id"]
    assert page.read_bytes() == Path(again["page_path"]).read_bytes()
    exported_b = export_knowledge_context(workspace, paper_id=PAPER_B)
    chunk_b = exported_b["context"]["evidence"][0]["chunk_id"]
    second = import_knowledge(
        workspace,
        exported_b,
        _knowledge_document(PAPER_B, chunk_b, concept="synthetic method"),
    )
    assert second["ok"] is True
    views = build_knowledge_views(workspace)
    assert views["ok"] is True
    assert views["reused"] is False
    index = Path(views["index_path"])
    assert index.is_file()
    index_text = index.read_text(encoding="utf-8")
    assert "现行论文" in index_text
    concept_dir = index.parent / "concepts"
    assert concept_dir.is_dir()
    concept_pages = list(concept_dir.glob("*.md"))
    assert len(concept_pages) == 1
    assert HEX_NAME(concept_pages[0].stem)
    assert "Foo" not in concept_pages[0].name
    related = (index.parent / "papers" / f"{SHA_A}.md").read_text(encoding="utf-8")
    assert "相同概念建议" in related
    assert "Beta paper" in related
    assert "支持" not in related or "不是支持" in related
    reused_views = build_knowledge_views(workspace)
    assert reused_views["ok"] is True
    assert reused_views["reused"] is True
    assert reused_views["view_id"] == views["view_id"]
    notes = workspace / "knowledge" / "notes.md"
    notes.write_text("keep user notes\n", encoding="utf-8")
    again_views = build_knowledge_views(workspace)
    assert again_views["reused"] is True
    assert notes.read_text(encoding="utf-8") == "keep user notes\n"


def HEX_NAME(name: str) -> bool:
    return len(name) == 64 and all(char in "0123456789abcdef" for char in name)


def test_unknown_sections_and_all_unknown_close(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    document = _knowledge_document(PAPER_A, chunk)
    assert document["sections"]["method"]["text"] == UNKNOWN_TEXT
    published = import_knowledge(workspace, exported, document)
    assert published["ok"] is True
    all_unknown = {
        "concepts": [],
        "paper_id": PAPER_A,
        "schema": KNOWLEDGE_DOCUMENT_SCHEMA,
        "sections": {key: _unknown() for key in SECTION_KEYS},
    }
    closed = import_knowledge(workspace, exported, all_unknown)
    assert closed["ok"] is False
    assert closed["status"] == INSUFFICIENT_EVIDENCE
    assert list_knowledge(workspace)["heads"][PAPER_A] == published["record_id"]


def test_page_spread_and_character_budget(tmp_path: Path) -> None:
    pages = [f"spread page {index} uniquealpha token {index}." for index in range(1, 61)]
    workspace = _workspace(tmp_path, pages_a=pages)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    assert exported["ok"] is True
    assert exported["coverage"]["total_chunks"] == 60
    assert exported["coverage"]["exported_chunks"] == 48
    assert exported["coverage"]["truncated"] is True
    assert exported["coverage"]["omitted_pages"] == list(range(49, 61))
    huge = "x" * 90_000
    workspace2 = tmp_path / ".work" / "huge"
    workspace2.mkdir(parents=True)
    _write_paper(workspace2, SHA_A, "Huge", [huge])
    build_index(workspace2)
    huge_export = export_knowledge_context(workspace2, paper_id=PAPER_A)
    assert huge_export["ok"] is True
    assert huge_export["coverage"]["truncated"] is True
    assert huge_export["coverage"]["exported_chunks"] >= 1
    assert sum(len(item["text"]) for item in huge_export["context"]["evidence"]) <= 80_000
    for item in huge_export["context"]["evidence"]:
        source = (workspace2 / item["markdown_path"]).read_text(encoding="utf-8")
        assert source[item["text_start"] : item["text_end"]] == item["text"]


def test_false_mixed_missing_citations_and_marks(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    missing = _knowledge_document(PAPER_A, chunk)
    missing["sections"]["summary"]["citations"] = []
    assert import_knowledge(workspace, exported, missing)["status"] == LIGHT_KNOWLEDGE_INVALID
    unknown = _knowledge_document(PAPER_A, chunk)
    unknown["sections"]["summary"]["citations"] = ["chk-missing"]
    assert import_knowledge(workspace, exported, unknown)["status"] == LIGHT_KNOWLEDGE_INVALID
    marked = _knowledge_document(PAPER_A, chunk)
    marked["sections"]["summary"]["text"] = f"Uses [@{chunk}]"
    assert import_knowledge(workspace, exported, marked)["status"] == LIGHT_KNOWLEDGE_INVALID
    other = export_knowledge_context(workspace, paper_id=PAPER_B)
    foreign = _knowledge_document(PAPER_A, other["context"]["evidence"][0]["chunk_id"])
    assert import_knowledge(workspace, exported, foreign)["status"] == LIGHT_KNOWLEDGE_INVALID
    wrong_paper = _knowledge_document(PAPER_B, chunk)
    assert import_knowledge(workspace, exported, wrong_paper)["status"] == LIGHT_KNOWLEDGE_INVALID
    assert not (workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME).exists()


def test_source_drift_and_stale_list(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    published = import_knowledge(workspace, exported, _knowledge_document(PAPER_A, chunk))
    assert published["ok"] is True
    source = workspace / "papers" / SHA_A / "source.md"
    original = source.read_bytes()
    source.write_text(source.read_text(encoding="utf-8").replace("quasar", "changed"))
    stale_import = import_knowledge(workspace, exported, _knowledge_document(PAPER_A, chunk))
    assert stale_import["ok"] is False
    assert stale_import["status"] in {INDEX_STALE, LIGHT_KNOWLEDGE_INVALID}
    listed = list_knowledge(workspace)
    assert listed["records"][0]["source_status"] == "stale"
    source.write_bytes(original)
    listed_ok = list_knowledge(workspace)
    assert listed_ok["records"][0]["source_status"] == "current"
    source.unlink()
    (workspace / "papers" / SHA_A / "source.json").unlink()
    (workspace / "papers" / SHA_A).rmdir()
    missing = list_knowledge(workspace)
    assert missing["records"][0]["source_status"] == "missing-source"


def test_edited_bundle_conflict_and_concept_escaping(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    document = _knowledge_document(PAPER_A, chunk, concept="Foo|Bar / ../evil")
    published = import_knowledge(workspace, exported, document)
    assert published["ok"] is True
    record = workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME / published["record_id"]
    page = record / KNOWLEDGE_PAGE_NAME
    before = page.read_bytes()
    page.write_text(page.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
    conflict = import_knowledge(workspace, exported, document)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_KNOWLEDGE_CONFLICT
    assert page.read_bytes() != before
    page.write_bytes(before)
    reused = import_knowledge(workspace, exported, document)
    assert reused["reused"] is True
    rendered = before.decode("utf-8")
    assert "Foo\\|Bar" in rendered or "Foo|Bar" not in rendered.split("**", 2)[-1]
    assert "../evil" not in str(record)
    views = build_knowledge_views(workspace)
    concept_names = [path.name for path in (Path(views["index_path"]).parent / "concepts").glob("*.md")]
    assert concept_names
    assert all("evil" not in name and "Foo" not in name for name in concept_names)


def test_view_history_excludes_stale_relationships(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported_a = export_knowledge_context(workspace, paper_id=PAPER_A)
    exported_b = export_knowledge_context(workspace, paper_id=PAPER_B)
    import_knowledge(workspace, exported_a, _knowledge_document(PAPER_A, exported_a["context"]["evidence"][0]["chunk_id"]))
    import_knowledge(workspace, exported_b, _knowledge_document(PAPER_B, exported_b["context"]["evidence"][0]["chunk_id"], concept="synthetic method"))
    first = build_knowledge_views(workspace)
    first_id = first["view_id"]
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar", "mutated"))
    build_index(workspace)
    listed = list_knowledge(workspace)
    statuses = {item["paper_id"]: item["source_status"] for item in listed["records"]}
    assert statuses[PAPER_A] == "stale"
    assert statuses[PAPER_B] == "current"
    second = build_knowledge_views(workspace)
    assert second["ok"] is True
    assert second["view_id"] != first_id
    assert (workspace / "knowledge" / "views" / first_id / "index.md").is_file()
    current_index = Path(second["index_path"]).read_text(encoding="utf-8")
    assert "过期或历史记录" in current_index
    beta_page = Path(second["index_path"]).parent / "papers" / f"{SHA_B}.md"
    assert "Alpha paper" not in beta_page.read_text(encoding="utf-8")
    current = json.loads((workspace / "knowledge" / "CURRENT.json").read_text(encoding="utf-8"))
    assert current["view_id"] == second["view_id"]


def test_managed_roots_and_unsafe_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    answer = {"citations": [{"chunk_id": chunk}], "text": f"note [@{chunk}]"}
    for relative in (".light-knowledge/stolen.md", ".light-library/stolen.md", "knowledge/stolen.md"):
        target = workspace / relative
        with pytest.raises(ResearchError) as exc:
            import_document(workspace, exported["context"], answer, output=target)
        assert exc.value.code == WORKSPACE_INVALID
        assert not target.exists()
    outside = tmp_path / "plain"
    outside.mkdir()
    _write_paper(outside, SHA_A, "Alpha paper", ["Synthetic quasar method evidence."])
    build_index(outside)
    with pytest.raises(ResearchError) as exc:
        export_knowledge_context(outside, paper_id=PAPER_A)
    assert exc.value.code == WORKSPACE_INVALID
    with pytest.raises(ResearchError):
        export_knowledge_context(workspace, paper_id="not-a-paper")
    missing = export_knowledge_context(workspace, paper_id="sha256:" + ("c" * 64))
    assert missing["status"] == LIGHT_SELECTION_INVALID


def test_busy_lock_and_malformed_fields(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    document = _knowledge_document(PAPER_A, chunk)
    held = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with _exclusive_lock(_workspace_lock_path(workspace), workspace):
            held.set()
            release.wait(2)

    worker = threading.Thread(target=_hold)
    worker.start()
    assert held.wait(2)
    try:
        busy = import_knowledge(workspace, exported, document)
        assert busy["ok"] is False
        assert busy["status"] == LIGHT_WORKSPACE_BUSY
    finally:
        release.set()
        worker.join()
    extra = _knowledge_document(PAPER_A, chunk)
    extra["extra"] = True
    assert import_knowledge(workspace, exported, extra)["status"] == LIGHT_KNOWLEDGE_INVALID
    extra_section = _knowledge_document(PAPER_A, chunk)
    extra_section["sections"]["summary"]["note"] = "nope"
    assert import_knowledge(workspace, exported, extra_section)["status"] == LIGHT_KNOWLEDGE_INVALID
    heads = workspace / KNOWLEDGE_STATE_DIR / HEADS_NAME
    published = import_knowledge(workspace, exported, document)
    assert published["ok"] is True
    heads.write_bytes(b"{not-json\n")
    listed = list_knowledge(workspace)
    assert listed["ok"] is False
    assert listed["status"] == LIGHT_KNOWLEDGE_CONFLICT


def test_no_evidence_is_closed(tmp_path: Path) -> None:
    workspace = tmp_path / ".work" / "empty-paper"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Empty", [""])
    build_index(workspace)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    assert exported["ok"] is False
    assert exported["status"] == INSUFFICIENT_EVIDENCE


def _accepted(result: dict) -> dict:
    assert result.get("ok") is True, result
    return result


def _refused(call) -> None:
    try:
        result = call()
    except ResearchError:
        return
    assert result.get("ok") is False, result


def _publish(workspace: Path, paper_id: str, *, concept: str = "Shared mechanical fixture") -> dict:
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=paper_id))
    chunk = wrapper["context"]["evidence"][0]["chunk_id"]
    return _accepted(import_knowledge(workspace, wrapper, _knowledge_document(paper_id, chunk, concept=concept)))


def test_successful_publication_leaves_no_pending_stage(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    _accepted(build_knowledge_views(workspace))
    staging = workspace / KNOWLEDGE_STATE_DIR / "staging"
    assert not staging.exists() or not list(staging.iterdir())


@pytest.mark.parametrize("extra", ["symlink-dir", "empty-dir"])
def test_record_reuse_refuses_unrecognized_directory_entries(tmp_path: Path, extra: str) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    chunk = wrapper["context"]["evidence"][0]["chunk_id"]
    document = _knowledge_document(PAPER_A, chunk)
    result = _accepted(import_knowledge(workspace, wrapper, document))
    record = Path(result["page_path"]).parent
    foreign = record / "unrecognized"
    if extra == "symlink-dir":
        foreign.symlink_to(workspace / "papers", target_is_directory=True)
    else:
        foreign.mkdir()
    _refused(lambda: import_knowledge(workspace, wrapper, document))
    assert os.path.lexists(foreign)


def test_edited_record_cannot_be_current_or_supply_new_concepts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result = _publish(workspace, PAPER_A)
    record = Path(result["page_path"]).parent
    path = record / "document.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["concepts"] = [{"name": "UNVERIFIED ALTERED CONCEPT", "citations": ["unknown-chunk"]}]
    changed = persisted_bytes(value)
    path.write_bytes(changed)
    listing = _accepted(list_knowledge(workspace))
    row = next(item for item in listing["records"] if item["record_id"] == result["record_id"])
    assert row["source_status"] == "conflict", row
    built = build_knowledge_views(workspace)
    if built.get("ok") is True:
        assert "UNVERIFIED ALTERED CONCEPT" not in Path(built["index_path"]).read_text(encoding="utf-8")
    assert path.read_bytes() == changed


def test_related_paper_links_resolve_to_existing_siblings(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    _publish(workspace, PAPER_B, concept="Shared mechanical fixture")
    result = _accepted(build_knowledge_views(workspace))
    view = Path(result["index_path"]).parent
    related_links = 0
    for page in (view / "papers").glob("*.md"):
        for href in re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            if href.endswith(".md") and not href.startswith(("http:", "https:")):
                assert (page.parent / href).resolve().is_file(), (page, href)
                related_links += 1
    assert related_links >= 6
    for page in (view / "concepts").glob("*.md"):
        for href in re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            if href.endswith(".md") and not href.startswith(("http:", "https:")):
                assert (page.parent / href).resolve().is_file(), (page, href)


def test_unknown_current_pointer_is_preserved(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    _accepted(build_knowledge_views(workspace))
    pointer = workspace / "knowledge" / "CURRENT.json"
    original = b'{"user_owned":"preserve these bytes"}\n'
    pointer.write_bytes(original)
    _refused(lambda: build_knowledge_views(workspace))
    assert pointer.read_bytes() == original


@pytest.mark.parametrize("missing", ["coverage", "paper_snapshot", "prompt"])
def test_missing_knowledge_wrapper_field_closes_without_traceback(tmp_path: Path, missing: str) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    del wrapper[missing]
    _refused(lambda: import_knowledge(workspace, wrapper, document))


def test_hardlinked_source_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    source = workspace / "papers" / SHA_A / "source.md"
    alias = workspace.parent / "source-alias.md"
    os.link(source, alias)
    try:
        exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    except ResearchError:
        return
    assert exported.get("ok") is False
    assert exported.get("status") in {SOURCE_INVALID, LIGHT_KNOWLEDGE_INVALID, LIGHT_KNOWLEDGE_CONFLICT}


@pytest.mark.parametrize("edit", ["payload", "ownership-target"])
def test_interrupted_staging_does_not_discard_unknown_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edit: str) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    original_write = _write_bytes

    def crash_after_document(path: Path, data: bytes) -> None:
        original_write(path, data)
        if path.name == "document.json":
            raise RuntimeError("interrupted partial record publication")

    with monkeypatch.context() as patch:
        patch.setattr("video_paper_wiki_research.light_knowledge._write_bytes", crash_after_document)
        with pytest.raises(RuntimeError):
            import_knowledge(workspace, wrapper, document)
    stage = next((workspace / KNOWLEDGE_STATE_DIR / "staging").iterdir())
    path = stage / ("payload/document.json" if edit == "payload" else "ownership.json")
    if edit == "payload":
        changed = b"USER EDIT: keep my partial work\n"
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
        value["intended_relative_target"] = "papers/foreign/source.md"
        changed = persisted_bytes(value)
    path.write_bytes(changed)
    _refused(lambda: import_knowledge(workspace, wrapper, document))
    assert path.read_bytes() == changed


def test_validated_partial_staging_still_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    original_write = _write_bytes

    def crash_after_document(path: Path, data: bytes) -> None:
        original_write(path, data)
        if path.name == "document.json":
            raise RuntimeError("interrupted matching partial record")

    with monkeypatch.context() as patch:
        patch.setattr("video_paper_wiki_research.light_knowledge._write_bytes", crash_after_document)
        with pytest.raises(RuntimeError):
            import_knowledge(workspace, wrapper, document)
    recovered = import_knowledge(workspace, wrapper, document)
    assert recovered["ok"] is True
    assert recovered["reused"] is False
    assert not list((workspace / KNOWLEDGE_STATE_DIR / "staging").iterdir())


def test_source_change_during_render_refuses_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    source = workspace / "papers" / SHA_A / "source.md"
    from video_paper_wiki_research import light_knowledge as knowledge

    original = knowledge._record_files

    def render_then_edit(**kwargs):
        result = original(**kwargs)
        source.write_bytes(source.read_bytes() + b"\nExternal source edit during rendering\n")
        return result

    monkeypatch.setattr(knowledge, "_record_files", render_then_edit)
    _refused(lambda: import_knowledge(workspace, wrapper, document))
    records = workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME
    assert not records.exists() or not list(records.iterdir())


def test_missing_prior_current_target_is_preserved(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    _accepted(build_knowledge_views(workspace))
    pointer = workspace / "knowledge" / "CURRENT.json"
    prior = {
        "index_relative": "knowledge/views/" + "f" * 64 + "/index.md",
        "schema": CURRENT_SCHEMA,
        "view_id": "f" * 64,
    }
    pointer.write_bytes(persisted_bytes(prior))
    before = pointer.read_bytes()
    _refused(lambda: build_knowledge_views(workspace))
    assert pointer.read_bytes() == before


def test_missing_prior_head_target_is_preserved(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    first = _accepted(import_knowledge(workspace, wrapper, document))
    pointer = workspace / KNOWLEDGE_STATE_DIR / HEADS_NAME
    assert pointer.exists()
    prior = {"heads": {wrapper["paper_id"]: "f" * 64}, "schema": HEADS_SCHEMA}
    pointer.write_bytes(persisted_bytes(prior))
    before = pointer.read_bytes()
    _refused(lambda: import_knowledge(workspace, wrapper, document))
    assert pointer.read_bytes() == before
    listed = _accepted(list_knowledge(workspace))
    assert listed["heads"][PAPER_A] == "f" * 64
    missing = next(item for item in listed["records"] if item["record_id"] == "f" * 64)
    assert missing["source_status"] == "conflict"
    assert missing["is_head"] is False
    original = next(item for item in listed["records"] if item["record_id"] == first["record_id"])
    assert original["is_head"] is False


@pytest.mark.parametrize("filename", ["manifest.json", "identity.json"])
def test_record_unknown_manifest_or_identity_fields_are_conflict(tmp_path: Path, filename: str) -> None:
    workspace = _workspace(tmp_path)
    result = _publish(workspace, PAPER_A)
    record = Path(result["page_path"]).parent
    path = record / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    value["unexpected_field"] = "Preserve me as malformed data"
    path.write_bytes(persisted_bytes(value))
    if filename == "identity.json":
        manifest_path = record / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest["files"]:
            if row.get("path") == "identity.json":
                row.update(size_bytes=path.stat().st_size, sha256=sha256_bytes(path.read_bytes()))
        manifest_path.write_bytes(persisted_bytes(manifest))
    before = path.read_bytes()
    listing = _accepted(list_knowledge(workspace))
    item = next(row for row in listing["records"] if row["record_id"] == result["record_id"])
    assert item["source_status"] == "conflict", item
    assert item["is_head"] is False
    assert path.read_bytes() == before
    built = build_knowledge_views(workspace)
    if built.get("ok") is True:
        assert "Preserve me as malformed data" not in Path(built["index_path"]).read_text(encoding="utf-8")


def test_valid_prior_pointer_can_advance_to_new_record_and_view(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    original = _accepted(import_knowledge(workspace, wrapper, document))
    first = _accepted(build_knowledge_views(workspace))
    new_doc = copy.deepcopy(document)
    new_doc["sections"]["summary"]["text"] = "A distinct valid mechanical summary with the same source"
    second_record = _accepted(import_knowledge(workspace, wrapper, new_doc))
    assert second_record["record_id"] != original["record_id"]
    second = _accepted(build_knowledge_views(workspace))
    assert second["view_id"] != first["view_id"]
    assert Path(first["index_path"]).is_file()
    assert Path(second["index_path"]).is_file()
    manifest = json.loads((Path(second["index_path"]).parent / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"files", "fingerprint", "heads", "schema", "view_id"}
    assert sha256_canonical(manifest["fingerprint"]) == second["view_id"]
    assert Path(original["page_path"]).is_file()
    assert Path(second_record["page_path"]).is_file()


def test_valid_prior_pointer_advances_after_source_staleness_and_archival(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first_a = _publish(workspace, PAPER_A)
    first_b = _publish(workspace, PAPER_B, concept="synthetic method")
    first_view = _accepted(build_knowledge_views(workspace))
    source = workspace / "papers" / SHA_A / "source.md"
    source.write_text(source.read_text(encoding="utf-8").replace("quasar", "mutated-alpha"), encoding="utf-8")
    _accepted(build_index(workspace))
    stale_listed = _accepted(list_knowledge(workspace))
    statuses = {item["record_id"]: item for item in stale_listed["records"]}
    assert statuses[first_a["record_id"]]["source_status"] == "stale"
    assert statuses[first_a["record_id"]]["is_head"] is False
    assert stale_listed["heads"][PAPER_A] == first_a["record_id"]
    fresh = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    chunk = fresh["context"]["evidence"][0]["chunk_id"]
    second_a = _accepted(import_knowledge(workspace, fresh, _knowledge_document(PAPER_A, chunk)))
    assert second_a["record_id"] != first_a["record_id"]
    assert Path(first_a["page_path"]).is_file()
    second_view = _accepted(build_knowledge_views(workspace))
    assert second_view["view_id"] != first_view["view_id"]
    assert Path(first_view["index_path"]).is_file()
    paper_b_dir = workspace / "papers" / SHA_B
    for child in list(paper_b_dir.iterdir()):
        child.unlink()
    paper_b_dir.rmdir()
    _accepted(build_index(workspace))
    archived = _accepted(list_knowledge(workspace))
    row_b = next(item for item in archived["records"] if item["record_id"] == first_b["record_id"])
    assert row_b["source_status"] == "missing-source"
    assert row_b["is_head"] is False
    assert archived["heads"][PAPER_B] == first_b["record_id"]
    third_view = _accepted(build_knowledge_views(workspace))
    assert third_view["view_id"] != second_view["view_id"]
    assert Path(second_view["index_path"]).is_file()
    assert Path(first_view["index_path"]).is_file()
    current = json.loads((workspace / "knowledge" / "CURRENT.json").read_text(encoding="utf-8"))
    assert current["view_id"] == third_view["view_id"]
    assert current["view_id"] != first_view["view_id"]


@pytest.mark.parametrize("bad", [{}, []])
def test_unhashable_knowledge_status_is_closed(tmp_path: Path, bad: object) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    document = _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])
    document["sections"]["summary"]["status"] = bad
    _refused(lambda: import_knowledge(workspace, wrapper, document))
    assert not (workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME).exists() or not list(
        (workspace / KNOWLEDGE_STATE_DIR / RECORDS_DIRNAME).iterdir()
    )


def test_heads_key_must_match_referenced_record_paper(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = _publish(workspace, PAPER_A)
    second = _accepted(export_knowledge_context(workspace, paper_id=PAPER_B))
    assert first["paper_id"] != second["paper_id"]
    pointer = workspace / KNOWLEDGE_STATE_DIR / HEADS_NAME
    original = persisted_bytes({"heads": {second["paper_id"]: first["record_id"]}, "schema": HEADS_SCHEMA})
    pointer.write_bytes(original)
    _refused(lambda: import_knowledge(workspace, second, _knowledge_document(PAPER_B, second["context"]["evidence"][0]["chunk_id"])))
    assert pointer.read_bytes() == original
    listed = _accepted(list_knowledge(workspace))
    assert listed["heads"][PAPER_B] == first["record_id"]
    mismatch = next(
        item
        for item in listed["records"]
        if item["paper_id"] == PAPER_B and item["record_id"] == first["record_id"]
    )
    assert mismatch["source_status"] == "conflict"
    assert mismatch["is_head"] is False
    owned = next(item for item in listed["records"] if item["record_id"] == first["record_id"] and item["paper_id"] == PAPER_A)
    assert owned["is_head"] is False
    _refused(lambda: build_knowledge_views(workspace))
    assert pointer.read_bytes() == original


def test_current_view_cannot_borrow_foreign_missing_record_references(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    built = _accepted(build_knowledge_views(workspace))
    foreign = workspace.parent / "foreign-library"
    foreign.mkdir()
    (foreign / ".work").mkdir(exist_ok=True)
    shutil.copytree(workspace / "papers", foreign / "papers")
    _accepted(build_index(foreign))
    view = Path(built["index_path"]).parent
    shutil.copytree(view, foreign / "knowledge" / "views" / view.name)
    pointer = foreign / "knowledge" / "CURRENT.json"
    original = (workspace / "knowledge" / "CURRENT.json").read_bytes()
    pointer.write_bytes(original)
    _refused(lambda: build_knowledge_views(foreign))
    assert pointer.read_bytes() == original


def test_record_redundant_snapshots_are_bound_to_original_wrapper(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    wrapper = _accepted(export_knowledge_context(workspace, paper_id=PAPER_A))
    result = _accepted(import_knowledge(workspace, wrapper, _knowledge_document(PAPER_A, wrapper["context"]["evidence"][0]["chunk_id"])))
    paper = workspace / "papers" / SHA_A
    source_path = paper / "source.json"
    metadata = json.loads(source_path.read_text(encoding="utf-8"))
    metadata["title"] = "Changed metadata after original import"
    source_path.write_bytes(persisted_bytes(metadata))
    new_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    directory = Path(result["page_path"]).parent
    identity_path = directory / "identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    assert identity["wrapper"]["paper_snapshot"]["source_json_sha256"] != new_hash
    identity["paper_snapshot"]["source_json_sha256"] = new_hash
    identity_path.write_bytes(persisted_bytes(identity))
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["paper_snapshot"]["source_json_sha256"] = new_hash
    manifest["source"]["source_json_sha256"] = new_hash
    for item in manifest["files"]:
        if item.get("path") == "identity.json":
            item["sha256"] = hashlib.sha256(identity_path.read_bytes()).hexdigest()
            item["size_bytes"] = identity_path.stat().st_size
    manifest_path.write_bytes(persisted_bytes(manifest))
    listing = _accepted(list_knowledge(workspace))
    row = next(item for item in listing["records"] if item["record_id"] == result["record_id"])
    assert row["source_status"] == "conflict", row
    assert identity_path.read_bytes() == persisted_bytes(identity)


def test_complete_workspace_relocation_preserves_valid_old_view_and_advance(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _publish(workspace, PAPER_A)
    _accepted(build_knowledge_views(workspace))
    relocated = workspace.parent / "relocated-library"
    shutil.copytree(workspace, relocated)
    _accepted(build_index(relocated))
    listing = _accepted(list_knowledge(relocated))
    assert listing["records"]
    assert all(item["source_status"] == "current" for item in listing["records"])
    wrapper = _accepted(export_knowledge_context(relocated, paper_id=PAPER_B))
    _accepted(import_knowledge(relocated, wrapper, _knowledge_document(PAPER_B, wrapper["context"]["evidence"][0]["chunk_id"])))
    built = _accepted(build_knowledge_views(relocated))
    assert Path(built["index_path"]).is_file()
    assert built["view_id"] != json.loads((relocated / "knowledge" / "CURRENT.json").read_text(encoding="utf-8")).get("unused", "")
    first_id = json.loads((workspace / "knowledge" / "CURRENT.json").read_text(encoding="utf-8"))["view_id"]
    assert built["view_id"] != first_id


def test_legacy_import_still_rejects_custom_wrapper_schema(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    exported = export_knowledge_context(workspace, paper_id=PAPER_A)
    tampered = dict(exported)
    tampered["schema"] = "video-paper-wiki.light-knowledge-batch-record-context.v1"
    closed = import_knowledge(
        workspace,
        tampered,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"]),
    )
    assert closed["ok"] is False
    assert closed["status"] == LIGHT_KNOWLEDGE_INVALID
    accepted = import_knowledge(
        workspace,
        exported,
        _knowledge_document(PAPER_A, exported["context"]["evidence"][0]["chunk_id"]),
    )
    assert accepted["ok"] is True
