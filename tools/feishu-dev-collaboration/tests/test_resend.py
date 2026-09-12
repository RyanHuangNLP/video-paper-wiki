import asyncio
import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.models import ClientResult, sha256_text
from cli_bridge.plugin import _STATE, on_unload
from cli_bridge.store import TaskStore
from tests.helpers import FakeGateway, invoke, owner_event, register_plugin, temp_roots


class ResendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_resend_does_not_rerun_client_or_change_hash(self):
        clients = FakeClients([ClientResult("ok", "# PRD\nfixed body\n")])
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        gateway = FakeGateway()
        _, accepted = await invoke(ctx, gateway, owner_event("/dev-prd need", message_id="d1"))
        await asyncio.gather(*ctx.spawned)
        task_id = accepted.split()[1]
        rec = _STATE.engine.store.load(task_id)
        digest = rec.prd_hash
        self.assertEqual(digest, sha256_text(_STATE.engine.store.read_artifact(task_id, rec.prd_artifact)))
        calls_after_draft = list(clients.calls)
        gateway.adapters["feishu"].sent.clear()
        _, result = await invoke(
            ctx, gateway, owner_event("/dev-resend %s" % task_id, message_id="r1")
        )
        self.assertIn(task_id, result)
        rec2 = _STATE.engine.store.load(task_id)
        self.assertEqual(rec2.prd_hash, digest)
        self.assertEqual(rec2.stage, "draft")
        self.assertEqual(rec2.handoff_round, 0)
        self.assertEqual(rec2.approved_hash, None)
        self.assertEqual(clients.calls, calls_after_draft)
        self.assertTrue(gateway.adapters["feishu"].sent)
        content = gateway.adapters["feishu"].sent[-1]["content"]
        self.assertIn(digest, content)
        self.assertIn("/dev-approve", content)
        self.assertNotIn("/dev-approve %s" % task_id, content)

    async def test_resend_handoff_does_not_start_build(self):
        extra = {
            "cli_role": "codex",
            "allowed_group_chat_ids": ["oc-dev"],
            "trusted_peer_open_ids": ["ou-peer-grok"],
            "peer_open_id": "ou-peer-grok",
            "peer_name": "Grok",
        }
        data, project = temp_roots()
        clients = FakeClients()
        ctx = register_plugin(clients, data, project, extra=extra)
        store = TaskStore(data, project)
        seeder = TaskEngine(
            store,
            clients=clients,
            owner_open_id="openid-owner",
            owner_chat_id="oc-dev",
        )
        rec, _ = seeder.start_draft("need", "m1", "openid-owner", "oc-dev")
        rec = await seeder.run_draft(rec.task_id)
        rec = seeder.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        _STATE.engine = seeder
        gateway = FakeGateway()
        event = owner_event(
            "/dev-resend %s handoff" % rec.task_id,
            chat_type="group",
            chat_id="oc-dev",
            message_id="rh1",
        )
        _, result = await invoke(ctx, gateway, event)
        rec2 = seeder.store.load(rec.task_id)
        self.assertEqual(rec2.stage, "approved")
        self.assertEqual(rec2.handoff_round, 0)
        self.assertTrue(any("/dev-build" in item["content"] for item in gateway.adapters["feishu"].sent))
        self.assertEqual([c[0] for c in clients.calls], ["draft"])
        self.assertIn(rec.task_id, result)

    async def test_peer_cannot_resend(self):
        extra = {
            "cli_role": "codex",
            "allowed_group_chat_ids": ["oc-dev"],
            "trusted_peer_open_ids": ["ou-peer-grok"],
        }
        ctx = register_plugin(FakeClients(), *temp_roots(), extra=extra)
        event = owner_event(
            "/dev-resend %s" % ("a" * 32),
            chat_type="group",
            chat_id="oc-dev",
            open_id="ou-peer-grok",
            sender_type="app",
            is_bot=True,
        )
        _, result = await invoke(ctx, FakeGateway(), event)
        self.assertEqual(result, "Unauthorized.")
