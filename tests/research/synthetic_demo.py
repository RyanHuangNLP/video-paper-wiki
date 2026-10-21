"""Placeholder-free synthetic demo: manual PDF → publication → QA → Markdown.

This is a fixture-Vault demonstration. It does not mutate a real Vault, run
vpwiki-admin, download models, or treat synthetic answers as factual review.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
EXECUTOR = ROOT / "operator" / "parser_executor" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(EXECUTOR) not in sys.path:
    sys.path.insert(0, str(EXECUTOR))

from tests.research.conftest import SESSION, TEXT, UPSTREAM, fixture_converter, write_pdf
from tests.research.pipeline_support import (
    apply_inspected_publication,
    bootstrap_genesis,
    capture_pdf_bytes,
)
from tests.research.test_pipeline import _patch_runtime, _unsealed_proposal
from tests.support import make_checkout
from video_paper_wiki_parser_executor.exporter import export_run, set_test_converter
from video_paper_wiki_research.catalog_index import build_published_catalog
from video_paper_wiki_research.parser_profile import create_profile
from video_paper_wiki_research.publication_bridge import bridge_publication
from video_paper_wiki_research.source_admission import admit_source
from video_paper_wiki_research.storage import open_research_session


PYTHON = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python")
ENV = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join((str(SRC), str(EXECUTOR))),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def _run(argv: list[str], *, cwd: Path) -> dict:
    print("+", " ".join(argv), flush=True)
    result = subprocess.run(argv, cwd=cwd, env=ENV, capture_output=True, text=True, check=False)
    sys.stdout.write(result.stdout)
    sys.stdout.flush()
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else {}


def _research(args: list[str], *, cwd: Path) -> dict:
    return _run([str(PYTHON), "-m", "video_paper_wiki_research", *args], cwd=cwd)


def main() -> int:
    import tempfile

    import pytest

    root = Path(tempfile.mkdtemp(prefix="vpwiki-demo-")).resolve()
    checkout = (root / "checkout")
    checkout.mkdir()
    checkout = checkout.resolve()
    make_checkout(checkout)
    os.chdir(checkout)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(checkout)
    _patch_runtime(monkeypatch)
    models = root / "models"
    (models / "layout").mkdir(parents=True)
    (models / "layout" / "weights.bin").write_bytes(b"synthetic-model-bytes")
    (models / "config.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    pdf_path = write_pdf(checkout / "paper.pdf").resolve()
    intake = _research(["pdf", "intake", "--pdf", str(pdf_path), "--session", SESSION], cwd=checkout)
    assert intake["data"]["capture_authorized"] is False
    assert intake["data"]["receipt_backed"] is False
    assert intake["data"]["published"] is False
    intake_path = Path(intake["data"]["path"])
    with open_research_session(SESSION) as session:
        profile = create_profile(session, models, version_loader=lambda: ("2.117.0", "2.92.0"))
        profile_path = Path(profile["path"])
        set_test_converter(fixture_converter())
        try:
            exported = export_run(
                session,
                intake_path=intake_path,
                profile_path=profile_path,
                artifacts_path=models,
                run_id="run-1",
            )
        finally:
            set_test_converter(None)
        run_dir = checkout / Path(exported["paths"]["document_json"]).parent
    context = _research(
        [
            "pdf",
            "context",
            "--intake",
            str(intake_path),
            "--profile",
            str(profile_path),
            "--run",
            str(run_dir),
            "--upstream-root",
            str(UPSTREAM),
            "--session",
            SESSION,
        ],
        cwd=checkout,
    )
    assert context["data"]["capture_authorized"] is False
    assert context["data"]["published"] is False
    context_path = Path(context["data"]["path"])
    proposal_path = checkout / "proposal.unsealed.json"
    proposal_path.write_bytes(
        json.dumps(_unsealed_proposal(context_path), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    analyzed = _research(
        [
            "pdf",
            "analyze",
            "--context",
            str(context_path),
            "--proposal",
            str(proposal_path),
            "--upstream-root",
            str(UPSTREAM),
            "--session",
            SESSION,
        ],
        cwd=checkout,
    )
    assert analyzed["data"]["published"] is False
    vault = root / "vault"
    bootstrap_genesis(checkout, vault, root)
    captured = capture_pdf_bytes(checkout, vault, pdf_path.read_bytes(), batch_id="research-capture")
    intake_doc = json.loads(intake_path.read_text(encoding="utf-8"))
    admitted = admit_source(
        intake=intake_doc,
        capture_authority=captured["authority"],
        vault_root=vault,
        upstream_root=UPSTREAM,
        batch_id="research-admit",
        operation_id="research-admit",
    )
    apply_inspected_publication(
        checkout,
        vault,
        request_path=admitted["request_path"],
        operation_id="research-admit",
        batch_id="research-admit",
    )
    bridged = bridge_publication(
        intake=intake_doc,
        capture_bind=captured["bound"],
        captured_pdf=vault / admitted["stored_path"],
        document_json=run_dir / "document.json",
        parser_config=run_dir / "parser-config.json",
        model_manifest=run_dir / "model-manifest.json",
        run_manifest=run_dir / "run.json",
        legacy_draft=Path(analyzed["data"]["legacy_draft_path"]),
        source_id=admitted["source_id"],
        vault_root=vault,
        package_batch_id="research-package",
        package_operation_id="research-package",
        paper_batch_id="research-paper",
        paper_operation_id="research-paper",
    )
    apply_inspected_publication(
        checkout,
        vault,
        request_path=bridged["package"]["request_path"],
        operation_id="research-package",
        batch_id="research-package",
    )
    apply_inspected_publication(
        checkout,
        vault,
        request_path=bridged["paper"]["request_path"],
        operation_id="research-paper",
        batch_id="research-paper",
    )
    catalog = build_published_catalog(vault_root=vault, upstream_root=UPSTREAM)
    paper_id = bridged["paper"]["paper_id"]
    qa_context = _research(
        [
            "qa",
            "export",
            "--question",
            TEXT,
            "--vault-root",
            str(vault),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            catalog["config_path"],
        ],
        cwd=checkout,
    )
    context_file = checkout / "qa-context.json"
    answer_file = checkout / "qa-answer.json"
    unit = qa_context["evidence"][0]
    context_file.write_text(json.dumps(qa_context, ensure_ascii=False), encoding="utf-8")
    answer_file.write_text(
        json.dumps(
            {
                "text": f"SYNTHETIC FIXTURE ANSWER citing {unit['paper_id']}.",
                "citations": [
                    {
                        "paper_id": unit["paper_id"],
                        "evidence_unit_id": unit["evidence_unit_id"],
                        "locator_fingerprint": unit["locator_fingerprint"],
                    }
                ],
                "synthetic_fixture": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    qa_imported = _research(
        ["qa", "import", "--context", str(context_file), "--answer", str(answer_file)],
        cwd=checkout,
    )
    writing_context = _research(
        [
            "writing",
            "export",
            "--topic",
            TEXT,
            "--requirements",
            "Write a short editable overview with sources.",
            "--paper-id",
            paper_id,
            "--vault-root",
            str(vault),
            "--upstream-root",
            str(UPSTREAM),
            "--config",
            catalog["config_path"],
        ],
        cwd=checkout,
    )
    writing_file = checkout / "writing-context.json"
    draft_file = checkout / "writing-draft.json"
    writing_file.write_text(json.dumps(writing_context, ensure_ascii=False), encoding="utf-8")
    wunit = writing_context["evidence"][0]
    draft_file.write_text(
        json.dumps(
            {
                "markdown": f"SYNTHETIC FIXTURE DRAFT for {TEXT}.",
                "citations": [
                    {
                        "paper_id": wunit["paper_id"],
                        "evidence_unit_id": wunit["evidence_unit_id"],
                    }
                ],
                "synthetic_fixture": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    written = _research(
        ["writing", "import", "--context", str(writing_file), "--draft", str(draft_file)],
        cwd=checkout,
    )
    print("DEMO_OK", flush=True)
    print("paper_id", paper_id, flush=True)
    print("qa_ok", qa_imported.get("ok"), flush=True)
    print("writing_ok", written.get("ok"), flush=True)
    print("markdown_has_references", "## 参考文献" in (written.get("markdown") or ""), flush=True)
    monkeypatch.undo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
