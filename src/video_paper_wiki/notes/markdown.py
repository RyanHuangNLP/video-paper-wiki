"""Render paper-analysis-draft.v1 as Obsidian markdown. Local only."""

from __future__ import annotations

from typing import Any, Mapping

from video_paper_wiki.parse.draft_document import SECTION_SPECS

_UNSAFE = set(':{}[]#&*!|>\'%"@`,?')


def _yaml_scalar(value: str) -> str:
    if (
        value == ""
        or value[0] in " \t"
        or value[-1] in " \t"
        or any(ch in _UNSAFE or ch in "\n\r" for ch in value)
    ):
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'
    return value


def render_paper_markdown(document: Mapping[str, Any]) -> str:
    paper_id = str(document.get("paper_id", ""))
    title = str(document.get("title", ""))
    title_zh = str(document.get("title_zh", ""))
    by_section: dict[str, list[str]] = {section_id: [] for section_id, _heading in SECTION_SPECS}
    claims = document.get("claims") or []
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            section = str(claim.get("section", ""))
            text = str(claim.get("claim_text", "")).strip()
            if section in by_section and text:
                by_section[section].append(text)

    lines = [
        "---",
        f"paper_id: {_yaml_scalar(paper_id)}",
        f"title: {_yaml_scalar(title)}",
        f"title_zh: {_yaml_scalar(title_zh)}",
        "---",
        "",
    ]
    for section_id, heading_zh in SECTION_SPECS:
        lines.append(f"## {heading_zh}")
        lines.append("")
        for text in by_section[section_id]:
            lines.append(text)
            lines.append("")
    return "\n".join(lines)
