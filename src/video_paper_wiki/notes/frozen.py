"""Fail-closed catalog precheck before writing paper copies. No network."""

from __future__ import annotations

from video_paper_wiki.notes.architectures import load_architectures
from video_paper_wiki.notes.associations import load_associations
from video_paper_wiki.notes.code_resources import load_code_urls
from video_paper_wiki.notes.conclusions import load_conclusions
from video_paper_wiki.notes.experiments import load_experiments
from video_paper_wiki.notes.limitations import load_limitations
from video_paper_wiki.notes.methods import load_methods
from video_paper_wiki.notes.questions import load_questions
from video_paper_wiki.notes.training import load_training
from video_paper_wiki.parse.title import catalog_paper_ids

_CATALOG_SOURCE = "engine-mvp.json"


class FrozenSeedMissing(Exception):
    """paper_id is outside the managed catalog, or a required overlay file is missing."""

    def __init__(self, paper_id: str, source: str = _CATALOG_SOURCE) -> None:
        self.paper_id = paper_id
        self.source = source
        super().__init__(
            "paper_id is not in the managed seed catalog or a required overlay is missing"
        )


def require_managed_seed(paper_id: str) -> None:
    """Raise FrozenSeedMissing when *paper_id* is not a catalog paper or overlays cannot load.

    Papers in the catalog but absent from an individual overlay map are allowed
    (empty-then-overlay-if-present). Fail-closed is for ids outside the catalog,
    and for a required overlay JSON that is missing or unreadable.
    """
    wanted = str(paper_id).strip()
    catalog = catalog_paper_ids()
    if not wanted or wanted not in catalog:
        raise FrozenSeedMissing(wanted, _CATALOG_SOURCE)
    overlays = (
        ("engine-mvp-conclusions.json", load_conclusions),
        ("engine-mvp-questions.json", load_questions),
        ("engine-mvp-methods.json", load_methods),
        ("engine-mvp-architectures.json", load_architectures),
        ("engine-mvp-training.json", load_training),
        ("engine-mvp-experiments.json", load_experiments),
        ("engine-mvp-limitations.json", load_limitations),
        ("engine-mvp-associations.json", load_associations),
        ("engine-mvp-code-urls.json", load_code_urls),
    )
    for filename, loader in overlays:
        mapping = loader()
        if mapping is None:
            raise FrozenSeedMissing(wanted, filename)
