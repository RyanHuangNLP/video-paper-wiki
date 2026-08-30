"""Exact ATX H2 matching for frozen overlays and note scanners."""

from __future__ import annotations

import re

# Optional 0–3 leading spaces, exactly ## (not ###), then space/tab or end.
H2_LINE_RE = re.compile(r"^ {0,3}##(?!#)(?:[ \t]+|$)")


def is_atx_h2(line: str) -> bool:
    """True when *line* is a CommonMark ATX heading of level 2."""
    return H2_LINE_RE.match(line) is not None


def h2_heading_text(line: str) -> str | None:
    """Heading text with prefix stripped, or None if *line* is not an ATX H2."""
    match = H2_LINE_RE.match(line)
    if match is None:
        return None
    return line[match.end() :].strip()


def h2_span(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(heading_index, body_end_exclusive) for the first exact H2, or None."""
    start: int | None = None
    for index, line in enumerate(lines):
        if h2_heading_text(line) == heading:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if is_atx_h2(lines[index]):
            end = index
            break
    return start, end


def replace_h2_body(text: str, heading: str, body_lines: list[str]) -> str:
    """Replace the body under the first exact H2. Missing heading: unchanged."""
    lines = text.splitlines()
    span = h2_span(lines, heading)
    if span is None:
        return text
    start, end = span
    replaced = lines[: start + 1] + body_lines + lines[end:]
    out = "\n".join(replaced)
    if not out.endswith("\n"):
        out += "\n"
    return out


def apply_h2_sentence(
    text: str, paper_id: str, heading: str, mapping: dict[str, str] | None
) -> str:
    """Overlay one frozen sentence when *paper_id* is in *mapping*. Else unchanged."""
    wanted = str(paper_id).strip()
    if not wanted or not mapping:
        return text
    sentence = mapping.get(wanted)
    if not sentence:
        return text
    return replace_h2_body(text, heading, ["", sentence, ""])
