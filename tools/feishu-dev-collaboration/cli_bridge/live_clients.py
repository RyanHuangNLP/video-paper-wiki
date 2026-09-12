"""Live Codex/Grok adapters. Policy is local trusted config, never chat input."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tomllib
from pathlib import Path

from .clients import classify_known_failure
from .models import (
    KIND_AUTH,
    KIND_CANCELLED,
    KIND_DISABLED,
    KIND_EMPTY,
    KIND_INVALID,
    KIND_MAX_TURNS,
    KIND_NONZERO,
    KIND_OK,
    KIND_RATE_LIMIT,
    ClientResult,
)
from .runner import AsyncProcessRunner, RunLimits

CODEX_BIN = "/opt/homebrew/bin/codex"
GROK_BIN = "/Users/huangzhanpeng/.local/bin/grok"
ACCOUNT_HOME = "/Users/huangzhanpeng"
PINNED_CODEX = "codex-cli 0.142.0"
PINNED_GROK = "grok 1.0.5"
GROK_CONFIG = os.path.join(ACCOUNT_HOME, ".grok", "config.toml")
VAULT = os.path.join(ACCOUNT_HOME, "Documents", "video-paper-vault")
TMP_PREFIXES = ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp")
PREFLIGHT_TIMEOUT = 30.0
MODEL_TIMEOUT = 900.0
MAX_OUTPUT = 8_000_000
GROK_MAX_TURNS = 40

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review.schema.json")

_PATH = (
    "/Users/huangzhanpeng/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
)


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_tmp(path):
    resolved = os.path.realpath(path)
    for prefix in TMP_PREFIXES:
        if resolved == prefix or resolved.startswith(prefix + os.sep):
            return True
    tmpdir = os.environ.get("TMPDIR") or ""
    if tmpdir:
        real_tmp = os.path.realpath(tmpdir)
        if resolved == real_tmp or resolved.startswith(real_tmp.rstrip("/") + os.sep):
            return True
    return False


def _regular_file(path):
    return os.path.isfile(path) and not os.path.islink(path) and not os.path.islink(os.path.abspath(path))


def child_env():
    env = {
        "HOME": ACCOUNT_HOME,
        "USER": os.environ.get("USER", "huangzhanpeng"),
        "LOGNAME": os.environ.get("LOGNAME", os.environ.get("USER", "huangzhanpeng")),
        "PATH": _PATH,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "TERM": "dumb",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GROK_DISABLE_AUTOUPDATER": "1",
        "GROK_MEMORY": "0",
        "GROK_SUBAGENTS": "0",
        "GROK_TOOL_SEARCH": "0",
        "GROK_CURSOR_SKILLS_ENABLED": "0",
        "GROK_CURSOR_RULES_ENABLED": "0",
        "GROK_CURSOR_AGENTS_ENABLED": "0",
        "GROK_CURSOR_MCPS_ENABLED": "0",
        "GROK_CURSOR_HOOKS_ENABLED": "0",
        "GROK_CLAUDE_SKILLS_ENABLED": "0",
        "GROK_CLAUDE_RULES_ENABLED": "0",
        "GROK_CLAUDE_AGENTS_ENABLED": "0",
        "GROK_CLAUDE_MCPS_ENABLED": "0",
        "GROK_CLAUDE_HOOKS_ENABLED": "0",
    }
    return env


def _disabled(reason, extra=None):
    payload = {"reason": reason, "stage": extra.get("stage") if extra else None}
    if extra:
        payload.update(extra)
    return ClientResult(kind=KIND_DISABLED, text="live execution disabled", extra=payload)


class LiveClients:
    def __init__(self, policy, runner_factory=None):
        self.policy = dict(policy or {})
        self._runner_factory = runner_factory or (
            lambda limits=None: AsyncProcessRunner(limits=limits)
        )
        self._error = self._validate_policy()

    def _validate_policy(self):
        p = self.policy
        if p.get("enabled") is not True:
            return "disabled"
        root = p.get("project_root")
        data = p.get("data_root")
        if not isinstance(root, str) or not os.path.isabs(root):
            return "project_root"
        if not isinstance(data, str) or not os.path.isabs(data):
            return "data_root"
        if os.path.realpath(root) != os.path.abspath(root):
            return "project_root_symlink"
        if os.path.islink(root) or os.path.islink(data):
            return "symlink_policy"
        if _is_tmp(data):
            return "data_root_tmp"
        if os.path.commonpath([os.path.realpath(data), os.path.realpath(root)]) == os.path.realpath(root):
            return "data_inside_project"
        name = p.get("grok_profile_name")
        path = p.get("grok_profile_path")
        digest = p.get("grok_profile_sha256")
        cfg_digest = p.get("grok_config_sha256")
        if name != "workspace":
            return "profile_name"
        if not isinstance(path, str) or not _regular_file(path):
            return "profile_path"
        if not isinstance(digest, str) or len(digest) != 64:
            return "profile_hash"
        if _sha256_file(path) != digest:
            return "profile_hash_mismatch"
        if not _regular_file(GROK_CONFIG):
            return "grok_config"
        if not isinstance(cfg_digest, str) or _sha256_file(GROK_CONFIG) != cfg_digest:
            return "config_hash_mismatch"
        if _has_custom_model_provider(GROK_CONFIG):
            return "custom_provider"
        if not os.path.exists(CODEX_BIN) or not os.path.exists(GROK_BIN):
            return "missing_executable"
        role = str(p.get("cli_role") or "").strip().lower()
        if role and role not in ("codex", "grok", "both"):
            return "cli_role"
        return None

    def _project_ok(self, project):
        want = os.path.realpath(self.policy["project_root"])
        got = os.path.realpath(project) if isinstance(project, str) else ""
        return want == got

    async def draft(self, requirement, project):
        return await self._stage("draft", requirement, project)

    async def build(self, prd, prior_review, project):
        return await self._stage("build", prd, project, prior_review=prior_review)

    async def review(self, prd, build_report, project):
        return await self._stage("review", prd, project, build_report=build_report)

    async def _stage(self, stage, primary, project, prior_review="", build_report=""):
        extra = {"stage": stage, "client": "codex" if stage != "build" else "grok"}
        if self._error:
            return _disabled(self._error, extra)
        role = str(self.policy.get("cli_role") or "").strip().lower()
        if role == "codex" and stage == "build":
            return _disabled("role_mismatch", extra)
        if role == "grok" and stage in ("draft", "review"):
            return _disabled("role_mismatch", extra)
        if not self._project_ok(project):
            return _disabled("project_mismatch", extra)
        if os.path.exists(os.path.join(project, ".grok", "config.toml")) or os.path.exists(
            os.path.join(project, ".grok", "requirements.toml")
        ):
            return _disabled("unvetted_project_grok_config", extra)
        pre = await self._preflight(stage, project)
        if pre is not None:
            return pre
        if stage == "draft":
            return await self._run_codex_draft(primary, project, extra)
        if stage == "build":
            return await self._run_grok_build(primary, prior_review, project, extra)
        return await self._run_codex_review(primary, build_report, project, extra)

    async def _preflight(self, stage, project):
        extra = {"stage": stage}
        if stage in ("draft", "review"):
            ver = await self._exec(
                [CODEX_BIN, "--version"],
                ACCOUNT_HOME,
                PREFLIGHT_TIMEOUT,
                merge_stderr=True,
            )
            if PINNED_CODEX not in (ver.text or ""):
                return _disabled("codex_version", extra)
            login = await self._exec(
                [CODEX_BIN, "login", "status"],
                ACCOUNT_HOME,
                PREFLIGHT_TIMEOUT,
                merge_stderr=True,
            )
            if "Logged in using ChatGPT" not in (login.text or ""):
                kind = classify_known_failure(login.text or "")
                if kind == KIND_AUTH:
                    return ClientResult(kind=KIND_AUTH, text="auth failure", extra=extra)
                return _disabled("codex_login", extra)
        if stage == "build":
            ver = await self._exec(
                [GROK_BIN, "--version"],
                ACCOUNT_HOME,
                PREFLIGHT_TIMEOUT,
                merge_stderr=True,
            )
            if PINNED_GROK not in (ver.text or ""):
                return _disabled("grok_version", extra)
            models = await self._exec(
                [GROK_BIN, "models"],
                ACCOUNT_HOME,
                PREFLIGHT_TIMEOUT,
                merge_stderr=True,
            )
            body = models.text or ""
            if "You are logged in with grok.com." not in body or "Default model:" not in body:
                kind = classify_known_failure(body)
                if kind == KIND_AUTH:
                    return ClientResult(kind=KIND_AUTH, text="auth failure", extra=extra)
                return _disabled("grok_login", extra)
            inspect = await self._exec(
                [GROK_BIN, "--cwd", project, "inspect", "--json"],
                project,
                PREFLIGHT_TIMEOUT,
                merge_stderr=False,
            )
            if inspect.kind != KIND_OK:
                return _disabled("grok_inspect", extra)
            try:
                discovered = json.loads(inspect.text)
            except ValueError:
                return _disabled("grok_inspect_json", extra)
            for key in ("hooks", "plugins", "mcpServers", "lspServers"):
                value = discovered.get(key) or []
                if value:
                    return _disabled("discovered_" + key, extra)
        return None

    async def _run_codex_draft(self, requirement, project, extra):
        prompt = (
            "Write a concise Chinese Markdown PRD and acceptance criteria for the "
            "following requirement. Read-only: do not implement code, do not run "
            "mutating tools, do not git commit/push. Requirement:\n"
        ) + str(requirement)
        argv = self._codex_argv(project, review=False)
        result = await self._model_run(argv, project, prompt.encode("utf-8"), extra)
        if not result.ok:
            return result
        text = _codex_final_text(result.text)
        if not text:
            return ClientResult(kind=KIND_INVALID, text="", extra=extra)
        return ClientResult(
            kind=KIND_OK,
            text=text,
            extra={**extra, "version": PINNED_CODEX, "exit": 0},
        )

    async def _run_codex_review(self, prd, build_report, project, extra):
        prompt = (
            "Inspect the actual project files and tests against the approved PRD. "
            "Read-only tests only. No git push/merge, no admin, no human gate. "
            "Return JSON only with keys verdict and explanation. "
            "verdict must be pass, needs_changes, or fail.\n\nPRD:\n"
            + str(prd)
            + "\n\nBuild report:\n"
            + str(build_report)
        )
        argv = self._codex_argv(project, review=True)
        result = await self._model_run(argv, project, prompt.encode("utf-8"), extra)
        if not result.ok:
            return result
        text = _codex_final_text(result.text)
        if not text:
            return ClientResult(kind=KIND_INVALID, text="", extra=extra)
        return ClientResult(
            kind=KIND_OK,
            text=text,
            extra={**extra, "version": PINNED_CODEX, "exit": 0},
        )

    async def _run_grok_build(self, prd, prior_review, project, extra):
        prompt = (
            "Implement only within the approved PRD and this project. "
            "Read the prior review if present. Run self-tests and report actual "
            "command results. No git commit/push/PR/merge, no vpwiki-admin, no "
            "human gate, no credentials, no provider changes.\n\nPRD:\n"
            + str(prd)
            + "\n\nPrior review:\n"
            + str(prior_review or "")
        )
        argv = [
            GROK_BIN,
            "--cwd",
            project,
            "--no-plan",
            "--no-subagents",
            "--disable-web-search",
            "--sandbox",
            "workspace",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "Bash,Read,Grep,Glob,Write,Edit",
            "--allow",
            "Read",
            "--allow",
            "Write",
            "--allow",
            "Edit",
            "--allow",
            "Bash",
            "--max-turns",
            str(GROK_MAX_TURNS),
            "--reasoning-effort",
            "medium",
            "--output-format",
            "json",
            "--single",
            prompt,
        ]
        result = await self._model_run(argv, project, None, extra)
        parsed = _parse_grok_json(result)
        if parsed is not None:
            return parsed
        if result.kind == KIND_MAX_TURNS:
            return ClientResult(kind=KIND_MAX_TURNS, text="", extra=extra)
        if result.kind == KIND_EMPTY:
            return ClientResult(kind=KIND_EMPTY, text="", extra=extra)
        if result.kind == KIND_NONZERO:
            return ClientResult(kind=KIND_NONZERO, text="", extra=extra)
        if result.kind == KIND_CANCELLED:
            return ClientResult(kind=KIND_CANCELLED, text="", extra=extra)
        return ClientResult(kind=KIND_INVALID, text="", extra=extra)

    def _codex_argv(self, project, review):
        argv = [
            CODEX_BIN,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--json",
            "-C",
            project,
            "--sandbox",
            "read-only",
            "-c",
            'forced_login_method="chatgpt"',
            "-c",
            'approval_policy="never"',
        ]
        if review:
            argv.extend(["--output-schema", _SCHEMA_PATH])
        argv.append("-")
        return argv

    async def _model_run(self, argv, cwd, stdin_bytes, extra):
        runner = self._runner_factory(
            RunLimits(timeout_sec=MODEL_TIMEOUT, max_output_bytes=MAX_OUTPUT)
        )
        result = await runner.run(list(argv), cwd, env=child_env(), stdin_bytes=stdin_bytes)
        result.extra = {**extra, **(result.extra or {})}
        marked = classify_known_failure(result.text or "")
        if marked:
            result.kind = marked
        return result

    async def _exec(self, argv, cwd, timeout, merge_stderr=False):
        runner = self._runner_factory(
            RunLimits(timeout_sec=timeout, max_output_bytes=MAX_OUTPUT)
        )
        result = await runner.run(
            list(argv),
            cwd,
            env=child_env(),
            stdin_bytes=None,
            merge_stderr=merge_stderr,
        )
        return result


def _has_custom_model_provider(path):
    try:
        data = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return True
    models = data.get("model")
    if isinstance(models, dict):
        for value in models.values():
            if isinstance(value, dict) and "provider" in value:
                return True
    return False


def _codex_final_text(raw):
    if not raw or not raw.strip():
        return ""
    saw_completed = False
    saw_failed = False
    texts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        typ = event.get("type") or event.get("kind")
        if typ in ("turn.failed", "error", "turn.error"):
            saw_failed = True
        if typ == "turn.completed":
            saw_completed = True
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        if typ in ("item.completed", "agent_message") or item.get("type") == "agent_message":
            text = item.get("text") or event.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    if saw_failed or not saw_completed or not texts:
        # Some exec --json dumps a single object.
        try:
            obj = json.loads(raw)
        except ValueError:
            return ""
        if isinstance(obj, dict):
            for key in ("text", "message", "last_agent_message"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
    return texts[-1].strip()


def _parse_grok_json(result):
    extra = dict(result.extra or {})
    raw = result.text or ""
    try:
        data = json.loads(raw)
    except ValueError:
        if "cancelled" in raw.lower():
            return ClientResult(kind=KIND_CANCELLED, text="", extra=extra)
        return None
    if not isinstance(data, dict):
        return None
    stop = str(data.get("stopReason") or data.get("stop_reason") or "")
    if stop in ("cancelled", "canceled"):
        return ClientResult(kind=KIND_CANCELLED, text="", extra=extra)
    if stop in ("max_turns", "max-turns"):
        return ClientResult(kind=KIND_MAX_TURNS, text="", extra=extra)
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        messages = data.get("messages") or data.get("result")
        if isinstance(messages, str) and messages.strip():
            text = messages
        else:
            return ClientResult(kind=KIND_EMPTY, text="", extra=extra)
    turns = data.get("num_turns") or data.get("numTurns") or 0
    try:
        turns_n = int(turns)
    except (TypeError, ValueError):
        turns_n = 0
    if turns_n > GROK_MAX_TURNS:
        return ClientResult(kind=KIND_MAX_TURNS, text="", extra=extra)
    if result.exit_code not in (0, None) and result.kind != KIND_OK:
        return ClientResult(kind=KIND_NONZERO, text="", extra=extra)
    if stop and stop not in ("end_turn", "end-turn", "stop", ""):
        return ClientResult(kind=KIND_INVALID, text="", extra=extra)
    return ClientResult(
        kind=KIND_OK,
        text=text.strip(),
        extra={**extra, "version": PINNED_GROK, "exit": 0, "num_turns": turns_n},
    )
