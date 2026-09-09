from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path

import pytest

from tests.support import (
    ROOT,
    code_evidence_request,
    complete_ingest_plan,
    make_approval_ref,
    make_checkout,
    paper_source_request,
    pdf_bytes,
    plant_blob,
    plant_unix_socket,
    work_plan,
    work_prepared,
    write_json,
)
from video_paper_wiki.cli import main
from video_paper_wiki.identity import plan_approval_hash
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.staging import stage_bytes
from tests.pdf_samples import sample_pdf_path

TINY_PDF = sample_pdf_path("tiny")


def _payload(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1, captured.out
    return json.loads(lines[0])


def _replace_same_bytes_with_distinct_inode(target: Path) -> tuple[tuple[int, int], tuple[int, int]]:
    """Atomically replace *target* after proving the sibling inode is distinct."""
    raw = target.read_bytes()
    before = target.stat(follow_symlinks=False)
    replacement = target.with_name(target.name + ".identity-replacement")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    try:
        fd = os.open(replacement, flags, stat.S_IMODE(before.st_mode))
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fsync(fd)
        os.fchmod(fd, stat.S_IMODE(before.st_mode))
        os.close(fd)
        fd = None
        os.utime(
            replacement,
            ns=(before.st_atime_ns, before.st_mtime_ns),
            follow_symlinks=False,
        )
        replacement_stat = replacement.stat(follow_symlinks=False)
        before_identity = (before.st_dev, before.st_ino)
        replacement_identity = (replacement_stat.st_dev, replacement_stat.st_ino)
        assert replacement_identity != before_identity
        assert stat.S_IMODE(replacement_stat.st_mode) == stat.S_IMODE(before.st_mode)
        assert replacement_stat.st_size == before.st_size == len(raw)
        assert replacement_stat.st_mtime_ns == before.st_mtime_ns
        os.replace(replacement, target)
        named = target.stat(follow_symlinks=False)
        assert (named.st_dev, named.st_ino) == replacement_identity
        assert target.read_bytes() == raw
        return before_identity, replacement_identity
    finally:
        if fd is not None:
            os.close(fd)
        try:
            replacement.unlink()
        except FileNotFoundError:
            pass


def _bind_plan(
    checkout: Path,
    request: dict,
    *,
    input_sha256: str | None = None,
) -> tuple[Path, Path, dict]:
    plan = complete_ingest_plan(request)
    staged = stage_bytes(
        batch_id=plan["batch_id"],
        relative=("plan", "ingest-plan.v1.json"),
        data=canonicalize(plan),
    )
    ref = make_approval_ref(plan, **({"input_sha256": input_sha256} if input_sha256 else {}))
    ref_path = write_json(checkout / f"{plan['batch_id']}.approval-ref.json", ref)
    return staged.path, ref_path, plan


def test_prepare_paper_success_same_fd_snapshot(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="p1", local_sha256=digest)
    plan_path, ref_path, plan = _bind_plan(tmp_path, request)
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 0
    payload = _payload(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "ingest.prepare"
    data_out = payload["data"]
    assert data_out["approval_ref_bound"] is True
    assert data_out["batch_id"] == "p1"
    assert data_out["sha256"] == digest
    assert data_out["byte_count"] == len(data)
    assert data_out["page_count"] == 1
    assert data_out["media_type"] == "application/pdf"
    assert data_out["plan_approval_hash"] == plan["approval_hash"]
    assert len(data_out["approval_ref_sha256"]) == 64
    assert data_out["already_staged"] is False
    assert "human_approved" not in data_out
    assert "approval_verified" not in data_out
    staged = Path(data_out["staged_path"])
    assert staged == work_prepared(tmp_path, "p1", digest)
    assert staged.read_bytes() == data
    request_path = Path(data_out["request_path"])
    assert request_path.name == "staged-pdf-capture-request.v1.json"
    request_bytes = request_path.read_bytes()
    assert data_out["request_sha256"] == __import__("hashlib").sha256(request_bytes).hexdigest()
    request = json.loads(request_bytes)
    assert request["approval_ref"]["input_sha256"] == digest
    assert request["payload"]["file"] == f"prepared/{digest}.blob"
    assert canonicalize(request) == request_bytes
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 0
    again = _payload(capsys)
    assert again["data"]["already_staged"] is True
    staged.unlink()
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 0
    repaired = _payload(capsys)
    assert repaired["data"]["already_staged"] is False
    assert staged.read_bytes() == data
    assert request_path.read_bytes() == request_bytes
    assert network_attempts == []


def test_code_map_prepare_opaque_no_unzip_or_pypdf(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, b"opaque-code-bytes")
    request = code_evidence_request(batch_id="c1")
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request, input_sha256=digest)

    def boom(*_a, **_k):
        raise AssertionError("pypdf must not run for code-evidence")

    monkeypatch.setattr("pypdf.PdfReader", boom)
    assert main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path), "--source-path", "src/model.py"]) == 0
    payload = _payload(capsys)
    assert payload["command"] == "code-map.prepare"
    assert payload["data"]["approval_ref_bound"] is True
    assert "page_count" not in payload["data"]
    assert Path(payload["data"]["staged_path"]).read_bytes() == b"opaque-code-bytes"
    assert main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path), "--source-path", "src/other.py"]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_KIND_MISMATCH"
    prepare_src = (ROOT / "src" / "video_paper_wiki" / "commands" / "prepare.py").read_text()
    assert "zipfile" not in prepare_src
    assert "subprocess" not in prepare_src
    assert network_attempts == []


def test_paper_prepare_request_conflict_leaves_exact_blob(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(tmp_path,paper_source_request(batch_id='pair-conflict',local_sha256=digest))
    request=tmp_path/'.work/pair-conflict/prepared/staged-pdf-capture-request.v1.json'
    request.parent.mkdir(parents=True); request.write_bytes(b'conflict')
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==75
    assert _payload(capsys)['error']['code']=='STAGING_CONFLICT'
    assert work_prepared(tmp_path,'pair-conflict',digest).read_bytes()==data
    assert request.read_bytes()==b'conflict'; assert network_attempts==[]


def test_arxiv_plan_without_local_sha_uses_external_ref_digest(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    request=paper_source_request(batch_id='arxiv-prepared',local_sha256=digest)
    request['input']={'kind':'arxiv','arxiv_id':'2311.15127','pdf_url':'https://arxiv.org/pdf/2311.15127'}
    plan_path,ref_path,_=_bind_plan(tmp_path,request,input_sha256=digest)
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==0
    value=_payload(capsys)['data']; prepared=json.loads(Path(value['request_path']).read_text())
    assert prepared['plan']['input_kind']=='arxiv'
    assert prepared['payload']['sha256']==digest
    assert network_attempts==[]


def test_paper_pair_refuses_plan_same_bytes_inode_replacement_between_installs(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(tmp_path,paper_source_request(batch_id='pair-race',local_sha256=digest))
    from video_paper_wiki import staging as staging_module
    real=staging_module._atomic_install
    def replace(*args,**kwargs):
        value=real(*args,**kwargs)
        target = kwargs.get('target')
        if isinstance(target, Path) and target.name == f'{digest}.blob':
            raw=plan_path.read_bytes(); plan_path.unlink(); plan_path.write_bytes(raw)
        return value
    monkeypatch.setattr(staging_module,'_atomic_install',replace)
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==2
    assert _payload(capsys)['error']['code']=='WORK_PATH_UNSAFE'
    assert work_prepared(tmp_path,'pair-race',digest).read_bytes()==data
    assert network_attempts==[]


def test_paper_pair_refuses_plan_replacement_before_request_construction(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(tmp_path,paper_source_request(batch_id='factory-race',local_sha256=digest))
    from video_paper_wiki.commands import prepare as prepare_module
    real=prepare_module._stage_prepared_pdf_capture
    def replace(**kwargs):
        raw=plan_path.read_bytes(); plan_path.unlink(); plan_path.write_bytes(raw)
        return real(**kwargs)
    monkeypatch.setattr(prepare_module,'_stage_prepared_pdf_capture',replace)
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==2
    assert _payload(capsys)['error']['code']=='WORK_PATH_UNSAFE'
    assert not (tmp_path/'.work/factory-race/prepared').exists()
    assert network_attempts==[]


def test_missing_blob_repair_refuses_existing_request_inode_replacement(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(tmp_path,paper_source_request(batch_id='repair-race',local_sha256=digest))
    argv=['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)]
    assert main(argv)==0; first=_payload(capsys)['data']
    blob=Path(first['staged_path']); request=Path(first['request_path']); blob.unlink()
    from video_paper_wiki import staging as staging_module
    real=staging_module._atomic_install
    def replace(*args,**kwargs):
        value=real(*args,**kwargs); target=kwargs.get('target')
        if isinstance(target,Path) and target.name==f'{digest}.blob':
            raw=request.read_bytes(); request.unlink(); request.write_bytes(raw)
        return value
    monkeypatch.setattr(staging_module,'_atomic_install',replace)
    assert main(argv)==2
    assert _payload(capsys)['error']['code']=='WORK_PATH_UNSAFE'
    assert blob.read_bytes()==data and network_attempts==[]


def test_missing_blob_install_refuses_same_bytes_inode_replacement(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(
        tmp_path, paper_source_request(batch_id='missing-blob-window',local_sha256=digest),
    )
    from video_paper_wiki import staging as staging_module
    real=staging_module._atomic_install
    identities=[]
    def replace(*args,**kwargs):
        value=real(*args,**kwargs); target=kwargs.get('target')
        if isinstance(target,Path) and target.name==f'{digest}.blob':
            identities.extend(_replace_same_bytes_with_distinct_inode(target))
        return value
    monkeypatch.setattr(staging_module,'_atomic_install',replace)
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==2
    assert _payload(capsys)['error']['code']=='WORK_PATH_UNSAFE'
    prepared=tmp_path/'.work/missing-blob-window/prepared'
    assert identities[0] != identities[1]
    assert not (prepared/'staged-pdf-capture-request.v1.json').exists()
    assert network_attempts==[]


def test_missing_request_install_refuses_same_bytes_inode_replacement(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path); monkeypatch.chdir(tmp_path)
    blob_root=tmp_path/'blobs'; monkeypatch.setenv('VPWIKI_BLOB_ROOT',str(blob_root))
    data=TINY_PDF.read_bytes(); digest=plant_blob(blob_root,data)
    plan_path,ref_path,_=_bind_plan(
        tmp_path, paper_source_request(batch_id='missing-request-window',local_sha256=digest),
    )
    from video_paper_wiki import staging as staging_module
    real=staging_module._atomic_install
    identities=[]
    def replace(*args,**kwargs):
        value=real(*args,**kwargs); target=kwargs.get('target')
        if isinstance(target,Path) and target.name=='staged-pdf-capture-request.v1.json':
            identities.extend(_replace_same_bytes_with_distinct_inode(target))
        return value
    monkeypatch.setattr(staging_module,'_atomic_install',replace)
    assert main(['ingest','prepare','--plan',str(plan_path),'--approval-ref',str(ref_path)])==2
    assert _payload(capsys)['error']['code']=='WORK_PATH_UNSAFE'
    prepared=tmp_path/'.work/missing-request-window/prepared'
    assert identities[0] != identities[1]
    assert (prepared/f'{digest}.blob').read_bytes()==data
    assert network_attempts==[]


@pytest.mark.parametrize("family", ["ingest", "code-map"])
@pytest.mark.parametrize("flag", ["--sha256", "--approval-hash", "--batch-id", "--work-dir"])
def test_old_prepare_flags_are_usage(family, flag, tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    argv = [family, "prepare", flag, "x"]
    assert main(argv) == 2
    payload = _payload(capsys)
    assert payload["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_prepare_missing_flags_are_usage(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["ingest", "prepare"]) == 2
    assert _payload(capsys)["error"]["code"] == "USAGE"
    assert network_attempts == []


def test_prepare_plan_not_found_and_unsafe_paths(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    ref = tmp_path / "ref.json"
    ref.write_text("{}", encoding="utf-8")
    assert main(
        [
            "ingest",
            "prepare",
            "--plan",
            str(tmp_path / ".work" / "p1" / "plan" / "ingest-plan.v1.json"),
            "--approval-ref",
            str(ref),
        ]
    ) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_NOT_FOUND"

    outside = tmp_path / "outside.json"
    write_json(outside, {"schema": "video-paper-wiki.ingest-plan.v1"})
    assert main(["ingest", "prepare", "--plan", str(outside), "--approval-ref", str(ref)]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_PATH_UNSAFE"
    assert network_attempts == []


@pytest.mark.parametrize("family", ["ingest", "code-map"])
@pytest.mark.parametrize("schema_value", [{}, []])
def test_prepare_non_string_plan_schema_is_a_refusal(
    family, schema_value, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    request = (
        paper_source_request(local_sha256="a" * 64)
        if family == "ingest"
        else code_evidence_request()
    )
    plan_path, ref_path, plan = _bind_plan(tmp_path, request, input_sha256="a" * 64)
    plan["schema"] = schema_value
    write_json(plan_path, plan)
    original_bytes = plan_path.read_bytes()

    argv = [family, "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]
    if family == "code-map": argv += ["--source-path", "src/model.py"]
    code = main(argv)
    payload = _payload(capsys)
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] == f"{family}.prepare"
    assert payload["error"]["code"] == "SCHEMA_INVALID"
    assert payload["error"]["details"]["instance_pointer"] == "/schema"
    assert not (tmp_path / ".work" / plan["batch_id"] / "prepared").exists()
    assert plan_path.read_bytes() == original_bytes
    assert network_attempts == []


def _plant_special(path: Path, kind: str) -> socket.socket | None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()
    server = None
    if kind == "symlink":
        path.symlink_to("missing-target")
    elif kind == "dir":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "socket":
        server = plant_unix_socket(path)
    elif kind == "device":
        os.symlink("/dev/null", path)
    return server


def _clear_special(path: Path, server: socket.socket | None) -> None:
    if server is not None:
        server.close()
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()


@pytest.mark.parametrize("kind", ["symlink", "dir", "fifo", "socket", "device"])
def test_plan_ref_blob_special_files(kind, tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="sp1", local_sha256=digest)
    plan_path, ref_path, plan = _bind_plan(tmp_path, request)
    plan_bytes = plan_path.read_bytes()
    ref_obj = make_approval_ref(plan)

    server = _plant_special(plan_path, kind)
    try:
        code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
        payload = _payload(capsys)
        assert code == 2
        assert payload["error"]["code"] == "PLAN_PATH_UNSAFE"
    finally:
        _clear_special(plan_path, server)
    plan_path.write_bytes(plan_bytes)

    server = _plant_special(ref_path, kind)
    try:
        code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
        payload = _payload(capsys)
        assert code == 2
        assert payload["error"]["code"] == "APPROVAL_REF_INVALID"
    finally:
        _clear_special(ref_path, server)
    write_json(ref_path, ref_obj)

    blob_path = blob_root / digest
    server = _plant_special(blob_path, kind)
    try:
        code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
        payload = _payload(capsys)
        assert code == 2
        assert payload["error"]["code"] == "BLOB_PATH_UNSAFE"
    finally:
        _clear_special(blob_path, server)
    assert network_attempts == []


def test_plan_and_ref_device_path_dev_null(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    ref = tmp_path / "ref.json"
    ref.write_text("{}", encoding="utf-8")
    assert main(["ingest", "prepare", "--plan", "/dev/null", "--approval-ref", str(ref)]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_PATH_UNSAFE"
    digest = plant_blob(tmp_path / "blobs", TINY_PDF.read_bytes())
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    request = paper_source_request(batch_id="dev1", local_sha256=digest)
    plan_path, _ref_path, _plan = _bind_plan(tmp_path, request)
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", "/dev/null"]) == 2
    assert _payload(capsys)["error"]["code"] == "APPROVAL_REF_INVALID"
    assert network_attempts == []


def test_blob_root_symlink_and_wrong_bytes(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    real_root = tmp_path / "real-blobs"
    digest = plant_blob(real_root, TINY_PDF.read_bytes())
    linked = tmp_path / "linked-blobs"
    linked.symlink_to(real_root)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(linked))
    request = paper_source_request(batch_id="sy1", local_sha256=digest)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 2
    assert _payload(capsys)["error"]["code"] == "BLOB_PATH_UNSAFE"

    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(real_root))
    blob = real_root / digest
    blob.write_bytes(b"%PDF-not-the-same")
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 2
    assert _payload(capsys)["error"]["code"] == "BLOB_HASH_MISMATCH"
    assert network_attempts == []


def test_blob_missing_and_family_mismatch(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(tmp_path / "blobs"))
    digest = "a" * 64
    request = paper_source_request(batch_id="m1", local_sha256=digest)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 2
    assert _payload(capsys)["error"]["code"] == "BLOB_NOT_FOUND"
    assert main(["code-map", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path), "--source-path", "src/model.py"]) == 2
    assert _payload(capsys)["error"]["code"] == "PLAN_KIND_MISMATCH"
    assert network_attempts == []


def test_pdf_magic_truncated_encrypted_zero_page_and_limits(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))

    def run(data: bytes, *, max_pages: int = 10, max_bytes: int = 50_000_000, batch: str) -> dict:
        digest = plant_blob(blob_root, data)
        request = paper_source_request(
            batch_id=batch, local_sha256=digest, max_pages=max_pages, max_bytes=max_bytes
        )
        plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
        code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
        payload = _payload(capsys)
        payload["_code"] = code
        return payload

    bad_magic = run(b"not-a-pdf", batch="bad-magic")
    assert bad_magic["_code"] == 2
    assert bad_magic["error"]["code"] == "MEDIA_TYPE_INVALID"

    truncated = run(b"%PDF-1.4\n", batch="trunc")
    assert truncated["_code"] == 2
    assert truncated["error"]["code"] == "PDF_INVALID"

    encrypted = run(pdf_bytes(pages=1, encrypt=True), batch="enc")
    assert encrypted["_code"] == 2
    assert encrypted["error"]["code"] == "PDF_INVALID"

    zero = run(pdf_bytes(pages=0), batch="zero")
    assert zero["_code"] == 2
    assert zero["error"]["code"] == "PDF_INVALID"

    over_pages = run(pdf_bytes(pages=2), max_pages=1, batch="pages")
    assert over_pages["_code"] == 2
    assert over_pages["error"]["code"] == "PAGE_LIMIT_EXCEEDED"

    over_bytes = run(TINY_PDF.read_bytes(), max_bytes=8, batch="bytes")
    assert over_bytes["_code"] == 2
    assert over_bytes["error"]["code"] == "BLOB_LIMIT_EXCEEDED"
    assert network_attempts == []


def test_prepare_conflict_and_approval_ref_not_found(
    tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="cf1", local_sha256=digest)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    stage_bytes(batch_id="cf1", relative=("prepared", f"{digest}.blob"), data=b"other-bytes")
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 75
    assert _payload(capsys)["error"]["code"] == "STAGING_CONFLICT"
    missing = tmp_path / "missing-ref.json"
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(missing)]) == 2
    assert _payload(capsys)["error"]["code"] == "APPROVAL_REF_NOT_FOUND"
    assert network_attempts == []


def test_source_has_no_follow_helpers() -> None:
    for relative in (
        "src/video_paper_wiki/blob_store.py",
        "src/video_paper_wiki/secure_io.py",
        "src/video_paper_wiki/commands/prepare.py",
    ):
        text = Path(relative).read_text(encoding="utf-8")
        assert "is_file(" not in text
        assert "read_bytes(" not in text
        assert "copy2" not in text


def test_prepare_missing_pipeline_fingerprint(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="fp1", local_sha256=digest)
    plan = complete_ingest_plan(request)
    plan.pop("pipeline_fingerprint")
    plan["approval_hash"] = plan_approval_hash(plan)
    staged = stage_bytes(
        batch_id=plan["batch_id"],
        relative=("plan", "ingest-plan.v1.json"),
        data=canonicalize(plan),
    )
    ref = make_approval_ref(plan)
    ref_path = write_json(tmp_path / "fp1.approval-ref.json", ref)
    code = main(["ingest", "prepare", "--plan", str(staged.path), "--approval-ref", str(ref_path)])
    payload = _payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "PIPELINE_FINGERPRINT_MISMATCH"
    assert network_attempts == []


def test_prepare_ref_only_fingerprint_mismatch(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    request = paper_source_request(batch_id="fp2", local_sha256=digest)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    ref["pipeline_fingerprint"] = "e" * 64
    write_json(ref_path, ref)
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    payload = _payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "APPROVAL_REF_MISMATCH"
    assert payload["error"]["details"]["field"] == "pipeline_fingerprint"
    assert network_attempts == []


def _race_child_open(monkeypatch, path: Path, mutator) -> None:
    real_open = os.open
    replaced = {"done": False}

    def racing_open(name, flags, *args, **kwargs):
        result_name = name if isinstance(name, str) else os.fsdecode(name)
        if (
            result_name == path.name
            and not replaced["done"]
            and kwargs.get("dir_fd") is not None
            and not (flags & getattr(os, "O_DIRECTORY", 0))
        ):
            replaced["done"] = True
            mutator(path)
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", racing_open)


@pytest.mark.parametrize("target", ["plan", "ref", "blob"])
@pytest.mark.parametrize("kind", ["delete", "symlink", "dir", "fifo"])
def test_prepare_lstat_open_race_is_source_changed(
    target, kind, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = TINY_PDF.read_bytes()
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="race1", local_sha256=digest)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    blob_path = blob_root / digest
    path = {"plan": plan_path, "ref": ref_path, "blob": blob_path}[target]

    def mutate(current: Path) -> None:
        if current.exists() or current.is_symlink():
            if current.is_dir() and not current.is_symlink():
                current.rmdir()
            else:
                current.unlink()
        if kind == "delete":
            return
        if kind == "symlink":
            current.symlink_to("missing-target")
        elif kind == "dir":
            current.mkdir()
        elif kind == "fifo":
            os.mkfifo(current)

    _race_child_open(monkeypatch, path, mutate)
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    payload = _payload(capsys)
    assert code == 75
    assert payload["error"]["code"] == "SOURCE_CHANGED"
    assert payload["error"]["code"] not in {
        "BLOB_NOT_FOUND",
        "PLAN_NOT_FOUND",
        "PLAN_PATH_UNSAFE",
        "BLOB_PATH_UNSAFE",
        "APPROVAL_REF_INVALID",
        "APPROVAL_REF_NOT_FOUND",
    }
    assert network_attempts == []


@pytest.mark.parametrize("kind", ["duplicate", "float", "nan", "utf8"])
def test_approval_ref_strict_json_is_invalid(
    kind, tmp_path, monkeypatch, capsys, network_attempts
) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    digest = plant_blob(blob_root, TINY_PDF.read_bytes())
    request = paper_source_request(batch_id="refbad", local_sha256=digest)
    plan_path, ref_path, plan = _bind_plan(tmp_path, request)
    good = json.dumps(make_approval_ref(plan), separators=(",", ":"))
    if kind == "duplicate":
        ref_path.write_text(good[:-1] + ',"format":"video-paper-wiki.approval-ref.v1"}', encoding="utf-8")
    elif kind == "float":
        ref_path.write_text('{"format":1.5}', encoding="utf-8")
    elif kind == "nan":
        ref_path.write_text('{"format":NaN}', encoding="utf-8")
    else:
        ref_path.write_bytes(b'{"format":"x"\xff}')
    code = main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)])
    payload = _payload(capsys)
    assert code == 2
    assert payload["error"]["code"] == "APPROVAL_REF_INVALID"
    assert network_attempts == []


def test_hard_byte_cap_monkeypatch(tmp_path, monkeypatch, capsys, network_attempts) -> None:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("video_paper_wiki.commands.prepare.HARD_MAX_BYTES", 16)
    blob_root = tmp_path / "blobs"
    monkeypatch.setenv("VPWIKI_BLOB_ROOT", str(blob_root))
    data = b"%PDF-" + b"x" * 32
    digest = plant_blob(blob_root, data)
    request = paper_source_request(batch_id="cap1", local_sha256=digest, max_bytes=50_000_000)
    plan_path, ref_path, _plan = _bind_plan(tmp_path, request)
    assert main(["ingest", "prepare", "--plan", str(plan_path), "--approval-ref", str(ref_path)]) == 2
    assert _payload(capsys)["error"]["code"] == "BLOB_LIMIT_EXCEEDED"
    assert network_attempts == []
