"""Isolated installed-wheel checks for the integrated research CLI.

Builds a fresh wheel from this source, installs it into a temporary venv, and
runs live-backend research operations. Missing owner modules fail. Fixture JSON
is built from those installed exports. This is not a real-paper trial.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from tests.research.conftest import ROOT
from tests.research.test_light_cli import _pdf_with_page_texts
from tests.research.test_light_knowledge import _knowledge_document
from tests.research.test_light_knowledge_batch import _merge_document
from video_paper_wiki_research.light_query import REWRITE_SCHEMA
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
from tests.research.test_light_writing_project import _outline_document, _section_document

OWNED_CLI = Path("src/video_paper_wiki_research/cli.py")
BACKEND_MODULES = (
    Path("src/video_paper_wiki_research/cli.py"),
    Path("src/video_paper_wiki_research/light_backup.py"),
    Path("src/video_paper_wiki_research/light_context.py"),
    Path("src/video_paper_wiki_research/light_index.py"),
    Path("src/video_paper_wiki_research/light_knowledge.py"),
    Path("src/video_paper_wiki_research/light_knowledge_batch.py"),
    Path("src/video_paper_wiki_research/light_knowledge_refresh.py"),
    Path("src/video_paper_wiki_research/light_query.py"),
    Path("src/video_paper_wiki_research/light_writing_project.py"),
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


def test_fresh_wheel_exposes_research_backends_and_runs_operations(tmp_path: Path) -> None:
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
                "from video_paper_wiki_research import (\n"
                "    cli, light_backup, light_context, light_index, light_knowledge,\n"
                "    light_knowledge_batch, light_knowledge_refresh, light_query, light_writing_project,\n"
                ")\n"
                "mods = {\n"
                "    'cli': cli, 'light_backup': light_backup, 'light_context': light_context,\n"
                "    'light_index': light_index, 'light_knowledge': light_knowledge,\n"
                "    'light_knowledge_batch': light_knowledge_batch,\n"
                "    'light_knowledge_refresh': light_knowledge_refresh,\n"
                "    'light_query': light_query, 'light_writing_project': light_writing_project,\n"
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
        ("light_context", Path("src/video_paper_wiki_research/light_context.py")),
        ("light_index", Path("src/video_paper_wiki_research/light_index.py")),
        ("light_knowledge", Path("src/video_paper_wiki_research/light_knowledge.py")),
        ("light_knowledge_batch", Path("src/video_paper_wiki_research/light_knowledge_batch.py")),
        ("light_knowledge_refresh", Path("src/video_paper_wiki_research/light_knowledge_refresh.py")),
        ("light_query", Path("src/video_paper_wiki_research/light_query.py")),
        ("light_writing_project", Path("src/video_paper_wiki_research/light_writing_project.py")),
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
    for name in ("writing", "knowledge", "backup", "qa"):
        assert name in help_run.stdout

    workspace = tmp_path / ".work" / "installed-research"
    workspace.mkdir(parents=True)
    first_pdf = tmp_path / "installed-alpha.pdf"
    first_pdf.write_bytes(_pdf_with_page_texts(["Installed quasar method evidence uniquealpha."]))
    alpha = _installed(
        venv_python,
        env,
        tmp_path,
        ["pdf", "add", "--pdf", str(first_pdf), "--workspace", str(workspace), "--title", "InstalledAlpha"],
    )
    assert alpha["ok"] is True
    built = _installed(venv_python, env, tmp_path, ["index", "build", "--workspace", str(workspace)])
    assert built["ok"] is True
    question = "这篇论文的方法是什么"
    rewrite_path = workspace / "installed-rewrite.json"
    rewrite_path.write_text(
        json.dumps(
            {
                "language": "en",
                "original_query": question,
                "rewritten_query": "quasar method",
                "schema": REWRITE_SCHEMA,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    qa = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "qa",
            "export",
            "--question",
            question,
            "--workspace",
            str(workspace),
            "--rewrite",
            str(rewrite_path),
        ],
    )
    assert qa["ok"] is True
    assert qa["query"] == question
    assert qa["evidence"]

    topic = "请按证据写提纲"
    writing_rewrite = workspace / "installed-wrewrite.json"
    writing_rewrite.write_text(
        json.dumps(
            {
                "language": "en",
                "original_query": topic,
                "rewritten_query": "quasar method",
                "schema": REWRITE_SCHEMA,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    writing = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "writing",
            "export",
            "--topic",
            topic,
            "--requirements",
            "用中文写提纲。",
            "--workspace",
            str(workspace),
            "--rewrite",
            str(writing_rewrite),
        ],
    )
    assert writing["ok"] is True
    wctx = workspace / "installed-wctx.json"
    wctx.write_text(json.dumps(writing, ensure_ascii=False), encoding="utf-8")
    outline = _installed(
        venv_python,
        env,
        tmp_path,
        ["writing", "outline-export", "--workspace", str(workspace), "--context", str(wctx)],
    )
    assert outline["ok"] is True
    octx = workspace / "installed-octx.json"
    odoc = workspace / "installed-odoc.json"
    octx.write_text(json.dumps(outline, ensure_ascii=False), encoding="utf-8")
    odoc.write_text(json.dumps(_outline_document(writing), ensure_ascii=False), encoding="utf-8")
    created = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "writing",
            "outline-import",
            "--workspace",
            str(workspace),
            "--context",
            str(octx),
            "--document",
            str(odoc),
        ],
    )
    assert created["ok"] is True
    project_id = created["project_id"]
    exported_section = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "writing",
            "section-export",
            "--workspace",
            str(workspace),
            "--project-id",
            project_id,
            "--section-id",
            "s1",
        ],
    )
    assert exported_section["ok"] is True
    sctx = workspace / "installed-sctx.json"
    sdoc = workspace / "installed-sdoc.json"
    sctx.write_text(json.dumps(exported_section, ensure_ascii=False), encoding="utf-8")
    sdoc.write_text(
        json.dumps(
            _section_document(project_id, "s1", writing["evidence"][0]["chunk_id"], "安装环境方法段。"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    written = _installed(
        venv_python,
        env,
        tmp_path,
        [
            "writing",
            "section-import",
            "--workspace",
            str(workspace),
            "--context",
            str(sctx),
            "--document",
            str(sdoc),
        ],
    )
    assert written["ok"] is True
    assert written["progress"]["complete"] is False

    planned = _installed(
        venv_python,
        env,
        tmp_path,
        ["knowledge", "batch-plan", "--workspace", str(workspace), "--paper-id", alpha["paper_id"]],
    )
    assert planned["ok"] is True
    plan_id = planned["plan_id"]
    for index in range(planned["batch_count"]):
        exported = _installed(
            venv_python,
            env,
            tmp_path,
            [
                "knowledge",
                "batch-export",
                "--workspace",
                str(workspace),
                "--plan-id",
                plan_id,
                "--batch-index",
                str(index),
            ],
        )
        chunk = exported["context"]["evidence"][0]["chunk_id"]
        bctx = workspace / f"installed-batch-{index}.json"
        bdoc = workspace / f"installed-batch-{index}-doc.json"
        bctx.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")
        bdoc.write_text(json.dumps(_knowledge_document(alpha["paper_id"], chunk), ensure_ascii=False), encoding="utf-8")
        imported = _installed(
            venv_python,
            env,
            tmp_path,
            [
                "knowledge",
                "batch-import",
                "--workspace",
                str(workspace),
                "--context",
                str(bctx),
                "--document",
                str(bdoc),
            ],
        )
        assert imported["ok"] is True
        merge = _installed(
            venv_python,
            env,
            tmp_path,
            ["knowledge", "merge-export", "--workspace", str(workspace), "--plan-id", plan_id],
        )
        mctx = workspace / f"installed-merge-{index}.json"
        mdoc = workspace / f"installed-merge-{index}-doc.json"
        mctx.write_text(json.dumps(merge, ensure_ascii=False), encoding="utf-8")
        mdoc.write_text(json.dumps(_merge_document(alpha["paper_id"], merge), ensure_ascii=False), encoding="utf-8")
        merged = _installed(
            venv_python,
            env,
            tmp_path,
            [
                "knowledge",
                "merge-import",
                "--workspace",
                str(workspace),
                "--context",
                str(mctx),
                "--document",
                str(mdoc),
            ],
        )
        assert merged["ok"] is True
    finalized = _installed(
        venv_python,
        env,
        tmp_path,
        ["knowledge", "finalize", "--workspace", str(workspace), "--plan-id", plan_id],
    )
    assert finalized["ok"] is True
    listed = _installed(venv_python, env, tmp_path, ["knowledge", "list", "--workspace", str(workspace)])
    assert listed["heads"][alpha["paper_id"]] == finalized["record_id"]

    archive = tmp_path / ".work" / "installed-backups" / "ws.zip"
    archive.parent.mkdir(parents=True)
    created_backup = _installed(
        venv_python,
        env,
        tmp_path,
        ["backup", "create", "--workspace", str(workspace), "--output", str(archive)],
    )
    assert created_backup["ok"] is True
    verified = _installed(venv_python, env, tmp_path, ["backup", "verify", "--archive", str(archive)])
    assert verified["ok"] is True
    dest = tmp_path / ".work" / "installed-restored"
    restored = _installed(
        venv_python,
        env,
        tmp_path,
        ["backup", "restore", "--archive", str(archive), "--destination", str(dest)],
    )
    assert restored["ok"] is True
    history = _installed(
        venv_python,
        env,
        tmp_path,
        ["writing", "history", "--workspace", str(dest), "--project-id", project_id],
    )
    assert history["ok"] is True
    assert {row["source_status"] for row in history["revisions"]} == {"historical"}
