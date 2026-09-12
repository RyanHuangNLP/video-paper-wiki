import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.models import ClientResult
from cli_bridge.store import TaskStore
from tests.helpers import temp_roots


class DualProfileIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_human_gate_alias_cancel_and_forbidden_paths(self):
        data, project = temp_roots()
        store = TaskStore(data, project)
        draft_text = "# PRD\nsubtract sample — tests only\n"
        clients = FakeClients(
            [
                ClientResult("ok", draft_text),
                ClientResult("ok", "implemented"),
                ClientResult(
                    "ok",
                    '{"verdict": "needs_changes", "explanation": "fix tests"}',
                ),
                ClientResult("ok", "fixed"),
                ClientResult(
                    "ok",
                    '{"verdict": "pass", "explanation": "tests pass"}',
                ),
            ]
        )
        codex = TaskEngine(
            store,
            clients=clients,
            owner_open_id="ou-codex-human",
            owner_chat_id="oc-dev",
            cli_role="codex",
            trusted_peer_open_ids=["ou-peer-grok"],
            owner_alias_open_ids=["ou-grok-human"],
        )
        grok = TaskEngine(
            store,
            clients=clients,
            owner_open_id="ou-grok-human",
            owner_chat_id="oc-dev",
            cli_role="grok",
            trusted_peer_open_ids=["ou-peer-codex"],
            owner_alias_open_ids=["ou-codex-human"],
        )
        rec, _ = codex.start_draft("need subtract", "m-draft", "ou-codex-human", "oc-dev")
        rec = await codex.run_draft(rec.task_id)
        self.assertEqual(rec.stage, "draft")
        with self.assertRaises(PermissionError):
            grok.approve(rec.task_id, rec.prd_hash, "ou-peer-codex", "m-bad")
        with self.assertRaises(ValueError):
            codex.approve(rec.task_id, "0" * 64, "ou-codex-human", "m-wrong")
        rec = codex.approve(rec.task_id, rec.prd_hash, "ou-codex-human", "m-ok")
        self.assertEqual(rec.stage, "approved")
        rec, dup = grok.request_build(rec.task_id, "ou-peer-codex", "m-build")
        self.assertFalse(dup)
        rec = await grok.run_build(rec.task_id)
        self.assertEqual(rec.stage, "built")
        rec, _ = codex.request_review(rec.task_id, "ou-codex-human", "m-rev1")
        rec = await codex.run_review(rec.task_id)
        self.assertEqual(rec.stage, "needs_changes")
        rec, _ = grok.request_build(rec.task_id, "ou-grok-human", "m-build2")
        rec = await grok.run_build(rec.task_id)
        rec, _ = codex.request_review(rec.task_id, "ou-peer-grok", "m-rev2")
        rec = await codex.run_review(rec.task_id)
        self.assertEqual(rec.stage, "ready_for_pr")
        rec2, _ = codex.start_draft("other", "z1", "ou-codex-human", "oc-dev")
        rec2 = await codex.run_draft(rec2.task_id)
        cancelled = grok.cancel(rec2.task_id, "ou-grok-human")
        self.assertEqual(cancelled.stage, "cancelled")
        with self.assertRaises(PermissionError):
            grok.cancel(rec.task_id, "ou-peer-codex")
        self.assertEqual(rec.handoff_round, 4)
