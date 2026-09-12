from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_backup import create_backup, restore_backup, verify_backup
from video_paper_wiki_research.light_index import build_index
from video_paper_wiki_research.light_library import archive_paper
from video_paper_wiki_research.light_library_state import (
    LIGHT_BACKUP_CONFLICT,
    LIGHT_BACKUP_INVALID,
    LIGHT_LIBRARY_NEEDS_RECOVERY,
    set_library_inject_hook,
)
from video_paper_wiki_research.light_pdf import extract_pdf
from video_paper_wiki_research.light_workflow import prepare_workflow, workflow_status


def _workspace(tmp_path: Path, name: str = "ws") -> Path:
    root = tmp_path / ".work" / name
    root.mkdir(parents=True)
    return root


def _add(tmp_path: Path, workspace: Path, name: str, text: str) -> dict:
    pdf = _write_pdf(tmp_path / f"{name}.pdf", _pdf_with_page_texts([text]))
    result = extract_pdf(pdf, workspace, title=name)
    assert result["ok"] is True
    return result


def _output(tmp_path: Path, name: str = "backup.zip") -> Path:
    folder = tmp_path / ".work" / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def _zip_flags(path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        return [{"filename": info.filename, "flag_bits": info.flag_bits} for info in archive.infolist()]


def _mutate_zip_flags(source: Path, target: Path, *, local: int, central: int) -> None:
    data = bytearray(source.read_bytes())
    cursor = 0
    local_count = central_count = 0
    while cursor < len(data):
        local_at = data.find(b"PK\x03\x04", cursor)
        central_at = data.find(b"PK\x01\x02", cursor)
        choices = [(at, "local") for at in (local_at,) if at >= 0]
        choices.extend((at, "central") for at in (central_at,) if at >= 0)
        if not choices:
            break
        at, kind = min(choices)
        if kind == "local":
            data[at + 6 : at + 8] = struct.pack("<H", local)
            local_count += 1
        else:
            data[at + 8 : at + 10] = struct.pack("<H", central)
            central_count += 1
        cursor = at + 4
    assert local_count >= 2 and central_count >= 2, (local_count, central_count)
    target.write_bytes(data)


def _mutate_zip_name(source: Path, target: Path, *, old: str) -> None:
    data = bytearray(source.read_bytes())
    encoded = old.encode("utf-8")
    replacement = b"papers/fixture/notes-\xff\xfe-\xe4\xb8\xad\xe6\x96\x87.md"
    assert len(encoded) == len(replacement)
    changed = 0
    cursor = 0
    while cursor < len(data):
        local_at = data.find(b"PK\x03\x04", cursor)
        central_at = data.find(b"PK\x01\x02", cursor)
        choices = [(at, "local") for at in (local_at,) if at >= 0]
        choices.extend((at, "central") for at in (central_at,) if at >= 0)
        if not choices:
            break
        at, kind = min(choices)
        name_len_offset = at + (26 if kind == "local" else 28)
        name_offset = at + (30 if kind == "local" else 46)
        name_len = struct.unpack_from("<H", data, name_len_offset)[0]
        if bytes(data[name_offset : name_offset + name_len]) == encoded:
            data[name_offset : name_offset + name_len] = replacement
            changed += 1
        cursor = at + 4
    assert changed == 2, changed
    target.write_bytes(data)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            payload[str(path.relative_to(root))] = path.read_bytes()
    return payload


def test_backup_exclusions_and_byte_exact_restore(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    added = _add(tmp_path, workspace, "bk", "Backup lexical body token.")
    paper_id = added["paper_id"]
    Path(added["markdown_path"]).parent.joinpath("notes.md").write_text("workspace note\n", encoding="utf-8")
    (workspace / "reports").mkdir()
    (workspace / "reports" / "draft.md").write_text("inside report\n", encoding="utf-8")
    built = build_index(workspace)
    assert built["ok"] is True
    prepared = prepare_workflow(workspace, kind="writing", query="Backup lexical", paper_ids=[paper_id])
    assert prepared["ok"] is True
    session_dir = Path(prepared["context_path"]).parent
    session_files = {name: (session_dir / name).read_bytes() for name in ("request.json", "context.json", "manifest.json")}
    extra = tmp_path / ".work" / "external.md"
    extra.write_text("external draft\n", encoding="utf-8")
    output = _output(tmp_path)
    created = create_backup(workspace, output=output, extra_outputs=[extra])
    assert created["ok"] is True
    assert created["reused"] is False
    excluded = {item["path"] for item in created["exclusions"]}
    assert any(path.endswith("index.v1.json") or path.startswith(".light-index") for path in excluded)
    verified = verify_backup(output)
    assert verified["ok"] is True
    assert verified["workspace_id"] == created["workspace_id"]
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "LIGHT-LIBRARY-MANIFEST.json"
        assert all(not name.endswith("/") for name in names)
        assert ".light-index/index.v1.json" not in names
        history_prefix = f".light-workflow/history/{created['workspace_id']}/sessions/"
        assert any(name.startswith(history_prefix) for name in names)
        assert not any(name.startswith(".light-workflow/sessions/") for name in names)
        info = archive.getinfo(history_prefix + f"{session_dir.name}/context.json")
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.compress_type == zipfile.ZIP_STORED
    dest = tmp_path / ".work" / "restored"
    restored = restore_backup(output, destination=dest)
    assert restored["ok"] is True
    new_paper = dest / "papers" / paper_id.split(":", 1)[1]
    assert (new_paper / "notes.md").read_bytes() == b"workspace note\n"
    assert (new_paper / "source.md").read_bytes() == Path(added["markdown_path"]).read_bytes()
    assert (dest / "reports" / "draft.md").read_text(encoding="utf-8") == "inside report\n"
    hist = Path(restored["historical_session_root"])
    assert hist.is_dir()
    for name, data in session_files.items():
        assert (hist / session_dir.name / name).read_bytes() == data
    assert not (dest / ".light-workflow" / "sessions").exists() or not any((dest / ".light-workflow" / "sessions").iterdir())
    status = workflow_status(dest)
    assert status["ok"] is True
    assert status["sessions"] == []
    exported = dest / "exports" / "external" / created["extra_outputs"][0]["hash"] / "external.md"
    assert exported.read_text(encoding="utf-8") == "external draft\n"
    assert not (dest / ".light-index" / "index.v1.json").exists()
    empty_conflict = restore_backup(output, destination=dest)
    assert empty_conflict["ok"] is False
    assert empty_conflict["status"] == LIGHT_BACKUP_CONFLICT


def test_backup_refuses_pending_and_binary_and_links(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "unsafe")
    added = _add(tmp_path, workspace, "bad", "Unsafe backup body.")
    paper_id = added["paper_id"]

    def _stop(_point: str) -> None:
        raise RuntimeError("leave pending archive")

    set_library_inject_hook("after_intent", _stop)
    with pytest.raises(RuntimeError, match="leave pending archive"):
        archive_paper(workspace, paper_id)
    set_library_inject_hook(None)
    pending = create_backup(workspace, output=_output(tmp_path, "pending.zip"))
    assert pending["ok"] is False
    assert pending["status"] in {LIGHT_LIBRARY_NEEDS_RECOVERY, LIGHT_BACKUP_INVALID}

    workspace2 = _workspace(tmp_path, "binary")
    added2 = _add(tmp_path, workspace2, "bin", "Binary extra body.")
    (Path(added2["markdown_path"]).parent / "secret.pdf").write_bytes(b"%PDF-1.4 extra")
    binary = create_backup(workspace2, output=_output(tmp_path, "binary.zip"))
    assert binary["ok"] is False
    assert binary["status"] == LIGHT_BACKUP_INVALID

    workspace3 = _workspace(tmp_path, "link")
    added3 = _add(tmp_path, workspace3, "lnk", "Symlink extra body.")
    (Path(added3["markdown_path"]).parent / "alias.md").symlink_to("notes.md")
    linked = create_backup(workspace3, output=_output(tmp_path, "link.zip"))
    assert linked["ok"] is False

    workspace4 = _workspace(tmp_path, "hard")
    added4 = _add(tmp_path, workspace4, "hl", "Hardlink extra body.")
    src = Path(added4["markdown_path"]).parent / "notes.md"
    src.write_text("note\n", encoding="utf-8")
    os.link(src, Path(added4["markdown_path"]).parent / "copy.md")
    hard = create_backup(workspace4, output=_output(tmp_path, "hard.zip"))
    assert hard["ok"] is False


def test_backup_oversize_tamper_and_create_only(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "size")
    added = _add(tmp_path, workspace, "sz", "Oversize body.")
    huge = Path(added["markdown_path"]).parent / "huge.txt"
    huge.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    oversize = create_backup(workspace, output=_output(tmp_path, "huge.zip"))
    assert oversize["ok"] is False
    assert oversize["status"] == LIGHT_BACKUP_INVALID
    huge.unlink()
    (Path(added["markdown_path"]).parent / "notes.md").write_text("ok\n", encoding="utf-8")
    output = _output(tmp_path, "good.zip")
    first = create_backup(workspace, output=output)
    assert first["ok"] is True
    reused = create_backup(workspace, output=output)
    assert reused["ok"] is True
    assert reused["reused"] is True
    (Path(added["markdown_path"]).parent / "notes.md").write_text("changed\n", encoding="utf-8")
    conflict = create_backup(workspace, output=output)
    assert conflict["ok"] is False
    assert conflict["status"] == LIGHT_BACKUP_CONFLICT
    assert output.read_bytes() == Path(first["archive_path"]).read_bytes()
    with zipfile.ZipFile(output, "r") as original:
        members = {info.filename: original.read(info.filename) for info in original.infolist()}
    target = next(name for name in members if name.endswith("notes.md"))
    members[target] = b"tampered notes\n"
    from video_paper_wiki_research.light_backup import _zip_info

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, data in members.items():
            archive.writestr(_zip_info(name), data)
    bad = verify_backup(output)
    assert bad["ok"] is False
    assert bad["status"] == LIGHT_BACKUP_INVALID


def test_backup_source_race_is_detected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "race")
    added = _add(tmp_path, workspace, "race", "Race body.")
    note = Path(added["markdown_path"]).parent / "notes.md"
    note.write_text("before\n", encoding="utf-8")

    def _flip(_point: str) -> None:
        note.write_text("after\n", encoding="utf-8")

    set_library_inject_hook("after_backup_snapshot", _flip)
    result = create_backup(workspace, output=_output(tmp_path, "race.zip"))
    set_library_inject_hook(None)
    assert result["ok"] is False
    assert result["status"] == LIGHT_BACKUP_CONFLICT
    assert not (_output(tmp_path, "race.zip")).exists()


def test_backup_rejects_output_inside_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "inside")
    _add(tmp_path, workspace, "in", "Inside output body.")
    with pytest.raises(ResearchError):
        create_backup(workspace, output=workspace / "out.zip")


def test_verify_refuses_traversal_and_internal_extra(tmp_path: Path) -> None:
    from video_paper_wiki_research.light_backup import _zip_info

    archive = _output(tmp_path, "traverse.zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as zf:
        zf.writestr(_zip_info("LIGHT-LIBRARY-MANIFEST.json"), b"{}\n")
        zf.writestr(_zip_info("../evil.md"), b"no\n")
    bad = verify_backup(archive)
    assert bad["ok"] is False
    assert bad["status"] == LIGHT_BACKUP_INVALID
    workspace = _workspace(tmp_path, "extra-in")
    _add(tmp_path, workspace, "ex", "Extra inside body.")
    inside = workspace / "reports"
    inside.mkdir()
    report = inside / "dup.md"
    report.write_text("already inside\n", encoding="utf-8")
    refused = create_backup(workspace, output=_output(tmp_path, "dup.zip"), extra_outputs=[report])
    assert refused["ok"] is False
    assert refused["status"] == LIGHT_BACKUP_INVALID


def test_backup_rechecks_after_archive_construction_before_publish(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "recheck")
    (workspace / "notes.md").write_text("# Tiny archive fixture\n", encoding="utf-8")
    output = _output(tmp_path, "recheck.zip")
    note = workspace / "notes.md"
    set_library_inject_hook("before_backup_publish", lambda _point: note.write_text("Changed just before publication\n", encoding="utf-8"))
    result = create_backup(workspace, output=output)
    set_library_inject_hook(None)
    assert result["ok"] is False
    assert not output.exists()
    assert note.read_text(encoding="utf-8") == "Changed just before publication\n"


def test_restore_preserves_existing_archived_restoration_record(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "restore-rec")
    original = b'{"user_record":"preserve the original record"}\n'
    record = workspace / ".light-library" / "restoration.json"
    record.parent.mkdir()
    record.write_bytes(original)
    output = _output(tmp_path, "record.zip")
    created = create_backup(workspace, output=output)
    assert created["ok"] is True
    restored = tmp_path / ".work" / "restored-record"
    result = restore_backup(output, destination=restored)
    if result.get("ok") is True:
        assert (restored / ".light-library" / "restoration.json").read_bytes() == original
    else:
        assert not restored.exists()


def test_backup_of_restored_workspace_preserves_prior_record(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "cycle")
    (workspace / "notes.md").write_text("cycle note\n", encoding="utf-8")
    first = _output(tmp_path, "first.zip")
    created = create_backup(workspace, output=first)
    assert created["ok"] is True
    first_root = tmp_path / ".work" / "first-restore"
    restored = restore_backup(first, destination=first_root)
    assert restored["ok"] is True
    before = {p.relative_to(first_root).as_posix(): p.read_bytes() for p in first_root.rglob("*") if p.is_file()}
    second = _output(tmp_path, "second.zip")
    again = create_backup(first_root, output=second)
    assert again["ok"] is True
    second_root = tmp_path / ".work" / "second-restore"
    second_restored = restore_backup(second, destination=second_root)
    assert second_restored["ok"] is True
    for relative, data in before.items():
        assert (second_root / relative).read_bytes() == data, relative


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _rewrite_archive(source: Path, destination: Path, *, manifest_edit=None, info_edit=None) -> None:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        manifest = json.loads(archive.read(infos[0]))
        payloads = {info.filename: archive.read(info) for info in infos[1:]}
    if manifest_edit:
        manifest_edit(manifest)
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as out:
        for index, original_info in enumerate(infos):
            info = copy.copy(original_info)
            if info_edit:
                info_edit(info, index)
            data = _canonical(manifest) + b"\n" if index == 0 else payloads[original_info.filename]
            out.writestr(info, data)


@pytest.mark.parametrize("field", ["workspace-id", "workspace-root", "extra-row", "exclusions", "trailing-nonobject-file"])
def test_verify_validates_all_manifest_identity_and_rows(tmp_path: Path, field: str) -> None:
    workspace = _workspace(tmp_path, "manifest")
    (workspace / "notes.md").write_text("manifest note\n", encoding="utf-8")
    source = _output(tmp_path, "valid-manifest.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    target = source.with_name("invalid-manifest.zip")

    def edit(manifest: dict) -> None:
        if field == "workspace-id":
            manifest["workspace_id"] = "0" * 64
            manifest["restore_remaps"] = {".light-workflow/sessions/": ".light-workflow/history/" + "0" * 64 + "/sessions/"}
        elif field == "workspace-root":
            manifest["workspace_root"] = ["not", "a", "path"]
        elif field == "extra-row":
            manifest["extra_outputs"] = [
                {
                    "original_path": "/unrelated.md",
                    "archive_path": "../x.md",
                    "restore_path": "../x.md",
                    "hash": "wrong",
                }
            ]
        elif field == "exclusions":
            manifest["exclusions"] = "invalid-shape"
        else:
            manifest["files"].append(None)

    _rewrite_archive(source, target, manifest_edit=edit)
    bad = verify_backup(target)
    assert bad.get("ok") is False
    destination = tmp_path / ".work" / "invalid-restore"
    refused = restore_backup(target, destination=destination)
    assert refused.get("ok") is False
    assert not destination.exists()


@pytest.mark.parametrize("variant", ["symlink-mode", "public-mode", "manifest-time", "extra-field", "zip64-version"])
def test_verify_enforces_fixed_zip_member_metadata(tmp_path: Path, variant: str) -> None:
    workspace = _workspace(tmp_path, "zipmeta")
    (workspace / "notes.md").write_text("zip meta note\n", encoding="utf-8")
    source = _output(tmp_path, "valid-meta.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    target = source.with_name("invalid-metadata.zip")

    def edit(info: zipfile.ZipInfo, index: int) -> None:
        if variant == "manifest-time" and index == 0:
            info.date_time = (2025, 1, 1, 0, 0, 0)
        elif index == 1:
            if variant == "symlink-mode":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            elif variant == "public-mode":
                info.external_attr = (stat.S_IFREG | 0o666) << 16
            elif variant == "extra-field":
                info.extra = b"\x01\x00\x00\x00"
            elif variant == "zip64-version":
                info.extract_version = 45

    _rewrite_archive(source, target, info_edit=edit)
    bad = verify_backup(target)
    assert bad.get("ok") is False


def test_backup_input_chain_cannot_traverse_symlink(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "alias")
    (workspace / "notes.md").write_text("alias note\n", encoding="utf-8")
    archive = _output(tmp_path, "alias-src.zip")
    created = create_backup(workspace, output=archive)
    assert created["ok"] is True
    alias = archive.parent / "alias"
    alias.symlink_to(archive.parent, target_is_directory=True)
    with pytest.raises(ResearchError):
        verify_backup(alias / archive.name)


@pytest.mark.parametrize("root", ["relative/.work/library", "/tmp/.work/../foreign", "/tmp//.work/library"])
def test_manifest_original_root_requires_absolute_normalized_path(tmp_path: Path, root: str) -> None:
    workspace = _workspace(tmp_path, "root")
    (workspace / "notes.md").write_text("# Tiny archive fixture\n", encoding="utf-8")
    source = _output(tmp_path, "valid-root.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    target = source.with_name("invalid-root.zip")

    def edit(manifest: dict) -> None:
        manifest["workspace_root"] = root
        identity = hashlib.sha256(_canonical({"workspace_root": root})).hexdigest()
        manifest["workspace_id"] = identity
        manifest["restore_remaps"] = {".light-workflow/sessions/": ".light-workflow/history/" + identity + "/sessions/"}

    _rewrite_archive(source, target, manifest_edit=edit)
    assert verify_backup(target).get("ok") is False


@pytest.mark.parametrize("variant", ["unsafe-path", "invented-rule", "included-file"])
def test_manifest_exclusions_are_actual_known_policy_rows(tmp_path: Path, variant: str) -> None:
    workspace = _workspace(tmp_path, "excl")
    (workspace / "notes.md").write_text("exclusion note\n", encoding="utf-8")
    source = _output(tmp_path, "valid-excl.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    target = source.with_name("invalid-exclusion.zip")

    def edit(manifest: dict) -> None:
        if variant == "unsafe-path":
            manifest["exclusions"] = [{"path": "../../private.md", "rule": "anything"}]
        elif variant == "invented-rule":
            manifest["exclusions"] = [{"path": ".light-index", "rule": "invented policy"}]
        else:
            manifest["exclusions"] = [{"path": "notes.md", "rule": "stable-lock"}]

    _rewrite_archive(source, target, manifest_edit=edit)
    assert verify_backup(target).get("ok") is False


@pytest.mark.parametrize("variant", ["wrong-basename", "inside-workspace", "relative-original", "non-markdown-original"])
def test_manifest_extra_mapping_matches_explicit_external_markdown(tmp_path: Path, variant: str) -> None:
    workspace = _workspace(tmp_path, "extra-map")
    (workspace / "notes.md").write_text("extra map note\n", encoding="utf-8")
    extra = tmp_path / "explicit.md"
    extra.write_text("# Explicit external output\n", encoding="utf-8")
    source = _output(tmp_path, "external.zip")
    created = create_backup(workspace, output=source, extra_outputs=[extra])
    assert created["ok"] is True
    target = source.with_name("invalid-extra.zip")

    def edit(manifest: dict) -> None:
        row = manifest["extra_outputs"][0]
        row["original_path"] = {
            "wrong-basename": str(extra.with_name("different.md")),
            "inside-workspace": str(workspace / "explicit.md"),
            "relative-original": "explicit.md",
            "non-markdown-original": str(extra.with_suffix(".pdf")),
        }[variant]

    _rewrite_archive(source, target, manifest_edit=edit)
    assert verify_backup(target).get("ok") is False


def test_positive_deterministic_backup_roundtrip_with_outside_work_extra(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "extra-pos")
    (workspace / "notes.md").write_text("# Tiny archive fixture\n", encoding="utf-8")
    extra = tmp_path / "outside-work.md"
    extra.write_text("# Explicit external output\n", encoding="utf-8")
    assert ".work" not in extra.parts
    source = _output(tmp_path, "valid-extra.zip")
    first = create_backup(workspace, output=source, extra_outputs=[extra])
    assert first["ok"] is True
    again = create_backup(workspace, output=source, extra_outputs=[extra])
    assert again["ok"] is True
    assert again.get("reused") is True
    verified = verify_backup(source)
    assert verified["ok"] is True
    restored = tmp_path / ".work" / "roundtrip"
    result = restore_backup(source, destination=restored)
    assert result["ok"] is True
    assert (restored / "notes.md").read_bytes() == (workspace / "notes.md").read_bytes()
    assert (restored / first["extra_outputs"][0]["restore_path"]).read_bytes() == extra.read_bytes()


def test_backup_publication_race_preserves_newly_appearing_output(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "pub-race")
    (workspace / "notes.md").write_text("publication race note\n", encoding="utf-8")
    output = _output(tmp_path, "race.zip")
    sentinel = b"User sentinel that appeared before publication\n"

    def _appear(_point: str) -> None:
        output.write_bytes(sentinel)

    set_library_inject_hook("before_backup_rename", _appear)
    try:
        result = create_backup(workspace, output=output)
    finally:
        set_library_inject_hook(None)
    assert result["ok"] is False
    assert output.read_bytes() == sentinel


def test_restore_empty_destination_race_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "dest-race")
    (workspace / "notes.md").write_text("destination race note\n", encoding="utf-8")
    source = _output(tmp_path, "dest-race.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    destination = tmp_path / ".work" / "appeared"

    def _appear(_point: str) -> None:
        destination.mkdir()

    set_library_inject_hook("before_restore_publish", _appear)
    try:
        result = restore_backup(source, destination=destination)
    finally:
        set_library_inject_hook(None)
    assert result["ok"] is False
    assert destination.is_dir()
    assert not (destination / "notes.md").exists()


def test_restore_preserves_unknown_or_edited_stage_on_publish_failure(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "stage-keep")
    (workspace / "notes.md").write_text("stage keep note\n", encoding="utf-8")
    source = _output(tmp_path, "stage-keep.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    destination = tmp_path / ".work" / "kept-restore"

    def _tamper(_point: str) -> None:
        parent = destination.parent
        stages = [path for path in parent.iterdir() if path.name.startswith(".light-backup-stage-")]
        assert stages
        stage = stages[0]
        (stage / "unexpected.txt").write_text("unknown addition\n", encoding="utf-8")
        notes = stage / "payload" / "notes.md"
        notes.write_text("edited generated notes\n", encoding="utf-8")
        raise OSError("injected publication failure")

    set_library_inject_hook("before_restore_publish", _tamper)
    try:
        result = restore_backup(source, destination=destination)
    finally:
        set_library_inject_hook(None)
    assert result["ok"] is False
    assert not destination.exists()
    stages = [path for path in destination.parent.iterdir() if path.name.startswith(".light-backup-stage-")]
    assert stages
    stage = stages[0]
    assert (stage / "unexpected.txt").read_text(encoding="utf-8") == "unknown addition\n"
    assert (stage / "payload" / "notes.md").read_text(encoding="utf-8") == "edited generated notes\n"


def test_verify_refuses_truncated_eocd_and_local_crc_mismatch(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "crc")
    (workspace / "notes.md").write_text("crc note\n", encoding="utf-8")
    source = _output(tmp_path, "crc.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    raw = source.read_bytes()

    truncated = tmp_path / ".work" / "truncated-eocd.zip"
    truncated.write_bytes(b"\x00PK\x05\x06" + b"\x00" * 17)
    bad_eocd = verify_backup(truncated)
    assert bad_eocd.get("ok") is False

    flipped = bytearray(raw)
    pos = raw.find(b"PK\x03\x04")
    assert pos >= 0
    flipped[pos + 14] ^= 0xFF
    local_crc = tmp_path / ".work" / "local-crc.zip"
    local_crc.write_bytes(bytes(flipped))
    bad_crc = verify_backup(local_crc)
    assert bad_crc.get("ok") is False

    again = verify_backup(source)
    assert again["ok"] is True
    restored = tmp_path / ".work" / "crc-restore"
    assert restore_backup(source, destination=restored)["ok"] is True


def test_backup_unicode_chinese_greek_create_verify_restore_reuse(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "unicode-library")
    chinese_notes = workspace / "papers" / "fixture" / "notes-α-中文.md"
    greek_code = workspace / "papers" / "fixture" / "code-δ.py"
    chinese_notes.parent.mkdir(parents=True)
    chinese_notes.write_text("嵌套中文笔记\n", encoding="utf-8")
    greek_code.write_text("# Greek code-note\nprint('γ')\n", encoding="utf-8")
    expected = {
        "papers/fixture/notes-α-中文.md": chinese_notes.read_bytes(),
        "papers/fixture/code-δ.py": greek_code.read_bytes(),
    }
    extra = tmp_path / "external-报告-β.md"
    extra_bytes = "外部报告：中文与 Ελληνικά\n".encode("utf-8")
    extra.write_bytes(extra_bytes)
    extra_before = extra.read_bytes()
    source = _output(tmp_path, "unicode.zip")
    created = create_backup(workspace, output=source, extra_outputs=[extra])
    assert created["ok"] is True
    assert created["reused"] is False
    names = [row["filename"] for row in _zip_flags(source)]
    assert "papers/fixture/notes-α-中文.md" in names
    assert "papers/fixture/code-δ.py" in names
    assert any(row["filename"].endswith("external-报告-β.md") for row in _zip_flags(source))
    assert any(int(row["flag_bits"]) == 0x800 for row in _zip_flags(source))
    first_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    reused = create_backup(workspace, output=source, extra_outputs=[extra])
    assert reused["ok"] is True
    assert reused["reused"] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == first_sha
    verified = verify_backup(source)
    assert verified["ok"] is True
    destination = tmp_path / ".work" / "unicode-restored"
    restored = restore_backup(source, destination=destination)
    assert restored["ok"] is True
    for relative, payload in expected.items():
        assert (destination / relative).read_bytes() == payload
    extra_rows = verified.get("extra_outputs") or []
    assert len(extra_rows) == 1
    assert (destination / extra_rows[0]["restore_path"]).read_bytes() == extra_bytes
    assert extra.read_bytes() == extra_before
    assert chinese_notes.read_bytes() == expected["papers/fixture/notes-α-中文.md"]
    assert greek_code.read_bytes() == expected["papers/fixture/code-δ.py"]


def test_backup_ascii_filename_flags_remain_zero(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "ascii-library")
    (workspace / "notes-alpha.md").write_text("ASCII note\n", encoding="utf-8")
    source = _output(tmp_path, "ascii.zip")
    created = create_backup(workspace, output=source)
    assert created["ok"] is True
    assert all(int(row["flag_bits"]) == 0 for row in _zip_flags(source))
    verified = verify_backup(source)
    assert verified["ok"] is True
    destination = tmp_path / ".work" / "ascii-restored"
    restored = restore_backup(source, destination=destination)
    assert restored["ok"] is True
    assert (destination / "notes-alpha.md").read_bytes() == b"ASCII note\n"


def test_verify_refuses_unsafe_and_noncanonical_zip_filename_flags(tmp_path: Path) -> None:
    unicode_workspace = _workspace(tmp_path, "unicode-flags")
    unicode_notes = unicode_workspace / "papers" / "fixture" / "notes-α-中文.md"
    unicode_notes.parent.mkdir(parents=True)
    unicode_notes.write_text("嵌套中文笔记\n", encoding="utf-8")
    (unicode_workspace / "papers" / "fixture" / "code-δ.py").write_text("# Greek code-note\nprint('γ')\n", encoding="utf-8")
    extra = tmp_path / "external-报告-β.md"
    extra.write_text("外部报告：中文与 Ελληνικά\n", encoding="utf-8")
    unicode_archive = _output(tmp_path, "unicode-flags.zip")
    assert create_backup(unicode_workspace, output=unicode_archive, extra_outputs=[extra])["ok"] is True

    ascii_workspace = _workspace(tmp_path, "ascii-flags")
    (ascii_workspace / "notes-alpha.md").write_text("ASCII note\n", encoding="utf-8")
    ascii_archive = _output(tmp_path, "ascii-flags.zip")
    assert create_backup(ascii_workspace, output=ascii_archive)["ok"] is True

    unicode_bytes = unicode_archive.read_bytes()
    ascii_bytes = ascii_archive.read_bytes()
    extra_bytes = extra.read_bytes()
    unicode_tree = _tree_bytes(unicode_workspace)
    ascii_tree = _tree_bytes(ascii_workspace)

    def _refused(mutated: Path) -> None:
        destination = tmp_path / ".work" / f"refuse-{mutated.name}"
        verified = verify_backup(mutated)
        restored = restore_backup(mutated, destination=destination)
        assert verified.get("ok") is False
        assert verified.get("status") == LIGHT_BACKUP_INVALID
        assert restored.get("ok") is False
        assert restored.get("status") == LIGHT_BACKUP_INVALID
        assert not destination.exists()
        assert unicode_archive.read_bytes() == unicode_bytes
        assert ascii_archive.read_bytes() == ascii_bytes
        assert extra.read_bytes() == extra_bytes
        assert _tree_bytes(unicode_workspace) == unicode_tree
        assert _tree_bytes(ascii_workspace) == ascii_tree

    mutations = tmp_path / ".work" / "mutations"
    mutations.mkdir()
    for label, bit in (("encrypted", 0x001), ("data_descriptor", 0x008), ("unknown", 0x020)):
        for mode, local, central in (
            ("local_only", bit, 0),
            ("central_only", 0, bit),
            ("both", bit, bit),
        ):
            mutated = mutations / f"{label}-{mode}.zip"
            _mutate_zip_flags(ascii_archive, mutated, local=local, central=central)
            _refused(mutated)

    missing_utf8 = mutations / "unicode-flags-zero.zip"
    _mutate_zip_flags(unicode_archive, missing_utf8, local=0, central=0)
    _refused(missing_utf8)

    ascii_marked = mutations / "ascii-unicode-flag.zip"
    _mutate_zip_flags(ascii_archive, ascii_marked, local=0x800, central=0x800)
    _refused(ascii_marked)

    mismatch_local = mutations / "unicode-mismatch-local.zip"
    _mutate_zip_flags(unicode_archive, mismatch_local, local=0, central=0x800)
    _refused(mismatch_local)

    mismatch_central = mutations / "unicode-mismatch-central.zip"
    _mutate_zip_flags(unicode_archive, mismatch_central, local=0x800, central=0)
    _refused(mismatch_central)

    malformed = mutations / "unicode-malformed-name.zip"
    _mutate_zip_name(unicode_archive, malformed, old="papers/fixture/notes-α-中文.md")
    _refused(malformed)


def test_backup_refuses_pending_knowledge_batch_job(tmp_path: Path) -> None:
    from tests.research.test_light_index import SHA_A, _write_paper
    from video_paper_wiki_research.light_knowledge_batch import plan_knowledge_batches

    workspace = tmp_path / ".work" / "batch-pending"
    workspace.mkdir(parents=True)
    _write_paper(workspace, SHA_A, "Alpha paper", ["Synthetic quasar method evidence uniquealpha."])
    assert build_index(workspace)["ok"] is True
    planned = plan_knowledge_batches(workspace, paper_id="sha256:" + SHA_A)
    assert planned["ok"] is True
    blocked = create_backup(workspace, output=_output(tmp_path, "pending-batch.zip"))
    assert blocked["ok"] is False
    assert blocked["status"] == LIGHT_BACKUP_INVALID
    assert planned["plan_id"] in blocked["message"]
