"""Synthetic text and approval fixtures; never evidence of a human decision."""
from __future__ import annotations

import json
from pathlib import Path

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source_contracts import APPROVAL, digest, sha
from video_paper_wiki_research.formal_source import plan_markdown_source, prepare_markdown_source
from video_paper_wiki_research.light_index import _locate_pages

LIGHT_ID = "sha256:" + "a" * 64


def light_source(checkout: Path, *, text: str = "A temporal transformer predicts 视频 frames.\n第二行 evidence.") -> tuple[Path, Path, Path]:
    workspace = checkout / ".work" / "light-library"
    directory = workspace / "papers" / ("a" * 64)
    directory.mkdir(parents=True)
    payload = ('# Test paper\n\n<a id="page-1"></a>\n\n## PDF 第 1 页\n\n' + text + "\n\n").encode("utf-8")
    pages = _locate_pages(payload.decode("utf-8"), page_count=1)
    metadata = {"schema": "video-paper-wiki.light-paper.v1", "paper_id": LIGHT_ID, "title": "Test paper",
                "source": {"sha256": "a" * 64, "original_path": "/test-only/original.pdf"},
                "page_count": 1, "document": {"path": f'papers/{"a" * 64}/source.md', "sha256": sha(payload)},
                "pages": [{k: v for k, v in row.items() if k != "text"} for row in pages]}
    md, meta = directory / "source.md", directory / "source.json"
    md.write_bytes(payload)
    meta.write_bytes(canonicalize(metadata))
    return workspace, md, meta


def approval_fixture(plan: dict) -> dict:
    return {"schema": APPROVAL, "plan_sha256": digest(plan), "batch_id": plan["batch_id"],
            "paper_id": plan["observation"]["paper_id"],
            "markdown_sha256": plan["observation"]["markdown"]["sha256"]}


def prepared_source(checkout: Path, *, batch: str = "md-capture") -> tuple[dict, dict, bytes]:
    workspace, md, meta = light_source(checkout)
    planned = plan_markdown_source(workspace_root=workspace, paper_id=LIGHT_ID, batch_id=batch)
    plan = json.loads(Path(planned["plan_path"]).read_bytes())
    approval = checkout / ".work" / "fixture-approval.json"
    approval.write_bytes(canonicalize(approval_fixture(plan)))
    prepared = prepare_markdown_source(plan=planned["plan_path"], approval_ref=approval)
    return planned, prepared, md.read_bytes()
