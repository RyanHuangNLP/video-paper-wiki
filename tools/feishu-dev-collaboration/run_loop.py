#!/usr/bin/env python3
"""Run one local PRD -> owner hash confirm -> Grok build -> Codex review loop."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cli_bridge.engine import TaskEngine
from cli_bridge.live_clients import GROK_CONFIG, LiveClients, _sha256_file
from cli_bridge.store import TaskStore

PROJECT = ROOT / "loop-sandbox"
DATA = ROOT / "task-data"
PROFILE = ROOT / "policy" / "workspace-profile.txt"
OWNER = "local-owner"
REQUIREMENT = (
    "在本项目实现 add(a: int, b: int) -> int，返回两数之和。"
    "test_add.py 已存在。请实现 add.py 使 python3 -m unittest test_add.py 通过。"
    "不要 git commit/push，不要访问项目外路径，不要改 Vault。"
)


def build_policy():
    return {
        "enabled": True,
        "project_root": str(PROJECT),
        "data_root": str(DATA),
        "grok_profile_name": "workspace",
        "grok_profile_path": str(PROFILE),
        "grok_profile_sha256": _sha256_file(PROFILE),
        "grok_config_sha256": _sha256_file(GROK_CONFIG),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    DATA.mkdir(mode=0o700, exist_ok=True)
    store = TaskStore(str(DATA), str(PROJECT))
    clients = LiveClients(build_policy())
    engine = TaskEngine(store, clients=clients, owner_open_id=OWNER, owner_chat_id="local")
    rec, _ = engine.start_draft(REQUIREMENT, "m-draft-" + uuid.uuid4().hex, OWNER, "local")
    rec = await engine.run_draft(rec.task_id)
    report = {
        "draft_stage": rec.stage,
        "draft_error": rec.last_error,
        "prd_hash": rec.prd_hash,
        "prd_artifact": rec.prd_artifact,
    }
    if rec.stage != "draft" or not rec.prd_hash:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        return 1
    rec = engine.approve(rec.task_id, rec.prd_hash, OWNER, "m-approve-" + uuid.uuid4().hex)
    rec, _ = engine.request_build(rec.task_id, OWNER, "m-build-" + uuid.uuid4().hex)
    rec = await engine.run_build(rec.task_id)
    report.update(
        {
            "task_id": rec.task_id,
            "final_stage": rec.stage,
            "final_error": rec.last_error,
            "build_artifact": rec.build_artifact,
            "review_artifact": rec.review_artifact,
            "approved_hash": rec.approved_hash,
        }
    )
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    tests = os.system(
        "python3 -m unittest test_add.py -v"
    )
    report["unittest_exit"] = tests >> 8
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if rec.stage in ("ready_for_pr", "needs_changes") and rec.prd_hash:
        return 0 if rec.stage == "ready_for_pr" else 2
    return 1


if __name__ == "__main__":
    os.chdir(PROJECT)
    raise SystemExit(asyncio.run(main()))
