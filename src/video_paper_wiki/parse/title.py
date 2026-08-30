"""Resolve draft titles from the seed catalog. Never downloads."""

from __future__ import annotations

import json
from pathlib import Path

_SEED_RELATIVE = Path("docs") / "seed" / "engine-mvp.json"

_HEADER_PREFIXES: tuple[str, ...] = (
    "published in",
    "arxiv:",
)

_HEADER_NEEDLES: tuple[str, ...] = (
    "arxiv.org",
    "copyright",
    "all rights reserved",
    "tmlr",
    "transactions on machine learning research",
)


def _resolve_seed_path() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _SEED_RELATIVE
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / _SEED_RELATIVE
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def _catalog_entry(paper_id: str) -> dict | None:
    path = _resolve_seed_path()
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
        return None
    wanted = str(paper_id).strip()
    if not wanted:
        return None
    for item in payload["papers"]:
        if not isinstance(item, dict):
            continue
        if str(item.get("paper_id", "")).strip() != wanted:
            continue
        return item
    return None


def catalog_title_for_paper_id(paper_id: str) -> str | None:
    item = _catalog_entry(paper_id)
    if item is None:
        return None
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def catalog_arxiv_id_for_paper_id(paper_id: str) -> str | None:
    item = _catalog_entry(paper_id)
    if item is None:
        return None
    arxiv_id = item.get("arxiv_id")
    if isinstance(arxiv_id, str) and arxiv_id.strip():
        return arxiv_id.strip()
    return None


def looks_like_header(line: str) -> bool:
    folded = line.strip().casefold()
    if not folded:
        return False
    for prefix in _HEADER_PREFIXES:
        if folded.startswith(prefix):
            return True
    for needle in _HEADER_NEEDLES:
        if needle in folded:
            return True
    return False


def _is_single_letter_token(token: str) -> bool:
    letters = [char for char in token if char.isalpha()]
    return len(letters) == 1


def _isolated_letter_space_joins(text: str) -> int:
    count = 0
    index = 0
    length = len(text)
    while index < length:
        if text[index].isspace() and index > 0 and text[index - 1].isalpha():
            cursor = index
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor < length and text[cursor].isalpha():
                left_isolated = index < 2 or not text[index - 2].isalpha()
                right_isolated = cursor + 1 >= length or not text[cursor + 1].isalpha()
                if left_isolated or right_isolated:
                    count += 1
            index = cursor
            continue
        index += 1
    return count


def _looks_letter_spaced(text: str) -> bool:
    tokens = text.split()
    singles = sum(1 for token in tokens if _is_single_letter_token(token))
    xy_pairs = 0
    for left, right in zip(tokens, tokens[1:]):
        if _is_single_letter_token(left) and _is_single_letter_token(right):
            xy_pairs += 1
    isolated = _isolated_letter_space_joins(text)
    return singles >= 3 or xy_pairs >= 2 or isolated >= 2


def _squeeze_hyphen_spaces(text: str) -> str:
    squeezed = text
    while " -" in squeezed or "- " in squeezed:
        squeezed = squeezed.replace(" -", "-").replace("- ", "-")
    return squeezed


def _collapse_letter_letter_spaces(text: str) -> str:
    chars: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace() and chars and chars[-1].isalpha():
            cursor = index
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor < length and text[cursor].isalpha():
                left_isolated = len(chars) < 2 or not chars[-2].isalpha()
                right_isolated = cursor + 1 >= length or not text[cursor + 1].isalpha()
                if left_isolated or right_isolated:
                    index = cursor
                    continue
        chars.append(char)
        index += 1
    return "".join(chars)


def collapse_letter_spacing(text: str) -> str:
    stripped = text.strip()
    if not stripped or not _looks_letter_spaced(stripped):
        return stripped
    collapsed = _collapse_letter_letter_spaces(stripped)
    return _squeeze_hyphen_spaces(collapsed)


def _first_non_header_line(page1_text: str) -> str:
    for line in (page1_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if looks_like_header(stripped):
            continue
        return stripped
    return ""


def resolve_draft_title(paper_id: str, raw_title: str, page1_text: str = "") -> str:
    catalog = catalog_title_for_paper_id(paper_id)
    if catalog is not None:
        return catalog
    candidate = (raw_title or "").strip()
    if not candidate or looks_like_header(candidate):
        candidate = _first_non_header_line(page1_text)
    if not candidate:
        return ""
    return collapse_letter_spacing(candidate)
