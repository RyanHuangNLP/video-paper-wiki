#!/usr/bin/env python3
"""Read-only local checker for product-generated paper source links. Stdlib only."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PAGE = re.compile(r"^page-\d+$")
_MD_HREF = re.compile(r"\]\((?:<([^>]+)>|([^)\s]+))\)")
_TICK = re.compile(r"`([^`]+)`")
_HTML_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_NETWORK = frozenset({"http", "https", "ftp"})


def verify_links(workspace: Path, output: Path, report: Path | None = None) -> dict[str, Any]:
    """Inspect Markdown source citations. Read-only on workspace/output; may write report."""
    if not isinstance(workspace, Path):
        workspace = Path(workspace)
    if not isinstance(output, Path):
        output = Path(output)
    if report is not None and not isinstance(report, Path):
        report = Path(report)
    errors: list[str] = []
    checked: list[dict[str, Any]] = []
    if not workspace.is_dir() or workspace.is_symlink():
        errors.append(f"workspace is not a regular directory: {workspace}")
        return _finish(False, 0, checked, errors, report)
    if not output.is_file() or output.is_symlink():
        errors.append(f"output markdown is missing: {output}")
        return _finish(False, 0, checked, errors, report)
    markdown = output.read_text(encoding="utf-8")
    hrefs = _extract_hrefs(markdown)
    workspace_root = workspace.resolve()
    output_parent = output.parent
    seen: set[str] = set()
    for href in hrefs:
        if href in seen:
            continue
        kind, scheme, path, fragment = _classify(href)
        if kind == "ordinary":
            continue
        seen.add(href)
        item = _check_source_href(
            href=href,
            kind=kind,
            scheme=scheme,
            path=path,
            fragment=fragment,
            workspace_root=workspace_root,
            output_parent=output_parent,
        )
        checked.append(item)
        errors.extend(item.pop("_errors"))
    if not checked:
        errors.append("no source citations found")
    ok = not errors
    return _finish(ok, len(checked), checked, errors, report)


def _finish(
    ok: bool,
    source_link_count: int,
    checked: list[dict[str, Any]],
    errors: list[str],
    report: Path | None,
) -> dict[str, Any]:
    payload = {
        "ok": ok,
        "source_link_count": source_link_count,
        "checked": checked,
        "errors": errors,
    }
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp = report.with_name(report.name + ".tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(report)
    return payload


def _extract_hrefs(markdown: str) -> list[str]:
    found: list[str] = []
    for match in _MD_HREF.finditer(markdown):
        href = match.group(1) if match.group(1) is not None else match.group(2)
        if href:
            found.append(href)
    for match in _TICK.finditer(markdown):
        found.append(match.group(1))
    for match in _HTML_HREF.finditer(markdown):
        href = match.group(1) if match.group(1) is not None else match.group(2)
        if href:
            found.append(href)
    return found


def _classify(href: str) -> tuple[str, str, str, str]:
    raw = href.strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme in _NETWORK or (scheme and scheme not in {"", "file"}):
        path = unquote(parsed.path)
        fragment = unquote(parsed.fragment)
        return _kind_from_path(path, fragment, network=True), scheme, path, fragment
    if scheme == "file":
        path = unquote(parsed.path)
        fragment = unquote(parsed.fragment)
        return _kind_from_path(path, fragment, network=True), scheme, path, fragment
    if "#" in raw:
        path_part, fragment_part = raw.rsplit("#", 1)
    else:
        path_part, fragment_part = raw, ""
    path = unquote(path_part)
    fragment = unquote(fragment_part)
    return _kind_from_path(path, fragment, network=False), "", path, fragment


def _kind_from_path(path: str, fragment: str, *, network: bool) -> str:
    posix = path.replace("\\", "/").rstrip("/")
    parts = [item for item in posix.split("/") if item != ""]
    if not parts:
        return "ordinary"
    looks_source = parts[-1] == "source.md"
    has_papers = "papers" in parts
    if not looks_source:
        return "ordinary"
    if not has_papers:
        if fragment.startswith("page-"):
            return "illegal"
        return "ordinary"
    well_formed = len(parts) >= 3 and parts[-3] == "papers" and _HEX64.fullmatch(parts[-2]) is not None
    if network:
        return "illegal"
    if well_formed:
        return "source"
    return "illegal"


def _check_source_href(
    *,
    href: str,
    kind: str,
    scheme: str,
    path: str,
    fragment: str,
    workspace_root: Path,
    output_parent: Path,
) -> dict[str, Any]:
    item_errors: list[str] = []
    resolved: Path | None = None
    if kind != "source" or scheme:
        item_errors.append(f"unsupported or illegal source-link syntax: {href}")
        exists = False
        if not scheme:
            resolved = _resolve(output_parent, path)
            exists = resolved.is_file()
        return {
            "href": href,
            "resolved_path": "" if resolved is None else str(resolved),
            "anchor": fragment,
            "exists": exists,
            "_errors": item_errors,
        }
    resolved = _resolve(output_parent, path)
    exists = resolved.is_file()
    if not _PAGE.fullmatch(fragment or ""):
        item_errors.append(f"unparsable source citation fragment: {href}")
    expected_digest = path.replace("\\", "/").rstrip("/").split("/")[-2]
    expected = (workspace_root / "papers" / expected_digest / "source.md").resolve()
    try:
        relative = resolved.resolve().relative_to(workspace_root)
        in_workspace = True
    except ValueError:
        relative = None
        in_workspace = False
    target_ok = in_workspace and relative is not None and relative.as_posix() == f"papers/{expected_digest}/source.md"
    if not target_ok:
        item_errors.append(
            f"resolved path is not the declared workspace papers/{expected_digest}/source.md: {href} -> {resolved}"
        )
    elif not exists:
        item_errors.append(f"missing source file: {resolved}")
    elif f'<a id="{fragment}"></a>' not in resolved.read_text(encoding="utf-8"):
        item_errors.append(f"missing page anchor {fragment} in {resolved}")
    if not exists and expected.is_file() and expected != resolved.resolve():
        item_errors.append(
            f"workspace still has {expected}, but the full href does not resolve to it"
        )
    return {
        "href": href,
        "resolved_path": str(resolved),
        "anchor": fragment,
        "exists": exists,
        "_errors": item_errors,
    }


def _resolve(output_parent: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (output_parent / path).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_links.py",
        description="Read-only checker for local paper source.md page links. No network.",
        allow_abbrev=False,
    )
    parser.add_argument("--workspace", required=True, help="absolute workspace directory")
    parser.add_argument("--output", required=True, help="absolute Markdown file to inspect")
    parser.add_argument("--report", required=True, help="absolute JSON report path")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code is None else int(code)
    for name, value in (("workspace", args.workspace), ("output", args.output), ("report", args.report)):
        if not Path(value).is_absolute():
            sys.stderr.write(f"{name} must be an absolute path\n")
            return 2
    result = verify_links(Path(args.workspace), Path(args.output), Path(args.report))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
