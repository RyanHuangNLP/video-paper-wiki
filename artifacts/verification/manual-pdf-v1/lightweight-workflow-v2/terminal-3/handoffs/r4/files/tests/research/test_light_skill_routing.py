"""Skill metadata, routing, and protocol-shape checks. Not a current-model trial."""

from __future__ import annotations

import re
from pathlib import Path

from tests.research.test_light_workflow import ProtocolWorkflowBackend, _prepare
from video_paper_wiki_research.light_workflow import complete_workflow

ROOT = Path(__file__).resolve().parents[2]
READ = ROOT / ".agents" / "skills" / "video-paper-read"
INGEST = ROOT / ".agents" / "skills" / "video-paper-ingest" / "SKILL.md"
QUERY = ROOT / ".agents" / "skills" / "video-paper-query" / "SKILL.md"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _parse_simple_yaml(text: str) -> dict:
    """Parse the flat/quoted YAML used by these Skills. Not a general YAML library."""

    data: dict = {}
    stack: list[tuple[int, dict]] = [(-1, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line.endswith(":") and ":" == line[-1] and line.count(":") == 1 and not line.startswith("-"):
            key = line[:-1].strip()
            child: dict = {}
            while stack and indent <= stack[-1][0]:
                stack.pop()
            stack[-1][1][key] = child
            stack.append((indent, child))
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            parsed: object = value[1:-1]
        elif value in {"true", "false"}:
            parsed = value == "true"
        else:
            parsed = value
        while stack and indent <= stack[-1][0]:
            stack.pop()
        stack[-1][1][key] = parsed
    return data


def _frontmatter(path: Path) -> dict:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match, f"{path} is missing YAML frontmatter"
    data = _parse_simple_yaml(match.group(1))
    assert type(data) is dict
    return data


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    assert match
    return text[match.end() :]


def test_read_skill_metadata_and_references_are_parseable() -> None:
    meta = _frontmatter(READ / "SKILL.md")
    assert meta["name"] == "video-paper-read"
    assert type(meta["description"]) is str and meta["description"].strip()
    assert "Vault" in meta["description"] or "canonical" in meta["description"]
    openai = _parse_simple_yaml((READ / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    assert openai["interface"]["display_name"]
    assert 25 <= len(openai["interface"]["short_description"]) <= 64
    assert "$video-paper-read" in openai["interface"]["default_prompt"]
    assert openai["policy"]["allow_implicit_invocation"] is True
    workflow = READ / "references" / "workflow.md"
    assert workflow.is_file()
    body = _body(READ / "SKILL.md")
    assert "references/workflow.md" in body
    assert "OCR" in body
    assert ".work/" in body


def test_example_protocol_fields_match_backend_prepare_and_complete(tmp_path: Path) -> None:
    backend = ProtocolWorkflowBackend()
    workspace, prepared = _prepare(tmp_path, backend)
    completed = complete_workflow(
        workspace,
        prepared["session_id"],
        {"text": "The paper uses the protocol method. [@chk-protocol-1]", "citations": [{"chunk_id": "chk-protocol-1"}]},
        output=tmp_path / "skill-out.md",
        _backend=backend,
    )
    reference = (READ / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "structural test fixture" in reference
    assert "not an actual current-session-model trial" in reference
    for key in ("ok", "status", "schema", "session_id", "state", "context_path", "request_path", "manifest_path", "context", "next_actions", "reused"):
        assert key in prepared
        assert key in reference
    assert prepared["schema"] == "video-paper-wiki.light-workflow.v1"
    assert prepared["context"]["schema"] == "video-paper-wiki.light-context.v1"
    assert reference.count("video-paper-wiki.light-workflow.v1") >= 1
    assert "video-paper-wiki.light-context.v1" in reference
    for key in ("ok", "status", "state", "session_id", "path", "output_sha256", "reused"):
        assert key in completed
        assert key in reference
    assert completed["ok"] is True
    assert completed["state"] == "complete"
    skill = _body(READ / "SKILL.md")
    assert "structural test fixture" in skill or "structural test fixture" in reference
    assert "current-model trial" in reference


def test_ingest_and_query_route_lightweight_intent_without_recursion_loops() -> None:
    ingest_meta = _frontmatter(INGEST)
    query_meta = _frontmatter(QUERY)
    ingest = _body(INGEST)
    query = _body(QUERY)
    assert "video-paper-read" in ingest_meta["description"]
    assert "video-paper-read" in query_meta["description"]
    assert "video-paper-read" in ingest
    assert "video-paper-read" in query
    assert "do not bounce" in ingest.lower() or "loop" in ingest.lower()
    assert "do not recurse" in query.lower() or "unless the user then asks" in query.lower()
    assert "vpwiki-research pdf intake" in ingest
    assert "vpwiki capture inspect" in ingest
    assert "vpwiki-admin" in ingest
    assert "Never execute it" in ingest or "never execute" in ingest.lower()
    assert "vpwiki query" in query
    assert "vault-root" in query
    assert "pinned Claude Obsidian" in query or "claude-obsidian" in query
    read = _body(READ / "SKILL.md")
    assert "video-paper-ingest" in read
    assert "video-paper-query" in read
    assert "Never pick a real Vault implicitly" in read or "never pick a real Vault" in read.lower()


def test_skill_distinguishes_no_results_stale_draft_and_scanned_pdf() -> None:
    combined = _body(READ / "SKILL.md") + (READ / "references" / "workflow.md").read_text(encoding="utf-8")
    for token in ("NO_RESULTS", "PARSER_NO_TEXT", "stale", "LIGHT_OUTPUT_CONFLICT", "LIGHT_SESSION_CONFLICT", "sha256:"):
        assert token in combined
    assert "overwrite=True" in combined or "never uses `overwrite=True`" in combined
    assert "canonical" in combined.lower()
    assert "Vault" in combined
