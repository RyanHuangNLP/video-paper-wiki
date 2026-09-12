import asyncio
import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.handoff import extract_command_text, format_peer_ping, ping_for_record
from cli_bridge.store import TaskStore
from tests.helpers import FakeGateway, invoke, make_engine, owner_event, register_plugin, temp_roots


GROUP = {
    "allowed_group_chat_ids": ["oc-dev"],
    "trusted_peer_open_ids": ["ou-peer-codex", "ou-peer-grok"],
}


class HandoffUnitTests(unittest.TestCase):
    def test_extract_command_strips_at_markup(self):
        self.assertEqual(
            extract_command_text('<at user_id="ou-peer-grok">Grok</at> /dev-build abc'),
            "/dev-build abc",
        )
        self.assertEqual(extract_command_text("@Grok /dev-review abc"), "/dev-review abc")
        self.assertEqual(extract_command_text("/dev-help"), "/dev-help")
        self.assertEqual(extract_command_text("please ship it"), "please ship it")

    def test_ping_does_not_require_inbound_membership(self):
        ping = format_peer_ping("/dev-build abc", "ou-mention-only", "Grok")
        self.assertEqual(
            ping, '<at user_id="ou-mention-only">Grok</at> /dev-build abc'
        )
        self.assertIsNone(
            format_peer_ping('/dev-build x', 'ou_"onclick', "X")
        )
        ping = format_peer_ping(
            "/dev-build abc",
            "ou-peer-grok",
            'Grok<script>',
        )
        self.assertEqual(ping, '<at user_id="ou-peer-grok">Grok</at> /dev-build abc')
        self.assertNotIn("<script", ping)
        self.assertIsNone(
            format_peer_ping(
                "/dev-build abc",
                "ou-peer-grok",
                "Grok",
                self_open_id="ou-peer-grok",
            )
        )


class HandoffDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data, self.project = temp_roots()
        self.clients = FakeClients()
        self.gateway = FakeGateway()

    async def test_approve_in_group_pings_grok(self):
        extra = {
            "cli_role": "codex",
            "peer_open_id": "ou-peer-grok",
            "peer_name": "Grok开发",
            **GROUP,
        }
        ctx = register_plugin(self.clients, self.data, self.project, extra=extra)
        from cli_bridge.plugin import _STATE
        from cli_bridge.engine import TaskEngine
        from cli_bridge.store import TaskStore

        store = TaskStore(self.data, self.project)
        seeder = TaskEngine(
            store,
            clients=self.clients,
            owner_open_id="openid-owner",
            owner_chat_id="oc-dev",
        )
        rec, _ = seeder.start_draft("need add", "m1", "openid-owner", "oc-dev")
        rec = await seeder.run_draft(rec.task_id)
        _STATE.engine = seeder
        event = owner_event(
            "/dev-approve %s %s" % (rec.task_id, rec.prd_hash),
            chat_type="group",
            chat_id="oc-dev",
            message_id="m2",
        )
        _, result = await invoke(ctx, self.gateway, event)
        self.assertIn("approved", result)
        ping_kwargs = self.gateway.adapters["feishu"].sent[-1]
        ping = ping_kwargs["content"]
        self.assertIn('<at user_id="ou-peer-grok">', ping)
        self.assertIn("/dev-build %s" % rec.task_id, ping)
        self.assertTrue(ping.startswith("<at "))
        self.assertNotIn("reply_to", ping_kwargs)

    async def test_dm_approve_does_not_ping(self):
        extra = {
            "cli_role": "codex",
            "peer_open_id": "ou-peer-grok",
            "peer_name": "Grok",
            **GROUP,
        }
        ctx = register_plugin(self.clients, self.data, self.project, extra=extra)
        from cli_bridge.plugin import _STATE

        seeder = TaskEngine(
            TaskStore(self.data, self.project),
            clients=self.clients,
            owner_open_id="openid-owner",
            owner_chat_id="chat-owner",
        )
        rec, _ = seeder.start_draft("need add", "m1", "openid-owner", "chat-owner")
        rec = await seeder.run_draft(rec.task_id)
        _STATE.engine = seeder
        _, result = await invoke(
            ctx,
            self.gateway,
            owner_event("/dev-approve %s %s" % (rec.task_id, rec.prd_hash), message_id="m2"),
        )
        self.assertIn("approved", result)
        self.assertEqual(self.gateway.adapters["feishu"].sent, [])

    async def test_grok_build_completion_pings_codex(self):
        extra = {
            "cli_role": "grok",
            "peer_open_id": "ou-peer-codex",
            "peer_name": "Codex架构",
            **GROUP,
        }
        ctx = register_plugin(self.clients, self.data, self.project, extra=extra)
        seeder = TaskEngine(
            TaskStore(self.data, self.project),
            clients=self.clients,
            owner_open_id="openid-owner",
            owner_chat_id="oc-dev",
            cli_role="both",
        )
        rec, _ = seeder.start_draft("need add", "m1", "openid-owner", "oc-dev")
        rec = await seeder.run_draft(rec.task_id)
        rec = seeder.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        event = owner_event(
            "/dev-build %s" % rec.task_id,
            chat_type="group",
            chat_id="oc-dev",
            message_id="m3",
            open_id="ou-peer-codex",
            sender_type="app",
            is_bot=True,
        )
        _, result = await invoke(ctx, self.gateway, event)
        self.assertIn("building", result)
        await asyncio.gather(*ctx.spawned)
        sent = self.gateway.adapters["feishu"].sent
        contents = [item["content"] for item in sent]
        pings = [item for item in sent if str(item.get("content", "")).startswith("<at ")]
        self.assertTrue(pings)
        ping_kwargs = pings[-1]
        ping = ping_kwargs["content"]
        self.assertIn('<at user_id="ou-peer-codex">', ping)
        self.assertIn("/dev-review %s" % rec.task_id, ping)
        self.assertTrue(
            any(
                "stage=built" in item or "已向 architect 发出 /dev-review" in item
                for item in contents
            )
        )
        self.assertNotIn("reply_to", ping_kwargs)

    async def test_mention_prefixed_command_is_not_help(self):
        extra = {"cli_role": "grok", **GROUP}
        ctx = register_plugin(self.clients, self.data, self.project, extra=extra)
        event = owner_event(
            '<at user_id="ou-peer-codex">Codex</at> /dev-status',
            chat_type="group",
            chat_id="oc-dev",
            open_id="ou-peer-codex",
            sender_type="app",
            is_bot=True,
        )
        rewrite, result = await invoke(ctx, self.gateway, event)
        self.assertEqual(rewrite["action"], "rewrite")
        self.assertEqual(rewrite["text"], "/dev-status")
        self.assertEqual(result, "no tasks")

    async def test_handoff_round_limit(self):
        engine, _, _ = make_engine(self.clients)
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        rec = engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        rec.handoff_round = 8
        engine.store.save(rec)
        with self.assertRaises(RuntimeError):
            engine.request_build(rec.task_id, "openid-owner", "m3")
        rec = engine.store.load(rec.task_id)
        self.assertEqual(rec.stage, "failed")


class PingRecordTests(unittest.TestCase):
    def test_no_ping_for_draft(self):
        rec = type("R", (), {"stage": "draft", "task_id": "a" * 32})()
        self.assertIsNone(ping_for_record(rec, "ou-peer-grok", "Grok"))
