"""One retained, locked discovery lineage with create-only artifact installation."""
from __future__ import annotations

import fcntl
import os
import re
import stat
import tomllib
import unicodedata
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from video_paper_wiki.secure_io import close_fd, dir_open_flags, file_open_flags, stamp
from video_paper_wiki.staging import _atomic_install
from video_paper_wiki_research.discovery_contracts import (
    CAPS, KINDS, RESOURCE_PATHS, bound_resources, fail, invalid, limit,
    parse_json, reference, saved_bytes, validate,
)

FAMILIES = ("requests", "observations", "metadata", "proposals", "decisions")
TOTAL_BYTES = 67108864
FAMILY_BYTES = 33554432
PENDING_BYTES = 14680064
FAMILY_COUNTS = {f: 512 if f == "decisions" else 256 for f in FAMILIES}


def unsafe(message):
    fail("WORK_PATH_UNSAFE", message)


def checked_path(value):
    try:
        raw = os.fspath(value)
        if (type(raw) is not str or not raw or len(raw) > 4094 or "\\" in raw
                or "//" in raw or any(p in {".", ".."} for p in raw.split("/"))
                or unicodedata.normalize("NFC", raw) != raw
                or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in raw)):
            raise ValueError
        return Path(os.path.abspath(raw))
    except (TypeError, ValueError, OSError):
        unsafe("input path spelling is unsafe")


def identity(entry):
    return entry.st_dev, entry.st_ino, entry.st_mode


def verify_all(checks):
    failure = None
    for check in checks:
        try:
            check()
        except BaseException as exc:
            if failure is None or getattr(exc, "code", None) == "WORK_PATH_UNSAFE":
                failure = exc
    if failure is not None:
        raise failure


class RetainedTree:
    """Remember each first named observation, including absence and partial scans."""

    def __init__(self):
        self.edges, self.files, self.sets, self.directories = {}, {}, {}, {}
        self.root_fd = os.open("/", dir_open_flags())
        self.root_first = os.fstat(self.root_fd)
        self.directories[Path("/")] = self.root_fd

    def edge(self, path, *, observed=...):
        if path in self.edges:
            return self.edges[path]
        parent = self.directories[path.parent]
        if observed is ...:
            try:
                observed = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                observed = None
        edge = {"parent": parent, "name": path.name, "first": observed, "fd": None,
                "directory": observed is None or stat.S_ISDIR(observed.st_mode),
                "data": None, "read": False, "maximum": 0}
        self.edges[path] = edge
        return edge

    def directory(self, path, *, optional=False, create=False):
        path = checked_path(path)
        current = Path("/")
        for name in path.parts[1:]:
            current /= name
            if current in self.directories:
                continue
            edge = self.edge(current)
            if edge["first"] is None:
                if create and current == path:
                    self.verify()
                    try:
                        os.mkdir(name, 0o700, dir_fd=edge["parent"])
                    except FileExistsError:
                        unsafe("a first-observed missing directory was filled by another writer")
                    first = os.stat(name, dir_fd=edge["parent"], follow_symlinks=False)
                    if not stat.S_ISDIR(first.st_mode):
                        unsafe("created directory was replaced")
                    edge["first"] = first
                    if current.parent in self.sets:
                        self.sets[current.parent].add(name)
                elif optional:
                    return None
                else:
                    unsafe("required retained directory is missing")
            if not stat.S_ISDIR(edge["first"].st_mode):
                unsafe("retained directory is not a real directory")
            edge["fd"] = os.open(name, dir_open_flags(), dir_fd=edge["parent"])
            self.directories[current] = edge["fd"]
            self.verify_edge(edge)
        return self.directories[path]

    def observe_set(self, path):
        fd = self.directory(path)
        if path in self.sets:
            self.verify_set(path)
            return self.sets[path]
        # Register the complete name set before classification can fail. Keep
        # every classifier stat reached before opening/reading any sibling.
        names = set(os.listdir(fd))
        self.sets[path] = names
        for name in sorted(names):
            first = os.stat(name, dir_fd=fd, follow_symlinks=False)
            self.edge(path / name, observed=first)
        return names

    def file(self, path, *, maximum, optional=False, private=False):
        path = checked_path(path)
        if path in self.files:
            value = self.files[path]
            if value["first"] is not None and value["first"].st_size > maximum:
                limit("retained input exceeds its byte bound")
            self.verify_file(value)
            return value
        self.directory(path.parent)
        edge = self.edge(path)
        edge.update(directory=False, maximum=maximum)
        self.files[path] = edge
        first = edge["first"]
        if first is None:
            if optional:
                return edge
            invalid("required discovery input/resource is missing")
        if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1
                or private and stat.S_IMODE(first.st_mode) != 0o600):
            unsafe("retained file must be a single-link regular file with required private permissions")
        if first.st_size > maximum:
            limit("retained file exceeds its byte bound", maximum=maximum)
        edge["fd"] = os.open(path.name, file_open_flags(), dir_fd=edge["parent"])
        self.verify_edge(edge)
        edge["data"] = self.read(edge)
        edge["read"] = True
        self.verify_file(edge)
        return edge

    @staticmethod
    def read(edge):
        os.lseek(edge["fd"], 0, os.SEEK_SET)
        result, size = [], 0
        while True:
            chunk = os.read(edge["fd"], min(65536, edge["maximum"] + 1 - size))
            if not chunk:
                break
            result.append(chunk)
            size += len(chunk)
            if size > edge["maximum"]:
                unsafe("retained file grew beyond its byte bound")
        return b"".join(result)

    @staticmethod
    def verify_edge(edge):
        try:
            now = os.stat(edge["name"], dir_fd=edge["parent"], follow_symlinks=False)
        except FileNotFoundError:
            now = None
        first = edge["first"]
        compare = identity if edge["directory"] else stamp
        if ((now is None) != (first is None)
                or first is not None and compare(now) != compare(first)):
            unsafe("retained named edge changed")
        if edge["fd"] is not None and (first is None or compare(os.fstat(edge["fd"])) != compare(first)):
            unsafe("retained descriptor identity changed")
        if first is not None and not edge["directory"] and now.st_nlink != first.st_nlink:
            unsafe("retained file link count changed")

    def verify_file(self, edge):
        self.verify_edge(edge)
        if edge["read"]:
            if self.read(edge) != edge["data"]:
                unsafe("retained file bytes changed")
            self.verify_edge(edge)

    def verify_set(self, path):
        if set(os.listdir(self.directories[path])) != self.sets[path]:
            unsafe("retained complete directory set changed")

    def verify(self):
        def root():
            if identity(os.fstat(self.root_fd)) != identity(self.root_first):
                unsafe("retained filesystem root changed")
        checks = [root]
        checks += [lambda e=e: self.verify_edge(e) for e in self.edges.values()]
        checks += [lambda p=p: self.verify_set(p) for p in self.sets]
        checks += [lambda e=e: self.verify_file(e) for e in self.files.values()]
        try:
            verify_all(checks)
        except OSError:
            unsafe("retained filesystem lineage could not be verified")

    def close(self):
        for edge in reversed(list(self.edges.values())):
            close_fd(edge["fd"])
        close_fd(self.root_fd)


class DiscoveryStore:
    def __init__(self, tree, checkout, session):
        if type(session) is not str or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", session) is None:
            invalid("session must be a bounded lowercase slug")
        self.tree, self.checkout, self.session = tree, checkout, session
        self.root = checkout / ".work" / "research" / session / "discovery-v1"
        self.documents, self.raws = {}, {}
        self.pending_plan = None

    def scan(self):
        if self.tree.directory(self.root, optional=True) is None:
            return
        names = self.tree.observe_set(self.root)
        if not names <= set(FAMILIES):
            unsafe("unknown entry in discovery root")
        total = 0
        # Observe all fixed family slots, including missing ones, before parsing
        # or reading a single artifact. Failures retain every reached name/stat.
        for family in FAMILIES:
            self.tree.edge(self.root / family)
        for family in FAMILIES:
            path = self.root / family
            fd = self.tree.directory(path, optional=True)
            if fd is None:
                continue
            names = self.tree.observe_set(path)
            if len(names) > FAMILY_COUNTS[family]:
                limit("discovery family file count exceeds its bound", family=family)
        for family in FAMILIES:
            path = self.root / family
            if path not in self.tree.directories:
                continue
            family_total = 0
            for name in sorted(self.tree.sets[path]):
                if re.fullmatch(r"[0-9a-f]{64}\.json", name) is None:
                    unsafe("unexpected discovery artifact filename")
                entry = self.tree.edges[path / name]["first"]
                if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or stat.S_IMODE(entry.st_mode) != 0o600:
                    unsafe("discovery artifact type, link count or permissions are unsafe")
                family_total += entry.st_size
                total += entry.st_size
                if family_total > FAMILY_BYTES or total > TOTAL_BYTES:
                    limit("discovery store exceeds its byte bound")
                raw = self.tree.file(path / name, maximum=max(CAPS.values()), private=True)["data"]
                self.raws[path] = self.raws.get(path, {})
                self.raws[path][name] = raw
        self.tree.verify()

    def parse(self):
        for path, entries in self.raws.items():
            for name, raw in entries.items():
                doc = validate(parse_json(raw))
                if (KINDS[doc["kind"]] != path.name or name != self.filename(doc)
                        or raw != saved_bytes(doc) or doc["id"] in self.documents):
                    fail("DISCOVERY_GRAPH_INVALID", "artifact family, filename, saved bytes or identity disagree")
                self.documents[doc["id"]] = doc
        from video_paper_wiki_research.discovery_graph import Graph
        self.graph = Graph(self.documents, self.session)
        self.pending_plan = self.graph.pending_plan
        self.preflight()

    @staticmethod
    def filename(document):
        return document["content_sha256"] + ".json"

    def ensure_layout(self):
        self.tree.verify()
        current = self.checkout
        for name in (".work", "research", self.session, "discovery-v1"):
            current /= name
            self.tree.directory(current, create=True)
        self.tree.observe_set(self.root)
        if not self.tree.sets[self.root] <= set(FAMILIES):
            unsafe("unknown discovery root entry")
        for family in FAMILIES:
            self.tree.directory(self.root / family, create=True)
            self.tree.observe_set(self.root / family)
        self.tree.verify()

    def input(self, path, *, maximum):
        edge = self.tree.file(checked_path(path), maximum=maximum)
        self.tree.verify()
        return parse_json(edge["data"], maximum=maximum)

    def capacity(self, extra=(), *, pending_plan=...):
        """Charge nonpending bytes plus the complete pending reservation."""
        plan = self.pending_plan if pending_plan is ... else pending_plan
        docs = dict(self.documents)
        for doc in extra:
            validate(doc)
            if doc["id"] in docs and saved_bytes(docs[doc["id"]]) != saved_bytes(doc):
                fail("DISCOVERY_CONFLICT", "same artifact id has different bytes")
            docs[doc["id"]] = doc
        actual = {f: {"bytes": 0, "files": 0} for f in FAMILIES}
        base = {f: {"bytes": 0, "files": 0} for f in FAMILIES}
        pending = {f: {"bytes": 0, "files": 0} for f in FAMILIES}
        plan_id = None if plan is None else plan["id"]
        request_ids = {d["id"] for d in docs.values() if d["kind"] == "discovery-request" and d["data"]["plan_id"] == plan_id}
        for doc in docs.values():
            kind, data = doc["kind"], doc["data"]
            owned = plan is not None and (
                doc["id"] == plan_id
                or data.get("plan_id") == plan_id
                or kind == "discovery-observation" and data["request"]["id"] in request_ids
                or kind == "research-round-event" and data["plan"]["id"] == plan_id)
            family, size = KINDS[kind], len(saved_bytes(doc))
            actual[family]["bytes"] += size
            actual[family]["files"] += 1
            target = pending if owned else base
            target[family]["bytes"] += size
            target[family]["files"] += 1
        reserve = {f: {"bytes": 0, "files": 0} for f in FAMILIES}
        if plan is not None:
            n = len(plan["data"]["request_specs"])
            reserve = {"requests": {"bytes": n * 65536, "files": n},
                       "observations": {"bytes": n * 1114112, "files": n},
                       "metadata": {"bytes": 131072, "files": 2},
                       "proposals": {"bytes": 3407872, "files": 3},
                       "decisions": {"bytes": 262144, "files": 1}}
        charged = {f: {key: base[f][key] + max(reserve[f][key], pending[f][key])
                       for key in ("bytes", "files")} for f in FAMILIES}
        limiting = []
        for f in FAMILIES:
            if charged[f]["bytes"] > FAMILY_BYTES:
                limiting.append(f + ":bytes")
            if charged[f]["files"] > FAMILY_COUNTS[f]:
                limiting.append(f + ":files")
            if plan is not None and any(pending[f][k] > reserve[f][k] for k in ("bytes", "files")):
                limiting.append(f + ":pending_reservation")
        actual_total = sum(v["bytes"] for v in actual.values())
        total = (sum(v["bytes"] for v in base.values()) +
                 max(PENDING_BYTES if plan is not None else 0, sum(v["bytes"] for v in pending.values())))
        if total > TOTAL_BYTES:
            limiting.append("total:bytes")
        return {"fits": not limiting, "limiting_bounds": limiting, "actual": actual,
                "actual_total_bytes": actual_total, "charged": charged,
                "charged_total_bytes": total, "pending_reservation": reserve,
                "unspent_total_reservation": total - actual_total}

    def preflight(self, extra=(), *, pending_plan=...):
        self.tree.verify()
        result = self.capacity(extra, pending_plan=pending_plan)
        if not result["fits"]:
            limit("discovery physical reservation cannot fit", limiting_bounds=result["limiting_bounds"])
        return result

    def install(self, document):
        validate(document)
        raw = saved_bytes(document)
        from video_paper_wiki_research.discovery_graph import Graph
        prospective = Graph({**self.documents, document["id"]: document}, self.session)
        # The old pending reservation persists through event installation;
        # a new plan establishes its complete reservation before its first byte.
        reserved_plan = self.pending_plan or prospective.pending_plan
        self.preflight([document], pending_plan=reserved_plan)
        self.ensure_layout()
        family = self.root / KINDS[document["kind"]]
        target = family / self.filename(document)
        if document["id"] in self.documents:
            edge = self.tree.file(target, maximum=CAPS[document["kind"]], private=True)
            if edge["data"] != raw:
                fail("DISCOVERY_CONFLICT", "existing artifact bytes differ")
            self.tree.verify()
            return reference(document)
        edge = self.tree.file(target, maximum=CAPS[document["kind"]], optional=True, private=True)
        if edge["first"] is not None:
            unsafe("an unclassified artifact occupied a new committed slot")
        self.tree.verify()
        result, installed = _atomic_install(
            self.tree.directories[self.checkout / ".work"], self.tree.directories[family], target.name, raw,
            target=target, checkout_fd=self.tree.directories[self.checkout], return_identity=True)
        if result:
            unsafe("a first-observed missing artifact was filled by another writer")
        # The temporary link is gone when _atomic_install returns; retain the
        # installed inode and its final single-link stamp without adopting bytes.
        now = os.stat(target.name, dir_fd=edge["parent"], follow_symlinks=False)
        if (identity(now) != identity(installed) or now.st_nlink != 1
                or now.st_size != len(raw) or stat.S_IMODE(now.st_mode) != 0o600):
            unsafe("new artifact identity changed during installation")
        edge["first"] = now
        edge["fd"] = os.open(target.name, file_open_flags(), dir_fd=edge["parent"])
        edge["data"], edge["read"] = raw, True
        self.tree.sets[family].add(target.name)
        self.tree.verify()
        self.documents[document["id"]] = document
        self.graph = prospective
        self.pending_plan = prospective.pending_plan
        return reference(document)


@contextmanager
def open_store(session):
    tree, locked = RetainedTree(), None
    try:
        checkout = checked_path(Path.cwd())
        checkout_fd = tree.directory(checkout)
        try:
            fcntl.flock(checkout_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("DISCOVERY_BUSY", "another discovery command holds this checkout")
        locked = os.dup(checkout_fd)
        # Hold checkout marker and project bytes around the established root
        # validator. This happens before the first .work observation.
        marker = tree.edge(checkout / ".git")
        if marker["first"] is None:
            fail("WORKSPACE_ROOT_INVALID", "cwd is not a video-paper-wiki checkout root")
        if stat.S_ISDIR(marker["first"].st_mode):
            tree.directory(checkout / ".git")
        else:
            tree.file(checkout / ".git", maximum=65536)
        project_bytes = tree.file(checkout / "pyproject.toml", maximum=1048576)["data"]
        try:
            project = tomllib.loads(project_bytes.decode("utf-8"))
            if type(project.get("project")) is not dict or project["project"].get("name") != "video-paper-wiki":
                raise ValueError
        except (ValueError, UnicodeError):
            fail("WORKSPACE_ROOT_INVALID", "cwd is not a video-paper-wiki checkout root")
        store = DiscoveryStore(tree, checkout, session)
        store.scan()
        package = resources.files("video_paper_wiki_research")
        raws = {}
        for name in RESOURCE_PATHS:
            target = checked_path(package.joinpath(name))
            raws[name] = tree.file(target, maximum=2097152)["data"]
        tree.verify()
        with bound_resources(raws):
            store.parse()
            yield store
    except OSError:
        unsafe("discovery retained input or staging operation is unavailable")
    except Exception as exc:
        if not isinstance(exc, ResearchError) and hasattr(exc, "code"):
            code = "DISCOVERY_CONFLICT" if exc.code == "STAGING_CONFLICT" else exc.code
            raise ResearchError(code, str(exc), getattr(exc, "details", {}), exit_code=getattr(exc, "exit_code", 2)) from exc
        raise
    finally:
        try:
            tree.verify()
        finally:
            try:
                tree.close()
            finally:
                # A duplicate of the checkout open-file description keeps the
                # flock live through the entire retained descriptor cleanup.
                close_fd(locked)


# Imported last solely for boundary normalization; all decisions use the same
# shared JSON error type as the existing research CLI.
from video_paper_wiki_research.contracts import ResearchError
