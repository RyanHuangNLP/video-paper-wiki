from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.research.test_source_admission import bootstrap_genesis
from tests.upstream.test_markdown_source import _snapshot
from tests.upstream.test_source_catalog import published
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.source_catalog import build_source_catalog, query_source_catalog, source_catalog_status


def empty(checkout):
    vault = checkout / "vault"
    bootstrap_genesis(checkout, vault, checkout)
    return vault


@pytest.mark.parametrize("problem", ["symlink", "hardlink", "directory", "fifo", "permissions", "sibling"])
def test_unsafe_cache_shape_refuses_without_rewrite(checkout, problem):
    vault = empty(checkout)
    built = build_source_catalog(vault_root=vault, batch_id="catalog")
    path = Path(built["cache_path"])
    original = path.read_bytes()
    if problem == "symlink":
        saved = checkout / "saved"; path.rename(saved); path.symlink_to(saved)
    elif problem == "hardlink":
        os.link(path, checkout / "linked")
    elif problem == "directory":
        path.unlink(); path.mkdir()
    elif problem == "fifo":
        path.unlink(); os.mkfifo(path, 0o600)
    elif problem == "permissions":
        path.chmod(0o644)
    else:
        (path.parent / "foreign").write_bytes(b"owned elsewhere")
    before = _snapshot(vault)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="catalog")
    assert err.value.code == "WORK_PATH_UNSAFE" and _snapshot(vault) == before
    if problem in {"permissions", "hardlink", "sibling"}:
        assert path.read_bytes() == original


@pytest.mark.parametrize("ordinary_error", [False, True])
@pytest.mark.parametrize("replacement", ["file", "directory"])
def test_original_vault_named_replacement_wins_on_all_exits(checkout, monkeypatch, ordinary_error, replacement):
    import video_paper_wiki.source_catalog as module
    from video_paper_wiki.source_publication_contracts import SOURCE_LEDGER
    vault = empty(checkout)
    original = module.collect_source_state
    saved = checkout / "saved"
    def mutate(*args, **kwargs):
        state = original(*args, **kwargs)
        target = vault / SOURCE_LEDGER if replacement == "file" else vault
        target.rename(saved)
        if replacement == "file":
            target.write_bytes(saved.read_bytes()); target.chmod(0o600)
        else:
            shutil.copytree(saved, target)
        assert target.stat().st_ino != saved.stat().st_ino
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary fixture failure")
        return state
    monkeypatch.setattr(module, "collect_source_state", mutate)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="missing")
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert not (checkout / ".work/missing").exists()


@pytest.mark.parametrize("create", [False, True])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_foreign_appearance_at_first_missing_cache_edge_refuses(checkout, monkeypatch, create, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    original = module.reconstruct
    def appear(*args, **kwargs):
        value = original(*args, **kwargs)
        if create:
            path = checkout / ".work/new/source-catalog/catalog.json"
            path.write_bytes(value[1]); path.chmod(0o600)
        else:
            (checkout / ".work/new").mkdir(mode=0o700)
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary fixture failure")
        return value
    monkeypatch.setattr(module, "reconstruct", appear)
    with pytest.raises(ContractError) as err:
        (build_source_catalog if create else source_catalog_status)(vault_root=vault, batch_id="new")
    assert err.value.code == "WORK_PATH_UNSAFE"


def installed_generation(checkout, monkeypatch):
    from video_paper_wiki import resources
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


@pytest.mark.parametrize("target", ["python", "schema", "taxonomy", "profile", "add-python", "add-schema", "directory"])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_retained_generation_changes_win_even_on_ordinary_failure(checkout, monkeypatch, target, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    package = installed_generation(checkout, monkeypatch)
    original = module.collect_source_state
    def mutate(*args, **kwargs):
        state = original(*args, **kwargs)
        targets = {"python": package / "source_catalog.py", "schema": package / "schemas/video-paper-wiki.source-catalog.v1.schema.json",
                   "taxonomy": package / "taxonomy/v1.json", "profile": package / "catalog/source-catalog-v1.json"}
        if target in targets:
            path = targets[target]; saved = checkout / "saved-generation"
            path.rename(saved); path.write_bytes(saved.read_bytes()); path.chmod(saved.stat().st_mode & 0o777)
            assert path.stat().st_ino != saved.stat().st_ino
        elif target == "add-python":
            (package / "added.py").write_bytes(b"# New generation source\n")
        elif target == "add-schema":
            (package / "schemas/added.schema.json").write_bytes(b"{}")
        else:
            path = package / "schemas"; saved = checkout / "saved-schemas"
            path.rename(saved); shutil.copytree(saved, path)
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary fixture failure")
        return state
    monkeypatch.setattr(module, "collect_source_state", mutate)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="missing")
    assert err.value.code == "WORK_PATH_UNSAFE"
    assert not (checkout / ".work/missing").exists()


def test_actual_collector_uses_captured_resources_only(checkout, monkeypatch):
    from video_paper_wiki import resources
    import video_paper_wiki.source_catalog as module
    vault, _, _, _ = published(checkout)
    original = module.audit_integrity
    def audited(*args, **kwargs):
        monkeypatch.setattr(resources.resources, "files", lambda *a: pytest.fail("live package read after capture"))
        monkeypatch.setattr(resources, "_package_text", lambda *a: pytest.fail("live package text after capture"))
        monkeypatch.setattr(resources, "_repo_text", lambda *a: pytest.fail("live repo/CWD text after capture"))
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "audit_integrity", audited)
    before = _snapshot(vault)
    result = build_source_catalog(vault_root=vault, batch_id="resources")
    assert result["counts"]["claims"] == 1 and _snapshot(vault) == before


def test_public_catalog_operation_is_zero_egress(checkout, monkeypatch):
    import socket
    import subprocess
    import urllib.request
    vault, _, _, _ = published(checkout)
    def refuse(*a, **k):
        pytest.fail("catalog attempted external execution or networking")
    for parent, name in ((socket.socket, "connect"), (socket, "create_connection"), (socket, "getaddrinfo"),
                         (subprocess, "Popen"), (urllib.request, "urlopen")):
        monkeypatch.setattr(parent, name, refuse)
    build_source_catalog(vault_root=vault, batch_id="offline")
    assert query_source_catalog(vault_root=vault, batch_id="offline", text="attention")["hits"]


@pytest.mark.parametrize("missing", ["work", "batch", "directory", "leaf"])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_each_missing_cache_edge_stays_absent_until_every_exit(checkout, monkeypatch, missing, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    work = checkout / ".work"
    if missing == "work":
        work.rename(checkout / "prior-work")
        target = work
    else:
        target = work / "new"
        if missing in {"directory", "leaf"}:
            target.mkdir(mode=0o700)
            target /= "source-catalog"
        if missing == "leaf":
            target.mkdir(mode=0o700)
            target /= "catalog.json"
    original = module.reconstruct
    def appear(*args, **kwargs):
        result = original(*args, **kwargs)
        if missing == "leaf":
            target.write_bytes(result[1]); target.chmod(0o600)
        else:
            target.mkdir(mode=0o700)
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary synthetic failure")
        return result
    monkeypatch.setattr(module, "reconstruct", appear)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="new")
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("command", ["build", "status", "lookup", "query", "resolve"])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_cache_file_replacement_is_checked_by_every_public_command(checkout, monkeypatch, command, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    built = build_source_catalog(vault_root=vault, batch_id="catalog")
    path = Path(built["cache_path"])
    original = module.reconstruct
    def replace(*args, **kwargs):
        result = original(*args, **kwargs)
        saved = checkout / "retained-catalog"
        path.rename(saved)
        path.write_bytes(saved.read_bytes()); path.chmod(0o600)
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary synthetic failure")
        return result
    monkeypatch.setattr(module, "reconstruct", replace)
    function, arguments = {
        "build": (module.build_source_catalog, {}), "status": (module.source_catalog_status, {}),
        "lookup": (module.lookup_source_catalog, {"kind": "paper", "key": "unknown"}),
        "query": (module.query_source_catalog, {"text": "unknown"}),
        "resolve": (module.resolve_source_catalog, {"claim_id": "clm-" + "0" * 20, "evidence_ordinal": 0}),
    }[command]
    with pytest.raises(ContractError) as err:
        function(vault_root=vault, batch_id="catalog", **arguments)
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("change", ["batch", "directory", "mode", "links", "sibling", "bytes"])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_cache_retained_ancestors_set_and_metadata_changes_refuse(checkout, monkeypatch, change, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    path = Path(build_source_catalog(vault_root=vault, batch_id="catalog")["cache_path"])
    original = module.reconstruct
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        if change in {"batch", "directory"}:
            target = path.parent.parent if change == "batch" else path.parent
            saved = checkout / "saved-ancestor"
            target.rename(saved); shutil.copytree(saved, target)
        elif change == "mode":
            path.chmod(0o644)
        elif change == "links":
            os.link(path, checkout / "second-link")
        elif change == "sibling":
            (path.parent / "foreign").write_bytes(b"foreign")
        else:
            path.write_bytes(b"different content")
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary synthetic failure")
        return result
    monkeypatch.setattr(module, "reconstruct", mutate)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="catalog")
    assert err.value.code == "WORK_PATH_UNSAFE"


@pytest.mark.parametrize("change", ["remove-python", "remove-schema", "bytes", "python-directory", "package"])
@pytest.mark.parametrize("ordinary_error", [False, True])
def test_remaining_generation_deletions_ancestry_and_bytes_refuse(checkout, monkeypatch, change, ordinary_error):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    package = installed_generation(checkout, monkeypatch)
    original = module.collect_source_state
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == "remove-python":
            (package / "source_catalog.py").unlink()
        elif change == "remove-schema":
            (package / "schemas/video-paper-wiki.source-catalog.v1.schema.json").unlink()
        elif change == "bytes":
            path = package / "source_catalog.py"
            path.write_bytes(path.read_bytes() + b"# Changed installed bytes\n")
        else:
            path = package / "notes" if change == "python-directory" else package
            saved = checkout / "saved-generation"
            path.rename(saved); shutil.copytree(saved, path)
        if ordinary_error:
            raise ContractError("SOURCE_CATALOG_INVALID", "ordinary synthetic failure")
        return result
    monkeypatch.setattr(module, "collect_source_state", mutate)
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="missing")
    assert err.value.code == "WORK_PATH_UNSAFE"


def test_generation_excludes_pycache_and_never_falls_back_to_cwd(checkout, monkeypatch):
    import video_paper_wiki.source_catalog as module
    vault = empty(checkout)
    package = installed_generation(checkout, monkeypatch)
    original = module.collect_source_state
    def compile_cache(*args, **kwargs):
        pycache = package / "__pycache__"
        pycache.mkdir(exist_ok=True)
        (pycache / "created-during-read.pyc").write_bytes(b"interpreter cache")
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "collect_source_state", compile_cache)
    assert source_catalog_status(vault_root=vault, batch_id="missing")["state"] == "absent"
    shutil.copytree(package / "schemas", checkout / "schemas")
    shutil.rmtree(package / "schemas")
    with pytest.raises(ContractError) as err:
        source_catalog_status(vault_root=vault, batch_id="missing")
    assert err.value.code == "SOURCE_CATALOG_INVALID"
