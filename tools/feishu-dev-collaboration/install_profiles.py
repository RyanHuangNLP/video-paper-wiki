#!/usr/bin/env python3
"""Create isolated Hermes profiles for the two Feishu CLI bots.

Does not clone the default profile, does not copy ~/.hermes/.env,
does not restart ai.hermes.gateway, and does not start the new gateways.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "cli_bridge"
PROJECT = ROOT / "loop-sandbox"
DATA = ROOT / "task-data"
GROK_PROFILE = ROOT / "policy" / "workspace-profile.txt"
GROK_CONFIG = Path.home() / ".grok" / "config.toml"
HERMES = Path.home() / ".local" / "bin" / "hermes"
DEFAULT_HOME = Path.home() / ".hermes"
PROFILES = DEFAULT_HOME / "profiles"
DEFAULT_CONFIG = DEFAULT_HOME / "config.yaml"
DEFAULT_ENV = DEFAULT_HOME / ".env"
DEFAULT_PLIST = Path.home() / "Library" / "LaunchAgents" / "ai.hermes.gateway.plist"

PROFILES_TO_CREATE = (
    {
        "name": "codexarch",
        "cli_role": "codex",
        "description": "Feishu Codex architecture bot. Runs Codex CLI for PRD and review only.",
        "soul": (
            "You are the Feishu Codex architecture bot.\n"
            "You do not write product code. Slash commands dispatch to the local Codex CLI.\n"
            "Do not approve PRDs. Do not call Grok. Do not git push or merge.\n"
            "Never introduce yourself. Never prepend identity lines "
            "(including Chinese 我是…bot) to replies. "
            "Command replies must be the command output only.\n"
        ),
    },
    {
        "name": "grokdev",
        "cli_role": "grok",
        "description": "Feishu Grok development bot. Runs Grok CLI for implementation only.",
        "soul": (
            "You are the Feishu Grok development bot.\n"
            "You implement only inside the approved project via the local Grok CLI.\n"
            "Do not draft PRDs, do not approve hashes, do not git commit/push/merge.\n"
            "Never introduce yourself. Never prepend identity lines "
            "(including Chinese 我是…bot) to replies. "
            "Command replies must be the command output only.\n"
        ),
    },
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_default() -> dict[str, str]:
    return {
        "config": sha256_file(DEFAULT_CONFIG),
        "env": sha256_file(DEFAULT_ENV),
        "plist": sha256_file(DEFAULT_PLIST),
    }


def run_hermes(args: list[str]) -> None:
    cmd = [str(HERMES), *args]
    subprocess.run(cmd, check=True)


def merge_profile_config(profile_dir: Path, role: str, policy: dict) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML required; run with Hermes venv python") from exc

    path = profile_dir / "config.yaml"
    data = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    plugins = data.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if "cli-bridge" not in enabled:
        enabled.append("cli-bridge")
    entries = plugins.setdefault("entries", {})
    previous = {}
    current_entry = entries.get("cli-bridge")
    if isinstance(current_entry, dict):
        previous = current_entry.get("settings") or {}
    settings = {
        "cli_role": role,
        "owner_open_id": previous.get("owner_open_id") or "",
        "owner_chat_id": previous.get("owner_chat_id") or "",
        "self_open_id": previous.get("self_open_id") or "",
        "allowed_group_chat_ids": previous.get("allowed_group_chat_ids") or [],
        "data_root": str(DATA),
        "project_root": str(PROJECT),
        "execution_policy": policy,
    }
    if previous.get("roster") is not None or previous.get("roster_self"):
        settings["roster"] = previous.get("roster") or []
        settings["roster_self"] = previous.get("roster_self") or ""
    else:
        settings["peer_open_id"] = previous.get("peer_open_id") or ""
        settings["peer_name"] = previous.get("peer_name") or (
            "Grok开发" if role == "codex" else "Codex架构"
        )
        settings["trusted_peer_open_ids"] = previous.get("trusted_peer_open_ids") or []
    entries["cli-bridge"] = {"settings": settings}
    feishu = data.setdefault("feishu", {})
    feishu["allow_bots"] = "mentions"
    platforms = data.setdefault("platforms", {})
    feishu_platform = platforms.setdefault("feishu", {})
    feishu_platform.setdefault("unauthorized_dm_behavior", "ignore")
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def link_plugin(profile_dir: Path) -> None:
    dest_dir = profile_dir / "plugins"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "cli-bridge"
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() and dest.resolve() == PLUGIN.resolve():
            return
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    os.symlink(PLUGIN, dest, target_is_directory=True)


def main() -> int:
    before = snapshot_default()
    DATA.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DATA, 0o700)
    policy = {
        "enabled": True,
        "project_root": str(PROJECT),
        "data_root": str(DATA),
        "grok_profile_name": "workspace",
        "grok_profile_path": str(GROK_PROFILE),
        "grok_profile_sha256": sha256_file(GROK_PROFILE),
        "grok_config_sha256": sha256_file(GROK_CONFIG),
    }
    for spec in PROFILES_TO_CREATE:
        name = spec["name"]
        profile_dir = PROFILES / name
        if not (profile_dir / "config.yaml").is_file():
            run_hermes(
                [
                    "profile",
                    "create",
                    name,
                    "--no-skills",
                    "--description",
                    spec["description"],
                ]
            )
        policy_role = dict(policy)
        policy_role["cli_role"] = spec["cli_role"]
        merge_profile_config(profile_dir, spec["cli_role"], policy_role)
        link_plugin(profile_dir)
        (profile_dir / "SOUL.md").write_text(spec["soul"], encoding="utf-8")
        env_path = profile_dir / ".env"
        if env_path.is_file():
            os.chmod(env_path, 0o600)
        print("profile ready:", name, "role=", spec["cli_role"], "home=", profile_dir)
    after = snapshot_default()
    if after != before:
        raise SystemExit("default Hermes files changed: %s -> %s" % (before, after))
    print("default config/env/plist hashes unchanged")
    print("did not start gateways; fill Feishu app credentials per SETUP_FEISHU.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
