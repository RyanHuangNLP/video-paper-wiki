from __future__ import annotations
import shutil
from pathlib import Path
import pytest

from tests.research.test_source_admission import bootstrap_genesis
from tests.support import make_checkout
from video_paper_wiki.contracts import ContractError
from video_paper_wiki import resources
from video_paper_wiki.source_catalog import source_catalog_status
from video_paper_wiki.source_catalog_io import Generation, catalog_slot, retained_tree, verify_all


def _installed(checkout, monkeypatch):
    source = Path(resources.__file__).parent
    root = source.parent.parent
    package = checkout / "installation/video_paper_wiki"
    shutil.copytree(source, package, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(root / "schemas", package / "schemas")
    shutil.copytree(root / "taxonomy", package / "taxonomy")
    shutil.copytree(root / "catalog", package / "catalog")
    monkeypatch.setattr(resources.resources, "files", lambda _: package)
    monkeypatch.setattr(resources, "_source_checkout_root", lambda: None)
    return package


@pytest.mark.parametrize("missing", [
    "schemas/video-paper-wiki.source-catalog.v1.schema.json",
    "taxonomy/v1.json",
    "catalog/source-catalog-v1.json",
])
def test_missing_installed_optional_resource_does_not_create_or_cwd_fallback(tmp_path, monkeypatch, missing):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    package = _installed(checkout, monkeypatch)
    bootstrap_genesis(checkout, checkout / "vault", checkout)
    target = package / missing
    target.unlink()
    with pytest.raises(ContractError) as exc:
        source_catalog_status(vault_root=checkout / "vault", batch_id="missing")
    assert exc.value.code == "SOURCE_CATALOG_INVALID"
    assert not target.exists()
    assert not (checkout / "schemas").exists()
    assert not (checkout / "taxonomy").exists()
    assert not (checkout / "catalog").exists()
    assert not (checkout / ".work" / "missing").exists()


def test_classifier_retains_first_stat_before_open(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    package = _installed(checkout, monkeypatch)
    target = package / "source_catalog.py"
    original_stat = __import__("video_paper_wiki.source_catalog_io", fromlist=["os"]).os.stat
    fired = False
    def racing_stat(name, *args, **kwargs):
        nonlocal fired
        result = original_stat(name, *args, **kwargs)
        if not fired and name == "source_catalog.py" and kwargs.get("follow_symlinks") is False:
            fired = True
            saved = checkout / "saved-source-catalog.py"
            target.rename(saved)
            target.write_bytes(saved.read_bytes() + b"\n# replacement\n")
        return result
    import video_paper_wiki.source_catalog_io as module
    monkeypatch.setattr(module.os, "stat", racing_stat)
    with pytest.raises(ContractError) as exc:
        with retained_tree() as tree:
            Generation(tree)
    assert fired
    assert exc.value.code == "WORK_PATH_UNSAFE"


def test_final_checks_continue_after_earlier_failure_and_override_body_error():
    events = []
    def first():
        events.append("first")
        raise ContractError("WORK_PATH_UNSAFE", "first failure")
    def second():
        events.append("second")
        raise ContractError("SOURCE_CATALOG_INVALID", "second failure")
    with pytest.raises(ContractError) as exc:
        verify_all([first, second])
    assert events == ["first", "second"]
    assert exc.value.code == "WORK_PATH_UNSAFE"


def test_read_only_absent_catalog_slot_does_not_create_work_tree(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    with catalog_slot("absent", create=False) as slot:
        assert slot.fd is None and slot.data is None
    assert not (checkout / ".work" / "absent").exists()
