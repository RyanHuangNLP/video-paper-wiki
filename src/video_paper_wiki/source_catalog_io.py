"""Retained package/resource generation and one private fixed catalog slot."""
from __future__ import annotations

import os
import platform
import stat
import sys
import unicodedata
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

from video_paper_wiki import resources
from video_paper_wiki.markdown_source_io import _identity
from video_paper_wiki.secure_io import close_fd, dir_open_flags, file_open_flags, stamp
from video_paper_wiki.source_catalog_contracts import MAX_CACHE, PROFILE_SHA, fail, invalid, limit
from video_paper_wiki.source_publication_io import checked_path
from video_paper_wiki.source_semantics_contracts import sha
from video_paper_wiki.staging import _atomic_install, _open_batch_session, resolve_checkout_root, validate_batch_id


def unsafe(message):
    fail("WORK_PATH_UNSAFE", message)


def verify_all(functions):
    """Check every retained group, including after another check has failed."""
    failure = None
    for function in functions:
        try:
            function()
        except BaseException as exc:
            if failure is None:
                failure = exc
    if failure is not None:
        raise failure


class _Tree:
    """Shared descriptors for reached named edges, files and scoped sets."""

    def __init__(self):
        self.directories, self.edges, self.files, self.sets = {}, {}, {}, {}
        self.root_fd = os.open("/", dir_open_flags())
        self.root_first = os.fstat(self.root_fd)
        self.directories[Path("/")] = self.root_fd

    def _edge(self, path, *, observed=None):
        if path in self.edges:
            return self.edges[path]
        parent = self.directories[path.parent]
        first = observed
        if first is None:
            try:
                first = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
        edge = {"parent": parent, "name": path.name, "first": first, "fd": None,
                "directory": first is None or stat.S_ISDIR(first.st_mode)}
        self.edges[path] = edge
        return edge

    def directory(self, path, *, optional=False, create=False):
        path = checked_path(path)
        current = Path("/")
        for name in path.parts[1:]:
            current /= name
            if current in self.directories:
                continue
            edge = self._edge(current)
            if edge["first"] is None:
                if create and current == path:
                    self.verify()
                    try:
                        os.mkdir(name, 0o700, dir_fd=edge["parent"])
                    except FileExistsError:
                        unsafe("missing catalog directory was filled by another writer")
                    edge["first"] = os.stat(name, dir_fd=edge["parent"], follow_symlinks=False)
                elif optional:
                    return None
                else:
                    unsafe("required retained directory is missing")
            if not stat.S_ISDIR(edge["first"].st_mode):
                unsafe("retained directory is not a real directory")
            child = os.open(name, dir_open_flags(), dir_fd=edge["parent"])
            edge["fd"] = child
            self.directories[current] = child
            self._verify_edge(edge)
        return self.directories[path]

    def observe_set(self, path, kind):
        fd = self.directory(path)
        key = (path, kind)
        if key in self.sets:
            self._verify_set(path, kind, self.sets[key])
            return self.sets[key]
        names = set()
        self.sets[key] = names
        for name in sorted(os.listdir(fd)):
            if kind == "schemas" and not name.endswith(".schema.json") or kind == "python" and name == "__pycache__":
                continue
            first = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if kind == "python" and not (name.endswith(".py") or stat.S_ISDIR(first.st_mode) or stat.S_ISLNK(first.st_mode)):
                continue
            names.add(name)
            # Keep the first classifier observation; opening must not adopt a
            # later replacement as the original generation/cache entry.
            self._edge(path / name, observed=first)
        return names

    @staticmethod
    def _names(fd, kind):
        names = set(os.listdir(fd))
        if kind == "all":
            return names
        if kind == "schemas":
            return {n for n in names if n.endswith(".schema.json")}
        result = set()
        for name in names:
            if name == "__pycache__":
                continue
            entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if name.endswith(".py") or stat.S_ISDIR(entry.st_mode) or stat.S_ISLNK(entry.st_mode):
                result.add(name)
        return result

    def file(self, path, *, optional=False, private=False, maximum=MAX_CACHE):
        path = checked_path(path)
        if path in self.files:
            return self.files[path]
        self.directory(path.parent)
        edge = self._edge(path)
        edge.update(directory=False, private=private, maximum=maximum, data=None, read=False)
        self.files[path] = edge
        if edge["first"] is None:
            if optional:
                return edge
            invalid("required generation resource is missing")
        first = edge["first"]
        if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1
                or private and stat.S_IMODE(first.st_mode) != 0o600):
            unsafe("retained file type, links or private permissions are unsafe")
        if first.st_size > maximum:
            limit("retained file exceeds its byte bound")
        fd = os.open(path.name, file_open_flags(), dir_fd=edge["parent"])
        edge["fd"] = fd
        self._verify_edge(edge)
        edge["data"] = self._read(edge)
        edge["read"] = True
        self._verify_file(edge)
        return edge

    @staticmethod
    def _read(edge):
        os.lseek(edge["fd"], 0, os.SEEK_SET)
        chunks, size = [], 0
        while True:
            data = os.read(edge["fd"], min(65536, edge["maximum"] + 1 - size))
            if not data:
                break
            chunks.append(data)
            size += len(data)
            if size > edge["maximum"]:
                unsafe("retained file grew beyond its bound")
        return b"".join(chunks)

    @staticmethod
    def _verify_edge(edge):
        try:
            now = os.stat(edge["name"], dir_fd=edge["parent"], follow_symlinks=False)
        except FileNotFoundError:
            now = None
        first = edge["first"]
        identity = _identity if edge["directory"] else stamp
        if ((now is None) != (first is None)
                or first is not None and identity(now) != identity(first)):
            unsafe("retained named edge changed")
        if edge["fd"] is not None and (first is None or identity(os.fstat(edge["fd"])) != identity(first)):
            unsafe("retained descriptor identity changed")
        if first is not None and not edge["directory"] and now.st_nlink != first.st_nlink:
            unsafe("retained file link count changed")

    def _verify_file(self, edge):
        self._verify_edge(edge)
        if edge["read"]:
            if self._read(edge) != edge["data"]:
                unsafe("retained file bytes changed")
            self._verify_edge(edge)

    def _verify_set(self, path, kind, names):
        if self._names(self.directories[path], kind) != names:
            unsafe("retained complete set changed")

    def verify(self):
        def root():
            if _identity(os.fstat(self.root_fd)) != _identity(self.root_first):
                unsafe("retained filesystem root changed")
        checks = [root]
        checks += [lambda e=e: self._verify_edge(e) for e in self.edges.values()]
        checks += [lambda p=p, k=k, n=n: self._verify_set(p, k, n) for (p, k), n in self.sets.items()]
        checks += [lambda e=e: self._verify_file(e) for e in self.files.values()]
        try:
            verify_all(checks)
        except OSError:
            unsafe("retained filesystem group is unavailable")

    def close(self):
        for edge in reversed(list(self.edges.values())):
            close_fd(edge["fd"])
        close_fd(self.root_fd)


@contextmanager
def retained_tree():
    tree = _Tree()
    try:
        yield tree
    finally:
        try:
            tree.verify()
        finally:
            tree.close()


class CatalogSlot:
    def __init__(self, tree, batch, session=None):
        self.tree, self.session = tree, session
        self.path = resolve_checkout_root() / ".work" / batch / "source-catalog"
        self.fd = tree.directory(self.path, optional=session is None, create=session is not None)
        self.held = None
        if self.fd is not None:
            names = tree.observe_set(self.path, "all")
            if not names <= {"catalog.json"}:
                unsafe("catalog directory has foreign siblings")
            self.held = tree.file(self.path / "catalog.json", optional=True, private=True)

    @property
    def data(self):
        return None if self.held is None else self.held["data"]

    def install(self, raw):
        if self.session is None:
            invalid("read-only catalog cannot install files")
        self.tree.verify()
        self.session.verify()
        if self.data is not None:
            if self.data != raw:
                fail("SOURCE_CATALOG_CONFLICT", "catalog slot contains a different generation; use a fresh batch")
            return "reused"
        held = self.held
        reused, identity = _atomic_install(self.session.work_fd, self.fd, "catalog.json", raw,
            target=self.path / "catalog.json", checkout_fd=self.session.checkout_fd, return_identity=True)
        if reused:
            unsafe("missing catalog slot was filled by another writer")
        # Only the installer's original descriptor identity may fill this slot.
        fd = os.open("catalog.json", file_open_flags(), dir_fd=self.fd)
        held["fd"] = fd
        first = os.fstat(fd)
        if (_identity(first) != _identity(identity) or not stat.S_ISREG(first.st_mode)
                or first.st_nlink != 1 or stat.S_IMODE(first.st_mode) != 0o600):
            unsafe("new catalog file differs from the owned installation")
        held.update(first=first, data=raw, read=True)
        self.tree.sets[(self.path, "all")].add("catalog.json")
        self.tree.verify()
        self.session.verify()
        return "created"


@contextmanager
def catalog_slot(batch, *, create):
    batch = validate_batch_id(batch)
    with retained_tree() as tree:
        if create:
            # Retain checkout ancestors before the established batch creator.
            tree.directory(resolve_checkout_root())
            with _open_batch_session(batch, create=True) as session:
                slot = CatalogSlot(tree, batch, session)
                try:
                    yield slot
                finally:
                    verify_all([tree.verify, session.verify])
        else:
            yield CatalogSlot(tree, batch)


class Generation:
    def __init__(self, tree):
        self.tree = tree
        self.material = {}
        self.implementation, self.resources = [], []
        # importlib's package origin is never resolved against the caller CWD.
        package = resources.resources.files("video_paper_wiki")
        if not isinstance(package, Path):
            invalid("catalog requires an installed filesystem package")
        package = checked_path(package)
        self._python(package, package)
        root = resources._source_checkout_root()
        if root is not None:
            root = checked_path(root)
            # The source checkout fallback is tied to this retained module.
            if package != root / "src/video_paper_wiki":
                invalid("package and source resource origins disagree")
        schema_dir = package / "schemas"
        fd = tree.directory(schema_dir, optional=True)
        names = set() if fd is None else tree.observe_set(schema_dir, "schemas")
        if not names:
            if root is None:
                invalid("canonical schema registry is unavailable")
            schema_dir = root / "schemas"
            names = tree.observe_set(schema_dir, "schemas")
        self.schema_names = tuple(sorted(names))
        if not names:
            invalid("canonical schema registry is empty")
        for name in self.schema_names:
            self._resource("schema", name, schema_dir / name)
        for kind, name in (("taxonomy", "v1.json"), ("catalog", "source-catalog-v1.json")):
            directory = package / kind
            fd = tree.directory(directory, optional=True)
            entry = None if fd is None else tree.file(directory / name, optional=True)
            if entry is None or entry["first"] is None:
                if root is None:
                    invalid("fixed projection resource is missing")
                directory = root / kind
            self._resource(kind, name, directory / name)
        self.implementation.sort(key=lambda x: x["path"].encode())
        self.resources.sort(key=lambda x: x["path"].encode())
        if sha(self.material[("catalog", "source-catalog-v1.json")]) != PROFILE_SHA:
            invalid("catalog profile bytes differ from the frozen implementation")
        self.runtime = {
            "python_implementation": platform.python_implementation(),
            "python_version": ".".join(map(str, sys.version_info[:3])) + (
                "" if sys.version_info.releaselevel == "final" else
                "-" + sys.version_info.releaselevel + "." + str(sys.version_info.serial)),
            "unicode_version": unicodedata.unidata_version,
            "jsonschema": version("jsonschema"), "referencing": version("referencing"),
            "rpds-py": version("rpds-py"),
        }

    def _python(self, directory, root):
        names = self.tree.observe_set(directory, "python")
        for name in sorted(names):
            path = directory / name
            first = self.tree.edges[path]["first"]
            if stat.S_ISDIR(first.st_mode):
                self._python(path, root)
            elif name.endswith(".py"):
                entry = self.tree.file(path)
                self.implementation.append({"path": path.relative_to(root).as_posix(),
                    "sha256": sha(entry["data"]), "size_bytes": len(entry["data"])})
            else:
                unsafe("package contains a linked generation entry")

    def _resource(self, kind, name, path):
        raw = self.tree.file(path)["data"]
        self.material[(kind, name)] = raw
        self.resources.append({"path": ("schemas" if kind == "schema" else kind) + "/" + name,
                               "sha256": sha(raw), "size_bytes": len(raw)})

    def record(self, rows_sha256):
        return {"profile_sha256": PROFILE_SHA, "resources": self.resources,
                "implementation": self.implementation, "runtime": self.runtime,
                "rows_sha256": rows_sha256}


@contextmanager
def generation():
    with retained_tree() as tree:
        value = Generation(tree)
        with resources._retained_resource_view(value.material, value.schema_names):
            yield value
