import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.constants import ROLE_DENIED, UNAUTHORIZED, commands_for_role
from cli_bridge.plugin import _STATE
from tests.helpers import FakeGateway, invoke, owner_event, register_plugin, temp_roots


GROUP = {
    "allowed_group_chat_ids": ["oc-dev"],
    "trusted_peer_open_ids": ["ou-peer-codex", "ou-peer-grok"],
}


class DualBotDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data, self.project = temp_roots()
        self.clients = FakeClients()
        self.gateway = FakeGateway()

    async def test_default_still_rejects_group_and_bot(self):
        ctx = register_plugin(self.clients, self.data, self.project)
        _, result = await invoke(
            ctx, self.gateway, owner_event("/dev-help", chat_type="group", chat_id="oc-dev")
        )
        self.assertEqual(result, UNAUTHORIZED)
        _, result = await invoke(
            ctx, self.gateway, owner_event("/dev-help", is_bot=True, sender_type="app")
        )
        self.assertEqual(result, UNAUTHORIZED)
        self.assertEqual(self.clients.calls, [])

    async def test_group_owner_help_when_allowlisted(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "codex", **GROUP},
        )
        event = owner_event(
            "/dev-help",
            chat_type="group",
            chat_id="oc-dev",
            message_id="g1",
        )
        _, result = await invoke(ctx, self.gateway, event)
        self.assertIn("/dev-prd", result)
        self.assertNotIn("/dev-build", result)
        self.assertNotIn("dev-build", ctx.commands)

    async def test_grok_role_registers_build_not_prd(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "grok", **GROUP},
        )
        self.assertIn("dev-build", ctx.commands)
        self.assertNotIn("dev-prd", ctx.commands)
        self.assertNotIn("dev-approve", ctx.commands)
        self.assertNotIn("dev-review", ctx.commands)
        self.assertEqual(
            commands_for_role("grok"),
            ("dev-help", "dev-build", "dev-status", "dev-cancel", "dev-artifact", "dev-resend"),
        )

    async def test_peer_inbound_open_id_need_not_match_mention_target(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={
                "cli_role": "codex",
                "peer_open_id": "ou-peer-grok-self",
                "peer_name": "grok",
                "allowed_group_chat_ids": ["oc-dev"],
                "trusted_peer_open_ids": [
                    "ou-peer-grok-self",
                    "ou-peer-grok-inbound",
                ],
            },
        )
        unknown, unknown_result = await invoke(
            ctx,
            self.gateway,
            owner_event(
                "/dev-status",
                chat_type="group",
                chat_id="oc-dev",
                open_id="ou-other-bot",
                sender_type="app",
                is_bot=True,
                message_id="bot-unknown",
            ),
        )
        self.assertEqual(unknown_result, UNAUTHORIZED)
        _, result = await invoke(
            ctx,
            self.gateway,
            owner_event(
                "/dev-status",
                chat_type="group",
                chat_id="oc-dev",
                open_id="ou-peer-grok-inbound",
                sender_type="app",
                is_bot=True,
                message_id="bot-inbound",
            ),
        )
        self.assertEqual(result, "no tasks")

    async def test_peer_can_request_build_on_grok_bot(self):
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
        rec = seeder.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        grok = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "grok", **GROUP},
        )
        event = owner_event(
            "/dev-build %s" % rec.task_id,
            chat_type="group",
            chat_id="oc-dev",
            message_id="m3",
            open_id="ou-peer-codex",
            sender_type="app",
            is_bot=True,
        )
        _, result = await invoke(grok, self.gateway, event)
        self.assertIn("accepted", result)
        self.assertIn("building", result)

    async def test_peer_cannot_approve(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "codex", **GROUP},
        )
        event = owner_event(
            "/dev-approve %s %s" % ("a" * 32, "b" * 64),
            chat_type="group",
            chat_id="oc-dev",
            open_id="ou-peer-grok",
            sender_type="app",
            is_bot=True,
        )
        _, result = await invoke(ctx, self.gateway, event)
        self.assertEqual(result, UNAUTHORIZED)
        self.assertEqual(self.clients.calls, [])

    async def test_self_open_id_ignored(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "codex", "self_open_id": "openid-owner", **GROUP},
        )
        _, result = await invoke(ctx, self.gateway, owner_event("/dev-help", chat_type="group", chat_id="oc-dev"))
        self.assertEqual(result, UNAUTHORIZED)

    async def test_wrong_group_rejected(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "codex", **GROUP},
        )
        _, result = await invoke(
            ctx,
            self.gateway,
            owner_event("/dev-help", chat_type="group", chat_id="oc-other"),
        )
        self.assertEqual(result, UNAUTHORIZED)

    async def test_owner_on_grok_cannot_use_prd_command(self):
        ctx = register_plugin(
            self.clients,
            self.data,
            self.project,
            extra={"cli_role": "grok", **GROUP},
        )
        self.assertIsNone(ctx.commands.get("dev-prd"))
        rewrite, result = await invoke(
            ctx,
            self.gateway,
            owner_event("/dev-prd x", chat_type="group", chat_id="oc-dev"),
        )
        self.assertEqual(rewrite["action"], "rewrite")
        self.assertIn("/dev-build", result)
        self.assertNotIn("/dev-prd", result)
        self.assertEqual(self.clients.calls, [])
        self.assertEqual(ROLE_DENIED, "This bot does not handle that command.")
