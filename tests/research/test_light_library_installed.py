"""Isolated installed-wheel checks for the integrated lightweight library CLI.

Builds a fresh wheel from this source, installs it into a temporary venv, and
runs live-backend operations through isolated console/module entrypoints.
Missing owner modules fail. Fixture JSON is built from those installed exports.
This is not a real-paper trial.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from tests.research.conftest import ROOT
from tests.research.test_light_cli import _pdf_with_page_texts
from tests.research.test_light_compare import _comparison_document
from tests.research.test_light_knowledge import _knowledge_document
from tests.research.test_light_workflow_installed import (
    _HATCHLING_PKGS,
    _build_env,
    _create_isolated_venv,
    _hatchling_roots,
    _install_wheel,
    _isolated_run_env,
    _purelib,
    _run,
    _runtime_python,
    _seed_locked_runtime_deps,
    _sha256,
)

OWNED_CLI = Path("src/video_paper_wiki_research/cli.py")
BACKEND_MODULES = (
    Path("src/video_paper_wiki_research/cli.py"),
    Path("src/video_paper_wiki_research/light_backup.py"),
    Path("src/video_paper_wiki_research/light_compare.py"),
    Path("src/video_paper_wiki_research/light_context.py"),
    Path("src/video_paper_wiki_research/light_index.py"),
    Path("src/video_paper_wiki_research/light_knowledge.py"),
    Path("src/video_paper_wiki_research/light_library.py"),
    Path("src/video_paper_wiki_research/light_library_state.py"),
    Path("src/video_paper_wiki_research/light_pdf.py"),
    Path("src/video_paper_wiki_research/light_workspace.py"),
)


def _offline_cache() -> Path:
    candidates = []
    for key in ("LW2_UV_CACHE", "UV_CACHE_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw:
            candidates.append(Path(raw))
    candidates.append(Path.home() / ".cache" / "uv")
    for cache in candidates:
        archive = cache / "archive-v0"
        if not archive.is_dir():
            continue
        if all(any((child / name).is_dir() for child in archive.iterdir() if child.is_dir()) for name in _HATCHLING_PKGS):
            return cache
    raise AssertionError("no offline uv cache contains hatchling build dependencies")


def _build_offline_wheel(python: Path, tmp_path: Path) -> Path:
    preset = os.environ.get("LW2_INSTALLED_WHEEL", "").strip()
    if preset:
        wheel = Path(preset)
        if not wheel.is_file():
            raise AssertionError(f"LW2_INSTALLED_WHEEL does not exist: {wheel}")
        return wheel.resolve()
    out_dir = tmp_path / "dist"
    out_dir.mkdir()
    cache = _offline_cache()
    roots = _hatchling_roots(cache)
    built = _run(
        [str(python), "-B", "-m", "hatchling", "build", "-t", "wheel", "-d", str(out_dir)],
        cwd=ROOT,
        env=_build_env({"PYTHONPATH": os.pathsep.join(str(path) for path in roots), "UV_CACHE_DIR": str(cache)}),
    )
    wheels = sorted(out_dir.glob("*.whl"))
    if built.returncode != 0 or not wheels:
        raise AssertionError(
            "offline hatchling wheel build failed\n"
            f"cache={cache}\nexit={built.returncode}\nstdout={built.stdout}\nstderr={built.stderr}"
        )
    return wheels[0].resolve()


def _installed(venv_python: Path, env: dict[str, str], cwd: Path, args: list[str], *, expect: int = 0) -> dict:
    assert not env.get("PYTHONPATH")
    result = _run(
        [str(venv_python), "-I", "-B", "-m", "video_paper_wiki_research", *args],
        cwd=cwd,
        env=env,
    )
    assert result.returncode == expect, result.stderr or result.stdout
    return json.loads(result.stdout)


NESTED_CHINESE_NOTE = Path("笔记") / "深层" / "阅读.md"
NESTED_GREEK_CODE = Path("notes-α") / "deep" / "code-δ.py"
NESTED_EMPTY_DIR = Path("notes-α") / "deep" / "empty"
ASCII_NOTE = Path("notes.md")
CHINESE_EXTERNAL_REPORT = "外部报告.md"


def _add_nested_notes(paper: Path) -> None:
    (paper / NESTED_EMPTY_DIR).mkdir(parents=True)
    (paper / NESTED_GREEK_CODE).write_text("# Greek code-note\nprint('γ')\n", encoding="utf-8")
    (paper / NESTED_CHINESE_NOTE).parent.mkdir(parents=True)
    (paper / NESTED_CHINESE_NOTE).write_text("嵌套中文笔记\n", encoding="utf-8")


def _console(script: Path, env: dict[str, str], cwd: Path, args: list[str], *, expect: int = 0) -> dict:
    assert not env.get("PYTHONPATH")
    result = _run([str(script), *args], cwd=cwd, env=env)
    assert result.returncode == expect, result.stderr or result.stdout
    return json.loads(result.stdout)


def _paper_inventory(paper: Path) -> tuple[dict[str, bytes], list[str]]:
    files = {
        path.relative_to(paper).as_posix(): path.read_bytes()
        for path in paper.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    directories = sorted(
        path.relative_to(paper).as_posix()
        for path in paper.rglob("*")
        if path.is_dir() and not path.is_symlink()
    )
    return files, directories


def test_fresh_wheel_exposes_live_backends_and_runs_operations(tmp_path: Path) -> None:
    for rel in BACKEND_MODULES:
        if not (ROOT / rel).is_file():
            raise AssertionError(f"required backend is missing from source: {rel}")
    python = _runtime_python()
    wheel = _build_offline_wheel(python, tmp_path)
    venv = tmp_path / "isolated-venv"
    venv_python, bindir = _create_isolated_venv(python, venv)
    _install_wheel(venv_python, wheel, tmp_path)
    env = _isolated_run_env(venv, bindir)
    assert "PYTHONPATH" not in env or not env.get("PYTHONPATH")
    venv_site = _purelib(venv_python, isolated=True, cwd=tmp_path)
    _seed_locked_runtime_deps(venv_site)

    inspect = _run(
        [
            str(venv_python),
            "-I",
            "-B",
            "-c",
            (
                "import hashlib, json, sys\n"
                "from pathlib import Path\n"
                "from video_paper_wiki_research import cli, light_backup, light_compare, light_context, "
                "light_index, light_knowledge, light_library, light_library_state, light_pdf, light_workspace\n"
                "mods = {\n"
                "    'cli': cli, 'light_backup': light_backup, 'light_compare': light_compare,\n"
                "    'light_context': light_context, 'light_index': light_index,\n"
                "    'light_knowledge': light_knowledge, 'light_library': light_library,\n"
                "    'light_library_state': light_library_state, 'light_pdf': light_pdf,\n"
                "    'light_workspace': light_workspace,\n"
                "}\n"
                "print(json.dumps({\n"
                "    'executable': sys.executable,\n"
                "    'prefix': sys.prefix,\n"
                "    'files': {name: str(Path(mod.__file__)) for name, mod in mods.items()},\n"
                "    'sha256': {name: hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest() for name, mod in mods.items()},\n"
                "}))\n"
            ),
        ],
        cwd=tmp_path,
        env=env,
    )
    assert inspect.returncode == 0, inspect.stderr
    payload = json.loads(inspect.stdout)
    assert Path(payload["executable"]).resolve() == venv_python.resolve()
    assert Path(payload["prefix"]).resolve() == venv.resolve()
    for name, rel in (
        ("cli", OWNED_CLI),
        ("light_backup", Path("src/video_paper_wiki_research/light_backup.py")),
        ("light_compare", Path("src/video_paper_wiki_research/light_compare.py")),
        ("light_context", Path("src/video_paper_wiki_research/light_context.py")),
        ("light_index", Path("src/video_paper_wiki_research/light_index.py")),
        ("light_knowledge", Path("src/video_paper_wiki_research/light_knowledge.py")),
        ("light_library", Path("src/video_paper_wiki_research/light_library.py")),
        ("light_library_state", Path("src/video_paper_wiki_research/light_library_state.py")),
        ("light_pdf", Path("src/video_paper_wiki_research/light_pdf.py")),
        ("light_workspace", Path("src/video_paper_wiki_research/light_workspace.py")),
    ):
        installed = Path(payload["files"][name])
        assert ROOT.resolve() not in installed.resolve().parents
        assert payload["sha256"][name] == _sha256(ROOT / rel)

    help_run = _run(
        [str(venv_python), "-I", "-B", "-m", "video_paper_wiki_research", "--help"],
        cwd=tmp_path,
        env=env,
    )
    assert help_run.returncode == 0, help_run.stderr
    for name in ("library", "knowledge", "compare", "backup", "workflow"):
        assert name in help_run.stdout

    workspace = tmp_path / ".work" / "installed-ws"
    workspace.mkdir(parents=True)
    listed = _installed(venv_python, env, tmp_path, ["library", "list", "--workspace", str(workspace)])
    assert listed["ok"] is True
    assert listed["papers"] == []

    first_pdf = tmp_path / "installed-alpha.pdf"
    second_pdf = tmp_path / "installed-beta.pdf"
    first_pdf.write_bytes(_pdf_with_page_texts(["Installed residual attention transformer uniquealpha."]))
    second_pdf.write_bytes(_pdf_with_page_texts(["Installed diffusion transformer uniquebeta."]))
    alpha = _installed(
        venv_python,
        env,
        tmp_path,
        ["pdf", "add", "--pdf", str(first_pdf), "--workspace", str(workspace), "--title", "InstalledAlpha"],
    )
    beta = _installed(
        venv_python,
        env,
        tmp_path,
        ["pdf", "add", "--pdf", str(second_pdf), "--workspace", str(workspace), "--title", "InstalledBeta"],
    )
    assert alpha["ok"] is True and beta["ok"] is True
    paper = Path(alpha["markdown_path"]).parent
    note = paper / ASCII_NOTE
    note.write_text("keep this installed user note\n", encoding="utf-8")
    _add_nested_notes(paper)
    nested_bytes = {
        ASCII_NOTE.as_posix(): note.read_bytes(),
        NESTED_CHINESE_NOTE.as_posix(): (paper / NESTED_CHINESE_NOTE).read_bytes(),
        NESTED_GREEK_CODE.as_posix(): (paper / NESTED_GREEK_CODE).read_bytes(),
    }
    live_inventory = _paper_inventory(paper)
    assert NESTED_EMPTY_DIR.as_posix() in live_inventory[1]
    assert NESTED_CHINESE_NOTE.as_posix() in live_inventory[0]
    assert NESTED_GREEK_CODE.as_posix() in live_inventory[0]

    built = _installed(venv_python, env, tmp_path, ["index", "build", "--workspace", str(workspace)])
    assert built["ok"] is True
    prepared = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "workflow",
            "prepare",
            "--workspace",
            str(workspace),
            "--kind",
            "qa",
            "--query",
            "residual attention transformer",
            "--paper-id",
            alpha["paper_id"],
        ],
    )
    assert prepared["ok"] is True
    session_dir = Path(prepared["context_path"]).parent
    session_files = {
        name: (session_dir / name).read_bytes() for name in ("request.json", "context.json", "manifest.json")
    }

    exported = _installed(
        venv_python,
        env,
        tmp_path,
        ["knowledge", "export", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
    )
    assert exported["ok"] is True
    chunk = exported["context"]["evidence"][0]["chunk_id"]
    context_path = workspace / "installed-kctx.json"
    document_path = workspace / "installed-kdoc.json"
    context_path.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")
    # LABELLED fixture built from the installed export; not a current-model trial.
    document_path.write_text(
        json.dumps(_knowledge_document(alpha["paper_id"], chunk), ensure_ascii=False),
        encoding="utf-8",
    )
    imported = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "knowledge",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(context_path),
            "--document",
            str(document_path),
        ],
    )
    assert imported["ok"] is True
    views = _installed(venv_python, env, tmp_path, ["knowledge", "build", "--workspace", str(workspace)])
    assert views["ok"] is True
    knowledge = _installed(venv_python, env, tmp_path, ["knowledge", "list", "--workspace", str(workspace)])
    assert knowledge["ok"] is True
    assert knowledge["heads"][alpha["paper_id"]] == imported["record_id"]

    compared = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "compare",
            "export",
            "--workspace",
            str(workspace),
            "--query",
            "transformer",
            "--paper-id",
            alpha["paper_id"],
            "--paper-id",
            beta["paper_id"],
        ],
    )
    assert compared["ok"] is True
    by_paper = {item["paper_id"]: item["chunk_id"] for item in compared["context"]["evidence"]}
    compare_ctx = workspace / "installed-cctx.json"
    compare_doc = workspace / "installed-cdoc.json"
    compare_md = workspace / "reports" / "compare.md"
    compare_ctx.write_text(json.dumps(compared, ensure_ascii=False), encoding="utf-8")
    compare_doc.write_text(
        json.dumps(_comparison_document([alpha["paper_id"], beta["paper_id"]], by_paper), ensure_ascii=False),
        encoding="utf-8",
    )
    table = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "compare",
            "import",
            "--workspace",
            str(workspace),
            "--context",
            str(compare_ctx),
            "--document",
            str(compare_doc),
            "--output",
            str(compare_md),
        ],
    )
    assert table["ok"] is True
    markdown = compare_md.read_text(encoding="utf-8")
    assert "|" in markdown
    assert "source.md#page-1" in markdown

    tagged = _installed(
        venv_python,
        env,
        tmp_path,
        ["library", "edit", "--workspace", str(workspace), "--paper-id", alpha["paper_id"], "--tag", "installed"],
    )
    assert tagged["ok"] is True
    assert tagged["tags"] == ["installed"]
    live_inventory = _paper_inventory(paper)
    archived = _installed(
        venv_python,
        env,
        tmp_path,
        ["library", "remove", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
    )
    assert archived["ok"] is True
    archive_paper = workspace / ".light-library" / "archive" / archived["archive_id"] / "paper"
    assert not paper.exists()
    assert _paper_inventory(archive_paper) == live_inventory
    restored_paper = _installed(
        venv_python,
        env,
        tmp_path,
        ["library", "restore", "--workspace", str(workspace), "--archive-id", archived["archive_id"]],
    )
    assert restored_paper["ok"] is True
    assert _paper_inventory(paper) == live_inventory
    assert (paper / NESTED_EMPTY_DIR).is_dir()
    for rel, data in nested_bytes.items():
        assert (paper / rel).read_bytes() == data
        assert (paper / rel).name == Path(rel).name

    replacement_pdf = tmp_path / "installed-replacement.pdf"
    replacement_pdf.write_bytes(_pdf_with_page_texts(["Installed replacement unique-replace."]))
    replaced = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "library",
            "replace",
            "--workspace",
            str(workspace),
            "--paper-id",
            alpha["paper_id"],
            "--pdf",
            str(replacement_pdf),
            "--title",
            "Installed replaced",
        ],
    )
    assert replaced["ok"] is True
    assert replaced["new_paper_id"] != alpha["paper_id"]
    old_archive = workspace / ".light-library" / "archive" / replaced["archive_id"] / "paper"
    assert _paper_inventory(old_archive) == live_inventory
    current = workspace / "papers" / replaced["new_paper_id"].split(":", 1)[1]
    prior = (current / "prior-paper-notes.md").read_text(encoding="utf-8")
    assert NESTED_GREEK_CODE.as_posix() in prior
    assert NESTED_CHINESE_NOTE.as_posix() in prior
    recovered = _installed(venv_python, env, tmp_path, ["library", "recover", "--workspace", str(workspace)])
    assert recovered["ok"] is True
    assert recovered["operations"]
    assert all(item.get("ok") is True for item in recovered["operations"])

    extra = tmp_path / CHINESE_EXTERNAL_REPORT
    extra_bytes = "外部报告：中文与 Ελληνικά\n".encode("utf-8")
    extra.write_bytes(extra_bytes)
    extra_before = extra.read_bytes()
    backup = tmp_path / ".work" / "installed-backups" / "ws.zip"
    backup.parent.mkdir(parents=True)
    created = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup),
            "--include-output",
            str(extra),
        ],
    )
    assert created["ok"] is True
    assert created.get("reused") is False
    first_backup = backup.read_bytes()
    reused_backup = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "backup",
            "create",
            "--workspace",
            str(workspace),
            "--output",
            str(backup),
            "--include-output",
            str(extra),
        ],
    )
    assert reused_backup["ok"] is True
    assert reused_backup.get("reused") is True
    assert backup.read_bytes() == first_backup

    script = bindir / "vpwiki-research"
    if not script.is_file():
        script = bindir / "vpwiki-research.exe"
    if not script.is_file():
        raise AssertionError(f"console script vpwiki-research is missing from isolated venv: {bindir}")

    tagged_beta = _console(
        script,
        env,
        tmp_path,
        ["library", "edit", "--workspace", str(workspace), "--paper-id", beta["paper_id"], "--tag", "console"],
    )
    assert tagged_beta["ok"] is True
    assert tagged_beta["tags"] == ["console"]

    verified = _console(script, env, tmp_path, ["backup", "verify", "--archive", str(backup)])
    assert verified["ok"] is True
    extra_rows = verified.get("extra_outputs") or []
    assert extra_rows
    assert extra_rows[0]["restore_path"].endswith(CHINESE_EXTERNAL_REPORT)
    destination = tmp_path / ".work" / "installed-restored"
    restored = _console(
        script,
        env,
        tmp_path,
        ["backup", "restore", "--archive", str(backup), "--destination", str(destination)],
    )
    assert restored["ok"] is True
    hist = Path(restored["historical_session_root"])
    for name, data in session_files.items():
        assert (hist / session_dir.name / name).read_bytes() == data
    dest_notes = list(destination.joinpath(".light-library").glob("archive/*/paper/notes.md"))
    dest_chinese = list(destination.joinpath(".light-library").glob("archive/*/paper/笔记/深层/阅读.md"))
    dest_code = list(destination.joinpath(".light-library").glob("archive/*/paper/notes-α/deep/code-δ.py"))
    assert any("keep this installed user note" in path.read_text(encoding="utf-8") for path in dest_notes)
    assert dest_chinese
    assert all(path.name == "阅读.md" for path in dest_chinese)
    assert all(path.read_bytes() == nested_bytes[NESTED_CHINESE_NOTE.as_posix()] for path in dest_chinese)
    assert dest_code
    assert all(path.name == "code-δ.py" for path in dest_code)
    assert all(path.read_bytes() == nested_bytes[NESTED_GREEK_CODE.as_posix()] for path in dest_code)
    assert (destination / extra_rows[0]["restore_path"]).read_bytes() == extra_bytes
    assert extra.read_bytes() == extra_before

    script_list = _console(script, env, tmp_path, ["library", "list", "--workspace", str(workspace)])
    assert any(item["paper_id"] == replaced["new_paper_id"] for item in script_list["papers"])
    assert any(item["paper_id"] == beta["paper_id"] for item in script_list["papers"])
    beta_row = next(item for item in script_list["papers"] if item["paper_id"] == beta["paper_id"])
    assert beta_row["tags"] == ["console"]

    record = tmp_path / "installed-library-observation.json"
    observation = {
        "wheel": str(wheel),
        "wheel_sha256": _sha256(wheel),
        "runtime_python": str(python),
        "venv_python": str(venv_python),
        "venv": str(venv),
        "observed_executable": payload["executable"],
        "observed_prefix": payload["prefix"],
        "console_script": str(script),
        "backends": payload,
        "owner_modules_expected": "integrated",
        "operations": [
            "knowledge import/build/list",
            "compare export/import",
            "metadata",
            "archive/restore/replace/recover",
            "unicode nested notes and Chinese external report",
            "backup create/verify/restore/reuse",
            "console backup verify/restore",
            "console library edit",
        ],
    }
    record.write_text(json.dumps(observation, indent=2) + "\n", encoding="utf-8")
    assert json.loads(record.read_text(encoding="utf-8"))["owner_modules_expected"] == "integrated"
