"""Parser-config, model-manifest, and sealed profile construction.

Runtime version checks use importlib.metadata, never a self-reported version.
The agent CLI never imports Docling; `vpwiki-parser` calls these functions.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import stat
from pathlib import Path
from typing import Any, Callable

from video_paper_wiki.identity import pipeline_fingerprint
from video_paper_wiki.secure_io import SOURCE_CHANGED, SecureIOError, read_regular_file, stamp

from video_paper_wiki_research.contracts import (
    DOCLING_CORE_VERSION,
    DOCLING_VERSION,
    MODEL_FILE_MAX,
    MODEL_MAX_DEPTH,
    MODEL_MAX_FILES,
    MODEL_TOTAL_MAX,
    PARSER_CONFIG,
    PARSER_MODELS_MISSING,
    PARSER_PROFILE_CHANGED,
    PARSER_PROFILE_INVALID,
    PARSER_RUNTIME_INCOMPATIBLE,
    PARSER_RUNTIME_MISSING,
    ResearchError,
    exact_ref,
    jcs_bytes,
    saved_bytes,
    seal_document,
    sha256_bytes,
)
from video_paper_wiki_research.storage import (
    RetainedResearchSession,
    stage_research,
)

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def installed_versions() -> tuple[str, str]:
    try:
        docling = importlib.metadata.version("docling")
        core = importlib.metadata.version("docling-core")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ResearchError(PARSER_RUNTIME_MISSING, "Docling runtime is not installed") from exc
    if docling != DOCLING_VERSION or core != DOCLING_CORE_VERSION:
        raise ResearchError(
            PARSER_RUNTIME_INCOMPATIBLE,
            "installed Docling versions differ from the pinned runtime",
            {"docling": docling, "docling_core": core},
        )
    return docling, core


def _unsafe_model(path: Path, message: str) -> None:
    raise ResearchError(PARSER_PROFILE_INVALID, message, {"path": path.as_posix()})


def _relative_posix(root: Path, path: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel in {".", ""} or rel.startswith("/") or "\\" in rel:
        _unsafe_model(path, "model path is not a portable relative path")
    for segment in rel.split("/"):
        if not segment or segment in {".", ".."} or _SEGMENT.fullmatch(segment) is None:
            _unsafe_model(path, "model path is not a portable relative path")
    return rel


def inventory_models(root: Path) -> tuple[list[dict[str, Any]], int, tuple[tuple[str, str, int, tuple[int, ...]], ...]]:
    if not root.exists() or root.is_symlink() or not root.is_dir():
        raise ResearchError(PARSER_MODELS_MISSING, "model tree is missing")
    root_st = os.lstat(root)
    if stat.S_ISLNK(root_st.st_mode) or not stat.S_ISDIR(root_st.st_mode):
        raise ResearchError(PARSER_MODELS_MISSING, "model tree is missing")
    files: list[dict[str, Any]] = []
    identities: list[tuple[str, str, int, tuple[int, ...]]] = []
    total = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        depth = len(current.relative_to(root).parts)
        if depth > MODEL_MAX_DEPTH:
            _unsafe_model(current, "model tree exceeds depth 16")
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise ResearchError(
                PARSER_PROFILE_INVALID, "model directory is unreadable", {"path": current.as_posix()}
            ) from exc
        if stat.S_ISLNK(st.st_mode):
            _unsafe_model(current, "model tree must not contain symlinks")
        if not stat.S_ISDIR(st.st_mode):
            _unsafe_model(current, "model tree contains a special path")
        dirnames.sort()
        filenames.sort()
        for name in list(dirnames):
            child = current / name
            child_st = os.lstat(child)
            if stat.S_ISLNK(child_st.st_mode) or not stat.S_ISDIR(child_st.st_mode):
                _unsafe_model(child, "model tree must not contain symlinks or special files")
        for name in filenames:
            child = current / name
            child_st = os.lstat(child)
            if stat.S_ISLNK(child_st.st_mode):
                _unsafe_model(child, "model tree must not contain symlinks")
            if not stat.S_ISREG(child_st.st_mode) or stat.S_ISFIFO(child_st.st_mode) or stat.S_ISSOCK(child_st.st_mode):
                _unsafe_model(child, "model tree must contain only regular files and directories")
            if child_st.st_nlink != 1:
                _unsafe_model(child, "model files must not be hard-linked")
            if child_st.st_size > MODEL_FILE_MAX:
                _unsafe_model(child, "model file exceeds 4 GiB")
            file_count += 1
            if file_count > MODEL_MAX_FILES:
                _unsafe_model(child, "model tree exceeds 4096 files")
            rel = _relative_posix(root, child)
            digest = _hash_file(child, child_st)
            total += child_st.st_size
            if total > MODEL_TOTAL_MAX:
                _unsafe_model(child, "model tree exceeds 32 GiB")
            files.append({"path": rel, "sha256": digest, "size_bytes": int(child_st.st_size)})
            identities.append(
                (rel, digest, int(child_st.st_size), (int(child_st.st_dev), int(child_st.st_ino), int(child_st.st_mtime_ns)))
            )
    if not files:
        raise ResearchError(PARSER_MODELS_MISSING, "model tree is empty")
    files.sort(key=lambda item: item["path"].encode("utf-8"))
    identities_tuple = tuple(sorted(identities, key=lambda item: item[0].encode("utf-8")))
    paths = [item["path"] for item in files]
    if len(paths) != len(set(paths)):
        raise ResearchError(PARSER_PROFILE_INVALID, "model inventory paths must be unique")
    return files, total, identities_tuple


def _hash_file(path: Path, expected: os.stat_result) -> str:
    hasher = hashlib.sha256()
    try:
        raw = read_regular_file(
            path,
            missing_code=PARSER_PROFILE_INVALID,
            unsafe_code=PARSER_PROFILE_INVALID,
            changed_code=SOURCE_CHANGED,
            max_bytes=MODEL_FILE_MAX,
            limit_code=PARSER_PROFILE_INVALID,
        )
    except SecureIOError as exc:
        if exc.code == SOURCE_CHANGED:
            raise ResearchError(PARSER_PROFILE_CHANGED, "model file changed while hashed") from exc
        raise ResearchError(PARSER_PROFILE_INVALID, str(exc.message), dict(exc.details)) from exc
    after = os.lstat(path)
    if stamp(after) != stamp(expected):
        raise ResearchError(PARSER_PROFILE_CHANGED, "model file identity changed while hashed")
    hasher.update(raw)
    return hasher.hexdigest()


def recheck_models(
    root: Path,
    expected: tuple[tuple[str, str, int, tuple[int, ...]], ...],
) -> None:
    files, _total, now = inventory_models(root)
    if now != expected:
        raise ResearchError(PARSER_PROFILE_CHANGED, "model tree membership or bytes changed")
    del files


def create_profile(
    session: RetainedResearchSession,
    artifacts_path: Path,
    *,
    version_loader: Callable[[], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    loader = installed_versions if version_loader is None else version_loader
    loader()
    files, total, identities = inventory_models(artifacts_path)
    config = dict(PARSER_CONFIG)
    config["options"] = dict(PARSER_CONFIG["options"])
    manifest = {"schema": "manual-pdf-model-manifest.v1", "files": files, "total_bytes": total}
    config_bytes = jcs_bytes(config) + b"\n"
    manifest_bytes = jcs_bytes(manifest) + b"\n"
    parser = {
        "engine": "docling",
        "engine_version": DOCLING_VERSION,
        "core_version": DOCLING_CORE_VERSION,
        "config_sha256": sha256_bytes(config_bytes),
        "model_manifest_sha256": sha256_bytes(manifest_bytes),
    }
    fingerprint = pipeline_fingerprint(parser)
    data = {"parser": parser, "parser_config": config, "model_manifest": manifest}
    document = seal_document("profile", data)
    envelope_bytes = saved_bytes(document)
    recheck_models(artifacts_path, identities)
    session.verify()
    cfg = stage_research(session, ("profile", "parser-config.json"), config_bytes)
    man = stage_research(session, ("profile", "model-manifest.json"), manifest_bytes)
    env = stage_research(session, ("profile", "profile.json"), envelope_bytes)
    recheck_models(artifacts_path, identities)
    session.verify()
    if sha256_bytes(cfg.path.read_bytes()) != parser["config_sha256"]:
        raise ResearchError(PARSER_PROFILE_INVALID, "parser-config bytes differ after staging")
    if sha256_bytes(man.path.read_bytes()) != parser["model_manifest_sha256"]:
        raise ResearchError(PARSER_PROFILE_INVALID, "model-manifest bytes differ after staging")
    return {
        "profile": document,
        "ref": exact_ref(document),
        "path": env.path.as_posix(),
        "parser_config_path": cfg.path.as_posix(),
        "model_manifest_path": man.path.as_posix(),
        "pipeline_fingerprint": fingerprint,
        "already_staged": env.already_staged,
        "next_action": "awaiting_parser_export",
    }


def load_profile(path: Path) -> tuple[dict[str, Any], bytes]:
    from video_paper_wiki_research.storage import load_saved_document

    return load_saved_document(path, kind="profile", invalid_code=PARSER_PROFILE_INVALID)
