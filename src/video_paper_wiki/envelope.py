"""JSON stdout envelopes shared by the agent-safe CLI."""

from __future__ import annotations

import json
from typing import Any

EXIT_SUCCESS = 0
EXIT_UNEXPECTED = 1
EXIT_REFUSED = 2
EXIT_TEMPORARY_FAILURE = 75


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def emit_success(command: str, result: dict[str, Any]) -> int:
    """Emit one successful response object and return the success exit code."""
    _emit({"ok": True, "command": command, "result": result})
    return EXIT_SUCCESS


def emit_error(
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    exit_code: int = EXIT_REFUSED,
) -> int:
    """Emit one error response object and return its requested exit code."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    _emit({"ok": False, "command": command, "error": error})
    return exit_code
