"""Empty operator stub. Do not implement fetch/apply/index/parser-model."""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    sys.stdout.write(
        json.dumps(
            {
                "ok": False,
                "command": "vpwiki-admin",
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "vpwiki-admin is an empty operator stub",
                    "details": {},
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    sys.stdout.write("\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
