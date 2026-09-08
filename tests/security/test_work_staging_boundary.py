from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import stat
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from video_paper_wiki import staging as staging_module
from tests.security._source_policy import assert_no_network_imports
from tests.support import (
    make_approval_ref,
    make_checkout,
    paper_source_request,
    plant_blob,
    complete_ingest_plan,
    work_draft,
    work_plan,
    work_prepared,
    work_review,
    plant_unix_socket,
    write_json,
)
from video_paper_wiki.cli import main
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.resources import _package_text, _repo_file
from video_paper_wiki.staging import (
    CODE_STAGING_CONFLICT,
    CODE_WORK_PATH_ESCAPE,
    CODE_WORK_PATH_UNSAFE,
    StagingError,
    _assert_inside_work,
    stage_bytes,
)
from tests.pdf_samples import sample_pdf_path

ROOT = Path(__file__).resolve().parents[2]
TINY_PDF = sample_pdf_path("tiny")
MINIMAL = ROOT / "tests" / "fixtures" / "drafts" / "minimal.json"
ENVELOPE = ROOT / "schemas" / "video-paper-wiki.cli-envelope.v1.schema.json"
SRC = ROOT / "src" / "video_paper_wiki"
MAV = "arxiv:2209.14792"


def _run_transaction_stage(
    kind: str, batch: str, content: tuple[tuple[str, bytes], ...], bundle: bytes,
):
    if kind == "standalone":
        return staging_module._stage_transaction_inspect_files(
            batch_id=batch, content=content, bundle=bundle,
        )
    with staging_module._open_batch_session(batch, create=True) as session:
        return staging_module._stage_transaction_inspect_files_in_session(
            session, content=content, bundle=bundle,
        )


@pytest.mark.parametrize("kind", ["standalone", "retained"])
def test_transaction_exception_exit_overrides_content_conflict_with_lineage_drift(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    data = b"expected"; digest = hashlib.sha256(data).hexdigest(); batch = f"content-{kind}"
    content_dir = checkout / f".work/{batch}/transaction-inspect/content"
    content_dir.mkdir(parents=True); (content_dir / digest).write_bytes(b"different")
    real = staging_module._existing_same_bytes; attacked = False
    def replace(*args, **kwargs):
        nonlocal attacked
        if not attacked and args[1] == digest:
            attacked = True; content_dir.rename(content_dir.with_name("content-old")); content_dir.mkdir()
            (content_dir / digest).write_bytes(b"different")
        return real(*args, **kwargs)
    monkeypatch.setattr(staging_module, "_existing_same_bytes", replace)
    with pytest.raises(StagingError) as caught:
        _run_transaction_stage(kind, batch, ((digest, data),), b"bundle")
    assert attacked and caught.value.code == CODE_WORK_PATH_UNSAFE


@pytest.mark.parametrize("kind", ["standalone", "retained"])
def test_transaction_exception_exit_overrides_bundle_conflict_with_lineage_drift(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    data = b"expected"; digest = hashlib.sha256(data).hexdigest(); batch = f"bundle-{kind}"
    transport = checkout / f".work/{batch}/transaction-inspect"; content_dir = transport / "content"
    content_dir.mkdir(parents=True); (content_dir / digest).write_bytes(data)
    (transport / "bundle.json").write_bytes(b"different")
    real = staging_module._existing_same_bytes; attacked = False
    def replace(*args, **kwargs):
        nonlocal attacked
        if not attacked and args[1] == "bundle.json":
            attacked = True; transport.rename(transport.with_name("transaction-inspect-old"))
            (transport / "content").mkdir(parents=True); (transport / "bundle.json").write_bytes(b"different")
        return real(*args, **kwargs)
    monkeypatch.setattr(staging_module, "_existing_same_bytes", replace)
    with pytest.raises(StagingError) as caught:
        _run_transaction_stage(kind, batch, ((digest, data),), b"bundle")
    assert attacked and caught.value.code == CODE_WORK_PATH_UNSAFE


@pytest.mark.parametrize("kind", ["standalone", "retained"])
@pytest.mark.parametrize("slot", ["content", "bundle"])
def test_transaction_unchanged_conflict_keeps_staging_conflict(
    checkout: Path, kind: str, slot: str,
) -> None:
    data = b"expected"; digest = hashlib.sha256(data).hexdigest(); batch = f"plain-{kind}-{slot}"
    transport = checkout / f".work/{batch}/transaction-inspect"; content_dir = transport / "content"
    content_dir.mkdir(parents=True)
    (content_dir / digest).write_bytes(b"different" if slot == "content" else data)
    if slot == "bundle": (transport / "bundle.json").write_bytes(b"different")
    with pytest.raises(StagingError) as caught:
        _run_transaction_stage(kind, batch, ((digest, data),), b"bundle")
    assert caught.value.code == CODE_STAGING_CONFLICT


@pytest.mark.parametrize("slot", ["checkout", "work", "batch", "transport", "content"])
def test_transaction_session_refuses_named_lineage_replacement_after_content(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    slot: str,
) -> None:
    first, second = b"first", b"second"
    request = tuple(sorted((
        (hashlib.sha256(first).hexdigest(), first),
        (hashlib.sha256(second).hexdigest(), second),
    )))
    real_install = staging_module._atomic_install
    attacked = False

    def replace_after_install(*args, **kwargs):
        nonlocal attacked
        result = real_install(*args, **kwargs)
        if attacked:
            return result
        attacked = True
        paths = {
            "checkout": checkout,
            "work": checkout / ".work",
            "batch": checkout / ".work/race",
            "transport": checkout / ".work/race/transaction-inspect",
            "content": checkout / ".work/race/transaction-inspect/content",
        }
        target = paths[slot]
        displaced = target.with_name(target.name + "-displaced")
        target.rename(displaced)
        if slot == "checkout":
            target.mkdir()
            (target / ".git").mkdir()
            (target / "pyproject.toml").write_bytes(
                (displaced / "pyproject.toml").read_bytes()
            )
        (checkout / ".work/race/transaction-inspect/content").mkdir(
            parents=True, exist_ok=True,
        )
        return result

    monkeypatch.setattr(staging_module, "_atomic_install", replace_after_install)
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="race", content=request, bundle=b"{}",
        )
    assert attacked
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert not (checkout / ".work/race/transaction-inspect/bundle.json").exists()


@pytest.mark.parametrize("timing", ["after-final-content", "after-bundle"])
def test_transaction_session_rechecks_lineage_at_publication_boundaries(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    timing: str,
) -> None:
    data = b"only-content"
    digest = hashlib.sha256(data).hexdigest()
    real_install = staging_module._atomic_install
    attacked = False

    def replace_batch(*args, **kwargs):
        nonlocal attacked
        result = real_install(*args, **kwargs)
        filename = args[2]
        should_attack = (
            timing == "after-final-content" and filename == digest
        ) or (timing == "after-bundle" and filename == "bundle.json")
        if should_attack and not attacked:
            attacked = True
            batch = checkout / ".work/boundary"
            batch.rename(checkout / ".work/boundary-displaced")
            (batch / "transaction-inspect/content").mkdir(parents=True)
        return result

    monkeypatch.setattr(staging_module, "_atomic_install", replace_batch)
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="boundary", content=((digest, data),), bundle=b"bundle",
        )
    assert attacked
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert not (
        checkout / ".work/boundary/transaction-inspect/bundle.json"
    ).exists()


def test_transaction_session_rechecks_named_lineage_before_first_install(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"content"
    digest = hashlib.sha256(data).hexdigest()
    real_verify = staging_module._verify_transaction_inspect_session
    calls = 0

    def replace_before_first(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            batch = checkout / ".work/before-first"
            batch.rename(checkout / ".work/before-first-displaced")
            (batch / "transaction-inspect/content").mkdir(parents=True)
        return real_verify(**kwargs)

    monkeypatch.setattr(
        staging_module, "_verify_transaction_inspect_session", replace_before_first,
    )
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="before-first", content=((digest, data),), bundle=b"bundle",
        )
    assert calls == 3  # pre-op failure is followed by the required exception-exit recheck
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert not (
        checkout / ".work/before-first/transaction-inspect/bundle.json"
    ).exists()


def test_transaction_session_refuses_deleted_open_content_directory(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"content"
    digest = hashlib.sha256(data).hexdigest()
    real_install = staging_module._atomic_install

    def delete_after_content(*args, **kwargs):
        result = real_install(*args, **kwargs)
        if args[2] == digest:
            content = checkout / ".work/deleted/transaction-inspect/content"
            displaced = content.with_name("content-displaced")
            content.rename(displaced)
            displaced.joinpath(digest).unlink()
            displaced.rmdir()
            content.mkdir()
        return result

    monkeypatch.setattr(staging_module, "_atomic_install", delete_after_content)
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="deleted", content=((digest, data),), bundle=b"bundle",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE


def test_transaction_session_final_set_rejects_content_tamper_after_bundle(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"content"
    digest = hashlib.sha256(data).hexdigest()
    real_install = staging_module._atomic_install

    def tamper_after_bundle(*args, **kwargs):
        result = real_install(*args, **kwargs)
        if args[2] == "bundle.json":
            (checkout / ".work/final-set/transaction-inspect/content" / digest).write_bytes(
                b"tampered"
            )
        return result

    monkeypatch.setattr(staging_module, "_atomic_install", tamper_after_bundle)
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="final-set", content=((digest, data),), bundle=b"bundle",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE


@pytest.mark.parametrize(
    "orphan_kind",
    ["fifo", "symlink", "directory", "non-digest-regular", "transport-extra"],
)
def test_transaction_session_rejects_unsafe_unreferenced_entries_before_bundle(
    checkout: Path,
    tmp_path: Path,
    orphan_kind: str,
) -> None:
    data = b"expected"
    digest = hashlib.sha256(data).hexdigest()
    transport = checkout / ".work/orphans/transaction-inspect"
    content = transport / "content"
    content.mkdir(parents=True)
    orphan_digest = "f" * 64
    if orphan_kind == "fifo":
        os.mkfifo(content / orphan_digest)
    elif orphan_kind == "symlink":
        external = tmp_path / "external"
        external.write_bytes(b"outside")
        content.joinpath(orphan_digest).symlink_to(external)
    elif orphan_kind == "directory":
        content.joinpath(orphan_digest).mkdir()
    elif orphan_kind == "non-digest-regular":
        content.joinpath("orphan.bin").write_bytes(b"orphan")
    else:
        transport.joinpath("extra.json").write_bytes(b"{}")
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="orphans", content=((digest, data),), bundle=b"bundle",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert not transport.joinpath("bundle.json").exists()


def test_unsafe_orphan_does_not_delete_preexisting_exact_bundle(checkout: Path) -> None:
    data = b"expected"
    digest = hashlib.sha256(data).hexdigest()
    transport = checkout / ".work/orphan-existing/transaction-inspect"
    content = transport / "content"
    content.mkdir(parents=True)
    content.joinpath("not-a-digest").write_bytes(b"unsafe")
    transport.joinpath("bundle.json").write_bytes(b"bundle")
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="orphan-existing", content=((digest, data),), bundle=b"bundle",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert transport.joinpath("bundle.json").read_bytes() == b"bundle"


def test_transaction_session_final_enumeration_rejects_new_extra_entry(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"expected"
    digest = hashlib.sha256(data).hexdigest()
    real_install = staging_module._atomic_install

    def add_extra_after_bundle(*args, **kwargs):
        result = real_install(*args, **kwargs)
        if args[2] == "bundle.json":
            (checkout / ".work/final-extra/transaction-inspect/extra.json").write_bytes(
                b"{}"
            )
        return result

    monkeypatch.setattr(staging_module, "_atomic_install", add_extra_after_bundle)
    with pytest.raises(StagingError) as caught:
        staging_module._stage_transaction_inspect_files(
            batch_id="final-extra", content=((digest, data),), bundle=b"bundle",
        )
    assert caught.value.code == CODE_WORK_PATH_UNSAFE
    assert (
        checkout / ".work/final-extra/transaction-inspect/bundle.json"
    ).read_bytes() == b"bundle"


def _snapshot(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"__missing__": True}
    out: dict[str, object] = {}
    for current, dirs, files in os.walk(path, followlinks=False):
        rel_dir = os.path.relpath(current, path)
        dir_path = Path(current)
        st = os.lstat(dir_path)
        out[rel_dir] = ("dir", st.st_mode)
        for name in dirs + files:
            child = dir_path / name
            rel = os.path.relpath(child, path)
            cst = os.lstat(child)
            if stat.S_ISLNK(cst.st_mode):
                out[rel] = ("symlink", os.readlink(child), cst.st_mtime_ns)
            elif stat.S_ISREG(cst.st_mode):
                out[rel] = ("file", child.read_bytes())
            elif stat.S_ISFIFO(cst.st_mode):
                out[rel] = ("fifo", cst.st_mode)
            elif stat.S_ISSOCK(cst.st_mode):
                out[rel] = ("sock", cst.st_mode)
            else:
                out[rel] = ("other", cst.st_mode)
    return out


def _stdout_payload(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    return payload


def _clone_mav_draft(tmp_path: Path) -> Path:
    document = json.loads(MINIMAL.read_text(encoding="utf-8"))
    document["paper_id"] = MAV
    document["title"] = "Make-A-Video"
    path = tmp_path / "mav.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _prepare_checkout(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    make_checkout(checkout)
    monkeypatch.chdir(checkout)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "secret.bin"
    sentinel.write_bytes(b"SENTINEL-BYTES")
    return checkout, external


@pytest.mark.parametrize(
    "batch_id",
    ["", "/tmp/out", "..", "../x", "a/b", "a\\b", "x" * 129],
)
def test_illegal_batch_id_does_not_touch_external(
    batch_id, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    sentinel = (external / "secret.bin").read_bytes()
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", batch_id])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_BATCH_ID"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == sentinel
    assert network_attempts == []


def test_malicious_paper_id_is_not_used_in_output_path(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    paper_id = "../../secret"
    code = main(
        [
            "draft",
            "export",
            "--sha256",
            digest,
            "--paper-id",
            paper_id,
            "--batch-id",
            "b1",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_PAPER_ID"
    assert paper_id not in json.dumps(payload.get("data", {}))
    assert not (checkout / ".work").exists() or paper_id not in str(
        list((checkout / ".work").rglob("*"))
    )
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_work_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    (checkout / ".work").symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_batch_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_intermediate_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    review_dir = checkout / ".work" / "b1" / "review"
    review_dir.parent.mkdir(parents=True)
    review_dir.symlink_to(external)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_target_symlink_refuses_and_leaves_sentinel(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    target = work_review(checkout, "b1")
    target.parent.mkdir(parents=True)
    target.symlink_to(external / "secret.bin")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_different_byte_target_is_conflict(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    target = work_review(checkout, "b1")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other-content")
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 75
    assert payload["error"]["code"] == "STAGING_CONFLICT"
    assert target.read_bytes() == b"other-content"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_fifo_and_special_files_are_unsafe(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    fifo_work = checkout / ".work"
    os.mkfifo(fifo_work)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert stat.S_ISFIFO(os.lstat(fifo_work).st_mode)
    os.unlink(fifo_work)
    work_dir = checkout / ".work" / "b1" / "review"
    work_dir.mkdir(parents=True)
    os.mkfifo(work_dir / "paper.md")
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_prepare_symlink_and_conflict_leave_external(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    (checkout / ".work").symlink_to(external)
    before = _snapshot(external)
    ref = write_json(checkout / "ref.json", {"format": "video-paper-wiki.approval-ref.v1"})
    code = main(
        [
            "ingest",
            "prepare",
            "--plan",
            str(checkout / ".work" / "b1" / "plan" / "ingest-plan.v1.json"),
            "--approval-ref",
            str(ref),
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "PLAN_PATH_UNSAFE"
    assert payload["error"]["details"].get("approval_hash_present") is not True
    assert "verified" not in payload["error"]["message"].lower()
    assert "human_approved" not in json.dumps(payload)
    assert _snapshot(external) == before
    assert network_attempts == []
    assert digest


def test_writable_commands_share_one_batch_tree(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    blob_root = checkout / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    plan = complete_ingest_plan(paper_source_request(batch_id="shared", local_sha256=digest))
    plan_path = stage_bytes(
        batch_id="shared",
        relative=("plan", "ingest-plan.v1.json"),
        data=canonicalize(plan),
    ).path
    ref_path = write_json(checkout / "shared.approval-ref.json", make_approval_ref(plan))
    code = main(
        [
            "ingest",
            "prepare",
            "--plan",
            str(plan_path),
            "--approval-ref",
            str(ref_path),
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    assert payload["data"]["already_staged"] is False
    assert payload["data"]["approval_ref_bound"] is True
    assert "approval_hash_present" not in payload["data"]
    staged = Path(payload["data"]["staged_path"])
    assert staged == work_prepared(checkout, "shared", digest)
    assert plan_path == work_plan(checkout, "shared")
    assert staged.is_file()
    code = main(
        [
            "draft",
            "export",
            "--sha256",
            digest,
            "--paper-id",
            MAV,
            "--batch-id",
            "shared",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    draft_path = Path(payload["data"]["path"])
    assert draft_path == work_draft(checkout, "shared")
    assert MAV not in draft_path.as_posix().split(".work", 1)[1]
    code = main(
        [
            "review",
            "export",
            "--draft",
            str(draft_path),
            "--batch-id",
            "shared",
        ]
    )
    payload = _stdout_payload(capsys)
    assert code == 0
    review_path = Path(payload["data"]["path"])
    assert review_path == work_review(checkout, "shared")
    assert MAV not in review_path.as_posix().split(".work", 1)[1]
    work = checkout / ".work" / "shared"
    assert staged.resolve().is_relative_to(work.resolve())
    assert draft_path.resolve().is_relative_to(work.resolve())
    assert review_path.resolve().is_relative_to(work.resolve())
    assert _snapshot(external) == before
    assert network_attempts == []


def test_no_network_clients_or_boundary_bypasses(network_attempts) -> None:
    concat_vault = False
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert_no_network_imports(text, filename=str(path))
        if path.parent.name == "commands":
            assert "vault" not in text, f"{path.name} contains lowercase vault"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "lower":
                # Command/path boundary tests must not be bypassed via .lower().
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    lowered = node.value.value.lower()
                    assert "vault" not in lowered
                    assert "wiki" not in lowered or node.value.value == node.value.value.lower()
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                chunks = []
                for part in (node.left, node.right):
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        chunks.append(part.value)
                joined = "".join(chunks).lower()
                if "vault" in joined:
                    concat_vault = True
    assert concat_vault is False
    staging = (SRC / "staging.py").read_text(encoding="utf-8")
    assert "paper_id" not in staging
    assert network_attempts == []


def test_resolved_path_outside_work_is_exactly_escape(
    tmp_path, monkeypatch, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    target = work / "b1" / ".." / ".." / "secret.md"
    with pytest.raises(StagingError) as exc:
        _assert_inside_work(target, work)
    assert exc.value.code == CODE_WORK_PATH_ESCAPE
    assert exc.value.code != CODE_WORK_PATH_UNSAFE
    assert not (external / "paper.md").exists()
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_intermediate_dir_swap_after_mkdir_is_unsafe(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    real_mkdir = os.mkdir

    def racing_mkdir(name, mode=0o777, **kwargs):
        result = real_mkdir(name, mode, **kwargs)
        review = checkout / ".work" / "b1" / "review"
        if name == "review" and review.is_dir() and not review.is_symlink():
            stolen = tmp_path / "stolen-review"
            review.rename(stolen)
            review.symlink_to(external)
        return result

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert not (external / "paper.md").exists()
    assert _snapshot(external) == before
    assert network_attempts == []


def test_intermediate_dir_swap_during_link_does_not_escape(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    review_dir = checkout / ".work" / "b1" / "review"
    review_dir.mkdir(parents=True)
    draft = _clone_mav_draft(checkout)
    real_link = os.link

    def racing_link(src, dst, *args, **kwargs):
        if review_dir.exists() and not review_dir.is_symlink():
            stolen = tmp_path / "stolen-review"
            review_dir.rename(stolen)
            review_dir.symlink_to(external)
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert not (external / "paper.md").exists()
    assert not (tmp_path / "stolen-review" / "paper.md").exists()
    assert _snapshot(external) == before
    assert network_attempts == []


def test_work_tree_steal_during_link_does_not_escape(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    review_dir = checkout / ".work" / "b1" / "review"
    review_dir.mkdir(parents=True)
    draft = _clone_mav_draft(checkout)
    real_link = os.link
    stolen = tmp_path / "stolen-work"

    def racing_link(src, dst, *args, **kwargs):
        work = checkout / ".work"
        if work.exists() and not work.is_symlink():
            work.rename(stolen)
            work.symlink_to(external)
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert not (external / "paper.md").exists()
    assert not (stolen / "b1" / "review" / "paper.md").exists()
    assert _snapshot(external) == before
    assert network_attempts == []


@pytest.mark.parametrize("slot", ["batch", "intermediate"])
@pytest.mark.parametrize("kind", ["fifo", "socket"])
def test_batch_or_intermediate_fifo_or_socket_is_unsafe_json(
    slot, kind, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    before = _snapshot(external)
    if slot == "batch":
        (checkout / ".work").mkdir()
        target = checkout / ".work" / "b1"
    else:
        (checkout / ".work" / "b1").mkdir(parents=True)
        target = checkout / ".work" / "b1" / "review"
    server = None
    if kind == "fifo":
        os.mkfifo(target)
    else:
        server = plant_unix_socket(target)
    try:
        draft = _clone_mav_draft(checkout)
        code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) == 1, captured.out
        payload = json.loads(lines[0])
        Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
        assert code == 2
        assert payload["ok"] is False
        assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
        assert _snapshot(external) == before
        assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
        assert network_attempts == []
    finally:
        if server is not None:
            server.close()


def test_batch_file_slot_is_unsafe_json_envelope(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    work = checkout / ".work"
    work.mkdir()
    (work / "b1").write_bytes(b"not-a-dir")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "NotADirectoryError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_intermediate_file_slot_is_unsafe_json_envelope(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    parent = checkout / ".work" / "b1"
    parent.mkdir(parents=True)
    (parent / "review").write_bytes(b"not-a-dir")
    before = _snapshot(external)
    draft = _clone_mav_draft(checkout)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "NotADirectoryError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
    assert _snapshot(external) == before
    assert network_attempts == []


def test_project_not_table_is_workspace_invalid_json(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text('project = "video-paper-wiki"\n', encoding="utf-8")
    monkeypatch.chdir(root)
    code = main(["seed", "render", "--batch-id", "invalid-project"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "AttributeError" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "WORKSPACE_ROOT_INVALID"
    assert network_attempts == []


def test_corrupt_engine_mvp_json_rejected_via_cli(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    draft = _clone_mav_draft(checkout)
    bad = tmp_path / "bad-engine-mvp.json"
    bad.write_bytes(b'{"papers": []}\n' + bytes([0xFF]))

    def fake_package(*parts: str):
        if parts and parts[-1] == "engine-mvp.json":
            return None
        return _package_text(*parts)

    def fake_repo(relative: Path):
        if Path(relative).name == "engine-mvp.json":
            return bad
        return _repo_file(relative)

    monkeypatch.setattr("video_paper_wiki.resources._package_text", fake_package)
    monkeypatch.setattr("video_paper_wiki.resources._repo_file", fake_repo)
    code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    payload = json.loads(lines[0])
    Draft202012Validator(json.loads(ENVELOPE.read_text(encoding="utf-8"))).validate(payload)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ENCODING"
    work = checkout / ".work"
    assert not work.exists() or list(work.rglob("*")) == []
    assert (external / "secret.bin").read_bytes() == b"SENTINEL-BYTES"
    assert network_attempts == []


def test_unix_socket_sentinel_unchanged(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    checkout, external = _prepare_checkout(tmp_path, monkeypatch)
    sock_path = external / "sentinel.sock"
    server = plant_unix_socket(sock_path)
    try:
        before = _snapshot(external)
        draft = _clone_mav_draft(checkout)
        (checkout / ".work").symlink_to(external)
        code = main(["review", "export", "--draft", str(draft), "--batch-id", "b1"])
        payload = _stdout_payload(capsys)
        assert code == 2
        assert payload["error"]["code"] == "WORK_PATH_UNSAFE"
        assert _snapshot(external) == before
        assert sock_path.exists()
    finally:
        server.close()
    assert network_attempts == []
