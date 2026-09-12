import asyncio
import unittest
from enum import Enum

from cli_bridge.clients import FakeClients
from cli_bridge.delivery import (
    DELIVERY_EXCEPTION,
    DELIVERY_MISSING,
    DELIVERY_UNSUCCESSFUL,
    resolve_adapter,
)
from cli_bridge.models import ClientResult
from cli_bridge.plugin import _STATE, on_unload
from tests.helpers import FakeAdapter, FakeGateway, invoke, owner_event, register_plugin, temp_roots


class PlainPlatform(Enum):
    FEISHU = "feishu"
    SLACK = "slack"


class DeliveryResolveTests(unittest.TestCase):
    def test_string_and_plain_enum_match_only_requested_platform(self):
        feishu = FakeAdapter()
        slack = FakeAdapter()
        gateway = FakeGateway()
        gateway.adapters = {PlainPlatform.FEISHU: feishu, PlainPlatform.SLACK: slack}
        adapter, err = resolve_adapter(gateway, "feishu")
        self.assertIs(adapter, feishu)
        self.assertIsNone(err)
        adapter, err = resolve_adapter(gateway, PlainPlatform.SLACK)
        self.assertIs(adapter, slack)
        missing, err = resolve_adapter(gateway, "telegram")
        self.assertIsNone(missing)
        self.assertEqual(err, DELIVERY_MISSING)

    def test_unknown_platform_does_not_use_other_adapter(self):
        slack = FakeAdapter()
        gateway = FakeGateway()
        gateway.adapters = {PlainPlatform.SLACK: slack}
        adapter, err = resolve_adapter(gateway, "feishu")
        self.assertIsNone(adapter)
        self.assertEqual(err, DELIVERY_MISSING)


class DeliverySendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_plain_enum_async_completion_and_peer_handoff(self):
        clients = FakeClients()
        data, project = temp_roots()
        extra = {
            "cli_role": "codex",
            "allowed_group_chat_ids": ["oc-dev"],
            "trusted_peer_open_ids": ["ou-peer-grok"],
            "peer_open_id": "ou-peer-grok",
            "peer_name": "Grok",
        }
        ctx = register_plugin(clients, data, project, extra=extra)
        gateway = FakeGateway()
        adapter = gateway.adapters.pop("feishu")
        gateway.adapters[PlainPlatform.FEISHU] = adapter
        event = owner_event(
            "/dev-prd need add",
            chat_type="group",
            chat_id="oc-dev",
            message_id="m1",
        )
        _, accepted = await invoke(ctx, gateway, event)
        self.assertIn("accepted", accepted)
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(accepted.split()[1])
        self.assertEqual(rec.stage, "draft")
        self.assertEqual(rec.last_delivery_status, "ok")
        self.assertTrue(adapter.sent)
        self.assertIn("/dev-approve", adapter.sent[-1]["content"])
        rec = _STATE.engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        from cli_bridge.plugin import _send_peer_handoff
        from cli_bridge.route import extract_route, set_route

        route = extract_route(event)
        set_route(route)
        ok, status = await _send_peer_handoff(gateway, route, rec)
        self.assertTrue(ok)
        self.assertEqual(status, "ok")
        self.assertIn('<at user_id="ou-peer-grok">', adapter.sent[-1]["content"])
        self.assertIn("/dev-build", adapter.sent[-1]["content"])

    async def test_send_exception_is_token_not_raw_text(self):
        clients = FakeClients([ClientResult("ok", "# PRD\nbody\n")])
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        gateway = FakeGateway()
        gateway.adapters["feishu"] = FakeAdapter(raise_exc=True)
        _, accepted = await invoke(ctx, gateway, owner_event("/dev-prd x", message_id="e1"))
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(accepted.split()[1])
        self.assertEqual(rec.last_delivery_status, DELIVERY_EXCEPTION)
        self.assertEqual(rec.last_error, "delivery failed: send_exception")
        self.assertNotIn("boom", rec.last_error or "")

    async def test_unsuccessful_send_recorded(self):
        clients = FakeClients([ClientResult("ok", "# PRD\nbody\n")])
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        _, accepted = await invoke(
            ctx, FakeGateway(success=False), owner_event("/dev-prd x", message_id="u1")
        )
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(accepted.split()[1])
        self.assertEqual(rec.last_delivery_status, DELIVERY_UNSUCCESSFUL)
        self.assertIn("send_unsuccessful", rec.last_error)


class HostPlatformTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_installed_hermes_platform_enum(self):
        try:
            from gateway.config import Platform
        except ImportError:
            self.skipTest("installed Hermes gateway.config.Platform unavailable")
        self.assertFalse(issubclass(Platform, str))
        data, project = temp_roots()
        ctx = register_plugin(FakeClients(), data, project)
        gateway = FakeGateway()
        adapter = gateway.adapters.pop("feishu")
        gateway.adapters[Platform.FEISHU] = adapter
        _, accepted = await invoke(ctx, gateway, owner_event("/dev-prd host", message_id="h1"))
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(accepted.split()[1])
        self.assertEqual(rec.stage, "draft")
        self.assertEqual(rec.last_delivery_status, "ok")
        self.assertTrue(adapter.sent)
