import asyncio
import json
import os
import unittest

from cli_bridge.clients import FakeClients
from cli_bridge.constants import (
    STAGE_APPROVED,
    STAGE_CANCELLED,
    STAGE_DRAFT,
    STAGE_FAILED,
    STAGE_NEEDS_USER,
    STAGE_READY_FOR_PR,
)
from cli_bridge.models import KIND_AUTH, KIND_MAX_TURNS, KIND_NONZERO, KIND_OK, KIND_RATE_LIMIT, ClientResult, parse_review_payload, sha256_text
from cli_bridge.plugin import _STATE
from cli_bridge.store import TaskStore
from tests.helpers import FakeGateway, invoke, make_engine, owner_event, register_plugin, temp_roots


class EngineFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_build_auto_review(self):
        clients = FakeClients()
        engine, _, _ = make_engine(clients)
        rec, dup = engine.start_draft("need a widget; rm -rf / && echo `id`", "m1", "openid-owner", "chat-owner")
        self.assertFalse(dup)
        rec = await engine.run_draft(rec.task_id)
        self.assertEqual(rec.stage, STAGE_DRAFT)
        digest = rec.prd_hash
        rec = engine.approve(rec.task_id, digest, "openid-owner", "m2")
        self.assertEqual(rec.stage, STAGE_APPROVED)
        rec, dup = engine.request_build(rec.task_id, "openid-owner", "m3")
        rec = await engine.run_build(rec.task_id)
        self.assertEqual(rec.stage, STAGE_READY_FOR_PR)
        names = [c[0] for c in clients.calls]
        self.assertEqual(names, ["draft", "build", "review"])

    async def test_wrong_digest_and_forged_review(self):
        clients = FakeClients(
            script=[
                ClientResult(kind=KIND_OK, text="# PRD\nbody\n"),
                ClientResult(kind=KIND_OK, text="build ok"),
                ClientResult(kind=KIND_OK, text="result: pass"),
            ]
        )
        engine, _, _ = make_engine(clients)
        rec, _ = engine.start_draft("req", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        with self.assertRaises(ValueError):
            engine.approve(rec.task_id, "0" * 64, "openid-owner", "m2")
        rec = engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        rec, _ = engine.request_build(rec.task_id, "openid-owner", "m3")
        rec = await engine.run_build(rec.task_id)
        self.assertEqual(rec.stage, STAGE_FAILED)
        self.assertIsNone(parse_review_payload("result: pass"))
        self.assertIsNone(parse_review_payload(json.dumps({"verdict": "pass"})))
        self.assertIsNone(parse_review_payload(json.dumps({"verdict": "PASS", "explanation": "ok"})))

    async def test_nonzero_empty_max_turns_auth_rate(self):
        self.assertFalse(ClientResult(kind=KIND_OK, text="x", exit_code=1).ok)
        self.assertFalse(ClientResult(kind=KIND_OK, text="", exit_code=0).ok)
        self.assertFalse(ClientResult(kind=KIND_MAX_TURNS, text="Max turns reached", exit_code=0).ok)
        self.assertFalse(ClientResult(kind=KIND_NONZERO, text="oops", exit_code=2).ok)
        engine, _, _ = make_engine(FakeClients(script=[ClientResult(kind=KIND_AUTH, text="no")]))
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        self.assertEqual(rec.stage, STAGE_FAILED)
        engine, _, _ = make_engine(FakeClients(script=[ClientResult(kind=KIND_RATE_LIMIT, text="429")]))
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        self.assertEqual(rec.stage, "rate_limited")

    async def test_cancel_race_does_not_overwrite(self):
        gate = asyncio.Event()

        async def slow(name, kwargs):
            await gate.wait()
            return ClientResult(kind=KIND_OK, text="# PRD\nlater\n")

        clients = FakeClients(script=[slow])
        engine, _, _ = make_engine(clients)
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        job = asyncio.create_task(engine.run_draft(rec.task_id))
        engine._jobs[rec.task_id] = job
        engine.cancel(rec.task_id, "openid-owner")
        gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await job
        rec = engine.store.load(rec.task_id)
        self.assertEqual(rec.stage, STAGE_CANCELLED)

    async def test_duplicate_draft_no_extra_call(self):
        clients = FakeClients()
        engine, _, _ = make_engine(clients)
        rec, dup = engine.start_draft("r", "same", "openid-owner", "chat-owner")
        self.assertFalse(dup)
        rec2, dup2 = engine.start_draft("r", "same", "openid-owner", "chat-owner")
        self.assertTrue(dup2)
        self.assertEqual(rec.task_id, rec2.task_id)

    async def test_restart_recovery_no_rerun(self):
        clients = FakeClients()
        engine, data, project = make_engine(clients)
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        engine.store._clear_job_pid(rec.task_id)
        store2 = TaskStore(data, project)
        recovered = store2.load(rec.task_id)
        self.assertEqual(recovered.stage, STAGE_NEEDS_USER)
        self.assertIn("Recovered", recovered.last_error)

    async def test_split_handoff_stops_after_build(self):
        from cli_bridge.constants import STAGE_BUILT

        engine, _, _ = make_engine(FakeClients())
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        engine.cli_role = "grok"
        engine.split_handoff = True
        rec, _ = engine.request_build(rec.task_id, "openid-owner", "m3")
        rec = await engine.run_build(rec.task_id)
        self.assertEqual(rec.stage, STAGE_BUILT)
        self.assertIsNotNone(rec.build_artifact)

    async def test_peer_cannot_approve_but_can_build(self):
        engine, _, _ = make_engine(FakeClients())
        engine.trusted_peer_open_ids = {"ou-peer"}
        engine.cli_role = "both"
        engine.split_handoff = True
        rec, _ = engine.start_draft("r", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        with self.assertRaises(PermissionError):
            engine.approve(rec.task_id, rec.prd_hash, "ou-peer", "m2")
        rec = engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        rec, dup = engine.request_build(rec.task_id, "ou-peer", "m3")
        self.assertFalse(dup)
        rec = await engine.run_build(rec.task_id)
        self.assertEqual(rec.stage, "built")

    async def test_idle_approved_does_not_block_new_draft(self):
        clients = FakeClients()
        engine, _, _ = make_engine(clients)
        rec, _ = engine.start_draft("r1", "m1", "openid-owner", "chat-owner")
        rec = await engine.run_draft(rec.task_id)
        engine.approve(rec.task_id, rec.prd_hash, "openid-owner", "m2")
        rec2, dup = engine.start_draft("r2", "m3", "openid-owner", "chat-owner")
        self.assertFalse(dup)
        self.assertNotEqual(rec.task_id, rec2.task_id)

    async def test_plugin_cancel_stops_job_and_sends_result(self):
        gate = asyncio.Event()

        async def slow(name, kwargs):
            await gate.wait()
            return ClientResult(kind=KIND_OK, text="# PRD\nbody\n")

        clients = FakeClients(script=[slow])
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        gateway = FakeGateway()
        _, accepted = await invoke(ctx, gateway, owner_event("/dev-prd need it", message_id="p1"))
        self.assertIn("accepted", accepted)
        task_id = accepted.split()[1]
        _, cancelled = await invoke(ctx, gateway, owner_event("/dev-cancel %s" % task_id, message_id="p2"))
        self.assertIn("cancelled", cancelled)
        gate.set()
        await asyncio.sleep(0.05)
        rec = _STATE.engine.store.load(task_id)
        self.assertEqual(rec.stage, STAGE_CANCELLED)
        self.assertTrue(ctx.spawned[0].cancelled())
        self.assertNotIn(task_id, _STATE.engine._jobs)

    async def test_bad_user_never_executes(self):
        clients = FakeClients()
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        gateway = FakeGateway()
        _, result = await invoke(
            ctx,
            gateway,
            owner_event("/dev-prd hack", open_id="intruder", message_id="bad"),
        )
        self.assertEqual(result, "Unauthorized.")
        self.assertEqual(clients.calls, [])
