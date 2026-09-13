"""Receipt-backed, read-only integrity audit for a Video Paper Wiki Vault."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import (close_fd, dir_open_flags, file_open_flags,
    open_dir_nofollow, read_child_regular, stamp)

SCHEMA = "video-paper-wiki.integrity-audit-authority.v1"
HEAD = "wiki/meta/registries/operation-head.json"
LOCK = ".vault-meta/mutation.lock"
RECEIPT_RE = re.compile(r"wiki/meta/operations/[0-9]{12}-[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
CURRENT_PREFIXES = (".raw/derived/", "wiki/papers/", "wiki/code/", "wiki/concepts/",
                    "wiki/meta/ledgers/", "wiki/meta/records/", "wiki/meta/reviews/",
                    "wiki/meta/gates/")
CURRENT_EXACT = {"wiki/meta/registries/gate-heads.json"}
MAX_RECEIPTS = 100_000
MAX_ENTRIES = 1_000_000
MAX_TOTAL = 64 * 1024 * 1024 * 1024


def _fail(code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
    raise ContractError(code, message, dict(details or {}))


def _parse(raw: bytes, title: str, path: str) -> dict[str, Any]:
    from video_paper_wiki.secure_io import parse_strict_json
    try:
        return validate_document(parse_strict_json(raw, invalid_code="RECEIPT_CHAIN_INVALID"), title)
    except ContractError:
        raise
    except Exception:
        _fail("RECEIPT_CHAIN_INVALID", "receipt authority is malformed", {"path": path})


class _Snapshot:
    """Retained Vault authority; all named edges are reopened descriptor-relative."""
    def __init__(self, root: Path) -> None:
        self.root = root
        try:
            self.root_stat = root.lstat()
        except OSError:
            _fail("AUDIT_RACE", "Vault root is unavailable")
        if not stat.S_ISDIR(self.root_stat.st_mode) or stat.S_ISLNK(self.root_stat.st_mode):
            _fail("AUDIT_RACE", "Vault root is unsafe")
        self.root_fd = open_dir_nofollow(root, missing_code="AUDIT_RACE", unsafe_code="AUDIT_RACE")
        if stamp(os.fstat(self.root_fd)) != stamp(self.root_stat):
            close_fd(self.root_fd); _fail("AUDIT_RACE", "Vault root changed")
        self.files: dict[str, tuple[os.stat_result, bytes]] = {}
        self.directories: dict[str, os.stat_result] = {"": os.fstat(self.root_fd)}
        self.absent: set[str] = set()
        self.inventory: set[str] | None = None

    @staticmethod
    def _parts(relative: str) -> tuple[str, ...]:
        if type(relative) is not str or not relative or relative.startswith("/") or "\x00" in relative:
            _fail("AUDIT_RACE", "Vault-relative path is invalid")
        parts = tuple(relative.split("/"))
        if any(x in {"", ".", ".."} for x in parts) or len(parts) > 64:
            _fail("AUDIT_RACE", "Vault-relative path is invalid")
        return parts

    def _parent_fd(self, relative: str, *, allow_missing: bool = False) -> tuple[int | None, tuple[str, ...]]:
        parts = self._parts(relative); fd = os.dup(self.root_fd)
        try:
            for index, part in enumerate(parts[:-1]):
                try: nxt = os.open(part, dir_open_flags(), dir_fd=fd)
                except FileNotFoundError:
                    if allow_missing: close_fd(fd); return None, parts
                    raise
                close_fd(fd); fd = nxt
                key = "/".join(parts[:index + 1]); current = os.fstat(fd)
                prior = self.directories.get(key)
                if prior is not None and stamp(prior) != stamp(current):
                    _fail("AUDIT_RACE", "managed directory changed", {"path": key})
                self.directories.setdefault(key, current)
            return fd, parts
        except ContractError:
            close_fd(fd); raise
        except OSError:
            close_fd(fd); _fail("AUDIT_RACE", "managed directory is unsafe")

    def track_dir(self, relative: str) -> None:
        if not relative: return
        fd, _ = self._parent_fd(relative + "/probe", allow_missing=False)
        close_fd(fd)

    def read(self, relative: str, *, max_bytes: int = 64 * 1024 * 1024) -> bytes:
        fd, parts = self._parent_fd(relative)
        assert fd is not None
        try:
            raw = read_child_regular(fd, parts[-1], path=self.root / relative,
                missing_code="AUDIT_RACE", unsafe_code="AUDIT_RACE", changed_code="AUDIT_RACE",
                max_bytes=max_bytes, limit_code="RECEIPT_CHAIN_INVALID")
            current = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        except ContractError: raise
        except OSError: _fail("AUDIT_RACE", "audited file changed", {"path": relative})
        finally: close_fd(fd)
        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
            _fail("AUDIT_RACE", "audited file is unsafe", {"path": relative})
        prior = self.files.get(relative)
        if prior is not None and (stamp(prior[0]) != stamp(current) or prior[1] != raw):
            _fail("AUDIT_RACE", "audited file changed", {"path": relative})
        self.files.setdefault(relative, (current, raw))
        self.absent.discard(relative)
        return raw

    def read_optional(self, relative: str, *, max_bytes: int = 64 * 1024 * 1024) -> bytes | None:
        fd, parts = self._parent_fd(relative, allow_missing=True)
        if fd is None:
            self.absent.add(relative); return None
        try:
            try: current = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                self.absent.add(relative); return None
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                _fail("AUDIT_RACE", "managed destination is unsafe", {"path": relative})
        finally: close_fd(fd)
        return self.read(relative, max_bytes=max_bytes)

    def _current_stat(self, relative: str) -> os.stat_result:
        fd, parts = self._parent_fd(relative)
        assert fd is not None
        try: return os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        except OSError: _fail("AUDIT_RACE", "Vault changed during integrity audit", {"path": relative})
        finally: close_fd(fd)

    def verify(self) -> None:
        try:
            if stamp(self.root.lstat()) != stamp(self.root_stat) or stamp(os.fstat(self.root_fd)) != stamp(self.root_stat):
                raise OSError
            for relative, first in self.directories.items():
                if not relative: continue
                fd = os.dup(self.root_fd)
                try:
                    for part in relative.split('/'):
                        nxt = os.open(part, dir_open_flags(), dir_fd=fd); close_fd(fd); fd = nxt
                    if stamp(os.fstat(fd)) != stamp(first): raise OSError
                finally: close_fd(fd)
            for relative, (first, _raw) in self.files.items():
                if stamp(self._current_stat(relative)) != stamp(first): raise OSError
            for relative in self.absent:
                fd, parts = self._parent_fd(relative, allow_missing=True)
                if fd is None: continue
                try:
                    try: os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError: continue
                    raise OSError
                finally: close_fd(fd)
            lock_fd, lock_parts = self._parent_fd(LOCK, allow_missing=True)
            if lock_fd is not None:
                try:
                    try: os.stat(lock_parts[-1], dir_fd=lock_fd, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise OSError
                finally: close_fd(lock_fd)
            if self.inventory is not None:
                try: current=_inventory_names(self)
                except ContractError as exc: raise ContractError("AUDIT_RACE","Vault changed during final inventory verification",{}) from exc
                if current != self.inventory: raise OSError
        except ContractError: raise
        except OSError: _fail("AUDIT_RACE", "Vault changed during integrity audit")

    def close(self) -> None: close_fd(self.root_fd)


def _managed(path: str) -> bool:
    return path in CURRENT_EXACT or any(path.startswith(prefix) and len(path) > len(prefix) for prefix in CURRENT_PREFIXES)


def _walk_inventory(snap: _Snapshot, *, read_bytes: bool) -> dict[str, tuple[str, int, int]]:
    result: dict[str, tuple[str, int, int]] = {}; total = 0; entries_seen = 0
    keys: dict[str, str] = {}
    def walk_from(parent_fd: int, relative_dir: str, depth: int) -> None:
        nonlocal total, entries_seen
        if depth > 64: _fail("RECEIPT_CHAIN_INVALID", "managed tree exceeds depth limit")
        try: fd=os.open(relative_dir.rsplit('/',1)[-1],dir_open_flags(),dir_fd=parent_fd)
        except FileNotFoundError: return
        except OSError: _fail("AUDIT_RACE","managed directory changed during enumeration")
        keydir=relative_dir; current=os.fstat(fd); prior=snap.directories.get(keydir)
        if prior is not None and stamp(prior)!=stamp(current): close_fd(fd);_fail("AUDIT_RACE","managed directory changed",{"path":keydir})
        snap.directories.setdefault(keydir,current)
        if not read_bytes: result[keydir]=(str(current.st_dev)+":"+str(current.st_ino),0,stat.S_IMODE(current.st_mode))
        try:
            entries=sorted(os.scandir(fd),key=lambda x:x.name.encode("utf-8"))
            for entry in entries:
                entries_seen += 1
                if entries_seen > MAX_ENTRIES: _fail("RECEIPT_CHAIN_INVALID","audit resource limit exceeded")
                relative=relative_dir+"/"+entry.name; st=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode): _fail("OUT_OF_BAND_WRITE","managed tree contains a symlink")
                portable=unicodedata.normalize("NFC",relative).casefold()
                if portable in keys and keys[portable]!=relative:_fail("OUT_OF_BAND_WRITE","managed paths collide portably")
                keys[portable]=relative
                if stat.S_ISDIR(st.st_mode):
                    if relative.startswith("wiki/meta/operations/"):_fail("OUT_OF_BAND_WRITE","receipt directory contains a non-receipt entry")
                    walk_from(fd,relative,depth+1);continue
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1: _fail("OUT_OF_BAND_WRITE","managed tree contains an unsafe entry")
                selected=(relative.startswith("wiki/meta/operations/") or relative==HEAD or _managed(relative) or relative.startswith(".raw/captured/"))
                if not selected: continue
                mode=stat.S_IMODE(st.st_mode)
                if mode & 0o077:_fail("OUT_OF_BAND_WRITE","managed file permissions are not private",{"path":relative})
                if read_bytes:
                    raw=snap.read(relative,max_bytes=1024*1024 if relative==HEAD or relative.startswith("wiki/meta/operations/") else 64*1024*1024);total += len(raw)
                    if total>MAX_TOTAL:_fail("RECEIPT_CHAIN_INVALID","audit resource limit exceeded")
                    result[relative]=(hashlib.sha256(raw).hexdigest(),len(raw),mode)
                else:
                    result[relative]=(str(st.st_dev)+":"+str(st.st_ino),st.st_size,mode)
        except OSError:_fail("AUDIT_RACE","managed directory changed during enumeration")
        finally:close_fd(fd)
    for top in (".raw/captured",".raw/derived","wiki/papers","wiki/code","wiki/concepts",
                "wiki/meta/ledgers","wiki/meta/records","wiki/meta/reviews","wiki/meta/gates","wiki/meta/operations"):
        parent,parts=snap._parent_fd(top,allow_missing=True)
        if parent is None:continue
        try:walk_from(parent,top,1)
        finally:close_fd(parent)
    for relative in (HEAD,"wiki/meta/registries/gate-heads.json"):
        if read_bytes:
            raw=snap.read_optional(relative,max_bytes=1024*1024 if relative==HEAD else 64*1024*1024)
            if raw is None:continue
            st=snap.files[relative][0];mode=stat.S_IMODE(st.st_mode)
            if mode&0o077:_fail("OUT_OF_BAND_WRITE","managed file permissions are not private",{"path":relative})
            result[relative]=(hashlib.sha256(raw).hexdigest(),len(raw),mode)
        else:
            fd,parts=snap._parent_fd(relative,allow_missing=True)
            if fd is None:continue
            try:
                try:st=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:continue
                if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_nlink!=1:_fail("OUT_OF_BAND_WRITE","managed exact slot is unsafe")
                result[relative]=(str(st.st_dev)+":"+str(st.st_ino),st.st_size,stat.S_IMODE(st.st_mode))
            finally:close_fd(fd)
    return result


def _inventory_names(snap: _Snapshot) -> set[str]:
    return set(_walk_inventory(snap,read_bytes=False))


def _enumerate(root: Path, snap: _Snapshot) -> dict[str, tuple[str, int, int]]:
    result=_walk_inventory(snap,read_bytes=True);snap.inventory=_inventory_names(snap);return result


def _pristine(actual: Mapping[str, tuple[str, int, int]], snap: _Snapshot) -> bool:
    if set(actual) != {"wiki/meta/ledgers/claim-ledger.json", "wiki/meta/ledgers/source-ledger.json"}: return False
    from video_paper_wiki.secure_io import parse_strict_json
    source=parse_strict_json(snap.read("wiki/meta/ledgers/source-ledger.json"),invalid_code="OUT_OF_BAND_WRITE")
    claims=parse_strict_json(snap.read("wiki/meta/ledgers/claim-ledger.json"),invalid_code="OUT_OF_BAND_WRITE")
    def timestamp(value: object) -> bool:
        if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",value) is None:return False
        try:datetime.fromisoformat(value[:-1]+"+00:00")
        except ValueError:return False
        return True
    return (type(source) is dict and set(source)=={"schema","generated_at","sources"} and source["schema"]=="claude-obsidian.source-ledger.v1" and source["sources"]=={} and timestamp(source["generated_at"])
            and type(claims) is dict and set(claims)=={"schema","generated_at","claims"} and claims["schema"]=="claude-obsidian.claim-ledger.v1" and claims["claims"]=={} and timestamp(claims["generated_at"]))


def audit_integrity(vault_root: Path | str, *, runtime_result: object | None = None,
                    _snapshot: _Snapshot | None = None) -> dict[str, Any]:
    """Audit canonical receipts and managed bytes without mutating the Vault."""
    root = Path(vault_root)
    snap = _snapshot or _Snapshot(root); owns = _snapshot is None
    try:
        lock_fd,lock_parts=snap._parent_fd(LOCK,allow_missing=True)
        if lock_fd is not None:
            try:
                try:os.stat(lock_parts[-1],dir_fd=lock_fd,follow_symlinks=False)
                except FileNotFoundError:snap.absent.add(LOCK)
                else:_fail("AUDIT_RACE","mutation lock is present")
            finally:close_fd(lock_fd)
        else:snap.absent.add(LOCK)
        actual = _enumerate(root, snap)
        if HEAD not in actual:
            if not actual:
                value = {"schema": SCHEMA, "classification": "empty", "valid": True, "head": None,
                         "receipts": [], "current_paths": [], "ever_claimed_raw": [], "orphans": [],
                         "runtime_correlated": runtime_result is None}
                snap.verify()
                return validate_integrity_audit_authority(value)
            if _pristine(actual, snap):
                _fail("RECEIPT_BOOTSTRAP_REQUIRED", "pristine ledgers require a real genesis publication")
            _fail("OUT_OF_BAND_WRITE", "headless managed state is not pristine")
        head_raw = snap.read(HEAD, max_bytes=1024 * 1024)
        head = _parse(head_raw, "video-paper-wiki.operation-head.v1", HEAD)
        path = head["receipt_path"]; digest = head["receipt_sha256"]
        chain: list[tuple[str, dict[str, Any], bytes]] = []
        seen: set[str] = set()
        while path is not None:
            if path in seen or len(chain) >= MAX_RECEIPTS or RECEIPT_RE.fullmatch(path) is None:
                _fail("RECEIPT_CHAIN_INVALID", "receipt chain is cyclic, too large, or malformed")
            seen.add(path); raw = snap.read(path, max_bytes=1024 * 1024)
            if hashlib.sha256(raw).hexdigest() != digest:
                _fail("RECEIPT_CHAIN_INVALID", "receipt digest differs", {"path": path})
            receipt = _parse(raw, "video-paper-wiki.operation-receipt.v1", path)
            if raw != canonicalize(receipt): _fail("RECEIPT_CHAIN_INVALID","receipt is not exact JCS",{"path":path})
            expected_path=f"wiki/meta/operations/{receipt['sequence']:012d}-{receipt['operation_id']}.json"
            if path!=expected_path or receipt_intent_sha256(receipt)!=receipt['intent_sha256']: _fail("RECEIPT_CHAIN_INVALID","receipt identity differs",{"path":path})
            chain.append((path, receipt, raw))
            previous = receipt["previous"]
            path = None if previous is None else previous["path"]
            digest = None if previous is None else previous["sha256"]
        if head_raw != canonicalize(head): _fail("RECEIPT_CHAIN_INVALID","head is not exact JCS")
        if not chain or chain[0][1]["sequence"] != head["sequence"] or [x[1]["sequence"] for x in chain] != list(range(head["sequence"], 0, -1)):
            _fail("RECEIPT_CHAIN_INVALID", "receipt sequence has a gap or rollback")
        receipt_files = {p for p in actual if p.startswith("wiki/meta/operations/")}
        if receipt_files != seen:
            _fail("RECEIPT_CHAIN_INVALID", "receipt set contains unreachable or missing entries")
        state: dict[str, str] = {}
        claimed_raw: set[str] = set()
        for _path, receipt, _raw in reversed(chain):
            for item in receipt["claimed_inputs"]:
                if item["path"].startswith(".raw/"):
                    claimed_raw.add(item["path"])
                known=state.get(item["path"])
                if known is not None and known!=item["sha256"]:_fail("RECEIPT_CHAIN_INVALID","claimed input differs at replay point",{"path":item["path"]})
                if known is None:
                    pristine_claim=(receipt["sequence"]==1 and item["path"] in {"wiki/meta/ledgers/claim-ledger.json","wiki/meta/ledgers/source-ledger.json"})
                    captured_match=re.fullmatch(r"\.raw/captured/([0-9a-f]{64})\.[A-Za-z0-9][A-Za-z0-9._-]*",item["path"])
                    captured_claim=captured_match is not None and captured_match.group(1)==item["sha256"]
                    if not (pristine_claim or captured_claim):_fail("RECEIPT_CHAIN_INVALID","receipt claims an unknown managed input",{"path":item["path"]})
                    state[item["path"]]=item["sha256"]
            for write in receipt["writes"]:
                prior = state.get(write["path"])
                if (write["mode"] == "create" and (write["before_sha256"] is not None or prior is not None)) or (write["mode"] == "replace" and prior != write["before_sha256"]):
                    _fail("RECEIPT_CHAIN_INVALID", "receipt replay precondition differs", {"path": write["path"]})
                state[write["path"]] = write["after_sha256"]
                if write["path"].startswith(".raw/"):
                    claimed_raw.add(write["path"])
        current = {p: d for p, d in state.items() if _managed(p)}
        actual_current = {p: v[0] for p, v in actual.items() if _managed(p)}
        if current != actual_current:
            _fail("OUT_OF_BAND_WRITE", "managed complete set differs from receipt replay")
        for path in claimed_raw:
            if path not in actual or actual[path][0] != state.get(path):
                _fail("OUT_OF_BAND_WRITE", "ever-claimed raw input is missing or changed", {"path": path})
        orphans = sorted(p for p in actual if p.startswith(".raw/captured/") and p not in claimed_raw)
        runtime_ok = runtime_result is None
        if runtime_result is not None:
            from video_paper_wiki.operation_result import validate_operation_result_authority
            try: runtime=validate_operation_result_authority(runtime_result)
            except ContractError as exc: raise ContractError("RUNTIME_CORRELATION_INVALID","runtime authority is invalid",exc.details) from exc
            latest_path,latest,_=chain[0];result=runtime["result"]
            paths=[item["path"] for item in latest["writes"]]+[latest_path,HEAD]
            hashes={path:actual[path][0] for path in paths};modes={path:actual[path][2] for path in paths}
            if (result["changed_paths"]!=paths or result["hashes"]!=hashes or result["modes"]!=modes
                    or runtime["transaction"]["receipt"]!=latest or runtime["transaction"]["head"]!=head):
                _fail("RUNTIME_CORRELATION_INVALID", "runtime result does not correlate with canonical receipt bytes")
            runtime_ok = True
        value = {"schema": SCHEMA, "classification": "receipt_backed", "valid": True,
                 "head": head, "receipts": [p for p, _r, _b in reversed(chain)],
                 "current_paths": sorted(current), "ever_claimed_raw": sorted(claimed_raw),
                 "orphans": orphans, "runtime_correlated": runtime_ok}
        snap.verify()
        return validate_integrity_audit_authority(value)
    except BaseException:
        snap.verify()
        raise
    finally:
        if owns: snap.close()


def validate_integrity_audit_authority(value: object) -> dict[str, Any]:
    return validate_document(value, SCHEMA)
