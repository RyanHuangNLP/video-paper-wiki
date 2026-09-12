"""Redaction and input limits. Regex is defense in depth, not complete coverage."""

import re

from .constants import MAX_PREVIEW_CHARS, MAX_SUMMARY_CHARS

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+")
_API_KEY_RE = re.compile(r"(?i)((?:api[_-]?key|sk-|xox[baprs]-)\s*[=:]?\s*)[A-Za-z0-9_\-]{8,}")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text):
    if not isinstance(text, str):
        return ""
    return _ANSI_RE.sub("", text)


def redact_secrets(text):
    if not isinstance(text, str):
        return ""
    out = _BEARER_RE.sub(r"\1[redacted]", text)
    out = _API_KEY_RE.sub(r"\1[redacted]", out)
    return out


def strip_controls(text):
    if not isinstance(text, str):
        return ""
    return _CTRL_RE.sub("", text)


def safe_text(text, limit=MAX_SUMMARY_CHARS):
    cleaned = strip_controls(redact_secrets(strip_ansi(text or "")))
    if len(cleaned) > limit:
        return cleaned[:limit] + "..."
    return cleaned


def preview(text):
    return safe_text(text, MAX_PREVIEW_CHARS)


def sanitize_persisted(text):
    """Redact and strip controls/ANSI with no truncation; hash binds this text."""
    return strip_controls(redact_secrets(strip_ansi(text or "")))


def reject_invalid_text(text, max_chars, field="input"):
    if not isinstance(text, str):
        raise ValueError("%s must be text" % field)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("%s is not valid UTF-8" % field)
    if "\x00" in text:
        raise ValueError("%s contains NUL" % field)
    if len(text) > max_chars:
        raise ValueError("%s exceeds length limit" % field)
    return text
