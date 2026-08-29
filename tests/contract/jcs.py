"""Small RFC 8785 subset used by the frozen integer-only contract vectors."""

from __future__ import annotations

import json
from typing import Any


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
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise TypeError("Contract JCS fixtures intentionally forbid floats")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JCS object keys must be strings")
        keys = sorted(value, key=_key_order)
        return "{" + ",".join(f"{_string(key)}:{_serialize(value[key])}" for key in keys) + "}"
    raise TypeError(f"Unsupported JCS value: {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """Return integer-only RFC 8785 canonical JSON as UTF-8, without a newline."""

    return _serialize(value).encode("utf-8")
