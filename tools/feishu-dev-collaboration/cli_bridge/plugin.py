"""Hermes register() glue. No IO during registration."""

import asyncio

from .constants import (
    ALLOWED_GROUP_CHAT_TYPE,
    ARTIFACT_SELECTORS,
    HELP_TEXT,
    HUMAN_ONLY_COMMANDS,
    MAX_MESSAGE_CHARS,
    PEER_COMMANDS,
    ROLE_DENIED,
    SAFE_COMMAND_FAILED,
    SHA256_RE,
    TASK_ID_RE,
    UNAUTHORIZED,
    commands_for_role,
    help_text_for_role,
)
from .delivery import (
    DELIVERY_EXCEPTION,
    DELIVERY_MISSING,
    DELIVERY_NO_MENTION,
    DELIVERY_OK,
    DELIVERY_SKIPPED,
    DELIVERY_UNSUCCESSFUL,
    resolve_adapter,
    send_result_mentions,
)
from .engine import TaskEngine
from .handoff import peer_handoff_command, ping_for_record
from .roster import commands_for_roles, load_roster
from .route import (
    actor_kind,
    get_gateway,
    get_route,
    normalize_id_list,
    pre_gateway_dispatch,
    route_authorized,
    set_own_commands,
)
from .sanitize import safe_text
from .summary import strip_identity_preamble
from .store import TaskStore


class PluginState:
    def __init__(self):
        self.ctx = None
        self.engine = None
        self.owner_open_id = ""
        self.owner_chat_id = ""
        self.data_root = ""
        self.project_root = ""
        self.execution_policy = None
        self.clients = None
        self.cli_role = ""
        self.allowed_group_chat_ids = []
        self.trusted_peer_open_ids = []
        self.self_open_id = ""
        self.peer_open_id = ""
        self.peer_name = ""
        self.owner_alias_open_ids = []
        self.own_commands = ()
        self.roster = None


_STATE = PluginState()


def _as_id_list(value):
    return normalize_id_list(value)


def _config(ctx):
    owner_open_id = ctx.get_config("owner_open_id", "") or ""
    owner_chat_id = ctx.get_config("owner_chat_id", "") or ""
    data_root = ctx.get_config("data_root", "") or ""
    project_root = ctx.get_config("project_root", "") or ""
    execution_policy = ctx.get_config("execution_policy", None)
    cli_role = ctx.get_config("cli_role", "") or ""
    allowed_group_chat_ids = _as_id_list(ctx.get_config("allowed_group_chat_ids", None))
    trusted_peer_open_ids = _as_id_list(ctx.get_config("trusted_peer_open_ids", None))
    self_open_id = ctx.get_config("self_open_id", "") or ""
    peer_open_id = ctx.get_config("peer_open_id", "") or ""
    peer_name = ctx.get_config("peer_name", "") or ""
    owner_alias_open_ids = _as_id_list(ctx.get_config("owner_alias_open_ids", None))
    return {
        "owner_open_id": owner_open_id,
        "owner_chat_id": owner_chat_id,
        "data_root": data_root,
        "project_root": project_root,
        "execution_policy": execution_policy,
        "cli_role": cli_role,
        "allowed_group_chat_ids": allowed_group_chat_ids,
        "trusted_peer_open_ids": trusted_peer_open_ids,
        "self_open_id": self_open_id,
        "peer_open_id": peer_open_id,
        "peer_name": peer_name,
        "owner_alias_open_ids": owner_alias_open_ids,
        "roster": ctx.get_config("roster", None),
        "roster_self": ctx.get_config("roster_self", None),
    }


def _ensure_engine():
    if _STATE.engine is not None:
        return _STATE.engine
    store = TaskStore(_STATE.data_root, _STATE.project_root)
    _STATE.engine = TaskEngine(
        store,
        clients=_STATE.clients,
        execution_policy=_STATE.execution_policy,
        owner_open_id=_STATE.owner_open_id,
        owner_chat_id=_STATE.owner_chat_id,
        cli_role=_STATE.cli_role,
        trusted_peer_open_ids=_STATE.trusted_peer_open_ids,
        owner_alias_open_ids=_STATE.owner_alias_open_ids,
    )
    return _STATE.engine


def _auth():
    route = get_route()
    if not route_authorized(
        route,
        _STATE.owner_open_id,
        _STATE.owner_chat_id,
        allowed_group_chat_ids=_STATE.allowed_group_chat_ids,
        trusted_peer_open_ids=_STATE.trusted_peer_open_ids,
        self_open_id=_STATE.self_open_id,
    ):
        return None
    return route


def _actor():
    route = _auth()
    if route is None:
        return None, None
    kind = actor_kind(route, _STATE.owner_open_id, _STATE.trusted_peer_open_ids)
    if kind is None:
        return None, None
    return route, kind


def _peer_roles(route):
    roster = _STATE.roster
    if roster is None or route is None:
        return None
    entry = roster.by_inbound(route.open_id)
    if entry is None:
        return None
    return entry.roles


def _command_allowed(name, kind, route=None):  # route used for peer role checks
    if name not in _STATE.own_commands:
        return False
    if kind == "peer" and name not in PEER_COMMANDS:
        return False
    if kind == "peer" and name in HUMAN_ONLY_COMMANDS:
        return False
    if kind == "peer" and name in ("dev-build", "dev-review"):
        roles = _peer_roles(route)
        if roles is None:
            return False
        if roles <= frozenset({"observe"}):
            return False
    return True


async def _send_human_summary(gateway, route, content):
    if gateway is None or route is None:
        return False, DELIVERY_MISSING
    adapter, err = resolve_adapter(gateway, route.platform)
    if adapter is None:
        return False, err or DELIVERY_MISSING
    try:
        result = await adapter.send(
            chat_id=route.chat_id,
            content=safe_text(strip_identity_preamble(content), limit=MAX_MESSAGE_CHARS),
            reply_to=route.message_id,
        )
    except Exception:
        return False, DELIVERY_EXCEPTION
    if getattr(result, "success", False) is not True:
        return False, DELIVERY_UNSUCCESSFUL
    return True, DELIVERY_OK


async def _send_unicast_command(gateway, route, content):
    if gateway is None or route is None:
        return False, DELIVERY_MISSING
    adapter, err = resolve_adapter(gateway, route.platform)
    if adapter is None:
        return False, err or DELIVERY_MISSING
    try:
        result = await adapter.send(
            chat_id=route.chat_id,
            content=safe_text(strip_identity_preamble(content), limit=MAX_MESSAGE_CHARS),
        )
    except Exception:
        return False, DELIVERY_EXCEPTION
    if getattr(result, "success", False) is not True:
        return False, DELIVERY_UNSUCCESSFUL
    if not send_result_mentions(result):
        return False, DELIVERY_NO_MENTION
    return True, DELIVERY_OK


async def _send_with_status(gateway, route, content):
    return await _send_human_summary(gateway, route, content)


async def _send(gateway, route, content):
    ok, _status = await _send_with_status(gateway, route, content)
    return ok


def _handoff_entry(rec):
    command = peer_handoff_command(rec)
    if not command:
        return None
    roster = _STATE.roster
    if roster is None:
        return None
    if command.startswith("/dev-build"):
        return roster.default_peer_for_role("build")
    if command.startswith("/dev-review"):
        return roster.default_peer_for_role("review")
    return None


async def _send_peer_handoff(gateway, route, rec):
    if route is None or route.chat_type != ALLOWED_GROUP_CHAT_TYPE:
        return True, DELIVERY_SKIPPED
    if peer_handoff_command(rec) is None:
        return True, DELIVERY_SKIPPED
    entry = _handoff_entry(rec)
    if entry is None or not entry.mention_open_id:
        return True, DELIVERY_SKIPPED
    ping = ping_for_record(
        rec,
        entry.mention_open_id,
        entry.display_name,
        self_open_id=_STATE.self_open_id,
    )
    if not ping:
        return True, DELIVERY_SKIPPED
    return await _send_unicast_command(gateway, route, ping)


def _capture_delivery():
    return get_route(), get_gateway()


def _register_job(task_id, coro, name):
    if _STATE.ctx is not None:
        handle = _STATE.ctx.spawn_task(coro, name=name)
    else:
        handle = asyncio.create_task(coro, name=name)
    engine = _STATE.engine
    if engine is not None:
        engine._jobs[task_id] = handle
        def drop_finished(done):
            if engine._jobs.get(task_id) is done:
                engine._jobs.pop(task_id, None)
        handle.add_done_callback(drop_finished)
    return handle


async def _supervised(task_id, route, gateway, runner):
    engine = _STATE.engine
    rec = None
    try:
        rec = await runner()
    except asyncio.CancelledError:
        try:
            rec = engine.store.load(task_id)
            if rec.stage != "cancelled":
                rec = engine.cancel(task_id, rec.owner_open_id)
        except Exception:
            pass
        raise
    except Exception:
        try:
            rec = engine.fail_job(task_id, "job failed")
        except Exception:
            pass
    finally:
        if engine is not None:
            engine._jobs.pop(task_id, None)
    if rec is None:
        return
    _pinged, handoff_status = await _send_peer_handoff(gateway, route, rec)
    try:
        engine.note_delivery(task_id, "handoff", handoff_status)
    except Exception:
        pass
    rec = engine.store.load(task_id)
    _delivered, user_status = await _send_human_summary(
        gateway, route, engine.completion_message(rec, handoff_status=handoff_status)
    )
    try:
        engine.note_delivery(task_id, "user", user_status)
    except Exception:
        pass


def _wrap(handler):
    async def inner(raw_args):
        try:
            result = await handler(raw_args if isinstance(raw_args, str) else "")
        except Exception:
            return SAFE_COMMAND_FAILED
        if isinstance(result, str):
            return strip_identity_preamble(result)
        return result

    return inner


async def cmd_help(raw_args):
    route, kind = _actor()
    if route is None or not _command_allowed("dev-help", kind, route):
        return UNAUTHORIZED
    return help_text_for_role(_STATE.cli_role) if _STATE.cli_role else HELP_TEXT


async def cmd_prd(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-prd", kind, route):
        return ROLE_DENIED if kind == "owner" else UNAUTHORIZED
    engine = _ensure_engine()
    rec, dup = engine.start_draft(
        (raw_args or "").strip(),
        route.message_id,
        route.open_id,
        route.chat_id,
    )
    if dup:
        return "duplicate ignored %s" % rec.task_id
    route, gateway = _capture_delivery()

    async def run():
        return await engine.run_draft(rec.task_id)

    _register_job(
        rec.task_id,
        _supervised(rec.task_id, route, gateway, run),
        name="prd-%s" % rec.task_id,
    )
    return "task %s accepted (drafting)" % rec.task_id


async def cmd_approve(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-approve", kind, route):
        return UNAUTHORIZED
    parts = (raw_args or "").split()
    if len(parts) != 2 or not TASK_ID_RE.match(parts[0]) or not SHA256_RE.match(parts[1]):
        return "Usage: /dev-approve <task-id> <sha256>"
    engine = _ensure_engine()
    rec = engine.approve(parts[0], parts[1], route.open_id, route.message_id)
    captured_route, gateway = _capture_delivery()
    _ok, handoff_status = await _send_peer_handoff(gateway, captured_route, rec)
    try:
        engine.note_delivery(rec.task_id, "handoff", handoff_status)
    except Exception:
        pass
    return engine.completion_message(rec, handoff_status=handoff_status)


async def cmd_build(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-build", kind, route):
        return ROLE_DENIED if kind in ("owner", "peer") else UNAUTHORIZED
    task_id = (raw_args or "").strip()
    engine = _ensure_engine()
    rec, dup = engine.request_build(task_id, route.open_id, route.message_id)
    if dup:
        return "duplicate ignored %s" % rec.task_id
    route, gateway = _capture_delivery()

    async def run():
        return await engine.run_build(rec.task_id)

    _register_job(
        rec.task_id,
        _supervised(rec.task_id, route, gateway, run),
        name="build-%s" % rec.task_id,
    )
    return "task %s accepted (building)" % rec.task_id


async def cmd_review(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-review", kind, route):
        return ROLE_DENIED if kind in ("owner", "peer") else UNAUTHORIZED
    task_id = (raw_args or "").strip()
    engine = _ensure_engine()
    rec, dup = engine.request_review(task_id, route.open_id, route.message_id)
    if dup:
        return "duplicate ignored %s" % rec.task_id
    route, gateway = _capture_delivery()
    async def run():
        return await engine.run_review(rec.task_id)

    _register_job(
        rec.task_id,
        _supervised(rec.task_id, route, gateway, run),
        name="review-%s" % rec.task_id,
    )
    return "task %s accepted (reviewing)" % rec.task_id


async def cmd_status(raw_args):
    route, kind = _actor()
    if route is None or not _command_allowed("dev-status", kind, route):
        return UNAUTHORIZED
    engine = _ensure_engine()
    task_id = (raw_args or "").strip() or None
    recs = engine.status(task_id)
    if not recs:
        return "no tasks"
    return "\n".join(engine.summarize(r) for r in recs)


async def cmd_artifact(raw_args):
    route, kind = _actor()
    if route is None or not _command_allowed("dev-artifact", kind, route):
        return UNAUTHORIZED
    parts = (raw_args or "").split()
    if len(parts) not in (2, 3) or parts[1] not in ARTIFACT_SELECTORS:
        return "Usage: /dev-artifact <task-id> <prd|build|review> [page]"
    page = int(parts[2]) if len(parts) == 3 else 1
    return _ensure_engine().paged_artifact(parts[0], parts[1], page, route.open_id)


async def cmd_cancel(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-cancel", kind, route):
        return UNAUTHORIZED
    engine = _ensure_engine()
    rec = engine.cancel((raw_args or "").strip(), route.open_id)
    return engine.summarize(rec)


async def cmd_resend(raw_args):
    route, kind = _actor()
    if route is None:
        return UNAUTHORIZED
    if not _command_allowed("dev-resend", kind, route):
        return UNAUTHORIZED
    parts = (raw_args or "").split()
    if not parts or not TASK_ID_RE.match(parts[0]) or len(parts) > 2:
        return "Usage: /dev-resend <task-id> [handoff]"
    target = "user"
    if len(parts) == 2:
        if parts[1] != "handoff":
            return "Usage: /dev-resend <task-id> [handoff]"
        target = "handoff"
    engine = _ensure_engine()
    rec, dup = engine.request_resend(parts[0], route.open_id, route.message_id, target=target)
    if dup:
        return "duplicate ignored %s" % rec.task_id
    captured_route, gateway = _capture_delivery()
    if target == "handoff":
        _ok, status = await _send_peer_handoff(gateway, captured_route, rec)
        engine.note_delivery(rec.task_id, "handoff", status)
        return engine.summarize(engine.store.load(rec.task_id))
    _ok, status = await _send_human_summary(
        gateway, captured_route, engine.completion_message(rec)
    )
    engine.note_delivery(rec.task_id, "user", status)
    return engine.summarize(engine.store.load(rec.task_id))


def on_unload():
    set_own_commands(None)
    engine = _STATE.engine
    if engine is None:
        _STATE.ctx = None
        return
    for task_id, job in list(engine._jobs.items()):
        try:
            job.cancel()
        except Exception:
            pass
        engine._jobs.pop(task_id, None)
    _STATE.engine = None
    _STATE.ctx = None


_COMMAND_SPEC = (
    ("dev-help", cmd_help, "Show commands", "", "text"),
    ("dev-prd", cmd_prd, "Draft a PRD (Codex)", "<requirement>", "text"),
    ("dev-approve", cmd_approve, "Approve PRD digest (human only)", "<task-id> <sha256>", "text"),
    ("dev-build", cmd_build, "Run Grok Build", "<task-id>", "text"),
    ("dev-review", cmd_review, "Run Codex review", "<task-id>", "text"),
    ("dev-status", cmd_status, "Show task status", "[task-id]", "text"),
    ("dev-cancel", cmd_cancel, "Cancel owner task", "<task-id>", "text"),
    ("dev-artifact", cmd_artifact, "Read task artifact", "<task-id> <prd|build|review> [page]", "text"),
    ("dev-resend", cmd_resend, "Resend last result without rerunning CLI", "<task-id> [handoff]", "text"),
)


def register(ctx):
    on_unload()
    cfg = _config(ctx)
    roster = load_roster(cfg)
    _STATE.ctx = ctx
    _STATE.owner_open_id = cfg["owner_open_id"]
    _STATE.owner_chat_id = cfg["owner_chat_id"]
    _STATE.data_root = cfg["data_root"]
    _STATE.project_root = cfg["project_root"]
    _STATE.execution_policy = cfg["execution_policy"]
    _STATE.cli_role = cfg["cli_role"]
    _STATE.allowed_group_chat_ids = cfg["allowed_group_chat_ids"]
    _STATE.roster = roster
    _STATE.trusted_peer_open_ids = list(roster.inbound_ids())
    _STATE.self_open_id = cfg["self_open_id"]
    _STATE.peer_open_id = ""
    _STATE.peer_name = ""
    _STATE.owner_alias_open_ids = cfg["owner_alias_open_ids"]
    self_entry = roster.self_entry()
    if self_entry is not None:
        _STATE.own_commands = commands_for_roles(self_entry.roles)
    else:
        _STATE.own_commands = commands_for_role(_STATE.cli_role)
    _STATE.engine = None
    _STATE.clients = getattr(_STATE, "clients", None)
    set_own_commands(_STATE.own_commands)
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
    handlers = {item[0]: item[1] for item in _COMMAND_SPEC}
    for name, _handler, description, args_hint, argument_mode in _COMMAND_SPEC:
        if name not in _STATE.own_commands:
            continue
        ctx.register_command(
            name,
            _wrap(handlers[name]),
            description=description,
            args_hint=args_hint,
            argument_mode=argument_mode,
        )
    ctx.on_unload(on_unload)
