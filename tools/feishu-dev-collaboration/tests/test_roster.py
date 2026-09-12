"""Section 6.1 roster/handoff contract tests. Drive shipped helpers only."""

import asyncio
import inspect
import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.constants import ROLE_DENIED
from cli_bridge.delivery import DELIVERY_NO_MENTION
from cli_bridge.engine import TaskEngine
from cli_bridge.handoff import format_peer_ping, format_watcher_notify, ping_for_record
from cli_bridge.plugin import _STATE, on_unload
from cli_bridge.roster import LEGACY_WARNING, RosterError, load_roster
from cli_bridge.store import TaskStore
from cli_bridge.summary import (
    human_summary_ok,
    human_summary_violations,
    strip_identity_preamble,
)
from tests.helpers import FakeGateway, invoke, owner_event, register_plugin, temp_roots


def _sample_roster(**kwargs):
    entry = {
        "id": "architect",
        "roles": ["review"],
        "display_name": "Codex",
        "mention_open_id": "ou-mention-architect",
        "inbound_open_ids": ["ou-inbound-architect"],
    }
    entry.update(kwargs)
    return [entry]


class RosterParseTests(unittest.TestCase):
    def test_roles_enum_rejects_prd_empty_and_unknown(self):
        with self.assertRaises(RosterError):
            load_roster({"roster": [{"id": "x", "roles": ["prd"]}]})
        with self.assertRaises(RosterError):
            load_roster({"roster": [{"id": "x", "roles": []}]})
        with self.assertRaises(RosterError):
            load_roster({"roster": [{"id": "x", "roles": ["wizard"]}]})

    def test_duplicate_inbound_id_fails_closed(self):
        with self.assertRaises(RosterError) as ctx:
            load_roster(
                {
                    "roster": [
                        {
                            "id": "a",
                            "roles": ["review"],
                            "inbound_open_ids": ["ou-shared"],
                        },
                        {
                            "id": "b",
                            "roles": ["build"],
                            "inbound_open_ids": ["ou-shared"],
                        },
                    ]
                }
            )
        self.assertIn("ou-shared", str(ctx.exception))

    def test_legacy_only_synthesizes_and_warns(self):
        roster = load_roster(
            {
                "cli_role": "codex",
                "peer_open_id": "ou-mention-peer",
                "trusted_peer_open_ids": ["ou-inbound-peer"],
                "peer_name": "Grok",
            }
        )
        self.assertEqual(roster.warnings, (LEGACY_WARNING,))
        self.assertEqual(len(roster.entries), 1)
        peer = roster.entries[0]
        self.assertEqual(peer.mention_open_id, "ou-mention-peer")
        self.assertEqual(peer.inbound_open_ids, frozenset({"ou-inbound-peer"}))
        ping = format_peer_ping("/dev-build x", peer.mention_open_id, peer.display_name)
        self.assertIn("ou-mention-peer", ping)
        self.assertIsNotNone(roster.by_inbound("ou-inbound-peer"))
        self.assertIsNone(roster.by_inbound("ou-mention-peer"))

    def test_mixed_keys_fail_closed(self):
        with self.assertRaises(RosterError):
            load_roster(
                {
                    "roster": _sample_roster(),
                    "roster_self": "architect",
                    "peer_open_id": "ou-legacy",
                }
            )
        with self.assertRaises(RosterError):
            load_roster(
                {
                    "roster": _sample_roster(),
                    "trusted_peer_open_ids": ["ou-inbound-architect"],
                }
            )

    def test_pure_new_config_ignores_empty_legacy(self):
        roster = load_roster(
            {
                "roster": _sample_roster(),
                "roster_self": "architect",
                "peer_open_id": "",
                "trusted_peer_open_ids": [],
            }
        )
        self.assertEqual(roster.warnings, ())
        self.assertEqual(roster.self_id, "architect")
        self.assertEqual(roster.by_id("architect").mention_open_id, "ou-mention-architect")


class ShippedPathContractTests(unittest.TestCase):
    def test_shipped_ping_signature_has_no_inbound_allowlist_param(self):
        params = inspect.signature(format_peer_ping).parameters
        self.assertNotIn("trusted_peer_open_ids", params)
        self.assertIn("mention_open_id", params)
        source = inspect.getsource(format_peer_ping)
        self.assertNotIn("trusted_peer", source)

    def test_unicast_send_source_omits_reply_to(self):
        from cli_bridge.plugin import _send_human_summary, _send_unicast_command

        unicast = inspect.getsource(_send_unicast_command)
        summary = inspect.getsource(_send_human_summary)
        self.assertNotIn("reply_to", unicast)
        self.assertIn("reply_to", summary)
        self.assertIn("send_result_mentions", unicast)


class SummaryReadabilityTests(unittest.TestCase):
    def test_strip_identity_preamble(self):
        body = "task=abc stage=built"
        self.assertEqual(
            strip_identity_preamble("我是负责调用codex cli的bot\n" + body),
            body,
        )
        self.assertEqual(
            strip_identity_preamble("我是调用grok cli的bot " + body),
            body,
        )
        self.assertEqual(strip_identity_preamble(body), body)
        self.assertIn(
            "persona",
            human_summary_violations("我是负责调用codex cli的bot\n" + body),
        )

    def test_narrative_command_name_without_task_id_passes(self):
        text = "task=abc stage=built\n已向 architect 发出 /dev-review"
        self.assertEqual(human_summary_violations(text), [])
        self.assertTrue(human_summary_ok(text))

    def test_executable_command_and_at_and_leading_slash_fail(self):
        task = "a" * 32
        self.assertIn(
            "executable_command",
            human_summary_violations("Next: /dev-build %s" % task),
        )
        self.assertIn("at_tag", human_summary_violations('<at user_id="ou-x">x</at> hi'))
        self.assertIn("leading_slash_line", human_summary_violations("note\n/dev-help\n"))

    def test_engine_completion_is_readable(self):
        from tests.helpers import make_engine

        engine, _, _ = make_engine()
        rec, _ = engine.start_draft("need multiply", "m1", "openid-owner", "chat-owner")
        rec = asyncio.run(engine.run_draft(rec.task_id))
        draft = engine.completion_message(rec)
        self.assertTrue(human_summary_ok(draft), human_summary_violations(draft))
        rec = engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        approved = engine.completion_message(rec)
        self.assertTrue(human_summary_ok(approved), human_summary_violations(approved))
        self.assertIn("已向 builder 发出 /dev-build", approved)
        from cli_bridge.summary import executable_command_in

        self.assertFalse(executable_command_in(approved))


class ObservePeerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_observe_peer_denied_build_review_but_notify_may_at(self):
        data, project = temp_roots()
        extra = {
            "cli_role": "grok",
            "allowed_group_chat_ids": ["oc-dev"],
            "roster_self": "hub",
            "roster": [
                {
                    "id": "hub",
                    "roles": ["build", "review"],
                    "self_open_id": "ou-self",
                    "display_name": "hub",
                },
                {
                    "id": "watcher",
                    "roles": ["observe"],
                    "display_name": "watch",
                    "mention_open_id": "ou-mention-watch",
                    "inbound_open_ids": ["ou-inbound-watch"],
                },
            ],
        }
        ctx = register_plugin(FakeClients(), data, project, extra=extra)
        event = owner_event(
            "/dev-build %s" % ("a" * 32),
            chat_type="group",
            chat_id="oc-dev",
            open_id="ou-inbound-watch",
            sender_type="app",
            is_bot=True,
        )
        _, result = await invoke(ctx, FakeGateway(), event)
        self.assertEqual(result, ROLE_DENIED)
        _, review = await invoke(
            ctx,
            FakeGateway(),
            owner_event(
                "/dev-review %s" % ("a" * 32),
                chat_type="group",
                chat_id="oc-dev",
                open_id="ou-inbound-watch",
                sender_type="app",
                is_bot=True,
                message_id="r1",
            ),
        )
        self.assertEqual(review, ROLE_DENIED)
        roster = _STATE.roster
        watcher = roster.by_id("watcher")
        notify = format_watcher_notify("构建已完成", [watcher])
        self.assertIn('<at user_id="ou-mention-watch">', notify)
        self.assertFalse(
            __import__("cli_bridge.summary", fromlist=["executable_command_in"]).executable_command_in(
                notify
            )
        )


class UnicastSendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_empty_mentions_is_not_ok(self):
        extra = {
            "cli_role": "codex",
            "allowed_group_chat_ids": ["oc-dev"],
            "trusted_peer_open_ids": ["ou-inbound-grok"],
            "peer_open_id": "ou-mention-grok",
            "peer_name": "Grok",
        }
        data, project = temp_roots()
        ctx = register_plugin(FakeClients(), data, project, extra=extra)
        store = TaskStore(data, project)
        seeder = TaskEngine(
            store,
            clients=FakeClients(),
            owner_open_id="openid-owner",
            owner_chat_id="oc-dev",
        )
        rec, _ = seeder.start_draft("need add", "m1", "openid-owner", "oc-dev")
        rec = await seeder.run_draft(rec.task_id)
        rec = seeder.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        _STATE.engine = seeder
        gateway = FakeGateway(mentions=[])
        event = owner_event(
            "/dev-resend %s handoff" % rec.task_id,
            chat_type="group",
            chat_id="oc-dev",
            message_id="rh-empty",
        )
        _, result = await invoke(ctx, gateway, event)
        rec2 = seeder.store.load(rec.task_id)
        self.assertEqual(rec2.last_handoff_status, DELIVERY_NO_MENTION)
        self.assertNotEqual(rec2.last_handoff_status, "ok")
        self.assertIn(rec.task_id, result)
        self.assertNotIn("reply_to", gateway.adapters["feishu"].sent[-1])

    async def test_mention_id_not_in_inbound_still_pings(self):
        ping = format_peer_ping("/dev-build abc", "ou-mention-only", "Grok")
        self.assertIsNotNone(ping)
        self.assertIn("ou-mention-only", ping)
        roster = load_roster(
            {
                "peer_open_id": "ou-mention-only",
                "trusted_peer_open_ids": ["ou-inbound-only"],
            }
        )
        self.assertIsNone(roster.by_inbound("ou-mention-only"))
        self.assertIsNotNone(
            ping_for_record(
                type("R", (), {"stage": "approved", "task_id": "a" * 32})(),
                roster.entries[0].mention_open_id,
                roster.entries[0].display_name,
            )
        )
