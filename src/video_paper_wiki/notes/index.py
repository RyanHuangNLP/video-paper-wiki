"""Upsert local notes-root index.md. No network, no apply."""

from __future__ import annotations

from pathlib import Path


def _link_needle(paper_id: str) -> str:
    return f"](papers/{paper_id}.md)"


def _link_label(title: str, paper_id: str) -> str:
    label = title.strip() if title else ""
    if not label:
        label = paper_id
    return label.replace("[", "(").replace("]", ")")


def _entry_line(paper_id: str, title: str) -> str:
    return f"[{_link_label(title, paper_id)}](papers/{paper_id}.md)"


def upsert_index_entry(root: Path, paper_id: str, title: str) -> Path:
    """Write or replace one papers/ link in root/index.md.

    Does not create *root* itself. Creates index.md inside an existing root.
    Unmatched lines (headers, blanks, other papers) are preserved in order.
    """
    index_path = root / "index.md"
    needle = _link_needle(paper_id)
    new_line = _entry_line(paper_id, title)
    if index_path.is_file():
        lines = index_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    replaced = False
    for i, line in enumerate(lines):
        if needle in line:
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    index_path.write_text(text, encoding="utf-8")
    return index_path
