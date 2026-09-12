"""Immutable names, states, and limits for the staging cli-bridge plugin."""

import re

PLUGIN_NAME = "cli-bridge"
PLUGIN_VERSION = "0.3.0"

COMMAND_NAMES = (
    "dev-help",
    "dev-prd",
    "dev-approve",
    "dev-build",
    "dev-review",
    "dev-status",
    "dev-cancel",
    "dev-artifact",
    "dev-resend",
)

# Hermes host builtins that must not be rewritten to /dev-help.
HERMES_BUILTIN_COMMANDS = frozenset({"help", "status"})

OWN_COMMANDS = frozenset(COMMAND_NAMES)

STAGE_DRAFTING = "drafting"
STAGE_DRAFT = "draft"
STAGE_APPROVED = "approved"
STAGE_BUILDING = "building"
STAGE_BUILT = "built"
STAGE_REVIEWING = "reviewing"
STAGE_NEEDS_CHANGES = "needs_changes"
STAGE_READY_FOR_PR = "ready_for_pr"
STAGE_NEEDS_USER = "needs_user"
STAGE_RATE_LIMITED = "rate_limited"
STAGE_CANCELLED = "cancelled"
STAGE_FAILED = "failed"

ALL_STAGES = frozenset(
    {
        STAGE_DRAFTING,
        STAGE_DRAFT,
        STAGE_APPROVED,
        STAGE_BUILDING,
        STAGE_BUILT,
        STAGE_REVIEWING,
        STAGE_NEEDS_CHANGES,
        STAGE_READY_FOR_PR,
        STAGE_NEEDS_USER,
        STAGE_RATE_LIMITED,
        STAGE_CANCELLED,
        STAGE_FAILED,
    }
)

# In-flight jobs recovered to needs_user on store open. No PID kill, no rerun.
IN_PROGRESS_STAGES = frozenset(
    {STAGE_DRAFTING, STAGE_BUILDING, STAGE_REVIEWING}
)

# Running stages occupy the exclusive per-project job slot.
ACTIVE_RUN_STAGES = frozenset(
    {STAGE_DRAFTING, STAGE_BUILDING, STAGE_REVIEWING}
)

# Terminal states free every slot. Idle waiting states do not block a new draft.
TERMINAL_STAGES = frozenset(
    {STAGE_CANCELLED, STAGE_FAILED, STAGE_READY_FOR_PR}
)

TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MAX_REQUIREMENT_CHARS = 32000
MAX_PRD_CHARS = 400000
MAX_REPORT_CHARS = 400000
MAX_REVIEW_CHARS = 200000
MAX_SUMMARY_CHARS = 500
MAX_PREVIEW_CHARS = 240
MAX_STATE_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 2_000_000
ARTIFACT_PAGE_CHARS = 6000
MAX_MESSAGE_CHARS = 7000
ARTIFACT_SELECTORS = ("prd", "build", "review")
MAX_HANDOFF_ROUNDS = 8

# Process runner bounds (tests use short timeouts; live policy is later).
DEFAULT_PROCESS_TIMEOUT_SEC = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
KILL_GRACE_SEC = 1.0
STREAM_CHUNK_BYTES = 4096

DIR_MODE = 0o700
FILE_MODE = 0o600

ALLOWED_PLATFORM = "feishu"
ALLOWED_CHAT_TYPE = "dm"
ALLOWED_GROUP_CHAT_TYPE = "group"
ALLOWED_SENDER_TYPE = "user"
BOT_SENDER_TYPES = frozenset({"bot", "app"})

CLI_ROLE_BOTH = "both"
CLI_ROLE_CODEX = "codex"
CLI_ROLE_GROK = "grok"
VALID_CLI_ROLES = frozenset({CLI_ROLE_BOTH, CLI_ROLE_CODEX, CLI_ROLE_GROK, ""})

CODEX_ONLY_COMMANDS = frozenset({"dev-prd", "dev-approve", "dev-review"})
GROK_ONLY_COMMANDS = frozenset({"dev-build"})
HUMAN_ONLY_COMMANDS = frozenset({"dev-prd", "dev-approve", "dev-cancel", "dev-resend"})
PEER_COMMANDS = frozenset(
    {"dev-help", "dev-build", "dev-review", "dev-status", "dev-artifact"}
)


def commands_for_role(role):
    value = (role or CLI_ROLE_BOTH).strip().lower()
    if value in ("", CLI_ROLE_BOTH):
        return COMMAND_NAMES
    if value == CLI_ROLE_CODEX:
        return tuple(name for name in COMMAND_NAMES if name not in GROK_ONLY_COMMANDS)
    if value == CLI_ROLE_GROK:
        return tuple(name for name in COMMAND_NAMES if name not in CODEX_ONLY_COMMANDS)
    return COMMAND_NAMES

REVIEW_VERDICTS = frozenset({"pass", "needs_changes", "fail"})

HELP_TEXT = (
    "cli-bridge owner commands (staging; live execution disabled by default):\n"
    "/dev-help\n"
    "/dev-prd <requirement>\n"
    "/dev-approve <task-id> <sha256>\n"
    "/dev-build <task-id>\n"
    "/dev-review <task-id>\n"
    "/dev-status [task-id]\n"
    "/dev-cancel <task-id>\n"
    "/dev-artifact <task-id> <prd|build|review> [page]\n"
    "/dev-resend <task-id> [handoff]\n"
    "Unknown messages are rewritten to /dev-help. Rewriting is not a security "
    "boundary; a dedicated no-model gateway is required before any deployment."
)

SAFE_COMMAND_FAILED = "Command failed."
UNAUTHORIZED = "Unauthorized."
ROLE_DENIED = "This bot does not handle that command."
REWRITE_HELP = {"action": "rewrite", "text": "/dev-help"}


def help_text_for_role(role):
    names = commands_for_role(role)
    value = (role or CLI_ROLE_BOTH).strip().lower() or CLI_ROLE_BOTH
    lines = [
        "cli-bridge commands (role=%s; live CLI is policy-gated):" % value,
    ]
    for name in names:
        lines.append("/" + name)
    lines.append("Identity is the Feishu bot display name; replies do not recite it.")
    lines.append(
        "Unknown messages are rewritten to /dev-help. Rewriting is not a "
        "security boundary; owner/peer checks are."
    )
    return "\n".join(lines)
