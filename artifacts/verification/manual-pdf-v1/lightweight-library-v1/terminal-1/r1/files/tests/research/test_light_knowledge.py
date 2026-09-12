from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from tests.research.test_light_index import SHA_A, SHA_B, _write_paper
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_context import import_document
from video_paper_wiki_research.light_index import INDEX_STALE, LIGHT_SELECTION_INVALID, OK, build_index
from video_paper_wiki_research.light_knowledge import (
    HEADS_NAME,
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
    build_knowledge_views,
    export_knowledge_context,
    import_knowledge,
    list_knowledge,
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
