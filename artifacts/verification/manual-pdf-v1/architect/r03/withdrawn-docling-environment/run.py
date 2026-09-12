#!/usr/bin/env python3
"""Reusable isolated environment for manual-PDF development on this machine."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENVROOT = ROOT / ".work/environments/manual-pdf"
PYTHON = ENVROOT / "bin/python"
CACHE = ROOT / ".work/cache/uv"
MODELS = ROOT / ".work/models/docling-2.117.0"
UV = shutil.which("uv") or str(Path.home() / ".hermes/bin/uv")


def environment(*, offline: bool = True) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env.update({
        "PATH": str(ENVROOT / "bin") + os.pathsep + str(Path(UV).parent) + os.pathsep + env.get("PATH", ""),
        "UV_CACHE_DIR": str(CACHE), "UV_PYTHON_DOWNLOADS": "never",
        "UV_LINK_MODE": "copy", "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TMPDIR": "/private/tmp", "HF_HOME": str(ROOT / ".work/cache/huggingface"),
        "HF_HUB_DISABLE_TELEMETRY": "1", "DOCLING_DISABLE_TELEMETRY": "1",
    })
    for key in ("UV_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        if offline:
            env[key] = "1"
        else:
            env.pop(key, None)
    return env


def run(argv: list[str | Path], *, cwd: Path = ROOT, offline: bool = True) -> None:
    print("+ " + " ".join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=cwd, env=environment(offline=offline), check=True)


def preflight() -> None:
    if not PYTHON.is_file():
        raise SystemExit("Missing isolated environment; run setup first.")
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vp.env.", dir="/private/tmp") as tmp:
        probe = Path(tmp) / "socket"
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(probe))
        except PermissionError as exc:
            raise SystemExit("This sandbox forbids Unix sockets. Run this same test command in a normal local terminal or with approved execution permissions; tests were not started.") from exc
    with tempfile.TemporaryFile(dir=CACHE):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("setup", help="Network-enabled installation from the checked-in hash lock")
    setup.add_argument("--python", default=str(ROOT / ".venv/bin/python"))
    build = sub.add_parser("build", help="Build both candidate wheels from an explicit checkout and install offline")
    build.add_argument("--source", type=Path, required=True)
    test = sub.add_parser("test", help="Preflight and run a fresh complete suite against an explicit checkout")
    test.add_argument("--source", type=Path, required=True)
    sub.add_parser("check", help="Check dependencies, runtime API, model inventory and local test permissions")
    for name in ("parser", "research"):
        command = sub.add_parser(name)
        command.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "setup":
        if not PYTHON.is_file():
            run([UV, "venv", "--no-project", "--python", args.python, ENVROOT], offline=False)
        run([UV, "pip", "sync", "--python", PYTHON, "--require-hashes", HERE / "requirements.lock"], offline=False)
        run([UV, "pip", "check", "--python", PYTHON])
    elif args.action == "build":
        source = args.source.resolve(strict=True)
        output = Path(tempfile.mkdtemp(prefix="vp.build.", dir="/private/tmp"))
        staging = output / "source"
        staging.mkdir()
        for relative in ("pyproject.toml", "src", "docs/seed", "schemas", "taxonomy", "catalog", "operator/parser_executor"):
            src, dst = source / relative, staging / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".venv", "dist", "*.egg-info"))
            else:
                shutil.copy2(src, dst)
        wheels = output / "wheels"
        for project in (staging, staging / "operator/parser_executor"):
            run([PYTHON, "-m", "hatchling", "build", "-t", "wheel", "-d", wheels], cwd=project)
        files = sorted(wheels.glob("*.whl"))
        if len(files) != 2:
            raise SystemExit("Expected exactly two wheels.")
        run([UV, "pip", "install", "--python", PYTHON, "--no-deps", "--reinstall", *files])
        (ENVROOT / "candidate.json").write_text(json.dumps({"source": str(source), "wheels": list(map(str, files))}, indent=2) + "\n")
    elif args.action == "test":
        preflight()
        output = Path(tempfile.mkdtemp(prefix="vp.test.", dir="/private/tmp"))
        run([PYTHON, "-B", "-m", "pytest", "-q", "--basetemp", output / "p", "-o", "cache_dir=" + str(output / "cache")], cwd=args.source.resolve(strict=True))
    elif args.action == "check":
        preflight()
        run([UV, "pip", "check", "--python", PYTHON])
        run([PYTHON, "-I", "-c", "from video_paper_wiki_research.parser_profile import installed_versions, inventory_models; from docling.document_converter import DocumentConverter; from pathlib import Path; import sys; print('runtime:', installed_versions()); f,n,_=inventory_models(Path(sys.argv[1])); print('model files:',len(f),'bytes:',n)", MODELS])
    else:
        extra = args.args[1:] if args.args[:1] == ["--"] else args.args
        exe = ENVROOT / "bin" / ("vpwiki-parser" if args.action == "parser" else "vpwiki-research")
        run([exe, *extra])


if __name__ == "__main__":
    main()
