"""Shared test fixtures. Synthetic IDs and temp directories only."""

import asyncio
import os
import tempfile
from types import SimpleNamespace

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.plugin import _STATE, register
from cli_bridge.route import make_sdk_event
from cli_bridge.store import TaskStore


class SendResult:
    def __init__(self, success=True, mentions=None):
        self.success = success
        self.mentions = mentions if mentions is not None else []


class FakeAdapter:
    def __init__(self, success=True, raise_exc=False, mentions=None):
        self.success = success
        self.raise_exc = raise_exc
        self.forced_mentions = mentions
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        if self.raise_exc:
            raise RuntimeError("adapter boom")
        if self.forced_mentions is not None:
            mentions = self.forced_mentions
        elif "<at " in (kwargs.get("content") or ""):
            mentions = [{"id": "auto"}]
        else:
            mentions = []
        return SendResult(self.success, mentions=mentions)


class FakeGateway:
    def __init__(self, success=True, mentions=None):
        self.adapters = {"feishu": FakeAdapter(success=success, mentions=mentions)}


class FakeCtx:
    def __init__(self, config):
        self._config = config
        self.hooks = {}
        self.commands = {}
        self.spawned = []
        self.unload = None

    def get_config(self, key, default=None):
        return self._config.get(key, default)

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_command(self, name, handler, description="", args_hint="", argument_mode="text"):
        self.commands[name] = handler

    def spawn_task(self, coro, name=""):
        task = asyncio.create_task(coro, name=name)
        self.spawned.append(task)
        return task

    def on_unload(self, callback):
        self.unload = callback


def temp_roots():
    root = os.path.realpath(tempfile.mkdtemp(prefix="cli-bridge-test-"))
    data = os.path.join(root, "data")
    project = os.path.join(root, "project")
    os.makedirs(data)
    os.makedirs(project)
    return data, project


def make_engine(clients=None, **engine_kwargs):
    data, project = temp_roots()
    store = TaskStore(data, project)
    kwargs = {
        "owner_open_id": "openid-owner",
        "owner_chat_id": "chat-owner",
    }
    kwargs.update(engine_kwargs)
    engine = TaskEngine(
        store,
        clients=clients or FakeClients(),
        **kwargs,
    )
    return engine, data, project


def owner_event(text="/dev-help", message_id="msg-1", **kwargs):
    return make_sdk_event(text=text, message_id=message_id, **kwargs)


def register_plugin(clients, data_root, project_root, extra=None):
    _STATE.clients = clients
    config = {
        "owner_open_id": "openid-owner",
        "owner_chat_id": "chat-owner",
        "data_root": data_root,
        "project_root": project_root,
        "execution_policy": None,
    }
    if extra:
        config.update(extra)
    ctx = FakeCtx(config)
    register(ctx)
    _STATE.clients = clients
    _STATE.engine = None
    return ctx


async def invoke(ctx, gateway, event):
    hook = ctx.hooks["pre_gateway_dispatch"]
    rewrite = hook(event, gateway)
    text = event.text
    if isinstance(rewrite, dict) and rewrite.get("action") == "rewrite":
        text = rewrite.get("text") or "/dev-help"
    name = text.strip().split(None, 1)[0][1:]
    raw = ""
    if " " in text.strip():
        raw = text.strip().split(None, 1)[1]
    handler = ctx.commands.get(name)
    if handler is None:
        return rewrite, None
    result = await handler(raw)
    return rewrite, result
