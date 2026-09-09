from __future__ import annotations

import os
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.source_publication_io import PublicationTree, checked_path, staged_tree
from video_paper_wiki.source_semantics_contracts import sha


@pytest.mark.parametrize("value", [None, 1, b"/tmp/a", "a/../b", "a/./b", "a//b", "a\\b", "a\x00b"])
def test_original_caller_spelling_is_checked_before_path_normalization(value):
    with pytest.raises(ContractError) as err:
        checked_path(value)
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("change", ["hash", "type", "name", "count", "size", "total"])
def test_install_rejects_invalid_content_before_any_file_write(checkout, monkeypatch, change):
    import video_paper_wiki.source_publication_io as io
    raw = b"exact payload"
    contents = {sha(raw): raw}
    if change == "hash": contents = {"a" * 64: raw}
    elif change == "type": contents = {sha(raw): "not bytes"}
    elif change == "name": contents = {"../outside": raw}
    elif change == "count": monkeypatch.setattr(io, "MAX_PAYLOADS", 0)
    elif change == "size": monkeypatch.setattr(io, "MAX_FILE", len(raw) - 1)
    else: monkeypatch.setattr(io, "MAX_TOTAL", len(raw) - 1)
    with staged_tree("slots", create=True) as tree:
        with pytest.raises(ContractError):
            tree.install(b"request", contents)
        assert list((tree.path / "content").iterdir()) == []
        assert not (tree.path / "request.json").exists()


def external_tree(checkout):
    root = checkout / "external/source-publication"
    (root / "content").mkdir(parents=True)
    (root / "request.json").write_bytes(b"request")
    return root


@pytest.mark.parametrize("exception", [False, True])
def test_existing_content_identity_is_bound_before_request_read(checkout, monkeypatch, exception):
    import video_paper_wiki.source_publication_io as io
    root = external_tree(checkout)
    original = io.RetainedFile

    def retain(path, **kwargs):
        held = original(path, **kwargs)
        (root / "content").rename(root.parent / "detached-content")
        (root / "content").mkdir()
        if exception:
            held.close()
            raise ContractError("SOURCE_PUBLICATION_INVALID", "injected request parse failure")
        return held

    monkeypatch.setattr(io, "RetainedFile", retain)
    with pytest.raises(ContractError) as err:
        PublicationTree(root)
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("present", [False, True])
def test_request_slot_is_bound_before_content_acquisition(checkout, monkeypatch, present):
    import video_paper_wiki.source_publication_io as io
    root = external_tree(checkout)
    if not present:
        (root / "request.json").unlink()
    original = io.RetainedDirectory

    def retain(path):
        held = original(path)
        if Path(path).name == "content":
            replacement = root.parent / "replacement"
            replacement.write_bytes(b"changed-request")
            os.replace(replacement, root / "request.json")
        return held

    monkeypatch.setattr(io, "RetainedDirectory", retain)
    with pytest.raises(ContractError) as err:
        PublicationTree(root)
    assert err.value.code == "WORK_PATH_UNSAFE"


def test_new_root_retains_the_original_session_descriptor(checkout, monkeypatch):
    import video_paper_wiki.source_publication_io as io
    original = io._ensure_dir_at

    def replace(parent, name, path, **kwargs):
        fd = original(parent, name, path, **kwargs)
        path.rename(checkout / "detached-root")
        path.mkdir()
        return fd

    monkeypatch.setattr(io, "_ensure_dir_at", replace)
    with pytest.raises(ContractError) as err:
        with staged_tree("initial-root", create=True):
            pytest.fail("replaced source root was accepted")
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "orphan", "case-alias", "private-mode"])
def test_generated_content_rejects_unsafe_or_extra_entries(checkout, kind):
    raw = b"payload"
    with staged_tree("unsafe", create=True) as tree:
        tree.install(b"request", {sha(raw): raw})
        root = tree.path
    target = root / "content" / sha(raw)
    if kind == "symlink":
        target.unlink(); target.symlink_to(checkout / "outside")
    elif kind == "hardlink":
        os.link(target, checkout / "link")
    elif kind == "directory":
        target.unlink(); target.mkdir()
    elif kind == "orphan":
        (root / "unknown").write_bytes(b"unknown")
    elif kind == "case-alias":
        target.rename(target.with_name(target.name.upper()))
    else:
        target.chmod(0o644)
    with pytest.raises(ContractError) as err:
        with staged_tree("unsafe", create=False):
            pytest.fail("unsafe staged input accepted")
    assert err.value.code == "WORK_PATH_UNSAFE"


def test_changed_lineage_overrides_install_exception(checkout, monkeypatch):
    import video_paper_wiki.source_publication_io as io
    with pytest.raises(ContractError) as err:
        with staged_tree("failure", create=True) as tree:
            original = io._atomic_install

            def replace(*args, **kwargs):
                value = original(*args, **kwargs)
                tree.path.rename(checkout / "detached")
                tree.path.mkdir()
                raise ContractError("SOURCE_HISTORY_CONFLICT", "injected install failure")

            monkeypatch.setattr(io, "_atomic_install", replace)
            tree.install(b"request", {sha(b"payload"): b"payload"})
    assert err.value.code == "WORK_PATH_UNSAFE"


def test_foreign_fill_of_missing_slot_cannot_be_adopted(checkout, monkeypatch):
    import video_paper_wiki.source_publication_io as io
    original = io._atomic_install

    def fill(*args, **kwargs):
        target = kwargs["target"]
        target.write_bytes(args[3]); target.chmod(0o600)
        return original(*args, **kwargs)

    monkeypatch.setattr(io, "_atomic_install", fill)
    with pytest.raises(ContractError) as err:
        with staged_tree("foreign-fill", create=True) as tree:
            tree.install(b"request", {sha(b"payload"): b"payload"})
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("target", ["content", "vault"])
@pytest.mark.parametrize("exception", [False, True])
def test_final_source_guards_cover_pinned_inspector_success_and_failure(checkout, monkeypatch, target, exception):
    import video_paper_wiki.publication as publication
    from tests.research.conftest import UPSTREAM
    from tests.source_publication_fixture import knowledge_proposal, registered_source
    from video_paper_wiki.source_publication import inspect_source_publication, prepare_source_publication
    vault, capture, _, _ = registered_source(checkout)
    payloads, _, _ = knowledge_proposal(vault, capture)
    prepared = prepare_source_publication(batch_id="guard", operation_id="guard", vault_root=vault, payloads=payloads)
    original = publication.inspect_pinned_transaction
    replaced = vault if target == "vault" else Path(prepared["request_path"]).parent / "content"

    def inspect(*args, **kwargs):
        result = original(*args, **kwargs)
        replaced.rename(checkout / "detached-guard-target")
        replaced.mkdir()
        if exception:
            raise ContractError("UPSTREAM_INSPECT_REFUSED", "injected post-inspection failure")
        return result

    monkeypatch.setattr(publication, "inspect_pinned_transaction", inspect)
    with pytest.raises(ContractError) as err:
        inspect_source_publication(prepared=prepared["request_path"], operation_id="guard", vault_root=vault, upstream_root=UPSTREAM)
    assert err.value.code == "WORK_PATH_UNSAFE"
