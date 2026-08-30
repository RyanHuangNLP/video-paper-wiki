"""Empty heading-regex remnant sections on vault paper copies. No network."""

from __future__ import annotations

_CLEAR_HEADINGS = (
    "研究问题",
    "方法",
    "表示与架构",
    "训练与数据",
    "实验与结果",
    "局限",
    "关联",
)


def apply_empty_draft_sections(text: str) -> str:
    """Keep the listed ## headings; replace each body with one blank line."""
    out = text
    for heading in _CLEAR_HEADINGS:
        out = _empty_one(out, heading)
    if not out.endswith("\n"):
        out += "\n"
    return out


def _empty_one(text: str, heading: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("##") and line[2:].strip() == heading:
            start = index
            break
    if start is None:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("##"):
            end = index
            break
    replaced = lines[: start + 1] + [""] + lines[end:]
    return "\n".join(replaced)
