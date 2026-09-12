"""Feishu bot-to-bot handoff pings. Mentions must be real <at> tags."""

import re

from .constants import STAGE_APPROVED, STAGE_BUILT, STAGE_NEEDS_CHANGES

PEER_OPEN_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,80}$")
_AT_TAG_RE = re.compile(r'^(?:<at\s+user_id="[^"]+">[^<]*</at>\s*)+')
_AT_NAME_RE = re.compile(r"^@\S+\s+")
_NAME_SAFE_RE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fff ]+")


def sanitize_peer_name(name):
    stripped = re.sub(r"<[^>]*>", "", name or "")
    cleaned = _NAME_SAFE_RE.sub("", stripped.strip())[:32].strip()
    return cleaned or "peer"


def extract_command_text(text):
    if not isinstance(text, str):
        return text
    remaining = text.strip()
    remaining = _AT_TAG_RE.sub("", remaining, count=1).strip()
    while True:
        match = _AT_NAME_RE.match(remaining)
        if not match:
            break
        rest = remaining[match.end() :]
        if not rest.startswith("/"):
            break
        remaining = rest
    return remaining.strip()


def peer_handoff_command(rec):
    if rec is None:
        return None
    if rec.stage == STAGE_APPROVED:
        return "/dev-build %s" % rec.task_id
    if rec.stage == STAGE_BUILT:
        return "/dev-review %s" % rec.task_id
    if rec.stage == STAGE_NEEDS_CHANGES:
        return "/dev-build %s" % rec.task_id
    return None


def format_peer_ping(command, mention_open_id, display_name, self_open_id=""):
    """Build a unicast @ command. mention_open_id is not an inbound allowlist member."""
    if not isinstance(command, str) or not command.startswith("/"):
        return None
    if not PEER_OPEN_ID_RE.match(mention_open_id or ""):
        return None
    if self_open_id and mention_open_id == self_open_id:
        return None
    name = sanitize_peer_name(display_name)
    return '<at user_id="%s">%s</at> %s' % (mention_open_id, name, command)


def ping_for_record(rec, mention_open_id, display_name, self_open_id=""):
    command = peer_handoff_command(rec)
    if not command:
        return None
    return format_peer_ping(
        command,
        mention_open_id,
        display_name,
        self_open_id=self_open_id,
    )


def format_watcher_notify(narrative, watcher_entries):
    """Observer notify may @ watchers; must not carry an executable /dev-* task command."""
    if not isinstance(narrative, str) or not narrative.strip():
        return None
    tags = []
    for entry in watcher_entries or ():
        mention = getattr(entry, "mention_open_id", "") or ""
        if not PEER_OPEN_ID_RE.match(mention):
            continue
        name = sanitize_peer_name(getattr(entry, "display_name", "") or "peer")
        tags.append('<at user_id="%s">%s</at>' % (mention, name))
    if tags:
        return "%s %s" % (" ".join(tags), narrative.strip())
    return narrative.strip()
