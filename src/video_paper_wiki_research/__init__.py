"""Manual PDF research intake, source admission, QA, and writing. Zero network."""

from video_paper_wiki_research.catalog_index import build_published_catalog
from video_paper_wiki_research.manual_pdf import intake_pdf, plan_handoff
from video_paper_wiki_research.publication_bridge import (
    bind_capture_operation,
    bridge_publication,
    package_extraction_run,
    prepare_paper_concept_publication,
)
from video_paper_wiki_research.qa import export_from_question, import_and_check
from video_paper_wiki_research.source_admission import admit_source
from video_paper_wiki_research.source_context import analyze_proposal, build_context
from video_paper_wiki_research.writing import export_from_request, import_and_render

__version__ = "0.1.0"

__all__ = [
    "admit_source",
    "analyze_proposal",
    "bind_capture_operation",
    "bridge_publication",
    "build_context",
    "build_published_catalog",
    "export_from_question",
    "export_from_request",
    "import_and_check",
    "import_and_render",
    "intake_pdf",
    "package_extraction_run",
    "plan_handoff",
    "prepare_paper_concept_publication",
]
