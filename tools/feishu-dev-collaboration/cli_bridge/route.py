"""Immutable Feishu DM route capture for pre_gateway_dispatch."""

from dataclasses import dataclass
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any, Optional

from .constants import (
    ALLOWED_CHAT_TYPE,
    ALLOWED_GROUP_CHAT_TYPE,
    ALLOWED_PLATFORM,
    ALLOWED_SENDER_TYPE,
    BOT_SENDER_TYPES,
    HERMES_BUILTIN_COMMANDS,
    OWN_COMMANDS,
    REWRITE_HELP,
)
from .handoff import extract_command_text

_ROUTE: ContextVar[Optional["Route"]] = ContextVar("cli_bridge_route", default=None)
_GATEWAY: ContextVar[Any] = ContextVar("cli_bridge_gateway", default=None)
_ACTIVE_COMMANDS = OWN_COMMANDS


def set_own_commands(names=None):
    global _ACTIVE_COMMANDS
    _ACTIVE_COMMANDS = frozenset(names) if names else OWN_COMMANDS


def normalize_id_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


@dataclass(frozen=True)
class Route:
    """Frozen snapshot of the authorized Feishu DM identity and adapter key."""

    platform: str
    chat_type: str
    chat_id: str
    message_id: str
    open_id: str
    sender_type: str
    is_bot: bool


def get_route():
    return _ROUTE.get()


def reset_route():
    _ROUTE.set(None)
    _GATEWAY.set(None)


def get_gateway():
    return _GATEWAY.get()


def set_route(route):
    _ROUTE.set(route)


def _attr(obj, name, default=None):
    if obj is None:
        return default
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _platform_value(source):
    platform = _attr(source, "platform")
    if platform is None:
        return None
    value = _attr(platform, "value", platform)
    if not isinstance(value, str):
        return None
    return value


def extract_openid(event):
    raw = _attr(event, "raw_message")
    inner = _attr(raw, "event")
    sender = _attr(inner, "sender")
    sender_id = _attr(sender, "sender_id")
    open_id = _attr(sender_id, "open_id")
    sender_type = _attr(sender, "sender_type")
    if not isinstance(open_id, str) or not open_id:
        return None, None
    if not isinstance(sender_type, str):
        return None, None
    return open_id, sender_type


def extract_route(event):
    if event is None:
        return None
    source = _attr(event, "source")
    if source is None:
        return None
    platform = _platform_value(source)
    chat_type = _attr(source, "chat_type")
    chat_id = _attr(source, "chat_id")
    message_id = _attr(event, "message_id")
    is_bot = _attr(source, "is_bot", False)
    open_id, sender_type = extract_openid(event)
    if not isinstance(chat_id, str) or not chat_id:
        return None
    if not isinstance(message_id, str) or not message_id:
        return None
    if not isinstance(chat_type, str):
        return None
    if platform is None:
        return None
    return Route(
        platform=platform,
        chat_type=chat_type,
        chat_id=chat_id,
        message_id=message_id,
        open_id=open_id,
        sender_type=sender_type,
        is_bot=bool(is_bot),
    )


def _is_peer_sender(route):
    return bool(route.is_bot) or route.sender_type in BOT_SENDER_TYPES


def actor_kind(route, owner_open_id, trusted_peer_open_ids=None):
    if route is None:
        return None
    if _is_peer_sender(route):
        peers = set(normalize_id_list(trusted_peer_open_ids))
        if route.open_id and route.open_id in peers:
            return "peer"
        return None
    if (
        route.sender_type == ALLOWED_SENDER_TYPE
        and not route.is_bot
        and route.open_id
        and route.open_id == owner_open_id
    ):
        return "owner"
    return None


def route_authorized(
    route,
    owner_open_id,
    owner_chat_id,
    allowed_group_chat_ids=None,
    trusted_peer_open_ids=None,
    self_open_id="",
):
    if route is None:
        return False
    if route.platform != ALLOWED_PLATFORM:
        return False
    if self_open_id and route.open_id == self_open_id:
        return False
    groups = set(normalize_id_list(allowed_group_chat_ids))
    if route.chat_type == ALLOWED_CHAT_TYPE:
        if not route.chat_id or route.chat_id != owner_chat_id:
            return False
    elif route.chat_type == ALLOWED_GROUP_CHAT_TYPE:
        if not groups or route.chat_id not in groups:
            return False
    else:
        return False
    return actor_kind(route, owner_open_id, trusted_peer_open_ids) is not None


def _command_name(text):
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    first = stripped.split(None, 1)[0][1:]
    return first


def should_rewrite(text):
    name = _command_name(extract_command_text(text))
    if name is None:
        return True
    if name in _ACTIVE_COMMANDS or name in HERMES_BUILTIN_COMMANDS:
        return False
    return True


def pre_gateway_dispatch(event, gateway, **kwargs):
    reset_route()
    route = extract_route(event)
    if route is None:
        return dict(REWRITE_HELP)
    set_route(route)
    _GATEWAY.set(gateway)
    text = _attr(event, "text", None)
    if text is None:
        content = _attr(event, "content")
        text = content if isinstance(content, str) else _attr(content, "text")
    cleaned = extract_command_text(text)
    if should_rewrite(cleaned):
        return dict(REWRITE_HELP)
    if isinstance(text, str) and cleaned != text.strip():
        return {"action": "rewrite", "text": cleaned}
    return None


def make_sdk_event(
    *,
    platform="feishu",
    chat_type="dm",
    chat_id="chat-owner",
    message_id="msg-1",
    open_id="openid-owner",
    sender_type="user",
    is_bot=False,
    text="/dev-help",
):
    platform_obj = SimpleNamespace(value=platform)
    source = SimpleNamespace(
        platform=platform_obj,
        chat_type=chat_type,
        chat_id=chat_id,
        is_bot=is_bot,
        user_id="unreliable-user-id",
    )
    sender_id = SimpleNamespace(open_id=open_id)
    sender = SimpleNamespace(sender_id=sender_id, sender_type=sender_type)
    inner = SimpleNamespace(sender=sender)
    raw = SimpleNamespace(event=inner)
    return SimpleNamespace(
        source=source,
        message_id=message_id,
        raw_message=raw,
        text=text,
    )
