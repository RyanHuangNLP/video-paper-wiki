#!/usr/bin/env python3
"""Resolve source.md hrefs from the Markdown file's parent directory."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MD_LINK = re.compile(r"\]\((?:<)?([^)>]+)(?:>)?\)")
TICK_LINK = re.compile(r"`([^`]*source\.md#page-\d+)`")


def verify(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    parent = md_path.parent
    found: list[str] = []
    for match in MD_LINK.finditer(text):
        href = match.group(1).strip()
        if "source.md" in href or "#page-" in href:
            found.append(href)
    for match in TICK_LINK.finditer(text):
        href = match.group(1).strip()
        if href not in found:
            found.append(href)
    errors = []
    checked = []
    for href in found:
        path_part, _sep, anchor = href.partition("#")
        target = Path(path_part)
        resolved = target if target.is_absolute() else (parent / path_part).resolve()
        item = {
            "href": href,
            "resolved_from": str(parent),
            "resolved": str(resolved),
            "exists": resolved.is_file(),
            "anchor": anchor or None,
        }
        if not resolved.is_file():
            item["ok"] = False
            errors.append({**item, "error": "target_missing"})
            checked.append(item)
            continue
        body = resolved.read_text(encoding="utf-8")
        if anchor:
            needle = f'id="{anchor}"'
            item["anchor_present"] = needle in body
            if needle not in body:
                item["ok"] = False
                errors.append({**item, "error": "anchor_missing"})
                checked.append(item)
                continue
        item["ok"] = True
        checked.append(item)
    return {
        "markdown": str(md_path),
        "parent": str(parent),
        "href_count": len(found),
        "ok": not errors,
        "errors": errors,
        "checked": checked,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = {str(Path(path)): verify(Path(path)) for path in args.markdown}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if any(not item["ok"] for item in payload.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
