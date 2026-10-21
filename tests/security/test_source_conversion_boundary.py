from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.research.test_source_conversion import conversion_fixture
from tests.upstream.test_markdown_source import _snapshot
from video_paper_wiki.contracts import ContractError
from video_paper_wiki_research import source_conversion as conversion
from video_paper_wiki_research import source_conversion_io as conversion_io


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "case-alias", "non-nfc", "control"])
def test_complete_light_tree_refuses_unsafe_unselected_entries(checkout, monkeypatch, kind):
    kwargs, _, _, _ = conversion_fixture(checkout)
    root = kwargs["workspace_root"] / ".light-knowledge"
    target = root / "unrelated"
    if kind == "symlink":
        target.symlink_to(kwargs["capture_authority"])
    elif kind == "hardlink":
        os.link(kwargs["capture_authority"], target)
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "case-alias":
        # Preserve the same rejection vector on filesystems that merge the two
        # names: duplicate enumeration alone must fail before opening either.
        (root / "Case").write_bytes(b"a")
        (root / "case").write_bytes(b"b")
        names = set(os.listdir(root))
        if not {"Case", "case"} <= names:
            original = os.listdir
            identity = root.stat()

            def collision(path):
                if isinstance(path, int) and os.fstat(path).st_ino == identity.st_ino:
                    return sorted(set(original(path)) | {"Case", "case"})
                return original(path)

            monkeypatch.setattr(conversion_io.os, "listdir", collision)
    elif kind == "non-nfc":
        (root / "e\u0301.json").write_bytes(b"{}")
    else:
        (root / "invalid\nname").write_bytes(b"{}")
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert before == _snapshot(kwargs["vault_root"])
    assert not (checkout / ".work/convert/source-publication").exists()


@pytest.mark.parametrize("target", ["tree-root", "empty-directory", "unrelated-file", "source-ancestor", "authority", "metadata", "mirror-file", "mirror-root"])
@pytest.mark.parametrize("ordinary_failure", [False, True])
def test_all_input_lineages_verified_on_success_and_semantic_failure(checkout, monkeypatch, target, ordinary_failure):
    kwargs, _, _, _ = conversion_fixture(checkout)
    root = kwargs["workspace_root"] / ".light-knowledge"
    (root / "empty").mkdir()
    (root / "unrelated").write_bytes(b"old")
    original = conversion._current_record

    def replace_during_validation(mirror, paper_id, record_id):
        result = original(mirror, paper_id, record_id)
        if target == "tree-root":
            root.rename(root.with_name("old-light"))
            root.mkdir()
        elif target == "empty-directory":
            (root / "empty/new").write_bytes(b"new")
        elif target == "unrelated-file":
            (root / "unrelated").write_bytes(b"new")
        elif target == "source-ancestor":
            parent = kwargs["workspace_root"] / "papers"
            parent.rename(parent.with_name("old-papers"))
            parent.mkdir()
        elif target in {"authority", "metadata"}:
            path = kwargs["capture_authority" if target == "authority" else "metadata"]
            replacement = path.with_name("replacement")
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        elif target == "mirror-file":
            path = mirror / ".light-knowledge/unrelated"
            path.write_bytes(b"changed mirror")
        else:
            mirror.rename(mirror.with_name(mirror.name + "-old"))
            mirror.mkdir()
        if ordinary_failure:
            raise ContractError("SOURCE_CONVERSION_INVALID", "injected semantic refusal", {"instance_pointer": "/record_id"})
        return result

    monkeypatch.setattr(conversion, "_current_record", replace_during_validation)
    before = _snapshot(kwargs["vault_root"])
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert before == _snapshot(kwargs["vault_root"])


def test_unchanged_semantic_error_retains_code_pointer_and_exit(checkout, monkeypatch):
    kwargs, _, _, _ = conversion_fixture(checkout)

    def refused(*args):
        raise ContractError("CUSTOM_LOWER_LEVEL", "original message", {"instance_pointer": "/exact"}, exit_code=75)

    monkeypatch.setattr(conversion, "_current_record", refused)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert (err.value.code, err.value.details, err.value.exit_code) == ("CUSTOM_LOWER_LEVEL", {"instance_pointer": "/exact"}, 75)


@pytest.mark.parametrize("limit,value", [("MAX_ENTRIES", 1), ("MAX_DEPTH", 1), ("MAX_FILE", 2), ("MAX_TOTAL", 3)])
def test_light_tree_resource_bounds_precede_validator_and_request(checkout, monkeypatch, limit, value):
    kwargs, _, _, _ = conversion_fixture(checkout)
    monkeypatch.setattr(conversion_io, limit, value)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "SOURCE_CONVERSION_INVALID"
    assert not (checkout / ".work/convert/source-publication").exists()


def test_raw_dot_alias_is_rejected_before_path_normalization(checkout):
    kwargs, _, _, _ = conversion_fixture(checkout)
    kwargs["workspace_root"] = str(kwargs["workspace_root"]) + "/."
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"


def test_partial_acquisition_rechecks_unread_sibling_identity(checkout, monkeypatch):
    kwargs, _, _, _ = conversion_fixture(checkout)
    root = kwargs["workspace_root"] / ".light-knowledge"
    first, later = root / "000-first", root / "zzz-unread"
    first.write_bytes(b"first")
    later.write_bytes(b"same-size")
    first_stat = first.stat()
    original = conversion_io._read

    def fail_first(fd, maximum):
        if os.fstat(fd).st_ino == first_stat.st_ino:
            later.write_bytes(b"different")
            raise ContractError("SOURCE_CONVERSION_INVALID", "acquisition stopped", {"instance_pointer": "/input"})
        return original(fd, maximum)

    monkeypatch.setattr(conversion_io, "_read", fail_first)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert not (checkout / ".work/convert/source-publication").exists()


def test_existing_nonce_is_never_reused_or_modified(checkout, monkeypatch):
    kwargs, _, _, _ = conversion_fixture(checkout)
    slot = checkout / ".work/convert/source-conversion" / ("inputs-" + "a" * 32)
    slot.mkdir(parents=True)
    (slot / "foreign").write_bytes(b"preserve this content")
    monkeypatch.setattr(conversion_io.secrets, "token_hex", lambda count: "a" * 32)
    before = _snapshot(slot)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert _snapshot(slot) == before


@pytest.mark.parametrize("same_bytes", [False, True])
def test_raced_foreign_install_has_one_safety_error(checkout, monkeypatch, same_bytes):
    kwargs, _, _, _ = conversion_fixture(checkout)
    original = conversion_io._atomic_install
    planted = []

    def occupy(work_fd, parent_fd, name, data, **options):
        if not planted:
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode=0o600, dir_fd=parent_fd)
            raw = data if same_bytes else b"foreign bytes"
            try:
                os.write(fd, raw)
            finally:
                os.close(fd)
            planted.append((options["target"], raw))
        return original(work_fd, parent_fd, name, data, **options)

    monkeypatch.setattr(conversion_io, "_atomic_install", occupy)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert planted and planted[0][0].read_bytes() == planted[0][1]


def test_session_only_staging_error_keeps_direct_api_contract(checkout, monkeypatch):
    from video_paper_wiki.staging import StagingError, _RetainedBatchSession
    kwargs, _, _, _ = conversion_fixture(checkout)
    original_record = conversion._current_record
    original_verify = _RetainedBatchSession.verify
    ready = False

    def after_validation(*args):
        nonlocal ready
        value = original_record(*args)
        ready = True
        return value

    def refused_session(session):
        if ready and session.batch == "convert":
            raise StagingError("WORK_PATH_UNSAFE", "injected session-only lineage failure", {"instance_pointer": "/session"})
        return original_verify(session)

    monkeypatch.setattr(conversion, "_current_record", after_validation)
    monkeypatch.setattr(_RetainedBatchSession, "verify", refused_session)
    with pytest.raises(ContractError) as err:
        conversion.convert_source_knowledge(**kwargs)
    assert (err.value.code, err.value.details["instance_pointer"], err.value.exit_code) == ("WORK_PATH_UNSAFE", "/session", 2)


@pytest.mark.parametrize("ancestor", [False, True])
@pytest.mark.parametrize("ordinary_failure", [False, True])
def test_named_vault_replacement_has_safety_priority_at_prepare(checkout, monkeypatch, ancestor, ordinary_failure):
    import shutil
    kwargs, _, _, capture = conversion_fixture(checkout)
    vault = kwargs["vault_root"]
    target = vault / (".raw/captured" if ancestor else capture["stored_path"])
    saved = checkout / "saved-original-capture"
    original = conversion._prepare_source_publication_retained
    before = _snapshot(vault)
    injected = False

    def replace_before_prepare(**options):
        nonlocal injected
        target.rename(saved)
        if ancestor:
            shutil.copytree(saved, target)
        else:
            target.write_bytes(saved.read_bytes())
        injected = True
        if ordinary_failure:
            raise ContractError("SOURCE_CONVERSION_INVALID", "ordinary prepare refusal", {"instance_pointer": "/prepare"})
        return original(**options)

    monkeypatch.setattr(conversion, "_prepare_source_publication_retained", replace_before_prepare)
    try:
        with pytest.raises(ContractError) as err:
            conversion.convert_source_knowledge(**kwargs)
        assert injected and err.value.code == "WORK_PATH_UNSAFE" and err.value.exit_code == 2
        assert "instance_pointer" in err.value.details
    finally:
        if injected:
            if ancestor:
                shutil.rmtree(target)
            else:
                target.unlink()
            saved.rename(target)
    assert before == _snapshot(vault)
    assert not (checkout / ".work/convert/source-publication").exists()
