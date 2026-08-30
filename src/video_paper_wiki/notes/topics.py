"""Write topic wiki pages under an existing notes root. No network, no apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_paper_wiki.parse.title import catalog_title_for_paper_id

_TOPICS_RELATIVE = Path("docs") / "seed" / "engine-mvp-topics.json"
_TOPICS_HEADING = "## 主题"


def _resolve_topics_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _TOPICS_RELATIVE
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / _TOPICS_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def _safe_segment(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    return "/" not in value and "\\" not in value


def load_topics() -> list[dict[str, Any]] | None:
    path = _resolve_topics_path()
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        return None
    topics: list[dict[str, Any]] = []
    for item in payload["topics"]:
        if not isinstance(item, dict):
            continue
        topic_id = item.get("id")
        heading = item.get("heading_zh")
        paper_ids = item.get("paper_ids")
        if not isinstance(topic_id, str) or not _safe_segment(topic_id.strip()):
            continue
        if not isinstance(heading, str):
            continue
        ids: list[str] = []
        if isinstance(paper_ids, list):
            for paper_id in paper_ids:
                if isinstance(paper_id, str) and paper_id.strip():
                    ids.append(paper_id.strip())
        blurb = item.get("blurb_zh")
        if not isinstance(blurb, str):
            blurb = ""
        topics.append(
            {
                "id": topic_id.strip(),
                "heading_zh": heading,
                "paper_ids": ids,
                "blurb_zh": blurb,
            }
        )
    return topics


def _paper_note_exists(root: Path, paper_id: str) -> bool:
    if not _safe_segment(paper_id):
        return False
    return (root / "papers" / f"{paper_id}.md").is_file()


def _topic_page_text(
    heading_zh: str, paper_ids: list[str], root: Path, blurb_zh: str = ""
) -> str:
    # Lazy import: notes.index -> frontmatter -> links -> topics.
    from video_paper_wiki.notes.index import paper_index_year

    lines = [f"# {heading_zh}", ""]
    if blurb_zh:
        lines.append(blurb_zh)
        lines.append("")
    for paper_id in paper_ids:
        title = catalog_title_for_paper_id(paper_id)
        if title is None:
            continue
        if not _paper_note_exists(root, paper_id):
            continue
        line = f"[{title}](../papers/{paper_id}.md)"
        year = paper_index_year(paper_id)
        if year is not None:
            line = f"{line} ({year})"
        lines.append(line)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _topic_index_block(topics: list[dict[str, Any]]) -> list[str]:
    lines = [_TOPICS_HEADING]
    for topic in topics:
        lines.append(f"[{topic['heading_zh']}](wiki/{topic['id']}.md)")
    return lines


def _is_topics_heading(line: str) -> bool:
    return line.strip() == _TOPICS_HEADING


def _replace_topics_section(index_text: str, topics: list[dict[str, Any]]) -> str:
    lines = index_text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if _is_topics_heading(line):
            start = i
            break
    block = _topic_index_block(topics)
    if start is None:
        result = list(lines)
        result.extend(block)
    else:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            stripped = lines[j].lstrip()
            if stripped.startswith("## "):
                end = j
                break
        result = lines[:start] + block + lines[end:]
    text = "\n".join(result)
    if not text.endswith("\n"):
        text += "\n"
    return text


def refresh_topic_pages(root: Path) -> None:
    """Write wiki/<id>.md pages and a root-index 主题 section.

    Does not create *root*. Missing topics file skips all wiki writes.
    Never writes wiki/index.md.
    """
    if not root.is_dir():
        return
    topics = load_topics()
    if topics is None:
        return
    wiki_dir = root / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for topic in topics:
        page = wiki_dir / f"{topic['id']}.md"
        page.write_text(
            _topic_page_text(
                topic["heading_zh"],
                topic["paper_ids"],
                root,
                topic.get("blurb_zh", ""),
            ),
            encoding="utf-8",
        )
    index_path = root / "index.md"
    if not index_path.is_file():
        return
    updated = _replace_topics_section(index_path.read_text(encoding="utf-8"), topics)
    index_path.write_text(updated, encoding="utf-8")
