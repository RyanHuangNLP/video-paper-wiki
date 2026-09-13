"""Real isolated fixed-upstream behavior; missing/dirty pins fail, never download."""
from functools import partial

import pytest

from tests.upstream._transaction_fixture import (
    UP, Runner, dump, negative, positive, snapshot, stable_source,
    verify_sources, wrong_source_id,
)


@pytest.fixture(scope="module")
def upstream_run(tmp_path_factory):
    # Use README's short real temporary basetemp, not a long symlinked /tmp.
    out = tmp_path_factory.mktemp("up").resolve()
    before = verify_sources(out)
    runner = Runner(out)
    try:
        yield runner
    finally:
        after = snapshot(UP)
        dump(out / "source-after.json", after)
        assert before == after, "Pinned upstream source inventory changed during fixture"


@pytest.fixture(scope="module")
def positive_vault(upstream_run):
    positive(upstream_run, partial(stable_source, upstream_run))
    return upstream_run


def test_capture_publication_lint_and_retrieval(positive_vault):
    assert (positive_vault.out / "positive-results.json").is_file()


def test_managed_expansion_cannot_preserve_head_last(upstream_run):
    negative(upstream_run)


def test_canonical_source_identity_is_enforced(positive_vault):
    wrong_source_id(positive_vault)
