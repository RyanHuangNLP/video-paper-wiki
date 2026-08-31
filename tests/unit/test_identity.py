from __future__ import annotations

from collections import OrderedDict

import pytest

from video_paper_wiki.identity import (
    IDENTITY_CONFLICT,
    INVALID_PAPER_ID,
    IdentityError,
    bound_pipeline_object,
    claim_id,
    establish_canonical_paper_id,
    event_id,
    evidence_fingerprint,
    is_canonical_paper_id,
    is_stable_subject_id,
    nfkc_collapse,
    normalize_doi,
    paper_id_from_pdf_sha256,
    paper_page_slug,
    pipeline_fingerprint,
    repo_id,
)


def test_arxiv_strips_version_and_wins_priority() -> None:
    paper_id, aliases = establish_canonical_paper_id(
        arxiv_ids=["2311.15127v2"],
        dois=["10.1234/Foo"],
        openalex_ids=["W123"],
        pdf_sha256="ab" * 32,
    )
    assert paper_id == "arxiv:2311.15127"
    assert "doi:10.1234/foo" in aliases
    assert "openalex:W123" in aliases
    assert f"sha256:{'ab' * 32}" in aliases


def test_doi_lowercase_when_no_arxiv() -> None:
    paper_id, aliases = establish_canonical_paper_id(
        dois=["https://doi.org/10.1234/FooBar"],
        openalex_ids=["W99"],
        pdf_sha256="cd" * 32,
    )
    assert paper_id == "doi:10.1234/foobar"
    assert aliases == ("openalex:W99", f"sha256:{'cd' * 32}")


def test_openalex_then_full_sha_fallback() -> None:
    paper_id, _aliases = establish_canonical_paper_id(openalex_ids=["openalex:W123"])
    assert paper_id == "openalex:W123"
    digest = "ef" * 32
    paper_id, aliases = establish_canonical_paper_id(pdf_sha256=digest)
    assert paper_id == f"sha256:{digest}"
    assert aliases == ()
    assert paper_id_from_pdf_sha256(digest) == f"sha256:{digest}"


def test_sha_fallback_rejects_truncated_digest() -> None:
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(pdf_sha256="abcdabcdabcd")
    assert exc.value.code == INVALID_PAPER_ID


def test_malformed_nonempty_candidate_is_not_skipped() -> None:
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(arxiv_ids=["not-an-id"], dois=["10.1234/foo"])
    assert exc.value.code == INVALID_PAPER_ID


def test_same_priority_conflict() -> None:
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(arxiv_ids=["2311.15127", "2209.14792"])
    assert exc.value.code == IDENTITY_CONFLICT
    assert exc.value.exit_code == 75


def test_existing_id_never_renamed_and_pdf_conflict() -> None:
    paper_id, aliases = establish_canonical_paper_id(
        existing_paper_id="arxiv:2311.15127",
        dois=["10.1234/foo"],
        pdf_sha256="ab" * 32,
    )
    assert paper_id == "arxiv:2311.15127"
    assert "doi:10.1234/foo" in aliases
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(
            existing_paper_id="arxiv:2311.15127",
            pdf_sha256="cd" * 32,
            existing_paper_bindings={"arxiv:2311.15127": "ab" * 32},
        )
    assert exc.value.code == IDENTITY_CONFLICT


def test_page_slug_is_not_canonical() -> None:
    assert is_canonical_paper_id("arxiv:2311.15127")
    assert not is_canonical_paper_id("arxiv-2311.15127")
    assert paper_page_slug("arxiv:2311.15127") == "arxiv-2311.15127"
    assert paper_page_slug("openalex:W123") == "openalex-W123"
    digest = "ab" * 32
    assert paper_page_slug(f"sha256:{digest}") == f"sha256-{digest}"
    doi = "doi:10.1234/foo"
    slug = paper_page_slug(doi)
    assert slug.startswith("doi-")
    assert slug != doi
    assert ":" not in slug
    assert len(slug) == 4 + 64
    old = paper_page_slug("arxiv:hep-th/9901001")
    assert old == "arxiv-hep-th-9901001"
    assert "/" not in old
    assert not is_canonical_paper_id(old)


def test_uppercase_doi_canonicalizes_and_is_not_kept() -> None:
    assert not is_canonical_paper_id("doi:10.1234/Foo")
    paper_id, aliases = establish_canonical_paper_id(existing_paper_id="doi:10.1234/Foo")
    assert paper_id == "doi:10.1234/foo"
    assert "doi:10.1234/Foo" not in (paper_id, *aliases)


def test_non_ascii_uppercase_doi_is_not_kept_as_canonical() -> None:
    dotted_i = "doi:10.1234/foo\u0130"
    assert not is_canonical_paper_id(dotted_i)
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(existing_paper_id=dotted_i)
    assert exc.value.code == INVALID_PAPER_ID

    kelvin = "doi:10.1234/foo\u212a"
    assert not is_canonical_paper_id(kelvin)
    folded, kelvin_aliases = establish_canonical_paper_id(existing_paper_id=kelvin)
    assert folded == normalize_doi(kelvin)
    assert folded != kelvin
    assert kelvin not in (folded, *kelvin_aliases)
    assert is_canonical_paper_id(folded)

    ligature = "doi:10.1234/foo\ufb01"
    assert not is_canonical_paper_id(ligature)
    collapsed, ligature_aliases = establish_canonical_paper_id(existing_paper_id=ligature)
    assert collapsed == normalize_doi(ligature)
    assert collapsed != ligature
    assert ligature not in (collapsed, *ligature_aliases)
    assert is_canonical_paper_id(collapsed)


def test_cherokee_uppercase_doi_is_rejected() -> None:
    cherokee = "doi:10.1234/foo\u13a0"
    assert not is_canonical_paper_id(cherokee)
    with pytest.raises(IdentityError) as exc:
        normalize_doi(cherokee)
    assert exc.value.code == INVALID_PAPER_ID
    with pytest.raises(IdentityError) as establish_exc:
        establish_canonical_paper_id(existing_paper_id=cherokee)
    assert establish_exc.value.code == INVALID_PAPER_ID
    assert is_canonical_paper_id("doi:10.1234/foo")


def test_pipeline_fingerprint_is_jcs_sha256_of_bound_parser() -> None:
    parser = {
        "engine": "docling",
        "engine_version": "2.117.0",
        "core_version": "2.92.0",
        "config_sha256": "b" * 64,
        "model_manifest_sha256": "c" * 64,
    }
    bound = bound_pipeline_object(
        engine="docling",
        engine_version="2.117.0",
        core_version="2.92.0",
        config_sha256="b" * 64,
        model_manifest_sha256="c" * 64,
    )
    digest = pipeline_fingerprint(bound)
    assert digest == pipeline_fingerprint(parser)
    assert len(digest) == 64
    assert digest != pipeline_fingerprint({**parser, "engine_version": "0.0.0"})


def test_existing_sha_cannot_skip_present_arxiv() -> None:
    digest = "a" * 64
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(
            existing_paper_id=f"sha256:{digest}",
            arxiv_ids=["2311.15127"],
            pdf_sha256=digest,
        )
    assert exc.value.code == IDENTITY_CONFLICT
    assert exc.value.exit_code == 75


def test_existing_arxiv_conflicts_with_different_arxiv_candidate() -> None:
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(
            existing_paper_id="arxiv:2311.15127",
            arxiv_ids=["2209.14792"],
        )
    assert exc.value.code == IDENTITY_CONFLICT
    assert exc.value.exit_code == 75


def test_existing_sha256_id_conflicts_without_bindings() -> None:
    with pytest.raises(IdentityError) as exc:
        establish_canonical_paper_id(
            existing_paper_id="sha256:" + "a" * 64,
            pdf_sha256="b" * 64,
        )
    assert exc.value.code == IDENTITY_CONFLICT
    assert exc.value.exit_code == 75


def test_repo_id_casefold_excludes_commit() -> None:
    assert repo_id("Stability-AI/generative-models") == "github:stability-ai/generative-models"
    assert is_stable_subject_id("repo:github:stability-ai/generative-models")
    assert not is_stable_subject_id("repo:github:Stability-AI/generative-models")


def test_claim_id_nfkc_whitespace_and_locator_stability() -> None:
    subject = "paper:arxiv:2311.15127"
    text = "The model uses a diffusion transformer."
    base = claim_id(subject, text)
    equivalent = claim_id(subject, "  The model\tuses a diffusion transformer．  ")
    assert base == equivalent
    assert nfkc_collapse("  A\u2003B\tC  ") == "A B C"
    first = [{"page": 3, "ref": "#/texts/7"}]
    second = [{"page": 99, "ref": "#/texts/800"}]
    assert claim_id(subject, text, first) == claim_id(subject, text, second)
    assert claim_id(subject, "The model uses a U-Net.") != base
    assert claim_id("repo:github:stability-ai/generative-models", text) != base


def test_event_and_evidence_ignore_key_order() -> None:
    event = {
        "schema": "video-paper-wiki.assessment-event.v1",
        "claim_id": "clm-0123456789abcdefabcd",
        "previous_event_id": None,
        "actor_kind": "system",
        "transition_kind": "genesis",
        "from_assessment": None,
        "to_assessment": "provisional",
        "claim_text_sha256": "a" * 64,
        "evidence_fingerprint": "b" * 64,
        "decided_by": "vpwiki",
        "decided_at": "2026-08-29T12:00:00Z",
        "reason": "Initial provisional assessment.",
    }
    reversed_event = OrderedDict(reversed(list(event.items())))
    assert event_id(event) == event_id(reversed_event)
    pdf = {
        "relation": "supports",
        "kind": "pdf",
        "source_id": "src-paper",
        "page": 3,
        "ref": "#/texts/7",
        "bbox": [1, 2, 3, 4],
        "artifact_path": "p.json",
        "artifact_sha256": "a" * 64,
        "text_sha256": "b" * 64,
    }
    code = {
        "relation": "uncertain",
        "kind": "code",
        "source_id": "src-repo",
        "repository": "ExampleOrg/VideoModel",
        "commit": "c" * 40,
        "path": "models/dit.py",
        "lines": {"start": 10, "end": 30},
        "symbol": "X",
        "snippet_sha256": "d" * 64,
    }
    assert evidence_fingerprint([pdf, code]) == evidence_fingerprint([code, pdf])
