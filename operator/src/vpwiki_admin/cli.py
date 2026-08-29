"""Reserved operator entry point; no operator behavior is implemented yet."""

from __future__ import annotations

import json
import sys


def main() -> int:
    payload = {
        "ok": False,
        "command": "vpwiki-admin",
        "error": {
            "code": "NOT_IMPLEMENTED",
            "message": "The operator CLI is not implemented yet.",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 2


if __name__ == "__main__":
    sys.exit(main())
