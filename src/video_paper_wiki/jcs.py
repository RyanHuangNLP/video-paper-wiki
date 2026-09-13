"""Integer-only RFC 8785 JCS. Production canonical JSON authority."""

from __future__ import annotations

import json
from typing import Any

CANONICAL_JSON_INVALID = "CANONICAL_JSON_INVALID"


class CanonicalJsonError(ValueError):
    """Input cannot be RFC 8785 canonicalized with the frozen integer-only subset."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = CANONICAL_JSON_INVALID
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = 2


def _key_order(value: str) -> bytes:
    return value.encode("utf-16-be", errors="surrogatepass")


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        raise CanonicalJsonError(
            "Contract JCS forbids floats",
            details={"type": "float"},
        )
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalJsonError(
                "JCS object keys must be strings",
                details={"type": "object"},
            )
        keys = sorted(value, key=_key_order)
        return "{" + ",".join(f"{_string(key)}:{_serialize(value[key])}" for key in keys) + "}"
    raise CanonicalJsonError(
        f"Unsupported JCS value: {type(value).__name__}",
        details={"type": type(value).__name__},
    )


def canonicalize(value: Any) -> bytes:
    """Return integer-only RFC 8785 canonical JSON as UTF-8, without a newline."""

    try:
        return _serialize(value).encode("utf-8")
    except CanonicalJsonError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalJsonError(str(exc)) from exc
