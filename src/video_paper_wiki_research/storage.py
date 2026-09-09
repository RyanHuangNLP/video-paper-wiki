"""Retained `.work/research/<session>/manual-pdf` layout and staging wrapper.

Internal helpers: `stage_bytes`, checkout resolution, and directory-identity
checks from `video_paper_wiki.staging`. Semantics are unchanged. Generated
research files stay under `.work/research/<session>/manual-pdf/`; PDF bytes
use the explicit `.work/blobs/<sha256>` exception.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from video_paper_wiki.secure_io import (
    SOURCE_CHANGED,
    SecureIOError,
    read_regular_file,
    stamp,
)
from video_paper_wiki.staging import (
    CODE_STAGING_CONFLICT,
    CODE_WORK_PATH_UNSAFE,
    StagingError,
    WORK_DIRNAME,
    _close_fd,
    _ensure_dir_at,
    _open_dir_at,
    _open_dir_path,
    _require_fd_inside_work,
    _require_same_directory,
    _require_work_still_in_checkout,
    resolve_checkout_root,
    stage_bytes,
    validate_batch_id,
)

from video_paper_wiki_research.contracts import (
    FAMILY_LIMIT,
    INTAKE_INVALID,
    MANUAL_PDF_CHANGED,
    ResearchError,
    exact_ref,
    parse_envelope_json,
    saved_bytes,
    sha256_bytes,
    validate_document,
)

RESEARCH_BATCH = "research"
MANUAL_PDF = "manual-pdf"
BLOB_BATCH = "blobs"
FAMILIES = ("intakes", "contexts", "proposals", "runs", "failed-runs", "profile")


@dataclass
class RetainedResearchSession:
    checkout: Path
    session_id: str
    checkout_fd: int
    work_fd: int
    research_fd: int
    session_fd: int
    output_fd: int
    identities: tuple[os.stat_result, os.stat_result, os.stat_result, os.stat_result, os.stat_result]

    @property
    def output_root(self) -> Path:
        return self.checkout / WORK_DIRNAME / RESEARCH_BATCH / self.session_id / MANUAL_PDF

    @property
    def work_root(self) -> Path:
        return self.checkout / WORK_DIRNAME

    def posix(self, *parts: str) -> str:
        return (Path(WORK_DIRNAME) / RESEARCH_BATCH / self.session_id / MANUAL_PDF / Path(*parts)).as_posix()

    def path(self, *parts: str) -> Path:
        return self.output_root.joinpath(*parts)

    def verify(self) -> None:
        mapping = (
            (self.checkout_fd, self.identities[0], self.checkout),
            (self.work_fd, self.identities[1], self.work_root),
            (self.research_fd, self.identities[2], self.work_root / RESEARCH_BATCH),
            (self.session_fd, self.identities[3], self.work_root / RESEARCH_BATCH / self.session_id),
            (self.output_fd, self.identities[4], self.output_root),
        )
        for fd, expected, path in mapping:
            _require_same_directory(fd, expected, path)
        _require_work_still_in_checkout(self.work_fd, self.checkout_fd, self.work_root)
        _require_fd_inside_work(self.output_fd, self.work_fd, self.output_root)
        opened: list[int] = []
        try:
            checkout_fd = _open_dir_path(self.checkout)
            opened.append(checkout_fd)
            _require_same_directory(checkout_fd, self.identities[0], self.checkout)
            work_fd = _open_dir_at(checkout_fd, WORK_DIRNAME, self.work_root)
            opened.append(work_fd)
            _require_same_directory(work_fd, self.identities[1], self.work_root)
            research_fd = _open_dir_at(work_fd, RESEARCH_BATCH, self.work_root / RESEARCH_BATCH)
            opened.append(research_fd)
            _require_same_directory(research_fd, self.identities[2], self.work_root / RESEARCH_BATCH)
            session_fd = _open_dir_at(
                research_fd, self.session_id, self.work_root / RESEARCH_BATCH / self.session_id
            )
            opened.append(session_fd)
            _require_same_directory(
                session_fd, self.identities[3], self.work_root / RESEARCH_BATCH / self.session_id
            )
            output_fd = _open_dir_at(session_fd, MANUAL_PDF, self.output_root)
            opened.append(output_fd)
            _require_same_directory(output_fd, self.identities[4], self.output_root)
        finally:
            for fd in reversed(opened):
                _close_fd(fd)


def validate_session_id(raw: object) -> str:
    try:
        return validate_batch_id(raw)
    except StagingError as exc:
        raise ResearchError(INTAKE_INVALID, "session id is not a legal batch id", dict(exc.details)) from exc


@contextmanager
def open_research_session(session_id: object, *, create: bool = True) -> Iterator[RetainedResearchSession]:
    session = validate_session_id(session_id)
    checkout = resolve_checkout_root()
    work_root = checkout / WORK_DIRNAME
    research_path = work_root / RESEARCH_BATCH
    session_path = research_path / session
    output_path = session_path / MANUAL_PDF
    checkout_fd: int | None = None
    owned: list[int] = []
    try:
        checkout_fd = _open_dir_path(checkout)
        if create:
            work_fd = _ensure_dir_at(checkout_fd, WORK_DIRNAME, work_root, work_fd=None)
        else:
            work_fd = _open_dir_at(checkout_fd, WORK_DIRNAME, work_root)
        owned.append(work_fd)
        _require_work_still_in_checkout(work_fd, checkout_fd, work_root)
        opener = _ensure_dir_at if create else _open_dir_at
        if create:
            research_fd = opener(work_fd, RESEARCH_BATCH, research_path, work_fd=work_fd)
        else:
            research_fd = opener(work_fd, RESEARCH_BATCH, research_path)
        owned.append(research_fd)
        if create:
            session_fd = opener(research_fd, session, session_path, work_fd=work_fd)
        else:
            session_fd = opener(research_fd, session, session_path)
        owned.append(session_fd)
        if create:
            output_fd = opener(session_fd, MANUAL_PDF, output_path, work_fd=work_fd)
        else:
            output_fd = opener(session_fd, MANUAL_PDF, output_path)
        owned.append(output_fd)
        identities = tuple(
            os.fstat(fd) for fd in (checkout_fd, work_fd, research_fd, session_fd, output_fd)
        )
        held = RetainedResearchSession(
            checkout,
            session,
            checkout_fd,
            work_fd,
            research_fd,
            session_fd,
            output_fd,
            identities,  # type: ignore[arg-type]
        )
        held.verify()
        try:
            yield held
        except BaseException as exc:
            try:
                held.verify()
            except StagingError as unsafe:
                if unsafe.code == CODE_WORK_PATH_UNSAFE:
                    raise unsafe from exc
                raise
            raise
        else:
            held.verify()
    finally:
        for fd in reversed(owned):
            _close_fd(fd)
        _close_fd(checkout_fd)


def stage_research(session: RetainedResearchSession, relative: tuple[str, ...], data: bytes):
    session.verify()
    result = stage_bytes(
        batch_id=RESEARCH_BATCH,
        relative=(session.session_id, MANUAL_PDF, *relative),
        data=data,
    )
    session.verify()
    return result


def stage_blob(digest: str, data: bytes):
    return stage_bytes(batch_id=BLOB_BATCH, relative=(digest,), data=data)


def family_count(session: RetainedResearchSession, family: str) -> int:
    root = session.path(family)
    if not root.exists():
        return 0
    if family == "runs":
        return sum(1 for path in root.iterdir() if path.is_dir() and not path.is_symlink())
    if family == "proposals":
        return sum(
            1
            for path in root.iterdir()
            if path.is_file() and path.name.endswith(".json") and not path.name.endswith(".draft.json")
        )
    return sum(1 for path in root.iterdir() if path.is_file())


def require_family_slot(session: RetainedResearchSession, family: str, target: Path) -> None:
    if target.exists():
        return
    if family_count(session, family) >= FAMILY_LIMIT:
        raise ResearchError(INTAKE_INVALID, f"{family} family exceeds {FAMILY_LIMIT} records")


def write_document(session: RetainedResearchSession, family: str, document: dict[str, Any]):
    digest = str(document["content_sha256"])
    relative = (family, f"{digest}.json")
    target = session.path(*relative)
    require_family_slot(session, family, target)
    payload = saved_bytes(document)
    result = stage_research(session, relative, payload)
    return result, exact_ref(document)


def load_saved_document(path: Path, *, kind: str, invalid_code: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = read_regular_file(
            path,
            missing_code=invalid_code,
            unsafe_code=invalid_code,
            changed_code=SOURCE_CHANGED,
            max_bytes=8 * 1024 * 1024,
            limit_code=invalid_code,
        )
    except SecureIOError as exc:
        if exc.code == SOURCE_CHANGED:
            raise ResearchError(MANUAL_PDF_CHANGED, str(exc.message), dict(exc.details), exit_code=75) from exc
        raise ResearchError(invalid_code, str(exc.message), dict(exc.details)) from exc
    parsed = parse_envelope_json(raw, invalid_code=invalid_code)
    document = validate_document(parsed, expected_kind=kind)
    if raw != saved_bytes(document):
        raise ResearchError(invalid_code, "saved document bytes are not canonical JCS+LF")
    return document, raw


def session_from_research_path(path: Path, *, kind_dir: str) -> str:
    checkout = resolve_checkout_root()
    target = path if path.is_absolute() else (Path.cwd() / path)
    try:
        relative = target.resolve().relative_to((checkout / WORK_DIRNAME / RESEARCH_BATCH).resolve())
    except ValueError as exc:
        raise ResearchError(INTAKE_INVALID, "path is outside .work/research") from exc
    parts = relative.parts
    if len(parts) < 4 or parts[1] != MANUAL_PDF or parts[2] != kind_dir:
        raise ResearchError(INTAKE_INVALID, "path is not a manual-pdf research object")
    return validate_session_id(parts[0])


@dataclass
class RetainedSource:
    path: Path
    identity: os.stat_result
    digest: str
    data: bytes

    def verify(self) -> None:
        try:
            now = os.lstat(self.path)
        except OSError as exc:
            raise ResearchError(MANUAL_PDF_CHANGED, "source PDF is no longer available", {"path": self.path.as_posix()}) from exc
        if stamp(now) != stamp(self.identity):
            raise ResearchError(MANUAL_PDF_CHANGED, "source PDF identity changed", {"path": self.path.as_posix()})
        if stat.S_ISLNK(now.st_mode) or not stat.S_ISREG(now.st_mode) or now.st_nlink != 1:
            raise ResearchError(MANUAL_PDF_CHANGED, "source PDF is no longer a single-link regular file")
        try:
            raw = read_regular_file(
                self.path,
                missing_code=MANUAL_PDF_CHANGED,
                unsafe_code=MANUAL_PDF_CHANGED,
                changed_code=SOURCE_CHANGED,
                max_bytes=64 * 1024 * 1024,
                limit_code=MANUAL_PDF_CHANGED,
            )
        except SecureIOError as exc:
            raise ResearchError(MANUAL_PDF_CHANGED, str(exc.message), dict(exc.details), exit_code=75) from exc
        if raw != self.data or sha256_bytes(raw) != self.digest:
            raise ResearchError(MANUAL_PDF_CHANGED, "source PDF bytes changed")


def dominate_unsafe(session: RetainedResearchSession, source: RetainedSource | None, exc: BaseException) -> None:
    try:
        session.verify()
        if source is not None:
            source.verify()
    except StagingError as unsafe:
        if unsafe.code == CODE_WORK_PATH_UNSAFE:
            raise unsafe from exc
        raise
    except ResearchError:
        raise
    raise exc
