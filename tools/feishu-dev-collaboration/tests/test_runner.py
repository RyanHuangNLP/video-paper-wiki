import asyncio
import os
import sys
import time
import unittest

from cli_bridge.runner import AsyncProcessRunner, RunLimits


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cwd = os.path.dirname(__file__)
        self.runners = []

    async def asyncTearDown(self):
        for runner in self.runners:
            try:
                await runner.terminate_group()
            except Exception:
                pass

    def _runner(self, **kwargs):
        runner = AsyncProcessRunner(RunLimits(**kwargs))
        self.runners.append(runner)
        return runner

    async def test_success_and_env_not_inherited(self):
        runner = self._runner(timeout_sec=5, max_output_bytes=4096)
        os.environ["CLI_BRIDGE_SECRET_TEST"] = "leaked"
        try:
            result = await runner.run(
                [sys.executable, "-c", "import os; print(os.environ.get('CLI_BRIDGE_SECRET_TEST','missing'))"],
                cwd=self.cwd,
                env={"PATH": os.environ.get("PATH", "/usr/bin")},
            )
        finally:
            os.environ.pop("CLI_BRIDGE_SECRET_TEST", None)
        self.assertEqual(result.kind, "ok")
        self.assertIn("missing", result.text)

    async def test_nonzero(self):
        runner = self._runner(timeout_sec=5, max_output_bytes=4096)
        result = await runner.run([sys.executable, "-c", "raise SystemExit(3)"], cwd=self.cwd, env={})
        self.assertEqual(result.kind, "nonzero")
        self.assertEqual(result.exit_code, 3)

    async def test_stdin_timeout_when_unread(self):
        runner = self._runner(timeout_sec=0.4, max_output_bytes=4096)
        started = time.monotonic()
        result = await runner.run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=self.cwd,
            env={},
            stdin_bytes=b"x" * 1024 * 64,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.kind, "timeout")
        self.assertLess(elapsed, 5)

    async def test_overflow_classifies_promptly(self):
        runner = self._runner(timeout_sec=5, max_output_bytes=64)
        started = time.monotonic()
        result = await runner.run(
            [sys.executable, "-c", "import sys; sys.stdout.write('a'*100000); sys.stdout.flush(); sys.stderr.write('b'*100000); import time; time.sleep(20)"],
            cwd=self.cwd,
            env={},
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.kind, "overflow")
        self.assertLess(elapsed, 4)

    async def test_descendant_cleanup(self):
        runner = self._runner(timeout_sec=8, max_output_bytes=4096)
        code = (
            "import os, signal, sys, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"
            "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "    time.sleep(60)\n"
            "    os._exit(0)\n"
            "print(pid, flush=True)\n"
            "time.sleep(30)\n"
        )
        task = asyncio.create_task(
            runner.run([sys.executable, "-c", code], cwd=self.cwd, env={})
        )
        await asyncio.sleep(0.3)
        await runner.terminate_group()
        try:
            await asyncio.wait_for(task, timeout=5)
        except Exception:
            pass
        self.assertIsNone(runner._pgid)
