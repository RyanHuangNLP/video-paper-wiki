"""Seed http(s) URLs under ## 代码与资源. Offline urlsplit only. No PDF reads."""

from __future__ import annotations

from urllib.parse import urlsplit

from video_paper_wiki.notes.encoding import InvalidEncoding
from video_paper_wiki.notes.headings import replace_h2_body
from video_paper_wiki.resources import load_seed_json

_HEADING = "代码与资源"
_CODE_URLS_FILE = "engine-mvp-code-urls.json"


def is_http_url(value: str) -> bool:
    """True when *value* has an http(s) scheme and a netloc. No network."""
    stripped = str(value).strip()
    if not stripped or any(ch.isspace() for ch in stripped):
        return False
    try:
        parts = urlsplit(stripped)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def valid_http_urls(values: list[str]) -> list[str]:
    """Keep http(s) URLs with a netloc, in order. Drop invalid. No network."""
    urls: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if not is_http_url(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        urls.append(candidate)
    return urls


def load_code_urls() -> dict[str, list[str]] | None:
    """paper_id -> http(s) URLs. Legal empty seed → {}. Missing or unreadable → None."""
    try:
        payload = load_seed_json(_CODE_URLS_FILE)
    except InvalidEncoding:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("code_urls"), dict):
        return None
    raw_map = payload["code_urls"]
    mapping: dict[str, list[str]] = {}
    for raw_id, raw_urls in raw_map.items():
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        values: list[str] = []
        if isinstance(raw_urls, list):
            values = [item for item in raw_urls if isinstance(item, str)]
        elif isinstance(raw_urls, str):
            values = [raw_urls]
        urls = valid_http_urls(values)
        if urls:
            mapping[raw_id.strip()] = urls
    return mapping


def code_urls_for(paper_id: str) -> list[str]:
    wanted = str(paper_id).strip()
    if not wanted:
        return []
    mapping = load_code_urls()
    if mapping is None:
        return []
    return list(mapping.get(wanted, []))


def apply_clean_code_resources(text: str, paper_id: str = "") -> str:
    """Replace ## 代码与资源 with seeded http(s) URLs. Never reads a PDF body."""
    urls = code_urls_for(paper_id)
    body = [""] + urls + [""] if urls else [""]
    return replace_h2_body(text, _HEADING, body)
