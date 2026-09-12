"""Parse a machine roster. Mention ids are not inbound ids."""

from dataclasses import dataclass

from .handoff import PEER_OPEN_ID_RE
from .route import normalize_id_list

ROSTER_ROLES = frozenset({"build", "review", "observe"})
LEGACY_WARNING = (
    "legacy peer_open_id/trusted_peer_open_ids synthesized into roster; remove old keys"
)


class RosterError(ValueError):
    """Fail-closed roster / settings error."""


@dataclass(frozen=True)
class RosterEntry:
    id: str
    roles: frozenset
    display_name: str
    self_open_id: str
    mention_open_id: str
    inbound_open_ids: frozenset


@dataclass(frozen=True)
class Roster:
    self_id: str
    entries: tuple
    warnings: tuple

    def by_id(self, entry_id):
        if not entry_id:
            return None
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def self_entry(self):
        return self.by_id(self.self_id)

    def by_inbound(self, open_id):
        if not open_id:
            return None
        for entry in self.entries:
            if open_id in entry.inbound_open_ids:
                return entry
        return None

    def inbound_ids(self):
        ids = set()
        for entry in self.entries:
            ids.update(entry.inbound_open_ids)
        return frozenset(ids)

    def default_peer_for_role(self, role):
        for entry in self.entries:
            if self.self_id and entry.id == self.self_id:
                continue
            if role in entry.roles and entry.mention_open_id:
                return entry
        return None


def _has_new_keys(settings):
    if settings.get("roster") is not None:
        return True
    self_id = settings.get("roster_self")
    return isinstance(self_id, str) and bool(self_id.strip())


def _legacy_peer(settings):
    return (settings.get("peer_open_id") or "").strip()


def _legacy_trusted(settings):
    return normalize_id_list(settings.get("trusted_peer_open_ids"))


def _has_legacy_keys(settings):
    return bool(_legacy_peer(settings) or _legacy_trusted(settings))


def _parse_roles(raw, entry_id):
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise RosterError("roster entry %s roles must be a list" % entry_id)
    roles = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise RosterError("roster entry %s has empty role" % entry_id)
        role = item.strip().lower()
        if role == "prd":
            raise RosterError("roster entry %s must not use role prd" % entry_id)
        if role not in ROSTER_ROLES:
            raise RosterError("roster entry %s has unknown role %s" % (entry_id, role))
        roles.append(role)
    if not roles:
        raise RosterError("roster entry %s has empty roles" % entry_id)
    return frozenset(roles)


def _parse_entry(raw):
    if not isinstance(raw, dict):
        raise RosterError("roster entry must be a mapping")
    entry_id = (raw.get("id") or "").strip()
    if not entry_id:
        raise RosterError("roster entry id is required")
    roles = _parse_roles(raw.get("roles"), entry_id)
    display_name = (raw.get("display_name") or entry_id).strip()
    self_open_id = (raw.get("self_open_id") or "").strip()
    mention_open_id = (raw.get("mention_open_id") or "").strip()
    if mention_open_id and not PEER_OPEN_ID_RE.match(mention_open_id):
        raise RosterError("roster entry %s has invalid mention_open_id" % entry_id)
    inbound = frozenset(normalize_id_list(raw.get("inbound_open_ids")))
    for inbound_id in inbound:
        if not PEER_OPEN_ID_RE.match(inbound_id):
            raise RosterError("roster entry %s has invalid inbound_open_id" % entry_id)
    return RosterEntry(
        id=entry_id,
        roles=roles,
        display_name=display_name,
        self_open_id=self_open_id,
        mention_open_id=mention_open_id,
        inbound_open_ids=inbound,
    )


def _parse_new(settings):
    raw_list = settings.get("roster")
    if raw_list is None:
        raw_list = []
    if not isinstance(raw_list, (list, tuple)):
        raise RosterError("roster must be a list")
    entries = []
    seen_ids = set()
    inbound_owner = {}
    for raw in raw_list:
        entry = _parse_entry(raw)
        if entry.id in seen_ids:
            raise RosterError("duplicate roster id %s" % entry.id)
        seen_ids.add(entry.id)
        for inbound_id in entry.inbound_open_ids:
            previous = inbound_owner.get(inbound_id)
            if previous:
                raise RosterError(
                    "inbound_open_id %s is claimed by %s and %s"
                    % (inbound_id, previous, entry.id)
                )
            inbound_owner[inbound_id] = entry.id
        entries.append(entry)
    self_id = (settings.get("roster_self") or "").strip()
    if self_id and self_id not in seen_ids:
        raise RosterError("roster_self %s is not a roster id" % self_id)
    return Roster(self_id=self_id, entries=tuple(entries), warnings=())


def _peer_roles_from_cli_role(cli_role):
    value = (cli_role or "").strip().lower()
    if value == "grok":
        return frozenset({"review"})
    if value == "codex":
        return frozenset({"build"})
    return frozenset({"build", "review"})


def _synthesize_legacy(settings):
    mention = _legacy_peer(settings)
    inbound = frozenset(_legacy_trusted(settings))
    if mention and not PEER_OPEN_ID_RE.match(mention):
        raise RosterError("legacy peer_open_id is invalid")
    name = (settings.get("peer_name") or "peer").strip() or "peer"
    entry = RosterEntry(
        id="legacy-peer",
        roles=_peer_roles_from_cli_role(settings.get("cli_role")),
        display_name=name,
        self_open_id="",
        mention_open_id=mention,
        inbound_open_ids=inbound,
    )
    return Roster(
        self_id="",
        entries=(entry,),
        warnings=(LEGACY_WARNING,),
    )


def load_roster(settings):
    """Pure function over a settings dict. Fail closed on mixed keys / bad roles."""
    if not isinstance(settings, dict):
        settings = {}
    new_keys = _has_new_keys(settings)
    legacy_keys = _has_legacy_keys(settings)
    if new_keys and legacy_keys:
        raise RosterError("roster and legacy peer keys cannot both be set")
    if new_keys:
        return _parse_new(settings)
    if legacy_keys:
        return _synthesize_legacy(settings)
    return Roster(self_id="", entries=(), warnings=())


def commands_for_roles(roles):
    wanted = set(roles or ())
    if not wanted:
        from .constants import COMMAND_NAMES

        return COMMAND_NAMES
    names = []
    from .constants import COMMAND_NAMES

    allow = {"dev-help", "dev-status", "dev-artifact"}
    if "review" in wanted:
        allow.update(
            {"dev-prd", "dev-approve", "dev-review", "dev-cancel", "dev-resend"}
        )
    if "build" in wanted:
        allow.update({"dev-build", "dev-cancel", "dev-resend"})
    for name in COMMAND_NAMES:
        if name in allow:
            names.append(name)
    return tuple(names)
