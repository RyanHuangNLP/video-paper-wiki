from __future__ import annotations

import errno
import json
import os
import secrets
import unicodedata
from pathlib import Path


def fold_name(value):
    return unicodedata.normalize("NFC", value).casefold()


def create_payload_relpaths(prepared, *substrings):
    request = json.loads(Path(prepared).read_bytes())
    found = []
    for item in request["payloads"]:
        if item["mode"] != "create":
            continue
        path = str(item["path"]).replace("\\", "/")
        if any(part in path for part in substrings):
            found.append(item["path"])
    if not found:
        raise AssertionError(
            "prepared request has no create payloads matching " + repr(substrings)
        )
    return found


def directory_entry_names(directory):
    return tuple(sorted(os.listdir(os.fspath(directory))))


def directory_tree_names(directory):
    root = os.fspath(directory)
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            prefix = ""
        else:
            prefix = rel_dir.replace("\\", "/") + "/"
        for name in dirnames:
            out.append(prefix + name)
        for name in filenames:
            out.append(prefix + name)
    return tuple(sorted(out))


def actual_directory_entry(parent, wanted):
    parent = os.fspath(parent)
    folded = fold_name(wanted)
    matches = [name for name in os.listdir(parent) if fold_name(name) == folded]
    if len(matches) != 1:
        raise AssertionError(
            "expected exactly one directory entry folding to "
            + repr(wanted)
            + ", found "
            + repr(sorted(matches))
        )
    return matches[0]


def rename_directory_spelling(parent, source_name, dest_name):
    parent = os.fspath(parent)
    current = actual_directory_entry(parent, source_name)
    token = secrets.token_hex(16)
    temp_name = ".vpkb-fs-rename-" + token
    if fold_name(temp_name) in {fold_name(current), fold_name(dest_name), fold_name(source_name)}:
        raise AssertionError("transit directory name is not casefold-distinct")
    src = os.path.join(parent, current)
    tmp = os.path.join(parent, temp_name)
    dest = os.path.join(parent, dest_name)
    os.rename(src, tmp)
    try:
        os.rename(tmp, dest)
    except BaseException:
        if os.path.lexists(tmp) and not os.path.lexists(dest):
            os.rename(tmp, src)
        raise
    names = directory_entry_names(parent)
    if dest_name not in names:
        raise AssertionError("final directory spelling " + repr(dest_name) + " missing: " + repr(names))
    if temp_name in names:
        raise AssertionError("transit directory remained: " + repr(names))
    if current != dest_name and current in names:
        raise AssertionError("source directory spelling remained: " + repr(names))
    return names


class PortableEnospcInjector:
    def __init__(self, module, vault_root, relative_targets, *, partial_bytes=0):
        self.module = module
        self.vault_root = os.fspath(vault_root)
        self.relative_targets = [str(path).replace("\\", "/") for path in relative_targets]
        self._target_set = set(self.relative_targets)
        self.partial_bytes = int(partial_bytes)
        self.real_write = module.os.write
        self.real_write_excl = module._write_excl
        self.hits = 0
        self.partial_writes = 0
        self.created_before_inject = False
        self.matched_relpaths = []
        self._active_paths = []
        self._partial_fds = set()

    def wrapped_write_excl(self, parent_fd, name, data, created_files=None, created_path=None):
        track = created_path is not None and str(created_path).replace("\\", "/") in self._target_set
        if track:
            self._active_paths.append(str(created_path).replace("\\", "/"))
        try:
            return self.real_write_excl(parent_fd, name, data, created_files, created_path)
        finally:
            if track:
                rel = str(created_path).replace("\\", "/")
                if self._active_paths and self._active_paths[-1] == rel:
                    self._active_paths.pop()

    def _match_relpath(self, fd):
        try:
            fst = os.fstat(int(fd))
        except OSError:
            return None
        ident = (fst.st_dev, fst.st_ino)
        seen = []
        for rel in list(self._active_paths) + self.relative_targets:
            if rel in seen:
                continue
            seen.append(rel)
            path = os.path.join(self.vault_root, rel)
            try:
                tst = os.lstat(path)
            except OSError:
                continue
            if (tst.st_dev, tst.st_ino) == ident:
                return rel
        return None

    def write(self, fd, data):
        rel = self._match_relpath(fd)
        if rel is None:
            return self.real_write(fd, data)
        self.created_before_inject = True
        self.matched_relpaths.append(rel)
        key = int(fd)
        if self.partial_bytes > 0 and key not in self._partial_fds:
            view = data if isinstance(data, memoryview) else memoryview(data)
            take = min(self.partial_bytes, len(view))
            if take > 0:
                self._partial_fds.add(key)
                written = self.real_write(fd, view[:take])
                self.partial_writes += 1
                return written
        self.hits += 1
        raise OSError(errno.ENOSPC, "No space left on device")

    def restore(self, monkeypatch):
        monkeypatch.setattr(self.module.os, "write", self.real_write)
        monkeypatch.setattr(self.module, "_write_excl", self.real_write_excl)

    def assert_hit(self, *, require_partial=False):
        assert self.created_before_inject is True
        assert self.hits >= 1
        assert self.matched_relpaths
        if require_partial:
            assert self.partial_writes >= 1


def install_portable_enospc(
    monkeypatch,
    module,
    vault_root,
    prepared,
    *substrings,
    partial_bytes=0,
):
    targets = create_payload_relpaths(prepared, *substrings)
    injector = PortableEnospcInjector(
        module,
        vault_root,
        targets,
        partial_bytes=partial_bytes,
    )
    monkeypatch.setattr(module.os, "write", injector.write)
    monkeypatch.setattr(module, "_write_excl", injector.wrapped_write_excl)
    return injector
