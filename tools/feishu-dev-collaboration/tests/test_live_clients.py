"""Deterministic LiveClients tests with an injected runner."""

import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from cli_bridge.live_clients import LiveClients, child_env
from cli_bridge.models import KIND_CANCELLED, KIND_DISABLED, KIND_OK
from cli_bridge.clients import clients_from_policy, DisabledLiveClients


class FakeRunner:
    def __init__(self, script, captured):
        self.script = script
        self.captured = captured

    async def run(self, argv, cwd, env=None, stdin_bytes=None, merge_stderr=False):
        self.captured.append({"argv": list(argv), "cwd": cwd, "env": dict(env or {}), "stdin": stdin_bytes})
        if not self.script:
            from cli_bridge.models import ClientResult

            return ClientResult(kind=KIND_OK, text="ok", extra={})
        item = self.script.pop(0)
        if callable(item):
            return item(argv, cwd, env, stdin_bytes)
        return item


class LiveClientsTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        root = Path(self.td.name)
        self.project = root / "project"
        self.data = root / "data"
        self.profile = root / "profile.md"
        self.project.mkdir()
        self.data.mkdir()
        self.profile.write_text("workspace\n")
        # Isolate from real grok config by expecting mismatch unless patched.
        self.base_policy = {
            "enabled": True,
            "project_root": str(self.project.resolve()),
            "data_root": str(self.data.resolve()),
            "grok_profile_name": "workspace",
            "grok_profile_path": str(self.profile),
            "grok_profile_sha256": hashlib.sha256(b"workspace\n").hexdigest(),
            "grok_config_sha256": "0" * 64,
        }

    def tearDown(self):
        self.td.cleanup()

    def test_factory_disabled_without_enabled(self):
        self.assertIsInstance(clients_from_policy(None), DisabledLiveClients)
        self.assertIsInstance(clients_from_policy({"enabled": False}), DisabledLiveClients)

    def test_invalid_policy_disables(self):
        clients = LiveClients({"enabled": True})
        result = asyncio.run(clients.draft("x", "/tmp/nope"))
        self.assertEqual(result.kind, KIND_DISABLED)

    def test_tmp_data_root_rejected(self):
        policy = dict(self.base_policy)
        policy["data_root"] = "/tmp/not-allowed"
        clients = LiveClients(policy)
        result = asyncio.run(clients.draft("x", policy["project_root"]))
        self.assertEqual(result.kind, KIND_DISABLED)

    def test_malicious_requirement_stays_stdin(self):
        captured = []
        from cli_bridge.models import ClientResult

        script = [
            ClientResult(kind=KIND_OK, text="codex-cli 0.142.0"),
            ClientResult(kind=KIND_OK, text="Logged in using ChatGPT"),
            ClientResult(
                kind=KIND_OK,
                text='{"type":"item.completed","item":{"type":"agent_message","text":"# PRD\\nok"}}\n{"type":"turn.completed"}\n',
            ),
        ]

        def factory(limits=None):
            return FakeRunner(script, captured)

        policy = dict(self.base_policy)
        # Bypass real config hash by pointing validation at temp profile only;
        # config hash still checked against ~/.grok/config.toml so this stays disabled
        # unless we skip by injecting _error after construct.
        clients = LiveClients(policy, runner_factory=factory)
        clients._error = None
        evil = "x; rm -rf / --eval $(whoami)"
        result = asyncio.run(clients.draft(evil, policy["project_root"]))
        self.assertEqual(result.kind, KIND_OK)
        stdin = captured[-1]["stdin"].decode("utf-8")
        self.assertIn(evil, stdin)
        argv = captured[-1]["argv"]
        self.assertTrue(all(evil not in str(part) for part in argv[:-1] or argv))
        self.assertNotIn("bypassPermissions", argv)
        self.assertNotIn("--always-approve", argv)
        self.assertEqual(argv[0], "/opt/homebrew/bin/codex")
        self.assertIn("-", argv)

    def test_grok_cancelled_is_not_success(self):
        captured = []
        from cli_bridge.models import ClientResult

        script = [
            ClientResult(kind=KIND_OK, text="grok 1.0.5 (abc)"),
            ClientResult(
                kind=KIND_OK,
                text="You are logged in with grok.com.\n\nDefault model: grok-4.6\n",
            ),
            ClientResult(
                kind=KIND_OK,
                text=json.dumps(
                    {"hooks": [], "plugins": [], "mcpServers": [], "lspServers": []}
                ),
            ),
            ClientResult(
                kind=KIND_OK,
                text=json.dumps({"stopReason": "cancelled", "text": "almost", "num_turns": 1}),
            ),
        ]

        def factory(limits=None):
            return FakeRunner(script, captured)

        clients = LiveClients(self.base_policy, runner_factory=factory)
        clients._error = None
        result = asyncio.run(clients.build("# PRD", "", self.base_policy["project_root"]))
        self.assertEqual(result.kind, KIND_CANCELLED)
        self.assertFalse(result.ok)
        env = captured[-1]["env"]
        self.assertNotIn("FEISHU_APP_SECRET", env)
        self.assertEqual(env.get("GROK_MEMORY"), "0")
        self.assertIn("--sandbox", captured[-1]["argv"])
        self.assertIn("workspace", captured[-1]["argv"])

    def test_child_env_has_no_api_keys(self):
        env = child_env()
        joined = " ".join(env.keys())
        self.assertNotIn("API", joined)
        self.assertNotIn("FEISHU", joined)
        self.assertEqual(env["TERM"], "dumb")

    def test_cli_role_mismatch_disables_stage(self):
        policy = dict(self.base_policy)
        policy["cli_role"] = "codex"
        clients = LiveClients(policy)
        clients._error = None
        result = asyncio.run(clients.build("# PRD", "", policy["project_root"]))
        self.assertEqual(result.kind, KIND_DISABLED)
        self.assertEqual(result.extra.get("reason"), "role_mismatch")
        policy["cli_role"] = "grok"
        clients = LiveClients(policy)
        clients._error = None
        result = asyncio.run(clients.draft("x", policy["project_root"]))
        self.assertEqual(result.kind, KIND_DISABLED)


if __name__ == "__main__":
    unittest.main()
