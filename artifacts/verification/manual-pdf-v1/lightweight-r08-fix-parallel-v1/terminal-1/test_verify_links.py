"""Independent tests for the shipped verify_links.py. Disk facts are the oracle."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
VERIFY_PY = HERE / "verify_links.py"
OLD_VERIFY = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/"
    "lightweight-r06-parallel-v1/terminal-3/verify_r06.py"
)
SAMPLE = HERE / "samples" / "r07-false-positive"
HEX_A = "a" * 64
HEX_B = "b" * 64
PAGE_ONE = '<a id="page-1"></a>\n\n## PDF 第 1 页\n\nquasar describes the first PDF page only.\n'
PYTHON = "/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python"


def _load_verify():
    spec = importlib.util.spec_from_file_location("verify_links_shipped", VERIFY_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_old():
    spec = importlib.util.spec_from_file_location("verify_r06_frozen", OLD_VERIFY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_links_mod = _load_verify()
verify_links = verify_links_mod.verify_links
old_verify = _load_old()


def _write_source(workspace: Path, digest: str, body: str = PAGE_ONE) -> Path:
    directory = workspace / "papers" / digest
    directory.mkdir(parents=True)
    path = directory / "source.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_output(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def _disk_join(output: Path, href: str) -> Path:
    raw = href
    if "#" in raw:
        raw = raw.rsplit("#", 1)[0]
    raw = raw.replace("%20", " ")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (output.parent / raw).resolve()


def _product_href(source: Path, output: Path, anchor: str = "page-1") -> str:
    display = Path(os.path.relpath(str(source.resolve()), str(output.parent.resolve()))).as_posix()
    return f"{display}#{anchor}"


def _run_cli(workspace: Path, output: Path, report: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        PYTHON,
        "-B",
        str(VERIFY_PY),
        "--workspace",
        str(workspace),
        "--output",
        str(output),
        "--report",
        str(report),
    ]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_output_at_workspace_root(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    assert source.is_file()
    assert f'<a id="page-1"></a>' in source.read_text(encoding="utf-8")
    assert _disk_join(output, href) == source.resolve()
    before = {source: source.read_bytes(), output: output.read_bytes()}
    result = verify_links(workspace, output)
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["source_link_count"] == 1
    item = result["checked"][0]
    assert item["href"] == href
    assert item["resolved_path"] == str(source.resolve())
    assert item["anchor"] == "page-1"
    assert item["exists"] is True
    assert source.read_bytes() == before[source]
    assert output.read_bytes() == before[output]


def test_output_in_workspace_subdirectory(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"../papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "notes" / "answer.md", f"[cite]({href})\n")
    assert _disk_join(output, href) == source.resolve()
    result = verify_links(workspace, output)
    assert result["ok"] is True
    assert result["checked"][0]["exists"] is True
    assert result["checked"][0]["anchor"] == "page-1"


def test_output_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    output = _write_output(tmp_path / "out" / "answer.md", "")
    href = _product_href(source, output)
    output.write_text(f"[cite]({href})\n", encoding="utf-8")
    assert ".." in href
    assert _disk_join(output, href) == source.resolve()
    result = verify_links(workspace, output)
    assert result["ok"] is True
    assert result["checked"][0]["href"] == href
    assert result["checked"][0]["exists"] is True


def test_parent_with_spaces_and_parentheses_angle_brackets(tmp_path: Path) -> None:
    workspace = tmp_path / "Project (v1)" / "ws"
    source = _write_source(workspace, HEX_A)
    output = _write_output(tmp_path / "out" / "answer.md", "")
    href = _product_href(source, output)
    assert " " in href and "(" in href
    output.write_text(f"[cite](<{href}>)\n", encoding="utf-8")
    assert _disk_join(output, href) == source.resolve()
    result = verify_links(workspace, output)
    assert result["ok"] is True
    assert result["checked"][0]["href"] == href
    assert result["checked"][0]["exists"] is True


def test_percent_encoding_and_html_and_backtick(tmp_path: Path) -> None:
    workspace = tmp_path / "My Docs" / "ws"
    source = _write_source(workspace, HEX_A)
    output = _write_output(tmp_path / "out" / "answer.md", "")
    href = _product_href(source, output)
    rel = href.rsplit("#", 1)[0]
    encoded = rel.replace(" ", "%20")
    markdown = (
        f"[angle](<{rel}#page-1>)\n"
        f'<a href="{encoded}#page-1">html cite</a>\n'
        f"`{rel}#page-1`\n"
    )
    output.write_text(markdown, encoding="utf-8")
    assert " " in rel
    assert _disk_join(output, encoded + "#page-1") == source.resolve()
    result = verify_links(workspace, output)
    assert result["ok"] is True
    hrefs = {item["href"] for item in result["checked"]}
    assert f"{encoded}#page-1" in hrefs
    assert f"{rel}#page-1" in hrefs
    assert all(item["exists"] is True and item["anchor"] == "page-1" for item in result["checked"])


def test_wrong_prefix_while_workspace_source_exists(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"other/papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    bogus = _disk_join(output, href)
    assert source.is_file()
    assert not bogus.exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["checked"][0]["exists"] is False
    assert result["checked"][0]["href"] == href
    assert any("does not resolve" in item or "not the declared workspace" in item for item in result["errors"])


def test_wrong_relative_depth(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    output = _write_output(tmp_path / "out" / "sub" / "answer.md", "")
    wrong = f"../papers/{HEX_A}/source.md#page-1"
    output.write_text(f"[cite]({wrong})\n", encoding="utf-8")
    bogus = _disk_join(output, wrong)
    assert source.is_file()
    assert not bogus.exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["checked"][0]["exists"] is False
    assert any("not the declared workspace" in item for item in result["errors"])


def test_missing_source_md(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    directory = workspace / "papers" / HEX_A
    directory.mkdir(parents=True)
    href = f"papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    missing = _disk_join(output, href)
    assert not missing.exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["checked"][0]["exists"] is False
    assert any("missing" in item for item in result["errors"])


def test_missing_page_anchor(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"papers/{HEX_A}/source.md#page-2"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    text = source.read_text(encoding="utf-8")
    assert source.is_file()
    assert '<a id="page-2"></a>' not in text
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["checked"][0]["exists"] is True
    assert result["checked"][0]["anchor"] == "page-2"
    assert any("missing page anchor page-2" in item for item in result["errors"])


def test_wrong_paper_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"papers/{HEX_B}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    bogus = _disk_join(output, href)
    assert source.is_file()
    assert not bogus.exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["checked"][0]["exists"] is False
    assert HEX_B in result["checked"][0]["href"]


def test_zero_source_citations(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _write_source(workspace, HEX_A)
    output = _write_output(
        workspace / "answer.md",
        "See [notes](notes/readme.md) and [web](https://example.invalid/page).\n",
    )
    assert "source.md" not in output.read_text(encoding="utf-8")
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["source_link_count"] == 0
    assert result["checked"] == []
    assert any("no source citations" in item for item in result["errors"])


def test_illegal_hash_is_error_not_green(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _write_source(workspace, HEX_A)
    href = "papers/not-a-real-digest/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert any("illegal" in item or "unsupported" in item for item in result["errors"])


def test_preserved_r07_false_positive_old_empty_new_fails() -> None:
    workspace = SAMPLE / "workspace"
    output = SAMPLE / "output" / "answer.md"
    source = workspace / "papers" / ("a" * 64) / "source.md"
    href = (
        "../not-workspace/papers/"
        + ("a" * 64)
        + "/source.md#page-1"
    )
    assert source.is_file()
    assert '<a id="page-1"></a>' in source.read_text(encoding="utf-8")
    bogus = _disk_join(output, href)
    assert not bogus.exists()
    markdown = output.read_text(encoding="utf-8")
    assert href in markdown
    old = old_verify._verify_links(markdown, workspace, output)
    assert old["errors"] == []
    before = source.read_bytes()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["errors"]
    assert result["checked"][0]["href"] == href
    assert result["checked"][0]["exists"] is False
    assert source.read_bytes() == before
    assert output.read_text(encoding="utf-8") == markdown


def test_cli_requires_absolute_flags_and_writes_report(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    href = f"papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    report = tmp_path / "report.json"
    good = _run_cli(workspace, output, report)
    assert good.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["checked"][0]["resolved_path"] == str(source.resolve())
    missing = subprocess.run(
        [PYTHON, "-B", str(VERIFY_PY), "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    relative = subprocess.run(
        [
            PYTHON,
            "-B",
            str(VERIFY_PY),
            "--workspace",
            "relative-ws",
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert relative.returncode != 0


def test_cli_bad_link_nonzero_and_nonempty_errors(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _write_source(workspace, HEX_A)
    href = f"../not-workspace/papers/{HEX_A}/source.md#page-1"
    output = _write_output(workspace / "answer.md", f"[cite]({href})\n")
    assert not _disk_join(output, href).exists()
    report = tmp_path / "bad.json"
    proc = _run_cli(workspace, output, report)
    assert proc.returncode != 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["errors"]
    assert payload["checked"]


def test_loads_new_r08_copy_not_old_release() -> None:
    assert "lightweight-r08-fix-parallel-v1" in str(VERIFY_PY)
    assert "lightweight-release-parallel-v1" not in str(VERIFY_PY)
    assert Path(verify_links_mod.__file__).resolve() == VERIFY_PY.resolve()


def _mixed_workspace(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    workspace = tmp_path / "ws"
    source = _write_source(workspace, HEX_A)
    output = _write_output(tmp_path / "out" / "answer.md", "")
    good = _product_href(source, output)
    missing = f"../missing/papers/{HEX_A}/source.md"
    assert source.is_file()
    assert '<a id="page-1"></a>' in source.read_text(encoding="utf-8")
    assert '<a id="page-2"></a>' not in source.read_text(encoding="utf-8")
    assert not (output.parent / missing).exists()
    return workspace, source, output, good, missing


def test_mixed_query_does_not_hide_missing_file(tmp_path: Path) -> None:
    workspace, source, output, good, missing = _mixed_workspace(tmp_path)
    query_href = f"{missing}?x=1#page-1"
    output.write_text(f"[ok]({good})\n[bad]({query_href})\n", encoding="utf-8")
    assert not (output.parent / missing).exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["errors"]
    hrefs = [item["href"] for item in result["checked"]]
    assert query_href in hrefs
    assert good in hrefs
    bad = next(item for item in result["checked"] if item["href"] == query_href)
    assert bad["exists"] is False
    assert any("query" in item for item in result["errors"])
    assert source.read_text(encoding="utf-8")


def test_mixed_markdown_title_checks_missing_target(tmp_path: Path) -> None:
    workspace, source, output, good, missing = _mixed_workspace(tmp_path)
    titled = f"{missing}#page-1"
    output.write_text(f'[ok]({good})\n[bad]({titled} "missing")\n', encoding="utf-8")
    assert not (output.parent / missing).exists()
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["errors"]
    hrefs = [item["href"] for item in result["checked"]]
    assert titled in hrefs
    assert good in hrefs
    bad = next(item for item in result["checked"] if item["href"] == titled)
    assert bad["exists"] is False


def test_mixed_unquoted_html_missing_anchor(tmp_path: Path) -> None:
    workspace, source, output, good, _missing = _mixed_workspace(tmp_path)
    unquoted = f"../ws/papers/{HEX_A}/source.md#page-2"
    output.write_text(f"[ok]({good})\n<a href={unquoted}>bad</a>\n", encoding="utf-8")
    assert source.is_file()
    assert '<a id="page-2"></a>' not in source.read_text(encoding="utf-8")
    result = verify_links(workspace, output)
    assert result["ok"] is False
    assert result["errors"]
    hrefs = [item["href"] for item in result["checked"]]
    assert unquoted in hrefs
    assert good in hrefs
    bad = next(item for item in result["checked"] if item["href"] == unquoted)
    assert bad["exists"] is True
    assert bad["anchor"] == "page-2"
    assert any("missing page anchor page-2" in item for item in result["errors"])
