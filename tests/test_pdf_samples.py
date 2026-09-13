from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from pypdf import PdfReader
import pytest

from tests.pdf_samples import sample_pdf_bytes, sample_pdf_path


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,size,digest,pages,title,text",
    [
        ("tiny", 674, "c37df90f89d97fd1e575ee894c8fce6c2a979b2de76332a20105f1af70d8c7b9",
         1, "Tiny VPKB paper", ["Tiny VPKB paper"]),
        ("sectioned", 1206, "03645f6fdd81c46f7377ab28602aa070e51109c0c95500f06496d07de1badc4b",
         2, "Sectioned VPKB Paper", ["Abstract", "1 Introduction", "2. Method",
         "This abstract sentence is the conclusion claim.",
         "We train a diffusion transformer on video latents."]),
    ],
)
def test_samples_preserve_historical_bytes_and_parser_content(name, size, digest, pages, title, text):
    data = sample_pdf_bytes(name)
    assert len(data) == size
    assert hashlib.sha256(data).hexdigest() == digest
    reader = PdfReader(BytesIO(data))
    assert len(reader.pages) == pages
    assert reader.metadata.title == title
    extracted = "\n".join(page.extract_text() for page in reader.pages)
    assert all(part in extracted for part in text)
    path = sample_pdf_path(name)
    assert path == path.resolve()
    assert not path.is_relative_to(ROOT)
    assert path.parent.parent == Path("/tmp").resolve()
    assert path.read_bytes() == data
    assert sample_pdf_path(name) == path


@pytest.mark.parametrize("name", ["", "tiny.pdf", "../tiny", "/tmp/tiny", "unknown"])
def test_unknown_sample_names_are_rejected(name):
    with pytest.raises(ValueError, match="unknown PDF sample"):
        sample_pdf_path(name)


def test_sample_processes_have_separate_directories_and_clean_up():
    code = """
import json
from tests.pdf_samples import sample_pdf_path
tiny = sample_pdf_path('tiny')
sectioned = sample_pdf_path('sectioned')
print(json.dumps({'tiny': str(tiny), 'sectioned': str(sectioned),
                  'both_exist': tiny.is_file() and sectioned.is_file()}))
"""
    roots = []
    for _ in range(2):
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        observation = json.loads(result.stdout)
        assert observation["both_exist"] is True
        tiny, sectioned = Path(observation["tiny"]), Path(observation["sectioned"])
        assert tiny != sectioned and tiny.parent == sectioned.parent
        assert not tiny.parent.exists(), "normal process exit must clean up both samples"
        roots.append(tiny.parent)
    assert roots[0] != roots[1]


@pytest.mark.parametrize("name", ["paper.pdf", "paper.PDF", "nested/paper.pDf", "nested space/line\nbreak.PdF"])
def test_pdf_ignore_rule_covers_case_and_nested_paths(name):
    result = subprocess.run(["git", "check-ignore", "--no-index", "-q", "--", name], cwd=ROOT)
    assert result.returncode == 0


def _workflow_pdf_guard() -> str:
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    match = re.search(r"      - name: Reject tracked PDF files\n        run: \|\n((?:          .*\n)+)", workflow)
    assert match, "the tracked-PDF guard must remain in the Tests workflow"
    assert workflow.index("name: Check out source") < match.start()
    assert match.start() < workflow.index("name: Set up uv and select Python")
    return "\n".join(line[10:] for line in match.group(1).splitlines())


@pytest.mark.parametrize("tracked", [None, "paper.pdf", "paper.PDF", "nested/space and\nline.pDf"])
def test_ci_guard_rejects_force_added_pdfs_but_allows_untracked_samples(tmp_path, tracked):
    # Only this disposable repository is mutated. No PDF enters the project index.
    env = {key: value for key, value in os.environ.items()
           if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}}
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], env=env, check=True)
    (tmp_path / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    (tmp_path / "guide.md").write_text("test repository\n")
    (tmp_path / "untracked.PdF").write_bytes(b"synthetic untracked placeholder")
    subprocess.run(["git", "add", "--", ".gitignore", "guide.md"], cwd=tmp_path, env=env, check=True)
    if tracked is not None:
        path = tmp_path / tracked
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic tracked placeholder")
        subprocess.run(["git", "add", "--force", "--", tracked], cwd=tmp_path, env=env, check=True)
    result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", _workflow_pdf_guard()],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == (0 if tracked is None else 1), result.stderr
    if tracked is not None:
        assert "Tracked PDF files are forbidden:" in result.stderr
        assert repr(tracked) in result.stderr
