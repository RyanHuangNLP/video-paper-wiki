"""Pure validation for the closed base projection input inventory."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.projection_runtime import _preflight

_TITLE = "video-paper-wiki.projection-input.v1"
_HEX = re.compile(r"[0-9a-f]{64}")
_WINDOWS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_OPAQUE_HASH_PATH = {
    "captured-artifact": re.compile(r"\.raw/captured/([0-9a-f]{64})\.[^/]+"),
    "code-evidence-manifest": re.compile(r"\.raw/derived/code-manifests/([0-9a-f]{64})\.json"),
    "alignment-manifest": re.compile(r"\.raw/derived/alignment-manifests/([0-9a-f]{64})\.json"),
}
_SINGLETONS = {"source-ledger", "claim-ledger", "taxonomy"}
_BRANCHES = {
    "source-ledger": re.compile(r"wiki/meta/ledgers/source-ledger\.json"),
    "claim-ledger": re.compile(r"wiki/meta/ledgers/claim-ledger\.json"),
    "taxonomy": re.compile(r"taxonomy/v1\.json"),
    "paper-record": re.compile(r"wiki/meta/records/papers/[A-Za-z0-9][A-Za-z0-9._-]*\.json"),
    "repo-record": re.compile(r"wiki/meta/records/repos/[A-Za-z0-9][A-Za-z0-9._-]*\.json"),
    "assessment-event": re.compile(r"wiki/meta/reviews/clm-[0-9a-f]{20}/ase-[0-9a-f]{20}\.json"),
    "captured-artifact": re.compile(r"\.raw/captured/[0-9a-f]{64}\.[A-Za-z0-9][A-Za-z0-9._-]*"),
    "docling-document": re.compile(r"\.raw/derived/[0-9a-f]{64}/docling/[0-9a-f]{64}/document\.json"),
    "parser-config": re.compile(r"\.raw/derived/[0-9a-f]{64}/docling/[0-9a-f]{64}/parser-config\.json"),
    "model-manifest": re.compile(r"\.raw/derived/[0-9a-f]{64}/docling/[0-9a-f]{64}/model-manifest\.json"),
    "run-manifest": re.compile(r"\.raw/derived/[0-9a-f]{64}/runs/[A-Za-z0-9][A-Za-z0-9._-]*\.json"),
    "code-evidence-manifest": re.compile(r"\.raw/derived/code-manifests/[0-9a-f]{64}\.json"),
    "alignment-manifest": re.compile(r"\.raw/derived/alignment-manifests/[0-9a-f]{64}\.json"),
}


def _fail(code: str, pointer: str, message: str) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _pf(value: object) -> None:
    try:
        _preflight(value)
    except ContractError as exc:
        if exc.code == "PROJECTION_LIMIT_EXCEEDED":
            raise
        raise ContractError("SCHEMA_INVALID", "unsupported projection input value", exc.details) from None


def _schema(value: object) -> None:
    if type(value) is not dict or set(value) != {"schema", "entries"}:
        _fail("PROJECTION_INPUT_INVALID", "", "projection input root is not closed")
    if value.get("schema") != _TITLE or type(value.get("entries")) is not list or len(value["entries"]) < 3:
        _fail("PROJECTION_INPUT_INVALID", "", "projection input root is invalid")
    for index, item in enumerate(value["entries"]):
        pointer=f"/entries/{index}"
        if type(item) is not dict or set(item)!={"path","kind","sha256","size_bytes"}:
            _fail("PROJECTION_INPUT_INVALID",pointer,"projection input entry is not closed")
        path,kind,digest,size=item["path"],item["kind"],item["sha256"],item["size_bytes"]
        if (type(path) is not str or type(kind) is not str or kind not in _BRANCHES
                or _BRANCHES[kind].fullmatch(path) is None or type(digest) is not str
                or _HEX.fullmatch(digest) is None or type(size) is not int or not 0<=size<=64*1024*1024):
            _fail("PROJECTION_INPUT_INVALID",pointer,"projection input entry is invalid")


def _portable(path: str, index: int, seen: dict[tuple[str, ...], str]) -> None:
    pointer = f"/entries/{index}/path"
    try:
        raw = path.encode("utf-8")
    except UnicodeError:
        _fail("PROJECTION_INPUT_INVALID", pointer, "projection path is invalid")
    parts = path.split("/")
    if (not path or path.startswith("/") or path.endswith("/") or "//" in path
            or len(raw) > 1024 or unicodedata.normalize("NFC", path) != path
            or any(p in {"", ".", ".."} for p in parts)
            or any(any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts)):
        _fail("PROJECTION_INPUT_INVALID", pointer, "projection path is invalid")
    keys = []
    for part in parts:
        key = unicodedata.normalize("NFC", part.casefold())
        stem = key.rstrip(".").split(".", 1)[0]
        if key in {".git", ".obsidian", ".vault-meta"} or part.endswith(".") or stem in _WINDOWS:
            _fail("PROJECTION_INPUT_INVALID", pointer, "projection path is not portable")
        keys.append(key)
    for length in range(1, len(keys) + 1):
        alias = tuple(keys[:length])
        spelling = "/".join(parts[:length])
        if alias in seen and seen[alias] != spelling:
            _fail("PROJECTION_INPUT_INVALID", pointer, "projection paths collide")
        seen[alias] = spelling


def _variable_component(value: str, pointer: str) -> None:
    key=unicodedata.normalize("NFC",value.casefold())
    if value.endswith(".") or key.rstrip(".").split(".",1)[0] in _WINDOWS:
        _fail("PROJECTION_INPUT_INVALID",pointer,"variable path component is not portable")


def _validated(value: object) -> dict:
    _pf(value)
    _schema(value)
    assert type(value) is dict
    entries = value["entries"]
    if sum(item["size_bytes"] for item in entries) > 8 * 1024 * 1024 * 1024:
        _fail("PROJECTION_LIMIT_EXCEEDED", "/entries", "declared byte budget exceeded")
    previous: bytes | None = None
    seen_paths: dict[tuple[str, ...], str] = {}
    counts: dict[str, int] = {}
    digests: dict[str, set[str]] = {}
    for index, item in enumerate(entries):
        path, kind = item["path"], item["kind"]
        encoded = path.encode("utf-8")
        if previous is not None and encoded <= previous:
            _fail("PROJECTION_INPUT_INVALID", f"/entries/{index}/path", "inventory paths are not strictly ordered")
        previous = encoded
        _portable(path, index, seen_paths)
        if kind in {"paper-record","repo-record","run-manifest"}:
            _variable_component(path.rsplit("/",1)[1][:-5],f"/entries/{index}/path")
        elif kind=="captured-artifact":
            _variable_component(path.rsplit("/",1)[1][65:],f"/entries/{index}/path")
        counts[kind] = counts.get(kind, 0) + 1
        match = _OPAQUE_HASH_PATH.get(kind)
        if match is not None:
            found = match.fullmatch(path)
            if found is None or found.group(1) != item["sha256"]:
                _fail("PROJECTION_INPUT_INVALID", f"/entries/{index}/sha256", "filename digest does not match file digest")
            if kind == "captured-artifact":
                if item["sha256"] in digests.setdefault(kind, set()):
                    _fail("PROJECTION_INPUT_INVALID", f"/entries/{index}/sha256", "captured digest is duplicated")
                digests[kind].add(item["sha256"])
    for kind in _SINGLETONS:
        if counts.get(kind) != 1:
            _fail("PROJECTION_INPUT_INVALID", "/entries", "required singleton input is missing or duplicated")
    return value


def validate_projection_inventory(value: object) -> None:
    _validated(value)


def validate_projection_bytes(value: object, *, bytes_map: object) -> None:
    inventory = _validated(value)
    if type(bytes_map) is not dict:
        _fail("PROJECTION_INPUT_MISMATCH", "/bytes_map", "byte map must be an exact object")
    expected = {item["path"] for item in inventory["entries"]}
    if any(type(key) is not str for key in bytes_map) or set(bytes_map) != expected:
        _fail("PROJECTION_INPUT_MISMATCH", "/bytes_map", "byte map keys do not equal inventory paths")
    total = 0
    for item in inventory["entries"]:
        payload = bytes_map[item["path"]]
        if type(payload) is not bytes:
            _fail("PROJECTION_INPUT_MISMATCH", "/bytes_map", "byte map values must be exact bytes")
        total += len(payload)
        if len(payload) > 64 * 1024 * 1024 or total > 8 * 1024 * 1024 * 1024:
            _fail("PROJECTION_LIMIT_EXCEEDED", "/bytes_map", "actual byte budget exceeded")
    for item in inventory["entries"]:
        payload = bytes_map[item["path"]]
        if len(payload) != item["size_bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            _fail("PROJECTION_INPUT_MISMATCH", "/bytes_map", "declared and actual bytes differ")


__all__ = ["validate_projection_inventory", "validate_projection_bytes"]
