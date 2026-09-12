"""Narrow parser for official arXiv abstract-page normalized text, without I/O."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from video_paper_wiki_research.preview_contracts import MAX_BYTES, fail, reference, timestamp

ADAPTER = "arxiv-abs-normalized-v1"
_MODERN = re.compile(r"([0-9]{2})([0-9]{2})\.([0-9]{4,5})")
_LEGACY = re.compile(r"([A-Za-z][A-Za-z0-9.-]*)/([0-9]{2})([0-9]{2})([0-9]{3})")
_VERSION = re.compile(r"(.+?)v([0-9]+)")
_MARKER = re.compile(r"arXiv:([A-Za-z0-9./-]+(?:v[0-9]+)?)", re.I)
_FIELDS = re.compile(r"^(?:>\s*)?(?:#+\s*)?(Title|Authors|Abstract|Subjects|Cite as|Comments|Journal reference|Report number|DOI|Related DOI)\s*:\s*(.*)$", re.I)


def normalize_arxiv(value: object) -> tuple[str, int | None]:
    if type(value) is not str or len(value) > 4096:
        fail("ARXIV_ID_INVALID", "provide a bounded arXiv ID or official HTTPS abstract URL")
    text = value.strip()
    if not text or any(c.isspace() or ord(c) < 32 for c in text) or "%" in text or "\\" in text:
        fail("ARXIV_ID_INVALID", "arXiv identity contains ambiguous characters")
    if "://" in text:
        try:
            parsed = urlsplit(text)
        except ValueError:
            fail("ARXIV_ID_INVALID", "arXiv URL is malformed")
        if (parsed.scheme != "https" or parsed.netloc != "arxiv.org" or parsed.query or parsed.fragment
                or not parsed.path.startswith("/abs/")):
            fail("ARXIV_ID_INVALID", "only exact official HTTPS arXiv abstract URLs are accepted")
        text = parsed.path[5:]
    elif text.lower().startswith("arxiv:"):
        text = text[6:]
    version = None
    match = _VERSION.fullmatch(text)
    if match:
        digits = match.group(2)
        if len(digits) > 4 or not 1 <= int(digits) <= 9999:
            fail("ARXIV_ID_INVALID", "arXiv version is outside 1..9999")
        text, version = match.group(1), int(digits)
    modern = _MODERN.fullmatch(text)
    legacy = _LEGACY.fullmatch(text)
    if modern is not None:
        month = int(modern.group(2))
    elif legacy is not None:
        month = int(legacy.group(3))
        text = text.lower()
    else:
        fail("ARXIV_ID_INVALID", "arXiv ID grammar is invalid")
    if not 1 <= month <= 12:
        fail("ARXIV_ID_INVALID", "arXiv ID contains an invalid month")
    return text, version


def validate_origin_url(value: object) -> None:
    if type(value) is not str or any(ord(c) < 33 for c in value) or "%" in value or "\\" in value:
        fail("OBSERVATION_BINDING_MISMATCH", "observed URL is not an exact official URL")
    try:
        parsed = urlsplit(value)
    except ValueError:
        fail("OBSERVATION_BINDING_MISMATCH", "observed URL is malformed")
    if parsed.scheme != "https" or parsed.netloc != "arxiv.org" or parsed.query or parsed.fragment:
        fail("OBSERVATION_BINDING_MISMATCH", "observed URL is outside the requested HTTPS origin")


def _labels(text: str) -> list[str]:
    labels = []
    for match in re.finditer(r"cite[^†]+†([^]+)|【[^†】]+†([^】]+)】|\[([^\]]+)\]\([^\n)]+\)", text):
        label = next(group for group in match.groups() if group is not None).split("†", 1)[0]
        labels.append(label)
    return labels


def _undecorate(text: str) -> str:
    def label(match):
        return next(group for group in match.groups() if group is not None).split("†", 1)[0]
    text = re.sub(r"cite[^†]+†([^]+)|【[^†】]+†([^】]+)】|\[([^\]]+)\]\([^\n)]+\)", label, text)
    return text.replace("\u00a0", " ").strip()


def _lines(text: str) -> tuple[list[str], list[str]]:
    if type(text) is not str:
        fail("OBSERVATION_MISSING", "normalized text is unavailable")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        fail("ARXIV_METADATA_INCOMPLETE", "normalized text is not UTF-8")
    if size > MAX_BYTES:
        fail("RESPONSE_TOO_LARGE", "normalized page exceeds one MiB")
    raw_lines = text.splitlines()
    # The Web rendering can place the next L<number>: on the same physical line.
    # Its numbered stream, including empty numbered lines, is the boundary.
    numbered = list(re.finditer(r"(?<!\S)L(\d+):[ \t]?", text))
    if numbered:
        if any(len(item.group(1)) > 7 or not item.group(1).isascii() for item in numbered):
            fail("ARXIV_METADATA_INCOMPLETE", "normalized line number is outside the supported range")
        numbers = [int(item.group(1)) for item in numbered]
        if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            fail("ARXIV_METADATA_INCOMPLETE", "normalized page line sequence is incomplete")
        raw_lines = [text[item.end():numbered[index + 1].start() if index + 1 < len(numbered) else len(text)].strip()
                     for index, item in enumerate(numbered)]
    return raw_lines, [_undecorate(line) for line in raw_lines]


def _history_time(value: str) -> str:
    value = re.sub(r"\s+\([^)]*\)\s*$", "", value).strip()
    try:
        dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        fail("ARXIV_METADATA_INCOMPLETE", "submission history timestamp is missing or unsupported")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_normalized_page(text: str, *, entity_id: str, requested_version: int | None) -> dict:
    raw_lines, lines = _lines(text)
    fields = {}
    for index, line in enumerate(lines):
        match = _FIELDS.fullmatch(line)
        if re.fullmatch(r"(?:#+\s*)?Submission history\s*:?", line, re.I):
            if "submission history" in fields:
                fail("ARXIV_METADATA_INCOMPLETE", "normalized page repeats submission history")
            fields["submission history"] = (index, "")
        if match is not None:
            key = match.group(1).casefold()
            if key in fields:
                fail("ARXIV_METADATA_INCOMPLETE", "normalized page has duplicate named sections", section=key)
            fields[key] = (index, match.group(2).lstrip("| "))

    # Identity only comes from trusted cite/current-version sections, never footer links.
    trusted = []
    if "cite as" in fields:
        begin = fields["cite as"][0]
        end = min([row[0] for row in fields.values() if row[0] > begin] or [len(lines)])
        trusted.extend(lines[begin:end])
    trusted.extend(line for line in lines if line.startswith("[Submitted on "))
    entities, versions = set(), set()
    for line in trusted:
        for match in _MARKER.finditer(line):
            candidate, version = normalize_arxiv(match.group(1))
            entities.add(candidate)
            if version is not None:
                versions.add(version)
        if line.startswith("[Submitted on "):
            versions.update(int(x) for x in re.findall(r"\(this version, v([1-9][0-9]{0,3})\)", line))
    if entities and entities != {entity_id}:
        fail("ARXIV_ID_MISMATCH", "trusted page markers identify a different paper")
    if not entities or not versions:
        fail("ARXIV_VERSION_UNCONFIRMED", "page does not establish this paper's current version")
    if len(versions) != 1:
        fail("ARXIV_VERSION_MISMATCH", "trusted page version markers conflict")
    resolved = next(iter(versions))
    if requested_version is not None and resolved != requested_version:
        fail("ARXIV_VERSION_MISMATCH", "the served abstract belongs to another version")
    required = {"title", "authors", "abstract", "subjects", "cite as", "submission history"}
    if not required <= set(fields):
        fail("ARXIV_METADATA_INCOMPLETE", "normalized page lacks required bibliographic sections")
    order = [fields[key][0] for key in ("title", "authors", "abstract", "subjects", "cite as", "submission history")]
    if order != sorted(order):
        fail("ARXIV_METADATA_INCOMPLETE", "named page sections are out of order")

    def block(key: str) -> str:
        index, initial = fields[key]
        end = min([row[0] for row in fields.values() if row[0] > index] or [len(lines)])
        return "\n".join([initial, *lines[index + 1:end]]).strip()

    title = fields["title"][1].strip()
    authors_begin = fields["authors"][0]
    linked_authors = _labels(raw_lines[authors_begin])
    authors = [part.strip() for part in linked_authors or fields["authors"][1].split(",")]
    abstract = block("abstract")
    # A new named field always terminates abstract text. Omissions never become prose.
    if not title or not abstract or any(not author for author in authors) or re.search(r"\b(?:omitted|truncated)\b|\.\.\.|…", abstract, re.I):
        fail("ARXIV_METADATA_INCOMPLETE", "title, authors or abstract are empty or explicitly incomplete")
    subjects = block("subjects")
    categories = re.findall(r"\(([A-Za-z][A-Za-z0-9.-]*)\)", subjects)
    if not categories:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]*(?:\s*;\s*[A-Za-z][A-Za-z0-9.-]*)*", subjects):
            categories = [value.strip() for value in subjects.split(";")]
        else:
            fail("ARXIV_METADATA_INCOMPLETE", "subject categories are unavailable")
    if len(set(categories)) != len(categories):
        fail("ARXIV_METADATA_INCOMPLETE", "subject categories are duplicated")

    history_start = fields["submission history"][0] + 1
    history, boundary, malformed, submitter = {}, False, False, False
    for line in lines[history_start:]:
        if re.match(r"^(?:#+\s*)?(?:Download|Access Paper|References\s*&\s*Citations|Bibliographic|Bookmark|Full-text|Related Papers|Submission history ends)\b", line, re.I):
            boundary = True
            break
        if re.match(r"^#+\s+", line):
            break
        item = re.fullmatch(r"\[v([1-9][0-9]{0,3})\]\s+(.+)", line)
        if item is not None:
            number = int(item.group(1))
            if number in history:
                fail("ARXIV_METADATA_INCOMPLETE", "submission history repeats a version")
            history[number] = _history_time(item.group(2))
        elif line.startswith("[v") or re.search(r"\b(?:omitted|truncated)\b|\.\.\.|…", line, re.I):
            malformed = True
        elif line:
            if not history and not submitter and re.fullmatch(r"From: .+\[\s*view email\s*\]", line):
                submitter = True
            else:
                fail("ARXIV_METADATA_INCOMPLETE", "submission history contains an unsupported line")
    if 1 not in history or resolved not in history:
        fail("ARXIV_METADATA_INCOMPLETE", "history lacks initial or resolved-version timestamps")
    ordered = sorted(history)
    complete = boundary and not malformed and ordered == list(range(1, max(ordered) + 1))
    latest = resolved == max(ordered) if complete else None
    others = "yes" if any(number != resolved for number in history) else "no" if complete else "unknown"
    return {"entity_id": entity_id, "requested_version": requested_version, "resolved_version": resolved,
            "latest_at_observation": latest, "other_versions_exist": others,
            "title": title, "authors": authors, "published_at": history[1], "updated_at": history[resolved],
            "categories": categories, "abstract": abstract,
            "abstract_url": f"https://arxiv.org/abs/{entity_id}v{resolved}",
            "pdf_url": f"https://arxiv.org/pdf/{entity_id}v{resolved}"}


def derive_metadata(request: dict, observation: dict) -> dict:
    data, observed = request["data"], observation["data"]
    if observed["request"] != reference(request) or observed["source_url"] != data["source_url"]:
        fail("OBSERVATION_BINDING_MISMATCH", "observation does not bind this request")
    if observed["capability_profile"] != "normalized-content":
        fail("CONNECTOR_CAPABILITY_UNAVAILABLE", "byte-exact page execution is unavailable in this adapter")
    reported = observed["reported_content_type"]
    if reported is not None and reported.split(";", 1)[0].strip().lower() != "text/html":
        fail("MEDIA_TYPE_REFUSED", "normalized abstract page was not reported as HTML")
    status = observed["outcome"]["status"]
    if status != "ok":
        codes = {"not_found": "ARXIV_VERSION_UNAVAILABLE" if data["requested_version"] is not None else "ARXIV_ENTRY_NOT_FOUND",
                 "timeout": "CONNECTOR_TIMEOUT", "rate_limited": "CONNECTOR_RATE_LIMITED", "failure": "CONNECTOR_FAILURE"}
        fail(codes[status], "connector observation cannot produce paper metadata",
             retry_after_seconds=observed["outcome"]["retry_after_seconds"])
    parsed = parse_normalized_page(observed["payload"]["text"], entity_id=data["entity_id"],
                                   requested_version=data["requested_version"])
    return {"request": reference(request), "observation": reference(observation), **parsed,
            "observed_at": observed["observed_at"], "adapter": ADAPTER,
            "preview_only": True, "ingest_authorized": False}
