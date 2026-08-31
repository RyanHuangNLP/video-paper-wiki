from __future__ import annotations

import hashlib
import json
from pathlib import Path

PYPROJECT = '[project]\nname = "video-paper-wiki"\n'
ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"


def make_checkout(path: Path) -> Path:
    git = path / ".git"
    if not git.exists():
        git.mkdir()
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        pyproject.write_text(PYPROJECT, encoding="utf-8")
    return path


def plant_blob(root: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    dest = Path(root)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / digest
    path.write_bytes(data)
    return digest


def work_prepared(root: Path, batch_id: str, sha256: str) -> Path:
    return root / ".work" / batch_id / "prepared" / f"{sha256}.blob"


def work_draft(root: Path, batch_id: str) -> Path:
    return root / ".work" / batch_id / "draft" / "paper-analysis-draft.v1.json"


def work_review(root: Path, batch_id: str) -> Path:
    return root / ".work" / batch_id / "review" / "paper.md"


def write_catalog_paper_note(root: Path, paper_id: str, title: str | None = None) -> Path:
    from video_paper_wiki.notes import paper_note_link_suffix, render_paper_copy_markdown
    from video_paper_wiki.parse.title import catalog_title_for_paper_id

    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = paper_id
    document["title"] = title or catalog_title_for_paper_id(paper_id) or paper_id
    text = render_paper_copy_markdown(document) + paper_note_link_suffix(paper_id)
    path = root / "papers" / f"{paper_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
