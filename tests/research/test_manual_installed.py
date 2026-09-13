from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tests.research.conftest import ROOT
from tests.support import make_checkout, pdf_bytes


def test_pyproject_exposes_research_script_not_admin() -> None:
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts["vpwiki"] == "video_paper_wiki.cli:main"
    assert scripts["vpwiki-research"] == "video_paper_wiki_research.cli:main"
    assert "vpwiki-admin" not in scripts
    parser = tomllib.loads((ROOT / "operator" / "parser_executor" / "pyproject.toml").read_text(encoding="utf-8"))
    assert parser["project"]["scripts"]["vpwiki-parser"] == "video_paper_wiki_parser_executor.cli:main"
    assert parser["project"]["dependencies"] == []
    assert all("docling" not in item for item in data["project"]["dependencies"])
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "src/video_paper_wiki_research" in wheel["packages"]


def _install_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest)


def test_installed_layout_exposes_entrypoints_and_resources(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    lib = prefix / "lib"
    lib.mkdir(parents=True)
    _install_tree(ROOT / "src" / "video_paper_wiki", lib / "video_paper_wiki")
    _install_tree(ROOT / "src" / "video_paper_wiki_research", lib / "video_paper_wiki_research")
    _install_tree(
        ROOT / "operator" / "parser_executor" / "src" / "video_paper_wiki_parser_executor",
        lib / "video_paper_wiki_parser_executor",
    )
    locked = []
    for key in ("purelib", "platlib"):
        candidate = Path(sysconfig.get_paths()[key]).resolve()
        if candidate not in locked:
            locked.append(candidate)
    (lib / "vpwiki-locked-dependencies.pth").write_text(
        "".join(str(path) + "\n" for path in locked), encoding="utf-8"
    )
    bin_dir = prefix / "bin"
    bin_dir.mkdir()
    research = bin_dir / "vpwiki-research"
    parser = bin_dir / "vpwiki-parser"
    research.write_text(
        "#!" + sys.executable + "\nfrom video_paper_wiki_research.cli import main\nimport sys\nsys.exit(main())\n",
        encoding="utf-8",
    )
    parser.write_text(
        "#!" + sys.executable + "\nfrom video_paper_wiki_parser_executor.cli import main\nimport sys\nsys.exit(main())\n",
        encoding="utf-8",
    )
    research.chmod(stat.S_IRWXU)
    parser.chmod(stat.S_IRWXU)
    env = {
        "PATH": str(bin_dir) + ":/usr/bin:/bin",
        "PYTHONPATH": str(lib),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(tmp_path / "home"),
    }
    (tmp_path / "home").mkdir()
    origin = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, video_paper_wiki_research, importlib.resources as r; "
            "print(json.dumps({"
            "'module': video_paper_wiki_research.__file__, "
            "'schema': r.files('video_paper_wiki_research').joinpath('schemas/manual-pdf-intake.v1.schema.json').is_file(), "
            "'prompt': r.files('video_paper_wiki_research').joinpath('prompts/paper-analysis-v1.md').is_file()"
            "}))",
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    payload = json.loads(origin.stdout)
    assert Path(payload["module"]).resolve().is_relative_to(lib.resolve())
    assert payload["schema"] is True
    assert payload["prompt"] is True
    usage = subprocess.run(
        [str(research), "pdf", "intake"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert usage.returncode == 2
    assert json.loads(usage.stdout)["error"]["code"] == "USAGE"
    parser_usage = subprocess.run(
        [str(parser), "export"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert parser_usage.returncode == 2
    assert json.loads(parser_usage.stdout)["error"]["code"] == "USAGE"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    pdf = checkout / "paper.pdf"
    pdf.write_bytes(pdf_bytes())
    intake = subprocess.run(
        [str(research), "pdf", "intake", "--pdf", str(pdf), "--session", "installed"],
        cwd=checkout,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert intake.returncode == 0, intake.stdout + intake.stderr
    body = json.loads(intake.stdout)
    assert body["ok"] is True
    assert body["data"]["next_action"] == "awaiting_parser_profile"
    assert body["data"]["published"] is False
    assert (checkout / ".work" / "blobs" / body["data"]["pdf_sha256"]).is_file()
