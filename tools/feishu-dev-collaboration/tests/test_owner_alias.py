import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.models import ClientResult
from cli_bridge.store import TaskStore
from tests.helpers import temp_roots


class OwnerAliasTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_alias_fails_closed_for_other_app_owner(self):
        data, project = temp_roots()
        store = TaskStore(data, project)
        codex = TaskEngine(
            store,
            clients=FakeClients(),
            owner_open_id="ou-codex-human",
            owner_chat_id="oc-dev",
        )
        rec, _ = codex.start_draft("need", "m1", "ou-codex-human", "oc-dev")
        rec = await codex.run_draft(rec.task_id)
        grok = TaskEngine(
            store,
            clients=FakeClients(),
            owner_open_id="ou-grok-human",
            owner_chat_id="oc-dev",
            cli_role="grok",
        )
        with self.assertRaises(PermissionError):
            grok.cancel(rec.task_id, "ou-grok-human")
        with self.assertRaises(PermissionError):
            grok.approve(rec.task_id, rec.prd_hash, "ou-grok-human", "m2")

    async def test_configured_alias_allows_cancel_not_peer_approve(self):
        data, project = temp_roots()
        store = TaskStore(data, project)
        clients = FakeClients()
        codex = TaskEngine(
            store,
            clients=clients,
            owner_open_id="ou-codex-human",
            owner_chat_id="oc-dev",
            cli_role="codex",
        )
        rec, _ = codex.start_draft("need", "m1", "ou-codex-human", "oc-dev")
        rec = await codex.run_draft(rec.task_id)
        rec = codex.approve(rec.task_id, rec.prd_hash, "ou-codex-human", "m2")
        grok = TaskEngine(
            store,
            clients=FakeClients(),
            owner_open_id="ou-grok-human",
            owner_chat_id="oc-dev",
            cli_role="grok",
            trusted_peer_open_ids=["ou-peer-codex"],
            owner_alias_open_ids=["ou-codex-human"],
        )
        cancelled = grok.cancel(rec.task_id, "ou-grok-human")
        self.assertEqual(cancelled.stage, "cancelled")
        rec2, _ = codex.start_draft("need2", "n1", "ou-codex-human", "oc-dev")
        rec2 = await codex.run_draft(rec2.task_id)
        with self.assertRaises(PermissionError):
            grok.approve(rec2.task_id, rec2.prd_hash, "ou-peer-codex", "n2")
        with self.assertRaises(PermissionError):
            grok.cancel(rec2.task_id, "ou-peer-codex")
        with self.assertRaises(PermissionError):
            grok.cancel(rec2.task_id, "stranger")

    async def test_unknown_historical_owner_fail_closed(self):
        data, project = temp_roots()
        store = TaskStore(data, project)
        engine = TaskEngine(
            store,
            clients=FakeClients([ClientResult("ok", "# PRD\nbody\n")]),
            owner_open_id="ou-current",
            owner_chat_id="oc-dev",
            owner_alias_open_ids=["ou-other-self"],
        )
        rec, _ = engine.start_draft("need", "m1", "ou-current", "oc-dev")
        rec = await engine.run_draft(rec.task_id)
        rec.owner_open_id = "ou-unknown-history"
        engine.store.save(rec)
        with self.assertRaises(PermissionError):
            engine.cancel(rec.task_id, "ou-current")
