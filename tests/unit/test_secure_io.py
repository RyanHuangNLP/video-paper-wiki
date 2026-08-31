from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from video_paper_wiki.blob_store import BlobStore
from video_paper_wiki.secure_io import (
    BLOB_LIMIT_EXCEEDED,
    BLOB_NOT_FOUND,
    BLOB_PATH_UNSAFE,
    PLAN_NOT_FOUND,
    PLAN_PATH_UNSAFE,
    SOURCE_CHANGED,
    SecureIOError,
    is_special,
    load_strict_json,
    parse_strict_json,
    read_regular_file,
    stamp,
)


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


def _delete(path: Path) -> None:
    path.unlink()


def _to_symlink(path: Path) -> None:
    path.unlink()
    path.symlink_to("missing-target")


def _to_dir(path: Path) -> None:
    path.unlink()
    path.mkdir()


def _to_fifo(path: Path) -> None:
    path.unlink()
    os.mkfifo(path)


def _to_socket(path: Path, holders: list) -> None:
    path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    holders.append(server)


def _to_chmod000_dir(path: Path) -> None:
    path.unlink()
    path.mkdir()
    path.chmod(0)


def _to_device_or_fallback(path: Path) -> None:
    path.unlink()
    try:
        os.mknod(path, stat.S_IFCHR | 0o666, device=os.makedev(1, 3))
    except OSError:
        os.mkfifo(path)


def _restore_chmod000_dir(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        path.chmod(0o700)


def _race_child_open_fail(monkeypatch, path: Path, mutator, err: int) -> None:
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
            raise OSError(err, os.strerror(err))
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", racing_open)


def test_parse_strict_json_rejects_duplicate_float_nan_trailing_and_utf8() -> None:
    parse_strict_json(b'{"a":1}', invalid_code="X")
    with pytest.raises(SecureIOError) as dup:
        parse_strict_json(b'{"a":1,"a":2}', invalid_code="X")
    assert dup.value.code == "X"
    with pytest.raises(SecureIOError) as floated:
        parse_strict_json(b'{"a":1.5}', invalid_code="X")
    assert floated.value.code == "X"
    with pytest.raises(SecureIOError):
        parse_strict_json(b'{"a":NaN}', invalid_code="X")
    with pytest.raises(SecureIOError):
        parse_strict_json(b'{"a":1}{"b":2}', invalid_code="X")
    with pytest.raises(SecureIOError):
        parse_strict_json(b'{"a":1}\xff', invalid_code="X")
    with pytest.raises(SecureIOError):
        parse_strict_json(b'\xef\xbb\xbf{"a":1}', invalid_code="X")


def test_missing_symlink_dir_fifo_socket_device(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(
            missing,
            missing_code=PLAN_NOT_FOUND,
            unsafe_code=PLAN_PATH_UNSAFE,
        )
    assert exc.value.code == PLAN_NOT_FOUND

    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "target.json")
    with pytest.raises(SecureIOError) as linked:
        read_regular_file(link, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert linked.value.code == PLAN_PATH_UNSAFE

    directory = tmp_path / "dir.json"
    directory.mkdir()
    with pytest.raises(SecureIOError) as as_dir:
        read_regular_file(directory, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert as_dir.value.code == PLAN_PATH_UNSAFE

    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    with pytest.raises(SecureIOError) as as_fifo:
        read_regular_file(fifo, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert as_fifo.value.code == PLAN_PATH_UNSAFE

    sock_path = tmp_path / "sock.json"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)
    try:
        with pytest.raises(SecureIOError) as as_sock:
            read_regular_file(sock_path, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
        assert as_sock.value.code == PLAN_PATH_UNSAFE
    finally:
        server.close()

    st = os.lstat("/dev/null")
    assert stat.S_ISCHR(st.st_mode)
    assert is_special(st)
    with pytest.raises(SecureIOError) as as_dev:
        read_regular_file(Path("/dev/null"), missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert as_dev.value.code == PLAN_PATH_UNSAFE


def test_lstat_open_replace_is_source_changed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    real_open = os.open
    replaced = {"done": False}

    def racing_open(name, flags, *args, **kwargs):
        result_name = name if isinstance(name, str) else name
        if result_name == "doc.json" and not replaced["done"] and kwargs.get("dir_fd") is not None:
            if flags & os.O_DIRECTORY:
                return real_open(name, flags, *args, **kwargs)
            replaced["done"] = True
            path.unlink()
            path.write_text('{"other":true}', encoding="utf-8")
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", racing_open)
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(path, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert exc.value.code == SOURCE_CHANGED
    assert exc.value.exit_code == 75


@pytest.mark.parametrize("kind", ["delete", "symlink", "dir", "fifo", "socket"])
def test_lstat_open_type_race_is_source_changed(kind, tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    holders: list = []
    mutators = {
        "delete": _delete,
        "symlink": _to_symlink,
        "dir": _to_dir,
        "fifo": _to_fifo,
        "socket": lambda current: _to_socket(current, holders),
    }
    _race_child_open(monkeypatch, path, mutators[kind])
    try:
        with pytest.raises(SecureIOError) as exc:
            read_regular_file(
                path,
                missing_code=PLAN_NOT_FOUND,
                unsafe_code=PLAN_PATH_UNSAFE,
            )
        assert exc.value.code == SOURCE_CHANGED
        assert exc.value.exit_code == 75
        assert exc.value.code not in {PLAN_NOT_FOUND, PLAN_PATH_UNSAFE}
    finally:
        for server in holders:
            server.close()


@pytest.mark.parametrize("kind", ["delete", "symlink", "dir", "fifo"])
def test_blob_lstat_open_type_race_is_source_changed(kind, tmp_path: Path, monkeypatch) -> None:
    data = b"blob-bytes"
    digest = hashlib.sha256(data).hexdigest()
    root = tmp_path / "blobs"
    root.mkdir()
    path = root / digest
    path.write_bytes(data)
    mutators = {
        "delete": _delete,
        "symlink": _to_symlink,
        "dir": _to_dir,
        "fifo": _to_fifo,
    }
    _race_child_open(monkeypatch, path, mutators[kind])
    with pytest.raises(SecureIOError) as exc:
        BlobStore(root).read(digest)
    assert exc.value.code == SOURCE_CHANGED
    assert exc.value.exit_code == 75
    assert exc.value.code not in {BLOB_NOT_FOUND, BLOB_PATH_UNSAFE}


def test_lstat_open_chmod000_dir_is_source_changed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    _race_child_open(monkeypatch, path, _to_chmod000_dir)
    try:
        with pytest.raises(SecureIOError) as exc:
            read_regular_file(
                path,
                missing_code=PLAN_NOT_FOUND,
                unsafe_code=PLAN_PATH_UNSAFE,
            )
        assert exc.value.code == SOURCE_CHANGED
        assert exc.value.exit_code == 75
        assert exc.value.code not in {PLAN_NOT_FOUND, PLAN_PATH_UNSAFE}
    finally:
        _restore_chmod000_dir(path)


@pytest.mark.parametrize(
    "kind,err",
    [
        ("chmod000_dir", errno.EACCES),
        ("fifo", errno.EACCES),
        ("fifo", errno.EPERM),
        ("device", errno.ENODEV),
        ("device", errno.EACCES),
        ("device", errno.EPERM),
    ],
)
def test_lstat_open_failure_after_swap_is_source_changed(
    kind, err, tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    mutators = {
        "chmod000_dir": _to_chmod000_dir,
        "fifo": _to_fifo,
        "device": _to_device_or_fallback,
    }
    _race_child_open_fail(monkeypatch, path, mutators[kind], err)
    try:
        with pytest.raises(SecureIOError) as exc:
            read_regular_file(
                path,
                missing_code=PLAN_NOT_FOUND,
                unsafe_code=PLAN_PATH_UNSAFE,
            )
        assert exc.value.code == SOURCE_CHANGED
        assert exc.value.exit_code == 75
        assert exc.value.code not in {PLAN_NOT_FOUND, PLAN_PATH_UNSAFE}
    finally:
        _restore_chmod000_dir(path)


@pytest.mark.parametrize(
    "kind,err",
    [
        ("chmod000_dir", errno.EACCES),
        ("fifo", errno.EPERM),
        ("device", errno.ENODEV),
    ],
)
def test_blob_lstat_open_failure_after_swap_is_source_changed(
    kind, err, tmp_path: Path, monkeypatch
) -> None:
    data = b"blob-bytes"
    digest = hashlib.sha256(data).hexdigest()
    root = tmp_path / "blobs"
    root.mkdir()
    path = root / digest
    path.write_bytes(data)
    mutators = {
        "chmod000_dir": _to_chmod000_dir,
        "fifo": _to_fifo,
        "device": _to_device_or_fallback,
    }
    _race_child_open_fail(monkeypatch, path, mutators[kind], err)
    try:
        with pytest.raises(SecureIOError) as exc:
            BlobStore(root).read(digest)
        assert exc.value.code == SOURCE_CHANGED
        assert exc.value.exit_code == 75
        assert exc.value.code not in {BLOB_NOT_FOUND, BLOB_PATH_UNSAFE}
    finally:
        _restore_chmod000_dir(path)


def test_same_file_open_eacces_is_path_unsafe(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"ok":true}', encoding="utf-8")
    real_open = os.open

    def denied_open(name, flags, *args, **kwargs):
        result_name = name if isinstance(name, str) else os.fsdecode(name)
        if (
            result_name == path.name
            and kwargs.get("dir_fd") is not None
            and not (flags & getattr(os, "O_DIRECTORY", 0))
        ):
            raise OSError(errno.EACCES, os.strerror(errno.EACCES))
        return real_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied_open)
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(path, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert exc.value.code == PLAN_PATH_UNSAFE
    assert exc.value.exit_code == 2
    assert exc.value.code != SOURCE_CHANGED


def test_in_place_modify_during_read_is_source_changed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_bytes(b"{" + b"a" * 20 + b":1}")
    monkeypatch.setattr("video_paper_wiki.secure_io.READ_CHUNK", 4)
    real_read = os.read
    mutated = {"done": False}

    def racing_read(fd, n):
        chunk = real_read(fd, n)
        if not mutated["done"]:
            try:
                st = os.fstat(fd)
            except OSError:
                return chunk
            if stat.S_ISREG(st.st_mode) and st.st_size >= 20:
                mutated["done"] = True
                extra = os.open(os.fspath(path), os.O_WRONLY | os.O_APPEND)
                try:
                    os.write(extra, b"EXTRA")
                finally:
                    os.close(extra)
        return chunk

    monkeypatch.setattr(os, "read", racing_read)
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(path, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert exc.value.code == SOURCE_CHANGED


def test_rename_replace_during_read_is_source_changed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "doc.json"
    path.write_bytes(b'{"payload":"' + b"x" * 32 + b'"}')
    monkeypatch.setattr("video_paper_wiki.secure_io.READ_CHUNK", 4)
    real_read = os.read
    replaced = {"done": False}

    def racing_read(fd, n):
        chunk = real_read(fd, n)
        if not replaced["done"]:
            replaced["done"] = True
            path.unlink()
            path.write_bytes(b'{"payload":"' + b"y" * 32 + b'"}')
        return chunk

    monkeypatch.setattr(os, "read", racing_read)
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(path, missing_code=PLAN_NOT_FOUND, unsafe_code=PLAN_PATH_UNSAFE)
    assert exc.value.code == SOURCE_CHANGED


def test_max_bytes_limit(tmp_path: Path) -> None:
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 16)
    with pytest.raises(SecureIOError) as exc:
        read_regular_file(
            path,
            missing_code=PLAN_NOT_FOUND,
            unsafe_code=PLAN_PATH_UNSAFE,
            max_bytes=8,
            limit_code=BLOB_LIMIT_EXCEEDED,
        )
    assert exc.value.code == BLOB_LIMIT_EXCEEDED


def test_load_strict_json_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"k": 1, "nested": {"z": True}}), encoding="utf-8")
    obj = load_strict_json(
        path,
        missing_code=PLAN_NOT_FOUND,
        unsafe_code=PLAN_PATH_UNSAFE,
        invalid_code="BAD",
    )
    assert obj == {"k": 1, "nested": {"z": True}}


def test_stamp_includes_mtime_ctime(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"abc")
    st = os.lstat(path)
    values = stamp(st)
    assert values[0] == st.st_dev
    assert values[1] == st.st_ino
    assert values[3] == 3
