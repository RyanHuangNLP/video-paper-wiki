"""Independent acceptance checks added during Codex review."""
import asyncio
import unittest
from enum import Enum

from cli_bridge.clients import FakeClients
from cli_bridge.engine import TaskEngine
from cli_bridge.models import ClientResult, sha256_text
from cli_bridge.plugin import _STATE, on_unload
from cli_bridge.route import get_gateway, get_route, pre_gateway_dispatch
from cli_bridge.store import TaskStore
from tests.helpers import FakeGateway, invoke, make_engine, owner_event, register_plugin, temp_roots


class AcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        on_unload()
        await asyncio.sleep(0)

    async def test_delivery_and_full_prd_pagination(self):
        prd = 'x' * 12001 + '\nBearer synthetic-secret-123456'
        clients = FakeClients([ClientResult('ok', prd)])
        data, project = temp_roots()
        ctx = register_plugin(clients, data, project)
        gateway = FakeGateway()
        class Platform(str, Enum):
            FEISHU = 'feishu'
        adapter = gateway.adapters.pop('feishu')
        gateway.adapters[Platform.FEISHU] = adapter
        _, accepted = await invoke(ctx, gateway, owner_event('/dev-prd example', message_id='draft'))
        task_id = accepted.split()[1]
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(task_id)
        saved = _STATE.engine.store.read_artifact(task_id, rec.prd_artifact)
        self.assertNotIn('synthetic-secret-123456', saved)
        self.assertEqual(rec.prd_hash, sha256_text(saved))
        sent = adapter.sent[-1]['content']
        self.assertIn('/dev-approve', sent)
        self.assertIn(rec.prd_hash, sent)
        self.assertNotIn('/dev-approve ' + task_id, sent)
        pages = []
        for page in range(1, 4):
            _, result = await invoke(ctx, gateway, owner_event(f'/dev-artifact {task_id} prd {page}', message_id=str(page)))
            self.assertIn(rec.prd_hash, result)
            pages.append(result.split('\n', 1)[1])
        self.assertEqual(''.join(pages), saved)
        _, result = await invoke(ctx, gateway, owner_event(f'/dev-artifact {task_id} prd', open_id='intruder'))
        self.assertEqual(result, 'Unauthorized.')
        for args in ('../secret prd', f'{task_id} ../state', f'{task_id} prd 0', f'{task_id} prd 99'):
            _, result = await invoke(ctx, gateway, owner_event('/dev-artifact ' + args))
            self.assertNotIn(saved, result)
            self.assertTrue(result.startswith(('Command failed', 'Usage:')))

    async def test_delivery_failure_persisted(self):
        data, project = temp_roots()
        ctx = register_plugin(FakeClients(), data, project)
        _, accepted = await invoke(ctx, FakeGateway(success=False), owner_event('/dev-prd example'))
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(accepted.split()[1])
        self.assertIn('delivery failed', rec.last_error)

    async def test_late_result_after_cancel_and_busy_cleanup(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def resistant(name, kwargs):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return ClientResult('ok', 'late PRD')
        data, project = temp_roots()
        ctx = register_plugin(FakeClients([resistant]), data, project)
        gateway = FakeGateway()
        _, accepted = await invoke(ctx, gateway, owner_event('/dev-prd example', message_id='first'))
        task_id = accepted.split()[1]
        await started.wait()
        await invoke(ctx, gateway, owner_event('/dev-cancel ' + task_id, message_id='cancel'))
        _, blocked = await invoke(ctx, gateway, owner_event('/dev-prd next', message_id='next'))
        self.assertEqual(blocked, 'Command failed.')
        release.set()
        await asyncio.gather(*ctx.spawned)
        rec = _STATE.engine.store.load(task_id)
        self.assertEqual(rec.stage, 'cancelled')
        self.assertIsNone(rec.prd_artifact)
        await asyncio.sleep(0)
        self.assertFalse(_STATE.engine.has_live_job())

    async def test_restart_dedup_and_rereview(self):
        engine, data, project = make_engine()
        rec, _ = engine.start_draft('requirement', 'original', 'openid-owner', 'chat-owner')
        rec = await engine.run_draft(rec.task_id)
        recovered = TaskEngine(TaskStore(data, project), clients=FakeClients())
        duplicate, is_duplicate = recovered.start_draft('requirement', 'original', 'openid-owner', 'chat-owner')
        self.assertTrue(is_duplicate)
        self.assertEqual(rec.task_id, duplicate.task_id)
        engine.approve(rec.task_id, rec.prd_hash, 'openid-owner', 'approval')
        engine.request_build(rec.task_id, 'openid-owner', 'build')
        rec = await engine.run_build(rec.task_id)
        self.assertEqual(rec.stage, 'ready_for_pr')
        engine.request_review(rec.task_id, 'openid-owner', 'review')
        rec = await engine.run_review(rec.task_id)
        self.assertEqual(rec.stage, 'ready_for_pr')

    async def test_malformed_event_clears_gateway(self):
        pre_gateway_dispatch(owner_event(), FakeGateway())
        self.assertIsNotNone(get_gateway())
        pre_gateway_dispatch(None, None)
        self.assertIsNone(get_gateway())
        self.assertIsNone(get_route())
