#!/usr/bin/env python3
"""Build protocol answer/draft JSON from this export's evidence. Not model-quality evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--answer", default=None)
    parser.add_argument("--draft", default=None)
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    evidence = context.get("evidence") or []
    if not evidence:
        raise SystemExit("protocol JSON needs evidence[].chunk_id from this export")
    first = str(evidence[0]["chunk_id"])
    second = str(evidence[1]["chunk_id"]) if len(evidence) > 1 else first
    if args.answer:
        payload = {
            "text": (
                f"Protocol walkthrough using this export. First evidence [@{first}]. "
                f"Second evidence [@{second}]."
            ),
            "citations": [{"chunk_id": first}, {"chunk_id": second}],
        }
        Path(args.answer).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.draft:
        payload = {
            "markdown": (
                f"Protocol paragraph one [@{first}].\n\n"
                f"Protocol paragraph two [@{second}]."
            ),
            "citations": [{"chunk_id": first}, {"chunk_id": second}],
        }
        Path(args.draft).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.answer and not args.draft:
        raise SystemExit("provide --answer and/or --draft")


if __name__ == "__main__":
    main()
