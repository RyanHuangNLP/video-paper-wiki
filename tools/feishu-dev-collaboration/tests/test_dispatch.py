import asyncio
import importlib.util
import os
import sys
import unittest
from types import SimpleNamespace

from cli_bridge.clients import FakeClients, clients_from_policy
from cli_bridge.constants import HELP_TEXT, UNAUTHORIZED
from cli_bridge.models import ClientResult, KIND_OK
from cli_bridge.plugin import _STATE, register
from cli_bridge.route import extract_route, pre_gateway_dispatch, reset_route, get_route
from tests.helpers import FakeGateway, invoke, owner_event, register_plugin, temp_roots


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data, self.project = temp_roots()
        self.clients = FakeClients()
        self.ctx = register_plugin(self.clients, self.data, self.project)
        self.gateway = FakeGateway()

    async def test_owner_help_and_unknown_rewrite(self):
        rewrite, result = await invoke(self.ctx, self.gateway, owner_event("/dev-help"))
        self.assertIsNone(rewrite)
        self.assertIn("/dev-prd", result)
        rewrite, result = await invoke(self.ctx, self.gateway, owner_event("please ship it"))
        self.assertEqual(rewrite["action"], "rewrite")
        self.assertIn("dev-help", result)

    async def test_rejects_wrong_identities_without_client(self):
        cases = [
            owner_event(platform="slack"),
            owner_event(chat_type="group"),
            owner_event(is_bot=True),
            owner_event(open_id="other"),
            owner_event(chat_id="other-chat"),
            owner_event(sender_type="bot"),
        ]
        for event in cases:
            _, result = await invoke(self.ctx, self.gateway, event)
            self.assertEqual(result, UNAUTHORIZED)
        self.assertEqual(self.clients.calls, [])

    async def test_malformed_raw_identity_rejected(self):
        event = owner_event("/dev-prd x")
        event.raw_message = SimpleNamespace(event=SimpleNamespace(sender=None))
        _, result = await invoke(self.ctx, self.gateway, event)
        self.assertEqual(result, UNAUTHORIZED)
        self.assertEqual(self.clients.calls, [])

    async def test_contextvar_isolation_and_malformed_reset(self):
        results = []

        async def one():
            pre_gateway_dispatch(owner_event(open_id="openid-owner", message_id="a"), self.gateway)
            await asyncio.sleep(0.01)
            results.append(get_route().message_id)

        async def two():
            pre_gateway_dispatch(owner_event(open_id="openid-owner", message_id="b"), self.gateway)
            results.append(get_route().message_id)

        await asyncio.gather(one(), two())
        self.assertEqual(set(results), {"a", "b"})
        pre_gateway_dispatch(None, self.gateway)
        self.assertIsNone(get_route())

    async def test_rewrite_keeps_identity(self):
        event = owner_event(text="hello", message_id="keep-me")
        pre_gateway_dispatch(event, self.gateway)
        route = get_route()
        self.assertEqual(route.message_id, "keep-me")
        self.assertEqual(route.open_id, "openid-owner")

    async def test_handler_errors_do_not_escape(self):
        handler = self.ctx.commands["dev-approve"]
        result = await handler("not-a-task not-a-hash")
        self.assertIsInstance(result, str)

    async def test_live_default_disabled_no_registration_io(self):
        clients = clients_from_policy(None)
        result = await clients.draft("x", self.project)
        self.assertEqual(result.kind, "disabled")
        self.assertFalse(result.ok)

    async def test_frozen_route(self):
        pre_gateway_dispatch(owner_event(), self.gateway)
        route = get_route()
        with self.assertRaises(Exception):
            route.chat_id = "mutated"


class NamespaceImportTests(unittest.TestCase):
    def test_namespaced_package_loads_with_relative_imports(self):
        pkg_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "cli_bridge")
        )
        init_path = os.path.join(pkg_dir, "__init__.py")
        spec = importlib.util.spec_from_file_location(
            "hermes_ns.cli_bridge",
            init_path,
            submodule_search_locations=[pkg_dir],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "register"))
