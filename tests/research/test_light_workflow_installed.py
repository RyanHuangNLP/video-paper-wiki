"""Isolated installed-wheel checks for the lightweight workflow CLI.

Official T4 verification builds one fresh offline wheel, or passes that
wheel through LW2_INSTALLED_WHEEL. The wheel is installed into a new
virtual environment. Assertions use that environment's interpreter with
``-I`` and no PYTHONPATH, and that environment's ``vpwiki-research``
console script. Missing console entry is a failure.

Runtime and cache locations are taken from the current interpreter or
explicit environment variables (LW2_PYTHON, LW2_UV, LW2_UV_CACHE /
UV_CACHE_DIR). A missing user-specific directory does not skip the check.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.research.conftest import ROOT


OWNED_CLI = Path("src/video_paper_wiki_research/cli.py")
CHECKOUT_SCHEMAS = Path("schemas")
NEW_MODULE_PATHS = (
    Path("src/video_paper_wiki_research/cli.py"),
    Path("src/video_paper_wiki_research/light_pdf.py"),
    Path("src/video_paper_wiki_research/light_workspace.py"),
    Path("src/video_paper_wiki_research/light_index.py"),
    Path("src/video_paper_wiki_research/light_context.py"),
    Path("src/video_paper_wiki_research/light_workflow.py"),
)
_HATCHLING_PKGS = (
    "hatchling",
    "packaging",
    "pathspec",
    "pluggy",
    "tomlkit",
    "trove_classifiers",
)
_RUNTIME_DISTS = (
    "attrs",
    "jsonschema",
    "jsonschema_specifications",
    "pypdf",
    "referencing",
    "rpds-py",
)
# Match referencing's conditional dependency in the locked default environment.
if sys.version_info < (3, 13):
    _RUNTIME_DISTS += ("typing-extensions",)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_python() -> Path:
    raw = os.environ.get("LW2_PYTHON", "").strip()
    candidate = Path(raw) if raw else Path(sys.executable)
    if not candidate.exists():
        pytest.fail(f"locked runtime is not a file: {candidate}")
    return candidate


def _uv_program() -> Path | None:
    raw = os.environ.get("LW2_UV", "").strip()
    if raw:
        path = Path(raw)
        if not path.is_file():
            pytest.fail(f"LW2_UV is not a file: {path}")
        return path.resolve()
    found = shutil.which("uv")
    return Path(found).resolve() if found else None


def _cache_dir() -> Path | None:
    for key in ("LW2_UV_CACHE", "UV_CACHE_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw)
    return None


def _expected_new_modules() -> list[Path]:
    return [path for path in NEW_MODULE_PATHS if (ROOT / path).is_file()]


def _hatchling_roots(cache: Path) -> list[Path]:
    archive = cache / "archive-v0"
    if not archive.is_dir():
        pytest.fail(f"offline cache has no archive-v0: {cache}")
    found: dict[str, Path] = {}
    for child in archive.iterdir():
        if not child.is_dir():
            continue
        for name in _HATCHLING_PKGS:
            if (child / name).is_dir():
                found[name] = child
    missing = [name for name in _HATCHLING_PKGS if name not in found]
    if missing:
        pytest.fail(f"offline cache is missing hatchling build dependencies: {missing}")
    return [found[name] for name in _HATCHLING_PKGS]


def _run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(Path.home())),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "UV_OFFLINE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
        "GIT_OPTIONAL_LOCKS": "0",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    cache = _cache_dir()
    if cache is not None:
        env["UV_CACHE_DIR"] = str(cache)
    if extra:
        env.update(extra)
    return env


def _build_wheel(python: Path, tmp_path: Path) -> Path:
    preset = os.environ.get("LW2_INSTALLED_WHEEL", "").strip()
    if preset:
        wheel = Path(preset)
        if not wheel.is_file():
            pytest.fail(f"LW2_INSTALLED_WHEEL does not exist: {wheel}")
        return wheel.resolve()

    out_dir = tmp_path / "dist"
    out_dir.mkdir()
    uv = _uv_program()
    if uv is not None:
        built = _run(
            [str(uv), "build", "--offline", "--wheel", "--out-dir", str(out_dir)],
            cwd=ROOT,
            env=_build_env(),
        )
        wheels = sorted(out_dir.glob("*.whl"))
        if built.returncode != 0 or not wheels:
            pytest.fail(
                "offline uv wheel build failed\n"
                f"exit={built.returncode}\nstdout={built.stdout}\nstderr={built.stderr}"
            )
        return wheels[0].resolve()

    cache = _cache_dir()
    if cache is None or not cache.is_dir():
        pytest.fail(
            "cannot build an offline wheel: uv is not on PATH/LW2_UV and "
            "LW2_UV_CACHE/UV_CACHE_DIR is unset or missing"
        )
    roots = _hatchling_roots(cache)
    built = _run(
        [str(python), "-B", "-m", "hatchling", "build", "-t", "wheel", "-d", str(out_dir)],
        cwd=ROOT,
        env=_build_env({"PYTHONPATH": os.pathsep.join(str(path) for path in roots)}),
    )
    wheels = sorted(out_dir.glob("*.whl"))
    if built.returncode != 0 or not wheels:
        pytest.fail(
            "offline hatchling wheel build failed\n"
            f"exit={built.returncode}\nstdout={built.stdout}\nstderr={built.stderr}"
        )
    return wheels[0].resolve()


def _venv_paths(venv: Path) -> tuple[Path, Path]:
    unix_python = venv / "bin" / "python"
    win_python = venv / "Scripts" / "python.exe"
    if unix_python.is_file():
        return unix_python, venv / "bin"
    if win_python.is_file():
        return win_python, venv / "Scripts"
    pytest.fail(f"isolated venv has no python executable: {venv}")


def _create_isolated_venv(python: Path, dest: Path) -> tuple[Path, Path]:
    created = _run([str(python), "-B", "-m", "venv", str(dest)], cwd=dest.parent, env=_build_env())
    if created.returncode != 0:
        pytest.fail(
            "failed to create an isolated venv for the new wheel\n"
            f"exit={created.returncode}\nstdout={created.stdout}\nstderr={created.stderr}"
        )
    venv_python, bindir = _venv_paths(dest)
    probe = _run([str(venv_python), "-I", "-B", "-m", "pip", "--version"], cwd=dest, env=_build_env())
    if probe.returncode != 0:
        pytest.fail(
            "isolated venv has no pip; cannot install the new wheel\n"
            f"stdout={probe.stdout}\nstderr={probe.stderr}"
        )
    return venv_python, bindir


def _purelib(python: Path, *, isolated: bool, cwd: Path) -> Path:
    argv = [str(python), "-B", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"]
    if isolated:
        argv.insert(1, "-I")
    result = _run(argv, cwd=cwd, env=_build_env())
    path = Path(result.stdout.strip()) if result.returncode == 0 else Path()
    if result.returncode != 0 or not path.is_dir():
        pytest.fail(
            "could not resolve site-packages\n"
            f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return path.resolve()


def _seed_locked_runtime_deps(venv_site: Path) -> None:
    from importlib.metadata import PackageNotFoundError, distribution

    site = venv_site.resolve()
    for name in _RUNTIME_DISTS:
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            pytest.fail(f"locked runtime is missing declared wheel dependency: {name}")
        records = list(dist.files or [])
        if not records:
            pytest.fail(f"locked runtime distribution has no recorded files: {name}")
        copied = 0
        for rec in records:
            src = Path(dist.locate_file(rec))
            if not src.is_file():
                continue
            dest = (site / str(rec)).resolve()
            try:
                dest.relative_to(site)
            except ValueError:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            copied += 1
        if copied == 0:
            pytest.fail(f"locked runtime distribution copied no files: {name}")


def _install_wheel(venv_python: Path, wheel: Path, cwd: Path) -> None:
    installed = _run(
        [
            str(venv_python),
            "-I",
            "-B",
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(wheel),
        ],
        cwd=cwd,
        env=_build_env(),
    )
    if installed.returncode != 0:
        pytest.fail(
            "offline wheel install into isolated venv failed\n"
            f"stdout={installed.stdout}\nstderr={installed.stderr}"
        )


def _isolated_run_env(venv: Path, bindir: Path) -> dict[str, str]:
    return {
        "PATH": f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "VIRTUAL_ENV": str(venv),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def test_fresh_wheel_exposes_equivalent_entries_and_workflow_help(tmp_path: Path) -> None:
    python = _runtime_python()
    wheel = _build_wheel(python, tmp_path)
    venv = tmp_path / "isolated-venv"
    venv_python, bindir = _create_isolated_venv(python, venv)
    _install_wheel(venv_python, wheel, tmp_path)
    env = _isolated_run_env(venv, bindir)
    expected = _expected_new_modules()
    assert expected, "checkout has no lightweight modules to verify"
    venv_site = _purelib(venv_python, isolated=True, cwd=tmp_path)
    installed_pkg = venv_site / "video_paper_wiki_research"
    for path in expected:
        installed = installed_pkg / path.name
        assert installed.is_file(), installed
        assert _sha256(installed) == _sha256(ROOT / path)
    _seed_locked_runtime_deps(venv_site)

    inspect = _run(
        [
            str(venv_python),
            "-I",
            "-B",
            "-c",
            (
                "import hashlib, json, sys\n"
                "from importlib import import_module\n"
                "from pathlib import Path\n"
                "names = json.loads(sys.argv[1])\n"
                "payload = {'executable': sys.executable, 'prefix': sys.prefix, 'modules': {}}\n"
                "for name in names:\n"
                "    mod = import_module(name)\n"
                "    path = Path(mod.__file__)\n"
                "    payload['modules'][name] = {\n"
                "        'file': str(path),\n"
                "        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),\n"
                "    }\n"
                "print(json.dumps(payload))\n"
            ),
            json.dumps(
                [
                    "video_paper_wiki_research." + path.stem
                    if path.stem != "cli"
                    else "video_paper_wiki_research.cli"
                    for path in expected
                ]
            ),
        ],
        cwd=tmp_path,
        env=env,
    )
    assert inspect.returncode == 0, inspect.stderr
    payload = json.loads(inspect.stdout)
    assert Path(payload["executable"]).resolve() == venv_python.resolve()
    assert Path(payload["prefix"]).resolve() == venv.resolve()

    installed_files: dict[str, Path] = {}
    for path in expected:
        name = "video_paper_wiki_research." + path.stem
        module_info = payload["modules"][name]
        installed = Path(module_info["file"]).resolve()
        installed_files[name] = installed
        assert str(venv.resolve()) in str(installed)
        assert ROOT.resolve() not in installed.parents
        assert "src" not in installed.parts or "site-packages" in installed.parts
        assert module_info["sha256"] == _sha256(ROOT / path)
        assert installed.name == path.name

    site = installed_files["video_paper_wiki_research.cli"].parent.parent
    schema_dir = site / "video_paper_wiki" / "schemas"
    checkout_schema_dir = ROOT / CHECKOUT_SCHEMAS
    checkout_schemas = sorted(path.name for path in checkout_schema_dir.glob("*.schema.json"))
    installed_schemas = sorted(path.name for path in schema_dir.glob("*.schema.json"))
    assert installed_schemas == checkout_schemas
    assert len(installed_schemas) >= 26
    for name in checkout_schemas:
        assert _sha256(schema_dir / name) == _sha256(checkout_schema_dir / name)

    module_help = _run(
        [str(venv_python), "-I", "-B", "-m", "video_paper_wiki_research", "workflow", "prepare"],
        cwd=tmp_path,
        env=env,
    )
    assert module_help.returncode == 2, module_help.stderr
    module_payload = json.loads(module_help.stdout)
    assert module_payload["ok"] is False
    assert module_payload["error"]["code"] == "USAGE"

    script = bindir / "vpwiki-research"
    if not script.is_file():
        script = bindir / "vpwiki-research.exe"
    if not script.is_file():
        pytest.fail(f"console script vpwiki-research is missing from isolated venv: {bindir}")

    script_help = _run([str(script), "workspace", "inspect"], cwd=tmp_path, env=env)
    assert script_help.returncode == 2, script_help.stderr
    script_payload = json.loads(script_help.stdout)
    assert script_payload["ok"] is False
    assert script_payload["error"]["code"] == "USAGE"

    record = tmp_path / "installed-observation.json"
    observation = {
        "wheel": str(wheel),
        "wheel_sha256": _sha256(wheel),
        "runtime_python": str(python),
        "venv_python": str(venv_python),
        "venv": str(venv),
        "observed_executable": payload["executable"],
        "observed_prefix": payload["prefix"],
        "console_script": str(script),
        "modules": payload["modules"],
        "schema_count": len(installed_schemas),
        "schemas": installed_schemas,
    }
    record.write_text(json.dumps(observation, indent=2) + "\n", encoding="utf-8")
    assert json.loads(record.read_text(encoding="utf-8"))["schema_count"] == len(checkout_schemas)
    assert OWNED_CLI.as_posix()
