"""Section-aware merge of an existing papers/<id>.md copy. No network."""

from __future__ import annotations

from video_paper_wiki.notes.headings import h2_heading_text, is_atx_h2
from video_paper_wiki.parse.draft_document import SECTION_SPECS

OWNED_YAML_KEYS = (
    "title",
    "paper_id",
    "arxiv_id",
    "year",
    "topics",
    "related",
    "backlinks",
)
_OWNED = frozenset(OWNED_YAML_KEYS)
_FROZEN_HEADINGS = tuple(heading for _section_id, heading in SECTION_SPECS)
_FROZEN = frozenset(_FROZEN_HEADINGS)


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Opening YAML block (without --- fences) and the remainder, or (None, text)."""
    if not text.startswith("---"):
        return None, text
    rest = text[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    else:
        return None, text
    closer = rest.find("\n---")
    if closer == -1:
        return None, text
    block = rest[:closer]
    after = rest[closer + len("\n---") :]
    if after.startswith("\r\n"):
        after = after[2:]
    elif after.startswith("\n"):
        after = after[1:]
    return block, after


def _yaml_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or ":" not in stripped:
        return None
    return stripped.split(":", 1)[0].strip() or None


def merge_yaml_block(existing: str, rendered: str) -> str:
    """Replace owned identity keys from *rendered*; keep unknown existing keys."""
    rendered_by_key: dict[str, str] = {}
    rendered_lines = rendered.splitlines()
    for line in rendered_lines:
        key = _yaml_key(line)
        if key:
            rendered_by_key[key] = line
    used_owned: set[str] = set()
    out: list[str] = []
    for line in existing.splitlines():
        key = _yaml_key(line)
        if key in _OWNED:
            replacement = rendered_by_key.get(key)
            if replacement is not None:
                out.append(replacement)
                used_owned.add(key)
            continue
        out.append(line)
    for line in rendered_lines:
        key = _yaml_key(line)
        if key in _OWNED and key not in used_owned:
            out.append(line)
            used_owned.add(key)
    return "\n".join(out)


def _split_h2_blocks(body: str) -> list[tuple[str | None, list[str]]]:
    """Sequence of (heading_or_None, lines). Preamble has heading None."""
    blocks: list[tuple[str | None, list[str]]] = []
    heading: str | None = None
    current: list[str] = []
    started = False
    for line in body.splitlines():
        text = h2_heading_text(line) if is_atx_h2(line) else None
        if text is not None:
            if started or current:
                blocks.append((heading, current))
            heading = text
            current = [line]
            started = True
            continue
        current.append(line)
        started = True
    if started or current:
        blocks.append((heading, current))
    return blocks


def merge_body(existing_body: str, rendered_body: str) -> str:
    """Replace the ten frozen H2 bodies; preserve unknown H2s and extra prose."""
    existing_blocks = _split_h2_blocks(existing_body)
    rendered_frozen: dict[str, list[str]] = {}
    for heading, lines in _split_h2_blocks(rendered_body):
        if heading in _FROZEN:
            rendered_frozen[heading] = lines
    out_blocks: list[list[str]] = []
    seen: set[str] = set()
    last_frozen_at = -1
    for heading, lines in existing_blocks:
        if heading in _FROZEN:
            out_blocks.append(rendered_frozen.get(heading, lines))
            seen.add(heading)
            last_frozen_at = len(out_blocks) - 1
            continue
        out_blocks.append(lines)
        if heading is None and last_frozen_at < 0:
            last_frozen_at = 0
    missing = [heading for heading in _FROZEN_HEADINGS if heading not in seen]
    extras = [rendered_frozen[heading] for heading in missing if heading in rendered_frozen]
    if extras:
        insert_at = last_frozen_at + 1 if last_frozen_at >= 0 else len(out_blocks)
        for offset, block in enumerate(extras):
            out_blocks.insert(insert_at + offset, block)
    lines: list[str] = []
    for block in out_blocks:
        lines.extend(block)
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def join_frontmatter(block: str, body: str) -> str:
    yaml = block.strip("\n")
    body_text = body if body.startswith("\n") else "\n" + body
    if not body_text.endswith("\n"):
        body_text += "\n"
    return f"---\n{yaml}\n---{body_text}"


def merge_paper_copy(existing: str, rendered: str) -> str:
    """Merge a newly rendered copy into an existing papers/<id>.md note."""
    existing_yaml, existing_body = split_frontmatter(existing)
    rendered_yaml, rendered_body = split_frontmatter(rendered)
    if rendered_yaml is None:
        rendered_yaml = ""
    if existing_yaml is None:
        yaml = rendered_yaml
        body = merge_body(existing, rendered_body)
    else:
        yaml = merge_yaml_block(existing_yaml, rendered_yaml)
        body = merge_body(existing_body, rendered_body)
    return join_frontmatter(yaml, body)
