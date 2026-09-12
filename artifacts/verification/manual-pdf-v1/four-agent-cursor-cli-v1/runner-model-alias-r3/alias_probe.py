"""Offline candidate runner alias and observation probe; never starts Cursor."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path
from typing import Any

CANDIDATE_PATH = Path(__file__).with_name("candidate.py")
spec = importlib.util.spec_from_file_location("runner_alias_candidate", CANDIDATE_PATH)
assert spec and spec.loader
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)

class StubProcess:
    def __init__(self, lines: list[dict[str, Any]], argv: list[str], pid: int) -> None:
        self.pid = pid
        self.stdout = io.BytesIO(b"".join((json.dumps(x).encode() + b"\n") for x in lines))
        self.stderr = io.BytesIO(b"")
        self._argv = argv
    def poll(self) -> int:
        return 0
    def wait(self, timeout: float | None = None) -> int:
        return 0
    def send_signal(self, signum: int) -> None:
        raise AssertionError("stub should never need a signal")


def main() -> None:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="runner-alias-r3-", dir="/private/tmp") as tmp_name:
        tmp = Path(tmp_name)
        pinned = tmp / ".work" / "parallel" / "lightweight-workflow-v2" / "terminal-1" / "source"
        pinned.mkdir(parents=True)
        prompt = tmp / "prompt.txt"
        prompt.write_text("offline stub prompt\n", encoding="utf-8")
        candidate.PINNED_ROOT = tmp
        candidate.ROOT = tmp
        candidate.EVIDENCE_ROOT = tmp / "evidence"
        candidate.LANE_SOURCES = {1: pinned, 2: pinned, 3: pinned, 4: pinned}
        counter = {"value": 0}

        cases: list[tuple[str, list[dict[str, Any]], bool]] = [
            ("exact_id", [{"type": "init", "model": candidate.REQUESTED_MODEL, "session_id": "s-exact-id"}], True),
            ("exact_display_name", [{"type": "init", "model": "Cursor Grok 4.6 Extra High Fast", "session_id": "s-display"}], True),
            ("mixed_verified_aliases", [
                {"type": "init", "model": candidate.REQUESTED_MODEL, "session_id": "s-mixed"},
                {"type": "model_init", "model": "Cursor Grok 4.6 Extra High Fast", "session_id": "s-mixed"},
            ], True),
            ("unknown_model", [{"type": "init", "model": "Cursor Grok 4.6 Unknown", "session_id": "s-unknown"}], False),
            ("generic_grok", [{"type": "init", "model": "grok-4.6", "session_id": "s-generic"}], False),
            ("wrong_effort", [{"type": "init", "model": "Cursor Grok 4.6 High Fast", "session_id": "s-effort"}], False),
            ("wrong_speed", [{"type": "init", "model": "Cursor Grok 4.6 Extra High", "session_id": "s-speed"}], False),
            ("mixed_other_model", [
                {"type": "init", "model": candidate.REQUESTED_MODEL, "session_id": "s-mixed-other"},
                {"type": "session_init", "model": "grok-4.6", "session_id": "s-mixed-other"},
            ], False),
            ("nested_tool_model_ignored", [{
                "type": "init", "session_id": "s-nested",
                "tool": {"model": "grok-4.6", "arguments": {"model_id": "fake-other"}},
            }], False),
            ("verified_top_level_nested_other_ignored", [{
                "type": "init", "model": candidate.REQUESTED_MODEL, "session_id": "s-nested-ok",
                "tool": {"model": "grok-4.6", "result": {"model": "fake-other"}},
            }], True),
        ]
        for name, lines, expected in cases:
            counter["value"] += 1
            captured: dict[str, Any] = {}
            def factory(argv, **kwargs):
                captured["argv"] = list(argv)
                captured["kwargs"] = {k: str(v) for k, v in kwargs.items() if k in {"cwd", "stdin"}}
                return StubProcess(lines, list(argv), counter["value"])
            final = candidate.run_attempt(
                lane=1,
                prompt_file=prompt,
                controller_id=f"stub-{counter['value']}",
                popen_factory=factory,
                executable=tmp / "stub-agent",
                workspace=pinned,
                progress_interval=0.0,
            )
            observed = final.get("observed_models")
            row = {
                "case": name,
                "expected_run_verified": expected,
                "run_verified": final.get("run_verified"),
                "status": final.get("status"),
                "exit_code": final.get("exit_code"),
                "requested_model": final.get("requested_model"),
                "observed_model": final.get("observed_model"),
                "observed_models": observed,
                "model_mismatch": final.get("model_mismatch"),
                "model_observation": final.get("model_observation"),
                "architect_accepted": final.get("architect_accepted"),
                "verification_blockers": final.get("verification_blockers"),
                "argv_model": captured["argv"][captured["argv"].index("--model") + 1],
                "attempt_dir": final.get("attempt_dir"),
            }
            assert final.get("run_verified") is expected, row
            assert final.get("status") == "succeeded", row
            assert final.get("exit_code") == 0, row
            assert final.get("architect_accepted") is False, row
            assert row["argv_model"] == candidate.REQUESTED_MODEL, row
            if name == "nested_tool_model_ignored":
                assert observed == [], row
                assert final.get("observed_model") is None, row
                assert final.get("model_observation") == "unknown", row
            if name == "verified_top_level_nested_other_ignored":
                assert observed == [candidate.REQUESTED_MODEL], row
                assert final.get("model_mismatch") is False, row
            if name == "mixed_verified_aliases":
                assert observed == [candidate.REQUESTED_MODEL, "Cursor Grok 4.6 Extra High Fast"], row
            if name == "mixed_other_model":
                assert observed == [candidate.REQUESTED_MODEL, "grok-4.6"], row
                assert final.get("model_mismatch") is True, row
            rows.append(row)
        probe = {
            "schema": "runner-model-alias-r3-offline-probe.v1",
            "synthetic_only": True,
            "network_used": False,
            "cursor_started": False,
            "candidate_path": str(CANDIDATE_PATH),
            "candidate_sha256": hashlib.sha256(CANDIDATE_PATH.read_bytes()).hexdigest(),
            "requested_model": candidate.REQUESTED_MODEL,
            "verified_model_names": sorted(candidate.VERIFIED_MODEL_NAMES),
            "cases": rows,
            "all_assertions_passed": True,
        }
    out = CANDIDATE_PATH.with_name("alias-probe-results.json")
    out.write_text(json.dumps(probe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(probe, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
