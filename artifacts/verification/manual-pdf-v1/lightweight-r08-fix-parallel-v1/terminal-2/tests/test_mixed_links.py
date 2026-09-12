"""Independent mixed-link regressions. Drive the selected verify_links.py CLI only."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

PYTHON = "/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python"
HEX = "a" * 64
PAGE_ONE = '<a id="page-1"></a>\n\n## PDF 第 1 页\n\nquasar describes the first PDF page only.\n'


def _identity_log() -> Path | None:
    raw = os.environ.get("MIXED_LINKS_IDENTITY_LOG")
    return Path(raw) if raw else None


def _report_dir() -> Path | None:
    raw = os.environ.get("MIXED_LINKS_REPORT_DIR")
    return Path(raw) if raw else None


def _write_workspace(root: Path) -> tuple[Path, Path]:
    workspace = root / "ws"
    source = workspace / "papers" / HEX / "source.md"
    source.parent.mkdir(parents=True)
    source.write_text(PAGE_ONE, encoding="utf-8")
    output_dir = root / "out"
    output_dir.mkdir()
    return workspace, output_dir


def _good_href() -> str:
    return f"../ws/papers/{HEX}/source.md#page-1"


def _missing_source() -> str:
    return f"../missing/papers/{HEX}/source.md"


def _url_parts(href: str) -> tuple[str, str, str]:
    parsed = urlsplit(href)
    path = unquote(parsed.path)
    query = parsed.query
    fragment = unquote(parsed.fragment)
    return path, query, fragment


def _resolve_file(output_parent: Path, href: str) -> Path:
    path, _query, _fragment = _url_parts(href)
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (output_parent / path).resolve()


def _run_cli(verifier: Path, workspace: Path, output: Path, report: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        PYTHON,
        "-B",
        str(verifier),
        "--workspace",
        str(workspace),
        "--output",
        str(output),
        "--report",
        str(report),
    ]
    identity = _identity_log()
    if identity is not None:
        identity.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "argv": cmd,
                "argv_script": cmd[2],
                "verifier": str(verifier),
                "script_equals_verifier": Path(cmd[2]).resolve() == verifier.resolve(),
            }
        )
        previous = identity.read_text(encoding="utf-8") if identity.exists() else ""
        identity.write_text(previous + line + "\n", encoding="utf-8")
    return subprocess.run(cmd, cwd=str(output.parent), text=True, capture_output=True, timeout=20)


def _persist_report(name: str, report: Path) -> None:
    directory = _report_dir()
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True)
    if report.is_file():
        (directory / f"{name}.json").write_bytes(report.read_bytes())
    else:
        (directory / f"{name}.missing").write_text("report file was not written\n", encoding="utf-8")


def _load_report(report: Path) -> dict | None:
    if not report.is_file():
        return None
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if type(payload) is dict else None


def _errors_text(report: dict | None) -> str:
    if not report:
        return ""
    errors = report.get("errors") or []
    return "\n".join(str(item) for item in errors)


def _assert_refused_bad_source(*, proc: subprocess.CompletedProcess[str], report_path: Path, report: dict | None, needle: str) -> None:
    assert report_path.is_file(), "CLI must write a report; a crash without a report is not a correct refusal"
    assert report is not None, "report must be JSON object"
    assert proc.returncode != 0, f"mixed bad source link must be nonzero, got {proc.returncode}"
    assert report.get("ok") is False, f"report ok must be false, got {report.get('ok')!r}"
    errors = report.get("errors") or []
    assert type(errors) is list and errors, "errors must be nonempty"
    blob = _errors_text(report)
    assert needle in blob, f"errors must show the bad source href was processed; missing {needle!r} in {blob!r}"


def test_identity_cli_invokes_selected_verifier(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    output.write_text(f"[ok]({_good_href()})\n", encoding="utf-8")
    report = tmp_path / "identity.json"
    proc = _run_cli(verifier, workspace, output, report)
    assert Path(proc.args[2]).resolve() == verifier.resolve()
    digest = hashlib.sha256(verifier.read_bytes()).hexdigest()
    assert len(digest) == 64


def test_valid_source_link_alone_succeeds(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    href = _good_href()
    output.write_text(f"[ok]({href})\n", encoding="utf-8")
    target, fragment = _resolve_file(output.parent, href), _url_parts(href)[2]
    assert target.is_file()
    assert f'<a id="{fragment}"></a>' in target.read_text(encoding="utf-8")
    report_path = tmp_path / "valid.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("valid_only", report_path)
    report = _load_report(report_path)
    assert report_path.is_file()
    assert proc.returncode == 0
    assert report is not None and report.get("ok") is True
    assert report.get("errors") == []


def test_missing_source_md_without_query_or_title_is_refused(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    href = _missing_source() + "#page-1"
    output.write_text(f"[bad]({href})\n", encoding="utf-8")
    target = _resolve_file(output.parent, href)
    assert not target.exists()
    report_path = tmp_path / "missing-plain.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("missing_source_plain", report_path)
    report = _load_report(report_path)
    _assert_refused_bad_source(proc=proc, report_path=report_path, report=report, needle=str(HEX))


def test_valid_plus_missing_nonsource_link_still_succeeds(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    ordinary = "../nowhere.png"
    output.write_text(f"[ok]({_good_href()})\n[img]({ordinary})\n", encoding="utf-8")
    assert not (output.parent / ordinary).exists()
    good = _resolve_file(output.parent, _good_href())
    assert good.is_file()
    report_path = tmp_path / "ordinary.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("valid_plus_nonsource", report_path)
    report = _load_report(report_path)
    assert report_path.is_file()
    assert proc.returncode == 0
    assert report is not None and report.get("ok") is True
    assert report.get("errors") == []


def test_mixed_query_missing_source_is_refused(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    bad = _missing_source() + "?x=1#page-1"
    output.write_text(f"[ok]({_good_href()})\n[bad]({bad})\n", encoding="utf-8")
    target = _resolve_file(output.parent, bad)
    assert not target.exists(), "disk oracle: query href path without ?x=1 must not exist"
    report_path = tmp_path / "mixed-query.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("mixed_query", report_path)
    report = _load_report(report_path)
    _assert_refused_bad_source(proc=proc, report_path=report_path, report=report, needle="missing/papers")
    blob = _errors_text(report)
    assert "?x=1" in blob or "missing/papers" in blob or "unsupported" in blob or "illegal" in blob


def test_mixed_markdown_title_missing_source_is_refused(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    missing = _missing_source()
    output.write_text(f'[ok]({_good_href()})\n[bad]({missing}#page-1 "missing")\n', encoding="utf-8")
    target = _resolve_file(output.parent, missing + "#page-1")
    assert not target.exists(), "disk oracle: titled missing source.md does not exist"
    report_path = tmp_path / "mixed-title.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("mixed_title", report_path)
    report = _load_report(report_path)
    blob_needles = (HEX, "missing", "unsupported", "illegal", "source.md")
    _assert_refused_bad_source(proc=proc, report_path=report_path, report=report, needle=HEX)
    blob = _errors_text(report)
    assert any(token in blob for token in blob_needles)


def test_mixed_unquoted_html_missing_anchor_is_refused(verifier: Path, tmp_path: Path) -> None:
    workspace, output_dir = _write_workspace(tmp_path)
    output = output_dir / "answer.md"
    html_href = f"../ws/papers/{HEX}/source.md#page-2"
    output.write_text(f"[ok]({_good_href()})\n<a href={html_href}>bad</a>\n", encoding="utf-8")
    target = _resolve_file(output.parent, html_href)
    assert target.is_file(), "disk oracle: HTML href file exists"
    assert '<a id="page-2"></a>' not in target.read_text(encoding="utf-8"), "disk oracle: page-2 is absent"
    report_path = tmp_path / "mixed-html.json"
    proc = _run_cli(verifier, workspace, output, report_path)
    _persist_report("mixed_html", report_path)
    report = _load_report(report_path)
    _assert_refused_bad_source(proc=proc, report_path=report_path, report=report, needle="page-2")
