"""Human-summary readability rules. Not a security boundary."""

import re

from .constants import TASK_ID_RE

_AT_RE = re.compile(r"<at\b", re.I)
_EXEC_RE = re.compile(r"/dev-[a-z]+(?:-[a-z]+)*\s+[0-9a-f]{32}", re.I)
_IDENTITY_PREFIX_RE = re.compile(
    r"^(?:我是负责调用codex cli的bot|我是调用grok cli的bot)\s*",
    re.I,
)


def strip_identity_preamble(text):
    """Drop known command-reply identity recitals. Profile/plugin layer only."""
    if not isinstance(text, str):
        return text
    return _IDENTITY_PREFIX_RE.sub("", text, count=1).lstrip("\n")


def human_summary_violations(text):
    if not isinstance(text, str):
        return ["not_text"]
    issues = []
    if _IDENTITY_PREFIX_RE.match(text):
        issues.append("persona")
    if _AT_RE.search(text):
        issues.append("at_tag")
    if _EXEC_RE.search(text):
        issues.append("executable_command")
    for line in text.splitlines():
        if line.strip().startswith("/"):
            issues.append("leading_slash_line")
            break
    return issues


def human_summary_ok(text):
    return not human_summary_violations(text)


def executable_command_in(text):
    if not isinstance(text, str):
        return False
    return bool(_EXEC_RE.search(text))


def task_id_in_command(text, task_id):
    if not task_id or not TASK_ID_RE.match(task_id):
        return False
    if not isinstance(text, str):
        return False
    return bool(re.search(r"/dev-[a-z]+(?:-[a-z]+)*\s+" + re.escape(task_id), text, re.I))
