"""Independent Flow B entry: export writing context or import a Markdown draft."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from video_paper_wiki_research.writing import export_from_request, import_and_render


def _dump(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video_paper_wiki_research.writing_cli",
        description="Export writing context and render an imported Markdown draft.",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    export_cmd = sub.add_parser("export", allow_abbrev=False)
    export_cmd.add_argument("--topic", required=True)
    export_cmd.add_argument("--requirements", required=True)
    export_cmd.add_argument("--paper-id", dest="paper_ids", action="append", required=True)
    export_cmd.add_argument("--vault-root", required=True)
    export_cmd.add_argument("--upstream-root", required=True)
    export_cmd.add_argument("--config", required=True)
    import_cmd = sub.add_parser("import", allow_abbrev=False)
    import_cmd.add_argument("--context", required=True)
    import_cmd.add_argument("--draft", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "export":
        result = export_from_request(
            topic=args.topic,
            requirements=args.requirements,
            paper_ids=args.paper_ids,
            vault_root=args.vault_root,
            upstream_root=args.upstream_root,
            retrieval_config=args.config,
        )
    else:
        context_path = Path(args.context)
        draft_path = Path(args.draft)
        result = import_and_render(
            context=json.loads(context_path.read_text(encoding="utf-8")),
            draft=draft_path.read_text(encoding="utf-8"),
        )
    _dump(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
