"""JSON stdout envelope for the agent-safe vpwiki CLI."""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

EXIT_SUCCESS = 0
EXIT_UNEXPECTED = 1
EXIT_REFUSAL = 2
EXIT_TEMPORARY_FAILURE = 75


def _dump(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_success(command: str, data: dict[str, Any]) -> int:
    _dump({"ok": True, "command": command, "data": data})
    return EXIT_SUCCESS


def emit_error(
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    exit_code: int = EXIT_REFUSAL,
) -> int:
    _dump(
        {
            "ok": False,
            "command": command,
            "error": {
                "code": code,
                "message": message,
                "details": {} if details is None else details,
            },
        }
    )
    return exit_code
